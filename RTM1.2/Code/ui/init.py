"""
ui 模块初始化文件
"""

from .main_window import FileProcessTool
from .tab_widgets import (
    FileOpenTab, MultiLayerTab, LongPathTab,
    LargeFileTab, ProcessMemoryTab, DllInjectorTab,
    FilePermissionTab, HostModifyTab, FileChecksumTabWrapper,
    FileComparisonTabWrapper, TextGeneratorTab  # 添加这一行
)

__all__ = [
    'FileProcessTool',
    'FileOpenTab', 'MultiLayerTab', 'LongPathTab',
    'LargeFileTab', 'ProcessMemoryTab', 'DllInjectorTab',
    'FilePermissionTab', 'HostModifyTab', 'FileChecksumTabWrapper',
    'FileComparisonTabWrapper', 'TextGeneratorTab'  # 添加这一行
]