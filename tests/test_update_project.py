"""Test hook discovery and Git failures without invoking external tools."""

import subprocess
from unittest import mock

import pytest


@pytest.fixture
def update_project(sandbox):
    return sandbox.load_script("update_project")


@pytest.fixture
def hook_project(sandbox, update_project, monkeypatch):
    monkeypatch.chdir(sandbox.root)
    monkeypatch.setattr(update_project, "command_exists", lambda _name: True)
    return update_project


def diff_result(status):
    """Build a synthetic Git diff result with diagnostic output."""
    return subprocess.CompletedProcess(
        ["git", "diff", "--cached", "--quiet"], status, "", "git diff detail"
    )


# These public methods call a missing _find_config in the original script.
def test_no_config_is_not_applicable_and_has_no_state(hook_project):
    """Treat an absent hook config as inapplicable with empty state."""
    updater = hook_project.HookUpdater()
    assert not updater.is_applicable()
    assert updater.capture_state() == {}
    assert updater.tracked_files() == []


def test_no_config_update_is_rejected_without_running_commands(hook_project):
    """Reject updates without a hook config before running commands."""
    updater = hook_project.HookUpdater()
    with (
        mock.patch.object(hook_project, "run") as run,
        pytest.raises(RuntimeError, match="config"),
    ):
        updater.update()
    run.assert_not_called()


@pytest.mark.parametrize(
    ("name", "content"),
    [
        pytest.param(
            "prek.toml",
            '[[repos]]\nrepo = "https://example.invalid/hooks"\nrev = "v1"\n',
            id="prek-toml",
        ),
        pytest.param(
            ".pre-commit-config.yaml",
            "repos:\n  - repo: https://example.invalid/hooks\n    rev: v1\n",
            id="yaml",
        ),
        pytest.param(
            ".pre-commit-config.yml",
            "repos:\n  - repo: https://example.invalid/hooks\n    rev: v1\n",
            id="yml",
        ),
    ],
)
def test_hook_config_is_discovered_and_parsed(sandbox, hook_project, name, content):
    """Discover supported configs, capture revisions, and update explicitly."""
    config = sandbox.root / name
    config.write_text(content)
    updater = hook_project.HookUpdater()
    assert updater.is_applicable()
    assert updater.is_available()
    assert updater.capture_state() == {"https://example.invalid/hooks": "v1"}
    assert updater.tracked_files() == [name]
    with mock.patch.object(hook_project, "run") as run:
        updater.update()
    run.assert_called_once_with(["prek", "auto-update", "--config", str(config)])


def test_config_discovery_prefers_prek_toml(sandbox, hook_project):
    """Prefer prek TOML when all supported config names are present."""
    for name in ("prek.toml", ".pre-commit-config.yaml", ".pre-commit-config.yml"):
        (sandbox.root / name).write_text("")
    assert hook_project.HookUpdater().tracked_files() == ["prek.toml"]


def test_pre_commit_fallback_uses_its_own_subcommand(sandbox, hook_project):
    """Use pre-commit's update spelling when prek is unavailable."""
    config = sandbox.root / ".pre-commit-config.yaml"
    config.write_text("repos: []\n")
    with mock.patch.object(
        hook_project, "command_exists", side_effect=lambda name: name == "pre-commit"
    ):
        updater = hook_project.HookUpdater()
    assert updater.is_available()
    with mock.patch.object(hook_project, "run") as run:
        updater.update()
    run.assert_called_once_with(["pre-commit", "autoupdate", "--config", str(config)])


def test_pre_commit_alone_cannot_update_toml(sandbox, hook_project):
    """Keep TOML configs unavailable when only pre-commit is installed."""
    (sandbox.root / "prek.toml").write_text("")
    with mock.patch.object(
        hook_project, "command_exists", side_effect=lambda name: name == "pre-commit"
    ):
        updater = hook_project.HookUpdater()
    assert not updater.is_available()


def test_git_diff_zero_means_no_staged_changes(update_project):
    """Treat Git diff status zero as an unchanged index."""
    with mock.patch.object(
        update_project.subprocess, "run", return_value=diff_result(0)
    ) as run:
        assert not update_project.has_staged_changes()
    run.assert_called_once_with(
        ["git", "diff", "--cached", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_git_diff_one_means_staged_changes(update_project):
    """Treat Git diff status one as a changed index."""
    with mock.patch.object(
        update_project.subprocess, "run", return_value=diff_result(1)
    ):
        assert update_project.has_staged_changes()


def test_git_diff_greater_than_one_preserves_failure_details(update_project):
    """Preserve Git's error status and diagnostic for actual failures."""
    with (
        mock.patch.object(
            update_project.subprocess, "run", return_value=diff_result(128)
        ),
        pytest.raises(subprocess.CalledProcessError, match="128") as caught,
    ):
        update_project.has_staged_changes()
    assert caught.value.returncode == 128
    assert "git diff detail" in caught.value.stderr


def test_checkout_unrelated_failure_preserves_message_and_stops_updates(
    sandbox, update_project
):
    """Stop updates and preserve unrelated checkout error details."""
    error = subprocess.CalledProcessError(
        128,
        ["git", "checkout", "-b", "test-branch"],
        stderr="permission denied on index.lock",
    )

    def git(args):
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(["git", *args], 0, "", "")
        raise error

    with (
        mock.patch.object(update_project, "find_tools", return_value=[mock.Mock()]),
        mock.patch.object(update_project, "git", side_effect=git),
        mock.patch.object(update_project, "update_tool") as update,
    ):
        result, _, stderr = sandbox.main(update_project, "--branch", "test-branch")
    assert result == 1
    assert "permission denied on index.lock" in stderr
    assert "checkout" in stderr
    assert "already exists" not in stderr
    assert "Traceback" not in stderr
    update.assert_not_called()


def test_no_config_workflow_returns_failure_without_git(
    sandbox, update_project, monkeypatch
):
    """Skip Git entirely when no updater has an applicable config."""
    monkeypatch.chdir(sandbox.root)
    with (
        mock.patch.object(update_project, "UPDATERS", [update_project.HookUpdater()]),
        mock.patch.object(update_project, "git") as git,
    ):
        result, _, stderr = sandbox.main(update_project, "--dry-run")
    assert result == 1
    assert "No applicable updaters" in stderr
    git.assert_not_called()
