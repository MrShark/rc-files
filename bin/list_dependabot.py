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


# --------------------------------------------------------------------------- #
# Helper: paginated GET
# --------------------------------------------------------------------------- #
def _get(url: str, params: dict | None = None) -> list[dict]:
    """Return all pages of results for a GitHub REST endpoint."""
    items = []
    page = 1
    while True:
        p = (params or {}).copy()
        p.update({"per_page": 100, "page": page})
        # Construct URL with query parameters
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
        except Exception:
            return []
    return items


# --------------------------------------------------------------------------- #
# Fetch repositories where the team has maintainer permission
# --------------------------------------------------------------------------- #
def repos_for_team(org: str, team_slug: str) -> list[dict]:
    url = f"{API}/orgs/{org}/teams/{team_slug}/repos"
    repos = _get(url)  # team/repositories endpoint
    # Keep only those with maintainer rights
    return [r for r in repos if r.get("permissions", {}).get("maintain") is True]


# --------------------------------------------------------------------------- #
# Fetch open Dependabot alerts for a repository
# --------------------------------------------------------------------------- #
def open_alerts(owner: str, repo: str) -> list[dict]:
    """
    Fetch open Dependabot alerts for a repository.

    Cursor-based pagination is required; GitHub removed offset pagination.
    """
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

                # 'Link' header contains 'rel="next"' URL if more pages exist
                link = response.headers.get("Link", "")
                if 'rel="next"' not in link:
                    break
                # Parse next URL from Link header
                next_url = None
                for part in link.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip("<> ")
                        break
                if not next_url:
                    break
                url = next_url
                params = None  # next_url already contains all params
        except Exception:
            break
    return alerts


# --------------------------------------------------------------------------- #
# Fetch open PRs created by Dependabot
# --------------------------------------------------------------------------- #
def open_prs(owner: str, repo: str) -> list[dict]:
    url = f"{API}/repos/{owner}/{repo}/pulls"
    prs = _get(url, {"state": "open"})
    return [p for p in prs if p["user"]["login"] == "dependabot[bot]"]


# --------------------------------------------------------------------------- #
# Main routine
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Dependabot overview for a team")
    parser.add_argument("--org", help="GitHub organisation", default="CL-Products")
    parser.add_argument("--team", help="Team slug", default="devops")
    args = parser.parse_args()

    repos = repos_for_team(args.org, args.team)
    if not repos:
        print(f"No repositories found where {args.team} is maintainer")
        return

    for r in repos:
        owner, name = r["owner"]["login"], r["name"]

        alerts = open_alerts(owner, name)
        prs = open_prs(owner, name)

        if not alerts and not prs:
            continue

        print(f"\n{name} ({owner})")

        for a in alerts:
            print(
                f"  ALERT  {a['security_advisory']['ghsa_id']}  {a['security_advisory']['severity']}"
            )

        for p in prs:
            print(f"  PR     {p['title']}  {p['html_url']}")


if __name__ == "__main__":
    main()
