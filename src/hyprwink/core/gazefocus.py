"""Focus follows gaze: focus the window the user looks at.

The gaze point comes from the vision service in Hyprland layout
coordinates. The window under it gets the focus once the gaze has stayed
on it for a dwell time (DWELL), so a glance across does not move the
focus.

The focused window is preferred: another window counts only once the gaze
is clearly inside it (INSET from its edges), so the focus does not jump
back and forth at a border. A window on another monitor than the focused
one needs more: the gaze must be BORDER px inside that monitor and stay
twice the dwell time, as the estimate is least sure across monitors.

A monitor without windows gets the focus like that, too (gaze inside it by
BORDER px, twice the dwell time), so a new window opens where the user
looks, as with the mouse.

The mouse wins: while it moves, and for MOUSE_PAUSE seconds after, the gaze
does not move the focus.

Self-correction while in use: the user looks at the mouse pointer while
moving it, and at a window they switch to themselves (click, keyboard).
Both moments show where the gaze really is; the difference to the
estimate slowly shifts a correction that is added to every gaze point.
"""

import time

import numpy as np

from . import hypr

# Seconds the gaze stays on a window before it gets the focus, per setting.
DWELL = {"fast": 0.15, "medium": 0.3, "slow": 0.5}
REFRESH = 0.5      # seconds between reading the window layout
POINTER = 0.1      # seconds between reading the mouse pointer
MOUSE_PAUSE = 0.5  # seconds after the last mouse movement before gaze takes over again
MOVED = 40         # px the pointer must move to count as "being looked at"
FAR = 900          # px: a larger difference is not trusted (looked elsewhere)
RATE_POINTER = 0.08
RATE_WINDOW = 0.25
INSET = 0.08       # share of a window's smaller side the gaze must be inside it
INSET_MAX = 60     # px
BORDER = 150       # px the gaze must be inside another monitor


def _towards(point, rect):
    """Shortest shift that brings point into rect (zero if already inside)."""
    (x, y), (w, h) = rect
    margin = min(w, h) * 0.15
    tx = min(max(point[0], x + margin), x + w - margin)
    ty = min(max(point[1], y + margin), y + h - margin)
    return np.array([tx - point[0], ty - point[1]])


class GazeFocus:
    def __init__(self):
        self.windows, self.read_at = [], 0.0
        self.monitors = {}
        self.candidate, self.since = None, 0.0
        self.focused = None
        self.ours = None                 # last window focused by gaze
        self.correction = np.zeros(2)
        self.pointer, self.pointer_at = None, 0.0
        self.mouse_until = 0.0
        self.dwell = DWELL["medium"]

    def _layout(self, now, point):
        if now - self.read_at <= REFRESH:
            return self.windows
        self.read_at = now
        wins = hypr.windows()
        self.monitors = hypr.monitors()
        # Floating windows lie on top; then the most recently focused.
        self.windows = sorted(wins, key=lambda c: (not c.get("floating"), c.get("focusHistoryID", 99)))
        current = next((c for c in wins if c.get("focusHistoryID") == 0), None)
        address = current["address"] if current else None
        if current and address != self.focused and address != self.ours and point is not None:
            # The user switched windows themselves: they look at it now.
            self._learn(_towards(point, (current["at"], current["size"])), RATE_WINDOW)
        self.focused = address
        return self.windows

    def _learn(self, shift, rate):
        if np.linalg.norm(shift) < FAR:
            self.correction += rate * shift

    def _watch_pointer(self, now, point):
        if now - self.pointer_at < POINTER:
            return
        self.pointer_at = now
        pos = hypr.cursor()
        if pos is None:
            return
        if self.pointer is not None:
            moved = np.hypot(pos[0] - self.pointer[0], pos[1] - self.pointer[1])
            if moved > 2:
                self.mouse_until = now + MOUSE_PAUSE
            if moved > MOVED:
                self._learn(np.asarray(pos) - point, RATE_POINTER)
        self.pointer = pos

    def _monitor_of(self, address):
        return next((c.get("monitor") for c in self.windows if c["address"] == address), None)

    def _other_monitor(self, address):
        mine = self._monitor_of(self.focused)
        return mine is not None and self._monitor_of(address) not in (None, mine)

    def window_at(self, x, y):
        for c in self.windows:
            (wx, wy), (ww, wh) = c["at"], c["size"]
            inset = 0 if c["address"] == self.focused else min(min(ww, wh) * INSET, INSET_MAX)
            if not (wx + inset <= x < wx + ww - inset and wy + inset <= y < wy + wh - inset):
                continue
            rect = self.monitors.get(c.get("monitor"))
            if rect and self._other_monitor(c["address"]):
                mx, my, mw, mh = rect
                if not (mx + BORDER <= x < mx + mw - BORDER and my + BORDER <= y < my + mh - BORDER):
                    return None
            return c["address"]
        return None

    def empty_monitor_at(self, x, y):
        """Id of the monitor without windows the gaze is clearly inside, or None."""
        for mid, (mx, my, mw, mh) in self.monitors.items():
            if mx + BORDER <= x < mx + mw - BORDER and my + BORDER <= y < my + mh - BORDER:
                return None if any(c.get("monitor") == mid for c in self.windows) else mid
        return None

    def update(self, raw, now=None, focus=True):
        """Returns the corrected gaze point (or None). focus=False: only the
        point (for the dot), the focus stays."""
        now = time.monotonic() if now is None else now
        if raw is None:
            self.candidate = None
            return None
        point = np.asarray(raw, dtype=float) + self.correction
        self._layout(now, point)
        self._watch_pointer(now, point)
        if now < self.mouse_until or not focus:
            self.candidate = None        # mouse in use; start over afterwards
            return point
        address = self.window_at(*point)
        if address is None:
            empty = self.empty_monitor_at(*point)
            address = None if empty is None else ("monitor", empty)
        if address != self.candidate:
            self.candidate, self.since = address, now
            return point
        if isinstance(address, tuple):
            if address != self.ours and now - self.since >= self.dwell * 2:
                hypr.focus_monitor(address[1])
                self.focused, self.ours = None, address
            return point
        dwell = self.dwell * (2 if self._other_monitor(address) else 1)
        if address and address != self.focused and now - self.since >= dwell:
            hypr.focus(address)
            self.focused = self.ours = address
        return point
