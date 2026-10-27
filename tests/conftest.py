"""Shared filesystem and environment isolation for script regressions."""

import pytest

from tests.support import Sandbox


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Give every test its own workspace and HOME, restoring HOME afterward."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return Sandbox(tmp_path, home)
