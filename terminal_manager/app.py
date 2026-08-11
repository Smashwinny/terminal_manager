from __future__ import annotations

import time
import tkinter as tk
import uuid
from tkinter import messagebox, ttk

from . import __version__
from .dialogs import RegistrationDialog
from .discovery import discover_shell_candidates, suggest_candidate
from .model import STATUS_LABELS, ShellInfo, WindowInfo
from .monitor import refresh as inspect_shell
from .store import load_shells, remove_shell, save_shell
from .x11 import X11Error, active_window_id, find_window, focus_window, list_windows


STATUS_COLORS = {
    "idle": "#94a3b8",
    "running": "#46d483",
    "stopped": "#fbbf55",
    "ended": "#fb7185",
    "unknown": "#c4a7ff",
    "unbound": "#f0a95b",
    "window": "#67b7ff",
}

STATUS_DOTS = {status: "●" for status in STATUS_COLORS}

PALETTE = {
    "bg": "#080d18",
    "surface": "#101827",
    "surface_2": "#151f31",
    "surface_3": "#1b273b",
    "border": "#26354d",
    "text": "#f2f6ff",
    "muted": "#8fa1ba",
    "subtle": "#64748b",
    "accent": "#7c6cff",
    "accent_hover": "#9185ff",
    "cyan": "#47c8ff",
}


class TerminalManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Terminal Manager {__version__}")
        self.root.geometry("1180x720")
        self.root.minsize(860, 520)
        self.root.configure(background=PALETTE["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.items: dict[str, tuple[ShellInfo | None, WindowInfo | None]] = {}
        self.windows: list[WindowInfo] = []
        self.refresh_job: str | None = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self.refresh())
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self._configure_styles()
        container = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 22))
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 18))
        brand = ttk.Frame(header, style="App.TFrame")
        brand.pack(side=tk.LEFT)
        logo = tk.Label(
            brand,
            text=">_",
            font=("Ubuntu Mono", 17, "bold"),
            foreground="#ffffff",
            background=PALETTE["accent"],
            padx=10,
            pady=7,
        )
        logo.pack(side=tk.LEFT, padx=(0, 13))
        titles = ttk.Frame(brand, style="App.TFrame")
        titles.pack(side=tk.LEFT)
        ttk.Label(titles, text="Terminal Manager", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(titles, text="你的 Shell，一眼看清 · 一键抵达", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))

        header_actions = ttk.Frame(header, style="App.TFrame")
        header_actions.pack(side=tk.RIGHT)
        ttk.Button(header_actions, text="登记窗口", style="Ghost.TButton", command=self.register_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(header_actions, text="↻  刷新", style="Accent.TButton", command=self.refresh).pack(side=tk.LEFT)

        dashboard = ttk.Frame(container, style="App.TFrame")
        dashboard.pack(fill=tk.X, pady=(0, 16))
        self.metric_values: dict[str, tk.Label] = {}
        metrics = (
            ("total", "全部终端", PALETTE["cyan"]),
            ("running", "正在运行", STATUS_COLORS["running"]),
            ("idle", "空闲 Shell", STATUS_COLORS["idle"]),
            ("unregistered", "待注册", STATUS_COLORS["window"]),
        )
        for index, (key, label, color) in enumerate(metrics):
            card = tk.Frame(
                dashboard,
                background=PALETTE["surface"],
                highlightbackground=PALETTE["border"],
                highlightthickness=1,
                padx=16,
                pady=11,
            )
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if index == 0 else 6, 0 if index == len(metrics) - 1 else 6))
            top = tk.Frame(card, background=PALETTE["surface"])
            top.pack(fill=tk.X)
            tk.Label(top, text="●", foreground=color, background=PALETTE["surface"], font=("DejaVu Sans", 8)).pack(side=tk.LEFT)
            tk.Label(top, text=label, foreground=PALETTE["muted"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 9)).pack(side=tk.LEFT, padx=(7, 0))
            value = tk.Label(card, text="0", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Ubuntu", 20, "bold"))
            value.pack(anchor=tk.W, pady=(4, 0))
            self.metric_values[key] = value

        surface = tk.Frame(
            container,
            background=PALETTE["surface"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
        )
        surface.pack(fill=tk.BOTH, expand=True)

        toolbar = tk.Frame(surface, background=PALETTE["surface"], padx=16, pady=13)
        toolbar.pack(fill=tk.X)
        tk.Label(toolbar, text="Shell 工作区", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 11, "bold")).pack(side=tk.LEFT)
        tk.Label(toolbar, text="双击条目即可聚焦并震动提示", foreground=PALETTE["muted"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 9)).pack(side=tk.LEFT, padx=12)
        search_box = tk.Frame(toolbar, background=PALETTE["surface_2"], padx=10, pady=5)
        search_box.pack(side=tk.RIGHT)
        tk.Label(search_box, text="⌕", foreground=PALETTE["muted"], background=PALETTE["surface_2"], font=("DejaVu Sans", 12)).pack(side=tk.LEFT)
        search = tk.Entry(
            search_box,
            textvariable=self.search_var,
            width=24,
            background=PALETTE["surface_2"],
            foreground=PALETTE["text"],
            insertbackground=PALETTE["text"],
            selectbackground=PALETTE["accent"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=("Noto Sans CJK SC", 9),
        )
        search.pack(side=tk.LEFT, padx=(6, 0))

        columns = ("name", "status", "command", "cwd", "window")
        table = ttk.Frame(surface, style="Surface.TFrame")
        table.pack(fill=tk.BOTH, expand=True, padx=1)
        self.tree = ttk.Treeview(
            table,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Shell.Treeview",
            height=5,
        )
        labels = {
            "name": "名称",
            "status": "状态",
            "command": "当前前台命令",
            "cwd": "工作目录",
            "window": "窗口",
        }
        widths = {"name": 190, "status": 115, "command": 240, "cwd": 300, "window": 205}
        for key in columns:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], minwidth=70, stretch=key in ("command", "cwd"))
        scrollbar = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        self.tree.tag_configure("even", background=PALETTE["surface"])
        self.tree.tag_configure("odd", background=PALETTE["surface_2"])
        self.tree.bind("<Double-1>", lambda _event: self.focus_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_details())
        self.tree.bind("<Return>", lambda _event: self.focus_selected())

        footer = tk.Frame(surface, background=PALETTE["surface"], padx=16, pady=13)
        footer.pack(fill=tk.X)
        actions = ttk.Frame(footer, style="Surface.TFrame")
        actions.pack(side=tk.LEFT)
        ttk.Button(actions, text="进入并高亮", style="Accent.TButton", command=self.focus_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="编辑记录", style="Ghost.TButton", command=self.rename_selected).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="移除记录", style="Danger.TButton", command=self.remove_selected).pack(side=tk.LEFT)
        tk.Label(footer, text="自动刷新  2s", foreground=PALETTE["subtle"], background=PALETTE["surface"], font=("Ubuntu", 9)).pack(side=tk.RIGHT)

        detail_box = tk.Frame(
            container,
            background=PALETTE["surface"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            padx=16,
            pady=13,
        )
        detail_box.pack(fill=tk.X, pady=(14, 0))
        accent = tk.Frame(detail_box, background=PALETTE["accent"], width=3)
        accent.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        detail_content = tk.Frame(detail_box, background=PALETTE["surface"])
        detail_content.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(detail_content, text="状态说明", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 10, "bold")).pack(anchor=tk.W)
        self.details = tk.Label(
            detail_content,
            text="选择一个 Shell 查看说明",
            justify=tk.LEFT,
            anchor=tk.W,
            foreground=PALETTE["muted"],
            background=PALETTE["surface"],
            font=("Noto Sans CJK SC", 9),
        )
        self.details.pack(fill=tk.X, pady=(5, 0))

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=PALETTE["bg"])
        style.configure("Surface.TFrame", background=PALETTE["surface"])
        style.configure("Title.TLabel", background=PALETTE["bg"], foreground=PALETTE["text"], font=("Ubuntu", 18, "bold"))
        style.configure("Subtitle.TLabel", background=PALETTE["bg"], foreground=PALETTE["muted"], font=("Noto Sans CJK SC", 9))
        style.configure("Accent.TButton", background=PALETTE["accent"], foreground="#ffffff", borderwidth=0, padding=(15, 8), font=("Noto Sans CJK SC", 9, "bold"))
        style.map("Accent.TButton", background=[("active", PALETTE["accent_hover"]), ("pressed", "#6657e8")])
        style.configure("Ghost.TButton", background=PALETTE["surface_2"], foreground=PALETTE["text"], borderwidth=0, padding=(14, 8), font=("Noto Sans CJK SC", 9))
        style.map("Ghost.TButton", background=[("active", PALETTE["surface_3"]), ("pressed", PALETTE["border"])])
        style.configure("Danger.TButton", background=PALETTE["surface_2"], foreground="#fb8da0", borderwidth=0, padding=(14, 8), font=("Noto Sans CJK SC", 9))
        style.map("Danger.TButton", background=[("active", "#3a2030")])
        style.configure("Shell.Treeview", background=PALETTE["surface"], fieldbackground=PALETTE["surface"], foreground=PALETTE["text"], borderwidth=0, relief="flat", rowheight=43, font=("Noto Sans CJK SC", 9))
        style.configure("Shell.Treeview.Heading", background=PALETTE["surface_3"], foreground=PALETTE["muted"], borderwidth=0, relief="flat", padding=(10, 10), font=("Noto Sans CJK SC", 9, "bold"))
        style.map("Shell.Treeview", background=[("selected", "#332d68")], foreground=[("selected", "#ffffff")])
        style.map("Shell.Treeview.Heading", background=[("active", PALETTE["surface_3"])])
        style.configure("Dark.Vertical.TScrollbar", background=PALETTE["surface_3"], troughcolor=PALETTE["surface"], borderwidth=0, arrowcolor=PALETTE["muted"])

    def refresh(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        selected_shell_id = None
        selection = self.tree.selection()
        if selection:
            selected_shell_id = selection[0]
        try:
            self.windows = list_windows()
            error = ""
        except X11Error as exc:
            self.windows = []
            error = str(exc)

        shells = load_shells()
        for info in shells:
            if info.shell_pid > 0 and info.tty:
                inspect_shell(info)
            else:
                info.status = "unbound"
                info.status_detail = "已记录名称，但尚未关联 Shell，无法监测运行状态"

        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        query = self.search_var.get().strip().lower()
        row_index = 0
        covered_windows: set[str] = set()
        for info in sorted(shells, key=lambda item: (item.status == "ended", item.name.lower())):
            window = find_window(info.window_id, self.windows)
            if window:
                covered_windows.add(info.window_id)
            searchable = " ".join(
                (info.name, info.command, info.cwd, info.status, STATUS_LABELS.get(info.status, ""), window.title if window else "")
            ).lower()
            if query and query not in searchable:
                continue
            iid = f"shell:{info.shell_id}"
            self.items[iid] = (info, window)
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    info.name,
                    f"{STATUS_DOTS.get(info.status, '●')}  {STATUS_LABELS.get(info.status, info.status)}",
                    compact(info.command, 46),
                    compact(info.cwd, 54),
                    window.title if window else f"{info.window_id}（未找到）",
                ),
                tags=(info.status, "even" if row_index % 2 == 0 else "odd"),
            )
            row_index += 1

        for window in sorted(self.windows, key=lambda item: item.title.lower()):
            if window.window_id in covered_windows:
                continue
            searchable = f"{window.title} {window.wm_class} 未注册".lower()
            if query and query not in searchable:
                continue
            iid = f"window:{window.window_id}"
            self.items[iid] = (None, window)
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(window.title or "终端窗口", "●  未注册", "—", "—", window.wm_class),
                tags=("window", "even" if row_index % 2 == 0 else "odd"),
            )
            row_index += 1

        unregistered = sum(1 for window in self.windows if window.window_id not in covered_windows)
        total = len(shells) + unregistered
        running = sum(1 for shell in shells if shell.status == "running")
        idle = sum(1 for shell in shells if shell.status == "idle")
        values = {"total": total, "running": running, "idle": idle, "unregistered": unregistered}
        for key, value in values.items():
            self.metric_values[key].configure(text=str(value))
        if error:
            self.details.configure(text=error)
        active_item = None
        try:
            active_item = item_id_for_window(self.items, active_window_id())
        except (X11Error, ValueError):
            pass
        item_to_select = active_item or selected_shell_id
        if item_to_select and self.tree.exists(item_to_select):
            self.tree.selection_set(item_to_select)
            self.tree.focus(item_to_select)
            if active_item:
                self.tree.see(item_to_select)
        self.update_details()
        self.refresh_job = self.root.after(2000, self.refresh)

    def selected(self) -> tuple[str, ShellInfo | None, WindowInfo | None] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        iid = selection[0]
        shell, window = self.items[iid]
        return iid, shell, window

    def focus_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, window = selected
        window_id = window.window_id if window else shell.window_id if shell else ""
        if not window_id:
            return
        try:
            focus_window(window_id)
        except X11Error as exc:
            messagebox.showerror("无法进入终端", str(exc), parent=self.root)

    def update_details(self) -> None:
        selected = self.selected()
        if not selected:
            self.details.configure(text="选择一个 Shell 查看说明")
            return
        _iid, shell, window = selected
        if shell:
            age = max(0, int(time.time() - shell.last_seen))
            certainty = "确定事实：窗口、Shell PID、TTY、前台进程、目录。状态名称是基于前台进程的推断。"
            text = (
                f"{STATUS_LABELS.get(shell.status, shell.status)}：{shell.status_detail}\n"
                f"Shell PID {shell.shell_pid} · TTY {shell.tty} · 前台 PID {shell.foreground_pid or '未知'} · {age} 秒前更新\n"
                f"{certainty}"
            )
        else:
            text = (
                "这个终端窗口尚未登记，因此只能聚焦窗口。\n"
                "点击“登记窗口”或“编辑记录”，直接填写名称并选择对应的 TTY/Shell，即可启用状态监测。"
            )
        if not window:
            text += "\n当前窗口 ID 已不存在；Shell 可能结束或窗口已经关闭。"
        self.details.configure(text=text)

    def rename_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, window = selected
        if not shell:
            self.register_selected()
            return
        self.edit_record(shell, window)

    def register_selected(self) -> None:
        selected = self.selected()
        if not selected:
            messagebox.showinfo("登记窗口", "请先在列表中选择一个终端窗口。", parent=self.root)
            return
        _iid, shell, window = selected
        if shell:
            self.edit_record(shell, window)
            return
        if not window:
            return
        self.edit_record(None, window)

    def edit_record(self, shell: ShellInfo | None, window: WindowInfo | None) -> None:
        if not window and shell:
            window = find_window(shell.window_id, self.windows)
        if not window:
            messagebox.showerror("窗口不存在", "当前记录对应的终端窗口已经关闭。", parent=self.root)
            return
        assigned = {item.shell_pid for item in load_shells() if item.shell_pid > 0 and (not shell or item.shell_id != shell.shell_id)}
        candidates = [item for item in discover_shell_candidates(window.pid) if item.shell_pid not in assigned]
        selected_index = 0
        if shell and shell.shell_pid > 0:
            match = next((index for index, item in enumerate(candidates, start=1) if item.shell_pid == shell.shell_pid), None)
            selected_index = match or 0
        elif candidates:
            selected_index = suggest_candidate(window.title, candidates)
        dialog = RegistrationDialog(
            self.root,
            title="编辑终端记录" if shell else "登记终端窗口",
            initial_name=shell.name if shell else (window.title or "终端窗口"),
            candidates=candidates,
            selected_index=selected_index,
            palette=PALETTE,
        )
        if not dialog.result:
            return
        name, candidate = dialog.result
        now = time.time()
        if shell is None:
            shell = ShellInfo(
                shell_id=uuid.uuid4().hex[:12],
                window_id=window.window_id,
                shell_pid=0,
                tty="",
                name=name,
                status="unbound",
                status_detail="仅记录名称",
                command="",
                cwd="",
                foreground_pid=None,
                process_state="",
                registered_at=now,
                last_seen=now,
            )
        shell.name = name
        shell.window_id = window.window_id
        if candidate:
            shell.shell_pid = candidate.shell_pid
            shell.tty = candidate.tty
            shell.cwd = candidate.cwd
            shell.command = candidate.command
            shell.status = candidate.status
            shell.status_detail = candidate.status_detail
            shell.foreground_pid = candidate.foreground_pid
            shell.process_state = candidate.process_state
            shell.last_seen = now
        else:
            shell.shell_pid = 0
            shell.tty = ""
            shell.status = "unbound"
            shell.status_detail = "已记录名称，但尚未关联 Shell"
            shell.command = ""
            shell.cwd = ""
            shell.foreground_pid = None
            shell.process_state = ""
            shell.last_seen = now
        save_shell(shell)
        self.refresh()

    def remove_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, _window = selected
        if not shell:
            messagebox.showinfo("未注册窗口", "该条目没有注册记录可移除。", parent=self.root)
            return
        if messagebox.askyesno("移除记录", f"从总览移除“{shell.name}”？\n不会关闭 Shell 或终止任务。", parent=self.root):
            remove_shell(shell.shell_id)
            self.refresh()

def compact(value: str, length: int) -> str:
    value = value or "—"
    return value if len(value) <= length else "…" + value[-(length - 1) :]


def item_id_for_window(
    items: dict[str, tuple[ShellInfo | None, WindowInfo | None]], window_id: str
) -> str | None:
    for item_id, (shell, window) in items.items():
        linked_window_id = window.window_id if window else shell.window_id if shell else ""
        if linked_window_id == window_id:
            return item_id
    return None


def main() -> None:
    root = tk.Tk()
    try:
        TerminalManagerApp(root)
    except X11Error as exc:
        root.withdraw()
        messagebox.showerror("Terminal Manager 无法启动", str(exc))
        raise SystemExit(1) from exc
    root.mainloop()


if __name__ == "__main__":
    main()
