from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .model import ShellInfo


TTY_BINDINGS_VERSION = 2
LEARNED_SIGNALS_VERSION = 2


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "terminal-manager" / "shells"


def tty_bindings_path() -> Path:
    return state_dir().parent / "tty-bindings.json"


def learned_signals_path() -> Path:
    return state_dir().parent / "learned-signals.json"


def load_learned_protocol() -> dict[str, set[str]]:
    try:
        data = json.loads(learned_signals_path().read_text(encoding="utf-8"))
        if data.get("version") == 1:
            return normalize_learned_protocol({"active": {str(value) for value in data.get("prefixes", []) if len(str(value)) == 1}, "waiting": set(), "static": set()})
        if data.get("version") != LEARNED_SIGNALS_VERSION:
            return {"active": set(), "waiting": set(), "static": set()}
        states = data.get("states", {})
        return normalize_learned_protocol({status: {str(value) for value in states.get(status, []) if len(str(value)) <= 1} for status in ("active", "waiting", "static")})
    except (OSError, AttributeError, ValueError, TypeError, json.JSONDecodeError):
        return {"active": set(), "waiting": set(), "static": set()}


def load_learned_signals() -> set[str]:
    return load_learned_protocol()["active"]


def save_learned_signals(prefixes: set[str]) -> None:
    protocol = load_learned_protocol()
    protocol["active"] = set(prefixes)
    save_learned_protocol(protocol)


def save_learned_protocol(protocol: dict[str, set[str]]) -> None:
    protocol = normalize_learned_protocol(protocol)
    target = learned_signals_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    payload = {"version": LEARNED_SIGNALS_VERSION, "states": {status: sorted(protocol.get(status, set())) for status in ("active", "waiting", "static")}}
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def assign_learned_signal(protocol: dict[str, set[str]], status: str, prefix: str) -> None:
    for values in protocol.values():
        values.discard(prefix)
    protocol[status].add(prefix)


def normalize_learned_protocol(protocol: dict[str, set[str]]) -> dict[str, set[str]]:
    """Ensure one title signal cannot drive multiple thermal states."""
    normalized = {status: set(protocol.get(status, set())) for status in ("active", "static", "waiting")}
    # Existing ambiguous files resolve conservatively: waiting, then static,
    # then active. New UI assignments always use last-choice-wins instead.
    normalized["static"] -= normalized["waiting"]
    normalized["active"] -= normalized["waiting"] | normalized["static"]
    return normalized


def load_tty_bindings() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(tty_bindings_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != TTY_BINDINGS_VERSION:
            return {}
        data = data.get("bindings", {})
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
    payload = {"version": TTY_BINDINGS_VERSION, "bindings": bindings}
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
