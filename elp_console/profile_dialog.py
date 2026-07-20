"""Profile manager dialog: add / duplicate / edit / delete camera profiles.

Built-in profiles are read-only (duplicate them to customize); user profiles
persist to profiles.json via profiles.save_user_profiles."""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .profiles import CameraProfile, format_mode, parse_mode


class ProfileDialog(QDialog):
    """Edits a working copy; ``profiles()`` returns the result after accept."""

    def __init__(self, profiles: list[CameraProfile], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera Profiles")
        self.resize(720, 500)
        self.setMinimumSize(680, 460)
        self._profiles = list(profiles)
        self._current = -1
        self._build_ui()
        self._reload_list(select=0)

    def profiles(self) -> list[CameraProfile]:
        return list(self._profiles)

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        side = QVBoxLayout()
        side.setSpacing(10)
        self.profile_list = QListWidget(objectName="FileList")
        self.profile_list.currentRowChanged.connect(self._on_selected)
        side.addWidget(self.profile_list, stretch=1)
        row = QHBoxLayout()
        row.setSpacing(8)
        add_button = QPushButton("New")
        add_button.clicked.connect(self._add_profile)
        row.addWidget(add_button)
        clone_button = QPushButton("Duplicate")
        clone_button.clicked.connect(self._clone_profile)
        row.addWidget(clone_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_profile)
        row.addWidget(self.delete_button)
        side.addLayout(row)
        layout.addLayout(side, stretch=1)

        form = QVBoxLayout()
        form.setSpacing(8)
        form.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit()
        form.addWidget(self.name_edit)

        spec_row = QHBoxLayout()
        spec_row.setSpacing(8)
        spec_row.addWidget(QLabel("baseline(mm)"))
        self.baseline_spin = QDoubleSpinBox()
        self.baseline_spin.setRange(0.0, 1000.0)
        self.baseline_spin.setDecimals(2)
        self.baseline_spin.setToolTip("Design distance between lens centers — 0 if unknown. Shown against the calibration result")
        spec_row.addWidget(self.baseline_spin)
        spec_row.addWidget(QLabel("HFOV(°)"))
        self.hfov_spin = QDoubleSpinBox()
        self.hfov_spin.setRange(0.0, 360.0)
        self.hfov_spin.setDecimals(1)
        spec_row.addWidget(self.hfov_spin)
        spec_row.addStretch(1)
        form.addLayout(spec_row)

        form.addWidget(QLabel("Modes — one per line, combined SBS resolution (e.g. 3200x1200@60)"))
        self.modes_edit = QPlainTextEdit()
        self.modes_edit.setTabChangesFocus(True)
        form.addWidget(self.modes_edit, stretch=1)

        form.addWidget(QLabel("Notes"))
        self.notes_edit = QLineEdit()
        form.addWidget(self.notes_edit)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #f4606e; font-size: 11px;")
        form.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.apply_button = QPushButton("Save")
        self.apply_button.clicked.connect(self._apply_edits)
        buttons.addWidget(self.apply_button)
        close_button = QPushButton("Close", objectName="StartButton")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        form.addLayout(buttons)

        layout.addLayout(form, stretch=2)

    # ── 목록/선택 ────────────────────────────────────────────

    def _reload_list(self, select: int) -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in self._profiles:
            suffix = "  (built-in)" if profile.builtin else ""
            self.profile_list.addItem(QListWidgetItem(profile.name + suffix))
        self.profile_list.blockSignals(False)
        select = max(0, min(select, len(self._profiles) - 1))
        self.profile_list.setCurrentRow(select)

    @Slot(int)
    def _on_selected(self, row: int) -> None:
        self._current = row
        if row < 0 or row >= len(self._profiles):
            return
        profile = self._profiles[row]
        self.name_edit.setText(profile.name)
        self.baseline_spin.setValue(profile.baseline_mm)
        self.hfov_spin.setValue(profile.hfov_deg)
        self.modes_edit.setPlainText("\n".join(format_mode(m) for m in profile.modes))
        self.notes_edit.setText(profile.notes)
        self.notes_edit.setCursorPosition(0)  # show the start, not the scrolled tail
        self.error_label.setText("")
        editable = not profile.builtin
        for widget in (self.name_edit, self.baseline_spin, self.hfov_spin, self.modes_edit, self.notes_edit):
            widget.setEnabled(editable)
        self.apply_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)

    # ── CRUD ─────────────────────────────────────────────────

    def _add_profile(self) -> None:
        profile = CameraProfile(
            name=self._unique_name("New profile"), modes=((1280, 480, 30),)
        )
        self._profiles.append(profile)
        self._reload_list(select=len(self._profiles) - 1)

    def _clone_profile(self) -> None:
        if self._current < 0:
            return
        source = self._profiles[self._current]
        clone = CameraProfile(
            name=self._unique_name(f"{source.name} copy"),
            modes=source.modes,
            baseline_mm=source.baseline_mm,
            hfov_deg=source.hfov_deg,
            notes=source.notes,
        )
        self._profiles.append(clone)
        self._reload_list(select=len(self._profiles) - 1)

    def _delete_profile(self) -> None:
        if self._current < 0 or self._profiles[self._current].builtin:
            return
        del self._profiles[self._current]
        self._reload_list(select=self._current - 1)

    def _unique_name(self, base: str) -> str:
        names = {p.name for p in self._profiles}
        if base not in names:
            return base
        n = 2
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def _apply_edits(self) -> None:
        if self._current < 0 or self._profiles[self._current].builtin:
            return
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Enter a name.")
            return
        clash = any(
            p.name == name for i, p in enumerate(self._profiles) if i != self._current
        )
        if clash:
            self.error_label.setText(f"Name already exists: {name}")
            return
        try:
            modes = tuple(
                parse_mode(line)
                for line in self.modes_edit.toPlainText().splitlines()
                if line.strip()
            )
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        if not modes:
            self.error_label.setText("Enter at least one mode.")
            return
        self._profiles[self._current] = CameraProfile(
            name=name,
            modes=modes,
            baseline_mm=float(self.baseline_spin.value()),
            hfov_deg=float(self.hfov_spin.value()),
            notes=self.notes_edit.text().strip(),
        )
        self.error_label.setText("")
        self._reload_list(select=self._current)
