from hyprwink.core.reader import clean, sentences


def test_markdown_becomes_plain_text():
    text = "## Titel\n- **fett** und `code`\n```\nx = 1\n```\n[Link](https://x.y)"
    assert clean(text) == "Titel fett und code Code block. Link"


def test_sentences():
    assert sentences("Eins. Zwei? Drei!") == ["Eins.", "Zwei?", "Drei!"]


def test_cloud_pieces_stay_below_the_api_limit():
    from hyprwink.core.reader import _pieces
    from hyprwink.core.tts import fishaudio
    parts = ["Ein Satz mit etwas Text." for _ in range(40)]
    pieces = _pieces(parts, fishaudio.PIECE_CHARS)
    assert all(len(p) <= fishaudio.PIECE_CHARS for p in pieces)
    assert " ".join(pieces) == " ".join(parts)


def test_cloud_failure_falls_back_to_local(monkeypatch):
    from hyprwink.core import reader as reader_mod
    from hyprwink.core import tts
    from hyprwink.core.providers import ProviderError

    class Player:
        def __init__(self, rate, speed):
            self.written = []
        def write(self, data):
            self.written.append(data)
        def finish(self): pass
        def kill(self): pass
        def alive(self): return True
        def position(self): return 0.0
        def set_speed(self, speed): pass

    class Local:
        rate, pace = 22050, 1.0
        def synthesize(self, text):
            yield b"local:" + text.encode()

    monkeypatch.setattr(reader_mod, "Player", Player)
    monkeypatch.setattr(reader_mod.Selection, "_watch", lambda self: None)
    monkeypatch.setattr(tts.fishaudio, "speech", lambda voice, language: (_ for _ in ()).throw(ProviderError("key missing")))
    monkeypatch.setattr(reader_mod, "Leveler", lambda rate: lambda chunk: chunk)   # text stands in for audio
    monkeypatch.setattr(tts.piper, "speech", lambda voice, language: Local())
    r = reader_mod.Reader()
    notices = []
    r.on_notice = notices.append
    r.cfg["engine"] = "fish"
    r._speak("Eins. Zwei.", r.token)
    assert r.player.written == [b"local:Eins.", b"local:Zwei."]
    assert notices == ["Fish Audio: key missing – Piper"]


def test_voices_equally_loud():
    import numpy as np
    from hyprwink.core.reader import LEVEL, Leveler
    t = np.arange(16000) / 16000
    for amplitude in (0.02, 0.5):
        pcm = (np.sin(2 * np.pi * 220 * t) * amplitude * 32767).astype(np.int16).tobytes()
        level = Leveler(16000)
        out = b"".join(level(pcm[i:i + 1001]) for i in range(0, len(pcm), 1001))   # odd chunks
        x = np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32768
        assert len(out) == len(pcm)
        assert abs(10 * np.log10((x[4000:] ** 2).mean()) - LEVEL) < 1.5


def test_voice_follows_spoken_language():
    from hyprwink.core import tts
    assert tts.voice("piper", {"piper": "de_DE-karlsson-low"}, "de") == "de_DE-karlsson-low"
    assert tts.voice("piper", {"piper": "de_DE-karlsson-low"}, "en") == "en_US-lessac-high"
    assert tts.voice("fish", {"fish": "abc"}, "en") == "abc"


def test_text_order(monkeypatch):
    from hyprwink.core import reader as reader_mod
    monkeypatch.setattr(reader_mod.Selection, "_watch", lambda self: None)
    monkeypatch.setattr(reader_mod.hypr, "active_window", lambda: {"pid": 1, "title": "Chat"})
    monkeypatch.setattr(reader_mod.page, "newest", lambda window: "Newest message.")
    answer = None
    monkeypatch.setattr(reader_mod.answers, "for_window", lambda window: answer)
    r = reader_mod.Reader()
    monkeypatch.setattr(r.selection, "text", lambda: "Selected.")
    assert r.text() == "Newest message."            # nothing selected since start
    r.selection.changed = 5.0
    assert r.text() == "Selected."
    assert r.text() == "Newest message."            # a selection is read once
    answer = (10.0, "Answer.")
    assert r.text() == "Answer."
