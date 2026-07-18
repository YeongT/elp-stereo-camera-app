"""정렬 검증 sub-tab: live rectified preview against the raw stream.

Consumes the worker's throttled preview tap (raw, pre-rectification frames)
and applies the loaded calibration itself, so the comparison works regardless
of the live tab's 정렬 보정 toggle."""

import cv2
import numpy as np
from PySide6.QtCore import Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .calibration import rectify_maps, rectify_sbs
from .frames import compose_view
from .widgets import VideoView

PREVIEW_MAX_WIDTH = 1560
COMPARE_MODES = [
    ("보정 SBS", "rectified"),
    ("원본 SBS", "raw"),
    ("아나글리프 (보정)", "anaglyph"),
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
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(QLabel("보기"))
        self.compare_combo = QComboBox()
        for label, mode in COMPARE_MODES:
            self.compare_combo.addItem(label, mode)
        self.compare_combo.setToolTip("보정 전/후 비교 — 원본과 보정을 오가며 가이드선 위 정렬을 확인")
        bar.addWidget(self.compare_combo)

        self.guide_button = QPushButton("수평 가이드", objectName="GuideButton")
        self.guide_button.setCheckable(True)
        self.guide_button.setChecked(True)
        self.guide_button.setToolTip("에피폴라 수평선 — 보정 후 좌우 특징이 같은 선 위에 있어야 정상")
        bar.addWidget(self.guide_button)

        bar.addStretch(1)
        self.info_label = QLabel("", objectName="CalibResult")
        bar.addWidget(self.info_label)
        layout.addLayout(bar)

        self.preview = VideoView(
            idle_title="정렬 검증 대기 중",
            idle_subtitle="캘리브레이션을 로드하고 헤더의 시작으로 스트림을 켜면 보정 결과가 표시됩니다",
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
            self.info_label.setText("캘리브레이션 없음")
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
                    f"해상도 불일치 — 캘리브레이션 눈당 {calib_w}×{calib_h}, "
                    f"스트림 {frame.shape[1]}×{frame.shape[0]}"
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
