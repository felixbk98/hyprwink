"""Turns the recognised gesture into its action; keeps the status for the
window, the bar and `hyprwink watch`."""

import logging
import threading
import time

from .. import config, gestures, i18n, settings
from . import hypr, page, tts
from .actions import Actions
from .gazefocus import DWELL, GazeFocus
from .tts import piper

# A gesture counts again only after it was gone this long (it flickers while held).
REARM_S = 1.0

log = logging.getLogger("hyprwink.engine")


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.watchers = []
        self.vision = None
        self.holds = 0            # windows setting up a gesture or the gaze
        self.current = set()      # gestures held right now
        self.last_seen = {}       # gesture -> time last held
        self.cfg = config.load_config()
        self.gaze = GazeFocus()
        page.enable()
        self.gaze_shown = 0.0
        self.actions = Actions(self.cfg, self._dictation_changed)
        self.actions.reader.on_notice = self.notify_action
        self.actions.dictation.on_notice = self.notify_action
        self.status = {"type": "status", "paused": False, "gesture": None, "camera": True,
                       "action": "", "action_id": 0, "vision": False, "holding": False,
                       "dictation": "idle", "level": 0.0, "badge": "", "gaze": None}
        self.reload()
        # Without gestures and gaze there is nothing to recognise: start paused.
        s = settings.load()
        self.paused = s["start_paused"] or not (self.gestures or s["gaze"] or s["show_gaze"])
        self.status["paused"] = self.paused
        self.update_dim()

    def reload(self):
        s = settings.load()
        i18n.use()
        with self.lock:
            self.gestures = gestures.by_id(gestures.load())
            self.show_gaze = s["show_gaze"]
            self.gaze_focus = s["gaze"]
            self.dim = s["dim_inactive"]
            self.dim_strength = s["dim_strength"]
            self.gaze.dwell = DWELL.get(s["gaze_speed"], DWELL["medium"])
            if not self.show_gaze:
                self._show_gaze(None)
            reader = self.actions.reader
            reader.set_speed(s["read_speed"])
            reader.cfg["engine"] = s["read_engine"]
            reader.cfg["voices"] = dict(s["read_voices"])
            reader.cfg["language"] = i18n.spoken("read_language")
            piper.prune(tts.voice("piper", reader.cfg["voices"], reader.cfg["language"]))
            self.actions.dictation.cfg["engine"] = s["dictate_engine"]
            self.actions.dictation.cfg["language"] = i18n.spoken("dictate_language")
        if hasattr(self, "paused"):     # at start: once paused is known
            self.update_dim()

    def on_frame(self, msg):
        """msg["gestures"]: {gesture: {}} held right now; msg["gaze"]: point or None."""
        with self.lock:
            held = msg.get("gestures") or {}
            self._update_status(camera=msg.get("camera", True))
            enabled = not self.paused and not self.holds
            now = time.monotonic()
            for gid, info in held.items():
                action = self.gestures.get(gid, {}).get("action")
                if action and info.get("direction"):
                    action = {**action, "direction": info["direction"], "x": info.get("x")}
                rearmed = now - self.last_seen.get(gid, float("-inf")) > REARM_S
                if gid not in self.current and rearmed and action and enabled:
                    self.run(action)
                self.last_seen[gid] = now
            self.current = set(held)
            self._update_status(gesture=next(iter(held), None))
            focus = self.gaze_focus
        # Outside the lock: it asks Hyprland, which may be slow. Only the
        # vision connection calls on_frame, so this runs one at a time.
        point = None
        if enabled and msg.get("gaze") is not None:
            point = self.gaze.update(msg["gaze"], focus=focus)
        with self.lock:
            self._show_gaze(point)

    def _show_gaze(self, point):
        """The gaze point for the dot on screen (if switched on), ~20 per second."""
        now = time.monotonic()
        if point is None or not self.show_gaze:
            if self.status.get("gaze") is not None:
                self._update_status(gaze=None)    # the dot disappears
            return
        if now - self.gaze_shown < 0.05:
            return
        self.gaze_shown = now
        self._update_status(gaze=[round(float(point[0])), round(float(point[1]))])

    def run(self, action):
        if isinstance(action, str):   # CLI: built-in name
            action = {"type": "builtin", "value": action}
        self.notify_action(gestures.action_label(action))
        if action.get("type") != "wish":
            self.actions.run(action)

    def _dictation_changed(self, state, level, badge):
        """For the recording pill: state, microphone level (0..1), badge."""
        with self.lock:
            self._update_status(dictation=state, level=round(min(1.0, level), 3), badge=badge)

    def dictate(self, command, target=None, badge=""):
        d = self.actions.dictation
        if command in ("start", "toggle") and d.state == "idle":
            self.actions.reader.stop()   # the microphone would hear it
        if command == "toggle":
            d.toggle(target, badge)
        elif command == "start":
            d.start(target, badge)
        elif command == "stop":
            d.stop()
        elif command == "send":
            d.stop(send=True)
        elif command == "cancel":
            d.cancel()
        else:
            raise ValueError(f"unknown dictate command {command}")

    def set_paused(self, paused):
        with self.lock:
            self.paused = paused
            self._update_status(paused=paused)
        self._sync_vision()
        self.update_dim()

    def update_dim(self, on=None):
        """The other windows are dimmed while focus follows gaze (if wanted)."""
        if on is None:
            on = self.dim and self.gaze_focus and not getattr(self, "paused", True)
        hypr.dim_inactive(on, self.dim_strength)

    def set_holding(self, on):
        with self.lock:
            self.holds += 1 if on else -1
            self._update_status(holding=self.holds > 0)
        self._sync_vision()

    def _sync_vision(self):
        """Paused: the camera is switched off, except while setting something up."""
        self._send_vision({"type": "paused", "value": self.paused and not self.holds})

    def notify_action(self, label):
        with self.lock:
            self.status["action_id"] += 1
            self._update_status(action=label, force=True)

    def _update_status(self, force=False, **values):
        changed = force
        for key, value in values.items():
            if self.status.get(key) != value:
                self.status[key] = value
                changed = True
        if changed:
            for mailbox in self.watchers:
                mailbox.put(dict(self.status))

    def set_vision(self, conn):
        self.vision = conn
        self._update_status(vision=conn is not None)
        if conn is not None:
            self._sync_vision()

    def _send_vision(self, msg):
        conn = self.vision
        if conn is None:
            return
        try:
            conn.send(msg)
        except OSError:
            self.vision = None
