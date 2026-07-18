from pathlib import Path

import main


def test_detached_launcher_reexecutes_main_in_project_directory(monkeypatch):
    calls = []
    monkeypatch.setattr(main.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))

    main.launch_detached()

    command, kwargs = calls[0]
    assert Path(command[1]).resolve() == Path(main.__file__).resolve()
    assert command[2] == "--child"
    assert kwargs["cwd"] == str(Path(main.__file__).resolve().parent)
    assert kwargs["close_fds"]
