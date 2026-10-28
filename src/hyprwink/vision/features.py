"""Hand shape features from MediaPipe landmarks.

world: 21×3 world landmarks (metres, hand-centred, from MediaPipe).
img:   21×2 image landmarks, x scaled by the aspect ratio so both axes use the
       same unit (fraction of the image height), y pointing down.

The features describe the shape of the hand (how far each finger is bent,
where the thumb is) and where each finger points in the image, so the same
finger pointing up or to the side are different gestures. The variation the
user shows while recording sets how much the direction may vary.
"""

import numpy as np

FINGERS = ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
# Base and tip of thumb and fingers, for their direction.
POINTING = ((2, 4), (5, 8), (9, 12), (13, 16), (17, 20))
# Weight of a direction (unit vector) against the shape features: a finger
# turned by 90° adds 0.5, tilted by 20° about 0.12.
DIRECTION_WEIGHT = 0.35
SHAPE = 12           # the features of the shape; the directions follow
SIZE = SHAPE + 2 * len(POINTING)
EDGE = 0.02          # a hand closer to the image's edge than this is cut off


def _angle(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))))


def vector(world, img):
    w = np.asarray(world, dtype=np.float64)
    img = np.asarray(img, dtype=np.float64)
    palm = float(np.linalg.norm(w[9] - w[0])) or 1e-6

    def d(a, b):
        return float(np.linalg.norm(w[a] - w[b])) / palm

    bends = [(_angle(w[m] - w[0], w[p] - w[m]) + _angle(w[p] - w[m], w[q] - w[p])
              + _angle(w[q] - w[p], w[t] - w[q])) / 180 for m, p, q, t in FINGERS]
    thumb_bend = (_angle(w[2] - w[1], w[3] - w[2]) + _angle(w[3] - w[2], w[4] - w[3])) / 180
    thumb_dir = img[4] - img[2]
    thumb_up = float(-thumb_dir[1] / (np.linalg.norm(thumb_dir) or 1e-6))
    return np.array([
        *bends, thumb_bend,
        min(d(4, 8), 2), min(d(4, 12), 2), min(d(4, 6), 2), min(d(4, 10), 2),
        min(d(8, 12), 2), min(d(12, 16), 2), thumb_up,
        *[c for base, tip in POINTING for c in _direction(img[tip] - img[base])],
    ], dtype=np.float32)


def _direction(v):
    n = float(np.linalg.norm(v))
    return (v / n * DIRECTION_WEIGHT).tolist() if n > 1e-9 else [0.0, 0.0]


def current(entry):
    """Whether a recording in samples.json has today's features (older ones are skipped)."""
    if entry.get("kind") == "motion":
        return all(len(hand["shape"]) == SIZE for take in entry.get("takes", []) for hand in take.values())
    return all(len(v) == SIZE for vectors in entry.get("hands", {}).values() for v in vectors[:1])


def at_edge(img):
    """Whether a hand (landmarks as image fractions) reaches the image's edge."""
    return bool((img.min() < EDGE) or (img.max() > 1 - EDGE))
