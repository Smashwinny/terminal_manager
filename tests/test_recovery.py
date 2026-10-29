from unittest.mock import patch

from terminal_manager.app import TerminalManagerApp
from terminal_manager.model import ShellInfo
from terminal_manager.model import WindowInfo
from terminal_manager.recovery import recovery_command, validate_recovery_directory
from terminal_manager.store import (
    load_runtime_session,
    load_shells,
    runtime_session_path,
    save_runtime_session,
    save_shell,
    load_window_size,
    save_window_size,
    ui_state_path,
)


class Root:
    def __init__(self) -> None:
        self.callbacks = []

    def after(self, _delay, callback) -> None:
        self.callbacks.append(callback)


def window(window_id: str) -> WindowInfo:
    return WindowInfo(window_id, 0, 100, 0, 0, 800, 600, "gnome-terminal.Gnome-terminal", "host", "Shell")


def test_runtime_session_round_trip_is_private_and_atomic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    entries = [{
        "shell_id": "abc",
        "name": "项目窗口",
        "cwd": str(tmp_path),
        "window_id": "0x00000001",
    }]

    save_runtime_session(clean_shutdown=False, entries=entries)

    assert load_runtime_session() == {"clean_shutdown": False, "entries": entries}
    assert runtime_session_path().stat().st_mode & 0o777 == 0o600
    assert not runtime_session_path().with_suffix(".json.tmp").exists()


def test_clean_session_is_not_recoverable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    save_runtime_session(clean_shutdown=True, entries=[])
    assert load_runtime_session() == {"clean_shutdown": True, "entries": []}


def test_window_size_survives_restart_and_is_private(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    save_window_size(982, 646)
    assert load_window_size() == (982, 646)
    assert ui_state_path().stat().st_mode & 0o777 == 0o600


def test_recovery_directory_must_be_absolute_existing_and_accessible(tmp_path) -> None:
    directory, reason = validate_recovery_directory(str(tmp_path))
    assert directory == tmp_path
    assert reason == ""

    assert validate_recovery_directory("relative/path")[0] is None
    assert validate_recovery_directory(str(tmp_path / "missing"))[0] is None


def test_invalid_recovery_directory_never_launches(tmp_path) -> None:
    with patch("terminal_manager.recovery.subprocess.Popen") as popen:
        directory, _reason = validate_recovery_directory(str(tmp_path / "missing"))
    assert directory is None
    popen.assert_not_called()


def test_gnome_recovery_opens_a_new_window_in_saved_directory(tmp_path) -> None:
    with patch("terminal_manager.recovery.shutil.which", side_effect=lambda name: "/usr/bin/gnome-terminal" if name == "gnome-terminal" else None):
        assert recovery_command(tmp_path) == [
            "gnome-terminal",
            "--window",
            f"--working-directory={tmp_path}",
        ]


def test_existing_registered_window_is_not_launched_twice(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from terminal_manager import state_db
    from terminal_manager.recovery_queue import RecoveryQueue
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    entry = {'shell_id':'abc','name':'project','cwd':str(tmp_path),'window_id':'0x00000001','window_pid':100,'_boot':state_db.boot_id()}
    worker = RecoveryQueue(SimpleNamespace(reason=''))
    with patch('terminal_manager.recovery_queue.list_windows', return_value=[window('0x00000001')]), patch('terminal_manager.recovery_queue.launch_tracked') as launch:
        worker._one(entry)
    launch.assert_not_called()
    assert state_db.records()[0]['_state'] == 'ready'


def test_detected_recovery_window_rebinds_original_record(tmp_path, monkeypatch):
    from terminal_manager.recovery_queue import bind
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    save_shell(ShellInfo('abc','0x00000001',999,'/dev/pts/999','project','unbound','','',str(tmp_path),None,'',1,1))
    entry = {'shell_id':'abc','name':'project','cwd':str(tmp_path),'window_id':'0x00000001'}
    bind(entry, window('0x00000002'))
    restored = load_shells()[0]
    assert restored.window_id == '0x00000002' and restored.name == 'project'
    assert restored.shell_pid == 0 and restored.tty == ''


def test_missing_record_is_rebuilt_from_recovery_snapshot(tmp_path, monkeypatch):
    from terminal_manager.recovery_queue import bind
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    entry = {'shell_id':'rebuilt','name':'project','cwd':str(tmp_path),'window_id':'0x00000001'}
    bind(entry, window('0x00000003'))
    rebuilt = load_shells()[0]
    assert rebuilt.shell_id == 'rebuilt' and rebuilt.window_id == '0x00000003'
    assert rebuilt.cwd == str(tmp_path)
