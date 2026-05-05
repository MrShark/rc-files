#!/usr/bin/env python3
"""
update_project.py — Update dependencies in a Poetry-managed Python project.

Creates a new branch, runs poetry update and pre-commit/prek autoupdate,
stages the changed files, and commits with a message that lists every
version change.

Extend by subclassing Updater and appending an instance to UPDATERS.
"""

import argparse
import re
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import ClassVar

import tomllib

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run *cmd* and return the CompletedProcess; raise on non-zero exit."""
    return subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603


def git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return run(["git", *args])


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# Updater base class
# ---------------------------------------------------------------------------


class Updater(ABC):
    """
    Base class for a tool that updates pinned dependency versions.

    To add a new tool:
      1. Subclass Updater.
      2. Implement all abstract methods.
      3. Append an instance to UPDATERS at the bottom of this file.
    """

    name: str = ""
    message_header: str = ""

    @abstractmethod
    def is_applicable(self) -> bool:
        """Return True if this updater applies to the current directory."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the required CLI tool is installed."""

    @abstractmethod
    def capture_state(self) -> dict[str, str]:
        """Snapshot current version pins; the result is passed to describe_changes."""

    @abstractmethod
    def update(self) -> None:
        """Run the actual update command (raises on failure)."""

    @abstractmethod
    def tracked_files(self) -> list[str]:
        """Return project-relative paths of files modified by this updater."""

    @abstractmethod
    def describe_changes(
        self, before: dict[str, str], after: dict[str, str]
    ) -> list[str]:
        """Return a human-readable list of change lines (may be empty)."""


# ---------------------------------------------------------------------------
# Concrete updaters
# ---------------------------------------------------------------------------


class PoetryUpdater(Updater):
    """Updates packages pinned in poetry.lock via `poetry update`."""

    name = "Poetry"
    message_header = "Poetry dependencies"

    def is_applicable(self) -> bool:  # noqa: D102
        cwd = Path.cwd()
        return (cwd / "pyproject.toml").exists() and (cwd / "poetry.lock").exists()

    def is_available(self) -> bool:  # noqa: D102
        return command_exists("poetry")

    # -- internal -----------------------------------------------------------

    def _parse_lock(self) -> dict[str, str]:
        content = (Path.cwd() / "poetry.lock").read_text()
        data = tomllib.loads(content)
        return {p["name"]: p["version"] for p in data.get("package", [])}

    # -- Updater interface --------------------------------------------------

    def capture_state(self) -> dict[str, str]:  # noqa: D102
        return self._parse_lock()

    def update(self) -> None:  # noqa: D102
        try:
            run(["poetry", "update"])
        except subprocess.CalledProcessError as exc:
            print(exc.stderr, file=sys.stderr)
            msg = "poetry update failed"
            raise RuntimeError(msg) from exc

    def tracked_files(self) -> list[str]:  # noqa: D102
        return ["poetry.lock"]

    def describe_changes(  # noqa: D102
        self, before: dict[str, str], after: dict[str, str]
    ) -> list[str]:
        lines = []
        for pkg in sorted(set(before) | set(after)):
            bv, av = before.get(pkg), after.get(pkg)
            if bv == av:
                continue
            if bv is None:
                lines.append(f"  + {pkg} {av} (added)")
            elif av is None:
                lines.append(f"  - {pkg} {bv} (removed)")
            else:
                lines.append(f"  {pkg}: {bv} -> {av}")
        return lines


class HookUpdater(Updater):
    """Updates hooks pinned in .pre-commit-config.yaml or prek.toml via prek or pre-commit."""

    name = "Hooks"
    message_header = "Hooks for pre-commit/prek"

    # Preference order: prek is tried first, then pre-commit
    _CMD_SUBCMD: ClassVar[dict[str, str]] = {
        "prek": "auto-update",
        "pre-commit": "autoupdate",
    }
    # Config file discovery order (mirrors prek's own precedence)
    _CONFIG_FILES: ClassVar[tuple[str, ...]] = (
        "prek.toml",
        ".pre-commit-config.yaml",
        ".pre-commit-config.yml",
    )

    def __init__(self) -> None:  # noqa: D107
        self._cmd: str | None = next(
            (cmd for cmd in self._CMD_SUBCMD if command_exists(cmd)), None
        )

    @cached_property
    def _config_path(self) -> Path | None:
        cwd = Path.cwd()
        return next((cwd / f for f in self._CONFIG_FILES if (cwd / f).exists()), None)

    def is_applicable(self) -> bool:  # noqa: D102
        return self._find_config() is not None

    def is_available(self) -> bool:  # noqa: D102
        return self._cmd is not None

    # -- internal -----------------------------------------------------------

    def _parse_config(self) -> dict[str, str]:
        """Return {repo_url: rev} from prek.toml or .pre-commit-config.yaml."""
        config_file = self._find_config()
        if config_file is None:
            return {}
        if config_file.suffix == ".toml":
            data = tomllib.loads(config_file.read_text())
            return {
                repo["repo"]: repo["rev"]
                for repo in data.get("repos", [])
                if "rev" in repo
            }
        content = config_file.read_text()
        repos: dict[str, str] = {}
        current_repo: str | None = None
        for line in content.splitlines():
            m = re.match(r"[ \t]*-?\s*repo:\s*(\S+)", line)
            if m:
                current_repo = m.group(1)
                continue
            m = re.match(r"[ \t]+rev:\s*(\S+)", line)
            if m and current_repo:
                repos[current_repo] = m.group(1)
                current_repo = None
        return repos

    # -- Updater interface --------------------------------------------------

    def capture_state(self) -> dict[str, str]:  # noqa: D102
        return self._parse_config()

    def update(self) -> None:  # noqa: D102
        if not self._cmd:
            msg = "is_available() must be called before update()"
            raise RuntimeError(msg)

        try:
            run([self._cmd, self._CMD_SUBCMD[self._cmd]])
        except subprocess.CalledProcessError as exc:
            print(exc.stderr, file=sys.stderr)
            msg = f"{self._cmd} {self._CMD_SUBCMD[self._cmd]} failed"
            raise RuntimeError(msg) from exc

    def tracked_files(self) -> list[str]:  # noqa: D102
        config_file = self._find_config()
        return [config_file.name] if config_file else []

    def describe_changes(  # noqa: D102
        self, before: dict[str, str], after: dict[str, str]
    ) -> list[str]:
        lines = []
        for repo in sorted(set(before) | set(after)):
            bv, av = before.get(repo), after.get(repo)
            if bv == av:
                continue
            short = repo.rstrip("/").rsplit("/", 1)[-1]
            if bv is None:
                lines.append(f"  + {short}: {av} (added)")
            elif av is None:
                lines.append(f"  - {short}: {bv} (removed)")
            else:
                lines.append(f"  {short}: {bv} -> {av}")
        return lines


# ---------------------------------------------------------------------------
# Registry — add new Updater subclasses here
# ---------------------------------------------------------------------------

UPDATERS: list[Updater] = [
    PoetryUpdater(),
    HookUpdater(),
]


# ---------------------------------------------------------------------------
# Git / workflow helpers
# ---------------------------------------------------------------------------


def ensure_clean_tree() -> None:
    result = git(["status", "--porcelain"])
    if result.stdout.strip():
        msg = "Working tree is not clean. Commit or stash your changes before running."
        raise SystemExit(msg)


def create_branch(branch: str) -> None:
    try:
        git(["checkout", "-b", branch])
    except subprocess.CalledProcessError as err:
        msg = f"Branch '{branch}' already exists. Delete it or use --branch to choose another name."
        raise SystemExit(msg) from err
    print(f"Created and checked out branch: {branch}")


def stage_files(files: list[str]) -> None:
    cwd = Path.cwd()
    existing = [f for f in files if (cwd / f).exists()]
    if existing:
        git(["add", "--", *existing])


def has_staged_changes() -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],  # noqa: S607
        check=False,
        capture_output=True,
    )
    return result.returncode != 0


def commit(message: str) -> None:
    result = git(["commit", "-m", message])
    # Print the short summary line git emits after committing
    if result.stdout:
        print(result.stdout.strip())


def build_commit_message(sections: dict[str, list[str]]) -> str:
    today = date.today().isoformat()  # noqa: DTZ011
    parts = [f"chore: update dependencies ({today})", ""]
    for section_name, lines in sections.items():
        if lines:
            parts.append(f"{section_name}:")
            parts.extend(lines)
            parts.append("")
    return "\n".join(parts).rstrip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update Poetry dependencies and pre-commit/prek hooks on a new branch "
            "in the current directory."
        ),
    )
    parser.add_argument(
        "--branch",
        help="Name for the new branch (default: chore/update-deps-YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making any changes",
    )
    return parser.parse_args()


def find_tools() -> list[Updater]:
    """Return updaters that are both applicable to cwd and installed."""
    active: list[Updater] = []
    for updater in UPDATERS:
        if not updater.is_applicable():
            print(
                f"[{updater.name}] skipping — config/lockfile not found",
                file=sys.stderr,
            )
            continue
        if not updater.is_available():
            print(
                f"[{updater.name}] skipping — CLI tool not installed", file=sys.stderr
            )
            continue
        active.append(updater)
    return active


def update_tool(updater: Updater) -> tuple[list[str], list[str]]:
    """Run *updater* and return (changes, tracked_files); raises RuntimeError on failure."""
    print(f"\n[{updater.name}] Capturing state before update...")
    before = updater.capture_state()

    print(f"[{updater.name}] Running update...")
    updater.update()  # raises RuntimeError on failure

    after = updater.capture_state()
    changes = updater.describe_changes(before, after)

    if changes:
        print(f"[{updater.name}] {len(changes)} change(s):")
        for line in changes:
            print(line)
    else:
        print(f"[{updater.name}] No version changes detected.")

    return changes, updater.tracked_files()


def commit_changes(
    commit_sections: dict[str, list[str]],
    files_to_stage: list[str],
) -> bool:
    """Stage *files_to_stage* and commit; return True if a commit was made."""
    stage_files(files_to_stage)
    if not has_staged_changes():
        print("\nNothing changed — no commit created.")
        return False
    message = build_commit_message(commit_sections)
    commit(message)
    print(f"\nCommit message:\n{message}")
    return True


def main() -> int:
    args = parse_args()
    branch = args.branch or f"chore/update-deps-{date.today().isoformat()}"  # noqa: DTZ011

    active = find_tools()
    if not active:
        print("No applicable updaters found.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Would create branch: {branch}")
        for u in active:
            print(f"Would run: [{u.name}] update")
        return 0

    ensure_clean_tree()
    create_branch(branch)

    commit_sections: dict[str, list[str]] = {}
    files_to_stage: list[str] = []

    for updater in active:
        try:
            changes, files = update_tool(updater)
        except RuntimeError as exc:
            print(f"[{updater.name}] ERROR: {exc}", file=sys.stderr)
            print(
                "The branch has been created but changes may be incomplete. Clean up manually.",
                file=sys.stderr,
            )
            return 1
        commit_sections[updater.message_header] = changes
        files_to_stage.extend(files)

    commit_changes(commit_sections, files_to_stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
