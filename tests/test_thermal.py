from terminal_manager.thermal import ThermalTracker, blend_color, mean_temperature, visual_temperature


def test_active_heats_to_maximum_in_ten_minutes() -> None:
    tracker = ThermalTracker(max_sample_gap_seconds=600)
    assert tracker.update({"a": "active"}, now=0)["a"] == 0
    assert tracker.update({"a": "active"}, now=300)["a"] == 0.5
    assert tracker.update({"a": "active"}, now=600)["a"] == 1


def test_static_cools_and_waiting_holds() -> None:
    tracker = ThermalTracker(max_sample_gap_seconds=600)
    tracker.update({"a": "active"}, now=0)
    tracker.update({"a": "active"}, now=600)
    assert tracker.update({"a": "waiting"}, now=900)["a"] == 1
    assert tracker.update({"a": "static"}, now=1080)["a"] == 0.5
    assert tracker.update({"a": "static"}, now=1260)["a"] == 0


def test_colour_and_project_mean() -> None:
    assert blend_color("#000000", "#ffffff", 0.5) == "#808080"
    assert mean_temperature({"a": 0.25, "b": 0.75}) == 0.5


def test_visual_curve_is_stronger_early_and_reaches_exact_endpoints() -> None:
    assert visual_temperature(0) == 0
    assert visual_temperature(0.01) == 0.1
    assert visual_temperature(0.25) == 0.5
    assert visual_temperature(1) == 1
    assert visual_temperature(0.1) - visual_temperature(0) > visual_temperature(1) - visual_temperature(0.9)


def test_long_unobserved_gap_does_not_jump_to_red() -> None:
    tracker = ThermalTracker()
    tracker.update({"a": "active"}, now=0)
    assert tracker.update({"a": "active"}, now=3600)["a"] == 10 / 600
