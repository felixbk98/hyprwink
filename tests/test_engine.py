import pytest

from hyprwink import gestures
from hyprwink.core import engine as engine_mod

GESTURES = {"gestures": [
    {"id": "a", "name": "Daumen", "action": {"type": "builtin", "value": "dictate_start"}},
    {"id": "b", "name": "Faust", "action": {"type": "key", "value": "CTRL+C"}},
    {"id": "c", "name": "Wunsch", "action": {"type": "wish", "value": "irgendwas"}},
]}


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(engine_mod.time, "monotonic", lambda: now[0])
    return now


@pytest.fixture
def engine(monkeypatch, clock):
    monkeypatch.setattr(gestures, "load", lambda: GESTURES)
    e = engine_mod.Engine()
    e.ran = []
    e.actions.run = e.ran.append
    e.set_paused(False)
    return e


def frame(e, *held):
    e.on_frame({"t": 0, "gestures": {g: {} for g in held if g}})


def test_action_once_per_gesture(engine, clock):
    frame(engine, "a")
    frame(engine, "a")
    frame(engine, None)
    frame(engine, "b")
    assert engine.ran == [{"type": "builtin", "value": "dictate_start"}, {"type": "key", "value": "CTRL+C"}]


def test_flicker(engine, clock):
    frame(engine, "a")
    for held in ["", "a", "", "a"]:     # dropouts
        clock[0] += 0.2
        frame(engine, held)
    assert engine.ran == [{"type": "builtin", "value": "dictate_start"}]
    clock[0] += 1.5
    frame(engine, None)
    frame(engine, "a")
    assert len(engine.ran) == 2


def test_wish_does_nothing_yet(engine):
    frame(engine, "c")
    assert engine.ran == [] and engine.status["action"].startswith("Wish")


def test_paused_does_nothing(engine):
    engine.set_paused(True)
    frame(engine, "a")
    assert engine.ran == []


def test_setup_blocks_actions(engine):
    engine.set_holding(True)
    frame(engine, "a")
    assert engine.ran == []


def test_two_gestures_at_once(engine):
    frame(engine, "a", "b")
    assert len(engine.ran) == 2
    frame(engine, "a")
    assert len(engine.ran) == 2


def test_camera_state_in_status(engine):
    engine.on_frame({"t": 0, "gestures": {}, "camera": False})
    assert engine.status["camera"] is False


def test_gaze_dot_disappears_when_switched_off(engine):
    engine.show_gaze = True
    engine._show_gaze((100, 200))
    assert engine.status["gaze"] == [100, 200]
    engine.show_gaze = False
    engine._show_gaze((120, 200))
    assert engine.status["gaze"] is None
