"""Library tab: browse and play back recordings/snapshots from the output dir."""

import os
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from .widgets import VideoView

MEDIA_SUFFIXES = (".mp4", ".png", ".jpg")


def _format_ms(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class LibraryView(QWidget):
    def __init__(
        self,
        get_directory: Callable[[], str],
        log: Callable[[str], None],
        parent=None,
    ):
        super().__init__(parent)
        self._get_directory = get_directory
        self._log = log
        self._slider_held = False
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        side = QVBoxLayout()
        side.setSpacing(8)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        refresh = QPushButton("새로 고침")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)
        open_folder = QPushButton("폴더 열기")
        open_folder.clicked.connect(self._open_folder)
        buttons.addWidget(open_folder)
        side.addLayout(buttons)

        self.file_list = QListWidget(objectName="FileList")
        self.file_list.currentItemChanged.connect(self._on_item_selected)
        side.addWidget(self.file_list, stretch=1)

        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(320)
        layout.addWidget(side_widget)

        right = QVBoxLayout()
        right.setSpacing(8)

        self._stack = QStackedLayout()
        self.placeholder = VideoView(
            idle_title="파일을 선택하세요",
            idle_subtitle="왼쪽 목록에서 녹화 영상이나 스냅샷을 고르면 여기서 재생됩니다",
        )
        self._stack.addWidget(self.placeholder)
        self.video_widget = QVideoWidget()
        self._stack.addWidget(self.video_widget)
        self.image_view = VideoView()
        self._stack.addWidget(self.image_view)
        stack_host = QWidget()
        stack_host.setLayout(self._stack)
        right.addWidget(stack_host, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.play_button = QPushButton("재생")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_button)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setEnabled(False)
        self.position_slider.sliderPressed.connect(lambda: setattr(self, "_slider_held", True))
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        controls.addWidget(self.position_slider, stretch=1)

        self.time_label = QLabel("00:00 / 00:00", objectName="TimeLabel")
        controls.addWidget(self.time_label)
        right.addLayout(controls)
        layout.addLayout(right, stretch=1)

        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video_widget)
        self.player.durationChanged.connect(self._on_duration)
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(self._on_playback_state)
        self.player.errorOccurred.connect(self._on_player_error)

    # ── 파일 목록 ────────────────────────────────────────────

    @Slot()
    def refresh(self) -> None:
        current = self.file_list.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.file_list.blockSignals(True)
        self.file_list.clear()

        directory = Path(self._get_directory())
        files = []
        if directory.is_dir():
            files = sorted(
                (p for p in directory.iterdir() if p.suffix.lower() in MEDIA_SUFFIXES),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        for path in files:
            stat = path.stat()
            stamp = time.strftime("%m-%d %H:%M", time.localtime(stat.st_mtime))
            item = QListWidgetItem(f"{path.name}\n{stamp} · {stat.st_size / 1_048_576:.1f}MB")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.file_list.addItem(item)
            if selected == str(path):
                self.file_list.setCurrentItem(item)
        self.file_list.blockSignals(False)

    def _open_folder(self) -> None:
        directory = Path(self._get_directory())
        directory.mkdir(parents=True, exist_ok=True)
        os.startfile(str(directory))  # noqa: S606 — local folder, user-initiated

    # ── 재생 ─────────────────────────────────────────────────

    @Slot()
    def _on_item_selected(self, current, _previous=None) -> None:
        if current is None:
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        if path.suffix.lower() == ".mp4":
            self._show_video(path)
        else:
            self._show_image(path)

    def _show_video(self, path: Path) -> None:
        self._stack.setCurrentWidget(self.video_widget)
        self.play_button.setEnabled(True)
        self.position_slider.setEnabled(True)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def _show_image(self, path: Path) -> None:
        self.player.stop()
        self.play_button.setEnabled(False)
        self.position_slider.setEnabled(False)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._log(f"[ERROR] 이미지 열기 실패: {path.name}")
            return
        self._stack.setCurrentWidget(self.image_view)
        self.image_view.set_frame(pixmap, view_mode="none")

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def pause(self) -> None:
        """Called when the tab is hidden — do not keep the file handle busy."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()

    # ── player 신호 ──────────────────────────────────────────

    def _on_duration(self, duration: int) -> None:
        self.position_slider.setRange(0, duration)
        self._update_time_label()

    def _on_position(self, position: int) -> None:
        if not self._slider_held:
            self.position_slider.setValue(position)
        self._update_time_label()

    def _on_slider_released(self) -> None:
        self._slider_held = False
        self.player.setPosition(self.position_slider.value())

    def _on_playback_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("일시정지" if playing else "재생")

    def _on_player_error(self, _error, message: str) -> None:
        self._log(f"[ERROR] 재생 실패: {message}")

    def _update_time_label(self) -> None:
        self.time_label.setText(
            f"{_format_ms(self.player.position())} / {_format_ms(self.player.duration())}"
        )
