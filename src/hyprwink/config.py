"""Loading and saving: config.toml (fine tuning) and the JSON files."""

import json
import logging
import os
import tempfile
import tomllib
from importlib import resources

from . import paths

log = logging.getLogger("hyprwink.config")


def _default(name):
    return tomllib.loads(resources.files("hyprwink").joinpath(name).read_text())


def _merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config():
    config = _default("default_config.toml")
    try:
        config = _merge(config, tomllib.loads(paths.CONFIG_FILE.read_text()))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:     # broken file: defaults, not a crash
        log.error("%s: %s", paths.CONFIG_FILE, e)
    return config


def write_atomic(path, text):
    """Readers never see a half-written file, also with several writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def load_json(path, default):
    """The file's content, or default when it is missing, broken or of
    another type than default."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        log.error("%s: %s", path, e)
        return default
    return data if default is None or isinstance(data, type(default)) else default


def save_json(path, data):
    write_atomic(path, json.dumps(data, indent=1))
