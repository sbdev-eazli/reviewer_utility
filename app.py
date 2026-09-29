#!/usr/bin/env python3
"""
Simple PR review comment viewer (web version).

Starts a local web server with a small form (PR URL + local repo path).
Submitting it fetches the PR's inline review comments, reviews, general
comments, and diff via the gh CLI, and displays them as a GitHub-style
tabbed view: a Conversation tab plus one tab per changed file, with review
comments anchored to their exact diff line.

Usage:
    python3 app.py [--port 8765]
"""

import argparse
import html
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pr_data import approve_pr, gather_pr_data, list_open_prs, list_repos

PAGE_STYLE = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  max-width: 1100px; margin: 0 auto; padding: 0 1rem 3rem; color: #1f2328; background: #fff;
}
code, pre, .code, .diff-table { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

.pr-header { padding: 1.25rem 0 0.75rem; border-bottom: 1px solid #d0d7de; display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.pr-header h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.pr-header .sub { color: #59636e; font-size: 0.9rem; }
.back-link { color: #0969da; text-decoration: none; font-size: 0.85rem; }
.back-link:hover { text-decoration: underline; }

.approve-btn {
  padding: 0.5rem 1rem; background: #1f883d; color: #fff; border: none;
  border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; white-space: nowrap;
}
.approve-btn:hover { background: #1a7f37; }
.banner { padding: 0.6rem 0.9rem; border-radius: 6px; font-size: 0.88rem; margin: 1rem 0; }
.banner.success { background: #dafbe1; color: #116329; border: 1px solid #4ac26b; }
.banner.error { background: #ffebe9; color: #82071e; border: 1px solid #ff8182; white-space: pre-wrap; }

.tabs {
  display: flex; gap: 0.25rem; border-bottom: 1px solid #d0d7de; overflow-x: auto;
  margin-top: 0.5rem; position: sticky; top: 0; background: #fff; z-index: 5;
}
.tab-btn {
  padding: 0.6rem 0.9rem; border: none; background: none; cursor: pointer;
  border-bottom: 2px solid transparent; font-size: 0.85rem; white-space: nowrap; color: #59636e;
}
.tab-btn:hover { color: #1f2328; background: #f6f8fa; }
.tab-btn.active { border-bottom-color: #fd8c73; font-weight: 600; color: #1f2328; }
.tab-btn .badge {
  display: inline-block; background: #eaeef2; border-radius: 999px; padding: 0 6px;
  font-size: 0.7rem; margin-left: 5px; color: #57606a;
}
.tab-btn.active .badge { background: #ffe0d3; color: #a02f00; }

.tab-panel { display: none; padding-top: 1rem; }
.tab-panel.active { display: block; }

h2 { font-size: 1rem; margin: 1.5rem 0 0.5rem; }
h2:first-child { margin-top: 0; }

.comment {
  margin: 0.6rem 0; padding: 0.6rem 0.8rem; border: 1px solid #d0d7de; border-radius: 6px; background: #fff;
}
.comment .meta { font-size: 0.8rem; color: #59636e; margin-bottom: 0.3rem; }
.comment .author { font-weight: 600; color: #1f2328; }
.comment .body { font-size: 0.88rem; line-height: 1.5; white-space: pre-wrap; }
.comment .body.markdown { white-space: normal; overflow-wrap: anywhere; }
.markdown > :first-child { margin-top: 0; }
.markdown > :last-child { margin-bottom: 0; }
.markdown p, .markdown ul, .markdown ol, .markdown blockquote, .markdown pre, .markdown table { margin: 0 0 0.6rem; }
.markdown ul, .markdown ol { padding-left: 1.6rem; }
.markdown h1, .markdown h2, .markdown h3, .markdown h4 { font-size: 1rem; margin: 0.8rem 0 0.4rem; }
.markdown a { color: #0969da; }
.markdown code { background: #eff1f3; padding: 0.1em 0.35em; border-radius: 4px; font-size: 85%; }
.markdown pre { background: #f6f8fa; padding: 0.6rem 0.8rem; border-radius: 6px; overflow-x: auto; }
.markdown pre code { background: none; padding: 0; font-size: 12px; }
.markdown blockquote { color: #59636e; border-left: 3px solid #d0d7de; padding: 0 0.8rem; }
.markdown table { border-collapse: collapse; display: block; overflow-x: auto; }
.markdown th, .markdown td { border: 1px solid #d0d7de; padding: 0.25rem 0.6rem; }
.markdown img { max-width: 100%; }
.markdown details { margin: 0 0 0.6rem; }
.markdown .task-list-item { list-style: none; }
.markdown .task-list-item input { margin: 0 0.3rem 0 -1.3rem; }
.state-CHANGES_REQUESTED { color: #cf222e; font-weight: 600; }
.state-APPROVED { color: #1a7f37; font-weight: 600; }
.state-COMMENTED { color: #57606a; font-weight: 600; }
.empty { color: #59636e; font-size: 0.88rem; padding: 0.5rem 0; }

.file-header {
  display: flex; align-items: baseline; gap: 0.6rem; padding: 0.5rem 0.2rem;
  font-size: 0.9rem; font-weight: 600; border-bottom: 1px solid #d0d7de; margin-bottom: 0.5rem;
}
.file-header .path { word-break: break-all; }
.file-header .note { font-weight: 400; color: #59636e; font-size: 0.82rem; }

table.diff-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 1.5rem; border: 1px solid #d0d7de; border-radius: 6px; overflow: hidden; }
table.diff-table td { padding: 0 8px; vertical-align: top; }
tr.hunk-header td { background: #f6f8fa; color: #59636e; padding: 4px 8px; font-size: 11px; }
td.linenum { width: 42px; text-align: right; color: #8c959f; user-select: none; border-right: 1px solid #eee; white-space: nowrap; }
td.marker { width: 16px; text-align: center; user-select: none; }
td.code { white-space: pre-wrap; word-break: break-word; width: 100%; }
tr.line-add td.code, tr.line-add td.marker { background: #e6ffec; }
tr.line-del td.code, tr.line-del td.marker { background: #ffebe9; }
tr.line-add td.linenum { background: #ccffd8; }
tr.line-del td.linenum { background: #ffd7d5; }
tr.line-add .marker { color: #1a7f37; }
tr.line-del .marker { color: #cf222e; }

tr.comment-row td { background: #f6f8fa; padding: 0.6rem 0.8rem; border-top: 1px solid #d0d7de; border-bottom: 1px solid #d0d7de; }
tr.comment-row .comment { background: #fff; }
.unmatched-comments { margin-top: 0.5rem; }
.unmatched-comments .hint { font-size: 0.8rem; color: #59636e; margin-bottom: 0.3rem; }

form label { display: block; margin-top: 1rem; font-size: 0.9rem; }
input[type=text] { width: 100%; padding: 0.5rem; font-family: monospace; margin-top: 0.25rem; border: 1px solid #d0d7de; border-radius: 6px; }
input[type=submit] {
  margin-top: 1.1rem; padding: 0.5rem 1.1rem; background: #1f883d; color: #fff; border: none;
  border-radius: 6px; cursor: pointer; font-size: 0.9rem;
}
input[type=submit]:hover { background: #1a7f37; }
.error { color: #cf222e; white-space: pre-wrap; margin-top: 1rem; }

.nav-link { color: #0969da; text-decoration: none; font-size: 0.85rem; }
.nav-link:hover { text-decoration: underline; }
.repo-list, .pr-list { list-style: none; padding: 0; margin: 1rem 0; }
.repo-list li, .pr-list li {
  padding: 0.6rem 0.8rem; border: 1px solid #d0d7de; border-radius: 6px; margin-bottom: 0.5rem;
}
.repo-list a, .pr-list a { color: #0969da; text-decoration: none; font-weight: 600; }
.repo-list a:hover, .pr-list a:hover { text-decoration: underline; }
.repo-list .visibility { color: #59636e; font-size: 0.78rem; margin-left: 0.5rem; font-weight: 400; }
.pr-list .pr-meta { color: #59636e; font-size: 0.8rem; }
"""

TAB_SCRIPT = """
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(function (el) { el.classList.remove('active'); });
  document.querySelectorAll('.tab-btn').forEach(function (el) { el.classList.remove('active'); });
  document.getElementById(id).classList.add('active');
  document.querySelector('.tab-btn[data-tab="' + id + '"]').classList.add('active');
}
document.querySelectorAll('.tab-btn').forEach(function (btn) {
  btn.addEventListener('click', function () { showTab(btn.dataset.tab); });
});
"""


def esc(text):
    return html.escape(text or "", quote=True)


def render_form(pr_url="", repo_path="", error=""):
    error_html = f'<p class="error">{esc(error)}</p>' if error else ""
    return f"""
<html>
<head><title>PR Review Viewer</title><style>{PAGE_STYLE}</style></head>
<body>
<div class="pr-header">
  <h1>PR Review Viewer</h1>
  <div class="sub"><a class="nav-link" href="/repos">Browse repos &amp; open PRs &raquo;</a></div>
</div>
<form method="POST" action="/">
  <label>PR URL
    <input type="text" name="pr_url" placeholder="https://github.com/org/repo/pull/123" value="{esc(pr_url)}" required>
  </label>
  <label>Local repo path (optional)
    <input type="text" name="repo_path" placeholder="/path/to/local/checkout" value="{esc(repo_path)}">
  </label>
  <input type="submit" value="Load PR">
</form>
{error_html}
</body>
</html>
"""


def render_repo_list(repos, error=""):
    error_html = f'<p class="error">{esc(error)}</p>' if error else ""
    items = []
    for r in repos:
        visibility = "private" if r["private"] else "public"
        items.append(
            "<li>"
            f'<a href="/repos?owner={esc(r["owner"])}&repo={esc(r["repo"])}">{esc(r["full_name"])}</a>'
            f'<span class="visibility">{visibility}</span>'
            "</li>"
        )
    body = "".join(items) if items else '<p class="empty">No repos found.</p>'
    return f"""
<html>
<head><title>Repos - PR Review Viewer</title><style>{PAGE_STYLE}</style></head>
<body>
<div class="pr-header">
  <h1>Repos</h1>
  <div class="sub"><a class="nav-link" href="/">&laquo; back to PR URL form</a></div>
</div>
{error_html}
<ul class="repo-list">{body}</ul>
</body>
</html>
"""


def render_repo_prs(owner, repo, prs, error=""):
    error_html = f'<p class="error">{esc(error)}</p>' if error else ""
    items = []
    for pr in prs:
        items.append(
            "<li>"
            f'<a href="/?pr_url={esc(pr["url"])}">#{pr["number"]} {esc(pr["title"])}</a>'
            f'<div class="pr-meta">opened by {esc(pr["author"])}</div>'
            "</li>"
        )
    body = "".join(items) if items else '<p class="empty">No open pull requests.</p>'
    return f"""
<html>
<head><title>{esc(owner)}/{esc(repo)} - PR Review Viewer</title><style>{PAGE_STYLE}</style></head>
<body>
<div class="pr-header">
  <h1>{esc(owner)}/{esc(repo)} - open PRs</h1>
  <div class="sub"><a class="nav-link" href="/repos">&laquo; back to repos</a></div>
</div>
{error_html}
<ul class="pr-list">{body}</ul>
</body>
</html>
"""


def render_body(item):
    if item.get("body_html"):
        return f'<div class="body markdown">{item["body_html"]}</div>'
    return f'<div class="body">{esc(item["body"])}</div>'


def render_comment(c):
    return (
        '<div class="comment">'
        f'<div class="meta"><span class="author">{esc(c["author"])}</span></div>'
        f"{render_body(c)}"
        "</div>"
    )


def render_conversation_tab(data, active):
    parts = [f'<section id="conversation" class="tab-panel{" active" if active else ""}">']

    parts.append("<h2>Reviews</h2>")
    if data["reviews"]:
        for r in data["reviews"]:
            parts.append('<div class="comment">')
            parts.append(
                f'<div class="meta"><span class="author">{esc(r["author"])}</span> - '
                f'<span class="state-{esc(r["state"])}">{esc(r["state"])}</span></div>'
            )
            if r["body"]:
                parts.append(render_body(r))
            parts.append("</div>")
    else:
        parts.append('<p class="empty">No reviews.</p>')

    parts.append("<h2>General comments</h2>")
    if data["general_comments"]:
        for c in data["general_comments"]:
            parts.append(render_comment(c))
    else:
        parts.append('<p class="empty">No general comments.</p>')

    parts.append("</section>")
    return "".join(parts)


def render_diff_line_row(entry):
    if entry["type"] == "add":
        row_class, marker, old_num, new_num = "line-add", "+", "", entry["new_line"]
    elif entry["type"] == "del":
        row_class, marker, old_num, new_num = "line-del", "-", entry["old_line"], ""
    else:
        row_class, marker, old_num, new_num = "line-ctx", "", entry["old_line"], entry["new_line"]
    return (
        f'<tr class="{row_class}">'
        f'<td class="linenum">{old_num}</td>'
        f'<td class="linenum">{new_num}</td>'
        f'<td class="marker">{marker}</td>'
        f'<td class="code">{esc(entry["content"])}</td>'
        "</tr>"
    )


def render_comment_thread_row(comments):
    body = "".join(render_comment(c) for c in comments)
    return f'<tr class="comment-row"><td colspan="4"><div class="thread">{body}</div></td></tr>'


def render_file_tab(tab_id, file_data, active):
    path = file_data["new_path"]
    is_added = file_data["old_path"] == "/dev/null"
    is_deleted = file_data["new_path"] == "/dev/null"
    display_path = file_data["old_path"] if is_deleted else path
    note = ""
    if is_added:
        note = "added"
    elif is_deleted:
        note = "deleted"
    elif file_data["old_path"] != file_data["new_path"]:
        note = f'renamed from {esc(file_data["old_path"])}'

    parts = [f'<section id="{tab_id}" class="tab-panel{" active" if active else ""}">']
    parts.append(
        '<div class="file-header">'
        f'<span class="path">{esc(display_path)}</span>'
        + (f'<span class="note">{note}</span>' if note else "")
        + "</div>"
    )

    if file_data["binary"]:
        parts.append('<p class="empty">Binary file not shown.</p>')
    elif not file_data["hunks"]:
        parts.append('<p class="empty">No textual changes to display.</p>')
    else:
        parts.append('<table class="diff-table">')
        for hunk in file_data["hunks"]:
            parts.append(f'<tr class="hunk-header"><td colspan="4">{esc(hunk["header"])}</td></tr>')
            for entry in hunk["lines"]:
                parts.append(render_diff_line_row(entry))
                side_line_pairs = []
                if entry["new_line"] is not None:
                    side_line_pairs.append(("RIGHT", entry["new_line"]))
                if entry["old_line"] is not None:
                    side_line_pairs.append(("LEFT", entry["old_line"]))
                seen = set()
                for key in side_line_pairs:
                    comments = file_data["line_comments"].get(key)
                    if comments and key not in seen:
                        seen.add(key)
                        parts.append(render_comment_thread_row(comments))
        parts.append("</table>")

    if file_data["unmatched_comments"]:
        parts.append('<div class="unmatched-comments">')
        parts.append('<div class="hint">Additional comments (anchored to a line outside this diff view):</div>')
        for c in file_data["unmatched_comments"]:
            parts.append(render_comment(c))
        parts.append("</div>")

    parts.append("</section>")
    return "".join(parts)


def render_results(data, banner=""):
    diff_files = data["diff_files"]

    tab_buttons = ['<button class="tab-btn active" data-tab="conversation">Conversation</button>']
    panels = [render_conversation_tab(data, active=True)]

    for idx, f in enumerate(diff_files):
        tab_id = f"file-{idx}"
        count = sum(len(v) for v in f["line_comments"].values()) + len(f["unmatched_comments"])
        badge = f'<span class="badge">{count}</span>' if count else ""
        label = f["old_path"] if f["new_path"] == "/dev/null" else f["new_path"]
        tab_buttons.append(
            f'<button class="tab-btn" data-tab="{tab_id}" title="{esc(label)}">{esc(label)}{badge}</button>'
        )
        panels.append(render_file_tab(tab_id, f, active=False))

    header = (
        '<div class="pr-header">'
        '<div>'
        f'<h1>{esc(data["owner"])}/{esc(data["repo"])} #{data["pr_number"]}</h1>'
        f'<div class="sub"><a class="back-link" href="/">&laquo; load another PR</a></div>'
        "</div>"
        '<form method="POST" action="/approve" onsubmit="return confirm(\'Approve this pull request?\');">'
        f'<input type="hidden" name="pr_url" value="{esc(data["pr_url"])}">'
        f'<input type="hidden" name="repo_path" value="{esc(data["repo_path"])}">'
        '<button type="submit" class="approve-btn">Approve</button>'
        "</form>"
        "</div>"
    )

    banner_html = ""
    if banner:
        cls, text = banner
        banner_html = f'<div class="banner {cls}">{esc(text)}</div>'

    return (
        "<html><head><title>PR Review Viewer</title>"
        f"<style>{PAGE_STYLE}</style></head><body>"
        f"{header}"
        f"{banner_html}"
        f'<div class="tabs">{"".join(tab_buttons)}</div>'
        f'<div class="tab-content">{"".join(panels)}</div>'
        f"<script>{TAB_SCRIPT}</script>"
        "</body></html>"
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep the terminal quiet

    def _send_html(self, body, status=200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            fields = parse_qs(parsed.query)
            pr_url = fields.get("pr_url", [""])[0]
            repo_path = fields.get("repo_path", [""])[0]
            if pr_url:
                try:
                    data = gather_pr_data(pr_url, repo_path)
                except (ValueError, RuntimeError) as e:
                    self._send_html(render_form(pr_url, repo_path, error=str(e)))
                    return
                self._send_html(render_results(data))
            else:
                self._send_html(render_form(pr_url, repo_path))
        elif parsed.path == "/repos":
            fields = parse_qs(parsed.query)
            owner = fields.get("owner", [""])[0]
            repo = fields.get("repo", [""])[0]
            if owner and repo:
                try:
                    prs = list_open_prs(owner, repo)
                except RuntimeError as e:
                    self._send_html(render_repo_prs(owner, repo, [], error=str(e)))
                    return
                self._send_html(render_repo_prs(owner, repo, prs))
            else:
                try:
                    repos = list_repos()
                except RuntimeError as e:
                    self._send_html(render_repo_list([], error=str(e)))
                    return
                self._send_html(render_repo_list(repos))
        else:
            self._send_html("Not found", status=404)

    def do_POST(self):
        if self.path == "/":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            fields = parse_qs(body)
            pr_url = fields.get("pr_url", [""])[0].strip()
            repo_path = fields.get("repo_path", [""])[0].strip()

            try:
                data = gather_pr_data(pr_url, repo_path)
            except (ValueError, RuntimeError) as e:
                self._send_html(render_form(pr_url, repo_path, error=str(e)))
                return

            self._send_html(render_results(data))
        elif self.path == "/approve":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            fields = parse_qs(body)
            pr_url = fields.get("pr_url", [""])[0].strip()
            repo_path = fields.get("repo_path", [""])[0].strip()

            banner = None
            try:
                approve_pr(pr_url)
                banner = ("success", "Pull request approved.")
            except RuntimeError as e:
                banner = ("error", str(e))

            try:
                data = gather_pr_data(pr_url, repo_path)
            except (ValueError, RuntimeError) as e:
                self._send_html(render_form(pr_url, repo_path, error=str(e)))
                return

            self._send_html(render_results(data, banner=banner))
        else:
            self._send_html("Not found", status=404)


def main():
    parser = argparse.ArgumentParser(description="Local web app for viewing GitHub PR review comments.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving on {url} (Ctrl+C to stop)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
