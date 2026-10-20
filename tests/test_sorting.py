from terminal_manager.activity import ActivityState
from terminal_manager.app import activity_sort_key


def state(status: str, duration: float) -> ActivityState:
    return ActivityState(status, duration, 3)


def test_waiting_then_active_then_static() -> None:
    waiting = activity_sort_key(state("waiting", 9), "waiting", "waiting")
    active = activity_sort_key(state("active", 2), "active", "active")
    static = activity_sort_key(state("static", 1), "static", "static")
    assert waiting < active < static


def test_warmer_windows_sort_before_status_priority() -> None:
    cold_waiting = activity_sort_key(state("waiting", 2), "waiting", "cold", 0.1)
    warm_static = activity_sort_key(state("static", 20), "static", "warm", 0.8)

    assert warm_static < cold_waiting


def test_temperature_is_clamped_before_sorting() -> None:
    maximum = activity_sort_key(state("active", 1), "active", "maximum", 1.0)
    above_maximum = activity_sort_key(state("active", 1), "active", "above", 9.0)
    minimum = activity_sort_key(state("active", 1), "active", "minimum", 0.0)
    below_minimum = activity_sort_key(state("active", 1), "active", "below", -9.0)

    assert maximum[0] == above_maximum[0] == -1.0
    assert minimum[0] == below_minimum[0] == 0.0


def test_each_group_sorts_shorter_duration_first() -> None:
    for status in ("waiting", "active", "static"):
        assert activity_sort_key(state(status, 2), status, "new") < activity_sort_key(
            state(status, 20), status, "old"
        )
