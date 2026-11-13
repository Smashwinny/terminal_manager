"""Exercise actual pipes/process lifetime without touching desktop AT-SPI."""
import sys
import threading
import time

import pytest

from terminal_manager.tab_worker import TabWorker


ECHO = '''import sys,json,os
for line in sys.stdin:
    print(json.dumps({'result': [os.getpid(), json.loads(line)]}), flush=True)
'''


def make_worker(code=ECHO, timeout=1):
    return TabWorker([sys.executable, '-u', '-c', code], timeout=timeout)


def test_many_scans_and_selections_share_one_process():
    worker = make_worker()
    try:
        pid = worker.request({'windows': []})[0]
        for i in range(100):
            payload = {'select': '0x2a', 'index': i % 2} if i % 2 else {'windows': []}
            assert worker.request(payload) == [pid, payload]
            assert worker.retry()  # Refresh must not replace a healthy process.
        child = worker.process
    finally:
        worker.close()
    assert child.poll() == 0
    assert worker.request({}) is None
    assert not worker.retry()


@pytest.mark.parametrize('code', [
    'import os; os._exit(11)',
    'import time; time.sleep(30)',
    'print("not-json", flush=True)',
    'print(\'{"result":null,"error":"native failed"}\', flush=True)',
    'print("x" * (4*1024*1024+1), flush=True)',
])
def test_failure_opens_circuit_until_explicit_retry(code):
    worker = make_worker(code, timeout=0.3)
    try:
        assert worker.request({}) is None
        assert worker.error
        assert worker.process is None
        worker.command = [sys.executable, '-u', '-c', ECHO]
        for _ in range(100):
            assert worker.request({}) is None
            assert worker.process is None
        assert worker.retry()
        assert worker.request({'retry': True})[1] == {'retry': True}
    finally:
        worker.close()


def test_large_request_and_response_do_not_deadlock_on_pipe_capacity():
    worker = make_worker()
    try:
        payload = {'windows': ['测试' * 100000]}
        assert worker.request(payload)[1] == payload
    finally:
        worker.close()


def test_concurrent_click_returns_without_queueing_and_close_cancels_scan():
    worker = make_worker('import time; time.sleep(30)', timeout=10)
    scan = threading.Thread(target=lambda: worker.request({}))
    scan.start()
    until = time.monotonic() + 2
    while worker.process is None and time.monotonic() < until:
        time.sleep(0.005)
    assert worker.process is not None
    started = time.monotonic()
    assert worker.request({}) is None
    assert time.monotonic() - started < 0.1
    assert not worker.retry()
    child = worker.process
    worker.close()
    scan.join(timeout=2)
    assert not scan.is_alive()
    assert child.poll() is not None
    assert time.monotonic() - started < 2


def test_child_exit_between_requests_does_not_automatically_respawn():
    worker = make_worker()
    try:
        assert worker.request({})
        worker.process.kill()
        worker.process.wait(timeout=2)
        assert worker.request({}) is None
        assert worker.error
        assert worker.process is None
    finally:
        worker.close()
