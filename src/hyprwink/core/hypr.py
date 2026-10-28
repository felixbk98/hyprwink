"""Hyprland access through hyprctl (Lua config, Hyprland ≥ 0.55)."""

import json
import math
import subprocess


def _run(*args, timeout=2):
    try:
        return subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


_saved_dim = None    # Hyprland's own dim settings while Hyprwink dims


def _option(name):
    out = json.loads(_run("-j", "getoption", name) or "{}")
    return out.get("bool", out.get("float"))


def dim_inactive(on, strength=0.15):
    """Dim the windows without focus by strength (0..1, Hyprland's
    decoration.dim_inactive); off: Hyprland's own setting again."""
    global _saved_dim
    if on:
        if _saved_dim is None:
            _saved_dim = (bool(_option("decoration:dim_inactive")), _option("decoration:dim_strength") or 0.5)
        lua(f"hl.config({{ decoration = {{ dim_inactive = true, dim_strength = {strength} }} }})")
    elif not on and _saved_dim is not None:
        dim, strength = _saved_dim
        _saved_dim = None
        lua(f"hl.config({{ decoration = {{ dim_inactive = {str(dim).lower()}, dim_strength = {strength} }} }})")


def lua(code):
    _run("eval", code)


def lua_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_combo(combo):
    """'CTRL+SHIFT+C' -> ('CTRL SHIFT', 'C')."""
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    return " ".join(p.upper() for p in parts[:-1]), parts[-1]


# Modifier bits in `hyprctl binds` and their names for wtype.
MOD_BITS = {"SHIFT": 1, "CTRL": 4, "CONTROL": 4, "ALT": 8, "SUPER": 64, "WIN": 64}
WTYPE_MODS = {"SHIFT": "shift", "CTRL": "ctrl", "CONTROL": "ctrl", "ALT": "alt", "SUPER": "logo", "WIN": "logo"}


def _bound(mods, name):
    """Whether Hyprland itself has a key binding for this shortcut."""
    mask = sum(MOD_BITS.get(m, 0) for m in set(mods.split()))
    try:
        binds = json.loads(_run("-j", "binds") or "[]")
    except json.JSONDecodeError:
        return False
    return any(b.get("modmask") == mask and b.get("key", "").lower() == name.lower() and not b.get("submap")
               for b in binds)


def key(combo):
    """Press and release a shortcut in the active window. Keys sent to a
    window do not reach Hyprland's own key bindings, so those shortcuts are
    typed on a virtual keyboard (wtype) instead; its keys are matched by
    name, as its key codes are its own."""
    mods, name = parse_combo(combo)
    if _bound(mods, name):
        lua('hl.device({ name = "hl-virtual-keyboard-wtype", resolve_binds_by_sym = true })')
        held = [WTYPE_MODS[m] for m in mods.split() if m in WTYPE_MODS]
        try:
            subprocess.run(["wtype", *[a for m in held for a in ("-M", m)], "-k", name,
                            *[a for m in reversed(held) for a in ("-m", m)]], timeout=2)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
    state = "{{mods = {m}, key = {k}, state = {s}}}"
    down = state.format(m=lua_string(mods), k=lua_string(name), s='"down"')
    up = state.format(m=lua_string(mods), k=lua_string(name), s='"up"')
    lua(
        f"hl.dispatch(hl.dsp.send_key_state({down})) "
        f"hl.timer(function() hl.dispatch(hl.dsp.send_key_state({up})) end, "
        '{timeout = 30, type = "oneshot"})'
    )


TERMINALS = {"com.mitchellh.ghostty", "kitty", "Alacritty", "foot", "footclient", "org.wezfurlong.wezterm",
             "org.kde.konsole", "org.gnome.Console", "org.gnome.Terminal", "xterm"}


def active_window():
    """The focused window ({} when unknown)."""
    try:
        return json.loads(_run("-j", "activewindow") or "{}") or {}
    except json.JSONDecodeError:
        return {}


def in_terminal():
    """Whether the focused window is a terminal (its class, or the tag "terminal")."""
    window = active_window()
    tags = [t.rstrip("*") for t in window.get("tags", [])]
    return "terminal" in tags or window.get("class") in TERMINALS


def dispatch(expr):
    """Run one hl.dsp dispatcher, e.g. dispatch('hl.dsp.window.close()')."""
    lua(f"hl.dispatch({expr})")


def cursor():
    """Mouse pointer in layout coordinates, or None."""
    try:
        pos = json.loads(_run("-j", "cursorpos") or "{}")
        return pos["x"], pos["y"]
    except (json.JSONDecodeError, KeyError):
        return None


def windows():
    """Visible windows: mapped, on a workspace shown on a monitor."""
    try:
        monitors = json.loads(_run("-j", "monitors") or "[]")
        clients = json.loads(_run("-j", "clients") or "[]")
    except json.JSONDecodeError:
        return []
    shown = {m["activeWorkspace"]["id"] for m in monitors}
    return [c for c in clients if c.get("mapped") and not c.get("hidden") and c["workspace"]["id"] in shown]


def size(monitor):
    """Width and height of a monitor in layout coordinates (scaled, turned)."""
    w, h = monitor["width"] / monitor["scale"], monitor["height"] / monitor["scale"]
    return (h, w) if monitor.get("transform", 0) % 2 else (w, h)


def monitors():
    """{monitor id: (x, y, width, height)} in layout coordinates."""
    try:
        return {m["id"]: (m["x"], m["y"], *size(m)) for m in json.loads(_run("-j", "monitors") or "[]")}
    except (json.JSONDecodeError, KeyError, ZeroDivisionError):
        return {}


def monitor_toward(dx, dy, hand_x=None, steep=30):
    """Name of the monitor the swipe (dx, dy; y down) points at from the
    focused window's centre, as if the window were dragged there, or None.
    Several in the way: the one whose centre lies closest to the direction.

    A swipe up or down (within steep degrees) starts instead where the hand
    ended across the image (hand_x, 0 left … 1 right), mapped onto the
    window's monitor: on a wide monitor below two others, a swipe up on the
    right side goes to the right one."""
    try:
        mons = json.loads(_run("-j", "monitors") or "[]")
        window = active_window()
    except json.JSONDecodeError:
        return None
    here = next((m for m in mons if m["id"] == window.get("monitor")), None) or \
        next((m for m in mons if m.get("focused")), None)
    if here is None or math.hypot(dx, dy) < 1e-6:
        return None
    if window.get("at") and window.get("size"):
        ox, oy = window["at"][0] + window["size"][0] / 2, window["at"][1] + window["size"][1] / 2
    else:
        w, h = size(here)
        ox, oy = here["x"] + w / 2, here["y"] + h / 2
    if hand_x is not None and math.degrees(math.atan2(abs(dx), abs(dy))) <= steep:
        w, _h = size(here)
        ox = here["x"] + w * min(max(hand_x, 0.0), 1.0)
    aim = math.atan2(dy, dx)

    def hit(x, y, w, h):
        """Whether the ray from (ox, oy) along (dx, dy) passes through the rectangle."""
        near, far = 0.0, math.inf
        for o, d, lo, hi in ((ox, dx, x, x + w), (oy, dy, y, y + h)):
            if abs(d) < 1e-9:
                if not lo <= o <= hi:
                    return False
                continue
            t1, t2 = sorted(((lo - o) / d, (hi - o) / d))
            near, far = max(near, t1), min(far, t2)
        return near <= far

    best = None
    for m in mons:
        if m is here:
            continue
        w, h = size(m)
        if hit(m["x"], m["y"], w, h):
            cx, cy = m["x"] + w / 2, m["y"] + h / 2
            off = abs((math.atan2(cy - oy, cx - ox) - aim + math.pi) % (2 * math.pi) - math.pi)
            if best is None or off < best[0]:
                best = (off, m["name"])
    return best and best[1]


def move_to_monitor(name):
    """Move the focused window to that monitor (fullscreen stays fullscreen)."""
    dispatch(f"hl.dsp.window.move({{ monitor = {lua_string(name)} }})")


def focus(address):
    """Focus the window with this address."""
    lua(f'local w = hl.get_window("address:{address}") if w then hl.dispatch(hl.dsp.focus({{window = w}})) end')
