"""Media players (MPRIS over D-Bus) and the volume (PipeWire, wpctl)."""

import subprocess

MPRIS = "org.mpris.MediaPlayer2"
OBJECT = "/org/mpris/MediaPlayer2"
SINK = "@DEFAULT_AUDIO_SINK@"


def _run(*command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def players():
    out = _run("busctl", "--user", "list", "--no-legend")
    return [line.split()[0] for line in out.splitlines() if line.startswith(MPRIS + ".")]


def playing(name):
    return '"Playing"' in _run("busctl", "--user", "get-property", name, OBJECT, MPRIS + ".Player",
                               "PlaybackStatus")


def call(name, method):
    _run("busctl", "--user", "call", name, OBJECT, MPRIS + ".Player", method)


def current():
    """The player that plays, else the first one (None without players)."""
    names = players()
    return next((n for n in names if playing(n)), names[0] if names else None)


def control(method):
    """PlayPause, Next or Previous on the current player."""
    name = current()
    if name:
        call(name, method)


def volume(change):
    """change: "5%+", "5%-" or "mute" (toggles)."""
    if change == "mute":
        _run("wpctl", "set-mute", SINK, "toggle")
    else:
        _run("wpctl", "set-volume", "-l", "1", SINK, change)


class Pause:
    """Pauses the players that are playing, and resumes exactly those."""

    def __init__(self):
        self.paused = []

    def pause(self):
        self.paused = [n for n in players() if playing(n)]
        for name in self.paused:
            call(name, "Pause")

    def resume(self):
        for name in self.paused:
            call(name, "Play")
        self.paused = []
