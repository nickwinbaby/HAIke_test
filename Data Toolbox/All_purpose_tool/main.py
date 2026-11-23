"""数据分析综合工具箱启动入口。"""

from datetime import date
import sys

from config import APP_EXPIRY_DATE


def show_expiry_notice():
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showwarning("版本已到期", "请联系管理员获取新版本", parent=root)
    finally:
        root.destroy()


def main(args):
    if date.today() > APP_EXPIRY_DATE:
        show_expiry_notice()
        return 1

    from app import run
    from core.shell_compare_queue import collect_shell_selection

    if "--compare-item" in args:
        marker = args.index("--compare-item")
        item = args[marker + 1] if len(args) > marker + 1 else ""
        selection = collect_shell_selection(item) if item else None
        if selection:
            run(selection)
    elif "--compare" in args:
        marker = args.index("--compare")
        run(args[marker + 1:])
    else:
        run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

