"""Shared logic for fetching PR review data via the gh CLI."""

import json
import re
import subprocess
import sys
from pathlib import Path


def parse_pr_url(url):
    """Extract (owner, repo, pr_number) from a GitHub PR URL."""
    match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not match:
        raise ValueError(f"Could not parse a PR URL from: {url}")
    owner, repo, pr_number = match.groups()
    return owner, repo, int(pr_number)


def gh_api(path, accept=None):
    """Call `gh api <path>` (paginated) and return parsed JSON.

    `accept` optionally overrides the request's Accept media type.
    """
    cmd = ["gh", "api", "--paginate", path]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {path} failed:\n{result.stderr.strip()}")
    output = result.stdout.strip()
    if not output:
        return []
    # --paginate concatenates one JSON array per page; merge them.
    items = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(output):
        output_slice = output[idx:].lstrip()
        if not output_slice:
            break
        idx += len(output[idx:]) - len(output_slice)
        obj, end = decoder.raw_decode(output_slice)
        items.extend(obj if isinstance(obj, list) else [obj])
        idx += end
    return items


def get_pr_diff(pr_url):
    """Return the full diff of files changed in the PR via `gh pr diff`."""
    result = subprocess.run(
        ["gh", "pr", "diff", pr_url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh pr diff failed:\n{result.stderr.strip()}")
    return result.stdout


_FILE_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


def parse_diff(diff_text):
    """Parse a unified diff (as produced by `gh pr diff`) into a list of
    per-file dicts: {old_path, new_path, binary, hunks: [{header, lines}]}.

    Each line dict is {type: "add"|"del"|"ctx", old_line, new_line, content}.
    """
    files = []
    current = None
    hunk = None
    old_line = new_line = 0

    for line in diff_text.splitlines():
        header_match = _FILE_HEADER_RE.match(line)
        if header_match:
            current = {
                "old_path": header_match.group(1),
                "new_path": header_match.group(2),
                "binary": False,
                "hunks": [],
            }
            files.append(current)
            hunk = None
            continue

        if current is None:
            continue

        if line.startswith("Binary files"):
            current["binary"] = True
            continue

        if (
            line.startswith("--- ")
            or line.startswith("+++ ")
            or line.startswith("index ")
            or line.startswith("new file mode")
            or line.startswith("deleted file mode")
            or line.startswith("old mode")
            or line.startswith("new mode")
            or line.startswith("similarity index")
            or line.startswith("rename from")
            or line.startswith("rename to")
        ):
            continue

        hunk_match = _HUNK_RE.match(line)
        if hunk_match:
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(2))
            hunk = {"header": line, "lines": []}
            current["hunks"].append(hunk)
            continue

        if hunk is None or not line:
            continue

        if line.startswith("\\"):  # "\ No newline at end of file"
            continue
        elif line.startswith("+"):
            hunk["lines"].append({"type": "add", "old_line": None, "new_line": new_line, "content": line[1:]})
            new_line += 1
        elif line.startswith("-"):
            hunk["lines"].append({"type": "del", "old_line": old_line, "new_line": None, "content": line[1:]})
            old_line += 1
        else:
            content = line[1:] if line.startswith(" ") else line
            hunk["lines"].append({"type": "ctx", "old_line": old_line, "new_line": new_line, "content": content})
            old_line += 1
            new_line += 1

    return files


def get_local_line(repo_path, file_path, line_number):
    """Best-effort fetch of a single line's text from the local repo checkout."""
    if not repo_path or line_number is None:
        return None
    full_path = Path(repo_path) / file_path
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].rstrip("\n")
    except OSError:
        return None
    return None


def list_repos():
    """Return repos the authenticated gh user has access to (owned,
    collaborator, or org member), most recently updated first."""
    items = gh_api("/user/repos?per_page=100&sort=updated")
    repos = []
    for r in items:
        full_name = r.get("full_name")
        if not full_name or "/" not in full_name:
            continue
        owner, name = full_name.split("/", 1)
        repos.append(
            {
                "owner": owner,
                "repo": name,
                "full_name": full_name,
                "private": r.get("private", False),
            }
        )
    return repos


def list_open_prs(owner, repo):
    """Return open pull requests for a single repo."""
    items = gh_api(f"/repos/{owner}/{repo}/pulls?state=open&per_page=100")
    return [
        {
            "number": p.get("number"),
            "title": p.get("title", ""),
            "author": p.get("user", {}).get("login", "unknown"),
            "url": p.get("html_url", ""),
        }
        for p in items
    ]


def approve_pr(pr_url):
    """Approve a PR via `gh pr review --approve`."""
    result = subprocess.run(
        ["gh", "pr", "review", pr_url, "--approve"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh pr review --approve failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


FULL_BODY_MEDIA_TYPE = "application/vnd.github.full+json"


def gather_pr_data(pr_url, repo_path):
    """Fetch everything needed to review a PR: inline comments, reviews,
    general comments, and the diff. Returns a plain dict."""
    owner, repo, pr_number = parse_pr_url(pr_url)

    inline_comments = gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/comments", accept=FULL_BODY_MEDIA_TYPE)
    reviews = gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/reviews", accept=FULL_BODY_MEDIA_TYPE)
    issue_comments = gh_api(f"repos/{owner}/{repo}/issues/{pr_number}/comments", accept=FULL_BODY_MEDIA_TYPE)
    diff = get_pr_diff(pr_url)

    by_file = {}
    for c in inline_comments:
        file_path = c.get("path", "(unknown file)")
        line = c.get("line") or c.get("original_line")
        local_line = get_local_line(repo_path, file_path, line)
        by_file.setdefault(file_path, []).append(
            {
                "line": line,
                "author": c.get("user", {}).get("login", "unknown"),
                "body": (c.get("body") or "").strip(),
                "local_line": local_line,
            }
        )
    for comments in by_file.values():
        comments.sort(key=lambda c: (c["line"] is None, c["line"]))

    diff_files = parse_diff(diff)
    files_by_path = {}
    for f in diff_files:
        files_by_path.setdefault(f["new_path"], f)
        files_by_path.setdefault(f["old_path"], f)
        f["line_comments"] = {}
        f["unmatched_comments"] = []
        # Index every add/ctx/del line under (side, line_number) so a comment
        # anchored to either side of a hunk can be found in one lookup.
        for hunk in f["hunks"]:
            for entry in hunk["lines"]:
                if entry["new_line"] is not None:
                    f["line_comments"].setdefault(("RIGHT", entry["new_line"]), [])
                if entry["old_line"] is not None:
                    f["line_comments"].setdefault(("LEFT", entry["old_line"]), [])

    for c in inline_comments:
        path = c.get("path", "(unknown file)")
        target = files_by_path.get(path)
        comment = {
            "author": c.get("user", {}).get("login", "unknown"),
            "body": (c.get("body") or "").strip(),
            "body_html": c.get("body_html") or "",
        }
        if target is None:
            continue
        side = c.get("side") or "RIGHT"
        line = c.get("line")
        key = (side, line) if line is not None else None
        if key is None or key not in target["line_comments"]:
            orig_side = c.get("original_side") or side
            orig_line = c.get("original_line")
            key = (orig_side, orig_line) if orig_line is not None else None
        if key is not None and key in target["line_comments"]:
            target["line_comments"][key].append(comment)
        else:
            target["unmatched_comments"].append(comment)

    review_list = [
        {
            "author": r.get("user", {}).get("login", "unknown"),
            "state": r.get("state", "?"),
            "body": (r.get("body") or "").strip(),
            "body_html": r.get("body_html") or "",
        }
        for r in reviews
    ]

    general_list = [
        {
            "author": c.get("user", {}).get("login", "unknown"),
            "body": (c.get("body") or "").strip(),
            "body_html": c.get("body_html") or "",
        }
        for c in issue_comments
    ]

    return {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "repo_path": repo_path,
        "inline_by_file": by_file,
        "reviews": review_list,
        "general_comments": general_list,
        "diff": diff,
        "diff_files": diff_files,
    }
