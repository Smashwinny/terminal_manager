from terminal_manager.app import layout_resize_allowed


def test_background_row_changes_do_not_resize_user_window() -> None:
    assert layout_resize_allowed(None)
    assert not layout_resize_allowed(4)
    assert layout_resize_allowed(4, force=True)
