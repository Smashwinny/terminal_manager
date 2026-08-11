from terminal_manager.activity import ActivityState
from terminal_manager.app import activity_sort_key


def state(status: str, stopped: float, active: float | None = None) -> ActivityState:
    return ActivityState(status, 0.0, stopped, active, 3)


def test_static_windows_sort_by_shortest_stop_time_first() -> None:
    recent = activity_sort_key(state("static", 5), "static", "recent")
    old = activity_sort_key(state("static", 50), "static", "old")
    assert recent < old


def test_active_windows_are_last_and_longest_output_is_furthest_back() -> None:
    static = activity_sort_key(state("static", 500), "static", "static")
    recent_active = activity_sort_key(state("active", 0, 3), "active", "new")
    old_active = activity_sort_key(state("active", 0, 90), "active", "old")
    assert static < recent_active < old_active
