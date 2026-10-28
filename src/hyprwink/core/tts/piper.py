"""Piper, local: voices from rhasspy/piper-voices, downloaded when first
chosen; only the chosen one stays on disk."""

import shutil
import threading
import urllib.request

from ... import paths
from ...i18n import N_, _
from ..providers import ProviderError

LABEL = "Piper"
CLOUD = False
PACE = 1.35          # Piper speaks rather slowly
PIECE_CHARS = 0
URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{family}/{locale}/{speaker}/{quality}/{voice}"
BROWSE = None
# Per spoken language; the first one is the default.
LANGUAGE_VOICES = {
    "en": {
        "en_US-lessac-high": N_("Lessac (US, best quality)"),
        "en_US-ryan-high": N_("Ryan (US, male)"),
        "en_US-amy-medium": N_("Amy (US, female)"),
        "en_GB-alan-medium": N_("Alan (British, male)"),
        "en_GB-jenny_dioco-medium": N_("Jenny (British, female)"),
    },
    "de": {
        "de_DE-thorsten-high": N_("Thorsten (best quality)"),
        "de_DE-thorsten-medium": N_("Thorsten (faster)"),
        "de_DE-karlsson-low": N_("Karlsson (male)"),
        "de_DE-pavoque-low": N_("Pavoque (male)"),
        "de_DE-kerstin-low": N_("Kerstin (female)"),
        "de_DE-ramona-low": N_("Ramona (female)"),
        "de_DE-eva_k-x_low": N_("Eva (female, simple)"),
    },
}
ALL_VOICES = {voice: label for voices in LANGUAGE_VOICES.values() for voice, label in voices.items()}


def voices(language):
    return LANGUAGE_VOICES.get(language, LANGUAGE_VOICES["en"])


def default_voice(language):
    return next(iter(voices(language)))

_loaded = {}         # voice id -> PiperVoice
_lock = threading.Lock()


def prepare(voice):
    """Download the voice (model + config) unless it is there already."""
    if voice not in ALL_VOICES:
        raise ProviderError(_("unknown voice"))
    locale, speaker, quality = voice.split("-", 2)
    paths.VOICE_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("onnx", "onnx.json"):
        target = paths.VOICE_DIR / f"{voice}.{ext}"
        if target.exists():
            continue
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with urllib.request.urlopen(URL.format(family=locale.split("_")[0], locale=locale, speaker=speaker, quality=quality,
                                                   voice=voice) + f".{ext}",
                                        timeout=60) as response, open(tmp, "wb") as out:
                shutil.copyfileobj(response, out)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise ProviderError(_("voice cannot be loaded")) from e
        tmp.rename(target)


def voice_name(voice):
    return _(ALL_VOICES[voice]) if voice in ALL_VOICES else voice


def prune(keep):
    """Only the chosen voice stays on disk."""
    for path in paths.VOICE_DIR.glob("*.onnx*"):
        if not path.name.startswith(keep + "."):
            path.unlink(missing_ok=True)
    with _lock:
        for voice in [v for v in _loaded if v != keep]:
            del _loaded[voice]


class Speech:
    pace = 1.0       # PACE is applied by Piper itself (sounds better than speeding up)

    def __init__(self, voice):
        self.voice = voice
        self.rate = voice.config.sample_rate

    def synthesize(self, text):
        from piper import SynthesisConfig
        config = SynthesisConfig(length_scale=1 / PACE)
        for chunk in self.voice.synthesize(text, syn_config=config):
            yield chunk.audio_int16_bytes


def speech(voice, language):
    with _lock:
        if voice not in _loaded:
            from piper import PiperVoice
            prepare(voice)
            _loaded[voice] = PiperVoice.load(str(paths.VOICE_DIR / f"{voice}.onnx"))
        return Speech(_loaded[voice])
