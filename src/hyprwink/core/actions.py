"""Runs an action: a built-in one (gestures.BUILTIN), a shortcut, a program or a command."""

import logging
import math
import shlex
import threading

from .. import gestures, settings
from . import hypr, media
from .dictation import Dictation
from .reader import Reader

log = logging.getLogger("hyprwink.actions")

DISPATCH = {
    "window_close": "hl.dsp.window.close()",
    "window_fullscreen_on": 'hl.dsp.window.fullscreen({ mode = "fullscreen", action = "set" })',
    "window_fullscreen_off": 'hl.dsp.window.fullscreen({ mode = "fullscreen", action = "unset" })',
    "window_float": 'hl.dsp.window.float({ action = "toggle" })',
    "window_next": "hl.dsp.window.cycle_next()",
    "workspace_next": 'hl.dsp.focus({ workspace = "e+1" })',
    "workspace_previous": 'hl.dsp.focus({ workspace = "e-1" })',
}
# Copy and paste differ in terminals.
KEYS = {"tab": ("Tab", "Tab"), "select_all": ("CTRL+A", "CTRL+SHIFT+A"), "copy": ("CTRL+C", "CTRL+SHIFT+C"), "cut": ("CTRL+X", "CTRL+X"),
        "paste": ("CTRL+V", "SHIFT+Insert"), "undo": ("CTRL+Z", "CTRL+Z")}
MEDIA = {"media_play_pause": "PlayPause", "media_next": "Next", "media_previous": "Previous"}
VOLUME = {"volume_up": "5%+", "volume_down": "5%-", "volume_mute": "mute"}
STRAIGHT = 15        # degrees around left/right/up/down that count as straight; the rest is diagonal


def snap(dx, dy):
    """A swipe as one of 8 directions, like a cut pizza: narrow straight
    slices (STRAIGHT) and wide diagonal ones."""
    angle = math.degrees(math.atan2(dy, dx)) % 360
    for straight in (0, 90, 180, 270, 360):
        if abs(angle - straight) <= STRAIGHT:
            return round(math.cos(math.radians(straight))), round(math.sin(math.radians(straight)))
    return (1 if dx > 0 else -1), (1 if dy > 0 else -1)


class Actions:
    def __init__(self, cfg, on_dictation):
        self.reader = Reader()
        self.dictation = Dictation({"engine": settings.DEFAULTS["dictate_engine"], "language": "en"}, on_dictation)

    def run(self, action):
        """action: see gestures.py (a wish does nothing); a movement gesture
        adds its "direction" (dx, dy in the image, y down) and "x", where across
        the image the hand ended (0 left … 1 right)."""
        # Shell-outs take a few milliseconds; keep the frame loop free.
        threading.Thread(target=self._run, args=(action,), daemon=True).start()

    def _run(self, action):
        kind, value = action.get("type"), action.get("value", "")
        try:
            if kind == "key":
                hypr.key(value)
            elif kind == "app":
                self._launch(value)
            elif kind == "command":
                self._exec(value)
            elif kind == "builtin":
                self._builtin(value, action.get("direction"), action.get("x"))
        except Exception:
            log.exception("action %s failed", action)

    def _launch(self, desktop_id):
        path = gestures.app_file(desktop_id)
        if path is None:
            log.warning("program %s not found", desktop_id)
            return
        self._exec(f"gio launch {shlex.quote(str(path))}")

    @staticmethod
    def _exec(command):
        # Started by Hyprland, so it does not belong to this service.
        hypr.dispatch(f"hl.dsp.exec_cmd({hypr.lua_string(command)})")

    def _builtin(self, name, direction=None, x=None):
        d = self.dictation
        if name == "dictate_start":
            self.reader.stop()   # the microphone would hear it
            d.start()
        elif name == "dictate_stop":
            d.stop()
        elif name == "dictate_send":
            d.stop(send=True)
        elif name == "read_start":
            self.reader.start()
        elif name == "read_stop":
            self.reader.stop()
        elif name == "enter":
            d.stop(send=True) if d.state == "recording" else hypr.key("Return")
        elif name in ("escape", "cancel"):
            if d.state != "idle":
                d.cancel()
            elif self.reader.reading:
                self.reader.stop()
            elif name == "escape":
                hypr.key("Escape")
        elif name in KEYS:
            normal, terminal = KEYS[name]
            hypr.key(terminal if normal != terminal and hypr.in_terminal() else normal)
        elif name == "window_swipe":
            # Onto the monitor the swipe points at, else along the layout on the
            # same monitor (two windows side by side swap).
            direction = direction and snap(*direction)
            target = direction and hypr.monitor_toward(*direction, hand_x=x)
            if target:
                hypr.move_to_monitor(target)
            elif direction:
                dx, dy = direction
                side = ("r" if dx > 0 else "l") if abs(dx) >= abs(dy) else ("d" if dy > 0 else "u")
                hypr.dispatch(f'hl.dsp.window.move({{ direction = "{side}" }})')
        elif name in DISPATCH:
            hypr.dispatch(DISPATCH[name])
        elif name in MEDIA:
            media.control(MEDIA[name])
        elif name in VOLUME:
            media.volume(VOLUME[name])
        else:
            log.warning("unknown action %s", name)
