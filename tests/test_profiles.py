"""Camera profile tests: mode parsing, persistence, builtin protection."""

import pytest

from elp_console.profiles import (
    BUILTIN_PROFILES,
    CameraProfile,
    find_profile,
    format_mode,
    load_profiles,
    parse_mode,
    save_user_profiles,
)


class TestParseMode:
    def test_full_form(self):
        assert parse_mode("3200x1200@60") == (3200, 1200, 60)

    def test_unicode_multiply_and_spaces(self):
        assert parse_mode(" 2560 × 720 @ 60 ") == (2560, 720, 60)

    def test_fps_defaults_to_30(self):
        assert parse_mode("1280x480") == (1280, 480, 30)

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            parse_mode("fast please")

    def test_roundtrip_with_format(self):
        mode = (1600, 600, 120)
        assert parse_mode(format_mode(mode)) == mode


class TestPersistence:
    def test_load_without_file_returns_builtins(self, tmp_path):
        profiles = load_profiles(tmp_path / "profiles.json")
        assert [p.name for p in profiles] == [p.name for p in BUILTIN_PROFILES]

    def test_save_load_roundtrip(self, tmp_path):
        path = tmp_path / "profiles.json"
        custom = CameraProfile(
            name="TestCam", modes=((1280, 480, 30),), baseline_mm=42.0, hfov_deg=70.0, notes="n"
        )
        save_user_profiles([*BUILTIN_PROFILES, custom], path)
        loaded = load_profiles(path)
        found = find_profile(loaded, "TestCam")
        assert found is not None
        assert found.baseline_mm == 42.0
        assert found.modes == ((1280, 480, 30),)
        assert not found.builtin

    def test_builtins_not_written_to_disk(self, tmp_path):
        path = tmp_path / "profiles.json"
        save_user_profiles(list(BUILTIN_PROFILES), path)
        assert path.read_text(encoding="utf-8").strip() == "[]"

    def test_corrupt_file_falls_back_to_builtins(self, tmp_path):
        path = tmp_path / "profiles.json"
        path.write_text("{not json", encoding="utf-8")
        assert len(load_profiles(path)) == len(BUILTIN_PROFILES)


class TestBuiltins:
    def test_elp_profile_matches_spec(self):
        elp = BUILTIN_PROFILES[0]
        assert elp.baseline_mm == 60.85
        assert (3200, 1200, 60) in elp.modes
        assert elp.builtin
