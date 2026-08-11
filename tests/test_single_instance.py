from pathlib import Path
from unittest.mock import patch

from terminal_manager.single_instance import SingleInstance, activate_existing


def test_only_one_instance_can_hold_lock(tmp_path: Path) -> None:
    path = tmp_path / "manager.lock"
    first = SingleInstance(path)
    second = SingleInstance(path)

    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_second_launch_raises_existing_window() -> None:
    with patch("terminal_manager.single_instance.subprocess.run") as run:
        activate_existing()

    assert run.call_args.args[0] == ["wmctrl", "-a", "Terminal Manager"]
