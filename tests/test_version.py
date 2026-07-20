import subprocess
import sys

from elp_console import __version__
from tools.check_version import project_version


def test_project_and_runtime_versions_match():
    assert project_version() == __version__


def test_version_cli():
    result = subprocess.run(
        [sys.executable, "main.py", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip().endswith(f"v{__version__}")


def test_version_check_script_runs_from_tools_directory():
    result = subprocess.run(
        [sys.executable, "tools/check_version.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"Version OK: v{__version__}"
