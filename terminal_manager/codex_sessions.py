"""Read-only Codex identity discovery; recovery always uses an exact UUID."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
FIELDS = ("codex_session_id", "codex_cwd", "codex_home")


def default_home() -> str:
    return str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve())


def valid_id(value: str) -> bool:
    return isinstance(value, str) and UUID.fullmatch(value) is not None


def sessions(home: str = "", cwd: str | None = None) -> list[dict]:
    """Read metadata only, never prompts, credentials, or conversation bodies."""
    root = Path(home or default_home())
    names = {}
    try:
        for line in (root / "session_index.jsonl").read_text().splitlines():
            try:
                item = json.loads(line)
                names[item["id"]] = item.get("thread_name", "")
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass
    try:
        with sqlite3.connect((root / "state_5.sqlite").as_uri() + "?mode=ro", uri=True, timeout=.2) as db:
            db.row_factory = sqlite3.Row
            query = "SELECT id,cwd,title,source,updated_at,rollout_path FROM threads WHERE archived=0"
            rows = db.execute(query + (" AND cwd=?" if cwd else "") + " ORDER BY updated_at DESC", (cwd,) if cwd else ()).fetchall()
    except (OSError, ValueError, sqlite3.Error):
        return []
    return [{**dict(row), "label": names.get(row["id"]) or row["title"], "home": str(root)} for row in rows if valid_id(row["id"]) and row["source"] in ("cli", "vscode", "exec")]


def metadata(session_id: str, home: str = "") -> dict | None:
    if not valid_id(session_id):
        return None
    return next((s for s in sessions(home) if s["id"] == session_id), None)


def resume_argv(session_id: str, directory: str, home: str = "") -> list[str]:
    if not valid_id(session_id):
        raise ValueError("Codex 会话 ID 无效；不会改为恢复最近的对话")
    if not metadata(session_id, home):
        raise ValueError("本地 Codex 索引中找不到这个会话；请仅恢复目录或重新关联会话")
    path = Path(directory)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("Codex 会话目录不存在")
    executable = shutil.which("codex")
    if not executable:
        local = Path.home() / ".local/bin/codex"
        executable = str(local) if os.access(local, os.X_OK) else None
    if not executable:
        raise ValueError("未找到 Codex CLI")
    root = Path(home or default_home())
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Codex 会话存储目录无效")
    # No prompt, --last, exec, shell command interpolation, or permission overrides.
    return ["env", f"CODEX_HOME={root}", executable, "resume", session_id, "-C", str(path)]


def parse_cli(args: list[str]) -> tuple[bool, str]:
    if not args:
        return False, ""
    offset = 1
    if Path(args[0]).name == "node" and len(args) > 1 and Path(args[1]).name == "codex":
        offset = 2
    elif Path(args[0]).name != "codex":
        return False, ""
    rest = args[offset:]
    if rest and rest[0] in {"app-server", "sandbox", "exec", "exec-server", "review", "debug", "doctor", "mcp", "queue", "agents"}:
        return False, ""
    if "resume" in rest:
        index = rest.index("resume") + 1
        if index < len(rest) and valid_id(rest[index]):
            return True, rest[index]
    return True, ""


def live_processes(proc: Path = Path("/proc")) -> list[dict]:
    result = {}
    for path in proc.glob("[0-9]*"):
        try:
            if (path / "comm").read_text().strip() not in {"codex", "node"}:
                continue
            args = [a.decode(errors="replace") for a in (path / "cmdline").read_bytes().split(b"\0") if a]
            interactive, sid = parse_cli(args)
            if not interactive:
                continue
            tty = os.readlink(path / "fd/0")
            if not tty.startswith("/dev/pts/"):
                continue
            cwd = os.readlink(path / "cwd")
            home = default_home()
            for part in (path / "environ").read_bytes().split(b"\0"):
                if part.startswith(b"CODEX_HOME="):
                    home = part.split(b"=", 1)[1].decode()
            if not sid:
                ids = set()
                for fd in (path / "fd").iterdir():
                    try:
                        name = Path(os.readlink(fd)).name
                        if name.startswith("rollout-") and name.endswith(".jsonl"):
                            found = UUID.search(name)
                            if found: ids.add(found.group())
                    except OSError:
                        pass
                if len(ids) == 1:
                    sid = ids.pop()
            key = (tty, sid, home)
            result[key] = {"pid": int(path.name), "tty": tty, "cwd": cwd, "home": home, "id": sid}
        except (OSError, ValueError):
            continue
    return list(result.values())


def title_matches(title: str, label: str) -> bool:
    from .activity import split_status_prefix
    body = split_status_prefix(title)[1].strip()
    if body.startswith("[ ! ] Action Required | "):
        body = body.removeprefix("[ ! ] Action Required | ")
    return len(label.strip()) >= 4 and (body == label or body.startswith(label + " | "))


def detect(title: str, cwd: str, tty: str, processes: list[dict], catalog: list[dict]) -> dict:
    """Require a live CLI plus proven TTY or an exact unique session title."""
    candidates = [p for p in processes if (p["tty"] == tty if tty else p["cwd"] == cwd)]
    matches = {}
    for process in candidates:
        if not tty and not process["id"] and len({p["tty"] for p in candidates}) != 1:
            continue
        # /resume inside an existing TUI does not change its argv. Prefer the
        # uniquely matching current title over a stale startup session UUID.
        titled = [r for r in catalog if r["home"] == process["home"] and (tty or r["cwd"] == cwd) and (tty or not process["id"] or r["id"] == process["id"]) and title_matches(title, r["label"])]
        for record in titled:
            matches[(record["home"], record["id"])] = record
    if len(matches) != 1:
        return {}
    record = next(iter(matches.values()))
    return {"codex_session_id": record["id"], "codex_cwd": record["cwd"], "codex_home": record["home"]}


def snapshot() -> tuple[list[dict], list[dict]]:
    processes = live_processes()
    catalog = [session for home in {p["home"] for p in processes} for session in sessions(home)]
    return processes, catalog


def is_live(session_id: str, home: str = "") -> bool:
    root = home or default_home()
    return any(p["id"] == session_id and p["home"] == root for p in live_processes())
