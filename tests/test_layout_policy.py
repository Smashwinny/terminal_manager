from terminal_manager.app import layout_resize_allowed, responsive_scale


def test_background_row_changes_do_not_resize_user_window() -> None:
    assert layout_resize_allowed(None)
    assert not layout_resize_allowed(4)
    assert layout_resize_allowed(4, force=True)


def test_responsive_scale_reaches_one_quarter_of_previous_minimum() -> None:
    assert responsive_scale(860, 520) == 1.0
    assert responsive_scale(430, 260) == 0.5
    assert responsive_scale(215, 130) == 0.25
    assert responsive_scale(100, 60) == 0.25
