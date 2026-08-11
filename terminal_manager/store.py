from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .model import ShellInfo


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "terminal-manager" / "shells"


def tty_bindings_path() -> Path:
    return state_dir().parent / "tty-bindings.json"


def load_tty_bindings() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(tty_bindings_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            str(window_id): {str(key): str(tty) for key, tty in bindings.items()}
            for window_id, bindings in data.items()
            if isinstance(bindings, dict)
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def save_tty_binding(window_id: str, tab_key: str, tty: str) -> None:
    target = tty_bindings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    bindings = load_tty_bindings()
    bindings.setdefault(window_id, {})[tab_key] = tty
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(bindings, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def shell_path(shell_id: str) -> Path:
    return state_dir() / f"{shell_id}.json"


def save_shell(info: ShellInfo) -> None:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = shell_path(info.shell_id)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(info), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def load_shells() -> list[ShellInfo]:
    directory = state_dir()
    if not directory.exists():
        return []
    shells: list[ShellInfo] = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            shells.append(ShellInfo(**data))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return shells


def remove_shell(shell_id: str) -> bool:
    try:
        shell_path(shell_id).unlink()
        return True
    except FileNotFoundError:
        return False
