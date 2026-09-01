from unittest.mock import Mock, patch

from terminal_manager.pointer import PointerPressMonitor


def test_reader_reports_only_raw_left_button_presses() -> None:
    monitor = PointerPressMonitor()
    monitor._process = Mock()
    monitor._process.stdout = iter(
        [
            "EVENT type 15 (RawButtonPress)\n",
            "    detail: 3\n",
            "EVENT type 15 (RawButtonPress)\n",
            "    detail: 1\n",
            "EVENT type 16 (RawButtonRelease)\n",
            "    detail: 1\n",
        ]
    )

    with patch("terminal_manager.pointer.time.monotonic", return_value=12.5):
        monitor._read_events()

    assert monitor.drain() == [12.5]
    assert monitor.drain() == []
