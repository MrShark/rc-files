#!/usr/bin/env python3
"""
Amend the last commit message with a Jira ID and push the change.

Usage:
    python script.py <PR> <JIRA_CASE>
"""

import argparse
import subprocess
import sys


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Run a shell command and return the CompletedProcess."""
    return subprocess.run(cmd, check=check, capture_output=True)  # noqa: S603


def main() -> None:
    """Amend Pull request with Jira ID."""
    parser = argparse.ArgumentParser(description="Amend pull request with Jira ID.")
    parser.add_argument("pr", help="GitHub pull-request number")
    parser.add_argument("jira_case", help="Jira case identifier")
    parser.add_argument(
        "-m", "--merge", action="store_true", help="Aprove and merge the pr"
    )
    parser.add_argument(
        "-s",
        "--sync",
        action="store_true",
        help="Update pre-commit config to use new versions of ruff and deptry",
    )
    args = parser.parse_args()

    run(["git", "checkout", "main"])
    run(["git", "pull"])
    run(["gh", "pr", "checkout", args.pr])

    if args.sync:
        run(["pre-commit", "autoupdate"])
        run(["git", "add", ".pre-commit-config.yaml"])

    old_msg = run(["git", "log", "--format=%B", "-n1"]).stdout.decode().strip()
    new_msg = f"{old_msg}\n\nJira-Id: {args.jira_case}"

    run(["git", "commit", "--amend", "--message", new_msg])
    run(["git", "push", "--force"])

    if args.merge:
        run(["gh", "pr", "review", "--approve", "-b", ""])
        run(["gh", "pr", "merge", "--rebase"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(), file=sys.stderr)
        sys.exit(e.returncode)
