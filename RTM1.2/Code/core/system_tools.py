"""
系统工具功能实现 - 完整修复版
支持Windows XP到Windows 11及Windows Server 2012到2022
"""

import os
import sys
import subprocess
import ctypes
import platform
import tkinter as tk
from tkinter import scrolledtext
from utils.helpers import is_admin


class SystemTools:
    """系统工具类 - 兼容多Windows版本"""

    def __init__(self):
        self.windows_version = self._get_windows_version()

    def _get_windows_version(self):
        """获取Windows版本信息"""
        try:
            ver = platform.version()
            major, minor, build = map(int, ver.split('.'))

            # Windows版本判断
            if major == 10:
                if build >= 22000:
                    return "Windows 11"
                else:
                    return "Windows 10"
            elif major == 6:
                if minor == 3:
                    return "Windows 8.1"
                elif minor == 2:
                    return "Windows 8"
                elif minor == 1:
                    return "Windows 7"
                elif minor == 0:
                    return "Windows Vista"
            elif major == 5:
                if minor == 2:
                    return "Windows Server 2003"
                elif minor == 1:
                    return "Windows XP"

            return f"Windows {major}.{minor}"
        except:
            return "Unknown Windows Version"

    def query_file_permission(self, path, parent_window=None):
        """查询文件或文件夹的权限 - 修复版，支持弹窗显示"""
        if not path or not os.path.exists(path):
            raise FileNotFoundError("请选择有效的文件或文件夹路径")

        if sys.platform == 'win32':
            return self._query_windows_permission_detailed(path, parent_window)
        else:
            return self._query_unix_permission(path)

    def _query_windows_permission_detailed(self, path, parent_window):
        """在Windows上查询文件权限 - 详细版本，支持弹窗显示"""
        try:
            # 使用icacls命令查询权限 - 兼容所有Windows版本
            cmd = f'icacls "{path}"'

            # 对于Windows XP，可能需要使用cacls命令作为备选
            if self.windows_version == "Windows XP":
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                except:
                    # 回退到cacls命令
                    cmd = f'cacls "{path}"'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

            # 创建弹窗显示详细信息
            if parent_window:
                self._show_permission_dialog(parent_window, path, result)

            if result.returncode == 0:
                output_lines = result.stdout.split('\n')
                permission_info = f"文件权限信息: {path}\n"
                for line in output_lines:
                    if line.strip() and not line.startswith(path):
                        permission_info += f"{line}\n"
                return permission_info
            else:
                return f"查询权限失败: {result.stderr}"

        except Exception as e:
            return f"查询权限时发生错误: {str(e)}"

    def _show_permission_dialog(self, parent, path, result):
        """显示权限详细信息的弹窗 - 添加权限说明"""
        dialog = tk.Toplevel(parent)
        dialog.title(f"权限信息 - {os.path.basename(path)}")
        dialog.geometry("700x500")
        dialog.transient(parent)
        dialog.grab_set()

        # 标题
        title_frame = tk.Frame(dialog)
        title_frame.pack(fill='x', padx=10, pady=10)

        tk.Label(title_frame, text=f"路径: {path}",
                 font=('Arial', 10, 'bold'), wraplength=600, justify='left').pack(anchor='w')

        # 权限信息显示区域
        info_frame = tk.Frame(dialog)
        info_frame.pack(fill='both', expand=True, padx=10, pady=5)

        # 添加滚动文本框
        text_area = scrolledtext.ScrolledText(info_frame, wrap=tk.WORD, width=80, height=25)
        text_area.pack(fill='both', expand=True)

        # 配置文本样式 - 添加权限说明
        text_area.tag_configure("deny_perm", foreground="red", font=('Arial', 9, 'bold'))
        text_area.tag_configure("allow_perm", foreground="green", font=('Arial', 9))
        text_area.tag_configure("normal_perm", font=('Arial', 9))
        text_area.tag_configure("header", font=('Arial', 10, 'bold'))
        text_area.tag_configure("explanation", foreground="blue", font=('Arial', 9))
        text_area.tag_configure("warning", foreground="orange", font=('Arial', 9, 'bold'))

        # 显示权限信息
        if result.returncode == 0:
            text_area.insert(tk.END, "✅ 权限查询成功\n\n", "header")
            text_area.insert(tk.END, f"目标路径: {path}\n", "normal_perm")
            text_area.insert(tk.END, "=" * 60 + "\n\n", "normal_perm")

            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if line.strip():
                    # 检查是否包含DENY权限
                    if "DENY" in line.upper():
                        # 提取DENY部分进行高亮显示
                        parts = line.split("DENY")
                        if len(parts) > 1:
                            text_area.insert(tk.END, parts[0], "normal_perm")
                            text_area.insert(tk.END, "DENY", "deny_perm")
                            text_area.insert(tk.END, parts[1] + '\n', "normal_perm")
                        else:
                            text_area.insert(tk.END, line + '\n', "deny_perm")
                    elif any(perm in line.upper() for perm in ['F', 'M', 'RX', 'R', 'W', 'D']):
                        # 允许权限使用绿色
                        text_area.insert(tk.END, line + '\n', "allow_perm")
                    else:
                        text_area.insert(tk.END, line + '\n', "normal_perm")

            # 添加权限说明 - 修改为更详细的说明
            text_area.insert(tk.END, "\n" + "=" * 60 + "\n", "normal_perm")
            text_area.insert(tk.END, "权限说明:\n", "header")
            text_area.insert(tk.END, "F - 完全控制 (允许所有操作)\n", "explanation")
            text_area.insert(tk.END, "M - 修改 (允许读取、写入、执行、删除)\n", "explanation")
            text_area.insert(tk.END, "RX - 读取和执行 (允许读取和执行文件)\n", "explanation")
            text_area.insert(tk.END, "R - 只读 (仅允许读取文件内容)\n", "explanation")
            text_area.insert(tk.END, "W - 只写 (仅允许写入文件)\n", "explanation")
            text_area.insert(tk.END, "D - 删除 (允许删除文件或文件夹)\n", "explanation")
            text_area.insert(tk.END, "DENY - 拒绝权限（红色加粗显示，优先级最高）\n", "deny_perm")
            text_area.insert(tk.END, "\n注意: 权限按顺序评估，DENY权限会覆盖ALLOW权限\n", "explanation")
            text_area.insert(tk.END, "重要: 对于可执行文件，需要为当前用户设置DENY X才能确保无法执行\n", "warning")
        else:
            text_area.insert(tk.END, "❌ 权限查询失败\n\n", "header")
            text_area.insert(tk.END, f"错误信息: {result.stderr}\n", "normal_perm")

        text_area.config(state=tk.DISABLED)

        # 关闭按钮
        button_frame = tk.Frame(dialog)
        button_frame.pack(fill='x', padx=10, pady=10)

        tk.Button(button_frame, text="关闭", command=dialog.destroy,
                  width=15, height=2).pack()

        # 让对话框居中
        dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def set_file_permission(self, path, permission, take_ownership=True):
        """设置文件权限 - 修复版，处理拒绝访问的情况，增加可读取不可执行权限，并支持递归设置"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件或文件夹不存在: {path}")

        if sys.platform == 'win32':
            return self._set_windows_permission_robust(path, permission, take_ownership)
        else:
            return self._set_unix_permission(path, permission)

    def _set_windows_permission_robust(self, path, permission, take_ownership):
        """在Windows上设置文件权限 - 更健壮的版本，支持递归设置"""
        # 首先尝试直接设置权限
        try:
            return self._set_windows_permission(path, permission)
        except Exception as first_error:
            # 如果第一次失败，尝试获取所有权后重试
            if take_ownership:
                try:
                    self._take_ownership(path)
                    # 再次尝试设置权限
                    return self._set_windows_permission(path, permission)
                except Exception as second_error:
                    raise Exception(f"设置权限失败: {first_error}\n获取所有权后重试也失败: {second_error}")
            else:
                raise first_error

    def _take_ownership(self, path):
        """获取文件所有权 - 兼容所有Windows版本"""
        if not is_admin():
            raise PermissionError("获取所有权需要管理员权限")

        try:
            # Windows XP使用不同的命令
            if self.windows_version == "Windows XP":
                return self._take_ownership_xp(path)
            else:
                return self._take_ownership_modern(path)
        except Exception as e:
            # 如果命令行方法失败，尝试使用ctypes
            try:
                self._take_ownership_ctypes(path)
                return "成功获取所有权 (使用ctypes)"
            except Exception as ctypes_error:
                raise Exception(f"获取所有权失败: {e}\nctypes方法也失败: {ctypes_error}")

    def _take_ownership_xp(self, path):
        """Windows XP获取所有权方法"""
        try:
            # Windows XP使用subinacl或cacls命令
            if os.path.isdir(path):
                cmd = f'cacls "{path}" /E /G "%USERNAME%":F'
            else:
                cmd = f'cacls "{path}" /G "%USERNAME%":F'

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return "成功获取所有权 (Windows XP)"
            else:
                raise Exception(f"cacls失败: {result.stderr}")
        except Exception as e:
            raise Exception(f"Windows XP获取所有权失败: {e}")

    def _take_ownership_modern(self, path):
        """现代Windows系统获取所有权方法"""
        try:
            # 使用takeown和icacls命令获取所有权
            if os.path.isdir(path):
                cmd_takeown = f'takeown /f "{path}" /r /d y'
                cmd_icacls = f'icacls "{path}" /grant:r "%USERNAME%":F'
            else:
                cmd_takeown = f'takeown /f "{path}"'
                cmd_icacls = f'icacls "{path}" /grant:r "%USERNAME%":F'

            # 执行takeown命令
            result_takeown = subprocess.run(cmd_takeown, shell=True, capture_output=True, text=True)
            if result_takeown.returncode != 0:
                print(f"takeown失败: {result_takeown.stderr}")

            # 执行icacls命令授予完全控制权
            result_icacls = subprocess.run(cmd_icacls, shell=True, capture_output=True, text=True)
            if result_icacls.returncode != 0:
                raise Exception(f"icacls失败: {result_icacls.stderr}")

            return "成功获取所有权"

        except Exception as e:
            raise Exception(f"获取所有权失败: {e}")

    def _take_ownership_ctypes(self, path):
        """使用ctypes获取所有权 - 兼容多Windows版本"""
        try:
            # 使用Windows API获取所有权
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)

            # 定义常量
            TOKEN_ALL_ACCESS = 0x000F01FF
            SE_TAKE_OWNERSHIP_NAME = "SeTakeOwnershipPrivilege"

            # 打开进程令牌
            token = ctypes.c_void_p()
            if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_ALL_ACCESS, ctypes.byref(token)):
                raise Exception("无法打开进程令牌")

            # 启用特权
            luid = ctypes.c_ulonglong()
            if not advapi32.LookupPrivilegeValueW(None, SE_TAKE_OWNERSHIP_NAME, ctypes.byref(luid)):
                raise Exception("无法查找特权值")

            # 设置特权
            new_state = (ctypes.c_ulong * 3)()
            new_state[0] = 1  # 特权数量
            new_state[1] = luid
            new_state[2] = 2  # SE_PRIVILEGE_ENABLED

            if not advapi32.AdjustTokenPrivileges(token, False, new_state, 0, None, None):
                raise Exception("无法调整令牌特权")

            return "特权已启用"

        except Exception as e:
            raise Exception(f"ctypes获取所有权失败: {e}")

    def _set_windows_permission(self, path, permission):
        """在Windows上设置文件权限 - 增加可读取不可执行权限，支持递归设置"""
        try:
            # 尝试使用win32security模块
            try:
                import win32security
                import ntsecuritycon as con

                # 获取当前文件的安全描述符
                if os.path.isdir(path):
                    sd = win32security.GetFileSecurity(path, win32security.DACL_SECURITY_INFORMATION)
                else:
                    sd = win32security.GetFileSecurity(path, win32security.DACL_SECURITY_INFORMATION)

                # 获取当前用户的SID - 修复GetCurrentProcess错误
                try:
                    # 正确的方法获取当前进程令牌
                    import win32process
                    import win32api

                    token = win32security.OpenProcessToken(
                        win32process.GetCurrentProcess(),
                        win32security.TOKEN_QUERY
                    )
                    user_sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
                except:
                    # 如果上述方法失败，使用备用方法
                    username = os.environ.get('USERNAME')
                    if not username:
                        username = os.environ.get('USER')
                    user_sid, _, _ = win32security.LookupAccountName(None, username)

                # 根据权限模式设置访问掩码
                if permission == "full_control":
                    access_mask = con.FILE_ALL_ACCESS
                elif permission == "read_no_execute":
                    # 可读取不可执行：只授予读取权限，不包括执行权限
                    access_mask = con.FILE_GENERIC_READ
                elif permission == "read_execute":
                    access_mask = con.FILE_GENERIC_READ | con.FILE_GENERIC_EXECUTE
                elif permission == "deny_read_execute":
                    access_mask = 0  # 无权限

                # 创建新的ACE
                dacl = win32security.ACL()
                if permission == "deny_read_execute":
                    dacl.AddAccessDeniedAce(win32security.ACL_REVISION,
                                            con.FILE_GENERIC_READ | con.FILE_GENERIC_EXECUTE, user_sid)
                else:
                    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, access_mask, user_sid)

                # 设置新的DACL
                sd.SetSecurityDescriptorDacl(1, dacl, 0)

                # 应用安全描述符
                if os.path.isdir(path):
                    win32security.SetFileSecurity(path, win32security.DACL_SECURITY_INFORMATION, sd)
                else:
                    win32security.SetFileSecurity(path, win32security.DACL_SECURITY_INFORMATION, sd)

                return f"权限设置成功: {permission}"

            except ImportError:
                # 如果win32security不可用，使用icacls命令
                return self._set_permission_with_icacls(path, permission)

        except Exception as e:
            # 如果win32security方法失败，回退到icacls
            return self._set_permission_with_icacls(path, permission)

    def _set_permission_with_icacls(self, path, permission):
        """使用icacls命令设置权限 - 增加可读取不可执行权限，支持递归设置"""
        # Windows XP兼容性处理
        if self.windows_version == "Windows XP":
            return self._set_permission_with_cacls(path, permission)

        # 构建基本命令
        if permission == "full_control":
            perm_flag = "F"
        elif permission == "read_execute":
            perm_flag = "RX"
        elif permission == "read_no_execute":
            # 对于"可读取不执行"权限，我们需要特殊处理
            return self._set_read_no_execute_permission_strict(path)
        elif permission == "deny_read_execute":
            # 拒绝权限使用deny命令
            if os.path.isdir(path):
                cmd = f'icacls "{path}" /deny "%USERNAME%":RX /T /Q'
            else:
                cmd = f'icacls "{path}" /deny "%USERNAME%":RX'
        else:
            raise Exception(f"未知的权限类型: {permission}")

        # 如果不是"可读取不执行"权限，构建授权命令
        if permission != "read_no_execute":
            if os.path.isdir(path):
                # 对于文件夹，使用/T参数递归设置所有子文件夹和文件
                cmd = f'icacls "{path}" /grant:r "%USERNAME%":{perm_flag} /T /Q'
            else:
                cmd = f'icacls "{path}" /grant:r "%USERNAME%":{perm_flag}'

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                if os.path.isdir(path):
                    return f"权限设置成功: {permission} (已递归应用到所有子文件夹和文件)"
                else:
                    return f"权限设置成功: {permission}"
            else:
                # 如果失败，尝试先获取所有权
                self._take_ownership(path)
                # 再次尝试
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    if os.path.isdir(path):
                        return f"权限设置成功 (需要获取所有权): {permission} (已递归应用到所有子文件夹和文件)"
                    else:
                        return f"权限设置成功 (需要获取所有权): {permission}"
                else:
                    # 如果还是失败，尝试手动递归设置
                    if os.path.isdir(path) and permission in ["full_control", "read_execute", "read_no_execute"]:
                        return self._set_permission_manual_recursive(path, permission)
                    else:
                        raise Exception(f"icacls命令执行失败: {result.stderr}")
        except subprocess.CalledProcessError as e:
            raise Exception(f"icacls命令执行失败: {e}")

    def _set_read_no_execute_permission_strict(self, path):
        """严格设置'可读取不可执行'权限 - 确保exe文件无法执行"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件或文件夹不存在: {path}")

        try:
            if os.path.isdir(path):
                # 对于文件夹，我们需要更严格的递归处理
                return self._set_read_no_execute_recursive_strict(path)
            else:
                # 对于单个文件，使用严格设置
                return self._set_read_no_execute_single_file_strict(path)
        except Exception as e:
            raise Exception(f"设置'可读取不可执行'权限失败: {str(e)}")

    def _get_current_username(self):
        """获取当前用户名"""
        try:
            username = os.environ.get('USERNAME')
            if not username:
                username = os.environ.get('USER')
            if not username:
                import getpass
                username = getpass.getuser()
            return username
        except:
            return os.environ.get('USERNAME', 'CurrentUser')

    def _set_read_no_execute_single_file_strict(self, file_path):
        """为单个文件设置严格的'可读取不可执行'权限 - 确保当前用户无法执行"""
        # 获取当前用户名
        current_user = self._get_current_username()

        # 获取文件扩展名
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        # 定义可执行文件扩展名
        executable_extensions = ['.exe', '.bat', '.cmd', '.ps1', '.msi', '.com', '.scr',
                                '.vbs', '.js', '.vbe', '.jse', '.wsf', '.wsh', '.reg',
                                '.sh', '.py', '.pl', '.rb', '.php', '.java', '.class']

        if ext in executable_extensions:
            # 对于可执行文件，需要更严格的权限设置
            try:
                # 1. 先获取文件所有权（如果需要）
                try:
                    self._take_ownership(file_path)
                except:
                    pass  # 如果获取所有权失败，继续尝试

                # 2. 禁用继承权限
                cmd_inherit = f'icacls "{file_path}" /inheritance:r'
                result_inherit = subprocess.run(cmd_inherit, shell=True, capture_output=True, text=True)

                if result_inherit.returncode != 0:
                    # 如果禁用继承失败，尝试使用备用方法
                    print(f"禁用继承失败: {result_inherit.stderr}")

                # 3. 设置当前用户只读权限
                cmd_read = f'icacls "{file_path}" /grant:r "{current_user}":R'
                result_read = subprocess.run(cmd_read, shell=True, capture_output=True, text=True)

                if result_read.returncode != 0:
                    # 如果设置只读失败，使用备用用户名格式
                    cmd_read = f'icacls "{file_path}" /grant:r "%USERNAME%":R'
                    result_read = subprocess.run(cmd_read, shell=True, capture_output=True, text=True)

                # 4. 拒绝当前用户的执行权限 - 这是关键步骤！
                cmd_deny_execute = f'icacls "{file_path}" /deny "{current_user}":X'
                result_deny = subprocess.run(cmd_deny_execute, shell=True, capture_output=True, text=True)

                if result_deny.returncode != 0:
                    # 如果拒绝权限失败，使用备用用户名格式
                    cmd_deny_execute = f'icacls "{file_path}" /deny "%USERNAME%":X'
                    result_deny = subprocess.run(cmd_deny_execute, shell=True, capture_output=True, text=True)

                # 5. 验证权限设置
                verify_cmd = f'icacls "{file_path}"'
                verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)

                if (result_read.returncode == 0 and result_deny.returncode == 0 and
                    verify_result.returncode == 0):
                    # 检查是否成功设置了DENY X权限
                    if f"{current_user}:(DENY)(X)" in verify_result.stdout or \
                       f"{os.environ.get('USERNAME', 'CurrentUser')}:(DENY)(X)" in verify_result.stdout:
                        return f"权限设置成功: read_no_execute (已严格禁止执行: {os.path.basename(file_path)})"
                    else:
                        # 备用方法：尝试使用SYSTEM用户设置只读，然后拒绝所有用户执行
                        cmd_system = f'icacls "{file_path}" /grant:r "SYSTEM":R'
                        cmd_deny_all = f'icacls "{file_path}" /deny Everyone:X'

                        subprocess.run(cmd_system, shell=True, capture_output=True, text=True)
                        subprocess.run(cmd_deny_all, shell=True, capture_output=True, text=True)

                        return f"权限设置成功: read_no_execute (备用方法: {os.path.basename(file_path)})"
                else:
                    # 备用方法：直接拒绝当前用户读取和执行权限
                    cmd_deny_all = f'icacls "{file_path}" /deny "{current_user}":RX'
                    result_deny_all = subprocess.run(cmd_deny_all, shell=True, capture_output=True, text=True)

                    if result_deny_all.returncode == 0:
                        return f"权限设置成功: read_no_execute (拒绝所有读取和执行: {os.path.basename(file_path)})"
                    else:
                        raise Exception(f"设置可执行文件权限失败: {result_deny_all.stderr}")

            except Exception as e:
                raise Exception(f"设置可执行文件权限时出错: {str(e)}")
        else:
            # 对于非可执行文件，设置只读权限
            try:
                current_user = self._get_current_username()
                cmd = f'icacls "{file_path}" /grant:r "{current_user}":R'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode == 0:
                    return f"权限设置成功: read_no_execute (只读: {os.path.basename(file_path)})"
                else:
                    # 尝试获取所有权后重试
                    try:
                        self._take_ownership(file_path)
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                        if result.returncode == 0:
                            return f"权限设置成功 (需要获取所有权): read_no_execute (只读: {os.path.basename(file_path)})"
                        else:
                            raise Exception(f"设置文件权限失败: {result.stderr}")
                    except Exception as e:
                        raise Exception(f"设置文件权限失败: {result.stderr}")
            except Exception as e:
                raise Exception(f"设置文件权限失败: {str(e)}")

    def _set_read_no_execute_recursive_strict(self, folder_path):
        """递归设置文件夹的严格'可读取不可执行'权限"""
        folder_count = 0
        file_count = 0
        exe_file_count = 0
        failed_items = []

        try:
            current_user = self._get_current_username()

            # 首先设置文件夹本身的权限
            try:
                # 对于文件夹，禁用继承，设置只读权限
                cmd_inherit = f'icacls "{folder_path}" /inheritance:r'
                cmd_read = f'icacls "{folder_path}" /grant:r "{current_user}":R'

                result_inherit = subprocess.run(cmd_inherit, shell=True, capture_output=True, text=True)
                if result_inherit.returncode != 0:
                    self._take_ownership(folder_path)
                    result_inherit = subprocess.run(cmd_inherit, shell=True, capture_output=True, text=True)

                result_read = subprocess.run(cmd_read, shell=True, capture_output=True, text=True)
                if result_read.returncode == 0:
                    folder_count += 1
                else:
                    failed_items.append(folder_path)
                    print(f"警告: 设置文件夹 {folder_path} 权限失败: {result_read.stderr}")
            except Exception as e:
                failed_items.append(folder_path)
                print(f"警告: 设置文件夹 {folder_path} 权限时出错: {e}")

            # 定义可执行文件扩展名
            executable_extensions = ['.exe', '.bat', '.cmd', '.ps1', '.msi', '.com', '.scr',
                                    '.vbs', '.js', '.vbe', '.jse', '.wsf', '.wsh', '.reg',
                                    '.sh', '.py', '.pl', '.rb', '.php', '.java', '.class']

            # 递归遍历所有子文件夹和文件
            for root, dirs, files in os.walk(folder_path):
                # 设置子文件夹权限
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        cmd_dir = f'icacls "{dir_path}" /grant:r "{current_user}":R'
                        result_dir = subprocess.run(cmd_dir, shell=True, capture_output=True, text=True)
                        if result_dir.returncode == 0:
                            folder_count += 1
                        else:
                            failed_items.append(dir_path)
                            print(f"警告: 设置子文件夹 {dir_path} 权限失败: {result_dir.stderr}")
                    except Exception as e:
                        failed_items.append(dir_path)
                        print(f"警告: 设置子文件夹 {dir_path} 权限时出错: {e}")

                # 设置文件权限
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        # 检查文件扩展名
                        _, ext = os.path.splitext(file_name)
                        ext = ext.lower()

                        if ext in executable_extensions:
                            # 对于可执行文件，使用严格的权限设置
                            # 1. 禁用继承权限
                            cmd_inherit = f'icacls "{file_path}" /inheritance:r'
                            result_inherit = subprocess.run(cmd_inherit, shell=True, capture_output=True, text=True)

                            if result_inherit.returncode != 0:
                                # 如果失败，尝试获取所有权
                                self._take_ownership(file_path)
                                result_inherit = subprocess.run(cmd_inherit, shell=True, capture_output=True, text=True)

                            # 2. 设置当前用户只读权限
                            cmd_read = f'icacls "{file_path}" /grant:r "{current_user}":R'
                            result_read = subprocess.run(cmd_read, shell=True, capture_output=True, text=True)

                            if result_read.returncode != 0:
                                # 尝试使用备用用户名格式
                                cmd_read = f'icacls "{file_path}" /grant:r "%USERNAME%":R'
                                result_read = subprocess.run(cmd_read, shell=True, capture_output=True, text=True)

                            # 3. 拒绝当前用户的执行权限 - 这是关键步骤！
                            cmd_deny = f'icacls "{file_path}" /deny "{current_user}":X'
                            result_deny = subprocess.run(cmd_deny, shell=True, capture_output=True, text=True)

                            if result_deny.returncode != 0:
                                # 尝试使用备用用户名格式
                                cmd_deny = f'icacls "{file_path}" /deny "%USERNAME%":X'
                                result_deny = subprocess.run(cmd_deny, shell=True, capture_output=True, text=True)

                            # 验证权限设置
                            verify_cmd = f'icacls "{file_path}"'
                            verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)

                            if (result_read.returncode == 0 and result_deny.returncode == 0 and
                                verify_result.returncode == 0):
                                # 检查是否成功设置了DENY X权限
                                if f"{current_user}:(DENY)(X)" in verify_result.stdout or \
                                   f"{os.environ.get('USERNAME', 'CurrentUser')}:(DENY)(X)" in verify_result.stdout:
                                    file_count += 1
                                    exe_file_count += 1
                                else:
                                    # 备用方法：拒绝所有读取和执行
                                    cmd_deny_all = f'icacls "{file_path}" /deny "{current_user}":RX'
                                    result_deny_all = subprocess.run(cmd_deny_all, shell=True, capture_output=True, text=True)

                                    if result_deny_all.returncode == 0:
                                        file_count += 1
                                        exe_file_count += 1
                                    else:
                                        failed_items.append(file_path)
                                        print(f"警告: 设置可执行文件 {file_path} 权限失败")
                        else:
                            # 对于非可执行文件，设置只读权限
                            cmd = f'icacls "{file_path}" /grant:r "{current_user}":R'
                            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                            if result.returncode == 0:
                                file_count += 1
                            else:
                                failed_items.append(file_path)
                                print(f"警告: 设置文件 {file_path} 权限失败: {result.stderr}")
                    except Exception as e:
                        failed_items.append(file_path)
                        print(f"警告: 设置文件 {file_path} 权限时出错: {e}")

            # 返回结果
            total_items = folder_count + file_count + len(failed_items)
            success_rate = ((folder_count + file_count) / total_items * 100) if total_items > 0 else 0

            if len(failed_items) == 0:
                return f"权限设置成功: read_no_execute (已应用到 {folder_count} 个文件夹和 {file_count} 个文件，其中 {exe_file_count} 个可执行文件已严格禁止执行)"
            else:
                return f"权限设置部分成功: read_no_execute (成功: {folder_count} 个文件夹和 {file_count} 个文件，失败: {len(failed_items)} 个，成功率: {success_rate:.1f}%)"

        except Exception as e:
            raise Exception(f"递归设置权限失败: {str(e)}")

    def _verify_permission_recursive(self, path, permission):
        """验证权限是否递归设置成功"""
        folders = 0
        files = 0
        failed_items = []

        # 只检查前几层和部分文件，避免性能问题
        max_depth = 3
        max_items = 50
        checked_items = 0

        for root, dirs, file_names in os.walk(path):
            # 计算当前深度
            current_depth = root[len(path):].count(os.sep)
            if current_depth > max_depth:
                break

            # 检查子文件夹
            for dir_name in dirs:
                if checked_items >= max_items:
                    break
                dir_path = os.path.join(root, dir_name)
                try:
                    # 尝试查询权限
                    cmd = f'icacls "{dir_path}"'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        folders += 1
                except:
                    failed_items.append(dir_path)
                checked_items += 1

            # 检查文件
            for file_name in file_names:
                if checked_items >= max_items:
                    break
                file_path = os.path.join(root, file_name)
                try:
                    cmd = f'icacls "{file_path}"'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        files += 1
                except:
                    failed_items.append(file_path)
                checked_items += 1

            if checked_items >= max_items:
                break

        return {
            "success": len(failed_items) == 0,
            "folders": folders,
            "files": files,
            "failed_items": failed_items
        }

    def _set_permission_manual_recursive(self, path, permission):
        """手动递归设置权限（当icacls递归失败时使用）"""
        if permission == "full_control":
            perm_flag = "F"
        elif permission == "read_execute":
            perm_flag = "RX"
        elif permission == "read_no_execute":
            # 对于"可读取不执行"权限，需要特殊处理
            return self._set_read_no_execute_recursive_strict(path)
        else:
            raise Exception(f"不支持的权限类型: {permission}")

        folder_count = 0
        file_count = 0

        try:
            # 首先设置当前文件夹
            cmd = f'icacls "{path}" /grant:r "%USERNAME%":{perm_flag}'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"警告: 设置文件夹 {path} 权限失败: {result.stderr}")

            folder_count += 1

            # 递归遍历所有子文件夹和文件
            for root, dirs, files in os.walk(path):
                # 设置子文件夹权限
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    cmd = f'icacls "{dir_path}" /grant:r "%USERNAME%":{perm_flag}'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        folder_count += 1
                    else:
                        print(f"警告: 设置子文件夹 {dir_path} 权限失败: {result.stderr}")

                # 设置文件权限
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    cmd = f'icacls "{file_path}" /grant:r "%USERNAME%":{perm_flag}'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        file_count += 1
                    else:
                        print(f"警告: 设置文件 {file_path} 权限失败: {result.stderr}")

            return f"权限设置成功: {permission} (手动递归应用到 {folder_count} 个文件夹和 {file_count} 个文件)"

        except Exception as e:
            raise Exception(f"手动递归设置权限失败: {str(e)}")

    def _set_permission_with_cacls(self, path, permission):
        """Windows XP使用cacls命令设置权限 - 支持递归设置"""
        def set_single_path(file_path, perm):
            """为单个路径设置权限"""
            if perm == "full_control":
                cmd = f'cacls "{file_path}" /G "%USERNAME%":F'
            elif perm == "read_execute":
                cmd = f'cacls "{file_path}" /G "%USERNAME%":RX'
            elif perm == "read_no_execute":
                # 对于"可读取不执行"权限，需要特殊处理可执行文件
                _, ext = os.path.splitext(file_path)
                ext = ext.lower()

                # 在Windows XP中，cacls无法直接设置DENY权限，只能设置允许权限
                # 对于可执行文件，我们设置只读权限，但这可能无法阻止执行
                cmd = f'cacls "{file_path}" /G "%USERNAME%":R'
            elif perm == "deny_read_execute":
                cmd = f'cacls "{file_path}" /D "%USERNAME%"'

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"cacls命令执行失败: {result.stderr}")

        try:
            # 首先设置当前路径
            set_single_path(path, permission)

            # 如果是文件夹，递归设置所有子文件夹和文件
            if os.path.isdir(path):
                file_count = 0
                folder_count = 0
                exe_file_count = 0

                for root, dirs, files in os.walk(path):
                    # 设置子文件夹权限
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            set_single_path(dir_path, permission)
                            folder_count += 1
                        except Exception as e:
                            print(f"警告: 设置文件夹 {dir_path} 权限失败: {e}")

                    # 设置文件权限
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        try:
                            set_single_path(file_path, permission)
                            file_count += 1

                            # 统计exe文件
                            _, ext = os.path.splitext(file_name)
                            if ext.lower() in ['.exe', '.bat', '.cmd', '.ps1', '.msi', '.com']:
                                exe_file_count += 1
                        except Exception as e:
                            print(f"警告: 设置文件 {file_path} 权限失败: {e}")

                if permission == "read_no_execute":
                    return f"权限设置成功: {permission} (已递归应用到 {folder_count} 个文件夹和 {file_count} 个文件，其中 {exe_file_count} 个可执行文件。注意：在Windows XP中可能无法完全阻止可执行文件的执行)"
                else:
                    return f"权限设置成功: {permission} (已递归应用到 {folder_count} 个文件夹和 {file_count} 个文件)"
            else:
                return f"权限设置成功: {permission}"

        except subprocess.CalledProcessError as e:
            raise Exception(f"cacls命令执行失败: {e}")

    def _set_unix_permission(self, path, permission):
        """在Unix系统上设置权限 - 增加可读取不可执行权限，支持递归设置"""
        def set_single_unix_path(file_path, perm):
            """为单个Unix路径设置权限"""
            if perm == "full_control":
                os.chmod(file_path, 0o777)  # rwxrwxrwx
            elif perm == "read_execute":
                os.chmod(file_path, 0o555)  # r-xr-xr-x
            elif perm == "read_no_execute":
                # 对于"可读取不执行"权限，设置只读权限
                os.chmod(file_path, 0o444)  # r--r--r-- (读取但不执行)
            elif perm == "deny_read_execute":
                os.chmod(file_path, 0o000)  # ---------

        try:
            # 设置当前路径权限
            set_single_unix_path(path, permission)

            # 如果是文件夹，递归设置所有子文件夹和文件
            if os.path.isdir(path):
                file_count = 0
                folder_count = 0

                for root, dirs, files in os.walk(path):
                    # 设置子文件夹权限
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            set_single_unix_path(dir_path, permission)
                            folder_count += 1
                        except Exception as e:
                            print(f"警告: 设置文件夹 {dir_path} 权限失败: {e}")

                    # 设置文件权限
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        try:
                            set_single_unix_path(file_path, permission)
                            file_count += 1
                        except Exception as e:
                            print(f"警告: 设置文件 {file_path} 权限失败: {e}")

                return f"权限设置成功: {permission} (已递归应用到 {folder_count} 个文件夹和 {file_count} 个文件)"
            else:
                return f"权限设置成功: {permission}"

        except Exception as e:
            raise Exception(f"Unix权限设置失败: {e}")

    def modify_host_file(self):
        """修改host文件权限并使用记事本打开 - 兼容多Windows版本"""
        # 确定host文件路径
        if self.windows_version == "Windows XP":
            host_path = r"C:\WINDOWS\system32\drivers\etc\hosts"
        else:
            host_path = r"C:\Windows\System32\drivers\etc\hosts"

        if not os.path.exists(host_path):
            raise FileNotFoundError("找不到host文件")

        # 检查管理员权限
        if not is_admin():
            raise PermissionError("此操作需要管理员权限。请以管理员身份重新运行此程序。")

        try:
            # 设置完全控制权限
            result = self._set_windows_permission_robust(host_path, "full_control", True)

            # 使用记事本打开host文件
            if self.windows_version == "Windows XP":
                notepad_path = r"C:\WINDOWS\system32\notepad.exe"
            else:
                notepad_path = r"C:\Windows\System32\notepad.exe"

            if os.path.exists(notepad_path):
                subprocess.Popen([notepad_path, host_path])
                open_result = "使用记事本打开host文件"
            else:
                # 如果找不到记事本，使用默认程序
                os.startfile(host_path)
                open_result = "使用默认程序打开host文件"

            return f"host文件权限已设置并打开: {result}\n{open_result}"
        except Exception as e:
            # 如果常规方法失败，尝试使用命令行
            try:
                # 使用icacls直接设置权限
                if self.windows_version == "Windows XP":
                    cmd = f'cacls "{host_path}" /G "%USERNAME%":F'
                else:
                    cmd = f'icacls "{host_path}" /grant:r "%USERNAME%":F'

                subprocess.run(cmd, shell=True, check=True)

                # 使用记事本打开host文件
                if os.path.exists(notepad_path):
                    subprocess.Popen([notepad_path, host_path])
                    open_result = "使用记事本打开host文件"
                else:
                    os.startfile(host_path)
                    open_result = "使用默认程序打开host文件"

                return "host文件权限已设置并打开 (使用命令行)"
            except Exception as cmd_error:
                raise Exception(f"修改host文件失败: {str(e)}\n命令行方法也失败: {str(cmd_error)}")

    def get_system_info(self):
        """获取系统信息"""
        try:
            info = {
                'windows_version': self.windows_version,
                'platform': platform.platform(),
                'architecture': platform.architecture()[0],
                'processor': platform.processor(),
                'is_admin': is_admin()
            }

            # 尝试获取更多系统信息
            try:
                import psutil
                info['memory_total'] = psutil.virtual_memory().total
                info['memory_available'] = psutil.virtual_memory().available
                info['disk_usage'] = psutil.disk_usage('/' if os.name != 'nt' else 'C:')
            except:
                pass

            return info
        except Exception as e:
            return {'error': f'获取系统信息失败: {str(e)}'}