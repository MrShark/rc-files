#!/usr/bin/env python3
"""Checks the SSL/TLS certificate expiry for a list of HTTPS URLs."""

import argparse
import datetime
import pathlib
import socket
import ssl
import sys
from urllib.parse import urlparse


def get_cert_expiry(hostname: str, *, port: int = 443, verbose: bool = False):
    """
    Connect to hostname:port and check the certificate.

    returns a tuple (days_left, not_after_str, chain_valid, error_string, cert_information).
    """
    cert_information = None
    try:
        context = ssl.create_default_context()
        with context.wrap_socket(
            socket.create_connection((hostname, port), timeout=5),
            server_hostname=hostname,
        ) as ssock:
            cert = ssock.getpeercert()
            if verbose:
                cert_information = dict(cert)
            not_after = cert["notAfter"]
            expiry = datetime.datetime.strptime(
                not_after,
                "%b %d %H:%M:%S %Y %Z",
            ).replace(tzinfo=datetime.timezone.utc)
    except ssl.SSLError as e:
        return None, None, False, str(e), cert_information
    except Exception as e:  # noqa: BLE001
        return None, None, None, str(e), cert_information

    now = datetime.datetime.now(datetime.timezone.utc)
    days_left = (expiry - now).days
    return days_left, not_after, True, None, cert_information


def colorize(msg: str, color: str = "white", *, flashing: bool = False) -> str:
    colors = {
        "red": "\033[91m",
        "yellow": "\033[93m",
        "green": "\033[92m",
        "white": "\033[97m",
        "reset": "\033[0m",
    }
    flash = "\033[5m" if flashing else ""
    return f"{flash}{colors.get(color, colors['white'])}{msg}{colors['reset']}"


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check SSL/TLS certificate expiry.")
    parser.add_argument("urls", nargs="*", help="URLs to check")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed certificate info",
    )
    return parser


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
    if days_left <= 4:
        return colorize(base, "red")
    if days_left <= 14:
        return colorize(base, "yellow")
    return colorize(base, "green")


def fmt_list(tuples) -> str:
    return ", ".join(f"{k}={v}" for k, v in tuples)


def print_verbose(cert_dict: dict) -> None:
    print(f"  Subject: {dict(x[0] for x in cert_dict.get('subject', []))}")
    print(f"  Issuer:  {dict(x[0] for x in cert_dict.get('issuer', []))}")
    sans = cert_dict.get("subjectAltName", [])
    if sans:
        print(f"  SANs:    {', '.join([n[1] for n in sans])}")

    for key, value in cert_dict.items():
        if key in {"subject", "issuer", "subjectAltName"}:
            continue
        if isinstance(value, list) and value and isinstance(value[0], tuple):
            value = fmt_list(value)  # noqa: PLW2901
        print(f"  {key}: {value}")


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    if args.urls:
        urls = args.urls
    else:
        urls = load_urls_from_cfg()

    if not urls:
        parser.print_usage()
        sys.exit(1)

    for url in urls:
        parsed = urlparse(url)
        if not parsed.scheme:
            parsed = urlparse(f"https://{url}")
        hostname, port = parsed.hostname, parsed.port or 443
        if not hostname:
            print(colorize(f"Invalid URL: {url}", "red"))
            continue

        days_left, not_after, chain_valid, err, cert_dict = get_cert_expiry(
            hostname,
            port=port,
            verbose=args.verbose,
        )

        if err:
            print(colorize(f"{hostname:30} ERROR: {err}", "red"))
            continue
        if not chain_valid:
            print(colorize(f"{hostname:30} INVALID CHAIN", "red"))
            continue

        print(f"{hostname:30} {format_status(days_left)}  (Expires: {not_after})")
        if args.verbose and cert_dict:
            print_verbose(cert_dict)


if __name__ == "__main__":
    main()
