"""
路径生成功能实现 - 修复字符类型选择问题，支持按比例均匀分配字符
改进：添加Windows 11 25H2长路径兼容性修复
修复：Windows 11 25H2路径长度300字符时的虚假失败报告问题
新增：Windows 11系统长路径支持功能开关控制
修复：打开长路径文件夹问题
"""

import os
import random
import string
import time
import ctypes
import winreg
import subprocess
from pathlib import Path
from utils.helpers import generate_random_content
from .windows_compat import windows_compat, safe_create_directory


class PathGenerator:
    """路径生成器 - 修复字符类型选择问题，支持按比例均匀分配字符，兼容所有Windows版本"""

    def __init__(self):
        self.long_path_enabled = self._check_long_path_support()
        print(f"系统长路径支持状态: {'✅ 已启用' if self.long_path_enabled else '❌ 未启用'}")

    def _check_long_path_support(self):
        """检查系统是否已启用长路径支持"""
        try:
            # 方法1: 检查注册表键值
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\FileSystem")
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            winreg.CloseKey(key)
            return value == 1
        except Exception as e:
            print(f"检查长路径支持失败: {e}")
            # 方法2: 尝试创建一个超过260字符的路径来测试
            return self._test_long_path_support()

    def _test_long_path_support(self):
        """通过实际测试检查长路径支持"""
        try:
            # 创建一个测试路径（长度超过260字符）
            test_dir = "C:\\long_path_test_" + "a" * 200
            if len(test_dir) > 260:
                os.makedirs(test_dir, exist_ok=True)
                exists = os.path.exists(test_dir)
                if exists:
                    os.rmdir(test_dir)
                return exists
        except Exception:
            pass
        return False

    def enable_long_path_support(self):
        """启用系统长路径支持（需要管理员权限）"""
        try:
            # 检查是否具有管理员权限
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("❌ 需要管理员权限来启用长路径支持")
                return False, "需要管理员权限", False

            # 修改注册表启用长路径支持
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\FileSystem",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)

            print("✅ 已启用系统长路径支持")

            # 更新状态
            self.long_path_enabled = True

            # 返回成功和需要重启的提示
            return True, "已成功启用Windows长路径支持！\n\n⚠️ 重要提示：为了使设置生效，需要重启系统。\n\n是否立即重启系统？", True

        except Exception as e:
            print(f"启用长路径支持失败: {e}")
            return False, f"启用失败: {str(e)}", False

    def disable_long_path_support(self):
        """禁用系统长路径支持（需要管理员权限）"""
        try:
            # 检查是否具有管理员权限
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("❌ 需要管理员权限来禁用长路径支持")
                return False, "需要管理员权限", False

            # 修改注册表禁用长路径支持
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\FileSystem",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)

            print("✅ 已禁用系统长路径支持")

            # 更新状态
            self.long_path_enabled = False

            return True, "已成功禁用Windows长路径支持！\n\n⚠️ 重要提示：为了使设置生效，需要重启系统。\n\n是否立即重启系统？", True

        except Exception as e:
            print(f"禁用长路径支持失败: {e}")
            return False, f"禁用失败: {str(e)}", False

    def get_short_path_name(self, long_name):
        """获取长路径的短路径名称（8.3格式）用于打开文件夹"""
        try:
            # 导入Windows API函数
            GetShortPathName = ctypes.windll.kernel32.GetShortPathNameW

            # 准备参数
            buf_size = 1024
            buffer = ctypes.create_unicode_buffer(buf_size)

            # 调用函数
            length = GetShortPathName(long_name, buffer, buf_size)

            if length == 0:
                # 函数失败，返回原始路径
                print(f"获取短路径失败: {ctypes.GetLastError()}")
                return long_name
            else:
                short_path = buffer.value
                print(f"获取短路径成功: {long_name[:50]}... -> {short_path[:50]}...")
                return short_path

        except Exception as e:
            print(f"获取短路径异常: {e}")
            return long_name

    def open_folder_safely(self, folder_path):
        """安全打开文件夹，特别处理长路径问题"""
        try:
            # 检查路径是否存在
            if not os.path.exists(folder_path):
                # 尝试等待文件系统刷新
                time.sleep(0.5)
                if not os.path.exists(folder_path):
                    return False, f"文件夹不存在: {folder_path[:80]}..."

            # 对于长路径，尝试多种方法
            path_length = len(folder_path)

            # 方法1: 直接使用os.startfile（适用于短路径）
            if path_length < 250:
                try:
                    os.startfile(folder_path)
                    return True, f"已打开文件夹: {folder_path[:80]}..."
                except Exception as e1:
                    print(f"方法1失败: {e1}")

            # 方法2: 获取短路径后打开
            try:
                short_path = self.get_short_path_name(folder_path)
                if short_path != folder_path and len(short_path) < 250:
                    os.startfile(short_path)
                    return True, f"已通过短路径打开文件夹: {short_path[:80]}..."
            except Exception as e2:
                print(f"方法2失败: {e2}")

            # 方法3: 使用explorer命令
            try:
                # 使用引号包裹路径
                cmd = f'explorer "{folder_path}"'
                subprocess.Popen(cmd, shell=True)
                return True, f"已使用explorer命令打开文件夹: {folder_path[:80]}..."
            except Exception as e3:
                print(f"方法3失败: {e3}")

            # 方法4: 使用explorer /select, 命令
            try:
                # 如果有文件，选择文件；如果只有文件夹，打开文件夹
                if os.path.isfile(folder_path):
                    cmd = f'explorer /select,"{folder_path}"'
                else:
                    cmd = f'explorer "{folder_path}"'
                subprocess.Popen(cmd, shell=True)
                return True, f"已使用explorer /select命令打开文件夹: {folder_path[:80]}..."
            except Exception as e4:
                print(f"方法4失败: {e4}")

            # 方法5: 使用start命令
            try:
                cmd = f'start "" "{folder_path}"'
                subprocess.Popen(cmd, shell=True)
                return True, f"已使用start命令打开文件夹: {folder_path[:80]}..."
            except Exception as e5:
                print(f"方法5失败: {e5}")

            return False, f"所有打开文件夹方法都失败，请手动访问: {folder_path[:80]}..."

        except Exception as e:
            return False, f"打开文件夹时发生错误: {str(e)}"

    def _get_character_pools(self, char_types):
        """根据字符类型设置获取字符池字典 - 返回每种类型的独立字符池"""
        char_pools = {}

        # 英文字符
        if char_types.get('include_english', True):
            char_pools['english'] = string.ascii_letters

        # 数字字符
        if char_types.get('include_digits', True):
            char_pools['digits'] = string.digits

        # 中文字符 - 常用汉字范围 (Unicode: 4E00-9FFF)
        if char_types.get('include_chinese', True):
            # 常用汉字范围，包括基本汉字和扩展汉字
            common_chinese_chars = [
                '的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严'
            ]
            char_pools['chinese'] = ''.join(common_chinese_chars)

        # 特殊字符 - Windows系统允许的文件名特殊字符
        if char_types.get('include_special', True):
            # Windows文件名允许的特殊字符（不包括 \/:*?"<>|）
            special_chars = '~!@#$%^&()_+-=[]{};,\'. '
            char_pools['special'] = special_chars

        # Unicode字符 - 其他可打印Unicode字符
        if char_types.get('include_unicode', True):
            # 包括一些常见的Unicode符号和表情符号
            unicode_chars = [
                '★', '☆', '♡', '♥', '♦', '♣', '♠', '●', '○', '◎', '◇', '◆', '□', '■', '△', '▲', '▽', '▼',
                '→', '←', '↑', '↓', '↔', '↕', '✔', '✓', '✕', '✖', '✨', '⭐', '🌟', '☀', '☁', '☂', '☃',
                '☎', '☑', '☒', '☔', '☕', '☘', '☝', '☠', '☢', '☣', '☦', '☪', '☮', '☯', '☸', '☹', '☺',
                '♀', '♂', '♩', '♪', '♫', '♬', '♾', '⚓', '⚡', '⚪', '⚫', '⚽', '⚾', '⛄', '⛅', '⛎', '⛔',
                '⛪', '⛲', '⛳', '⛵', '⛺', '⛽', '✂', '✈', '✉', '✌', '✍', '✏', '✒', '✔', '✖', '✝', '✡',
                '✨', '✳', '✴', '❄', '❇', '❌', '❎', '❓', '❔', '❕', '❗', '❤', '➡', '⭐', '🌟', '🙂', '😀',
                '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', '😇', '🙃', '😉', '😌', '😍', '🥰', '😘', '😗',
                '😙', '😚', '😋', '😛', '😝', '😜', '🤪', '🤨', '🧐', '🤓', '😎', '🤩', '🥳', '😏', '😒', '😞',
                '😔', '😟', '😕', '🙁', '☹', '😣', '😖', '😫', '😩', '🥺', '😢', '😭', '😤', '😠', '😡', '🤬',
                '🤯', '😳', '🥵', '🥶', '😱', '😨', '😰', '😥', '😓', '🤗', '🤔', '🤭', '🤫', '🤥', '😶', '😐',
                '😑', '😬', '🙄', '😯', '😦', '😧', '😮', '😲', '🥱', '😴', '🤤', '😪', '😵', '🤐', '🥴', '🤢'
            ]
            char_pools['unicode'] = ''.join(unicode_chars)

        return char_pools

    def _generate_name_with_types(self, length, char_types):
        """根据字符类型生成随机名称 - 按比例均匀分配字符"""
        char_pools = self._get_character_pools(char_types)

        if not char_pools:
            # 回退到默认字符集
            char_pools = {
                'english': string.ascii_letters,
                'digits': string.digits
            }

        # 计算每种字符类型应该生成多少个字符
        pool_count = len(char_pools)
        base_chars_per_pool = length // pool_count
        remainder = length % pool_count

        # 生成字符列表
        all_chars = []

        for i, (pool_name, char_pool) in enumerate(char_pools.items()):
            # 计算该字符池应该生成的字符数量
            chars_needed = base_chars_per_pool
            if i < remainder:  # 将余数分配到前几个字符池
                chars_needed += 1

            # 从该字符池中随机选择指定数量的字符
            if len(char_pool) >= chars_needed:
                selected_chars = random.sample(char_pool, chars_needed)
            else:
                # 如果字符池中的字符不够，重复选择
                selected_chars = [random.choice(char_pool) for _ in range(chars_needed)]

            all_chars.extend(selected_chars)

        # 打乱字符顺序
        random.shuffle(all_chars)

        # 组合成最终名称
        name = ''.join(all_chars)

        # 确保名称不以空格或点开头/结尾（Windows限制）
        name = name.strip(' .')

        # 如果名称变空，重新生成
        if not name:
            name = self._generate_name_with_types(length, char_types)

        return name

    def _create_directory_safe(self, path, retry_count=3):
        """
        安全创建目录，兼容所有Windows版本
        修复Windows 11 25H2虚假失败报告问题
        """
        # 首先检查路径是否已经存在
        if os.path.exists(path):
            print(f"✅ 目录已存在，跳过创建: {path[:80]}...")
            return True

        path_length = len(path)

        # Windows 11 25H2的特殊处理：当路径长度接近300字符时，添加额外检查和延迟
        if path_length >= 280 and path_length <= 320:
            print(f"⚠️ Windows 11 25H2长路径警告: 路径长度 {path_length} 字符，使用增强创建和验证方法")

        retry_attempts = 0
        last_error = None

        while retry_attempts < retry_count:
            try:
                # 方法1: 首先尝试使用标准os.makedirs
                print(f"尝试创建目录 (尝试 {retry_attempts + 1}/{retry_count}): {path[:60]}...")
                os.makedirs(path, exist_ok=True)

                # Windows 11 25H2特殊处理：添加延迟，让文件系统有足够时间更新
                if path_length >= 280 and path_length <= 320:
                    time.sleep(0.1)  # 100毫秒延迟

                # 验证目录是否真的创建成功
                if os.path.exists(path):
                    print(f"✅ 目录创建成功并验证存在: {path[:60]}...")
                    return True
                else:
                    print(f"⚠️ 目录创建后验证失败，等待后重试...")
                    time.sleep(0.2)  # 200毫秒后重试

            except Exception as e:
                last_error = e
                print(f"目录创建失败 (尝试 {retry_attempts + 1}): {e}")

                # 等待一段时间后重试
                time.sleep(0.1 * (retry_attempts + 1))

            retry_attempts += 1

        # 如果标准方法失败，尝试逐级创建
        print(f"尝试逐级创建目录: {path[:60]}...")
        try:
            path_parts = path.split(os.sep)
            current_path = ""

            for i, part in enumerate(path_parts):
                if i == 0 and ':' in part:
                    # 处理盘符
                    current_path = part + os.sep
                else:
                    current_path = os.path.join(current_path, part) if current_path else part

                if not current_path or current_path.endswith(':'):
                    continue

                # 检查当前路径是否存在
                if not os.path.exists(current_path):
                    try:
                        os.mkdir(current_path)
                        print(f"✅ 逐级创建目录: {current_path[:60]}...")

                        # Windows 11 25H2特殊处理：对于长路径，添加延迟
                        if len(current_path) >= 280 and len(current_path) <= 320:
                            time.sleep(0.05)

                    except FileExistsError:
                        pass
                    except Exception as mkdir_error:
                        print(f"创建子目录 {current_path[:60]}... 失败: {mkdir_error}")
                        # 继续尝试创建后续目录

            # 最终验证
            if os.path.exists(path):
                print(f"✅ 逐级方法创建目录成功: {path[:60]}...")
                return True
            else:
                raise Exception(f"逐级创建后目录仍然不存在: {path}")

        except Exception as e2:
            print(f"逐级创建方法失败: {e2}")
            last_error = e2

        # 如果到这里仍然失败，抛出最后一个错误
        if last_error:
            raise Exception(f"所有目录创建方法都失败: {last_error}")
        else:
            raise Exception(f"无法创建目录: {path}")

    def _create_file_safe(self, filepath, content, retry_count=3):
        """
        安全创建文件，兼容所有Windows版本
        修复Windows 11 25H2虚假失败报告问题
        """
        # 首先检查文件是否已经存在
        if os.path.exists(filepath):
            print(f"✅ 文件已存在，跳过创建: {filepath[:80]}...")
            return True

        # 确保目录存在
        dir_path = os.path.dirname(filepath)
        if dir_path and not os.path.exists(dir_path):
            try:
                # 创建父目录时也使用重试机制
                self._create_directory_safe(dir_path, retry_count=2)
            except Exception as e:
                raise Exception(f"无法创建父目录 '{dir_path}': {e}")

        # 检查文件路径长度
        filepath_length = len(filepath)
        if filepath_length >= 280 and filepath_length <= 320:
            print(f"⚠️ Windows 11 25H2长文件路径警告: 路径长度 {filepath_length} 字符")

        retry_attempts = 0
        last_error = None

        while retry_attempts < retry_count:
            try:
                # 方法1: 标准open方法
                print(f"尝试创建文件 (尝试 {retry_attempts + 1}/{retry_count}): {filepath[:60]}...")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Windows 11 25H2特殊处理：添加延迟
                if filepath_length >= 280 and filepath_length <= 320:
                    time.sleep(0.1)

                # 验证文件是否真的创建成功
                if os.path.exists(filepath):
                    # 额外检查文件大小
                    file_size = os.path.getsize(filepath)
                    print(f"✅ 文件创建成功并验证存在，大小: {file_size} 字节: {filepath[:60]}...")
                    return True
                else:
                    print(f"⚠️ 文件创建后验证失败，等待后重试...")
                    time.sleep(0.2)

            except Exception as e:
                last_error = e
                print(f"文件创建失败 (尝试 {retry_attempts + 1}): {e}")

                # 等待一段时间后重试
                time.sleep(0.1 * (retry_attempts + 1))

            retry_attempts += 1

        # 如果到这里仍然失败，尝试替代方法
        print(f"尝试二进制模式创建文件: {filepath[:60]}...")
        try:
            with open(filepath, 'wb') as f:
                f.write(content.encode('utf-8'))

            # 验证
            if os.path.exists(filepath):
                print(f"✅ 二进制方法创建文件成功: {filepath[:60]}...")
                return True
        except Exception as e2:
            print(f"二进制方法失败: {e2}")
            last_error = e2

        # 如果到这里仍然失败，尝试缩短文件名
        if filepath_length > 250:
            print(f"尝试缩短文件名创建文件: {filepath[:60]}...")
            try:
                # 缩短文件名
                dir_name = os.path.dirname(filepath)
                file_name = os.path.basename(filepath)

                if len(file_name) > 50:
                    # 文件名太长，缩短
                    name_without_ext, ext = os.path.splitext(file_name)
                    short_name = name_without_ext[:30] + "_short" + ext
                    new_filepath = os.path.join(dir_name, short_name)

                    with open(new_filepath, 'w', encoding='utf-8') as f:
                        f.write(content)

                    print(f"✅ 缩短文件名创建成功: {short_name}")
                    return True
            except Exception as e3:
                print(f"缩短文件名方法失败: {e3}")
                last_error = e3

        # 如果所有方法都失败，抛出错误
        if last_error:
            raise Exception(f"无法创建文件 '{filepath}': {last_error}")
        else:
            raise Exception(f"无法创建文件: {filepath}")

    def generate_multi_layer_folders(self, base_path, layers, char_types=None):
        """生成多层文件夹结构 - 修复字符类型选择问题，添加兼容性"""
        if char_types is None:
            char_types = {
                'include_english': True,
                'include_chinese': True,
                'include_digits': True,
                'include_special': True,
                'include_unicode': False  # 修改：默认不勾选Unicode字符
            }

        current_path = Path(base_path)

        # 生成多层文件夹
        for i in range(layers):
            # 根据字符类型生成文件夹名
            folder_name = self._generate_name_with_types(8, char_types)
            current_path = current_path / folder_name

        # 使用安全的目录创建方法
        try:
            self._create_directory_safe(str(current_path), retry_count=2)
        except Exception as e:
            # 如果标准方法失败，尝试创建简化路径
            try:
                # 创建较短的路径
                short_path = str(current_path)[:200] if len(str(current_path)) > 200 else str(current_path)
                self._create_directory_safe(short_path, retry_count=2)
                current_path = Path(short_path)
            except Exception as e2:
                raise Exception(f"无法创建目录: {e2}")

        # 生成随机文件名和内容
        file_name = self._generate_name_with_types(8, char_types) + ".txt"
        file_content = generate_random_content(100)

        file_path = current_path / file_name

        # 使用安全的文件创建方法
        try:
            self._create_file_safe(str(file_path), file_content, retry_count=2)
        except Exception as e:
            raise Exception(f"无法创建文件: {e}")

        # 获取使用的字符类型信息
        used_types = []
        if char_types.get('include_english'):
            used_types.append("英文")
        if char_types.get('include_chinese'):
            used_types.append("中文")
        if char_types.get('include_digits'):
            used_types.append("数字")
        if char_types.get('include_special'):
            used_types.append("特殊字符")
        if char_types.get('include_unicode'):
            used_types.append("Unicode")

        type_info = "、".join(used_types)

        return f"生成成功!\n使用的字符类型: {type_info}\n路径: {file_path}\n文件大小: {os.path.getsize(file_path) if os.path.exists(file_path) else 0} 字节"

    def generate_long_path(self, base_path, target_length, char_types=None, ignore_warning=False):
        """生成长路径 - 修复Windows 11 25H2虚假失败报告问题，支持长路径控制"""
        if char_types is None:
            char_types = {
                'include_english': True,
                'include_chinese': True,
                'include_digits': True,
                'include_special': True,
                'include_unicode': False  # 修改：默认不勾选Unicode字符
            }

        # 检查基础路径是否存在
        if not os.path.exists(base_path):
            try:
                self._create_directory_safe(base_path, retry_count=2)
            except Exception as e:
                raise Exception(f"无法创建基础路径 '{base_path}': {e}")

        current_path = base_path

        # 获取操作系统兼容性信息
        compat_info = windows_compat.get_os_compatibility_info()
        is_windows_11 = windows_compat.is_windows_11()
        is_windows_11_25h2 = (is_windows_11 and '25H2' in compat_info.get('os_name', ''))

        # Windows最大路径限制
        max_path_length = 32767

        # 检查是否需要启用长路径支持
        if target_length > 300 and is_windows_11 and not self.long_path_enabled and not ignore_warning:
            # 路径长度超过300且未启用长路径支持，需要提示用户
            raise Exception(f"路径长度超过300字符，但系统长路径支持未启用。\n"
                            f"Windows系统需要启用长路径支持才能创建超过260字符的路径。")

        # 特别处理Windows 11 25H2的300字符问题
        if is_windows_11_25h2 and target_length >= 280 and target_length <= 320:
            print(f"⚠️ Windows 11 25H2检测到目标路径长度 {target_length}，应用特殊兼容性处理")

        # 确保目标长度在合理范围内
        if not self.long_path_enabled:
            # 如果未启用长路径支持，限制最大长度为260
            max_length_without_support = 260
            if target_length > max_length_without_support:
                print(f"⚠️ 系统长路径支持未启用，限制路径长度为{max_length_without_support}")
                target_length = min(target_length, max_length_without_support)
        else:
            # 如果启用了长路径支持，使用正常限制
            target_length = min(target_length, max_path_length - 100)  # 留出缓冲空间

        # 计算需要生成的路径长度（减去基础路径和分隔符）
        base_len = len(base_path)
        # 预留文件名长度（随机文件名 + 扩展名 + 分隔符）
        filename_len = 30  # 估计值
        remaining_len = target_length - base_len - filename_len - 10  # 额外缓冲

        if remaining_len <= 0:
            # 如果基础路径已经很长，就在基础路径下创建文件
            file_name = self._generate_name_with_types(8, char_types) + ".txt"
            file_content = generate_random_content(100)
            file_path = os.path.join(base_path, file_name)

            try:
                self._create_file_safe(file_path, file_content, retry_count=3)
            except Exception as e:
                raise Exception(f"无法创建文件: {e}")

            actual_length = len(file_path)

            # 获取使用的字符类型信息
            used_types = []
            if char_types.get('include_english'):
                used_types.append("英文")
            if char_types.get('include_chinese'):
                used_types.append("中文")
            if char_types.get('include_digits'):
                used_types.append("数字")
            if char_types.get('include_special'):
                used_types.append("特殊字符")
            if char_types.get('include_unicode'):
                used_types.append("Unicode")

            type_info = "、".join(used_types)

            return f"基础路径较长，直接创建文件\n使用的字符类型: {type_info}\n实际路径长度: {actual_length}\n路径: {file_path}"

        # 生成长路径 - 使用更精确的计算
        segments = []
        current_total_len = base_len

        # 对于Windows 11 25H2，特别是300字符附近的问题，调整策略
        if is_windows_11_25h2 and target_length >= 280:
            # 减少层级，增加每层长度，避免路径过深
            max_segments = min(remaining_len // 120, 3)  # 最多3层，每层更长
            segment_length = remaining_len // max_segments if max_segments > 0 else 120
        elif is_windows_11:
            # 减少层级，增加每层长度
            max_segments = min(remaining_len // 100, 4)  # 最多4层
            segment_length = remaining_len // max_segments if max_segments > 0 else 100
        else:
            max_segments = remaining_len // 50  # 正常情况
            segment_length = 50

        segments_created = 0

        while (current_total_len < target_length - 50 and
               segments_created < max_segments and
               len(segments) < 100):  # 安全限制，最多100层

            # 计算这一层需要的长度
            remaining_needed = target_length - current_total_len - 50
            if remaining_needed <= 0:
                break

            # 这一层文件夹名的长度
            segment_len = min(remaining_needed, segment_length)
            if segment_len < 5:  # 最小长度
                break

            # 根据字符类型生成文件夹名
            folder_name = self._generate_name_with_types(segment_len, char_types)
            segments.append(folder_name)

            # 更新当前总长度（加上文件夹名和分隔符）
            current_total_len += len(folder_name) + 1  # +1 for path separator
            segments_created += 1

        # 构建完整路径
        for folder_name in segments:
            current_path = os.path.join(current_path, folder_name)

        # 使用安全的目录创建方法 - 对于Windows 11 25H2增加重试次数
        retry_for_dir = 4 if is_windows_11_25h2 and target_length >= 280 else 3
        try:
            self._create_directory_safe(current_path, retry_count=retry_for_dir)
        except Exception as e:
            # 如果失败，尝试创建简化版本
            try:
                # 缩短路径 - 特别处理Windows 11 25H2 300字符问题
                if len(current_path) > 250 and is_windows_11_25h2:
                    # 对于Windows 11 25H2长路径，尝试分段创建
                    path_parts = current_path.split(os.sep)
                    rebuild_path = path_parts[0] + os.sep

                    for i, part in enumerate(path_parts[1:], 1):
                        if i == len(path_parts) - 1 and len(part) > 60:
                            # 最后一层目录名太长，缩短
                            part = part[:40] + "_s"

                        rebuild_path = os.path.join(rebuild_path, part)
                        if not os.path.exists(rebuild_path):
                            try:
                                os.makedirs(rebuild_path, exist_ok=True)
                                # Windows 11 25H2特殊处理：添加延迟
                                if is_windows_11_25h2 and len(rebuild_path) >= 280:
                                    time.sleep(0.05)
                            except Exception as mkdir_error:
                                # 如果这一层创建失败，尝试创建替代名称
                                alt_part = part[:25] + "_a"
                                rebuild_path = os.path.join(os.path.dirname(rebuild_path), alt_part)
                                os.makedirs(rebuild_path, exist_ok=True)

                    current_path = rebuild_path
                else:
                    self._create_directory_safe(current_path, retry_count=retry_for_dir)
            except Exception as e2:
                # 这里需要更仔细的错误处理：先检查路径是否实际已经创建成功
                if os.path.exists(current_path):
                    print(f"⚠️ 目录创建报告失败，但路径实际存在: {current_path[:80]}...")
                    # 如果路径实际存在，我们继续执行而不是抛出异常
                else:
                    raise Exception(f"无法创建目录 '{current_path[:100]}...': {e2}")

        # 创建随机文件名和内容的文件
        file_name = self._generate_name_with_types(8, char_types) + ".txt"
        file_content = generate_random_content(100)
        file_path = os.path.join(current_path, file_name)

        # 对于Windows 11 25H2增加重试次数
        retry_for_file = 4 if is_windows_11_25h2 and len(file_path) >= 280 else 3
        try:
            self._create_file_safe(file_path, file_content, retry_count=retry_for_file)
        except Exception as e:
            # 特别处理Windows 11 25H2 300字符问题
            if is_windows_11_25h2 and len(file_path) >= 280 and len(file_path) <= 320:
                print(f"⚠️ Windows 11 25H2 300字符问题检测，尝试替代方案")

                # 首先检查文件是否已经创建成功
                if os.path.exists(file_path):
                    print(f"✅ 文件实际已存在，报告虚假失败: {file_path[:80]}...")
                    # 文件已经存在，继续执行
                else:
                    # 尝试缩短文件名
                    short_file_name = "file_s.txt"
                    short_file_path = os.path.join(current_path, short_file_name)

                    try:
                        self._create_file_safe(short_file_path, file_content, retry_count=3)
                        file_path = short_file_path
                        print(f"✅ 使用短文件名创建成功: {short_file_name}")
                    except Exception as short_error:
                        # 最后检查一次原始文件路径
                        if os.path.exists(file_path):
                            print(f"✅ 原始文件路径实际已存在，继续执行")
                        else:
                            raise Exception(f"Windows 11 25H2文件创建失败: {short_error}")
            else:
                raise Exception(f"无法创建文件 '{file_path[:100]}...': {e}")

        actual_length = len(file_path)

        # 获取使用的字符类型信息
        used_types = []
        if char_types.get('include_english'):
            used_types.append("英文")
        if char_types.get('include_chinese'):
            used_types.append("中文")
        if char_types.get('include_digits'):
            used_types.append("数字")
        if char_types.get('include_special'):
            used_types.append("特殊字符")
        if char_types.get('include_unicode'):
            used_types.append("Unicode")

        type_info = "、".join(used_types)

        # 构建结果消息 - 改进格式，确保路径信息完整
        result_msg = f"生成长路径成功!\n使用的字符类型: {type_info}\n目标长度: {target_length}\n实际路径长度: {actual_length}\n路径: {file_path}"

        # 添加系统长路径支持状态信息
        if not self.long_path_enabled:
            result_msg += f"\n⚠️ 系统长路径支持: 未启用 (最大路径长度限制为260字符)"
        else:
            result_msg += f"\n✅ 系统长路径支持: 已启用"

        if actual_length < target_length:
            result_msg += f"\n⚠️ 注意: 实际路径长度 ({actual_length}) 小于目标长度 ({target_length})"
        elif actual_length > 32767:
            result_msg += f"\n⚠️ 警告: 路径长度超过Windows最大限制 (32767字符)"

        # 添加操作系统兼容性信息
        result_msg += f"\n操作系统: {compat_info['specific_version']}"
        if is_windows_11:
            result_msg += f"\nWindows 11检测: 已应用兼容性优化"
        if is_windows_11_25h2:
            result_msg += "\n(已应用Windows 11 25H2兼容性优化，修复虚假失败报告问题)"

        return result_msg

    def _calculate_path_length(self, path):
        """计算路径长度"""
        return len(str(path))