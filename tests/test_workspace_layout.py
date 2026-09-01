from pathlib import Path


def test_workspace_footer_has_a_non_expanding_grid_row() -> None:
    """Guard the layout contract that keeps the action buttons visible.

    Tk cannot be instantiated in headless CI, so this checks the declarative
    geometry contract without opening a desktop window.
    """
    source = (Path(__file__).parents[1] / "terminal_manager" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "surface.grid_rowconfigure(1, weight=1)" in source
    assert 'table.grid(row=1, column=0, sticky="nsew", padx=1)' in source
    assert 'footer.grid(row=2, column=0, sticky="ew")' in source
