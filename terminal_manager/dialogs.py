from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .discovery import ShellCandidate


class RegistrationDialog:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        initial_name: str,
        candidates: list[ShellCandidate],
        selected_index: int = 0,
        palette: dict[str, str],
    ) -> None:
        self.result: tuple[str, ShellCandidate | None] | None = None
        self.candidates = candidates
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

        tk.Label(body, text="关联 Shell（用于状态检测）", background=palette["bg"], foreground=palette["muted"], font=("Noto Sans CJK SC", 9)).pack(anchor=tk.W)
        choices = ["仅记录名称，不监测状态"] + [candidate.label for candidate in candidates]
        self.choice = ttk.Combobox(body, values=choices, state="readonly", width=78, font=("Ubuntu Mono", 9))
        self.choice.current(min(max(selected_index, 0), len(choices) - 1))
        self.choice.pack(fill=tk.X, pady=(6, 7), ipady=4)
        tk.Label(body, text="提示：TTY、前台命令和目录可以帮助确认对应 Shell。", background=palette["bg"], foreground=palette["subtle"], font=("Noto Sans CJK SC", 8)).pack(anchor=tk.W)

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
        index = self.choice.current()
        candidate = self.candidates[index - 1] if index > 0 else None
        self.result = (name, candidate)
        self.window.destroy()

    def cancel(self) -> None:
        self.window.destroy()

