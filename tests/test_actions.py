import types

from hyprwink import gestures
from hyprwink.core import actions


def _actions(monkeypatch, state="idle", reading=False, terminal=False):
    keys, dispatched, calls = [], [], []
    monkeypatch.setattr(actions.hypr, "key", keys.append)
    monkeypatch.setattr(actions.hypr, "dispatch", dispatched.append)
    monkeypatch.setattr(actions.hypr, "in_terminal", lambda: terminal)
    a = actions.Actions.__new__(actions.Actions)
    a.dictation = types.SimpleNamespace(state=state, stop=lambda send=False: calls.append(("stop", send)),
                                        cancel=lambda: calls.append("cancel"))
    a.reader = types.SimpleNamespace(reading=reading, stop=lambda: calls.append("read_stop"))
    return a, keys, dispatched, calls


def test_enter_sends_while_dictating(monkeypatch):
    a, keys, _, calls = _actions(monkeypatch, state="recording")
    a._builtin("enter")
    assert calls == [("stop", True)] and keys == []
    a, keys, _, calls = _actions(monkeypatch)
    a._builtin("enter")
    assert keys == ["Return"] and calls == []


def test_escape_cancels_first(monkeypatch):
    a, keys, _, calls = _actions(monkeypatch, state="transcribing")
    a._builtin("escape")
    assert calls == ["cancel"]
    a, keys, _, calls = _actions(monkeypatch, reading=True)
    a._builtin("escape")
    assert calls == ["read_stop"]
    a, keys, _, calls = _actions(monkeypatch)
    a._builtin("escape")
    assert keys == ["Escape"]


def test_cancel_never_presses_escape(monkeypatch):
    a, keys, _, calls = _actions(monkeypatch, state="recording")
    a._builtin("cancel")
    assert calls == ["cancel"]
    a, keys, _, calls = _actions(monkeypatch)
    a._builtin("cancel")
    assert keys == [] and calls == []


def test_copy_paste_in_terminals(monkeypatch):
    a, keys, _, _ = _actions(monkeypatch, terminal=True)
    a._builtin("copy")
    a._builtin("paste")
    assert keys == ["CTRL+SHIFT+C", "SHIFT+Insert"]


def test_every_builtin_is_handled(monkeypatch):
    handled = {"dictate_start", "dictate_stop", "dictate_send", "read_start", "read_stop", "enter", "escape", "cancel",
               "window_swipe"}
    handled |= set(actions.KEYS) | set(actions.DISPATCH) | set(actions.MEDIA) | set(actions.VOLUME)
    assert set(gestures.BUILTIN) == handled


def test_app_label(monkeypatch, tmp_path):
    (tmp_path / "applications").mkdir()
    (tmp_path / "applications" / "x.desktop").write_text("[Desktop Entry]\nName=Beispiel\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert gestures.action_label({"type": "app", "value": "x.desktop"}) == "Program: Beispiel"


def test_command_is_started_by_hyprland(monkeypatch):
    a, _, dispatched, _ = _actions(monkeypatch)
    a._run({"type": "command", "value": 'notify-send "Hallo"'})
    assert dispatched == ['hl.dsp.exec_cmd("notify-send \\"Hallo\\"")']



def test_hyprland_shortcut_is_typed(monkeypatch):
    from hyprwink.core import hypr
    calls, evals = [], []
    binds = '[{"modmask": 65, "key": "DOWN", "submap": ""}]'
    monkeypatch.setattr(hypr, "_run", lambda *a, **k: binds if a[:2] == ("-j", "binds") else evals.append(a))
    monkeypatch.setattr(hypr.subprocess, "run", lambda cmd, **k: calls.append(cmd))
    hypr.key("SHIFT+SUPER+Down")
    assert calls == [["wtype", "-M", "shift", "-M", "logo", "-k", "Down", "-m", "logo", "-m", "shift"]]
    calls.clear()
    hypr.key("CTRL+C")            # not a Hyprland binding: sent to the window
    assert calls == [] and "send_key_state" in evals[-1][1]


def test_monitor_in_swipe_direction(monkeypatch):
    from hyprwink.core import hypr
    mons = [{"id": 0, "name": "DP-1", "x": 0, "y": 1152, "width": 5120, "height": 1440, "scale": 1.25},
            {"id": 1, "name": "DP-2", "x": 0, "y": 0, "width": 2560, "height": 1440, "scale": 1.25},
            {"id": 2, "name": "DP-3", "x": 2048, "y": 0, "width": 2560, "height": 1440, "scale": 1.25}]
    import json
    monkeypatch.setattr(hypr, "_run", lambda *a, **k: json.dumps(mons))
    monkeypatch.setattr(hypr, "active_window", lambda: {"monitor": 0})
    assert hypr.monitor_toward(-1, -1) == "DP-2"      # bottom right to top left
    assert hypr.monitor_toward(1, -1) == "DP-3"
    assert hypr.monitor_toward(1, 0) is None           # nothing to the right
    assert hypr.monitor_toward(-1, -0.02) is None      # sideways on the bottom monitor: stays there
    monkeypatch.setattr(hypr, "active_window", lambda: {"monitor": 1})
    assert hypr.monitor_toward(1, 0) == "DP-3"
    assert hypr.monitor_toward(0, 1) == "DP-1"
    assert hypr.monitor_toward(-0.3, 1) == "DP-1"      # a bit to the left: still down
    # A window on the right half of the bottom monitor goes up to the right one.
    monkeypatch.setattr(hypr, "active_window", lambda: {"monitor": 0, "at": [2600, 1300], "size": [1200, 800]})
    assert hypr.monitor_toward(0, -1) == "DP-3"
    # Fullscreen in the middle: the side the hand is on decides.
    monkeypatch.setattr(hypr, "active_window", lambda: {"monitor": 0, "at": [0, 1152], "size": [4096, 1152]})
    assert hypr.monitor_toward(0.05, -1, hand_x=0.3) == "DP-2"
    assert hypr.monitor_toward(-0.05, -1, hand_x=0.7) == "DP-3"


def test_swipe_snaps_to_eight_directions():
    assert actions.snap(1, 0.2) == (1, 0)          # 11°: straight
    assert actions.snap(1, -0.4) == (1, -1)        # 22°: diagonal
    assert actions.snap(-0.1, -1) == (0, -1)       # straight up
    assert actions.snap(-0.5, -1) == (-1, -1)
