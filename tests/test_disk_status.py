"""Check host configuration, remote df parsing, and disk usage reporting offline."""

import subprocess
from unittest import mock

import pytest

from tests.support import assert_clean_failure

DF_HEADER = "Filesystem Size Used Avail Use% Mounted on\n"


@pytest.fixture
def disk_status(sandbox):
    return sandbox.load_script("disk_status")


@pytest.mark.parametrize("contents", [None, "", " \n# comment\n\t# another\n"])
def test_absent_or_empty_config_has_no_hosts(sandbox, disk_status, contents):
    assert sandbox.home / ".disk_status" == disk_status.CONFIG_FILE
    if contents is not None:
        disk_status.CONFIG_FILE.write_text(contents)
    assert disk_status.read_config() == []


def test_config_strips_comments_and_keeps_host_order(disk_status):
    disk_status.CONFIG_FILE.write_text(
        "# servers\n  alice@first.invalid # primary\n\n\tsecond.invalid\t\n"
        "alice@first.invalid # repeat\n"
    )
    assert disk_status.read_config() == [
        "alice@first.invalid",
        "second.invalid",
        "alice@first.invalid",
    ]


def test_run_df_parses_rows_and_mount_paths_with_spaces(disk_status):
    output = (
        DF_HEADER
        + "/dev/a 100G 90G 10G 90% /\n"
        + "short row\n\n"
        + "/dev/b 200G 182G 18G 91% /media/My Disk\n"
    )
    with mock.patch.object(
        disk_status.subprocess, "check_output", return_value=output
    ) as ssh:
        rows = disk_status.run_df("alice@offline.invalid")
    assert rows == [
        {"fs": "/dev/a", "size": "100G", "used": "90G", "use_pct": 90, "mount": "/"},
        {
            "fs": "/dev/b",
            "size": "200G",
            "used": "182G",
            "use_pct": 91,
            "mount": "/media/My Disk",
        },
    ]
    ssh.assert_called_once_with(
        [
            "ssh",
            "-o",
            "ConnectTimeout=5",
            "alice@offline.invalid",
            "df -hPx tmpfs -x devtmpfs -x proc -x sysfs -x cgroup -x squashfs",
        ],
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_empty_df_output_has_no_disks(disk_status):
    with mock.patch.object(disk_status.subprocess, "check_output", return_value=""):
        assert disk_status.run_df("offline.invalid") == []


def test_default_hosts_are_checked_and_threshold_formatting_is_exact(
    sandbox, disk_status
):
    disk_status.CONFIG_FILE.write_text("first.invalid # first\nsecond.invalid\n")
    with mock.patch.object(
        disk_status.subprocess,
        "check_output",
        side_effect=[
            DF_HEADER + "/dev/a 100G 90G 10G 90% /data\n",
            DF_HEADER + "/dev/b 100G 91G 9G 91% /backup\n",
        ],
    ) as ssh:
        status, stdout, stderr = sandbox.main(disk_status)
    assert status == 0
    assert stderr == ""
    assert [call.args[0][3] for call in ssh.call_args_list] == [
        "first.invalid",
        "second.invalid",
    ]
    assert stdout == (
        "\033[30m\n--- first.invalid ---\033[0m\n"
        f"\033[32m{'/data':30}  90% used (90G of 100G used) \033[0m\n"
        "\033[30m\n--- second.invalid ---\033[0m\n"
        f"\033[31m{'/backup':30}  91% used (91G of 100G used) ⚠  WARNING: above 90%\033[0m\n"
        "\nChecks complete.\n"
    )


def test_explicit_hosts_bypass_config(sandbox, disk_status):
    with (
        mock.patch.object(disk_status, "read_config") as config,
        mock.patch.object(disk_status, "run_df", return_value=[]) as run,
    ):
        status, stdout, stderr = sandbox.main(disk_status, "explicit.invalid")
    assert status == 0
    assert "Checks complete." in stdout
    assert stderr == ""
    config.assert_not_called()
    run.assert_called_once_with("explicit.invalid")


def test_no_default_hosts_is_a_clean_cli_failure(sandbox):
    result = sandbox.cli("disk_status")
    assert_clean_failure(result, "No hosts given and none found in")
    assert str(sandbox.home / ".disk_status") in result.stderr
    assert result.returncode == 1
    assert result.stdout == ""


@pytest.mark.parametrize("kind", ["directory", "invalid-utf8"])
def test_unreadable_config_returns_failure_before_ssh(sandbox, disk_status, kind):
    if kind == "directory":
        disk_status.CONFIG_FILE.mkdir()
    else:
        disk_status.CONFIG_FILE.write_bytes(b"\xff")
    with mock.patch.object(disk_status, "run_df") as run:
        status, stdout, stderr = sandbox.main(disk_status)
    assert status == 1
    assert stdout == ""
    assert f"Cannot load {disk_status.CONFIG_FILE}:" in stderr
    assert "Traceback" not in stderr
    run.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "detail"),
    [
        (subprocess.CalledProcessError(255, ["ssh"]), ""),
        (
            subprocess.CalledProcessError(255, ["ssh"], output="permission denied\n"),
            "permission denied",
        ),
        (FileNotFoundError("ssh unavailable"), "ssh unavailable"),
    ],
    ids=["no-error-output", "text-error-output", "missing-ssh"],
)
def test_failed_host_does_not_prevent_later_host_checks(
    sandbox, disk_status, failure, detail
):
    with mock.patch.object(
        disk_status.subprocess,
        "check_output",
        side_effect=[failure, DF_HEADER + "/dev/a 10G 1G 9G 10% /ok\n"],
    ) as ssh:
        status, stdout, stderr = sandbox.main(
            disk_status, "bad.invalid", "good.invalid"
        )
    assert status == 1
    assert ssh.call_count == 2
    assert "SSH failed for bad.invalid:" in stderr
    assert detail in stderr
    assert "Traceback" not in stderr
    assert "/ok" in stdout
    assert "10% used" in stdout
    assert "Checks complete." in stdout


def test_config_permission_error_is_reported(sandbox, disk_status):
    disk_status.CONFIG_FILE.touch()
    with (
        mock.patch.object(
            disk_status.pathlib.Path,
            "read_text",
            side_effect=PermissionError("config denied"),
        ),
        mock.patch.object(disk_status, "run_df") as run,
    ):
        status, stdout, stderr = sandbox.main(disk_status)
    assert status == 1
    assert stdout == ""
    assert stderr == f"Cannot load {disk_status.CONFIG_FILE}: config denied\n"
    run.assert_not_called()
