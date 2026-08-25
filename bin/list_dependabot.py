#!/usr/bin/env python3
"""
List Dependabot alerts and PRs for every repository where a named team is maintainer.

Usage:
    export GH_TOKEN="ghp_xxxxxxxxxxxxxxxx"
    python dependabot_team_report.py --org MY_ORG --team Nisse
"""

import argparse
import json
import os
import urllib.request
from multiprocessing import Pool

API = "https://api.github.com"
TOKEN = os.getenv("GH_TOKEN")
if not TOKEN:
    msg = "GH_TOKEN not set"
    raise SystemExit(msg)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"
CHECK_MARK = "\u2713"

CHECK_STATUS_COLOR = {"success": GREEN, "failure": RED, "pending": YELLOW}


def hyperlink(url: str, text: str) -> str:
    """Return text as a clickable terminal hyperlink using an OSC 8 escape sequence."""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def _get(url: str, params: dict | None = None) -> list[dict]:
    """Return all pages of results for a GitHub REST endpoint."""
    items = []
    page = 1
    while True:
        p = (params or {}).copy()
        p.update({"per_page": 100, "page": page})
        query = "&".join(f"{k}={v}" for k, v in p.items())
        request_url = f"{url}?{query}"

        req = urllib.request.Request(request_url, headers=HEADERS)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=2) as response:  # noqa: S310
                data = json.loads(response.read().decode())
                if not data:
                    break
                items.extend(data)
                page += 1
        except Exception:  # noqa: BLE001
            return []
    return items


def repos_for_team(org: str, team_slug: str) -> list[dict]:
    """Fetch repositories where the team has maintainer permission, filtering out archived repositories."""
    url = f"{API}/orgs/{org}/teams/{team_slug}/repos"
    repos = _get(url)  # team/repositories endpoint

    # Filter out archived repositories and those without maintain permission
    return [
        r
        for r in repos
        if not r.get("archived", False)
        and r.get("permissions", {}).get("maintain") is True
    ]


def dependabot_enabled(owner: str, repo: str) -> bool:
    """Check if Dependabot security updates are enabled for a repository."""
    url = f"{API}/repos/{owner}/{repo}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)  # noqa: S310
        with urllib.request.urlopen(req, timeout=2) as response:  # noqa: S310
            data = json.loads(response.read().decode())
            return (
                data["security_and_analysis"]["dependabot_security_updates"]["status"]
                == "enabled"
            )
    except KeyError:
        return False


def open_alerts(owner: str, repo: str) -> list[dict]:
    """Fetch open Dependabot alerts for a repository."""
    url = f"{API}/repos/{owner}/{repo}/dependabot/alerts"
    params = {"state": "open", "per_page": 100}
    alerts = []
    while True:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        request_url = f"{url}?{query}"
        req = urllib.request.Request(request_url, headers=HEADERS)  # noqa: S310

        try:
            with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
                if response.getcode() == 403:
                    break
                batch = json.loads(response.read().decode())
                if not batch:
                    break
                alerts.extend(batch)

                link = response.headers.get("Link", "")
                if 'rel="next"' not in link:
                    break
                next_url = None
                for part in link.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip("<> ")
                        break
                if not next_url:
                    break
                url = next_url
                params = None
        except Exception:  # noqa: BLE001
            break
    return alerts


def open_prs(owner: str, repo: str) -> list[dict]:
    """Fetch open PRs created by Dependabot."""
    url = f"{API}/repos/{owner}/{repo}/pulls"
    prs = _get(url, {"state": "open"})
    return [p for p in prs if p["user"]["login"] == "dependabot[bot]"]


def checks_status(owner: str, repo: str, sha: str) -> str:
    """Return the combined CI status for a commit: success, failure, pending, or unknown."""
    url = f"{API}/repos/{owner}/{repo}/commits/{sha}/check-runs"
    req = urllib.request.Request(url, headers=HEADERS)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
            runs = json.loads(response.read().decode()).get("check_runs", [])
    except Exception:  # noqa: BLE001
        return "unknown"

    if not runs:
        return "unknown"
    if any(r["status"] != "completed" for r in runs):
        return "pending"
    if any(
        r["conclusion"] in ("failure", "cancelled", "timed_out", "action_required")
        for r in runs
    ):
        return "failure"
    return "success"


def pr_mergeable_state(owner: str, repo: str, number: int) -> str:
    """Return the mergeable_state of a PR (e.g. 'clean' when ready to merge)."""
    url = f"{API}/repos/{owner}/{repo}/pulls/{number}"
    req = urllib.request.Request(url, headers=HEADERS)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
            return json.loads(response.read().decode()).get("mergeable_state", "")
    except Exception:  # noqa: BLE001
        return ""


def process_repo(r: dict) -> str | None:
    """Process a single repository and return formatted output if alerts or PRs exist."""
    owner, name = r["owner"]["login"], r["name"]

    # Check if Dependabot security updates are enabled
    enabled = dependabot_enabled(owner, name)

    alerts = open_alerts(owner, name)
    prs = open_prs(owner, name)

    if not alerts and not prs and enabled:
        return None

    lines = [f"\n{name} ({owner})"]

    # Add warning if Dependabot security updates are not enabled
    if not enabled:
        settings_url = f"https://github.com/{owner}/{name}/settings/security_analysis"
        lines.append(
            f"  ALERT  Dependabot security updates are not enabled for this repository\t{hyperlink(settings_url, settings_url)}"
        )

    lines.extend(
        [
            f"  ALERT  {a['security_advisory']['severity']}\t{a['security_advisory']['summary']}\t{hyperlink(a['html_url'], a['html_url'])}"
            for a in alerts
        ]
    )

    for p in prs:
        status = checks_status(owner, name, p["head"]["sha"])
        color = CHECK_STATUS_COLOR.get(status, "")
        reset = RESET if color else ""
        ready = CHECK_MARK if pr_mergeable_state(owner, name, p["number"]) == "clean" else " "
        lines.append(
            f"  PR  {ready}  {color}{p['title']}{reset}  {hyperlink(p['html_url'], p['html_url'])}"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dependabot overview for a team")
    parser.add_argument("--org", help="GitHub organisation", default="CL-Products")
    parser.add_argument("--team", help="Team slug", default="devops")
    args = parser.parse_args()

    repos = repos_for_team(args.org, args.team)
    if not repos:
        print(f"No repositories found where {args.team} is maintainer")
        return

    with Pool() as pool:
        results = pool.map(process_repo, repos)

    for result in results:
        if result:
            print(result)


if __name__ == "__main__":
    main()
