"""Where Hyprwink keeps its files (XDG directories)."""

import os
from pathlib import Path

APP = "hyprwink"


def _xdg(var, fallback):
    return Path(os.environ.get(var) or Path.home() / fallback)


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / APP
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / APP

# Runtime
CORE_SOCKET = RUNTIME_DIR / "core.sock"
VISION_SOCKET = RUNTIME_DIR / "vision.sock"
DICTATION_STATE = RUNTIME_DIR / "dictation"         # idle | recording | transcribing
ANSWERS_DIR = RUNTIME_DIR / "answers"               # Claude Code answers per session

# Configuration
CONFIG_FILE = CONFIG_DIR / "config.toml"            # fine tuning, see default_config.toml
SETTINGS_FILE = CONFIG_DIR / "settings.json"        # what the window sets
GESTURES_FILE = CONFIG_DIR / "gestures.json"        # name and action per gesture
SAMPLES_FILE = CONFIG_DIR / "samples.json"          # recordings per gesture
PHOTO_DIR = CONFIG_DIR / "photos"                   # photo and clip per gesture
GAZE_FILE = CONFIG_DIR / "gaze.json"                # gaze calibration
GAZE_SAMPLES = CONFIG_DIR / "gaze-samples.json"     # its measured values (head, iris; no images)

# Models: downloaded again when missing
MODEL_DIR = CACHE_DIR / "models"
HAND_MODEL = MODEL_DIR / "hand_landmarker.task"
FACE_MODEL = MODEL_DIR / "face_landmarker.task"
WHISPER_DIR = MODEL_DIR / "whisper"
VOICE_DIR = CACHE_DIR / "voices"                    # Piper voices
