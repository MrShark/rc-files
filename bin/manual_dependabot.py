#!/usr/bin/env python3
"""
Manually create a dependency-update.

Create a branch, bump one package with Poetry, and open a draft pull request.

Usage:
    python manual_dependabot.py <package> <jira-id>

Example:
    python manual_dependabot.py requests PLAT-123

"""

import argparse
import json
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Run a shell command and return the CompletedProcess."""
    return subprocess.run(cmd, check=check, capture_output=True)  # noqa: S603


def fetch_cve_summary(cve_id: str) -> str:
    """Return a wrapped CVE block string for use in commit messages and PR bodies."""
    url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
            data = json.loads(response.read().decode())
        descriptions = data["vulnerabilities"][0]["cve"]["descriptions"]
        for entry in descriptions:
            if entry.get("lang") == "en":
                summary = entry["value"]
                break
        else:
            summary = ""
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as exc:
        print(f"Warning: could not fetch CVE summary: {exc}", file=sys.stderr)
        summary = ""

    cve_header = f"{cve_id}:"
    wrapped = textwrap.fill(
        f"{cve_header} {summary}",
        width=80,
        subsequent_indent=" " * (len(cve_header) + 1),
    )
    return f"\n\n{wrapped}"


def assert_clean_working_tree() -> None:
    """Abort if there are uncommitted changes in the repository."""
    result = run(["git", "status", "--porcelain"])
    if result.stdout.strip():
        print(
            "Uncommitted changes detected. Please commit or stash them first.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """Create an update branch, bump the package, commit and open a draft PR."""
    parser = argparse.ArgumentParser(
        description="Manually bump a Python package and open a draft PR."
    )
    parser.add_argument("package", help="Python package name to update")
    parser.add_argument("jira_id", help="Jira issue ID (e.g. PLAT-123)")
    parser.add_argument(
        "--cve", help="CVE identifier to include in commit and PR (e.g. CVE-2024-1234)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare the commit but do not push the branch or create the PR",
    )
    args = parser.parse_args()

    package: str = args.package
    jira_id: str = args.jira_id
    cve: str | None = args.cve
    dry_run: bool = args.dry_run
    branch = f"wip-sejenpe-{jira_id}-update_{package}"

    assert_clean_working_tree()

    run(["git", "checkout", "main"])
    run(["git", "pull", "--prune"])

    run(["git", "checkout", "-b", branch])

    run(["poetry", "update", package])

    changed = run(["git", "diff", "--name-only"]).stdout.decode().strip()
    if not changed:
        print(
            f"No files changed after 'poetry update {package}'. Nothing to commit.",
            file=sys.stderr,
        )
        run(["git", "checkout", "main"])
        run(["git", "branch", "-d", branch])
        sys.exit(1)

    print("Changed files:")
    for f in changed.splitlines():
        print(f"  {f}")

    cve_block = fetch_cve_summary(cve) if cve else ""
    commit_msg = (
        f"Update {package}\n\nJira-Id: {jira_id}"
        if not cve_block
        else f"Update {package}{cve_block}\n\nJira-Id: {jira_id}"
    )
    run(["git", "add", "--update"])
    run(["git", "commit", "--message", commit_msg])

    if dry_run:
        print("\nDry run: branch committed locally but not pushed. No PR created.")
        return

    run(["git", "push", "--set-upstream", "origin", branch])

    pr_title = f"Update {package}"
    pr_body = (
        f"Jira-Id: {jira_id}"
        if not cve_block
        else f"{cve_block.strip()}\n\nJira-Id: {jira_id}"
    )
    run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--title",
            pr_title,
            "--body",
            pr_body,
            "--base",
            "main",
        ]
    )

    print(f"\nDraft PR created for branch '{branch}'.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(), file=sys.stderr)
        sys.exit(e.returncode)
