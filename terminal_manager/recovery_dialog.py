import tkinter as tk
from tkinter import ttk


class RecoveryDialog:
    def __init__(self, parent, entries, palette):
        self.result = None
        window = tk.Toplevel(parent)
        window.title("恢复清单")
        window.configure(background=palette["bg"])
        window.transient(parent)
        window.grab_set()
        ttk.Label(window, text="保活任务连接原会话；普通记录只打开目录。外部关闭的窗口也会保留在清单中。", style="Subtitle.TLabel").pack(padx=15, pady=12)
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=15)
        tree = ttk.Treeview(frame, columns=("name", "cwd", "mode"), show="headings", height=14)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for column, label, width in (("name", "名称", 220), ("cwd", "工作目录", 370), ("mode", "恢复方式", 130)):
            tree.heading(column, text=label)
            tree.column(column, width=width)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for index, entry in enumerate(entries):
            tree.insert("", tk.END, iid=str(index), values=(entry["name"], entry["cwd"], "连接原任务" if entry.get("protected_id") else "仅打开目录"))
        def restore(directory_only=False):
            selected = tree.selection()
            if selected:
                self.result = dict(entries[int(selected[0])])
                if directory_only and self.result.get("protected_id"):
                    # A new ordinary record preserves the original task identity.
                    self.result.update(shell_id=self.result["shell_id"] + "-directory", window_id="", protected_id="")
                window.destroy()
        ttk.Button(window, text="恢复选中项", command=restore).pack(pady=12)
        ttk.Button(window, text="仅打开目录（不恢复进程）", command=lambda: restore(True)).pack(pady=(0, 12))
        tree.bind("<Double-1>", lambda event: restore())
        parent.wait_window(window)
