"""DirectShow device enumeration."""


def list_devices() -> list[str]:
    try:
        from pygrabber.dshow_graph import FilterGraph

        names = FilterGraph().get_input_devices()
        if names:
            return names
    except Exception:  # noqa: BLE001 — enumeration is best-effort
        pass
    return ["Camera 0"]
