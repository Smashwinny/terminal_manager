from terminal_manager.store import load_tty_bindings, save_tty_binding, tty_bindings_path
from terminal_manager.tty_probe import _tty_number


def test_tty_bindings_are_saved_per_window_and_tab(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    save_tty_binding("0x00000001", "tab:0", "/dev/pts/2")
    save_tty_binding("0x00000001", "tab:1", "/dev/pts/7")
    save_tty_binding("0x00000002", "main", "/dev/pts/4")

    assert load_tty_bindings() == {
        "0x00000001": {"tab:0": "/dev/pts/2", "tab:1": "/dev/pts/7"},
        "0x00000002": {"main": "/dev/pts/4"},
    }


def test_ttys_sort_numerically() -> None:
    assert sorted(["/dev/pts/10", "/dev/pts/2"], key=_tty_number) == [
        "/dev/pts/2",
        "/dev/pts/10",
    ]


def test_legacy_unverified_bindings_are_ignored(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    path = tty_bindings_path()
    path.parent.mkdir(parents=True)
    path.write_text('{"0x00000001": {"main": "/dev/pts/8"}}', encoding="utf-8")

    assert load_tty_bindings() == {}
