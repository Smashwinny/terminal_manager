from terminal_manager.highlight import border_geometries
from terminal_manager.model import WindowInfo


def test_border_geometries_surround_window() -> None:
    window = WindowInfo("0x1", 0, 1, 100, 200, 800, 600, "XTerm.XTerm", "host", "title")
    assert border_geometries(window, 6) == (
        "812x6+94+194",
        "812x6+94+800",
        "6x600+94+200",
        "6x600+900+200",
    )
    assert border_geometries(window, 6, (20, 30, 400, 300))[0] == "412x6+14+24"
