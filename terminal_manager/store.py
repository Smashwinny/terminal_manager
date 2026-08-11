from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .model import ShellInfo


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "terminal-manager" / "shells"


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

