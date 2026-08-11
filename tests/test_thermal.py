from terminal_manager.thermal import ThermalTracker, blend_color, mean_temperature


def test_active_heats_to_maximum_in_ten_minutes() -> None:
    tracker = ThermalTracker()
    assert tracker.update({"a": "active"}, now=0)["a"] == 0
    assert tracker.update({"a": "active"}, now=300)["a"] == 0.5
    assert tracker.update({"a": "active"}, now=600)["a"] == 1


def test_static_cools_and_waiting_holds() -> None:
    tracker = ThermalTracker()
    tracker.update({"a": "active"}, now=0)
    tracker.update({"a": "active"}, now=600)
    assert tracker.update({"a": "waiting"}, now=900)["a"] == 1
    assert tracker.update({"a": "static"}, now=960)["a"] == 0.5
    assert tracker.update({"a": "static"}, now=1020)["a"] == 0


def test_colour_and_project_mean() -> None:
    assert blend_color("#000000", "#ffffff", 0.5) == "#808080"
    assert mean_temperature({"a": 0.25, "b": 0.75}) == 0.5
