from terminal_manager.app import item_id_for_window
from terminal_manager.model import ShellInfo, WindowInfo


def test_find_visible_item_for_active_window() -> None:
    window = WindowInfo("0x0000002a", 0, 10, 0, 0, 800, 600, "XTerm.XTerm", "host", "work")
    items = {"window:42": (None, window)}
    assert item_id_for_window(items, "0x0000002a") == "window:42"
    assert item_id_for_window(items, "0x00000099") is None


def test_registered_item_uses_saved_window_when_window_metadata_is_missing() -> None:
    shell = ShellInfo("abc", "0x0000002a", 12, "/dev/pts/1", "work", "idle", "", "bash", "/tmp", 12, "S", 0, 0)
    assert item_id_for_window({"shell:abc": (shell, None)}, "0x0000002a") == "shell:abc"

