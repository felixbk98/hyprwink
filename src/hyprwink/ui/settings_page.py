"""Settings page: dictation, speech output, gaze (focus follows gaze switched in
its header), general (with language and export/import).

The providers of dictation and reading come from core/stt and core/tts;
their rows (voice, API key) are built from what each provider declares.
"""

import re
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .. import backup, config, i18n, paths, settings  # noqa: E402
from ..core import providers, stt, tts  # noqa: E402
from ..i18n import N_, _, ngettext  # noqa: E402
from . import style  # noqa: E402
from .calibration import Calibration  # noqa: E402
from .common import Choice, core, in_thread, no_wheel, vision  # noqa: E402

SAMPLE = N_("Hello! This is how I sound when reading aloud. So that you can judge the speed, I am "
            "reading a few whole sentences to you. Imagine a quiet evening, it is slowly getting dark "
            "outside, and a long answer is still waiting on the screen that you would rather listen to "
            "than read yourself. If this is too fast or too slow, move the slider a little and listen "
            "again.")
SLOWEST, FASTEST = 0.5, 2.5
SERVICES = ["hyprwink-core.service", "hyprwink-vision.service"]
GAZE_SPEEDS = {"fast": N_("Fast"), "medium": N_("Medium"), "slow": N_("Slow")}


def _sample():
    """The sample text in the spoken language."""
    return i18n.translate(SAMPLE, i18n.spoken("read_language"))


def _slider_to_speed(position):
    return 1 + position * ((1 - SLOWEST) if position < 0 else (FASTEST - 1))


def _speed_to_slider(speed):
    return (speed - 1) / ((1 - SLOWEST) if speed < 1 else (FASTEST - 1))


def _set(name, value):
    """Save a setting; the services pick it up at once."""
    settings.put(name, value)
    core({"cmd": "reload"})


def _autostart_enabled():
    try:
        result = subprocess.run(["systemctl", "--user", "is-enabled", *SERVICES], capture_output=True, text=True,
                                timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return all(line.strip() == "enabled" for line in result.stdout.splitlines())


def _provider_label(provider):
    return f"{provider.LABEL} · {_("cloud") if provider.CLOUD else _("local")}"


def _button(label, on_click, css=()):
    button = Gtk.Button(label=label, valign=Gtk.Align.CENTER, css_classes=["row-button", *css])
    button.connect("clicked", lambda *_: on_click())
    return button


def _icon(row, name):
    row.add_prefix(Gtk.Image(icon_name=name))
    return row


def _choice(title, icon, options, selected, on_change):
    return _icon(Choice(title, options, selected, on_change), icon)


def _group(title, switch):
    """Group with its on/off switch beside the title."""
    group = Adw.PreferencesGroup(title=title)
    switch.set_valign(Gtk.Align.CENTER)
    switch.set_margin_end(14)   # in line with the switches in the rows
    group.set_header_suffix(switch)
    return group


def _switch(title, icon, name, on_change=None):
    """Switch row for a boolean setting."""
    row = _icon(Adw.SwitchRow(title=title, active=settings.get(name)), icon)
    row.connect("notify::active", lambda r, _: (on_change or (lambda on: _set(name, on)))(r.get_active()))
    return row


class SettingsPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        self.set_child(Adw.Clamp(maximum_size=900, child=box))
        box.append(self._dictation())
        box.append(self._reading())
        box.append(self._gaze())
        box.append(self._general())

    # ------------------------------------------------------------ groups

    def _dictation(self):
        group = Adw.PreferencesGroup(title=_("Dictation"))
        engine = settings.get("dictate_engine")
        keys = {}

        def changed(name):
            _set("dictate_engine", name)
            for other, row in keys.items():
                row.set_visible(other == name)

        group.add(_choice(_("Provider"), "audio-input-microphone-symbolic",
                          {name: _provider_label(p) for name, p in stt.PROVIDERS.items()}, engine, changed))
        group.add(_choice(_("Language"), "preferences-desktop-locale-symbolic", i18n.available(),
                          i18n.spoken("dictate_language"), lambda language: _set("dictate_language", language)))
        for name, provider in stt.PROVIDERS.items():
            if provider.CLOUD:
                keys[name] = self._key_row(group, provider)
                keys[name].set_visible(name == engine)
        return group

    def _reading(self):
        group = Adw.PreferencesGroup(title=_("Speech output"))
        engine = settings.get("read_engine")
        rows = {}       # provider -> its rows (voice, key)

        def changed(name):
            _set("read_engine", name)
            for other, items in rows.items():
                for row in items:
                    row.set_visible(other == name)

        group.add(_choice(_("Provider"), "audio-speakers-symbolic",
                          {name: _provider_label(p) for name, p in tts.PROVIDERS.items()}, engine, changed))
        group.add(_choice(_("Language"), "preferences-desktop-locale-symbolic", i18n.available(),
                          i18n.spoken("read_language"), lambda language: self._language("read_language", language)))
        for name, provider in tts.PROVIDERS.items():
            items = [self._voice_row(group, name, provider)]
            if provider.CLOUD:
                items.append(self._key_row(group, provider))
            for row in items:
                row.set_visible(name == engine)
            rows[name] = items

        group.add(self._tempo_row())
        sample = _icon(Adw.ActionRow(title=_("Sample")), "media-playback-start-symbolic")
        sample.add_suffix(_button(_("Stop"), lambda: core({"cmd": "stop_reading"})))
        sample.add_suffix(_button(_("Listen"), lambda: core({"cmd": "read", "text": _sample()})))
        group.add(sample)
        return group

    def _gaze(self):
        # On: focus follows gaze (possible once calibrated).
        self.gaze = Gtk.Switch()
        self.gaze.connect("notify::active", lambda sw, _: self._gaze_on(sw.get_active()))
        group = _group(_("Gaze"), self.gaze)
        group.add(_choice(_("Reaction"), "speedometer-symbolic", {k: _(v) for k, v in GAZE_SPEEDS.items()},
                          settings.get("gaze_speed"),
                          lambda speed: _set("gaze_speed", speed)))
        # Expands to the rounds of the calibration, each with date and time.
        self.calibration = _icon(Adw.ExpanderRow(title=_("Calibration")), "find-location-symbolic")
        self.forget = _button(_("Delete"), self._forget, ["destructive-action"])
        self.add_round = _button(_("Add"), lambda: self._calibrate(add=True))
        for button in (self.forget, self.add_round, _button(_("Calibrate"), self._calibrate)):
            self.calibration.add_suffix(button)
        self.round_rows = []
        group.add(self.calibration)
        self.dot = _switch(_("Show gaze point"), "mark-location-symbolic", "show_gaze", self._dot)
        group.add(self.dot)
        self.dim = _switch(_("Dim inactive windows"), "weather-few-clouds-night-symbolic", "dim_inactive",
                           self._dim)
        group.add(self.dim)
        self.dim_strength = self._dim_strength_row()
        group.add(self.dim_strength)
        self._show_gaze()
        return group

    def _general(self):
        group = Adw.PreferencesGroup(title=_("General"))
        group.add(_choice(_("Display language"), "preferences-desktop-locale-symbolic", i18n.available(), i18n.current(),
                          lambda language: self._language("language", language)))
        group.add(_choice(_("Design"), "applications-graphics-symbolic", {k: _(v) for k, v in style.THEMES.items()},
                          settings.get("theme"), self._theme))
        autostart = _icon(Adw.SwitchRow(title=_("Start with the computer"), active=_autostart_enabled()),
                          "system-run-symbolic")
        autostart.connect("notify::active", lambda row, _: self._autostart(row.get_active()))
        group.add(autostart)
        group.add(_switch(_("Camera off at start"), "camera-disabled-symbolic", "start_paused"))
        group.add(_switch(_("Closing minimises to the bar"), "go-bottom-symbolic", "minimize_on_close"))
        self.mini = _icon(Adw.SwitchRow(title=_("Mini view")), "view-paged-symbolic")
        self.mini.connect("notify::active", lambda row, _: self._mini(row.get_active()))
        group.add(self.mini)
        self.transfer = _icon(Adw.ActionRow(title=_("Configuration")), "document-save-symbolic")
        self.transfer.add_suffix(_button(_("Import"), self._import))
        self.transfer.add_suffix(_button(_("Export"), self._export))
        group.add(self.transfer)
        return group

    # ---------------------------------------------------------- providers

    def _key_row(self, group, provider):
        row = _icon(Adw.ActionRow(title=_("API key"), subtitle="…"), "dialog-password-symbolic")

        def save(key):
            if not key:
                return
            try:
                providers.store_key(provider.ACCOUNT, provider.LABEL, key)
                row.set_subtitle(_("saved"))
            except (OSError, subprocess.SubprocessError):
                row.set_subtitle(_("Saving failed"))

        row.add_suffix(_button(_("Change"), lambda: self._ask(
            _("API key {provider}").format(provider=provider.LABEL), "", True, save)))
        group.add(row)
        in_thread(lambda: providers.api_key(provider.ACCOUNT),
                  lambda key: row.set_subtitle(_("saved") if key else _("missing")))
        return row

    def _voice_row(self, group, name, provider):
        language = i18n.spoken("read_language")
        current = tts.voice(name, settings.get("read_voices"), language)
        choices = provider.voices(language)
        if choices:
            row = _choice(_("Voice"), "system-users-symbolic", {k: _(v) for k, v in choices.items()}, current,
                          lambda voice: self._voice_changed(row, name, voice))
            group.add(row)
            return row
        row = _icon(Adw.ActionRow(title=_("Voice")), "system-users-symbolic")
        if provider.BROWSE:
            row.add_suffix(_button(_("Search"), lambda: Gtk.UriLauncher.new(provider.BROWSE).launch(
                self.get_root(), None, None, None)))
        row.add_suffix(_button(_("Change"), lambda: self._ask(
            _("Voice"), tts.voice(name, settings.get("read_voices"), i18n.spoken("read_language")), False,
            lambda text: self._voice_changed(row, name, self._voice_id(text)))))
        group.add(row)
        self._show_voice(row, provider, current)
        return row

    @staticmethod
    def _voice_id(text):
        # A link like https://fish.audio/de/m/<id>/ works as well as the bare id.
        match = re.search(r"[0-9a-f]{32}", text)
        return match.group(0) if match else text.strip()

    def _show_voice(self, row, provider, voice):
        """The voice's name (its id until that is known)."""
        row.set_subtitle(voice or _("Default"))
        if voice:
            def show(title):
                if title:
                    row.set_subtitle(title)
            in_thread(lambda: provider.voice_name(voice), show)

    def _voice_changed(self, row, name, voice):
        voices = dict(settings.get("read_voices"), **{name: voice})
        settings.put("read_voices", voices)
        provider = tts.get(name)
        if provider.voices(i18n.spoken("read_language")) is None:
            self._show_voice(row, provider, voice)
        row.set_sensitive(False)

        def done(reply):
            row.set_sensitive(True)
            if reply.get("ok"):
                core({"cmd": "read", "text": _sample()})
            else:
                row.set_subtitle(reply.get("error", _("Loading failed")))
        in_thread(lambda: core({"cmd": "voice", "engine": name, "voice": voice}, timeout=180), done)

    def _dim(self, on):
        _set("dim_inactive", on)
        self.dim_strength.set_visible(on)

    def _dim_strength_row(self):
        row = _icon(Adw.ActionRow(title=_("Strength")), "display-brightness-symbolic")
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 60, 1)
        scale.set_value(round(settings.get("dim_strength") * 100))
        scale.set_hexpand(True)
        scale.set_size_request(260, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        no_wheel(scale)
        value = Gtk.Label(width_chars=5, xalign=1, css_classes=["numeric", "dim-label"])

        def show():
            value.set_label(f"{scale.get_value():.0f} %")

        def changed(*_):
            show()
            _set("dim_strength", round(scale.get_value() / 100, 2))

        show()
        scale.connect("value-changed", changed)
        row.add_suffix(scale)
        row.add_suffix(value)
        row.set_visible(settings.get("dim_inactive"))
        return row

    def _tempo_row(self):
        row = _icon(Adw.ActionRow(title=_("Speed")), "speedometer-symbolic")
        # Middle = normal speed; left down to SLOWEST, right up to FASTEST.
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1, 1, 0.02)
        scale.set_value(_speed_to_slider(settings.get("read_speed")))
        scale.set_hexpand(True)
        scale.set_size_request(260, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        scale.add_css_class("tempo")
        no_wheel(scale)
        value = Gtk.Label(width_chars=5, xalign=1, css_classes=["numeric", "dim-label"])

        def show():
            # Translators: the decimal separator
            value.set_label(f"{_slider_to_speed(scale.get_value()):.1f}×".replace(".", _(".")))

        def changed(*_):
            show()
            _set("read_speed", round(_slider_to_speed(scale.get_value()), 2))

        show()
        scale.connect("value-changed", changed)
        row.add_suffix(scale)
        row.add_suffix(value)
        return row

    # --------------------------------------------------------------- gaze

    def _show_gaze(self, text=None):
        saved = config.load_json(paths.GAZE_FILE, {})
        calibrated = "model" in saved
        rounds = saved.get("rounds", []) if calibrated else []
        count = ngettext("{n} round", "{n} rounds", len(rounds)).format(n=len(rounds))
        self.calibration.set_subtitle(text or (count if calibrated else _("not calibrated")))
        for row in self.round_rows:
            self.calibration.remove(row)
        self.round_rows = []
        for i, r in enumerate(rounds, 1):
            when = GLib.DateTime.new_from_unix_local(int(r["time"])).format("%d.%m. %H:%M")
            kind = _("full") if r.get("full") else _("short")
            row = Adw.ActionRow(title=_("Round {n}").format(n=i), subtitle=f"{kind} · {when}")
            if i > 1:   # the first round is the full grid; it goes only with "Delete"
                delete = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                    css_classes=["flat", "delete-button"])
                delete.connect("clicked", lambda *_, n=r["round"]: self._drop_round(n))
                row.add_suffix(delete)
            self.calibration.add_row(row)
            self.round_rows.append(row)
        self.calibration.set_enable_expansion(calibrated)
        self.gaze.set_sensitive(calibrated)
        self.gaze.set_active(calibrated and settings.get("gaze"))
        self.dot.set_sensitive(calibrated)
        self.dim.set_sensitive(calibrated)
        self.dim_strength.set_sensitive(calibrated)
        self.forget.set_visible(calibrated)
        self.add_round.set_visible(calibrated)

    def _drop_round(self, number):
        def done(reply):
            self._show_gaze(None if reply.get("ok") else _("Removing failed"))
        in_thread(lambda: vision({"cmd": "gaze_drop", "round": number}, timeout=20), done)

    def _gaze_on(self, on):
        if on != settings.get("gaze"):
            _set("gaze", on)
            vision({"cmd": "gaze_reload"})

    def _dot(self, on):
        _set("show_gaze", on)
        vision({"cmd": "gaze_reload"})

    def _forget(self):
        """Delete the calibration; focus follows gaze is off until the next one."""
        paths.GAZE_FILE.unlink(missing_ok=True)
        paths.GAZE_SAMPLES.unlink(missing_ok=True)
        _set("gaze", False)
        vision({"cmd": "gaze_reload"})
        self._show_gaze()

    def _calibrate(self, add=False):
        def done(reply):
            if reply.get("ok"):
                _set("gaze", True)
                vision({"cmd": "gaze_reload"})
                self._show_gaze()
            elif reply.get("error") == "cancelled":
                self._show_gaze()
            elif reply.get("error") == "monitors":
                self._show_gaze(_("No monitors found"))
            else:
                self._show_gaze(_("No face recognised – try again"))
        Calibration(self.get_root().get_application(), done, add)

    # ------------------------------------------------------------ general

    def _language(self, setting, language):
        _set(setting, language)
        if setting == "read_language":   # fetch the local voice now, not at the first reading
            voice = tts.voice("piper", settings.get("read_voices"), language)
            in_thread(lambda: core({"cmd": "voice", "engine": "piper", "voice": voice}, timeout=180))
        # The window is built anew in the new language, with the voices of the
        # spoken one (after this click is handled).
        GLib.idle_add(lambda: self.get_root().get_application().reload() and False)

    def _theme(self, theme):
        settings.put("theme", theme)
        style.apply(theme)

    def _autostart(self, on):
        # Only the start at login changes; the running services stay as they are.
        subprocess.run(["systemctl", "--user", "enable" if on else "disable", *SERVICES], check=False)

    def _mini(self, on):
        app = self.get_root().get_application()
        if on != (app.mini is not None):
            app.toggle_mini()

    def show_mini(self, on):
        """Keep the switch in line when the mini view is opened/closed elsewhere."""
        if self.mini.get_active() != on:
            self.mini.set_active(on)

    def _zip_dialog(self, title):
        dialog = Gtk.FileDialog(title=title, modal=True)
        zips = Gtk.FileFilter(name="ZIP")
        zips.add_suffix("zip")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(zips)
        dialog.set_filters(filters)
        dialog.set_default_filter(zips)
        return dialog

    def _export(self):
        dialog = self._zip_dialog(_("Export configuration"))
        dialog.set_initial_name(f"hyprwink-{GLib.DateTime.new_now_local().format('%Y-%m-%d')}.zip")

        def chosen(d, result):
            try:
                file = d.save_finish(result)
            except GLib.Error:
                return      # cancelled
            try:
                backup.save(file.get_path())
                self.transfer.set_subtitle(_("exported"))
            except backup.BackupError as e:
                self.transfer.set_subtitle(_("Export failed: {error}").format(error=e))
        dialog.save(self.get_root(), None, chosen)

    def _import(self):
        def chosen(d, result):
            try:
                file = d.open_finish(result)
            except GLib.Error:
                return      # cancelled
            confirm = Adw.AlertDialog(heading=_("Replace everything?"))
            confirm.add_response("cancel", _("Cancel"))
            confirm.add_response("import", _("Import"))
            confirm.set_response_appearance("import", Adw.ResponseAppearance.DESTRUCTIVE)
            confirm.connect("response", lambda _c, r: r == "import" and self._load(file.get_path()))
            confirm.present(self.get_root())
        self._zip_dialog(_("Import configuration")).open(self.get_root(), None, chosen)

    def _load(self, path):
        app = self.get_root().get_application()
        self.transfer.set_sensitive(False)

        def done(error):
            if error:
                self.transfer.set_sensitive(True)
                self.transfer.set_subtitle(_("Import failed: {error}").format(error=error))
            else:
                app.reload()

        def run():
            try:
                backup.load(path)
            except backup.BackupError as e:
                return str(e)
        in_thread(run, done)

    def _ask(self, title, text, secret, on_save):
        """Small dialog with one input field and Speichern/Abbrechen."""
        dialog = Adw.AlertDialog(heading=title)
        entry = Gtk.PasswordEntry(show_peek_icon=True) if secret else Gtk.Entry(text=text)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.connect("response", lambda _d, r: r == "save" and on_save(entry.get_text().strip()))
        dialog.present(self.get_root())
        entry.grab_focus()
