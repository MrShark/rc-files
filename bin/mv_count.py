#!/usr/bin/env python3
"""
mv_count — Move/rename files using a shared numeric counter.

Usage examples:
- mv_count a b c              # a -> file-1, b -> file-2, c -> file-3
- mv_count -n 3 a             # a -> file-3
- mv_count -p 'name-{}' a     # a -> name-1
- mv_count -p 'name-{:03d}' a # a -> name-001
- mv_count -f a file-1        # a -> file-1, file-1 -> file-2 (safe, no data loss)
- mv_count -s a b c           # show what would happen, without renaming anything
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mv_count", description="Move files to new names with a shared counter"
    )
    parser.add_argument(
        "-p",
        "--pattern",
        default="file-{}",
        help="Destination name pattern, Python format() syntax (default: %(default)r)",
    )
    parser.add_argument(
        "-n",
        "--start",
        type=int,
        default=1,
        help="Starting counter value (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing destinations instead of failing",
    )
    parser.add_argument(
        "-s",
        "--sandbox",
        action="store_true",
        help="Show what would be renamed without touching the filesystem",
    )
    parser.add_argument("files", nargs="+", help="Files to rename")
    return parser.parse_args()


def check_sources_exist(sources: list[Path]) -> None:
    seen = set()
    for src in sources:
        key = path_key(src)
        if key in seen:
            msg = f"Error: duplicate source path: {src}"
            raise SystemExit(msg)
        seen.add(key)
        if not os.path.lexists(src):
            msg = f"Error: source file not found: {src}"
            raise SystemExit(msg)
        if src.is_dir() or not (src.is_file() or src.is_symlink()):
            msg = f"Error: unsupported source (expected a file): {src}"
            raise SystemExit(msg)


def path_key(path: Path) -> Path:
    return path.parent.resolve() / path.name


def build_destinations(sources: list[Path], pattern: str, start: int) -> list[Path]:
    try:
        destinations = [Path(pattern.format(start + i)) for i in range(len(sources))]
    except (ValueError, TypeError, IndexError, KeyError, AttributeError) as exc:
        msg = f"Error: invalid pattern {pattern!r}: {exc}"
        raise SystemExit(msg) from exc

    seen = set()
    for dest in destinations:
        key = path_key(dest)
        if key in seen:
            msg = f"Error: pattern {pattern!r} produces duplicate destination: {dest}"
            raise SystemExit(msg)
        seen.add(key)

    return destinations


def check_conflicts(
    sources: list[Path], destinations: list[Path], *, force: bool
) -> None:
    for dest in destinations:
        if not dest.name or "\0" in str(dest) or not dest.parent.is_dir():
            msg = f"Error: invalid destination parent: {dest}"
            raise SystemExit(msg)
        if dest.is_dir():
            msg = f"Error: destination is a directory: {dest}"
            raise SystemExit(msg)
    conflicts = [
        dest
        for src, dest in zip(sources, destinations, strict=True)
        if path_key(dest) != path_key(src) and os.path.lexists(dest)
    ]
    if conflicts and not force:
        names = ", ".join(str(c) for c in conflicts)
        msg = f"Error: destination already exists: {names} (use -f to overwrite)"
        raise SystemExit(msg)


def move_to_temporary(path: Path) -> Path:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".mv_count-")
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        path.replace(tmp_path)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError as exc:
            print(f"Could not remove temporary file {tmp_path}: {exc}", file=sys.stderr)
        raise
    return tmp_path


def restore_path(current: Path, original: Path) -> None:
    try:
        if os.path.lexists(original):
            print(
                f"Cannot restore {original}; data retained at {current}",
                file=sys.stderr,
            )
            return
        current.replace(original)
    except OSError as exc:
        print(
            f"Cannot restore {original}; data retained at {current}: {exc}",
            file=sys.stderr,
        )


def rollback(moves: list[tuple[Path, Path, Path]], placed: list, backups: list) -> None:
    # Vacate final names before restoring sources, since the plan may contain cycles.
    for tmp_path, dest in reversed(placed):
        restore_path(dest, tmp_path)
    for src, tmp_path, _ in reversed(moves):
        if os.path.lexists(tmp_path):
            restore_path(tmp_path, src)
    for dest, backup in reversed(backups):
        restore_path(backup, dest)


def remove_backups(backups: list[tuple[Path, Path]]) -> bool:
    cleanup_failed = False
    for _, backup in backups:
        try:
            backup.unlink()
        except OSError as exc:
            print(f"Could not remove backup {backup}: {exc}", file=sys.stderr)
            cleanup_failed = True
    return cleanup_failed


def rename_all(sources: list[Path], destinations: list[Path]) -> None:
    moves = []
    placed = []
    backups = []
    try:
        for src, dest in zip(sources, destinations, strict=True):
            if path_key(src) != path_key(dest):
                moves.append((src, move_to_temporary(src), dest))

        for _, _, dest in moves:
            if os.path.lexists(dest):
                backups.append((dest, move_to_temporary(dest)))

        for _, tmp_path, dest in moves:
            tmp_path.replace(dest)
            placed.append((tmp_path, dest))
    except OSError as exc:
        rollback(moves, placed, backups)
        msg = f"Error: rename failed: {exc}"
        raise SystemExit(msg) from exc

    cleanup_failed = remove_backups(backups)
    for src, _, dest in moves:
        print(f"{src} -> {dest}")
    if cleanup_failed:
        msg = "Renames completed, but some temporary backups could not be removed."
        raise SystemExit(msg)


def main() -> int:
    args = parse_args()

    sources = [Path(f) for f in args.files]
    try:
        check_sources_exist(sources)
        destinations = build_destinations(sources, args.pattern, args.start)
        check_conflicts(sources, destinations, force=args.force)
    except (OSError, ValueError, RuntimeError) as exc:
        msg = f"Error: invalid rename plan: {exc}"
        raise SystemExit(msg) from exc

    if args.sandbox:
        for src, dest in zip(sources, destinations, strict=True):
            if src != dest:
                print(f"{src} -> {dest} (sandbox, not moved)")
        return 0

    rename_all(sources, destinations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
