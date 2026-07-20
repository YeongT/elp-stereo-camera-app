"""Reusable titled section card for the tool panels.

A card frames a group of controls: title, optional caption, then form rows
(fixed label column so controls line up), full-width actions, or a uniform
button grid. Shared by the live side panel and the calibration sub-tabs so the
whole app speaks one visual language. Styled via ``#GroupCard`` in styles.py."""

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

LABEL_WIDTH = 64


class SectionCard(QFrame):
    """Bordered card: header (title + optional caption) above a form/button body."""

    def __init__(self, title: str, caption: str = "", parent=None):
        super().__init__(parent, objectName="GroupCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        header = QVBoxLayout()
        header.setSpacing(1)
        header.addWidget(QLabel(title, objectName="CardTitle"))
        if caption:
            header.addWidget(QLabel(caption, objectName="CardCaption"))
        outer.addLayout(header)

        self._body = QVBoxLayout()
        self._body.setSpacing(6)
        outer.addLayout(self._body)

    def add_row(self, label_text: str, widget: QWidget, label_width: int = LABEL_WIDTH) -> None:
        """Label-left form row: fixed label column, control fills the rest."""
        row = QGridLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setHorizontalSpacing(10)
        label = QLabel(label_text, objectName="RowLabel")
        label.setFixedWidth(label_width)
        row.addWidget(label, 0, 0)
        row.addWidget(widget, 0, 1)
        row.setColumnStretch(1, 1)
        self._body.addLayout(row)

    def add_full(self, widget: QWidget) -> None:
        """Full-width control/action spanning the card body."""
        self._body.addWidget(widget)

    def add_grid(self, buttons, columns: int = 2) -> None:
        """Uniform grid of equal-width buttons."""
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        for i, button in enumerate(buttons):
            grid.addWidget(button, i // columns, i % columns)
        for col in range(columns):
            grid.setColumnStretch(col, 1)
        self._body.addLayout(grid)

    def add_layout(self, layout) -> None:
        """Escape hatch for a caller-built sub-layout inside the card body."""
        self._body.addLayout(layout)
