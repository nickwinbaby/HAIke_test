"""
主窗口界面 - 文件进程工具
移除顶部兼容性信息栏
"""

import os
import sys
import tkinter as tk
from tkinter import ttk

# 尝试导入标签页
try:
    from ui.tab_widgets import (
        FileOpenTab, MultiLayerTab, LongPathTab,
        LargeFileTab, ProcessMemoryTab, DllInjectorTab,
        FilePermissionTab, HostModifyTab, FileChecksumTabWrapper,
        FileComparisonTabWrapper, TextGeneratorTab
    )
except ImportError as e:
    print(f"导入标签页失败: {e}")

    # 创建空的标签页作为备选
    class FileOpenTab:
        def __init__(self, parent):
            ttk.Label(parent, text="文件打开模式功能加载失败").pack()

    class MultiLayerTab:
        def __init__(self, parent):
            ttk.Label(parent, text="多层文件夹功能加载失败").pack()

    class LongPathTab:
        def __init__(self, parent):
            ttk.Label(parent, text="长路径生成功能加载失败").pack()

    class LargeFileTab:
        def __init__(self, parent):
            ttk.Label(parent, text="大文件生成功能加载失败").pack()

    class ProcessMemoryTab:
        def __init__(self, parent):
            ttk.Label(parent, text="进程内存占用功能加载失败").pack()

    class DllInjectorTab:
        def __init__(self, parent):
            ttk.Label(parent, text="DLL注入功能加载失败").pack()

    class FilePermissionTab:
        def __init__(self, parent):
            ttk.Label(parent, text="文件权限功能加载失败").pack()

    class HostModifyTab:
        def __init__(self, parent):
            ttk.Label(parent, text="Host修改功能加载失败").pack()

    class FileChecksumTabWrapper:
        def __init__(self, parent):
            ttk.Label(parent, text="文件计算校验功能加载失败").pack()

    class FileComparisonTabWrapper:
        def __init__(self, parent):
            ttk.Label(parent, text="文件对比功能加载失败").pack()

    class TextGeneratorTab:
        def __init__(self, parent):
            ttk.Label(parent, text="文本生成功能加载失败").pack()


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


class FileProcessTool:
    def __init__(self, root):
        self.root = root
        self.root.title("文件进程工具 V1.0")

        # 设置更大的窗口大小，确保所有内容可见
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        # 计算窗口位置和大小，使用更大的默认尺寸
        window_width = min(1400, screen_width - 40)
        window_height = min(900, screen_height - 40)  # 增加窗口高度
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(1300, 800)  # 进一步增加最小高度

        # 设置窗口图标
        self.set_window_icon()

        self.setup_ui()

    def set_window_icon(self):
        """设置窗口图标 - 使用新的图标查找方法"""
        try:
            icon_path = find_icon_file()
            if icon_path and os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
                print(f"✅ 已设置窗口图标: {icon_path}")
            else:
                print("⚠️ 未找到图标文件，使用默认图标")
        except Exception as e:
            print(f"⚠️ 设置窗口图标失败: {e}")

    def setup_ui(self):
        """设置用户界面 - 重新设计布局确保底部信息始终可见"""
        # 使用grid布局管理器，更精确控制空间分配
        self.root.grid_rowconfigure(0, weight=1)  # 主内容区域可扩展
        self.root.grid_rowconfigure(1, weight=0)  # 底部状态栏固定高度
        self.root.grid_columnconfigure(0, weight=1)

        # 创建主内容区域
        main_content = ttk.Frame(self.root)
        main_content.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)
        main_content.grid_rowconfigure(0, weight=1)
        main_content.grid_columnconfigure(0, weight=1)

        # 创建笔记本控件
        notebook = ttk.Notebook(main_content)
        notebook.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        # 创建各个标签页
        self.tabs = {}

        # 文件打开模式页面
        file_open_frame = ttk.Frame(notebook)
        file_open_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['file_open'] = FileOpenTab(file_open_frame)
        notebook.add(file_open_frame, text="文件打开模式")

        # 文本生成页面 - 新增的标签页
        text_generator_frame = ttk.Frame(notebook)
        text_generator_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['text_generator'] = TextGeneratorTab(text_generator_frame)
        notebook.add(text_generator_frame, text="文本生成")

        # 多层文件夹生成页面
        multi_layer_frame = ttk.Frame(notebook)
        multi_layer_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['multi_layer'] = MultiLayerTab(multi_layer_frame)
        notebook.add(multi_layer_frame, text="多层文件夹")

        # 长路径生成页面
        long_path_frame = ttk.Frame(notebook)
        long_path_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['long_path'] = LongPathTab(long_path_frame)
        notebook.add(long_path_frame, text="长路径生成")

        # 大文件生成页面
        large_file_frame = ttk.Frame(notebook)
        large_file_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['large_file'] = LargeFileTab(large_file_frame)
        notebook.add(large_file_frame, text="大文件生成")

        # 进程内存占用页面
        process_memory_frame = ttk.Frame(notebook)
        process_memory_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['process_memory'] = ProcessMemoryTab(process_memory_frame)
        notebook.add(process_memory_frame, text="进程内存占用")

        # 文件计算校验页面
        file_checksum_frame = ttk.Frame(notebook)
        file_checksum_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['file_checksum'] = FileChecksumTabWrapper(file_checksum_frame)
        notebook.add(file_checksum_frame, text="文件计算校验")

        # 文件对比页面
        file_comparison_frame = ttk.Frame(notebook)
        file_comparison_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['file_comparison'] = FileComparisonTabWrapper(file_comparison_frame)
        notebook.add(file_comparison_frame, text="文件对比")

        # DLL注入页面
        dll_injector_frame = ttk.Frame(notebook)
        dll_injector_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['dll_injector'] = DllInjectorTab(dll_injector_frame)
        notebook.add(dll_injector_frame, text="DLL注入")

        # 文件权限页面
        file_permission_frame = ttk.Frame(notebook)
        file_permission_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['file_permission'] = FilePermissionTab(file_permission_frame)
        notebook.add(file_permission_frame, text="文件权限")

        # Host修改页面
        host_modify_frame = ttk.Frame(notebook)
        host_modify_frame.pack(fill='both', expand=True, padx=20, pady=20)
        self.tabs['host_modify'] = HostModifyTab(host_modify_frame)
        notebook.add(host_modify_frame, text="Host修改")

        # 底部信息区域 - 使用固定高度的框架确保始终可见
        self.setup_bottom_status_bar()

        # 强制更新布局
        self.root.update_idletasks()

    def setup_bottom_status_bar(self):
        """设置底部状态栏 - 确保在任何窗口大小下都可见"""
        # 创建底部状态栏框架 - 使用固定高度
        status_bar_frame = ttk.Frame(self.root, height=30, relief='sunken', borderwidth=1)
        status_bar_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=(5, 10))
        status_bar_frame.grid_propagate(True)  # 阻止框架自动调整大小
        status_bar_frame.columnconfigure(0, weight=1)
        status_bar_frame.columnconfigure(1, weight=1)
        status_bar_frame.columnconfigure(2, weight=1)

        # 左侧：权限状态
        from utils.helpers import is_admin
        admin_status = "管理员权限" if is_admin() else "普通用户权限"
        admin_color = "green" if is_admin() else "red"

        left_frame = ttk.Frame(status_bar_frame)
        left_frame.grid(row=0, column=0, sticky='w', padx=15, pady=10)

        admin_icon = "🛡️" if is_admin() else "👤"
        admin_label = ttk.Label(left_frame,
                               text=f"{admin_icon} {admin_status}",
                               foreground=admin_color,
                               font=('Arial', 10, 'bold'))
        admin_label.pack(side='left')

        # 中间：作者信息
        center_frame = ttk.Frame(status_bar_frame)
        center_frame.grid(row=0, column=1, sticky='ns', pady=10)

        author_label = ttk.Label(center_frame,
                                text="@火绒安全测试分部 陶小睿",
                                foreground='darkblue',
                                font=('Arial', 10, 'bold'))
        author_label.pack()

        # 右侧：版本信息
        right_frame = ttk.Frame(status_bar_frame)
        right_frame.grid(row=0, column=2, sticky='e', padx=15, pady=10)

        version_label = ttk.Label(right_frame,
                                 text="🚀 版本 V1.0",
                                 foreground='purple',
                                 font=('Arial', 10, 'bold'))
        version_label.pack(side='right')

        # 添加分隔线在状态栏顶部
        separator = ttk.Separator(status_bar_frame, orient='horizontal')
        separator.grid(row=0, column=0, columnspan=3, sticky='ew', padx=5, pady=(0, 40))