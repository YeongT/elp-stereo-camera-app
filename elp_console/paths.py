"""Project-relative locations for generated application data and diagnostics."""

from pathlib import Path


RUNTIME_DIR = Path(".runtime")
ARTIFACTS_DIR = Path(".artifacts")

PROFILES_PATH = RUNTIME_DIR / "profiles.json"
CALIBRATION_DIR = RUNTIME_DIR / "calibration"
CAPTURES_DIR = RUNTIME_DIR / "captures"
UI_ARTIFACTS_DIR = ARTIFACTS_DIR / "ui"
