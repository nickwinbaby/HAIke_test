"""
进程管理功能实现 - 多进程内存分配方案，支持多种内存分配策略
"""

import os
import sys
import tempfile
import subprocess
import time
import threading
import psutil
import ctypes
from ctypes import wintypes
import math


class ProcessManager:
    """进程管理器 - 多进程内存分配方案，支持多种内存分配策略"""

    def __init__(self):
        self.created_processes = {}
        self.process_lock = threading.Lock()

    def create_multi_memory_processes(self, total_memory_mb, strategy="commit", commit_ratio=100, working_set_ratio=0):
        """创建多进程内存测试程序 - 使用多进程分配方案，支持多种内存分配策略

        Args:
            total_memory_mb: 总内存占用大小(MB)
            strategy: 内存分配策略 - "commit"|"mixed"
            commit_ratio: 提交大小占用比例(0-100)
            working_set_ratio: 专用工作集占用比例(0-100)
        """
        try:
            # 首先检查是否已有GUI内存测试程序在运行，如果有则先终止
            self._kill_all_memory_test_tools()

            # 查找 GUI MemoryTestTool.exe
            memory_tool_path = self._find_gui_memory_test_tool()
            if not memory_tool_path:
                # 如果找不到GUI版本，尝试编译
                print("未找到GUI内存测试工具，尝试编译...")
                if self._compile_gui_memory_test_tool():
                    memory_tool_path = self._find_gui_memory_test_tool()
                    if memory_tool_path:
                        print(f"成功编译并找到GUI内存测试工具: {memory_tool_path}")
                    else:
                        print("编译成功但未找到生成的可执行文件")
                else:
                    print("GUI内存测试工具编译失败")
                    return "❌ GUI内存测试工具编译失败，请检查编译环境"

            if not memory_tool_path:
                raise Exception("未找到带界面的内存测试工具 GUIMemoryTestTool.exe")

            print(f"使用带界面内存测试工具: {memory_tool_path}")
            print(f"目标总内存: {total_memory_mb} MB")
            print(f"分配策略: {strategy}")
            if strategy == "mixed":
                print(f"提交大小比例: {commit_ratio}%, 专用工作集比例: {working_set_ratio}%")

            # 验证内存测试工具
            if not self._validate_memory_tool(memory_tool_path):
                raise Exception("内存测试工具验证失败")

            # 计算需要启动的进程数量和每个进程的内存大小
            process_count, memory_per_process = self._calculate_process_distribution(total_memory_mb)

            print(f"启动 {process_count} 个进程，每个进程分配 {memory_per_process} MB")

            processes_info = []
            start_time = time.time()

            # 启动多个进程
            for i in range(process_count):
                process_id = f"gui_memory_process_{int(time.time())}_{i}"

                try:
                    # 构建命令行参数
                    cmd_args = [
                        memory_tool_path,
                        str(memory_per_process[i]),
                        "--auto-start",
                        f"--strategy={strategy}"
                    ]

                    # 根据策略添加相应参数
                    if strategy == "mixed":
                        cmd_args.append(f"--commit-ratio={commit_ratio}")
                        cmd_args.append(f"--working-set-ratio={working_set_ratio}")

                    print(f"启动进程 {i+1} 命令: {' '.join(cmd_args)}")

                    # 启动带界面的内存测试程序
                    process = subprocess.Popen(
                        cmd_args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                        text=True,
                        encoding='utf-8',
                        bufsize=1
                    )

                    # 获取进程信息
                    pid = process.pid

                    # 等待进程启动
                    time.sleep(2)

                    # 验证进程状态
                    if process.poll() is not None:
                        stdout, stderr = self._get_process_output(process)
                        error_msg = stderr if stderr else stdout if stdout else "进程启动后立即退出"
                        print(f"进程 {i + 1} 启动失败: {error_msg}")
                        continue

                    if not self._is_process_running(pid):
                        print(f"进程 {i + 1} 启动后进程不存在")
                        continue

                    # 记录进程信息
                    with self.process_lock:
                        self.created_processes[process_id] = {
                            'process': process,
                            'memory_mb': memory_per_process[i],
                            'start_time': start_time,
                            'pid': pid,
                            'type': 'gui_memory_test',
                            'tool_path': memory_tool_path,
                            'last_check': time.time(),
                            'is_running': True,
                            'auto_started': True,
                            'strategy': strategy,
                            'commit_ratio': commit_ratio,
                            'working_set_ratio': working_set_ratio
                        }

                    processes_info.append({
                        'pid': pid,
                        'start_time': start_time
                    })

                    # 启动监控线程
                    self._start_output_monitor(process, process_id)

                    print(f"✅ 进程 {i + 1} 已启动并自动开始内存占用 (PID: {pid}, 内存: {memory_per_process[i]} MB)")

                except Exception as e:
                    print(f"进程 {i + 1} 创建失败: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue

            if not processes_info:
                raise Exception("所有进程启动都失败了")

            # 等待一段时间让内存占用稳定
            time.sleep(3)

            # 生成状态报告
            success_count = len(processes_info)

            # 根据策略生成结果报告
            if strategy == "commit":
                strategy_text = "主要占用提交大小"
            else:
                strategy_text = f"混合比例分配 (提交大小: {commit_ratio}%, 专用工作集: {working_set_ratio}%)"

            result = (f"✅ 多进程内存占用已启动并自动开始\n"
                      f"分配策略: {strategy_text}\n"
                      f"成功启动: {success_count}/{process_count} 个进程\n"
                      f"目标分配内存: {total_memory_mb} MB\n\n"
                      f"进程信息:\n")

            for i, info in enumerate(processes_info):
                running_time = time.time() - info['start_time']
                result += f"进程 {i + 1}: PID {info['pid']}, 运行时长: {running_time:.1f}秒\n"

            result += f"\n注意: 这些程序已创建为独立进程，已自动开始内存占用，需要手动关闭或使用结束按钮"

            return result

        except Exception as e:
            # 清理资源
            self._kill_all_memory_test_tools()
            raise Exception(f"创建多进程内存测试程序失败: {str(e)}")

    def _calculate_process_distribution(self, total_memory_mb):
        """计算进程分配方案"""
        MAX_MEMORY_PER_PROCESS = 1700  # 每个进程最大1700MB

        if total_memory_mb <= MAX_MEMORY_PER_PROCESS:
            # 如果内存需求小于等于1700MB，只启动一个进程
            return 1, [total_memory_mb]

        # 计算需要的进程数量
        process_count = math.ceil(total_memory_mb / MAX_MEMORY_PER_PROCESS)

        # 计算每个进程的内存分配（尽量平均分配）
        base_memory = total_memory_mb // process_count
        remainder = total_memory_mb % process_count

        memory_per_process = [base_memory] * process_count

        # 将余数分配到前几个进程
        for i in range(remainder):
            memory_per_process[i] += 1

        return process_count, memory_per_process

    def _compile_gui_memory_test_tool(self):
        """编译GUI内存测试工具 - 支持多种内存分配策略"""
        try:
            # 创建GUI内存测试工具的Python代码 - 支持策略参数
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
        """根据策略分配内存 - 完全重写工作集策略"""
        # 根据策略计算目标内存大小
        if self.strategy == "commit":
            # 主要占用提交大小
            target_commit_bytes = size_mb * 1024 * 1024
            target_working_set_bytes = 0
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

            # 分配内存
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
                        status_callback(f"内存分配失败在 {self.total_committed//1024//1024}MB")
                    break

                # 转换为可写入的指针
                memory_ptr = ctypes.cast(memory_block, ctypes.POINTER(ctypes.c_byte))

                # 对于mixed策略，按比例访问内存
                if self.strategy == "mixed" and target_working_set_bytes > 0:
                    # 混合策略：按比例访问内存
                    remaining_working_set = target_working_set_bytes - self.total_working_set
                    bytes_to_touch = min(current_chunk_bytes, remaining_working_set)
                    if bytes_to_touch > 0:
                        try:
                            page_size = 4096
                            for j in range(0, bytes_to_touch, page_size):
                                if j < current_chunk_bytes:
                                    memory_ptr[j] = random.randint(0, 255)
                            self.total_working_set += bytes_to_touch
                        except Exception as e:
                            if status_callback:
                                status_callback(f"写入内存时出错: {e}")
                else:
                    # commit策略不需要写入
                    pass

                self.allocated_blocks.append((memory_block, current_chunk_bytes))
                self.total_committed += current_chunk_bytes

                # 计算总体进度
                total_target = max(target_commit_bytes, target_working_set_bytes)
                if total_target > 0:
                    if self.strategy == "commit":
                        progress = (self.total_committed / total_target) * 100
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
                    else:
                        status_callback(f"已分配: 提交 {current_commit_mb}MB/{target_commit_bytes//1024//1024}MB, 工作集 {current_working_set_mb}MB/{target_working_set_bytes//1024//1024}MB")

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
                else:
                    commit_success = self.total_committed >= target_commit_bytes * 0.95 if target_commit_bytes > 0 else True
                    working_set_success = self.total_working_set >= target_working_set_bytes * 0.95 if target_working_set_bytes > 0 else True
                    if commit_success and working_set_success:
                        status_callback(f"✅ 分配成功: 提交 {final_commit_mb}MB, 工作集 {final_working_set_mb}MB\\n内存占用保持中，进程持续运行...")
                    else:
                        status_callback(f"⚠️ 分配部分完成: 提交 {final_commit_mb}MB, 工作集 {final_working_set_mb}MB\\n内存占用保持中，进程持续运行...")

            return self.total_committed

        except Exception as e:
            if status_callback:
                status_callback(f"分配过程中出错: {e}")
            return self.total_committed

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
            strategy_text = "分配策略: 主要占用提交大小"
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
                       choices=['commit', 'mixed'],
                       help='内存分配策略: commit|mixed')
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

            # 写入临时文件并编译
            temp_script = "gui_memory_temp.py"
            with open(temp_script, 'w', encoding='utf-8') as f:
                f.write(gui_code)

            # 使用PyInstaller编译
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

            print(f"编译命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            # 清理临时文件
            if os.path.exists(temp_script):
                os.remove(temp_script)

            if result.returncode == 0:
                print("GUI内存测试工具编译成功")
                return True
            else:
                print(f"编译失败: {result.stderr}")
                return False

        except Exception as e:
            print(f"编译GUI内存测试工具时出错: {e}")
            return False

    def _find_gui_memory_test_tool(self):
        """查找GUI内存测试工具"""
        search_paths = [
            'GUIMemoryTestTool.exe',
            './GUIMemoryTestTool.exe',
            'dist/GUIMemoryTestTool.exe',
            './dist/GUIMemoryTestTool.exe',
        ]

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
            search_paths.extend([
                os.path.join(base_path, 'GUIMemoryTestTool.exe'),
                os.path.join(base_path, 'dist', 'GUIMemoryTestTool.exe'),
            ])

        current_dir = os.path.dirname(os.path.abspath(__file__))
        search_paths.extend([
            os.path.join(current_dir, 'GUIMemoryTestTool.exe'),
            os.path.join(current_dir, 'dist', 'GUIMemoryTestTool.exe'),
        ])

        # 添加项目根目录搜索
        project_root = os.path.dirname(current_dir) if 'core' in current_dir else current_dir
        search_paths.extend([
            os.path.join(project_root, 'GUIMemoryTestTool.exe'),
            os.path.join(project_root, 'dist', 'GUIMemoryTestTool.exe'),
        ])

        for path in search_paths:
            if os.path.exists(path):
                print(f"找到GUI内存测试工具: {os.path.abspath(path)}")
                return os.path.abspath(path)

        print("未找到GUI内存测试工具，搜索路径:")
        for path in search_paths:
            print(f"  {path}")
        return None

    def _validate_memory_tool(self, tool_path):
        """验证内存测试工具"""
        try:
            if os.path.exists(tool_path) and os.path.getsize(tool_path) > 1024:
                print(f"内存测试工具验证成功: {tool_path} ({os.path.getsize(tool_path)} 字节)")
                return True
            else:
                print(f"内存测试工具验证失败: {tool_path}")
                return False
        except Exception as e:
            print(f"验证内存测试工具时出错: {e}")
            return False

    def _kill_all_memory_test_tools(self):
        """终止所有内存测试进程"""
        try:
            killed_count = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and 'MemoryTestTool' in proc.info['name']:
                        print(f"终止内存测试进程: {proc.info['pid']} ({proc.info['name']})")
                        proc.terminate()
                        killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 等待进程终止
            time.sleep(2)

            # 强制终止仍未退出的进程
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and 'MemoryTestTool' in proc.info['name']:
                        print(f"强制终止内存测试进程: {proc.info['pid']} ({proc.info['name']})")
                        proc.kill()
                        killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            print(f"共终止 {killed_count} 个内存测试进程")

        except Exception as e:
            print(f"终止进程时出错: {e}")

    def _get_process_output(self, process, timeout=2):
        """获取进程输出"""
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return stdout, stderr
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                stdout, stderr = process.communicate(timeout=1)
                return stdout, stderr
            except:
                return "", "超时"
        except Exception as e:
            return "", str(e)

    def _is_process_running(self, pid):
        """检查进程是否运行"""
        try:
            return psutil.pid_exists(pid)
        except:
            return False

    def _start_output_monitor(self, process, process_id):
        """启动输出监控"""
        def monitor():
            try:
                while process.poll() is None:
                    try:
                        line = process.stdout.readline()
                        if line:
                            print(f"[内存测试进程 {process_id}]: {line.strip()}")
                        else:
                            time.sleep(0.1)
                    except:
                        break

                # 进程结束，清理
                with self.process_lock:
                    if process_id in self.created_processes:
                        self.created_processes[process_id]['is_running'] = False

            except Exception as e:
                print(f"监控进程输出失败: {e}")

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def kill_memory_process(self):
        """终止所有内存测试进程"""
        self._kill_all_memory_test_tools()

        with self.process_lock:
            self.created_processes.clear()

        return "✅ 已终止所有内存测试进程"

    def get_running_processes(self):
        """获取运行中的进程信息 - 修改：只返回PID和运行时长"""
        processes_info = []
        current_time = time.time()

        with self.process_lock:
            # 清理已结束的进程
            to_remove = []
            for pid, info in self.created_processes.items():
                if not self._is_process_running(info['pid']):
                    to_remove.append(pid)

            for pid in to_remove:
                del self.created_processes[pid]

            # 收集运行中进程信息 - 只保留PID和运行时长
            for pid, info in self.created_processes.items():
                if info.get('type') != 'gui_memory_test':
                    continue

                running_time = current_time - info['start_time']

                processes_info.append({
                    'pid': info['pid'],
                    'running_time': running_time
                })

        return processes_info

    # 兼容旧版本的方法
    def create_memory_process(self, memory_mb):
        """创建独立的内存占用测试程序 - 兼容旧版本"""
        try:
            return self.create_gui_memory_process(memory_mb)
        except Exception as e:
            raise Exception(f"创建内存测试程序失败: {str(e)}")

    def create_gui_memory_process(self, memory_mb):
        """创建带界面的内存测试程序"""
        return self.create_multi_memory_processes(memory_mb)