#!/usr/bin/env python3
"""
文件操作工具 - 完全重写编译脚本
使用 PyInstaller 将 Python 代码编译为可执行文件
"""

import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path


class Compiler:
    """编译器类 - 完全重写版本"""

    def __init__(self):
        self.current_dir = os.getcwd()
        self.dependencies_checked = False

    def check_environment(self):
        """检查编译环境"""
        print("=" * 60)
        print("FileOperationTool 编译工具 - 完全重写版本")
        print("=" * 60)

        # 检查当前目录
        if not os.path.exists('main.py'):
            print("❌ 错误: 请在项目根目录运行此脚本!")
            return False

        # 检查图标文件
        if not self.check_icon_file():
            print("❌ 图标文件检查失败!")
            return False

        return True

    def check_icon_file(self):
        """检查图标文件 - 优先使用程序目录下的 FileTestTool_icon.ico"""
        # 首先尝试当前目录
        icon_file = 'FileTestTool_icon.ico'
        if not os.path.exists(icon_file):
            # 尝试其他可能的位置
            search_paths = [
                './FileTestTool_icon.ico',
                '../FileTestTool_icon.ico',
                '../../FileTestTool_icon.ico'
            ]

            for path in search_paths:
                if os.path.exists(path):
                    # 复制到当前目录
                    shutil.copy2(path, 'FileTestTool_icon.ico')
                    print(f"✅ 找到并复制图标文件: {path} -> {icon_file}")
                    break
            else:
                print(f"❌ 未找到图标文件: {icon_file}")
                print("请将 FileTestTool_icon.ico 文件放在当前目录")
                return False

        # 验证图标文件
        try:
            file_size = os.path.getsize(icon_file)
            if file_size < 1024:
                print("⚠️ 警告: 图标文件可能太小")
            print(f"✅ 找到图标文件: {icon_file} ({file_size} 字节)")
            return True
        except Exception as e:
            print(f"❌ 检查图标文件失败: {e}")
            return False

    def install_dependencies(self):
        """安装依赖"""
        print("\n正在检查依赖...")

        dependencies = [
            'psutil',
            'pywin32',
            'pyinstaller'
        ]

        missing_deps = []

        for dep in dependencies:
            try:
                __import__(dep)
                print(f"✅ {dep} 已安装")
            except ImportError:
                print(f"❌ {dep} 未安装")
                missing_deps.append(dep)

        if missing_deps:
            print(f"\n正在安装缺失的依赖: {', '.join(missing_deps)}")
            try:
                subprocess.check_call([
                                          sys.executable, "-m", "pip", "install"
                                      ] + missing_deps)
                print("✅ 依赖安装成功!")
            except subprocess.CalledProcessError:
                print("❌ 依赖安装失败!")
                return False

        self.dependencies_checked = True
        return True

    def compile_memory_test_tools(self):
        """编译内存测试工具 - 只编译GUI版本"""
        print("\n正在编译内存测试工具...")

        # 只编译GUI版本，删除控制台版本编译
        if not self._compile_gui_memory_tool():
            print("❌ GUI内存测试工具编译失败")
            return False

        print("✅ 内存测试工具编译完成")
        return True

    def _compile_gui_memory_tool(self):
        """编译GUI内存测试工具 - 支持多种内存分配策略版本"""
        # 代码保持不变，因为这部分不涉及图标
        gui_code = '''import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import psutil
import ctypes
import sys
import os
import random
import argparse

class MemoryAllocator:
    """内存分配器 - 支持多种内存分配策略"""

    def __init__(self):
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.allocated_blocks = []
        self.total_committed = 0
        self.total_working_set = 0
        self.stop_allocating = False
        self.allocation_complete = False
        self.strategy = "commit"  # 默认策略
        self.commit_ratio = 100
        self.working_set_ratio = 0

    def set_allocation_strategy(self, strategy, commit_ratio=100, working_set_ratio=0):
        """设置内存分配策略和比例"""
        self.strategy = strategy
        self.commit_ratio = commit_ratio
        self.working_set_ratio = working_set_ratio

        # 根据策略自动设置比例
        if strategy == "commit":
            self.commit_ratio = 100
            self.working_set_ratio = 0
        # 对于mixed策略，使用传入的比例

    def allocate_memory_with_strategy(self, size_mb, progress_callback=None, status_callback=None):
        """根据策略分配内存"""
        # 根据策略计算目标内存大小
        if self.strategy == "commit":
            # 全部占用提交大小
            target_commit_bytes = size_mb * 1024 * 1024
            target_working_set_bytes = 0
        elif self.strategy == "working_set":
            # 全部占用专用工作集 - 修复：需要先提交内存再占用工作集
            target_commit_bytes = size_mb * 1024 * 1024  # 先提交全部内存
            target_working_set_bytes = size_mb * 1024 * 1024  # 然后全部占用工作集
        else:
            # 混合比例分配
            target_commit_bytes = int(size_mb * self.commit_ratio / 100 * 1024 * 1024)
            target_working_set_bytes = int(size_mb * self.working_set_ratio / 100 * 1024 * 1024)

        self.total_committed = 0
        self.total_working_set = 0
        self.stop_allocating = False
        self.allocation_complete = False

        # 显示分配策略信息
        if status_callback:
            if self.strategy == "commit":
                status_text = f"开始分配内存: 提交大小 100% ({size_mb}MB)"
            elif self.strategy == "working_set":
                status_text = f"开始分配内存: 专用工作集 100% ({size_mb}MB)"
            else:
                status_text = f"开始分配内存: 提交大小 {self.commit_ratio}% ({target_commit_bytes//1024//1024}MB), 专用工作集 {self.working_set_ratio}% ({target_working_set_bytes//1024//1024}MB)"
            status_callback(status_text)

        # 定义Windows API常量
        MEM_COMMIT = 0x00001000
        MEM_RESERVE = 0x00002000
        PAGE_READWRITE = 0x04

        try:
            # 使用固定块大小
            chunk_size_mb = 10
            chunk_size_bytes = chunk_size_mb * 1024 * 1024

            # 分配提交内存
            while self.total_committed < target_commit_bytes and not self.stop_allocating:
                current_chunk_bytes = min(chunk_size_bytes, target_commit_bytes - self.total_committed)

                # 使用VirtualAlloc分配内存
                memory_block = self.kernel32.VirtualAlloc(
                    None,
                    current_chunk_bytes,
                    MEM_RESERVE | MEM_COMMIT,
                    PAGE_READWRITE
                )

                if not memory_block:
                    if status_callback:
                        status_callback(f"提交内存分配失败在 {self.total_committed//1024//1024}MB")
                    break

                # 转换为可写入的指针
                memory_ptr = ctypes.cast(memory_block, ctypes.POINTER(ctypes.c_byte))

                # 写入数据以确保内存被实际提交和工作集占用
                # 修复：对于working_set策略，需要写入所有分配的内存来确保工作集占用
                bytes_to_touch = 0
                if self.strategy == "working_set":
                    # working_set策略：写入全部内存以确保工作集占用
                    bytes_to_touch = current_chunk_bytes
                elif self.strategy == "mixed":
                    # mixed策略：按比例写入
                    remaining_working_set = target_working_set_bytes - self.total_working_set
                    bytes_to_touch = min(current_chunk_bytes, remaining_working_set)
                # commit策略不需要写入（不占用工作集）

                if bytes_to_touch > 0:
                    try:
                        # 分页写入以确保工作集占用
                        page_size = 4096
                        for j in range(0, bytes_to_touch, page_size):
                            if j < current_chunk_bytes:
                                memory_ptr[j] = random.randint(0, 255)
                                # 确保每页都被访问到
                                if j + page_size - 1 < current_chunk_bytes:
                                    memory_ptr[j + page_size - 1] = random.randint(0, 255)
                        self.total_working_set += bytes_to_touch
                    except Exception as e:
                        if status_callback:
                            status_callback(f"写入内存时出错: {e}")
                        # 继续分配，不中断

                self.allocated_blocks.append((memory_block, current_chunk_bytes))
                self.total_committed += current_chunk_bytes

                # 计算总体进度
                total_target = max(target_commit_bytes, target_working_set_bytes)
                if total_target > 0:
                    if self.strategy == "commit":
                        progress = (self.total_committed / total_target) * 100
                    elif self.strategy == "working_set":
                        progress = (self.total_working_set / total_target) * 100
                    else:
                        # 混合策略：取两者进度的最大值
                        commit_progress = (self.total_committed / target_commit_bytes) * 100 if target_commit_bytes > 0 else 0
                        working_set_progress = (self.total_working_set / target_working_set_bytes) * 100 if target_working_set_bytes > 0 else 0
                        progress = max(commit_progress, working_set_progress)
                else:
                    progress = 0

                if progress_callback:
                    progress_callback(min(progress, 100.0))

                # 状态更新
                current_commit_mb = self.total_committed // 1024 // 1024
                current_working_set_mb = self.total_working_set // 1024 // 1024

                if status_callback and (current_commit_mb % 100 == 0 or current_working_set_mb % 100 == 0):
                    if self.strategy == "commit":
                        status_callback(f"已分配提交内存: {current_commit_mb}MB/{size_mb}MB")
                    elif self.strategy == "working_set":
                        status_callback(f"已分配专用工作集: {current_working_set_mb}MB/{size_mb}MB")
                    else:
                        status_callback(f"已分配: 提交 {current_commit_mb}MB/{target_commit_bytes//1024//1024}MB, 专用工作集 {current_working_set_mb}MB/{target_working_set_bytes//1024//1024}MB")

                time.sleep(0.01)

            # 标记分配完成
            self.allocation_complete = True

            final_commit_mb = self.total_committed // 1024 // 1024
            final_working_set_mb = self.total_working_set // 1024 // 1024

            # 根据策略显示完成信息
            if status_callback:
                if self.strategy == "commit":
                    if self.total_committed >= target_commit_bytes * 0.95:
                        status_callback(f"✅ 分配成功: 提交 {final_commit_mb}MB/{size_mb}MB\\n内存占用保持中，进程持续运行...")
                    else:
                        status_callback(f"⚠️ 分配部分完成: 提交 {final_commit_mb}MB/{size_mb}MB\\n内存占用保持中，进程持续运行...")
                elif self.strategy == "working_set":
                    if self.total_working_set >= target_working_set_bytes * 0.95:
                        status_callback(f"✅ 分配成功: 专用工作集 {final_working_set_mb}MB/{size_mb}MB\\n内存占用保持中，进程持续运行...")
                    else:
                        status_callback(f"⚠️ 分配部分完成: 专用工作集 {final_working_set_mb}MB/{size_mb}MB\\n内存占用保持中，进程持续运行...")
                else:
                    commit_success = self.total_committed >= target_commit_bytes * 0.95 if target_commit_bytes > 0 else True
                    working_set_success = self.total_working_set >= target_working_set_bytes * 0.95 if target_working_set_bytes > 0 else True
                    if commit_success and working_set_success:
                        status_callback(f"✅ 分配成功: 提交 {final_commit_mb}MB, 专用工作集 {final_working_set_mb}MB\\n内存占用保持中，进程持续运行...")
                    else:
                        status_callback(f"⚠️ 分配部分完成: 提交 {final_commit_mb}MB, 专用工作集 {final_working_set_mb}MB\\n内存占用保持中，进程持续运行...")

            return self.total_committed + self.total_working_set

        except Exception as e:
            if status_callback:
                status_callback(f"分配过程中出错: {e}")
            return self.total_committed + self.total_working_set

    def free_memory(self):
        """释放所有分配的内存"""
        MEM_RELEASE = 0x8000
        freed_bytes = 0

        for memory_block, size in self.allocated_blocks:
            if memory_block:
                try:
                    if self.kernel32.VirtualFree(memory_block, 0, MEM_RELEASE):
                        freed_bytes += size
                except:
                    pass

        self.allocated_blocks.clear()
        self.total_committed = 0
        self.total_working_set = 0
        return freed_bytes

    def stop(self):
        """停止分配"""
        self.stop_allocating = True

    def get_committed_memory(self):
        """获取已提交的内存大小"""
        return self.total_committed

    def get_working_set_memory(self):
        """获取工作集内存大小"""
        return self.total_working_set

    def is_allocation_complete(self):
        """检查分配是否完成"""
        return self.allocation_complete

class MemoryTestApp:
    """内存测试应用程序 - 支持多种内存分配策略"""

    def __init__(self, memory_mb, auto_start=True, strategy="commit", commit_ratio=100, working_set_ratio=0):
        self.memory_mb = memory_mb
        self.allocator = MemoryAllocator()
        self.allocator.set_allocation_strategy(strategy, commit_ratio, working_set_ratio)
        self.allocation_thread = None
        self.auto_start = auto_start
        self.keep_running = True
        self.setup_ui()

        # 如果启用自动开始，立即开始内存占用
        if self.auto_start:
            self.auto_start_allocation()

    def setup_ui(self):
        """设置用户界面"""
        self.root = tk.Tk()
        self.root.title(f"内存测试工具 - 目标: {self.memory_mb} MB")
        self.root.geometry("600x500")
        self.root.resizable(True, True)

        # 主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill='both', expand=True)

        # 标题
        title_label = ttk.Label(main_frame, 
                               text="内存占用测试程序",
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=10)

        # 目标内存显示
        target_label = ttk.Label(main_frame,
                                text=f"目标内存: {self.memory_mb} MB",
                                font=('Arial', 12))
        target_label.pack(pady=5)

        # 分配策略显示
        strategy_text = ""
        if self.allocator.strategy == "commit":
            strategy_text = "分配策略: 全部占用提交大小 (100%)"
        elif self.allocator.strategy == "working_set":
            strategy_text = "分配策略: 全部占用专用工作集 (100%)"
        else:
            strategy_text = f"分配策略: 混合比例分配 (提交大小: {self.allocator.commit_ratio}%, 专用工作集: {self.allocator.working_set_ratio}%)"

        strategy_label = ttk.Label(main_frame,
                                  text=strategy_text,
                                  font=('Arial', 10),
                                  foreground='blue')
        strategy_label.pack(pady=5)

        # 自动开始状态显示
        auto_status = "✅ 自动开始内存占用" if self.auto_start else "⏸️ 等待手动开始"
        auto_label = ttk.Label(main_frame,
                              text=auto_status,
                              font=('Arial', 10, 'bold'),
                              foreground='green' if self.auto_start else 'blue')
        auto_label.pack(pady=5)

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, 
                                           orient='horizontal',
                                           length=500,
                                           mode='determinate',
                                           variable=self.progress_var)
        self.progress_bar.pack(pady=20)

        # 状态显示
        self.status_var = tk.StringVar(value="正在自动开始内存占用..." if self.auto_start else "等待开始内存占用...")
        status_label = ttk.Label(main_frame, 
                                textvariable=self.status_var,
                                font=('Arial', 10),
                                wraplength=500,
                                justify='center')
        status_label.pack(pady=10)

        # 内存信息显示
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(pady=10, fill='x')

        self.memory_info_var = tk.StringVar(value="提交内存: 0 MB, 专用工作集: 0 MB")
        memory_info_label = ttk.Label(info_frame,
                                     textvariable=self.memory_info_var,
                                     font=('Arial', 9))
        memory_info_label.pack()

        self.system_info_var = tk.StringVar(value="系统可用内存: 计算中...")
        system_info_label = ttk.Label(info_frame,
                                     textvariable=self.system_info_var,
                                     font=('Arial', 9))
        system_info_label.pack()

        # 控制按钮框架
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(pady=10)

        if not self.auto_start:
            self.start_btn = ttk.Button(control_frame, text="开始占用内存",
                                       command=self.manual_start_allocation)
            self.start_btn.pack(side='left', padx=5)

        self.stop_btn = ttk.Button(control_frame, text="停止占用并退出",
                                  command=self.stop_and_exit)
        self.stop_btn.pack(side='left', padx=5)

        # 提示信息
        tip_text = f"提示: 使用{self.allocator.strategy}内存分配策略" + ("，自动开始内存占用" if self.auto_start else "") + "，内存占用完成后进程持续运行"
        tip_label = ttk.Label(main_frame,
                             text=tip_text,
                             font=('Arial', 8),
                             foreground='blue',
                             justify='center')
        tip_label.pack(pady=5)

        # 启动内存信息更新
        self.update_memory_info()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def auto_start_allocation(self):
        """自动开始内存占用"""
        self.status_var.set("正在自动分配内存...")
        self.allocation_thread = threading.Thread(target=self._allocate_memory)
        self.allocation_thread.daemon = True
        self.allocation_thread.start()

    def manual_start_allocation(self):
        """手动开始内存占用"""
        self.auto_start_allocation()
        if hasattr(self, 'start_btn'):
            self.start_btn.config(state='disabled')

    def update_memory_info(self):
        """更新内存信息显示"""
        try:
            # 显示提交内存和专用工作集大小
            committed_memory = self.allocator.get_committed_memory()
            working_set_memory = self.allocator.get_working_set_memory()
            committed_mb = committed_memory // 1024 // 1024
            working_set_mb = working_set_memory // 1024 // 1024

            # 系统内存
            system_memory = psutil.virtual_memory()
            available_mb = system_memory.available // 1024 // 1024
            total_mb = system_memory.total // 1024 // 1024

            self.memory_info_var.set(f"提交内存: {committed_mb} MB, 专用工作集: {working_set_mb} MB")
            self.system_info_var.set(f"系统内存: {available_mb}/{total_mb} MB 可用")

            # 如果分配完成，显示保持运行状态
            if self.allocator.is_allocation_complete():
                if self.allocator.strategy == "commit":
                    self.status_var.set(f"✅ 内存占用完成: 提交 {committed_mb}MB/{self.memory_mb}MB\\n进程持续运行中，内存占用保持...")
                elif self.allocator.strategy == "working_set":
                    self.status_var.set(f"✅ 内存占用完成: 专用工作集 {working_set_mb}MB/{self.memory_mb}MB\\n进程持续运行中，内存占用保持...")
                else:
                    self.status_var.set(f"✅ 内存占用完成: 提交 {committed_mb}MB, 专用工作集 {working_set_mb}MB\\n进程持续运行中，内存占用保持...")

        except Exception as e:
            self.memory_info_var.set(f"内存信息获取失败: {e}")

        # 每秒更新一次
        if self.keep_running:
            self.root.after(1000, self.update_memory_info)

    def _allocate_memory(self):
        """在后台线程中分配内存"""
        allocated_bytes = self.allocator.allocate_memory_with_strategy(
            self.memory_mb,
            progress_callback=self.update_progress,
            status_callback=self.update_status
        )

        if allocated_bytes > 0:
            self.root.after(0, self._allocation_complete, allocated_bytes)
        else:
            self.root.after(0, self._allocation_failed)

    def _allocation_complete(self, allocated_bytes):
        """分配完成"""
        committed_mb = self.allocator.get_committed_memory() // 1024 // 1024
        working_set_mb = self.allocator.get_working_set_memory() // 1024 // 1024

        # 根据策略显示完成信息
        if self.allocator.strategy == "commit":
            status_text = f"分配完成! 实际提交: {committed_mb} MB\\n内存占用保持中，进程持续运行..."
        elif self.allocator.strategy == "working_set":
            status_text = f"分配完成! 实际专用工作集: {working_set_mb} MB\\n内存占用保持中，进程持续运行..."
        else:
            status_text = f"分配完成! 实际提交: {committed_mb} MB, 专用工作集: {working_set_mb} MB\\n内存占用保持中，进程持续运行..."

        self.status_var.set(status_text)
        self.progress_var.set(100)

    def _allocation_failed(self):
        """分配失败"""
        self.status_var.set("分配失败! 进程持续运行中...")

    def update_progress(self, progress):
        """更新进度条"""
        self.root.after(0, lambda: self.progress_var.set(progress))

    def update_status(self, status):
        """更新状态"""
        self.root.after(0, lambda: self.status_var.set(status))

    def stop_and_exit(self):
        """停止内存占用并退出程序"""
        self.keep_running = False
        if self.allocator:
            self.allocator.stop()
            time.sleep(0.5)
            self.allocator.free_memory()
        self.root.destroy()

    def on_close(self):
        """窗口关闭事件"""
        self.stop_and_exit()

    def run(self):
        """运行界面"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.stop_and_exit()

def parse_arguments():
    """使用argparse解析命令行参数"""
    parser = argparse.ArgumentParser(description='GUI内存测试工具')
    parser.add_argument('memory_mb', type=int, help='内存大小(MB)')
    parser.add_argument('--auto-start', action='store_true', help='自动开始内存占用')
    parser.add_argument('--strategy', type=str, default='commit', 
                       choices=['commit', 'working_set', 'mixed'],
                       help='内存分配策略: commit|working_set|mixed')
    parser.add_argument('--commit-ratio', type=int, default=100, help='提交大小比例(0-100)')
    parser.add_argument('--working-set-ratio', type=int, default=0, help='专用工作集比例(0-100)')

    try:
        args = parser.parse_args()
        return args
    except SystemExit:
        return None

def main():
    args = parse_arguments()
    if args is None:
        time.sleep(2)
        return

    memory_mb = args.memory_mb
    auto_start = args.auto_start
    strategy = args.strategy
    commit_ratio = args.commit_ratio
    working_set_ratio = args.working_set_ratio

    # 验证参数
    if memory_mb <= 0:
        messagebox.showerror("错误", "内存大小必须大于0")
        return

    if memory_mb > 100000:
        messagebox.showerror("错误", "内存大小不能超过100000 MB (100GB)")
        return

    # 验证比例
    if strategy == "mixed" and (commit_ratio + working_set_ratio != 100):
        messagebox.showerror("错误", "提交大小和专用工作集的比例之和必须等于100%")
        return

    # 检查系统内存
    try:
        system_memory = psutil.virtual_memory()
        available_mb = system_memory.available // 1024 // 1024

        if memory_mb > available_mb:
            if not auto_start:
                result = messagebox.askyesno(
                    "内存不足警告",
                    f"请求内存 {memory_mb} MB 超过系统可用内存 {available_mb} MB。\\n可能影响系统稳定性。\\n是否继续？"
                )
                if not result:
                    return
            else:
                print(f"警告: 请求内存 {memory_mb} MB 超过系统可用内存 {available_mb} MB")
    except:
        pass

    app = MemoryTestApp(memory_mb, auto_start=auto_start, strategy=strategy, 
                       commit_ratio=commit_ratio, working_set_ratio=working_set_ratio)
    app.run()

if __name__ == "__main__":
    main()
'''

        try:
            # 写入临时文件并编译
            temp_script = "gui_memory_temp.py"
            with open(temp_script, 'w', encoding='utf-8') as f:
                f.write(gui_code)

            # 编译
            cmd = [
                'pyinstaller',
                '--onefile',
                '--windowed',
                '--name=GUIMemoryTestTool',
                '--clean',
                '--noconfirm',
                '--hidden-import=argparse',
                '--hidden-import=psutil',
                temp_script
            ]

            print(f"编译GUI内存测试工具: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            # 清理临时文件
            if os.path.exists(temp_script):
                os.remove(temp_script)

            if result.returncode == 0:
                # 复制到当前目录
                if os.path.exists('dist/GUIMemoryTestTool.exe'):
                    shutil.copy2('dist/GUIMemoryTestTool.exe', 'GUIMemoryTestTool.exe')
                    print("✅ GUI内存测试工具编译成功")
                    return True
                else:
                    print("❌ 编译成功但未找到生成的可执行文件")
                    return False
            else:
                print(f"编译错误: {result.stderr}")
                return False

        except Exception as e:
            print(f"编译GUI工具时出错: {e}")
            return False

    def compile_main_program(self):
        """编译主程序"""
        print("\n正在编译主程序...")

        # 创建spec文件
        spec_content = self._create_spec_content()
        with open('FileOperationTool.spec', 'w', encoding='utf-8') as f:
            f.write(spec_content)

        # 编译主程序
        try:
            cmd = ['pyinstaller', '--clean', '--noconfirm', 'FileOperationTool.spec']
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print("✅ 主程序编译成功!")

                # 验证生成的可执行文件
                exe_path = 'dist/FileOperationTool.exe'
                if os.path.exists(exe_path):
                    file_size = os.path.getsize(exe_path)
                    print(f"生成的可执行文件: {exe_path} ({file_size} 字节)")

                    # 复制内存测试工具到dist目录
                    self._copy_tools_to_dist()

                    return True
                else:
                    print("❌ 生成的可执行文件不存在!")
                    return False
            else:
                print(f"❌ 主程序编译失败: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ 编译主程序时出错: {e}")
            return False

    def _create_spec_content(self):
        """创建spec文件内容 - 使用正确的图标路径"""
        icon_path = os.path.abspath('FileTestTool_icon.ico')

        # 确保图标文件存在
        if not os.path.exists(icon_path):
            print(f"❌ 图标文件不存在: {icon_path}")
            # 尝试查找图标文件
            icon_path = self._find_icon_file()
            if not icon_path:
                print("❌ 无法找到图标文件，编译将继续但不设置图标")
                icon_path = ""

        return f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

hidden_imports = [
    'psutil',
    'pywin32',
    'win32api',
    'win32security',
    'win32con',
    'win32file',
    'win32process',
    'tkinter',
    'tkinter.ttk',
    'argparse'
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FileOperationTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r'{icon_path}',
)
'''

    def _find_icon_file(self):
        """查找图标文件"""
        search_paths = [
            'FileTestTool_icon.ico',
            './FileTestTool_icon.ico',
            '../FileTestTool_icon.ico',
            '../../FileTestTool_icon.ico'
        ]

        for path in search_paths:
            if os.path.exists(path):
                return os.path.abspath(path)
        return None

    def _copy_tools_to_dist(self):
        """复制工具到dist目录"""
        tools = ['GUIMemoryTestTool.exe']

        for tool in tools:
            if os.path.exists(tool):
                shutil.copy2(tool, f'dist/{tool}')
                print(f"✅ 已复制 {tool} 到 dist 目录")
            else:
                print(f"⚠️ 未找到 {tool}")

    def create_build_script(self):
        """创建构建脚本"""
        build_script = '''@echo off
chcp 65001 >nul
echo ========================================
echo    FileOperationTool 构建工具
echo ========================================
echo.

python setup.py build

echo.
echo 构建完成!
echo 可执行文件位于 dist 目录
pause
'''

        with open('build.bat', 'w', encoding='utf-8') as f:
            f.write(build_script)

        print("✅ 已创建构建脚本: build.bat")

    def cleanup(self):
        """清理临时文件"""
        temp_files = [
            'build',
            'GUIMemoryTestTool.exe'
        ]

        for item in temp_files:
            if os.path.exists(item):
                if os.path.isdir(item):
                    shutil.rmtree(item)
                else:
                    os.remove(item)

        print("✅ 清理完成")

    def run(self):
        """运行编译流程"""
        if not self.check_environment():
            return

        if not self.install_dependencies():
            return

        if not self.compile_memory_test_tools():
            return

        if not self.compile_main_program():
            return

        self.create_build_script()

        print("\n" + "=" * 60)
        print("✅ 编译完成!")
        print("=" * 60)
        print(f"主程序: dist/FileOperationTool.exe")
        print(f"GUI内存测试工具: dist/GUIMemoryTestTool.exe")
        print("\n注意: 如果图标显示不正确，请确保 FileTestTool_icon.ico 文件位于程序目录下")


def main():
    """主函数"""
    compiler = Compiler()
    compiler.run()


if __name__ == "__main__":
    main()