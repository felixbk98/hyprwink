import numpy as np

from hyprwink.vision import drag, features

GRAB = np.zeros(features.SIZE, dtype=np.float32)
OTHER = np.full(features.SIZE, 1.0, dtype=np.float32)
FPS = 30


def _hand(x, y, vector):
    img = np.zeros((21, 2))
    img[:] = (x, y)
    img[9] = (x, y - 0.1)           # palm length 0.1
    return {"img": img, "aspect": 1.0, "vector": vector}


def _run(d, steps, t=0.0):
    """steps: [(frames, x0, y0, x1, y1, vector or None)] -> results, time."""
    out = []
    for n, x0, y0, x1, y1, vector in steps:
        for i in range(n):
            f = i / max(n - 1, 1)
            hands = {} if vector is None else {"Left": _hand(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, vector)}
            r = d.update(t, hands)
            if r:
                out.append(r)
            t += 1 / FPS
    return out, t


def drags():
    return drag.Drags({"g": {"kind": "swipe", "hands": {"Left": [GRAB.tolist()] * 20}}})


def test_grab_drag_release():
    out, _ = _run(drags(), [(10, 0.5, 0.5, 0.5, 0.5, GRAB),      # grab: held still
                            (8, 0.5, 0.5, 0.2, 0.5, GRAB),       # drag to the left, fast
                            (8, 0.2, 0.5, 0.2, 0.5, OTHER)])     # release: another shape
    assert len(out) == 1 and out[0]["gesture"] == "g"
    assert out[0]["direction"] == [-1.0, 0.0]


def test_lowering_the_hand_does_nothing():
    out, _ = _run(drags(), [(10, 0.5, 0.5, 0.5, 0.5, GRAB),
                            (8, 0.5, 0.5, 0.5, 0.9, GRAB),       # lowered in the grab shape
                            (20, 0, 0, 0, 0, None)])             # and gone
    assert out == []


def test_moving_without_grabbing_does_nothing():
    out, _ = _run(drags(), [(10, 0.5, 0.9, 0.5, 0.3, GRAB),      # raised, never held still
                            (8, 0.5, 0.3, 0.5, 0.3, OTHER)])
    assert out == []


def test_short_drag_does_nothing():
    out, _ = _run(drags(), [(10, 0.5, 0.5, 0.5, 0.5, GRAB),
                            (5, 0.5, 0.5, 0.52, 0.5, GRAB),
                            (8, 0.52, 0.5, 0.52, 0.5, OTHER)])
    assert out == []
