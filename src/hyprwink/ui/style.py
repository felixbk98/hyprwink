"""The two designs of the window. Colours come from libadwaita, which takes
them from the desktop theme (matugen) and follows light/dark.

- material: Material Design 3 – rounded shapes (full for buttons, switches
  and chips, 16 px for lists and cards, 28 px for dialogs), tonal surfaces
  instead of borders, filled and tonal buttons, radio buttons, the
  slider with a bar handle, Roboto.
- omarchy: like the Omarchy desktop – square corners, thin borders, monospace.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from ..i18n import N_  # noqa: E402

THEMES = {"material": N_("Theme 1"), "omarchy": N_("Theme 2")}

COMMON = """
window.gaze-calibration { background: black; }
window.hyprwink-mini { background: transparent; }
image.drag-handle { opacity: 0.55; padding: 6px 2px; }
image.drag-handle:hover { opacity: 1; }
row.dragging { background: alpha(var(--accent-color), 0.15); }
row.recognized { background: alpha(var(--accent-color), 0.12); }
button.delete-button { color: var(--destructive-color); }
button.row-button { min-width: 112px; }
button.bottom-button { min-height: 44px; }
/* The pencil of entry rows looks like a button but is none. */
row.entry .edit-icon { opacity: 0; }
.camera-card { background: var(--view-bg-color); }
.camera-empty image { color: alpha(var(--window-fg-color), 0.35); }
.chip { padding: 3px 10px; background: alpha(black, 0.6); color: white; font-weight: 700; }
.chip.active { background: var(--accent-bg-color); color: var(--accent-fg-color); }
.gesture-placeholder { background: alpha(var(--window-fg-color), 0.06); }
.big-button { padding: 0 24px; }
scale.tempo highlight { background: var(--accent-bg-color); }
list.choice-list { background: transparent; }
"""

OMARCHY = """
* { border-radius: 0; }
window, dialog { font-family: monospace; }

/* Thin borders instead of shadows, like the bar and its panels. */
.boxed-list, list.boxed-list, .card, .camera-card, popover > contents, .gesture-photo,
.gesture-placeholder {
  border: 1px solid alpha(var(--window-fg-color), 0.25);
  box-shadow: none;
}
popover > contents { border-color: var(--accent-color); }
dialog.floating sheet, dialog.alert sheet { border: 1px solid var(--accent-color); box-shadow: none; }

button {
  border: 1px solid alpha(currentColor, 0.35);
  background: alpha(currentColor, 0.04);
  box-shadow: none;
}
button:hover { background: alpha(currentColor, 0.10); }
button.flat, row button.flat, headerbar button.image-button { border-color: transparent; background: transparent; }
button.suggested-action, button.pill.suggested-action {
  background: alpha(var(--accent-color), 0.18);
  color: var(--accent-color);
  border-color: var(--accent-color);
}
button.suggested-action:hover { background: alpha(var(--accent-color), 0.28); }
button.destructive-action {
  background: alpha(var(--destructive-color), 0.12);
  color: var(--destructive-color);
  border-color: var(--destructive-color);
}
row.button.destructive-action { color: var(--destructive-color); }
/* One button size everywhere. */
button, button.pill { min-height: 34px; padding: 0 16px; }
button.flat, button.image-button { padding: 0 8px; }

switch { border: 1px solid alpha(currentColor, 0.35); }
switch:checked { border-color: var(--accent-color); }
viewswitcher button.toggle:checked { box-shadow: inset 0 -2px var(--accent-color); }
row.dragging, row.recognized { box-shadow: inset 3px 0 0 var(--accent-color); }
/* Opened choices: lighter and indented; the chosen one has the accent line and colour, no radio. */
row.expander list.nested { background: alpha(var(--window-fg-color), 0.05); }
row.expander list.nested > row, list.choice-list > row { padding-left: 30px; }
row.expander list.nested > row.choice-scroll { padding: 0; }
list.choice-list > row.chosen, row.expander list.nested > row.chosen { box-shadow: inset 3px 0 0 var(--accent-color); color: var(--accent-color); }
checkbutton.choice-radio, checkbutton.choice-radio radio { min-width: 0; min-height: 0; padding: 0; margin: 0;
  border: none; background: none; box-shadow: none; -gtk-icon-size: 0; opacity: 0; }

/* Tempo: thin track, round knob. */
scale.tempo trough { min-height: 4px; background: alpha(var(--window-fg-color), 0.2); }
scale.tempo slider { min-width: 18px; min-height: 18px; margin: -7px; border-radius: 9999px;
  background: var(--accent-bg-color); border: none; box-shadow: none; }
"""

MATERIAL = """
window, dialog { font-family: Roboto, "Adwaita Sans", sans-serif; }

/* Surfaces: tonal containers, no borders and no shadows. */
.boxed-list, list.boxed-list, .card, .camera-card {
  border: none;
  box-shadow: none;
  border-radius: 16px;
  background: mix(var(--window-bg-color), var(--accent-bg-color), 0.07);
}
list.boxed-list > row:first-child { border-top-left-radius: 16px; border-top-right-radius: 16px; }
list.boxed-list > row:last-child { border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }
list.boxed-list > row { border-color: alpha(var(--window-fg-color), 0.06); }
.gesture-photo, .gesture-placeholder { border-radius: 12px; border: none; }
popover > contents { border-radius: 16px; border: none;
  background: mix(var(--window-bg-color), var(--accent-bg-color), 0.11); }
dialog.floating sheet, dialog.alert sheet { border-radius: 28px; border: none;
  background: mix(var(--window-bg-color), var(--accent-bg-color), 0.11); }

/* Buttons: full rounding, 40 px; tonal by default, filled for the main action. */
button {
  min-height: 40px;
  padding: 0 24px;
  border-radius: 9999px;
  border: none;
  box-shadow: none;
  font-weight: 500;
  background: mix(var(--window-bg-color), var(--accent-bg-color), 0.18);
  color: var(--window-fg-color);
}
button:hover { background: mix(var(--window-bg-color), var(--accent-bg-color), 0.26); }
button.suggested-action, button.pill.suggested-action {
  background: var(--accent-bg-color);
  color: var(--accent-fg-color);
}
button.suggested-action:hover { background: mix(var(--accent-bg-color), var(--accent-fg-color), 0.08); }
button.destructive-action { background: var(--destructive-bg-color); color: var(--destructive-fg-color); }
row.button.destructive-action { color: var(--destructive-color); }
button.flat, row button.flat, headerbar button.image-button, button.image-button {
  background: transparent; padding: 0 8px; min-width: 40px; }
button.flat:hover, headerbar button.image-button:hover { background: alpha(var(--window-fg-color), 0.08); }

/* Switches: 52×32 track (with the 2 px border), the handle grows when on and when pressed. */
switch { min-width: 48px; min-height: 28px; border-radius: 9999px; padding: 0;
  border: 2px solid alpha(var(--window-fg-color), 0.5); background: transparent; }
switch slider { min-width: 16px; min-height: 16px; margin: 6px; border-radius: 9999px;
  background: alpha(var(--window-fg-color), 0.5); box-shadow: none; }
switch:checked { border-color: var(--accent-bg-color); background: var(--accent-bg-color); }
switch:checked slider { min-width: 24px; min-height: 24px; margin: 2px; background: var(--accent-fg-color); }
switch:active slider { min-width: 28px; min-height: 28px; margin: 0; }

/* Navigation: a pill behind the active tab. */
viewswitcher button.toggle { border-radius: 9999px; background: transparent; }
viewswitcher button.toggle:checked { background: mix(var(--window-bg-color), var(--accent-bg-color), 0.24); }

entry { border-radius: 4px 4px 0 0; box-shadow: inset 0 -1px alpha(var(--window-fg-color), 0.5); }
entry:focus-within { box-shadow: inset 0 -2px var(--accent-bg-color); }
.chip { border-radius: 8px; }
row.dragging, row.recognized { border-radius: 12px; }

/* Section headers: primary colour, title small. */
preferencesgroup > box > box.header label.heading { color: var(--accent-color); font-size: 14px; font-weight: 500; }

/* Choices that open in place: radio buttons (20 px, 2 px ring, 10 px dot). */
row.expander list.nested { background: mix(var(--window-bg-color), var(--accent-bg-color), 0.13); }
row.expander list.nested > row, list.choice-list > row { padding-left: 30px; }
row.expander list.nested > row.choice-scroll { padding: 0; }
radio { min-width: 16px; min-height: 16px; padding: 0; -gtk-icon-size: 16px; background: transparent;
  border: 2px solid alpha(var(--window-fg-color), 0.7); box-shadow: none; }
radio:checked, radio:checked:hover { border-color: var(--accent-bg-color); background: transparent;
  color: var(--accent-bg-color); }

/* Slider: 16 px track, 4×44 px handle with a 6 px gap, stop dot at the end. */
scale trough { min-height: 16px; border-radius: 8px;
  background-color: mix(var(--window-bg-color), var(--accent-bg-color), 0.25);
  background-image: radial-gradient(circle 2px at calc(100% - 6px) center, var(--accent-bg-color) 99%,
    transparent 100%); }
scale highlight { border-radius: 8px 2px 2px 8px; background: var(--accent-bg-color); }
scale slider { min-width: 4px; min-height: 44px; margin: -14px 0; border-radius: 2px; border: none;
  background: var(--accent-bg-color);
  box-shadow: 0 0 0 6px mix(var(--window-bg-color), var(--accent-bg-color), 0.07); outline: none; }
scale:active slider { min-width: 2px; }
scale:hover trough, scale:active trough { background-color: mix(var(--window-bg-color), var(--accent-bg-color), 0.25); }
scale:hover slider, scale:active slider { background: var(--accent-bg-color); }
"""

_provider = None


def apply(theme):
    """Switch the design of all windows (at start and when chosen)."""
    global _provider
    display = Gdk.Display.get_default()
    if _provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _provider)
    _provider = Gtk.CssProvider()
    _provider.load_from_string(COMMON + (OMARCHY if theme == "omarchy" else MATERIAL))
    Gtk.StyleContext.add_provider_for_display(display, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
