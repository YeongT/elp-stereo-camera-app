"""Calibration tab: 수집·실행 / 정렬 검증 / 뎁스 sub-tabs.

CaptureView collects chessboard pairs and solves; RectifyPreview and
DepthPreview (own modules) consume the worker's preview tap. Detection and the
calibration solve run in helper threads — results come back through Qt
signals, so the GUI thread never blocks on OpenCV."""

import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .calibration import (
    MIN_PAIRS,
    RECOMMENDED_PAIRS,
    BoardSpec,
    calibrate_stereo,
    detect_pair_with_square_count_fallback,
    draw_pair_overlay,
)
from .cards import SectionCard
from .depth_preview import DepthPreview
from .paths import CALIBRATION_DIR, CALIBRATION_PAIRS_DIR
from .rectify_preview import RectifyPreview
from .segmented import SegmentedStack
from .widgets import VideoView
from .frames import split_sbs

AUTO_CAPTURE_MS = 2000
PREVIEW_MAX_WIDTH = 1560
THUMBNAIL_WIDTH = 96


def _to_pixmap(frame: np.ndarray) -> QPixmap:
    frame = np.ascontiguousarray(frame)
    height, width = frame.shape[:2]
    image = QImage(frame.data, width, height, frame.strides[0], QImage.Format.Format_BGR888)
    return QPixmap.fromImage(image)


class CaptureView(QWidget):
    """수집·실행 sub-tab: chessboard pair collection and the stereo solve."""

    request_frame = Signal()  # ask the window for one full-res stream frame
    calibrated = Signal(object)  # StereoCalibration
    log = Signal(str)
    _detected = Signal(object, object, object, object, str)  # (overlay, pair, BoardSpec, paths | None, save error)
    _solved = Signal(object, str)  # (StereoCalibration | None, error message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pairs: list = []
        self._image_size: tuple[int, int] | None = None  # per-eye, locked at first pair
        self._detecting = False
        self._solving = False
        self._streaming = False
        self._auto_ready = False
        self._pattern_hint = ""
        self._capture_session_dir: Path | None = None
        self._design_baseline = 0.0  # from the active camera profile; 0 = unknown
        self._build_ui()
        self._detected.connect(self._on_detected)
        self._solved.connect(self._on_solved)

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        side = QVBoxLayout()
        side.setSpacing(12)

        board_card = SectionCard("Chessboard (inner corners)", "9×6 squares = 8×5 inner corners")

        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(3, 25)
        self.cols_spin.setValue(9)
        self.cols_spin.setToolTip("Inner intersections across — a 9-square-wide board has 8")
        board_card.add_row("Columns", self.cols_spin)

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(3, 25)
        self.rows_spin.setValue(6)
        self.rows_spin.setToolTip("Inner intersections down — a 6-square-high board has 5")
        board_card.add_row("Rows", self.rows_spin)

        self.square_spin = QDoubleSpinBox()
        self.square_spin.setRange(1.0, 200.0)
        self.square_spin.setValue(25.0)
        self.square_spin.setDecimals(1)
        self.square_spin.setSuffix(" mm")
        self.square_spin.setToolTip("Real edge length of one chessboard square")
        board_card.add_row("Square", self.square_spin)

        for spin in (self.cols_spin, self.rows_spin, self.square_spin):
            spin.valueChanged.connect(self._on_board_changed)

        self.capture_button = QPushButton("Capture")
        self.capture_button.setEnabled(False)
        self.capture_button.setToolTip("Add a pair when corners are found in both eyes of the current frame")
        self.capture_button.clicked.connect(self.request_frame.emit)
        self.auto_button = QPushButton("Auto Capture", objectName="AutoCaptureButton")
        self.auto_button.setCheckable(True)
        self.auto_button.setEnabled(False)
        self.auto_button.setToolTip("Continuously scan until a board is found, then wait the selected interval")
        self.auto_button.toggled.connect(self._on_auto_toggled)

        self.auto_interval_spin = QSpinBox()
        self.auto_interval_spin.setRange(1, 60)
        self.auto_interval_spin.setValue(AUTO_CAPTURE_MS // 1000)
        self.auto_interval_spin.setSuffix(" s")
        self.auto_interval_spin.setToolTip("Wait time after each successful automatic capture")
        board_card.add_row("Interval", self.auto_interval_spin)
        board_card.add_grid((self.capture_button, self.auto_button))
        side.addWidget(board_card)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._on_auto_interval_elapsed)

        self.status_label = QLabel(f"0 pairs — min {MIN_PAIRS}, recommended {RECOMMENDED_PAIRS}+")
        self.status_label.setWordWrap(True)
        side.addWidget(self.status_label)

        self.pair_list = QListWidget(objectName="FileList")
        self.pair_list.setIconSize(QSize(THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 3 // 8))
        side.addWidget(self.pair_list, stretch=1)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(10)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_selected)
        edit_row.addWidget(delete_button)
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self._clear_pairs)
        edit_row.addWidget(clear_button)
        side.addLayout(edit_row)

        self.solve_button = QPushButton("Run Calibration", objectName="CalibrateButton")
        self.solve_button.setEnabled(False)
        self.solve_button.clicked.connect(self._run_solve)
        side.addWidget(self.solve_button)

        self.result_label = QLabel("", objectName="CalibResult")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self.result_label)

        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(360)
        layout.addWidget(side_widget)

        self.preview = VideoView(
            idle_title="Waiting for calibration",
            idle_subtitle=(
                "Start the stream from the header, hold the chessboard so both cameras see it, "
                "and capture. Vary distance and tilt; 12+ pairs gives an accurate result."
            ),
        )
        layout.addWidget(self.preview, stretch=1)

    # ── 외부 연결점 (window가 호출) ──────────────────────────

    def board_spec(self) -> BoardSpec:
        return BoardSpec(self.cols_spin.value(), self.rows_spin.value(), float(self.square_spin.value()))

    def set_design_baseline(self, baseline_mm: float) -> None:
        self._design_baseline = baseline_mm

    def set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming
        self.capture_button.setEnabled(streaming)
        self.auto_button.setEnabled(streaming)
        if not streaming:
            self.auto_button.setChecked(False)
            self._auto_ready = False
        elif not self._pairs:
            self.status_label.setText("Live preview ready — capture manually or turn on Auto Capture.")

    def _show_preview(self, frame) -> None:
        """Render the throttled raw camera feed without triggering detection."""
        preview = frame
        if preview.shape[1] > PREVIEW_MAX_WIDTH:
            scale = PREVIEW_MAX_WIDTH / preview.shape[1]
            preview = cv2.resize(preview, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        self.preview.set_frame(_to_pixmap(preview))

    @Slot(object)
    def on_preview_frame(self, frame) -> None:
        """Keep the right-hand camera view live while collecting pairs."""
        self._show_preview(frame)
        if self.auto_button.isChecked() and self._auto_ready:
            self._start_detection(frame)

    @Slot(object)
    def on_frame(self, frame) -> None:
        """Full-res frame from the worker; detect in a helper thread."""
        self._start_detection(frame)

    def _start_detection(self, frame) -> None:
        """Start one detection at a time; preview frames continue while it runs."""
        if self._detecting:
            return
        self._detecting = True
        board = self.board_spec()
        pair_number = len(self._pairs) + 1

        def _detect() -> None:
            try:
                detected_board, pair = detect_pair_with_square_count_fallback(frame, board)
                overlay = draw_pair_overlay(frame, detected_board, pair) if pair is not None else frame
                paths = None
                save_error = ""
                if pair is not None:
                    try:
                        paths = self._save_pair_images(frame, pair_number)
                    except OSError as exc:
                        save_error = str(exc)
                self._detected.emit(overlay, pair, detected_board, paths, save_error)
            except Exception as exc:  # noqa: BLE001 — keep auto capture recoverable
                self._detected.emit(frame, None, board, None, f"Detection error: {exc}")

        threading.Thread(target=_detect, daemon=True, name="calib-detect").start()

    # ── 내부 동작 ────────────────────────────────────────────

    @Slot()
    def _on_auto_toggled(self, checked: bool) -> None:
        if checked:
            self._auto_timer.stop()
            self._auto_ready = True
            self.status_label.setText(
                "Auto Capture on — scanning continuously until the first board is found."
            )
        else:
            self._auto_timer.stop()
            self._auto_ready = False
            self._update_status()

    @Slot()
    def _on_auto_interval_elapsed(self) -> None:
        if not self.auto_button.isChecked():
            return
        self._auto_ready = True
        self.status_label.setText("Auto Capture scanning for the next board position.")

    @Slot()
    def _on_board_changed(self) -> None:
        if self._pairs:
            self._clear_pairs()
            self.status_label.setText("Board spec changed — captures cleared.")
        self._pattern_hint = ""

    @Slot(object, object, object, object, str)
    def _on_detected(self, overlay, pair, detected_board, paths, save_error: str) -> None:
        self._detecting = False

        if save_error and pair is None:
            self.status_label.setText(save_error)
            self.log.emit(f"[ERROR] Chessboard detection failed: {save_error}")
            return

        if pair is None:
            if self.auto_button.isChecked():
                self.status_label.setText(
                    "Auto Capture on — no complete board yet; keep it visible in both eyes. "
                    "Counts are inner corners, not squares."
                )
            else:
                self.status_label.setText(
                    "Detection failed — use inner corners: a 9×6-square board is 8×5."
                )
            return

        if save_error:
            self.status_label.setText(f"Detected the board but could not save the pair: {save_error}")
            self.log.emit(f"[ERROR] Calibration pair save failed: {save_error}")
            return

        configured_board = self.board_spec()
        if detected_board != configured_board:
            for spin, value in (
                (self.cols_spin, detected_board.cols),
                (self.rows_spin, detected_board.rows),
            ):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
            self._pattern_hint = f"detected {detected_board.cols}×{detected_board.rows} inner corners"

        eye_size = (overlay.shape[1] // 2, overlay.shape[0])
        if self._image_size is None:
            self._image_size = eye_size
        elif eye_size != self._image_size:
            self.status_label.setText(
                f"Resolution changed (was per eye {self._image_size[0]}×{self._image_size[1]}) — "
                "clear all and recapture."
            )
            return

        self._pairs.append(pair)
        pair_number = len(self._pairs)
        thumb = cv2.resize(overlay, (THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * overlay.shape[0] // overlay.shape[1]))
        item = QListWidgetItem(QIcon(_to_pixmap(thumb)), f"Pair {len(self._pairs)}")
        self.pair_list.addItem(item)
        self.preview.flash_capture()
        self.log.emit(f"Calibration pair {pair_number} saved — {paths[0].name}, {paths[1].name}")
        self._update_status()
        if self.auto_button.isChecked():
            self._auto_ready = False
            interval_s = self.auto_interval_spin.value()
            self._auto_timer.start(interval_s * 1000)
            self.status_label.setText(
                f"{len(self._pairs)} pairs — captured. Next automatic capture in {interval_s}s."
            )

    def _update_status(self) -> None:
        count = len(self._pairs)
        hint = f"min {MIN_PAIRS}, recommended {RECOMMENDED_PAIRS}+" if count < RECOMMENDED_PAIRS else "ready"
        pattern_hint = getattr(self, "_pattern_hint", "")
        suffix = f" · {pattern_hint}" if pattern_hint else ""
        self.status_label.setText(f"{count} pairs — {hint}{suffix}")
        self.solve_button.setEnabled(count >= MIN_PAIRS and not self._solving)

    def _delete_selected(self) -> None:
        row = self.pair_list.currentRow()
        if row < 0:
            return
        self.pair_list.takeItem(row)
        del self._pairs[row]
        for i in range(self.pair_list.count()):
            self.pair_list.item(i).setText(f"Pair {i + 1}")
        if not self._pairs:
            self._image_size = None
        self._update_status()

    def _clear_pairs(self) -> None:
        self.pair_list.clear()
        self._pairs.clear()
        self._image_size = None
        self._capture_session_dir = None
        self._update_status()

    def _save_pair_images(self, frame, pair_number: int) -> tuple[Path, Path]:
        """Persist the pre-rectification SBS input as separate left/right PNGs."""
        if self._capture_session_dir is None:
            base = CALIBRATION_PAIRS_DIR / time.strftime("%Y%m%d_%H%M%S")
            session = base
            suffix = 2
            while session.exists():
                session = CALIBRATION_PAIRS_DIR / f"{base.name}_{suffix}"
                suffix += 1
            session.mkdir(parents=True, exist_ok=False)
            self._capture_session_dir = session

        left, right = split_sbs(frame)
        left_path = self._capture_session_dir / f"pair_{pair_number:03d}_left.png"
        right_path = self._capture_session_dir / f"pair_{pair_number:03d}_right.png"
        if not cv2.imwrite(str(left_path), left) or not cv2.imwrite(str(right_path), right):
            raise OSError("Could not write calibration pair images")
        return left_path, right_path

    # ── 계산 ─────────────────────────────────────────────────

    def _run_solve(self) -> None:
        if self._solving or self._image_size is None:
            return
        self._solving = True
        self.solve_button.setEnabled(False)
        self.solve_button.setText("Solving…")
        board = self.board_spec()
        image_size = self._image_size
        pairs = list(self._pairs)

        def _solve() -> None:
            try:
                calib = calibrate_stereo(board, image_size, pairs)
                calib.save(CALIBRATION_DIR)
                self._solved.emit(calib, "")
            except Exception as exc:  # noqa: BLE001 — degenerate poses raise from cv2
                self._solved.emit(None, str(exc))

        threading.Thread(target=_solve, daemon=True, name="calib-solve").start()

    @Slot(object, str)
    def _on_solved(self, calib, error: str) -> None:
        self._solving = False
        self.solve_button.setText("Run Calibration")
        self._update_status()
        if calib is None:
            self.result_label.setText(f"Failed: {error}")
            self.log.emit(f"[ERROR] Calibration failed: {error}")
            return
        design = f" (design {self._design_baseline:.2f})" if self._design_baseline > 0 else ""
        self.result_label.setText(
            f"RMS: stereo {calib.rms_stereo:.3f} (L {calib.rms_left:.3f} / R {calib.rms_right:.3f})\n"
            f"baseline: {calib.baseline_mm:.2f} mm{design}\n"
            f"input pairs: {calib.pair_count}\n"
            f"fx L/R: {calib.K1[0, 0]:.1f} / {calib.K2[0, 0]:.1f} px\n"
            f"Saved: {CALIBRATION_DIR.as_posix()}/ (npz + json)"
        )
        self.log.emit(
            f"Calibration done — RMS {calib.rms_stereo:.3f}, baseline {calib.baseline_mm:.2f} mm, "
            f"{len(self._pairs)} pairs"
        )
        self.calibrated.emit(calib)


class CalibrationTab(QWidget):
    """Container: Capture / Align / Depth sub-tabs behind one main page.

    Keeps the window-facing surface of the old single-page tab (signals,
    on_frame, set_streaming, ...) and routes the worker's preview tap to
    whichever sub-tab is active."""

    request_frame = Signal()
    calibrated = Signal(object)
    log = Signal(str)
    preview_needed = Signal()  # active sub-tab changed — window re-evaluates the tap

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.capture = CaptureView()
        self.verify = RectifyPreview()
        self.depth = DepthPreview()

        self.sub_tabs = SegmentedStack(object_name="SubNav", heading="Calibration workspace")
        self.sub_tabs.addTab(self.capture, "Capture")
        self.sub_tabs.addTab(self.verify, "Align")
        self.sub_tabs.addTab(self.depth, "Depth")
        self.sub_tabs.currentChanged.connect(lambda _index: self.preview_needed.emit())
        layout.addWidget(self.sub_tabs)

        self.capture.request_frame.connect(self.request_frame)
        self.capture.calibrated.connect(self.calibrated)
        self.capture.calibrated.connect(self.set_calibration)
        self.capture.log.connect(self.log)

        # window/tool compatibility surface
        self.status_label = self.capture.status_label
        self.pair_list = self.capture.pair_list

    def wants_preview(self) -> bool:
        """True when the active sub-tab consumes the continuous preview tap."""
        return self.sub_tabs.currentWidget() in (self.capture, self.verify, self.depth)

    def set_streaming(self, streaming: bool) -> None:
        self.capture.set_streaming(streaming)

    def set_design_baseline(self, baseline_mm: float) -> None:
        self.capture.set_design_baseline(baseline_mm)

    @Slot(object)
    def set_calibration(self, calib) -> None:
        self.verify.set_calibration(calib)
        self.depth.set_calibration(calib)

    @Slot(object)
    def on_frame(self, frame) -> None:
        self.capture.on_frame(frame)

    @Slot(object)
    def on_preview_frame(self, frame) -> None:
        widget = self.sub_tabs.currentWidget()
        if widget is self.capture:
            self.capture.on_preview_frame(frame)
        elif widget is self.verify:
            self.verify.on_preview_frame(frame)
        elif widget is self.depth:
            self.depth.on_preview_frame(frame)
