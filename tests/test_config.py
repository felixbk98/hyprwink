from hyprwink import config, gestures


def test_defaults_load():
    cfg = config.load_config()
    assert cfg["camera"]["width"] == 1280


def test_action_labels():
    assert gestures.action_label({"type": "builtin", "value": "dictate_send"}) == "Stop dictation and send"
    assert gestures.action_label({"type": "key", "value": "CTRL+SHIFT+C"}) == "Key: Ctrl+Shift+C"
    assert gestures.action_label({"type": "wish", "value": "x"}) == "Wish: x"


def test_speed_slider_has_normal_speed_in_the_middle():
    from hyprwink.ui.settings_page import _slider_to_speed, _speed_to_slider
    assert _slider_to_speed(0) == 1.0
    assert _slider_to_speed(-1) == 0.5
    assert _slider_to_speed(1) == 2.5
    assert abs(_speed_to_slider(1.75) - 0.5) < 1e-9
