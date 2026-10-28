"""Core service: receives the gestures from vision, runs actions, serves the CLI and the window."""

import logging
import signal
import sys
import threading

from .. import ipc, paths
from .engine import Engine
from .providers import ProviderError

log = logging.getLogger("hyprwink.core")


class Core:
    def __init__(self):
        self.engine = Engine()

    def run(self):
        server = ipc.Server(paths.CORE_SOCKET, self.handle)
        server.start()
        log.info("listening on %s", paths.CORE_SOCKET)
        threading.Event().wait()

    def handle(self, conn):
        msg, _ = conn.recv()
        if msg is None:
            return
        if msg.get("type") == "hello" and msg.get("role") == "vision":
            self._vision(conn)
        elif msg.get("cmd") == "watch":
            self._watch(conn)
        elif msg.get("cmd") == "hold":
            self._hold(conn)
        else:
            conn.send(self.command(msg))

    def _vision(self, conn):
        log.info("vision connected")
        self.engine.set_vision(conn)
        try:
            while True:
                msg, _ = conn.recv()
                if msg is None:
                    break
                if msg.get("type") == "frame":
                    self.engine.on_frame(msg)
        finally:
            if self.engine.vision is conn:
                self.engine.set_vision(None)
            log.info("vision disconnected")

    def _watch(self, conn):
        engine = self.engine
        mailbox = ipc.Mailbox(conn)
        with engine.lock:
            mailbox.put(dict(engine.status))
            engine.watchers.append(mailbox)
        try:
            while conn.recv()[0] is not None:
                pass
        finally:
            with engine.lock:
                engine.watchers.remove(mailbox)
            mailbox.close()

    def _hold(self, conn):
        """Gesture actions stay blocked (and the camera on) as long as this
        connection is open, so a crashed window cannot leave them blocked."""
        engine = self.engine
        engine.set_holding(True)
        try:
            conn.send({"ok": True})
            while conn.recv()[0] is not None:
                pass
        finally:
            engine.set_holding(False)

    def command(self, msg):
        e = self.engine
        cmd = msg.get("cmd")
        try:
            if cmd == "status":
                return dict(e.status, ok=True)
            if cmd == "pause":
                e.set_paused(True)
            elif cmd == "resume":
                e.set_paused(False)
            elif cmd == "toggle":
                e.set_paused(not e.paused)
            elif cmd == "action":
                e.run(msg["action"])
            elif cmd == "reload":
                e.reload()
            elif cmd == "read":
                e.actions.reader.start(msg.get("text"))
            elif cmd == "voice":
                e.actions.reader.set_voice(msg["engine"], msg["voice"])
            elif cmd == "dictate":
                e.dictate(msg["command"], msg.get("file"), msg.get("badge") or "")
            elif cmd == "stop_reading":
                e.actions.reader.stop()
            else:
                return {"ok": False, "error": f"unknown command {cmd}"}
        except ProviderError as ex:
            return {"ok": False, "error": str(ex)}
        except Exception as ex:
            log.exception("command %s failed", cmd)
            return {"ok": False, "error": str(ex)}
        return {"ok": True}


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    core = Core()

    def stop(*_):
        core.engine.update_dim(False)     # Hyprland's own look again
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    core.run()


if __name__ == "__main__":
    main()
