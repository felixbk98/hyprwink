from hyprwink import config
from hyprwink.vision.tracker import Tracker

FPS = 30


def feed(tracker, gesture, frames, start=0.0, dx=0.0):
    t, stable = start, set()
    for i in range(frames):
        present = {gesture: (0.5 + dx * i, 0.5)} if gesture else {}
        stable = tracker.update(t, present)
        t += 1 / FPS
    return t, stable


def tracker():
    return Tracker(config.load_config())


def test_gesture_needs_hold_time():
    tr = tracker()
    t, stable = feed(tr, "a", 3)
    assert stable == set()
    _, stable = feed(tr, "a", 5, start=t)
    assert stable == {"a"}


def test_gesture_requires_stillness():
    _, stable = feed(tracker(), "a", 15, dx=0.03)
    assert stable == set()


def test_short_dropout_keeps_gesture_long_one_ends_it():
    tr = tracker()
    t, _ = feed(tr, "a", 10)
    t, stable = feed(tr, None, 4, start=t)
    assert stable == {"a"}
    _, stable = feed(tr, None, 10, start=t)
    assert stable == set()

