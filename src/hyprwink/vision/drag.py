"""Grab – drag – release, like on a touch screen, for an action that takes a
direction (gestures.DIRECTION_ACTIONS, e.g. "move window in swipe direction").

The gesture is a hand shape, recorded held like a pose with one hand
(samples.json: {"g…": {"kind": "swipe", "hands": {"Left": [[…], …]}}}).

- Grab: that hand shows the shape, held still for GRAB_S.
- Drag: the hand moves, at any speed (a blurred hand may be lost or look
  different for a moment).
- Release: the hand shows another shape and has slowed down: the gesture
  counts, with the direction from where it was grabbed to where it was
  released (if at least MIN_DRAG long).
- The hand leaves the picture: nothing happens (lowering the hand).

Raising or lowering the hand, or moving it in that shape without grabbing,
does nothing. While grabbed and shortly after, hand shape gestures do not
count (releasing passes through other shapes).
"""

import numpy as np

from . import features

SHAPE = features.SHAPE   # only the hand's shape counts, not where the fingers point
ACCEPT = 0.9         # distance of the hand's shape to the recording
GRAB_S = 0.2         # the shape held this long grabs
STILL = 0.5          # ... moving less than this (palm lengths)
RELEASE_S = 0.12     # another shape this long releases
SLOW = 1.5           # ... with the hand slower than this (palm lengths per second)
LOST_S = 0.3         # the hand gone this long: cancelled
MIN_DRAG = 1.5       # palm lengths from grab to release
PAUSE_S = 1.0        # no hand shape gestures this long after a release


def position(hand):
    """Centre (x scaled by the aspect ratio) and palm length of a hand."""
    img = hand["img"] * [hand["aspect"], 1]
    return img[[0, 5, 9, 13, 17]].mean(axis=0), float(np.linalg.norm(img[9] - img[0])) or 1e-3


class Drags:
    def __init__(self, samples):
        self.shapes = {gid: {label: np.asarray(v, dtype=np.float32)[:, :SHAPE] for label, v in value["hands"].items()
                             if v}
                       for gid, value in samples.items()
                       if value.get("kind") == "swipe" and value.get("hands") and features.current(value)}
        self.candidate = None    # (gid, label, since, start position, palm)
        self.grab = None         # see update()
        self.ended = float("-inf")

    def __bool__(self):
        return bool(self.shapes)

    def busy(self, t):
        """Grabbed or just released: no hand shape gestures now."""
        return self.grab is not None or t - self.ended < PAUSE_S

    def grabbed(self):
        """(gesture, hand) while grabbed, else None."""
        return (self.grab["gid"], self.grab["label"]) if self.grab else None

    def _fits(self, gid, label, hand):
        recorded = self.shapes[gid].get(label)
        if recorded is None:
            return False
        return float(np.linalg.norm(recorded - hand["vector"][:SHAPE], axis=1).min()) <= ACCEPT

    def update(self, t, hands):
        """hands: {label: hand} of this frame. Returns {"gesture", "direction"
        (dx, dy in the image, y down, the larger one 1), "x" (where across the
        image the hand was released, 0 left … 1 right)} on a release, else None."""
        if self.grab is not None:
            return self._dragging(t, hands)
        for gid, recorded in self.shapes.items():
            for label, hand in hands.items():
                if label not in recorded or not self._fits(gid, label, hand):
                    continue
                pos, palm = position(hand)
                c = self.candidate
                if c is None or c[:2] != (gid, label) or np.linalg.norm(pos - c[3]) / c[4] > STILL:
                    self.candidate = (gid, label, t, pos, palm)
                elif t - c[2] >= GRAB_S:
                    self.grab = {"gid": gid, "label": label, "start": c[3], "palm": c[4], "last": pos,
                                 "prev": pos, "seen": t, "off": None, "aspect": hand["aspect"]}
                    self.candidate = None
                return None
        self.candidate = None
        return None

    def _dragging(self, t, hands):
        g = self.grab
        hand = hands.get(g["label"])
        if hand is None:
            if t - g["seen"] > LOST_S:          # gone: cancelled
                self.grab, self.ended = None, t
            return None
        pos, _palm = position(hand)
        speed = float(np.linalg.norm(pos - g["prev"])) / g["palm"] / max(t - g["seen"], 1e-3)
        g["seen"], g["prev"] = t, pos
        if self._fits(g["gid"], g["label"], hand):
            g["last"], g["off"] = pos, None
            return None
        if speed > SLOW:                         # blurred while moving fast: not let go
            g["off"] = None
            return None
        g["off"] = g["off"] or t
        if t - g["off"] < RELEASE_S:
            return None
        self.grab, self.ended = None, t
        way = (g["last"] - g["start"]) / g["palm"]
        if float(np.linalg.norm(way)) < MIN_DRAG:
            return None
        direction = way / float(np.abs(way).max())
        return {"gesture": g["gid"], "direction": [round(float(c), 3) for c in direction],
                "x": round(float(g["last"][0]) / g["aspect"], 3)}
