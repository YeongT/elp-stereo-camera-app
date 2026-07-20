"""Native DirectShow camera property dialog (brightness, exposure, contrast...).

The driver's property page (``OleCreatePropertyFrame``) fails with E_FAIL on a
*bare* source filter — one added to a graph but never connected or run. So we
attach a NullRenderer, build the graph, and run it before showing the page;
that keeps the filter live and its property provider available. The dialog is
modal and pumps its own message loop, so it runs in a helper thread to keep the
Qt UI alive.

VideoProcAmp changes apply to the device globally, so with the app streaming the
same camera the live preview reflects them immediately — the intended workflow.
This runs its own graph, so opening while streaming needs a multi-access camera
(e.g. the Windows Frame Server); otherwise the second open fails device-busy and
the exception below is logged.
"""

import threading
from collections.abc import Callable


def open_camera_settings(device_index: int, log: Callable[[str], None]) -> None:
    def _show() -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
            graph = None
            try:
                from pygrabber.dshow_graph import FilterGraph

                graph = FilterGraph()
                graph.add_video_input_device(device_index)
                graph.add_null_render()  # sink so the source pin can connect
                graph.prepare_preview_graph()  # connect source -> null renderer
                graph.run()  # live filter — its property page can now activate
                try:
                    graph.get_input_device().set_properties()
                finally:
                    graph.stop()
                    graph.remove_filters()
            finally:
                comtypes.CoUninitialize()
        except Exception as exc:  # noqa: BLE001 — device busy, no property page, driver quirk
            log(f"[ERROR] Camera settings dialog failed — this driver may not support the property window: {exc}")

    threading.Thread(target=_show, daemon=True, name="camera-settings").start()
