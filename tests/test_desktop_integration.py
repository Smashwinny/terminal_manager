from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_desktop_entry_matches_tk_window_class() -> None:
    desktop = (ROOT / "packaging" / "terminal-manager.desktop").read_text(encoding="utf-8")
    app = (ROOT / "terminal_manager" / "app.py").read_text(encoding="utf-8")

    assert "StartupWMClass=Terminalmanager" in desktop
    assert 'tk.Tk(className="TerminalManager")' in app


def test_dock_icon_sizes_are_packaged_and_installed() -> None:
    icon_64 = ROOT / "terminal_manager" / "assets" / "terminal-manager-64.png"
    icon_512 = ROOT / "terminal_manager" / "assets" / "terminal-manager.png"
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert icon_64.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert icon_512.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "hicolor/64x64/apps" in installer
    assert "hicolor/512x512/apps" in installer
