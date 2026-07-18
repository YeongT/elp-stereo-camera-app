"""Native DirectShow camera property dialog (brightness, exposure, contrast...).

The driver's VideoProcAmp page applies changes to the UVC device immediately,
so adjustments show up live in the running stream. The dialog is modal and
pumps its own message loop — run it in a helper thread to keep the Qt UI alive.
"""

import threading
from collections.abc import Callable


def open_camera_settings(device_index: int, log: Callable[[str], None]) -> None:
    def _show() -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
            try:
                from pygrabber.dshow_graph import FilterGraph, FilterType

                graph = FilterGraph()
                graph.add_video_input_device(device_index)
                graph.filters[FilterType.video_input].set_properties()
            finally:
                comtypes.CoUninitialize()
        except Exception as exc:  # noqa: BLE001 — device busy, no property page, etc.
            log(f"[ERROR] 카메라 설정 대화상자 실패: {exc}")

    threading.Thread(target=_show, daemon=True, name="camera-settings").start()
