"""资源管理器右键菜单集成。只写入当前用户自己的注册表项。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

try:
    import winreg
except ImportError:  # pragma: no cover - 仅供非Windows环境导入模块
    winreg = None


REGISTRY_ROOT = r"Software\Classes\AllFilesystemObjects\shell\RichlinkGNSSCompare"
VERB_LABEL = "GNN文件对比"


def _require_windows():
    if winreg is None:
        raise OSError("右键菜单注册仅支持Windows系统")


def _application_command() -> str:
    """生成Explorer逐项传入选中路径的命令行。"""
    if getattr(sys, "frozen", False):
        prefix = subprocess.list2cmdline([sys.executable])
    else:
        main_file = Path(__file__).resolve().parents[1] / "main.py"
        interpreter = Path(sys.executable)
        pythonw = interpreter.with_name("pythonw.exe")
        if interpreter.name.lower() == "python.exe" and pythonw.exists():
            interpreter = pythonw
        prefix = subprocess.list2cmdline([str(interpreter), str(main_file)])
    # Windows静态多选菜单会为每个项目分别调用一次命令，%1才是当前项目。
    # main.py在短时间窗口内汇总两次调用，只启动一个实际对比窗口。
    return f'{prefix} --compare-item "%1"'


def registry_command() -> str:
    """公开命令文本，供界面提示和测试使用。"""
    return _application_command()


def register_shell_integration() -> None:
    """写入当前用户右键菜单，支持同时选择两个文件或文件夹。"""
    _require_windows()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_ROOT) as verb_key:
        winreg.SetValueEx(verb_key, "MUIVerb", 0, winreg.REG_SZ, VERB_LABEL)
        winreg.SetValueEx(verb_key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        icon_path = Path(sys.executable if getattr(sys, "frozen", False) else "")
        if not getattr(sys, "frozen", False):
            icon_path = Path(__file__).resolve().parents[1] / "photo" / "All_purpose_tool.ico"
        if icon_path.exists():
            winreg.SetValueEx(verb_key, "Icon", 0, winreg.REG_SZ, str(icon_path))
        with winreg.CreateKey(verb_key, r"command") as command_key:
            winreg.SetValue(command_key, "", winreg.REG_SZ, _application_command())


def _delete_tree(parent_key, name: str) -> None:
    try:
        with winreg.OpenKey(parent_key, name, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(key, child)
        winreg.DeleteKey(parent_key, name)
    except FileNotFoundError:
        pass


def remove_shell_integration() -> None:
    """只删除本工具创建的右键菜单项。"""
    _require_windows()
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\AllFilesystemObjects\shell",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        ) as shell_key:
            _delete_tree(shell_key, "RichlinkGNSSCompare")
    except FileNotFoundError:
        pass


def shell_integration_exists() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_ROOT):
            return True
    except FileNotFoundError:
        return False

