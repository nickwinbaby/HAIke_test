"""
DLL注入功能实现 - 兼容多Windows版本
"""

import os
import sys
import ctypes
from ctypes import wintypes, c_void_p, c_wchar_p, Structure, POINTER, sizeof

# 尝试导入 psutil，如果失败则提供替代方案
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("警告: psutil 模块未安装，进程列表功能将受限")

# 尝试导入win32模块
try:
    import win32process
    import win32security
    import win32con
    import win32api
    import win32file

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("警告: pywin32 模块未安装，进程完整性检查功能受限")


class DLLInjector:
    """DLL注入器 - 兼容多Windows版本"""

    def __init__(self):
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
        self.ntdll = ctypes.WinDLL('ntdll', use_last_error=True)
        self.setup_functions()

    def setup_functions(self):
        """设置Windows API函数 - 兼容多版本"""
        # OpenProcess
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE

        # VirtualAllocEx
        self.kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, c_void_p, ctypes.c_size_t, wintypes.DWORD,
                                                 wintypes.DWORD]
        self.kernel32.VirtualAllocEx.restype = c_void_p

        # WriteProcessMemory
        self.kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, c_void_p, c_void_p, ctypes.c_size_t,
                                                     ctypes.POINTER(ctypes.c_size_t)]
        self.kernel32.WriteProcessMemory.restype = wintypes.BOOL

        # GetProcAddress
        self.kernel32.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
        self.kernel32.GetProcAddress.restype = c_void_p

        # GetModuleHandle
        self.kernel32.GetModuleHandleW.argtypes = [c_wchar_p]
        self.kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        # CreateRemoteThread
        self.kernel32.CreateRemoteThread.argtypes = [wintypes.HANDLE, c_void_p, ctypes.c_size_t, c_void_p, c_void_p,
                                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.CreateRemoteThread.restype = wintypes.HANDLE

        # WaitForSingleObject
        self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD

        # CloseHandle
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        # VirtualFreeEx
        self.kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, c_void_p, ctypes.c_size_t, wintypes.DWORD]
        self.kernel32.VirtualFreeEx.restype = wintypes.BOOL

        # GetExitCodeThread
        self.kernel32.GetExitCodeThread.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.GetExitCodeThread.restype = wintypes.BOOL

        # LoadLibraryA
        self.kernel32.LoadLibraryA.argtypes = [ctypes.c_char_p]
        self.kernel32.LoadLibraryA.restype = wintypes.HMODULE

        # GetCurrentProcess
        self.kernel32.GetCurrentProcess.restype = wintypes.HANDLE

        # GetLastError
        self.kernel32.GetLastError.restype = wintypes.DWORD

        # 设置错误处理
        ctypes.set_last_error(0)

    def check_process_integrity(self, pid):
        """检查进程完整性级别 - 简化版本，兼容所有Windows版本"""
        try:
            # 使用psutil检查进程权限
            if PSUTIL_AVAILABLE:
                try:
                    process = psutil.Process(pid)
                    username = process.username()

                    # 简单的基于用户名的完整性级别判断
                    if username and 'SYSTEM' in username.upper():
                        return "系统"
                    elif username and ('ADMIN' in username.upper() or username.endswith('$')):
                        return "高"
                    else:
                        return "中"
                except:
                    pass

            # 如果psutil方法失败，使用文件权限检查
            try:
                if WIN32_AVAILABLE:
                    # 尝试打开进程获取基本信息
                    PROCESS_QUERY_INFORMATION = 0x0400
                    process_handle = win32api.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                    if process_handle:
                        win32api.CloseHandle(process_handle)
                        return "中/高"  # 如果能打开，至少是中等权限
            except:
                pass

            # 最后回退方法：检查进程是否可访问
            if self.is_process_accessible(pid):
                return "中/高"
            else:
                return "未知"

        except Exception as e:
            return f"未知"

    def is_signed_process_protected(self, pid):
        """检查进程是否可能受数字签名保护 - 简化版本"""
        integrity_level = self.check_process_integrity(pid)

        # 高完整性级别通常表示受保护进程
        protected_levels = ["系统", "高", "中/高"]
        return integrity_level in protected_levels

    def get_process_list(self, hide_system_processes=True):
        """获取进程列表 - 兼容所有Windows版本"""
        if not PSUTIL_AVAILABLE:
            # 如果 psutil 不可用，返回空列表
            print("警告: psutil 未安装，无法获取进程列表")
            return []

        processes = []
        system_usernames = ['SYSTEM', 'LOCAL SERVICE', 'NETWORK SERVICE']

        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                # 如果隐藏系统进程且当前进程是系统进程，则跳过
                if hide_system_processes and proc.info['username'] and any(
                        sys_user in proc.info['username'] for sys_user in system_usernames):
                    continue

                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'username': proc.info['username'] or 'N/A'
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return sorted(processes, key=lambda x: x['name'].lower())

    def inject_dll_normal(self, pid, dll_path):
        """DLL注入方法 - 兼容所有Windows版本"""
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"DLL文件不存在: {dll_path}")

        # 确保DLL路径是绝对路径
        dll_path = os.path.abspath(dll_path)

        # 检查DLL架构是否匹配
        if not self._check_architecture_match(pid, dll_path):
            raise Exception("DLL架构与目标进程架构不匹配（32位/64位）")

        # 使用标准注入方法
        return self.standard_injection(pid, dll_path)

    def _check_architecture_match(self, pid, dll_path):
        """检查DLL架构是否与目标进程匹配"""
        try:
            # 获取目标进程架构
            process_arch = self._get_process_architecture(pid)
            dll_arch = self._get_dll_architecture(dll_path)

            if process_arch and dll_arch and process_arch != dll_arch:
                print(f"警告: 架构不匹配 - 进程: {process_arch}, DLL: {dll_arch}")
                return False

            return True
        except Exception as e:
            print(f"架构检查失败: {e}")
            return True  # 如果检查失败，继续尝试注入

    def _get_process_architecture(self, pid):
        """获取进程架构（32位或64位）"""
        try:
            if PSUTIL_AVAILABLE:
                # 在Windows XP上使用更兼容的方法
                import platform
                if platform.machine().endswith('64'):
                    # 在64位系统上，检查是否是32位进程
                    try:
                        is_wow64 = ctypes.c_int(0)
                        process_handle = self.kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
                        if process_handle:
                            # 检查IsWow64Process是否可用（Windows XP 64位及以上）
                            if hasattr(self.kernel32, 'IsWow64Process'):
                                self.kernel32.IsWow64Process(process_handle, ctypes.byref(is_wow64))
                                self.kernel32.CloseHandle(process_handle)
                                return "32位" if is_wow64.value else "64位"
                            else:
                                # Windows XP 32位系统
                                self.kernel32.CloseHandle(process_handle)
                                return "32位"
                    except:
                        pass
            return None
        except:
            return None

    def _get_dll_architecture(self, dll_path):
        """获取DLL架构（32位或64位）"""
        try:
            # 简单的PE头检查
            with open(dll_path, 'rb') as f:
                # 读取DOS头
                dos_header = f.read(64)
                if dos_header[0:2] != b'MZ':
                    return None

                # 读取PE头偏移
                pe_offset = int.from_bytes(dos_header[60:64], byteorder='little')
                f.seek(pe_offset)

                # 读取PE签名
                pe_signature = f.read(4)
                if pe_signature != b'PE\x00\x00':
                    return None

                # 读取机器类型
                machine_type = int.from_bytes(f.read(2), byteorder='little')

                # 0x014c = IMAGE_FILE_MACHINE_I386 (32位)
                # 0x8664 = IMAGE_FILE_MACHINE_AMD64 (64位)
                if machine_type == 0x014c:
                    return "32位"
                elif machine_type == 0x8664:
                    return "64位"
                else:
                    return None
        except:
            return None

    def standard_injection(self, pid, dll_path):
        """标准DLL注入方法 - 兼容所有Windows版本"""
        # 打开目标进程
        # 使用更兼容的进程访问权限
        PROCESS_CREATE_THREAD = 0x0002
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_OPERATION = 0x0008
        PROCESS_VM_WRITE = 0x0020
        PROCESS_VM_READ = 0x0010

        process_access = (PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
                          PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ)

        process_handle = self.kernel32.OpenProcess(process_access, False, pid)
        if not process_handle:
            error_code = ctypes.get_last_error()
            raise Exception(f"无法打开进程 (PID: {pid})，错误代码: {error_code}")

        try:
            # 将DLL路径转换为宽字符串（UTF-16）
            dll_path_wide = dll_path
            if not isinstance(dll_path_wide, str):
                dll_path_wide = str(dll_path_wide)

            # 计算需要的缓冲区大小（字符数，包括null终止符）
            buffer_size = (len(dll_path_wide) + 1) * 2  # UTF-16每个字符2字节

            # 在目标进程中分配内存
            MEM_COMMIT = 0x00001000
            MEM_RESERVE = 0x00002000
            PAGE_READWRITE = 0x04

            remote_memory = self.kernel32.VirtualAllocEx(
                process_handle,
                None,
                buffer_size,
                MEM_COMMIT | MEM_RESERVE,
                PAGE_READWRITE
            )

            if not remote_memory:
                error_code = ctypes.get_last_error()
                raise Exception(f"无法在目标进程中分配内存，错误代码: {error_code}")

            # 将DLL路径写入目标进程
            bytes_written = ctypes.c_size_t(0)

            # 使用ctypes直接创建UTF-16字符串
            dll_path_encoded = ctypes.create_unicode_buffer(dll_path_wide)

            write_result = self.kernel32.WriteProcessMemory(
                process_handle,
                remote_memory,
                dll_path_encoded,
                buffer_size,
                ctypes.byref(bytes_written)
            )

            if not write_result:
                self.kernel32.VirtualFreeEx(process_handle, remote_memory, 0, 0x8000)  # MEM_RELEASE
                error_code = ctypes.get_last_error()
                raise Exception(f"无法写入DLL路径到目标进程，错误代码: {error_code}")

            # 获取LoadLibraryW函数地址
            kernel32_handle = self.kernel32.GetModuleHandleW("kernel32.dll")
            if not kernel32_handle:
                error_code = ctypes.get_last_error()
                raise Exception(f"无法获取kernel32.dll模块句柄，错误代码: {error_code}")

            # 使用正确的字符类型获取函数地址
            load_library_addr = self.kernel32.GetProcAddress(kernel32_handle, b"LoadLibraryW")
            if not load_library_addr:
                error_code = ctypes.get_last_error()
                raise Exception(f"无法获取LoadLibraryW函数地址，错误代码: {error_code}")

            # 创建远程线程执行LoadLibraryW
            thread_handle = self.kernel32.CreateRemoteThread(
                process_handle,
                None,  # lpThreadAttributes
                0,  # dwStackSize
                load_library_addr,
                remote_memory,
                0,  # dwCreationFlags
                None  # lpThreadId
            )

            if not thread_handle:
                self.kernel32.VirtualFreeEx(process_handle, remote_memory, 0, 0x8000)  # MEM_RELEASE
                error_code = ctypes.get_last_error()
                raise Exception(f"无法创建远程线程，错误代码: {error_code}")

            # 等待线程执行完成
            WAIT_OBJECT_0 = 0x00000000
            wait_result = self.kernel32.WaitForSingleObject(thread_handle, 10000)  # 10秒超时

            if wait_result != WAIT_OBJECT_0:
                print(f"警告: 远程线程可能未正常完成 (等待结果: {wait_result})")

            # 获取线程退出代码
            exit_code = wintypes.DWORD()
            if self.kernel32.GetExitCodeThread(thread_handle, ctypes.byref(exit_code)):
                if exit_code.value == 0:
                    # 线程返回0，表示LoadLibrary失败
                    error_msg = "远程线程执行失败，LoadLibrary返回NULL。"
                    error_msg += self._get_loadlibrary_error_details(pid, dll_path)
                    raise Exception(error_msg)
                else:
                    print(f"远程线程执行成功，返回代码: {exit_code.value}")

                    # 验证DLL是否真的加载成功
                    if not self.verify_dll_loaded(pid, dll_path):
                        raise Exception("DLL注入看似成功，但未在目标进程中检测到加载的DLL模块")

            # 清理资源
            self.kernel32.CloseHandle(thread_handle)
            self.kernel32.VirtualFreeEx(process_handle, remote_memory, 0, 0x8000)  # MEM_RELEASE

            return f"✅ DLL注入成功! PID: {pid}, DLL: {os.path.basename(dll_path)}"

        except Exception as e:
            # 确保在异常时清理资源
            if 'remote_memory' in locals() and remote_memory:
                self.kernel32.VirtualFreeEx(process_handle, remote_memory, 0, 0x8000)
            raise e
        finally:
            self.kernel32.CloseHandle(process_handle)

    def _get_loadlibrary_error_details(self, pid, dll_path):
        """获取LoadLibrary失败的详细错误信息"""
        error_details = "\n\n可能的原因："

        # 1. 检查DLL文件是否存在且可访问
        if not os.path.exists(dll_path):
            error_details += "\n• DLL文件不存在"
        else:
            try:
                with open(dll_path, 'rb'):
                    pass
            except PermissionError:
                error_details += "\n• 无法访问DLL文件（权限不足）"
            except Exception as e:
                error_details += f"\n• 无法访问DLL文件: {e}"

        # 2. 检查DLL依赖
        error_details += "\n• DLL可能缺少依赖项或依赖项版本不匹配"

        # 3. 检查架构匹配
        if not self._check_architecture_match(pid, dll_path):
            error_details += "\n• DLL架构与目标进程不匹配（32位/64位问题）"

        # 4. 通用建议
        error_details += "\n• 尝试以管理员权限运行程序"
        error_details += "\n• 检查目标进程是否受保护（如杀毒软件、系统进程）"
        error_details += "\n• 确保DLL文件是有效的Windows DLL"

        return error_details

    def verify_dll_loaded(self, pid, dll_path):
        """验证DLL是否在目标进程中成功加载"""
        if not PSUTIL_AVAILABLE:
            print("警告: 无法验证DLL加载状态，psutil模块未安装")
            return True  # 如果无法验证，假设成功

        try:
            process = psutil.Process(pid)
            dll_name = os.path.basename(dll_path).lower()

            # 检查进程加载的所有DLL
            for dll in process.memory_maps():
                if dll_name in dll.path.lower():
                    print(f"验证成功: 在目标进程中找到DLL: {dll.path}")
                    return True

            print(f"警告: 在目标进程中未找到DLL: {dll_name}")
            return False

        except Exception as e:
            print(f"验证DLL加载状态时出错: {e}")
            return True  # 如果验证过程出错，假设成功

    def is_process_accessible(self, pid):
        """检查进程是否可访问"""
        try:
            PROCESS_QUERY_INFORMATION = 0x0400
            process_handle = self.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            if process_handle:
                self.kernel32.CloseHandle(process_handle)
                return True
            return False
        except:
            return False

    def get_process_info(self, pid):
        """获取进程详细信息"""
        if not PSUTIL_AVAILABLE:
            return None

        try:
            process = psutil.Process(pid)

            # 获取完整性级别
            integrity_level = self.check_process_integrity(pid)

            return {
                'pid': pid,
                'name': process.name(),
                'exe': process.exe(),
                'status': process.status(),
                'username': process.username(),
                'create_time': process.create_time(),
                'memory_info': process.memory_info(),
                'cpu_percent': process.cpu_percent(),
                'num_threads': process.num_threads(),
                'integrity_level': integrity_level,
                'is_protected': self.is_signed_process_protected(pid)
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None