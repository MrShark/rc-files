#!/usr/bin/env python

"""
    mkpasswd Generate a password
"""

import os
import sys
import argparse
from random import SystemRandom
import os.path


scriptname = os.path.basename(sys.argv[0])
__version__ = "0.0.1"
__id__ = ""

args = None

_words = None

rnd = SystemRandom()
def word():
    wrd = rnd.choice(_words)
    if rnd.randint(0,1):
        return wrd
    else:
        return wrd.capitalize()


def separator():
    return rnd.choice("-_!$&*+=23456789")


def init():
    """
    Initialize the enviorment and parse options
    """
    parser = argparse.ArgumentParser(description='Skeleton file')
    parser.add_argument('--debug', dest='debug_level',
                        type=int, default=0, help='Debug level, higher is more info')

    parser.parse_args(args)

    global _words
    _words = open(os.path.join(os.environ["HOME"], ".passwdwords")).read().splitlines()
    assert len(_words) >= 4096

def main():
    """
    Main prosessing
    """
    init()
    print(word()+separator()+word()+separator()+word())
    return 0


if __name__ == '__main__' or __name__ == sys.argv[0]:
    try:
        sys.exit(main())
    except KeyboardInterrupt as e:
        print("[%s]  Interrupted!" % scriptname)
