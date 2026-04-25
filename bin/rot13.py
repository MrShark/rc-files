#!/usr/bin/env python3
"""
rot13 CLI.

Usage examples:
- rot13                # read from stdin, encode to stdout
- rot13 -s "text"      # encode provided text to stdout
- rot13 file           # read file, encode to stdout
- rot13 -               # read from stdin (explicit), encode to stdout
- rot13 -s "text" -o out.txt
- rot13 file -o out.txt
"""

import argparse
import codecs
import sys
from pathlib import Path


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="rot13", description="ROT13 encoder")
    parser.add_argument(
        "-s", "--string", help="Text to encode (mutually exclusive with input file)"
    )
    parser.add_argument("-o", "--output", help="Write encoded output to file")
    parser.add_argument(
        "file", nargs="?", help='Input file (use "-" or omit for stdin)'
    )
    args = parser.parse_args(argv)

    # Validate mutually exclusive inputs
    if args.string and args.file:
        parser.error("Specify either -s/--string or an input file, not both.")

    try:
        if args.string is not None:
            data = args.string
        # Determine input source: file, explicit "-" or omitted -> stdin
        elif args.file and args.file != "-":
            path = Path(args.file)
            if not path.is_file():
                print(f"Error: input file not found: {args.file}", file=sys.stderr)
                return 2
            data = path.read_text(encoding="utf-8")
        else:
            # Read from stdin (explicit '-' or no parameter)
            # Read bytes and decode as UTF-8 to avoid locale-dependent behavior
            data = sys.stdin.buffer.read().decode("utf-8")

        # ROT13 encoding
        encoded = codecs.encode(data, "rot_13")

        if args.output:
            out_path = Path(args.output)
            out_path.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
