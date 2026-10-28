"""GTK4/libadwaita window (Kamera, Gesten, Einstellungen) and the mini view."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from .. import gestures, i18n, settings  # noqa: E402
from ..i18n import _  # noqa: E402
from . import style  # noqa: E402
from .camera import CameraCard  # noqa: E402
from .common import preview_client, status_client  # noqa: E402
from .camera_page import CameraPage  # noqa: E402
from .gestures_page import GesturesPage  # noqa: E402
from .settings_page import SettingsPage  # noqa: E402

APP_ID = "io.github.felixbk98.hyprwink"
MINI_TITLE = "Hyprwink Mini"


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Hyprwink", default_width=1100, default_height=820)
        self.stack = Adw.ViewStack()
        self.camera_page = CameraPage()
        self.gestures = GesturesPage(app.set_names)
        self.stack.add_titled_with_icon(self.camera_page, "camera", _("Camera"), "camera-web-symbolic")
        self.stack.add_titled_with_icon(self.gestures, "gestures", _("Gestures"), "input-touchpad-symbolic")
        self.settings = SettingsPage()
        self.stack.add_titled_with_icon(self.settings, "settings", _("Settings"),
                                            "emblem-system-symbolic")
        self.connect("close-request", self._on_close)
        self.stack.connect("notify::visible-child-name", self._on_page)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.stack)
        self.set_content(view)
        self.set_size_request(460, 520)

    def _on_close(self, *_):
        """Closing hides the window if wanted; the bar symbol brings it back."""
        if settings.get("minimize_on_close"):
            self.set_visible(False)
            return True
        return False

    def start_page(self):
        """Without gestures the Gesten page comes first."""
        return "camera" if gestures.load()["gestures"] else "gestures"

    def _on_page(self, *_):
        if self.stack.get_visible_child_name() == "gestures":
            self.gestures.build()

    def on_preview(self, msg, payload):
        name = self.stack.get_visible_child_name()
        if name == "camera":
            self.camera_page.camera.set_frame(msg, payload)
        elif name == "gestures":
            self.gestures.on_preview(msg, payload)

    def on_status(self, status):
        self.camera_page.set_status(status)
        self.gestures.set_status(status)


class MiniWindow(Gtk.Window):
    """Small always-on-top camera view; Hyprland rules (title) keep it floating."""

    def __init__(self, app):
        super().__init__(application=app, title=MINI_TITLE, default_width=384, default_height=216,
                         decorated=False, css_classes=["hyprwink-mini"])
        self.camera = CameraCard(compact=True)
        self.set_child(self.camera)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.main = None
        self.mini = None
        self.add_main_option("mini", 0, 0, 0, _("Mini view on/off"), None)
        self.add_main_option("setup", 0, 0, 0, _("Open gestures"), None)
        self.add_main_option("toggle", 0, 0, 0, _("Show/hide the window"), None)
        self.add_main_option("settings", 0, 0, 0, _("Show/hide the settings"), None)
        self.names = {}

    def do_startup(self):
        Adw.Application.do_startup(self)
        style.apply(settings.get("theme"))
        self.names = gestures.labels(gestures.load())
        self.preview = preview_client(self._on_preview)
        self.status = status_client(self._on_status)

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if options.get("mini"):
            self.toggle_mini()
        elif options.get("toggle") and self.main is not None and self.main.get_visible():
            self.main.close()   # hides or quits, as set
        elif options.get("settings") and self.main is not None and self.main.get_visible() \
                and self.main.stack.get_visible_child_name() == "settings":
            self.main.close()
        elif options.get("settings"):
            self.show_main("settings")
        else:
            self.show_main("gestures" if options.get("setup") else None)
        return 0

    def show_main(self, page=None):
        first = self.main is None
        if first:
            self.main = MainWindow(self)
            self.main.camera_page.camera.names = self.names
            self.main.connect("destroy", lambda *_: setattr(self, "main", None))
        if page or first:
            self.main.stack.set_visible_child_name(page or self.main.start_page())
        self.main.present()

    def reload(self):
        """After importing a configuration or changing the language: theme,
        language, names and fresh windows."""
        i18n.use()
        style.apply(settings.get("theme"))
        self.set_names(gestures.labels(gestures.load()))
        if self.main is not None:
            self.main.destroy()
            self.main = None
        if self.mini is not None:
            self.mini.destroy()
            self.mini = None
            self.toggle_mini()
        self.show_main("settings")

    def set_names(self, names):
        """Gesture names for the labels in the camera images."""
        self.names = names
        if self.main is not None:
            self.main.camera_page.camera.names = names
        if self.mini is not None:
            self.mini.camera.names = names

    def toggle_mini(self):
        if self.mini is not None:
            self.mini.close()
            return
        self.mini = MiniWindow(self)
        self.mini.camera.names = self.names
        self.mini.connect("destroy", lambda *_: self._mini_closed())
        self.mini.present()
        self._sync_mini()

    def _mini_closed(self):
        self.mini = None
        self._sync_mini()

    def _sync_mini(self):
        if self.main is not None:
            self.main.settings.show_mini(self.mini is not None)

    def _on_preview(self, msg, payload):
        if self.main is not None:
            self.main.on_preview(msg, payload)
        if self.mini is not None:
            self.mini.camera.set_frame(msg, payload)

    def _on_status(self, msg, _payload):
        if msg is None:
            msg = {"offline": True}
        if self.main is not None:
            self.main.on_status(msg)
        if self.mini is not None:
            self.mini.camera.set_status(msg)


def main(argv=None):
    return App().run(argv if argv is not None else sys.argv)
