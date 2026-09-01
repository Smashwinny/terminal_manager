from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from .model import ShellInfo


TTY_BINDINGS_VERSION = 2
LEARNED_SIGNALS_VERSION = 2
RUNTIME_SESSION_VERSION = 1
UI_STATE_VERSION = 1


def state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "terminal-manager" / "shells"


def tty_bindings_path() -> Path:
    return state_dir().parent / "tty-bindings.json"


def learned_signals_path() -> Path:
    return state_dir().parent / "learned-signals.json"


def runtime_session_path() -> Path:
    return state_dir().parent / "runtime-session.json"


def ui_state_path() -> Path:
    return state_dir().parent / "ui-state.json"


def _atomic_private_json(target: Path, payload: object) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    temporary = target.with_suffix(target.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(target)
        target.chmod(0o600)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def load_runtime_session() -> dict[str, object]:
    empty = {"clean_shutdown": True, "entries": []}
    try:
        data = json.loads(runtime_session_path().read_text(encoding="utf-8"))
        if data.get("version") != RUNTIME_SESSION_VERSION:
            return empty
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            return empty
        valid = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            required = ("shell_id", "name", "cwd", "window_id")
            if all(isinstance(entry.get(key), str) for key in required):
                valid.append({key: entry[key] for key in required})
        return {"clean_shutdown": bool(data.get("clean_shutdown", False)), "entries": valid}
    except (OSError, AttributeError, ValueError, TypeError, json.JSONDecodeError):
        return empty


def save_runtime_session(*, clean_shutdown: bool, entries: list[dict[str, str]]) -> None:
    payload = {
        "version": RUNTIME_SESSION_VERSION,
        "clean_shutdown": clean_shutdown,
        "updated_at": time.time(),
        "entries": entries,
    }
    _atomic_private_json(runtime_session_path(), payload)


def load_window_size() -> tuple[int, int] | None:
    try:
        data = json.loads(ui_state_path().read_text(encoding="utf-8"))
        if data.get("version") != UI_STATE_VERSION:
            return None
        width, height = int(data["width"]), int(data["height"])
        if width < 1 or height < 1:
            return None
        return width, height
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_window_size(width: int, height: int) -> None:
    if width < 1 or height < 1:
        return
    _atomic_private_json(
        ui_state_path(),
        {"version": UI_STATE_VERSION, "width": int(width), "height": int(height)},
    )


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
    payload = {"version": LEARNED_SIGNALS_VERSION, "states": {status: sorted(protocol.get(status, set())) for status in ("active", "waiting", "static")}}
    _atomic_private_json(target, payload)


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
    bindings = load_tty_bindings()
    bindings.setdefault(window_id, {})[tab_key] = tty
    payload = {"version": TTY_BINDINGS_VERSION, "bindings": bindings}
    _atomic_private_json(target, payload)


def shell_path(shell_id: str) -> Path:
    return state_dir() / f"{shell_id}.json"


def save_shell(info: ShellInfo) -> None:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = shell_path(info.shell_id)
    _atomic_private_json(target, asdict(info))


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
