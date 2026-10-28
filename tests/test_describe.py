from hyprwink.vision import describe, features
from handmodel import ALL, curled, hand


def text(**kw):
    world, img = hand(**kw)
    v = features.vector(world, img)
    return describe.shape([v, v])


def test_shapes():
    assert text().startswith("open hand")
    assert text(fingers=curled(*ALL), thumb="across") == "fist"
    assert text(fingers=curled(*ALL), thumb="up") == "thumbs up"
    assert text(fingers=curled(*ALL), thumb="down") == "thumbs down"
    assert text(fingers=curled(*ALL), thumb="side") == "fist, thumb out to the side"
    assert text(fingers=curled("ring", "pinky"), thumb="press").startswith("index finger and middle finger stretched")
    assert text(fingers={"index": (40, 60, 40)}, thumb="pinch") == "OK sign"


def test_two_hands():
    world, img = hand()
    v = features.vector(world, img).tolist()
    # MediaPipe's labels are swapped by the mirror image.
    shape = describe.shape([v])
    assert describe.describe({"Right": [v], "Left": [v]}) == f"right hand: {shape} · left hand: {shape}"


def test_relaxed_open_hand_from_a_real_recording():
    # Measured on a real open hand: fingers bent 74, 54, 51, 62 degrees.
    v = [74 / 180, 54 / 180, 51 / 180, 62 / 180, 23 / 180, 0.51, 0.6, 0.5, 0.6, 0.5, 0.5, 0.98]
    assert describe.shape([v]).startswith("open hand")


def test_v_apart_or_side_by_side():
    base = [40 / 180, 40 / 180, 220 / 180, 220 / 180, 100 / 180, 1.0, 0.8, 0.4, 0.4]
    apart = base + [0.6, 0.5, 0.2]
    together = base + [0.25, 0.5, 0.2]
    assert describe.shape([apart]) == "index finger and middle finger stretched, spread"
    assert describe.shape([together]) == "index finger and middle finger stretched, together"


def test_thumb_stretched_out_counts():
    # Measured "three": thumb 22°, 0.88 from the middle finger's base.
    v = [52 / 180, 36 / 180, 1.0, 1.0, 22 / 180, 0.82, 1.22, 0.57, 0.88, 0.44, 1.27, 0.85]
    assert describe.shape([v]) == "thumb, index finger and middle finger stretched, spread"


def test_four_fingers_thumb_folded():
    # Measured: fingers 55, 47, 29, 47°, thumb 90°.
    v = [55 / 180, 47 / 180, 29 / 180, 47 / 180, 90 / 180, 0.93, 1.01, 0.7, 0.71, 0.5, 0.5, 0.55]
    assert describe.shape([v]) == "four fingers stretched, thumb folded in"
    v[4] = 40 / 180
    assert describe.shape([v]).startswith("open hand")


def test_open_hand_spread_or_closed():
    # Measured: tips index–middle / middle–ring 0.40 + 0.42 vs 0.30 + 0.25.
    v = [72 / 180, 55 / 180, 47 / 180, 74 / 180, 20 / 180, 0.6, 0.9, 0.5, 1.08, 0.40, 0.42, 0.9]
    assert describe.shape([v]) == "open hand, fingers spread"
    v[9], v[10] = 0.30, 0.25
    assert describe.shape([v]) == "open hand, fingers together"
