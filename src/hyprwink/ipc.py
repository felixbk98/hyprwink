"""Newline-delimited JSON over Unix sockets.

A message may carry a binary payload: its header has "bytes": n and the n raw
bytes follow right after the newline (used for preview frames).
"""

import json
import logging
import os
import socket
import threading

log = logging.getLogger("hyprwink.ipc")


class Connection:
    def __init__(self, sock):
        self.sock = sock
        self.rfile = sock.makefile("rb")
        self._lock = threading.Lock()

    def send(self, msg, payload=None):
        if payload is not None:
            msg = dict(msg, bytes=len(payload))
        data = json.dumps(msg, separators=(",", ":")).encode() + b"\n"
        with self._lock:
            self.sock.sendall(data + payload if payload is not None else data)

    def recv(self):
        """Next (message, payload) or (None, None) once the peer is gone."""
        line = self.rfile.readline()
        if not line:
            return None, None
        msg = json.loads(line)
        payload = None
        if "bytes" in msg:
            payload = self.rfile.read(msg["bytes"])
        return msg, payload

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def connect(path, timeout=None):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(path))
    sock.settimeout(None)
    return Connection(sock)


def request(path, msg, timeout=3):
    """One request, one reply ({"ok": False} when the peer gave none)."""
    conn = connect(path, timeout)
    conn.sock.settimeout(timeout)
    try:
        conn.send(msg)
        reply, _ = conn.recv()
        return reply if isinstance(reply, dict) else {"ok": False, "error": "no reply"}
    finally:
        conn.close()


class Mailbox:
    """Sends the latest message to one subscriber in its own thread, so a
    slow or stuck reader never blocks the sender; older unsent ones are
    dropped."""

    def __init__(self, conn):
        self.conn = conn
        self.cond = threading.Condition()
        self.item = None
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, msg, payload=None):
        with self.cond:
            self.item = (msg, payload)
            self.cond.notify()

    def close(self):
        with self.cond:
            self.alive = False
            self.cond.notify()

    def _run(self):
        while True:
            with self.cond:
                while self.item is None and self.alive:
                    self.cond.wait()
                if not self.alive:
                    return
                (msg, payload), self.item = self.item, None
            try:
                self.conn.send(msg, payload)
            except OSError:
                self.alive = False
                return


class Server:
    """Accepts connections and runs handler(conn) for each in its own thread."""

    def __init__(self, path, handler):
        self.path = path
        self.handler = handler
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(path))
        os.chmod(path, 0o600)
        self.sock.listen(16)

    def start(self):
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            sock, _ = self.sock.accept()
            threading.Thread(target=self._run, args=(Connection(sock),), daemon=True).start()

    def _run(self, conn):
        try:
            self.handler(conn)
        except (OSError, ValueError):
            pass
        except Exception:
            log.exception("request failed")
        finally:
            conn.close()
