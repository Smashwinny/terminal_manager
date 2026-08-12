from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .activity import split_status_prefix

class RegistrationDialog:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        initial_name: str,
        palette: dict[str, str],
    ) -> None:
        self.result: str | None = None
        self.palette = palette
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.configure(background=palette["bg"])
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        body = tk.Frame(self.window, background=palette["bg"], padx=22, pady=20)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="登记终端窗口", background=palette["bg"], foreground=palette["text"], font=("Noto Sans CJK SC", 15, "bold")).pack(anchor=tk.W)
        tk.Label(body, text="名称保存在管理器中，不会修改终端标题或 Shell。", background=palette["bg"], foreground=palette["muted"], font=("Noto Sans CJK SC", 9)).pack(anchor=tk.W, pady=(4, 16))

        tk.Label(body, text="用途名称", background=palette["bg"], foreground=palette["muted"], font=("Noto Sans CJK SC", 9)).pack(anchor=tk.W)
        self.name_var = tk.StringVar(value=initial_name)
        name_entry = tk.Entry(body, textvariable=self.name_var, width=72, background=palette["surface_2"], foreground=palette["text"], insertbackground=palette["text"], selectbackground=palette["accent"], relief=tk.FLAT, highlightthickness=1, highlightbackground=palette["border"], highlightcolor=palette["accent"], font=("Noto Sans CJK SC", 10))
        name_entry.pack(fill=tk.X, pady=(6, 15), ipady=7)

        tk.Label(
            body,
            text="状态将直接根据该窗口最近是否有画面输出自动判断，无需关联 Shell。",
            background=palette["bg"],
            foreground=palette["subtle"],
            font=("Noto Sans CJK SC", 8),
        ).pack(anchor=tk.W)

        buttons = tk.Frame(body, background=palette["bg"])
        buttons.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(buttons, text="取消", style="Ghost.TButton", command=self.cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="保存记录", style="Accent.TButton", command=self.save).pack(side=tk.RIGHT, padx=(0, 8))

        self.window.bind("<Escape>", lambda _event: self.cancel())
        self.window.bind("<Return>", lambda _event: self.save())
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.window.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.window.winfo_reqheight()) // 2)
        self.window.geometry(f"+{x}+{y}")
        name_entry.focus_set()
        name_entry.selection_range(0, tk.END)
        parent.wait_window(self.window)

    def save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            return
        self.result = name
        self.window.destroy()

    def cancel(self) -> None:
        self.window.destroy()


class SignalLearningDialog:
    def __init__(self, parent: tk.Misc, *, window_title, palette: dict[str, str]) -> None:
        self.result: dict[str, set[str]] | None = None
        self.window_title = window_title
        self.samples: dict[str, set[str]] = {"static": set(), "active": set(), "waiting": set()}
        self.current_title = ""
        self.window = tk.Toplevel(parent)
        self.window.title("学习标题信号")
        self.window.configure(background=palette["bg"])
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        body = tk.Frame(self.window, background=palette["bg"], padx=22, pady=20)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="学习 Agent 状态", background=palette["bg"], foreground=palette["text"], font=("Noto Sans CJK SC", 15, "bold")).pack(anchor=tk.W)
        tk.Label(body, text="切换目标窗口状态，再点击对应按钮记录当前标题。优先记录三个状态，至少两个即可保存。", background=palette["bg"], foreground=palette["muted"], font=("Noto Sans CJK SC", 9)).pack(anchor=tk.W, pady=(4, 16))
        self.title_label = tk.Label(body, text="等待标题…", width=72, anchor=tk.W, background=palette["surface_2"], foreground=palette["text"], padx=12, pady=10, font=("Noto Sans CJK SC", 9))
        self.title_label.pack(fill=tk.X)
        capture = tk.Frame(body, background=palette["bg"])
        capture.pack(fill=tk.X, pady=(12, 0))
        for status, label in (("static", "记录为静态"), ("active", "记录为输出中"), ("waiting", "记录为等待用户")):
            ttk.Button(capture, text=label, style="Ghost.TButton", command=lambda value=status: self.capture(value)).pack(side=tk.LEFT, padx=(0, 8))
        self.progress_label = tk.Label(body, text="尚未记录状态", background=palette["bg"], foreground=palette["subtle"], font=("Noto Sans CJK SC", 9))
        self.progress_label.pack(anchor=tk.W, pady=(12, 0))
        buttons = tk.Frame(body, background=palette["bg"])
        buttons.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(buttons, text="取消", style="Ghost.TButton", command=self.cancel).pack(side=tk.RIGHT)
        self.save_button = ttk.Button(buttons, text="保存协议", style="Accent.TButton", command=self.save, state=tk.DISABLED)
        self.save_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda _event: self.cancel())
        self.window.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.window.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.window.winfo_reqheight()) // 2)
        self.window.geometry(f"+{x}+{y}")
        self._sample()
        parent.wait_window(self.window)

    def _sample(self) -> None:
        title = self.window_title()
        if title is None:
            self.progress_label.configure(text="目标窗口已关闭，学习已停止")
            return
        self.title_label.configure(text=title or "（空标题）")
        self.current_title = title
        self.window.after(200, self._sample)

    def capture(self, status: str) -> None:
        prefix, _body = split_status_prefix(self.current_title)
        self.samples[status].add(prefix)
        recorded = [status for status, values in self.samples.items() if values]
        labels = {"static": "静态", "active": "输出中", "waiting": "等待用户"}
        self.progress_label.configure(text=f"已记录 {len(recorded)} / 3 个状态：{'、'.join(labels[value] for value in recorded)}")
        if len(recorded) >= 2:
            self.save_button.configure(state=tk.NORMAL)

    def save(self) -> None:
        if sum(bool(values) for values in self.samples.values()) < 2:
            return
        self.result = {status: set(values) for status, values in self.samples.items()}
        self.window.destroy()

    def cancel(self) -> None:
        self.window.destroy()
