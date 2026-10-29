"""Isolated Xvfb test of automatic Codex resume routing, using a recording stub.

Run on a private X/DBus display with XDG_STATE_HOME under project tmp/.
The stub records argv and stays idle; it sends no prompts or API requests.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terminal_manager.store import save_runtime_session, save_shell, load_shells
from terminal_manager.model import ShellInfo


def main():
    import tkinter as tk
    from terminal_manager.app import TerminalManagerApp
    assert str(ROOT / "tmp") in os.environ.get("XDG_STATE_HOME", "")
    out = ROOT / 'tmp/codex-recovery-smoke'
    out.mkdir(exist_ok=True)
    home = out / 'codex-home'
    home.mkdir(exist_ok=True)
    os.environ['CODEX_HOME'] = str(home)
    sid = '11111111-2222-4333-8444-555555555555'
    with sqlite3.connect(home / 'state_5.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS threads(id,cwd,title,source,updated_at,rollout_path,archived)')
        db.execute('DELETE FROM threads')
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?)', (sid,str(out),'Isolated recovery','cli',1,'',0))
    fake = out / 'codex'
    receipt = out / 'argv.json'
    receipt.unlink(missing_ok=True)
    fake.write_text('#!/usr/bin/python3\nimport os,json,sys,time\nfrom pathlib import Path\nif "--version" in sys.argv: print("isolated stub"); sys.exit(0)\n'+f'Path({str(receipt)!r}).write_text(json.dumps({{"argv":sys.argv[1:],"cwd":os.getcwd(),"home":os.environ.get("CODEX_HOME"),"pid":os.getpid()}}))\n'+'print("Isolated resume recording stub",flush=True)\ntime.sleep(45)\n')
    fake.chmod(0o700)
    os.environ['PATH'] = str(out) + os.pathsep + os.environ['PATH']
    entries = [{'shell_id':'codex-smoke','window_id':'0x00000001','name':'恢复测试','cwd':str(out),'codex_session_id':sid,'codex_cwd':str(out),'codex_home':str(home)}]
    save_shell(ShellInfo('codex-smoke','0x00000001',999999,'/dev/pts/9999','恢复测试','ended','','',str(out),None,'',0,0))
    save_runtime_session(clean_shutdown=False,entries=entries)
    from terminal_manager import state_db
    state_db.mark(entries[0], 'pending')
    tools = ROOT/'tmp/protection-tools/extracted/usr'
    os.environ['XDG_DATA_DIRS'] = str(tools/'share')+':/usr/local/share:/usr/share'
    wm_log = (out/'openbox.log').open('w')
    wm = subprocess.Popen([str(tools/'bin/openbox'),'--sm-disable','--config-file',str(tools.parent/'etc/xdg/openbox/rc.xml')], stdout=wm_log,stderr=wm_log)
    for _ in range(40):
        if subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0: break
        time.sleep(.1)
    else:
        raise RuntimeError('test window manager failed: '+(out/'openbox.log').read_text())
    server = subprocess.Popen(['/usr/libexec/gnome-terminal-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    root = None
    app = None
    try:
        time.sleep(.6)
        root = tk.Tk(className='TerminalManagerCodexSmoke')
        app = TerminalManagerApp(root)
        app.recovery_queue.timeout = 2
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            root.update()
            saved=load_shells()[0]
            if receipt.exists() and saved.window_id!='0x00000001' and not app._recovery_active:
                break
            time.sleep(.05)
        else:
            from terminal_manager.x11 import list_windows, window_role
            print('recovery token',app._recovery_token,flush=True)
            print('wmctrl',subprocess.run(['wmctrl','-lpx'],capture_output=True,text=True).stdout,flush=True)
            print('windows',[(w.window_id,window_role(w.window_id)) for w in list_windows()],flush=True)
            raise AssertionError('automatic recovery timed out')
        observed=json.loads(receipt.read_text())
        assert observed['argv']==['resume',sid,'-C',str(out)],observed
        assert observed['home']==str(home)
        assert saved.codex_session_id==sid
        assert saved.tty=='' and saved.shell_pid==0
        # The stub cannot prove a real conversation loaded: never call it ready.
        assert state_db.records()[0]['_state']=='awaiting'
        root.update()
        subprocess.run(['xwd','-silent','-id',str(root.winfo_id()),'-out',str(out/'manager.xwd')],check=True,timeout=5)
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(out/'manager.xwd'),str(out/'manager.png')],check=True,timeout=5)
        result={'automatic_resume':True,'exact_argv':observed['argv'],'window_rebound':saved.window_id,'stale_tty_cleared':True,'stub_only':True}
        (out/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
    finally:
        if app: app._close()
        elif root: root.destroy()
        server.terminate();server.wait(timeout=5)
        wm.terminate();wm.wait(timeout=5)
        wm_log.close()


if __name__=='__main__': main()
