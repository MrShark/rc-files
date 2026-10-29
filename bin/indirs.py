#!/usr/bin/env python3
"""
Run one command in each of the specified directories.

Usage: indirs [--header] [--no-shell] [--parallel][=N] <command> <dir> ...
"""

import argparse
import os
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GREEN = "\033[32m"
RESET = "\033[0m"


def positive_int(value: str) -> int:
    """Return a positive integer or raise an argparse-friendly error."""
    try:
        number = int(value)
    except ValueError as exc:
        msg = "worker count must be a positive integer"
        raise argparse.ArgumentTypeError(msg) from exc
    if number <= 0:
        msg = "worker count must be a positive integer"
        raise argparse.ArgumentTypeError(msg)
    return number


def normalize_parallel_args(argv: list[str]) -> list[str]:
    """Convert the optional-value syntax to options argparse can parse safely."""
    normalized = []
    for index, arg in enumerate(argv):
        if arg == "--":
            normalized.extend(argv[index:])
            break
        if arg.startswith("--parallel="):
            normalized.append(f"--worker-count={arg.partition('=')[2]}")
        else:
            normalized.append(arg)
    return normalized


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="indirs",
        description="Run one command in each of the specified directories",
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="print each directory argument in green before its command output",
    )
    parser.add_argument(
        "--no-shell",
        action="store_true",
        help="split the command into arguments without shell expansion",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="run directories concurrently using the CPU count as the worker count",
    )
    parser.add_argument(
        "--worker-count",
        type=positive_int,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("command", help="command string to run in each directory")
    parser.add_argument("dirs", nargs="+", help="directories to process")
    return parser


def run_command(directory, command, argv, *, capture_output=False):
    try:
        result = subprocess.run(  # noqa: S603
            argv if argv is not None else command,
            cwd=directory,
            shell=argv is None,
            check=False,
            capture_output=capture_output,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        return None, f"indirs: could not run command in {directory}: {exc}"
    if result.returncode:
        return result, (
            f"indirs: command failed in {directory} (exit status {result.returncode})"
        )
    return result, None


def run_in_directory(directory: Path, command: str, argv: list[str] | None) -> bool:
    _, error = run_command(directory, command, argv)
    if error is not None:
        print(error, file=sys.stderr)
    return error is None


def run_parallel(directories, command, argv, workers, *, header):
    failed = False
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(
            lambda item: run_command(item[0], command, argv, capture_output=True),
            directories,
        )
        for (_, spelling), (result, error) in zip(directories, results, strict=True):
            if header:
                print(f"{GREEN}{spelling}{RESET}", flush=True)
            if result is not None:
                sys.stdout.write(result.stdout)
                sys.stdout.flush()
                sys.stderr.write(result.stderr)
                sys.stderr.flush()
            if error is not None:
                print(error, file=sys.stderr, flush=True)
                failed = True
    return failed


def main() -> int:
    parser = create_parser()
    args = parser.parse_args(normalize_parallel_args(sys.argv[1:]))

    command_args = None
    if args.no_shell:
        try:
            command_args = shlex.split(args.command)
        except ValueError as exc:
            parser.error(f"invalid command string: {exc}")
        if not command_args:
            parser.error("command must not be empty when using --no-shell")

    directories = []
    failed = False
    for item in args.dirs:
        directory = Path(item)
        if not directory.is_dir():
            print(f"indirs: not a directory: {directory}", file=sys.stderr)
            failed = True
        else:
            directories.append((directory, item))

    workers = args.worker_count
    parallel = args.parallel or workers is not None
    if parallel and workers is None:
        workers = os.cpu_count() or 1

    if parallel:
        failed |= run_parallel(
            directories, args.command, command_args, workers, header=args.header
        )
    else:
        for directory, spelling in directories:
            if args.header:
                print(f"{GREEN}{spelling}{RESET}", flush=True)
            failed |= not run_in_directory(directory, args.command, command_args)

    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
