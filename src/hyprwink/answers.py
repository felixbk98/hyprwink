"""Claude Code answers per window, written by the Stop hook (cli.cmd_hook).

The hook stores each session's answer together with the pid of its claude
process. A terminal window belongs to a session when that process runs
inside it. Other windows (also Claude Code in the browser, which does not
tell which session it shows) get no answer: only marked text is read there.
"""

import fcntl
import os
import time

from . import config, paths

DIR = paths.ANSWERS_DIR
INDEX = DIR / "sessions.json"


def _parent(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def _ancestors(pid):
    seen = []
    while pid > 1 and len(seen) < 64:
        seen.append(pid)
        pid = _parent(pid)
    return seen


def _claude_pid():
    """The claude process that runs this hook."""
    for pid in _ancestors(os.getppid()):
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() == "claude":
                    return pid
        except OSError:
            pass
    return 0


def answered(session, text):
    if not session.replace("-", "").isalnum() or not text.strip():
        return
    DIR.mkdir(parents=True, exist_ok=True)
    config.write_atomic(DIR / f"{session}.txt", text)
    # Several sessions may end at the same moment.
    with open(DIR / "sessions.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = config.load_json(INDEX, {})
        index[session] = {"time": time.time(), "pid": _claude_pid()}
        config.save_json(INDEX, index)


def for_window(client):
    """(time, text) of the answer to read for that window, or None."""
    window_pid = client.get("pid", 0)
    best = None
    for session, info in config.load_json(INDEX, {}).items():
        path = DIR / f"{session}.txt"
        pid = info.get("pid", 0)
        if not path.exists() or not pid or not os.path.exists(f"/proc/{pid}"):
            continue
        if window_pid and window_pid in _ancestors(pid):
            if best is None or info["time"] > best[0]:
                best = (info["time"], path)
    return (best[0], best[1].read_text()) if best else None
