"""One isolated AT-SPI connection owner, with a fail-closed restart policy."""
from __future__ import annotations

import atexit
import json
import os
import select
import subprocess
import sys
import threading
import time


MAX_MESSAGE = 4 * 1024 * 1024


class TabWorker:
    def __init__(self, command=None, timeout: float = 6.0):
        self.command = command or [sys.executable, "-m", "terminal_manager.tabs"]
        self.timeout = timeout
        self.process = None
        self.error = ""
        self._lock = threading.Lock()
        self._closed = threading.Event()

    def request(self, payload):
        # The UI and background scanner share this connection. Do not queue UI
        # clicks behind a slow scan, or interleave messages on the same pipe.
        if not self._lock.acquire(blocking=False):
            return None
        try:
            if self._closed.is_set() or self.error:
                return None
            if self.process is None:
                self.process = subprocess.Popen(
                    self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0, close_fds=True,
                )
                os.set_blocking(self.process.stdin.fileno(), False)
                os.set_blocking(self.process.stdout.fileno(), False)
            elif self.process.poll() is not None:
                raise RuntimeError("标签扫描进程已退出")
            outgoing = json.dumps(payload).encode() + b"\n"
            if len(outgoing) > MAX_MESSAGE:
                raise ValueError("标签请求过大")
            incoming = bytearray()
            deadline = time.monotonic() + self.timeout
            reader, writer = self.process.stdout.fileno(), self.process.stdin.fileno()
            while not self._closed.is_set():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("标签扫描超时")
                readable, writable, _ = select.select(
                    [reader], [writer] if outgoing else [], [], min(left, 0.1))
                if writable:
                    outgoing = outgoing[os.write(writer, outgoing[:65536]):]
                if readable:
                    chunk = os.read(reader, 65536)
                    if not chunk:
                        raise RuntimeError("标签扫描进程断开")
                    incoming.extend(chunk)
                    if len(incoming) > MAX_MESSAGE:
                        raise ValueError("标签响应过大")
                    if b"\n" in incoming:
                        response = json.loads(incoming)
                        if not isinstance(response, dict) or "result" not in response:
                            raise ValueError("标签响应无效")
                        if response.get("error"):
                            raise RuntimeError(str(response["error"]))
                        return response["result"]
            self._stop()
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            # Never turn a native crash/hang into another endless stream of
            # short-lived accessibility clients. Only explicit retry resets it.
            self.error = str(exc)
            self._stop()
        finally:
            self._lock.release()
        return None

    def _stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        process.stdin.close()  # EOF quits a healthy worker's GLib loop.
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            process.kill()  # Only our isolated worker, never a terminal.
            process.wait(timeout=1)
        finally:
            process.stdout.close()

    def retry(self) -> bool:
        if self._closed.is_set() or not self._lock.acquire(blocking=False):
            return False
        try:
            # Healthy workers must not be recycled by repeated refresh clicks.
            if self.error:
                self._stop()
                self.error = ""
            return True
        finally:
            self._lock.release()

    def close(self):
        self._closed.set()
        with self._lock:
            self._stop()


worker = TabWorker()
atexit.register(worker.close)
