"""Media output controller: snapshot, recording, timelapse, and output folder.

Owns the capture-output domain extracted from MainWindow — button/combo signal
wiring, QSettings persistence of the output directory, and the timelapse timer."""

import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QFileDialog

from .paths import CAPTURES_DIR

DEFAULT_OUTPUT_DIR = str(CAPTURES_DIR)


class MediaController(QObject):
    """스냅샷·녹화·타임랩스·저장 폴더를 담당하는 컨트롤러."""

    def __init__(self, panel, settings, get_worker, log, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._settings = settings
        self._get_worker = get_worker
        self._log = log
        saved_output_dir = settings.value("output_dir")
        # Migrate the old project-root default without overriding a folder the
        # user deliberately selected.
        self._output_dir = (
            DEFAULT_OUTPUT_DIR if saved_output_dir in (None, "captures") else str(saved_output_dir)
        )
        self._timelapse_dir: str | None = None
        self._timelapse_timer = QTimer(self)
        self._timelapse_timer.timeout.connect(self._timelapse_shot)

        c = panel
        c.folder_button.clicked.connect(self._choose_output_dir)
        c.timelapse_interval_combo.currentIndexChanged.connect(self._on_timelapse_interval_changed)
        c.timelapse_button.toggled.connect(self._toggle_timelapse)
        c.snapshot_button.clicked.connect(self._take_snapshot)
        c.record_format_combo.currentIndexChanged.connect(self._on_record_format_changed)
        c.record_button.toggled.connect(self._toggle_recording)
        self._update_folder_tooltip()

    # ── 공개 표면 ────────────────────────────────────────────

    @property
    def output_dir(self) -> str:
        return self._output_dir

    def on_streaming_started(self) -> None:
        for button in (
            self._panel.snapshot_button,
            self._panel.record_button,
            self._panel.timelapse_button,
        ):
            button.setEnabled(True)

    def on_stream_stopped(self) -> None:
        c = self._panel
        c.snapshot_button.setEnabled(False)
        for button in (c.record_button, c.timelapse_button):
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
            button.setEnabled(False)
        self._timelapse_timer.stop()
        self._timelapse_dir = None

    # ── 스냅샷/녹화 ──────────────────────────────────────────

    def _take_snapshot(self) -> None:
        worker = self._get_worker()
        if worker is not None:
            worker.request_snapshot(self._output_dir)

    @Slot(bool)
    def _toggle_recording(self, checked: bool) -> None:
        worker = self._get_worker()
        if worker is None:
            return
        if checked:
            worker.start_recording(self._output_dir, self._panel.record_format_combo.currentData())
        else:
            worker.stop_recording()

    @Slot()
    def _on_record_format_changed(self) -> None:
        worker = self._get_worker()
        if worker is not None and self._panel.record_button.isChecked():
            worker.start_recording(self._output_dir, self._panel.record_format_combo.currentData())

    # ── 타임랩스 ─────────────────────────────────────────────

    @Slot(bool)
    def _toggle_timelapse(self, checked: bool) -> None:
        if not checked:
            self._timelapse_timer.stop()
            if self._timelapse_dir is not None:
                self._log("Timelapse stopped")
                self._timelapse_dir = None
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._timelapse_dir = str(Path(self._output_dir) / f"timelapse_{stamp}")
        interval = self._panel.timelapse_interval_combo.currentData()
        self._log(f"Timelapse started — {interval}s interval, {self._timelapse_dir}")
        self._timelapse_timer.start(interval * 1000)
        self._timelapse_shot()

    @Slot()
    def _timelapse_shot(self) -> None:
        worker = self._get_worker()
        if worker is not None and self._timelapse_dir is not None:
            worker.request_snapshot(self._timelapse_dir)

    @Slot()
    def _on_timelapse_interval_changed(self) -> None:
        if self._timelapse_timer.isActive():
            self._timelapse_timer.setInterval(self._panel.timelapse_interval_combo.currentData() * 1000)

    # ── 저장 폴더 ────────────────────────────────────────────

    def _choose_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self._panel.window(), "Select save folder", self._output_dir)
        if not chosen:
            return
        self._output_dir = chosen
        self._settings.setValue("output_dir", chosen)
        self._update_folder_tooltip()
        self._log(f"Save folder: {chosen}")
        worker = self._get_worker()
        if worker is not None and self._panel.record_button.isChecked():
            # 다음 세그먼트부터 새 폴더
            worker.start_recording(chosen, self._panel.record_format_combo.currentData())

    def _update_folder_tooltip(self) -> None:
        self._panel.folder_button.setToolTip(f"Snapshot/recording save location: {Path(self._output_dir).absolute()}")
