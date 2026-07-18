"""Calibration tab: 수집·실행 / 정렬 검증 / 뎁스 sub-tabs.

CaptureView collects chessboard pairs and solves; RectifyPreview and
DepthPreview (own modules) consume the worker's preview tap. Detection and the
calibration solve run in helper threads — results come back through Qt
signals, so the GUI thread never blocks on OpenCV."""

import threading

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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .calibration import (
    MIN_PAIRS,
    RECOMMENDED_PAIRS,
    BoardSpec,
    calibrate_stereo,
    detect_pair,
    draw_pair_overlay,
)
from .depth_preview import DepthPreview
from .paths import CALIBRATION_DIR
from .rectify_preview import RectifyPreview
from .widgets import VideoView

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
    _detected = Signal(object, object)  # (overlay frame, pair | None) from helper thread
    _solved = Signal(object, str)  # (StereoCalibration | None, error message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pairs: list = []
        self._image_size: tuple[int, int] | None = None  # per-eye, locked at first pair
        self._detecting = False
        self._solving = False
        self._streaming = False
        self._design_baseline = 0.0  # from the active camera profile; 0 = unknown
        self._build_ui()
        self._detected.connect(self._on_detected)
        self._solved.connect(self._on_solved)

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        side = QVBoxLayout()
        side.setSpacing(8)

        board_row = QHBoxLayout()
        board_row.setSpacing(6)
        board_row.addWidget(QLabel("내부 코너"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(3, 25)
        self.cols_spin.setValue(9)
        self.cols_spin.setFixedWidth(56)
        board_row.addWidget(self.cols_spin)
        board_row.addWidget(QLabel("×"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(3, 25)
        self.rows_spin.setValue(6)
        self.rows_spin.setFixedWidth(56)
        board_row.addWidget(self.rows_spin)
        board_row.addSpacing(8)
        board_row.addWidget(QLabel("한 칸(mm)"))
        self.square_spin = QDoubleSpinBox()
        self.square_spin.setRange(1.0, 200.0)
        self.square_spin.setValue(25.0)
        self.square_spin.setDecimals(1)
        self.square_spin.setFixedWidth(76)
        board_row.addWidget(self.square_spin)
        board_row.addStretch(1)
        side.addLayout(board_row)
        for spin in (self.cols_spin, self.rows_spin, self.square_spin):
            spin.valueChanged.connect(self._on_board_changed)

        capture_row = QHBoxLayout()
        capture_row.setSpacing(8)
        self.capture_button = QPushButton("체스보드 캡처")
        self.capture_button.setEnabled(False)
        self.capture_button.setToolTip("현재 프레임에서 양쪽 눈 모두 코너 검출 시 쌍으로 추가")
        self.capture_button.clicked.connect(self.request_frame.emit)
        capture_row.addWidget(self.capture_button, stretch=1)
        self.auto_button = QPushButton("자동 캡처", objectName="AutoCaptureButton")
        self.auto_button.setCheckable(True)
        self.auto_button.setEnabled(False)
        self.auto_button.setToolTip(f"{AUTO_CAPTURE_MS // 1000}초 간격으로 자동 캡처 — 보드를 조금씩 움직이세요")
        self.auto_button.toggled.connect(self._on_auto_toggled)
        capture_row.addWidget(self.auto_button)
        side.addLayout(capture_row)

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(AUTO_CAPTURE_MS)
        self._auto_timer.timeout.connect(self.request_frame.emit)

        self.status_label = QLabel(f"체스보드 쌍 0개 — 최소 {MIN_PAIRS}, 권장 {RECOMMENDED_PAIRS}+")
        self.status_label.setWordWrap(True)
        side.addWidget(self.status_label)

        self.pair_list = QListWidget(objectName="FileList")
        self.pair_list.setIconSize(QSize(THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 3 // 8))
        side.addWidget(self.pair_list, stretch=1)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        delete_button = QPushButton("선택 삭제")
        delete_button.clicked.connect(self._delete_selected)
        edit_row.addWidget(delete_button)
        clear_button = QPushButton("전체 삭제")
        clear_button.clicked.connect(self._clear_pairs)
        edit_row.addWidget(clear_button)
        side.addLayout(edit_row)

        self.solve_button = QPushButton("캘리브레이션 실행", objectName="CalibrateButton")
        self.solve_button.setEnabled(False)
        self.solve_button.clicked.connect(self._run_solve)
        side.addWidget(self.solve_button)

        self.result_label = QLabel("", objectName="CalibResult")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self.result_label)

        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(340)
        layout.addWidget(side_widget)

        self.preview = VideoView(
            idle_title="캘리브레이션 대기 중",
            idle_subtitle=(
                "헤더의 시작으로 스트림을 켠 뒤 체스보드를 양쪽 카메라에 보이게 들고 "
                "캡처하세요. 거리·기울기를 바꿔 가며 12쌍 이상 모으면 정확해집니다"
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

    @Slot(object)
    def on_frame(self, frame) -> None:
        """Full-res frame from the worker; detect in a helper thread."""
        if self._detecting:
            return
        self._detecting = True
        board = self.board_spec()

        def _detect() -> None:
            pair = detect_pair(frame, board)
            overlay = draw_pair_overlay(frame, board, pair) if pair is not None else frame
            self._detected.emit(overlay, pair)

        threading.Thread(target=_detect, daemon=True, name="calib-detect").start()

    # ── 내부 동작 ────────────────────────────────────────────

    @Slot()
    def _on_auto_toggled(self, checked: bool) -> None:
        if checked:
            self._auto_timer.start()
            self.request_frame.emit()
        else:
            self._auto_timer.stop()

    @Slot()
    def _on_board_changed(self) -> None:
        if self._pairs:
            self._clear_pairs()
            self.status_label.setText("보드 사양 변경 — 캡처를 초기화했습니다.")

    @Slot(object, object)
    def _on_detected(self, overlay, pair) -> None:
        self._detecting = False
        preview = overlay
        if preview.shape[1] > PREVIEW_MAX_WIDTH:
            scale = PREVIEW_MAX_WIDTH / preview.shape[1]
            preview = cv2.resize(preview, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        self.preview.set_frame(_to_pixmap(preview))

        if pair is None:
            self.status_label.setText("검출 실패 — 보드 전체가 양쪽 눈에 보여야 합니다.")
            return

        eye_size = (overlay.shape[1] // 2, overlay.shape[0])
        if self._image_size is None:
            self._image_size = eye_size
        elif eye_size != self._image_size:
            self.status_label.setText(
                f"해상도가 바뀌었습니다 (기존 눈당 {self._image_size[0]}×{self._image_size[1]}) — "
                "전체 삭제 후 다시 캡처하세요."
            )
            return

        self._pairs.append(pair)
        thumb = cv2.resize(preview, (THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * preview.shape[0] // preview.shape[1]))
        item = QListWidgetItem(QIcon(_to_pixmap(thumb)), f"쌍 {len(self._pairs)}")
        self.pair_list.addItem(item)
        self._update_status()

    def _update_status(self) -> None:
        count = len(self._pairs)
        hint = f"최소 {MIN_PAIRS}, 권장 {RECOMMENDED_PAIRS}+" if count < RECOMMENDED_PAIRS else "실행 가능"
        self.status_label.setText(f"체스보드 쌍 {count}개 — {hint}")
        self.solve_button.setEnabled(count >= MIN_PAIRS and not self._solving)

    def _delete_selected(self) -> None:
        row = self.pair_list.currentRow()
        if row < 0:
            return
        self.pair_list.takeItem(row)
        del self._pairs[row]
        for i in range(self.pair_list.count()):
            self.pair_list.item(i).setText(f"쌍 {i + 1}")
        if not self._pairs:
            self._image_size = None
        self._update_status()

    def _clear_pairs(self) -> None:
        self.pair_list.clear()
        self._pairs.clear()
        self._image_size = None
        self._update_status()

    # ── 계산 ─────────────────────────────────────────────────

    def _run_solve(self) -> None:
        if self._solving or self._image_size is None:
            return
        self._solving = True
        self.solve_button.setEnabled(False)
        self.solve_button.setText("계산 중...")
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
        self.solve_button.setText("캘리브레이션 실행")
        self._update_status()
        if calib is None:
            self.result_label.setText(f"실패: {error}")
            self.log.emit(f"[ERROR] 캘리브레이션 실패: {error}")
            return
        design = f" (설계값 {self._design_baseline:.2f})" if self._design_baseline > 0 else ""
        self.result_label.setText(
            f"RMS: stereo {calib.rms_stereo:.3f} (L {calib.rms_left:.3f} / R {calib.rms_right:.3f})\n"
            f"baseline: {calib.baseline_mm:.2f} mm{design}\n"
            f"fx L/R: {calib.K1[0, 0]:.1f} / {calib.K2[0, 0]:.1f} px\n"
            f"저장: {CALIBRATION_DIR.as_posix()}/ (npz + json)"
        )
        self.log.emit(
            f"캘리브레이션 완료 — RMS {calib.rms_stereo:.3f}, baseline {calib.baseline_mm:.2f} mm, "
            f"쌍 {len(self._pairs)}개"
        )
        self.calibrated.emit(calib)


class CalibrationTab(QWidget):
    """Container: 수집·실행 / 정렬 검증 / 뎁스 sub-tabs behind one main tab.

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

        self.sub_tabs = QTabWidget(objectName="SubTabs")
        self.sub_tabs.addTab(self.capture, "수집·실행")
        self.sub_tabs.addTab(self.verify, "정렬 검증")
        self.sub_tabs.addTab(self.depth, "뎁스")
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
        return self.sub_tabs.currentWidget() in (self.verify, self.depth)

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
        if widget is self.verify:
            self.verify.on_preview_frame(frame)
        elif widget is self.depth:
            self.depth.on_preview_frame(frame)
