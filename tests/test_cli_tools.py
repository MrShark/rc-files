"""Safe offline CLI and core-function regressions for the smaller tools."""

import io
import os
import re
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

from tests.support import assert_clean_failure


@pytest.fixture
def disk_status(sandbox):
    return sandbox.load_script("disk_status")


@pytest.fixture
def ssl_checker(sandbox):
    return sandbox.load_script("ssl_checker")


@pytest.fixture
def mkpass(sandbox, write_words):
    write_words()
    return sandbox.load_script("mkpass")


@pytest.fixture
def dictionary(sandbox):
    return sandbox.home / ".passwdwords"


@pytest.fixture
def write_words(dictionary):
    def write(count=4096):
        words = [f"word{number:04d}" for number in range(count)]
        dictionary.write_text("\n".join(words) + "\n")
        return words

    return write


@pytest.fixture
def indirs(sandbox):
    return sandbox.load_script("indirs")


@pytest.fixture
def directories(sandbox):
    paths = [sandbox.root / name for name in ("first", "second", "third")]
    for path in paths:
        path.mkdir()
    return paths


def test_ssh_text_error_is_clean_and_returns_failure(sandbox, disk_status):
    """Report SSH error output without a traceback."""
    error = subprocess.CalledProcessError(255, ["ssh"], output="permission denied\n")
    with mock.patch.object(disk_status.subprocess, "check_output", side_effect=error):
        result, _, stderr = sandbox.main(disk_status, "offline.invalid")
    assert result == 1
    assert "permission denied" in stderr
    assert "Traceback" not in stderr


def test_missing_ssh_executable_is_clean_and_returns_failure(sandbox, disk_status):
    """Report a missing SSH executable as a clean failure."""
    with mock.patch.object(
        disk_status.subprocess,
        "check_output",
        side_effect=FileNotFoundError("ssh unavailable"),
    ):
        result, _, stderr = sandbox.main(disk_status, "offline.invalid")
    assert result == 1
    assert "ssh unavailable" in stderr
    assert "Traceback" not in stderr


def test_output_reports_used_not_free_space(sandbox, disk_status):
    """Label used space correctly and warn about high utilization."""
    df = "Filesystem Size Used Avail Use% Mounted on\n/dev/test 100G 91G 9G 91% /data\n"
    with mock.patch.object(
        disk_status.subprocess, "check_output", return_value=df
    ) as ssh:
        result, stdout, stderr = sandbox.main(disk_status, "offline.invalid")
    assert result == 0, stderr
    assert "91% used" in stdout
    assert "91G of 100G used" in stdout
    assert "WARNING" in stdout
    assert "free" not in stdout
    assert ssh.call_args.kwargs["text"]


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https:///path", id="missing-hostname"),
        pytest.param(
            "https://example.invalid:bad",
            id="nonnumeric-port",
        ),
        pytest.param(
            "https://example.invalid:65536",
            id="out-of-range-port",
        ),
        pytest.param(
            "https://[::1",
            id="malformed-ipv6",
        ),
        pytest.param("example.invalid:0", id="port-zero"),
    ],
)
def test_invalid_url_is_rejected_without_connecting(ssl_checker, url, capsys):
    """Reject invalid URLs before opening a connection."""
    with mock.patch.object(ssl_checker, "get_cert_expiry") as connect:
        result = ssl_checker.check_url(url)
    assert result is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Invalid URL" in captured.err
    assert url in captured.err
    assert "Traceback" not in captured.err
    connect.assert_not_called()


def test_schemeless_host_port_connects_to_requested_endpoint(ssl_checker, capsys):
    """Honor an explicit port without a URL scheme."""
    with mock.patch.object(
        ssl_checker,
        "get_cert_expiry",
        return_value=(40, "future expiry", True, None),
    ) as connect:
        result = ssl_checker.check_url("example.invalid:8443")
    connect.assert_called_once_with("example.invalid", port=8443)
    assert "example.invalid" in result
    assert "40 day(s) left" in result
    assert capsys.readouterr().err == ""


def test_bracketed_ipv6_uses_explicit_port(ssl_checker, capsys):
    """Pass an IPv6 host and its port separately to the connector."""
    with mock.patch.object(
        ssl_checker,
        "get_cert_expiry",
        return_value=(40, "future expiry", True, None),
    ) as connect:
        result = ssl_checker.check_url("[::1]:8443")
    connect.assert_called_once_with("::1", port=8443)
    assert result is not None
    assert capsys.readouterr().err == ""


def test_hostname_encoding_error_is_a_failed_result(ssl_checker, capsys):
    """Report hostname encoding failures without a traceback."""
    with mock.patch.object(
        ssl_checker.socket,
        "create_connection",
        side_effect=UnicodeError("hostname encoding error"),
    ):
        result = ssl_checker.check_url("bad-host.invalid")
    assert result is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR" in captured.err
    assert "bad-host.invalid" in captured.err
    assert "hostname encoding error" in captured.err
    assert "Traceback" not in captured.err


def test_main_prints_valid_results_and_fails_if_any_result_failed(sandbox, ssl_checker):
    """Keep successful output while returning failure for invalid URLs."""
    pool = mock.MagicMock()
    pool.__enter__.return_value.map.side_effect = lambda function, urls: list(
        map(function, urls)
    )
    with (
        mock.patch.object(ssl_checker, "Pool", return_value=pool),
        mock.patch.object(
            ssl_checker,
            "get_cert_expiry",
            return_value=(40, "future expiry", True, None),
        ) as connect,
    ):
        result, stdout, stderr = sandbox.main(
            ssl_checker, "good.invalid", "https:///path"
        )
    assert "good.invalid" in stdout
    assert "40 day(s) left" in stdout
    assert "Expires: future expiry" in stdout
    assert len(stdout.splitlines()) == 1
    assert "Invalid URL" not in stdout
    assert "None" not in stdout
    assert "Invalid URL" in stderr
    assert "https:///path" in stderr
    assert "Traceback" not in stderr
    connect.assert_called_once_with("good.invalid", port=443)
    pool.__enter__.return_value.map.assert_called_once_with(
        ssl_checker.check_url, ["good.invalid", "https:///path"]
    )
    assert result == 1


def test_help_succeeds_without_dictionary(sandbox, dictionary):
    """Show help without requiring a dictionary."""
    result = sandbox.cli("mkpass", "--help")
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert not dictionary.exists()


def test_missing_dictionary_fails_cleanly(sandbox):
    """Explain a missing dictionary without a traceback."""
    result = sandbox.cli("mkpass", "1")
    assert_clean_failure(result, "Cannot load")


def test_4096_unique_nonblank_words_are_accepted(sandbox, write_words):
    """Accept a dictionary meeting the distinct-word minimum."""
    expected = write_words()
    result = sandbox.cli("mkpass", "1")
    assert result.returncode == 0, result.stderr
    match = re.fullmatch(
        r"((?:word|Word)\d{4})[-_!$&*+=2-9]((?:word|Word)\d{4})[-_!$&*+=2-9]((?:word|Word)\d{4})",
        result.stdout.strip(),
    )
    assert match is not None
    assert all(word.lower() in expected for word in match.groups())


def test_duplicate_and_blank_lines_do_not_count_toward_minimum(
    sandbox, dictionary, write_words
):
    """Reject undersized dictionaries despite duplicate or blank entries."""
    words = write_words(4095)
    with dictionary.open("a") as stream:
        stream.write("\n  \n" + words[0] + "\n" + words[1] + "\n")
    result = sandbox.cli("mkpass", "1")
    assert_clean_failure(result, "distinct words")


def test_duplicate_and_blank_lines_are_removed_from_valid_dictionary(
    sandbox, dictionary, write_words
):
    """Normalize whitespace and deduplicate dictionary entries."""
    expected = write_words()
    with dictionary.open("a") as stream:
        stream.write("\n \n  word0000  \n")
    mkpass = sandbox.load_script("mkpass")
    words = mkpass.load_words()
    assert words == expected
    with mock.patch(
        "random.SystemRandom.choice", side_effect=lambda items: items[0]
    ) as choice:
        password = mkpass.generate_password(words)
    assert password.lower() == "word0000-word0000-word0000"
    assert choice.call_args_list == [
        mock.call(words),
        mock.call("-_!$&*+=23456789"),
        mock.call(words),
        mock.call("-_!$&*+=23456789"),
        mock.call(words),
    ]
    assert all(call.args[0] is words for call in choice.call_args_list[::2])


def test_count_cli_emits_exactly_requested_passwords(sandbox, write_words):
    """Emit the requested number of correctly structured passwords."""
    write_words()
    result = sandbox.cli("mkpass", "3")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 3
    pattern = r"(?:word|Word)\d{4}[-_!$&*+=2-9](?:word|Word)\d{4}[-_!$&*+=2-9](?:word|Word)\d{4}"
    for password in result.stdout.splitlines():
        assert re.fullmatch(pattern, password)


@pytest.mark.parametrize("count", ["0", "-1"])
def test_nonpositive_count_is_rejected_before_dictionary_load(sandbox, count):
    """Validate the requested count before reading the dictionary."""
    result = sandbox.cli("mkpass", count)
    assert_clean_failure(result, "positive integer")
    assert "Cannot load" not in result.stderr


def test_grid_reserves_one_row_for_prompt(sandbox, mkpass):
    """Fit the password grid within the available terminal space."""
    with (
        mock.patch.object(mkpass, "generate_password", return_value="abc-def-ghi"),
        mock.patch.object(
            mkpass.shutil,
            "get_terminal_size",
            return_value=os.terminal_size((40, 5)),
        ),
    ):
        result, stdout, stderr = sandbox.main(mkpass)
    assert result == 0, stderr
    assert len(stdout.splitlines()) == 4
    assert all(len(line) <= 40 for line in stdout.splitlines())
    assert all(line.split() == ["abc-def-ghi"] * 3 for line in stdout.splitlines())


def test_empty_string_and_file_conflict(sandbox):
    """Reject conflicting inputs without altering the input file."""
    source = sandbox.root / "input"
    source.write_text("hello")
    result = sandbox.cli("rot13", "--string", "", source)
    assert_clean_failure(result, "either")
    assert source.read_text() == "hello"
    assert result.stdout == ""


def test_empty_string_and_stdin_dash_conflict(sandbox):
    """Reject an empty string combined with explicit stdin input."""
    result = sandbox.cli("rot13", "--string", "", "-", input_text="do not consume")
    assert_clean_failure(result, "either")
    assert result.stdout == ""


def test_empty_string_alone_outputs_nothing(sandbox):
    """Treat an empty string as input instead of falling back to stdin."""
    result = sandbox.cli("rot13", "--string", "", input_text="do not consume")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_parallel_normalization_stops_at_option_terminator(indirs):
    """Leave arguments after the option terminator unchanged."""
    argv = ["--parallel=2", "--", "--parallel=9", "--parallel=3"]
    assert indirs.normalize_parallel_args(argv) == [
        "--worker-count=2",
        "--",
        "--parallel=9",
        "--parallel=3",
    ]


def test_invalid_directory_does_not_prevent_later_valid_directory(
    sandbox, indirs, directories
):
    """Continue processing valid directories after a missing directory."""
    missing = sandbox.root / "missing"
    with mock.patch.object(indirs, "run_in_directory", return_value=True) as run:
        result, _, stderr = sandbox.main(indirs, "command", missing, directories[0])
    assert result == 1
    assert "not a directory" in stderr
    run.assert_called_once_with(directories[0], "command", None)


@pytest.mark.parametrize(
    ("option", "expected_workers"),
    [
        pytest.param("--parallel=2", 2, id="explicit-worker-count"),
        pytest.param("--parallel", 3, id="default-cpu-count"),
    ],
)
def test_parallel_runs_all_directories(
    sandbox, indirs, directories, option, expected_workers
):
    """Honor the worker count and run every directory despite one failure."""

    def run(directory, command, _argv, *, capture_output):
        assert capture_output
        (directory / "result").write_text(command)
        result = subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        error = "command failed" if directory == directories[1] else None
        return result, error

    with (
        mock.patch.object(indirs.os, "cpu_count", return_value=3),
        mock.patch.object(
            indirs, "ThreadPoolExecutor", wraps=ThreadPoolExecutor
        ) as executor,
        mock.patch.object(indirs, "run_command", side_effect=run),
    ):
        result, _, _ = sandbox.main(indirs, option, "marker", *directories)
    executor.assert_called_once_with(max_workers=expected_workers)
    assert result == 1
    assert {
        directory.name: (directory / "result").read_text() for directory in directories
    } == {"first": "marker", "second": "marker", "third": "marker"}


def test_no_shell_preserves_literal_glob(sandbox, directories):
    """Pass glob characters literally when shell execution is disabled."""
    directory = directories[0]
    (directory / "would-expand.txt").write_text("payload")
    command = shlex.join(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "*.txt"]
    )
    result = sandbox.cli("indirs", "--no-shell", command, directory)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "*.txt\n"


@pytest.mark.parametrize("options", [[], ["--parallel=2"]])
@pytest.mark.parametrize("no_shell", [[], ["--no-shell"]])
def test_indirs_header_preserves_spelling_before_output(
    sandbox, directories, options, no_shell
):
    """Keep dot prefixes, repeated separators and trailing slashes in headers."""
    spellings = ["./first/", "second//", "./third/../third/"]
    command = shlex.join(
        [sys.executable, "-c", "import os; print(os.path.basename(os.getcwd()))"]
    )
    result = sandbox.cli("indirs", *options, *no_shell, "--header", command, *spellings)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "".join(
        f"\x1b[32m{spelling}\x1b[0m\n{directory.name}\n"
        for spelling, directory in zip(spellings, directories, strict=True)
    )
    assert result.stderr == ""


@pytest.mark.parametrize("header", [[], ["--header"]])
def test_indirs_parallel_groups_overlapping_stdout_and_stderr(
    sandbox, directories, header
):
    """Drain both pipes and publish whole invocations despite forced overlap."""
    command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time; "
                "directory = pathlib.Path.cwd(); name = directory.name; "
                "print(name + ':start', flush=True); "
                "print(name + ':start', file=sys.stderr, flush=True); "
                "(directory / 'started').touch(); "
                "deadline = time.monotonic() + 5\n"
                "while len(list(directory.parent.glob('*/started'))) < 2:\n"
                "    if time.monotonic() > deadline: sys.exit(9)\n"
                "    time.sleep(0.01)\n"
                "sys.stdout.write(name + ':out:' + 'x' * 100000 + '\\n'); "
                "sys.stdout.flush(); "
                "sys.stderr.write(name + ':err:' + 'y' * 100000 + '\\n'); "
                "sys.stderr.flush(); "
                "print(name + ':end', flush=True); "
                "print(name + ':end', file=sys.stderr, flush=True)"
            ),
        ]
    )
    paths = directories[:2]
    result = sandbox.cli(
        "indirs", "--parallel=2", "--no-shell", *header, command, *paths
    )
    assert result.returncode == 0, result.stderr
    order = [
        line.split(":")[0] for line in result.stdout.splitlines() if ":start" in line
    ]
    assert set(order) == {path.name for path in paths}
    headers = {
        path.name: f"\x1b[32m{path}\x1b[0m\n" if header else "" for path in paths
    }
    assert result.stdout == "".join(
        f"{headers[name]}{name}:start\n{name}:out:{'x' * 100000}\n{name}:end\n"
        for name in order
    )
    assert result.stderr == "".join(
        f"{name}:start\n{name}:err:{'y' * 100000}\n{name}:end\n" for name in order
    )


@pytest.mark.parametrize("options", [[], ["--parallel"], ["--parallel=2"]])
def test_indirs_command_failure_continues_with_headers(sandbox, directories, options):
    """Keep output and headers from every valid directory after a command fails."""
    command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, sys; name = pathlib.Path.cwd().name; "
                "print(name); print(name, file=sys.stderr); sys.exit(name == 'first')"
            ),
        ]
    )
    spellings = [f"./{directory.name}/" for directory in directories[:2]]
    result = sandbox.cli(
        "indirs", *options, "--no-shell", "--header", command, "missing", *spellings
    )
    assert_clean_failure(result, "not a directory")
    assert "exit status 1" in result.stderr
    assert (
        result.stdout
        == "\x1b[32m./first/\x1b[0m\nfirst\n\x1b[32m./second/\x1b[0m\nsecond\n"
    )
    assert "first\n" in result.stderr
    assert "second\n" in result.stderr
    assert result.returncode == 1


@pytest.mark.parametrize("options", [[], ["--parallel=2"]])
def test_indirs_missing_executable_continues_cleanly(sandbox, directories, options):
    """Report launch errors for every invocation without a traceback."""
    result = sandbox.cli(
        "indirs",
        *options,
        "--header",
        "--no-shell",
        "./missing-executable",
        *directories,
    )
    assert_clean_failure(result, "could not run command")
    assert result.returncode == 1
    assert result.stdout == "".join(f"\x1b[32m{path}\x1b[0m\n" for path in directories)
    for path in directories:
        assert f"could not run command in {path}:" in result.stderr


@pytest.mark.parametrize("count", ["0", "-1", "bad", ""])
def test_indirs_header_does_not_change_invalid_worker_count(sandbox, count):
    """Reject invalid worker counts before starting any command."""
    result = sandbox.cli("indirs", "--header", f"--parallel={count}", "unused", ".")
    assert_clean_failure(result, "worker count must be a positive integer")
    assert result.returncode == 2
    assert result.stdout == ""


def test_indirs_sequential_header_precedes_launch_without_capturing(
    sandbox, indirs, directories
):
    """Leave subprocess streams inherited and print the header before launching."""

    def run(command, **kwargs):
        assert sys.stdout.getvalue() == "\x1b[32m./first/\x1b[0m\n"
        assert not kwargs["capture_output"]
        assert kwargs["cwd"] == directories[0].relative_to(sandbox.root)
        assert not kwargs["shell"]
        assert "stdout" not in kwargs
        assert "stderr" not in kwargs
        print("streamed stdout")
        print("streamed stderr", file=sys.stderr)
        return subprocess.CompletedProcess(command, 0)

    with mock.patch.object(indirs.subprocess, "run", side_effect=run):
        result, stdout, stderr = sandbox.main(
            indirs, "--header", "--no-shell", "command", "./first/"
        )
    assert result == 0
    assert stdout == "\x1b[32m./first/\x1b[0m\nstreamed stdout\n"
    assert stderr == "streamed stderr\n"


def test_indirs_parallel_publication_groups_both_channels_and_diagnostics(
    indirs, directories
):
    """Finish every block, including stderr, before publishing another header."""
    stream = io.StringIO()
    spellings = [f"./{path.name}/" for path in directories]

    def run(directory, command, _argv, *, capture_output):
        assert capture_output
        name = directory.name
        result = subprocess.CompletedProcess(
            command, 0, stdout=f"{name} out\n", stderr=f"{name} err\n"
        )
        return result, "indirs: failure" if directory == directories[1] else None

    with (
        mock.patch.object(indirs, "run_command", side_effect=run),
        mock.patch.object(sys, "stdout", stream),
        mock.patch.object(sys, "stderr", stream),
    ):
        failed = indirs.run_parallel(
            list(zip(directories, spellings, strict=True)),
            "command",
            None,
            2,
            header=True,
        )
    assert failed
    assert stream.getvalue() == (
        "\x1b[32m./first/\x1b[0m\nfirst out\nfirst err\n"
        "\x1b[32m./second/\x1b[0m\nsecond out\nsecond err\nindirs: failure\n"
        "\x1b[32m./third/\x1b[0m\nthird out\nthird err\n"
    )


@pytest.mark.parametrize("options", [[], ["--parallel=2"]])
def test_indirs_option_terminator_preserves_header_directory(sandbox, options):
    """Treat a directory named like the flag as positional after the terminator."""
    (sandbox.root / "--header").mkdir()
    command = shlex.join([sys.executable, "-c", "print('plain')"])
    result = sandbox.cli("indirs", *options, "--no-shell", "--", command, "--header")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "plain\n"


@pytest.mark.parametrize("command", ["", "'unclosed"])
def test_indirs_header_preserves_no_shell_validation(sandbox, command):
    """Fail argument validation before emitting a header or starting a command."""
    result = sandbox.cli("indirs", "--no-shell", "--header", command, ".")
    assert_clean_failure(result, "command")
    assert result.returncode == 2
    assert result.stdout == ""
