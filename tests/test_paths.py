from pathlib import Path

from elp_console.paths import ARTIFACTS_DIR, CALIBRATION_DIR, CAPTURES_DIR, PROFILES_PATH, RUNTIME_DIR, UI_ARTIFACTS_DIR


def test_generated_paths_stay_under_ignored_project_directories():
    assert RUNTIME_DIR == Path(".runtime")
    assert ARTIFACTS_DIR == Path(".artifacts")
    assert PROFILES_PATH.parent == RUNTIME_DIR
    assert CALIBRATION_DIR.parent == RUNTIME_DIR
    assert CAPTURES_DIR.parent == RUNTIME_DIR
    assert UI_ARTIFACTS_DIR.parent == ARTIFACTS_DIR
