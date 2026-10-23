from dataclasses import asdict
from unittest.mock import Mock, patch

import pytest

from terminal_manager import protected
from terminal_manager.store import save_runtime_session, load_runtime_session, recovery_candidates, state_dir, load_shells, save_shell
from terminal_manager.model import ShellInfo
from terminal_manager.x11 import X11Error, focus_window


def entry(i):
    return {"shell_id": str(i), "name": str(i), "cwd": "/work", "window_id": f"0x{i:08x}"}


def test_empty_then_new_inventory_and_clean_exit_preserve_crash_history(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    before = [entry(i) for i in range(36)]
    save_runtime_session(clean_shutdown=False, entries=before)
    save_runtime_session(clean_shutdown=False, entries=[])
    save_runtime_session(clean_shutdown=False, entries=[entry(100)])
    save_runtime_session(clean_shutdown=True, entries=[])
    assert load_runtime_session()["entries"] == [entry(100)]
    assert {e["shell_id"] for e in recovery_candidates()} == {str(i) for i in range(36)} | {"100"}
    archive = next((state_dir().parent / "session-history").glob("incident-*.json"))
    assert archive.stat().st_mode & 0o777 == 0o600


def test_x11_failed_activation_does_not_raise_move_or_highlight():
    with patch("terminal_manager.x11.require_x11"), patch("terminal_manager.x11.window_exists", return_value=True), patch("terminal_manager.x11.subprocess.run", return_value=Mock(returncode=1)) as run, patch("terminal_manager.x11.shake_window") as shake, pytest.raises(X11Error):
        focus_window("0x1")
    assert run.call_count == 1
    shake.assert_not_called()


def test_reconnect_dead_task_never_starts_new_process():
    with patch("terminal_manager.protected.inspect_task", side_effect=protected.ProtectionError("任务已结束")), patch("terminal_manager.protected.run") as run, pytest.raises(protected.ProtectionError):
        protected.open_task("a" * 32)
    run.assert_not_called()


def test_task_paths_reject_traversal():
    with pytest.raises(protected.ProtectionError):
        protected.task_path("../victim")


def test_legacy_shell_records_still_load(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    shell = ShellInfo("one", "0x1", 0, "", "old", "unbound", "", "", "/work", None, "", 0, 0)
    save_shell(shell)
    assert load_shells()[0].protected_id == ""


def test_restore_rejects_previous_boot(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    from terminal_manager.store import _atomic_private_json
    _atomic_private_json(protected.task_path("a" * 32), {"boot_id": "old-boot"})
    with pytest.raises(protected.ProtectionError, match="上一次系统启动"):
        protected.load_task("a" * 32)


def test_reused_xid_does_not_bind_old_protected_record(tmp_path, monkeypatch):
    from terminal_manager.app import TerminalManagerApp
    from terminal_manager.model import WindowInfo
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    old = ShellInfo("old", "0x1", 0, "", "old", "unbound", "", "", "/work", None, "", 0, 0, "a" * 32)
    new = ShellInfo("new", "", 0, "", "new", "unbound", "", "", "/work", None, "", 0, 0, "b" * 32)
    save_shell(old)
    save_shell(new)
    app = object.__new__(TerminalManagerApp)
    app._window_roles = {}
    app.protected_states = {}
    windows = [WindowInfo("0x1", 0, 123, 0, 0, 800, 600, "gnome-terminal", "", "task")]
    with patch("terminal_manager.app.window_role", return_value=f"terminal-manager-{'b' * 32}-view"):
        app._sync_protected_windows(windows)
    records = {shell.shell_id: shell for shell in load_shells()}
    assert records["old"].window_id == ""
    assert records["new"].window_id == "0x1"


def test_recovery_role_ignores_unrelated_concurrent_window(tmp_path, monkeypatch):
    from terminal_manager.app import TerminalManagerApp
    from terminal_manager.model import WindowInfo
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    app = object.__new__(TerminalManagerApp)
    app.root = Mock()
    app.refresh = Mock()
    app._recovery_entries = [entry(1)]
    app._recovery_index = app._recovery_restored_count = app._recovery_poll_count = 0
    app._recovery_before_ids = set()
    app._recovery_token = "unique-token"
    windows = [WindowInfo(wid, 0, 123, 0, 0, 800, 600, "gnome-terminal", "", "task") for wid in ("0x2", "0x3")]
    with patch("terminal_manager.app.list_windows", return_value=windows), patch("terminal_manager.app.window_role", side_effect=lambda wid: "unique-token" if wid == "0x3" else "unrelated"):
        app._poll_recovered_window()
    assert load_shells()[0].window_id == "0x3"
