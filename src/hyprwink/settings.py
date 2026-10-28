"""What the user sets in the window, in settings.json.

Missing keys fall back to DEFAULTS. The services read the file again on
"reload" (sent by the window after every change).
"""

from . import config, paths

DEFAULTS = {
    "start_paused": False,
    "minimize_on_close": True,
    "gaze": False,              # focus follows gaze
    "dim_inactive": False,      # dim the other windows while focus follows gaze
    "dim_strength": 0.15,       # how much (0..1)
    "show_gaze": False,         # dot where the gaze is
    "gaze_speed": "medium",     # see core.gazefocus.DWELL
    "theme": "material",        # see ui/style.py
    "language": "",             # see i18n.py; empty: the system's
    "dictate_engine": "whisper",    # see core/stt
    "dictate_language": "",     # spoken language; empty: as "language"
    "read_engine": "piper",     # see core/tts
    "read_language": "",        # spoken language; empty: as "language"
    "read_voices": {},          # provider -> voice; missing: its default_voice()
    "read_speed": 1.0,
}


def load():
    return {**DEFAULTS, **config.load_json(paths.SETTINGS_FILE, {})}


def get(name):
    return load()[name]


def put(name, value):
    data = config.load_json(paths.SETTINGS_FILE, {})
    data[name] = value
    config.save_json(paths.SETTINGS_FILE, data)
