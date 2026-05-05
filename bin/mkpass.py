#!/usr/bin/env python3
"""mkpass — Generate a random passphrase-style password."""

import sys
from pathlib import Path
from random import SystemRandom

_words = (Path.home() / ".passwdwords").read_text("utf-8").splitlines()

if len(_words) < 4096:
    msg = "Not enough words in ~/.passwdwords (need at least 4096)."
    raise SystemExit(msg)

rnd = SystemRandom()


def word() -> str:
    wrd = rnd.choice(_words)
    if rnd.randint(0, 1):
        return wrd
    return wrd.capitalize()


def separator() -> str:
    return rnd.choice("-_!$&*+=23456789")


def main() -> int:
    print(word() + separator() + word() + separator() + word())
    return 0


if __name__ == "__main__":
    sys.exit(main())
