"""Depth preview math: SGBM disparity on a rectified pair, colorize, reproject.

Pure functions only — the depth sub-tab owns threading and display. Disparity
is float32 pixels (SGBM raw / 16); invalid pixels are <= 0."""

import math
from dataclasses import dataclass, replace

import cv2
import numpy as np

COLORMAPS = [
    ("TURBO", cv2.COLORMAP_TURBO),
    ("JET", cv2.COLORMAP_JET),
    ("VIRIDIS", cv2.COLORMAP_VIRIDIS),
    ("MAGMA", cv2.COLORMAP_MAGMA),
    ("BONE", cv2.COLORMAP_BONE),
]


@dataclass(frozen=True)
class SgbmParams:
    num_disparities: int = 96  # multiple of 16
    block_size: int = 7  # odd, >= 3
    uniqueness: int = 10
    speckle_window: int = 100
    speckle_range: int = 2


@dataclass(frozen=True)
class DepthProfile:
    """A named, analysis-oriented set of depth-preview controls.

    ``num_disparities`` deliberately does not live here: it is derived from
    the active calibration geometry and the selected near-distance limit.
    """

    name: str
    description: str
    compute_width: int
    min_distance_mm: int
    block_size: int
    uniqueness: int
    speckle_window: int
    colormap: int


DEPTH_PROFILES = (
    DepthProfile(
        "Inspect",
        "Reliable general inspection — favors stable matches over dense fill",
        800,
        450,
        9,
        15,
        150,
        cv2.COLORMAP_VIRIDIS,
    ),
    DepthProfile(
        "Near detail",
        "Closer subjects and fine edges — higher resolution, smaller matching block",
        800,
        250,
        7,
        12,
        100,
        cv2.COLORMAP_TURBO,
    ),
    DepthProfile(
        "Smooth surfaces",
        "Broad, low-texture surfaces — stronger rejection and smoothing",
        640,
        500,
        11,
        18,
        180,
        cv2.COLORMAP_MAGMA,
    ),
    DepthProfile(
        "Fast",
        "Responsive framing check — lower compute cost, not for measurement",
        480,
        500,
        7,
        10,
        100,
        cv2.COLORMAP_TURBO,
    ),
)


def build_sgbm(params: SgbmParams) -> cv2.StereoSGBM:
    block = max(3, params.block_size | 1)
    num = max(16, (params.num_disparities // 16) * 16)
    return cv2.StereoSGBM.create(
        minDisparity=0,
        numDisparities=num,
        blockSize=block,
        P1=8 * block * block,
        P2=32 * block * block,
        disp12MaxDiff=1,
        uniquenessRatio=params.uniqueness,
        speckleWindowSize=params.speckle_window,
        speckleRange=params.speckle_range,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )


def compute_disparity(left_gray: np.ndarray, right_gray: np.ndarray, params: SgbmParams) -> np.ndarray:
    """Disparity in float32 pixels; invalid pixels <= 0."""
    raw = build_sgbm(params).compute(left_gray, right_gray)
    return raw.astype(np.float32) / 16.0


def colorize_disparity(
    disp: np.ndarray, num_disparities: int, colormap: int = cv2.COLORMAP_TURBO
) -> np.ndarray:
    """Map disparity to a colormap image; invalid (<= 0) pixels become black."""
    scaled = np.clip(disp / float(max(1, num_disparities)) * 255.0, 0, 255).astype(np.uint8)
    color = cv2.applyColorMap(scaled, colormap)
    color[disp <= 0] = 0
    return color


# ── 자동 파라미터 ────────────────────────────────────────────

# numDisparities는 기하학으로 정답이 정해진다: 초점거리·baseline·최소거리로 산출.
# 나머지(block/uniqueness/speckle)는 장면 의존이라 정답이 없어 그리드 서치로 탐색.

DEFAULT_BLOCK_SIZES = (5, 7, 9, 11)
DEFAULT_UNIQUENESS = (5, 10, 15)
DEFAULT_SPECKLE = (50, 100, 150)


def auto_num_disparities(
    focal_px: float, baseline_mm: float, min_distance_mm: float, scale: float = 1.0, cap: int = 256
) -> int:
    """numDisparities (multiple of 16) needed to see objects as near as ``min_distance_mm``.

    Depth model ``Z = focal_px * baseline / disparity`` inverts to the largest
    disparity ``d = focal_px * baseline / Z_min`` at full resolution. ``scale`` is
    the downscale factor of the pair SGBM actually runs on (< 1 shrinks the
    disparity). Clamped to ``[16, cap]`` and rounded up to a multiple of 16."""
    if min_distance_mm <= 0 or focal_px <= 0 or baseline_mm <= 0:
        return 16
    disparity_full = focal_px * baseline_mm / min_distance_mm
    disparity = disparity_full * scale
    num = int(math.ceil(disparity / 16.0)) * 16
    return int(max(16, min(cap, num)))


def disparity_coverage(disp: np.ndarray) -> float:
    """Fraction of pixels holding a valid disparity (SGBM's disp12MaxDiff has
    already rejected left-right-inconsistent matches, so this is confident
    coverage, not raw fill)."""
    return float(np.count_nonzero(disp > 0)) / float(disp.size)


def disparity_stability(disp: np.ndarray, tolerance_px: float = 1.5) -> float:
    """Return how locally coherent the valid disparity pixels are.

    Coverage alone rewards a matcher that fills the image with unstable false
    matches.  This deliberately conservative score compares each valid pixel
    with its 5×5 median neighbourhood, while preserving invalid pixels as
    invalid rather than letting a median filter fill holes.
    """
    valid = disp > 0
    valid_count = int(np.count_nonzero(valid))
    if valid_count == 0:
        return 0.0
    median = cv2.medianBlur(np.where(valid, disp, 0).astype(np.float32), 5)
    stable = valid & (np.abs(disp - median) <= tolerance_px)
    return float(np.count_nonzero(stable)) / float(valid_count)


def disparity_quality(disp: np.ndarray) -> float:
    """Score useful depth, weighting local consistency above raw coverage."""
    coverage = disparity_coverage(disp)
    stability = disparity_stability(disp)
    return coverage * (0.35 + 0.65 * stability)


def auto_tune(
    left_gray: np.ndarray,
    right_gray: np.ndarray,
    base_params: "SgbmParams",
    block_sizes=DEFAULT_BLOCK_SIZES,
    uniqueness_values=DEFAULT_UNIQUENESS,
    speckle_values=DEFAULT_SPECKLE,
) -> tuple["SgbmParams", float]:
    """Grid-search block/uniqueness/speckle on one rectified pair; keep the combo
    with the most left-right-consistent valid pixels.

    ``numDisparities`` and the compute scale are geometry-derived and left
    untouched. Returns ``(best_params, best_score)`` where score is coverage in
    ``[0, 1]``."""
    best_params, best_score = base_params, -1.0
    for block in block_sizes:
        for uniqueness in uniqueness_values:
            for speckle in speckle_values:
                params = replace(
                    base_params, block_size=block, uniqueness=uniqueness, speckle_window=speckle
                )
                score = disparity_quality(compute_disparity(left_gray, right_gray, params))
                if score > best_score:
                    best_params, best_score = params, score
    return best_params, best_score


def reproject_point(x: float, y: float, disparity: float, q: np.ndarray):
    """(X, Y, Z) in calibration units (mm) for one pixel, or None if invalid.

    Coordinates and disparity must be in the calibration's full-eye resolution;
    callers computing on a downscaled pair must divide x/y/disparity by the
    scale first."""
    if disparity <= 0:
        return None
    vec = np.asarray(q, dtype=np.float64) @ np.array([x, y, disparity, 1.0])
    if abs(vec[3]) < 1e-12:
        return None
    return tuple(float(v) for v in (vec[:3] / vec[3]))
