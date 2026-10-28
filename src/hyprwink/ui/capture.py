"""Records a gesture, then checks it live."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import config, paths  # noqa: E402
from ..i18n import _  # noqa: E402
from ..vision import motion  # noqa: E402
from ..vision.describe import describe_entry  # noqa: E402
from .common import in_thread, vision  # noqa: E402


PICTURE = 140   # px of the picture next to the camera
RECORD_S = {"pose": 6, "motion": 30, "swipe": 6}    # seconds at most a gesture is recorded


def photo(gesture, size):
    """Square picture of the recorded gesture, or a placeholder."""
    path = paths.PHOTO_DIR / f"{gesture}.jpg"
    if path.exists():
        # Photos are square, so an image at a fixed pixel size fits exactly.
        pic = Gtk.Image(file=str(path), pixel_size=size)
        css = "gesture-photo"
    else:
        pic = Gtk.Image(icon_name="camera-photo-symbolic", pixel_size=size // 4, css_classes=["dim-label"])
        css = "gesture-placeholder"
    # A fixed square.
    pic.set_size_request(size, size)
    box = Gtk.Box(css_classes=[css], halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                  hexpand=False, vexpand=False)
    box.set_size_request(size, size)
    box.set_overflow(Gtk.Overflow.HIDDEN)
    box.append(pic)
    pic.set_hexpand(True)
    return box


class Clip(Gtk.Box):
    """The recording of a gesture as a short clip in a loop (or its photo)."""

    def __init__(self, gesture, size):
        super().__init__(css_classes=["gesture-photo"], halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                         hexpand=False, vexpand=False)
        self.set_size_request(size, size)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        folder = paths.PHOTO_DIR / f"{gesture}-clip"
        files = sorted(folder.glob("*.jpg")) if folder.exists() else []
        self.frames = [Gdk.Texture.new_from_filename(str(f)) for f in files]
        if not self.frames:
            self.append(photo(gesture, size))
            return
        self.picture = Gtk.Picture(paintable=self.frames[0], can_shrink=True)
        self.picture.set_size_request(size, size)
        self.append(self.picture)
        self.index = 0
        self.timer = GLib.timeout_add(80, self._next)
        self.connect("unrealize", lambda *_: GLib.source_remove(self.timer))

    def _next(self):
        self.index = (self.index + 1) % len(self.frames)
        self.picture.set_paintable(self.frames[self.index])
        return True


class Capture(Gtk.Box):
    """Record → countdown → recording (a pose held 6 s, or a movement made
    motion.TAKES times) → photo → "do it again" check.

    on_checked() runs once the new recording was recognised live.
    """

    def __init__(self, on_checked=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.on_checked = on_checked
        self.names = {}
        self.recorded = False
        self.status = Gtk.Label(css_classes=["title-4"], xalign=0, wrap=True)
        self.photo_box = Gtk.Box()
        self.record_button = Gtk.Button(label=_("Record"), halign=Gtk.Align.START,
                                        css_classes=["suggested-action", "pill", "big-button"])
        self.record_button.connect("clicked", lambda *_: self.start())
        self.cancel_button = Gtk.Button(label=_("Cancel"), visible=False, css_classes=["pill", "big-button"])
        self.cancel_button.connect("clicked", lambda *_: self.cancel())
        # Grid: picture on the left edge of the camera; text at its top, the
        # button at its bottom.
        row = Gtk.Box(spacing=16, valign=Gtk.Align.START)
        row.set_vexpand(False)
        self.photo_box.set_valign(Gtk.Align.START)
        row.append(self.photo_box)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        right.set_vexpand(False)
        right.append(self.status)
        self.description = Gtk.Label(css_classes=["dim-label", "caption"], xalign=0, wrap=True)
        right.append(self.description)
        # Stays while the gesture is tested: it may be mixed up with another one.
        self.warning = Gtk.Label(css_classes=["warning"], xalign=0, wrap=True, visible=False)
        right.append(self.warning)
        # How much of the recording is left.
        self.progress = Gtk.ProgressBar(visible=False, margin_top=6)
        right.append(self.progress)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        right.append(spacer)
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.START)
        buttons.append(self.record_button)
        buttons.append(self.cancel_button)
        right.append(buttons)
        row.append(right)
        self.append(row)
        self.gesture = None
        self.kind = "pose"           # or "motion"
        # Grab – drag – release (gestures.DIRECTION_ACTIONS, vision/drag.py):
        # only the hand shape is recorded, held like a pose.
        self.swipe = False
        self.token = 0
        self.checking = False
        self.recording = False

    def prepare(self, gesture):
        self.gesture = gesture
        self.recorded = False
        self.token += 1
        self.checking = False
        self.recording = False
        self.progress.set_visible(False)
        self.cancel_button.set_visible(False)
        self.warning.set_visible(False)
        if self.kind == "pose":
            self.status.set_label(_("Click Record, show the gesture and vary it a little."))
        elif self.swipe:
            self.status.set_label(_("Click Record and show the hand shape you grab with (one hand), "
                                    "held still and varied a little."))
        else:
            self.status.set_label(_("Click Record. Then make the movement {n} times.").format(n=motion.TAKES))
        self._show_photo(False)
        self.description.set_label("")
        self.record_button.set_label(_("Record"))
        self.record_button.add_css_class("suggested-action")
        self.record_button.set_sensitive(True)

    def _show_photo(self, visible):
        child = self.photo_box.get_first_child()
        if child:
            self.photo_box.remove(child)
        # Always a 140 px square, so the layout does not jump.
        self.photo_box.append(Clip(self.gesture, PICTURE) if visible else photo(None, PICTURE))
        if visible:
            entry = config.load_json(paths.SAMPLES_FILE, {}).get(self.gesture, {})
            self.description.set_label(describe_entry(entry))

    def start(self):
        self.checking = False
        self.warning.set_visible(False)
        self.record_button.set_sensitive(False)
        self.cancel_button.set_visible(True)
        self._countdown(3, self.token)

    def cancel(self):
        """Stop the countdown or the recording; nothing of it is kept."""
        self.token += 1
        self.recording = False
        vision({"cmd": "record_cancel"})
        self.cancel_button.set_visible(False)
        self.progress.set_visible(False)
        self.record_button.set_sensitive(True)
        self.status.set_label(_("Recording cancelled."))

    def _countdown(self, n, token):
        if token != self.token:
            return
        if n > 0:
            if self.kind == "pose" or self.swipe:
                text = _("Show the gesture … {n}")
            else:
                text = _("Hands to the start position … {n}")
            self.status.set_label(text.format(n=n))
            GLib.timeout_add(1000, lambda: self._countdown(n - 1, token) or False)
            return
        gesture, kind = self.gesture, "swipe" if self.swipe else self.kind
        seconds = RECORD_S[kind]
        self.recording = True
        held = kind in ("pose", "swipe")
        if held:
            self.status.set_label(_("● Recording – hold and vary a little: turn, closer, further away"))
        else:
            self._takes(0, "nohands")
        # Held: the time left; a movement: how many of them are done (it may take its time).
        self.progress.set_fraction(0)
        self.progress.set_visible(True)
        if held:
            self._advance(GLib.get_monotonic_time(), seconds, token)
        in_thread(lambda: vision({"cmd": "record", "gesture": gesture, "seconds": seconds, "kind": kind},
                                 timeout=seconds + 15),
                  lambda reply: token == self.token and self._recorded(reply))

    def _takes(self, n, phase):
        """Guides through recording a movement, following the hands."""
        self.progress.set_fraction(n / motion.TAKES)
        what = {"nohands": _("Hands to the start position."),
                "wait": _("Hold still briefly."),
                "ready": _("Now make the movement."),
                "moving": _("…"),
                "back": _("Good. Back to the start position.")}.get(phase, "")
        self.status.set_label(_("Movement {n} of {total}").format(n=min(n + 1, motion.TAKES), total=motion.TAKES)
                              + "\n" + what)

    def _advance(self, start, seconds, token):
        if token != self.token or not self.progress.get_visible():
            return
        done = (GLib.get_monotonic_time() - start) / 1e6 / seconds
        self.progress.set_fraction(min(done, 1.0))
        if done < 1:
            GLib.timeout_add(50, lambda: self._advance(start, seconds, token) or False)

    def _recorded(self, reply):
        self.recording = False
        self.progress.set_visible(False)
        self.cancel_button.set_visible(False)
        self.record_button.set_sensitive(True)
        self.record_button.set_label(_("Record again"))
        if not reply.get("ok"):
            self.status.set_label(_("No movement recognised. Record again.") if reply.get("error") == "motion"
                                  else _("No hand recognised. Record again."))
            return
        self._show_photo(True)
        self.recorded = True
        self.lookalikes = reply.get("lookalikes", [])
        if self.lookalikes:
            names = ", ".join(self.names.get(f, _("another gesture")) for f in self.lookalikes)
            self.warning.set_label(_("⚠ Similar to {names}.").format(names=names))
        self.warning.set_visible(bool(self.lookalikes))
        self.checking = True
        if self.swipe:
            self._check_text(_("Recorded. To test: hold the shape briefly, drag, change the shape."))
        elif self.kind == "motion":
            self._check_text(_("Recorded. Make the movement again to test."))
        else:
            self._check_text(_("Recorded (both hands). Show it again to test.") if reply.get("hands") == 2
                             else _("Recorded. Show it again to test."))

    def _check_text(self, text):
        self.status.set_label(text)

    def on_preview(self, msg):
        """While checking: wait until the gesture is recognised live."""
        if msg is None:
            return
        if self.recording and self.kind == "motion" and not self.swipe:
            self._takes(msg.get("takes", 0), msg.get("phase"))
        if not self.checking:
            return
        recognised = list(msg.get("gestures", {}))
        if self.gesture in recognised:
            self.checking = False
            self.status.set_label(_("✓ Recognised"))
            # Recording done: "Record again" becomes a normal button.
            self.record_button.remove_css_class("suggested-action")
            if self.on_checked:
                self.on_checked()
        elif recognised:
            self._check_text(_("Recognised as {name}.").format(
                name=self.names.get(recognised[0], _("another gesture"))))
