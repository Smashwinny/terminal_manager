from __future__ import annotations

import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from . import __version__
from .model import STATUS_LABELS, ShellInfo, WindowInfo
from .store import load_shells, remove_shell, save_shell
from .x11 import X11Error, find_window, focus_window, list_windows


STATUS_COLORS = {
    "idle": "#5b6472",
    "running": "#16803c",
    "stopped": "#b76e00",
    "ended": "#a32929",
    "unknown": "#7653a6",
    "window": "#53657d",
}


class TerminalManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Terminal Manager {__version__}")
        self.root.geometry("1080x620")
        self.root.minsize(760, 430)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.items: dict[str, tuple[ShellInfo | None, WindowInfo | None]] = {}
        self.windows: list[WindowInfo] = []
        self.refresh_job: str | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="当前 Shell 总览", font=("Sans", 17, "bold")).pack(side=tk.LEFT)
        self.summary = ttk.Label(header, text="")
        self.summary.pack(side=tk.LEFT, padx=14)
        ttk.Button(header, text="刷新", command=self.refresh).pack(side=tk.RIGHT)
        ttk.Button(header, text="注册方法", command=self.show_register_help).pack(side=tk.RIGHT, padx=6)

        columns = ("name", "status", "command", "cwd", "window")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        labels = {
            "name": "名称",
            "status": "状态",
            "command": "当前前台命令",
            "cwd": "工作目录",
            "window": "窗口",
        }
        widths = {"name": 175, "status": 100, "command": 230, "cwd": 300, "window": 170}
        for key in columns:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], minwidth=70, stretch=key in ("command", "cwd"))
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar.place(in_=self.tree, relx=1.0, rely=0, relheight=1.0, anchor="ne")
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        self.tree.bind("<Double-1>", lambda _event: self.focus_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_details())
        self.tree.bind("<Return>", lambda _event: self.focus_selected())

        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="进入/高亮 Shell", command=self.focus_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="重命名", command=self.rename_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="移除记录", command=self.remove_selected).pack(side=tk.LEFT)
        ttk.Label(buttons, text="双击条目也可进入；每 2 秒自动刷新", foreground="#666").pack(side=tk.RIGHT)

        detail_box = ttk.LabelFrame(container, text="状态说明", padding=9)
        detail_box.pack(fill=tk.X)
        self.details = ttk.Label(detail_box, text="选择一个 Shell 查看说明", justify=tk.LEFT)
        self.details.pack(fill=tk.X)

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
        now = time.time()
        for info in shells:
            if info.status != "ended" and now - info.last_seen > 6:
                info.status = "unknown"
                info.status_detail = "超过 6 秒未收到监测器更新"

        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        covered_windows: set[str] = set()
        for info in sorted(shells, key=lambda item: (item.status == "ended", item.name.lower())):
            window = find_window(info.window_id, self.windows)
            if window:
                covered_windows.add(info.window_id)
            iid = f"shell:{info.shell_id}"
            self.items[iid] = (info, window)
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    info.name,
                    STATUS_LABELS.get(info.status, info.status),
                    compact(info.command, 46),
                    compact(info.cwd, 54),
                    window.title if window else f"{info.window_id}（未找到）",
                ),
                tags=(info.status,),
            )

        for window in sorted(self.windows, key=lambda item: item.title.lower()):
            if window.window_id in covered_windows:
                continue
            iid = f"window:{window.window_id}"
            self.items[iid] = (None, window)
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(window.title or "终端窗口", "未注册", "—", "—", window.wm_class),
                tags=("window",),
            )

        total = len(self.items)
        running = sum(1 for shell in shells if shell.status == "running")
        idle = sum(1 for shell in shells if shell.status == "idle")
        unregistered = sum(1 for window in self.windows if window.window_id not in covered_windows)
        self.summary.configure(text=error or f"共 {total} 项 · 运行 {running} · 空闲 {idle} · 未注册窗口 {unregistered}")
        if selected_shell_id and self.tree.exists(selected_shell_id):
            self.tree.selection_set(selected_shell_id)
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
                "这个终端窗口尚未绑定到具体 Shell，因此只能聚焦窗口，不能准确显示命令和目录。\n"
                "在该终端中执行 terminal-manager-register --name \"用途名称\" 即可启用状态监测。"
            )
        if not window:
            text += "\n当前窗口 ID 已不存在；Shell 可能结束或窗口已经关闭。"
        self.details.configure(text=text)

    def rename_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, _window = selected
        if not shell:
            self.show_register_help()
            return
        name = simpledialog.askstring("重命名", "Shell 用途名称：", initialvalue=shell.name, parent=self.root)
        if name and name.strip():
            shell.name = name.strip()
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

    def show_register_help(self) -> None:
        messagebox.showinfo(
            "注册当前 Shell",
            "切换到需要管理的终端，在其中执行：\n\n"
            "terminal-manager-register --name \"用途名称\"\n\n"
            "这不会重启、迁移或控制 Shell；只登记窗口并监测其前台进程。",
            parent=self.root,
        )


def compact(value: str, length: int) -> str:
    value = value or "—"
    return value if len(value) <= length else "…" + value[-(length - 1) :]


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
