from hyprwink import config, gestures, paths
from hyprwink.vision import features


def test_examples_on_first_start(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "GESTURES_FILE", tmp_path / "gestures.json")
    monkeypatch.setattr(paths, "SAMPLES_FILE", tmp_path / "samples.json")
    data = gestures.load()
    assert data["gestures"]
    samples = config.load_json(paths.SAMPLES_FILE, {})
    for g in data["gestures"]:
        assert g["name"] == gestures.action_label(g["action"])
        assert features.current(samples[g["id"]])
    # "Delete all gestures": they do not come back.
    gestures.save({"gestures": []})
    assert gestures.load()["gestures"] == []
