from terminal_manager.app import metric_matches


def test_metric_status_groups() -> None:
    assert metric_matches("total", "ended", False)
    assert metric_matches("waiting", "waiting", False)
    assert metric_matches("running", "active", False)
    assert metric_matches("idle", "static", False)
    assert not metric_matches("waiting", "active", False)


def test_unregistered_group_is_independent_of_status() -> None:
    assert metric_matches("unregistered", "active", True)
    assert not metric_matches("unregistered", "active", False)
    assert not metric_matches(None, "waiting", True)
