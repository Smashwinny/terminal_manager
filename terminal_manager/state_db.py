"""Durable inventory, independent of window discovery and manager shutdown.

Only this application's metadata is stored here. Legacy JSON is imported once
and retained for rollback; Codex databases are never modified.
"""
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import time

from .model import ShellInfo


def root() -> Path:
    return Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'terminal-manager'


def boot_id() -> str:
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def _json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


@contextmanager
def connection():
    directory = root()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    db = sqlite3.connect(directory / 'inventory.sqlite3', timeout=3)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA wal_autocheckpoint=128')
        db.execute('PRAGMA journal_size_limit=1048576')
        db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,payload TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS recovery(id TEXT PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL,desired INTEGER NOT NULL,boot TEXT NOT NULL,token TEXT NOT NULL DEFAULT \'\',error TEXT NOT NULL DEFAULT \'\',attempts INTEGER NOT NULL DEFAULT 0,updated REAL NOT NULL)')
        if not db.execute("SELECT 1 FROM meta WHERE key='migrated'").fetchone():
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM meta WHERE key='migrated'").fetchone():
                _migrate(db)
        yield db
        db.commit()
        for path in directory.glob('inventory.sqlite3*'):
            path.chmod(0o600)
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _migrate(db):
    # Transactional and idempotent; interrupted imports start over next time.
    legacy = _json(root() / 'runtime-session.json', {})
    entries = {e['shell_id']: e for e in legacy.get('entries', []) if isinstance(e, dict) and e.get('shell_id')}
    for path in sorted((root() / 'session-history').glob('*.json'), reverse=True):
        for entry in _json(path, {}).get('entries', []):
            if isinstance(entry, dict) and all(isinstance(entry.get(k), str) for k in ('shell_id', 'cwd', 'window_id', 'name')):
                entries.setdefault(entry['shell_id'], entry)
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    same_boot = legacy.get('updated_at', 0) > time.time() - uptime
    registered = set()
    for path in (root() / 'shells').glob('*.json'):
        try:
            shell = ShellInfo(**_json(path, {}))
        except TypeError:
            continue
        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,0)', (shell.shell_id, json.dumps(asdict(shell))))
        registered.add(shell.shell_id)
        entry = {**asdict(shell), **entries.get(shell.shell_id, {})}
        for key in ('codex_session_id', 'codex_cwd', 'codex_home'):
            if getattr(shell, key):
                entry[key] = getattr(shell, key)
        entries[shell.shell_id] = entry
    current = {e.get('shell_id') for e in legacy.get('entries', []) if isinstance(e, dict)}
    for sid, entry in entries.items():
        wanted = sid in current or (sid in registered and bool(entry.get('codex_session_id')))
        state = 'observed' if same_boot and sid in current else 'pending' if wanted else 'available'
        db.execute('INSERT OR IGNORE INTO recovery(id,payload,state,desired,boot,updated) VALUES(?,?,?,?,?,?)',
                   (sid, json.dumps(entry), state, int(wanted), boot_id() if same_boot and sid in current else '', time.time()))
    db.execute("INSERT INTO meta VALUES('migrated','1')")


def shells():
    with connection() as db:
        return [ShellInfo(**json.loads(r[0])) for r in db.execute('SELECT payload FROM records WHERE removed=0')]


def save_shell(shell):
    payload = asdict(shell)
    with connection() as db:
        db.execute('INSERT INTO records VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,removed=0', (shell.shell_id, json.dumps(payload)))
        old = db.execute('SELECT payload FROM recovery WHERE id=?', (shell.shell_id,)).fetchone()
        entry = {**(json.loads(old[0]) if old else {}), **payload}
        if old:
            db.execute('UPDATE recovery SET payload=? WHERE id=?', (json.dumps(entry), shell.shell_id))
        else:
            db.execute('INSERT INTO recovery(id,payload,state,desired,boot,updated) VALUES(?,?,?,?,?,?)',
                       (shell.shell_id, json.dumps(entry), 'available', 1, boot_id(), time.time()))


def records():
    with connection() as db:
        return [{**json.loads(r['payload']), '_state': r['state'], '_boot': r['boot'], '_token': r['token'], '_error': r['error'], '_attempts': r['attempts'], '_desired': bool(r['desired'])} for r in db.execute("SELECT * FROM recovery WHERE state!='removed'")]


def mark(entry, state, error='', *, token=None):
    with connection() as db:
        old = db.execute('SELECT state FROM recovery WHERE id=?', (entry['shell_id'],)).fetchone()
        if old and old[0] == 'removed':
            return
        clean = {k: v for k, v in entry.items() if not k.startswith('_')}
        db.execute('INSERT INTO recovery(id,payload,state,desired,boot,updated,error) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,state=excluded.state,error=excluded.error,boot=excluded.boot,updated=excluded.updated',
                   (entry['shell_id'], json.dumps(clean), state, 1, boot_id(), time.time(), error[:2000]))
        if token is not None:
            db.execute('UPDATE recovery SET token=?,attempts=attempts+1 WHERE id=?', (token, entry['shell_id']))


def observe(entries):
    """Absence is not deletion, completion, or permission to relaunch a task."""
    with connection() as db:
        seen = {e['shell_id'] for e in entries}
        for entry in entries:
            old = db.execute('SELECT * FROM recovery WHERE id=?', (entry['shell_id'],)).fetchone()
            if old and old['state'] == 'removed':
                continue
            merged = {**(json.loads(old['payload']) if old else {}), **entry}
            # A live window alone does not confirm a Codex conversation.
            state = old['state'] if old and old['state'] in ('starting', 'awaiting', 'failed', 'skipped', 'paused') else 'observed'
            text = json.dumps(merged)
            if not old or old['payload'] != text or old['boot'] != boot_id() or old['state'] == 'missing':
                db.execute('INSERT INTO recovery(id,payload,state,desired,boot,updated) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,state=excluded.state,boot=excluded.boot,updated=excluded.updated',
                           (entry['shell_id'], text, state, 1, boot_id(), time.time()))
        for old in db.execute("SELECT id FROM recovery WHERE state IN ('observed','ready')").fetchall():
            if old['id'] not in seen:
                db.execute("UPDATE recovery SET state='missing',updated=? WHERE id=?", (time.time(), old['id']))


def pending():
    current = boot_id()
    return [r for r in records() if r['_state'] in ('pending', 'starting', 'failed') or
            (r['_desired'] and r['_boot'] != current and r['_state'] not in ('skipped', 'paused', 'available'))]


def remove(sid):
    with connection() as db:
        exists = db.execute('SELECT 1 FROM records WHERE id=? AND removed=0', (sid,)).fetchone()
        db.execute('UPDATE records SET removed=1 WHERE id=?', (sid,))
        db.execute("UPDATE recovery SET state='removed',desired=0 WHERE id=? OR id LIKE ?", (sid, sid + ':tab:%'))
        return bool(exists)


def backup():
    """Online backup API includes committed WAL contents, unlike copying DB alone."""
    with connection() as source:
        source.commit()
        path = root() / 'inventory-backup.sqlite3'
        with sqlite3.connect(path) as target:
            source.backup(target)
        path.chmod(0o600)
