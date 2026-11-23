#!/usr/bin/env python3
"""
文件进程工具 - 主程序入口
支持多种文件操作和测试功能
添加Windows多版本兼容性支持
"""

import os
import sys
import ctypes
import subprocess
import tkinter as tk
from tkinter import messagebox


def configure_console_output():
    """避免 Windows GBK 控制台因状态图标无法编码而中断启动。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (AttributeError, OSError, ValueError):
                pass


configure_console_output()

# 全局拖拽状态
HAS_DND = False
DND_FILES = 'DND_Files'

# 尝试导入 tkinterdnd2
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    root_class = TkinterDnD.Tk
    HAS_DND = True
    print("✅ tkinterdnd2 模块已成功加载")
except ImportError:
    HAS_DND = False
    root_class = tk.Tk
    print("❌ tkinterdnd2 模块加载失败，使用备用拖拽方案")
except Exception as e:
    print(f"❌ 加载拖拽模块时出错: {e}")
    HAS_DND = False
    root_class = tk.Tk

# 导出拖拽状态到其他模块
sys.modules['__main__'].HAS_DND = HAS_DND
sys.modules['__main__'].DND_FILES = DND_FILES


def is_admin():
    """检查是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """以管理员权限重新运行程序"""
    if sys.platform == 'win32':
        try:
            arguments = sys.argv[1:] if getattr(sys, 'frozen', False) else sys.argv
            parameters = subprocess.list2cmdline(arguments)
            launch_result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, parameters, None, 1
            )
            if launch_result <= 32:
                print(f"请求管理员权限失败，ShellExecuteW 返回: {launch_result}")
                return False
            return True
        except Exception as e:
            print(f"请求管理员权限失败: {e}")
            return False
    return False


def find_icon_file():
    """查找图标文件 - 优先使用程序目录下的 FileTestTool_icon.ico"""
    # 首先尝试当前工作目录
    current_dir = os.getcwd()
    icon_path = os.path.join(current_dir, "FileTestTool_icon.ico")

    if os.path.exists(icon_path):
        print(f"✅ 找到图标文件: {icon_path}")
        return icon_path

    # 尝试程序所在目录
    if getattr(sys, 'frozen', False):
        # 打包后的可执行文件
        base_path = os.path.dirname(sys.executable)
    else:
        # 脚本运行
        base_path = os.path.dirname(os.path.abspath(__file__))

    icon_path = os.path.join(base_path, "FileTestTool_icon.ico")
    if os.path.exists(icon_path):
        print(f"✅ 找到图标文件: {icon_path}")
        return icon_path

    # 尝试上级目录
    parent_dir = os.path.dirname(base_path)
    icon_path = os.path.join(parent_dir, "FileTestTool_icon.ico")
    if os.path.exists(icon_path):
        print(f"✅ 找到图标文件: {icon_path}")
        return icon_path

    # 尝试项目根目录
    project_root = os.path.dirname(parent_dir) if 'ui' in base_path or 'core' in base_path else base_path
    icon_path = os.path.join(project_root, "FileTestTool_icon.ico")
    if os.path.exists(icon_path):
        print(f"✅ 找到图标文件: {icon_path}")
        return icon_path

    print(f"❌ 未找到图标文件，搜索路径:")
    print(f"  {os.path.join(current_dir, 'FileTestTool_icon.ico')}")
    print(f"  {os.path.join(base_path, 'FileTestTool_icon.ico')}")
    print(f"  {os.path.join(parent_dir, 'FileTestTool_icon.ico')}")
    print(f"  {os.path.join(project_root, 'FileTestTool_icon.ico')}")

    return None


def check_windows_compatibility():
    """检查Windows兼容性并显示报告"""
    try:
        # 动态导入兼容性模块
        core_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core')
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)

        # 尝试导入
        try:
            from core.windows_compat import WindowsCompatibility
            compat = WindowsCompatibility()
            report = compat.get_os_compatibility_info()
            recommendations = []
            if not report['long_path_support']:
                recommendations.append(
                    "系统未启用长路径支持，超长路径相关功能可能受限"
                )

            print("=" * 60)
            print("Windows兼容性检查报告")
            print("=" * 60)

            print(f"操作系统: {report['os_name']}")
            print(f"具体版本: {report.get('specific_version', report['os_version'])}")
            print(f"架构: {report['python_arch']}")
            print(f"长路径支持: {'已启用' if report['long_path_support'] else '未启用'}")

            if recommendations:
                print("\n建议:")
                for rec in recommendations:
                    print(f"  • {rec}")

            print("=" * 60)

            # 返回兼容性信息
            return {
                'compatible': True,
                'os_info': report,
                'recommendations': recommendations
            }

        except ImportError as e:
            print(f"无法导入兼容性模块: {e}")
            return {'compatible': True, 'os_info': {}, 'recommendations': []}

    except Exception as e:
        print(f"兼容性检查失败: {e}")
        return {'compatible': True, 'os_info': {}, 'recommendations': []}


def main():
    """主函数"""
    # 显示启动信息
    print("=" * 60)
    print("文件进程工具 - 多版本Windows兼容性版本")
    print("=" * 60)

    # 检查Windows兼容性
    compat_result = check_windows_compatibility()

    # 检查管理员权限，如果不是管理员则请求提升权限
    if not is_admin():
        print("正在请求管理员权限...")
        if run_as_admin():
            sys.exit(0)
        else:
            result = messagebox.askyesno(
                "权限提示",
                "某些功能需要管理员权限才能正常工作。\n是否继续运行？"
            )
            if not result:
                sys.exit(0)

    try:
        # 添加当前目录到Python路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)

        # 添加核心模块路径
        core_dir = os.path.join(current_dir, 'core')
        if os.path.exists(core_dir):
            sys.path.insert(0, core_dir)

        # 添加UI模块路径
        ui_dir = os.path.join(current_dir, 'ui')
        if os.path.exists(ui_dir):
            sys.path.insert(0, ui_dir)

        # 添加工具模块路径
        utils_dir = os.path.join(current_dir, 'utils')
        if os.path.exists(utils_dir):
            sys.path.insert(0, utils_dir)

        print(f"Python路径: {sys.path}")
        print(f"拖拽功能状态: {'✅ 可用' if HAS_DND else '❌ 不可用'}")

        # 尝试导入主窗口
        try:
            from ui.main_window import FileProcessTool
        except ImportError as e:
            print(f"导入主窗口失败: {e}")
            # 尝试直接导入
            try:
                # 动态导入模块
                import importlib.util
                spec = importlib.util.spec_from_file_location("main_window", os.path.join(ui_dir, "main_window.py"))
                main_window_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(main_window_module)
                FileProcessTool = main_window_module.FileProcessTool
            except Exception as e2:
                messagebox.showerror("错误", f"无法加载主窗口模块: {e2}")
                sys.exit(1)

        # 创建主窗口
        print("正在创建主窗口...")
        root = root_class()

        # 设置程序图标 - 使用新的图标查找方法
        try:
            icon_path = find_icon_file()
            if icon_path and os.path.exists(icon_path):
                root.iconbitmap(icon_path)
                print(f"✅ 已设置程序图标: {icon_path}")
            else:
                print("⚠️ 未找到图标文件，使用默认图标")
        except Exception as e:
            print(f"⚠️ 设置图标失败: {e}")

        print("正在初始化应用程序...")
        app = FileProcessTool(root)
        print("✅ 应用程序初始化完成")

        root.mainloop()

    except Exception as e:
        print(f"❌ 程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        messagebox.showerror("错误", f"程序启动失败: {e}\n\n程序将退出。")
        sys.exit(1)


if __name__ == "__main__":
    main()
