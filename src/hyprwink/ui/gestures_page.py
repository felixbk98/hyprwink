"""Gesten page: grouped by action, each with the gestures that trigger it.

An action can have several gestures (e.g. left and right hand, or variants).
"""

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

from .. import config, gestures, paths  # noqa: E402
from ..i18n import N_, _  # noqa: E402
from .camera import CameraCard  # noqa: E402
from .capture import Capture, photo  # noqa: E402
from ..vision.describe import describe_entry  # noqa: E402
from .common import Choice, Hold, core, full_list, vision  # noqa: E402

KINDS = [("builtin", value, label) for value, label in gestures.BUILTIN.items()] + [
    ("key", None, N_("Keyboard shortcut …")),
    ("app", None, N_("Start a program …")),
    ("command", None, N_("Run a command …")),
    ("wish", None, N_("Own wish …")),
]


def _apps():
    """Installed programs shown in menus: [(desktop id, name)] by name."""
    apps = [(a.get_id(), a.get_display_name()) for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()]
    return sorted(apps, key=lambda a: a[1].casefold())
MODIFIERS = [(Gdk.ModifierType.CONTROL_MASK, "CTRL"), (Gdk.ModifierType.SHIFT_MASK, "SHIFT"),
             (Gdk.ModifierType.ALT_MASK, "ALT"), (Gdk.ModifierType.SUPER_MASK, "SUPER")]


def _key(action):
    return json.dumps(action, sort_keys=True)


class GesturesPage(Gtk.ScrolledWindow):
    def __init__(self, on_names):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.on_names = on_names     # tell the app the gesture names changed
        self.rows = {}
        self.editor = None
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                           margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.set_child(Adw.Clamp(maximum_size=900, child=self.box))
        # Reordering: grab a row at its handle and move it up or down live.
        drag = Gtk.GestureDrag(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", lambda _g, _dx, dy: self._drag_to(dy))
        drag.connect("drag-end", lambda *_: self._drag_end())
        self.box.add_controller(drag)
        self.dragging = None
        self.build()

    def build(self):
        child = self.box.get_first_child()
        while child:
            self.box.remove(child)
            child = self.box.get_first_child()
        self.data = gestures.load()
        # Labels in the camera image: the action a gesture triggers.
        self.on_names(gestures.labels(self.data))
        samples = config.load_json(paths.SAMPLES_FILE, {})

        add = Gtk.Button(css_classes=["suggested-action", "pill"], valign=Gtk.Align.CENTER,
                         child=Adw.ButtonContent(icon_name="list-add-symbolic", label=_("New gesture")))
        add.connect("clicked", lambda *_: self._edit(None, None))
        self.rows = {}
        self.groups = []   # [(group widget, [gesture ids])] in screen order
        if not self.data["gestures"]:
            add.set_halign(Gtk.Align.CENTER)
            self.box.append(Adw.StatusPage(icon_name="input-touchpad-symbolic", title=_("No gestures yet"),
                                           child=add))
            return

        groups = {}
        for g in self.data["gestures"]:
            groups.setdefault(_key(g["action"]), []).append(g)
        for items in groups.values():
            action = items[0]["action"]
            more = Gtk.Button(valign=Gtk.Align.CENTER, child=Adw.ButtonContent(
                icon_name="list-add-symbolic", label=_("Another gesture")))
            more.connect("clicked", lambda *_, a=action: self._edit(None, a))
            group = Adw.PreferencesGroup(title=gestures.action_label(action), header_suffix=more)
            self.groups.append((group, [g["id"] for g in items]))
            for g in items:
                entry = samples.get(g["id"], {})
                description = describe_entry(entry)
                # The group already shows the action: an own name only when it differs.
                if g["name"] in (gestures.action_label(action), description):
                    row = Adw.ActionRow(title=description or g["name"], activatable=True, title_lines=2)
                else:
                    row = Adw.ActionRow(title=g["name"], activatable=True, subtitle_lines=2, subtitle=description)
                # add_prefix puts each new prefix in front: handle ends up leftmost.
                row.add_prefix(photo(g["id"], 48))
                handle = Gtk.Image(icon_name="open-menu-symbolic", css_classes=["drag-handle"])
                handle.set_cursor(Gdk.Cursor.new_from_name("grab"))
                handle.gid = g["id"]
                row.add_prefix(handle)
                delete = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                    css_classes=["flat", "delete-button"])
                delete.connect("clicked", lambda *_, g=g: self.delete(g["id"]))
                row.add_suffix(delete)
                row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                row.connect("activated", lambda *_, g=g: self._edit(g, g["action"]))
                group.add(row)
                self.rows[g["id"]] = row
            self.box.append(group)

        # Two halves of the same width and height.
        buttons = Gtk.Box(spacing=12, homogeneous=True)
        add.set_valign(Gtk.Align.FILL)
        add.remove_css_class("pill")
        add.add_css_class("bottom-button")
        add.get_child().set_halign(Gtk.Align.CENTER)
        buttons.append(add)
        clear = Gtk.Button(css_classes=["destructive-action", "bottom-button"], child=Adw.ButtonContent(
            icon_name="user-trash-symbolic", label=_("Delete all gestures"), halign=Gtk.Align.CENTER))
        clear.connect("clicked", lambda *_: self._confirm_clear())
        buttons.append(clear)
        self.box.append(buttons)

    # ------------------------------------------------------------- reorder

    def _drag_begin(self, gesture, x, y):
        widget = self.box.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget is not None and widget is not self.box and not hasattr(widget, "gid"):
            widget = widget.get_parent()
        if widget is None or not hasattr(widget, "gid"):
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        adj = self.get_vadjustment()
        self.dragging = {"gid": widget.gid, "y0": y, "v0": adj.get_value(), "dy": 0.0}
        self.rows[widget.gid].add_css_class("dragging")
        self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
        self.dragging["timer"] = GLib.timeout_add(30, self._autoscroll)

    def _pointer_y(self):
        """Pointer position in the list, also after scrolling while dragging."""
        d = self.dragging
        return d["y0"] + d["dy"] + self.get_vadjustment().get_value() - d["v0"]

    def _autoscroll(self):
        """Near the top or bottom edge the page scrolls along."""
        if not self.dragging:
            return False
        ok, point = self.box.compute_point(self, Graphene.Point().init(0, self._pointer_y()))
        if ok:
            adj, edge = self.get_vadjustment(), 60
            step = 0
            if point.y < edge:
                step = -(edge - point.y) / 3
            elif point.y > self.get_height() - edge:
                step = (point.y - self.get_height() + edge) / 3
            if step:
                adj.set_value(adj.get_value() + step)
                self._place()
        return True

    def _drag_to(self, dy):
        if self.dragging:
            self.dragging["dy"] = dy
            self._place()

    def _layout(self):
        """Middles of the actions and their rows, computed from the heights
        (which do not change while reordering), so the result is right at
        once instead of after the next layout pass."""
        spacing, top, middles = self.box.get_spacing(), 0.0, []
        for group, ids in self.groups:
            height = group.get_height()
            rows = [self.rows[gid].get_height() for gid in ids]
            y = top + height - sum(rows)          # rows start below the title
            row_middles = []
            for h in rows:
                row_middles.append(y + h / 2)
                y += h
            middles.append((top + height / 2, row_middles))
            top += height + spacing
        return middles

    def _place(self):
        """Move the grabbed row (or its whole action) past its neighbours."""
        d = self.dragging
        if not d:
            return
        y = self._pointer_y()
        for _ in range(len(self.rows) + len(self.groups)):
            middles = self._layout()
            gi = next(i for i, (_, ids) in enumerate(self.groups) if d["gid"] in ids)
            group, ids = self.groups[gi]
            if gi > 0 and y < middles[gi - 1][0]:
                self.box.reorder_child_after(group, self.groups[gi - 1][0].get_prev_sibling())
                self.groups[gi - 1], self.groups[gi] = self.groups[gi], self.groups[gi - 1]
                continue
            if gi < len(self.groups) - 1 and y > middles[gi + 1][0]:
                self.box.reorder_child_after(group, self.groups[gi + 1][0])
                self.groups[gi + 1], self.groups[gi] = self.groups[gi], self.groups[gi + 1]
                continue
            j, rows = ids.index(d["gid"]), middles[gi][1]
            if j > 0 and y < rows[j - 1]:
                ids[j - 1], ids[j] = ids[j], ids[j - 1]
            elif j < len(ids) - 1 and y > rows[j + 1]:
                ids[j + 1], ids[j] = ids[j], ids[j + 1]
            else:
                break
            for gid in ids:
                group.remove(self.rows[gid])
            for gid in ids:
                group.add(self.rows[gid])

    def _drag_end(self):
        d, self.dragging = self.dragging, None
        if not d:
            return
        GLib.source_remove(d["timer"])
        self.set_cursor(None)
        self.rows[d["gid"]].remove_css_class("dragging")
        data = gestures.load()
        by_id = gestures.by_id(data)
        order = [gid for _, ids in self.groups for gid in ids]
        data["gestures"] = [by_id[gid] for gid in order if gid in by_id] + \
            [g for g in data["gestures"] if g["id"] not in order]
        gestures.save(data)

    def delete(self, gid):
        """Remove a gesture with its recording, photo and clip."""
        data = gestures.load()
        data["gestures"] = [g for g in data["gestures"] if g["id"] != gid]
        gestures.save(data)
        vision({"cmd": "delete", "gesture": gid})
        core({"cmd": "reload"})
        self.build()

    def _confirm_clear(self):
        dialog = Adw.AlertDialog(heading=_("Delete all gestures?"),
                                 body=_("Recordings and photos are deleted."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, response: response == "delete" and self._clear())
        dialog.present(self.get_root())

    def _clear(self):
        data = gestures.load()
        data["gestures"] = []
        gestures.save(data)
        vision({"cmd": "delete_all"})
        core({"cmd": "reload"})
        self.build()

    def set_status(self, status):
        current = status.get("gesture") if status else None
        for gid, row in self.rows.items():
            if gid == current:
                row.add_css_class("recognized")
            else:
                row.remove_css_class("recognized")

    def on_preview(self, msg, payload):
        if self.editor:
            self.editor.on_preview(msg, payload)

    def _edit(self, gesture, action):
        self.editor = Editor(self, gesture, action)
        self.editor.present(self.get_root())

    def editor_closed(self):
        self.editor = None
        vision({"cmd": "cleanup"})
        self.build()
        core({"cmd": "reload"})


class Editor(Adw.Dialog):
    """Record a gesture and choose what it does (also a free-text wish)."""

    def __init__(self, page, gesture, action):
        self.page = page
        self.new = gesture is None
        self.gesture = dict(gesture) if gesture else {"id": gestures.new_id(), "action": action}
        super().__init__(title=_("New gesture") if self.new else _("Edit gesture"), content_width=1100)
        self.hold = Hold()
        self.capturing_key = False

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        # Bottom bar on the same 24 px margins as the content, so its buttons
        # line up with the columns above.
        bar = Gtk.Box(spacing=12, margin_start=24, margin_end=24, margin_bottom=24)
        if not self.new:
            delete = Gtk.Button(css_classes=["destructive-action"], child=Adw.ButtonContent(
                icon_name="user-trash-symbolic", label=_("Delete")))
            delete.connect("clicked", lambda *_: self._delete())
            bar.append(delete)
        bar.append(Gtk.Box(hexpand=True))
        if not self.new:
            more = Gtk.Button(child=Adw.ButtonContent(icon_name="list-add-symbolic", label=_("Another gesture")))
            more.connect("clicked", lambda *_: self._more())
            bar.append(more)
        save = Gtk.Button(label=_("Save"), css_classes=["suggested-action"])
        save.connect("clicked", lambda *_: self._save())
        bar.append(save)
        view.add_bottom_bar(bar)

        box = Gtk.Box(spacing=24, margin_top=12, margin_bottom=24, margin_start=24, margin_end=24)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, width_request=420)
        names = Adw.PreferencesGroup()
        self.name = Adw.EntryRow(title=_("Name of the gesture"), text=self.gesture.get("name", ""))
        names.add(self.name)
        # A pose is held still; a movement is made (e.g. both hands drawn apart).
        sample = config.load_json(paths.SAMPLES_FILE, {}).get(self.gesture["id"], {})
        # A swipe (hand shape for any direction) counts as a movement here.
        self.saved_kind = {"swipe": "motion"}.get(sample.get("kind"), sample.get("kind", "pose")) if sample else None
        self.type = Choice(_("Type"), {"pose": _("Pose"), "motion": _("Movement")}, self.saved_kind or "pose",
                           on_change=lambda _: self._type_changed())
        names.add(self.type)
        left.append(names)
        form = Adw.PreferencesGroup(title=_("What should the gesture do?"))
        self.kind = Choice(_("Action"), {i: _(k[2]) for i, k in enumerate(KINDS)},
                           on_change=lambda _: self._kind_changed(), max_height=330)
        form.add(self.kind)
        self.key_row = Adw.ActionRow(title=_("Keyboard shortcut"))
        key_button = Gtk.Button(label=_("Set"), valign=Gtk.Align.CENTER, css_classes=["row-button"])
        key_button.connect("clicked", lambda *_: self._capture_key())
        self.key_row.add_suffix(key_button)
        form.add(self.key_row)
        self.apps = _apps()
        self.app_row = Adw.ComboRow(title=_("Program"), use_subtitle=True, enable_search=True,
                                    model=Gtk.StringList.new([name for _, name in self.apps]),
                                    expression=Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        full_list(self.app_row)
        self.app_row.connect("notify::selected", lambda *_: self._name_from_action())
        form.add(self.app_row)
        self.command_row = Adw.EntryRow(title=_("Command"))
        self.command_row.connect("changed", lambda *_: self._name_from_action())
        form.add(self.command_row)
        left.append(form)

        self.wish_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.wish_box.append(Gtk.Label(label=_("Only saved, it does nothing yet. Tell Claude Code and it implements it."),
                                       wrap=True, xalign=0, css_classes=["dim-label"]))
        self.wish = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, height_request=140,
                                 top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        self.wish.get_buffer().connect("changed", lambda *_: self._name_from_action())
        self.wish_box.append(Gtk.Frame(child=self.wish))
        left.append(self.wish_box)
        self.error = Gtk.Label(css_classes=["error"], xalign=0, wrap=True)
        left.append(self.error)
        box.append(left)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, hexpand=True)
        self.camera = CameraCard(show_state=False)
        self.camera.names = gestures.labels(gestures.load())
        right.append(self.camera)
        self.capture = Capture()
        self.capture.names = {gid: f"„{label}“" for gid, label in self.camera.names.items()}
        self.capture.kind = self.type.value
        self.capture.prepare(self.gesture["id"])
        if not self.new:
            self.capture.status.set_label(_("Saved."))
            self.capture.record_button.set_label(_("Record anew"))
            self.capture._show_photo(True)
        right.append(self.capture)
        box.append(right)
        view.set_content(box)
        self.set_child(view)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        self.connect("closed", self._closed)
        self._load_action()

    def _type_changed(self):
        """Another type needs a new recording (the old one stays until then)."""
        self.capture.kind = self.type.value
        self.capture.prepare(self.gesture["id"])
        if self.type.value == self.saved_kind:
            self.capture.status.set_label(_("Saved."))
            self.capture.record_button.set_label(_("Record anew"))
            self.capture._show_photo(True)

    def _load_action(self):
        action = self.gesture.get("action") or {"type": "builtin", "value": "dictate_start"}
        # The name follows the action as long as it is empty or was filled in from it.
        self.auto_name = gestures.action_label(action) if self.gesture.get("name") else ""
        for i, (kind, value, _) in enumerate(KINDS):
            if kind == action["type"] and (value is None or value == action["value"]):
                self.kind.select(i)
                break
        self.key_combo = action["value"] if action["type"] == "key" else None
        ids = [app_id for app_id, _ in self.apps]
        if action["type"] == "app" and action["value"] in ids:
            self.app_row.set_selected(ids.index(action["value"]))
        self.command_row.set_text(action["value"] if action["type"] == "command" else "")
        self.wish.get_buffer().set_text(action["value"] if action["type"] == "wish" else "")
        self._kind_changed()

    def _kind_changed(self):
        kind = KINDS[self.kind.value][0]
        self.key_row.set_visible(kind == "key")
        self.app_row.set_visible(kind == "app")
        self.command_row.set_visible(kind == "command")
        self.wish_box.set_visible(kind == "wish")
        combo = getattr(self, "key_combo", None)
        self.key_row.set_subtitle(gestures.key_label(combo) if combo else _("none yet"))
        self._name_from_action()
        self._sync_swipe()

    def _sync_swipe(self):
        """An action that takes the swipe's direction records the hand shape only."""
        if not hasattr(self, "capture"):
            return
        action = self._action()
        swipe = bool(action and action["type"] == "builtin" and action["value"] in gestures.DIRECTION_ACTIONS)
        if swipe != self.capture.swipe:
            self.capture.swipe = swipe
            if not self.capture.recorded and not self.capture.recording:
                self._type_changed()

    def _name_from_action(self):
        action = self._action() if hasattr(self, "auto_name") else None
        if action and self.name.get_text().strip() in ("", self.auto_name):
            self.auto_name = gestures.action_label(action)
            self.name.set_text(self.auto_name)

    def _capture_key(self):
        self.capturing_key = True
        self.key_row.set_subtitle(_("Press the keys …"))
        self.grab_focus()
        self._system_shortcuts(False)

    def _system_shortcuts(self, on):
        """Off while a shortcut is pressed, so Hyprland does not run it
        (keyboard shortcuts inhibit protocol)."""
        if on:
            if getattr(self, "inhibited", None):
                self.inhibited.restore_system_shortcuts()
                self.inhibited = None
            return
        surface = self.get_root().get_surface() if self.get_root() else None
        if isinstance(surface, Gdk.Toplevel):
            surface.inhibit_system_shortcuts(None)
            self.inhibited = surface

    def _key_pressed(self, controller, keyval, keycode, state):
        if not self.capturing_key:
            return False
        name = Gdk.keyval_name(Gdk.keyval_to_upper(keyval)) or ""
        if name.startswith(("Control", "Shift", "Alt", "Super", "Meta", "ISO_")):
            return True   # wait for the actual key
        mods = [label for mask, label in MODIFIERS if state & mask]
        self.key_combo = "+".join(mods + [name])
        self.capturing_key = False
        self._system_shortcuts(True)
        self._kind_changed()
        return True

    def _action(self):
        kind, value, _ = KINDS[self.kind.value]
        if kind == "builtin":
            return {"type": "builtin", "value": value}
        if kind == "key":
            return {"type": "key", "value": self.key_combo} if self.key_combo else None
        if kind == "command":
            command = self.command_row.get_text().strip()
            return {"type": "command", "value": command} if command else None
        if kind == "app":
            selected = self.app_row.get_selected()
            return {"type": "app", "value": self.apps[selected][0]} if selected < len(self.apps) else None
        buf = self.wish.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        return {"type": "wish", "value": text} if text else None

    def _save(self):
        action = self._action()
        if not action:
            self.error.set_label(_("Shortcut, program, command or wish text is missing."))
            return
        if self.type.value != self.saved_kind and not self.capture.recorded:
            self.error.set_label(_("Gesture not recorded yet."))
            return
        data = gestures.load()
        ids = [g["id"] for g in data["gestures"]]
        description = describe_entry(config.load_json(paths.SAMPLES_FILE, {}).get(self.gesture["id"], {}))
        name = self.name.get_text().strip() or description or gestures.action_label(action)
        entry = {"id": self.gesture["id"], "name": name, "action": action}
        if entry["id"] in ids:
            data["gestures"][ids.index(entry["id"])] = entry
        else:
            data["gestures"].append(entry)
        gestures.save(data)
        self.saved = True
        self.close()

    def _more(self):
        """Another gesture for the same action (opens once this one is closed)."""
        self.next_action = self._action() or self.gesture["action"]
        self.close()

    def _delete(self):
        data = gestures.load()
        data["gestures"] = [g for g in data["gestures"] if g["id"] != self.gesture["id"]]
        gestures.save(data)
        vision({"cmd": "delete", "gesture": self.gesture["id"]})
        self.saved = True   # editor_closed rebuilds the list
        self.close()

    def _closed(self, *_):
        self._system_shortcuts(True)
        if self.capture.cancel_button.get_visible():     # closed while recording
            self.capture.cancel()
        # A new gesture that was recorded but not saved leaves nothing behind.
        if self.new and not getattr(self, "saved", False) and self.capture.recorded:
            vision({"cmd": "delete", "gesture": self.gesture["id"]})
        self.hold.close()
        self.page.editor_closed()
        if getattr(self, "next_action", None):
            self.page._edit(None, self.next_action)

    def on_preview(self, msg, payload):
        self.camera.set_frame(msg, payload)
        self.capture.on_preview(msg)

