#!/usr/bin/env python3
"""可视化配置并启动 Windows Terminal PowerShell 分屏。"""

from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from terminal_split_cli import LAYOUTS, build_wt_args, find_shell, find_windows_terminal


LAYOUT_LABELS: Dict[int, Dict[str, str]] = {
    count: {key: f"{key}  —  {label}" for key, label in values.items()}
    for count, values in LAYOUTS.items()
}
WINDOW_TARGETS = {
    "新建独立窗口（推荐）": "new",
    "最近使用的窗口": "last",
    "编号 0 的窗口": "0",
}


class SplitTerminalApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PowerShell 分屏工作台")
        self.root.minsize(760, 500)
        self.root.geometry("900x650")

        self.count_var = tk.IntVar(value=4)
        self.layout_var = tk.StringVar()
        self.window_var = tk.StringVar(value="新建独立窗口（推荐）")
        self.shell_var = tk.StringVar(value="powershell.exe")
        self.terminal_var = tk.StringVar(value="")
        self.close_after_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="未启动。未选择目录的窗口将使用系统默认目录。")
        self.dir_vars: List[tk.StringVar] = []
        self.directory_cache: Dict[int, str] = {}
        self.rows_frame: Optional[ttk.Frame] = None

        self._build_ui()
        self._rebuild_layouts()
        self._rebuild_directory_rows()

    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        title = ttk.Label(root, text="PowerShell 分屏工作台", font=("Microsoft YaHei UI", 18, "bold"))
        title.grid(row=0, column=0, padx=24, pady=(20, 4), sticky="w")
        subtitle = ttk.Label(root, text="设置数量、布局和每个窗口的工作目录，然后一键打开 Windows Terminal。")
        subtitle.grid(row=1, column=0, padx=26, pady=(0, 16), sticky="w")

        main = ttk.Frame(root, padding=(24, 0, 24, 0))
        main.grid(row=2, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        settings = ttk.LabelFrame(main, text="分屏设置", padding=12)
        settings.grid(row=0, column=0, columnspan=2, sticky="ew")
        settings.columnconfigure(5, weight=1)

        ttk.Label(settings, text="窗口数量").grid(row=0, column=0, padx=(0, 8), sticky="w")
        count_box = ttk.Combobox(settings, textvariable=self.count_var, values=list(range(2, 7)), width=8, state="readonly")
        count_box.grid(row=0, column=1, padx=(0, 20), sticky="w")
        count_box.bind("<<ComboboxSelected>>", lambda _event: self._on_count_changed())

        ttk.Label(settings, text="布局").grid(row=0, column=2, padx=(0, 8), sticky="w")
        self.layout_box = ttk.Combobox(settings, textvariable=self.layout_var, width=30, state="readonly")
        self.layout_box.grid(row=0, column=3, padx=(0, 20), sticky="w")

        ttk.Label(settings, text="打开方式").grid(row=0, column=4, padx=(0, 8), sticky="w")
        ttk.Combobox(
            settings,
            textvariable=self.window_var,
            values=tuple(WINDOW_TARGETS),
            width=20,
            state="readonly",
        ).grid(row=0, column=5, sticky="w")

        dirs = ttk.LabelFrame(main, text="工作目录（按从左到右、从上到下编号；留空 = 系统默认目录）", padding=12)
        dirs.grid(row=2, column=0, columnspan=2, pady=(16, 0), sticky="nsew")
        dirs.columnconfigure(1, weight=1)
        dirs.rowconfigure(0, weight=1)
        self.rows_frame = ttk.Frame(dirs)
        self.rows_frame.grid(row=0, column=0, columnspan=3, sticky="nsew")
        self.rows_frame.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(main, text="高级设置", padding=10)
        options.grid(row=3, column=0, columnspan=2, pady=(14, 0), sticky="ew")
        options.columnconfigure(3, weight=1)
        ttk.Label(options, text="Shell").grid(row=0, column=0, padx=(0, 6), sticky="w")
        ttk.Entry(options, textvariable=self.shell_var, width=22).grid(row=0, column=1, padx=(0, 18), sticky="w")
        ttk.Label(options, text="wt.exe").grid(row=0, column=2, padx=(0, 6), sticky="w")
        ttk.Entry(options, textvariable=self.terminal_var).grid(row=0, column=3, padx=(0, 6), sticky="ew")
        ttk.Button(options, text="选择…", command=self.choose_terminal).grid(row=0, column=4, sticky="e")
        ttk.Checkbutton(options, text="启动后关闭配置窗口", variable=self.close_after_var).grid(
            row=1, column=0, columnspan=5, pady=(8, 0), sticky="w"
        )

        buttons = ttk.Frame(main)
        buttons.grid(row=4, column=0, columnspan=2, pady=(16, 0), sticky="ew")
        ttk.Button(buttons, text="预览命令", command=self.preview).pack(side="left")
        ttk.Button(buttons, text="启动分屏", command=self.launch).pack(side="right")

        status = ttk.Label(root, textvariable=self.status_var, relief="sunken", anchor="w", padding=(10, 5))
        status.grid(row=3, column=0, padx=24, pady=(14, 16), sticky="ew")

    def _on_count_changed(self) -> None:
        self._rebuild_layouts()
        self._rebuild_directory_rows()

    def _rebuild_layouts(self) -> None:
        count = int(self.count_var.get())
        labels = list(LAYOUT_LABELS[count].values())
        self.layout_box["values"] = labels
        current = self.layout_var.get()
        if current not in labels:
            self.layout_var.set(labels[0])

    def _rebuild_directory_rows(self) -> None:
        if self.rows_frame is None:
            return
        for child in self.rows_frame.winfo_children():
            child.destroy()
        for index, var in enumerate(self.dir_vars):
            self.directory_cache[index] = var.get()
        count = int(self.count_var.get())
        self.dir_vars = []
        for index in range(count):
            var = tk.StringVar(value=self.directory_cache.get(index, ""))
            self.dir_vars.append(var)
            ttk.Label(self.rows_frame, text=f"窗口 {index + 1}", width=10).grid(row=index, column=0, padx=(0, 10), pady=6, sticky="w")
            entry = ttk.Entry(self.rows_frame, textvariable=var)
            entry.grid(row=index, column=1, padx=(0, 8), pady=6, sticky="ew")
            ttk.Button(self.rows_frame, text="选择目录…", command=lambda v=var: self.choose_directory(v)).grid(row=index, column=2, padx=(0, 6), pady=6)
            ttk.Button(self.rows_frame, text="清空", command=lambda v=var: v.set("")).grid(row=index, column=3, pady=6)

    @staticmethod
    def choose_directory(var: tk.StringVar) -> None:
        selected = filedialog.askdirectory(title="选择该 PowerShell 窗口的工作目录")
        if selected:
            var.set(selected)

    def choose_terminal(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 Windows Terminal 可执行文件",
            filetypes=(("Windows Terminal", "wt.exe"), ("可执行文件", "*.exe")),
        )
        if selected:
            self.terminal_var.set(selected)

    def _get_wt_args(self) -> List[str]:
        count = int(self.count_var.get())
        label = self.layout_var.get()
        layout = next((key for key, text in LAYOUT_LABELS[count].items() if text == label), None)
        if layout is None:
            raise ValueError("请选择一个布局")

        directories: List[Optional[Path]] = []
        for index, var in enumerate(self.dir_vars, 1):
            raw = var.get().strip()
            if not raw:
                directories.append(None)
                continue
            path = Path(raw).expanduser()
            if not path.exists() or not path.is_dir():
                raise ValueError(f"窗口 {index} 的目录无效：{path}")
            directories.append(path.resolve())
        window = WINDOW_TARGETS.get(self.window_var.get(), "new")
        return build_wt_args(
            count,
            layout,
            directories,
            shell=self.shell_var.get().strip() or "powershell.exe",
            window=window,
        )

    def _terminal_path(self) -> Optional[str]:
        return find_windows_terminal(self.terminal_var.get().strip() or None)

    def preview(self) -> None:
        try:
            args = self._get_wt_args()
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc), parent=self.root)
            return
        terminal = self._terminal_path() or "wt.exe"
        command = subprocess.list2cmdline([terminal] + args)
        preview = tk.Toplevel(self.root)
        preview.title("启动命令预览")
        preview.geometry("850x300")
        text = tk.Text(preview, wrap="word", padx=10, pady=10)
        text.pack(fill="both", expand=True)
        text.insert("1.0", command)
        text.configure(state="disabled")

    def launch(self) -> None:
        try:
            args = self._get_wt_args()
        except ValueError as exc:
            messagebox.showerror("设置有误", str(exc), parent=self.root)
            return
        terminal = self._terminal_path()
        if not terminal:
            messagebox.showerror("找不到 Windows Terminal", "请先安装 Windows Terminal，或点击“选择…”指定 wt.exe。", parent=self.root)
            return
        shell = self.shell_var.get().strip() or "powershell.exe"
        if not find_shell(shell):
            messagebox.showerror("找不到 Shell", f"找不到可执行文件：{shell}", parent=self.root)
            return
        try:
            subprocess.Popen([terminal] + args)
        except OSError as exc:
            messagebox.showerror("启动失败", str(exc), parent=self.root)
            return
        self.status_var.set("已启动分屏 PowerShell，可在 Windows Terminal 中拖动分隔线调整大小。")
        if self.close_after_var.get():
            self.root.after(250, self.root.destroy)


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    SplitTerminalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
