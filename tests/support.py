"""Sandbox helpers shared by the standalone-script regression tests."""

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Sandbox:
    """Import and run scripts inside a fixture-managed workspace and HOME."""

    root: Path
    home: Path

    def load_script(self, name):
        """Import a repository script without running its CLI entry point."""
        path = ROOT / ("install.py" if name == "install" else f"bin/{name}.py")
        spec = importlib.util.spec_from_file_location(f"regression_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def cli(self, name, *args, input_text=""):
        """Run a script with the current interpreter in the sandbox."""
        return subprocess.run(  # noqa: S603
            [sys.executable, str(ROOT / "bin" / f"{name}.py"), *map(str, args)],
            cwd=self.root,
            env=dict(os.environ, HOME=str(self.home)),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def main(self, module, *args):
        """Capture CLI exit status and output with synthetic arguments."""
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.chdir(self.root),
            mock.patch.object(sys, "argv", [module.__name__, *map(str, args)]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                result = module.main()
            except SystemExit as exc:
                if isinstance(exc.code, str):
                    print(exc.code, file=sys.stderr)
                    result = 1
                else:
                    result = exc.code
        if result is None:
            result = 0
        return result, stdout.getvalue(), stderr.getvalue()


def assert_clean_failure(result, fragment):
    """Require a failed CLI result with a useful error and no traceback."""
    assert result.returncode != 0
    assert fragment in result.stderr
    assert "Traceback" not in result.stderr
