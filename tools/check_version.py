"""Verify that the release tag, Python package version, and project version agree."""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elp_console import __version__


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if match is None:
        raise ValueError("Could not read project.version from pyproject.toml")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Optional v-prefixed release tag to validate")
    args = parser.parse_args()

    pyproject_version = project_version()
    if pyproject_version != __version__:
        raise SystemExit(
            f"Version mismatch: pyproject.toml={pyproject_version}, elp_console={__version__}"
        )
    if args.tag and args.tag != f"v{__version__}":
        raise SystemExit(f"Tag {args.tag} must match v{__version__}")
    print(f"Version OK: v{__version__}")


if __name__ == "__main__":
    main()
