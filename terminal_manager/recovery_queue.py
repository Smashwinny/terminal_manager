"""Serial recovery with durable identities, pressure admission and explicit retry."""
import json
import queue
import threading
import time
import uuid

from . import codex_runtime, codex_sessions, state_db, protected
from .model import ShellInfo
from .recovery import launch_tracked
from .recovery_child import receipt_path
from .store import load_shells, save_shell
from .x11 import list_windows, window_role, X11Error

LABELS = {'pending': '待恢复', 'starting': '启动中', 'awaiting': '窗口已开 · 对话待确认',
          'ready': '恢复已确认', 'failed': '恢复失败 · 可重试', 'paused': '已暂停',
          'skipped': '已跳过', 'missing': '窗口未连接', 'available': '未自动恢复', 'observed': '已连接'}


def receipt(token):
    if not token:
        return {}
    try:
        value = json.loads(receipt_path(token).read_text())
        return value if value.get('boot') == state_db.boot_id() else {}
    except (OSError, ValueError):
        return {}


def bind(entry, window, tty=''):
    shell = next((s for s in load_shells() if s.shell_id == entry['shell_id']), None)
    if shell is None:
        shell = ShellInfo(entry['shell_id'], '', 0, '', entry['name'], 'unbound', '', '', entry['cwd'], None, '', time.time(), time.time())
    shell.window_id, shell.cwd = window.window_id, entry['cwd']
    shell.shell_pid, shell.tty, shell.foreground_pid, shell.command = 0, '', None, ''
    shell.protected_id = entry.get('protected_id', '')
    for key in codex_sessions.FIELDS:
        setattr(shell, key, entry.get(key, ''))
    save_shell(shell)
    entry = {**entry, 'window_id': window.window_id, 'window_pid': window.pid}
    return entry


class RecoveryQueue:
    def __init__(self, monitor, *, timeout=45):
        self.monitor = monitor
        self.timeout = timeout
        self.events = queue.SimpleQueue()
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.thread = None
        self.message = ''
        self._roles = {}

    def _role(self, window):
        key = (window.window_id, window.pid)
        value, checked = self._roles.get(key, ('', 0))
        if not value and time.monotonic() - checked > .5:
            value = window_role(window.window_id)
            self._roles[key] = (value, time.monotonic())
        return value

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, entries):
        if self.active:
            return False
        self.paused.clear()
        self.thread = threading.Thread(target=self._run, args=([dict(e) for e in entries],), daemon=True, name='recovery-queue')
        self.thread.start()
        return True

    def _run(self, entries):
        try:
            # Validate once before starting a batch: desktop PATH differs from shell PATH.
            if any(e.get('codex_session_id') for e in entries):
                try:
                    codex_runtime.preflight()
                except ValueError as exc:
                    for entry in entries:
                        state_db.mark(entry, 'failed', str(exc))
                    self.message = str(exc)
                    return
            for index, entry in enumerate(entries):
                if self.stop.is_set():
                    return
                if self.paused.is_set():
                    for remaining in entries[index:]:
                        state_db.mark(remaining, 'paused', '用户暂停恢复')
                    return
                reason = getattr(self.monitor, 'admission_reason', lambda: self.monitor.reason)
                while reason() and not self.stop.is_set() and not self.paused.is_set():
                    self.message = '恢复等待：' + reason()
                    self.stop.wait(1)
                if self.stop.is_set():
                    return
                if self.paused.is_set():
                    for remaining in entries[index:]:
                        state_db.mark(remaining, 'paused', '用户暂停恢复')
                    return
                # A user can remove or skip a record while this batch runs.
                current = next((r for r in state_db.records() if r['shell_id'] == entry['shell_id']), None)
                if current is None or current['_state'] == 'skipped':
                    continue
                self.message = f"恢复 {index + 1}/{len(entries)}：{entry['name']}"
                try:
                    self._one(entry)
                except Exception as exc:
                    state_db.mark(entry, 'failed', str(exc))
                self.events.put(('refresh', None))
                self.stop.wait(.2)
            self.message = '恢复队列处理完成；未确认和失败项目保留在恢复清单中。'
        except Exception as exc:
            self.message = '恢复队列停止：' + str(exc)
        finally:
            self.events.put(('refresh', None))

    def _one(self, entry):
        windows = list_windows()
        sid = entry.get('codex_session_id')
        if sid:
            processes, catalog = codex_sessions.snapshot()
            for window in windows:
                found = codex_sessions.detect(window.title, entry['cwd'], '', processes, catalog)
                if found.get('codex_session_id') == sid and found.get('codex_home') == (entry.get('codex_home') or codex_sessions.default_home()):
                    entry = bind(entry, window)
                    state_db.mark(entry, 'ready')
                    return
            if any(p['id'] == sid and p['home'] == (entry.get('codex_home') or codex_sessions.default_home()) for p in processes):
                state_db.mark(entry, 'awaiting', '准确会话进程已存在，等待窗口关联；不会重复启动')
                return
        if entry.get('protected_id'):
            try:
                protected.inspect_task(entry['protected_id'])
                protected.open_task(entry['protected_id'])
                state_db.mark(entry, 'awaiting', '已请求连接原任务')
            except protected.ProtectionError as exc:
                state_db.mark(entry, 'failed', str(exc))
            return
        # XIDs only identify a window during the same desktop lifetime.
        if entry.get('_boot') == state_db.boot_id():
            existing = next((w for w in windows if w.window_id == entry.get('window_id') and w.pid == entry.get('window_pid')), None)
            if existing and not sid:
                state_db.mark(entry, 'ready')
                return
        token = entry.get('_token') if entry.get('_boot') == state_db.boot_id() else ''
        prior = receipt(token)
        # Durable role tokens also find late windows after a timeout/restart.
        existing = next((w for w in windows if token and self._role(w) == token), None)
        if existing:
            entry = bind(entry, existing)
            state_db.mark(entry, 'awaiting' if sid else 'ready')
            self.events.put(('bound', (existing.window_id, prior.get('tty', ''))))
            return
        if prior.get('state') == 'running' and self._pid_alive(prior):
            state_db.mark(entry, 'awaiting', '原启动进程仍在，等待窗口出现；不会重复启动')
            return
        token = 'tm-recover-' + uuid.uuid4().hex
        before_ids = {w.window_id for w in windows}
        state_db.mark(entry, 'starting', token=token)
        if self.stop.is_set():
            return
        ok, error = launch_tracked(entry, token)
        if not ok:
            state_db.mark(entry, 'failed', error)
            return
        deadline = time.monotonic() + self.timeout
        bound_window = None
        next_check = 0
        while not self.stop.wait(.25):
            child = receipt(token)
            if child.get('state') in ('exited', 'failed'):
                state_db.mark(entry, 'failed', child.get('error') or f"终端内程序已退出，退出码 {child.get('exit_code')}；会话关联已保留")
                return
            try:
                windows = list_windows()
                window = next((w for w in windows if w.window_id not in before_ids and self._role(w) == token), None)
            except X11Error:
                window = None
            if window and child.get('state') == 'running':
                if bound_window != window.window_id:
                    entry = bind(entry, window)
                    bound_window = window.window_id
                    self.events.put(('bound', (window.window_id, child.get('tty', ''))))
                if not sid:
                    state_db.mark(entry, 'ready')
                    return
                if time.monotonic() >= next_check:
                    next_check = time.monotonic() + 2
                    found = codex_sessions.detect(window.title, entry['cwd'], child.get('tty', ''), *codex_sessions.snapshot())
                    if found.get('codex_session_id') == sid:
                        state_db.mark(entry, 'ready')
                        return
            if time.monotonic() >= deadline:
                state_db.mark(entry, 'awaiting' if window else 'failed', '窗口已打开，对话尚未确认' if window else '等待窗口超时；原启动身份已保存，可安全重试')
                return

    @staticmethod
    def _pid_alive(value):
        from pathlib import Path
        try:
            proc = Path(f"/proc/{value['pid']}")
            ticks = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
            return ticks == value.get('start_ticks') and (proc / 'fd/0').readlink().as_posix() == value.get('tty')
        except (OSError, KeyError):
            return False

    def close(self):
        self.stop.set()
        # No terminal child is stopped. A persisted 'starting' row resumes next time.
        if self.thread:
            self.thread.join(timeout=1)
