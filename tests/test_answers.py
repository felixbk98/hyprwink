import os

from hyprwink import answers


def test_terminal_window_gets_its_own_session(monkeypatch, tmp_path):
    monkeypatch.setattr(answers, "DIR", tmp_path)
    monkeypatch.setattr(answers, "INDEX", tmp_path / "sessions.json")
    # This test process plays the claude process, its parent the window.
    monkeypatch.setattr(answers, "_claude_pid", lambda: os.getpid())
    answers.answered("this", "aus diesem Terminal")
    window = {"pid": os.getppid(), "class": "com.mitchellh.ghostty", "title": "x"}
    assert answers.for_window(window)[1] == "aus diesem Terminal"
    assert answers.for_window({"pid": 999999999, "class": "other", "title": "x"}) is None
