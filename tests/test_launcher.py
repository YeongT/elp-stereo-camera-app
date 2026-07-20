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


def test_default_entrypoint_launches_detached(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "launch_detached", lambda: calls.append("detached"))
    monkeypatch.setattr(main, "main", lambda: calls.append("foreground"))

    main.entrypoint([])

    assert calls == ["detached"]


def test_foreground_and_version_entrypoints(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(main, "main", lambda: calls.append("foreground"))

    main.entrypoint(["--foreground"])
    main.entrypoint(["--version"])

    assert calls == ["foreground"]
    assert f"v{main.__version__}" in capsys.readouterr().out
