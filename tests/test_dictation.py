import sys
import threading
import types

import numpy as np

from hyprwink.core import dictation


class FakeStream:
    def __init__(self, callback, **_):
        self.callback = callback

    def start(self):
        data = np.full((dictation.RATE, 1), 1000, dtype=np.int16)   # one second of sound
        self.callback(data, len(data), None, None)

    def stop(self):
        pass

    def close(self):
        pass


def _dictation(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(InputStream=FakeStream))
    monkeypatch.setattr(dictation.paths, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(dictation.paths, "DICTATION_STATE", tmp_path / "dictation")
    monkeypatch.setattr(dictation.stt.LOCAL, "prepare", lambda: None)
    monkeypatch.setattr(dictation.media.Pause, "pause", lambda self: None)
    monkeypatch.setattr(dictation.media.Pause, "resume", lambda self: None)
    lua = []
    monkeypatch.setattr(dictation.hypr, "lua", lua.append)
    states = []
    d = dictation.Dictation({"engine": "whisper", "language": "de"}, lambda s, level, badge: states.append(s))
    done = threading.Event()
    pasted = []
    monkeypatch.setattr(d, "_transcribe", lambda pcm: "Hallo Welt")
    monkeypatch.setattr(d, "_paste", lambda text, send: (pasted.append((text, send)), done.set()))
    return d, lua, states, pasted, done


def test_record_transcribe_paste(monkeypatch, tmp_path):
    d, lua, states, pasted, done = _dictation(monkeypatch, tmp_path)
    d.toggle()
    assert d.state == "recording"
    assert 'hl.bind("Escape"' in lua[-1] and 'hl.bind("Return"' in lua[-1]
    d.stop(send=True)
    assert done.wait(2)
    assert pasted == [("Hallo Welt", True)]
    assert d.state == "idle" and (tmp_path / "dictation").read_text() == "idle\n"
    assert "hl.bind" not in lua[-1]          # Escape and Enter are free again
    assert "transcribing" in states


def test_cancel_drops_the_recording(monkeypatch, tmp_path):
    d, lua, _, pasted, _ = _dictation(monkeypatch, tmp_path)
    d.start()
    d.cancel()
    assert d.state == "idle" and pasted == []
    assert "hl.bind" not in lua[-1]


def test_file_target(monkeypatch, tmp_path):
    d, _, _, pasted, _ = _dictation(monkeypatch, tmp_path)
    target = tmp_path / "prompt.txt"
    d.start(str(target))
    d.stop()
    for _ in range(100):
        if target.exists():
            break
        threading.Event().wait(0.02)
    assert target.read_text() == "Hallo Welt" and pasted == []


def test_keys_freed_at_start(monkeypatch, tmp_path):
    _, lua, _, _, _ = _dictation(monkeypatch, tmp_path)
    assert lua and "hl.bind" not in lua[0]       # a crash during dictation leaves nothing bound


def test_cloud_failure_uses_local(monkeypatch, tmp_path):
    from hyprwink.core.providers import ProviderError
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(InputStream=FakeStream))
    monkeypatch.setattr(dictation.paths, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(dictation.paths, "DICTATION_STATE", tmp_path / "dictation")
    monkeypatch.setattr(dictation.hypr, "lua", lambda code: None)
    monkeypatch.setattr(dictation.stt.LOCAL, "prepare", lambda: None)
    monkeypatch.setattr(dictation.stt.LOCAL, "transcribe", lambda pcm, rate, language: "local")

    def fail(pcm, rate, language):
        raise ProviderError("not reachable")
    monkeypatch.setattr(dictation.stt.elevenlabs, "transcribe", fail)
    d = dictation.Dictation({"engine": "elevenlabs", "language": "de"}, lambda *a: None)
    notices = []
    d.on_notice = notices.append
    assert d._transcribe(b"\0" * 32000) == "local"
    assert notices == ["ElevenLabs: not reachable – converted locally"]

