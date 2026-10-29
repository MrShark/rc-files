#!/usr/bin/env python3
"""Checks the SSL/TLS certificate expiry for a list of HTTPS URLs."""

import argparse
import datetime
import pathlib
import socket
import ssl
import sys
from multiprocessing import Pool
from urllib.parse import urlparse


def get_cert_expiry(hostname: str, *, port: int = 443):
    """
    Connect to hostname:port and check the certificate.

    Returns (days_left, not_after_str, chain_valid, error_string).
    """
    try:
        context = ssl.create_default_context()
        with context.wrap_socket(
            socket.create_connection((hostname, port), timeout=5),
            server_hostname=hostname,
        ) as ssock:
            cert = ssock.getpeercert()
            not_after = cert["notAfter"]
            expiry = datetime.datetime.strptime(
                not_after,
                "%b %d %H:%M:%S %Y %Z",
            ).replace(tzinfo=datetime.UTC)
    except ssl.SSLError as e:
        return None, None, False, str(e)
    except (OSError, ValueError, KeyError, UnicodeError) as e:
        return None, None, None, str(e)

    now = datetime.datetime.now(datetime.UTC)
    days_left = (expiry - now).days
    return days_left, not_after, True, None


def colorize(msg: str, color: str = "white", *, flashing: bool = False) -> str:
    colors = {
        "red": "\033[91m",
        "yellow": "\033[93m",
        "green": "\033[32m",
        "white": "\033[97m",
        "reset": "\033[0m",
    }
    flash = "\033[5m" if flashing else ""
    return f"{flash}{colors.get(color, colors['white'])}{msg}{colors['reset']}"


def load_urls_from_cfg() -> list[str]:
    cfg_file = pathlib.Path("~/.ssl_checker_urls").expanduser()
    if not cfg_file.exists():
        return []
    lines = cfg_file.read_text(encoding="utf-8").splitlines()
    return [u for u in [u.split("#", 1)[0].strip() for u in lines if u.strip()] if u]


def format_status(days_left: int) -> str:
    base = f"{days_left} day(s) left"
    if days_left < 0:
        return colorize(f"EXPIRED ({abs(days_left)} day(s) ago)", "red", flashing=True)
    if days_left <= 10:
        return colorize(base, "red")
    if days_left <= 30:
        return colorize(base, "yellow")
    return colorize(base, "green")


def check_url(url: str) -> str | None:
    try:
        parsed = urlparse(
            url if "://" in url or url.startswith("//") else f"https://{url}"
        )
        hostname = parsed.hostname
        port = parsed.port if parsed.port is not None else 443
    except ValueError as exc:
        print(colorize(f"Invalid URL: {url}: {exc}", "red"), file=sys.stderr)
        return None
    if not hostname or not 1 <= port <= 65535:
        print(
            colorize(f"Invalid URL: {url}: missing hostname or invalid port", "red"),
            file=sys.stderr,
        )
        return None

    days_left, not_after, chain_valid, err = get_cert_expiry(
        hostname,
        port=port,
    )
    if err:
        print(colorize(f"{hostname:30} ERROR: {err}", "red"), file=sys.stderr)
        return None

    if not chain_valid:
        print(colorize(f"{hostname:30} INVALID CHAIN", "red"), file=sys.stderr)
        return None

    return f"{hostname:30} {format_status(days_left)}  (Expires: {not_after})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SSL/TLS certificate expiry.")
    parser.add_argument("urls", nargs="*", help="URLs to check")
    parser.add_argument(
        "-s",
        "--sort",
        action="store_true",
        help="Sort the input in alphabetical order",
    )
    args = parser.parse_args()

    if args.urls:
        urls = args.urls
    else:
        try:
            urls = load_urls_from_cfg()
        except (OSError, UnicodeError) as exc:
            print(f"Cannot load SSL checker URLs: {exc}", file=sys.stderr)
            return 1

    if not urls:
        parser.print_usage(file=sys.stderr)
        sys.exit(1)

    if args.sort:
        urls.sort()

    with Pool() as pool:
        results = pool.map(check_url, urls)
    for result in results:
        if result is not None:
            print(result)
    return int(any(result is None for result in results))


if __name__ == "__main__":
    sys.exit(main())
