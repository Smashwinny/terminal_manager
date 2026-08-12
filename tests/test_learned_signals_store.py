from pathlib import Path
from unittest.mock import patch

from terminal_manager.store import assign_learned_signal, load_learned_protocol, load_learned_signals, save_learned_protocol, save_learned_signals


def test_learned_signals_survive_reload(tmp_path: Path) -> None:
    with patch.dict("terminal_manager.store.os.environ", {"XDG_STATE_HOME": str(tmp_path)}):
        save_learned_signals({"◐", "◓", "◑"})
        assert load_learned_signals() == {"◐", "◓", "◑"}


def test_three_state_protocol_survives_reload(tmp_path: Path) -> None:
    protocol = {"static": {"✳"}, "active": {"⠂", "⠐"}, "waiting": {"!"}}
    with patch.dict("terminal_manager.store.os.environ", {"XDG_STATE_HOME": str(tmp_path)}):
        save_learned_protocol(protocol)
        assert load_learned_protocol() == protocol


def test_same_signal_moves_to_latest_state() -> None:
    protocol = {"static": {"✳"}, "active": set(), "waiting": set()}
    assign_learned_signal(protocol, "waiting", "✳")
    assert protocol == {"static": set(), "active": set(), "waiting": {"✳"}}
