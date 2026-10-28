"""Reading aloud with one of the text to speech providers (core/tts); when
a cloud provider fails, the local one reads the rest.

Text, always from the focused window (the one looked at): text selected
after its last Claude Code answer arrived (once), otherwise that answer
(written by the Stop hook), otherwise the newest message of its web page
(core/page).
"""

import json
import logging
import re
import socket
import subprocess
import threading
import time

import numpy as np

from .. import answers, i18n, paths, settings
from . import hypr, page, tts
from ..i18n import N_, _
from .providers import ProviderError

log = logging.getLogger("hyprwink.reader")

AHEAD = 20.0         # seconds of cloud audio fetched ahead of playback
LEVEL = -17.0        # dBFS of the speech (pauses left out): all voices equally loud
MAX_GAIN = 24.0      # dB


def clean(text, language="en"):
    """Markdown to plain sentences (in the spoken language)."""
    code = i18n.translate(N_("Code block."), language)
    text = re.sub(r"```.*?```", f" {code} ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)          # links
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.M)          # tables
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)               # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)            # bullets
    text = re.sub(r"[*_~>#|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sentences(text):
    """Sentences and clauses: a new tempo applies from the next one on."""
    return [s for s in re.split(r"(?<=[.!?:;,])\s+", text) if s.strip()]


def _pieces(parts, limit):
    """Sentences joined into requests of up to limit characters (0: one each)."""
    if not limit:
        return list(parts)
    pieces, current = [], ""
    for part in parts:
        if current and len(current) + 1 + len(part) > limit:
            pieces.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        pieces.append(current)
    return pieces


class Selection:
    """Remembers when the primary selection last changed."""

    def __init__(self):
        self.changed = 0.0
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        while True:
            try:
                proc = subprocess.Popen(["wl-paste", "--primary", "--watch", "echo"], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
                first = True
                for _ in proc.stdout:
                    if not first:   # the first line is the current state at start
                        self.changed = time.time()
                    first = False
            except OSError:
                pass
            time.sleep(5)

    @staticmethod
    def text():
        try:
            return subprocess.run(["wl-paste", "--primary", "--no-newline"], capture_output=True,
                                  text=True, timeout=1).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ""


class Leveler:
    """Brings every voice to the same loudness. The gain follows the mean
    level of the speech heard so far (pauses left out), so it settles within
    the first words; peaks are limited softly instead of clipping."""

    def __init__(self, rate):
        self.frame = max(1, rate // 50)     # 20 ms
        self.energy = 0.0
        self.frames = 0
        self.rest = b""

    def __call__(self, chunk):
        chunk, self.rest = self.rest + chunk, b""
        if len(chunk) % 2:
            chunk, self.rest = chunk[:-1], chunk[-1:]
        x = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768
        n = len(x) // self.frame * self.frame
        power = (x[:n].reshape(-1, self.frame) ** 2).mean(axis=1)
        voiced = power[power > 1e-4]        # above -40 dBFS
        self.energy += float(voiced.sum())
        self.frames += len(voiced)
        if not self.frames:
            return chunk
        level = 10 * np.log10(self.energy / self.frames)
        x = x * 10 ** (min(LEVEL - level, MAX_GAIN) / 20)
        knee = 0.8
        loud = np.abs(x) > knee
        x[loud] = np.sign(x[loud]) * (knee + (1 - knee) * np.tanh((np.abs(x[loud]) - knee) / (1 - knee)))
        return (x * 32767).astype(np.int16).tobytes()


class Player:
    """mpv playing raw 16-bit mono audio from stdin. The tempo changes live
    (scaletempo2 keeps the pitch), so the slider works while reading."""

    def __init__(self, rate, speed):
        paths.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self.socket = paths.RUNTIME_DIR / f"mpv-{id(self)}.sock"
        self.process = subprocess.Popen(
            ["mpv", "--no-config", "--no-video", "--no-terminal", "--demuxer=rawaudio",
             "--demuxer-rawaudio-format=s16le", f"--demuxer-rawaudio-rate={rate}",
             "--demuxer-rawaudio-channels=1", f"--speed={speed}", f"--input-ipc-server={self.socket}", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def write(self, data):
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def finish(self):
        """All audio written: wait until it has been played."""
        self.process.stdin.close()
        self.process.wait()
        self.socket.unlink(missing_ok=True)

    def kill(self):
        self.process.kill()
        try:
            self.process.stdin.close()
        except OSError:
            pass
        self.socket.unlink(missing_ok=True)

    def alive(self):
        return self.process.poll() is None

    def _ipc(self, *command):
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(1)
                sock.connect(str(self.socket))
                sock.sendall((json.dumps({"command": list(command)}) + "\n").encode())
                return json.loads(sock.makefile().readline() or "{}")
        except (OSError, ValueError):
            return {}

    def position(self):
        """Seconds of audio played so far."""
        value = self._ipc("get_property", "time-pos").get("data")
        return float(value) if isinstance(value, (int, float)) else 0.0

    def set_speed(self, speed):
        self._ipc("set_property", "speed", speed)


class Reader:
    def __init__(self):
        d = settings.DEFAULTS
        self.cfg = {"engine": d["read_engine"], "voices": dict(d["read_voices"]), "speed": d["read_speed"],
                    "language": "en"}
        self.player = None
        self.token = 0
        self.lock = threading.Lock()
        self.selection = Selection()
        self.selection_read = 0.0   # when the selection read last was made
        self.on_notice = lambda text: None
        self.factor = 1.0       # the provider's tempo factor in the current reading

    def text(self):
        """See above. Never the answer or page of another window."""
        window = hypr.active_window()
        answer = answers.for_window(window)
        selected = self.selection.text().strip()
        changed = self.selection.changed
        if selected and changed > max(answer[0] if answer else 0, self.selection_read):
            self.selection_read = changed
            return selected
        text = answer[1] if answer else page.newest(window)
        if not text:
            self.on_notice(_("Nothing to read – select some text"))
        return text

    def start(self, text=None):
        self.stop()
        text = clean(text or self.text(), self.cfg["language"])
        if not text:
            return False
        with self.lock:
            self.token += 1
            token = self.token
        threading.Thread(target=self._speak, args=(text, token), daemon=True).start()
        return True

    @property
    def reading(self):
        player = self.player
        return player is not None and player.alive()

    def stop(self):
        with self.lock:
            self.token += 1
            player, self.player = self.player, None
        if player:
            player.kill()

    def set_speed(self, speed):
        """Applies at once, also while reading."""
        if speed == self.cfg["speed"]:
            return
        self.cfg["speed"] = speed
        player = self.player
        if player is not None:
            player.set_speed(speed * self.factor)

    def set_voice(self, engine, voice):
        """Use another voice; fetches it first if needed (raises ProviderError)."""
        tts.get(engine).prepare(voice)
        self.cfg["voices"][engine] = voice

    def _speak(self, text, token):
        provider = tts.get(self.cfg["engine"])
        parts = sentences(text)
        try:
            rest = self._read(provider, parts, token)
            if rest and provider is not tts.LOCAL:
                rest = self._read(tts.LOCAL, rest, token)
        except (BrokenPipeError, OSError):
            pass
        except Exception:
            log.exception("reading failed")

    def _read(self, provider, parts, token):
        """Reads the sentences; returns those not read when the provider
        failed (None when done or stopped)."""
        name = next(n for n, p in tts.PROVIDERS.items() if p is provider)
        pieces = _pieces(parts, provider.PIECE_CHARS)
        try:
            language = self.cfg["language"]
            speech = provider.speech(tts.voice(name, self.cfg["voices"], language), language)
        except ProviderError as e:
            self._failed(provider, e)
            return parts
        player = self._player(speech, token)
        if player is None:
            return None
        fetched = 0.0   # seconds of audio handed to the player
        level = Leveler(speech.rate)
        for i, piece in enumerate(pieces):
            # Cloud: stay at most AHEAD seconds ahead of playback, so stopping
            # early wastes little of the paid text.
            while provider.CLOUD and token == self.token and player.alive() and fetched - player.position() > AHEAD:
                time.sleep(0.3)
            if token != self.token:
                return None
            try:
                for chunk in speech.synthesize(piece):
                    if token != self.token:
                        return None
                    player.write(level(chunk))
                    fetched += len(chunk) / (2 * speech.rate)
            except ProviderError as e:
                self._failed(provider, e)
                player.finish()
                return pieces[i:]
        player.finish()
        return None

    def _failed(self, provider, error):
        if provider is not tts.LOCAL:
            self.on_notice(f"{provider.LABEL}: {error} – {tts.LOCAL.LABEL}")
        else:
            self.on_notice(_("Reading aloud: {error}").format(error=error))

    def _player(self, speech, token):
        """A player for this reading; None if reading was stopped meanwhile."""
        self.factor = speech.pace
        player = Player(speech.rate, self.cfg["speed"] * speech.pace)
        with self.lock:
            if token != self.token:
                player.kill()
                return None
            self.player = player
        return player
