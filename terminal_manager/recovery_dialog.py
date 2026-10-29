import tkinter as tk
from tkinter import ttk
from datetime import datetime
from .recovery_queue import LABELS


class RecoveryDialog:
    def __init__(self, parent, entries, palette):
        self.result = None
        window = tk.Toplevel(parent)
        window.title("恢复清单")
        window.configure(background=palette["bg"])
        window.transient(parent)
        ttk.Label(window, text="保活任务连接原进程；已关联 Codex 的记录打开原对话；其余只恢复目录。", style="Subtitle.TLabel").pack(padx=15, pady=12)
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=15)
        tree = ttk.Treeview(frame, columns=("name", "cwd", "mode", "state"), show="headings", height=14)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for column, label, width in (("name", "名称", 180), ("cwd", "工作目录", 300), ("mode", "恢复方式", 130), ("state", "状态", 180)):
            tree.heading(column, text=label)
            tree.column(column, width=width)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for index, entry in enumerate(entries):
            tree.insert("", tk.END, iid=str(index), values=(entry["name"], entry["cwd"], "连接原任务" if entry.get("protected_id") else "Codex 原对话" if entry.get("codex_session_id") else "仅打开目录", LABELS.get(entry.get('_state'), '未确认')))
        detail = ttk.Label(window, text="选择记录可查看恢复失败原因。", wraplength=780)
        detail.pack(padx=15, pady=8)
        tree.bind('<<TreeviewSelect>>', lambda event: detail.configure(text=entries[int(tree.selection()[0])].get('_error') or '没有记录错误。') if tree.selection() else None)
        def restore(directory_only=False):
            selected = tree.selection()
            if selected:
                self.result = dict(entries[int(selected[0])])
                if directory_only:
                    self.result.update(codex_session_id="", codex_cwd="", codex_home="")
                if directory_only and self.result.get("protected_id"):
                    # A new ordinary record preserves the original task identity.
                    self.result.update(shell_id=self.result["shell_id"] + "-directory", window_id="", protected_id="")
                window.destroy()
        ttk.Button(window, text="恢复选中项", command=restore).pack(pady=12)
        def skip():
            if tree.selection():
                self.result = {**entries[int(tree.selection()[0])], '_action': 'skip'}
                window.destroy()
        ttk.Button(window, text="跳过自动恢复（保留记录）", command=skip).pack(pady=4)
        ttk.Button(window, text="仅打开目录（不恢复进程）", command=lambda: restore(True)).pack(pady=(0, 12))
        tree.bind("<Double-1>", lambda event: restore())
        window.wait_visibility()
        window.grab_set()
        parent.wait_window(window)


class CodexSessionDialog:
    def __init__(self, parent, entries, palette):
        self.result = None
        window = tk.Toplevel(parent)
        window.title("关联准确的 Codex 对话")
        window.configure(background=palette["bg"])
        window.transient(parent)
        ttk.Label(window, text="选择原对话。这里只保存关联，不会启动任务或发送消息。", style="Subtitle.TLabel").pack(padx=15, pady=12)
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=15)
        tree = ttk.Treeview(frame, columns=("title", "time", "id"), show="headings", height=12, selectmode="browse")
        for column, label, width in (("title", "对话", 400), ("time", "更新时间", 150), ("id", "会话 ID", 290)):
            tree.heading(column, text=label)
            tree.column(column, width=width)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True)
        for index, entry in enumerate(entries):
            tree.insert("", tk.END, iid=str(index), values=(entry["label"], datetime.fromtimestamp(entry["updated_at"]).strftime("%Y-%m-%d %H:%M"), entry["id"]))
        def choose():
            if tree.selection():
                self.result = entries[int(tree.selection()[0])]
                window.destroy()
        ttk.Button(window, text="保存关联", command=choose).pack(pady=12)
        tree.bind("<Double-1>", lambda event: choose())
        window.wait_visibility()
        window.grab_set()
        parent.wait_window(window)
