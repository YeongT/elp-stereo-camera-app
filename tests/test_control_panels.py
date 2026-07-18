"""Live tab chrome split: ControlBar holds stream setup, SidePanel holds tools."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from elp_console.control_bar import ControlBar, HeaderBar, StatusRow
from elp_console.side_panel import SidePanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_control_bar_holds_stream_setup_only(qapp):
    bar = ControlBar()
    for name in (
        "profile_combo",
        "profile_button",
        "device_combo",
        "refresh_button",
        "mode_combo",
    ):
        assert hasattr(bar, name), name
    # start/stop moved to the header; view/capture/backend tools to the side panel
    for name in ("start_button", "stop_button", "view_combo", "snapshot_button", "backend_combo"):
        assert not hasattr(bar, name), name


def test_header_bar_owns_stream_lifecycle_controls(qapp):
    header = HeaderBar()
    assert header.start_button.isEnabled()
    assert not header.stop_button.isEnabled()
    header.set_stream_state("opening")
    header.set_stream_state("streaming")
    header.set_stream_state("error")
    header.set_stream_state("idle")
    assert header.stream_chip.text()


def test_side_panel_holds_view_capture_device_tools(qapp):
    panel = SidePanel()
    for name in (
        "view_combo",
        "rotation_combo",
        "swap_button",
        "exposure_button",
        "rectify_button",
        "guide_button",
        "snapshot_button",
        "record_button",
        "record_format_combo",
        "timelapse_button",
        "timelapse_interval_combo",
        "folder_button",
        "backend_combo",
        "settings_button",
    ):
        assert hasattr(panel, name), name


def test_capture_tools_disabled_until_streaming(qapp):
    panel = SidePanel()
    assert not panel.snapshot_button.isEnabled()
    assert not panel.record_button.isEnabled()
    assert not panel.timelapse_button.isEnabled()
    assert not panel.rectify_button.isEnabled()


def test_status_row_log_toggle_defaults_on(qapp):
    row = StatusRow()
    assert row.log_toggle.isCheckable()
    assert row.log_toggle.isChecked()
