"""Connections to the services and shared helpers for the GTK interface."""

import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import ipc, paths  # noqa: E402


class StreamClient:
    """Background reader that hands the newest message to the GTK main loop.

    Frames arrive faster than they may be drawn; only the latest one is kept
    and delivered once the main loop is free.
    """

    def __init__(self, path, request, callback):
        self.path = path
        self.request = request
        self.callback = callback
        self.latest = None
        self.pending = False
        self.lock = threading.Lock()
        self.connected = False
        self.running = True
        self.conn = None
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False
        if self.conn:
            self.conn.close()

    def _run(self):
        while self.running:
            try:
                conn = ipc.connect(self.path, timeout=2)
                self.conn = conn
                if not self.running:
                    conn.close()
                    break
                conn.send(self.request)
                self.connected = True
                while True:
                    msg, payload = conn.recv()
                    if msg is None:
                        break
                    self._deliver(msg, payload)
            except OSError:
                pass
            if self.connected:
                self.connected = False
                if self.running:
                    self._deliver(None, None)
            time.sleep(1)

    def _deliver(self, msg, payload):
        with self.lock:
            self.latest = (msg, payload)
            if self.pending:
                return
            self.pending = True
        GLib.idle_add(self._flush)

    def _flush(self):
        with self.lock:
            item, self.latest, self.pending = self.latest, None, False
        if item is not None:
            self.callback(*item)
        return False


def preview_client(callback):
    """Preview frames; without a frame for 2 s the camera counts as gone."""
    state = {"last": time.monotonic(), "stale": False}

    def seen(msg, payload):
        state["last"] = time.monotonic()
        state["stale"] = False
        callback(msg, payload)

    def watchdog():
        if time.monotonic() - state["last"] > 2 and not state["stale"]:
            state["stale"] = True
            callback({"type": "preview", "camera": False}, None)
        return True
    GLib.timeout_add(500, watchdog)
    return StreamClient(paths.VISION_SOCKET, {"cmd": "preview"}, seen)


def status_client(callback):
    return StreamClient(paths.CORE_SOCKET, {"cmd": "watch"}, callback)


def core(msg, timeout=3):
    try:
        return ipc.request(paths.CORE_SOCKET, msg, timeout)
    except OSError as e:
        return {"ok": False, "error": str(e)}


def vision(msg, timeout=3):
    try:
        return ipc.request(paths.VISION_SOCKET, msg, timeout)
    except OSError as e:
        return {"ok": False, "error": str(e)}


def in_thread(fn, done=None):
    """Run fn() off the main loop, then done(result) on it."""
    def run():
        result = fn()
        if done:
            GLib.idle_add(lambda: done(result) and False)
    threading.Thread(target=run, daemon=True).start()


def theme_color(widget, css_class):
    """Colour of a libadwaita style class (follows matugen and light/dark)."""
    probe = Gtk.Label()
    probe.add_css_class(css_class)
    probe.set_parent(widget)
    rgba = probe.get_color()
    probe.unparent()
    return rgba.red, rgba.green, rgba.blue


def no_wheel(widget):
    """Scrolling the page with the mouse wheel must not change sliders: pass
    the wheel on to the surrounding scrolled window instead."""
    def scroll(_controller, _dx, dy):
        parent = widget.get_parent()
        while parent is not None and not isinstance(parent, Gtk.ScrolledWindow):
            parent = parent.get_parent()
        if parent is not None:
            adj = parent.get_vadjustment()
            adj.set_value(adj.get_value() + dy * 50)
        return True
    controller = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    controller.connect("scroll", scroll)
    widget.add_controller(controller)


def full_list(combo):
    """Entries of a combo row's drop-down list are shown in full (no "…"),
    the selected one with a check mark."""
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, item):
        box = Gtk.Box(spacing=12)
        box.append(Gtk.Label(xalign=0, hexpand=True, wrap=True, max_width_chars=60))
        box.append(Gtk.Image(icon_name="object-select-symbolic"))
        item.set_child(box)

    def mark(item):
        item.get_child().get_last_child().set_opacity(1 if item.get_item() == combo.get_selected_item() else 0)

    def bind(_factory, item):
        item.get_child().get_first_child().set_label(item.get_item().get_string())
        mark(item)
        item.watch = combo.connect("notify::selected-item", lambda *_: mark(item))

    def unbind(_factory, item):
        combo.disconnect(item.watch)

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    factory.connect("unbind", unbind)
    combo.set_list_factory(factory)


class Choice(Adw.ExpanderRow):
    """Row over {value: label} that opens in place, with radio buttons;
    on_change(value) when one is picked. With max_height the options scroll
    within that height, the row itself stays put."""

    def __init__(self, title, options, selected=None, on_change=None, max_height=None):
        super().__init__(title=title)
        self.options = options
        self.on_change = on_change
        self.radios = {}
        self.rows = {}
        self.quiet = False
        first = None
        options_list = None
        if max_height:
            options_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["choice-list"])
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=options_list,
                                          max_content_height=max_height, propagate_natural_height=True)
            self.add_row(Gtk.ListBoxRow(child=scroller, activatable=False, css_classes=["choice-scroll"]))
        for value, label in options.items():
            radio = Gtk.CheckButton(valign=Gtk.Align.CENTER, group=first, css_classes=["choice-radio"])
            first = first or radio
            radio.connect("toggled", self._toggled, value)
            row = Adw.ActionRow(title=label, activatable_widget=radio)
            row.add_prefix(radio)
            (options_list.append if options_list else self.add_row)(row)
            self.radios[value] = radio
            self.rows[value] = row
        self.select(selected if selected in options else next(iter(options)))

    def select(self, value):
        """Show value as chosen (without on_change)."""
        self._mark(value)
        self.quiet = True
        self.radios[value].set_active(True)
        self.quiet = False

    def _toggled(self, radio, value):
        if radio.get_active() and not self.quiet:
            self._mark(value)
            self.set_expanded(False)
            if self.on_change:
                self.on_change(value)

    def _mark(self, value):
        self.value = value
        self.set_subtitle(self.options[value])
        for other, row in self.rows.items():
            (row.add_css_class if other == value else row.remove_css_class)("chosen")


class Hold:
    """Blocks gesture actions (and keeps the camera on) while a gesture or
    the gaze is being set up."""

    def __init__(self):
        try:
            self.conn = ipc.connect(paths.CORE_SOCKET, timeout=2)
            self.conn.sock.settimeout(2)
            self.conn.send({"cmd": "hold"})
            self.conn.recv()
            self.conn.sock.settimeout(None)
        except OSError:
            self.conn = None

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
