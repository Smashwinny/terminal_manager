from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .discovery import ShellCandidate
from .terminal_preview import set_tty_preview


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
        self.preview_tty: str | None = None
        self.hovered_index: int | None = None
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

        tk.Label(body, text="关联 Shell（悬停候选项，观察对应终端变为紫色）", background=palette["bg"], foreground=palette["muted"], font=("Noto Sans CJK SC", 9)).pack(anchor=tk.W)
        choices = ["仅记录名称，不监测状态"] + [candidate.label for candidate in candidates]
        list_frame = tk.Frame(body, background=palette["border"], padx=1, pady=1)
        list_frame.pack(fill=tk.X, pady=(6, 7))
        self.choice = tk.Listbox(
            list_frame,
            height=min(7, max(2, len(choices))),
            width=82,
            background=palette["surface_2"],
            foreground=palette["text"],
            selectbackground=palette["accent"],
            selectforeground="#ffffff",
            activestyle="none",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            exportselection=False,
            font=("Ubuntu Mono", 9),
        )
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.choice.yview, style="Dark.Vertical.TScrollbar")
        self.choice.configure(yscrollcommand=scrollbar.set)
        for value in choices:
            self.choice.insert(tk.END, value)
        selected_index = min(max(selected_index, 0), len(choices) - 1)
        self.choice.selection_set(selected_index)
        self.choice.see(selected_index)
        self.choice.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, ipady=3)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.choice.bind("<Motion>", self.preview_hovered_candidate)
        self.choice.bind("<Leave>", lambda _event: self.clear_preview())
        hint = (
            "移动鼠标时，对应终端会临时变成紫色；确认后单击该项再保存。"
            if candidates
            else "没有可安全预览的 Shell，只记录名称，不提供猜测式关联。"
        )
        tk.Label(body, text=hint, background=palette["bg"], foreground=palette["subtle"], font=("Noto Sans CJK SC", 8)).pack(anchor=tk.W)

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
        selection = self.choice.curselection()
        index = selection[0] if selection else 0
        candidate = self.candidates[index - 1] if index > 0 else None
        self.result = (name, candidate)
        self.clear_preview()
        self.window.destroy()

    def cancel(self) -> None:
        self.clear_preview()
        self.window.destroy()

    def preview_hovered_candidate(self, event: tk.Event) -> None:
        index = self.choice.nearest(event.y)
        bbox = self.choice.bbox(index)
        if not bbox or not (bbox[1] <= event.y <= bbox[1] + bbox[3]):
            self.clear_preview()
            return
        if index == self.hovered_index:
            return
        self.clear_preview()
        self.hovered_index = index
        self.choice.itemconfigure(index, background=self.palette["surface_3"])
        if index > 0:
            tty = self.candidates[index - 1].tty
            if set_tty_preview(tty, True):
                self.preview_tty = tty

    def clear_preview(self) -> None:
        if self.preview_tty:
            set_tty_preview(self.preview_tty, False)
            self.preview_tty = None
        if self.hovered_index is not None:
            try:
                self.choice.itemconfigure(self.hovered_index, background=self.palette["surface_2"])
            except tk.TclError:
                pass
            self.hovered_index = None
