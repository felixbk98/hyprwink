"""Fish Audio (cloud): https://docs.fish.audio

POST /v1/tts with model s2.1-pro; the audio is streamed as raw PCM while it
is generated.
"""

import json
import logging
import urllib.error
import urllib.request

from ...i18n import _
from ..providers import ProviderError, api_key

LABEL = "Fish Audio"
CLOUD = True
ACCOUNT = "fish-audio"
PACE = 1.15          # its own speed setting sounds choppy: the player speeds it up
PIECE_CHARS = 280    # the API's chunk_length is at most 300
BROWSE = "https://fish.audio/discovery/"
URL = "https://api.fish.audio/v1/tts"
MODEL = "s2.1-pro"
RATE = 44100

log = logging.getLogger("hyprwink.fishaudio")


def voices(language):
    return None      # any voice id (BROWSE)


def default_voice(language):
    return ""        # Fish Audio's default voice


def voice_name(voice):
    """Title of a voice model, or "" when it cannot be looked up."""
    request = urllib.request.Request(f"https://api.fish.audio/model/{voice}",
                                     headers={"Authorization": f"Bearer {api_key(ACCOUNT)}"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.load(response).get("title", "")
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def prepare(voice):
    pass


class Speech:
    rate = RATE
    pace = PACE

    def __init__(self, voice, key, language):
        self.voice, self.key, self.language = voice, key, language

    def synthesize(self, text):
        body = {"text": text, "format": "pcm", "sample_rate": RATE, "latency": "low",
                "language": self.language}
        if self.voice:
            body["reference_id"] = self.voice
        request = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "model": MODEL})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                while chunk := response.read(8192):
                    yield chunk
        except urllib.error.HTTPError as e:
            log.warning("HTTP %s: %s", e.code, e.read()[:200].decode(errors="replace"))
            raise ProviderError(_("key invalid") if e.code in (401, 403) else _("not reachable")) from e
        except (urllib.error.URLError, OSError) as e:
            log.warning("%s", e)
            raise ProviderError(_("not reachable")) from e


def speech(voice, language):
    key = api_key(ACCOUNT)
    if not key:
        raise ProviderError(_("key missing"))
    return Speech(voice, key, language)
