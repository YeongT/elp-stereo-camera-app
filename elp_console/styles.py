"""Dark theme QSS and palette for the viewer."""

from PySide6.QtGui import QColor, QPalette

ACCENT = "#4f8cff"
BG_WINDOW = "#0f1117"
BG_SURFACE = "#161923"
BG_INPUT = "#1d2130"
BORDER = "#262b3b"
TEXT = "#e6e9f2"
TEXT_DIM = "#8b93a7"
GREEN = "#34d399"
RED = "#f4606e"
AMBER = "#f5b14d"

QSS = f"""
* {{
    font-family: "Segoe UI", "Malgun Gothic";
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, #Root {{
    background: {BG_WINDOW};
}}

#Header {{
    background: #12141c;
    border-bottom: 1px solid {BORDER};
}}
#TitleLabel {{
    font-size: 16px;
    font-weight: 600;
}}
#HeaderChip {{
    background: {BG_INPUT};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 3px 11px;
    font-size: 11px;
}}
#HeaderRight {{
    color: {TEXT_DIM};
    font-size: 11px;
}}

#ControlBar {{
    background: {BG_SURFACE};
    border-bottom: 1px solid {BORDER};
}}
#ControlBar QLabel {{
    color: {TEXT_DIM};
    font-size: 12px;
}}

#SidePanel {{
    background: {BG_SURFACE};
    border-left: 1px solid {BORDER};
}}
#SidePanelBody {{
    background: {BG_SURFACE};
}}
#SidePanelBody QLabel {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
#SidePanelBody QLabel#SectionLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 3px 0;
    border-bottom: 1px solid {BORDER};
}}
#SidePanelBody QPushButton {{
    padding: 7px 10px;
}}

QComboBox {{
    background: {BG_INPUT};
    border: 1px solid #2a3040;
    border-radius: 7px;
    padding: 5px 10px;
    min-width: 80px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox:disabled {{
    color: #5a6175;
    background: #171a23;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {BG_INPUT};
    border: 1px solid #2a3040;
    border-radius: 6px;
    selection-background-color: #2a3550;
    outline: none;
    padding: 4px;
}}

QPushButton {{
    background: {BG_INPUT};
    border: 1px solid #2a3040;
    border-radius: 7px;
    padding: 7px 18px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
    background: #222738;
}}
QPushButton:pressed {{
    background: #191d2b;
}}
QPushButton:disabled {{
    color: #5a6175;
    background: #171a23;
    border-color: #20242f;
}}

QPushButton#StartButton, QPushButton#StopButton, QPushButton#SnapshotButton {{
    min-width: 52px;
    padding: 7px 18px;
}}

QPushButton#StartButton {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#StartButton:hover {{
    background: #6ea1ff;
    border-color: #6ea1ff;
}}
QPushButton#StartButton:pressed {{
    background: #3d76e0;
}}
QPushButton#StartButton:disabled {{
    background: #26314a;
    border-color: #26314a;
    color: #6b7590;
}}

QPushButton#StopButton {{
    color: {RED};
    border-color: #52303a;
}}
QPushButton#StopButton:hover {{
    border-color: {RED};
    background: #241a20;
}}
QPushButton#StopButton:disabled {{
    color: #5a6175;
    border-color: #20242f;
}}

QPushButton#RefreshButton {{
    padding: 7px 12px;
    font-size: 14px;
}}

QPushButton#SwapButton:checked,
QPushButton#ExposureButton:checked,
QPushButton#TimelapseButton:checked,
QPushButton#RectifyButton:checked,
QPushButton#GuideButton:checked,
QPushButton#AutoCaptureButton:checked {{
    color: {ACCENT};
    border-color: {ACCENT};
    background: #1b2439;
}}

QPushButton#CalibrateButton {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#CalibrateButton:hover {{
    background: #6ea1ff;
    border-color: #6ea1ff;
}}
QPushButton#CalibrateButton:disabled {{
    background: #26314a;
    border-color: #26314a;
    color: #6b7590;
}}

QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    border: 1px solid #2a3040;
    border-radius: 7px;
    padding: 5px 8px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}
QSpinBox:disabled, QDoubleSpinBox:disabled,
QLineEdit:disabled, QPlainTextEdit:disabled {{
    color: #5a6175;
    background: #171a23;
}}

QLineEdit, QPlainTextEdit {{
    background: {BG_INPUT};
    border: 1px solid #2a3040;
    border-radius: 7px;
    padding: 5px 8px;
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}

#CalibResult {{
    color: {TEXT_DIM};
    font-family: "Cascadia Mono", "Consolas", "Malgun Gothic";
    font-size: 11px;
    padding: 4px 2px;
}}

QPushButton#RecordButton:checked {{
    background: {RED};
    border-color: {RED};
    color: white;
    font-weight: 600;
}}

#StatusRow {{
    background: #12141c;
    border-top: 1px solid {BORDER};
}}
QLabel[chip="true"] {{
    background: {BG_INPUT};
    border: 1px solid #2a3040;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-family: "Cascadia Mono", "Consolas", "Malgun Gothic";
    color: #aeb6c9;
}}
QLabel[chip="true"][state="ok"] {{
    color: {GREEN};
    border-color: #1e4034;
    background: #12241d;
}}
QLabel[chip="true"][state="bad"] {{
    color: {RED};
    border-color: #4a2730;
    background: #241318;
}}
QLabel[chip="true"][state="warn"] {{
    color: {AMBER};
    border-color: #453721;
    background: #231d12;
}}
#FlashLabel {{
    color: {GREEN};
    font-size: 12px;
}}

QPushButton#LogToggle {{
    padding: 3px 12px;
    font-size: 11px;
    border-radius: 6px;
}}
QPushButton#LogToggle:checked {{
    color: {ACCENT};
    border-color: {ACCENT};
    background: #1b2439;
}}

QPlainTextEdit#LogPanel {{
    background: #0b0d13;
    border: none;
    border-top: 1px solid {BORDER};
    font-family: "Cascadia Mono", "Consolas", "Malgun Gothic";
    font-size: 11px;
    color: #9aa3b8;
    padding: 6px;
}}

QTabWidget#MainTabs::pane, QTabWidget#SubTabs::pane {{
    border: none;
    background: {BG_WINDOW};
}}
QTabWidget#SubTabs QTabBar::tab {{
    padding: 6px 16px;
    font-size: 12px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 8px 22px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}
QTabBar {{
    background: #12141c;
}}

QListWidget#FileList {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    font-size: 12px;
    outline: none;
}}
QListWidget#FileList::item {{
    padding: 7px 9px;
    border-radius: 6px;
    color: #aeb6c9;
}}
QListWidget#FileList::item:selected {{
    background: #2a3550;
    color: {TEXT};
}}
QListWidget#FileList::item:hover:!selected {{
    background: #1d2130;
}}

QSlider::groove:horizontal {{
    height: 5px;
    background: {BG_INPUT};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 13px;
    height: 13px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider:disabled {{
    background: transparent;
}}

#TimeLabel {{
    color: {TEXT_DIM};
    font-family: "Cascadia Mono", "Consolas", "Malgun Gothic";
    font-size: 11px;
    min-width: 90px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2a3040;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a4152;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""


def dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_WINDOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_INPUT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    return palette
