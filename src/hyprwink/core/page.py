"""Web pages through the accessibility interface (AT-SPI), so it works
without rules per site: the newest message (reading aloud) and the text
field to type into (dictation).

The window's page is searched for the element with the most children that
contain text (a chat's message list, a feed, …; a paragraph itself is not a
message, so a long answer's paragraphs are no list); its last child that is
visible is the newest message. Only paragraphs, headings, list items and
the like are read: no buttons, icons, times or text that only screen
readers get.

The text field is the lowest visible editable one (a chat's message field);
nothing changes when the cursor already is in one.

Chromium based browsers give their pages to the interface only when
started with --force-renderer-accessibility (see README).
"""

import logging

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

log = logging.getLogger("hyprwink.page")

BLOCKS = {"paragraph", "heading", "list item", "block quote", "table cell", "description term",
          "description value", "preformatted"}
SKIP = {"button", "push button", "toggle button", "entry", "menu", "menu bar", "tool bar", "combo box",
        "image", "link", "navigation", "form", "dialog"}
MIN_ITEMS = 3
TIMEOUT_MS = 2000       # an app that hangs does not hold up reading


def enable():
    """Switch the accessibility interface on (the desktop's own setting), so
    apps started from now on offer it."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
                      GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", True))),
                      None, Gio.DBusCallFlags.NONE, TIMEOUT_MS)
    except GLib.Error as e:
        log.warning("accessibility not available: %s", e.message)


def _text(a):
    t = a.get_text_iface()
    if not t:
        return ""
    return Atspi.Text.get_text(t, 0, Atspi.Text.get_character_count(t)).replace("￼", "")


def _children(a):
    return [c for c in (a.get_child_at_index(i) for i in range(a.get_child_count())) if c]


def _blocks(a):
    """Readable texts in a."""
    role = a.get_role_name()
    if role in SKIP:
        return []
    if role in BLOCKS:
        e = a.get_extents(Atspi.CoordType.WINDOW)
        if e.width <= 1 or e.height <= 1:       # only for screen readers
            return []
        text = " ".join(_text(a).split())
        return [text] if text else []
    return [b for c in _children(a) for b in _blocks(c)]


def _document(a):
    if a.get_role_name() == "document web" and a.get_state_set().contains(Atspi.StateType.SHOWING):
        return a
    for c in _children(a):
        found = _document(c)
        if found:
            return found
    return None


def _frame(window):
    """The window's frame: same process, same title."""
    desktop = Atspi.get_desktop(0)
    for app in _children(desktop):
        if app.get_process_id() != window.get("pid"):
            continue
        frames = _children(app)
        for f in frames:
            if f.get_name() == window.get("title"):
                return f
        for f in frames:
            if f.get_state_set().contains(Atspi.StateType.ACTIVE):
                return f
    return None


def _list(doc):
    """(children with text, not text blocks themselves) of the element with the most of them."""
    best = []

    def scan(a):
        nonlocal best
        kids = _children(a)
        items = [c for c in kids if c.get_role_name() not in BLOCKS and _blocks(c)]
        if len(items) >= MIN_ITEMS and len(items) > len(best):
            best = items
        for c in kids:
            if c.get_role_name() not in SKIP | BLOCKS:
                scan(c)

    scan(doc)
    return best


def _sentence(text):
    return text if text[-1] in ".!?:;,…" else text + "."


def newest(window):
    """Text of the newest message in the window's page, or ""."""
    try:
        Atspi.set_timeout(TIMEOUT_MS, TIMEOUT_MS)
        frame = window and _frame(window)
        doc = frame and _document(frame)
        if not doc:
            return ""
        items = _list(doc)
        view = doc.get_extents(Atspi.CoordType.WINDOW)
        visible = [c for c in items if c.get_extents(Atspi.CoordType.WINDOW).y < view.y + view.height]
        if not visible:
            return ""
        return " ".join(_sentence(b) for b in _blocks(visible[-1]))
    except GLib.Error as e:
        log.warning("page not readable: %s", e.message)
        return ""


def _fields(a, found):
    """Editable elements in a (the outer one of an editable area); True
    when one of them has the focus."""
    states = a.get_state_set()
    if states.contains(Atspi.StateType.EDITABLE):
        if states.contains(Atspi.StateType.FOCUSED):
            return True
        if states.contains(Atspi.StateType.SHOWING):
            found.append(a)
        return False
    return any(_fields(c, found) for c in _children(a))


def focus_field(window):
    """Put the cursor into the text field of the window's page, unless it is
    in one already."""
    try:
        Atspi.set_timeout(TIMEOUT_MS, TIMEOUT_MS)
        frame = window and _frame(window)
        doc = frame and _document(frame)
        if not doc:
            return
        found = []
        if _fields(doc, found) or not found:
            return
        view = doc.get_extents(Atspi.CoordType.WINDOW)
        visible = [f for f in found if f.get_extents(Atspi.CoordType.WINDOW).y < view.y + view.height]
        if visible:
            field = max(visible, key=lambda f: f.get_extents(Atspi.CoordType.WINDOW).y)
            Atspi.Component.grab_focus(field.get_component_iface())
    except GLib.Error as e:
        log.warning("no text field: %s", e.message)
