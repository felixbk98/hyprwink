"""Setting Hyprwink up for the current user, and removing it again.

`hyprwink setup` (after installing, run again any time): models, the two
systemd user services and the app launcher (pointing at this installation),
the Quickshell plugin (bar symbol and dictation pill, if an Omarchy-style
Quickshell config is found) and the Claude Code Stop hook for reading aloud.

`hyprwink remove` (before uninstalling): all of that plus the user's data,
keys and the Hyprland blocks copied from data/hyprland.lua.

Lines added to other files carry the marker "// hyprwink"; Hyprland blocks
run from "-- Hyprwink" to "-- End Hyprwink".
"""

import json
import os
import re
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import config, models, paths
from .core import providers
from .i18n import _

SERVICES = ["hyprwink-core.service", "hyprwink-vision.service"]
DESKTOP = "io.github.felixbk98.hyprwink.desktop"
DATA = resources.files("hyprwink") / "data"
UNIT_DIR = paths.CONFIG_DIR.parent / "systemd" / "user"
APP_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "applications"
SHELL = paths.CONFIG_DIR.parent / "quickshell" / "shell"
HYPR = paths.CONFIG_DIR.parent / "hypr"
CLAUDE = Path.home() / ".claude" / "settings.json"
HOOK = "hyprwink hook"
MARK = "  // hyprwink"
IMPORT = "import qs.plugins.hyprwink as Hyprwink" + MARK


def _systemctl(*args):
    subprocess.run(["systemctl", "--user", *args], check=False)


def _add_import(lines):
    last = max((i for i, line in enumerate(lines) if line.startswith("import ")), default=None)
    if last is not None:
        lines.insert(last + 1, IMPORT)
    return last is not None


def _quickshell():
    if not (SHELL / "plugins").is_dir():
        return
    target = SHELL / "plugins" / "hyprwink"
    target.mkdir(parents=True, exist_ok=True)
    # Overwritten in place: Quickshell reloads changed files, but loses
    # track of a folder that is deleted and created again.
    with resources.as_file(resources.files("hyprwink") / "quickshell") as source:
        names = {f.name for f in source.iterdir() if f.is_file()}
        for name in names:
            if not (target / name).exists() or (target / name).read_bytes() != (source / name).read_bytes():
                shutil.copyfile(source / name, target / name)
    for old in target.iterdir():
        if old.name not in names:
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    print(_("Quickshell plugin"))
    # Bar symbol left of the settings symbol (Omarchy-style bar).
    bar = SHELL / "bar" / "Bar.qml"
    if bar.exists() and MARK not in bar.read_text():
        lines = bar.read_text().splitlines()
        anchor = next((i for i, line in enumerate(lines)
                       if re.match(r"\s*Settings\.BarWidget \{", line)), None)
        if anchor is not None:
            indent = re.match(r"\s*", lines[anchor]).group(0)
            lines.insert(anchor, f"{indent}Hyprwink.BarWidget {{ bar: barHost; "
                                 f"anchors.verticalCenter: parent.verticalCenter }}{MARK}")
            _add_import(lines)
            config.write_atomic(bar, "\n".join(lines) + "\n")
    # Dictation pill: once in the shell root, before its closing brace.
    root = SHELL / "shell.qml"
    if root.exists() and MARK not in root.read_text():
        lines = root.read_text().splitlines()
        close = max((i for i, line in enumerate(lines) if line.startswith("}")), default=None)
        if close is not None:
            lines.insert(close, "  Hyprwink.DictationPill {}" + MARK)
            _add_import(lines)
            config.write_atomic(root, "\n".join(lines) + "\n")


def _claude_hook(add):
    """The Stop hook keeps each session's last answer for reading aloud."""
    data = config.load_json(CLAUDE, None)
    if not isinstance(data, dict):
        return
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    present = any(h.get("command") == HOOK for entry in stop for h in entry.get("hooks", []))
    if add and not present:
        stop.append({"hooks": [{"type": "command", "command": HOOK}]})
        print(_("Claude Code hook"))
    elif not add and present:
        for entry in stop:
            entry["hooks"] = [h for h in entry.get("hooks", []) if h.get("command") != HOOK]
        data["hooks"]["Stop"] = [entry for entry in stop if entry.get("hooks")]
    else:
        return
    if not data["hooks"]["Stop"]:
        del data["hooks"]["Stop"]
    if not data["hooks"]:
        del data["hooks"]
    config.write_atomic(CLAUDE, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _launchers():
    """Services and app launcher, pointing at the Python and the command of
    this installation (pipx, a venv or a distribution package alike)."""
    python = sys.executable
    command = str(Path(python).with_name("hyprwink"))
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    for name in SERVICES:
        config.write_atomic(UNIT_DIR / name, (DATA / name).read_text().replace("{python}", python))
    APP_DIR.mkdir(parents=True, exist_ok=True)
    config.write_atomic(APP_DIR / DESKTOP, (DATA / DESKTOP).read_text().replace("{hyprwink}", command))
    _systemctl("daemon-reload")


def setup():
    print(_("Models (hand, face, voice, Whisper large-v3-turbo ~1.6 GB)"))
    models.download()
    _launchers()
    _quickshell()
    _claude_hook(True)
    _systemctl("enable", *SERVICES)
    _systemctl("restart", *SERVICES)
    print(_("Done. Shortcuts and window rule for your Hyprland config: {path} · Gestures: hyprwink ui --setup")
          .format(path=DATA / "hyprland.lua"))


def remove():
    _systemctl("disable", "--now", *SERVICES)
    for path in [UNIT_DIR / name for name in SERVICES] + [APP_DIR / DESKTOP]:
        path.unlink(missing_ok=True)
    _systemctl("daemon-reload")
    subprocess.run(["pkill", "-f", "hyprwink ui"], check=False)
    _claude_hook(False)
    shutil.rmtree(SHELL / "plugins" / "hyprwink", ignore_errors=True)
    for path in (SHELL / "bar" / "Bar.qml", SHELL / "shell.qml"):
        if path.exists():
            text = path.read_text()
            kept = [line for line in text.splitlines() if not line.endswith(MARK)]
            if len(kept) != len(text.splitlines()):
                config.write_atomic(path, "\n".join(kept) + "\n")
    for path in HYPR.rglob("*.lua") if HYPR.is_dir() else ():
        text = path.read_text()
        new = re.sub(r"^-- Hyprwink\b.*?^-- End Hyprwink\n", "", text, flags=re.S | re.M)
        if new != text:
            config.write_atomic(path, new)
    subprocess.run(["hyprctl", "reload"], capture_output=True, check=False)
    subprocess.run(["secret-tool", "clear", "service", providers.SERVICE], check=False)
    for directory in (paths.CONFIG_DIR, paths.CACHE_DIR, paths.RUNTIME_DIR):
        shutil.rmtree(directory, ignore_errors=True)
    print(_("Hyprwink removed for this user. Now uninstall it, e.g. pipx uninstall hyprwink"))
