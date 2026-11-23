"""
文件对比功能实现 - 优化版本，支持大文件快速对比和差异显示
新增文件夹对比功能，基于MD5值比较
"""

import difflib
import os
import hashlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import time
import threading
from pathlib import Path
import concurrent.futures
from docx import Document


class FileComparator:
    """文件比较器 - 优化版本，支持文件和文件夹对比"""

    def __init__(self):
        self.file1_content = ""
        self.file2_content = ""
        self.differences = []
        self.folder_differences = []
        self.folder_differences_full = []  # 存储完整的对比结果（包括相同文件）
        self.comparing = False
        self.stop_comparing = False
        self.folder1_files = {}  # 缓存文件夹1的扫描结果
        self.folder2_files = {}  # 缓存文件夹2的扫描结果
        self.current_comparison_type = None  # 当前对比类型

    def load_docx_as_text(self, file_path):
        """读取 docx 文件并返回 UTF-8 文本行列表"""
        doc = Document(file_path)
        lines = []
        for para in doc.paragraphs:
            if self.stop_comparing:
                break
            lines.append(para.text + "\n")
        return lines

    def load_file_fast(self, file_path, encoding='utf-8'):
        """快速加载文件内容 - 优化大文件读取"""
        try:
            content = []
            with open(file_path, 'r', encoding=encoding) as f:
                for line in f:
                    if self.stop_comparing:
                        break
                    content.append(line)
            return content
        except UnicodeDecodeError:
            encodings = ['gbk', 'latin-1', 'cp1252', 'iso-8859-1']
            for enc in encodings:
                try:
                    content = []
                    with open(file_path, 'r', encoding=enc) as f:
                        for line in f:
                            if self.stop_comparing:
                                break
                            content.append(line)
                    return content
                except UnicodeDecodeError:
                    continue
            raise Exception(f"无法解码文件: {file_path}")
        except Exception as e:
            raise Exception(f"读取文件失败: {str(e)}")

    def calculate_file_md5(self, file_path, chunk_size=8192):
        """计算文件的MD5值"""
        md5_hash = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    if self.stop_comparing:
                        return None
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            print(f"计算MD5失败 {file_path}: {e}")
            return None

    def calculate_file_md5_fast(self, file_info):
        """快速计算文件的MD5值 - 用于多线程"""
        file_path = file_info['path']
        md5_hash = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5_hash.update(chunk)
            file_info['md5'] = md5_hash.hexdigest()
            return file_info
        except Exception as e:
            print(f"计算MD5失败 {file_path}: {e}")
            return None

    def scan_folder_fast(self, folder_path, progress_callback=None, status_callback=None):
        """快速扫描文件夹，返回文件列表和MD5值字典 - 使用多线程加速"""
        file_info_list = []
        total_files = 0
        scanned_files = 0

        # 先统计文件总数
        try:
            for root, dirs, files in os.walk(folder_path):
                total_files += len(files)
        except Exception as e:
            if status_callback:
                status_callback(f"扫描文件夹失败: {str(e)}")
            return None

        if status_callback:
            status_callback(f"开始扫描文件夹，共发现 {total_files} 个文件...")

        try:
            # 第一步：收集所有文件信息（不包括MD5）
            for root, dirs, files in os.walk(folder_path):
                if self.stop_comparing:
                    break

                for file in files:
                    if self.stop_comparing:
                        break

                    file_full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_full_path, folder_path)

                    file_info_list.append({
                        'rel_path': rel_path,
                        'path': file_full_path,
                        'size': os.path.getsize(file_full_path),
                        'md5': None  # 稍后计算
                    })

            # 第二步：使用线程池并行计算MD5
            if status_callback:
                status_callback(f"正在计算文件MD5值...")

            # 使用多线程加速MD5计算
            file_info_dict = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                # 提交所有计算任务
                future_to_file = {executor.submit(self.calculate_file_md5_fast, info): info for info in file_info_list}

                for i, future in enumerate(concurrent.futures.as_completed(future_to_file)):
                    if self.stop_comparing:
                        break

                    result = future.result()
                    if result:
                        file_info_dict[result['rel_path']] = {
                            'path': result['path'],
                            'md5': result['md5'],
                            'size': result['size']
                        }

                    scanned_files += 1
                    if progress_callback and total_files > 0:
                        progress = (scanned_files / total_files) * 100
                        progress_callback(progress)

                    if status_callback and scanned_files % 100 == 0:
                        status_callback(f"已计算 {scanned_files}/{total_files} 个文件的MD5...")

            return file_info_dict

        except Exception as e:
            if status_callback:
                status_callback(f"扫描文件夹时出错: {str(e)}")
            return None

    def compare_folders_by_md5(self, folder1_path, folder2_path, hide_same=True, progress_callback=None, status_callback=None):
        """比较两个文件夹的内容，基于MD5值"""
        try:
            self.stop_comparing = False
            self.comparing = True
            self.folder_differences = []
            self.folder_differences_full = []
            self.current_comparison_type = "folder"

            # 验证文件夹存在
            if not os.path.exists(folder1_path) or not os.path.isdir(folder1_path):
                raise Exception(f"文件夹1不存在或不是文件夹: {folder1_path}")

            if not os.path.exists(folder2_path) or not os.path.isdir(folder2_path):
                raise Exception(f"文件夹2不存在或不是文件夹: {folder2_path}")

            # 扫描第一个文件夹
            if status_callback:
                status_callback("正在扫描文件夹1...")
            self.folder1_files = self.scan_folder_fast(folder1_path, progress_callback=progress_callback, status_callback=status_callback)
            if self.folder1_files is None or self.stop_comparing:
                return False

            # 扫描第二个文件夹
            if status_callback:
                status_callback("正在扫描文件夹2...")
            self.folder2_files = self.scan_folder_fast(folder2_path, progress_callback=progress_callback, status_callback=status_callback)
            if self.folder2_files is None or self.stop_comparing:
                return False

            # 比较文件
            if status_callback:
                status_callback("正在比较文件夹内容...")

            # 获取所有文件的相对路径
            all_files = set(self.folder1_files.keys()) | set(self.folder2_files.keys())

            for rel_path in sorted(all_files):
                if self.stop_comparing:
                    break

                file1_info = self.folder1_files.get(rel_path)
                file2_info = self.folder2_files.get(rel_path)

                diff_item = None
                if file1_info and file2_info:
                    # 文件在两个文件夹中都存在
                    if file1_info['md5'] == file2_info['md5']:
                        # MD5相同
                        diff_item = {
                            'status': 'same',
                            'relative_path': rel_path,
                            'file1_info': file1_info,
                            'file2_info': file2_info
                        }
                    else:
                        # MD5不同
                        diff_item = {
                            'status': 'different',
                            'relative_path': rel_path,
                            'file1_info': file1_info,
                            'file2_info': file2_info,
                            'md5_diff': f"{file1_info['md5']} ≠ {file2_info['md5']}"
                        }
                elif file1_info:
                    # 仅存在于文件夹1
                    diff_item = {
                        'status': 'only_in_1',
                        'relative_path': rel_path,
                        'file1_info': file1_info,
                        'file2_info': None
                    }
                else:
                    # 仅存在于文件夹2
                    diff_item = {
                        'status': 'only_in_2',
                        'relative_path': rel_path,
                        'file1_info': None,
                        'file2_info': file2_info
                    }

                # 添加到完整列表
                if diff_item:
                    self.folder_differences_full.append(diff_item)

            # 根据hide_same参数过滤结果
            self.apply_hide_same_filter(hide_same)

            self.comparing = False

            # 统计信息
            stats = self.get_folder_comparison_stats()
            if status_callback:
                status_callback(f"比较完成！相同文件: {stats['same_files']}, 不同文件: {stats['different_files']}, 仅存在于文件夹1: {stats['only_in_1']}, 仅存在于文件夹2: {stats['only_in_2']}")

            return True

        except Exception as e:
            self.comparing = False
            raise Exception(f"文件夹比较失败: {str(e)}")

    def apply_hide_same_filter(self, hide_same):
        """应用隐藏相同内容的过滤器"""
        if hide_same:
            # 隐藏相同文件
            self.folder_differences = [diff for diff in self.folder_differences_full if diff['status'] != 'same']
        else:
            # 显示所有文件
            self.folder_differences = self.folder_differences_full.copy()

    def toggle_hide_same_for_folders(self, hide_same):
        """切换文件夹对比的隐藏相同内容选项"""
        if self.current_comparison_type == "folder" and self.folder_differences_full:
            self.apply_hide_same_filter(hide_same)
            return True
        return False

    def get_folder_comparison_stats(self):
        """获取文件夹比较统计信息"""
        # 使用完整列表计算统计信息
        same_count = sum(1 for diff in self.folder_differences_full if diff['status'] == 'same')
        different_count = sum(1 for diff in self.folder_differences_full if diff['status'] == 'different')
        only_in_1_count = sum(1 for diff in self.folder_differences_full if diff['status'] == 'only_in_1')
        only_in_2_count = sum(1 for diff in self.folder_differences_full if diff['status'] == 'only_in_2')

        return {
            'total_files': len(self.folder_differences_full),
            'same_files': same_count,
            'different_files': different_count,
            'only_in_1': only_in_1_count,
            'only_in_2': only_in_2_count
        }

    def compare_files_fast(self, file1_path, file2_path, hide_same=True, progress_callback=None, status_callback=None):
        """快速比较两个文件 - 优化大文件对比"""
        try:
            self.stop_comparing = False
            self.comparing = True
            self.current_comparison_type = "file"

            # self.file1_content = self.load_file_fast(file1_path)
            if file1_path.lower().endswith(".docx"):
                self.file1_content = self.load_docx_as_text(file1_path)
            else:
                self.file1_content = self.load_file_fast(file1_path)

            if self.stop_comparing:
                return False

            # self.file2_content = self.load_file_fast(file2_path)
            if file2_path.lower().endswith(".docx"):
                self.file2_content = self.load_docx_as_text(file2_path)
            else:
                self.file2_content = self.load_file_fast(file2_path)

            if self.stop_comparing:
                return False

            max_lines = 50000
            if len(self.file1_content) > max_lines or len(self.file2_content) > max_lines:
                if not messagebox.askyesno("大文件警告",
                                          f"文件较大（超过{max_lines}行），完整比较可能较慢。\n是否继续完整比较？\n\n选择'否'将只比较前{max_lines}行"):
                    self.file1_content = self.file1_content[:max_lines]
                    self.file2_content = self.file2_content[:max_lines]

            differ = difflib.Differ()
            diff = list(differ.compare(self.file1_content, self.file2_content))

            self.differences = []
            line_num1 = 1
            line_num2 = 1

            for line in diff:
                if self.stop_comparing:
                    break

                if line.startswith('  '):
                    if not hide_same:
                        self.differences.append(('same', line_num1, line_num2, line[2:]))
                    line_num1 += 1
                    line_num2 += 1
                elif line.startswith('- '):
                    self.differences.append(('delete', line_num1, None, line[2:]))
                    line_num1 += 1
                elif line.startswith('+ '):
                    self.differences.append(('insert', None, line_num2, line[2:]))
                    line_num2 += 1
                elif line.startswith('? '):
                    continue

            self.comparing = False
            return True

        except Exception as e:
            self.comparing = False
            raise Exception(f"文件比较失败: {str(e)}")

    def stop_comparison(self):
        """停止比较"""
        self.stop_comparing = True
        self.comparing = False

    def get_comparison_stats(self):
        """获取比较统计信息"""
        same_count = sum(1 for diff in self.differences if diff[0] == 'same')
        delete_count = sum(1 for diff in self.differences if diff[0] == 'delete')
        insert_count = sum(1 for diff in self.differences if diff[0] == 'insert')

        return {
            'total_lines': len(self.differences),
            'same_lines': same_count,
            'different_lines': delete_count + insert_count,
            'delete_lines': delete_count,
            'insert_lines': insert_count
        }


class FileComparisonTab:
    """文件对比标签页 - 优化版本，支持大文件快速对比和文件夹对比"""

    def __init__(self, parent):
        self.parent = parent
        self.comparator = FileComparator()
        self.file1_path = ""
        self.file2_path = ""
        self.comparison_type = "file"  # 默认为文件对比
        self.setup_ui()

    def setup_ui(self):
        """设置用户界面"""
        # 标题
        title_label = ttk.Label(self.parent, text="文件/文件夹对比",
                                font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)

        # 说明信息
        info_text = """支持文本文件对比和文件夹对比
文件对比：差异使用颜色高亮显示，支持自动检测文件编码
文件夹对比：基于MD5值比较，显示文件差异状态
两个文件/文件夹都选择后自动开始对比
优化了大文件对比性能"""

        info_label = ttk.Label(self.parent, text=info_text, justify='left',
                               foreground='green', font=('Arial', 9))
        info_label.pack(pady=5, fill='x', padx=20)

        # 对比类型选择框架 - 使用单选框（圆圈选择）形式
        type_frame = ttk.LabelFrame(self.parent, text="对比类型", padding=10)
        type_frame.pack(pady=10, fill='x', padx=20)

        self.comparison_type_var = tk.StringVar(value="file")

        # 创建两个单选框
        radio_frame = ttk.Frame(type_frame)
        radio_frame.pack(fill='x', pady=5)

        ttk.Radiobutton(radio_frame, text="文件对比",
                       variable=self.comparison_type_var, value="file",
                       command=self.on_comparison_type_changed).pack(side='left', padx=20)

        ttk.Radiobutton(radio_frame, text="文件夹对比",
                       variable=self.comparison_type_var, value="folder",
                       command=self.on_comparison_type_changed).pack(side='left', padx=20)

        # 文件选择框架
        file_select_frame = ttk.Frame(self.parent)
        file_select_frame.pack(pady=10, fill='x', padx=20)

        # 文件1选择
        file1_frame = ttk.Frame(file_select_frame)
        file1_frame.pack(fill='x', pady=5)

        self.file1_label = ttk.Label(file1_frame, text="文件1:")
        self.file1_label.pack(side='left')

        self.file1_var = tk.StringVar()

        self.file1_entry = tk.Entry(file1_frame, textvariable=self.file1_var, width=50)
        self.file1_entry.pack(side='left', padx=5, fill='x', expand=True)

        file1_btn_frame = ttk.Frame(file1_frame)
        file1_btn_frame.pack(side='left')

        self.file1_browse_btn = ttk.Button(file1_btn_frame, text="浏览", command=lambda: self.browse_path(1))
        self.file1_browse_btn.pack(side='left')

        # 文件2选择
        file2_frame = ttk.Frame(file_select_frame)
        file2_frame.pack(fill='x', pady=5)

        self.file2_label = ttk.Label(file2_frame, text="文件2:")
        self.file2_label.pack(side='left')

        self.file2_var = tk.StringVar()

        self.file2_entry = tk.Entry(file2_frame, textvariable=self.file2_var, width=50)
        self.file2_entry.pack(side='left', padx=5, fill='x', expand=True)

        file2_btn_frame = ttk.Frame(file2_frame)
        file2_btn_frame.pack(side='left')

        self.file2_browse_btn = ttk.Button(file2_btn_frame, text="浏览", command=lambda: self.browse_path(2))
        self.file2_browse_btn.pack(side='left')

        # 快速操作框架
        quick_frame = ttk.Frame(self.parent)
        quick_frame.pack(pady=5, fill='x', padx=20)

        ttk.Button(quick_frame, text="选择两个对比",
                  command=self.select_both_paths).pack(side='left', padx=2)
        ttk.Button(quick_frame, text="清空选择",
                  command=self.clear_selection).pack(side='left', padx=2)
        ttk.Button(quick_frame, text="交换",
                  command=self.swap_paths).pack(side='left', padx=2)

        # 选项框架
        options_frame = ttk.Frame(self.parent)
        options_frame.pack(pady=10, fill='x', padx=20)

        # 隐藏相同内容选项
        self.hide_same_var = tk.BooleanVar(value=False)  # 文件对比默认不勾选
        self.hide_same_check = ttk.Checkbutton(options_frame, text="隐藏相同内容",
                       variable=self.hide_same_var, command=self.on_hide_same_changed)
        self.hide_same_check.pack(side='left', padx=10)

        # 只有文件对比时显示行号选项
        self.show_line_numbers_var = tk.BooleanVar(value=True)
        self.show_line_numbers_check = ttk.Checkbutton(options_frame, text="显示行号",
                       variable=self.show_line_numbers_var)
        self.show_line_numbers_check.pack(side='left', padx=10)

        # 按钮框架
        btn_frame = ttk.Frame(self.parent)
        btn_frame.pack(pady=10, fill='x', padx=20)

        self.compare_btn = ttk.Button(btn_frame, text="开始对比",
                  command=self.start_comparison)
        self.compare_btn.pack(side='left', padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="停止对比",
                  command=self.stop_comparison, state='disabled')
        self.stop_btn.pack(side='left', padx=5)

        ttk.Button(btn_frame, text="清空结果",
                  command=self.clear_results).pack(side='left', padx=5)

        ttk.Button(btn_frame, text="保存结果",
                  command=self.save_results).pack(side='left', padx=5)

        # 进度条
        self.progress = ttk.Progressbar(self.parent, orient='horizontal',
                                       length=400, mode='indeterminate')
        self.progress.pack(pady=5, fill='x', padx=20)

        # 统计信息框架
        stats_frame = ttk.Frame(self.parent)
        stats_frame.pack(pady=5, fill='x', padx=20)

        self.stats_var = tk.StringVar(value="就绪 - 使用上方按钮选择要对比的文件或文件夹")

        stats_label = ttk.Label(stats_frame, textvariable=self.stats_var,
                               foreground='blue', font=('Arial', 9))
        stats_label.pack(anchor='w')

        # 对比结果显示框架
        result_frame = ttk.Frame(self.parent)
        result_frame.pack(pady=10, fill='both', expand=True, padx=20)

        # 创建对比结果显示区域
        self.setup_result_display(result_frame)

    def setup_result_display(self, parent_frame):
        """设置结果显示区域"""
        # 创建Notebook，用于切换文件和文件夹对比结果
        self.result_notebook = ttk.Notebook(parent_frame)
        self.result_notebook.pack(fill='both', expand=True)

        # 文件对比结果标签页
        self.file_result_frame = ttk.Frame(self.result_notebook)
        self.result_notebook.add(self.file_result_frame, text="文件对比结果")

        # 创建左右分栏的文件对比显示
        file_comparison_frame = ttk.Frame(self.file_result_frame)
        file_comparison_frame.pack(fill='both', expand=True)

        # 左侧：文件1内容
        left_frame = ttk.Frame(file_comparison_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 2))

        ttk.Label(left_frame, text="文件1内容", font=('Arial', 10, 'bold')).pack(anchor='w')

        self.file1_text = scrolledtext.ScrolledText(
            left_frame, wrap=tk.WORD, width=40, height=20,
            font=('Courier New', 10), bg='#F8F8F8')

        # 配置左侧文本样式
        self.file1_text.tag_configure("same", foreground="black")
        self.file1_text.tag_configure("delete", foreground="red", font=('Courier New', 10, 'bold'))
        self.file1_text.tag_configure("line_num", foreground="gray", font=('Courier New', 9))

        self.file1_text.pack(fill='both', expand=True)

        # 右侧：文件2内容
        right_frame = ttk.Frame(file_comparison_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=(2, 0))

        ttk.Label(right_frame, text="文件2内容", font=('Arial', 10, 'bold')).pack(anchor='w')

        self.file2_text = scrolledtext.ScrolledText(
            right_frame, wrap=tk.WORD, width=40, height=20,
            font=('Courier New', 10), bg='#F8F8F8')

        # 配置右侧文本样式
        self.file2_text.tag_configure("same", foreground="black")
        self.file2_text.tag_configure("insert", foreground="red", font=('Courier New', 10, 'bold'))
        self.file2_text.tag_configure("line_num", foreground="gray", font=('Courier New', 9))

        self.file2_text.pack(fill='both', expand=True)

        # 同步两个文本区域的滚动
        self.file1_text.config(yscrollcommand=self._sync_scroll_y)
        self.file2_text.config(yscrollcommand=self._sync_scroll_y)

        # 文件夹对比结果标签页
        self.folder_result_frame = ttk.Frame(self.result_notebook)
        self.result_notebook.add(self.folder_result_frame, text="文件夹对比结果")

        # 创建Treeview显示文件夹对比结果
        self.folder_tree = ttk.Treeview(self.folder_result_frame, columns=('status', 'relative_path', 'md5_1', 'md5_2', 'size_1', 'size_2'),
                                         show='headings', height=20)

        # 定义列
        columns = [
            ('status', '状态', 120),
            ('relative_path', '相对路径', 300),
            ('md5_1', 'MD5 (文件夹1)', 150),
            ('md5_2', 'MD5 (文件夹2)', 150),
            ('size_1', '大小 (文件夹1)', 100),
            ('size_2', '大小 (文件夹2)', 100)
        ]

        for col_id, col_text, width in columns:
            self.folder_tree.heading(col_id, text=col_text)
            self.folder_tree.column(col_id, width=width)

        # 配置Treeview标签
        self.folder_tree.tag_configure('same', background='#d4edda')  # 绿色背景
        self.folder_tree.tag_configure('different', background='#f8d7da')  # 红色背景
        self.folder_tree.tag_configure('only_in_1', background='#fff3cd')  # 黄色背景
        self.folder_tree.tag_configure('only_in_2', background='#d1ecf1')  # 蓝色背景

        # 滚动条
        folder_scrollbar = ttk.Scrollbar(self.folder_result_frame, orient='vertical', command=self.folder_tree.yview)
        self.folder_tree.configure(yscrollcommand=folder_scrollbar.set)

        self.folder_tree.pack(side='left', fill='both', expand=True)
        folder_scrollbar.pack(side='right', fill='y')

        # 初始显示文件对比结果
        self.result_notebook.select(self.file_result_frame)

    def _sync_scroll_y(self, *args):
        """同步左右两个文本区域的滚动"""
        self.file1_text.yview_moveto(args[0])
        self.file2_text.yview_moveto(args[0])

    def on_comparison_type_changed(self, event=None):
        """对比类型改变事件"""
        self.comparison_type = self.comparison_type_var.get()

        # 更新标签文本
        if self.comparison_type == "file":
            self.file1_label.config(text="文件1:")
            self.file2_label.config(text="文件2:")
            self.file1_browse_btn.config(text="浏览")
            self.file2_browse_btn.config(text="浏览")
            self.show_line_numbers_check.pack(side='left', padx=10)  # 显示行号选项
            self.hide_same_var.set(False)  # 文件对比默认不勾选隐藏相同内容
        else:
            self.file1_label.config(text="文件夹1:")
            self.file2_label.config(text="文件夹2:")
            self.file1_browse_btn.config(text="浏览文件夹")
            self.file2_browse_btn.config(text="浏览文件夹")
            self.show_line_numbers_check.pack_forget()  # 隐藏行号选项
            self.hide_same_var.set(True)  # 文件夹对比默认勾选隐藏相同内容

        # 清空选择
        self.clear_selection()
        self.clear_results()

        # 切换结果显示标签页
        if self.comparison_type == "file":
            self.result_notebook.select(self.file_result_frame)
        else:
            self.result_notebook.select(self.folder_result_frame)

    def on_hide_same_changed(self):
        """隐藏相同内容选项改变事件"""
        if self.comparison_type == "folder":
            # 对于文件夹对比，直接应用过滤器，不需要重新对比
            if self.comparator.current_comparison_type == "folder" and self.comparator.folder_differences_full:
                # 应用过滤器
                hide_same = self.hide_same_var.get()
                self.comparator.apply_hide_same_filter(hide_same)

                # 刷新显示
                self.display_folder_comparison_results()

                # 更新统计信息
                stats = self.comparator.get_folder_comparison_stats()
                self.update_folder_stats(stats)

                # 显示提示信息
                if hide_same:
                    self.stats_var.set("已隐藏相同文件")
                else:
                    self.stats_var.set("已显示所有文件")
            else:
                # 如果没有对比结果，则开始对比
                self.start_comparison()
        else:
            # 对于文件对比，需要重新对比
            self.start_comparison()

    def browse_path(self, path_num):
        """浏览选择文件或文件夹"""
        if self.comparison_type == "file":
            # 选择文件
            file_path = filedialog.askopenfilename(
                title=f"选择文件{path_num}",
                filetypes=[
                    ("所有文件", "*.*"),
                    ("文档文件", "*.docx"),
                    ("文本文件", "*.txt;*.log;*.ini;*.xml;*.json"),
                    ("代码文件", "*.py;*.java;*.cpp;*.c;*.h;*.js;*.html;*.css")
                ]
            )
        else:
            # 选择文件夹
            file_path = filedialog.askdirectory(title=f"选择文件夹{path_num}")

        if file_path:
            self._set_path(file_path, path_num)
            self.stats_var.set(f"✅ 已设置{'文件' if self.comparison_type == 'file' else '文件夹'}{path_num}: {os.path.basename(file_path)}")

    def _set_path(self, path, path_num):
        """设置路径的通用方法"""
        if path_num == 1:
            self.file1_path = path
            self.file1_var.set(path)
        else:
            self.file2_path = path
            self.file2_var.set(path)

        # 检查是否两个路径都已设置，如果是则自动开始对比
        if self.file1_path and self.file2_path:
            self.stats_var.set("✅ 两个路径已设置，自动开始对比...")
            self.start_comparison()

    def select_both_paths(self):
        """一次性选择两个文件或文件夹进行对比"""
        if self.comparison_type == "file":
            # 选择两个文件
            files = filedialog.askopenfilenames(
                title="选择两个要对比的文件",
                filetypes=[
                    ("所有文件", "*.*"),
                    ("文本文件", "*.txt;*.log;*.ini;*.xml;*.json"),
                    ("代码文件", "*.py;*.java;*.cpp;*.c;*.h;*.js;*.html;*.css")
                ]
            )

            if len(files) >= 2:
                self._set_path(files[0], 1)
                self._set_path(files[1], 2)
            elif len(files) == 1:
                self._set_path(files[0], 1)
                self.stats_var.set("✅ 已设置路径1，请选择路径2")
        else:
            # 选择两个文件夹
            folder1 = filedialog.askdirectory(title="选择第一个文件夹")
            if folder1:
                self._set_path(folder1, 1)
                folder2 = filedialog.askdirectory(title="选择第二个文件夹")
                if folder2:
                    self._set_path(folder2, 2)
                else:
                    self.stats_var.set("✅ 已设置文件夹1，请选择文件夹2")

    def swap_paths(self):
        """交换路径1和路径2"""
        if self.file1_path and self.file2_path:
            # 交换路径
            self.file1_path, self.file2_path = self.file2_path, self.file1_path
            self.file1_var.set(self.file1_path)
            self.file2_var.set(self.file2_path)
            self.stats_var.set("✅ 已交换路径1和路径2")

            # 如果已经有对比结果，重新对比
            if self.comparison_type == "file" and self.comparator.differences:
                self.start_comparison()
            elif self.comparison_type == "folder" and self.comparator.folder_differences:
                self.start_comparison()

    def clear_selection(self):
        """清空路径选择"""
        self.file1_path = ""
        self.file2_path = ""
        self.file1_var.set("")
        self.file2_var.set("")
        self.stats_var.set("✅ 已清空路径选择")

    def start_comparison(self):
        """开始对比 - 使用多线程避免界面卡死"""
        if not self.file1_path or not os.path.exists(self.file1_path):
            messagebox.showerror("错误", "请选择有效的路径1")
            return

        if not self.file2_path or not os.path.exists(self.file2_path):
            messagebox.showerror("错误", "请选择有效的路径2")
            return

        # 根据类型验证路径
        if self.comparison_type == "file":
            if not os.path.isfile(self.file1_path):
                messagebox.showerror("错误", "路径1不是文件")
                return
            if not os.path.isfile(self.file2_path):
                messagebox.showerror("错误", "路径2不是文件")
                return
        else:
            if not os.path.isdir(self.file1_path):
                messagebox.showerror("错误", "路径1不是文件夹")
                return
            if not os.path.isdir(self.file2_path):
                messagebox.showerror("错误", "路径2不是文件夹")
                return

        # 清空显示区域
        self.clear_results()

        # 更新按钮状态
        self.compare_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.progress.config(mode='indeterminate')
        self.progress.start()

        # 在新线程中执行对比
        thread = threading.Thread(target=self._compare_thread)
        thread.daemon = True
        thread.start()

    def _compare_thread(self):
        """在后台线程中执行对比"""
        try:
            hide_same = self.hide_same_var.get()

            if self.comparison_type == "file":
                # 文件对比
                success = self.comparator.compare_files_fast(
                    self.file1_path, self.file2_path, hide_same,
                    progress_callback=self._update_progress,
                    status_callback=self._update_status
                )

                if success:
                    stats = self.comparator.get_comparison_stats()
                    if stats['different_lines'] == 0:
                        self.parent.after(0, self._show_no_differences)
                    else:
                        self.parent.after(0, self._display_file_comparison_results, stats)
                else:
                    self.parent.after(0, lambda: self.stats_var.set("对比已停止"))
            else:
                # 文件夹对比
                success = self.comparator.compare_folders_by_md5(
                    self.file1_path, self.file2_path, hide_same,
                    progress_callback=self._update_progress,
                    status_callback=self._update_status
                )

                if success:
                    stats = self.comparator.get_folder_comparison_stats()
                    # 检查是否有差异（不考虑相同文件）
                    filtered_diffs = [d for d in self.comparator.folder_differences if d['status'] != 'same']
                    if not filtered_diffs:
                        self.parent.after(0, self._show_no_differences)
                    else:
                        self.parent.after(0, self._display_folder_comparison_results, stats)
                else:
                    self.parent.after(0, lambda: self.stats_var.set("对比已停止"))

        except Exception as e:
            self.parent.after(0, lambda: self._show_error(f"对比失败: {str(e)}"))

    def _update_progress(self, progress):
        """更新进度"""
        self.parent.after(0, lambda: self.progress.config(mode='determinate', value=progress))

    def _update_status(self, status):
        """更新状态"""
        self.parent.after(0, lambda: self.stats_var.set(status))

    def _show_no_differences(self):
        """显示无差异提示"""
        self.progress.stop()
        self.compare_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        messagebox.showinfo("对比结果", f"{'文件' if self.comparison_type == 'file' else '文件夹'}内容完全相同，没有差异！")
        self.stats_var.set(f"✅ 对比完成 - {'文件' if self.comparison_type == 'file' else '文件夹'}内容相同")

    def _show_error(self, error_msg):
        """显示错误信息"""
        self.progress.stop()
        self.compare_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        messagebox.showerror("错误", error_msg)
        self.stats_var.set(f"❌ {error_msg}")

    def _display_file_comparison_results(self, stats):
        """显示文件对比结果"""
        self.display_comparison_results()
        self.update_stats(stats)
        self.progress.stop()
        self.compare_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

    def _display_folder_comparison_results(self, stats):
        """显示文件夹对比结果"""
        self.display_folder_comparison_results()
        self.update_folder_stats(stats)
        self.progress.stop()
        self.compare_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

    def stop_comparison(self):
        """停止对比"""
        self.comparator.stop_comparison()
        self.stats_var.set("正在停止对比...")

    def display_comparison_results(self):
        """显示文件对比结果 - 左右分栏显示，相同内容黑色，差异内容红色"""
        self.file1_text.delete(1.0, tk.END)
        self.file2_text.delete(1.0, tk.END)

        show_line_numbers = self.show_line_numbers_var.get()

        # 分别处理左右两侧的显示
        left_lines = []
        right_lines = []

        for diff_type, line1, line2, content in self.comparator.differences:
            line_prefix_left = ""
            line_prefix_right = ""

            if show_line_numbers:
                if line1:
                    line_prefix_left = f"{line1:4d} "
                if line2:
                    line_prefix_right = f"{line2:4d} "

            if diff_type == 'same':
                left_lines.append(('same', line_prefix_left, content))
                right_lines.append(('same', line_prefix_right, content))
            elif diff_type == 'delete':
                left_lines.append(('delete', line_prefix_left, content))
                right_lines.append(('same', line_prefix_right, ""))
            elif diff_type == 'insert':
                left_lines.append(('same', line_prefix_left, ""))
                right_lines.append(('insert', line_prefix_right, content))

        # 显示左侧内容（文件1）
        for tag, prefix, content in left_lines:
            if show_line_numbers:
                self.file1_text.insert(tk.END, prefix, "line_num")
            self.file1_text.insert(tk.END, content, tag)

        # 显示右侧内容（文件2）
        for tag, prefix, content in right_lines:
            if show_line_numbers:
                self.file2_text.insert(tk.END, prefix, "line_num")
            self.file2_text.insert(tk.END, content, tag)

        self.stats_var.set("✅ 文件对比完成")

    def display_folder_comparison_results(self):
        """显示文件夹对比结果"""
        # 清空Treeview
        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)

        # 添加对比结果
        for diff in self.comparator.folder_differences:
            status = diff['status']
            relative_path = diff['relative_path']
            file1_info = diff.get('file1_info')
            file2_info = diff.get('file2_info')

            # 根据状态设置显示
            status_text = ""
            if status == 'same':
                status_text = "文件相同"
            elif status == 'different':
                status_text = "文件不同"
            elif status == 'only_in_1':
                status_text = "仅存在于文件夹1"
            elif status == 'only_in_2':
                status_text = "仅存在于文件夹2"

            md5_1 = file1_info['md5'][:16] + "..." if file1_info and file1_info['md5'] else ""
            md5_2 = file2_info['md5'][:16] + "..." if file2_info and file2_info['md5'] else ""

            size_1 = self._format_size(file1_info['size']) if file1_info else ""
            size_2 = self._format_size(file2_info['size']) if file2_info else ""

            # 插入到Treeview，并设置标签
            item_id = self.folder_tree.insert('', 'end', values=(
                status_text,
                relative_path,
                md5_1,
                md5_2,
                size_1,
                size_2
            ))

            # 根据状态设置行颜色
            if status == 'same':
                self.folder_tree.item(item_id, tags=('same',))
            elif status == 'different':
                self.folder_tree.item(item_id, tags=('different',))
            elif status == 'only_in_1':
                self.folder_tree.item(item_id, tags=('only_in_1',))
            elif status == 'only_in_2':
                self.folder_tree.item(item_id, tags=('only_in_2',))

        self.stats_var.set("✅ 文件夹对比完成")

    def _format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"

    def update_stats(self, stats):
        """更新文件对比统计信息"""
        stats_text = (f"对比统计: 总行数 {stats['total_lines']} | "
                     f"相同行 {stats['same_lines']} | "
                     f"差异行 {stats['different_lines']} "
                     f"(删除 {stats['delete_lines']}, 新增 {stats['insert_lines']})")
        self.stats_var.set(stats_text)

    def update_folder_stats(self, stats):
        """更新文件夹对比统计信息"""
        # 计算显示的文件数（考虑隐藏相同内容选项）
        display_count = len(self.comparator.folder_differences)

        stats_text = (f"文件夹对比统计: 总文件数 {stats['total_files']} | "
                     f"相同文件 {stats['same_files']} | "
                     f"不同文件 {stats['different_files']} | "
                     f"仅存在于文件夹1 {stats['only_in_1']} | "
                     f"仅存在于文件夹2 {stats['only_in_2']}")

        if self.hide_same_var.get():
            stats_text += f" (显示 {display_count} 个文件)"

        self.stats_var.set(stats_text)

    def clear_results(self):
        """清空结果"""
        self.file1_text.delete(1.0, tk.END)
        self.file2_text.delete(1.0, tk.END)

        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)

        self.stats_var.set("✅ 对比结果已清空")

    def save_results(self):
        """保存对比结果"""
        if self.comparison_type == "file":
            if not self.comparator.differences:
                messagebox.showwarning("警告", "没有可保存的文件对比结果")
                return

            self._save_file_comparison_results()
        else:
            if not self.comparator.folder_differences:
                messagebox.showwarning("警告", "没有可保存的文件夹对比结果")
                return

            self._save_folder_comparison_results()

    def _save_file_comparison_results(self):
        """保存文件对比结果"""
        file_path = filedialog.asksaveasfilename(
            title="保存文件对比结果",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"文件对比结果\n")
                    f.write(f"文件1: {self.file1_path}\n")
                    f.write(f"文件2: {self.file2_path}\n")
                    f.write("="*50 + "\n\n")

                    # 保存左右对比格式
                    f.write("文件1内容:\n")
                    f.write(self.file1_text.get(1.0, tk.END))
                    f.write("\n" + "="*50 + "\n\n")
                    f.write("文件2内容:\n")
                    f.write(self.file2_text.get(1.0, tk.END))

                self.stats_var.set(f"✅ 文件对比结果已保存到: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")

    def _save_folder_comparison_results(self):
        """保存文件夹对比结果"""
        file_path = filedialog.asksaveasfilename(
            title="保存文件夹对比结果",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"文件夹对比结果\n")
                    f.write(f"文件夹1: {self.file1_path}\n")
                    f.write(f"文件夹2: {self.file2_path}\n")
                    f.write("="*80 + "\n\n")

                    # 保存统计信息
                    stats = self.comparator.get_folder_comparison_stats()
                    f.write(f"对比统计:\n")
                    f.write(f"  总文件数: {stats['total_files']}\n")
                    f.write(f"  相同文件: {stats['same_files']}\n")
                    f.write(f"  不同文件: {stats['different_files']}\n")
                    f.write(f"  仅存在于文件夹1: {stats['only_in_1']}\n")
                    f.write(f"  仅存在于文件夹2: {stats['only_in_2']}\n")
                    f.write("\n" + "="*80 + "\n\n")

                    # 保存详细对比结果
                    f.write("详细对比结果:\n")
                    f.write(f"{'状态':<20} {'相对路径':<40} {'MD5 (文件夹1)':<35} {'MD5 (文件夹2)':<35} {'大小 (文件夹1)':<15} {'大小 (文件夹2)':<15}\n")
                    f.write("-"*160 + "\n")

                    for diff in self.comparator.folder_differences_full:  # 保存完整结果
                        status = diff['status']
                        relative_path = diff['relative_path']
                        file1_info = diff.get('file1_info')
                        file2_info = diff.get('file2_info')

                        # 根据状态设置显示
                        status_text = ""
                        if status == 'same':
                            status_text = "文件相同"
                        elif status == 'different':
                            status_text = "文件不同"
                        elif status == 'only_in_1':
                            status_text = "仅存在于文件夹1"
                        elif status == 'only_in_2':
                            status_text = "仅存在于文件夹2"

                        md5_1 = file1_info['md5'] if file1_info and file1_info['md5'] else ""
                        md5_2 = file2_info['md5'] if file2_info and file2_info['md5'] else ""

                        size_1 = self._format_size(file1_info['size']) if file1_info else ""
                        size_2 = self._format_size(file2_info['size']) if file2_info else ""

                        f.write(f"{status_text:<20} {relative_path:<40} {md5_1:<35} {md5_2:<35} {size_1:<15} {size_2:<15}\n")

                self.stats_var.set(f"✅ 文件夹对比结果已保存到: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")