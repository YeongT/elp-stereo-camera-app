"""Live tab side panel: view, capture, and device tool groups.

Widget construction only — the main window and MediaController connect signals
and own all behavior. Every interactive widget is exposed as an attribute."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

BACKEND_MODES = ["Auto", "FFmpeg", "MSMF", "DSHOW"]
VIEW_MODES = [("SBS 합성", "sbs"), ("왼쪽만", "left"), ("오른쪽만", "right"), ("아나글리프 3D", "anaglyph")]
RECORD_FORMATS = [("SBS 한 파일", False), ("좌/우 분리", True)]
TIMELAPSE_INTERVALS = [1, 2, 5, 10, 30, 60]

PANEL_WIDTH = 240


class SidePanel(QScrollArea):
    """Grouped tool column right of the video: 보기 / 캡처 / 장치."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="SidePanel")
        self.setFixedWidth(PANEL_WIDTH)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget(objectName="SidePanelBody")
        self._column = QVBoxLayout(body)
        self._column.setContentsMargins(14, 12, 14, 14)
        self._column.setSpacing(8)
        self._build_view_group()
        self._build_capture_group()
        self._build_device_group()
        self._column.addStretch(1)
        self.setWidget(body)

    # ── 레이아웃 헬퍼 ────────────────────────────────────────

    def _section(self, title: str, first: bool = False) -> None:
        if not first:
            self._column.addSpacing(10)
        self._column.addWidget(QLabel(title, objectName="SectionLabel"))

    def _labeled(self, text: str, widget: QWidget) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(text)
        label.setFixedWidth(40)
        row.addWidget(label)
        row.addWidget(widget, 1)
        self._column.addLayout(row)

    # ── 보기 ─────────────────────────────────────────────────

    def _build_view_group(self) -> None:
        self._section("보기", first=True)

        self.view_combo = QComboBox()
        for label, mode in VIEW_MODES:
            self.view_combo.addItem(label, mode)
        self.view_combo.setToolTip("표시 전용 보기 모드 — 스냅샷·녹화에는 미적용")
        self._labeled("모드", self.view_combo)

        self.rotation_combo = QComboBox()
        for degrees in (0, 90, 180, 270):
            self.rotation_combo.addItem(f"{degrees}°", degrees)
        self.rotation_combo.setToolTip("눈별 회전 — 스냅샷·녹화에도 적용")
        self._labeled("회전", self.rotation_combo)

        self.swap_button = QPushButton("좌우 교체", objectName="SwapButton")
        self.swap_button.setCheckable(True)
        self.swap_button.setToolTip("왼쪽/오른쪽 영상을 서로 바꿔 표시 (스냅샷·녹화에도 적용)")

        self.exposure_button = QPushButton("노출 체크", objectName="ExposureButton")
        self.exposure_button.setCheckable(True)
        self.exposure_button.setToolTip("히스토그램 + 클리핑 표시 (명부 빨강, 암부 파랑)")

        self.rectify_button = QPushButton("정렬 보정", objectName="RectifyButton")
        self.rectify_button.setCheckable(True)
        self.rectify_button.setEnabled(False)
        self.rectify_button.setToolTip("캘리브레이션 탭에서 캘리브레이션을 먼저 실행하세요")

        self.guide_button = QPushButton("수평 가이드", objectName="GuideButton")
        self.guide_button.setCheckable(True)
        self.guide_button.setToolTip(
            "수평선 오버레이 — 정렬 보정 후 좌우 특징이 같은 선에 놓이는지 확인 (표시 전용)"
        )

        grid = QGridLayout()
        grid.setSpacing(6)
        toggles = (self.swap_button, self.exposure_button, self.rectify_button, self.guide_button)
        for i, button in enumerate(toggles):
            grid.addWidget(button, i // 2, i % 2)
        self._column.addLayout(grid)

    # ── 캡처 ─────────────────────────────────────────────────

    def _build_capture_group(self) -> None:
        self._section("캡처")

        self.snapshot_button = QPushButton("스냅샷", objectName="SnapshotButton")
        self.snapshot_button.setEnabled(False)
        self.snapshot_button.setToolTip("좌/우 풀해상도 PNG 저장")
        self._column.addWidget(self.snapshot_button)

        self.record_format_combo = QComboBox()
        for label, split in RECORD_FORMATS:
            self.record_format_combo.addItem(label, split)
        self.record_format_combo.setToolTip("녹화 파일 구성 — 변경 시 새 세그먼트로 전환")
        self._labeled("형식", self.record_format_combo)

        self.record_button = QPushButton("녹화", objectName="RecordButton")
        self.record_button.setCheckable(True)
        self.record_button.setEnabled(False)
        self.record_button.setToolTip("MP4 녹화 (좌우 교체·회전·정렬 보정 적용, 보기 모드는 미적용)")
        self._column.addWidget(self.record_button)

        self.timelapse_interval_combo = QComboBox()
        for seconds in TIMELAPSE_INTERVALS:
            self.timelapse_interval_combo.addItem(f"{seconds}초", seconds)
        self.timelapse_interval_combo.setToolTip("타임랩스 촬영 간격")
        self._labeled("간격", self.timelapse_interval_combo)

        self.timelapse_button = QPushButton("타임랩스", objectName="TimelapseButton")
        self.timelapse_button.setCheckable(True)
        self.timelapse_button.setEnabled(False)
        self.timelapse_button.setToolTip("지정한 간격으로 스냅샷 자동 저장 (세션별 하위 폴더)")
        self._column.addWidget(self.timelapse_button)

        self.folder_button = QPushButton("저장 폴더")
        self._column.addWidget(self.folder_button)

    # ── 장치 ─────────────────────────────────────────────────

    def _build_device_group(self) -> None:
        self._section("장치")

        self.backend_combo = QComboBox()
        self.backend_combo.addItems(BACKEND_MODES)
        self.backend_combo.setToolTip("캡처 백엔드 — 스트리밍 중 변경 시 자동 재시작")
        self._labeled("백엔드", self.backend_combo)

        self.settings_button = QPushButton("카메라 설정")
        self.settings_button.setToolTip("드라이버 속성 창 열기 — 밝기·노출·대비 등 실시간 조절")
        self._column.addWidget(self.settings_button)
