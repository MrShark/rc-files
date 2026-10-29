"""Exercise rename planning, payload preservation, and rollback on real temp files."""

import contextlib
import io
from collections import Counter
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def mv_count(sandbox):
    return sandbox.load_script("mv_count")


@pytest.fixture
def work(sandbox):
    path = sandbox.root / "work"
    path.mkdir()
    return path


@pytest.fixture
def make_file(work):
    def create(name, content=None):
        path = work / name
        path.write_bytes(content if content is not None else name.encode())
        return path

    return create


@pytest.fixture
def file_contents(work):
    def read():
        return {path.name: path.read_bytes() for path in work.iterdir()}

    return read


@pytest.fixture
def rename(mv_count):
    def run(sources, destinations):
        with contextlib.redirect_stdout(io.StringIO()):
            mv_count.rename_all(sources, destinations)

    return run


@pytest.fixture
def reject_plan(sandbox, mv_count):
    def check(args, fragment):
        with mock.patch.object(mv_count, "rename_all") as transaction:
            result, _, stderr = sandbox.main(mv_count, *args)
        assert result == 1
        assert fragment in stderr
        assert "Traceback" not in stderr
        transaction.assert_not_called()

    return check


def test_normal_cli_renames_preserve_contents(sandbox, work, make_file, file_contents):
    """Preserve both payloads during ordinary sequential renames."""
    first, second = make_file("a"), make_file("b")
    result = sandbox.cli("mv_count", "-p", work / "file-{}", first, second)
    assert result.returncode == 0, result.stderr
    assert file_contents() == {"file-1": b"a", "file-2": b"b"}


def test_overlapping_cli_renames_preserve_both_sources(
    sandbox, work, make_file, file_contents
):
    """Preserve a source that is also another source's destination."""
    first, second = make_file("a"), make_file("file-1")
    result = sandbox.cli("mv_count", "-f", "-p", work / "file-{}", first, second)
    assert result.returncode == 0, result.stderr
    assert file_contents() == {"file-1": b"a", "file-2": b"file-1"}


def test_self_rename_leaves_payload_untouched(sandbox, work, make_file, file_contents):
    """Leave a file intact when its destination equals its source."""
    source = make_file("file-1")
    result = sandbox.cli("mv_count", "-p", work / "file-{}", source)
    assert result.returncode == 0, result.stderr
    assert file_contents() == {"file-1": b"file-1"}


def test_cycle_swaps_contents_without_loss(mv_count, make_file, rename, file_contents):
    """Swap two source paths without losing either payload."""
    first, second = make_file("a"), make_file("b")
    mv_count.check_conflicts([first, second], [second, first], force=True)
    rename([first, second], [second, first])
    assert file_contents() == {"a": b"b", "b": b"a"}


def test_duplicate_sources_are_rejected_before_mutation(
    make_file, reject_plan, file_contents
):
    """Reject equivalent source paths without altering any file."""
    source = make_file("a")
    reject_plan([source, source.parent / "." / source.name], "duplicate source")
    assert file_contents() == {"a": b"a"}


@pytest.mark.parametrize(
    "pattern",
    [
        pytest.param(
            "{",
        ),
        pytest.param(
            "{missing}",
        ),
        pytest.param(
            "{1}",
        ),
        pytest.param(
            "{:invalid}",
        ),
        pytest.param(
            "{0.missing}",
        ),
    ],
)
def test_malformed_formats_are_rejected_before_mutation(
    make_file, reject_plan, file_contents, pattern
):
    """Reject invalid destination patterns without altering any file."""
    source = make_file("a")
    reject_plan(["-p", pattern, source], "invalid pattern")
    assert file_contents() == {"a": b"a"}


def test_duplicate_destinations_are_rejected_before_mutation(
    work, make_file, reject_plan, file_contents
):
    """Reject multiple sources targeting the same destination."""
    first, second = make_file("a"), make_file("b")
    reject_plan(["-p", work / "same", first, second], "duplicate destination")
    assert file_contents() == {"a": b"a", "b": b"b"}


def test_dangling_symlink_destination_is_a_conflict(work, make_file, reject_plan):
    """Preserve dangling destination symlinks when force is disabled."""
    source = make_file("a")
    destination = work / "file-1"
    destination.symlink_to("missing-target")
    reject_plan(["-p", work / "file-{}", source], "already exists")
    assert destination.is_symlink()
    assert destination.readlink() == Path("missing-target")
    assert source.read_bytes() == b"a"


def test_directory_source_is_rejected_before_mutation(work, reject_plan):
    """Reject directory sources and preserve their contents."""
    source = work / "directory"
    source.mkdir()
    child = source / "payload"
    child.write_bytes(b"keep")
    reject_plan([source], "unsupported source")
    assert child.read_bytes() == b"keep"


@pytest.mark.parametrize(
    "parent_name",
    [
        pytest.param(
            "missing",
        ),
        pytest.param(
            "not-a-directory",
        ),
    ],
)
def test_invalid_destination_parents_are_rejected_before_mutation(
    work, make_file, reject_plan, file_contents, parent_name
):
    """Reject destination parents that are missing or not directories."""
    source = make_file("a")
    make_file("not-a-directory")
    reject_plan(
        ["-p", work / parent_name / "file-{}", source], "invalid destination parent"
    )
    assert file_contents() == {"a": b"a", "not-a-directory": b"not-a-directory"}


def test_destination_directory_is_rejected_even_with_force(
    work, make_file, reject_plan
):
    """Never overwrite a destination directory, even with force enabled."""
    source = make_file("a")
    destination = work / "file-1"
    destination.mkdir()
    reject_plan(["-f", "-p", work / "file-{}", source], "destination is a directory")
    assert source.read_bytes() == b"a"
    assert destination.is_dir()


def test_sandbox_cli_does_not_mutate_files(sandbox, work, make_file, file_contents):
    """Describe sandbox renames without changing source files."""
    source = make_file("a")
    result = sandbox.cli("mv_count", "-s", "-p", work / "file-{}", source)
    assert result.returncode == 0, result.stderr
    assert "sandbox" in result.stdout
    assert file_contents() == {"a": b"a"}


def test_staging_failure_recovers_previously_staged_sources(
    work, make_file, rename, file_contents
):
    """Restore staged sources when staging a later source fails."""
    first, second = make_file("a"), make_file("b")
    original = Path.replace

    def replace(path, target):
        if path == second and Path(target).name.startswith(".mv_count-"):
            msg = "injected staging failure"
            raise OSError(msg)
        return original(path, target)

    with (
        mock.patch.object(Path, "replace", replace),
        pytest.raises(SystemExit, match="rename failed"),
    ):
        rename([first, second], [work / "one", work / "two"])
    assert file_contents() == {"a": b"a", "b": b"b"}


def test_publication_failure_recovers_cycle_sources(make_file, rename, file_contents):
    """Restore both original payloads after a cycle publication fails."""
    first, second = make_file("a"), make_file("b")
    original = Path.replace
    failed = False

    def replace(path, target):
        nonlocal failed
        if Path(target) == first and path.name.startswith(".mv_count-") and not failed:
            failed = True
            msg = "injected publication failure"
            raise OSError(msg)
        return original(path, target)

    with (
        mock.patch.object(Path, "replace", replace),
        pytest.raises(SystemExit, match="rename failed"),
    ):
        rename([first, second], [second, first])
    assert failed
    assert file_contents() == {"a": b"a", "b": b"b"}


def test_force_success_overwrites_only_unrelated_destination(
    sandbox, work, make_file, file_contents
):
    """Replace an unrelated destination with the requested source payload."""
    source, destination = make_file("a"), make_file("file-1", b"old destination")
    result = sandbox.cli("mv_count", "-f", "-p", work / "file-{}", source)
    assert result.returncode == 0, result.stderr
    assert file_contents() == {destination.name: b"a"}


def test_force_publication_failure_restores_unrelated_backup(
    mv_count, work, make_file, rename, file_contents
):
    """Restore unrelated destination data after publication fails."""
    first, second = make_file("a"), make_file("b")
    destination = make_file("one", b"unrelated payload")
    last = work / "two"
    mv_count.check_conflicts([first, second], [destination, last], force=True)
    original = Path.replace

    def replace(path, target):
        if Path(target) == last:
            msg = "injected publication failure"
            raise OSError(msg)
        return original(path, target)

    with (
        mock.patch.object(Path, "replace", replace),
        pytest.raises(SystemExit, match="rename failed"),
    ):
        rename([first, second], [destination, last])
    assert file_contents() == {"a": b"a", "b": b"b", "one": b"unrelated payload"}


def test_backup_staging_failure_restores_sources_and_destination(
    make_file, rename, file_contents
):
    """Restore original files when backing up a destination fails."""
    source, destination = make_file("a"), make_file("one", b"unrelated")
    original = Path.replace

    def replace(path, target):
        if path == destination:
            msg = "injected backup failure"
            raise OSError(msg)
        return original(path, target)

    with (
        mock.patch.object(Path, "replace", replace),
        pytest.raises(SystemExit, match="rename failed"),
    ):
        rename([source], [destination])
    assert file_contents() == {"a": b"a", "one": b"unrelated"}


def test_rollback_failure_retains_payload_and_reports_its_location(
    work, make_file, rename, capsys
):
    """Retain recoverable data and report its path if rollback fails."""
    first, second = make_file("a"), make_file("b")
    last = work / "two"
    original = Path.replace

    def replace(path, target):
        if Path(target) in (last, first):
            msg = "injected publish/restore failure"
            raise OSError(msg)
        return original(path, target)

    with (
        mock.patch.object(Path, "replace", replace),
        pytest.raises(SystemExit, match="rename failed"),
    ):
        rename([first, second], [work / "one", last])
    stderr = capsys.readouterr().err
    payloads = {path: path.read_bytes() for path in work.iterdir()}
    assert Counter(payloads.values()) == Counter([b"a", b"b"])
    retained = next(path for path, data in payloads.items() if data == b"a")
    assert retained.name.startswith(".mv_count-")
    assert "Cannot restore" in stderr
    assert "data retained" in stderr
    assert str(retained) in stderr
    assert second.read_bytes() == b"b"
