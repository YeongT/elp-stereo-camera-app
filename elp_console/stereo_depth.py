"""Depth preview math: SGBM disparity on a rectified pair, colorize, reproject.

Pure functions only — the depth sub-tab owns threading and display. Disparity
is float32 pixels (SGBM raw / 16); invalid pixels are <= 0."""

from dataclasses import dataclass

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
