"""Capture worker.

Device constraints (ELP OG02B10, "3D USB Camera"):
- MJPEG frames can arrive truncated on a marginal USB link. OpenCV silently
  decodes those into gray/green-filled frames; the FFmpeg(PyAV) path validates
  each packet and drops corrupt frames instead, so it is tried first.
- OpenCV DSHOW must set size BEFORE fourcc or the camera falls back to YUY2.
"""

import os
import time
from pathlib import Path

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2
from PySide6.QtCore import QThread, Signal

from .calibration import rectify_sbs
from .frames import (
    apply_stereo_transform,
    compose_view,
    exposure_overlay,
    split_sbs,
)
from .paths import CAPTURES_DIR
from .recorder import RecordingSession

DISPLAY_MAX_WIDTH = 1560
EMIT_INTERVAL = 1.0 / 30.0
PREVIEW_TAP_INTERVAL = 1.0 / 10.0


class CaptureWorker(QThread):
    opened = Signal(dict)
    frame_ready = Signal(object, dict)
    frame_captured = Signal(object)  # full-res frame on request_frame()
    preview_frame = Signal(object)  # throttled full-res raw frame while tap is on
    failed = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        device_name: str,
        index: int,
        width: int,
        height: int,
        fps: int,
        backend_mode: str,
        opencv_indices: tuple[int, ...] = (),
        parent=None,
    ):
        super().__init__(parent)
        self._device_name = device_name
        self._index = index
        self._width = width
        self._height = height
        self._fps = fps
        self._backend_mode = backend_mode
        # OpenCV's numeric device order can differ from DirectShow/PyAV's
        # device-name order. Keep every UI-visible index as a fallback
        # candidate, with the selected item tried first.
        self._opencv_indices = tuple(dict.fromkeys((index, *opencv_indices)))
        self._stop_requested = False
        self._snapshot_dir: str | None = None
        self._swap_lr = False
        self._rotation = 0
        self._record_dir: str | None = None  # GUI-thread request flag
        self._record_split = False
        self._session: RecordingSession | None = None  # worker-thread owned
        self._view_mode = "sbs"
        self._exposure_check = False
        self._frame_requested = False
        self._rectify_maps = None  # (m1x, m1y, m2x, m2y) or None
        self._rectify_warned = False
        self._preview_tap = False
        self._preview_last = 0.0

    def stop(self) -> None:
        self._stop_requested = True

    def request_snapshot(self, dir_path: str) -> None:
        self._snapshot_dir = dir_path

    def set_transform(self, swap_lr: bool, rotation: int) -> None:
        """Live view transform; safe to call from the GUI thread (atomic writes)."""
        self._swap_lr = swap_lr
        self._rotation = rotation % 360

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = mode

    def set_exposure_check(self, enabled: bool) -> None:
        self._exposure_check = enabled

    def request_frame(self) -> None:
        """Ask for one full-res frame via frame_captured (pre-rectification)."""
        self._frame_requested = True

    def set_preview_tap(self, enabled: bool) -> None:
        """Continuous throttled raw-frame feed for the calibration sub-tabs."""
        self._preview_tap = enabled

    def set_rectification(self, maps) -> None:
        """Enable/disable live rectification; maps from calibration.rectify_maps."""
        self._rectify_maps = maps
        self._rectify_warned = False

    def start_recording(self, dir_path: str, split: bool) -> None:
        self._record_dir = dir_path
        self._record_split = split

    def stop_recording(self) -> None:
        self._record_dir = None

    # ── 공통 ─────────────────────────────────────────────────

    def _process(self, frame):
        """Transform → calibration capture → rectify → snapshot/record.

        The calibration frame is emitted BEFORE rectification: calibration must
        see the raw (distorted) image, while snapshots/recordings get the
        corrected one."""
        frame = apply_stereo_transform(frame, self._swap_lr, self._rotation)
        if self._frame_requested:
            self._frame_requested = False
            self.frame_captured.emit(frame.copy())
        if self._preview_tap:
            now = time.monotonic()
            if now - self._preview_last >= PREVIEW_TAP_INTERVAL:
                self._preview_last = now
                self.preview_frame.emit(frame.copy())
        frame = self._apply_rectify(frame)
        if self._snapshot_dir is not None:
            self._save_snapshot(frame)
        self._handle_recording(frame)
        return frame

    def _apply_rectify(self, frame):
        maps = self._rectify_maps
        if maps is None:
            return frame
        height, width = maps[0].shape[:2]
        if frame.shape[0] != height or frame.shape[1] != 2 * width:
            if not self._rectify_warned:
                self._rectify_warned = True
                self.log.emit(
                    f"[ERROR] Rectification skipped — calibration resolution (per eye {width}×{height}) "
                    f"differs from current stream ({frame.shape[1]}×{frame.shape[0]})."
                )
            return frame
        return rectify_sbs(frame, maps)

    def _handle_recording(self, frame) -> None:
        if self._record_dir is None:
            self._close_recorder()
            return
        try:
            stale = (
                self._session is None
                or self._session.directory != Path(self._record_dir)
                or self._session.split != self._record_split
            )
            if stale:
                self._close_recorder()
                self._session = RecordingSession(self._record_dir, self._fps, self._record_split)
            for path in self._session.write(frame):
                self.log.emit(f"Recording started: {path.name}")
        except Exception as exc:  # noqa: BLE001 — disk full, codec missing, etc.
            self._record_dir = None
            self._session = None
            self.log.emit(f"[ERROR] Recording failed: {exc}")

    def _close_recorder(self) -> None:
        if self._session is not None:
            paths = self._session.close()
            self._session = None
            if paths:
                self.log.emit("Recording saved: " + ", ".join(p.name for p in paths))

    def _save_snapshot(self, frame) -> None:
        directory = Path(self._snapshot_dir or CAPTURES_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        left, right = split_sbs(frame)
        left_path = directory / f"{stamp}_left.png"
        right_path = directory / f"{stamp}_right.png"
        cv2.imwrite(str(left_path), left)
        cv2.imwrite(str(right_path), right)
        self.log.emit(f"Snapshot saved: {left_path.name}, {right_path.name}")
        self._snapshot_dir = None

    def _emit_frame(self, frame, fps_ema: float, fourcc: str, drop_rate) -> None:
        """Compose the display image per view mode, downscale, add stats, emit."""
        display = compose_view(frame, self._view_mode)
        if display.shape[1] > DISPLAY_MAX_WIDTH:
            scale = DISPLAY_MAX_WIDTH / display.shape[1]
            display = cv2.resize(display, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        stats = {
            "fps": fps_ema,
            "mean": float(display.mean()),
            "width": frame.shape[1],
            "height": frame.shape[0],
            "fourcc": fourcc,
            "drop_rate": drop_rate,
            "view_mode": self._view_mode,
            "hist": None,
            "clip": None,
        }
        if self._exposure_check:
            display, hist, clip_low, clip_high = exposure_overlay(display)
            stats["hist"] = hist
            stats["clip"] = (clip_low, clip_high)
        self.frame_ready.emit(display, stats)

    # ── 진입점 ───────────────────────────────────────────────

    def run(self) -> None:
        # Lazy import: the capture modules import EMIT_INTERVAL from this
        # module at their top, so importing them here avoids a cycle.
        from .capture_ffmpeg import run_ffmpeg
        from .capture_opencv import run_opencv

        try:
            if self._backend_mode in ("Auto", "FFmpeg"):
                ran = run_ffmpeg(self)
                if ran or self._backend_mode == "FFmpeg":
                    return
            run_opencv(self)
        finally:
            self._close_recorder()
