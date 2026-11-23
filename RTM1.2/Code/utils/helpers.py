"""
辅助函数
"""

import random
import string
import ctypes
import os


def generate_random_name(length=10):
    """生成包含特殊字符、中英文和数字的随机名称"""
    # 英文字符
    english_chars = string.ascii_letters
    # 数字
    digits = string.digits
    # 特殊字符 (Windows允许的文件名特殊字符)
    special_chars = '!@#$%^&()[]{}~-_=+.,;'
    # 中文字符
    chinese_chars = '测试文件文件夹路径生成功'

    all_chars = english_chars + digits + special_chars + chinese_chars
    return ''.join(random.choice(all_chars) for _ in range(length))


def generate_random_content(length=50):
    """生成随机内容"""
    return generate_random_name(length)


def is_admin():
    """检查是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def get_current_directory():
    """获取当前程序目录"""
    return os.path.dirname(os.path.abspath(__file__))