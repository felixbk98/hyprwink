# Hyprwink

**English** · [Deutsch](README.de.md)

Dictation, reading aloud, your own hand gestures and "focus follows gaze" for
[Hyprland](https://hyprland.org) – with an ordinary webcam and a microphone.
Interface, dictation and speech output each in English or German.

> [!WARNING]
> **Made for my setup – expect to adapt it to yours.**
> Hyprwink is tuned to my own computer at home: Arch Linux, Hyprland, an Omarchy-style Quickshell bar,
> three monitors (two above, a wide one below, the webcam in between), an NVIDIA GPU. There it works
> really well; on yours, things will very likely need adjusting – monitor layout, keys, bar, camera,
> thresholds. The easiest way is to do that together with Claude Code or another coding agent: let it
> read this README and the code, then fine-tune it for your setup.
>
> I'm not a professional programmer – Hyprwink is vibe-coded, written together with an AI (Claude Code).
> Use it at your own risk; feel free to fork it.

## Features

### Dictation
- **Ctrl+Space** starts and stops recording; the text is pasted into the focused window.
- While recording, Hyprwink binds **Esc** (cancel, also while converting) and **Enter** (stop and
  send); otherwise both keys go to the applications as usual.
- Playing media (MPRIS) pauses while recording. Recorded through PipeWire, 16 kHz mono, at most 5 min.
- Converted locally with Whisper `large-v3-turbo` (faster-whisper; NVIDIA GPU, else CPU; silence is
  dropped) or in the cloud with ElevenLabs Scribe v2 (falls back to Whisper on errors).
- On a web page (chats, claude.ai, …) the cursor jumps into the text field at the start if it is in none
  (accessibility interface, see reading aloud).
- Pasted like typing: the clipboard is saved, the text copied, Ctrl+V (Shift+Insert in terminals),
  Enter when sending, then the old clipboard comes back.
- A pill at the bottom of the screen shows the level while recording and a circle while converting (Quickshell).

### Speech output (reading aloud)
- Reads from the focused window (the one you look at): newly selected text, otherwise Claude Code's
  last answer in that terminal (matched through the process tree), otherwise the newest message of the
  web page there (chats, claude.ai, …), found through the accessibility interface (AT-SPI) without
  rules per site.
- Voice locally with Piper (English and German voices, fetched when chosen) or in the cloud with
  Fish Audio (voice by id or link; falls back to Piper on errors).
- Speed 0.5–2.5×, also while reading. All voices equally loud (the level is evened out).

### Gestures
- Record your own gestures, with one hand or both:
  - **pose:** a hand shape held still briefly (recorded for 6 s, varying it a little).
  - **movement:** a hand shape plus a movement, e.g. drawing both hands apart; made 3 times while
    recording. It is recognised whatever its speed and size, once the hands stop or leave the picture.
  - Kept are the hand shapes or movement paths, a photo and a short clip, plus a description
    ("right hand: fist", "both hands: … · apart").
- On the first start there are example gestures (my own recordings, without photos): right open hand
  starts dictation, left open hand reads aloud, fist cancels dictation and reading (no Esc), both index
  fingers close the window, index and middle finger together move windows. Change, re-record or delete them as you like.
- Each gesture gets an action:
  - dictation: start / stop / stop and send recording; read aloud / stop reading; cancel dictation and
    reading (never presses Esc)
  - keys: Enter (sends while dictating), Esc (cancels dictation and reading), Tab, select all, copy, cut,
    paste, undo (with the terminal shortcuts in terminals)
  - windows: close, fullscreen on / off, floating, next window, next / previous workspace; move to the
    monitor in swipe direction, like on a touch screen: grab (show the recorded hand shape, held briefly),
    drag (any speed), let go (another hand shape); taking the hand out of the picture cancels. The
    direction snaps to 8 (narrow straight ones ±15°, wide diagonal ones) and points from the window at a
    monitor, as if dragging it there; up or down: the side of the image the hand is on decides; no
    monitor there: the window moves within the layout (two side by side swap). Recording it: only the
    hand shape, held like a pose with the hand it is used with
  - media: play/pause, next / previous track, volume up, down, mute
  - any keyboard shortcut (one of Hyprland's own key bindings is typed with wtype, so Hyprland runs it),
    starting a program or running a command
  - a wish of your own as text: only saved; Claude Code implements it when asked
- A gesture counts again only after it was gone for 1 s (it flickers while held).
- A hand cut off by the image's edge (being lowered) makes no gesture; nor does a hand shape while
  dragging (grab – drag – let go) and for 1 s after letting go.
- Several gestures may share an action; a new gesture that looks like an existing one gives a warning.
- The "Gestures" tab is grouped by action; reorder by dragging the handle.

### Focus follows gaze
- The window the gaze rests on gets the focus (reaction fast 0.15 s, medium 0.3 s, slow 0.5 s).
- No flickering at borders: another window only counts well inside it; a window on another monitor only
  150 px past its edge and after twice the wait.
- The mouse wins: while it moves and 0.5 s after, the gaze does not change the focus.
- Corrects itself while running: the mouse pointer and windows you switch to yourself show where the gaze
  really is.
- Calibration with dots on all monitors (any number, layout and rotation): round 1 full, then any number
  of short rounds from other sitting positions; rounds can be deleted one by one or added later. Needed
  again when the camera or monitors are moved.
- "Show gaze point" shows the recognised gaze as a dot (for testing).

### Use
- **Win+G** or left click on the bar symbol: camera on/off (gestures and gaze). Dictation and speech
  output also work with the camera off.
- **Win+Alt+G**: show/hide the settings. Right click on the bar symbol: window with the tabs Camera,
  Gestures, Settings.
- Mini view: small camera picture in the bottom right corner, always on top.

### Settings
- **Dictation:** provider (local or cloud), language, for cloud the API key.
- **Speech output:** provider, language, voice (matching the language), for cloud the API key, speed, sample.
- **Gaze:** switch beside the heading (focus follows gaze, once calibrated), reaction, calibration
  (rounds expandable), show gaze point, dim inactive windows (strength adjustable, only while focus follows gaze runs;
  uses Hyprland's `dim_inactive`).
- **General:** display language (without a choice the system's; also the default for dictation and
  speech output), design (Theme 1: Material Design 3; Theme 2:
  square, thin borders, monospace), start with the computer, camera off at start, closing minimises,
  mini view, export/import the configuration (one ZIP file with settings, gestures with their
  recordings and the gaze calibration; without API keys; importing replaces everything).

## Requirements

- Any Linux distribution with **Hyprland ≥ 0.55 and a Lua config** (with the old `hyprland.conf`, keys
  and window commands do not work), systemd, PipeWire/WirePlumber, a webcam, a microphone
- Python ≥ 3.12, GTK 4 and libadwaita ≥ 1.5 with Python bindings, mpv, wl-clipboard, wtype, PortAudio, libsecret,
  AT-SPI, pipx:

  | Distribution | Packages |
  |---|---|
  | Arch | `sudo pacman -S python-pipx python-gobject python-cairo gtk4 libadwaita mpv wl-clipboard wtype portaudio libsecret at-spi2-core` |
  | Fedora | `sudo dnf install pipx python3-gobject python3-cairo gtk4 libadwaita mpv wl-clipboard wtype portaudio libsecret at-spi2-core` (mpv from RPM Fusion) |
  | Debian / Ubuntu | `sudo apt install pipx python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 mpv wl-clipboard wtype libportaudio2 libsecret-tools gir1.2-atspi-2.0` (Debian 13 / Ubuntu 24.04 or later) |

- optional:
  - an **Omarchy-style Quickshell bar** (`~/.config/quickshell/shell/` with `plugins/`, `bar/Bar.qml`,
    `shell.qml`) for the bar symbol, the dictation pill and the gaze dot. With another bar only these are
    missing; `hyprwink watch` streams the state as JSON for your own integration.
  - **Claude Code** (Stop hook: the last answer per terminal, for reading aloud)
  - reading web pages aloud in **Chromium based browsers** (Chrome, Brave, …) needs the start option
    `--force-renderer-accessibility` (e.g. a line in `~/.config/brave-flags.conf` or
    `chromium-flags.conf`); Firefox gives its pages without it
  - an **NVIDIA GPU** (fast local dictation), the Roboto font (Theme 1)
- Copy and paste in terminals (Ctrl+Shift+C, Shift+Insert) knows Ghostty, Kitty, Alacritty, foot,
  WezTerm, Konsole, GNOME Console/Terminal and xterm (`TERMINALS` in `src/hyprwink/core/hypr.py`).

## Installation

```sh
pipx install --system-site-packages "hyprwink[gpu] @ git+https://github.com/felixbk98/hyprwink"
hyprwink setup        # per user: models, services, launcher, Quickshell plugin, Claude Code hook
hyprwink ui --setup   # record your first gestures
```

Without an NVIDIA GPU use `hyprwink` instead of `hyprwink[gpu]`. `--system-site-packages` takes GTK
and libadwaita from the system.

Shortcuts and the window rule of the mini view go into your own Hyprland config:
see [`src/hyprwink/data/hyprland.lua`](src/hyprwink/data/hyprland.lua) (`hyprwink setup` shows its path).

Update: `pipx upgrade hyprwink`, then `hyprwink setup`. Remove: `hyprwink remove` (per user: services,
launcher, data, keys, integrations), then `pipx uninstall hyprwink`.

## Commands

```
hyprwink status [--json]                               state
hyprwink pause | resume | toggle                       camera off / on / toggle
hyprwink reload                                        reload gestures and settings
hyprwink dictate toggle|start|stop|send|cancel [--file F] [--badge B]
                                                       dictation (--file: write the text into a file instead
                                                       of pasting, --badge: symbol in the pill, for other programs)
hyprwink action <name>                                 trigger an action as by gesture
hyprwink actions                                       built-in actions
hyprwink watch                                         the state continuously as JSON lines (for bars)
hyprwink hook                                          Stop hook for Claude Code
hyprwink export | import <file.zip>                    save / take over the configuration (replaces everything)
hyprwink setup | remove                                set up / remove for this user
hyprwink ui [--setup | --settings | --mini | --toggle]
                                                       window (--settings: show/hide the settings)
```

## Files

| Where | What |
|---|---|
| `~/.config/hyprwink/settings.json` | settings made in the window |
| `~/.config/hyprwink/config.toml` | fine tuning (optional, defaults in `src/hyprwink/default_config.toml`) |
| `~/.config/hyprwink/gestures.json`, `samples.json`, `photos/` | gestures: name and action, recordings, photos and clips |
| `~/.config/hyprwink/gaze.json`, `gaze-samples.json` | gaze calibration and its measurements (no images) |
| `~/.config/systemd/user/hyprwink-{core,vision}.service` | the two services (from `hyprwink setup`) |
| `~/.local/share/applications/io.github.felixbk98.hyprwink.desktop` | launcher (from `hyprwink setup`) |
| `~/.cache/hyprwink/` | models (hand, face, Whisper), Piper voice; fetched again when needed |
| `$XDG_RUNTIME_DIR/hyprwink/` | sockets, dictation state (`dictation`), Claude Code answers |
| keyring (Secret Service) | API keys: `service=hyprwink`, `account=fish-audio` / `elevenlabs` |

## Structure

Two systemd user services, connected through Unix sockets (JSON lines):

- **hyprwink-vision** (`src/hyprwink/vision/`): webcam → MediaPipe hand landmarks → your gestures,
  face → gaze point. Records gestures and calibrates the gaze.
  - `features.py` hand shape as features (finger bends, thumb, direction of each finger in the image)
  - `templates.py` comparison with the recordings; what resembles none triggers nothing; two-hand gestures first
  - `tracker.py` a pose only counts once it is held still briefly
  - `motion.py` movements: cut out (start to standstill), compare path and hand shape
  - `drag.py` grab – drag – let go (move window in swipe direction)
  - `describe.py` the hand shape in words (for checking only)
  - `gaze.py` gaze ray in 3D (head position and direction + iris) → crossing with the camera plane →
    a map per monitor; blinks are skipped, the gaze point is the median of the last frames
- **hyprwink-core** (`src/hyprwink/core/`): runs actions, state for the window and the bar.
  - `engine.py` gesture → action, status; `actions.py` runs actions; `media.py` players and volume
  - `dictation.py` dictation; `reader.py` reading aloud; `page.py` newest message of a web page
  - `stt/` speech to text (`whisper.py`, `elevenlabs.py`), `tts/` text to speech (`piper.py`,
    `fishaudio.py`), `providers.py` what they share (errors, API keys)
  - `gazefocus.py` focus follows gaze; `hypr.py` access to Hyprland (`hyprctl`)
- **Window** (`src/hyprwink/ui/`, GTK4/libadwaita): `camera_page.py`, `gestures_page.py`,
  `settings_page.py`, `calibration.py`; `style.py` the two designs.
- **Shared** (`src/hyprwink/`): `settings.py` settings, `gestures.py` gestures and actions,
  `config.py` loading/saving, `paths.py` locations, `ipc.py` sockets, `models.py` models, `i18n.py`
  languages, `integration.py` per-user setup/removal, `backup.py` export/import, `answers.py` Claude Code
  answers, `cli.py` commands.
- **Integrations**: `src/hyprwink/data/` templates for the services and the launcher, Hyprland example, `examples/` example gestures;
  `src/hyprwink/quickshell/` Quickshell plugin (bar symbol with gaze dot, dictation pill).

### Languages

All texts are written in English in the code, marked with `_("…")` (translated) or `N_("…")` (only
marked, translated where shown); `i18n.py` picks the language. Translations are gettext files in `po/`
(`hyprwink.pot` = all texts, `de.po` = German); compiled they are in `src/hyprwink/locale/` (kept in
the repository, so pipx installs them).

```sh
xgettext -L Python --from-code=UTF-8 -k_ -kN_ -kngettext:1,2 --add-comments=Translators \
  --add-location=file -o po/hyprwink.pot $(find src -name '*.py' | sort)   # collect the texts
msgmerge -U --backup=none po/de.po po/hyprwink.pot                          # update a translation
msgfmt -o src/hyprwink/locale/de/LC_MESSAGES/hyprwink.mo po/de.po          # compile it
```

A new language: `msginit -i po/hyprwink.pot -l <code> -o po/<code>.po`, translate, compile, add its
name to `i18n.NAMES`. For speech output it also needs Piper voices in `LANGUAGE_VOICES`
(`src/hyprwink/core/tts/piper.py`).

### More providers

A provider is a module in `core/stt/` or `core/tts/` plus an entry in `PROVIDERS` of its
`__init__.py`, which describes what the module has to provide. The settings build the provider list,
voice and API key rows from it. When a cloud provider fails, the local one takes over.

## Development

Straight from the source (changes apply at once):

```sh
venv=~/.local/share/hyprwink/venv
python -m venv --system-site-packages $venv
$venv/bin/pip install -e '.[gpu]'
ln -s $venv/bin/hyprwink ~/.local/bin/hyprwink
hyprwink setup
```

After a change: `systemctl --user restart hyprwink-core hyprwink-vision`, reopen the window.
Tests: `$venv/bin/pip install pytest && $venv/bin/python -m pytest`.

## License

MIT
