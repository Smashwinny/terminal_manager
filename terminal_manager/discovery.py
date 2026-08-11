from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .model import STATUS_LABELS, ShellInfo
from .monitor import proc_cmdline, proc_cwd, refresh


@dataclass(frozen=True)
class ProcessRow:
    pid: int
    ppid: int
    session_id: int
    tty: str
    command: str


@dataclass(frozen=True)
class ShellCandidate:
    shell_pid: int
    tty: str
    cwd: str
    command: str
    status: str
    status_detail: str
    foreground_pid: int | None
    process_state: str

    @property
    def label(self) -> str:
        command = self.command or "shell"
        if len(command) > 34:
            command = command[:31] + "…"
        cwd = self.cwd or "未知目录"
        if len(cwd) > 40:
            cwd = "…" + cwd[-39:]
        status = STATUS_LABELS.get(self.status, self.status)
        return f"{self.tty.replace('/dev/', ''):<8}  [{status:<3}]  {command:<35}  {cwd}"


def parse_ps_line(line: str) -> ProcessRow | None:
    parts = line.strip().split(None, 4)
    if len(parts) != 5:
        return None
    try:
        return ProcessRow(int(parts[0]), int(parts[1]), int(parts[2]), parts[3], parts[4])
    except ValueError:
        return None


def process_rows() -> list[ProcessRow]:
    result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,sid=,tty=,comm="],
        text=True,
        capture_output=True,
        timeout=3,
        check=False,
    )
    return [row for line in result.stdout.splitlines() if (row := parse_ps_line(line))]


def is_descendant(pid: int, ancestor_pid: int, parents: dict[int, int]) -> bool:
    seen: set[int] = set()
    current = pid
    while current > 1 and current not in seen:
        seen.add(current)
        current = parents.get(current, 0)
        if current == ancestor_pid:
            return True
    return False


def discover_shell_candidates(server_pid: int) -> list[ShellCandidate]:
    rows = process_rows()
    parents = {row.pid: row.ppid for row in rows}
    candidates: list[ShellCandidate] = []
    for row in rows:
        # Interactive shells launched by terminal emulators are normally session
        # leaders with a controlling PTY. This excludes child jobs in that shell.
        if row.tty == "?" or row.pid != row.session_id:
            continue
        if not is_descendant(row.pid, server_pid, parents):
            continue
        tty = row.tty if row.tty.startswith("/dev/") else f"/dev/{row.tty}"
        seed = ShellInfo(
            shell_id="candidate",
            window_id="",
            shell_pid=row.pid,
            tty=tty,
            name=row.command,
            status="unknown",
            status_detail="正在检测",
            command=proc_cmdline(row.pid) or row.command,
            cwd=proc_cwd(row.pid),
            foreground_pid=None,
            process_state="",
            registered_at=0,
            last_seen=0,
        )
        inspected = refresh(seed)
        candidates.append(
            ShellCandidate(
                shell_pid=row.pid,
                tty=tty,
                cwd=inspected.cwd,
                command=inspected.command,
                status=inspected.status,
                status_detail=inspected.status_detail,
                foreground_pid=inspected.foreground_pid,
                process_state=inspected.process_state,
            )
        )
    return sorted(candidates, key=lambda item: (item.tty, item.shell_pid))


def suggest_candidate(window_title: str, candidates: list[ShellCandidate]) -> int:
    title = window_title.lower()
    best_index = 0
    best_score = -1
    for index, candidate in enumerate(candidates, start=1):
        score = 0
        cwd_name = candidate.cwd.rstrip("/").rsplit("/", 1)[-1].lower()
        command_name = candidate.command.split()[0].rsplit("/", 1)[-1].lower() if candidate.command else ""
        if cwd_name and cwd_name in title:
            score += 4
        if command_name and command_name in title:
            score += 3
        if score > best_score:
            best_index = index
            best_score = score
    return best_index if best_score > 0 else (1 if candidates else 0)
