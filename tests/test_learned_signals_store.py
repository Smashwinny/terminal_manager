from pathlib import Path
from unittest.mock import patch

from terminal_manager.store import load_learned_signals, save_learned_signals


def test_learned_signals_survive_reload(tmp_path: Path) -> None:
    with patch.dict("terminal_manager.store.os.environ", {"XDG_STATE_HOME": str(tmp_path)}):
        save_learned_signals({"◐", "◓", "◑"})
        assert load_learned_signals() == {"◐", "◓", "◑"}
