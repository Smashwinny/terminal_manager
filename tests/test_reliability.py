import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import time

import pytest

from terminal_manager import state_db, codex_runtime
from terminal_manager.model import ShellInfo, WindowInfo
from terminal_manager.recovery_queue import RecoveryQueue
from terminal_manager.resources import pressure_reason
from terminal_manager.store import save_shell, remove_shell, recovery_candidates, save_runtime_session


@pytest.fixture
def entry(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    return {'shell_id':'one', 'name':'project', 'cwd':str(tmp_path), 'window_id':'0x1'}


def test_node_follows_npm_prefix_not_desktop_path(tmp_path, monkeypatch):
    prefix = tmp_path / 'node24'
    js = prefix / 'lib/node_modules/@openai/codex/bin/codex.js'
    js.parent.mkdir(parents=True)
    js.write_text('#!/usr/bin/env node\n')
    node = prefix / 'bin/node'
    node.parent.mkdir()
    node.write_text('#!/bin/sh\necho good-node\n')
    node.chmod(0o700)
    link = tmp_path / 'codex'
    link.symlink_to(js)
    monkeypatch.setenv('PATH', str(tmp_path))
    link.chmod(0o700)
    assert codex_runtime.command() == [str(node), str(js)]
    assert codex_runtime.preflight() == [str(node), str(js)]


def test_failed_entries_survive_empty_observation_clean_exit_and_restart(entry):
    state_db.mark(entry, 'failed', 'runtime unavailable')
    state_db.observe([])
    save_runtime_session(clean_shutdown=True, entries=[])
    assert state_db.pending()[0]['shell_id'] == entry['shell_id']
    assert recovery_candidates()[0]['_error'] == 'runtime unavailable'


def test_removal_tombstone_prevents_history_resurrection(entry):
    save_shell(ShellInfo('one','0x1',0,'','project','idle','','',entry['cwd'],None,'',0,0))
    save_runtime_session(clean_shutdown=False, entries=[entry])
    assert remove_shell('one')
    state_db.observe([entry])
    state_db.mark(entry, 'failed', 'stale worker')
    assert not recovery_candidates()


def test_new_boot_recovers_observed_even_after_clean_manager_exit(entry):
    state_db.observe([entry])
    save_runtime_session(clean_shutdown=True, entries=[entry])
    assert not state_db.pending()
    with patch('terminal_manager.state_db.boot_id', return_value='next-boot'):
        assert state_db.pending()[0]['shell_id'] == 'one'


def test_skipped_record_stays_skipped_across_reboot(entry):
    state_db.mark(entry, 'skipped')
    with patch('terminal_manager.state_db.boot_id', return_value='next-boot'):
        assert state_db.pending() == []
    assert len(state_db.records()) == 1


def test_partial_batch_does_not_lose_unfinished_items(entry):
    second = {**entry,'shell_id':'two'}
    state_db.mark(entry, 'ready')
    state_db.mark(second, 'starting', token='tm-recover-'+'b'*32)
    state_db.observe([entry])
    assert {r['shell_id'] for r in state_db.pending()} == {'two'}


def test_late_window_retry_reuses_role_without_launch(entry):
    record = {**entry, '_boot':state_db.boot_id(), '_token':'tm-recover-'+'a'*32}
    window = WindowInfo('0x2',0,12,0,0,800,600,'gnome-terminal','','shell')
    worker = RecoveryQueue(SimpleNamespace(reason=''))
    with patch('terminal_manager.recovery_queue.list_windows',return_value=[window]), patch('terminal_manager.recovery_queue.window_role',return_value=record['_token']), patch('terminal_manager.recovery_queue.launch_tracked') as launch:
        worker._one(record)
    launch.assert_not_called()
    assert state_db.records()[0]['window_id'] == '0x2'


def test_launcher_failure_is_recorded_not_success(entry):
    worker = RecoveryQueue(SimpleNamespace(reason=''))
    with patch('terminal_manager.recovery_queue.list_windows',return_value=[]), patch('terminal_manager.recovery_queue.launch_tracked',return_value=(False,'dbus unavailable')):
        worker._one(entry)
    assert state_db.pending()[0]['_error'] == 'dbus unavailable'


def test_common_preflight_failure_stops_whole_batch(entry):
    entries = [{**entry,'shell_id':str(n),'codex_session_id':'bad'} for n in range(4)]
    worker = RecoveryQueue(SimpleNamespace(reason=''))
    with patch('terminal_manager.codex_runtime.preflight', side_effect=ValueError('wrong Node')), patch('terminal_manager.recovery_queue.launch_tracked') as launch:
        worker._run(entries)
    launch.assert_not_called()
    assert len(state_db.pending()) == 4
    assert all(r['_error'] == 'wrong Node' for r in state_db.pending())


def test_pressure_pauses_launch_without_killing_processes(entry):
    state_db.mark(entry, 'pending')
    worker = RecoveryQueue(SimpleNamespace(reason='memory pressure'))
    with patch('terminal_manager.recovery_queue.launch_tracked') as launch:
        worker.start([entry])
        time.sleep(.05)
        worker.close()
    launch.assert_not_called()
    assert state_db.pending()[0]['shell_id'] == 'one'


def test_swap_usage_alone_does_not_pause():
    assert pressure_reason({'available': 4*1024**3, 'swap_used': 40*1024**3}) == ''
    assert pressure_reason({'available': 100*1024**2})
    assert pressure_reason({'available': 4*1024**3, 'memory_full': 8})
    assert pressure_reason({'available': 2*1024**3, 'total': 16*1024**3})
    assert pressure_reason({'available': 8*1024**3, 'swap_in_pages_sec': 5000})


def test_backup_contains_committed_wal_and_is_private(entry):
    import sqlite3
    state_db.mark(entry,'failed','keep me')
    state_db.backup()
    path = state_db.root() / 'inventory-backup.sqlite3'
    with sqlite3.connect(path) as db:
        assert db.execute('select error from recovery').fetchone()[0] == 'keep me'
    assert path.stat().st_mode & 0o777 == 0o600


def test_unchanged_snapshot_does_not_write_every_tick(entry):
    from terminal_manager.store import runtime_session_path
    save_runtime_session(clean_shutdown=False,entries=[entry])
    before = runtime_session_path().stat().st_mtime_ns
    save_runtime_session(clean_shutdown=False,entries=[entry])
    assert runtime_session_path().stat().st_mtime_ns == before
