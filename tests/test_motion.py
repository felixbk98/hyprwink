import numpy as np

from hyprwink.vision import features, motion

SHAPE = np.zeros(features.SIZE, dtype=np.float32)


def _hand(x, y, vector=SHAPE):
    img = np.zeros((21, 2))
    img[:] = (x, y)
    img[9] = (x, y - 0.1)           # palm length 0.1
    return {"img": img, "aspect": 1.0, "vector": vector}


def _movement(paths, fps=30, still=0.5, move=0.5):
    """paths: {label: (start, end)} -> frames still, moving, still, hands down."""
    frames, t = [], 0.0
    steps = int(move * fps)
    for i in range(int(still * fps)):
        frames.append((t, {k: _hand(*a) for k, (a, b) in paths.items()})); t += 1 / fps
    for i in range(1, steps + 1):
        f = i / steps
        frames.append((t, {k: _hand(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                           for k, (a, b) in paths.items()})); t += 1 / fps
    for i in range(int(still * fps)):
        frames.append((t, {k: _hand(*b) for k, (a, b) in paths.items()})); t += 1 / fps
    for i in range(10):
        frames.append((t, {})); t += 1 / fps        # hands lowered
    return frames


def _segments(frames):
    seg, found = motion.Segmenter(), []
    for t, hands in frames:
        done = seg.update(t, hands)
        movement = motion.describe(done) if done else None
        if movement:
            found.append(movement)
    return found


APART = {"Left": ((0.55, 0.5), (0.85, 0.5)), "Right": ((0.45, 0.5), (0.15, 0.5))}
TOGETHER = {"Left": ((0.85, 0.5), (0.55, 0.5)), "Right": ((0.15, 0.5), (0.45, 0.5))}


def test_one_movement_cut_out():
    found = _segments(_movement(APART))
    assert len(found) == 1 and sorted(found[0]) == ["Left", "Right"]


def test_apart_and_together_told_apart():
    samples = {"apart": {"kind": "motion", "takes": _segments(_movement(APART)) * 3},
               "together": {"kind": "motion", "takes": _segments(_movement(TOGETHER)) * 3}}
    m = motion.Motions(samples)
    assert m.match(_segments(_movement(APART, move=0.3))[0]) == "apart"         # faster
    assert m.match(_segments(_movement(TOGETHER, move=0.8))[0]) == "together"  # slower
    assert m.lookalikes("apart") == []


def test_small_jitter_is_no_movement():
    assert _segments(_movement({"Left": ((0.5, 0.5), (0.52, 0.5))})) == []


def test_description():
    from hyprwink.vision.describe import describe_motion
    take = _segments(_movement(APART))[0]
    assert describe_motion(take).endswith("· apart")
    take = _segments(_movement({"Left": ((0.5, 0.5), (0.5, 0.2))}))[0]
    assert describe_motion(take).startswith("right hand") and describe_motion(take).endswith("· up")


def test_phases_and_way_back():
    seg, phases = motion.Segmenter(), []
    for t, hands in _movement(APART):
        seg.update(t, hands)
        phases.append(seg.phase(t))
    assert phases[12] == "ready" and "moving" in phases and phases[-1] == "nohands"
    apart, together = _segments(_movement(APART))[0], _segments(_movement(TOGETHER))[0]
    assert motion.same_take(apart, _segments(_movement(APART, move=0.3))[0])
    assert not motion.same_take(apart, together)        # the way back
