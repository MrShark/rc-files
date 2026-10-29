#!/usr/bin/env python3
"""mkpass — Generate random passphrase-style passwords, filling the terminal."""

import argparse
import shutil
import sys
from pathlib import Path
from random import SystemRandom

rnd = SystemRandom()


def load_words() -> list[str]:
    try:
        content = (Path.home() / ".passwdwords").read_text("utf-8")
    except (OSError, UnicodeError) as exc:
        msg = f"Cannot load ~/.passwdwords: {exc}"
        raise SystemExit(msg) from exc
    words = list(
        dict.fromkeys(w for line in content.splitlines() if (w := line.strip()))
    )
    if len(words) < 4096:
        msg = "Not enough distinct words in ~/.passwdwords (need at least 4096)."
        raise SystemExit(msg)
    return words


def word(words: list[str]) -> str:
    wrd = rnd.choice(words)
    if rnd.randint(0, 1):
        return wrd
    return wrd.capitalize()


def separator() -> str:
    return rnd.choice("-_!$&*+=23456789")


def generate_password(words: list[str]) -> str:
    return word(words) + separator() + word(words) + separator() + word(words)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate random passphrase-style passwords."
    )
    parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=None,
        help="number of passwords to generate, one per line (default: fill the terminal)",
    )
    args = parser.parse_args()

    if args.count is not None and args.count <= 0:
        parser.error("count must be a positive integer")
    words = load_words()

    if args.count is not None:
        for _ in range(args.count):
            print(generate_password(words))
        return 0

    term_width, term_height = shutil.get_terminal_size()
    # Reserve one line for the shell prompt printed after the script exits.
    rows = max(term_height - 1, 1)

    # Passphrase length varies, so generate an oversized batch first and
    # trim it once the real column width is known.
    batch = [generate_password(words) for _ in range(rows * (term_width // 10 + 1))]

    col_width = max(len(p) for p in batch) + 2
    columns = max(term_width // col_width, 1)
    passwords = batch[: columns * rows]

    for row_start in range(0, len(passwords), columns):
        row = passwords[row_start : row_start + columns]
        print("".join(p.ljust(col_width) for p in row))

    return 0


if __name__ == "__main__":
    sys.exit(main())
