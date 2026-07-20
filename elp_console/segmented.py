"""Pill-style segmented control and a compact tab-stack built on it.

A SegmentedControl is an exclusive row of pill buttons — a lighter, denser
QTabBar replacement that fits inline in the header. SegmentedStack pairs one
with a QStackedWidget and exposes the small QTabWidget surface the app relies
on (count / tabText / currentWidget / setCurrentIndex / currentChanged)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SegmentedControl(QWidget):
    """Exclusive pill row. Emits ``currentChanged(index)`` on click or set."""

    currentChanged = Signal(int)

    def __init__(
        self,
        labels=(),
        parent=None,
        object_name: str = "Segmented",
        button_width: int | None = None,
    ):
        super().__init__(parent, objectName=object_name)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(4, 4, 4, 4)
        self._row.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        self._button_width = button_width
        for text in labels:
            self.add_segment(text)
        self._group.idClicked.connect(self.currentChanged)

    def add_segment(self, text: str) -> None:
        button = QPushButton(text, objectName="SegmentButton")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._button_width is not None:
            button.setFixedWidth(self._button_width)
        if not self._buttons:
            button.setChecked(True)
        self._group.addButton(button, len(self._buttons))
        self._row.addWidget(button)
        self._buttons.append(button)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 — Qt-style API
        if 0 <= index < len(self._buttons) and not self._buttons[index].isChecked():
            self._buttons[index].setChecked(True)
            self.currentChanged.emit(index)

    def currentIndex(self) -> int:  # noqa: N802 — Qt-style API
        return self._group.checkedId()

    def count(self) -> int:
        return len(self._buttons)

    def segmentText(self, index: int) -> str:  # noqa: N802 — Qt-style API
        return self._buttons[index].text()


class SegmentedStack(QWidget):
    """SegmentedControl + QStackedWidget — a compact QTabWidget replacement."""

    currentChanged = Signal(int)

    def __init__(self, parent=None, object_name: str = "SubNav", heading: str = ""):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        self._seg = SegmentedControl(object_name=object_name)
        self._stack = QStackedWidget()

        # Give nested work modes a dedicated section immediately after the
        # global stream controls, rather than leaving their switcher floating
        # above the workspace content.
        if heading:
            bar = QFrame(objectName="WorkspaceBar")
            row = QHBoxLayout(bar)
            row.setContentsMargins(20, 8, 20, 8)
            row.setSpacing(12)
            row.addWidget(QLabel(heading, objectName="WorkspaceTitle"))
            row.addStretch(1)
            row.addWidget(self._seg)
            box.addWidget(bar)
        else:
            bar = QHBoxLayout()
            bar.setContentsMargins(16, 12, 16, 8)
            bar.addWidget(self._seg)
            bar.addStretch(1)
            box.addLayout(bar)
        box.addWidget(self._stack, stretch=1)

        self._seg.currentChanged.connect(self._stack.setCurrentIndex)
        self._seg.currentChanged.connect(self.currentChanged)

    def addTab(self, widget: QWidget, text: str) -> None:  # noqa: N802 — Qt-style API
        self._stack.addWidget(widget)
        self._seg.add_segment(text)

    def count(self) -> int:
        return self._stack.count()

    def tabText(self, index: int) -> str:  # noqa: N802 — Qt-style API
        return self._seg.segmentText(index)

    def currentWidget(self) -> QWidget:  # noqa: N802 — Qt-style API
        return self._stack.currentWidget()

    def currentIndex(self) -> int:  # noqa: N802 — Qt-style API
        return self._stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 — Qt-style API
        self._seg.setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget) -> None:  # noqa: N802 — Qt-style API
        index = self._stack.indexOf(widget)
        if index >= 0:
            self._seg.setCurrentIndex(index)
