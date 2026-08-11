from pathlib import Path

from terminal_manager.app import display_directory


def test_home_directory_is_compacted() -> None:
    home = str(Path.home())
    assert display_directory(home) == "~"
    assert display_directory(home + "/projects/demo") == "~/projects/demo"


def test_unknown_and_external_directories() -> None:
    assert display_directory("") == "待识别"
    assert display_directory("/tmp/demo") == "/tmp/demo"
