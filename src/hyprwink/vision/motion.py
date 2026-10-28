"""Movement gestures: a hand shape plus the way the hand(s) move.

A movement starts when the hands start moving and ends when they stop (or
leave the picture), so lowering the hands afterwards is not part of it.
It is described by the path of each hand (resampled in time, relative to
where it started, scaled to the size of the whole movement, so the same
movement made faster, slower, bigger or smaller looks alike) and the hand
shape at its start.

samples.json: {"g…": {"kind": "motion", "takes": [{"Left": {"path": [[x, y], …],
"shape": […]}, "Right": {…}}, …]}}; the user makes the movement TAKES times
while recording.
"""

from collections import deque

import numpy as np

from . import features

POINTS = 16          # points per path
TAKES = 3            # movements made while recording
MIN_TAKES = 2        # fewer found: the recording failed
START_SPEED = 1.6    # palm lengths per second: the hands start moving
STOP_SPEED = 0.8     # below: they stopped
STOP_S = 0.12        # ... for this long
LOST_S = 0.1         # no hands for this long also ends a movement
MIN_S, MAX_S = 0.15, 2.5
MIN_TRAVEL = 1.5     # palm lengths the hands must travel
PRE_S = 0.15         # the still moment before the start is part of it (start shape)
PATH_ACCEPT = 0.5    # mean distance of the paths (in sizes of the movement)
SHAPE_ACCEPT = 1.1   # distance of the start shapes (feature units)
MARGIN = 0.75        # the best gesture must be this much closer than the second
HAND_SEEN = 0.4      # a hand takes part if seen in this share of the frames (two hands
                     # touching often hide one of them)
READY_S = 0.3        # hands still this long: ready to start a movement
SAME_TAKE = 1.5      # while recording, a movement counts as another take if its path is
                     # this close (× PATH_ACCEPT) to the first one; else it was the way back


def _hand(hand):
    """Position (x scaled by the aspect ratio) and palm length of a hand."""
    img = hand["img"] * [hand["aspect"], 1]
    return img[[0, 5, 9, 13, 17]].mean(axis=0), float(np.linalg.norm(img[9] - img[0])) or 1e-3


class Segmenter:
    """Cuts movements out of the stream of frames."""

    def __init__(self):
        self.history = deque()       # (t, {label: (position, palm, vector)})
        self.start = None            # time the current movement started
        self.slow_since = None
        self.seen = 0.0              # last time hands were seen
        self.fast = 0.0              # last time they moved

    def update(self, t, hands):
        """hands: {label: hand} of this frame. Returns a finished movement
        [(t, {label: (position, palm, vector)})] or None."""
        frame = {label: (*_hand(h), h["vector"]) for label, h in hands.items()}
        if frame:
            self.seen = t
        prev = self.history[-1] if self.history else None
        self.history.append((t, frame))
        while self.history and t - self.history[0][0] > MAX_S + PRE_S + 0.5:
            self.history.popleft()
        speed = self._speed(prev, (t, frame))
        if speed >= STOP_SPEED:
            self.fast = t
        if self.start is None:
            if speed > START_SPEED:
                self.start, self.slow_since = t - PRE_S, None
            return None
        if t - self.start > MAX_S + PRE_S:
            self.start = None        # too long: not a gesture
            return None
        ended = t - self.seen > LOST_S
        if speed < STOP_SPEED:
            self.slow_since = self.slow_since or t
            ended = ended or t - self.slow_since >= STOP_S
        else:
            self.slow_since = None
        if not ended:
            return None
        frames = [(ft, f) for ft, f in self.history if self.start <= ft <= t and f]
        self.start = None
        return frames if self._valid(frames) else None

    def phase(self, t):
        """"nohands", "wait" (hands moving about), "ready" (still) or "moving"."""
        if self.start is not None:
            return "moving"
        if t - self.seen > LOST_S:
            return "nohands"
        return "ready" if t - self.fast >= READY_S else "wait"

    @staticmethod
    def _speed(prev, cur):
        if prev is None or cur[0] <= prev[0]:
            return 0.0
        dt = cur[0] - prev[0]
        speeds = [np.linalg.norm(cur[1][label][0] - prev[1][label][0]) / cur[1][label][1] / dt
                  for label in cur[1] if label in prev[1]]
        return max(speeds, default=0.0)

    @staticmethod
    def _valid(frames):
        if len(frames) < 4 or not MIN_S <= frames[-1][0] - frames[0][0] <= MAX_S + PRE_S:
            return False
        travel = 0.0
        for label in frames[0][1]:
            pts = [(f[label][0], f[label][1]) for _, f in frames if label in f]
            if len(pts) > 1:
                palm = np.mean([p for _, p in pts])
                travel = max(travel, sum(np.linalg.norm(b[0] - a[0]) for a, b in zip(pts, pts[1:])) / palm)
        return travel >= MIN_TRAVEL


def describe(frames):
    """A finished movement as {label: {"path", "shape"}} for the hands that
    took part (seen in HAND_SEEN of its frames), or None."""
    counts = {}
    for _, f in frames:
        for label in f:
            counts[label] = counts.get(label, 0) + 1
    labels = sorted(label for label, n in counts.items() if n >= HAND_SEEN * len(frames))
    if not labels:
        return None
    paths, shapes = {}, {}
    for label in labels:
        own = [(t, f[label]) for t, f in frames if label in f]
        times = np.array([t for t, _ in own])
        pos = np.array([p[0] for _, p in own])
        grid = np.linspace(times[0], times[-1], POINTS)
        path = np.stack([np.interp(grid, times, pos[:, 0]), np.interp(grid, times, pos[:, 1])], axis=1)
        paths[label] = path - path[0]
        first = own[:max(1, len(own) // 3)]
        shapes[label] = np.mean([p[2] for _, p in first], axis=0)
    size = max(float(np.abs(p).max()) for p in paths.values())
    if size < 1e-6:
        return None
    # One scale for all hands: with two, which way each one goes tells
    # apart and together.
    return {label: {"path": (paths[label] / size).round(4).tolist(),
                    "shape": np.asarray(shapes[label]).round(4).tolist()} for label in labels}


def _distance(take, movement):
    """(path distance, shape distance) of a recorded take to a movement on
    the take's hands, or None if a hand is missing."""
    if not all(label in movement for label in take):
        return None
    path = np.mean([np.linalg.norm(np.asarray(take[label]["path"]) - np.asarray(movement[label]["path"]), axis=1).mean()
                    for label in take])
    shape = max(float(np.linalg.norm(np.asarray(take[label]["shape"]) - np.asarray(movement[label]["shape"])))
                for label in take)
    return float(path), shape


def same_take(first, movement):
    """While recording: is this movement another take of the first one?"""
    d = _distance(first, movement)
    return d is not None and d[0] <= SAME_TAKE * PATH_ACCEPT


def _score(d):
    return d[0] / PATH_ACCEPT + d[1] / SHAPE_ACCEPT


class Motions:
    def __init__(self, samples):
        self.takes = {gid: value["takes"] for gid, value in samples.items()
                      if value.get("kind") == "motion" and value.get("takes") and features.current(value)}

    def __bool__(self):
        return bool(self.takes)

    def match(self, movement):
        """The gesture of a finished movement, or None. Gestures with more
        hands go first; two that fit about equally: none."""
        found = []
        for gid, takes in self.takes.items():
            fits = [d for d in (_distance(take, movement) for take in takes)
                    if d is not None and d[0] <= PATH_ACCEPT and d[1] <= SHAPE_ACCEPT]
            if fits:
                found.append((-len(takes[0]), min(_score(d) for d in fits), gid))
        if not found:
            return None
        found.sort()
        best = found[0]
        rivals = [f for f in found[1:] if f[0] == best[0]]
        if rivals and best[1] > MARGIN * rivals[0][1]:
            return None
        return best[2]

    def lookalikes(self, gid):
        """Movements on the same hands that this one's takes would match: easy to mix up."""
        own = self.takes.get(gid)
        if not own:
            return []
        out = []
        for other, takes in self.takes.items():
            if other == gid or set(takes[0]) != set(own[0]):
                continue
            for take in own:
                d = [_distance(t, take) for t in takes]
                if any(x is not None and x[0] <= PATH_ACCEPT and x[1] <= SHAPE_ACCEPT for x in d):
                    out.append(other)
                    break
        return out
