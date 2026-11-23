"""
Windows兼容性模块 - 专门处理Windows 11 312字符路径问题
"""

import platform
import sys
import ctypes


class WindowsCompatibility:
    """Windows兼容性检查类"""

    def __init__(self):
        self.os_info = self._get_os_info()

    def _get_os_info(self):
        """获取操作系统信息"""
        info = {
            'os_name': platform.system(),
            'os_version': platform.version(),
            'os_release': platform.release(),
            'os_platform': platform.platform(),
            'python_arch': '64-bit' if sys.maxsize > 2**32 else '32-bit'
        }

        # 更具体的Windows版本检测
        if info['os_name'] == 'Windows':
            try:
                # 尝试获取更详细的Windows版本信息
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
                product_name = winreg.QueryValueEx(key, "ProductName")[0]
                release_id = winreg.QueryValueEx(key, "ReleaseId")[0] if hasattr(key, 'ReleaseId') else "Unknown"
                current_build = winreg.QueryValueEx(key, "CurrentBuild")[0]

                info['specific_version'] = f"{product_name} (Build {current_build})"
                info['release_id'] = release_id
                info['current_build'] = current_build

                # 检查是否是Windows 11
                info['is_windows_11'] = 'Windows 11' in product_name or int(current_build) >= 22000

                # 检查25H2版本
                info['is_25h2'] = '25H2' in product_name or release_id == '25H2'

                winreg.CloseKey(key)
            except Exception:
                info['specific_version'] = f"Windows {info['os_release']} {info['os_version']}"
                info['is_windows_11'] = info['os_release'] == '11' or (info['os_release'] == '10' and int(info['os_version'].split('.')[2]) >= 22000)
                info['is_25h2'] = False

        return info

    def is_windows_11(self):
        """检查是否是Windows 11"""
        return self.os_info.get('is_windows_11', False)

    def is_25h2(self):
        """检查是否是25H2版本"""
        return self.os_info.get('is_25h2', False)

    def check_long_path_support(self):
        """检查系统是否启用了长路径支持"""
        if self.os_info['os_name'] != 'Windows':
            return True  # 非Windows系统默认支持长路径

        try:
            # 检查注册表键值
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\FileSystem")
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            winreg.CloseKey(key)

            return value == 1
        except Exception:
            # 如果无法读取注册表，假设未启用
            return False

    def get_os_compatibility_info(self):
        """获取操作系统兼容性信息"""
        compat_info = self.os_info.copy()
        compat_info['long_path_support'] = self.check_long_path_support()
        compat_info['is_windows_11'] = self.is_windows_11()
        compat_info['is_25h2'] = self.is_25h2()

        # 添加Windows 11 312字符问题的特殊标记
        if compat_info['is_windows_11']:
            compat_info['312_char_issue'] = True
            compat_info['notes'] = "Windows 11存在312字符路径创建问题，已应用兼容性修复"
        else:
            compat_info['312_char_issue'] = False
            compat_info['notes'] = "正常系统"

        return compat_info


# 创建全局实例
windows_compat = WindowsCompatibility()


def safe_create_directory(path):
    """安全创建目录，专门处理Windows 11长路径问题"""
    try:
        # 首先尝试标准方法
        import os
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        # 如果标准方法失败，尝试逐级创建
        try:
            path_parts = path.split(os.sep)
            current_path = ""

            for part in path_parts:
                if not part:
                    continue

                if ':' in part and len(current_path) == 0:
                    current_path = part + os.sep
                else:
                    current_path = os.path.join(current_path, part) if current_path else part

                if not os.path.exists(current_path):
                    try:
                        os.mkdir(current_path)
                    except FileExistsError:
                        pass
                    except Exception:
                        # 如果这一层创建失败，继续尝试下一层
                        continue

            return os.path.exists(path)
        except Exception:
            return False