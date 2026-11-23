# Auto-generated init file

# 导入兼容性模块
from .windows_compat import WindowsCompatibility, windows_compat, safe_create_directory
from .file_operations import FileOperations
from .path_generator import PathGenerator
from .process_manager import ProcessManager
from .system_tools import SystemTools
from .dll_injector import DLLInjector
from .file_checksum import FileChecksumCalculator, FileChecksumTab
from .file_comparison import FileComparator, FileComparisonTab
from .text_generator import TextGenerator

__all__ = [
    'WindowsCompatibility',
    'windows_compat',
    'safe_create_directory',
    'FileOperations',
    'PathGenerator',
    'ProcessManager',
    'SystemTools',
    'DLLInjector',
    'FileChecksumCalculator',
    'FileChecksumTab',
    'FileComparator',
    'FileComparisonTab',
    'TextGenerator'
]