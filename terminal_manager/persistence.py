"""One coalescing inventory writer; UI refresh never waits for snapshot fsync."""
import threading
from . import state_db
from .store import save_runtime_session


class InventoryWriter:
    def __init__(self):
        self.condition = threading.Condition()
        self.pending = None
        self.stopping = False
        self.error = ''
        self.thread = threading.Thread(target=self._run, name='inventory-writer', daemon=True)
        self.thread.start()

    def submit(self, entries):
        with self.condition:
            self.pending = [dict(e) for e in entries]
            self.condition.notify()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending is not None or self.stopping)
                if self.pending is None:
                    return
                entries, self.pending = self.pending, None
            try:
                state_db.observe(entries)
                save_runtime_session(clean_shutdown=False, entries=entries)
                self.error = ''
            except Exception as exc:
                self.error = '登记保存失败：' + str(exc)

    def close(self):
        with self.condition:
            self.stopping = True
            self.condition.notify()
        self.thread.join(timeout=4)
        return not self.thread.is_alive()
