from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .activity import SignalLearningSession

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
        self.result: set[str] | None = None
        self.window_title = window_title
        self.session = SignalLearningSession()
        self.window = tk.Toplevel(parent)
        self.window.title("学习标题信号")
        self.window.configure(background=palette["bg"])
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        body = tk.Frame(self.window, background=palette["bg"], padx=22, pady=20)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(body, text="学习标题动画", background=palette["bg"], foreground=palette["text"], font=("Noto Sans CJK SC", 15, "bold")).pack(anchor=tk.W)
        tk.Label(body, text="仅观察当前选中的窗口；请让目标 Agent 保持输出。", background=palette["bg"], foreground=palette["muted"], font=("Noto Sans CJK SC", 9)).pack(anchor=tk.W, pady=(4, 16))
        self.title_label = tk.Label(body, text="等待标题…", width=72, anchor=tk.W, background=palette["surface_2"], foreground=palette["text"], padx=12, pady=10, font=("Noto Sans CJK SC", 9))
        self.title_label.pack(fill=tk.X)
        self.progress_label = tk.Label(body, text="已采集 0 / 2 个不同前缀", background=palette["bg"], foreground=palette["subtle"], font=("Noto Sans CJK SC", 9))
        self.progress_label.pack(anchor=tk.W, pady=(12, 0))
        buttons = tk.Frame(body, background=palette["bg"])
        buttons.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(buttons, text="取消", style="Ghost.TButton", command=self.cancel).pack(side=tk.RIGHT)
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
        complete = self.session.observe(title)
        frames = "  ".join(sorted(self.session.prefixes)) or "尚未发现未知动画"
        self.progress_label.configure(text=f"已采集 {len(self.session.prefixes)} / 2 个不同前缀：{frames}")
        if complete:
            self.result = set(self.session.prefixes)
            self.window.after(450, self.window.destroy)
            return
        self.window.after(200, self._sample)

    def cancel(self) -> None:
        self.window.destroy()
