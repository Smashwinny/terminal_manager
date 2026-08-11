import os

from terminal_manager.monitor import proc_cmdline, proc_cwd, proc_stat, process_exists


def test_current_process_can_be_inspected() -> None:
    pid = os.getpid()
    command, state = proc_stat(pid)
    assert process_exists(pid)
    assert command
    assert state in "RSDTtZXI"
    assert proc_cmdline(pid)
    assert proc_cwd(pid)

