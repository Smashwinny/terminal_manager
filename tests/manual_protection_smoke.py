"""Opt-in desktop fault injection, confined to its own Xvfb and D-Bus session.

Run with XDG_STATE_HOME inside project tmp/ and a working systemd user bus.
No production terminal PID or window is selected or signalled.
"""
import json
import os
from pathlib import Path
import select
import shlex
import signal
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal_manager import protected

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tmp/protection-tools/extracted/usr"
OUT = ROOT / "tmp/protection-smoke"


def wait_for(predicate, timeout=10):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("timed out waiting for isolated test condition")


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=15, **kwargs).stdout


def counter():
    target = Path(sys.argv[2])
    print("\033]0;⠋ protected-smoke\007", flush=True)
    with target.open("a") as stream:
        for number in range(10000):
            stream.write(f"{os.getpid()} {number}\n")
            stream.flush()
            print(number, flush=True)
            time.sleep(0.15)


def isolated_desktop(task_id):
    from terminal_manager.x11 import focus_window, set_window_above, window_is_above, list_windows, window_role
    from terminal_manager.highlight import set_tty_highlight
    task = protected.inspect_task(task_id)
    counter_file = OUT / f"{task_id}-counter.txt"
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), "--counter", str(counter_file)])
    protected.tmux(task, "send-keys", "-t", "task", "-l", command)
    protected.tmux(task, "send-keys", "-t", "task", "Enter")
    try:
        wait_for(lambda: counter_file.exists() and len(counter_file.read_text().splitlines()) >= 3)
    except AssertionError:
        print(protected.tmux(task, "capture-pane", "-p", "-t", "task").stdout, flush=True)
        raise
    wm_log = (OUT / "openbox.log").open("w")
    wm = subprocess.Popen([str(TOOLS / "bin/openbox"), "--sm-disable", "--config-file", str(TOOLS.parent / "etc/xdg/openbox/rc.xml")], stdout=wm_log, stderr=wm_log)
    server = None
    clients = []
    try:
        wait_for(lambda: subprocess.run(["wmctrl", "-m"], capture_output=True).returncode == 0)
        server = subprocess.Popen(["/usr/libexec/gnome-terminal-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.6)
        protected.open_task(task_id)
        window = wait_for(lambda: next((w for w in list_windows() if window_role(w.window_id).startswith(f"terminal-manager-{task_id}-")), None))
        wait_for(lambda: protected.inspect_task(task_id)["client_ttys"])
        before = protected.inspect_task(task_id)
        assert before["cwd"] == str(OUT)
        assert "protected-smoke" in before["title"]
        focus_window(window.window_id)
        assert set_window_above(window.window_id, True)
        wait_for(lambda: window_is_above(window.window_id))
        assert set_window_above(window.window_id, False)
        assert set_tty_highlight(before["client_ttys"][0], True)
        time.sleep(0.15)
        run(["xwd", "-silent", "-id", window.window_id, "-out", str(OUT / "purple.xwd")])
        run(["ffmpeg", "-y", "-v", "error", "-i", str(OUT / "purple.xwd"), str(OUT / "purple.png")])
        assert set_tty_highlight(before["client_ttys"][0], False)
        last_before = int(counter_file.read_text().splitlines()[-1].split()[1])
        counter_pid = int(counter_file.read_text().splitlines()[-1].split()[0])
        assert task["unit"] in Path(f"/proc/{counter_pid}/cgroup").read_text()
        assert task["unit"] not in Path(f"/proc/{server.pid}/cgroup").read_text()
        old_server = server.pid
        # Only the subprocess created above, on this private X/DBus session.
        server.kill()
        server.wait(timeout=5)
        wait_for(lambda: not protected.inspect_task(task_id)["client_ttys"])
        wait_for(lambda: int(counter_file.read_text().splitlines()[-1].split()[1]) > last_before + 5)
        after = protected.inspect_task(task_id)
        assert before["server_pid"] == after["server_pid"]
        assert before["pane_pid"] == after["pane_pid"]
        server = subprocess.Popen(["/usr/libexec/gnome-terminal-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.6)
        protected.open_task(task_id)
        wait_for(lambda: protected.inspect_task(task_id)["client_ttys"])
        reconnected = protected.inspect_task(task_id)
        samples = [tuple(map(int, line.split())) for line in counter_file.read_text().splitlines()]
        assert len({pid for pid, count in samples}) == 1
        assert [count for pid, count in samples] == list(range(len(samples)))
        assert before["pane_pid"] == reconnected["pane_pid"]
        import tkinter as tk
        from terminal_manager.app import TerminalManagerApp
        from terminal_manager.store import load_shells
        root = tk.Tk(className="TerminalManagerProtectionTest")
        print("GUI: creating manager", flush=True)
        app = TerminalManagerApp(root)
        print("GUI: waiting for role binding", flush=True)
        def ready():
            root.update()
            app.refresh()
            return any(shell and shell.protected_id == task_id and window for shell, window in app.items.values()) and bool(app.protected_states.get(task_id, {}).get("views"))
        try:
            wait_for(ready)
            print("GUI: bound; exercising focus", flush=True)
            iid = next(iid for iid, (shell, window) in app.items.items() if shell and shell.protected_id == task_id)
            app.tree.selection_set(iid)
            app.focus_selected(pin=True)
            root.update()
            assert app.window_highlighter.tty == protected.inspect_task(task_id)["client_ttys"][0]
            for _ in range(10):
                for geometry in ("215x130", "1180x720"):
                    root.geometry(geometry)
                    # Exercise the actual debounced Configure handler; calling
                    # its private callback directly leaves a pending Tk timer.
                    settled = time.monotonic() + 0.25
                    while time.monotonic() < settled:
                        root.update()
                        time.sleep(0.02)
            run(["xwd", "-silent", "-id", str(root.winfo_id()), "-out", str(OUT / "manager.xwd")])
            run(["ffmpeg", "-y", "-v", "error", "-i", str(OUT / "manager.xwd"), str(OUT / "manager.png")])
            bound = next(shell for shell in load_shells() if shell.protected_id == task_id)
            assert bound.cwd == str(OUT)
        finally:
            app._close()
        assert protected.inspect_task(task_id)["pane_pid"] == before["pane_pid"]
        from terminal_manager.tabs import scan_tab_groups, select_tab
        run(["gnome-terminal", "--window", "--role=tm-tabs-smoke", "--title=tab-one", "--tab", "--title=tab-two"])
        group = wait_for(lambda: next((g for g in scan_tab_groups(list_windows()) if len(g.tabs) == 2), None))
        target = 1 - group.selected.index
        assert select_tab(group, target)
        assert select_tab(group, target)
        wait_for(lambda: any(g.window_id == group.window_id and g.selected.index == target for g in scan_tab_groups(list_windows())))
        result = {"task": task_id, "killed_test_terminal_server": old_server, "tmux_server": after["server_pid"], "pane_pid_unchanged": before["pane_pid"], "counter_pid_unchanged": counter_pid, "continuous_samples": len(samples), "cgroup_independent": True, "reconnect": True, "focus_shake_pin": True, "title_directory": True, "purple_capture": str(OUT / "purple.png")}
        result["manager_rebind_highlight_and_close"] = True
        result["native_tab_scan_and_repeat_switch"] = True
        result["resize_cycles"] = 10
        (OUT / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        if server and server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
        wm.terminate()
        wm.wait(timeout=5)
        wm_log.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert str(ROOT / "tmp") in os.environ.get("XDG_STATE_HOME", ""), "must use isolated state"
    task_id = protected.create_task(str(OUT), "fault-injection-only")
    runtime = OUT / "runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    bus_config = OUT / "isolated-bus.conf"
    services = OUT / "dbus-services"
    services.mkdir(exist_ok=True)
    shutil.copyfile("/usr/share/dbus-1/services/org.a11y.Bus.service", services / "org.a11y.Bus.service")
    # Exclude desktop portal/keyring activation in this disposable session.
    bus_config.write_text(f'<busconfig><type>session</type><listen>unix:tmpdir={runtime}</listen><servicedir>{services}</servicedir><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
    read_fd, write_fd = os.pipe()
    xvfb = subprocess.Popen([str(TOOLS / "bin/Xvfb"), "-displayfd", str(write_fd), "-screen", "0", "1200x800x24", "-nolisten", "tcp"], pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(write_fd)
    try:
        assert select.select([read_fd], [], [], 10)[0]
        display = ":" + os.read(read_fd, 100).decode().strip()
        env = {**os.environ, "DISPLAY": display, "LD_LIBRARY_PATH": str(TOOLS / "lib/x86_64-linux-gnu"), "PYTHONPATH": str(ROOT), "XDG_DATA_DIRS": f"{TOOLS / 'share'}:/usr/local/share:/usr/share", "XDG_RUNTIME_DIR": str(runtime), "GTK_USE_PORTAL": "0", "GIO_USE_VFS": "local", "GSETTINGS_BACKEND": "memory", "XDG_CURRENT_DESKTOP": "Openbox"}
        for key in ("GNOME_TERMINAL_SERVICE", "GNOME_TERMINAL_SCREEN"):
            env.pop(key, None)
        child = subprocess.run(["dbus-run-session", "--config-file", str(bus_config), "--", sys.executable, str(Path(__file__).resolve()), "--desktop", task_id], env=env, timeout=60)
        assert child.returncode == 0, f"isolated desktop exit: {child.returncode}"
    finally:
        os.close(read_fd)
        protected.end_task(task_id)
        xvfb.terminate()
        xvfb.wait(timeout=5)
    try:
        protected.inspect_task(task_id)
        raise AssertionError("ended task still attachable")
    except protected.ProtectionError:
        pass
    print("explicit end verified; test task service stopped")


if __name__ == "__main__":
    if "--counter" in sys.argv:
        counter()
    elif "--desktop" in sys.argv:
        isolated_desktop(sys.argv[2])
    else:
        main()
