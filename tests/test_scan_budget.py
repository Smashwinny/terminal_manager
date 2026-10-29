from dataclasses import replace
from unittest.mock import Mock, patch

from terminal_manager.app import TerminalManagerApp
from terminal_manager.model import WindowInfo
from terminal_manager.scan_budget import ScanBudget


def test_periodic_scan_is_separate_from_two_second_ui_ticks():
    budget = ScanBudget()
    with patch("terminal_manager.scan_budget.time.monotonic") as clock:
        clock.return_value = 100
        assert budget.start("windows")
        clock.return_value = 100.1
        budget.finish()
        for now in (102, 104, 106, 108):
            clock.return_value = now
            assert not budget.start("windows")
        clock.return_value = 110
        assert budget.start("windows")


def test_new_windows_and_manual_requests_remain_responsive_without_flooding():
    budget = ScanBudget()
    with patch("terminal_manager.scan_budget.time.monotonic") as clock:
        clock.return_value = 100
        assert budget.start("old")
        clock.return_value = 101
        assert not budget.start("new", force=True)
        clock.return_value = 102
        assert budget.start("new")
        clock.return_value = 104
        assert budget.start("new", force=True)


def test_slow_scan_gets_cooldown_instead_of_running_again_immediately():
    budget = ScanBudget()
    with patch("terminal_manager.scan_budget.time.monotonic") as clock:
        clock.return_value = 100
        assert budget.start()
        clock.return_value = 106
        budget.finish()
        clock.return_value = 110
        assert not budget.start()
        clock.return_value = 159
        assert not budget.start()
        clock.return_value = 160
        assert budget.start()


def test_animated_titles_do_not_trigger_new_accessibility_scans():
    app = object.__new__(TerminalManagerApp)
    app.resources = Mock(reason='')
    app.recovery_queue = Mock(active=False)
    window = WindowInfo("0x2a", 0, 123, 0, 0, 800, 600, "gnome-terminal", "", "spinner 1")
    app.windows = [window]
    app.tab_groups = {}
    app._tab_scan_thread = None
    app._tab_scan_budget = ScanBudget()
    app._tab_scan_requested = False
    with patch("terminal_manager.scan_budget.time.monotonic") as clock, patch("terminal_manager.app.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        clock.return_value = 100
        app._request_tab_scan()
        for now in (102, 104, 106, 108):
            clock.return_value = now
            app.windows = [replace(window, title=f"spinner {now}", x=now)]
            app._request_tab_scan()
        assert thread.call_count == 1
        clock.return_value = 110
        app._request_tab_scan()
        assert thread.call_count == 2


def test_switching_known_tab_title_requests_prompt_scan_but_spinners_do_not():
    app = object.__new__(TerminalManagerApp)
    app.resources = Mock(reason='')
    app.recovery_queue = Mock(active=False)
    window = WindowInfo("0x2a", 0, 123, 0, 0, 800, 600, "gnome-terminal", "", "⠋ task A")
    app.windows = [window]
    app.tab_groups = {window.window_id: Mock()}
    app._tab_scan_thread = None
    app._tab_scan_budget = ScanBudget()
    app._tab_scan_requested = False
    with patch("terminal_manager.scan_budget.time.monotonic") as clock, patch("terminal_manager.app.threading.Thread") as thread:
        thread.return_value.is_alive.return_value = False
        clock.return_value = 100
        app._request_tab_scan()
        clock.return_value = 102
        app.windows = [replace(window, title="⠙ task A")]
        app._request_tab_scan()
        assert thread.call_count == 1
        clock.return_value = 104
        app.windows = [replace(window, title="task B")]
        app._request_tab_scan()
        assert thread.call_count == 2


def test_failed_scan_preserves_cached_tabs():
    app = object.__new__(TerminalManagerApp)
    app._tab_scan_result = None
    app.tab_groups = {"0x2a": Mock()}
    app._harvest_tab_scan()
    assert "0x2a" in app.tab_groups
