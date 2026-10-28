"""Command line: control the services and start the window."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import answers, gestures, ipc, paths
from .i18n import _


def _core(msg):
    try:
        return ipc.request(paths.CORE_SOCKET, msg)
    except OSError:
        print(_("Hyprwink is not running (hyprwink-core.service)."), file=sys.stderr)
        sys.exit(1)


def _print_reply(reply):
    if not reply.get("ok"):
        print(reply.get("error", _("Error")), file=sys.stderr)
        sys.exit(1)


def cmd_status(args):
    reply = _core({"cmd": "status"})
    if args.json:
        print(json.dumps(reply, ensure_ascii=False))
        return
    print(_("Camera:"), _("off") if reply["paused"] else _("on"))
    print(_("Camera service:"), _("connected") if reply["vision"] else _("not connected"))
    names = {g["id"]: g["name"] for g in gestures.load()["gestures"]}
    print(_("Gesture:"), names.get(reply.get("gesture"), "–"))


def cmd_simple(args):
    _print_reply(_core({"cmd": args.command}))


def cmd_action(args):
    _print_reply(_core({"cmd": "action", "action": args.name}))


def cmd_actions(args):
    for name, label in gestures.BUILTIN.items():
        print(f"{name:16} {_(label)}")


def cmd_dictate(args):
    target = str(Path(args.file).resolve()) if args.file else None
    _print_reply(_core({"cmd": "dictate", "command": args.what, "file": target, "badge": args.badge}))


def cmd_hook(args):
    """Claude Code Stop hook: keep the session's answer for reading aloud."""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    answers.answered(data.get("session_id", ""), data.get("last_assistant_message") or "")


def cmd_watch(args):
    """Status stream as JSON lines; reconnects when the service restarts.
    Ends quietly when the reader goes away."""
    try:
        _watch()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _watch():
    while True:
        try:
            conn = ipc.connect(paths.CORE_SOCKET, timeout=2)
            conn.send({"cmd": "watch"})
            while True:
                msg, _ = conn.recv()
                if msg is None:
                    break
                print(json.dumps(msg, ensure_ascii=False), flush=True)
        except BrokenPipeError:
            raise
        except OSError:
            pass
        print(json.dumps({"type": "status", "offline": True}), flush=True)
        time.sleep(2)


def cmd_export(args):
    from . import backup
    try:
        backup.save(args.file)
    except backup.BackupError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


def cmd_import(args):
    from . import backup
    try:
        backup.load(args.file)
    except backup.BackupError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


def cmd_setup(args):
    from . import integration
    integration.setup()


def cmd_remove(args):
    from . import integration
    integration.remove()


def cmd_ui(args):
    from .ui.app import main as ui_main
    argv = [sys.argv[0]]
    if args.mini:
        argv.append("--mini")
    if args.setup:
        argv.append("--setup")
    if args.toggle:
        argv.append("--toggle")
    if args.settings:
        argv.append("--settings")
    sys.exit(ui_main(argv))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="hyprwink",
                                     description=_("Dictation, speech output, gestures, focus follows gaze"))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help=_("show the state"))
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)
    for name, text in (("pause", _("camera off")), ("resume", _("camera on")),
                       ("toggle", _("camera on / off")),
                       ("reload", _("reload gestures and settings"))):
        sub.add_parser(name, help=text).set_defaults(func=cmd_simple)
    p = sub.add_parser("action", help=_("trigger an action (as by gesture)"))
    p.add_argument("name")
    p.set_defaults(func=cmd_action)
    sub.add_parser("actions", help=_("built-in actions")).set_defaults(func=cmd_actions)
    p = sub.add_parser("dictate", help=_("Dictation"))
    p.add_argument("what", choices=["toggle", "start", "stop", "send", "cancel"])
    p.add_argument("--file", help=_("write the text into this file instead of pasting it"))
    p.add_argument("--badge", default="", help=_("symbol in the pill for this recording"))
    p.set_defaults(func=cmd_dictate)
    sub.add_parser("hook", help=_("Claude Code hook (Stop): keep the answer of each session")).set_defaults(func=cmd_hook)
    sub.add_parser("watch", help=_("the state continuously as JSON")).set_defaults(func=cmd_watch)
    p = sub.add_parser("export", help=_("save the configuration to a file"))
    p.add_argument("file", help=_("ZIP file"))
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("import", help=_("take over the configuration from a file (replaces everything)"))
    p.add_argument("file", help=_("ZIP file"))
    p.set_defaults(func=cmd_import)
    sub.add_parser("setup", help=_("set up for this user (after installing)")).set_defaults(
        func=cmd_setup)
    sub.add_parser("remove", help=_("remove for this user (before uninstalling)")).set_defaults(
        func=cmd_remove)
    p = sub.add_parser("ui", help=_("open the window"))
    p.add_argument("--mini", action="store_true", help=_("Mini view on/off"))
    p.add_argument("--setup", action="store_true", help=_("Open gestures"))
    p.add_argument("--toggle", action="store_true", help=_("Show/hide the window"))
    p.add_argument("--settings", action="store_true", help=_("Show/hide the settings"))
    p.set_defaults(func=cmd_ui)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
