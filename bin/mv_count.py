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
    for src in sources:
        if not src.exists():
            msg = f"Error: source file not found: {src}"
            raise SystemExit(msg)


def build_destinations(sources: list[Path], pattern: str, start: int) -> list[Path]:
    destinations = [Path(pattern.format(start + i)) for i in range(len(sources))]

    seen = set()
    for dest in destinations:
        if dest in seen:
            msg = f"Error: pattern {pattern!r} produces duplicate destination: {dest}"
            raise SystemExit(msg)
        seen.add(dest)

    return destinations


def check_conflicts(
    sources: list[Path], destinations: list[Path], *, force: bool
) -> None:
    conflicts = [
        dest
        for src, dest in zip(sources, destinations, strict=True)
        if dest != src and dest.exists()
    ]
    if conflicts and not force:
        names = ", ".join(str(c) for c in conflicts)
        msg = f"Error: destination already exists: {names} (use -f to overwrite)"
        raise SystemExit(msg)


def rename_all(sources: list[Path], destinations: list[Path]) -> None:
    # Move every source to a temporary name first, then rename the temporary
    # names to their final destination. This way overlapping source and
    # destination names (e.g. "a file-1" -> "file-1 file-2") never clobber
    # each other, regardless of move order.
    temp_moves = []
    for src, dest in zip(sources, destinations, strict=True):
        if src == dest:
            continue
        fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".mv_count-")
        os.close(fd)
        tmp_path = Path(tmp_name)
        src.replace(tmp_path)
        temp_moves.append((tmp_path, dest))
        print(f"{src} -> {dest}")

    for tmp_path, dest in temp_moves:
        tmp_path.replace(dest)


def main() -> int:
    args = parse_args()

    sources = [Path(f) for f in args.files]
    check_sources_exist(sources)

    destinations = build_destinations(sources, args.pattern, args.start)
    check_conflicts(sources, destinations, force=args.force)

    if args.sandbox:
        for src, dest in zip(sources, destinations, strict=True):
            if src != dest:
                print(f"{src} -> {dest} (sandbox, not moved)")
        return 0

    rename_all(sources, destinations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
