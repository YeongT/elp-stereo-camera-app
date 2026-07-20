"""Depth preview math: SGBM disparity, colorize, Q reprojection."""

import numpy as np

from elp_console.stereo_depth import (
    SgbmParams,
    auto_num_disparities,
    auto_tune,
    colorize_disparity,
    compute_disparity,
    disparity_coverage,
    disparity_quality,
    disparity_stability,
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


def test_auto_num_disparities_covers_min_distance():
    # f=800px, B=60mm, Zmin=300mm -> d = 800*60/300 = 160px
    assert auto_num_disparities(800.0, 60.0, 300.0) == 160
    # compute pair downscaled by 0.5 -> disparity halves -> 80
    assert auto_num_disparities(800.0, 60.0, 300.0, scale=0.5) == 80
    # very near object exceeds the cap -> clamped
    assert auto_num_disparities(800.0, 60.0, 50.0, cap=256) == 256
    # always a positive multiple of 16
    n = auto_num_disparities(858.0, 60.85, 700.0)
    assert n % 16 == 0 and n >= 16


def test_auto_num_disparities_guards_bad_input():
    assert auto_num_disparities(800.0, 60.0, 0.0) == 16
    assert auto_num_disparities(0.0, 60.0, 300.0) == 16
    assert auto_num_disparities(800.0, 0.0, 300.0) == 16


def test_disparity_coverage_fraction():
    disp = np.full((10, 10), 5.0, np.float32)
    disp[:5] = -1.0  # half invalid
    assert abs(disparity_coverage(disp) - 0.5) < 1e-9


def test_quality_penalizes_locally_unstable_matches():
    stable = np.full((40, 60), 12.0, np.float32)
    unstable = stable.copy()
    rng = np.random.RandomState(3)
    unstable[:] = rng.uniform(1, 48, unstable.shape).astype(np.float32)

    assert disparity_stability(stable) > 0.99
    assert disparity_quality(stable) > disparity_quality(unstable)


def test_auto_tune_picks_dense_valid_params():
    shift = 12
    left = _textured(320, 240, seed=1)
    right = np.zeros_like(left)
    right[:, :-shift] = left[:, shift:]

    base = SgbmParams(num_disparities=48)
    best, score = auto_tune(left, right, base)

    assert isinstance(best, SgbmParams)
    assert 0.0 <= score <= 1.0
    assert best.num_disparities == 48  # geometry-derived knob left untouched
    assert score > 0.3  # a good match yields substantial coverage
