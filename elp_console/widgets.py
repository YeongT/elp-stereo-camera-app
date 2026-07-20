"""Custom widgets: letterboxed stereo video view with state surfaces."""

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .styles import ACCENT, RED, TEXT, TEXT_DIM

STATE_IDLE = "idle"
STATE_OPENING = "opening"
STATE_STREAMING = "streaming"
STATE_ERROR = "error"

_BG = QColor("#0b0d12")
_BADGE_BG = QColor(10, 12, 18, 190)


class VideoView(QWidget):
    """Single surface that renders the SBS stream plus idle/opening/error states."""

    def __init__(
        self,
        parent=None,
        idle_title: str = "Waiting for stream",
        idle_subtitle: str = "Pick a profile, device, and mode, then press Start",
    ):
        super().__init__(parent)
        self._state = STATE_IDLE
        self._pixmap: QPixmap | None = None
        self._error_message = ""
        self._view_mode = "sbs"
        self._hist = None
        self._clip: tuple[float, float] | None = None
        self._guides = False
        self._capture_flash = False
        self._idle_title = idle_title
        self._idle_subtitle = idle_subtitle
        self.setMinimumSize(640, 360)
        self._capture_flash_timer = QTimer(self)
        self._capture_flash_timer.setSingleShot(True)
        self._capture_flash_timer.timeout.connect(self._clear_capture_flash)

    def flash_capture(self, duration_ms: int = 550) -> None:
        """Briefly outline a successfully captured calibration frame in red."""
        self._capture_flash = True
        self._capture_flash_timer.start(duration_ms)
        self.update()

    def _clear_capture_flash(self) -> None:
        self._capture_flash = False
        self.update()

    def set_guides(self, enabled: bool) -> None:
        """Horizontal epipolar guide lines — rectification check (display only)."""
        self._guides = enabled
        self.update()

    def set_state(self, state: str, message: str = "") -> None:
        self._state = state
        self._error_message = message
        if state != STATE_STREAMING:
            self._pixmap = None
            self._hist = None
            self._clip = None
        self.update()

    def set_frame(self, pixmap: QPixmap, view_mode: str = "sbs", hist=None, clip=None) -> None:
        """view_mode: "sbs" draws divider + LEFT/RIGHT badges; "left"/"right"/
        "anaglyph" draw a single badge; any other value (e.g. "none") draws no
        overlay — used by the library image preview."""
        self._state = STATE_STREAMING
        self._pixmap = pixmap
        self._view_mode = view_mode
        self._hist = hist
        self._clip = clip
        self.update()

    def _target_rect(self) -> QRect:
        if self._pixmap is None:
            return self.rect()
        area = self.rect().adjusted(12, 12, -12, -12)
        scaled = self._pixmap.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = area.x() + (area.width() - scaled.width()) // 2
        y = area.y() + (area.height() - scaled.height()) // 2
        return QRect(x, y, scaled.width(), scaled.height())

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), _BG)

        if self._state == STATE_STREAMING and self._pixmap is not None:
            self._paint_stream(painter)
        elif self._state == STATE_OPENING:
            self._paint_message(painter, "Opening camera…", "Negotiating backend — see the log panel for progress", TEXT_DIM)
        elif self._state == STATE_ERROR:
            self._paint_message(painter, "Failed to open stream", self._error_message, RED)
        else:
            self._paint_message(painter, self._idle_title, self._idle_subtitle, TEXT_DIM)
        painter.end()

    def _paint_stream(self, painter: QPainter) -> None:
        target = self._target_rect()
        painter.drawPixmap(target, self._pixmap)

        if self._view_mode == "sbs":
            pen = QPen(QColor(ACCENT))
            pen.setWidth(2)
            painter.setPen(pen)
            center_x = target.x() + target.width() // 2
            painter.setOpacity(0.55)
            painter.drawLine(center_x, target.y(), center_x, target.y() + target.height())
            painter.setOpacity(1.0)
            self._paint_badge(painter, "LEFT", target.x() + 10, target.y() + 10)
            self._paint_badge(painter, "RIGHT", center_x + 10, target.y() + 10)
        else:
            label = {"left": "LEFT", "right": "RIGHT", "anaglyph": "3D"}.get(self._view_mode, "")
            if label:
                self._paint_badge(painter, label, target.x() + 10, target.y() + 10)

        if self._guides:
            pen = QPen(QColor(ACCENT))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setOpacity(0.35)
            step = max(24, target.height() // 12)
            for y in range(target.y() + step, target.y() + target.height(), step):
                painter.drawLine(target.x(), y, target.x() + target.width(), y)
            painter.setOpacity(1.0)

        if self._hist is not None:
            self._paint_histogram(painter, target)

        painter.setPen(QPen(QColor("#262b3b")))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target.adjusted(-1, -1, 0, 0))
        if self._capture_flash:
            pen = QPen(QColor(RED))
            pen.setWidth(5)
            painter.setPen(pen)
            painter.drawRect(target.adjusted(2, 2, -2, -2))

    def _paint_histogram(self, painter: QPainter, target: QRect) -> None:
        panel_w, panel_h = 196, 76
        panel = QRectF(target.x() + 10, target.y() + target.height() - panel_h - 10, panel_w, panel_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BADGE_BG)
        painter.drawRoundedRect(panel, 6, 6)

        bars = QRectF(panel.x() + 8, panel.y() + 8, panel.width() - 16, panel.height() - 34)
        count = len(self._hist)
        bar_w = bars.width() / count
        painter.setBrush(QColor(TEXT_DIM))
        for i, value in enumerate(self._hist):
            h = max(1.0, float(value) * bars.height())
            painter.drawRect(QRectF(bars.x() + i * bar_w, bars.bottom() - h, bar_w - 0.5, h))

        if self._clip is not None:
            clip_low, clip_high = self._clip
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.setPen(QColor("#6ea1ff"))
            painter.drawText(
                QRectF(panel.x() + 8, panel.bottom() - 22, panel.width() / 2 - 8, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"▼ Shadows {clip_low:.1f}%",
            )
            painter.setPen(QColor(RED))
            painter.drawText(
                QRectF(panel.x() + panel.width() / 2, panel.bottom() - 22, panel.width() / 2 - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"Highlights {clip_high:.1f}% ▲",
            )

    def _paint_badge(self, painter: QPainter, text: str, x: int, y: int) -> None:
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        w = metrics.horizontalAdvance(text) + 20
        h = metrics.height() + 8
        rect = QRectF(x, y, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BADGE_BG)
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor(TEXT))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_message(self, painter: QPainter, title: str, subtitle: str, title_color: str) -> None:
        rect = self.rect()

        title_font = QFont("Segoe UI", 15)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(title_color))
        title_rect = QRectF(rect.x(), rect.y() + rect.height() / 2 - 40, rect.width(), 30)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)

        if subtitle:
            sub_font = QFont("Segoe UI", 10)
            painter.setFont(sub_font)
            painter.setPen(QColor(TEXT_DIM))
            sub_rect = QRectF(rect.x() + 40, rect.y() + rect.height() / 2 - 2, rect.width() - 80, 48)
            painter.drawText(
                sub_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                subtitle,
            )
