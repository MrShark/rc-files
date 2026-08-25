#!/usr/bin/env python3
"""
RC-file installer.

Creates symlinks from the bundled dot-files to the user's home directory,
recursively installing any executable scripts found in the `bin/` directory.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# Base directories
RC_FILE_DIR: Path = Path(__file__).resolve().parent
HOME: Path = Path(os.environ["HOME"])

# Items to install
DOTFILES: tuple[str, ...] = (
    "bashrc",
    "passwdwords",
)

# Directories to install recursively
BINDIRS: tuple[str, ...] = ("bin",)


def install_link(src: Path, dst: Path, *, force_links: bool, force_file: bool) -> None:
    """
    Create a symbolic link `dst` pointing to `src`.

    - If `dst` already exists and is not a symlink, warn (or replace it if
      `force_file` is set).
    - If `dst` is a symlink but points elsewhere, warn (or replace it if
      `force_links` is set).
    - Otherwise, create the necessary parent directories and the symlink.
    """
    if dst.exists(follow_symlinks=False):
        if not dst.is_symlink():
            if not force_file:
                print(f"{dst} exists, but is not a symlink")
                return
            dst.unlink()
            print(f"Removed file {dst}")
        elif dst.resolve() != src.resolve():
            if not force_links:
                print(f"{dst} is a symlink, but not to {src}")
                return
            dst.unlink()
            print(f"Removed link {dst}")
        else:
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src)
    print(f"Created link {dst} -> {src}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install rc-files symlinks.")
    parser.add_argument(
        "--force-links",
        action="store_true",
        help="Overwrite existing symlinks that point elsewhere",
    )
    parser.add_argument(
        "--force-file",
        action="store_true",
        help="Overwrite existing regular files",
    )
    args = parser.parse_args()

    # Install individual dot-files
    for dotfile in DOTFILES:
        install_link(
            RC_FILE_DIR / dotfile,
            HOME / f".{dotfile}",
            force_links=args.force_links,
            force_file=args.force_file,
        )

    # Install executable scripts recursively
    for bindir in BINDIRS:
        src_root: Path = RC_FILE_DIR / bindir
        dst_root: Path = HOME / "bin"
        for path in src_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(src_root)
            dst_path = dst_root / relative.with_suffix("")
            install_link(
                path,
                dst_path,
                force_links=args.force_links,
                force_file=args.force_file,
            )


if __name__ == "__main__":
    main()
