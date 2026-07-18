"""뎁스 sub-tab: live disparity map from the rectified pair.

SGBM runs in a helper thread on a downscaled pair (drop-frame semantics — a
busy solver skips incoming frames). Hovering the map reprojects the pixel
through Q and shows metric distance."""

import threading

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .calibration import rectify_maps, rectify_sbs
from .frames import split_sbs
from .stereo_depth import COLORMAPS, SgbmParams, colorize_disparity, compute_disparity, reproject_point
from .widgets import VideoView

COMPUTE_WIDTHS = [480, 640, 800]  # per-eye width the SGBM pair is downscaled to


class DepthView(VideoView):
    """VideoView that reports normalized hover position over the image."""

    hovered = Signal(float, float)  # (u, v) in [0, 1] over the displayed image
    left = Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt override
        target = self._target_rect()
        if self._pixmap is not None and target.width() > 0 and target.contains(event.position().toPoint()):
            u = (event.position().x() - target.x()) / target.width()
            v = (event.position().y() - target.y()) / target.height()
            self.hovered.emit(u, v)
        else:
            self.left.emit()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 — Qt override
        self.left.emit()
        super().leaveEvent(event)


class DepthPreview(QWidget):
    """Live disparity preview with SGBM parameters and hover distance."""

    _computed = Signal(object, object, float)  # (disparity, colorized, scale)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calib = None
        self._maps = None
        self._computing = False
        self._disp = None  # last disparity (downscaled)
        self._scale = 1.0  # downscale factor vs calibration resolution
        self._size_warned = False
        self._build_ui()
        self._computed.connect(self._on_computed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        def _label(text: str) -> QLabel:
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return label

        self.colormap_combo = QComboBox()
        for name, code in COLORMAPS:
            self.colormap_combo.addItem(name, code)
        grid.addWidget(_label("컬러맵"), 0, 0)
        grid.addWidget(self.colormap_combo, 0, 1)

        self.width_combo = QComboBox()
        for width in COMPUTE_WIDTHS:
            self.width_combo.addItem(f"{width} px", width)
        self.width_combo.setCurrentIndex(1)
        self.width_combo.setToolTip("SGBM 연산용 눈당 가로 해상도 — 클수록 정밀하지만 느림")
        grid.addWidget(_label("연산 폭"), 0, 2)
        grid.addWidget(self.width_combo, 0, 3)

        self.num_disp_spin = QSpinBox()
        self.num_disp_spin.setRange(16, 256)
        self.num_disp_spin.setSingleStep(16)
        self.num_disp_spin.setValue(96)
        self.num_disp_spin.setToolTip("탐색 시차 범위 (16의 배수) — 가까운 물체일수록 큰 값 필요")
        grid.addWidget(_label("시차 범위"), 0, 4)
        grid.addWidget(self.num_disp_spin, 0, 5)

        self.block_spin = QSpinBox()
        self.block_spin.setRange(3, 21)
        self.block_spin.setSingleStep(2)
        self.block_spin.setValue(7)
        self.block_spin.setToolTip("매칭 블록 크기 (홀수) — 크면 매끈, 작으면 세밀")
        grid.addWidget(_label("블록"), 1, 0)
        grid.addWidget(self.block_spin, 1, 1)

        self.uniq_spin = QSpinBox()
        self.uniq_spin.setRange(0, 30)
        self.uniq_spin.setValue(10)
        self.uniq_spin.setToolTip("uniquenessRatio — 높이면 애매한 매칭 제거")
        grid.addWidget(_label("고유도"), 1, 2)
        grid.addWidget(self.uniq_spin, 1, 3)

        self.speckle_spin = QSpinBox()
        self.speckle_spin.setRange(0, 300)
        self.speckle_spin.setSingleStep(10)
        self.speckle_spin.setValue(100)
        self.speckle_spin.setToolTip("speckleWindowSize — 작은 노이즈 얼룩 제거 창")
        grid.addWidget(_label("스페클"), 1, 4)
        grid.addWidget(self.speckle_spin, 1, 5)

        grid.setColumnStretch(6, 1)
        self.distance_label = QLabel("거리 —", objectName="CalibResult")
        grid.addWidget(self.distance_label, 0, 7, 2, 1)
        layout.addLayout(grid)

        self.view = DepthView(
            idle_title="뎁스 대기 중",
            idle_subtitle="캘리브레이션을 로드하고 스트림을 켜면 disparity map이 표시됩니다",
        )
        self.view.hovered.connect(self._on_hover)
        self.view.left.connect(lambda: self.distance_label.setText("거리 —"))
        layout.addWidget(self.view, stretch=1)

    # ── 외부 연결점 ──────────────────────────────────────────

    def set_calibration(self, calib) -> None:
        self._calib = calib
        self._maps = rectify_maps(calib) if calib is not None else None
        self._disp = None
        self._size_warned = False

    def params(self) -> SgbmParams:
        return SgbmParams(
            num_disparities=self.num_disp_spin.value(),
            block_size=self.block_spin.value(),
            uniqueness=self.uniq_spin.value(),
            speckle_window=self.speckle_spin.value(),
        )

    @Slot(object)
    def on_preview_frame(self, frame) -> None:
        if self._maps is None or self._computing:
            return
        calib_w, calib_h = self._calib.image_size
        if frame.shape[0] != calib_h or frame.shape[1] != 2 * calib_w:
            if not self._size_warned:
                self._size_warned = True
                self.distance_label.setText(f"해상도 불일치 — 캘리브레이션 눈당 {calib_w}×{calib_h}")
            return

        self._computing = True
        maps = self._maps
        params = self.params()
        colormap = self.colormap_combo.currentData()
        scale = self.width_combo.currentData() / calib_w

        def _compute() -> None:
            rectified = rectify_sbs(frame, maps)
            left, right = split_sbs(rectified)
            if scale < 1.0:
                left = cv2.resize(left, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                right = cv2.resize(right, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            left_gray = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
            right_gray = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
            disp = compute_disparity(left_gray, right_gray, params)
            color = colorize_disparity(disp, params.num_disparities, colormap)
            self._computed.emit(disp, color, min(scale, 1.0))

        threading.Thread(target=_compute, daemon=True, name="depth-sgbm").start()

    # ── 내부 동작 ────────────────────────────────────────────

    @Slot(object, object, float)
    def _on_computed(self, disp, color, scale: float) -> None:
        self._computing = False
        self._disp = disp
        self._scale = scale
        color = np.ascontiguousarray(color)
        height, width = color.shape[:2]
        image = QImage(color.data, width, height, color.strides[0], QImage.Format.Format_BGR888)
        self.view.set_frame(QPixmap.fromImage(image), view_mode="none")

    @Slot(float, float)
    def _on_hover(self, u: float, v: float) -> None:
        if self._disp is None or self._calib is None:
            return
        x = int(u * (self._disp.shape[1] - 1))
        y = int(v * (self._disp.shape[0] - 1))
        disparity = float(self._disp[y, x])
        if disparity <= 0:
            self.distance_label.setText("거리 — (매칭 없음)")
            return
        # Q는 캘리브레이션 해상도 기준 — 다운스케일 좌표·시차를 원해상도로 환산
        point = reproject_point(x / self._scale, y / self._scale, disparity / self._scale, self._calib.Q)
        if point is None:
            self.distance_label.setText("거리 —")
            return
        _, _, z = point
        self.distance_label.setText(f"거리 {z:.0f} mm (d {disparity:.1f}px)")
