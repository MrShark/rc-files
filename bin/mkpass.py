#!/usr/bin/env python

"""mkpasswd - Generate a password."""

import argparse
import os
import pathlib
import sys
from random import SystemRandom

scriptname = pathlib.Path(sys.argv[0]).name
__version__ = "0.0.1"
__id__ = ""

args = None

_words = None

rnd = SystemRandom()

_words = (
    (pathlib.Path(os.environ["HOME"]) / ".passwdwords").read_text("utf-8").splitlines()
)

if len(_words) < 4096:
    msg = "Not enough words."
    raise ValueError(msg)


def word() -> str:
    wrd = rnd.choice(_words)
    if rnd.randint(0, 1):
        return wrd
    return wrd.capitalize()


def separator() -> str:
    return rnd.choice("-_!$&*+=23456789")


def init() -> None:
    """Initialize the enviorment and parse options."""
    parser = argparse.ArgumentParser(description="Skeleton file")
    parser.add_argument(
        "--debug",
        dest="debug_level",
        type=int,
        default=0,
        help="Debug level, higher is more info",
    )

    parser.parse_args(args)


def main() -> int:
    """Print a random password."""
    init()
    print(word() + separator() + word() + separator() + word())
    return 0


if __name__ == "__main__" or __name__ == sys.argv[0]:
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"[{scriptname}]  Interrupted!")
