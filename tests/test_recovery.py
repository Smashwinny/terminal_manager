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


def test_existing_registered_window_is_not_launched_twice() -> None:
    app = object.__new__(TerminalManagerApp)
    app.root = Root()
    app._recovery_entries = [{"shell_id": "abc", "name": "项目", "cwd": "/work", "window_id": "0x00000001"}]
    app._recovery_index = 0
    app._recovery_errors = []
    app._recovery_skipped_count = 0
    app.windows = [window("0x00000001")]

    with patch("terminal_manager.app.launch_recovery_terminal") as launch:
        app._restore_next_window()

    launch.assert_not_called()
    assert app._recovery_index == 1
    assert app._recovery_skipped_count == 1
    assert len(app.root.callbacks) == 1


def test_detected_recovery_window_rebinds_original_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    shell = ShellInfo(
        "abc", "0x00000001", 0, "", "项目", "unbound", "", "", str(tmp_path),
        None, "", 1.0, 1.0,
    )
    save_shell(shell)
    app = object.__new__(TerminalManagerApp)
    app.root = Root()
    app._recovery_entries = [{"shell_id": "abc", "name": "项目", "cwd": str(tmp_path), "window_id": "0x00000001"}]
    app._recovery_index = 0
    app._recovery_before_ids = {"0x00000001"}
    app._recovery_poll_count = 0
    app._recovery_restored_count = 0
    app.refresh = lambda: None

    with patch("terminal_manager.app.list_windows", return_value=[window("0x00000002")]):
        app._poll_recovered_window()

    restored = load_shells()[0]
    assert restored.window_id == "0x00000002"
    assert restored.name == "项目"
    assert restored.cwd == str(tmp_path)
    assert app._recovery_index == 1
    assert app._recovery_restored_count == 1


def test_missing_record_is_rebuilt_from_recovery_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    app = object.__new__(TerminalManagerApp)
    app.root = Root()
    app._recovery_entries = [{
        "shell_id": "rebuilt",
        "name": "重建项目",
        "cwd": str(tmp_path),
        "window_id": "0x00000001",
    }]
    app._recovery_index = 0
    app._recovery_before_ids = {"0x00000001"}
    app._recovery_poll_count = 0
    app._recovery_restored_count = 0
    app.refresh = lambda: None

    with patch("terminal_manager.app.list_windows", return_value=[window("0x00000003")]):
        app._poll_recovered_window()

    rebuilt = load_shells()[0]
    assert rebuilt.shell_id == "rebuilt"
    assert rebuilt.window_id == "0x00000003"
    assert rebuilt.name == "重建项目"
    assert rebuilt.cwd == str(tmp_path)
