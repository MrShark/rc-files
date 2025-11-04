#!/usr/bin/env python3
"""disk_status.py - check disk usage on remote Linux hosts."""

import argparse
import pathlib
import subprocess
import sys

CONFIG_FILE = pathlib.Path.home() / ".disk_status"
WARN_THRESHOLD = 90

# ANSI colours
BLACK = "\033[30m"
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def read_config() -> list:
    servers = []
    if CONFIG_FILE.exists():
        for raw in CONFIG_FILE.read_text().splitlines():
            line = raw.split("#")[0].strip()
            if line:
                servers.append(line)
    return servers


def run_df(hostspec: str) -> list:
    cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=5",
        hostspec,
        "df -hPx tmpfs -x devtmpfs -x proc -x sysfs -x cgroup -x squashfs",
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)  # noqa: S603
    except subprocess.CalledProcessError as e:
        print(
            RED
            + f"SSH failed for {hostspec}: "
            + e.output.decode(errors="replace").rstrip()
            + RESET
        )
        return []
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) >= 6:
            rows.append(
                {
                    "fs": parts[0],
                    "use_pct": int(parts[4].rstrip("%")),
                    "mount": parts[5],
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "hosts", nargs="*", help="user@host entries (omit to use ~/.disk_status)"
    )
    args = parser.parse_args()

    hosts = args.hosts if args.hosts else read_config()
    if not hosts:
        sys.exit("No hosts given and none found in " + str(CONFIG_FILE))

    for hostspec in hosts:
        print(BLACK + f"\n--- {hostspec} ---" + RESET)
        for r in run_df(hostspec):
            col = GREEN if r["use_pct"] <= WARN_THRESHOLD else RED
            print(col + f"{r['mount']:30} {r['use_pct']:3}% used" + RESET)
            if r["use_pct"] > WARN_THRESHOLD:
                print(col + f"⚠  WARNING: {r['mount']} above {WARN_THRESHOLD}%" + RESET)

    print("\nChecks complete.")


if __name__ == "__main__":
    main()
