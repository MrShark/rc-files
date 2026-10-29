"""Exercise ROT13 input selection, UTF-8 IO, and clean CLI failures."""

import io
from types import SimpleNamespace
from unittest import mock

import pytest

from tests.support import assert_clean_failure


@pytest.fixture
def rot13(sandbox):
    return sandbox.load_script("rot13")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        ("Hello, World!", "Uryyb, Jbeyq!"),
        ("Ångström café 日本語 🐍 123\n", "Åatfgeöz pnsé 日本語 🐍 123\n"),
    ],
)
def test_string_is_encoded_without_adding_a_newline(sandbox, rot13, text, expected):
    with mock.patch.object(rot13.sys, "stdin") as stdin:
        status, stdout, stderr = sandbox.main(rot13, "--string", text)
    assert status == 0
    assert stdout == expected
    assert stderr == ""
    stdin.buffer.read.assert_not_called()


@pytest.mark.parametrize("args", [(), ("-",)])
def test_stdin_bytes_are_decoded_as_utf8(sandbox, rot13, args):
    stdin = SimpleNamespace(buffer=io.BytesIO("Hello café 日本語\n".encode()))
    with mock.patch.object(rot13.sys, "stdin", stdin):
        status, stdout, stderr = sandbox.main(rot13, *args)
    assert status == 0
    assert stdout == "Uryyb pnsé 日本語\n"
    assert stderr == ""


def test_file_input_preserves_unicode_and_source(sandbox, rot13):
    source = sandbox.root / "input"
    source.write_text("Hello café 日本語\n", encoding="utf-8")
    status, stdout, stderr = sandbox.main(rot13, source)
    assert status == 0
    assert stdout == "Uryyb pnsé 日本語\n"
    assert stderr == ""
    assert source.read_text(encoding="utf-8") == "Hello café 日本語\n"


def test_cli_encodes_stdin_to_stdout(sandbox):
    result = sandbox.cli("rot13", "-", input_text="Hello café 日本語\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Uryyb pnsé 日本語\n"
    assert result.stderr == ""


def test_writes_utf8_output_file_instead_of_stdout(sandbox):
    output = sandbox.root / "output"
    output.write_text("old content to replace", encoding="utf-8")
    result = sandbox.invoke("rot13", "-s", "Hello café 日本語", "-o", output)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert output.read_bytes() == "Uryyb pnsé 日本語".encode()


@pytest.mark.parametrize("input_kind", ["missing", "directory"])
def test_nonfile_input_is_a_clean_error(sandbox, input_kind):
    source = sandbox.root / "input"
    if input_kind == "directory":
        source.mkdir()
    result = sandbox.invoke("rot13", source)
    assert_clean_failure(result, f"input file not found: {source}")
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("input_kind", ["file", "stdin"])
def test_invalid_utf8_is_a_clean_error_without_output(sandbox, rot13, input_kind):
    source = sandbox.root / "input"
    source.write_bytes(b"\xff")
    output = sandbox.root / "output"
    stdin = SimpleNamespace(buffer=io.BytesIO(b"\xff"))
    with mock.patch.object(rot13.sys, "stdin", stdin):
        status, stdout, stderr = sandbox.main(
            rot13, source if input_kind == "file" else "-", "-o", output
        )
    assert status == 1
    assert stdout == ""
    assert stderr.startswith("Error: ")
    assert "utf-8" in stderr
    assert "Traceback" not in stderr
    assert not output.exists()


def test_read_permission_error_is_reported(sandbox, rot13):
    source = sandbox.root / "input"
    source.touch()
    with mock.patch.object(
        rot13.Path, "read_text", side_effect=PermissionError("input denied")
    ):
        status, stdout, stderr = sandbox.main(rot13, source)
    assert status == 1
    assert stdout == ""
    assert stderr == "Error: input denied\n"


def test_unwritable_output_is_a_clean_error(sandbox):
    output = sandbox.root / "missing-parent" / "output"
    result = sandbox.invoke("rot13", "-s", "Hello", "-o", output)
    assert_clean_failure(result, "Error:")
    assert str(output) in result.stderr
    assert result.returncode == 1
    assert result.stdout == ""
    assert not output.exists()


@pytest.mark.parametrize("text", ["", "Hello"])
@pytest.mark.parametrize("source", ["input", "-"])
def test_conflicting_inputs_do_not_read_or_write(sandbox, rot13, text, source):
    output = sandbox.root / "output"
    output.write_text("keep me")
    source_path = sandbox.root / source
    if source != "-":
        source_path.write_text("source payload")
    with (
        mock.patch.object(rot13.Path, "read_text") as read,
        mock.patch.object(rot13.sys, "stdin") as stdin,
    ):
        status, stdout, stderr = sandbox.main(rot13, "-s", text, source, "-o", output)
    assert status == 2
    assert stdout == ""
    assert "Specify either" in stderr
    assert "Traceback" not in stderr
    read.assert_not_called()
    stdin.buffer.read.assert_not_called()
    assert output.read_text() == "keep me"
    if source != "-":
        assert source_path.read_text() == "source payload"


def test_help_describes_input_and_output_options(sandbox):
    result = sandbox.invoke("rot13", "--help")
    assert result.returncode == 0
    assert "--string" in result.stdout
    assert "--output" in result.stdout
    assert result.stderr == ""
