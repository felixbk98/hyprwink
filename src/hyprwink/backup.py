"""Export and import of the whole configuration as one ZIP file.

Contains the settings, the fine tuning, the gestures (names, actions,
recordings, photos, clips) and the gaze calibration. API keys stay in the
keyring and are not part of it.

Importing replaces everything: what the file does not contain is removed.
"""

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from . import paths
from .i18n import _
from .integration import SERVICES

MANIFEST = "hyprwink.json"
FORMAT = 1
FILES = [paths.CONFIG_FILE, paths.SETTINGS_FILE, paths.GESTURES_FILE, paths.SAMPLES_FILE,
         paths.GAZE_FILE, paths.GAZE_SAMPLES]
DIRS = [paths.PHOTO_DIR]
NAMES = {p.name for p in FILES + DIRS}


class BackupError(Exception):
    """The file is not a Hyprwink configuration or cannot be read/written."""


def save(target):
    """Write the configuration to target (a .zip file)."""
    target = Path(target)
    tmp = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
        with os.fdopen(fd, "wb") as f, zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps({"app": paths.APP, "format": FORMAT}))
            for path in FILES:
                if path.is_file():
                    z.write(path, path.name)
            for folder in DIRS:
                for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
                    if path.is_file():
                        z.write(path, path.relative_to(paths.CONFIG_DIR).as_posix())
        os.replace(tmp, target)
    except OSError as e:
        if tmp:
            Path(tmp).unlink(missing_ok=True)
        raise BackupError(str(e)) from e


def _check(z):
    """Only known names, nothing outside the configuration, JSON readable."""
    try:
        manifest = json.loads(z.read(MANIFEST))
    except (KeyError, ValueError) as e:
        raise BackupError(_("not a Hyprwink configuration")) from e
    if not isinstance(manifest, dict) or manifest.get("app") != paths.APP:
        raise BackupError(_("not a Hyprwink configuration"))
    if not isinstance(manifest.get("format"), int) or manifest["format"] > FORMAT:
        raise BackupError(_("made by a newer Hyprwink version"))
    for info in z.infolist():
        name = PurePosixPath(info.filename)
        if name.is_absolute() or ".." in name.parts or name.parts[0] not in NAMES | {MANIFEST}:
            raise BackupError(_("unexpected content: {name}").format(name=info.filename))
        if name.suffix == ".json":
            try:
                json.loads(z.read(info))
            except ValueError as e:
                raise BackupError(_("{name} is damaged").format(name=info.filename)) from e


def load(source):
    """Replace the configuration with the one in source, then restart the
    running services so they use it."""
    try:
        with zipfile.ZipFile(source) as z:
            _check(z)
            paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=paths.CONFIG_DIR, prefix=".import-") as tmp:
                z.extractall(tmp)
                for path in FILES + DIRS:
                    new = Path(tmp) / path.name
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)
                    if new.exists():
                        new.replace(path)
    except (OSError, zipfile.BadZipFile) as e:
        raise BackupError(str(e)) from e
    subprocess.run(["systemctl", "--user", "try-restart", *SERVICES], check=False)
