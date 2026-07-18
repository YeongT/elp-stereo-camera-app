"""Calibration math tests with synthetic geometry.

Ground truth mirrors the ELP-3DGS1200P01 spec: per-eye 1600x1200,
f ≈ 858 px, baseline 60.85 mm. Image points are produced by projecting a
virtual chessboard through two ideal cameras, so the calibrator must recover
the exact baseline and focal length.
"""

import cv2
import numpy as np
import pytest

from elp_console.calibration import (
    BoardSpec,
    StereoCalibration,
    calibrate_stereo,
    detect_pair,
    find_corners,
    load_latest,
    rectify_maps,
    rectify_sbs,
    render_board,
)

IMAGE_SIZE = (1600, 1200)
F_TRUE = 858.0
BASELINE_MM = 60.85
K_TRUE = np.array([[F_TRUE, 0, 800.0], [0, F_TRUE, 600.0], [0, 0, 1.0]])
T_LR = np.array([-BASELINE_MM, 0.0, 0.0])

BOARD = BoardSpec(cols=9, rows=6, square_mm=25.0)

# (rx, ry, rz, tx, ty, tz) — board pose in the left camera frame, mm/rad.
POSES = [
    (0.0, 0.0, 0.0, -100.0, -60.0, 500.0),
    (0.2, 0.0, 0.0, -100.0, -80.0, 550.0),
    (-0.2, 0.0, 0.0, -100.0, -40.0, 520.0),
    (0.0, 0.25, 0.0, -140.0, -60.0, 560.0),
    (0.0, -0.25, 0.0, -60.0, -60.0, 540.0),
    (0.15, 0.15, 0.1, -120.0, -70.0, 600.0),
    (-0.15, 0.2, -0.1, -80.0, -50.0, 480.0),
    (0.25, -0.15, 0.05, -110.0, -90.0, 650.0),
    (-0.1, -0.2, 0.15, -90.0, -30.0, 470.0),
    (0.1, 0.1, -0.15, -130.0, -60.0, 700.0),
    (0.0, 0.0, 0.3, -100.0, -55.0, 520.0),
    (-0.25, 0.1, 0.0, -95.0, -85.0, 580.0),
]


def _project_pairs():
    obj = BOARD.object_points()
    pairs = []
    for rx, ry, rz, tx, ty, tz in POSES:
        rvec = np.array([rx, ry, rz])
        tvec = np.array([tx, ty, tz])
        left, _ = cv2.projectPoints(obj, rvec, tvec, K_TRUE, None)
        # Right camera sits +baseline along x: X_r = X_l + T_LR.
        right, _ = cv2.projectPoints(obj, rvec, tvec + T_LR, K_TRUE, None)
        pairs.append((left.reshape(-1, 2).astype(np.float32), right.reshape(-1, 2).astype(np.float32)))
    return pairs


@pytest.fixture(scope="module")
def calib():
    return calibrate_stereo(BOARD, IMAGE_SIZE, _project_pairs())


class TestCalibrateStereo:
    def test_recovers_baseline(self, calib):
        assert calib.baseline_mm == pytest.approx(BASELINE_MM, abs=0.05)

    def test_recovers_focal_length(self, calib):
        assert calib.K1[0, 0] == pytest.approx(F_TRUE, abs=2.0)
        assert calib.K2[0, 0] == pytest.approx(F_TRUE, abs=2.0)

    def test_rms_small_on_perfect_points(self, calib):
        assert calib.rms_stereo < 0.1

    def test_q_matrix_present(self, calib):
        assert calib.Q.shape == (4, 4)

    def test_save_load_roundtrip(self, calib, tmp_path):
        calib.save(tmp_path)
        loaded = load_latest(tmp_path)
        assert loaded is not None
        assert loaded.baseline_mm == pytest.approx(calib.baseline_mm, abs=1e-6)
        np.testing.assert_allclose(loaded.K1, calib.K1)
        np.testing.assert_allclose(loaded.Q, calib.Q)
        assert loaded.image_size == calib.image_size
        # Human-readable export exists alongside.
        assert list(tmp_path.glob("stereo_*.json"))

    def test_load_latest_missing(self, tmp_path):
        assert load_latest(tmp_path / "nope") is None

    def test_rectify_maps_and_sbs(self, calib):
        maps = rectify_maps(calib)
        frame = np.random.default_rng(0).integers(0, 255, (1200, 3200, 3), np.uint8)
        out = rectify_sbs(frame, maps)
        assert out.shape == frame.shape
        assert out.dtype == np.uint8


class TestDetection:
    def test_find_corners_on_rendered_board(self):
        image = render_board(BOARD, square_px=40, margin=60)
        corners = find_corners(image, BOARD)
        assert corners is not None
        assert corners.shape[0] == BOARD.cols * BOARD.rows

    def test_find_corners_rejects_blank(self):
        blank = np.full((480, 640), 128, np.uint8)
        assert find_corners(blank, BOARD) is None

    def test_detect_pair_on_sbs(self):
        board = render_board(BOARD, square_px=40, margin=60)
        eye = cv2.resize(board, (640, 480), interpolation=cv2.INTER_AREA)
        eye = cv2.cvtColor(eye, cv2.COLOR_GRAY2BGR)
        frame = cv2.hconcat([eye, eye])
        result = detect_pair(frame, BOARD)
        assert result is not None
        left, right = result
        assert left.shape[0] == right.shape[0] == BOARD.cols * BOARD.rows

    def test_detect_pair_fails_when_one_eye_missing(self):
        board = render_board(BOARD, square_px=40, margin=60)
        eye = cv2.cvtColor(cv2.resize(board, (640, 480)), cv2.COLOR_GRAY2BGR)
        blank = np.full_like(eye, 128)
        assert detect_pair(cv2.hconcat([eye, blank]), BOARD) is None


class TestBoardSpec:
    def test_object_points_layout(self):
        pts = BOARD.object_points()
        assert pts.shape == (54, 3)
        assert pts[0].tolist() == [0.0, 0.0, 0.0]
        assert pts[1][0] == pytest.approx(25.0)  # next corner one square along x
        assert (pts[:, 2] == 0).all()


class TestStereoCalibrationType:
    def test_baseline_property(self):
        calib = StereoCalibration.__new__(StereoCalibration)
        object.__setattr__(calib, "T", np.array([[-60.85], [0.0], [0.0]]))
        assert calib.baseline_mm == pytest.approx(60.85)
