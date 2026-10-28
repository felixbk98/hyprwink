import json
import zipfile

import pytest

from hyprwink import backup, config, paths


@pytest.fixture(autouse=True)
def no_systemctl(monkeypatch):
    calls = []
    monkeypatch.setattr(backup.subprocess, "run", lambda args, **kw: calls.append(args))
    return calls


def _fill():
    config.save_json(paths.SETTINGS_FILE, {"theme": "omarchy"})
    config.save_json(paths.GESTURES_FILE, {"gestures": [{"id": "g1", "name": "Faust"}]})
    config.save_json(paths.SAMPLES_FILE, {"g1": [[0.1, 0.2]]})
    config.save_json(paths.GAZE_FILE, {"model": {}, "rounds": []})
    (paths.PHOTO_DIR / "g1-clip").mkdir(parents=True, exist_ok=True)
    (paths.PHOTO_DIR / "g1.jpg").write_bytes(b"jpg")
    (paths.PHOTO_DIR / "g1-clip" / "0.jpg").write_bytes(b"frame")


def test_round_trip(tmp_path, no_systemctl):
    _fill()
    target = tmp_path / "out" / "hyprwink.zip"
    backup.save(target)
    config.save_json(paths.SETTINGS_FILE, {"theme": "material"})
    config.save_json(paths.GAZE_SAMPLES, [])         # not in the export: removed by the import
    (paths.PHOTO_DIR / "g2.jpg").write_bytes(b"other")
    backup.load(target)
    assert config.load_json(paths.SETTINGS_FILE, {}) == {"theme": "omarchy"}
    assert config.load_json(paths.GESTURES_FILE, {})["gestures"][0]["name"] == "Faust"
    assert (paths.PHOTO_DIR / "g1-clip" / "0.jpg").read_bytes() == b"frame"
    assert not (paths.PHOTO_DIR / "g2.jpg").exists()
    assert not paths.GAZE_SAMPLES.exists()
    assert not list(paths.CONFIG_DIR.glob(".import-*"))
    assert no_systemctl and "try-restart" in no_systemctl[0]


def _zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


@pytest.mark.parametrize("entries", [
    {"settings.json": "{}"},                                                   # no manifest
    {backup.MANIFEST: '{"app": "other", "format": 1}'},
    {backup.MANIFEST: '{"app": "hyprwink", "format": 99}'},
    {backup.MANIFEST: '{"app": "hyprwink", "format": 1}', "../evil": "x"},
    {backup.MANIFEST: '{"app": "hyprwink", "format": 1}', "bashrc": "x"},
    {backup.MANIFEST: '{"app": "hyprwink", "format": 1}', "settings.json": "{kaputt"},
])
def test_rejects_foreign_files(tmp_path, entries, no_systemctl):
    _fill()
    before = paths.SETTINGS_FILE.read_text()
    with pytest.raises(backup.BackupError):
        backup.load(_zip(tmp_path / "x.zip", entries))
    assert paths.SETTINGS_FILE.read_text() == before
    assert not no_systemctl


def test_not_a_zip(tmp_path):
    (tmp_path / "x.zip").write_text("kein zip")
    with pytest.raises(backup.BackupError):
        backup.load(tmp_path / "x.zip")


def test_manifest(tmp_path):
    backup.save(tmp_path / "x.zip")
    with zipfile.ZipFile(tmp_path / "x.zip") as z:
        assert json.loads(z.read(backup.MANIFEST)) == {"app": "hyprwink", "format": 1}
