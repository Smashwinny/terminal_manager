"""Forty real terminals on a private X/DBus desktop, never the user's desktop."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tmp/protection-tools/extracted/usr'
OUT = ROOT / 'tmp/reliability-20261029/gui'
sys.path.insert(0, str(ROOT))


def desktop():
    import tkinter as tk
    from terminal_manager import state_db
    from terminal_manager.app import TerminalManagerApp
    from terminal_manager.x11 import list_windows
    wm = subprocess.Popen([str(TOOLS/'bin/openbox'), '--sm-disable', '--config-file', str(TOOLS.parent/'etc/xdg/openbox/rc.xml')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    server = None
    app = None
    try:
        until = time.monotonic()+8
        while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
            assert time.monotonic()<until
            time.sleep(.1)
        server = subprocess.Popen(['/usr/libexec/gnome-terminal-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(.5)
        for n in range(40):
            state_db.mark({'shell_id':f'load-{n}','name':f'Load {n:02}','cwd':str(OUT),'window_id':''}, 'pending')
        root = tk.Tk(className='TerminalManagerLoadTest')
        app = TerminalManagerApp(root)
        delay = []
        last = time.monotonic()
        heartbeat_job = None
        def heartbeat():
            nonlocal last, heartbeat_job
            now=time.monotonic();delay.append(now-last);last=now
            heartbeat_job = root.after(20,heartbeat)
        heartbeat_job = root.after(20,heartbeat)
        until = time.monotonic()+120
        while time.monotonic()<until:
            root.update()
            if len(list_windows())==40 and not app.recovery_queue.active and all(r['_state'] in ('ready','observed') for r in state_db.records()):
                break
            time.sleep(.01)
        else:
            raise AssertionError([(r['shell_id'],r['_state'],r['_error']) for r in state_db.records()])
        count_before = len(list_windows())
        memory = []
        until = time.monotonic()+float(os.environ.get('TM_SOAK_SECONDS','180'))
        next_sample = 0
        while time.monotonic()<until:
            root.update()
            if time.monotonic()>=next_sample:
                row={'t':time.monotonic()}
                for name,pid in [('manager',os.getpid()),('terminal',server.pid)]:
                    fields=dict(l.split(':',1) for l in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in l)
                    row[name+'_rss_kib']=int(fields['VmRSS'].split()[0])
                memory.append(row);next_sample=time.monotonic()+10
            time.sleep(.01)
        assert len(list_windows()) == count_before == 40
        root.attributes('-topmost', True)
        root.lift()
        root.update()
        time.sleep(.2)
        subprocess.run(['xwd','-silent','-id',str(root.winfo_id()),'-out',str(OUT/'manager.xwd')],check=True)
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(OUT/'manager.xwd'),str(OUT/'manager.png')],check=True)
        root.after_cancel(heartbeat_job)
        app._close();app=None
        root2 = tk.Tk(className='TerminalManagerRestartTest')
        app = TerminalManagerApp(root2)
        until=time.monotonic()+3
        while time.monotonic()<until:
            root2.update();time.sleep(.02)
        assert len(list_windows())==40 and not app.recovery_queue.active
        result={'real_terminals':40,'restart_duplicates':0,'max_ui_heartbeat_seconds':max(delay),'memory_samples':memory}
        (OUT/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
    finally:
        if app:app._close()
        if server:server.terminate();server.wait(timeout=5)
        wm.terminate();wm.wait(timeout=5)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    runtime=OUT/'runtime';runtime.mkdir(mode=0o700,exist_ok=True)
    config=ROOT/'tmp/protection-smoke/isolated-bus.conf'
    r,w=os.pipe()
    xvfb=subprocess.Popen([str(TOOLS/'bin/Xvfb'),'-displayfd',str(w),'-screen','0','1400x1000x24','-nolisten','tcp'],pass_fds=(w,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    os.close(w)
    try:
        assert select.select([r],[],[],10)[0]
        display=':'+os.read(r,100).decode().strip()
        mode='codex' if '--codex' in sys.argv else 'load'
        state=OUT/f'state-{mode}-{time.time_ns()}'
        env={**os.environ,'DISPLAY':display,'PYTHONPATH':str(ROOT),'XDG_STATE_HOME':str(state),'XDG_RUNTIME_DIR':str(runtime),'XDG_DATA_DIRS':f'{TOOLS / "share"}:/usr/local/share:/usr/share','LD_LIBRARY_PATH':str(TOOLS/'lib/x86_64-linux-gnu'),'GTK_USE_PORTAL':'0','GIO_USE_VFS':'local','GSETTINGS_BACKEND':'memory','XDG_CURRENT_DESKTOP':'Openbox'}
        for key in ('GNOME_TERMINAL_SERVICE','GNOME_TERMINAL_SCREEN'):
            env.pop(key,None)
        script=ROOT/'tests/manual_codex_recovery_smoke.py' if mode=='codex' else Path(__file__).resolve()
        result=subprocess.run(['dbus-run-session','--config-file',str(config),'--',sys.executable,str(script),'--desktop'],env=env,timeout=600)
        assert result.returncode==0
    finally:
        os.close(r);xvfb.terminate();xvfb.wait(timeout=5)


if __name__=='__main__':
    desktop() if '--desktop' in sys.argv else main()
