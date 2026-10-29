"""Exercise certificate dates, TLS failures, URL parsing, and CLI configuration offline."""

import datetime
import socket
import ssl
from unittest import mock

import pytest

from tests.support import assert_clean_failure


@pytest.fixture
def ssl_checker(sandbox):
    return sandbox.load_script("ssl_checker")


@pytest.fixture
def tls(ssl_checker):
    with (
        mock.patch.object(ssl_checker.ssl, "create_default_context") as context,
        mock.patch.object(ssl_checker.socket, "create_connection") as connect,
    ):
        peer = context.return_value.wrap_socket.return_value.__enter__.return_value
        yield context, connect, peer


@pytest.fixture
def pool(ssl_checker):
    with mock.patch.object(ssl_checker, "Pool") as factory:
        factory.return_value.__enter__.return_value.map.side_effect = (
            lambda function, urls: list(map(function, urls))
        )
        yield factory


@pytest.mark.parametrize(
    ("not_after", "days"),
    [
        ("Feb 10 12:00:00 2026 GMT", 40),
        ("Jan 01 00:00:00 2026 GMT", 0),
        ("Dec 31 23:59:59 2025 GMT", -1),
    ],
)
def test_certificate_expiry_is_utc_and_floors_partial_days(
    ssl_checker, tls, not_after, days
):
    context, connect, peer = tls
    peer.getpeercert.return_value = {"notAfter": not_after}
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    real_datetime = datetime.datetime
    with mock.patch.object(
        ssl_checker.datetime, "datetime", wraps=real_datetime
    ) as clock:
        clock.now.return_value = now
        result = ssl_checker.get_cert_expiry("offline.invalid", port=8443)
    assert result == (days, not_after, True, None)
    clock.now.assert_called_once_with(datetime.UTC)
    context.assert_called_once_with()
    connect.assert_called_once_with(("offline.invalid", 8443), timeout=5)
    context.return_value.wrap_socket.assert_called_once_with(
        connect.return_value, server_hostname="offline.invalid"
    )
    peer.getpeercert.assert_called_once_with()


@pytest.mark.parametrize(
    ("error", "validity"),
    [
        (ssl.SSLCertVerificationError("untrusted issuer"), False),
        (ssl.SSLError("TLS handshake failed"), False),
        (socket.gaierror("DNS lookup failed"), None),
        (TimeoutError("connection timed out"), None),
        (ConnectionRefusedError("connection refused"), None),
        (UnicodeError("hostname encoding failed"), None),
    ],
)
def test_connection_errors_return_structured_failure(ssl_checker, tls, error, validity):
    _, connect, _ = tls
    connect.side_effect = error
    assert ssl_checker.get_cert_expiry("offline.invalid") == (
        None,
        None,
        validity,
        str(error),
    )
    connect.assert_called_once_with(("offline.invalid", 443), timeout=5)


def test_tls_handshake_error_is_an_invalid_chain(ssl_checker, tls):
    context, _, peer = tls
    error = ssl.SSLError("handshake failed")
    context.return_value.wrap_socket.side_effect = error
    assert ssl_checker.get_cert_expiry("offline.invalid") == (
        None,
        None,
        False,
        str(error),
    )
    peer.getpeercert.assert_not_called()


@pytest.mark.parametrize(
    ("certificate", "expected_error"),
    [({}, "notAfter"), ({"notAfter": "not a date"}, "does not match format")],
)
def test_missing_or_malformed_certificate_expiry_is_reported(
    ssl_checker, tls, certificate, expected_error
):
    _, _, peer = tls
    peer.getpeercert.return_value = certificate
    days, expiry, validity, error = ssl_checker.get_cert_expiry("offline.invalid")
    assert days is None
    assert expiry is None
    assert validity is None
    assert expected_error in error


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (-2, "\033[5m\033[91mEXPIRED (2 day(s) ago)\033[0m"),
        (-1, "\033[5m\033[91mEXPIRED (1 day(s) ago)\033[0m"),
        (0, "\033[91m0 day(s) left\033[0m"),
        (10, "\033[91m10 day(s) left\033[0m"),
        (11, "\033[93m11 day(s) left\033[0m"),
        (30, "\033[93m30 day(s) left\033[0m"),
        (31, "\033[32m31 day(s) left\033[0m"),
    ],
)
def test_status_colors_at_expiry_boundaries(ssl_checker, days, expected):
    assert ssl_checker.format_status(days) == expected


@pytest.mark.parametrize("color", ["white", "unknown"])
def test_default_and_unknown_colors_use_white(ssl_checker, color):
    assert ssl_checker.colorize("message", color) == "\033[97mmessage\033[0m"


@pytest.mark.parametrize(
    ("url", "hostname", "port"),
    [
        ("example.invalid", "example.invalid", 443),
        ("https://Example.invalid/path?q=1", "example.invalid", 443),
        ("https://example.invalid:8443/path", "example.invalid", 8443),
        ("//example.invalid:444/path", "example.invalid", 444),
        ("https://[::1]/path", "::1", 443),
        ("example.invalid:8443", "example.invalid", 8443),
        ("[::1]:8443", "::1", 8443),
    ],
)
def test_valid_urls_connect_to_parsed_endpoint(
    ssl_checker, capsys, url, hostname, port
):
    with mock.patch.object(
        ssl_checker,
        "get_cert_expiry",
        return_value=(31, "Feb 01 00:00:00 2026 GMT", True, None),
    ) as connect:
        result = ssl_checker.check_url(url)
    connect.assert_called_once_with(hostname, port=port)
    assert result == (
        f"{hostname:30} \033[32m31 day(s) left\033[0m"
        "  (Expires: Feb 01 00:00:00 2026 GMT)"
    )
    assert capsys.readouterr() == ("", "")


def test_invalid_chain_without_error_is_rejected(ssl_checker, capsys):
    with mock.patch.object(
        ssl_checker, "get_cert_expiry", return_value=(None, None, False, None)
    ):
        assert ssl_checker.check_url("offline.invalid") is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"\033[91m{'offline.invalid':30} INVALID CHAIN\033[0m\n"


def test_certificate_error_is_printed_on_stderr(ssl_checker, tls, capsys):
    _, _, peer = tls
    peer.getpeercert.return_value = {}
    assert ssl_checker.check_url("offline.invalid") is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "offline.invalid" in captured.err
    assert "ERROR: 'notAfter'" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("contents", [None, "", "\n # comment only\n\t\n"])
def test_missing_or_empty_url_config_returns_no_urls(sandbox, ssl_checker, contents):
    if contents is not None:
        (sandbox.home / ".ssl_checker_urls").write_text(contents)
    assert ssl_checker.load_urls_from_cfg() == []


def test_config_strips_comments_and_preserves_url_order(sandbox, ssl_checker):
    (sandbox.home / ".ssl_checker_urls").write_text(
        "# urls\n  https://z.invalid/ # last\n\n a.invalid:8443\t\n"
        "https://z.invalid/ # repeat\n"
    )
    assert ssl_checker.load_urls_from_cfg() == [
        "https://z.invalid/",
        "a.invalid:8443",
        "https://z.invalid/",
    ]


@pytest.mark.parametrize("sort", [False, True])
def test_main_checks_config_urls_in_requested_order(sandbox, ssl_checker, pool, sort):
    (sandbox.home / ".ssl_checker_urls").write_text("z.invalid\na.invalid:8443\n")
    with mock.patch.object(
        ssl_checker, "get_cert_expiry", return_value=(40, "future expiry", True, None)
    ) as connect:
        status, stdout, stderr = sandbox.main(
            ssl_checker, *(["--sort"] if sort else [])
        )
    expected = ["a.invalid", "z.invalid"] if sort else ["z.invalid", "a.invalid"]
    assert status == 0
    assert stderr == ""
    assert [line.split()[0] for line in stdout.splitlines()] == expected
    assert connect.call_args_list == [
        mock.call(host, port=8443 if host == "a.invalid" else 443) for host in expected
    ]
    pool.return_value.__enter__.return_value.map.assert_called_once_with(
        ssl_checker.check_url,
        ["a.invalid:8443", "z.invalid"] if sort else ["z.invalid", "a.invalid:8443"],
    )


def test_explicit_urls_bypass_config(sandbox, ssl_checker, pool):
    with (
        mock.patch.object(ssl_checker, "load_urls_from_cfg") as config,
        mock.patch.object(
            ssl_checker,
            "get_cert_expiry",
            return_value=(40, "future expiry", True, None),
        ) as connect,
    ):
        status, stdout, stderr = sandbox.main(ssl_checker, "explicit.invalid")
    assert status == 0
    assert "explicit.invalid" in stdout
    assert stderr == ""
    config.assert_not_called()
    connect.assert_called_once_with("explicit.invalid", port=443)
    pool.assert_called_once_with()


@pytest.mark.parametrize("contents", [None, "", "# no urls\n"])
def test_no_urls_prints_usage_and_fails_without_a_pool(sandbox, ssl_checker, contents):
    if contents is not None:
        (sandbox.home / ".ssl_checker_urls").write_text(contents)
    with mock.patch.object(ssl_checker, "Pool") as pool:
        status, stdout, stderr = sandbox.main(ssl_checker)
    assert status == 1
    assert stdout == ""
    assert "usage:" in stderr
    pool.assert_not_called()


@pytest.mark.parametrize("kind", ["directory", "invalid-utf8"])
def test_config_read_errors_fail_before_starting_a_pool(sandbox, ssl_checker, kind):
    config = sandbox.home / ".ssl_checker_urls"
    if kind == "directory":
        config.mkdir()
    else:
        config.write_bytes(b"\xff")
    with mock.patch.object(ssl_checker, "Pool") as pool:
        status, stdout, stderr = sandbox.main(ssl_checker)
    assert status == 1
    assert stdout == ""
    assert "Cannot load SSL checker URLs:" in stderr
    assert "Traceback" not in stderr
    pool.assert_not_called()


def test_main_reports_all_connection_failures(sandbox, ssl_checker, pool, tls):
    _, connect, _ = tls
    connect.side_effect = [TimeoutError("timed out"), ssl.SSLError("bad chain")]
    status, stdout, stderr = sandbox.main(ssl_checker, "one.invalid", "two.invalid")
    assert status == 1
    assert stdout == ""
    assert "one.invalid" in stderr
    assert "two.invalid" in stderr
    assert "timed out" in stderr
    assert "bad chain" in stderr
    assert "Traceback" not in stderr
    assert connect.call_count == 2
    pool.assert_called_once_with()


def test_missing_config_cli_fails_with_usage(sandbox):
    result = sandbox.cli("ssl_checker")
    assert_clean_failure(result, "usage:")
    assert result.returncode == 1
    assert result.stdout == ""
