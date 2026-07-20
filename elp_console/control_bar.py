"""App chrome: header bar (brand + main nav + stream lifecycle), live-tab stream
setup bar, and status row.

Widget construction only — the main window connects signals and owns all
behavior. Every interactive widget is exposed as an attribute. View/capture
tools live in side_panel.py."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from .profiles import CameraProfile
from .segmented import SegmentedControl

STREAM_STATES = {
    "idle": ("Idle", None),
    "opening": ("Opening…", "warn"),
    "streaming": ("Streaming", "ok"),
    "error": ("Error", "bad"),
}

NAV_LABELS = ["Live", "Calibration", "Library"]


class HeaderBar(QWidget):
    """App-wide header: brand, main navigation, stream state, start/stop.

    Navigation and the stream lifecycle live here so every page (live,
    calibration, library) shares one top bar — no second tab row below it."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="Header")
        self.setFixedHeight(56)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(16)

        row.addWidget(QLabel("ELP Stereo", objectName="TitleLabel"))
        # Keep the global navigation compact: the tab itself is the target,
        # rather than a second large container around all three labels.
        self.nav = SegmentedControl(NAV_LABELS, object_name="HeaderNav")
        row.addWidget(self.nav)
        row.addStretch(1)

        self.profile_chip = QLabel("", objectName="HeaderChip")
        self.profile_chip.setFixedHeight(36)
        row.addWidget(self.profile_chip)

        self.stream_chip = _chip("Idle")
        self.stream_chip.setFixedHeight(36)
        row.addWidget(self.stream_chip)

        self.start_button = QPushButton("Start", objectName="StartButton")
        row.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop", objectName="StopButton")
        self.stop_button.setEnabled(False)
        row.addWidget(self.stop_button)

    def set_stream_state(self, state: str) -> None:
        text, chip_state = STREAM_STATES.get(state, STREAM_STATES["idle"])
        self.stream_chip.setText(text)
        _set_chip_state(self.stream_chip, chip_state)


class ControlBar(QWidget):
    """Stream setup only: profile, device, mode."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="ControlBar")
        self.setFixedHeight(56)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 10, 20, 10)
        row.setSpacing(8)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(150)
        self.profile_combo.setToolTip("Camera profile — defines the mode list and design baseline")
        row.addWidget(self.profile_combo)

        self.profile_button = QPushButton("Manage")
        self.profile_button.setToolTip("Add / duplicate / edit / delete profiles")
        row.addWidget(self.profile_button)

        row.addSpacing(8)
        row.addWidget(QLabel("Device"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(170)
        row.addWidget(self.device_combo)

        self.refresh_button = QPushButton("⟳", objectName="RefreshButton")
        self.refresh_button.setToolTip("Refresh the device list")
        row.addWidget(self.refresh_button)

        row.addSpacing(8)
        row.addWidget(QLabel("Mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(210)
        self.mode_combo.setToolTip("Combined SBS resolution @ requested fps — set by the profile")
        row.addWidget(self.mode_combo)

        row.addStretch(1)

    # ── combo fill (display only — signals blocked) ──────────

    def set_profiles(self, profiles: list[CameraProfile], selected_name: str = "") -> None:
        combo = self.profile_combo
        combo.blockSignals(True)
        combo.clear()
        for profile in profiles:
            combo.addItem(profile.name, profile)
        index = combo.findText(selected_name)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def set_modes(self, profile: CameraProfile) -> None:
        """Repopulate the mode combo; keeps the current mode when still offered."""
        combo = self.mode_combo
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for mode in profile.modes:
            width, height, fps = mode
            combo.addItem(f"{width}×{height} @{fps}  (per eye {width // 2}×{height})", mode)
        if current is not None:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)


def _chip(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("chip", "true")
    return label


def _set_chip_state(chip: QLabel, state: str | None) -> None:
    chip.setProperty("state", state)
    chip.style().unpolish(chip)
    chip.style().polish(chip)


class StatusRow(QWidget):
    """Chip strip below the video: negotiated format, live stats, flash notice."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="StatusRow")
        self.setFixedHeight(40)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(0)

        self.format_chip = _chip("Format —")
        self.size_chip = _chip("Size —")
        self.fps_chip = _chip("FPS —")
        self.mean_chip = _chip("Mean —")
        self.drop_chip = _chip("Drop —")
        self._chips = (self.format_chip, self.size_chip, self.fps_chip, self.mean_chip, self.drop_chip)
        for chip in self._chips:
            row.addWidget(chip)

        row.addStretch(1)
        self.flash_label = QLabel("", objectName="FlashLabel")
        row.addWidget(self.flash_label)

        self.log_toggle = QPushButton("Log", objectName="LogToggle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
        self.log_toggle.setToolTip("Show / hide the log panel")
        row.addWidget(self.log_toggle)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.flash_label.setText(""))

    def update_opened(self, info: dict) -> None:
        self.format_chip.setText(f"Format {info['fourcc']}")
        _set_chip_state(self.format_chip, "ok" if info["fourcc"] in ("MJPG", "RAW") else "bad")
        self.size_chip.setText(f"Size {info['width']}×{info['height']}")

    def update_stats(self, stats: dict) -> None:
        self.fps_chip.setText(f"{stats['fps']:.1f} fps")
        mean = stats["mean"]
        self.mean_chip.setText(f"Mean {mean:.0f}")
        _set_chip_state(self.mean_chip, "bad" if mean < 1 else None)
        if mean < 1:
            _set_chip_state(self.format_chip, "bad")

        drop_rate = stats.get("drop_rate")
        if drop_rate is None:
            self.drop_chip.setText("Drop —")
            _set_chip_state(self.drop_chip, None)
        else:
            self.drop_chip.setText(f"Drop {drop_rate:.0f}%")
            _set_chip_state(self.drop_chip, "bad" if drop_rate > 40 else "warn" if drop_rate > 10 else "ok")

    def reset(self) -> None:
        for chip, text in zip(self._chips, ("Format —", "Size —", "FPS —", "Mean —", "Drop —")):
            chip.setText(text)
            _set_chip_state(chip, None)

    def flash(self, message: str) -> None:
        self.flash_label.setText(message)
        self._flash_timer.start(3000)
