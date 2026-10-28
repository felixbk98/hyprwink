"""The user's gestures and what they do. Kept free of numpy/mediapipe.

gestures.json: {"gestures": [{"id": "g…", "name": "…", "action": {…}}]}
The recordings themselves are in samples.json (by id), photos in photos/.

An action is one of
  {"type": "builtin", "value": id in BUILTIN}
  {"type": "key", "value": "CTRL+C"}
  {"type": "app", "value": "firefox.desktop"}
  {"type": "command", "value": "notify-send Hallo"}   a shell command
  {"type": "wish", "value": free text}   only saved: Claude Code implements it later
"""

import os
import time
from pathlib import Path

from . import config, paths
from .i18n import N_, _

# Actions that take the direction of a movement: the gesture is a hand
# shape that grabs, drags and lets go (vision/drag.py).
DIRECTION_ACTIONS = {"window_swipe"}

BUILTIN = {
    "dictate_start": N_("Start dictation"),
    "dictate_stop": N_("Stop dictation"),
    "dictate_send": N_("Stop dictation and send"),
    "read_start": N_("Read aloud"),
    "read_stop": N_("Stop reading aloud"),
    "enter": N_("Enter (sends while dictating)"),
    "cancel": N_("Cancel dictation and reading aloud"),
    "escape": N_("Esc (cancels dictation and reading aloud)"),
    "tab": N_("Tab"),
    "select_all": N_("Select all"),
    "copy": N_("Copy"),
    "cut": N_("Cut"),
    "paste": N_("Paste"),
    "undo": N_("Undo"),
    "window_close": N_("Close window"),
    "window_swipe": N_("Move window in swipe direction"),
    "window_fullscreen_on": N_("Fullscreen on"),
    "window_fullscreen_off": N_("Fullscreen off"),
    "window_float": N_("Floating on/off"),
    "window_next": N_("Next window"),
    "workspace_next": N_("Next workspace"),
    "workspace_previous": N_("Previous workspace"),
    "media_play_pause": N_("Play/pause"),
    "media_next": N_("Next track"),
    "media_previous": N_("Previous track"),
    "volume_up": N_("Volume up"),
    "volume_down": N_("Volume down"),
    "volume_mute": N_("Mute on/off"),
}

KEY_NAMES = {"CTRL": N_("Ctrl"), "SHIFT": N_("Shift"), "ALT": "Alt",
             "SUPER": N_("Super"), "Return": N_("Enter"), "Escape": "Esc",
             "space": N_("Space"), "BackSpace": N_("Backspace"),
             "Delete": N_("Del"), "Tab": "Tab"}


EXAMPLES = Path(__file__).parent / "data" / "examples"   # without photos


def _examples():
    """On the first start: the example gestures (recorded by the author),
    named after their action. "Delete all gestures" keeps an empty file, so
    they do not come back."""
    data = config.load_json(EXAMPLES / "gestures.json", {"gestures": []})
    for g in data["gestures"]:
        g["name"] = action_label(g["action"])
    if not paths.SAMPLES_FILE.exists():
        config.save_json(paths.SAMPLES_FILE, config.load_json(EXAMPLES / "samples.json", {}))
    save(data)


def load():
    if not paths.GESTURES_FILE.exists():
        _examples()
    data = config.load_json(paths.GESTURES_FILE, {})
    data.setdefault("gestures", [])
    return data


def save(data):
    config.save_json(paths.GESTURES_FILE, data)


def by_id(data):
    return {g["id"]: g for g in data["gestures"]}


def new_id():
    return f"g{int(time.time() * 1000)}"


def labels(data):
    """{gesture id: what it does}, for the labels in the camera image."""
    return {g["id"]: action_label(g["action"]) for g in data["gestures"]}


def app_name(desktop_id):
    """The Name= of an installed .desktop file, else its id."""
    path = app_file(desktop_id)
    if path:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("Name="):
                return line[5:]
    return desktop_id.removesuffix(".desktop")


def app_file(desktop_id):
    """Path of an installed .desktop file (XDG data directories), or None."""
    dirs = [os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")]
    dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    for base in dirs:
        path = Path(base) / "applications" / desktop_id
        if path.is_file():
            return path
    return None


def key_label(combo):
    return "+".join(_(KEY_NAMES[part]) if part in KEY_NAMES else part for part in combo.split("+"))


def action_label(action):
    if not action:
        return _("no action")
    kind, value = action.get("type"), action.get("value", "")
    if kind == "builtin":
        return _(BUILTIN[value]) if value in BUILTIN else value
    if kind == "key":
        return _("Key: {key}").format(key=key_label(value))
    if kind == "app":
        return _("Program: {name}").format(name=app_name(value))
    if kind == "command":
        return _("Command: {command}").format(command=_short(value))
    if kind == "wish":
        return _("Wish: {text}").format(text=_short(value))
    return "?"


def _short(text):
    return text if len(text) <= 50 else text[:47] + "…"
