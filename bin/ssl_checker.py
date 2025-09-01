#!/usr/bin/env python3
"""Checks the SSL/TLS certificate expiry for a list of HTTPS URLs."""

import datetime
import socket
import ssl
import sys
import pathlib
from urllib.parse import urlparse


def get_cert_expiry(hostname: str, port: int = 443):
    """
    Connect to hostname:port and check the certificate.

    returns a tuple (days_left, not_after_str, chain_valid, error_string).
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
            ).replace(tzinfo=datetime.timezone.utc)
    except ssl.SSLError as e:
        return None, None, False, str(e)
    except Exception as e:
        return None, None, None, str(e)

    now = datetime.datetime.now(datetime.timezone.utc)
    days_left = (expiry - now).days
    return days_left, not_after, True, None


def colorize(msg: str, color: str = "white", flashing: bool = False) -> str:
    colors = {
        "red": "\033[91m",
        "yellow": "\033[93m",
        "green": "\033[92m",
        "white": "\033[97m",
        "reset": "\033[0m",
    }
    flash = "\033[5m" if flashing else ""
    return f"{flash}{colors.get(color, colors['white'])}{msg}{colors['reset']}"


def main() -> None:
    cfg_file = pathlib.Path("~/.ssh_checker_urls").expanduser()
    if len(sys.argv) < 2:
        if cfg_file.exists():
            urls = cfg_file.read_text(encoding="utf-8").splitlines()
            urls = [u.split("#", 1)[0] for u in urls]
            urls = [u for u in urls if u]
        else:
            print("Usage: ssl_checker <url1> <url2> ...")
            sys.exit(1)
    else:
        urls = sys.argv[1:]

    for url in urls:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or 443
        if not hostname:
            print(colorize(f"Invalid URL: {url}", "red"))
            continue

        days_left, not_after, chain_valid, err = get_cert_expiry(hostname, port)

        if err:
            print(colorize(f"{hostname:30} ERROR: {err}", "red"))
            continue

        if not chain_valid:
            print(colorize(f"{hostname:30} INVALID CHAIN", "red"))
            continue

        status = f"{days_left} day(s) left"
        if days_left < 0:
            status = colorize(
                f"EXPIRED ({abs(days_left)} day(s) ago)",
                "red",
                flashing=True,
            )
        elif days_left <= 4:
            status = colorize(status, "red")
        elif days_left <= 14:
            status = colorize(status, "yellow")
        else:
            status = colorize(status, "green")

        print(f"{hostname:30} {status}  (Expires: {not_after})")


if __name__ == "__main__":
    main()
