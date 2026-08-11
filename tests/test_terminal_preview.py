from unittest.mock import patch

from terminal_manager.terminal_preview import HIGHLIGHT_SEQUENCE, RESET_SEQUENCE, set_tty_preview


@patch("terminal_manager.terminal_preview.os.access", return_value=True)
@patch("terminal_manager.terminal_preview.os.path.exists", return_value=True)
@patch("terminal_manager.terminal_preview.os.close")
@patch("terminal_manager.terminal_preview.os.write")
@patch("terminal_manager.terminal_preview.os.open", return_value=42)
def test_preview_writes_display_only_sequences(open_fd, write, _close, _exists, _access) -> None:
    assert set_tty_preview("/dev/pts/7", True)
    write.assert_called_once_with(42, HIGHLIGHT_SEQUENCE)
    open_fd.assert_called_once()


@patch("terminal_manager.terminal_preview.os.access", return_value=True)
@patch("terminal_manager.terminal_preview.os.path.exists", return_value=True)
@patch("terminal_manager.terminal_preview.os.close")
@patch("terminal_manager.terminal_preview.os.write")
@patch("terminal_manager.terminal_preview.os.open", return_value=42)
def test_preview_reset_restores_profile_colors(_open_fd, write, _close, _exists, _access) -> None:
    assert set_tty_preview("/dev/pts/7", False)
    write.assert_called_once_with(42, RESET_SEQUENCE)


def test_preview_rejects_non_tty_paths() -> None:
    assert not set_tty_preview("/tmp/not-a-tty", True)

