"""Stereo calibration: chessboard detection, stereo calibrate, rectification.

Object points are in millimeters, so the recovered translation T is metric and
``baseline_mm`` can be compared directly against the mechanical design value
(ELP-3DGS1200P01: 60.85 mm). The saved ``.npz``/``.json`` pair carries the full
K/D/R/T/R1/R2/P1/P2/Q set that a downstream depth pipeline needs.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .frames import split_sbs

MIN_PAIRS = 5
RECOMMENDED_PAIRS = 12
LATEST_NAME = "latest.npz"

_ARRAY_FIELDS = ("K1", "D1", "K2", "D2", "R", "T", "R1", "R2", "P1", "P2", "Q")


@dataclass(frozen=True)
class BoardSpec:
    """Chessboard described by INNER corner counts and square edge length."""

    cols: int = 9
    rows: int = 6
    square_mm: float = 25.0

    def object_points(self) -> np.ndarray:
        pts = np.zeros((self.rows * self.cols, 3), np.float32)
        pts[:, :2] = np.mgrid[0 : self.cols, 0 : self.rows].T.reshape(-1, 2)
        return pts * self.square_mm


@dataclass(frozen=True)
class StereoCalibration:
    image_size: tuple[int, int]  # per-eye (width, height)
    K1: np.ndarray
    D1: np.ndarray
    K2: np.ndarray
    D2: np.ndarray
    R: np.ndarray
    T: np.ndarray
    R1: np.ndarray
    R2: np.ndarray
    P1: np.ndarray
    P2: np.ndarray
    Q: np.ndarray
    rms_left: float
    rms_right: float
    rms_stereo: float
    board: BoardSpec
    created: str

    @property
    def baseline_mm(self) -> float:
        return float(np.linalg.norm(self.T))

    def save(self, directory) -> Path:
        """Write timestamped npz + human-readable json, refresh ``latest.npz``."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        arrays = {name: getattr(self, name) for name in _ARRAY_FIELDS}
        meta = {
            "image_size": list(self.image_size),
            "rms_left": self.rms_left,
            "rms_right": self.rms_right,
            "rms_stereo": self.rms_stereo,
            "baseline_mm": self.baseline_mm,
            "board": {"cols": self.board.cols, "rows": self.board.rows, "square_mm": self.board.square_mm},
            "created": self.created,
        }
        path = directory / f"stereo_{stamp}.npz"
        np.savez(path, meta=json.dumps(meta), **arrays)
        np.savez(directory / LATEST_NAME, meta=json.dumps(meta), **arrays)
        json_payload = {**meta, **{name: arrays[name].tolist() for name in _ARRAY_FIELDS}}
        (directory / f"stereo_{stamp}.json").write_text(
            json.dumps(json_payload, indent=2), encoding="utf-8"
        )
        return path

    @classmethod
    def _from_npz(cls, path: Path) -> "StereoCalibration":
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data["meta"]))
        board = meta["board"]
        return cls(
            image_size=tuple(meta["image_size"]),
            **{name: data[name] for name in _ARRAY_FIELDS},
            rms_left=meta["rms_left"],
            rms_right=meta["rms_right"],
            rms_stereo=meta["rms_stereo"],
            board=BoardSpec(board["cols"], board["rows"], board["square_mm"]),
            created=meta["created"],
        )


def load_latest(directory) -> StereoCalibration | None:
    path = Path(directory) / LATEST_NAME
    if not path.is_file():
        return None
    try:
        return StereoCalibration._from_npz(path)  # noqa: SLF001 — own factory
    except Exception:  # noqa: BLE001 — stale/corrupt file must not block startup
        return None


# ── 검출 ─────────────────────────────────────────────────────


def find_corners(image, board: BoardSpec) -> np.ndarray | None:
    """Detect inner chessboard corners; returns (N, 2) float32 or None."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    ok, corners = cv2.findChessboardCornersSB(
        gray, (board.cols, board.rows), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
    )
    if not ok or corners is None:
        return None
    return corners.reshape(-1, 2).astype(np.float32)


def detect_pair(frame, board: BoardSpec):
    """Detect the board in BOTH eyes of an SBS frame; None unless both found."""
    left, right = split_sbs(frame)
    left_corners = find_corners(left, board)
    if left_corners is None:
        return None
    right_corners = find_corners(right, board)
    if right_corners is None:
        return None
    return left_corners, right_corners


def draw_pair_overlay(frame, board: BoardSpec, pair) -> np.ndarray:
    """Return a copy of the SBS frame with detected corners drawn on both eyes."""
    out = frame.copy()
    left, right = split_sbs(out)
    pattern = (board.cols, board.rows)
    cv2.drawChessboardCorners(left, pattern, pair[0].reshape(-1, 1, 2), True)
    cv2.drawChessboardCorners(right, pattern, pair[1].reshape(-1, 1, 2), True)
    return out


# ── 캘리브레이션 ─────────────────────────────────────────────


def calibrate_stereo(board: BoardSpec, image_size, pairs) -> StereoCalibration:
    """Full stereo calibration from detected corner pairs.

    Intrinsics are solved per eye first, then stereoCalibrate runs with
    CALIB_FIX_INTRINSIC to recover R/T only — the standard split that keeps the
    extrinsic solve well-conditioned."""
    if len(pairs) < MIN_PAIRS:
        raise ValueError(f"최소 {MIN_PAIRS}쌍 필요 (현재 {len(pairs)}쌍)")

    image_size = (int(image_size[0]), int(image_size[1]))
    obj = [board.object_points()] * len(pairs)
    left_pts = [p[0].reshape(-1, 1, 2) for p in pairs]
    right_pts = [p[1].reshape(-1, 1, 2) for p in pairs]

    rms_left, K1, D1, _, _ = cv2.calibrateCamera(obj, left_pts, image_size, None, None)
    rms_right, K2, D2, _, _ = cv2.calibrateCamera(obj, right_pts, image_size, None, None)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)
    rms_stereo, K1, D1, K2, D2, R, T, _, _ = cv2.stereoCalibrate(
        obj,
        left_pts,
        right_pts,
        K1,
        D1,
        K2,
        D2,
        image_size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=criteria,
    )

    R1, R2, P1, P2, Q, _, _ = cv2.stereoRectify(K1, D1, K2, D2, image_size, R, T, alpha=0)

    return StereoCalibration(
        image_size=image_size,
        K1=K1,
        D1=D1,
        K2=K2,
        D2=D2,
        R=R,
        T=T,
        R1=R1,
        R2=R2,
        P1=P1,
        P2=P2,
        Q=Q,
        rms_left=float(rms_left),
        rms_right=float(rms_right),
        rms_stereo=float(rms_stereo),
        board=board,
        created=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


# ── 렉티피케이션 ─────────────────────────────────────────────


def rectify_maps(calib: StereoCalibration):
    """(map1x, map1y, map2x, map2y) remap tables for cv2.remap per eye."""
    size = calib.image_size
    m1x, m1y = cv2.initUndistortRectifyMap(calib.K1, calib.D1, calib.R1, calib.P1, size, cv2.CV_16SC2)
    m2x, m2y = cv2.initUndistortRectifyMap(calib.K2, calib.D2, calib.R2, calib.P2, size, cv2.CV_16SC2)
    return m1x, m1y, m2x, m2y


def rectify_sbs(frame, maps):
    """Rectify both eyes of an SBS frame; output keeps the SBS layout."""
    left, right = split_sbs(frame)
    left = cv2.remap(left, maps[0], maps[1], cv2.INTER_LINEAR)
    right = cv2.remap(right, maps[2], maps[3], cv2.INTER_LINEAR)
    return cv2.hconcat([left, right])


# ── 테스트/미리보기용 렌더 ───────────────────────────────────


def render_board(board: BoardSpec, square_px: int = 60, margin: int = 80) -> np.ndarray:
    """Render a synthetic chessboard image (grayscale) for tests and previews."""
    squares = (np.indices((board.rows + 1, board.cols + 1)).sum(axis=0) % 2) * 255
    image = np.kron(squares, np.ones((square_px, square_px))).astype(np.uint8)
    return cv2.copyMakeBorder(
        image, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=255
    )
