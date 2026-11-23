"""
各个标签页的界面组件
包含所有功能模块的标签页实现
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import time
import subprocess
import math

# 尝试导入核心模块
try:
    from core.file_operations import FileOperations
    from core.path_generator import PathGenerator
    from core.process_manager import ProcessManager
    from core.system_tools import SystemTools
    from core.dll_injector import DLLInjector
    from core.file_checksum import FileChecksumTab
    from core.file_comparison import FileComparisonTab
    from core.text_generator import TextGenerator
except ImportError as e:
    print(f"导入核心模块失败: {e}")

    # 创建空的基类作为备选
    class FileOperations:
        def open_file_with_mode(self, *args, **kwargs):
            raise Exception("文件操作功能未加载")

        def close_file(self, *args, **kwargs):
            return "文件关闭功能未加载"

        def close_all_files(self, *args, **kwargs):
            return "文件关闭功能未加载"

        def test_file_open(self, *args, **kwargs):
            return "文件测试功能未加载"

        def get_open_files_status(self, *args, **kwargs):
            return "文件状态功能未加载"

        def create_large_file(self, *args, **kwargs):
            yield 0

        def stop_creating_large_file(self, *args, **kwargs):
            pass

        def delete_large_file(self, *args, **kwargs):
            return True


    class PathGenerator:
        def generate_multi_layer_folders(self, *args, **kwargs):
            return "路径生成功能未加载"

        def generate_long_path(self, *args, **kwargs):
            return "长路径生成功能未加载"


    class ProcessManager:
        def create_multi_memory_processes(self, *args, **kwargs):
            return "多进程创建功能未加载"

        def kill_memory_process(self, *args, **kwargs):
            return "进程终止功能未加载"

        def get_running_processes(self, *args, **kwargs):
            return []


    class SystemTools:
        def set_file_permission(self, *args, **kwargs):
            return "权限设置功能未加载"

        def query_file_permission(self, *args, **kwargs):
            return "权限查询功能未加载"

        def modify_host_file(self, *args, **kwargs):
            return "Host修改功能未加载"


    class DLLInjector:
        def get_process_list(self, *args, **kwargs):
            return []

        def inject_dll_normal(self, *args, **kwargs):
            return "DLL注入功能未加载"

        def is_process_accessible(self, *args, **kwargs):
            return False

        def check_process_integrity(self, *args, **kwargs):
            return "未知"

        def is_signed_process_protected(self, *args, **kwargs):
            return False

        def get_process_info(self, *args, **kwargs):
            return None


    class FileChecksumTab:
        def __init__(self, parent):
            ttk.Label(parent, text="文件计算校验功能加载失败").pack()


    class FileComparisonTab:
        def __init__(self, parent):
            ttk.Label(parent, text="文件对比功能加载失败").pack()


    class TextGenerator:
        def generate_text(self, *args, **kwargs):
            raise Exception("文本生成功能未加载")

        def stop_generation(self, *args, **kwargs):
            pass

from utils.helpers import generate_random_name, generate_random_content, is_admin

# 检查 psutil 是否可用
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# 检查 win32 是否可用
try:
    import win32process
    import win32security

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class BaseTab:
    """标签页基类"""

    def __init__(self, parent):
        self.parent = parent
        try:
            self.file_ops = FileOperations()
            self.path_gen = PathGenerator()
            self.process_mgr = ProcessManager()
            self.sys_tools = SystemTools()
            self.dll_injector = DLLInjector()
            self.text_generator = TextGenerator()
        except Exception as e:
            print(f"初始化工具类失败: {e}")


class FileOpenTab(BaseTab):
    """文件打开模式标签页 - 完全修复编码问题"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        # 标题
        title_label = ttk.Label(self.parent, text="文件打开模式测试",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 说明信息
        info_text = """功能说明：
• 打开文件：以指定模式打开文件并保持打开状态
• 关闭文件：关闭指定模式的文件句柄
• 测试打开：测试文件是否可以以指定模式打开（不保持打开状态）
• 自动检测文件编码，支持文本文件和二进制文件
• 支持编码：UTF-8, GBK, Latin-1, CP1252, ISO-8859-1, UTF-16
• 独占打开模式：使用Windows API以独占模式打开文件"""
        info_label = ttk.Label(self.parent, text=info_text, justify='left',
                               foreground='green', font=('Arial', 9), wraplength=800)
        info_label.pack(pady=5, fill='x', padx=20)

        # 文件选择
        file_frame = ttk.Frame(self.parent)
        file_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(file_frame, text="选择文件:").pack(side='left')
        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var, width=50)
        file_entry.pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(file_frame, text="浏览", command=self.browse_file).pack(side='left')

        # 打开模式选择
        mode_frame = ttk.Frame(self.parent)
        mode_frame.pack(pady=10, fill='x', padx=20)

        self.open_mode = tk.StringVar(value="shared_read")
        ttk.Radiobutton(mode_frame, text="共享读", variable=self.open_mode,
                        value="shared_read").pack(side='left', padx=10)
        ttk.Radiobutton(mode_frame, text="共享写", variable=self.open_mode,
                        value="shared_write").pack(side='left', padx=10)
        ttk.Radiobutton(mode_frame, text="独占打开模式", variable=self.open_mode,
                        value="exclusive").pack(side='left', padx=10)

        # 操作按钮框架 - 第一行：打开和关闭
        btn_frame1 = ttk.Frame(self.parent)
        btn_frame1.pack(pady=10, fill='x', padx=20)

        ttk.Button(btn_frame1, text="打开文件", command=self.open_file_with_mode).pack(side='left', padx=5)
        ttk.Button(btn_frame1, text="关闭文件", command=self.close_file).pack(side='left', padx=5)
        ttk.Button(btn_frame1, text="关闭所有文件", command=self.close_all_files).pack(side='left', padx=5)

        # 操作按钮框架 - 第二行：测试功能
        btn_frame2 = ttk.Frame(self.parent)
        btn_frame2.pack(pady=10, fill='x', padx=20)

        ttk.Button(btn_frame2, text="测试打开", command=self.test_file_open).pack(side='left', padx=5)
        ttk.Button(btn_frame2, text="查看打开状态", command=self.show_open_status).pack(side='left', padx=5)

        # 结果显示 - 修改高度为原来的50%（从15减少到8）
        result_frame = ttk.Frame(self.parent)
        result_frame.pack(pady=10, fill='both', expand=True, padx=20)

        # 添加滚动文本框用于显示结果 - 高度从15减少到8
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, width=80, height=8)
        self.result_text.pack(fill='both', expand=True)
        self.result_text.config(state=tk.DISABLED)

    def browse_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            self.file_path_var.set(filename)

    def open_file_with_mode(self):
        file_path = self.file_path_var.get()
        if not file_path:
            self._show_result("❌ 错误：请选择文件")
            return

        if not os.path.exists(file_path) and self.open_mode.get() != "exclusive":
            self._show_result("❌ 错误：文件不存在")
            return

        mode = self.open_mode.get()
        try:
            result = self.file_ops.open_file_with_mode(file_path, mode)
            self._show_result(f"✅ {result}")
        except Exception as e:
            error_msg = f"❌ 打开文件失败: {str(e)}"
            self._show_result(error_msg)

    def close_file(self):
        file_path = self.file_path_var.get()
        if not file_path:
            self._show_result("❌ 错误：请选择文件")
            return

        mode = self.open_mode.get()
        try:
            result = self.file_ops.close_file(file_path, mode)
            self._show_result(result)
        except Exception as e:
            self._show_result(f"❌ 关闭文件失败: {str(e)}")

    def close_all_files(self):
        try:
            result = self.file_ops.close_all_files()
            self._show_result(result)
        except Exception as e:
            self._show_result(f"❌ 关闭所有文件失败: {str(e)}")

    def test_file_open(self):
        file_path = self.file_path_var.get()
        if not file_path:
            self._show_result("❌ 错误：请选择文件")
            return

        if not os.path.exists(file_path) and self.open_mode.get() != "exclusive":
            self._show_result("❌ 错误：文件不存在")
            return

        mode = self.open_mode.get()
        try:
            result = self.file_ops.test_file_open(file_path, mode)
            self._show_result(result)
        except Exception as e:
            self._show_result(f"❌ 测试失败: {str(e)}")

    def show_open_status(self):
        try:
            result = self.file_ops.get_open_files_status()
            self._show_result(result)
        except Exception as e:
            self._show_result(f"❌ 获取状态失败: {str(e)}")

    def _show_result(self, text):
        """在结果文本框中显示文本"""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, text)
        self.result_text.config(state=tk.DISABLED)
        self.result_text.see(tk.END)  # 滚动到底部


class MultiLayerTab(BaseTab):
    """多层文件夹生成标签页 - 修复字符类型选择问题，修复打开最后一层文件夹问题"""

    def __init__(self, parent):
        super().__init__(parent)
        self.last_generated_path = None  # 存储最后生成的路径
        self.last_generated_folder = None  # 新增：存储最后生成的文件夹路径（最后一层）
        self.setup_ui()

    def setup_ui(self):
        title_label = ttk.Label(self.parent, text="多层文件夹生成",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 层数设置
        layer_frame = ttk.Frame(self.parent)
        layer_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(layer_frame, text="文件夹层数:").pack(side='left')
        self.layer_count = tk.IntVar(value=3)
        layer_spinbox = ttk.Spinbox(layer_frame, from_=1, to=1000,  # 增加最大层数
                                    textvariable=self.layer_count, width=10)
        layer_spinbox.pack(side='left', padx=5)

        # 路径选择
        path_frame = ttk.Frame(self.parent)
        path_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(path_frame, text="基础路径:").pack(side='left')
        self.base_path_var = tk.StringVar(value=os.getcwd())
        path_entry = ttk.Entry(path_frame, textvariable=self.base_path_var,
                               width=50)  # 修复：变量名从path_path_frame改为path_frame
        path_entry.pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(path_frame, text="浏览", command=self.browse_directory).pack(side='left')

        # 字符类型选择框架
        char_type_frame = ttk.LabelFrame(self.parent, text="字符类型选择", padding=10)
        char_type_frame.pack(pady=10, fill='x', padx=20)

        # 默认勾选：英文字符、中文字符、数字字符、特殊字符
        self.include_english = tk.BooleanVar(value=True)
        self.include_chinese = tk.BooleanVar(value=True)
        self.include_digits = tk.BooleanVar(value=True)
        self.include_special = tk.BooleanVar(value=True)
        self.include_unicode = tk.BooleanVar(value=False)  # 修改：默认不勾选Unicode字符

        # 第一行
        row1_frame = ttk.Frame(char_type_frame)
        row1_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row1_frame, text="英文字符 (A-Z, a-z)",
                        variable=self.include_english).pack(side='left', padx=10)
        ttk.Checkbutton(row1_frame, text="中文字符 (常用汉字)",
                        variable=self.include_chinese).pack(side='left', padx=10)
        ttk.Checkbutton(row1_frame, text="数字字符 (0-9)",
                        variable=self.include_digits).pack(side='left', padx=10)

        # 第二行
        row2_frame = ttk.Frame(char_type_frame)
        row2_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row2_frame, text="特殊字符 (!@#$%^&等)",
                        variable=self.include_special).pack(side='left', padx=10)
        ttk.Checkbutton(row2_frame, text="Unicode字符 (扩展字符、表情符号等)",
                        variable=self.include_unicode).pack(side='left', padx=10)

        # 快速选择按钮
        quick_select_frame = ttk.Frame(char_type_frame)
        quick_select_frame.pack(fill='x', pady=5)

        ttk.Button(quick_select_frame, text="全选",
                   command=self.select_all_types).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="全不选",
                   command=self.deselect_all_types).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="仅英文数字",
                   command=self.select_english_digits).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="仅中文",
                   command=self.select_chinese_only).pack(side='left', padx=5)

        # 生成按钮框架
        generate_frame = ttk.Frame(self.parent)
        generate_frame.pack(pady=20, fill='x', padx=20)

        ttk.Button(generate_frame, text="生成多层文件夹和文件",
                   command=self.generate_multi_layer).pack(side='left', padx=5)

        # 新增：打开对应文件或文件夹按钮
        ttk.Button(generate_frame, text="打开最后一层文件夹",
                   command=self.open_last_generated_folder).pack(side='left', padx=5)

        # 结果显示
        self.result_var = tk.StringVar()
        result_label = ttk.Label(self.parent, textvariable=self.result_var,
                                 foreground='blue', wraplength=800)
        result_label.pack(pady=5, fill='x', padx=20)

    def select_all_types(self):
        """全选所有字符类型"""
        self.include_english.set(True)
        self.include_chinese.set(True)
        self.include_digits.set(True)
        self.include_special.set(True)
        self.include_unicode.set(True)

    def deselect_all_types(self):
        """全不选所有字符类型"""
        self.include_english.set(False)
        self.include_chinese.set(False)
        self.include_digits.set(False)
        self.include_special.set(False)
        self.include_unicode.set(False)

    def select_english_digits(self):
        """仅选择英文和数字"""
        self.include_english.set(True)
        self.include_chinese.set(False)
        self.include_digits.set(True)
        self.include_special.set(False)
        self.include_unicode.set(False)

    def select_chinese_only(self):
        """仅选择中文"""
        self.include_english.set(False)
        self.include_chinese.set(True)
        self.include_digits.set(False)
        self.include_special.set(False)
        self.include_unicode.set(False)

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.base_path_var.set(directory)

    def generate_multi_layer(self):
        base_path = self.base_path_var.get()
        layers = self.layer_count.get()

        if not base_path:
            messagebox.showerror("错误", "请选择基础路径")
            return

        # 检查是否至少选择了一种字符类型
        if not any([
            self.include_english.get(),
            self.include_chinese.get(),
            self.include_digits.get(),
            self.include_special.get(),
            self.include_unicode.get()
        ]):
            messagebox.showerror("错误", "请至少选择一种字符类型")
            return

        try:
            # 获取字符类型设置 - 确保正确传递
            char_types = {
                'include_english': self.include_english.get(),
                'include_chinese': self.include_chinese.get(),
                'include_digits': self.include_digits.get(),
                'include_special': self.include_special.get(),
                'include_unicode': self.include_unicode.get()
            }

            result = self.path_gen.generate_multi_layer_folders(base_path, layers, char_types)

            # 从结果中提取生成的路径
            if "路径:" in result:
                path_start = result.find("路径:") + 3
                path_end = result.find("\n", path_start)
                if path_end == -1:
                    path_end = len(result)
                self.last_generated_path = result[path_start:path_end].strip()

                # 更新：获取最后一层文件夹路径
                # 如果最后生成的是文件路径，获取其所在文件夹
                if os.path.isfile(self.last_generated_path):
                    self.last_generated_folder = os.path.dirname(self.last_generated_path)
                else:
                    # 如果是文件夹路径，直接使用
                    self.last_generated_folder = self.last_generated_path

            self.result_var.set(result)
        except Exception as e:
            messagebox.showerror("错误", f"生成多层文件夹失败: {str(e)}")

    def open_last_generated_folder(self):
        """打开最后生成文件夹的最后一层文件夹"""
        if not self.last_generated_folder:
            messagebox.showwarning("警告", "请先生成多层文件夹")
            return

        # 检查路径是否存在
        if not os.path.exists(self.last_generated_folder):
            messagebox.showerror("错误", f"文件夹不存在: {self.last_generated_folder}")
            return

        try:
            # 直接使用最后一层文件夹路径打开
            if os.name == 'nt':
                os.startfile(self.last_generated_folder)
            else:
                subprocess.Popen(['xdg-open', self.last_generated_folder])

            self.result_var.set(f"已打开最后一层文件夹: {self.last_generated_folder}")
        except Exception as e:
            # 如果直接打开失败，尝试使用备用方法
            try:
                subprocess.Popen(f'explorer "{self.last_generated_folder}"', shell=True)
                self.result_var.set(f"已打开最后一层文件夹: {self.last_generated_folder}")
            except Exception as e2:
                messagebox.showerror("错误", f"打开文件夹失败: {str(e)}\n备用方法也失败: {str(e2)}")


class LongPathTab(BaseTab):
    """长路径生成标签页 - 修复字符类型选择问题，修复Windows 11 25H2虚假失败报告问题，添加长路径支持控制"""

    def __init__(self, parent):
        super().__init__(parent)
        self.last_generated_path = None  # 存储最后生成的路径
        self.last_generated_folder = None  # 新增：存储最后生成的文件夹路径（最后一层）
        self.ignore_long_path_warning = False  # 是否忽略长路径警告
        self.setup_ui()

    def setup_ui(self):
        title_label = ttk.Label(self.parent, text="长路径生成 - Windows 11 25H2兼容版",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 系统长路径支持状态显示
        status_frame = ttk.Frame(self.parent)
        status_frame.pack(pady=5, fill='x', padx=20)

        self.long_path_status_var = tk.StringVar(value="正在检测系统长路径支持状态...")
        status_label = ttk.Label(status_frame, textvariable=self.long_path_status_var,
                                 font=('Arial', 10, 'bold'), foreground='blue')
        status_label.pack(side='left')

        # 刷新状态按钮调整到系统长路径支持后面
        ttk.Button(status_frame, text="刷新状态",
                   command=self.update_long_path_status).pack(side='left', padx=10)

        # 检查长路径支持状态
        self.update_long_path_status()

        # 路径长度设置
        length_frame = ttk.Frame(self.parent)
        length_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(length_frame, text="路径长度:").pack(side='left')
        self.path_length = tk.IntVar(value=200)
        self.length_spinbox = ttk.Spinbox(length_frame, from_=10, to=32767,
                                          textvariable=self.path_length, width=10,
                                          command=self.on_path_length_changed)
        self.length_spinbox.pack(side='left', padx=5)

        # 修改文案：添加Windows路径长度限制说明 - 根据要求修改文案
        warning_label = ttk.Label(length_frame,
                                  text="字符 (Windows系统中，默认的文件路径长度限制为260个字符。启用长路径后可将路径限制扩展至约32767个字符。)",
                                  foreground='black', font=('Arial', 9), wraplength=600)
        warning_label.pack(side='left', padx=5)

        # 添加红色字体说明：当前测试windows11 25H2实际可用路径为1000个字符左右
        red_warning_label = ttk.Label(length_frame,
                                     text="当前测试Windows 11 25H2实际可用路径为1000个字符左右",
                                     foreground='red', font=('Arial', 9, 'bold'))
        red_warning_label.pack(side='left', padx=5)

        # 路径选择
        path_frame = ttk.Frame(self.parent)
        path_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(path_frame, text="基础路径:").pack(side='left')
        self.base_path_var = tk.StringVar(value=os.getcwd())
        path_entry = ttk.Entry(path_frame, textvariable=self.base_path_var, width=50)
        path_entry.pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(path_frame, text="浏览", command=self.browse_directory).pack(side='left')

        # 字符类型选择框架
        char_type_frame = ttk.LabelFrame(self.parent, text="字符类型选择", padding=10)
        char_type_frame.pack(pady=10, fill='x', padx=20)

        # 默认勾选：英文字符、中文字符、数字字符、特殊字符
        self.include_english = tk.BooleanVar(value=True)
        self.include_chinese = tk.BooleanVar(value=True)
        self.include_digits = tk.BooleanVar(value=True)
        self.include_special = tk.BooleanVar(value=True)
        self.include_unicode = tk.BooleanVar(value=False)  # 修改：默认不勾选Unicode字符

        # 第一行
        row1_frame = ttk.Frame(char_type_frame)
        row1_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row1_frame, text="英文字符 (A-Z, a-z)",
                        variable=self.include_english).pack(side='left', padx=10)
        ttk.Checkbutton(row1_frame, text="中文字符 (常用汉字)",
                        variable=self.include_chinese).pack(side='left', padx=10)
        ttk.Checkbutton(row1_frame, text="数字字符 (0-9)",
                        variable=self.include_digits).pack(side='left', padx=10)

        # 第二行
        row2_frame = ttk.Frame(char_type_frame)
        row2_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row2_frame, text="特殊字符 (!@#$%^&等)",
                        variable=self.include_special).pack(side='left', padx=10)
        ttk.Checkbutton(row2_frame, text="Unicode字符 (扩展字符、表情符号等)",
                        variable=self.include_unicode).pack(side='left', padx=10)

        # 快速选择按钮
        quick_select_frame = ttk.Frame(char_type_frame)
        quick_select_frame.pack(fill='x', pady=5)

        ttk.Button(quick_select_frame, text="全选",
                   command=self.select_all_types).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="全不选",
                   command=self.deselect_all_types).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="仅英文数字",
                   command=self.select_english_digits).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="仅中文",
                   command=self.select_chinese_only).pack(side='left', padx=5)

        # 长路径支持控制框架 - 修改：移除复选框，直接显示三个按钮
        long_path_frame = ttk.LabelFrame(self.parent, text="Windows长路径支持控制", padding=10)
        long_path_frame.pack(pady=10, fill='x', padx=20)

        # 长路径支持控制按钮 - 移除复选框，直接显示三个按钮
        long_path_btn_frame = ttk.Frame(long_path_frame)
        long_path_btn_frame.pack()

        ttk.Button(long_path_btn_frame, text="启用长路径支持",
                   command=self.enable_long_path_support_with_prompt).pack(side='left', padx=5)
        ttk.Button(long_path_btn_frame, text="禁用长路径支持",
                   command=self.disable_long_path_support).pack(side='left', padx=5)

        # 忽略长路径警告复选框
        warning_frame = ttk.Frame(self.parent)
        warning_frame.pack(pady=5, fill='x', padx=20)

        self.ignore_warning_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(warning_frame,
                        text="忽略长路径支持警告 (即使未启用长路径支持也尝试生成)",
                        variable=self.ignore_warning_var,
                        command=self.on_ignore_warning_changed).pack(side='left')

        # 生成按钮框架
        generate_frame = ttk.Frame(self.parent)
        generate_frame.pack(pady=20, fill='x', padx=20)

        ttk.Button(generate_frame, text="生成长路径文件夹和文件",
                   command=self.generate_long_path).pack(side='left', padx=5)

        # 修改：打开生成文件夹按钮 - 修复路径提取问题
        ttk.Button(generate_frame, text="打开生成文件夹",
                   command=self.open_generated_folder).pack(side='left', padx=5)

        # 添加清空结果按钮
        ttk.Button(generate_frame, text="清空结果",
                   command=self.clear_results).pack(side='left', padx=5)

        # 结果显示区域 - 使用滚动文本框显示更多信息
        result_frame = ttk.Frame(self.parent)
        result_frame.pack(pady=10, fill='both', expand=True, padx=20)

        # 添加滚动文本框用于显示详细结果
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, width=80, height=12)
        self.result_text.pack(fill='both', expand=True)
        self.result_text.config(state=tk.DISABLED)

        # 为结果文本框添加上下文菜单（右键菜单）
        self.create_context_menu()

        # 绑定路径长度变化事件
        self.path_length.trace('w', self.on_path_length_changed_trace)

    def create_context_menu(self):
        """为结果文本框创建上下文菜单"""
        self.context_menu = tk.Menu(self.result_text, tearoff=0)
        self.context_menu.add_command(label="全选", command=self.select_all_text)
        self.context_menu.add_command(label="复制", command=self.copy_text)
        self.context_menu.add_command(label="清空", command=self.clear_results)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="保存到文件", command=self.save_results_to_file)

        # 绑定右键事件
        self.result_text.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        """显示上下文菜单"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def select_all_text(self):
        """选择所有文本"""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.tag_add(tk.SEL, "1.0", tk.END)
        self.result_text.mark_set(tk.INSERT, "1.0")
        self.result_text.see(tk.INSERT)
        self.result_text.config(state=tk.DISABLED)

    def copy_text(self):
        """复制选中的文本"""
        try:
            # 获取选中的文本
            selected_text = self.result_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            if selected_text:
                self.parent.clipboard_clear()
                self.parent.clipboard_append(selected_text)
        except:
            # 如果没有选中文本，复制全部文本
            self.result_text.config(state=tk.NORMAL)
            all_text = self.result_text.get(1.0, tk.END)
            self.parent.clipboard_clear()
            self.parent.clipboard_append(all_text)
            self.result_text.config(state=tk.DISABLED)

    def save_results_to_file(self):
        """保存结果到文件"""
        try:
            self.result_text.config(state=tk.NORMAL)
            content = self.result_text.get(1.0, tk.END)
            self.result_text.config(state=tk.DISABLED)

            if not content.strip():
                messagebox.showwarning("警告", "没有内容可保存")
                return

            file_path = filedialog.asksaveasfilename(
                title="保存结果到文件",
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
            )

            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.append_result_with_time(f"✅ 结果已保存到: {file_path}\n")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件失败: {str(e)}")

    def update_long_path_status(self):
        """更新长路径支持状态显示"""
        try:
            if hasattr(self, 'path_gen') and self.path_gen:
                long_path_enabled = self.path_gen.long_path_enabled
                if long_path_enabled:
                    self.long_path_status_var.set("✅ 系统长路径支持: 已启用")
                else:
                    self.long_path_status_var.set("❌ 系统长路径支持: 未启用")
            else:
                self.long_path_status_var.set("❌ 无法检测长路径支持状态")
        except Exception as e:
            print(f"更新长路径状态失败: {e}")
            self.long_path_status_var.set("❌ 检测长路径支持状态失败")

    def on_path_length_changed_trace(self, *args):
        """路径长度变化跟踪事件"""
        # 使用after延迟处理，避免频繁触发
        if hasattr(self, '_length_change_timer'):
            self.parent.after_cancel(self._length_change_timer)
        self._length_change_timer = self.parent.after(500, self.on_path_length_changed)

    def on_path_length_changed(self):
        """路径长度变化事件处理"""
        try:
            target_length = self.path_length.get()

            # 检查是否需要显示长路径支持警告
            if target_length > 300:
                # 检查系统长路径支持状态
                if hasattr(self, 'path_gen') and self.path_gen:
                    if not self.path_gen.long_path_enabled and not self.ignore_warning_var.get():
                        # 显示警告对话框
                        self.show_long_path_warning_dialog(target_length)
        except Exception as e:
            print(f"处理路径长度变化失败: {e}")

    def show_long_path_warning_dialog(self, target_length):
        """显示长路径支持警告对话框"""
        from tkinter import messagebox

        warning_msg = f"您设置的路径长度 ({target_length}) 超过了300字符。\n\n"
        warning_msg += "Windows 系统默认限制路径长度为260字符，需要启用长路径支持才能创建超过此限制的路径。\n\n"
        warning_msg += "是否要启用系统长路径支持？\n\n"
        warning_msg += "注意：\n"
        warning_msg += "1. 启用长路径支持需要管理员权限\n"
        warning_msg += "2. 启用后可能需要重启资源管理器或重启系统\n"
        warning_msg += "3. 如果不启用，路径长度将被限制为300字符\n"

        response = messagebox.askyesnocancel(
            "Windows长路径支持警告",
            warning_msg
        )

        if response is None:  # 用户点击了取消
            return
        elif response:  # 用户点击了"是"，尝试启用长路径支持
            success, message, need_restart = self.enable_long_path_support(show_result=False)
            if success:
                # 如果启用成功，显示重启提示
                if need_restart:
                    self.show_restart_prompt_dialog()
                else:
                    messagebox.showinfo("长路径支持", f"{message}\n\n路径长度限制已解除，可以生成超过300字符的路径。")
                # 更新状态显示
                self.update_long_path_status()
            else:
                # 启用失败，询问是否继续
                continue_response = messagebox.askyesno(
                    "启用长路径支持失败",
                    f"启用长路径支持失败: {message}\n\n是否继续生成路径？（路径长度将被限制为300字符）"
                )
                if not continue_response:
                    # 用户选择不继续，重置路径长度为300
                    self.path_length.set(300)
                else:
                    # 用户选择继续，设置忽略警告
                    self.ignore_warning_var.set(True)
        else:  # 用户点击了"否"，重置路径长度为300
            self.path_length.set(300)
            messagebox.showinfo("路径长度已调整", "已禁用长路径支持，路径长度已重置为300字符。")

    def enable_long_path_support_with_prompt(self):
        """启用长路径支持，并弹窗提示需要重启系统"""
        success, message, need_restart = self.enable_long_path_support(show_result=False)

        if success:
            if need_restart:
                # 显示重启提示弹窗，包含红色感叹号等重要提醒内容
                self.show_restart_prompt_dialog()
            else:
                messagebox.showinfo("长路径支持", message)
            # 更新状态显示
            self.update_long_path_status()
        else:
            messagebox.showerror("启用长路径支持失败", message)

    def enable_long_path_support(self, show_result=True):
        """启用系统长路径支持"""
        try:
            if hasattr(self, 'path_gen') and self.path_gen:
                success, message, need_restart = self.path_gen.enable_long_path_support()
                if success:
                    # 如果启用成功且需要重启，返回给调用者处理
                    if need_restart:
                        return True, message, True
                    else:
                        if show_result:
                            messagebox.showinfo("启用长路径支持", message)
                        # 更新状态显示
                        self.update_long_path_status()
                        return True, message, False
                else:
                    if show_result:
                        messagebox.showerror("启用长路径支持失败", message)
                    return False, message, False
            else:
                message = "路径生成器未初始化"
                if show_result:
                    messagebox.showerror("错误", message)
                return False, message, False
        except Exception as e:
            message = f"启用长路径支持失败: {str(e)}"
            if show_result:
                messagebox.showerror("错误", message)
            return False, message, False

    def disable_long_path_support(self):
        """禁用系统长路径支持"""
        try:
            if hasattr(self, 'path_gen') and self.path_gen:
                success, message, need_restart = self.path_gen.disable_long_path_support()
                if success:
                    if need_restart:
                        self.show_restart_prompt_dialog()
                    else:
                        messagebox.showinfo("禁用长路径支持", message)
                    # 更新状态显示
                    self.update_long_path_status()
                else:
                    messagebox.showerror("禁用长路径支持失败", message)
            else:
                messagebox.showerror("错误", "路径生成器未初始化")
        except Exception as e:
            messagebox.showerror("错误", f"禁用长路径支持失败: {str(e)}")

    def show_restart_prompt_dialog(self):
        """显示重启系统提示对话框 - 增加红色感叹号等重要提醒内容"""
        # 创建自定义对话框
        dialog = tk.Toplevel(self.parent)
        dialog.title("⚠️ 重要提示：需要重启系统")
        dialog.geometry("650x350")
        dialog.resizable(False, False)
        dialog.transient(self.parent)
        dialog.grab_set()

        # 设置窗口图标（如果有）
        try:
            dialog.iconbitmap(default='FileTestTool_icon.ico')
        except:
            pass

        # 使用红色感叹号图标和红色标题
        title_frame = ttk.Frame(dialog)
        title_frame.pack(pady=20, fill='x')

        # 红色感叹号图标
        warning_icon = ttk.Label(title_frame, text="⚠️", font=('Arial', 36), foreground='red')
        warning_icon.pack(side='left', padx=10)

        # 红色标题
        title_label = ttk.Label(title_frame, text="重要提示：需要重启系统",
                                font=('Arial', 16, 'bold'), foreground='red')
        title_label.pack(side='left')

        # 提示信息
        info_text = "Windows长路径支持已成功启用！\n\n"
        info_text += "⚠️ 重要提示：为了使长路径支持设置生效，需要重启系统。\n\n"
        info_text += "如果不重启系统，长路径支持可能无法正常工作。\n\n"
        info_text += "是否立即重启系统？"

        info_label = ttk.Label(dialog, text=info_text, wraplength=550,
                               justify='left', font=('Arial', 11))
        info_label.pack(pady=15, padx=20)

        # 按钮框架
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=25)

        def restart_system():
            """重启系统"""
            try:
                import subprocess
                subprocess.run(["shutdown", "/r", "/t", "10", "/c", "长路径支持已启用，系统将在10秒后重启"])
                dialog.destroy()
                messagebox.showinfo("系统重启", "系统将在10秒后重启，请保存所有工作。")
            except Exception as e:
                messagebox.showerror("重启失败", f"重启系统失败: {str(e)}\n\n请手动重启系统。")
                dialog.destroy()

        def later_restart():
            """稍后重启"""
            dialog.destroy()
            messagebox.showinfo("稍后重启", "请记得手动重启系统以使长路径支持生效。")

        # 重启按钮（红色背景）
        restart_btn = ttk.Button(button_frame, text="是，立即重启系统",
                                 command=restart_system, style='Accent.TButton')
        restart_btn.pack(side='left', padx=15)

        # 稍后重启按钮
        later_btn = ttk.Button(button_frame, text="否，稍后手动重启",
                               command=later_restart)
        later_btn.pack(side='left', padx=15)

        # 使对话框居中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        # 设置焦点到稍后按钮，避免误操作
        later_btn.focus_set()

    def on_ignore_warning_changed(self):
        """忽略警告复选框变化事件"""
        self.ignore_long_path_warning = self.ignore_warning_var.get()

    def select_all_types(self):
        """全选所有字符类型"""
        self.include_english.set(True)
        self.include_chinese.set(True)
        self.include_digits.set(True)
        self.include_special.set(True)
        self.include_unicode.set(True)

    def deselect_all_types(self):
        """全不选所有字符类型"""
        self.include_english.set(False)
        self.include_chinese.set(False)
        self.include_digits.set(False)
        self.include_special.set(False)
        self.include_unicode.set(False)

    def select_english_digits(self):
        """仅选择英文和数字"""
        self.include_english.set(True)
        self.include_chinese.set(False)
        self.include_digits.set(True)
        self.include_special.set(False)
        self.include_unicode.set(False)

    def select_chinese_only(self):
        """仅选择中文"""
        self.include_english.set(False)
        self.include_chinese.set(True)
        self.include_digits.set(False)
        self.include_special.set(False)
        self.include_unicode.set(False)

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.base_path_var.set(directory)

    def get_current_time_str(self):
        """获取当前时间字符串"""
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def append_result_with_time(self, text):
        """在结果文本框中追加带时间戳的文本"""
        self.result_text.config(state=tk.NORMAL)
        timestamp = self.get_current_time_str()
        self.result_text.insert(tk.END, f"[{timestamp}] {text}")
        self.result_text.config(state=tk.DISABLED)
        self.result_text.see(tk.END)  # 滚动到底部

    def clear_results(self):
        """清空结果文本框"""
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED)
        self.append_result_with_time("结果已清空\n")

    def generate_long_path(self):
        base_path = self.base_path_var.get()
        target_length = self.path_length.get()

        if not base_path:
            messagebox.showerror("错误", "请选择基础路径")
            return

        # 检查是否至少选择了一种字符类型
        if not any([
            self.include_english.get(),
            self.include_chinese.get(),
            self.include_digits.get(),
            self.include_special.get(),
            self.include_unicode.get()
        ]):
            messagebox.showerror("错误", "请至少选择一种字符类型")
            return

        # 显示生成中状态
        self.clear_results()
        self.append_result_with_time("正在生成长路径，请稍候...\n")

        # 特别提示Windows 11 25H2 300字符问题
        import platform
        system_info = platform.platform()
        if 'Windows-11' in system_info and '25H2' in system_info:
            self.append_result_with_time(f"检测到Windows 11 25H2系统，目标长度: {target_length}字符\n")
            if target_length >= 280 and target_length <= 320:
                self.append_result_with_time("⚠️ 注意: 正在处理Windows 11 25H2 300字符虚假失败报告问题...\n")
                self.append_result_with_time("系统可能会报告失败但实际上已成功生成，请检查目标文件夹\n")

        try:
            # 获取字符类型设置 - 确保正确传递
            char_types = {
                'include_english': self.include_english.get(),
                'include_chinese': self.include_chinese.get(),
                'include_digits': self.include_digits.get(),
                'include_special': self.include_special.get(),
                'include_unicode': self.include_unicode.get()
            }

            # 显示选择的字符类型
            char_types_str = []
            if char_types['include_english']:
                char_types_str.append("英文")
            if char_types['include_chinese']:
                char_types_str.append("中文")
            if char_types['include_digits']:
                char_types_str.append("数字")
            if char_types['include_special']:
                char_types_str.append("特殊字符")
            if char_types['include_unicode']:
                char_types_str.append("Unicode")

            self.append_result_with_time(f"使用的字符类型: {'、'.join(char_types_str)}\n")

            # 检查长路径支持状态
            if hasattr(self, 'path_gen') and self.path_gen:
                if not self.path_gen.long_path_enabled and target_length > 300 and not self.ignore_long_path_warning:
                    self.append_result_with_time("⚠️ 警告: 系统长路径支持未启用，路径长度将限制为300字符\n")
                    # 自动调整路径长度
                    target_length = min(target_length, 300)
                    self.path_length.set(300)

            # 调用路径生成器
            result = self.path_gen.generate_long_path(base_path, target_length, char_types,
                                                      self.ignore_long_path_warning)

            # 从结果中提取生成的路径 - 改进提取逻辑
            if "路径:" in result:
                path_start = result.find("路径:") + 3
                path_end = result.find("\n", path_start)
                if path_end == -1:
                    path_end = len(result)

                # 获取完整路径
                extracted_path = result[path_start:path_end].strip()

                # 处理路径中的省略号
                if extracted_path.endswith("..."):
                    # 如果路径被截断，尝试从结果中找到完整的路径
                    # 查找路径的起始部分
                    path_lines = result.split('\n')
                    for line in path_lines:
                        if "路径:" in line:
                            path_part = line.split("路径:")[1].strip()
                            if not path_part.endswith("..."):
                                extracted_path = path_part
                                break

                self.last_generated_path = extracted_path
                self.append_result_with_time(f"提取的完整路径: {extracted_path}\n")

                # 更新：获取最后一层文件夹路径
                # 如果最后生成的是文件路径，获取其所在文件夹
                if os.path.isfile(self.last_generated_path):
                    self.last_generated_folder = os.path.dirname(self.last_generated_path)
                    self.append_result_with_time(f"检测到文件路径，父文件夹: {self.last_generated_folder}\n")
                else:
                    # 如果是文件夹路径，直接使用
                    self.last_generated_folder = self.last_generated_path
                    self.append_result_with_time(f"检测到文件夹路径: {self.last_generated_folder}\n")

            # 显示完整结果
            self.append_result_with_time(f"{result}\n")

            # 额外验证：检查路径是否实际存在
            if self.last_generated_path and os.path.exists(self.last_generated_path):
                self.append_result_with_time("✅ 验证: 路径实际存在，生成成功！\n")
            elif self.last_generated_folder and os.path.exists(self.last_generated_folder):
                self.append_result_with_time("✅ 验证: 文件夹实际存在，生成成功！\n")
            elif self.last_generated_path:
                self.append_result_with_time("⚠️ 注意: 程序报告成功但路径未找到，可能是Windows 11 25H2的文件系统延迟\n")
                self.append_result_with_time("建议稍等几秒后手动检查目标文件夹\n")

        except Exception as e:
            error_msg = f"生成长路径报告失败: {str(e)}\n\n"
            error_msg += "可能的原因:\n"
            error_msg += "1. Windows 11 25H2文件系统延迟导致的虚假失败报告\n"
            error_msg += "2. 路径长度超过系统限制\n"
            error_msg += "3. 系统长路径支持未启用\n"
            error_msg += "4. 包含系统不允许的字符\n"
            error_msg += "5. 权限不足\n"
            error_msg += "6. 磁盘空间不足\n\n"
            error_msg += "建议:\n"
            error_msg += "1. 检查目标文件夹是否实际已生成\n"
            error_msg += "2. 尝试启用系统长路径支持\n"
            error_msg += "3. 尝试缩短路径长度\n"
            error_msg += "4. 减少特殊字符的使用\n"
            error_msg += "5. 以管理员权限运行程序\n"
            error_msg += "6. 检查目标磁盘空间\n"

            self.append_result_with_time(f"{error_msg}\n")

            # 即使报告失败，也检查是否实际生成了
            if base_path and os.path.exists(base_path):
                self.append_result_with_time(f"正在检查基础路径 {base_path} 下的新内容...\n")
                try:
                    # 列出基础路径下的最近修改的文件夹
                    import datetime
                    items = os.listdir(base_path)
                    dirs = [os.path.join(base_path, d) for d in items if os.path.isdir(os.path.join(base_path, d))]

                    if dirs:
                        # 按修改时间排序
                        dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                        recent_dirs = dirs[:3]  # 最近修改的3个文件夹

                        self.append_result_with_time("最近修改的文件夹:\n")
                        for d in recent_dirs:
                            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(d))
                            self.append_result_with_time(
                                f"  - {os.path.basename(d)} (修改于: {mtime.strftime('%H:%M:%S')})\n")
                except Exception as check_error:
                    self.append_result_with_time(f"检查失败: {check_error}\n")

    def open_generated_folder(self):
        """打开生成的文件夹 - 修复路径提取问题"""
        # 首先检查是否有生成的文件夹路径
        if not self.last_generated_folder:
            # 检查是否有生成的路径
            if not self.last_generated_path:
                messagebox.showwarning("警告", "请先生成长路径文件夹")
                return
            else:
                # 如果有文件路径，使用其父文件夹
                if os.path.isfile(self.last_generated_path):
                    self.last_generated_folder = os.path.dirname(self.last_generated_path)
                else:
                    self.last_generated_folder = self.last_generated_path

        # 记录要打开的路径
        self.append_result_with_time(f"尝试打开文件夹: {self.last_generated_folder}\n")

        # 检查路径是否存在
        if not os.path.exists(self.last_generated_folder):
            # 尝试检查路径是否被截断
            self.append_result_with_time(f"⚠️ 文件夹不存在: {self.last_generated_folder}\n")

            # 尝试从基础路径开始查找
            base_path = self.base_path_var.get()
            if base_path and os.path.exists(base_path):
                self.append_result_with_time(f"正在基础路径 {base_path} 中查找最近生成的文件夹...\n")

                try:
                    # 获取基础路径下所有文件夹
                    all_items = []
                    for root, dirs, files in os.walk(base_path, maxdepth=3):  # 限制深度，避免耗时过长
                        for d in dirs:
                            dir_path = os.path.join(root, d)
                            all_items.append((dir_path, os.path.getmtime(dir_path)))

                    # 按修改时间排序
                    all_items.sort(key=lambda x: x[1], reverse=True)

                    # 取最近修改的5个文件夹
                    recent_items = all_items[:5]

                    if recent_items:
                        self.append_result_with_time("最近修改的文件夹:\n")
                        import datetime
                        for item_path, mtime in recent_items:
                            time_str = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
                            self.append_result_with_time(f"  - {item_path} (修改于: {time_str})\n")

                        # 尝试打开最近修改的文件夹
                        most_recent_path = recent_items[0][0]
                        self.append_result_with_time(f"尝试打开最近修改的文件夹: {most_recent_path}\n")
                        self.last_generated_folder = most_recent_path
                except Exception as e:
                    self.append_result_with_time(f"查找文件夹失败: {str(e)}\n")

            # 再次检查路径是否存在
            if not os.path.exists(self.last_generated_folder):
                self.append_result_with_time("❌ 无法找到可打开的文件夹\n")
                messagebox.showerror("错误", f"文件夹不存在: {self.last_generated_folder}")
                return

        try:
            # 使用路径生成器的安全打开方法
            if hasattr(self, 'path_gen') and self.path_gen:
                success, message = self.path_gen.open_folder_safely(self.last_generated_folder)
                if success:
                    self.append_result_with_time(f"{message}\n")
                else:
                    # 尝试其他方法
                    self.append_result_with_time(f"尝试打开文件夹失败: {message}\n")

                    # 尝试直接打开
                    try:
                        if os.name == 'nt':
                            os.startfile(self.last_generated_folder)
                            self.append_result_with_time(f"已直接打开文件夹: {self.last_generated_folder}\n")
                        else:
                            subprocess.Popen(['xdg-open', self.last_generated_folder])
                            self.append_result_with_time(
                                f"已使用xdg-open打开文件夹: {self.last_generated_folder}\n")
                    except Exception as e:
                        # 尝试使用explorer命令
                        try:
                            subprocess.Popen(f'explorer "{self.last_generated_folder}"', shell=True)
                            self.append_result_with_time(
                                f"已使用explorer命令打开文件夹: {self.last_generated_folder}\n")
                        except Exception as e2:
                            self.append_result_with_time(f"备用方法也失败: {str(e2)}\n")
                            messagebox.showerror("错误", f"打开文件夹失败: {str(e)}\n备用方法也失败: {str(e2)}")
            else:
                messagebox.showerror("错误", "路径生成器未初始化")

        except Exception as e:
            self.append_result_with_time(f"打开文件夹时发生错误: {str(e)}\n")
            messagebox.showerror("错误", f"打开文件夹时发生错误: {str(e)}")


class LargeFileTab(BaseTab):
    """大文件生成标签页 - 增加DOC、DOCX、XLS、XLSX、PPT、PPTX格式支持"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()
        self.current_file_path = None
        self.creating_thread = None
        self.stop_creating = False

    def setup_ui(self):
        """设置用户界面"""
        title_label = ttk.Label(self.parent, text="大文件生成",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 文件大小设置
        size_frame = ttk.Frame(self.parent)
        size_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(size_frame, text="文件大小:").pack(side='left')
        self.file_size = tk.IntVar(value=10)
        size_spinbox = ttk.Spinbox(size_frame, from_=1, to=10000,
                                   textvariable=self.file_size, width=10)
        size_spinbox.pack(side='left', padx=5)
        ttk.Label(size_frame, text="MB").pack(side='left')

        # 文件格式选择 - 增加新格式
        format_frame = ttk.Frame(self.parent)
        format_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(format_frame, text="文件格式:").pack(side='left')
        self.file_format = tk.StringVar(value="exe")  # 默认exe格式

        # 创建格式选择下拉菜单 - 增加新格式
        formats = [
            ("EXE文件", "exe"),
            ("ZIP压缩包", "zip"),
            ("RAR压缩包", "rar"),
            ("MP3音频", "mp3"),
            ("MP4视频", "mp4"),
            ("PDF文档", "pdf"),
            ("Word文档 (DOC)", "doc"),
            ("Word文档 (DOCX)", "docx"),
            ("Excel表格 (XLS)", "xls"),
            ("Excel表格 (XLSX)", "xlsx"),
            ("PowerPoint (PPT)", "ppt"),
            ("PowerPoint (PPTX)", "pptx"),
            ("DAT数据文件", "dat")
        ]

        format_combo = ttk.Combobox(format_frame, textvariable=self.file_format,
                                    values=[f[0] for f in formats], state="readonly", width=20)
        format_combo.pack(side='left', padx=5)

        # 设置格式映射
        self.format_mapping = {f[0]: f[1] for f in formats}
        self.extension_mapping = {f[1]: f[0].split(' ')[0].lower() for f in formats}

        # 文件路径
        file_path_frame = ttk.Frame(self.parent)
        file_path_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(file_path_frame, text="文件路径:").pack(side='left')
        self.file_path_var = tk.StringVar()
        # 根据选择的格式设置默认文件名 - 修改：默认扩展名为exe
        self._update_default_filename()
        file_entry = ttk.Entry(file_path_frame, textvariable=self.file_path_var, width=50)
        file_entry.pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(file_path_frame, text="浏览", command=self.browse_file).pack(side='left')

        # 绑定格式变化事件
        self.file_format.trace('w', self._on_format_changed)

        # 按钮框架
        btn_frame = ttk.Frame(self.parent)
        btn_frame.pack(pady=20, fill='x', padx=20)

        self.create_btn = ttk.Button(btn_frame, text="创建文件", command=self.create_large_file)
        self.create_btn.pack(side='left', padx=10)

        self.stop_btn = ttk.Button(btn_frame, text="停止创建", command=self.stop_creating_file, state='disabled')
        self.stop_btn.pack(side='left', padx=10)

        self.delete_btn = ttk.Button(btn_frame, text="删除文件", command=self.delete_large_file)
        self.delete_btn.pack(side='left', padx=10)

        # 进度条
        self.progress = ttk.Progressbar(self.parent, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(pady=10, fill='x', padx=20)

        # 状态显示
        self.status_var = tk.StringVar(value="就绪 - 选择文件格式和大小后创建文件")
        status_label = ttk.Label(self.parent, textvariable=self.status_var,
                                 foreground='blue', wraplength=800)
        status_label.pack(pady=5, fill='x', padx=20)

    def _on_format_changed(self, *args):
        """当文件格式改变时更新默认文件名"""
        self._update_default_filename()

    def _update_default_filename(self):
        """更新默认文件名 - 修改：默认扩展名为exe"""
        format_display = self.file_format.get()
        format_extension = self.format_mapping.get(format_display, "exe")  # 修改：默认扩展名为exe

        # 设置默认文件名，保持当前目录不变，只改变扩展名
        current_path = self.file_path_var.get()
        if current_path and os.path.basename(current_path).startswith("large_file."):
            # 如果当前路径已经是默认文件名，只改变扩展名
            dir_name = os.path.dirname(current_path) if os.path.dirname(current_path) else os.getcwd()
            new_filename = f"large_file.{format_extension}"
            new_path = os.path.join(dir_name, new_filename)
        else:
            # 否则创建新的默认路径 - 修改：默认扩展名为exe
            new_path = os.path.join(os.getcwd(), f"large_file.{format_extension}")

        self.file_path_var.set(new_path)

    def browse_file(self):
        """浏览选择文件保存位置"""
        format_display = self.file_format.get()
        format_extension = self.format_mapping.get(format_display, "exe")  # 修改：默认扩展名为exe

        # 根据格式设置文件类型
        file_types = {
            "exe": [("EXE files", "*.exe"), ("All files", "*.*")],
            "zip": [("ZIP files", "*.zip"), ("All files", "*.*")],
            "rar": [("RAR files", "*.rar"), ("All files", "*.*")],
            "mp3": [("MP3 files", "*.mp3"), ("All files", "*.*")],
            "mp4": [("MP4 files", "*.mp4"), ("All files", "*.*")],
            "pdf": [("PDF files", "*.pdf"), ("All files", "*.*")],
            "doc": [("Word documents", "*.doc"), ("All files", "*.*")],
            "docx": [("Word documents", "*.docx"), ("All files", "*.*")],
            "xls": [("Excel files", "*.xls"), ("All files", "*.*")],
            "xlsx": [("Excel files", "*.xlsx"), ("All files", "*.*")],
            "ppt": [("PowerPoint files", "*.ppt"), ("All files", "*.*")],
            "pptx": [("PowerPoint files", "*.pptx"), ("All files", "*.*")],
            "dat": [("Data files", "*.dat"), ("All files", "*.*")]
        }

        filetype = file_types.get(format_extension, [("All files", "*.*")])
        default_ext = format_extension

        filename = filedialog.asksaveasfilename(
            title="选择大文件保存位置",
            filetypes=filetype,
            defaultextension=f".{default_ext}",
            initialfile=f"large_file.{default_ext}"
        )
        if filename:
            self.file_path_var.set(filename)

    def create_large_file(self):
        """创建大文件 - 支持多种格式"""
        file_path = self.file_path_var.get()
        size_mb = self.file_size.get()
        format_display = self.file_format.get()
        file_format = self.format_mapping.get(format_display, "exe")  # 修改：默认扩展名为exe

        if not file_path:
            messagebox.showerror("错误", "请选择文件路径")
            return

        self.current_file_path = file_path
        self.stop_creating = False

        # 更新按钮状态
        self.create_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.delete_btn.config(state='disabled')

        def create_file_thread():
            try:
                self.progress['value'] = 0
                self.progress['maximum'] = 100

                # 根据格式创建文件
                for progress in self.file_ops.create_large_file_with_format(file_path, size_mb, file_format):
                    if self.stop_creating:
                        break
                    self.progress['value'] = progress
                    self.status_var.set(f"创建进度: {progress:.1f}% - 格式: {format_display}")
                    self.parent.update_idletasks()

                if self.stop_creating:
                    self.status_var.set("文件创建已停止")
                    # 删除部分创建的文件
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            self.status_var.set("已删除部分创建的文件")
                    except Exception as e:
                        self.status_var.set(f"删除部分文件失败: {str(e)}")
                else:
                    self.status_var.set(f"文件创建完成: {file_path} (格式: {format_display})")
                    self.progress['value'] = 100

            except Exception as e:
                self.status_var.set(f"创建失败: {str(e)}")
                self.progress['value'] = 0
            finally:
                # 恢复按钮状态
                self.create_btn.config(state='normal')
                self.stop_btn.config(state='disabled')
                self.delete_btn.config(state='normal')

        self.creating_thread = threading.Thread(target=create_file_thread, daemon=True)
        self.creating_thread.start()

    def stop_creating_file(self):
        """停止创建文件"""
        self.stop_creating = True
        self.file_ops.stop_creating_large_file()
        self.status_var.set("正在停止创建...")

    def delete_large_file(self):
        """删除创建的大文件"""
        if not self.current_file_path:
            messagebox.showerror("错误", "没有创建的文件可删除")
            return

        try:
            # 先停止创建（如果有）
            self.stop_creating_file()

            # 等待一下确保创建线程已停止
            if self.creating_thread and self.creating_thread.is_alive():
                self.creating_thread.join(timeout=2)

            # 删除文件
            success = self.file_ops.delete_large_file(self.current_file_path)
            if success:
                self.status_var.set("文件已删除")
                self.current_file_path = None
                self.progress['value'] = 0
            else:
                self.status_var.set("文件删除失败")
        except Exception as e:
            messagebox.showerror("错误", f"删除文件失败: {str(e)}")


class ProcessMemoryTab(BaseTab):
    """进程内存占用标签页 - 多进程方案解决2000MB退出问题，增加内存分配策略选项"""

    def __init__(self, parent):
        super().__init__(parent)
        self.is_creating_process = False
        self.is_killing_process = False
        self.last_refresh_time = 0
        self.auto_refresh_id = None
        self.auto_refresh_var = None
        self.setup_ui()

    def setup_ui(self):
        title_label = ttk.Label(self.parent, text="进程内存占用 - 多进程方案",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 说明信息 - 更新说明
        info_text = """全新多进程内存占用方案，彻底解决2000MB退出问题！

方案说明:
• 当内存需求超过1700MB时，自动启动多个进程平均分配内存占用
• 每个进程最大占用1700MB内存，避免单个进程崩溃
• 进程启动后自动开始内存占用，无需手动操作
• 结束时会自动关闭所有内存测试进程
• 支持两种内存分配策略：提交大小、混合比例分配

内存分配策略:
1. 主要占用提交大小: 100%占用提交大小
2. 混合比例分配: 自定义提交大小和专用工作集的比例

算法示例:
• 5000MB内存 = 启动3个进程 (1700MB + 1700MB + 1600MB)
• 8000MB内存 = 启动5个进程 (1600MB × 5)

注意: 
• 分配大量内存可能会影响系统性能
• 请确保有足够的可用内存
• 使用后请及时关闭内存测试程序释放内存"""
        info_label = ttk.Label(self.parent, text=info_text, justify='left',
                               foreground='green', font=('Arial', 9), wraplength=800)
        info_label.pack(pady=5, fill='x', padx=20)

        # 内存大小设置
        memory_frame = ttk.Frame(self.parent)
        memory_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(memory_frame, text="总内存占用:").pack(side='left')
        self.memory_size = tk.IntVar(value=100)
        memory_spinbox = ttk.Spinbox(memory_frame, from_=1, to=100000,
                                     textvariable=self.memory_size, width=10)
        memory_spinbox.pack(side='left', padx=5)
        ttk.Label(memory_frame, text="MB").pack(side='left')

        # 显示当前系统内存信息
        try:
            system_memory = psutil.virtual_memory()
            available_mb = system_memory.available // (1024 * 1024)
            total_mb = system_memory.total // (1024 * 1024)
            memory_info_label = ttk.Label(memory_frame,
                                          text=f"系统内存: {available_mb}/{total_mb} MB 可用",
                                          foreground='blue')
            memory_info_label.pack(side='left', padx=10)
        except:
            pass

        # 内存分配策略选择
        strategy_frame = ttk.LabelFrame(self.parent, text="内存分配策略", padding=10)
        strategy_frame.pack(pady=10, fill='x', padx=20)

        # 策略选择
        self.allocation_strategy = tk.StringVar(value="commit")

        strategy1_frame = ttk.Frame(strategy_frame)
        strategy1_frame.pack(fill='x', pady=2)
        ttk.Radiobutton(strategy1_frame, text="主要占用提交大小",
                        variable=self.allocation_strategy, value="commit").pack(side='left')

        strategy3_frame = ttk.Frame(strategy_frame)
        strategy3_frame.pack(fill='x', pady=2)
        ttk.Radiobutton(strategy3_frame, text="混合比例分配",
                        variable=self.allocation_strategy, value="mixed").pack(side='left')

        # 比例输入框架
        ratio_frame = ttk.Frame(strategy_frame)
        ratio_frame.pack(fill='x', pady=5)

        ttk.Label(ratio_frame, text="提交大小占用比例:").pack(side='left')
        self.commit_ratio = tk.IntVar(value=50)
        commit_spinbox = ttk.Spinbox(ratio_frame, from_=0, to=100,
                                     textvariable=self.commit_ratio, width=5)
        commit_spinbox.pack(side='left', padx=5)
        ttk.Label(ratio_frame, text="%").pack(side='left')

        # 添加灰色提示文案
        warning_label = ttk.Label(ratio_frame,
                                  text="(比例小于50%时占用内存值不正确)",
                                  foreground='gray', font=('Arial', 8))
        warning_label.pack(side='left', padx=5)

        ttk.Label(ratio_frame, text="内存（专用工作集）占用比例:").pack(side='left', padx=(20, 0))
        self.working_set_ratio = tk.IntVar(value=50)
        working_set_spinbox = ttk.Spinbox(ratio_frame, from_=0, to=100,
                                          textvariable=self.working_set_ratio, width=5)
        working_set_spinbox.pack(side='left', padx=5)
        ttk.Label(ratio_frame, text="%").pack(side='left')

        # 添加验证标签
        self.validation_label = ttk.Label(ratio_frame, text="", foreground='red')
        self.validation_label.pack(side='left', padx=10)

        # 策略切换事件
        def update_strategy_ui(*args):
            strategy = self.allocation_strategy.get()
            if strategy == "mixed":
                ratio_frame.pack(fill='x', pady=5)
                # 设置默认比例
                self.commit_ratio.set(50)
                self.working_set_ratio.set(50)
                self.validation_label.config(text="")
            else:
                ratio_frame.pack_forget()

        self.allocation_strategy.trace('w', update_strategy_ui)
        update_strategy_ui()  # 初始调用

        # 按钮框架
        btn_frame = ttk.Frame(self.parent)
        btn_frame.pack(pady=20, fill='x', padx=20)

        self.create_btn = ttk.Button(btn_frame, text="启动多进程内存占用",
                                     command=self.create_multi_memory_processes)
        self.create_btn.pack(side='left', padx=10)

        self.kill_btn = ttk.Button(btn_frame, text="结束所有内存测试程序",
                                   command=self.kill_memory_process)
        self.kill_btn.pack(side='left', padx=10)

        self.refresh_btn = ttk.Button(btn_frame, text="刷新状态",
                                      command=self.refresh_status)
        self.refresh_btn.pack(side='left', padx=10)

        # 自动刷新选项
        self.auto_refresh_var = tk.BooleanVar(value=True)
        auto_refresh_check = ttk.Checkbutton(btn_frame, text="自动刷新 (1.5秒)",
                                             variable=self.auto_refresh_var,
                                             command=self.toggle_auto_refresh)
        auto_refresh_check.pack(side='left', padx=10)

        # 进程状态显示
        self.status_var = tk.StringVar(value="就绪 - 设置内存大小并点击启动多进程内存占用")
        status_label = ttk.Label(self.parent, textvariable=self.status_var,
                                 foreground='blue', wraplength=800, justify='left')
        status_label.pack(pady=5, fill='x', padx=20)

        # 启动自动刷新
        self.start_auto_refresh()

    def create_multi_memory_processes(self):
        """创建多进程内存测试 - 使用新的多进程方案"""
        if self.is_creating_process:
            messagebox.showinfo("提示", "正在创建进程，请稍候...")
            return

        total_memory_mb = self.memory_size.get()
        strategy = self.allocation_strategy.get()

        if total_memory_mb <= 0:
            messagebox.showerror("错误", "内存大小必须大于0")
            return

        # 验证比例 - 只在混合策略下验证，且不自动调整
        if strategy == "mixed":
            commit_ratio = self.commit_ratio.get()
            working_set_ratio = self.working_set_ratio.get()

            # 验证比例范围
            if commit_ratio < 0 or commit_ratio > 100:
                self.validation_label.config(text="提交大小比例必须在0-100之间")
                return

            if working_set_ratio < 0 or working_set_ratio > 100:
                self.validation_label.config(text="专用工作集比例必须在0-100之间")
                return

            # 验证比例之和
            if commit_ratio + working_set_ratio != 100:
                self.validation_label.config(text=f"比例之和必须等于100% (当前: {commit_ratio + working_set_ratio}%)")
                return
            else:
                self.validation_label.config(text="")  # 清除错误信息

        # 检查系统内存
        try:
            system_memory = psutil.virtual_memory()
            available_mb = system_memory.available // (1024 * 1024)
            if total_memory_mb > available_mb:
                if not messagebox.askyesno("内存不足警告",
                                           f"请求内存 {total_memory_mb} MB 超过系统可用内存 {available_mb} MB。\n这可能导致系统不稳定。\n是否继续？"):
                    return
        except:
            pass

        if total_memory_mb > 100000:
            if not messagebox.askyesno("警告",
                                       f"您要分配 {total_memory_mb} MB 内存，这可能会严重影响系统性能。\n是否继续？"):
                return

        self.is_creating_process = True
        self.create_btn.config(state='disabled')
        self.status_var.set("正在计算进程分配方案...")

        # 在新线程中执行创建进程的操作
        thread = threading.Thread(target=self._create_multi_processes_thread,
                                  args=(total_memory_mb, strategy))
        thread.daemon = True
        thread.start()

    def _create_multi_processes_thread(self, total_memory_mb, strategy):
        """在后台线程中创建多进程内存测试"""
        try:
            # 计算分配比例
            commit_ratio = 100
            working_set_ratio = 0

            if strategy == "commit":
                commit_ratio = 100
                working_set_ratio = 0
            elif strategy == "mixed":
                commit_ratio = self.commit_ratio.get()
                working_set_ratio = self.working_set_ratio.get()

            # 使用新的多进程内存测试方案
            result = self.process_mgr.create_multi_memory_processes(
                total_memory_mb, strategy, commit_ratio, working_set_ratio)
            self.parent.after(0, self._create_process_done, result, None)
        except Exception as e:
            self.parent.after(0, self._create_process_done, None, str(e))

    def kill_memory_process(self):
        """结束所有内存测试程序"""
        try:
            if hasattr(self, 'process_mgr'):
                result = self.process_mgr.kill_memory_process()
                self.status_var.set(result)
            else:
                self.status_var.set("❌ 进程管理器未初始化")
        except Exception as e:
            self.status_var.set(f"❌ 结束进程失败: {str(e)}")

    def refresh_status(self):
        """刷新状态 - 修改：只显示PID和运行时长"""
        try:
            if hasattr(self, 'process_mgr'):
                processes = self.process_mgr.get_running_processes()
                if processes:
                    status_text = f"运行中的内存测试进程: {len(processes)} 个\n"
                    for proc in processes:
                        running_time_minutes = proc['running_time'] / 60
                        status_text += f"PID {proc['pid']}: 运行时长 {running_time_minutes:.1f}分钟\n"
                    self.status_var.set(status_text)
                else:
                    self.status_var.set("✅ 没有运行中的内存测试进程")
            else:
                self.status_var.set("❌ 进程管理器未初始化")
        except Exception as e:
            self.status_var.set(f"❌ 刷新状态失败: {str(e)}")

    def toggle_auto_refresh(self):
        """切换自动刷新"""
        if self.auto_refresh_var.get():
            self.start_auto_refresh()
        else:
            self.stop_auto_refresh()

    def start_auto_refresh(self):
        """开始自动刷新"""
        if self.auto_refresh_id:
            self.parent.after_cancel(self.auto_refresh_id)

        def auto_refresh():
            if self.auto_refresh_var.get():
                self.refresh_status()
                self.auto_refresh_id = self.parent.after(1500, auto_refresh)  # 1.5秒刷新一次

        self.auto_refresh_id = self.parent.after(1500, auto_refresh)

    def stop_auto_refresh(self):
        """停止自动刷新"""
        if self.auto_refresh_id:
            self.parent.after_cancel(self.auto_refresh_id)
            self.auto_refresh_id = None

    def _create_process_done(self, result, error):
        """进程创建完成回调"""
        self.is_creating_process = False
        self.create_btn.config(state='normal')

        if error:
            self.status_var.set(f"❌ 创建进程失败: {error}")
        else:
            self.status_var.set(result)
            # 自动刷新状态
            self.refresh_status()


class DllInjectorTab(BaseTab):
    """DLL注入标签页 - 移除签名注入功能"""

    def __init__(self, parent):
        super().__init__(parent)
        self.process_data = []  # 存储进程数据用于排序
        self.sort_column = 'pid'  # 当前排序列
        self.sort_reverse = False  # 排序方向
        self.hide_system_processes = True  # 默认隐藏系统进程
        self.setup_ui()
        self.refresh_process_list()

    def setup_ui(self):
        title_label = ttk.Label(self.parent, text="DLL注入工具",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 检查管理员权限
        admin_warning = ""
        if not is_admin():
            admin_warning = "\n⚠️ 警告: 当前未以管理员权限运行，DLL注入可能失败！"

        # 检查 psutil 是否可用
        psutil_warning = ""
        if not PSUTIL_AVAILABLE:
            psutil_warning = "\n⚠️ 警告: psutil 模块未安装，进程列表功能受限！"

        # 检查 win32 是否可用
        win32_warning = ""
        if not WIN32_AVAILABLE:
            win32_warning = "\n⚠️ 警告: pywin32 模块未安装，进程完整性检查功能受限！"

        # 说明信息
        info_text = f"""注意：DLL注入需要管理员权限，且可能被安全软件阻止。
请确保使用可信的DLL文件，并遵守相关法律法规。{admin_warning}{psutil_warning}{win32_warning}

注入方法说明：
• 普通注入：使用标准LoadLibrary方法进行DLL注入
• 支持Windows XP及以上所有Windows版本"""
        info_label = ttk.Label(self.parent, text=info_text, justify='left',
                               foreground='red', font=('Arial', 9), wraplength=800)
        info_label.pack(pady=5, fill='x', padx=20)

        # 进程选择框架
        process_frame = ttk.Frame(self.parent)
        process_frame.pack(pady=10, fill='x', padx=20)

        # 进程列表和选择
        process_select_frame = ttk.Frame(process_frame)
        process_select_frame.pack(fill='x')

        ttk.Label(process_select_frame, text="目标进程:").pack(side='left')

        # 进程列表
        list_frame = ttk.Frame(process_select_frame)
        list_frame.pack(side='left', fill='x', expand=True, padx=5)

        # 创建Treeview显示进程列表 - 支持所有列排序
        self.process_tree = ttk.Treeview(list_frame, columns=('pid', 'name', 'username', 'status', 'integrity'),
                                         show='headings', height=10)

        # 定义列 - 所有列都支持排序
        columns = [('pid', 'PID', 80), ('name', '进程名', 150),
                   ('username', '用户名', 120), ('status', '状态', 80),
                   ('integrity', '完整性级别', 100)]

        for col_id, col_text, width in columns:
            self.process_tree.heading(col_id, text=col_text,
                                      command=lambda c=col_id: self.sort_treeview(c))
            self.process_tree.column(col_id, width=width)

        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.process_tree.yview)
        self.process_tree.configure(yscrollcommand=scrollbar.set)

        self.process_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 绑定选择事件
        self.process_tree.bind('<<TreeviewSelect>>', self.on_process_select)

        # 手动输入PID的选项
        pid_frame = ttk.Frame(process_frame)
        pid_frame.pack(fill='x', pady=5)

        ttk.Label(pid_frame, text="或手动输入PID:").pack(side='left')
        self.pid_var = tk.StringVar()
        pid_entry = ttk.Entry(pid_frame, textvariable=self.pid_var, width=10)
        pid_entry.pack(side='left', padx=5)
        ttk.Button(pid_frame, text="检查PID", command=self.check_pid).pack(side='left', padx=5)
        ttk.Button(pid_frame, text="查看详情", command=self.view_process_details).pack(side='left', padx=5)

        # 隐藏系统进程选项
        self.hide_system_var = tk.BooleanVar(value=True)
        hide_check = ttk.Checkbutton(pid_frame, text="隐藏系统进程",
                                     variable=self.hide_system_var,
                                     command=self.toggle_system_processes)
        hide_check.pack(side='left', padx=10)

        # DLL文件选择框架
        dll_frame = ttk.Frame(self.parent)
        dll_frame.pack(pady=10, fill='x', padx=20)

        # DLL文件选择
        ttk.Label(dll_frame, text="DLL文件:").pack(side='left')
        self.dll_path_var = tk.StringVar()
        dll_entry = ttk.Entry(dll_frame, textvariable=self.dll_path_var, width=50)
        dll_entry.pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(dll_frame, text="浏览", command=self.browse_dll).pack(side='left')

        # 注入按钮框架
        inject_frame = ttk.Frame(self.parent)
        inject_frame.pack(pady=15, fill='x', padx=20)

        # 普通注入按钮 - 现在只有一个注入按钮
        self.normal_inject_btn = ttk.Button(inject_frame, text="注入DLL",
                                            command=self.inject_dll,
                                            style='Accent.TButton')
        self.normal_inject_btn.pack(side='left', padx=10, fill='x', expand=True)

        # 按钮框架
        btn_frame = ttk.Frame(self.parent)
        btn_frame.pack(pady=10, fill='x', padx=20)

        ttk.Button(btn_frame, text="刷新进程列表", command=self.refresh_process_list).pack(side='left', padx=5)

        # 状态显示
        self.status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(self.parent, textvariable=self.status_var,
                                 foreground='blue', wraplength=800, justify='left')
        status_label.pack(pady=5, fill='x', padx=20)

    def toggle_system_processes(self):
        """切换是否显示系统进程"""
        self.hide_system_processes = self.hide_system_var.get()
        self.refresh_process_list()

    def sort_treeview(self, column):
        """对Treeview进行排序"""
        # 切换排序方向
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        # 根据列类型进行排序
        if column == 'pid':
            # PID是数字，需要转换为整数排序
            self.process_data.sort(key=lambda x: int(x[0]), reverse=self.sort_reverse)
        else:
            # 其他列按字符串排序
            col_index = ['pid', 'name', 'username', 'status', 'integrity'].index(column)
            self.process_data.sort(key=lambda x: x[col_index], reverse=self.sort_reverse)

        # 更新Treeview显示
        self.update_treeview_display()

    def update_treeview_display(self):
        """更新Treeview显示"""
        # 清空现有列表
        for item in self.process_tree.get_children():
            self.process_tree.delete(item)

        # 添加排序后的数据
        for proc_data in self.process_data:
            self.process_tree.insert('', 'end', values=proc_data)

    def browse_dll(self):
        """浏览DLL文件"""
        dll_path = filedialog.askopenfilename(
            title="选择DLL文件",
            filetypes=[("DLL files", "*.dll"), ("All files", "*.*")]
        )
        if dll_path:
            self.dll_path_var.set(dll_path)

    def refresh_process_list(self):
        """刷新进程列表"""
        try:
            self.status_var.set("正在获取进程列表...")
            self.parent.update_idletasks()

            # 清空现有列表
            for item in self.process_tree.get_children():
                self.process_tree.delete(item)

            # 获取进程列表
            processes = self.dll_injector.get_process_list(self.hide_system_processes)

            if not processes:
                if not PSUTIL_AVAILABLE:
                    self.status_var.set("psutil 模块未安装，无法获取进程列表")
                    return
                else:
                    self.status_var.set("无法获取进程列表")
                    return

            # 存储进程数据用于排序
            self.process_data = []

            # 添加到Treeview和进程数据列表
            for proc in processes:
                pid = proc['pid']
                accessible = self.dll_injector.is_process_accessible(pid)
                status = "✅ 可访问" if accessible else "❌ 拒绝访问"

                # 获取完整性级别 - 使用简化的检查方法
                integrity_level = self.dll_injector.check_process_integrity(pid)
                is_protected = self.dll_injector.is_signed_process_protected(pid)

                # 为受保护进程添加标识
                integrity_display = f"{integrity_level}{' 🔒' if is_protected else ''}"

                proc_data = (
                    str(pid),
                    proc['name'],
                    proc['username'],
                    status,
                    integrity_display
                )
                self.process_data.append(proc_data)
                self.process_tree.insert('', 'end', values=proc_data)

            # 默认按PID排序
            self.sort_treeview('pid')

            self.status_var.set(f"已加载 {len(processes)} 个进程")

        except Exception as e:
            self.status_var.set(f"获取进程列表失败: {str(e)}")

    def on_process_select(self, event):
        """进程选择事件"""
        selection = self.process_tree.selection()
        if selection:
            item = selection[0]
            values = self.process_tree.item(item, 'values')
            if values:
                self.pid_var.set(values[0])  # PID

                # 检查是否为受保护进程，如果是则警告
                integrity_text = values[4] if len(values) > 4 else ""
                if "🔒" in integrity_text:
                    self.status_var.set("检测到受保护进程，注入可能失败")

    def check_pid(self):
        """检查手动输入的PID"""
        pid_str = self.pid_var.get()
        if not pid_str.isdigit():
            messagebox.showerror("错误", "请输入有效的PID（数字）")
            return

        pid = int(pid_str)
        try:
            if not PSUTIL_AVAILABLE:
                messagebox.showwarning("警告", "psutil 模块未安装，无法检查进程状态")
                return

            # 检查进程是否存在
            psutil.Process(pid)

            # 检查是否可访问
            accessible = self.dll_injector.is_process_accessible(pid)
            status = "可访问" if accessible else "拒绝访问"

            # 检查完整性级别
            integrity_level = self.dll_injector.check_process_integrity(pid)
            is_protected = self.dll_injector.is_signed_process_protected(pid)

            protection_status = "是" if is_protected else "否"

            messagebox.showinfo("PID检查",
                                f"进程 {pid} 存在\n"
                                f"状态: {status}\n"
                                f"完整性级别: {integrity_level}\n"
                                f"是否受保护: {protection_status}")

        except psutil.NoSuchProcess:
            messagebox.showerror("错误", f"进程 {pid} 不存在")
        except Exception as e:
            messagebox.showerror("错误", f"检查进程失败: {str(e)}")

    def view_process_details(self):
        """查看进程详情"""
        pid_str = self.pid_var.get()
        if not pid_str or not pid_str.isdigit():
            messagebox.showerror("错误", "请输入有效的PID")
            return

        pid = int(pid_str)
        try:
            process_info = self.dll_injector.get_process_info(pid)
            if process_info:
                details = f"""
进程详情:
--------
PID: {process_info['pid']}
进程名: {process_info['name']}
可执行文件: {process_info['exe']}
状态: {process_info['status']}
用户名: {process_info['username']}
创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(process_info['create_time']))}
内存使用: {process_info['memory_info'].rss // 1024 // 1024} MB
CPU使用率: {process_info['cpu_percent']}%
线程数: {process_info['num_threads']}
完整性级别: {process_info['integrity_level']}
是否受保护: {'是' if process_info['is_protected'] else '否'}
                """
                messagebox.showinfo(f"进程 {pid} 详情", details)
            else:
                messagebox.showerror("错误", f"无法获取进程 {pid} 的详细信息")
        except Exception as e:
            messagebox.showerror("错误", f"获取进程详情失败: {str(e)}")

    def inject_dll(self):
        """执行DLL注入"""
        dll_path = self.dll_path_var.get()
        pid_str = self.pid_var.get()

        if not dll_path:
            messagebox.showerror("错误", "请选择DLL文件")
            return

        if not pid_str or not pid_str.isdigit():
            messagebox.showerror("错误", "请输入有效的目标进程PID")
            return

        pid = int(pid_str)

        # 检查DLL文件是否存在
        if not os.path.exists(dll_path):
            messagebox.showerror("错误", f"DLL文件不存在: {dll_path}")
            return

        # 检查进程是否存在（如果psutil可用）
        if PSUTIL_AVAILABLE:
            try:
                psutil.Process(pid)
            except psutil.NoSuchProcess:
                messagebox.showerror("错误", f"进程 {pid} 不存在")
                return

        # 检查管理员权限
        if not is_admin():
            if not messagebox.askyesno("权限警告",
                                       "当前未以管理员权限运行，DLL注入很可能失败。\n是否继续尝试？"):
                return

        # 检查是否为受保护进程
        is_protected = self.dll_injector.is_signed_process_protected(pid)

        if is_protected:
            if not messagebox.askyesno("受保护进程警告",
                                       f"进程 {pid} 可能受数字签名保护，注入可能失败。\n\n"
                                       f"是否继续尝试注入？"):
                return

        # 确认对话框
        if not messagebox.askyesno("确认",
                                   f"确定要将DLL注入到进程 {pid} 吗？\n\n"
                                   f"DLL: {os.path.basename(dll_path)}\n"
                                   f"目标进程: {pid}\n"
                                   f"进程保护: {'是' if is_protected else '否'}"):
            return

        try:
            self.status_var.set("正在执行DLL注入...")
            self.parent.update_idletasks()

            result = self.dll_injector.inject_dll_normal(pid, dll_path)
            self.status_var.set(result)
            messagebox.showinfo("成功", result)

        except Exception as e:
            error_msg = f"DLL注入失败: {str(e)}"

            # 提供更详细的解决方案建议
            if "LoadLibrary返回NULL" in str(e):
                error_msg += "\n\n解决方案建议："
                error_msg += "\n1. 确保DLL文件路径不包含特殊字符或中文"
                error_msg += "\n2. 检查DLL依赖项是否完整（使用Dependency Walker工具）"
                error_msg += "\n3. 确保DLL架构与目标进程匹配（32位/64位）"
                error_msg += "\n4. 尝试将DLL复制到系统目录或目标进程目录"
                error_msg += "\n5. 以管理员权限运行程序"

            self.status_var.set(error_msg)
            messagebox.showerror("错误", error_msg)


class FilePermissionTab(BaseTab):
    """文件权限设置标签页 - 修改布局和结果显示，删除了'读取'选项"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        title_label = ttk.Label(self.parent, text="文件权限设置",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 说明文本 - 更新说明
        info_text = """重要说明：
1. 如果文件被设置为完全拒绝访问，可能需要先获取所有权或使用管理员权限
2. 对于文件夹设置，权限会递归应用到所有子文件夹和文件
3. "可读取不可执行"权限：使用严格权限设置，确保当前用户无法执行exe文件
4. "拒绝读取执行"会拒绝所有读取和执行权限

"可读取不可执行"权限的技术说明：
• 对文件夹和普通文件设置只读权限(R)
• 对可执行文件使用更严格的权限设置：
  1. 禁用继承权限 (/inheritance:r)
  2. 设置当前用户只读权限
  3. 拒绝当前用户的执行权限 (当前用户名:X)
• 支持的可执行文件类型：.exe, .bat, .cmd, .ps1, .msi, .com, .scr, .vbs, .js等
• 此方法可以确保当前用户无法执行这些文件，但其他用户可能仍然可以执行

关键点：权限设置针对当前用户，需要为当前用户单独设置拒绝执行权限"""
        info_label = ttk.Label(self.parent, text=info_text, foreground='red', wraplength=800, justify='left')
        info_label.pack(pady=5, fill='x', padx=20)

        # 文件选择
        file_frame = ttk.Frame(self.parent)
        file_frame.pack(pady=5, fill='x', padx=20)

        ttk.Label(file_frame, text="选择文件/文件夹:").pack(side='left')
        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(file_frame, textvariable=self.path_var, width=50)
        path_entry.pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(file_frame, text="浏览文件", command=self.browse_file).pack(side='left')
        ttk.Button(file_frame, text="浏览文件夹", command=self.browse_directory).pack(side='left', padx=5)

        # 权限选择 - 修改：删除了"读取"选项，只保留4个选项
        perm_frame = ttk.Frame(self.parent)
        perm_frame.pack(pady=10, fill='x', padx=20)

        self.permission_mode = tk.StringVar(value="full_control")

        # 修改后的权限选项（删除了"读取"选项）
        permissions = [
            ("完全控制", "full_control", "允许所有操作，包括读写执行删除"),
            ("可读取不可执行", "read_no_execute", "只读权限，当前用户无法执行exe文件（严格模式）【针对文件夹本功能无效】"),
            ("读取执行", "read_execute", "允许读取和执行"),
            ("拒绝读取执行", "deny_read_execute", "拒绝当前用户的读取和执行权限")
        ]

        # 使用网格布局排列权限选项
        for i, (text, value, description) in enumerate(permissions):
            frame = ttk.Frame(perm_frame)
            if i < 2:
                frame.grid(row=0, column=i, padx=10, pady=5, sticky='w')
            else:
                frame.grid(row=1, column=i-2, padx=10, pady=5, sticky='w')

            ttk.Radiobutton(frame, text=text, variable=self.permission_mode,
                            value=value).pack(anchor='w')
            # 添加权限描述（小字体）
            ttk.Label(frame, text=description, font=('Arial', 8),
                      foreground='gray', wraplength=250).pack(anchor='w')

        # 递归设置选项
        recursive_frame = ttk.Frame(self.parent)
        recursive_frame.pack(pady=10, fill='x', padx=20)

        # 特别注意"可读取不可执行"权限的递归设置说明
        ttk.Label(recursive_frame,
                  text="✅ 重要: '可读取不可执行'权限使用严格模式，确保当前用户无法执行exe文件",
                  foreground='green', font=('Arial', 9, 'bold'), wraplength=700).pack(anchor='w')

        ttk.Label(recursive_frame,
                  text="对可执行文件使用更严格的权限设置：1.禁用继承 2.设置只读 3.拒绝当前用户执行权限",
                  foreground='blue', font=('Arial', 8)).pack(anchor='w', pady=(2, 0))

        # 操作按钮框架
        action_frame = ttk.Frame(self.parent)
        action_frame.pack(pady=20, fill='x', padx=20)

        # 设置权限按钮
        ttk.Button(action_frame, text="设置权限",
                   command=self.set_file_permission).pack(side='left', padx=5)

        # 查询权限按钮
        ttk.Button(action_frame, text="查询目标权限",
                   command=self.query_permission).pack(side='left', padx=5)

        # 高级选项框架
        advanced_frame = ttk.Frame(self.parent)
        advanced_frame.pack(pady=10, fill='x', padx=20)

        self.take_ownership_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(advanced_frame, text="尝试获取所有权（需要管理员权限）",
                        variable=self.take_ownership_var).pack(side='left')

        # 权限状态显示
        self.status_var = tk.StringVar()
        status_label = ttk.Label(self.parent, textvariable=self.status_var,
                                 foreground='blue', wraplength=800, justify='left')
        status_label.pack(pady=5, fill='x', padx=20)

    def browse_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.path_var.set(path)

    def browse_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)

    def set_file_permission(self):
        path = self.path_var.get()
        permission = self.permission_mode.get()
        take_ownership = self.take_ownership_var.get()

        if not path or not os.path.exists(path):
            messagebox.showerror("错误", "请选择有效的文件或文件夹路径")
            return

        # 确认对话框，特别是对于文件夹的递归操作
        if os.path.isdir(path):
            if permission == "read_no_execute":
                # 对于"可读取不可执行"权限，特别提示
                if not messagebox.askyesno("确认",
                                           f"您将对文件夹及其所有子文件夹和文件设置'可读取不可执行'权限。\n\n"
                                           f"路径: {path}\n"
                                           f"权限: {permission}\n\n"
                                           f"✅ 此操作会递归应用到所有子项：\n"
                                           f"- 禁用所有文件和文件夹的继承权限\n"
                                           f"- 所有文件夹和普通文件设置为只读\n"
                                           f"- 所有可执行文件使用严格权限设置（拒绝当前用户执行）\n"
                                           f"- 确保当前用户无法执行这些文件\n"
                                           f"- 操作可能需要较长时间，取决于文件夹大小\n\n"
                                           f"是否继续？"):
                    return
            else:
                if not messagebox.askyesno("确认",
                                           f"您将对文件夹及其所有子文件夹和文件设置权限。\n\n"
                                           f"路径: {path}\n"
                                           f"权限: {permission}\n\n"
                                           f"✅ 此操作会递归应用到所有子项，包括深层嵌套的文件和文件夹。\n"
                                           f"操作可能需要较长时间，取决于文件夹大小。\n"
                                           f"是否继续？"):
                    return

        try:
            result = self.sys_tools.set_file_permission(path, permission, take_ownership)
            self.status_var.set(result)
        except Exception as e:
            messagebox.showerror("错误", f"设置权限失败: {str(e)}")

    def query_permission(self):
        """查询文件或文件夹的权限 - 修改为弹窗显示"""
        path = self.path_var.get()
        if not path or not os.path.exists(path):
            messagebox.showerror("错误", "请选择有效的文件或文件夹路径")
            return

        try:
            # 调用修改后的查询方法，传入父窗口用于创建弹窗
            result = self.sys_tools.query_file_permission(path, self.parent)
            self.status_var.set("权限信息已在新窗口中显示")
        except Exception as e:
            messagebox.showerror("错误", f"查询权限失败: {str(e)}")


class HostModifyTab(BaseTab):
    """Host文件修改标签页"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        title_label = ttk.Label(self.parent, text="Host文件修改",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 说明信息
        info_text = """注意：此操作需要管理员权限
• 设置host文件为当前用户完全控制
• 使用默认程序打开host文件"""

        info_label = ttk.Label(self.parent, text=info_text, justify='left',
                               foreground='red', font=('Arial', 10))
        info_label.pack(pady=10, fill='x', padx=20)

        # 修改按钮
        ttk.Button(self.parent, text="修改host文件权限并打开",
                   command=self.modify_host_file).pack(pady=20)

        # 状态显示
        self.status_var = tk.StringVar()
        status_label = ttk.Label(self.parent, textvariable=self.status_var,
                                 foreground='blue', wraplength=800)
        status_label.pack(pady=5, fill='x', padx=20)

    def modify_host_file(self):
        try:
            result = self.sys_tools.modify_host_file()
            self.status_var.set(result)
        except Exception as e:
            messagebox.showerror("错误", f"修改host文件失败: {str(e)}")


class TextGeneratorTab(BaseTab):
    """文本生成标签页 - 修复字符类型选择问题"""

    def __init__(self, parent):
        super().__init__(parent)
        self.generation_thread = None
        self.setup_ui()

    def setup_ui(self):
        """设置用户界面"""
        # 标题
        title_label = ttk.Label(self.parent, text="文本生成工具",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 说明信息
        info_text = """功能说明：
• 生成指定长度的随机文本
• 支持多种字符类型组合
• 包含Unicode字符和表情符号
• 支持大文本生成，实时显示进度
• 生成的文本可以保存到文件

字符类型说明：
• 英文字符: A-Z, a-z
• 中文字符: 常用汉字
• 数字字符: 0-9
• 特殊字符: !@#$%^&()[]{}~-_=+.,;
• Unicode字符: 扩展字符集、表情符号等"""

        info_label = ttk.Label(self.parent, text=info_text, justify='left',
                               foreground='green', font=('Arial', 9), wraplength=800)
        info_label.pack(pady=5, fill='x', padx=20)

        # 文本长度设置
        length_frame = ttk.Frame(self.parent)
        length_frame.pack(pady=10, fill='x', padx=20)

        ttk.Label(length_frame, text="文本长度:").pack(side='left')
        self.text_length = tk.IntVar(value=1000)
        length_spinbox = ttk.Spinbox(length_frame, from_=1, to=1000000,
                                     textvariable=self.text_length, width=10)
        length_spinbox.pack(side='left', padx=5)
        ttk.Label(length_frame, text="字符").pack(side='left')

        # 字符类型选择框架
        char_type_frame = ttk.LabelFrame(self.parent, text="字符类型选择", padding=10)
        char_type_frame.pack(pady=10, fill='x', padx=20)

        # 默认勾选：英文字符、中文字符、数字字符、特殊字符
        self.include_english = tk.BooleanVar(value=True)
        self.include_chinese = tk.BooleanVar(value=True)
        self.include_digits = tk.BooleanVar(value=True)
        self.include_special = tk.BooleanVar(value=True)
        self.include_unicode = tk.BooleanVar(value=False)  # 修改：默认不勾选Unicode字符

        # 第一行
        row1_frame = ttk.Frame(char_type_frame)
        row1_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row1_frame, text="英文字符 (A-Z, a-z)",
                        variable=self.include_english).pack(side='left', padx=10)
        ttk.Checkbutton(row1_frame, text="中文字符 (常用汉字)",
                        variable=self.include_chinese).pack(side='left', padx=10)

        # 第二行
        row2_frame = ttk.Frame(char_type_frame)
        row2_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row2_frame, text="数字字符 (0-9)",
                        variable=self.include_digits).pack(side='left', padx=10)
        ttk.Checkbutton(row2_frame, text="特殊字符 (!@#$%^&等)",
                        variable=self.include_special).pack(side='left', padx=10)

        # 第三行
        row3_frame = ttk.Frame(char_type_frame)
        row3_frame.pack(fill='x', pady=2)

        ttk.Checkbutton(row3_frame, text="Unicode字符 (扩展字符、表情符号等)",
                        variable=self.include_unicode).pack(side='left', padx=10)

        # 快速选择按钮
        quick_select_frame = ttk.Frame(char_type_frame)
        quick_select_frame.pack(fill='x', pady=5)

        ttk.Button(quick_select_frame, text="全选",
                   command=self.select_all_types).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="全不选",
                   command=self.deselect_all_types).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="仅英文数字",
                   command=self.select_english_digits).pack(side='left', padx=5)
        ttk.Button(quick_select_frame, text="仅中文",
                   command=self.select_chinese_only).pack(side='left', padx=5)

        # 控制按钮框架
        control_frame = ttk.Frame(self.parent)
        control_frame.pack(pady=15, fill='x', padx=20)

        self.generate_btn = ttk.Button(control_frame, text="开始生成文本",
                                       command=self.start_generation)
        self.generate_btn.pack(side='left', padx=10)

        self.stop_btn = ttk.Button(control_frame, text="停止生成",
                                   command=self.stop_generation, state='disabled')
        self.stop_btn.pack(side='left', padx=10)

        self.save_btn = ttk.Button(control_frame, text="保存到文件",
                                   command=self.save_to_file, state='disabled')
        self.save_btn.pack(side='left', padx=10)

        self.clear_btn = ttk.Button(control_frame, text="清空文本",
                                    command=self.clear_text)
        self.clear_btn.pack(side='left', padx=10)

        # 进度条
        self.progress = ttk.Progressbar(self.parent, orient='horizontal',
                                        length=400, mode='determinate')
        self.progress.pack(pady=10, fill='x', padx=20)

        # 状态显示
        self.status_var = tk.StringVar(value="就绪 - 设置参数后开始生成文本")
        status_label = ttk.Label(self.parent, textvariable=self.status_var,
                                 foreground='blue', wraplength=800)
        status_label.pack(pady=5, fill='x', padx=20)

        # 文本显示区域
        text_frame = ttk.Frame(self.parent)
        text_frame.pack(pady=10, fill='both', expand=True, padx=20)

        ttk.Label(text_frame, text="生成的文本:", font=('Arial', 10, 'bold')).pack(anchor='w')

        self.text_display = scrolledtext.ScrolledText(
            text_frame, wrap=tk.WORD, width=80, height=15,
            font=('Arial', 10))
        self.text_display.pack(fill='both', expand=True)

        # 文本统计信息
        self.stats_var = tk.StringVar(value="字符数: 0")
        stats_label = ttk.Label(text_frame, textvariable=self.stats_var,
                                foreground='green', font=('Arial', 9))
        stats_label.pack(anchor='w', pady=(5, 0))

    def select_all_types(self):
        """全选所有字符类型"""
        self.include_english.set(True)
        self.include_chinese.set(True)
        self.include_digits.set(True)
        self.include_special.set(True)
        self.include_unicode.set(True)
        self.status_var.set("已选择所有字符类型")

    def deselect_all_types(self):
        """全不选所有字符类型"""
        self.include_english.set(False)
        self.include_chinese.set(False)
        self.include_digits.set(False)
        self.include_special.set(False)
        self.include_unicode.set(False)
        self.status_var.set("已取消选择所有字符类型")

    def select_english_digits(self):
        """仅选择英文和数字"""
        self.include_english.set(True)
        self.include_chinese.set(False)
        self.include_digits.set(True)
        self.include_special.set(False)
        self.include_unicode.set(False)
        self.status_var.set("已选择英文和数字字符")

    def select_chinese_only(self):
        """仅选择中文"""
        self.include_english.set(False)
        self.include_chinese.set(True)
        self.include_digits.set(False)
        self.include_special.set(False)
        self.include_unicode.set(False)
        self.status_var.set("已选择中文字符")

    def start_generation(self):
        """开始生成文本"""
        length = self.text_length.get()

        if length <= 0:
            messagebox.showerror("错误", "文本长度必须大于0")
            return

        # 检查是否至少选择了一种字符类型
        if not any([
            self.include_english.get(),
            self.include_chinese.get(),
            self.include_digits.get(),
            self.include_special.get(),
            self.include_unicode.get()
        ]):
            messagebox.showerror("错误", "请至少选择一种字符类型")
            return

        # 更新按钮状态
        self.generate_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.save_btn.config(state='disabled')

        # 清空文本显示
        self.text_display.delete(1.0, tk.END)
        self.progress['value'] = 0

        # 在新线程中生成文本
        self.generation_thread = threading.Thread(target=self._generate_text_thread)
        self.generation_thread.daemon = True
        self.generation_thread.start()

    def _generate_text_thread(self):
        """在后台线程中生成文本"""
        try:
            length = self.text_length.get()

            # 生成文本 - 确保正确传递字符类型参数
            generated_text = self.text_generator.generate_text(
                length=length,
                include_english=self.include_english.get(),
                include_chinese=self.include_chinese.get(),
                include_digits=self.include_digits.get(),
                include_special=self.include_special.get(),
                include_unicode=self.include_unicode.get(),
                progress_callback=self.update_progress,
                status_callback=self.update_status
            )

            # 在主线程中更新显示
            self.parent.after(0, self._generation_complete, generated_text)

        except Exception as e:
            self.parent.after(0, self._generation_failed, str(e))

    def _generation_complete(self, generated_text):
        """文本生成完成"""
        # 更新文本显示
        self.text_display.delete(1.0, tk.END)
        self.text_display.insert(1.0, generated_text)

        # 更新统计信息
        char_count = len(generated_text)
        self.stats_var.set(f"字符数: {char_count}")

        # 更新按钮状态
        self.generate_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.save_btn.config(state='normal')

        self.status_var.set(f"文本生成完成! 共生成 {char_count} 个字符")
        self.progress['value'] = 100

    def _generation_failed(self, error_msg):
        """文本生成失败"""
        self.status_var.set(f"生成失败: {error_msg}")
        self.progress['value'] = 0

        # 恢复按钮状态
        self.generate_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

    def stop_generation(self):
        """停止生成文本"""
        self.text_generator.stop_generation()
        self.status_var.set("正在停止生成...")

    def update_progress(self, progress):
        """更新进度条"""
        self.parent.after(0, lambda: self.progress.config(value=progress))

    def update_status(self, status):
        """更新状态"""
        self.parent.after(0, lambda: self.status_var.set(status))

    def save_to_file(self):
        """保存文本到文件"""
        text_content = self.text_display.get(1.0, tk.END).strip()
        if not text_content:
            messagebox.showwarning("警告", "没有文本内容可保存")
            return

        file_path = filedialog.asksaveasfilename(
            title="保存文本文件",
            defaultextension=".txt",
            filetypes=[
                ("文本文件", "*.txt"),
                ("所有文件", "*.*")
            ]
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                self.status_var.set(f"文本已保存到: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")

    def clear_text(self):
        """清空文本"""
        self.text_display.delete(1.0, tk.END)
        self.stats_var.set("字符数: 0")
        self.status_var.set("文本已清空")


# 文件计算校验标签页包装器
class FileChecksumTabWrapper:
    """文件计算校验标签页包装器"""

    def __init__(self, parent):
        self.tab = FileChecksumTab(parent)


# 文件对比标签页包装器
class FileComparisonTabWrapper:
    """文件对比标签页包装器"""

    def __init__(self, parent):
        self.tab = FileComparisonTab(parent)