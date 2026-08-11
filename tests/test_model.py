from terminal_manager.model import WindowInfo, normalize_window_id


def test_normalize_window_id() -> None:
    assert normalize_window_id("0x3a00007") == "0x03a00007"
    assert normalize_window_id(123) == "0x0000007b"


def test_terminal_detection_uses_wm_class() -> None:
    terminal = WindowInfo("0x1", 0, 1, 0, 0, 100, 100, "gnome-terminal-server.Gnome-terminal", "host", "项目")
    manager = WindowInfo("0x2", 0, 1, 0, 0, 100, 100, "tk.Tk", "host", "Terminal Manager")
    assert terminal.is_terminal
    assert not manager.is_terminal

