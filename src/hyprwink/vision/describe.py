"""Plain-language description of a recorded hand shape, for checking only.

Made by fixed rules from the feature vectors (see features.vector): how far
each finger is bent and where the thumb is. Recognition does not use it.
"""

import numpy as np

from ..i18n import N_, _

FINGERS = [N_("index finger"), N_("middle finger"), N_("ring finger"),
           N_("little finger")]
# The image is mirrored, so MediaPipe's labels are swapped: its "Left" is the
# user's right hand. Recognition only needs them consistent; this is for text.
SIDE = {"Left": N_("right hand"), "Right": N_("left hand")}
# Total bend over a finger's three joints (degrees / 180, as in the vector).
# A relaxed open hand measures about 50–80°, a fist about 240°.
STRETCHED, CURLED = 100 / 180, 160 / 180
# Fingers curled at least this much around a stretched thumb (thumbs up, …).
# Measured: loosely curled 140°; a fist seen from the side looks less curled
# (95–135°), a stretched finger 50–80°.
BENT = 90 / 180
# Index finger this much less bent than the curled others: stretched.
POINTING = 45 / 180
# A thumb gesture's thumb stands away from the hand (tip to the middle
# finger's base). Measured: thumbs up/down 0.8–1.3, thumb along the fist 0.2.
THUMB_OUT = 0.6
# Index and middle fingertip apart (V) or side by side, in palm lengths.
# Measured: V about 0.6, side by side about 0.25.
SPREAD = 0.36
# Thumb stretched out to the side: hardly bent and far from the middle
# finger's base. Measured: out 22° / 0.88, folded in 70–80° / 0.25–0.6.
THUMB_STRAIGHT, THUMB_AWAY = 45, 0.75
# Thumb folded towards the palm. Measured: open hand 23–40°, folded 90°.
THUMB_FOLDED = 65
# Open hand, fingers spread or closed: index–middle plus middle–ring tip
# distance. Measured: spread 0.82, closed 0.55.
OPEN_SPREAD = 0.68


def shape(vectors):
    v = np.median(np.asarray(vectors), axis=0)
    bends, thumb_bend, pinch, spread, thumb_up = v[:4], v[4] * 180, v[5], v[9], v[11]
    thumb_out = thumb_bend < THUMB_STRAIGHT and v[8] > THUMB_AWAY
    up = [b < STRETCHED for b in bends]
    # A finger pointing at the camera or down looks less stretched than it is:
    # the index finger counts as stretched when clearly less bent than the
    # curled others (measured: pointing down 108° against 165°).
    if not up[0] and all(b > CURLED for b in bends[1:]) and bends[0] < min(bends[1:]) - POINTING:
        up[0] = True
    down = [b > CURLED for b in bends]
    if pinch < 0.3:
        if all(up[1:]):
            return _("OK sign")
        return _("thumb and index finger together")
    if all(b > BENT for b in bends) and not up[0] and thumb_bend < 60 and v[8] > THUMB_OUT:
        if thumb_up > 0.6:
            return _("thumbs up")
        if thumb_up < -0.6:
            return _("thumbs down")
        if v[8] > THUMB_AWAY:
            return _("fist, thumb out to the side")
    if all(down):
        return _("fist")
    if all(up):
        if thumb_bend > THUMB_FOLDED:
            return _("four fingers stretched, thumb folded in")
        return _("open hand, fingers spread") if v[9] + v[10] > OPEN_SPREAD \
            else _("open hand, fingers together")
    stretched = ([_("thumb")] if thumb_out else []) + [_(name) for name, u in zip(FINGERS, up) if u]
    if not stretched:
        return _("fingers half bent")
    if len(stretched) == 1:
        return _("{finger} stretched").format(finger=stretched[0])
    text = _("{fingers} and {last} stretched").format(fingers=", ".join(stretched[:-1]), last=stretched[-1])
    if up[0] and up[1]:
        text += _(", spread") if spread > SPREAD else _(", together")
    return text


def describe(hands):
    """hands: {label: [vectors]} -> e.g. "rechte Hand · Faust"."""
    return " · ".join(f"{_(SIDE[label]) if label in SIDE else label}: {shape(vectors)}"
                      for label, vectors in sorted(hands.items()))


DIRECTIONS = {"right": N_("to the right"), "left": N_("to the left"), "up": N_("up"), "down": N_("down")}


def _direction(path):
    dx, dy = path[-1]
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def describe_motion(take):
    """A recorded movement in words, e.g. "both hands: … · apart"."""
    labels = sorted(take)
    shape_text = shape([take[labels[0]]["shape"]])
    if len(labels) == 2:
        # In the mirrored image the user's right hand ("Left") is on the right.
        right_dx, left_dx = take["Left"]["path"][-1][0], take["Right"]["path"][-1][0]
        if right_dx > 0 > left_dx:
            way = _("apart")
        elif right_dx < 0 < left_dx:
            way = _("together")
        else:
            way = _(DIRECTIONS[_direction(take["Left"]["path"])])
        return f"{_('both hands')}: {shape_text} · {way}"
    label = labels[0]
    side = _(SIDE[label]) if label in SIDE else label
    return f"{side}: {shape_text} · {_(DIRECTIONS[_direction(take[label]['path'])])}"


def describe_entry(entry):
    """The description of a gesture's recording in samples.json, or ""."""
    if entry.get("kind") == "motion" and entry.get("takes"):
        return describe_motion(entry["takes"][0])
    if entry.get("kind") == "swipe" and entry.get("hands"):
        label, vectors = next(iter(entry["hands"].items()))
        side = _(SIDE[label]) if label in SIDE else label
        return f"{side}: {shape(vectors)} · {_('grab, drag, let go')}"
    return describe(entry["hands"]) if entry.get("hands") else ""
