import numpy as np

from hyprwink.vision import features
from hyprwink.vision.templates import Templates
from handmodel import ALL, curled, hand

rng = np.random.default_rng(1)
HALF = (45, 45, 30)
POINT = dict(fingers=curled("middle", "ring", "pinky"), thumb="raised", tilt=90)
FIST = dict(fingers=curled(*ALL), thumb="across")
THUMB = dict(fingers=curled(*ALL), thumb="up")
OPEN = dict()


def vec(**kw):
    world, img = hand(**kw)
    return features.vector(world, img)


def samples(n=30, **kw):
    """Recordings with a bit of jitter, like a real hand."""
    world, img = hand(**kw)
    return [features.vector(world + rng.normal(0, 0.002, world.shape), img).tolist() for _ in range(n)]


def one(label, **kw):
    return {"hands": {label: samples(**kw)}}


def model():
    return Templates({"point": one("Right", **POINT), "fist": one("Right", **FIST),
                      "thumb": one("Right", **THUMB), "open": one("Right", **OPEN)})


def test_recognises_recorded_gestures():
    m = model()
    for name, kw in (("point", POINT), ("fist", FIST), ("thumb", THUMB), ("open", OPEN)):
        assert m.match({"Right": vec(**kw)}) == {name: ["Right"]}


def test_wrong_hand_does_not_match():
    assert model().match({"Left": vec(**FIST)}) == {}


def test_unknown_hand_is_nothing():
    odd = dict(fingers={"index": HALF, "middle": HALF, "ring": (90, 90, 60), "pinky": HALF}, thumb="side")
    assert model().match({"Right": vec(**odd)}) == {}


def test_two_hand_gesture_needs_both_and_wins():
    m = Templates({"pray": {"hands": {"Left": samples(**OPEN), "Right": samples(**OPEN)}},
                   "open": one("Right", **OPEN)})
    assert m.match({"Left": vec(**OPEN), "Right": vec(**OPEN)}) == {"pray": ["Left", "Right"]}
    assert m.match({"Right": vec(**OPEN)}) == {"open": ["Right"]}


def test_both_hands_do_different_things():
    m = Templates({"left_fist": one("Left", **FIST), "right_thumb": one("Right", **THUMB)})
    assert m.match({"Left": vec(**FIST), "Right": vec(**THUMB)}) == {"left_fist": ["Left"],
                                                                     "right_thumb": ["Right"]}


def test_lookalike_gestures_are_reported():
    m = Templates({"a": one("Right", **FIST), "b": one("Right", **FIST), "c": one("Left", **FIST)})
    assert m.lookalikes("b") == ["a"]
    assert model().lookalikes("point") == []


def test_no_samples_no_recognition():
    assert Templates({}).match({"Right": vec()}) == {}



def test_hand_at_the_edge():
    from hyprwink.vision.features import at_edge
    assert not at_edge(np.array([[0.4, 0.5], [0.5, 0.7]]))
    assert at_edge(np.array([[0.4, 0.8], [0.5, 0.995]]))     # lowered, cut off below


def test_direction_counts():
    from hyprwink.vision.templates import ACCEPT
    world, img = hand(**POINT)
    turned = img @ np.array([[0, 1], [-1, 0]])           # the same hand turned by 90° in the image
    a, b = features.vector(world, img), features.vector(world, turned)
    assert len(a) == features.SIZE
    assert np.linalg.norm(a - b) > ACCEPT
    assert np.allclose(a[:11], b[:11], atol=0.05)        # same shape (thumb_up is a direction too)
