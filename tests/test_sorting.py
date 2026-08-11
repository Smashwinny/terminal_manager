from terminal_manager.activity import ActivityState
from terminal_manager.app import activity_sort_key


def state(status: str, duration: float) -> ActivityState:
    return ActivityState(status, duration, 3)


def test_waiting_then_active_then_static() -> None:
    waiting = activity_sort_key(state("waiting", 9), "waiting", "waiting")
    active = activity_sort_key(state("active", 2), "active", "active")
    static = activity_sort_key(state("static", 1), "static", "static")
    assert waiting < active < static


def test_each_group_sorts_shorter_duration_first() -> None:
    for status in ("waiting", "active", "static"):
        assert activity_sort_key(state(status, 2), status, "new") < activity_sort_key(
            state(status, 20), status, "old"
        )
