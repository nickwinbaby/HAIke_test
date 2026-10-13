#!/usr/bin/env python3
"""Windows Terminal multi-pane launcher.

Examples
--------
python terminal_split_cli.py --count 3 --layout left-large \
    --dir . --dir C:\\work --dir C:\\logs

Run without arguments for an interactive wizard.  Unspecified directories are
left untouched, so Windows Terminal/PowerShell uses its normal default folder.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


LAYOUTS = {
    2: {
        "columns": "左右并排",
        "rows": "上下并排",
    },
    3: {
        "row": "左右三列",
        "column": "上下三行",
        "left-large": "左大右两个小",
        "right-large": "右大左两个小",
    },
    4: {
        "grid": "十字型 2x2",
    },
    5: {
        "grid-3-2": "上三下二",
        "grid-2-3": "上二下三",
    },
    6: {
        "grid-3x2": "三列两行（推荐）",
    },
}


def layout_names(count: int) -> List[str]:
    return list(LAYOUTS[count])


def _is_file(path: Path) -> bool:
    """Return False for missing, broken, or inaccessible app aliases."""
    try:
        return path.is_file()
    except OSError:
        return False


def find_windows_terminal(explicit: Optional[str] = None) -> Optional[str]:
    """Find wt.exe from an explicit path, PATH, or common install aliases."""
    if explicit:
        candidate = Path(explicit).expanduser()
        if _is_file(candidate):
            return str(candidate.resolve())
        resolved = shutil.which(explicit)
        return resolved

    resolved = shutil.which("wt.exe") or shutil.which("wt")
    if resolved:
        return resolved

    candidates: List[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    if local_app_data:
        candidates += [
            Path(local_app_data) / "Microsoft" / "WindowsApps" / "wt.exe",
            Path(local_app_data) / "Microsoft" / "Windows Terminal" / "wt.exe",
        ]
    if program_files:
        candidates.append(Path(program_files) / "Windows Terminal" / "wt.exe")
    for candidate in candidates:
        if _is_file(candidate):
            return str(candidate)
    return None


def find_shell(shell: str) -> Optional[str]:
    """Resolve a shell name or path without invoking a command shell."""
    candidate = Path(shell).expanduser()
    if _is_file(candidate):
        return str(candidate.resolve())
    return shutil.which(shell)


def _pane_args(directory: Optional[Path], shell: str) -> List[str]:
    """Arguments that start one PowerShell pane."""
    args: List[str] = []
    if directory is not None:
        args += ["-d", str(directory)]

    # Windows Terminal's -d option already sets the process working directory.
    # Do not append a PowerShell `Set-Location; ...` command here: WT treats an
    # unescaped semicolon as its own pane-command separator, which would make
    # `Set-Location` look like an executable and produce 0x80070002.
    args += [shell, "-NoLogo", "-NoExit"]
    return args


def _split(
    orientation: str,
    directory: Optional[Path],
    shell: str,
    size: Optional[float] = None,
) -> List[str]:
    args = [";", "split-pane", orientation]
    if size is not None:
        args += ["--size", f"{size:g}"]
    return args + _pane_args(directory, shell)


def build_wt_args(
    count: int,
    layout: str,
    directories: Sequence[Optional[Path]],
    shell: str = "powershell.exe",
    window: str = "new",
) -> List[str]:
    """Build a Windows Terminal command line for the requested layout."""
    if count not in LAYOUTS:
        raise ValueError("窗口数量必须是 2 到 6")
    if layout not in LAYOUTS[count]:
        choices = ", ".join(layout_names(count))
        raise ValueError(f"{count} 个窗口不支持布局 {layout!r}，可选：{choices}")

    dirs = list(directories[:count]) + [None] * max(0, count - len(directories))
    args: List[str] = ["-w", window, "new-tab"] + _pane_args(dirs[0], shell)

    if count == 2:
        args += _split("-V" if layout == "columns" else "-H", dirs[1], shell)

    elif count == 3:
        if layout == "row":
            args += _split("-V", dirs[1], shell, size=2 / 3)
            args += _split("-V", dirs[2], shell, size=1 / 2)
        elif layout == "column":
            args += _split("-H", dirs[1], shell, size=2 / 3)
            args += _split("-H", dirs[2], shell, size=1 / 2)
        elif layout == "left-large":
            args += _split("-V", dirs[1], shell)
            args += _split("-H", dirs[2], shell)
        else:  # right-large
            # Visual order: pane 1 top-left, pane 2 bottom-left, pane 3 right.
            args += _split("-V", dirs[2], shell)
            args += [";", "move-focus", "left"]
            args += _split("-H", dirs[1], shell)

    elif count == 4:
        # Build bottom row first, then top row. This requires only one focus
        # move toward a full-width pane and avoids the ambiguous left/right
        # focus sequence that could occasionally produce a 1+3 layout.
        # Visual order remains: top-left, top-right, bottom-left, bottom-right.
        args += _split("-H", dirs[2], shell)
        args += _split("-V", dirs[3], shell)
        args += [";", "move-focus", "up"]
        args += _split("-V", dirs[1], shell)

    elif count == 5:
        if layout == "grid-3-2":
            # Visual order: panes 1-3 top, panes 4-5 bottom.
            args += _split("-H", dirs[3], shell)
            args += _split("-V", dirs[4], shell)
            args += [";", "move-focus", "up"]
            args += _split("-V", dirs[1], shell, size=2 / 3)
            args += _split("-V", dirs[2], shell, size=1 / 2)
        else:  # grid-2-3
            # Visual order: panes 1-2 top, panes 3-5 bottom.
            args += _split("-H", dirs[2], shell)
            args += [";", "move-focus", "up"]
            args += _split("-V", dirs[1], shell)
            args += [";", "move-focus", "down"]
            args += _split("-V", dirs[3], shell, size=2 / 3)
            args += _split("-V", dirs[4], shell, size=1 / 2)

    else:  # count == 6
        # Visual order: panes 1-3 top, panes 4-6 bottom.
        args += _split("-H", dirs[3], shell)
        args += _split("-V", dirs[4], shell, size=2 / 3)
        args += _split("-V", dirs[5], shell, size=1 / 2)
        args += [";", "move-focus", "up"]
        args += _split("-V", dirs[1], shell, size=2 / 3)
        args += _split("-V", dirs[2], shell, size=1 / 2)

    return args


def _format_command(args: Sequence[str]) -> str:
    # list2cmdline gives Windows-compatible quoting for paths and commands.
    return subprocess.list2cmdline(list(args))


def _print_layouts(count: int) -> None:
    print(f"{count} 个窗口可用布局：")
    for key, label in LAYOUTS[count].items():
        print(f"  {key:12} {label}")


def _parse_dirs(values: Iterable[str], count: int) -> List[Optional[Path]]:
    raw_values = list(values)
    if len(raw_values) > count:
        raise ValueError(f"最多只能为 {count} 个 pane 指定目录")
    result: List[Optional[Path]] = []
    for raw in raw_values:
        if not raw.strip():
            result.append(None)
            continue
        path = Path(raw).expanduser()
        if not path.exists():
            raise ValueError(f"目录不存在：{path}")
        if not path.is_dir():
            raise ValueError(f"不是目录：{path}")
        result.append(path.resolve())
    result.extend([None] * (count - len(result)))
    return result


def _interactive() -> Tuple[int, str, List[str]]:
    while True:
        try:
            count = int(input("窗口数量（2-6）：").strip())
            if count in LAYOUTS:
                break
        except ValueError:
            pass
        print("请输入 2 到 6。")

    _print_layouts(count)
    while True:
        layout = input("布局名称：").strip()
        if layout in LAYOUTS[count]:
            break
        print("布局名称无效，请从上面的列表选择。")

    print("依次输入每个 pane 的目录；直接回车表示使用系统默认目录。")
    dirs = [input(f"Pane {i} 目录：").strip() for i in range(1, count + 1)]
    return count, layout, dirs


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="创建 2-6 个可调 Windows PowerShell 分屏窗口")
    parser.add_argument("--count", type=int, choices=range(2, 7), help="窗口数量")
    parser.add_argument("--layout", help="布局名称；使用 --list-layouts 查看")
    parser.add_argument("--dir", dest="directories", action="append", default=[], help="pane 目录，可重复指定")
    parser.add_argument("--shell", default="powershell.exe", help="要启动的 shell（默认 powershell.exe）")
    parser.add_argument("--terminal", default=None, help="Windows Terminal 可执行文件路径，默认自动查找 wt.exe")
    parser.add_argument("--window", default="new", help="Windows Terminal 窗口目标（默认 new，新窗口）")
    parser.add_argument("--list-layouts", action="store_true", help="列出布局并退出；需同时指定 --count")
    parser.add_argument("--dry-run", action="store_true", help="只打印命令，不启动终端")
    args = parser.parse_args(argv)

    if args.list_layouts:
        if args.count is None:
            parser.error("--list-layouts 需要同时指定 --count")
        _print_layouts(args.count)
        return 0

    if args.count is None and not args.layout and not args.directories:
        count, layout, raw_dirs = _interactive()
    else:
        if args.count is None:
            parser.error("指定 --layout 或 --dir 时必须同时指定 --count")
        count = args.count
        layout = args.layout or ("grid-3x2" if count == 6 else "grid" if count == 4 else layout_names(count)[0])
        raw_dirs = args.directories

    try:
        directories = _parse_dirs(raw_dirs, count)
        wt_args = build_wt_args(count, layout, directories, shell=args.shell, window=args.window)
    except ValueError as exc:
        parser.error(str(exc))

    terminal = find_windows_terminal(args.terminal)
    if not terminal and not args.dry_run:
        print("找不到 wt.exe。请安装 Windows Terminal，或用 --terminal 指定可执行文件路径。", file=sys.stderr)
        return 2
    if not args.dry_run and not find_shell(args.shell):
        print(f"找不到 Shell 可执行文件：{args.shell}", file=sys.stderr)
        return 2

    print("将启动：")
    print(_format_command([terminal or "wt.exe"] + wt_args))
    if args.dry_run:
        return 0

    try:
        subprocess.Popen([terminal] + wt_args)
    except OSError as exc:
        print(f"启动 Windows Terminal 失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
