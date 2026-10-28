"""Synthetic hands for tests: 21 landmarks built from joint angles.

The hand faces the camera with the fingers up (image y points down, the
camera looks along +z, so -z is towards the camera).
"""

import numpy as np

MCP = {"index": (-0.03, -0.09), "middle": (-0.01, -0.095), "ring": (0.01, -0.09), "pinky": (0.03, -0.08)}
LENGTHS = (0.045, 0.025, 0.02)
THUMB = (0.045, 0.035, 0.03)
START = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}
STRAIGHT = (0, 0, 0)
CURLED = (85, 100, 60)


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def _chain(start, base_dir, bends, lengths, bend_axis_dir):
    """Points of a finger: each joint turns the direction towards bend_axis_dir."""
    points = []
    p = np.asarray(start, dtype=float)
    d = _unit(base_dir)
    toward = _unit(bend_axis_dir)
    angle = 0.0
    for bend, length in zip(bends, lengths):
        angle += np.radians(bend)
        direction = _unit(np.cos(angle) * d + np.sin(angle) * toward)
        p = p + direction * length
        points.append(p)
    return points


def hand(fingers=None, thumb="side", tilt=0):
    """fingers: name -> joint bends in degrees; thumb: side, up, down, raised, across, press, pinch."""
    fingers = fingers or {}
    w = np.zeros((21, 3))
    for name, start in START.items():
        mx, my = MCP[name]
        w[start] = (mx, my, 0)
        bends = fingers.get(name, STRAIGHT)
        w[start + 1:start + 4] = _chain(w[start], (0, -1, 0), bends, LENGTHS, (0, 0, -1))
    w[1] = (-0.035, -0.025, -0.005)
    if thumb == "side":
        w[2:5] = _chain(w[1], (-1, -0.6, -0.2), STRAIGHT, THUMB, (0, 0, -1))
    elif thumb == "up":
        w[2:5] = _chain(w[1], (-0.15, -1, -0.1), STRAIGHT, THUMB, (0, 0, -1))
    elif thumb == "down":
        w[2:5] = _chain(w[1], (-0.15, 1, -0.1), STRAIGHT, THUMB, (0, 0, -1))
    elif thumb == "raised":
        # Pistol: thumb on top, away from the fingers (for tilt=90).
        w[2:5] = _chain(w[1], (-0.4, -0.3, 1), STRAIGHT, THUMB, (0, 0, -1))
    elif thumb == "across":
        w[2:5] = _chain(w[1], (0.6, -0.6, -0.6), (0, 25, 0), (0.03, 0.03, 0.025), (1, 0, 0))
    elif thumb in ("press", "pinch"):
        target = w[6] if thumb == "press" else w[8]
        w[2] = w[1] + (target - w[1]) * 0.4
        w[3] = w[1] + (target - w[1]) * 0.75
        w[4] = target + np.array([0, 0, -0.005])
    if tilt:
        # Tilt 90°: the stretched fingers point at the camera.
        w = rotate_x(w, tilt)
    img = w[:, :2] * 3 + 0.5
    return w, img


def rotate_x(points, degrees):
    a = np.radians(degrees)
    r = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    return points @ r.T


def curled(*names):
    return {n: CURLED for n in names}


ALL = ("index", "middle", "ring", "pinky")

