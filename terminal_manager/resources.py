"""Bounded, read-only pressure sampling. Never kills or suspends user tasks."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import time

from . import state_db


def read_sample(proc=Path('/proc')):
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in (proc / 'meminfo').read_text().splitlines()}
    vm = dict(line.split() for line in (proc / 'vmstat').read_text().splitlines())
    pressure = {}
    for kind in ('memory', 'io'):
        try:
            for line in (proc / 'pressure' / kind).read_text().splitlines():
                parts = line.split()
                pressure[kind + '_' + parts[0]] = float(dict(p.split('=') for p in parts[1:])['avg10'])
        except (OSError, KeyError, ValueError):
            pass
    return {'time': time.time(), 'total': memory['MemTotal'], 'available': memory['MemAvailable'],
            'swap_used': memory['SwapTotal'] - memory['SwapFree'], 'swap_in_pages': int(vm['pswpin']),
            'swap_out_pages': int(vm['pswpout']), **pressure}


def pressure_reason(sample):
    reserve = max(1024**3, sample.get('total', 0) * .15)
    if sample.get('available', float('inf')) < reserve:
        return f'可用内存低于预留量 {reserve / 1024**3:.1f} GiB'
    if sample.get('swap_in_pages_sec', 0) + sample.get('swap_out_pages_sec', 0) > 4096:
        return '系统正在密集换页，等待负载稳定'
    if sample.get('memory_full', 0) >= 5 or sample.get('memory_some', 0) >= 15:
        return '系统正在因内存压力持续停顿'
    if sample.get('io_full', 0) >= 20:
        return '系统 I/O 等待过高'
    return ''


def processes(proc=Path('/proc')):
    result = []
    for p in proc.glob('[0-9]*'):
        try:
            values = dict(line.split(':', 1) for line in (p / 'status').read_text().splitlines() if ':' in line)
            name = values['Name'].strip()
            if name not in ('gnome-shell', 'gnome-terminal-', 'codex', 'tmux: server', 'python3'):
                continue
            if name == 'python3' and b'terminal_manager' not in (p / 'cmdline').read_bytes():
                continue
            rss = int(values.get('VmRSS', '0').split()[0])
            swap = int(values.get('VmSwap', '0').split()[0])
            result.append({'pid': int(p.name), 'name': name, 'rss_kib': rss, 'swap_kib': swap})
        except (OSError, ValueError, KeyError):
            pass
    return sorted(result, key=lambda r: r['rss_kib'], reverse=True)[:64]


class ResourceMonitor:
    def __init__(self):
        self.sample = {}
        self.reason = ''
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name='resource-monitor')
        self.thread.start()

    def _run(self):
        directory = state_db.root()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = RotatingFileHandler(directory / 'resource-metrics.log', maxBytes=1_000_000, backupCount=2)
        logger = logging.Logger('resources')
        logger.addHandler(handler)
        previous = None
        next_log = 0
        try:
            while not self.stop.is_set():
                try:
                    sample = read_sample()
                    if previous:
                        elapsed = max(.1, sample['time'] - previous['time'])
                        sample['swap_in_pages_sec'] = (sample['swap_in_pages'] - previous['swap_in_pages']) / elapsed
                        sample['swap_out_pages_sec'] = (sample['swap_out_pages'] - previous['swap_out_pages']) / elapsed
                    previous = sample
                    self.sample = sample
                    self.reason = pressure_reason(sample)
                    if time.monotonic() >= next_log:
                        logger.warning(json.dumps({**sample, 'processes': processes()}, ensure_ascii=False))
                        next_log = time.monotonic() + 30
                except (OSError, ValueError, KeyError) as exc:
                    self.reason = '资源采样暂不可用：' + str(exc)
                self.stop.wait(5)
        finally:
            handler.close()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)

    def admission_reason(self):
        try:
            # Check memory immediately before each launch, not a stale 5s sample.
            return pressure_reason({**self.sample, **read_sample()})
        except (OSError, ValueError, KeyError):
            return self.reason or '资源采样暂不可用'
