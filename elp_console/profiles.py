"""Camera profiles: per-model spec (SBS modes, baseline) with JSON persistence.

A profile describes one stereo camera model — its side-by-side output modes and
the mechanical design values the calibration compares against. Built-in
profiles ship with the app; user profiles live in ``.runtime/profiles.json``
and can be added/edited/deleted freely."""

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import PROFILES_PATH


@dataclass(frozen=True)
class CameraProfile:
    name: str
    modes: tuple[tuple[int, int, int], ...]  # SBS composite (width, height, fps)
    baseline_mm: float = 0.0  # 0 = unknown / not specified
    hfov_deg: float = 0.0
    notes: str = ""
    builtin: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "modes": [list(m) for m in self.modes],
            "baseline_mm": self.baseline_mm,
            "hfov_deg": self.hfov_deg,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CameraProfile":
        return cls(
            name=str(data["name"]),
            modes=tuple(tuple(int(v) for v in m) for m in data["modes"]),
            baseline_mm=float(data.get("baseline_mm", 0.0)),
            hfov_deg=float(data.get("hfov_deg", 0.0)),
            notes=str(data.get("notes", "")),
        )


# 벤더 공식 스펙 — docs/hardware/SPEC_CAMERA.md (whatsthere) 확정값 기준.
BUILTIN_PROFILES = (
    CameraProfile(
        name="ELP-3DGS1200P01 (OG02B10)",
        modes=((3200, 1200, 60), (2560, 720, 60), (1600, 600, 120), (1280, 480, 120), (640, 240, 120)),
        baseline_mm=60.85,
        hfov_deg=86.0,
        notes="OmniVision OG02B10 ×2 global shutter, H100 lens (EFL 2.8mm), USB2.0 MJPEG",
        builtin=True,
    ),
    CameraProfile(
        name="ELP SBS Template (manual)",
        modes=((2560, 960, 60), (2560, 720, 60), (1280, 480, 30), (640, 240, 30)),
        notes="For other ELP SBS models (960P/720P, V83/H110/H120/L180 lens variants) — duplicate and edit with the real spec",
        builtin=True,
    ),
)


def parse_mode(text: str) -> tuple[int, int, int]:
    """Parse "3200x1200@60" (also accepts × and spaces). Raises ValueError."""
    cleaned = text.strip().lower().replace("×", "x").replace(" ", "")
    if not cleaned:
        raise ValueError("empty line")
    size, _, fps = cleaned.partition("@")
    width, _, height = size.partition("x")
    if not (width.isdigit() and height.isdigit()):
        raise ValueError(f"Bad resolution format: {text!r} (e.g. 3200x1200@60)")
    fps_value = int(fps) if fps.isdigit() else 30
    return int(width), int(height), fps_value


def format_mode(mode: tuple[int, int, int]) -> str:
    return f"{mode[0]}x{mode[1]}@{mode[2]}"


def load_profiles(path: Path = PROFILES_PATH) -> list[CameraProfile]:
    """Built-ins first, then user profiles; a corrupt file falls back to built-ins."""
    profiles = list(BUILTIN_PROFILES)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles.extend(CameraProfile.from_dict(entry) for entry in data)
        except (ValueError, KeyError, TypeError):
            pass
    return profiles


def save_user_profiles(profiles: list[CameraProfile], path: Path = PROFILES_PATH) -> None:
    """Persist non-builtin profiles only — built-ins always come from code."""
    user = [p.to_dict() for p in profiles if not p.builtin]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(user, ensure_ascii=False, indent=2), encoding="utf-8")


def find_profile(profiles: list[CameraProfile], name: str) -> CameraProfile | None:
    return next((p for p in profiles if p.name == name), None)
