"""Mirror image of the webcam with the recognised hands, as a card.

CameraCard keeps its 16:9 size; without a camera it shows a placeholder,
and chips on top show the state and the recognised gesture.
"""

import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gtk, Pango, PangoCairo  # noqa: E402

from ..i18n import _  # noqa: E402
from .common import theme_color  # noqa: E402

LINKS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
         (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


class CameraView(Gtk.DrawingArea):
    """The image itself (cover-fit), hand skeletons and gesture labels."""

    def __init__(self, compact=False):
        super().__init__(hexpand=True, vexpand=False)
        self.compact = compact
        self.surface = None
        self.info = None
        self.dim = False
        self.names = {}   # gesture id -> name
        self.colors = None
        self.set_draw_func(self._draw)
        Adw.StyleManager.get_default().connect("notify::dark", lambda *a: self._reset_colors())
        Adw.StyleManager.get_default().connect("notify::accent-color-rgba", lambda *a: self._reset_colors())

    # Always 16:9: the height follows the width.
    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return (160, 640, -1, -1) if not self.compact else (160, 384, -1, -1)
        height = int(for_size * 9 / 16) if for_size > 0 else 360
        return height, height, -1, -1

    def _reset_colors(self):
        self.colors = None
        self.queue_draw()

    def set_frame(self, msg, payload):
        if msg is None or not msg.get("camera", True) or payload is None:
            self.surface, self.info = None, None
        else:
            w, h = msg["width"], msg["height"]
            self.surface = cairo.ImageSurface.create_for_data(bytearray(payload), cairo.FORMAT_ARGB32, w, h, w * 4)
            self.info = msg
        self.queue_draw()

    def _pill(self, cr, text, x, y, fg, bg):
        layout = PangoCairo.create_layout(cr)
        size = 9 if self.compact else 11
        layout.set_font_description(Pango.FontDescription.from_string(f"Sans Bold {size}"))
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        pad = 10 if not self.compact else 7
        w, h = tw + 2 * pad, th + 8
        x = x - w / 2
        cr.set_source_rgba(*bg)
        _rounded(cr, x, y - h, w, h, h / 2)
        cr.fill()
        cr.set_source_rgb(*fg)
        cr.move_to(x + pad, y - h + 4)
        PangoCairo.show_layout(cr, layout)

    def _draw(self, area, cr, width, height):
        if self.surface is None:
            return
        if self.colors is None:
            self.colors = {
                "accent": theme_color(self, "accent"),
                "other": theme_color(self, "success"),
            }
        fw, fh = self.surface.get_width(), self.surface.get_height()
        scale = max(width / fw, height / fh)          # cover the card
        ox, oy = (width - fw * scale) / 2, (height - fh * scale) / 2
        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        cr.set_source_surface(self.surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        cr.restore()
        if self.dim:
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.paint()
        for hand in self.info.get("hands", []):
            self._draw_hand(cr, hand, lambda p: (ox + p[0] * fw * scale, oy + p[1] * fh * scale))

    def _draw_hand(self, cr, hand, at):
        points = [at(p) for p in hand["landmarks"]]
        recognised = hand.get("gesture") in self.names
        color = self.colors["accent"] if recognised else (1, 1, 1)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        cr.set_source_rgba(*color, 0.9 if recognised else 0.55)
        cr.set_line_width(3 if not self.compact else 2)
        for a, b in LINKS:
            cr.move_to(*points[a])
            cr.line_to(*points[b])
        cr.stroke()
        for x, y in points:
            cr.arc(x, y, 3.5 if not self.compact else 2.5, 0, 2 * math.pi)
            cr.fill()
        if recognised:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            accent_fg = (1, 1, 1)
            self._pill(cr, self.names[hand["gesture"]], (min(xs) + max(xs)) / 2, min(ys) - 10,
                       accent_fg, (*self.colors["accent"], 0.95))


class CameraCard(Gtk.AspectFrame):
    """16:9 card with the camera image, a placeholder and state chips."""

    def __init__(self, compact=False, show_state=True):
        super().__init__(ratio=16 / 9, obey_child=False, valign=Gtk.Align.START, xalign=0)
        self.show_state = show_state
        self.view = CameraView(compact)
        self.overlay = Gtk.Overlay(child=self.view)
        self.overlay.add_css_class("camera-card")
        if compact:
            self.overlay.add_css_class("compact")
        self.overlay.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_child(self.overlay)

        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER,
                             valign=Gtk.Align.CENTER, css_classes=["camera-empty"])
        self.empty.append(Gtk.Image(icon_name="camera-disabled-symbolic", pixel_size=32 if compact else 64))
        self.empty_title = Gtk.Label(css_classes=["title-4" if compact else "title-2"])
        self.empty.append(self.empty_title)
        self.empty_text = Gtk.Label(css_classes=["dim-label"], wrap=True,
                                    justify=Gtk.Justification.CENTER)
        self.empty.append(self.empty_text)
        self.overlay.add_overlay(self.empty)

        margin = 10 if compact else 16
        self.state_chip = Gtk.Label(css_classes=["chip"], halign=Gtk.Align.START, valign=Gtk.Align.START,
                                    margin_start=margin, margin_top=margin, visible=False)
        self.overlay.add_overlay(self.state_chip)
        self.off = False
        self._set_empty(_("Connecting camera …"), "")

    @property
    def names(self):
        return self.view.names

    @names.setter
    def names(self, value):
        self.view.names = value
        self.view.queue_draw()

    def _set_empty(self, title, text):
        self.empty_title.set_label(title)
        self.empty_text.set_label(text)

    def set_frame(self, msg, payload):
        self.view.set_frame(msg, payload)
        live = self.view.surface is not None
        # "Camera off" already says it; no chip on top.
        self.off = bool(msg and msg.get("off"))
        if self.off:
            self.state_chip.set_visible(False)
        self.empty.set_visible(not live)
        if msg is None:
            self._set_empty(_("Service not running"), _("The camera service is restarting or off."))
        elif msg.get("off"):
            self._set_empty(_("Camera off"), _("Switch on with Win+G."))
        elif not live:
            self._set_empty(_("Camera not connected"),
                            _("Plug in the webcam – the picture appears by itself."))

    def set_status(self, status):
        status = status or {}
        if not self.show_state or status.get("offline") or self.off:
            self.state_chip.set_visible(False)
            return
        paused = status.get("paused")
        if status.get("holding"):
            text, active = _("Recording mode"), False
        elif status.get("dictation") == "recording":
            text, active = _("● Dictating"), True
        else:
            text, active = (_("Camera off") if paused else _("● Active")), not paused
        self.state_chip.set_label(text)
        self.state_chip.set_visible(True)
        if active:
            self.state_chip.add_css_class("active")
        else:
            self.state_chip.remove_css_class("active")
        self.view.dim = bool(paused and not status.get("holding"))
        self.view.queue_draw()


def _rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
