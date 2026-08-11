from __future__ import annotations

import time
import tkinter as tk
import threading
import uuid
from tkinter import messagebox, ttk

from . import __version__
from .activity import ActivityState, WindowActivityTracker
from .dialogs import RegistrationDialog
from .model import STATUS_LABELS, ShellInfo, WindowInfo
from .store import load_shells, remove_shell, save_shell
from .tabs import TabGroup, TerminalTab, scan_tab_groups, select_tab
from .x11 import X11Error, active_window_id, find_window, focus_window, list_windows


STATUS_COLORS = {
    "idle": "#94a3b8",
    "running": "#46d483",
    "stopped": "#fbbf55",
    "ended": "#fb7185",
    "unknown": "#c4a7ff",
    "observing": "#c4a7ff",
    "active": "#46d483",
    "waiting": "#fbbf55",
    "static": "#94a3b8",
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
        self.activities: dict[str, ActivityState] = {}
        self.activity_tracker = WindowActivityTracker()
        self.tab_activity_tracker = WindowActivityTracker()
        self.tab_groups: dict[str, TabGroup] = {}
        self.tab_items: dict[str, tuple[TabGroup, int]] = {}
        self._tab_scan_result: list[TabGroup] | None = None
        self._tab_scan_thread: threading.Thread | None = None
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
            ("waiting", "等待用户", STATUS_COLORS["waiting"]),
            ("running", "正在输出", STATUS_COLORS["active"]),
            ("idle", "静态窗口", STATUS_COLORS["static"]),
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

        columns = ("name", "status", "activity", "last_change", "window")
        table = ttk.Frame(surface, style="Surface.TFrame")
        table.pack(fill=tk.BOTH, expand=True, padx=1)
        self.tree = ttk.Treeview(
            table,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            style="Shell.Treeview",
            height=5,
        )
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, minwidth=34, stretch=False)
        labels = {
            "name": "名称",
            "status": "状态",
            "activity": "标题信号",
            "last_change": "当前状态时长",
            "window": "窗口",
        }
        widths = {"name": 220, "status": 125, "activity": 160, "last_change": 170, "window": 390}
        for key in columns:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], minwidth=70, stretch=key == "window")
        scrollbar = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        self.tree.tag_configure("even", background=PALETTE["surface"])
        self.tree.tag_configure("odd", background=PALETTE["surface_2"])
        self.tree.bind("<Double-1>", lambda _event: self.focus_selected())
        self.tree.bind("<ButtonRelease-1>", self._handle_tree_click)
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
        expanded_windows = {
            item.removeprefix("group:")
            for item in self.tree.get_children()
            if item.startswith("group:") and self.tree.item(item, "open")
        }
        selection = self.tree.selection()
        if selection:
            selected_shell_id = selection[0]
        try:
            self.windows = list_windows()
            self._harvest_tab_scan()
            self._request_tab_scan()
            self.activities = self.activity_tracker.update(self.windows)
            error = ""
        except X11Error as exc:
            self.windows = []
            self.activities = {}
            error = str(exc)

        shells = load_shells()

        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.tab_items.clear()
        query = self.search_var.get().strip().lower()
        row_index = 0
        records_by_window = {info.window_id: info for info in shells}
        used_record_ids: set[str] = set()
        rows: list[tuple[ShellInfo | None, WindowInfo | None, ActivityState | None, str, str]] = []
        for window in self.windows:
            info = records_by_window.get(window.window_id)
            if info:
                used_record_ids.add(info.shell_id)
            activity = self.activities.get(window.window_id)
            status = activity.status if activity else "unknown"
            name = info.name if info else (window.title or "终端窗口")
            rows.append((info, window, activity, status, name))
        for info in shells:
            if info.shell_id not in used_record_ids:
                rows.append((info, None, None, "ended", info.name))

        rows.sort(key=lambda row: activity_sort_key(row[2], row[3], row[4]))
        tab_signals = []
        for group in self.tab_groups.values():
            window = find_window(group.window_id, self.windows)
            if not window:
                continue
            for tab in group.tabs:
                tab_signals.append(tab_window_signal(window, tab))
        tab_activities = self.tab_activity_tracker.update(tab_signals)

        for info, window, activity, status, name in rows:
            window_title = window.title if window else f"{info.window_id}（未找到）" if info else "窗口不存在"
            searchable = " ".join((name, status, STATUS_LABELS.get(status, ""), window_title)).lower()
            if query and query not in searchable:
                continue
            group = self.tab_groups.get(window.window_id) if window else None
            iid = f"group:{window.window_id}" if group else f"shell:{info.shell_id}" if info else f"window:{window.window_id}"
            self.items[iid] = (info, window)
            registered_prefix = "" if info else "未登记 · "
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(name, status_text(status), signal_text(activity), age_text(activity), registered_prefix + window_title),
                tags=(status, "even" if row_index % 2 == 0 else "odd"),
                open=bool(window and window.window_id in expanded_windows),
            )
            row_index += 1
            if group and window:
                for tab in group.tabs:
                    if tab.selected:
                        continue
                    child_id = f"tab:{window.window_id}:{tab.index}"
                    child_activity = tab_activities.get(tab.signal_id(window.window_id))
                    child_status = child_activity.status if child_activity else "static"
                    child_title = tab.title or f"标签 {tab.index + 1}"
                    self.items[child_id] = (info, window)
                    self.tab_items[child_id] = (group, tab.index)
                    self.tree.insert(
                        iid,
                        tk.END,
                        iid=child_id,
                        text="",
                        values=(f"↳ {child_title}", status_text(child_status), signal_text(child_activity), age_text(child_activity), "隐藏标签"),
                        tags=(child_status,),
                    )

        registered_window_ids = {info.window_id for info in shells}
        unregistered = sum(1 for window in self.windows if window.window_id not in registered_window_ids)
        total = len(rows)
        running = sum(1 for state in self.activities.values() if state.status == "active")
        waiting = sum(1 for state in self.activities.values() if state.status == "waiting")
        idle = sum(1 for state in self.activities.values() if state.status == "static")
        values = {"total": total, "waiting": waiting, "running": running, "idle": idle, "unregistered": unregistered}
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

    def _handle_tree_click(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        if item_id in self.tab_items and self.tree.identify_region(event.x, event.y) in ("tree", "cell"):
            self.root.after_idle(self.focus_selected)

    def focus_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        iid, shell, window = selected
        tab_target = self.tab_items.get(iid)
        if tab_target:
            group, tab_index = tab_target
            if not select_tab(group, tab_index):
                self._tab_scan_result = None
                self._request_tab_scan()
                self.details.configure(text="标签列表刚刚发生变化，正在后台刷新；请再点击一次。")
                return
        window_id = window.window_id if window else shell.window_id if shell else ""
        if not window_id:
            return
        try:
            focus_window(window_id, shake=tab_target is None, sync=tab_target is None)
        except X11Error as exc:
            messagebox.showerror("无法进入终端", str(exc), parent=self.root)

    def _harvest_tab_scan(self) -> None:
        if self._tab_scan_result is not None:
            self.tab_groups = {group.window_id: group for group in self._tab_scan_result}
            self._tab_scan_result = None

    def _request_tab_scan(self) -> None:
        if self._tab_scan_thread and self._tab_scan_thread.is_alive():
            return
        windows = list(self.windows)

        def scan() -> None:
            self._tab_scan_result = scan_tab_groups(windows)

        self._tab_scan_thread = threading.Thread(target=scan, daemon=True, name="terminal-tab-scan")
        self._tab_scan_thread.start()

    def update_details(self) -> None:
        selected = self.selected()
        if not selected:
            self.details.configure(text="选择一个 Shell 查看说明")
            return
        iid, shell, window = selected
        window_id = window.window_id if window else shell.window_id if shell else ""
        activity = self.activities.get(window_id)
        if activity:
            text = activity_explanation(activity)
            if shell:
                text += f"\n用途名称“{shell.name}”仅保存在管理器中，与 Shell/TTY 无关。"
            else:
                text += "\n该窗口尚未命名；点击“登记窗口”只需记录用途名称。"
        else:
            text = "暂时无法取得该窗口的画面活动；窗口可能已经关闭。"
        if not window:
            text += "\n当前窗口 ID 已不存在；Shell 可能结束或窗口已经关闭。"
        elif iid in self.tab_items:
            text += "\n这是同一终端窗口中的隐藏标签；单击即可切换到该标签。"
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
        iid, shell, window = selected
        if iid in self.tab_items:
            messagebox.showinfo("隐藏标签", "隐藏标签暂时沿用所属窗口的管理记录。", parent=self.root)
            return
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
        dialog = RegistrationDialog(
            self.root,
            title="编辑终端记录" if shell else "登记终端窗口",
            initial_name=shell.name if shell else (window.title or "终端窗口"),
            palette=PALETTE,
        )
        if not dialog.result:
            return
        name = dialog.result
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
        shell.shell_pid = 0
        shell.tty = ""
        shell.status = "unbound"
        shell.status_detail = "Codex 状态由终端窗口标题识别"
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

def status_text(status: str) -> str:
    return f"{STATUS_DOTS.get(status, '●')}  {STATUS_LABELS.get(status, status)}"


def signal_text(activity: ActivityState | None) -> str:
    if not activity:
        return "无状态信号"
    if activity.status == "waiting":
        return f"{activity.prefix} 需要输入"
    if activity.status == "active":
        source = "已学习动画" if activity.learned_prefix else "Codex 动画"
        return f"{activity.prefix} {source}"
    return "无 Codex 状态图标"


def age_text(activity: ActivityState | None) -> str:
    if not activity:
        return "未知"
    duration = activity.seconds_in_status
    if activity.status == "waiting":
        return "刚需输入" if duration < 0.5 else f"等待 {duration:.1f} 秒"
    if activity.status == "active":
        return "刚开始输出" if duration < 0.5 else f"已输出 {duration:.1f} 秒"
    return "刚静止" if duration < 0.5 else f"静态 {duration:.1f} 秒"


def activity_sort_key(
    activity: ActivityState | None, status: str, name: str
) -> tuple[int, float, str]:
    order = {"waiting": 0, "active": 1, "static": 2}
    return (order.get(status, 3), activity.seconds_in_status if activity else 0.0, name.lower())


def activity_explanation(activity: ActivityState) -> str:
    duration = activity.seconds_in_status
    if activity.status == "waiting":
        return f"等待用户：Codex 在窗口标题中显示“{activity.prefix}”，已等待 {duration:.1f} 秒。"
    if activity.status == "active":
        source = "自动学习到的动画前缀" if activity.learned_prefix else "Codex 标准动画前缀"
        return f"正在输出：窗口标题正在显示{source}“{activity.prefix}”，已持续 {duration:.1f} 秒。"
    if activity.status == "static":
        return f"静态/空闲：窗口标题没有 Codex 状态图标，已持续 {duration:.1f} 秒。"
    return "无法从窗口标题判断当前状态。"


def item_id_for_window(
    items: dict[str, tuple[ShellInfo | None, WindowInfo | None]], window_id: str
) -> str | None:
    for item_id, (shell, window) in items.items():
        linked_window_id = window.window_id if window else shell.window_id if shell else ""
        if linked_window_id == window_id:
            return item_id
    return None


def tab_window_signal(window: WindowInfo, tab: TerminalTab) -> WindowInfo:
    return WindowInfo(
        tab.signal_id(window.window_id),
        window.desktop,
        window.pid,
        window.x,
        window.y,
        window.width,
        window.height,
        window.wm_class,
        window.host,
        tab.title,
    )


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
