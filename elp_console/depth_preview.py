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
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .calibration import rectify_maps, rectify_sbs
from .frames import split_sbs
from .stereo_depth import (
    COLORMAPS,
    DEPTH_PROFILES,
    DepthProfile,
    SgbmParams,
    auto_num_disparities,
    auto_tune,
    colorize_disparity,
    compute_disparity,
    reproject_point,
)
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

    _computed = Signal(object, object, object, float)  # (rectified SBS, disparity, colorized, scale)
    _tuned = Signal(object)  # best SgbmParams from the auto-tune thread
    _failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calib = None
        self._maps = None
        self._computing = False
        self._tuning = False
        self._disp = None  # last disparity (downscaled)
        self._scale = 1.0  # downscale factor vs calibration resolution
        self._last_pair = None  # last downscaled (left_gray, right_gray) — auto-tune input
        self._size_warned = False
        self._applying_profile = False
        self._build_ui()
        self._computed.connect(self._on_computed)
        self._tuned.connect(self._on_tuned)
        self._failed.connect(self._on_failed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        bar = QFrame(objectName="Toolbar")
        grid = QGridLayout(bar)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        def _label(text: str) -> QLabel:
            label = QLabel(text, objectName="RowLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return label

        self.profile_combo = QComboBox()
        for profile in DEPTH_PROFILES:
            self.profile_combo.addItem(profile.name, profile)
        self.profile_combo.addItem("Custom", None)
        self.profile_combo.setToolTip("Analysis preset. Editing a value below switches this to Custom.")
        grid.addWidget(_label("Profile"), 0, 0)
        grid.addWidget(self.profile_combo, 0, 1, 1, 2)

        self.profile_hint = QLabel(objectName="DepthProfileHint")
        self.profile_hint.setWordWrap(True)
        grid.addWidget(self.profile_hint, 0, 3, 1, 4)

        self.autotune_button = QPushButton("Auto-tune", objectName="AutoTuneButton")
        self.autotune_button.setEnabled(False)
        self.autotune_button.setToolTip(
            "Refine this frame for coverage and local depth consistency; results become a Custom profile"
        )
        self.autotune_button.clicked.connect(self._start_autotune)
        grid.addWidget(self.autotune_button, 0, 7, 1, 2)

        self.colormap_combo = QComboBox()
        for name, code in COLORMAPS:
            self.colormap_combo.addItem(name, code)
        self.colormap_combo.setToolTip("Color scale used only to visualize the active disparity profile")
        grid.addWidget(_label("Color scale"), 1, 0)
        grid.addWidget(self.colormap_combo, 1, 1)

        self.width_combo = QComboBox()
        for width in COMPUTE_WIDTHS:
            self.width_combo.addItem(f"{width} px", width)
        self.width_combo.setCurrentIndex(1)
        self.width_combo.setToolTip("Per-eye width SGBM runs on — larger is sharper but slower")
        grid.addWidget(_label("Compute"), 1, 2)
        grid.addWidget(self.width_combo, 1, 3)

        self.min_dist_spin = QSpinBox()
        self.min_dist_spin.setRange(100, 5000)
        self.min_dist_spin.setSingleStep(50)
        self.min_dist_spin.setValue(400)
        self.min_dist_spin.setSuffix(" mm")
        self.min_dist_spin.setToolTip(
            "Nearest subject distance — auto-derives the disparity range from calibration geometry"
        )
        grid.addWidget(_label("Near limit"), 1, 4)
        grid.addWidget(self.min_dist_spin, 1, 5)

        self.num_disp_spin = QSpinBox()
        self.num_disp_spin.setRange(16, 256)
        self.num_disp_spin.setSingleStep(16)
        self.num_disp_spin.setValue(96)
        self.num_disp_spin.setToolTip(
            "Search disparity range (multiple of 16) — auto-set from min distance, still adjustable"
        )
        grid.addWidget(_label("Range"), 1, 6)
        grid.addWidget(self.num_disp_spin, 1, 7)

        self.block_spin = QSpinBox()
        self.block_spin.setRange(3, 21)
        self.block_spin.setSingleStep(2)
        self.block_spin.setValue(7)
        self.block_spin.setToolTip("Matching block size (odd) — larger is smoother, smaller is finer")
        grid.addWidget(_label("Block"), 1, 9)
        grid.addWidget(self.block_spin, 1, 10)

        self.uniq_spin = QSpinBox()
        self.uniq_spin.setRange(0, 30)
        self.uniq_spin.setValue(10)
        self.uniq_spin.setToolTip("uniquenessRatio — higher rejects ambiguous matches")
        grid.addWidget(_label("Unique"), 1, 11)
        grid.addWidget(self.uniq_spin, 1, 12)

        self.speckle_spin = QSpinBox()
        self.speckle_spin.setRange(0, 300)
        self.speckle_spin.setSingleStep(10)
        self.speckle_spin.setValue(100)
        self.speckle_spin.setToolTip("speckleWindowSize — removes small noise speckles")
        grid.addWidget(_label("Speckle"), 1, 13)
        grid.addWidget(self.speckle_spin, 1, 14)

        grid.setColumnStretch(8, 1)
        grid.setColumnStretch(15, 1)
        layout.addWidget(bar)

        self.min_dist_spin.valueChanged.connect(self._recompute_disparity_range)
        self.width_combo.currentIndexChanged.connect(self._recompute_disparity_range)
        self.profile_combo.currentIndexChanged.connect(self._apply_selected_profile)
        for control in (
            self.colormap_combo,
            self.width_combo,
            self.min_dist_spin,
            self.num_disp_spin,
            self.block_spin,
            self.uniq_spin,
            self.speckle_spin,
        ):
            signal = control.currentIndexChanged if isinstance(control, QComboBox) else control.valueChanged
            signal.connect(self._mark_profile_custom)
        self.colormap_combo.currentIndexChanged.connect(self._update_depth_legend)

        # The primary surface is depth. The rectified SBS pair remains visible
        # alongside it as evidence for matching/lighting/alignment diagnosis.
        self.preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_splitter.setHandleWidth(8)

        primary = QFrame(objectName="DepthPrimaryPanel")
        primary_layout = QVBoxLayout(primary)
        primary_layout.setContentsMargins(14, 12, 14, 14)
        primary_layout.setSpacing(8)

        primary_header = QHBoxLayout()
        primary_header.setSpacing(10)
        primary_header.addWidget(QLabel("Depth map", objectName="DepthPrimaryTitle"))
        primary_header.addWidget(QLabel("Relative depth · hover for metric distance", objectName="DepthPrimaryHint"))
        primary_header.addStretch(1)
        legend = QFrame(objectName="DepthLegend")
        legend_row = QHBoxLayout(legend)
        legend_row.setContentsMargins(8, 4, 8, 4)
        legend_row.setSpacing(6)
        legend_row.addWidget(QLabel("Far", objectName="DepthLegendLabel"))
        self.depth_legend = QLabel(objectName="DepthLegendGradient")
        legend_row.addWidget(self.depth_legend)
        legend_row.addWidget(QLabel("Near", objectName="DepthLegendLabel"))
        primary_header.addWidget(legend)
        self.distance_label = QLabel("Dist —", objectName="DepthDistance")
        self.distance_label.setToolTip("Hover the depth map to read this point's calibrated distance")
        primary_header.addWidget(self.distance_label)
        primary_layout.addLayout(primary_header)

        self.view = DepthView(
            idle_title="Waiting for depth",
            idle_subtitle="Load a calibration and start the stream to see the depth map",
        )
        self.view.hovered.connect(self._on_hover)
        self.view.left.connect(lambda: self.distance_label.setText("Dist —"))
        self.view.setMinimumSize(460, 360)
        primary_layout.addWidget(self.view, stretch=1)
        self.preview_splitter.addWidget(primary)

        reference = QFrame(objectName="DepthReferencePanel")
        reference_layout = QVBoxLayout(reference)
        reference_layout.setContentsMargins(14, 12, 14, 14)
        reference_layout.setSpacing(8)
        reference_layout.addWidget(QLabel("Stereo reference", objectName="DepthReferenceTitle"))
        self.source_caption = QLabel("Rectified SBS input · LEFT / RIGHT", objectName="DepthPanelCaption")
        self.source_caption.setToolTip("The exact rectified stereo pair used for the depth calculation")
        reference_layout.addWidget(self.source_caption)
        self.source_view = VideoView(
            idle_title="Waiting for rectified source",
            idle_subtitle="Load a calibration and start the stream to inspect the SBS input",
        )
        self.source_view.setMinimumSize(300, 220)
        reference_layout.addWidget(self.source_view, stretch=1)
        self.calibration_label = QLabel("Calibration —", objectName="CalibrationSummary")
        self.calibration_label.setWordWrap(True)
        self.calibration_label.setToolTip("Calibration used to rectify and measure the primary depth map")
        reference_layout.addWidget(self.calibration_label)
        self.preview_splitter.addWidget(reference)
        self.preview_splitter.setStretchFactor(0, 3)
        self.preview_splitter.setStretchFactor(1, 2)
        self.preview_splitter.setSizes([900, 500])
        layout.addWidget(self.preview_splitter, stretch=1)

        self._apply_selected_profile()
        self._update_depth_legend()

    # ── 외부 연결점 ──────────────────────────────────────────

    def set_calibration(self, calib) -> None:
        self._calib = calib
        self._maps = rectify_maps(calib) if calib is not None else None
        self._disp = None
        self._last_pair = None
        self._size_warned = False
        self.autotune_button.setEnabled(False)
        if calib is None:
            self.calibration_label.setText("Calibration —")
            self.source_view.set_state("idle")
            self.view.set_state("idle")
        else:
            pair_text = f"{calib.pair_count} pairs" if calib.pair_count else "pair count unrecorded"
            self.calibration_label.setText(
                f"Calib · RMS {calib.rms_stereo:.3f} px · {calib.baseline_mm:.2f} mm · "
                f"{calib.board.cols}×{calib.board.rows} · {pair_text}"
            )
        self._recompute_disparity_range()

    def _update_depth_legend(self, *_args) -> None:
        """Render a compact Far → Near key for the active display colormap."""
        colormap = self.colormap_combo.currentData()
        gradient = np.linspace(0, 255, 160, dtype=np.uint8).reshape(1, -1)
        color = np.ascontiguousarray(cv2.applyColorMap(gradient, colormap))
        image = QImage(color.data, color.shape[1], color.shape[0], color.strides[0], QImage.Format.Format_BGR888)
        self.depth_legend.setPixmap(QPixmap.fromImage(image).scaled(160, 12))

    def _apply_selected_profile(self) -> None:
        profile = self.profile_combo.currentData()
        if not isinstance(profile, DepthProfile):
            self.profile_hint.setText("Manual values — suitable when validating a specific scene")
            return
        self._applying_profile = True
        try:
            self.profile_hint.setText(profile.description)
            self._set_combo_data(self.colormap_combo, profile.colormap)
            self._set_combo_data(self.width_combo, profile.compute_width)
            for spin, value in (
                (self.min_dist_spin, profile.min_distance_mm),
                (self.block_spin, profile.block_size),
                (self.uniq_spin, profile.uniqueness),
                (self.speckle_spin, profile.speckle_window),
            ):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
            self._recompute_disparity_range()
            self._update_depth_legend()
        finally:
            self._applying_profile = False

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _mark_profile_custom(self, *_args) -> None:
        if self._applying_profile or self.profile_combo.currentData() is None:
            return
        custom_index = self.profile_combo.count() - 1
        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentIndex(custom_index)
        self.profile_combo.blockSignals(False)
        self.profile_hint.setText("Manual values — suitable when validating a specific scene")

    def _recompute_disparity_range(self) -> None:
        """Derive numDisparities from the calibration geometry and min distance.

        Runs on the downscaled pair, so the scale factor shrinks the disparity
        the SGBM search must cover."""
        if self._calib is None:
            return
        focal_px = float(self._calib.P1[0, 0])
        calib_w = self._calib.image_size[0]
        scale = min(1.0, self.width_combo.currentData() / calib_w)
        num = auto_num_disparities(focal_px, self._calib.baseline_mm, self.min_dist_spin.value(), scale=scale)
        self.num_disp_spin.blockSignals(True)
        self.num_disp_spin.setValue(num)
        self.num_disp_spin.blockSignals(False)

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
                self.distance_label.setText(f"Size mismatch — calibration is per eye {calib_w}×{calib_h}")
            return

        self._computing = True
        maps = self._maps
        params = self.params()
        colormap = self.colormap_combo.currentData()
        scale = self.width_combo.currentData() / calib_w

        def _compute() -> None:
            try:
                rectified = rectify_sbs(frame, maps)
                left, right = split_sbs(rectified)
                if scale < 1.0:
                    left = cv2.resize(left, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                    right = cv2.resize(right, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                left_gray = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
                right_gray = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
                self._last_pair = (left_gray, right_gray)  # auto-tune input
                disp = compute_disparity(left_gray, right_gray, params)
                color = colorize_disparity(disp, params.num_disparities, colormap)
                self._computed.emit(rectified, disp, color, min(scale, 1.0))
            except Exception as exc:  # noqa: BLE001 — recover the live preview on a bad frame
                self._failed.emit(str(exc))

        threading.Thread(target=_compute, daemon=True, name="depth-sgbm").start()

    # ── 내부 동작 ────────────────────────────────────────────

    @Slot(object, object, object, float)
    def _on_computed(self, rectified, disp, color, scale: float) -> None:
        self._computing = False
        self._disp = disp
        self._scale = scale
        if not self._tuning:
            self.autotune_button.setEnabled(True)
        self.source_view.set_frame(self._pixmap_from_bgr(rectified), view_mode="sbs")
        self.view.set_frame(self._pixmap_from_bgr(color), view_mode="none")

    @staticmethod
    def _pixmap_from_bgr(image_bgr) -> QPixmap:
        image_bgr = np.ascontiguousarray(image_bgr)
        height, width = image_bgr.shape[:2]
        image = QImage(image_bgr.data, width, height, image_bgr.strides[0], QImage.Format.Format_BGR888)
        return QPixmap.fromImage(image)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._computing = False
        self.source_view.set_state("error", message)
        self.view.set_state("error", message)

    def _start_autotune(self) -> None:
        if self._tuning or self._last_pair is None:
            return
        self._tuning = True
        self.autotune_button.setText("Tuning…")
        self.autotune_button.setEnabled(False)
        left_gray, right_gray = self._last_pair
        base = self.params()

        def _run() -> None:
            best, _score = auto_tune(left_gray, right_gray, base)
            self._tuned.emit(best)

        threading.Thread(target=_run, daemon=True, name="depth-autotune").start()

    @Slot(object)
    def _on_tuned(self, params) -> None:
        self._tuning = False
        self.autotune_button.setText("Auto-tune")
        self.autotune_button.setEnabled(self._last_pair is not None)
        for spin, value in (
            (self.block_spin, params.block_size),
            (self.uniq_spin, params.uniqueness),
            (self.speckle_spin, params.speckle_window),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._mark_profile_custom()

    @Slot(float, float)
    def _on_hover(self, u: float, v: float) -> None:
        if self._disp is None or self._calib is None:
            return
        x = int(u * (self._disp.shape[1] - 1))
        y = int(v * (self._disp.shape[0] - 1))
        disparity = float(self._disp[y, x])
        if disparity <= 0:
            self.distance_label.setText("Dist — (no match)")
            return
        # Q is at calibration resolution — scale the downscaled coords/disparity back up
        point = reproject_point(x / self._scale, y / self._scale, disparity / self._scale, self._calib.Q)
        if point is None:
            self.distance_label.setText("Dist —")
            return
        _, _, z = point
        self.distance_label.setText(f"Dist {z:.0f} mm (d {disparity:.1f}px)")
