"""Live tab side panel: view, capture, and device tool groups.

Widget construction only — the main window and MediaController connect signals
and own all behavior. Every interactive widget is exposed as an attribute.
Each group is a titled card so the column reads as three separated sections
with aligned label/control rows instead of loose widgets of varying width."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .cards import SectionCard

BACKEND_MODES = ["Auto", "FFmpeg", "MSMF", "DSHOW"]
VIEW_MODES = [("Combined SBS", "sbs"), ("Left only", "left"), ("Right only", "right"), ("Anaglyph 3D", "anaglyph")]
RECORD_FORMATS = [("Single SBS file", False), ("Split L / R", True)]
TIMELAPSE_INTERVALS = [1, 2, 5, 10, 30, 60]

PANEL_WIDTH = 272


class SidePanel(QScrollArea):
    """Grouped tool column right of the video: View / Capture / Device."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="SidePanel")
        self.setFixedWidth(PANEL_WIDTH)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget(objectName="SidePanelBody")
        self._column = QVBoxLayout(body)
        self._column.setContentsMargins(14, 12, 14, 14)
        self._column.setSpacing(12)
        self._build_view_group()
        self._build_capture_group()
        self._build_device_group()
        self._column.addStretch(1)
        self.setWidget(body)

    # ── View ─────────────────────────────────────────────────

    def _build_view_group(self) -> None:
        card = SectionCard("View", "Display mode & alignment check")

        self.view_combo = QComboBox()
        for label, mode in VIEW_MODES:
            self.view_combo.addItem(label, mode)
        self.view_combo.setToolTip("Display-only view mode — not applied to snapshots/recording")
        card.add_row("Mode", self.view_combo)

        self.rotation_combo = QComboBox()
        for degrees in (0, 90, 180, 270):
            self.rotation_combo.addItem(f"{degrees}°", degrees)
        self.rotation_combo.setToolTip("Per-eye rotation — also applied to snapshots/recording")
        card.add_row("Rotate", self.rotation_combo)

        self.swap_button = QPushButton("Swap L/R", objectName="SwapButton")
        self.swap_button.setCheckable(True)
        self.swap_button.setToolTip("Swap the left/right eyes (also applied to snapshots/recording)")

        self.exposure_button = QPushButton("Exposure", objectName="ExposureButton")
        self.exposure_button.setCheckable(True)
        self.exposure_button.setToolTip("Histogram + clipping overlay (highlights red, shadows blue)")

        self.rectify_button = QPushButton("Rectify", objectName="RectifyButton")
        self.rectify_button.setCheckable(True)
        self.rectify_button.setEnabled(False)
        self.rectify_button.setToolTip("Run calibration in the Calibration tab first")

        self.guide_button = QPushButton("Guides", objectName="GuideButton")
        self.guide_button.setCheckable(True)
        self.guide_button.setToolTip(
            "Horizontal overlay — check left/right features land on the same line after rectify (display only)"
        )
        card.add_grid(
            (self.swap_button, self.exposure_button, self.rectify_button, self.guide_button)
        )
        self._column.addWidget(card)

    # ── Capture ──────────────────────────────────────────────

    def _build_capture_group(self) -> None:
        card = SectionCard("Capture", "Snapshot · Record · Timelapse")

        self.snapshot_button = QPushButton("Snapshot", objectName="SnapshotButton")
        self.snapshot_button.setEnabled(False)
        self.snapshot_button.setToolTip("Save a full-resolution left/right PNG")
        card.add_full(self.snapshot_button)

        self.record_format_combo = QComboBox()
        for label, split in RECORD_FORMATS:
            self.record_format_combo.addItem(label, split)
        self.record_format_combo.setToolTip("Recording file layout — switching starts a new segment")
        card.add_row("Format", self.record_format_combo)

        self.record_button = QPushButton("Record", objectName="RecordButton")
        self.record_button.setCheckable(True)
        self.record_button.setEnabled(False)
        self.record_button.setToolTip("MP4 recording (swap/rotate/rectify applied, view mode not applied)")
        card.add_full(self.record_button)

        self.timelapse_interval_combo = QComboBox()
        for seconds in TIMELAPSE_INTERVALS:
            self.timelapse_interval_combo.addItem(f"{seconds}s", seconds)
        self.timelapse_interval_combo.setToolTip("Timelapse capture interval")
        card.add_row("Every", self.timelapse_interval_combo)

        self.timelapse_button = QPushButton("Timelapse", objectName="TimelapseButton")
        self.timelapse_button.setCheckable(True)
        self.timelapse_button.setEnabled(False)
        self.timelapse_button.setToolTip("Auto-save snapshots at the interval (per-session subfolder)")
        card.add_full(self.timelapse_button)

        self.folder_button = QPushButton("Open Folder")
        self.folder_button.setToolTip("Open the snapshot/recording folder in the file explorer")
        card.add_full(self.folder_button)
        self._column.addWidget(card)

    # ── Device ───────────────────────────────────────────────

    def _build_device_group(self) -> None:
        card = SectionCard("Device", "Backend & driver properties")

        self.backend_combo = QComboBox()
        self.backend_combo.addItems(BACKEND_MODES)
        self.backend_combo.setToolTip("Capture backend — changing while streaming auto-restarts")
        card.add_row("Backend", self.backend_combo)

        self.settings_button = QPushButton("Camera Settings")
        self.settings_button.setToolTip(
            "Open the driver property window — brightness/exposure/contrast, live (watch the preview behind)"
        )
        card.add_full(self.settings_button)
        self._column.addWidget(card)
