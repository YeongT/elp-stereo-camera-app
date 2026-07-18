"""Main window: coordinates the capture worker, tabs, and per-tab widgets.

Widget construction lives in control_bar.py / side_panel.py / calibration_tab.py
/ library.py;
this module owns behavior — stream lifecycle, profile handling, and the
calibration wiring. Snapshot/recording/timelapse live in media_controller.py."""

import time
from pathlib import Path

from PySide6.QtCore import QSettings, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .calibration import load_latest, rectify_maps
from .calibration_tab import CalibrationTab
from .paths import CALIBRATION_DIR
from .camera import CaptureWorker
from .camera_settings import open_camera_settings
from .control_bar import ControlBar, HeaderBar, StatusRow
from .devices import list_devices
from .library import LibraryView
from .media_controller import MediaController
from .profile_dialog import ProfileDialog
from .profiles import load_profiles, save_user_profiles
from .side_panel import SidePanel
from .widgets import STATE_ERROR, STATE_IDLE, STATE_OPENING, VideoView


class MainWindow(QMainWindow):
    settings_log = Signal(str)  # thread-safe log entry point for helper threads

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ELP Stereo Camera App")
        self.resize(1500, 960)
        self.setMinimumSize(1180, 760)

        self._worker: CaptureWorker | None = None
        self._pending_restart = False
        self._streaming = False
        self._settings = QSettings("elp-viewer", "elp-viewer")
        self._rectify = None  # remap tables from the loaded calibration
        self._profiles = load_profiles()

        self._build_ui()
        self._connect_controls()
        self.settings_log.connect(self._append_log)
        self.controls.set_profiles(self._profiles, str(self._settings.value("profile", "")))
        self._apply_profile()
        self._refresh_devices()
        self._append_log("프로필·장치·모드를 선택한 뒤 시작을 누르세요.")
        self._append_log(f"저장 폴더: {Path(self.media.output_dir).absolute()}")
        self._load_calibration()

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        live = QWidget(objectName="Root")
        layout = QVBoxLayout(live)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.controls = ControlBar()
        layout.addWidget(self.controls)

        self.panel = SidePanel()
        self.media = MediaController(
            self.panel, self._settings, lambda: self._worker, self._append_log, self
        )

        self.video = VideoView()
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.video, stretch=1)
        content.addWidget(self.panel)
        layout.addLayout(content, stretch=1)

        self.status = StatusRow()
        layout.addWidget(self.status)

        self.log_panel = QPlainTextEdit(objectName="LogPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setFixedHeight(126)
        self.log_panel.setMaximumBlockCount(500)
        layout.addWidget(self.log_panel)

        show_log = self._settings.value("show_log", True, bool)
        self.status.log_toggle.setChecked(show_log)
        self.log_panel.setVisible(show_log)

        self.calibration_tab = CalibrationTab()
        self.library = LibraryView(get_directory=lambda: self.media.output_dir, log=self._append_log)

        self.tabs = QTabWidget(objectName="MainTabs")
        self.tabs.addTab(live, "라이브")
        self.tabs.addTab(self.calibration_tab, "캘리브레이션")
        self.tabs.addTab(self.library, "라이브러리")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.header = HeaderBar()

        root = QWidget(objectName="Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(root)

    def _connect_controls(self) -> None:
        c = self.controls
        c.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        c.profile_button.clicked.connect(self._open_profile_dialog)
        c.refresh_button.clicked.connect(self._refresh_devices)
        self.header.start_button.clicked.connect(self._start_stream)
        self.header.stop_button.clicked.connect(self._stop_stream)

        p = self.panel
        p.settings_button.clicked.connect(self._open_camera_settings)
        p.view_combo.currentIndexChanged.connect(self._on_view_changed)
        p.rotation_combo.currentIndexChanged.connect(self._on_transform_changed)
        p.swap_button.toggled.connect(self._on_transform_changed)
        p.exposure_button.toggled.connect(self._on_exposure_toggled)
        p.rectify_button.toggled.connect(self._on_rectify_toggled)
        p.guide_button.toggled.connect(self.video.set_guides)
        for combo in (c.device_combo, c.mode_combo, p.backend_combo):
            combo.currentIndexChanged.connect(self._on_settings_changed)

        self.status.log_toggle.toggled.connect(self._on_log_toggled)

        self.calibration_tab.request_frame.connect(self._on_calib_frame_request)
        self.calibration_tab.calibrated.connect(self._on_calibrated)
        self.calibration_tab.log.connect(self._append_log)
        self.calibration_tab.preview_needed.connect(self._update_preview_tap)

    # ── 장치/스트림 제어 ─────────────────────────────────────

    def _refresh_devices(self) -> None:
        names = list_devices()
        combo = self.controls.device_combo
        combo.blockSignals(True)
        combo.clear()
        for i, name in enumerate(names):
            combo.addItem(f"[{i}] {name}", (i, name))
        combo.blockSignals(False)
        self._append_log(f"장치 {len(names)}개 감지: " + ", ".join(names))

    def _start_stream(self) -> None:
        if self._worker is not None:
            self._pending_restart = True
            self._worker.stop()
            return

        c = self.controls
        device_data = c.device_combo.currentData()
        if device_data is None:
            self._append_log("[ERROR] 선택된 장치가 없습니다.")
            return
        index, device_name = device_data
        mode = c.mode_combo.currentData()
        if mode is None:
            self._append_log("[ERROR] 선택된 모드가 없습니다 — 프로필을 확인하세요.")
            return
        width, height, fps = mode

        self.video.set_state(STATE_OPENING)
        self.header.start_button.setEnabled(False)
        self.header.stop_button.setEnabled(True)
        self.header.set_stream_state("opening")

        p = self.panel
        self._worker = CaptureWorker(
            device_name, index, width, height, fps, p.backend_combo.currentText()
        )
        self._worker.set_transform(p.swap_button.isChecked(), p.rotation_combo.currentData())
        self._worker.set_view_mode(p.view_combo.currentData())
        self._worker.set_exposure_check(p.exposure_button.isChecked())
        if p.rectify_button.isChecked() and self._rectify is not None:
            self._worker.set_rectification(self._rectify)
        self._worker.log.connect(self._append_log)
        self._worker.opened.connect(self._on_opened)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.frame_captured.connect(self.calibration_tab.on_frame)
        self._worker.preview_frame.connect(self.calibration_tab.on_preview_frame)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_capture_finished)
        self._update_preview_tap()
        self._worker.start()

    def _stop_stream(self) -> None:
        if self._worker is not None:
            self._pending_restart = False
            self._worker.stop()
            self.header.stop_button.setEnabled(False)

    @Slot()
    def _on_view_changed(self) -> None:
        if self._worker is not None:
            self._worker.set_view_mode(self.panel.view_combo.currentData())

    @Slot(bool)
    def _on_exposure_toggled(self, checked: bool) -> None:
        if self._worker is not None:
            self._worker.set_exposure_check(checked)

    @Slot()
    def _on_transform_changed(self) -> None:
        if self._worker is not None:
            self._worker.set_transform(
                self.panel.swap_button.isChecked(), self.panel.rotation_combo.currentData()
            )

    @Slot()
    def _on_settings_changed(self) -> None:
        if self._worker is not None:
            self._append_log("설정 변경 — 스트림 재시작")
            self._pending_restart = True
            self._worker.stop()

    # ── 프로필 ───────────────────────────────────────────────

    @Slot()
    def _on_profile_changed(self) -> None:
        self._apply_profile()
        if self._worker is not None:
            self._append_log("프로필 변경 — 스트림 재시작")
            self._pending_restart = True
            self._worker.stop()

    def _apply_profile(self) -> None:
        profile = self.controls.profile_combo.currentData()
        if profile is None:
            return
        self.controls.set_modes(profile)
        self.header.profile_chip.setText(profile.name)
        self.calibration_tab.set_design_baseline(profile.baseline_mm)
        self._settings.setValue("profile", profile.name)

    def _open_profile_dialog(self) -> None:
        dialog = ProfileDialog(self._profiles, self)
        if not dialog.exec():
            return
        self._profiles = dialog.profiles()
        save_user_profiles(self._profiles)
        selected = self.controls.profile_combo.currentText()
        self.controls.set_profiles(self._profiles, selected)
        self._apply_profile()
        self._append_log(f"프로필 저장 — {len(self._profiles)}개")

    # ── 캘리브레이션 ─────────────────────────────────────────

    def _load_calibration(self) -> None:
        calib = load_latest(CALIBRATION_DIR)
        if calib is None:
            return
        self._apply_calibration(calib)
        self.calibration_tab.set_calibration(calib)
        self._append_log(
            f"저장된 캘리브레이션 로드 — baseline {calib.baseline_mm:.2f} mm, "
            f"RMS {calib.rms_stereo:.3f} ({calib.created})"
        )

    @Slot(object)
    def _on_calibrated(self, calib) -> None:
        self._apply_calibration(calib)
        if self._worker is not None and self.panel.rectify_button.isChecked():
            self._worker.set_rectification(self._rectify)

    def _apply_calibration(self, calib) -> None:
        self._rectify = rectify_maps(calib)
        button = self.panel.rectify_button
        button.setEnabled(True)
        button.setToolTip(
            f"렉티피케이션 적용 — baseline {calib.baseline_mm:.2f} mm, "
            f"눈당 {calib.image_size[0]}×{calib.image_size[1]}, {calib.created}"
        )

    @Slot()
    def _on_calib_frame_request(self) -> None:
        if self._worker is None:
            self.calibration_tab.status_label.setText("스트림이 없습니다 — 헤더의 시작을 누르세요.")
            return
        self._worker.request_frame()

    @Slot(bool)
    def _on_rectify_toggled(self, checked: bool) -> None:
        if self._worker is not None:
            self._worker.set_rectification(self._rectify if checked else None)
        self._append_log("정렬 보정 켜짐 — 스냅샷·녹화에도 적용됩니다." if checked else "정렬 보정 꺼짐")

    # ── 탭/카메라 설정 ───────────────────────────────────────

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.library:
            self.library.refresh()
        else:
            self.library.pause()
        self._update_preview_tap()

    @Slot()
    def _update_preview_tap(self) -> None:
        """Feed raw frames to the calibration sub-tabs only while one is visible."""
        if self._worker is None:
            return
        wanted = (
            self.tabs.currentWidget() is self.calibration_tab
            and self.calibration_tab.wants_preview()
        )
        self._worker.set_preview_tap(wanted)

    @Slot(bool)
    def _on_log_toggled(self, checked: bool) -> None:
        self.log_panel.setVisible(checked)
        self._settings.setValue("show_log", checked)

    def _open_camera_settings(self) -> None:
        device_data = self.controls.device_combo.currentData()
        if device_data is None:
            self._append_log("[ERROR] 선택된 장치가 없습니다.")
            return
        index, _ = device_data
        self._append_log("카메라 설정 창 열기 — 변경 사항은 스트림에 즉시 반영됩니다.")
        open_camera_settings(index, self.settings_log.emit)

    # ── worker 신호 처리 ─────────────────────────────────────

    @Slot(dict)
    def _on_opened(self, info: dict) -> None:
        self.status.update_opened(info)

    @Slot(object, dict)
    def _on_frame(self, frame, stats: dict) -> None:
        if not self._streaming:
            self._streaming = True
            self.media.on_streaming_started()
            self.calibration_tab.set_streaming(True)
            self.header.set_stream_state("streaming")

        height, width = frame.shape[:2]
        image = QImage(frame.data, width, height, frame.strides[0], QImage.Format.Format_BGR888)
        self.video.set_frame(
            QPixmap.fromImage(image),
            view_mode=stats.get("view_mode", "sbs"),
            hist=stats.get("hist"),
            clip=stats.get("clip"),
        )
        self.status.update_stats(stats)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.video.set_state(STATE_ERROR, message)
        self.status.reset()
        self.header.set_stream_state("error")
        self._append_log(f"[ERROR] {message}")

    @Slot()
    def _on_capture_finished(self) -> None:
        worker = self._worker
        self._worker = None
        self._streaming = False
        if worker is not None:
            worker.deleteLater()

        self.media.on_stream_stopped()
        self.calibration_tab.set_streaming(False)
        self.header.stop_button.setEnabled(False)
        self.header.start_button.setEnabled(True)

        if self._pending_restart:
            self._pending_restart = False
            self._start_stream()
            return

        if self.video._state not in (STATE_ERROR,):  # noqa: SLF001 — own widget state
            self.video.set_state(STATE_IDLE)
            self.status.reset()
            self.header.set_stream_state("idle")
            self._append_log("스트림 정지")

    # ── 로그/알림 ────────────────────────────────────────────

    def _append_log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_panel.appendPlainText(f"[{stamp}] {message}")
        if message.startswith("스냅샷 저장"):
            self.status.flash(message)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)
