"""정렬 검증 sub-tab: live rectified preview against the raw stream.

Consumes the worker's throttled preview tap (raw, pre-rectification frames)
and applies the loaded calibration itself, so the comparison works regardless
of the live tab's 정렬 보정 toggle."""

import cv2
import numpy as np
from PySide6.QtCore import Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .calibration import rectify_maps, rectify_sbs
from .frames import compose_view
from .widgets import VideoView

PREVIEW_MAX_WIDTH = 1560
COMPARE_MODES = [
    ("Rectified SBS", "rectified"),
    ("Raw SBS", "raw"),
    ("Anaglyph (rect.)", "anaglyph"),
]


def _to_pixmap(frame: np.ndarray) -> QPixmap:
    frame = np.ascontiguousarray(frame)
    height, width = frame.shape[:2]
    image = QImage(frame.data, width, height, frame.strides[0], QImage.Format.Format_BGR888)
    return QPixmap.fromImage(image)


class RectifyPreview(QWidget):
    """Rectified-vs-raw comparison with epipolar guide lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calib = None
        self._maps = None
        self._size_warned = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        bar_frame = QFrame(objectName="Toolbar")
        bar = QHBoxLayout(bar_frame)
        bar.setContentsMargins(14, 10, 14, 10)
        bar.setSpacing(10)
        bar.addWidget(QLabel("View", objectName="RowLabel"))
        self.compare_combo = QComboBox()
        for label, mode in COMPARE_MODES:
            self.compare_combo.addItem(label, mode)
        self.compare_combo.setToolTip("Compare before/after — flip between raw and rectified to check alignment on the guide lines")
        bar.addWidget(self.compare_combo)

        self.guide_button = QPushButton("Guides", objectName="GuideButton")
        self.guide_button.setCheckable(True)
        self.guide_button.setChecked(True)
        self.guide_button.setToolTip("Epipolar horizontal lines — after rectify, matching features should sit on the same line")
        bar.addWidget(self.guide_button)

        bar.addStretch(1)
        self.info_label = QLabel("", objectName="CalibResult")
        bar.addWidget(self.info_label)
        layout.addWidget(bar_frame)

        self.preview = VideoView(
            idle_title="Waiting for alignment check",
            idle_subtitle="Load a calibration and start the stream to see the rectified result",
        )
        self.preview.set_guides(True)
        self.guide_button.toggled.connect(self.preview.set_guides)
        layout.addWidget(self.preview, stretch=1)

    # ── 외부 연결점 ──────────────────────────────────────────

    def set_calibration(self, calib) -> None:
        self._calib = calib
        self._maps = rectify_maps(calib) if calib is not None else None
        self._size_warned = False
        if calib is None:
            self.info_label.setText("No calibration")
        else:
            self.info_label.setText(
                f"baseline {calib.baseline_mm:.2f} mm · RMS {calib.rms_stereo:.3f} · {calib.created}"
            )

    @Slot(object)
    def on_preview_frame(self, frame) -> None:
        if self._maps is None:
            return
        calib_w, calib_h = self._calib.image_size
        if frame.shape[0] != calib_h or frame.shape[1] != 2 * calib_w:
            if not self._size_warned:
                self._size_warned = True
                self.info_label.setText(
                    f"Size mismatch — calibration per eye {calib_w}×{calib_h}, "
                    f"stream {frame.shape[1]}×{frame.shape[0]}"
                )
            return

        mode = self.compare_combo.currentData()
        rectified = rectify_sbs(frame, self._maps)
        if mode == "raw":
            display, view_mode = frame, "sbs"
        elif mode == "anaglyph":
            display, view_mode = compose_view(rectified, "anaglyph"), "anaglyph"
        else:
            display, view_mode = rectified, "sbs"

        if display.shape[1] > PREVIEW_MAX_WIDTH:
            scale = PREVIEW_MAX_WIDTH / display.shape[1]
            display = cv2.resize(display, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        self.preview.set_frame(_to_pixmap(display), view_mode=view_mode)
