"""Fetches the models for a new installation: hand and face (MediaPipe),
the default Piper voice, Whisper. `python -m hyprwink.models` (install.sh)."""

import shutil
import urllib.request

from . import i18n, paths
from .core.stt import whisper
from .core.tts import piper

MEDIAPIPE = "https://storage.googleapis.com/mediapipe-models/{0}/{0}/float16/latest/{0}.task"


def _fetch(url, target):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, open(tmp, "wb") as out:
        shutil.copyfileobj(response, out)
    tmp.rename(target)


def download():
    _fetch(MEDIAPIPE.format("hand_landmarker"), paths.HAND_MODEL)
    _fetch(MEDIAPIPE.format("face_landmarker"), paths.FACE_MODEL)
    piper.prepare(piper.default_voice(i18n.spoken("read_language")))
    whisper.download()


if __name__ == "__main__":
    download()
