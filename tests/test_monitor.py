import os

from terminal_manager.monitor import proc_cmdline, proc_cwd, proc_stat, proc_tpgid, process_exists


def test_current_process_can_be_inspected() -> None:
    pid = os.getpid()
    command, state = proc_stat(pid)
    assert process_exists(pid)
    assert command
    assert state in "RSDTtZXI"
    assert proc_cmdline(pid)
    assert proc_cwd(pid)
    # The test runner may not own a TTY, but parsing the field must be safe.
    assert proc_tpgid(pid) is None or proc_tpgid(pid) > 0
