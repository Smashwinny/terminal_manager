from terminal_manager.discovery import ShellCandidate, is_descendant, parse_ps_line, suggest_candidate


def test_parse_ps_line() -> None:
    row = parse_ps_line("  4951  4921  4951 pts/0 bash")
    assert row is not None
    assert (row.pid, row.ppid, row.session_id, row.tty, row.command) == (4951, 4921, 4951, "pts/0", "bash")


def test_descendant_walk() -> None:
    parents = {30: 20, 20: 10, 10: 1}
    assert is_descendant(30, 10, parents)
    assert not is_descendant(30, 99, parents)


def test_candidate_suggestion_uses_window_title() -> None:
    candidates = [
        ShellCandidate(1, "/dev/pts/1", "/work/other", "bash", "idle", "", 1, "S"),
        ShellCandidate(2, "/dev/pts/2", "/work/mowmow", "codex", "running", "", 3, "S"),
    ]
    assert suggest_candidate("mowmow", candidates) == 2

