#!/usr/bin/env python3
"""
Simple PR review comment viewer (terminal version).

Fetches PR review comments (inline, file/line), general PR comments, review
summaries (e.g. "Request changes"), and the diff via the gh CLI, and prints
them grouped by file/line.

Usage:
    python3 reviewer_utility.py --pr <PR_URL> [--repo <LOCAL_REPO_PATH>]

If --pr is omitted, you'll be prompted for it. --repo is optional and only
used to show the local text of a commented-on line.
"""

import argparse
import sys

from pr_data import gather_pr_data


def print_header(text):
    print()
    print(text)
    print("-" * len(text))


def main():
    parser = argparse.ArgumentParser(description="Display GitHub PR review comments grouped by file/line.")
    parser.add_argument("--pr", help="PR URL, e.g. https://github.com/org/repo/pull/123")
    parser.add_argument("--repo", help="Optional: path to local checkout of the repo (used for line context)")
    args = parser.parse_args()

    pr_url = args.pr or input("PR URL: ").strip()
    repo_path = args.repo

    try:
        data = gather_pr_data(pr_url, repo_path)
    except (ValueError, RuntimeError) as e:
        sys.exit(str(e))

    print(f"PR: {data['owner']}/{data['repo']}#{data['pr_number']}")

    print_header("Inline review comments")
    if data["inline_by_file"]:
        for file_path in sorted(data["inline_by_file"]):
            print(f"\n  {file_path}")
            for c in data["inline_by_file"][file_path]:
                line_label = f"line {c['line']}" if c["line"] is not None else "line ?"
                print(f"    [{line_label}] {c['author']}:")
                if c["local_line"] is not None:
                    print(f"      code: {c['local_line'].strip()}")
                for body_line in c["body"].splitlines():
                    print(f"      {body_line}")
    else:
        print("  (none)")

    print_header("Reviews")
    if data["reviews"]:
        for r in data["reviews"]:
            print(f"\n  {r['author']} - {r['state']}")
            for body_line in r["body"].splitlines():
                print(f"    {body_line}")
    else:
        print("  (none)")

    print_header("General comments")
    if data["general_comments"]:
        for c in data["general_comments"]:
            print(f"\n  {c['author']}:")
            for body_line in c["body"].splitlines():
                print(f"    {body_line}")
    else:
        print("  (none)")

    print_header("Diff")
    print(data["diff"] if data["diff"].strip() else "  (no changes)")


if __name__ == "__main__":
    main()
