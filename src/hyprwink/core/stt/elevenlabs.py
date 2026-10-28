"""ElevenLabs Scribe v2 (cloud): https://elevenlabs.io/docs/api-reference/speech-to-text/convert

POST /v1/speech-to-text; the recording is sent as WAV, the transcript
comes back as JSON.
"""

import io
import json
import logging
import urllib.error
import urllib.request
import uuid
import wave

from ...i18n import _
from .. import providers

LABEL = "ElevenLabs"
CLOUD = True
ACCOUNT = "elevenlabs"
URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = "scribe_v2"

log = logging.getLogger("hyprwink.elevenlabs")


def _wav(pcm, rate):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def prepare():
    pass


def transcribe(pcm, rate, language):
    key = providers.api_key(ACCOUNT)
    if not key:
        raise providers.ProviderError(_("key missing"))
    boundary = uuid.uuid4().hex
    fields = {"model_id": MODEL, "language_code": language, "tag_audio_events": "false"}
    body = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
             "Content-Type: audio/wav\r\n\r\n").encode() + _wav(pcm, rate) + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(URL, data=body, method="POST", headers={
        "xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response).get("text", "").strip()
    except urllib.error.HTTPError as e:
        log.warning("HTTP %s: %s", e.code, e.read()[:200].decode(errors="replace"))
        raise providers.ProviderError(_("key invalid") if e.code in (401, 403) else _("not reachable")) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        log.warning("%s", e)
        raise providers.ProviderError(_("not reachable")) from e
