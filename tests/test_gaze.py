import numpy as np

from hyprwink.core import gazefocus
from hyprwink.vision import gaze


def _rot(yaw, pitch):
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    return ry @ rx


def _sample(target_cm, head_pos, head_share, rng):
    """Features of someone at head_pos looking at a point on the plane z = 0."""
    gaze_dir = np.array([*target_cm, 0.0]) - head_pos
    gaze_dir /= np.linalg.norm(gaze_dir)
    # Face looks along +z towards the camera; the eyes do the rest.
    yaw = np.arctan2(gaze_dir[0], gaze_dir[2]); pitch = np.arcsin(gaze_dir[1])
    r = _rot(yaw * head_share, -pitch * head_share)
    eye_yaw, eye_pitch = yaw * (1 - head_share), pitch * (1 - head_share)
    iris = np.array([eye_yaw / 2.0, eye_pitch / 2.5]) + rng.normal(0, 0.002, 2)
    # Check with the model's own geometry: the eye turns within the head.
    return np.concatenate([r.ravel(), head_pos, iris])


LOWER = {"name": "DP-1", "rect": [0, 1152, 4096, 1152], "round": 1}
UPPER = {"name": "DP-2", "rect": [0, 0, 4096, 1152], "round": 1}


def _px(cm):
    """Layout px of a point on the plane. The upper monitor is tilted: its
    scale differs from the lower one, which one affine map cannot cover."""
    if cm[1] > 20:
        return np.array([cm[0] * 34 + 2048, 1100 - (cm[1] - 20) * 30]), UPPER
    return np.array([cm[0] * 40 + 2048, 1152 + (20 - cm[1]) * 40]), LOWER


def _calibration(rng):
    samples = []
    for cm in [(x, y) for x in (-50, 0, 50) for y in (-5, 8, 18, 25, 40, 55)]:
        px, monitor = _px(cm)
        for _ in range(20):
            head = np.array([0, 0, -60]) + rng.normal(0, 1.5, 3)
            samples.append((_sample(cm, head, 0.6, rng), tuple(px), monitor))
    return samples


def test_ray_model_survives_sitting_elsewhere():
    rng = np.random.default_rng(1)
    model, error = gaze.fit(_calibration(rng))
    assert error < 40
    # Now 12 cm further left and 10 cm further back.
    for cm in [(20, 10), (-30, 45)]:
        g = gaze.Gaze(model)
        point = g.update(_sample(cm, np.array([-12, 0, -70]), 0.6, rng))
        assert np.linalg.norm(point - _px(cm)[0]) < 150



def test_blink_keeps_the_last_point():
    rng = np.random.default_rng(2)
    model, _ = gaze.fit(_calibration(rng))
    g = gaze.Gaze(model)
    first = g.update(_sample((0, 10), np.array([0, 0, -60]), 0.6, rng))
    assert np.array_equal(g.update("blink"), first)


def test_outliers_are_dropped():
    rng = np.random.default_rng(3)
    samples = _calibration(rng)
    bad = [(np.concatenate([f[:12], f[12:] + 0.5]), p, m) for f, p, m in samples[5:8]]
    assert len(gaze.clean(samples[:20] + bad)) < 20


def test_focus_after_dwell(monkeypatch):
    wins = [{"address": "a", "at": (0, 0), "size": (1000, 1000), "focusHistoryID": 0},
            {"address": "b", "at": (1000, 0), "size": (1000, 1000), "focusHistoryID": 1}]
    focused = []
    monkeypatch.setattr(gazefocus.hypr, "windows", lambda: wins)
    monkeypatch.setattr(gazefocus.hypr, "monitors", lambda: {})
    monkeypatch.setattr(gazefocus.hypr, "focus", focused.append)
    monkeypatch.setattr(gazefocus.hypr, "cursor", lambda: None)
    f = gazefocus.GazeFocus()
    f.update((1500, 500), now=1.0)
    f.update((1500, 500), now=1.1)
    assert focused == []                 # just a glance
    f.update((1500, 500), now=1.4)
    assert focused == ["b"]
    f.update((500, 500), now=1.5)
    f.update((1500, 500), now=1.6)       # back before the dwell ended
    assert focused == ["b"]


def test_other_monitor_needs_more(monkeypatch):
    """Lower monitor focused; the upper one counts only well inside it and
    after twice the dwell."""
    wins = [{"address": "low", "at": (0, 1000), "size": (2000, 1000), "focusHistoryID": 0, "monitor": 0},
            {"address": "up", "at": (0, 0), "size": (2000, 1000), "focusHistoryID": 1, "monitor": 1}]
    focused = []
    monkeypatch.setattr(gazefocus.hypr, "windows", lambda: wins)
    monkeypatch.setattr(gazefocus.hypr, "monitors", lambda: {0: (0, 1000, 2000, 1000), 1: (0, 0, 2000, 1000)})
    monkeypatch.setattr(gazefocus.hypr, "focus", focused.append)
    monkeypatch.setattr(gazefocus.hypr, "cursor", lambda: None)
    f = gazefocus.GazeFocus()
    for i in range(10):
        f.update((500, 900), now=1.0 + i * 0.1)    # just above the border
    assert focused == []
    f.update((500, 700), now=3.0)
    f.update((500, 700), now=3.4)
    assert focused == []                           # 0.4 s < 2 × 0.3 s
    f.update((500, 700), now=3.7)
    assert focused == ["up"]


def test_correction_from_pointer(monkeypatch):
    monkeypatch.setattr(gazefocus.hypr, "windows", lambda: [])
    monkeypatch.setattr(gazefocus.hypr, "monitors", lambda: {})
    pos = {"p": (0, 0)}
    monkeypatch.setattr(gazefocus.hypr, "cursor", lambda: pos["p"])
    f = gazefocus.GazeFocus()
    t = 0.0
    for i in range(60):
        pos["p"] = (1000 + (i % 2) * 100, 500)     # pointer moving around x≈1050
        t += 0.3
        f.update((850, 500), now=t)              # estimate 200 px too far left
    assert 150 < f.correction[0] < 250


def test_mouse_pauses_gaze(monkeypatch):
    wins = [{"address": "a", "at": (0, 0), "size": (1000, 1000), "focusHistoryID": 0},
            {"address": "b", "at": (1000, 0), "size": (1000, 1000), "focusHistoryID": 1}]
    focused = []
    pos = {"p": (100, 100)}
    monkeypatch.setattr(gazefocus.hypr, "windows", lambda: wins)
    monkeypatch.setattr(gazefocus.hypr, "monitors", lambda: {})
    monkeypatch.setattr(gazefocus.hypr, "focus", focused.append)
    monkeypatch.setattr(gazefocus.hypr, "cursor", lambda: pos["p"])
    f = gazefocus.GazeFocus()
    t = 1.0
    for i in range(10):                      # mouse moving, gaze on b
        pos["p"] = (100 + i * 10, 100)
        f.update((1500, 500), now=t)
        t += 0.12
    assert focused == []
    for _ in range(10):                      # mouse still: gaze takes over
        f.update((1500, 500), now=t)
        t += 0.12
    assert focused == ["b"]
