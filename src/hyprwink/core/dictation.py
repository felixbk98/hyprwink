"""Dictation: record the microphone, turn speech into text, paste it.

States: idle → recording → transcribing → idle. While busy, Escape cancels
and (only while recording) Enter stops and sends; both keys are bound in
Hyprland only then, so they reach the apps the rest of the time. Playing
media (MPRIS) pauses while recording.

Speech to text: one of the providers in core/stt; when a cloud provider
fails, the local one takes over.

At the start, the cursor is put into the text field of a web page in the
focused window if it is in none (core/page). The text is pasted into the
focused window like a typed paste: the
clipboard is kept, the text copied, Ctrl+V pressed (Shift+Insert in
terminals), Enter after it when sending, then the old clipboard comes back.
With a file target (`hyprwink dictate --file`) the text goes into that
file instead; a badge (`--badge`) is a symbol the pill shows, so another
program that uses the dictation can mark its recordings.
"""

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from .. import paths
from . import hypr, media, page, stt
from ..i18n import _
from .providers import ProviderError

log = logging.getLogger("hyprwink.dictation")

RATE = 16000
MAX_SECONDS = 300
LEVEL_EVERY = 0.06      # seconds between level updates for the pill
CLI = Path(sys.executable).with_name("hyprwink")


def _run(*command, input=None, timeout=3):
    try:
        return subprocess.run(command, input=input, capture_output=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return b""


def _detached(*command, input=None):
    """wl-copy keeps serving the clipboard in the background; in its own
    scope a restart of this service does not take the clipboard with it."""
    try:
        subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--collect", *command], input=input,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


class Dictation:
    def __init__(self, cfg, on_change):
        self.cfg = cfg                  # {"engine": provider name, "language": "de"}
        self.on_change = on_change      # (state, level, badge) for the status stream
        self.on_notice = lambda text: None
        self.state = "idle"
        self.lock = threading.Lock()
        self.chunks = []
        self.stream = None
        self.target = None              # file for the transcript, or None: paste
        self.badge = ""                 # symbol the pill shows for this recording
        self.send = False
        self.run_id = 0                 # a cancel during transcribing drops that result
        self.media = media.Pause()
        self.level_at, self.started = 0.0, 0.0
        self.too_long = False
        # Keys and media follow the state (_sync), in their own lock: pausing
        # media can take a while and must not hold up stop or cancel.
        self.effects = threading.Lock()
        self.keys_set = None            # (escape, enter) bound now; None: unknown
        self.media_held = False
        self._state_file("idle")
        self._sync()                    # frees Escape/Enter left bound by a crash
        # Ready before the first use; the local one is the fallback for the cloud.
        threading.Thread(target=stt.LOCAL.prepare, daemon=True).start()

    # ------------------------------------------------------------- commands

    def toggle(self, target=None, badge=""):
        if self.state == "recording":
            self.stop()
        elif self.state == "idle":
            self.start(target, badge)

    def start(self, target=None, badge=""):
        with self.lock:
            if self.state != "idle":
                return
            self.chunks, self.target, self.badge, self.send = [], target, badge, False
            self.started, self.too_long = time.monotonic(), False
            try:
                import sounddevice
                self.stream = sounddevice.InputStream(samplerate=RATE, channels=1, dtype="int16",
                                                      callback=self._audio)
                self.stream.start()
            except Exception as e:
                log.error("microphone: %s", e)
                self.on_notice(_("Microphone not available"))
                return
            self._set("recording")
        if target is None:
            threading.Thread(target=lambda: page.focus_field(hypr.active_window()), daemon=True).start()
        self._sync()

    def stop(self, send=False):
        with self.lock:
            if self.state != "recording":
                return
            self.send = send
            self._close_stream()
            self._set("transcribing")
            self.run_id += 1
            run_id, pcm, target, send = self.run_id, b"".join(self.chunks), self.target, self.send
        self._sync()
        threading.Thread(target=self._finish, args=(run_id, pcm, target, send), daemon=True).start()

    def cancel(self):
        with self.lock:
            if self.state == "idle":
                return
            self._close_stream()
            self.run_id += 1
            self.chunks = []
            self._set("idle")
            target = self.target
        self._sync()
        if target:
            Path(target).unlink(missing_ok=True)

    # --------------------------------------------------------------- inside

    def _audio(self, data, frames, _time, _status):
        self.chunks.append(bytes(data))
        now = time.monotonic()
        if now - self.level_at >= LEVEL_EVERY:
            self.level_at = now
            rms = float(np.sqrt(np.mean((data.astype(np.float32) / 32768) ** 2)))
            self.on_change(self.state, rms, self.badge)
        if now - self.started > MAX_SECONDS and not self.too_long:
            self.too_long = True
            threading.Thread(target=self.stop, daemon=True).start()

    def _close_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _set(self, state):
        self.state = state
        self._state_file(state)
        self.on_change(state, 0.0, self.badge)

    def _state_file(self, state):
        """Other programs (e.g. a bar) can follow the state in this file."""
        paths.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        tmp = paths.DICTATION_STATE.with_suffix(".tmp")
        tmp.write_text(state + "\n")
        tmp.replace(paths.DICTATION_STATE)

    def _sync(self):
        """Keys and media as the current state wants them: Escape while busy,
        Enter while recording, media paused while recording."""
        with self.effects:
            state = self.state
            recording = state == "recording"
            if recording != self.media_held:
                self.media.pause() if recording else self.media.resume()
                self.media_held = recording
            keys = (state != "idle", recording)
            if keys != self.keys_set:
                self._keys(*keys)
                self.keys_set = keys

    def _keys(self, escape, enter):
        """Escape and Enter belong to the dictation only while it is busy."""
        keys = (("Escape", escape, "cancel"), ("Return", enter, "send"), ("KP_Enter", enter, "send"))
        # Unbind first: a key bound twice would run twice.
        code = [f'pcall(hl.unbind, "{key}")' for key, _, _ in keys]
        code += [f'hl.bind("{key}", hl.dsp.exec_cmd("{CLI} dictate {sub}"))' for key, on, sub in keys if on]
        hypr.lua(" ".join(code))

    def _transcribe(self, pcm):
        provider = stt.get(self.cfg["engine"])
        language = self.cfg["language"]
        if provider is not stt.LOCAL:
            try:
                return provider.transcribe(pcm, RATE, language)
            except ProviderError as e:
                self.on_notice(_("{provider}: {error} – converted locally").format(provider=provider.LABEL, error=e))
        return stt.LOCAL.transcribe(pcm, RATE, language)

    def _finish(self, run_id, pcm, target, send):
        text = ""
        try:
            if len(pcm) > RATE * 2 * 0.3:     # shorter than 0.3 s: nothing said
                text = self._transcribe(pcm)
        except Exception:
            log.exception("transcription failed")
            self.on_notice(_("Dictation failed"))
        with self.lock:
            if run_id != self.run_id or self.state != "transcribing":
                return                        # cancelled meanwhile
            self._set("idle")
        self._sync()
        if target:
            try:
                Path(target).write_text(text)
            except OSError as e:
                log.error("transcript file: %s", e)
        elif text:
            self._paste(text, send)

    def _paste(self, text, send):
        mime = _run("wl-paste", "--list-types").decode(errors="replace").split("\n")[0].strip()
        old = _run("wl-paste", "--no-newline", "--type", mime, timeout=2) if mime else b""
        _detached("wl-copy", input=text.encode())
        time.sleep(0.05)
        hypr.key("SHIFT+Insert" if hypr.in_terminal() else "CTRL+V")
        if send:
            time.sleep(0.15)
            hypr.key("Return")
        time.sleep(0.3)
        if mime and old:
            _detached("wl-copy", "--type", mime, input=old)
        else:
            _detached("wl-copy", "--clear")
