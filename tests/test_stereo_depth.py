"""Depth preview math: SGBM disparity, colorize, Q reprojection."""

import numpy as np

from elp_console.stereo_depth import (
    SgbmParams,
    colorize_disparity,
    compute_disparity,
    reproject_point,
)


def _textured(width: int, height: int, seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    base = rng.randint(0, 255, (height, width), dtype=np.uint8)
    import cv2

    return cv2.GaussianBlur(base, (0, 0), 1.2)


def test_compute_disparity_recovers_known_shift():
    shift = 16
    left = _textured(480, 360)
    right = np.zeros_like(left)
    right[:, :-shift] = left[:, shift:]  # x_left = x_right + shift

    disp = compute_disparity(left, right, SgbmParams(num_disparities=64, block_size=7))

    center = disp[100:260, 120:360]
    valid = center[center > 0]
    assert valid.size > center.size * 0.5
    assert abs(float(np.median(valid)) - shift) < 2.0


def test_colorize_disparity_marks_invalid_black():
    disp = np.full((40, 60), 20.0, np.float32)
    disp[:10] = -1.0  # SGBM invalid marker
    color = colorize_disparity(disp, num_disparities=64)
    assert color.shape == (40, 60, 3)
    assert color.dtype == np.uint8
    assert (color[:10] == 0).all()
    assert color[20:].any()


def test_reproject_point_matches_pinhole_depth():
    f, cx, cy, baseline = 800.0, 320.0, 240.0, 60.0
    q = np.float64(
        [
            [1, 0, 0, -cx],
            [0, 1, 0, -cy],
            [0, 0, 0, f],
            [0, 0, 1.0 / baseline, 0],
        ]
    )
    x, y, z = reproject_point(320.0, 240.0, 16.0, q)
    assert abs(z - f * baseline / 16.0) < 1e-6
    assert abs(x) < 1e-6 and abs(y) < 1e-6


def test_reproject_point_rejects_invalid_disparity():
    q = np.eye(4)
    assert reproject_point(0.0, 0.0, 0.0, q) is None
    assert reproject_point(0.0, 0.0, -3.0, q) is None
