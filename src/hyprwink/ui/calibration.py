"""Calibration of "focus follows gaze": dots on every monitor, one by one.

Each monitor gets a black fullscreen window. A dot appears; the user looks
at it, and the vision service collects head and iris values for that point
(Hyprland layout coordinates). A ring shrinking onto the dot leads the
eyes there; values are collected once it has arrived. A dot where the face
was hardly seen is repeated.

The first round covers each monitor with a full grid; any number of short
rounds (corners and middle) can follow from other sitting positions, so
the model learns how head and eyes share the movement. The dots come in a
random order with mostly long jumps, also across monitors. "Add"
(add) starts with a short round on top of the saved calibration. Esc
cancels. The mini view is hidden meanwhile (a dot may sit behind it).
"""

import json
import math
import random
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from ..core.hypr import size as hypr_size  # noqa: E402
from ..i18n import _  # noqa: E402
from .common import Hold, in_thread, theme_color, vision  # noqa: E402

SETTLE_MS = 1500    # the ring shrinks onto the dot; the eyes move there
SAMPLE_S = 1.3      # time the values are collected per dot (its first quarter is dropped)
MIN_SAMPLES = 12    # fewer usable frames per dot: the dot is repeated
RETRIES = 2
RING = 0.1          # radius the ring starts with, of the monitor's longer side
NEXT = 0.35         # opacity of the next dot, seen from the corner of the eye


def _grid(width, height, full=True):
    """Dots as fractions of a monitor. Full: 5×3 on an ultrawide, else 3×3;
    short: corners and middle."""
    wide = width / height > 2.5
    if not full:
        x0, x1 = (0.05, 0.95) if wide else (0.08, 0.92)
        return [(0.5, 0.5), (x0, 0.1), (x1, 0.1), (x0, 0.9), (x1, 0.9)]
    xs = (0.05, 0.275, 0.5, 0.725, 0.95) if wide else (0.08, 0.5, 0.92)
    return [(x, y) for y in (0.1, 0.5, 0.9) for x in xs]


def _order(points):
    """Random order with long jumps: the next dot is drawn from the farther
    half of the remaining ones."""
    rest = list(points)
    random.shuffle(rest)
    order = [rest.pop()]
    while rest:
        _, _, _, x, y, _ = order[-1]
        rest.sort(key=lambda p: (p[3] - x) ** 2 + (p[4] - y) ** 2, reverse=True)
        order.append(rest.pop(random.randrange(max(1, len(rest) // 2))))
    return order


def _monitors():
    try:
        out = subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True, timeout=2).stdout
        return sorted(json.loads(out or "[]"), key=lambda m: (m["y"], m["x"]))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


class Calibration:
    def __init__(self, app, on_done, add=False):
        self.on_done = on_done
        self.app = app
        self.monitors, self.windows = [], {}
        gdk = {m.get_connector(): m for m in Gdk.Display.get_default().get_monitors()}
        for m in _monitors():
            if m["name"] not in gdk:
                continue
            self.monitors.append(m)
            self.windows[m["name"]] = self._window(app, gdk[m["name"]], m["name"])
        self.current = None
        self.next = None          # the dot after this one, shown faintly
        self.ring = 0.0           # 1 = ring at full size, 0 = arrived on the dot
        self.retries = 0
        self.cancelled = False
        self.waiting = False      # between the rounds, waiting for a key
        if not self.monitors:
            GLib.idle_add(lambda: on_done({"ok": False, "error": "monitors"}) and False)
            return
        self.hold = Hold()
        if app.mini is not None:
            app.mini.set_visible(False)
        self.round = vision({"cmd": "gaze_start", "add": add}).get("round", 1)
        self.full = not add
        self.points = self._points(self.full)
        GLib.timeout_add(1200, lambda: self._step(0) and False)

    def _points(self, full):
        points = []
        for m in self.monitors:
            w, h = hypr_size(m)
            for fx, fy in _grid(w, h, full):
                points.append((m["name"], fx, fy, m["x"] + fx * w, m["y"] + fy * h, [m["x"], m["y"], w, h]))
        return _order(points)

    def _window(self, app, monitor, name):
        win = Gtk.Window(application=app, decorated=False, title="Hyprwink Calibration",
                         css_classes=["gaze-calibration"])
        area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        area.set_draw_func(lambda _a, cr, w, h: self._draw(name, area, cr, w, h))
        overlay = Gtk.Overlay(child=area)
        hint = Gtk.Label(label=_("Look at the dot · Esc cancels"), css_classes=["dim-label"],
                         valign=Gtk.Align.END, margin_bottom=32)
        overlay.add_overlay(hint)
        question = Gtk.Label(css_classes=["title-3"], justify=Gtk.Justification.CENTER, visible=False)
        overlay.add_overlay(question)
        win.set_child(overlay)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, keyval, *_: self._key(keyval))
        win.add_controller(keys)
        win.area, win.hint, win.question = area, hint, question
        win.fullscreen_on_monitor(monitor)
        win.present()
        return win

    def _draw(self, name, area, cr, width, height):
        accent = theme_color(area, "accent")
        if self.next and self.next[0] == name:
            _, nx, ny, *_ = self.next
            cr.set_source_rgba(*accent, NEXT)
            cr.arc(nx * width, ny * height, 8, 0, 2 * math.pi)
            cr.fill()
        if not self.current or self.current[0] != name:
            return
        _, fx, fy, *_ = self.current
        if self.ring > 0:
            cr.set_source_rgb(*accent)
            cr.set_line_width(3 + 3 * self.ring)
            cr.arc(fx * width, fy * height, 16 + (RING * max(width, height) - 16) * self.ring, 0, 2 * math.pi)
            cr.stroke()
        cr.set_source_rgb(*accent)
        cr.arc(fx * width, fy * height, 16, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.arc(fx * width, fy * height, 4, 0, 2 * math.pi)
        cr.fill()

    def _key(self, keyval):
        if keyval == Gdk.KEY_Escape:
            return self._cancel()
        if self.waiting and keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.waiting = False
            self._ask(False)
            if keyval == Gdk.KEY_space:
                self.round += 1
                self.full = False
                self.points = self._points(False)
                GLib.timeout_add(1200, lambda: self._step(0) and False)
            else:
                self._finish_round()
            return True
        return False

    def _ask(self, on):
        text = _("Round {n} done\n\nSit differently (lean back, to the side, closer)\n\nSpace: another round · Enter: done").format(
            n=self.round)
        for win in self.windows.values():
            win.question.set_label(text)
            win.question.set_visible(on)
            win.hint.set_visible(not on)

    def _hint(self, text):
        for win in self.windows.values():
            win.hint.set_label(text)

    def _finish_round(self):
        in_thread(lambda: vision({"cmd": "gaze_finish", "save": True}, timeout=20), self._finish)

    def _redraw(self):
        for win in self.windows.values():
            win.area.queue_draw()

    def _step(self, i):
        if self.cancelled:
            return
        if i >= len(self.points):
            self.current = self.next = None
            self._redraw()
            self.waiting = True
            self._ask(True)
            return
        self.current = self.points[i]
        self.next = self.points[i + 1] if i + 1 < len(self.points) else None
        self._shrink(i, GLib.get_monotonic_time())

    def _shrink(self, i, start):
        """Ring from RING down onto the dot, fast at first and slow near it,
        then collect."""
        if self.cancelled:
            return
        done = (GLib.get_monotonic_time() - start) / 1000 / SETTLE_MS
        self.ring = max(0.0, 1 - done) ** 2
        self._redraw()
        if self.ring > 0:
            GLib.timeout_add(16, lambda: self._shrink(i, start) and False)
        else:
            self._sample(i, self.current)

    def _sample(self, i, point):
        if self.cancelled:
            return
        name, _, _, x, y, rect = point
        msg = {"cmd": "gaze_sample", "x": x, "y": y, "monitor": name, "rect": rect, "round": self.round,
               "full": self.full, "seconds": SAMPLE_S}
        in_thread(lambda: vision(msg, timeout=5), lambda reply: self._sampled(i, reply))

    def _sampled(self, i, reply):
        if self.cancelled:
            return
        if reply.get("samples", 0) < MIN_SAMPLES and self.retries < RETRIES:
            self.retries += 1
            self._hint(_("Face not recognised – look at the dot again"))
            self._step(i)
            return
        self.retries = 0
        self._hint(_("Look at the dot · Esc cancels"))
        self._step(i + 1)

    def _close(self):
        for win in self.windows.values():
            win.destroy()
        self.windows = {}
        self.hold.close()
        if self.app.mini is not None:
            self.app.mini.set_visible(True)

    def _cancel(self):
        if not self.cancelled:
            self.cancelled = True
            vision({"cmd": "gaze_finish", "save": False})
            self._close()
            self.on_done({"ok": False, "error": "cancelled"})
        return True

    def _finish(self, reply):
        self._close()
        self.on_done(reply)
