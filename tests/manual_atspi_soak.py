"""Opt-in native AT-SPI regression on a private Xvfb/D-Bus desktop.

Uses the incident's read-only GDB counter for this host's library builds.
The server explicitly allows its test parent/descendants to inspect it; no
production PID, accessibility setting, terminal or task is modified.
"""
import ctypes
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/atspi-20261113'
TOOLS = ROOT / 'tmp/protection-tools/extracted/usr'
sys.path.insert(0, str(ROOT))


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=20, **kwargs).stdout


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError('native test condition timed out')


def desktop():
    from terminal_manager.tabs import scan_tab_groups, select_tab
    from terminal_manager.tab_worker import worker
    from terminal_manager.x11 import list_windows
    wm_log = (OUT/'openbox.log').open('w')
    wm = subprocess.Popen([str(TOOLS/'bin/openbox'), '--sm-disable', '--config-file', str(TOOLS.parent/'etc/xdg/openbox/rc.xml')], stdout=wm_log, stderr=wm_log)
    server = None
    try:
        wait_for(lambda: subprocess.run(['wmctrl','-m'], capture_output=True).returncode == 0)
        def allow_test_debugger():
            assert ctypes.CDLL(None).prctl(0x59616d61, os.getppid(), 0, 0, 0) == 0
        server = subprocess.Popen(['/usr/libexec/gnome-terminal-server'], preexec_fn=allow_test_debugger, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(.5)
        run(['gnome-terminal','--window','--title=tab-one','--command=bash --noprofile --norc',
             '--tab','--title=tab-two','--command=bash --noprofile --norc'])
        wait_for(lambda: len(list_windows()) == 1)

        def count(label):
            output = run(['gdb','-q','-nx','-batch',f'/proc/{server.pid}/exe','-p',str(server.pid),
                          '-ex','set pagination off','-ex','tbreak g_main_context_prepare thread 1',
                          '-ex','continue','-ex',f'source {OUT}/count_sources.py','-ex','detach'],
                         env={**os.environ, 'DEBUGINFOD_URLS':''})
            (OUT/f'isolated-{label}.txt').write_text(output)
            line = next(l for l in output.splitlines() if l.startswith('QUEUE_CONNECTIONS'))
            return int(line.split()[1])

        before = count('before')
        # A control reproduces the old design, only on the disposable server.
        legacy = 'from terminal_manager.tabs import _scan_tab_groups_native; from terminal_manager.x11 import list_windows; _scan_tab_groups_native(list_windows())'
        for _ in range(3):
            run([sys.executable,'-c',legacy])
        old_after = count('old-three-clients')
        assert old_after - before == 3, (before, old_after)
        groups = wait_for(lambda: scan_tab_groups(list_windows()))
        assert len(groups) == 1 and len(groups[0].tabs) == 2
        pid = worker.process.pid
        warmed = count('persistent-warm')
        for n in range(100):
            groups = scan_tab_groups(list_windows())
            assert groups and len(groups[0].tabs) == 2, (n, worker.error)
            target = n % 2
            assert select_tab(groups[0], target)
            assert select_tab(groups[0], target)
            time.sleep(.02)
            assert scan_tab_groups(list_windows())[0].selected.index == target
            assert worker.process.pid == pid
        after = count('persistent-100-rounds')
        assert after == warmed, (warmed, after)
        if os.environ.get('TM_TEST_STALE_CLEANUP') == '1':
            output = run(['gdb','-q','-nx','-batch',f'/proc/{server.pid}/exe','-p',str(server.pid),
                          '-ex','set pagination off','-ex','tbreak g_main_context_prepare thread 1',
                          '-ex','continue','-ex','set $tm_apply = 1',
                          '-ex',f'source {OUT}/detach_stale_sources.py',
                          '-ex',f'source {OUT}/cleanup_stale_connections.py','-ex','detach'])
            (OUT/'isolated-cleanup.txt').write_text(output)
            assert 'OWNER_REMOVED 3' in output, output
            assert count('after-cleanup') == warmed - 3
            assert "ACTIVE_CONNECTION_STATES {'connected': 2}" in (OUT/'isolated-after-cleanup.txt').read_text()
            # All original windows, shells and the live accessibility client
            # continue functioning after detaching only the stale GSources.
            for n in range(20):
                groups = scan_tab_groups(list_windows())
                assert len(groups) == 1 and len(groups[0].tabs) == 2
                assert select_tab(groups[0], n % 2)
                assert worker.process.pid == pid
            assert count('after-cleanup-and-rescan') == warmed - 3
        # Topology changes must be visible without recreating the worker.
        run(['xdotool','windowactivate','--sync',groups[0].window_id,'key','ctrl+shift+t'])
        wait_for(lambda: any(len(g.tabs) == 3 for g in scan_tab_groups(list_windows()) or []))
        assert worker.process.pid == pid
        worker.close()
        closed = count('persistent-closed')
        result = dict(control_before=before, old_after_three_scans=old_after,
                      persistent_warm=warmed, persistent_after_100=after,
                      persistent_after_close=closed, same_worker_pid=pid,
                      repeated_selection=True, new_tab_detected=True)
        result['owner_cleanup_tested'] = os.environ.get('TM_TEST_STALE_CLEANUP') == '1'
        (OUT/'isolated-result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
    finally:
        worker.close()
        if server:
            server.terminate(); server.wait(timeout=5)
        wm.terminate(); wm.wait(timeout=5)
        wm_log.close()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    runtime=OUT/'runtime'; runtime.mkdir(mode=0o700,exist_ok=True)
    services=OUT/'dbus-services'; services.mkdir(exist_ok=True)
    shutil.copyfile('/usr/share/dbus-1/services/org.a11y.Bus.service', services/'org.a11y.Bus.service')
    config=OUT/'isolated-bus.conf'
    config.write_text(f'<busconfig><type>session</type><listen>unix:tmpdir={runtime}</listen><servicedir>{services}</servicedir><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
    read_fd, write_fd=os.pipe()
    xvfb=subprocess.Popen([str(TOOLS/'bin/Xvfb'),'-displayfd',str(write_fd),'-screen','0','1200x800x24','-nolisten','tcp'],pass_fds=(write_fd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    os.close(write_fd)
    try:
        assert select.select([read_fd],[],[],10)[0]
        display=':'+os.read(read_fd,100).decode().strip()
        env={**os.environ,'DISPLAY':display,'PYTHONPATH':str(ROOT),'XDG_RUNTIME_DIR':str(runtime),
             'LD_LIBRARY_PATH':str(TOOLS/'lib/x86_64-linux-gnu'),'GTK_USE_PORTAL':'0',
             'XDG_DATA_DIRS':f'{TOOLS / "share"}:/usr/local/share:/usr/share',
             'GIO_USE_VFS':'local','GSETTINGS_BACKEND':'memory','XDG_CURRENT_DESKTOP':'Openbox'}
        for key in ('GNOME_TERMINAL_SERVICE','GNOME_TERMINAL_SCREEN','AT_SPI_BUS_ADDRESS'):
            env.pop(key,None)
        subprocess.run(['dbus-run-session','--config-file',str(config),'--',sys.executable,str(Path(__file__).resolve()),'--desktop'],env=env,check=True,timeout=180)
    finally:
        os.close(read_fd)
        xvfb.terminate(); xvfb.wait(timeout=5)


if __name__ == '__main__':
    desktop() if '--desktop' in sys.argv else main()
