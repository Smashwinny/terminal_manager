from __future__ import annotations

import time
import tkinter as tk
import threading
import uuid
import os
import sys
from pathlib import Path
from tkinter import ttk
from tkinter import font as tkfont

from . import __version__
from .activity import CLAUDE_WORKING_PREFIXES, CODEX_SPINNER_PREFIXES, ActivityState, WindowActivityTracker
from .dialogs import ConfirmationDialog, NoticeDialog, RegistrationDialog, SignalLearningDialog, SignalManagementDialog
from .highlight import WindowHighlighter, can_highlight_tty
from .model import STATUS_LABELS, ShellInfo, WindowInfo
from .single_instance import DETACHED_CHILD_ENV, SingleInstance, activate_existing, launch_detached
from .recovery import launch_recovery_terminal, validate_recovery_directory
from .store import (
    load_learned_protocol,
    load_shells,
    load_tty_bindings,
    remove_shell,
    save_learned_protocol,
    assign_learned_signal,
    save_shell,
    save_tty_binding,
    load_runtime_session,
    save_runtime_session,
    load_window_size,
    save_window_size,
)
from .tabs import TabGroup, TerminalTab, scan_tab_groups, select_tab
from .thermal import HOT_ACCENT, HOT_ROW, ThermalTracker, blend_color, mean_temperature, visual_temperature
from .tty_probe import probe_visible_tty, terminal_tty_cwds
from .x11 import (
    X11Error,
    active_window_id,
    find_window,
    focus_window,
    list_windows,
    set_window_above,
    window_is_above,
    window_title,
)


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
    "bg": "#060914",
    "surface": "#0d1526",
    "surface_2": "#121d33",
    "surface_3": "#182744",
    "border": "#27436f",
    "text": "#f2f6ff",
    "muted": "#8fa1ba",
    "subtle": "#64748b",
    "accent": "#765cff",
    "accent_hover": "#947fff",
    "cyan": "#20d5ff",
}

BASE_MIN_WIDTH = 860
BASE_MIN_HEIGHT = 520
MIN_UI_SCALE = 0.25


def responsive_scale(width: int, height: int) -> float:
    return max(MIN_UI_SCALE, min(1.0, width / BASE_MIN_WIDTH, height / BASE_MIN_HEIGHT))


def scale_padding(root: tk.Misc, value: object, scale: float) -> int | tuple[int, ...]:
    try:
        parts = root.tk.splitlist(value)
    except (tk.TclError, TypeError):
        parts = (value,)
    scaled = tuple(max(0, round(float(str(part)) * scale)) for part in parts)
    return scaled[0] if len(scaled) == 1 else scaled


class TerminalManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window_icon: tk.PhotoImage | None = None
        icon_path = Path(__file__).parent / "assets" / "terminal-manager.png"
        try:
            self.window_icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self.window_icon)
        except tk.TclError:
            pass
        self.root.title(f"Terminal Manager {__version__}")
        saved_window_size = load_window_size()
        initial_width, initial_height = saved_window_size or (1180, 720)
        initial_width = min(max(BASE_MIN_WIDTH // 4, initial_width), self.root.winfo_screenwidth())
        initial_height = min(max(BASE_MIN_HEIGHT // 4, initial_height), self.root.winfo_screenheight())
        self.root.geometry(f"{initial_width}x{initial_height}")
        self.root.minsize(BASE_MIN_WIDTH // 4, BASE_MIN_HEIGHT // 4)
        self.root.configure(background=PALETTE["bg"])
        self.items: dict[str, tuple[ShellInfo | None, WindowInfo | None]] = {}
        self.windows: list[WindowInfo] = []
        self.activities: dict[str, ActivityState] = {}
        learned_protocol = load_learned_protocol()
        tracker_options = {
            "learned_prefixes": learned_protocol["active"],
            "learned_waiting_prefixes": learned_protocol["waiting"],
            "learned_static_prefixes": learned_protocol["static"],
        }
        self.activity_tracker = WindowActivityTracker(**tracker_options)
        self.tab_activity_tracker = WindowActivityTracker(**tracker_options)
        self.thermal_tracker = ThermalTracker()
        self.thermal_levels: dict[str, float] = {}
        self.tab_groups: dict[str, TabGroup] = {}
        self.tty_bindings = load_tty_bindings()
        self.tab_items: dict[str, tuple[TabGroup, int]] = {}
        self._tab_scan_result: list[TabGroup] | None = None
        self._tab_scan_thread: threading.Thread | None = None
        self._tab_group_misses: dict[str, int] = {}
        self.expanded_window_ids: set[str] = set()
        self._last_layout_rows: int | None = 0 if saved_window_size else None
        self._group_click_job: str | None = None
        self._suppress_group_release = False
        self.metric_highlight: str | None = None
        self.focused_item_id: str | None = None
        self._observed_active_item: str | None = None
        self._focus_clear_job: str | None = None
        self._focus_saved_tags: tuple[str, ...] | None = None
        self.refresh_job: str | None = None
        self.active_poll_job: str | None = None
        self.resize_job: str | None = None
        self.window_size_job: str | None = None
        self.ui_scale = 1.0
        self.pinned_window_id: str | None = None
        self._pinned_was_above = False
        self.search_var = tk.StringVar()
        self.thermal_enabled = tk.BooleanVar(value=True)
        previous_session = load_runtime_session()
        self._recovery_entries = list(previous_session["entries"]) if not previous_session["clean_shutdown"] else []
        self._recovery_index = 0
        self._recovery_before_ids: set[str] = set()
        self._recovery_poll_count = 0
        self._recovery_errors: list[str] = []
        self._recovery_restored_count = 0
        self._recovery_skipped_count = 0
        self._recovery_active = bool(self._recovery_entries)
        # Preserve the previous crash snapshot until recovery has completed.
        save_runtime_session(clean_shutdown=False, entries=self._recovery_entries)
        self.search_var.trace_add("write", lambda *_args: self.refresh())
        self._build_ui()
        self._capture_scalable_layout()
        self._thermal_background_widgets = self._collect_thermal_background_widgets()
        self.window_highlighter = WindowHighlighter(root)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Configure>", self._schedule_responsive_scale, add="+")
        self.refresh()
        self._poll_active_window()
        if self._recovery_active:
            self.root.after(350, self._restore_next_window)

    def _close(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        if self.active_poll_job is not None:
            self.root.after_cancel(self.active_poll_job)
            self.active_poll_job = None
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
            self.resize_job = None
        if self.window_size_job is not None:
            self.root.after_cancel(self.window_size_job)
            self.window_size_job = None
        if self._focus_clear_job is not None:
            self.root.after_cancel(self._focus_clear_job)
            self._focus_clear_job = None
        self._cancel_group_click()
        self._save_current_window_size()
        self.window_highlighter.hide()
        self._release_managed_pin()
        save_runtime_session(clean_shutdown=True, entries=[])
        self.root.destroy()

    def _build_ui(self) -> None:
        self._configure_styles()
        container = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 22))
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 18))
        brand = ttk.Frame(header, style="App.TFrame")
        brand.pack(side=tk.LEFT)
        brand_icon_path = Path(__file__).parent / "assets" / "terminal-manager-64.png"
        self.brand_icon_source = tk.PhotoImage(file=brand_icon_path)
        self.brand_icon_image = self.brand_icon_source
        self.logo = tk.Label(
            brand,
            image=self.brand_icon_image,
            background=PALETTE["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        self.logo.pack(side=tk.LEFT, padx=(0, 13))
        titles = ttk.Frame(brand, style="App.TFrame")
        titles.pack(side=tk.LEFT)
        ttk.Label(titles, text="Terminal Manager", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(titles, text="你的 Shell，一眼看清 · 一键抵达", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))

        header_actions = ttk.Frame(header, style="App.TFrame")
        header_actions.pack(side=tk.RIGHT)
        self.thermal_toggle = tk.Frame(header_actions, background=PALETTE["bg"], cursor="hand2")
        self.thermal_toggle.pack(side=tk.LEFT, padx=(0, 12))
        self.thermal_indicator = tk.Canvas(
            self.thermal_toggle,
            width=16,
            height=16,
            background=PALETTE["bg"],
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.thermal_indicator.pack(side=tk.LEFT)
        self.thermal_label = tk.Label(
            self.thermal_toggle,
            text="渲染",
            foreground=PALETTE["muted"],
            background=PALETTE["bg"],
            font=("Noto Sans CJK SC", 9),
            cursor="hand2",
        )
        self.thermal_label.pack(side=tk.LEFT, padx=(6, 0))
        for widget in (self.thermal_toggle, self.thermal_indicator, self.thermal_label):
            widget.bind("<Button-1>", lambda _event: self._toggle_thermal_rendering())
        self._draw_thermal_toggle()
        ttk.Button(header_actions, text="信号管理", style="Ghost.TButton", command=self.manage_signals).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(header_actions, text="登记窗口", style="Ghost.TButton", command=self.register_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(header_actions, text="↻  刷新", style="Accent.TButton", command=self.refresh).pack(side=tk.LEFT)

        dashboard = ttk.Frame(container, style="App.TFrame")
        dashboard.pack(fill=tk.X, pady=(0, 16))
        self.metric_values: dict[str, tk.Label] = {}
        self.metric_cards: dict[str, tk.Frame] = {}
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
            self.metric_cards[key] = card
            self._bind_metric_card(card, key)

        surface = tk.Frame(
            container,
            background=PALETTE["surface"],
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
        )
        surface.pack(fill=tk.BOTH, expand=True)
        # Keep the action footer in a dedicated, non-expanding row. The tree's
        # requested height grows with discovered terminals; when all three
        # regions used vertical pack geometry, that request could push the
        # footer (including "移除记录") below the visible surface.
        surface.grid_columnconfigure(0, weight=1)
        surface.grid_rowconfigure(1, weight=1)

        toolbar = tk.Frame(surface, background=PALETTE["surface"], padx=16, pady=13)
        toolbar.grid(row=0, column=0, sticky="ew")
        tk.Label(toolbar, text="Shell 工作区", foreground=PALETTE["text"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 11, "bold")).pack(side=tk.LEFT)
        tk.Label(toolbar, text="点击 ▸ 展开标签 · 双击条目进入窗口", foreground=PALETTE["muted"], background=PALETTE["surface"], font=("Noto Sans CJK SC", 9)).pack(side=tk.LEFT, padx=12)
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

        columns = ("name", "window", "cwd", "status", "last_change", "activity")
        table = ttk.Frame(surface, style="Surface.TFrame")
        table.grid(row=1, column=0, sticky="nsew", padx=1)
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
            "window": "窗口",
            "cwd": "目录",
            "status": "状态",
            "last_change": "时长",
            "activity": "识别依据",
        }
        widths = {"name": 205, "window": 225, "cwd": 265, "status": 110, "last_change": 125, "activity": 145}
        self._base_column_widths = dict(widths)
        for key in columns:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], minwidth=70, stretch=key == "window")
        self.scrollbar = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for status, color in STATUS_COLORS.items():
            self.tree.tag_configure(status, foreground=color)
        self.tree.tag_configure("even", background=PALETTE["surface"])
        self.tree.tag_configure("odd", background=PALETTE["surface_2"])
        self.tree.tag_configure("child", background="#0c1524")
        self.tree.tag_configure("metric_match", background="#2c265c", foreground="#ffffff")
        self.tree.tag_configure("focused_shell", background="#6557e8", foreground="#ffffff")
        self.tree.bind("<ButtonPress-1>", self._handle_tree_press)
        self.tree.bind("<Double-1>", self._handle_tree_double_click)
        self.tree.bind("<ButtonRelease-1>", self._handle_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self._handle_tree_selection)
        self.tree.bind("<Return>", lambda _event: self.focus_selected())

        footer = tk.Frame(surface, background=PALETTE["surface"], padx=16, pady=13)
        footer.grid(row=2, column=0, sticky="ew")
        actions = ttk.Frame(footer, style="Surface.TFrame")
        actions.pack(side=tk.LEFT)
        ttk.Button(actions, text="进入并高亮", style="Accent.TButton", command=self.focus_selected).pack(side=tk.LEFT)
        ttk.Button(actions, text="编辑记录", style="Ghost.TButton", command=self.rename_selected).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="学习信号", style="Ghost.TButton", command=self.learn_selected_signal).pack(side=tk.LEFT, padx=(0, 8))
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
        self.detail_accent = tk.Frame(detail_box, background=PALETTE["accent"], width=3)
        self.detail_accent.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
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

    def _capture_scalable_layout(self) -> None:
        self._scalable_fonts: list[tuple[tk.Widget, dict[str, object]]] = []
        self._scalable_geometry: list[tuple[tk.Widget, str, object, object]] = []
        self._scalable_internal: list[tuple[tk.Widget, str, object]] = []
        self._scalable_dimensions: list[tuple[tk.Widget, int, int]] = []

        def visit(widget: tk.Widget) -> None:
            try:
                value = widget.cget("font")
                if value:
                    self._scalable_fonts.append((widget, tkfont.Font(root=self.root, font=value).actual()))
            except tk.TclError:
                pass
            for option in ("padding", "padx", "pady"):
                try:
                    value = widget.cget(option)
                    if value not in ("", 0, "0"):
                        self._scalable_internal.append((widget, option, value))
                except tk.TclError:
                    pass
            if isinstance(widget, (tk.Canvas, tk.Frame)):
                try:
                    width, height = int(widget.cget("width")), int(widget.cget("height"))
                    if width or height:
                        self._scalable_dimensions.append((widget, width, height))
                except (tk.TclError, ValueError):
                    pass
            manager = widget.winfo_manager()
            if manager in {"pack", "grid"}:
                info = widget.pack_info() if manager == "pack" else widget.grid_info()
                self._scalable_geometry.append((widget, manager, info.get("padx", 0), info.get("pady", 0)))
            for child in widget.winfo_children():
                visit(child)

        visit(self.root)

    def _schedule_responsive_scale(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(60, self._apply_responsive_scale)
        if self.window_size_job is not None:
            self.root.after_cancel(self.window_size_job)
        self.window_size_job = self.root.after(350, self._save_current_window_size)

    def _save_current_window_size(self) -> None:
        if self.window_size_job is not None:
            try:
                self.root.after_cancel(self.window_size_job)
            except tk.TclError:
                pass
        self.window_size_job = None
        try:
            if self.root.state() == "normal":
                save_window_size(self.root.winfo_width(), self.root.winfo_height())
        except tk.TclError:
            pass

    def _apply_responsive_scale(self) -> None:
        self.resize_job = None
        scale = responsive_scale(self.root.winfo_width(), self.root.winfo_height())
        if abs(scale - self.ui_scale) < 0.015:
            return
        self.ui_scale = scale
        for widget, specification in self._scalable_fonts:
            try:
                size = max(2, round(abs(int(specification["size"])) * scale))
                styles = []
                if specification["weight"] == "bold":
                    styles.append("bold")
                if specification["slant"] == "italic":
                    styles.append("italic")
                if specification["underline"]:
                    styles.append("underline")
                if specification["overstrike"]:
                    styles.append("overstrike")
                widget.configure(font=(specification["family"], size, *styles))
            except (tk.TclError, ValueError, TypeError):
                continue
        for widget, manager, padx, pady in self._scalable_geometry:
            try:
                options = {"padx": scale_padding(self.root, padx, scale), "pady": scale_padding(self.root, pady, scale)}
                if manager == "pack":
                    widget.pack_configure(**options)
                else:
                    widget.grid_configure(**options)
            except tk.TclError:
                continue
        for widget, option, value in self._scalable_internal:
            try:
                widget.configure(**{option: scale_padding(self.root, value, scale)})
            except tk.TclError:
                continue
        for widget, width, height in self._scalable_dimensions:
            try:
                widget.configure(
                    width=max(1, round(width * scale)) if width else 0,
                    height=max(1, round(height * scale)) if height else 0,
                )
            except tk.TclError:
                continue
        self._configure_scaled_styles(scale)
        for key, width in self._base_column_widths.items():
            self.tree.column(key, width=max(18, round(width * scale)), minwidth=max(18, round(70 * scale)))
        divisor = max(1, min(4, round(1 / scale)))
        self.brand_icon_image = self.brand_icon_source.subsample(divisor, divisor)
        self.logo.configure(image=self.brand_icon_image)

    def _configure_scaled_styles(self, scale: float) -> None:
        size = lambda value: max(2, round(value * scale))
        self.style.configure("Title.TLabel", font=("Ubuntu", size(18), "bold"))
        self.style.configure("Subtitle.TLabel", font=("Noto Sans CJK SC", size(9)))
        self.style.configure("Accent.TButton", padding=(size(15), size(8)), font=("Noto Sans CJK SC", size(9), "bold"))
        self.style.configure("Ghost.TButton", padding=(size(14), size(8)), font=("Noto Sans CJK SC", size(9)))
        self.style.configure("Danger.TButton", padding=(size(14), size(8)), font=("Noto Sans CJK SC", size(9)))
        self.style.configure("Shell.Treeview", rowheight=max(11, round(43 * scale)), font=("Noto Sans CJK SC", size(9)))
        self.style.configure("Shell.Treeview.Heading", padding=(size(10), size(10)), font=("Noto Sans CJK SC", size(9), "bold"))

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        self.style = style
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
        style.map("Shell.Treeview", background=[], foreground=[])
        style.map("Shell.Treeview.Heading", background=[("active", PALETTE["surface_3"])])
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=PALETTE["accent"],
            troughcolor=PALETTE["surface"],
            borderwidth=0,
            relief="flat",
            arrowsize=0,
            width=8,
        )

    def refresh(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        try:
            self._refresh_once()
        except Exception as exc:
            # A periodic UI callback must always schedule its successor. Log
            # unexpected failures and keep the last rendered snapshot intact.
            print(f"Terminal Manager 刷新失败：{exc}", file=sys.stderr, flush=True)
            try:
                self.details.configure(text=f"刷新失败：{exc}；将在 2 秒后自动重试。")
            except tk.TclError:
                pass
        finally:
            if self.root.winfo_exists():
                self.refresh_job = self.root.after(2000, self.refresh)

    def _refresh_once(self) -> None:
        selected_shell_id = None
        selection = self.tree.selection()
        if selection:
            selected_shell_id = selection[0]
        scan_ok = False
        try:
            scanned_windows = list_windows()
            scanned_activities = self.activity_tracker.update(scanned_windows)
            self.windows = scanned_windows
            self.activities = scanned_activities
            self._harvest_tab_scan()
            self._request_tab_scan()
            error = ""
            scan_ok = True
        except X11Error as exc:
            # A transient wmctrl/xdotool failure must not turn every registered
            # task into an ended (red) row. Keep the last known-good snapshot
            # and try again on the next refresh.
            error = f"{exc}；已保留上一次有效状态，正在重试。"

        shells = load_shells()
        tty_cwds = terminal_tty_cwds()
        live_session_entries: list[dict[str, str]] = []

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

        # Persist every live registered window independently of search/filter
        # state. UI filtering must never remove an entry from the crash
        # recovery snapshot.
        for info, window, _activity, _status, _name in rows:
            if not info or not window:
                continue
            group = self.tab_groups.get(window.window_id)
            tab_key = f"tab:{group.selected.index}" if group else "main"
            cwd = self._directory_for(info, window, tab_key, tty_cwds)
            if not cwd:
                continue
            if info.cwd != cwd:
                info.cwd = cwd
                info.last_seen = time.time()
                save_shell(info)
            live_session_entries.append({
                "shell_id": info.shell_id,
                "name": info.name,
                "cwd": cwd,
                "window_id": window.window_id,
            })

        rows.sort(key=lambda row: activity_sort_key(row[2], row[3], row[4]))
        tab_signals = []
        for group in self.tab_groups.values():
            window = find_window(group.window_id, self.windows)
            if not window:
                continue
            for tab in group.tabs:
                tab_signals.append(tab_window_signal(window, tab))
        tab_activities = self.tab_activity_tracker.update(tab_signals)

        thermal_statuses = {
            window_id: activity.status for window_id, activity in self.activities.items()
        }
        for group in self.tab_groups.values():
            for tab in group.tabs:
                if tab.selected:
                    continue
                signal_id = tab.signal_id(group.window_id)
                tab_activity = tab_activities.get(signal_id)
                if tab_activity:
                    thermal_statuses[signal_id] = tab_activity.status
        self.thermal_levels = self.thermal_tracker.update(thermal_statuses)
        self.expanded_window_ids.intersection_update(self.tab_groups)

        for info, window, activity, status, name in rows:
            window_title = window.title if window else f"{info.window_id}（未找到）" if info else "窗口不存在"
            searchable = " ".join((name, status, STATUS_LABELS.get(status, ""), window_title)).lower()
            if query and query not in searchable:
                continue
            group = self.tab_groups.get(window.window_id) if window else None
            iid = f"group:{window.window_id}" if group else f"shell:{info.shell_id}" if info else f"window:{window.window_id}"
            tab_key = f"tab:{group.selected.index}" if group else "main"
            cwd = self._directory_for(info, window, tab_key, tty_cwds)
            self.items[iid] = (info, window)
            registered_prefix = "" if info else "未登记 · "
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    f"{'▾' if window and window.window_id in self.expanded_window_ids else '▸'}  {name}" if group else name,
                    f"GNOME Terminal · {len(group.tabs)} 个标签" if group else registered_prefix + window_title,
                    display_directory(cwd),
                    status_text(status),
                    age_text(activity),
                    signal_text(activity),
                ),
                tags=self._row_tags(
                    status,
                    row_index,
                    info is None,
                    window.window_id if window else "",
                    item_id=iid,
                    temperature=self.thermal_levels.get(window.window_id, 0.0) if window else 0.0,
                ),
            )
            row_index += 1
            if group and window and window.window_id in self.expanded_window_ids:
                for tab in group.tabs:
                    if tab.selected:
                        continue
                    child_id = f"tab:{window.window_id}:{tab.index}"
                    child_activity = tab_activities.get(tab.signal_id(window.window_id))
                    child_status = child_activity.status if child_activity else "static"
                    child_title = tab.title or f"标签 {tab.index + 1}"
                    child_cwd = self._directory_for(info, window, f"tab:{tab.index}", tty_cwds)
                    self.items[child_id] = (info, window)
                    self.tab_items[child_id] = (group, tab.index)
                    self.tree.insert(
                        "",
                        tk.END,
                        iid=child_id,
                        text="",
                        values=(
                            f"      └─  {child_title}",
                            f"同一窗口 · 标签 {tab.index + 1}",
                            display_directory(child_cwd),
                            status_text(child_status),
                            age_text(child_activity),
                            signal_text(child_activity),
                        ),
                        tags=self._row_tags(
                            child_status,
                            None,
                            info is None,
                            window.window_id,
                            item_id=child_id,
                            temperature=self.thermal_levels.get(tab.signal_id(window.window_id), 0.0),
                            child=True,
                        ),
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
        self._apply_thermal_theme(mean_temperature(self.thermal_levels))
        self._update_metric_cards()
        if error:
            self.details.configure(text=error)
        self._apply_focused_shell_highlight()
        item_to_select = selected_shell_id
        if item_to_select and self.tree.exists(item_to_select):
            self.tree.selection_set(item_to_select)
            self.tree.focus(item_to_select)
        if self.focused_item_id is None:
            self._sync_selected_style()
        self.update_details()
        self._adapt_window_height()
        if scan_ok and not self._recovery_active:
            save_runtime_session(clean_shutdown=False, entries=live_session_entries)

    def _restore_next_window(self) -> None:
        if self._recovery_index >= len(self._recovery_entries):
            self._finish_recovery()
            return
        entry = self._recovery_entries[self._recovery_index]
        live_ids = {window.window_id for window in self.windows}
        if entry["window_id"] in live_ids:
            self._recovery_skipped_count += 1
            self._recovery_index += 1
            self.root.after(0, self._restore_next_window)
            return
        directory, reason = validate_recovery_directory(entry["cwd"])
        if directory is None:
            self._record_recovery_error(entry, reason)
            self._recovery_index += 1
            self.root.after(0, self._restore_next_window)
            return
        self._recovery_before_ids = live_ids
        started, reason = launch_recovery_terminal(directory)
        if not started:
            self._record_recovery_error(entry, reason)
            self._recovery_index += 1
            self.root.after(0, self._restore_next_window)
            return
        self._recovery_poll_count = 0
        self.root.after(250, self._poll_recovered_window)

    def _poll_recovered_window(self) -> None:
        entry = self._recovery_entries[self._recovery_index]
        try:
            windows = list_windows()
        except X11Error:
            windows = []
        candidates = [window for window in windows if window.window_id not in self._recovery_before_ids]
        if candidates:
            window = candidates[-1]
            shell = next((item for item in load_shells() if item.shell_id == entry["shell_id"]), None)
            now = time.time()
            if shell is None:
                shell = ShellInfo(
                    shell_id=entry["shell_id"],
                    window_id=window.window_id,
                    shell_pid=0,
                    tty="",
                    name=entry["name"],
                    status="unbound",
                    status_detail="异常退出后已从恢复快照重建登记",
                    command="",
                    cwd=entry["cwd"],
                    foreground_pid=None,
                    process_state="",
                    registered_at=now,
                    last_seen=now,
                )
            else:
                shell.window_id = window.window_id
                shell.cwd = entry["cwd"]
                shell.status = "unbound"
                shell.status_detail = "异常退出后已按保存目录恢复"
                shell.last_seen = now
            save_shell(shell)
            self._recovery_restored_count += 1
            self._recovery_index += 1
            self.refresh()
            self.root.after(0, self._restore_next_window)
            return
        self._recovery_poll_count += 1
        if self._recovery_poll_count < 24:
            self.root.after(250, self._poll_recovered_window)
            return
        self._record_recovery_error(entry, "终端已启动，但未能在 6 秒内识别新窗口")
        self._recovery_index += 1
        self.root.after(0, self._restore_next_window)

    def _record_recovery_error(self, entry: dict[str, str], reason: str) -> None:
        message = f"恢复“{entry['name']}”失败：{reason}"
        self._recovery_errors.append(message)
        print(message, file=sys.stderr, flush=True)

    def _finish_recovery(self) -> None:
        self._recovery_active = False
        self.refresh()
        if self._recovery_errors:
            summary = f"已恢复 {self._recovery_restored_count} 个，跳过已存在 {self._recovery_skipped_count} 个。"
            self.details.configure(text=summary + "\n" + "；".join(self._recovery_errors))
        elif self._recovery_entries:
            self.details.configure(
                text=f"已恢复 {self._recovery_restored_count} 个异常结束前登记窗口，"
                f"跳过已存在 {self._recovery_skipped_count} 个。"
            )

    def _poll_active_window(self) -> None:
        """Track focus cheaply so reverse highlighting is independent of full refreshes."""
        self.active_poll_job = None
        try:
            active_item = item_id_for_window(self.items, active_window_id())
        except (X11Error, ValueError):
            active_item = None
        if active_item != self._observed_active_item:
            self._observed_active_item = active_item
            if active_item and self.tree.exists(active_item):
                self.tree.selection_set(active_item)
                self.tree.focus(active_item)
                self.tree.see(active_item)
                self._flash_workspace_item(active_item)
        self.active_poll_job = self.root.after(200, self._poll_active_window)

    def _directory_for(
        self,
        shell: ShellInfo | None,
        window: WindowInfo | None,
        tab_key: str,
        tty_cwds: dict[str, str],
    ) -> str:
        window_id = window.window_id if window else shell.window_id if shell else ""
        tty = self.tty_bindings.get(window_id, {}).get(tab_key, "")
        if tty in tty_cwds:
            return tty_cwds[tty]
        if shell and shell.tty in tty_cwds:
            return tty_cwds[shell.tty]
        return shell.cwd if shell and shell.cwd else ""

    def selected(self) -> tuple[str, ShellInfo | None, WindowInfo | None] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        iid = selection[0]
        shell, window = self.items[iid]
        return iid, shell, window

    def _handle_tree_selection(self, _event: tk.Event) -> None:
        self.update_details()
        if self.focused_item_id is None:
            self._sync_selected_style()

    def _sync_selected_style(self) -> None:
        selection = self.tree.selection()
        background = PALETTE["surface"]
        foreground = PALETTE["text"]
        if selection and self.tree.exists(selection[0]):
            for tag in self.tree.item(selection[0], "tags"):
                configured = self.tree.tag_configure(tag)
                background = configured.get("background") or background
                foreground = configured.get("foreground") or foreground
        self.style.map(
            "Shell.Treeview",
            background=[("selected", background)],
            foreground=[("selected", foreground)],
        )

    def _handle_tree_click(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        if self._suppress_group_release:
            self._suppress_group_release = False
            return
        if item_id.startswith("group:") and self.tree.identify_column(event.x) == "#1":
            bounds = self.tree.bbox(item_id, "name")
            if bounds and event.x - bounds[0] <= 38:
                self._schedule_group_click(lambda: self._toggle_group(item_id))
                return
            self._schedule_group_click(self.focus_selected)
            return
        if item_id in self.tab_items and self.tree.identify_region(event.x, event.y) == "cell":
            self.root.after_idle(self.focus_selected)
        elif item_id and self.tree.identify_column(event.x) == "#1" and self.tree.identify_region(event.x, event.y) == "cell":
            self.root.after_idle(self.focus_selected)

    def _handle_tree_press(self, event: tk.Event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        self._replay_clicked_row(item_id, event)
        if item_id.startswith("group:"):
            # Own every group-row mouse event so ttk's class-level double-click
            # binding can never toggle the item's open state behind our back.
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            return "break"
        return None

    def _handle_tree_double_click(self, event: tk.Event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        # Tk may route the second rapid press directly to <Double-1> instead
        # of the ordinary press binding, so replay explicitly here as well.
        self._replay_clicked_row(item_id, event)
        if item_id.startswith("group:") and self.tree.identify_column(event.x) == "#1":
            self._cancel_group_click()
            self._suppress_group_release = True
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.root.after_idle(lambda: self.focus_selected(pin=True))
            return "break"
        self.focus_selected(pin=True)
        return None

    def _replay_clicked_row(self, item_id: str, event: tk.Event) -> None:
        if not item_id or not self.tree.exists(item_id):
            return
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self._flash_workspace_item(item_id)

    def _schedule_group_click(self, callback) -> None:
        self._cancel_group_click()
        self._group_click_job = self.root.after(520, lambda: self._run_group_click(callback))

    def _run_group_click(self, callback) -> None:
        self._group_click_job = None
        callback()

    def _cancel_group_click(self) -> None:
        if self._group_click_job is not None:
            self.root.after_cancel(self._group_click_job)
            self._group_click_job = None

    def _toggle_group(self, item_id: str) -> None:
        if not self.tree.exists(item_id):
            return
        window_id = item_id.removeprefix("group:")
        if window_id in self.expanded_window_ids:
            self.expanded_window_ids.remove(window_id)
        else:
            self.expanded_window_ids.add(window_id)
        self._last_layout_rows = None
        self.refresh()

    def _bind_metric_card(self, widget: tk.Widget, key: str) -> None:
        widget.configure(cursor="hand2")
        widget.bind("<Button-1>", lambda _event, metric=key: self._set_metric_highlight(metric))
        for child in widget.winfo_children():
            self._bind_metric_card(child, key)

    def _set_metric_highlight(self, key: str) -> None:
        self.metric_highlight = None if self.metric_highlight == key else key
        self.refresh()

    def _update_metric_cards(self) -> None:
        temperature = visual_temperature(mean_temperature(self.thermal_levels)) if self.thermal_enabled.get() else 0.0
        surface = blend_color(PALETTE["surface"], HOT_ROW, temperature)
        selected_surface = blend_color("#2c265c", HOT_ROW, temperature)
        border = blend_color(PALETTE["border"], HOT_ROW, temperature)
        accent = blend_color(PALETTE["accent"], HOT_ACCENT, temperature)
        for key, card in self.metric_cards.items():
            selected = key == self.metric_highlight
            background = selected_surface if selected else surface
            card.configure(
                background=background,
                highlightbackground=accent if selected else border,
                highlightthickness=2 if selected else 1,
            )
            self._set_widget_background(card, background)

    def _set_widget_background(self, widget: tk.Widget, background: str) -> None:
        for child in widget.winfo_children():
            try:
                child.configure(background=background)
            except tk.TclError:
                pass
            self._set_widget_background(child, background)

    def _row_tags(
        self,
        status: str,
        row_index: int | None,
        unregistered: bool,
        window_id: str,
        *,
        item_id: str,
        temperature: float,
        child: bool = False,
    ) -> tuple[str, ...]:
        if metric_matches(self.metric_highlight, status, unregistered):
            return ("metric_match",)
        if self.thermal_enabled.get():
            heat_tag = f"heat:{item_id}"
            cold_background = "#0c1524" if child else PALETTE["surface_2"] if row_index is not None and row_index % 2 else PALETTE["surface"]
            self.tree.tag_configure(
                heat_tag,
                background=blend_color(cold_background, HOT_ROW, visual_temperature(temperature)),
                foreground=blend_color(
                    STATUS_COLORS.get(status, PALETTE["text"]),
                    "#ffffff",
                    visual_temperature(temperature),
                ),
            )
            return (heat_tag,)
        tags: list[str] = [status]
        if child:
            tags.append("child")
        elif row_index is not None:
            tags.append("even" if row_index % 2 == 0 else "odd")
        return tuple(tags)

    def _toggle_thermal_rendering(self) -> None:
        self.thermal_enabled.set(not self.thermal_enabled.get())
        self._draw_thermal_toggle()
        self.refresh()

    def _draw_thermal_toggle(self) -> None:
        self.thermal_indicator.delete("all")
        self.thermal_indicator.create_oval(2, 2, 14, 14, outline=PALETTE["muted"], width=1)
        if self.thermal_enabled.get():
            self.thermal_indicator.create_oval(6, 6, 10, 10, fill=PALETTE["muted"], outline="")

    def _apply_thermal_theme(self, project_temperature: float) -> None:
        enabled = self.thermal_enabled.get()
        temperature = visual_temperature(project_temperature) if enabled else 0.0
        themed = {
            key: blend_color(PALETTE[key], HOT_ROW, temperature)
            for key in ("bg", "surface", "surface_2", "surface_3", "border")
        }
        accent = blend_color(PALETTE["accent"], HOT_ACCENT, temperature)
        hover = blend_color(PALETTE["accent_hover"], "#ff5964", temperature)
        self.root.configure(background=themed["bg"])
        for widget, role in self._thermal_background_widgets:
            try:
                widget.configure(background=themed[role])
            except tk.TclError:
                pass
        self.logo.configure(background=accent)
        self.detail_accent.configure(background=accent)
        self._draw_thermal_toggle()
        self.style.configure("App.TFrame", background=themed["bg"])
        self.style.configure("Surface.TFrame", background=themed["surface"])
        self.style.configure("Title.TLabel", background=themed["bg"])
        self.style.configure("Subtitle.TLabel", background=themed["bg"])
        self.style.configure("Accent.TButton", background=accent)
        self.style.map("Accent.TButton", background=[("active", hover), ("pressed", accent)])
        self.style.configure("Ghost.TButton", background=themed["surface_2"])
        self.style.map("Ghost.TButton", background=[("active", themed["surface_3"]), ("pressed", themed["border"])])
        self.style.configure("Danger.TButton", background=themed["surface_2"])
        self.style.configure(
            "Shell.Treeview",
            background=themed["surface"],
            fieldbackground=themed["surface"],
        )
        self.style.configure("Shell.Treeview.Heading", background=themed["surface_3"])
        self.style.map("Shell.Treeview.Heading", background=[("active", themed["surface_3"])])
        self.style.configure("Dark.Vertical.TScrollbar", background=accent, troughcolor=themed["surface"])

    def _collect_thermal_background_widgets(self) -> list[tuple[tk.Widget, str]]:
        """Remember each Tk widget's cold palette role for repeatable theme updates."""
        roles_by_color = {PALETTE[key]: key for key in ("bg", "surface", "surface_2", "surface_3")}
        collected: list[tuple[tk.Widget, str]] = []
        pending = [self.root]
        while pending:
            parent = pending.pop()
            pending.extend(parent.winfo_children())
            if isinstance(parent, ttk.Widget) or parent is self.root:
                continue
            try:
                role = roles_by_color.get(str(parent.cget("background")))
            except tk.TclError:
                continue
            if role is not None:
                collected.append((parent, role))
        return collected

    def _adapt_window_height(
        self,
        *,
        force: bool = False,
        minimum_height: int | None = None,
    ) -> None:
        visible_rows = len(self.tree.get_children())
        visible_rows = max(1, visible_rows)
        if self.ui_scale < 0.99 or not layout_resize_allowed(self._last_layout_rows, force=force):
            # Background discovery must never override a size chosen by the
            # user. A None marker is set only for initial layout and explicit
            # triangle expansion/collapse.
            self._last_layout_rows = visible_rows
            self.tree.configure(height=visible_rows)
            self.root.update_idletasks()
            _first, last = self.tree.yview()
            if last < 1.0 and not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            elif last >= 1.0 and self.scrollbar.winfo_ismapped():
                self.scrollbar.pack_forget()
            return
        self._last_layout_rows = visible_rows
        desired_height = max(640, 455 + visible_rows * 43)
        current_y = self.root.winfo_y()
        maximum_height = max(520, self.root.winfo_screenheight() - current_y - 55)
        target_height = min(desired_height, maximum_height)
        if minimum_height is not None:
            # Expanding must never shrink the existing window. If there is no
            # room below, keep its size and let the list scroll instead.
            target_height = max(minimum_height, target_height)
        overflow = desired_height > maximum_height
        self.tree.configure(height=visible_rows)
        if overflow:
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        elif self.scrollbar.winfo_ismapped():
            self.scrollbar.pack_forget()
        width = max(BASE_MIN_WIDTH // 4, self.root.winfo_width())
        # A size-only geometry request leaves placement entirely untouched.
        # Reapplying winfo_x/y here is incorrect on decorated X11 windows:
        # Tk reports client coordinates while the window manager positions the
        # outer frame, producing a title-bar-sized downward jump.
        self.root.geometry(f"{width}x{target_height}")

    def focus_selected(self, *, pin: bool = False) -> None:
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
        self._flash_workspace_item(iid)
        self.root.update_idletasks()
        try:
            focus_window(window_id, shake=tab_target is None, sync=tab_target is None)
        except X11Error as exc:
            self._notice("无法进入终端", str(exc), kind="error")
            return
        if pin:
            self._pin_window(window_id)
        group = self.tab_groups.get(window_id)
        if tab_target:
            tab_key = f"tab:{tab_target[1]}"
        elif group:
            tab_key = f"tab:{group.selected.index}"
        else:
            tab_key = "main"

        tty = self.tty_bindings.get(window_id, {}).get(tab_key, "")
        if not can_highlight_tty(tty):
            tty = ""
        if not tty:
            self.details.configure(text="首次识别该标签，正在建立高亮关联…")
            self.root.update_idletasks()
            tty = probe_visible_tty(window_id) or ""
            if tty:
                self._remember_tty(window_id, tab_key, tty)
        if tty:
            self.window_highlighter.flash(tty)
        else:
            self.window_highlighter.hide()
            self.details.configure(text="未能自动识别该标签的 TTY；聚焦和震动仍然可用。")

    def _pin_window(self, window_id: str) -> None:
        if self.pinned_window_id == window_id:
            return
        self._release_managed_pin()
        was_above = window_is_above(window_id)
        try:
            pinned = was_above or set_window_above(window_id, True)
        except X11Error as exc:
            self.details.configure(text=f"窗口已聚焦，但置顶失败：{exc}")
            return
        if pinned:
            self.pinned_window_id = window_id
            self._pinned_was_above = was_above

    def _release_managed_pin(self) -> None:
        if self.pinned_window_id and not self._pinned_was_above:
            try:
                set_window_above(self.pinned_window_id, False)
            except X11Error:
                pass
        self.pinned_window_id = None
        self._pinned_was_above = False

    def _remember_tty(self, window_id: str, tab_key: str, tty: str) -> None:
        self.tty_bindings.setdefault(window_id, {})[tab_key] = tty
        save_tty_binding(window_id, tab_key, tty)

    def _apply_focused_shell_highlight(self) -> None:
        for item_id in self.items:
            if item_id == self.focused_item_id:
                self.tree.item(item_id, tags=("focused_shell",))

    def _flash_workspace_item(self, item_id: str, duration_ms: int = 1100) -> None:
        if self._focus_clear_job is not None:
            self.root.after_cancel(self._focus_clear_job)
        if self.focused_item_id and self._focus_saved_tags and self.tree.exists(self.focused_item_id):
            self.tree.item(self.focused_item_id, tags=self._focus_saved_tags)
        self.focused_item_id = item_id
        self._focus_saved_tags = tuple(self.tree.item(item_id, "tags")) if self.tree.exists(item_id) else None
        self._apply_focused_shell_highlight()
        self.style.map(
            "Shell.Treeview",
            background=[("selected", "#6557e8")],
            foreground=[("selected", "#ffffff")],
        )
        self._focus_clear_job = self.root.after(duration_ms, self._clear_workspace_highlight)

    def _clear_workspace_highlight(self) -> None:
        self._focus_clear_job = None
        if self.focused_item_id and self._focus_saved_tags and self.tree.exists(self.focused_item_id):
            self.tree.item(self.focused_item_id, tags=self._focus_saved_tags)
        self.focused_item_id = None
        self._focus_saved_tags = None
        self._sync_selected_style()

    def _harvest_tab_scan(self) -> None:
        if self._tab_scan_result is not None:
            scanned = {group.window_id: group for group in self._tab_scan_result}
            scanned_ids = set(scanned)
            live_windows = {window.window_id for window in self.windows}
            for window_id, old_group in self.tab_groups.items():
                if window_id in scanned or window_id not in live_windows:
                    self._tab_group_misses.pop(window_id, None)
                    continue
                misses = self._tab_group_misses.get(window_id, 0) + 1
                self._tab_group_misses[window_id] = misses
                if misses < 2:
                    scanned[window_id] = old_group
            for window_id in scanned_ids:
                self._tab_group_misses.pop(window_id, None)
            self.tab_groups = scanned
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
        if window_id and window_id == self.pinned_window_id:
            text += "\n📌 该终端由双击操作置顶；双击其他终端会转移置顶。"
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

    def learn_selected_signal(self) -> None:
        selected = self.selected()
        if not selected:
            self._notice("学习标题信号", "请先在 Shell 工作区中选择需要学习的终端窗口。")
            return
        _iid, shell, window = selected
        window_id = window.window_id if window else shell.window_id if shell else ""
        if not window_id:
            return

        def current_title() -> str | None:
            try:
                return window_title(window_id)
            except X11Error:
                return ""

        dialog = SignalLearningDialog(self.root, window_title=current_title, palette=PALETTE)
        if not dialog.result:
            return
        protocol = load_learned_protocol()
        for status, prefixes in dialog.result.items():
            for prefix in prefixes:
                assign_learned_signal(protocol, status, prefix)
        for tracker in (self.activity_tracker, self.tab_activity_tracker):
            tracker.learned_spinner_prefixes = set(protocol["active"])
            tracker.learned_waiting_prefixes = set(protocol["waiting"])
            tracker.learned_static_prefixes = set(protocol["static"])
        save_learned_protocol(protocol)
        recorded = sum(bool(values) for values in dialog.result.values())
        self.details.configure(text=f"已保存 {recorded} 个 Agent 状态；重启后仍然有效。")
        self.refresh()

    def manage_signals(self) -> None:
        dialog = SignalManagementDialog(self.root, protocol=load_learned_protocol(), palette=PALETTE)
        if dialog.result is None:
            return
        save_learned_protocol(dialog.result)
        for tracker in (self.activity_tracker, self.tab_activity_tracker):
            tracker.learned_spinner_prefixes = set(dialog.result["active"])
            tracker.learned_waiting_prefixes = set(dialog.result["waiting"])
            tracker.learned_static_prefixes = set(dialog.result["static"])
        self.details.configure(text="信号规则已更新；新的状态与温度处理立即生效。")
        self.refresh()

    def register_selected(self) -> None:
        selected = self.selected()
        if not selected:
            self._notice("登记窗口", "请先在 Shell 工作区中选择一个终端窗口。")
            return
        iid, shell, window = selected
        if iid in self.tab_items:
            self._notice("隐藏标签", "隐藏标签暂时沿用所属窗口的管理记录，请选择所属主窗口进行编辑。")
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
            self._notice("窗口不存在", "当前记录对应的终端窗口已经关闭。", kind="error")
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
        group = self.tab_groups.get(window.window_id)
        tab_key = f"tab:{group.selected.index}" if group else "main"
        tty_cwds = terminal_tty_cwds()
        captured_cwd = self._directory_for(shell, window, tab_key, tty_cwds)
        if not captured_cwd:
            try:
                focus_window(window.window_id, shake=False)
                tty = probe_visible_tty(window.window_id) or ""
            except X11Error:
                tty = ""
            if tty:
                self._remember_tty(window.window_id, tab_key, tty)
                captured_cwd = terminal_tty_cwds().get(tty, "")
        if shell is None and not captured_cwd:
            self._notice(
                "无法登记窗口",
                "未能确认该终端当前的工作目录，因此没有创建无法恢复的登记记录。请确认 xwd、ffmpeg 可用后重试。",
                kind="error",
            )
            return
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
                cwd=captured_cwd,
                foreground_pid=None,
                process_state="",
                registered_at=now,
                last_seen=now,
            )
        shell.name = name
        shell.window_id = window.window_id
        shell.status = "unbound"
        shell.status_detail = "Codex 状态由终端窗口标题识别"
        shell.command = ""
        shell.cwd = captured_cwd or shell.cwd
        shell.last_seen = now
        save_shell(shell)
        self.refresh()

    def remove_selected(self) -> None:
        selected = self.selected()
        if not selected:
            return
        _iid, shell, _window = selected
        if not shell:
            self._notice("未注册窗口", "该条目尚未登记，因此没有可移除的管理记录。")
            return
        dialog = ConfirmationDialog(self.root, title="移除记录", name=shell.name, palette=PALETTE)
        if dialog.result:
            remove_shell(shell.shell_id)
            self.refresh()

    def _notice(self, title: str, message: str, *, kind: str = "info") -> None:
        NoticeDialog(self.root, title=title, message=message, palette=PALETTE, kind=kind)

def status_text(status: str) -> str:
    return f"{STATUS_DOTS.get(status, '●')}  {STATUS_LABELS.get(status, status)}"


def display_directory(cwd: str) -> str:
    if not cwd:
        return "待识别"
    home = str(Path.home())
    return "~" + cwd[len(home) :] if cwd == home or cwd.startswith(home + "/") else cwd


def signal_text(activity: ActivityState | None) -> str:
    if not activity:
        return "窗口不可用"
    if activity.status == "waiting":
        return "明确等待提示"
    if activity.status == "active":
        if activity.prefix in CLAUDE_WORKING_PREFIXES:
            return "Claude 点动画"
        if activity.prefix in CODEX_SPINNER_PREFIXES:
            return "Codex 旋转动画"
        if activity.learned_prefix:
            return "自动学习动画"
        return "Agent 运行信号"
    return "未检测到 Agent 信号"


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


def metric_matches(metric: str | None, status: str, unregistered: bool) -> bool:
    if metric is None:
        return False
    if metric == "total":
        return True
    if metric == "waiting":
        return status == "waiting"
    if metric == "running":
        return status == "active"
    if metric == "idle":
        return status == "static"
    if metric == "unregistered":
        return unregistered
    return False


def layout_resize_allowed(last_layout_rows: int | None, *, force: bool = False) -> bool:
    """Resize only for initial layout or an explicit user layout action."""
    return force or last_layout_rows is None


def activity_explanation(activity: ActivityState) -> str:
    duration = activity.seconds_in_status
    if activity.status == "waiting":
        return f"等待用户：Codex 在窗口标题中显示“{activity.prefix}”，已等待 {duration:.1f} 秒。"
    if activity.status == "active":
        source = "自动学习到的动画前缀" if activity.learned_prefix else "Codex/Claude Code 标准运行前缀"
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
    if not os.environ.get(DETACHED_CHILD_ENV):
        probe = SingleInstance()
        if not probe.acquire():
            activate_existing()
            return
        probe.release()
        launch_detached()
        print("Terminal Manager 已在后台启动；现在可以关闭此终端。")
        return
    instance = SingleInstance()
    if not instance.acquire():
        activate_existing()
        return
    # A stable WM_CLASS lets GNOME associate this Tk window with
    # terminal-manager.desktop, so the running app can be pinned to the Dock.
    root = tk.Tk(className="TerminalManager")
    try:
        TerminalManagerApp(root)
    except X11Error as exc:
        root.withdraw()
        NoticeDialog(root, title="Terminal Manager 无法启动", message=str(exc), palette=PALETTE, kind="error")
        raise SystemExit(1) from exc
    try:
        root.mainloop()
    finally:
        instance.release()


if __name__ == "__main__":
    main()
