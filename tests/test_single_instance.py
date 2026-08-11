from pathlib import Path
from unittest.mock import patch

from terminal_manager.single_instance import (
    DETACHED_CHILD_ENV,
    SingleInstance,
    activate_existing,
    launch_detached,
)


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


def test_detached_launch_does_not_inherit_terminal(tmp_path: Path) -> None:
    with (
        patch.dict("terminal_manager.single_instance.os.environ", {"XDG_STATE_HOME": str(tmp_path)}),
        patch("terminal_manager.single_instance.subprocess.Popen") as popen,
    ):
        launch_detached()

    options = popen.call_args.kwargs
    assert options["stdin"] is not None
    assert options["start_new_session"] is True
    assert options["close_fds"] is True
    assert options["cwd"] == "/"
    assert options["env"][DETACHED_CHILD_ENV] == "1"
