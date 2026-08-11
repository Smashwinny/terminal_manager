from terminal_manager.highlight import flash_geometry


def test_flash_geometry_covers_window() -> None:
    assert flash_geometry((100, 200, 800, 600)) == "800x600+100+200"
