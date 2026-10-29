"""Runs inside the terminal: records PID/TTY/exit without reading TUI output."""
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .state_db import root, boot_id
from .store import _atomic_private_json


def receipt_path(token):
    if not re.fullmatch(r'tm-recover-[a-f0-9]{32}', token):
        raise ValueError('Invalid recovery identity')
    return root() / 'launches' / (token + '.json')


def main():
    token, *argv = sys.argv[1:]
    if argv and argv[0] == '--':
        argv.pop(0)
    path = receipt_path(token)
    receipt = {'boot': boot_id(), 'time': time.time(), 'tty': os.ttyname(0), 'state': 'starting'}
    try:
        child = subprocess.Popen(argv)
        receipt.update(pid=child.pid, state='running')
        try:
            receipt['start_ticks'] = Path(f'/proc/{child.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError:
            pass
        _atomic_private_json(path, receipt)
        code = child.wait()
        receipt.update(state='exited', exit_code=code, time=time.time())
    except Exception as exc:
        receipt.update(state='failed', error=str(exc), time=time.time())
    _atomic_private_json(path, receipt)
    # Receipts contain only process metadata, never conversation text.
    for old in sorted(path.parent.glob('tm-recover-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[128:]:
        old.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
