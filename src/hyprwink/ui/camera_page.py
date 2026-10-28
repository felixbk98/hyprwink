"""Kamera page: the camera card, on/off, recognised gesture, last action."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from .camera import CameraCard  # noqa: E402
from .common import core  # noqa: E402


class CameraPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.set_child(Adw.Clamp(maximum_size=900, child=box))

        self.camera = CameraCard()
        box.append(self.camera)

        group = Adw.PreferencesGroup()
        self.active = Adw.SwitchRow(title=_("Camera"), subtitle="Win+G")
        self.active.add_prefix(Gtk.Image(icon_name="camera-web-symbolic"))
        self._updating = False
        self.active.connect("notify::active", self._on_active)
        group.add(self.active)
        self.gesture_row = Adw.ActionRow(title=_("Recognised gesture"))
        self.gesture_row.add_prefix(Gtk.Image(icon_name="view-reveal-symbolic"))
        self.gesture_label = Gtk.Label(css_classes=["dim-label"], ellipsize=3)
        self.gesture_row.add_suffix(self.gesture_label)
        group.add(self.gesture_row)
        self.action_row = Adw.ActionRow(title=_("Last action"))
        self.action_row.add_prefix(Gtk.Image(icon_name="media-playback-start-symbolic"))
        self.action_label = Gtk.Label(css_classes=["dim-label"], ellipsize=3)
        self.action_row.add_suffix(self.action_label)
        group.add(self.action_row)
        box.append(group)

    def _on_active(self, row, _):
        if not self._updating:
            core({"cmd": "resume" if row.get_active() else "pause"})

    def set_status(self, status):
        status = status or {}
        self._updating = True
        self.active.set_active(not status.get("paused", False))
        self._updating = False
        self.active.set_sensitive(not status.get("offline"))
        self.gesture_label.set_label(self.camera.names.get(status.get("gesture"), "–"))
        action = status.get("action") or "–"
        if status.get("offline") or not status.get("vision", True):
            action = _("Service not reachable")
        elif not status.get("camera", True):
            action = _("Camera not connected")
        self.action_label.set_label(action)
        self.camera.set_status(status)
