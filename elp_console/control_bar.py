"""App chrome: header bar, live tab stream bar, and status row.

Widget construction only — the main window connects signals and owns all
behavior. Every interactive widget is exposed as an attribute. View/capture
tools live in side_panel.py."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from .profiles import CameraProfile

STREAM_STATES = {
    "idle": ("대기", None),
    "opening": ("여는 중...", "warn"),
    "streaming": ("스트리밍", "ok"),
    "error": ("오류", "bad"),
}


class HeaderBar(QWidget):
    """App-wide header: title, profile chip, stream state, start/stop.

    Stream lifecycle lives here so every tab (live, calibration, library) can
    start or stop the stream without switching back to the live tab."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="Header")
        self.setFixedHeight(50)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(10)

        row.addWidget(QLabel("ELP Stereo Camera App", objectName="TitleLabel"))
        self.profile_chip = QLabel("", objectName="HeaderChip")
        row.addWidget(self.profile_chip)
        row.addStretch(1)

        self.stream_chip = _chip("대기")
        row.addWidget(self.stream_chip)

        self.start_button = QPushButton("시작", objectName="StartButton")
        row.addWidget(self.start_button)

        self.stop_button = QPushButton("정지", objectName="StopButton")
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
        self.setFixedHeight(52)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(8)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(150)
        self.profile_combo.setToolTip("카메라 프로필 — 모드 목록·baseline 설계값을 결정")
        row.addWidget(self.profile_combo)

        self.profile_button = QPushButton("관리")
        self.profile_button.setToolTip("프로필 추가·복제·편집·삭제")
        row.addWidget(self.profile_button)

        row.addSpacing(10)
        row.addWidget(QLabel("장치"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(170)
        row.addWidget(self.device_combo)

        self.refresh_button = QPushButton("⟳", objectName="RefreshButton")
        self.refresh_button.setToolTip("장치 목록 새로 고침")
        row.addWidget(self.refresh_button)

        row.addSpacing(10)
        row.addWidget(QLabel("모드"))
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(210)
        self.mode_combo.setToolTip("SBS 합성 해상도 @ 요청 fps — 프로필이 정의")
        row.addWidget(self.mode_combo)

        row.addStretch(1)

    # ── 콤보 채우기 (표시 로직만 — 시그널은 차단) ────────────

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
            combo.addItem(f"{width}×{height} @{fps}  (카메라당 {width // 2}×{height})", mode)
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
        self.setFixedHeight(38)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(8)

        self.format_chip = _chip("형식 —")
        self.size_chip = _chip("해상도 —")
        self.fps_chip = _chip("측정 fps —")
        self.mean_chip = _chip("밝기 —")
        self.drop_chip = _chip("드롭 —")
        self._chips = (self.format_chip, self.size_chip, self.fps_chip, self.mean_chip, self.drop_chip)
        for chip in self._chips:
            row.addWidget(chip)

        row.addStretch(1)
        self.flash_label = QLabel("", objectName="FlashLabel")
        row.addWidget(self.flash_label)

        self.log_toggle = QPushButton("로그", objectName="LogToggle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
        self.log_toggle.setToolTip("로그 패널 표시/숨기기")
        row.addWidget(self.log_toggle)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.flash_label.setText(""))

    def update_opened(self, info: dict) -> None:
        self.format_chip.setText(f"형식 {info['fourcc']}")
        _set_chip_state(self.format_chip, "ok" if info["fourcc"] in ("MJPG", "RAW") else "bad")
        self.size_chip.setText(f"해상도 {info['width']}×{info['height']}")

    def update_stats(self, stats: dict) -> None:
        self.fps_chip.setText(f"측정 {stats['fps']:.1f} fps")
        mean = stats["mean"]
        self.mean_chip.setText(f"밝기 {mean:.0f}")
        _set_chip_state(self.mean_chip, "bad" if mean < 1 else None)
        if mean < 1:
            _set_chip_state(self.format_chip, "bad")

        drop_rate = stats.get("drop_rate")
        if drop_rate is None:
            self.drop_chip.setText("드롭 —")
            _set_chip_state(self.drop_chip, None)
        else:
            self.drop_chip.setText(f"드롭 {drop_rate:.0f}%")
            _set_chip_state(self.drop_chip, "bad" if drop_rate > 40 else "warn" if drop_rate > 10 else "ok")

    def reset(self) -> None:
        for chip, text in zip(self._chips, ("형식 —", "해상도 —", "측정 fps —", "밝기 —", "드롭 —")):
            chip.setText(text)
            _set_chip_state(chip, None)

    def flash(self, message: str) -> None:
        self.flash_label.setText(message)
        self._flash_timer.start(3000)
