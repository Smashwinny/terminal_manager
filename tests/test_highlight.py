from unittest.mock import patch

from terminal_manager.highlight import RESET_SEQUENCE, WindowHighlighter


class Root:
    def __init__(self) -> None:
        self.callback = None

    def after(self, _delay: int, callback):
        self.callback = callback
        return "job"

    def after_cancel(self, _job: str) -> None:
        pass


@patch("terminal_manager.highlight.set_tty_highlight", return_value=True)
def test_native_tty_flash_and_reset(set_highlight) -> None:
    root = Root()
    highlighter = WindowHighlighter(root)
    assert highlighter.flash("/dev/pts/10")
    set_highlight.assert_called_once_with("/dev/pts/10", True)
    root.callback()
    assert set_highlight.call_args_list[-1].args == ("/dev/pts/10", False)
    assert RESET_SEQUENCE.startswith(b"\x1b]111")
