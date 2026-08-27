import os
import sys
import ctypes
import json
import re
import time
from datetime import datetime

import requests
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QRect, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPalette, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# PyInstaller --noconfirm --onefile --windowed --icon "icon.ico" --add-data "icon.ico;." "串口log过滤 - V15.0-调试.py"

version = "15.0"
Compilation_date = "2026-08-17 00:00:00"
LOG_FILE_MAX_BYTES = 200 * 1024 * 1024
LOG_FILE_SIZE_REFRESH_INTERVAL_MS = 60 * 1000
LOG_FILE_FIRST_SIZE_REFRESH_DELAY_MS = 5 * 1000
LOG_FILE_ROTATE_CHECK_INTERVAL_MS = 60 * 60 * 1000
WINDOWS_APP_ID = "RichLink.SerialPortTool.V15"
SEND_URL = "http://10.85.40.3:8088/client/send"
APP_DATA_DIR_NAME = "tool_data"
SERIAL_PARTIAL_LINE_FLUSH_MS = 300
FIXED_AT_DEFAULT_ROWS = 10
FIXED_AT_MAX_ROWS = 100
FIXED_AT_GROUP_COUNT = 5
FIXED_AT_COLLAPSED_WIDTH = 28
FIXED_AT_COMPACT_EXPANDED_WIDTH = 315
FIXED_AT_WIDE_EXPANDED_WIDTH = 360
FIXED_AT_WIDE_WINDOW_THRESHOLD = 1200
LOG_AUTO_SCROLL_MARGIN = 2
LOG_NORMAL_MAX_LINES = 3000
LOG_READING_MAX_LINES = 30000
AT_HISTORY_REMARK_DELIMITER = "-->"
AT_HISTORY_COMMAND_COLUMN_CHARS = 46


TEXTS = {
    "en": {
        "help": "Help",
        "modify": "Modify",
        "instructions": "Instructions",
        "about": "About",
        "setting": "Setting",
        "language": "Language",
        "english": "English",
        "chinese": "中文",
        "timestamp": "Timestamp",
        "show_timestamp": "Show Timestamp",
        "display_data": "Data Display",
        "display_text": "Text",
        "display_hex": "HEX",
        "port": "Port",
        "baud": "Baud",
        "refresh": "Refresh",
        "connect": "Connect",
        "disconnect": "Disconnect",
        "disconnected": "Disconnected",
        "connected_fmt": "Connected: {port} / {baudrate}",
        "connected_status_fmt": "Connected to {port} at {baudrate}",
        "filter": "Filter",
        "keyword": "Keyword",
        "regex": "Regex",
        "filter_keyword_placeholder": "Filter keywords, split by comma",
        "filter_regex_placeholder": "Regex filter, example: ERROR|FAIL|F10[23]",
        "save_filtered_only": "Save filtered only",
        "pause": "Pause",
        "resume": "Resume",
        "start_save": "Start Save",
        "stop_save": "Stop Save",
        "open_folder": "Open Folder",
        "manual_extend": "+",
        "manual_extend_tooltip": "Create a new extend log file now",
        "clear": "Clear",
        "at_commands": "AT Commands",
        "at_command_placeholder": "AT command, F102/F103, HEX bytes when HEX is checked, or command -->remark",
        "send": "Send",
        "send_with_enter": "Send with Enter",
        "hex": "HEX",
        "invalid_hex_title": "Invalid HEX",
        "invalid_hex_msg": "Please enter an even number of valid HEX characters, such as 01 03 0D 0A.",
        "fixed_at_commands": "Fixed AT Commands",
        "at_command_row_placeholder_fmt": "AT command {index}",
        "group_label_fmt": "G{index}",
        "expand": "Add",
        "delete": "Delete",
        "collapse": "Collapse",
        "fixed_at_max_reached_fmt": "Fixed AT rows reached the maximum: {count}",
        "fixed_at_min_reached_fmt": "Fixed AT rows keep at least {count} rows.",
        "no_empty_fixed_at_row": "Only an empty bottom row can be deleted.",
        "interval": "Interval",
        "count": "Count",
        "auto_send": "Auto Send",
        "stop_auto": "Stop Auto",
        "imei": "IMEI",
        "ready": "Ready",
        "language_switched": "Language switched",
        "ports_found_fmt": "{count} port(s) found",
        "no_serial_port": "No serial port found",
        "serial_setting_changed_fmt": "Serial setting changed to {port} / {baudrate}, reconnecting...",
        "no_command_selected_title": "No Command Selected",
        "no_command_selected_msg": "Please select at least one Fixed AT command.",
        "no_port_title": "No Port",
        "no_port_msg": "Please select a serial port.",
        "invalid_baud_title": "Invalid Baud Rate",
        "invalid_baud_msg": "The selected baud rate is not valid.",
        "save_log_title": "Save Log",
        "text_files_filter": "Text Files (*.txt);;All Files (*)",
        "auto_send_started": "Auto send started",
        "auto_sending": "Auto sending",
        "auto_send_stopped": "Auto send stopped",
        "auto_send_completed": "Auto send completed",
        "auto_send_failed": "Auto send stopped: send failed",
        "auto_send_serial_changed": "Auto send stopped: serial setting changed",
        "auto_send_serial_disconnected": "Auto send stopped: serial disconnected",
        "auto_send_serial_error": "Auto send stopped: serial error",
        "disconnected_auto_send_stopped": "Disconnected, auto send stopped",
        "serial_error_auto_send_stopped": "Serial error, auto send stopped",
        "serial_error": "Serial error",
        "display_resumed": "Display resumed",
        "display_paused": "Display paused",
        "display_paused_saving_fmt": "Display paused, saving continues: {file_name} | Size: {size}",
        "recording_fmt": "Recording log to {file_name} | Size: {size}",
        "stopped_saving_fmt": "Stopped saving log: {file_name}",
        "log_saving_stopped": "Log saving stopped",
        "log_display_cleared": "Log display cleared",
        "manual_extend_done_fmt": "Manual extend created: {file_name}",
        "manual_extend_unavailable": "Start saving before manual extend",
        "folder_not_found_title": "Folder Not Found",
        "folder_not_found_msg": "The log folder does not exist.",
        "missing_imei_title": "Missing IMEI",
        "missing_imei_msg": "F102/F103 data channel requires IMEI.",
        "invalid_imei_title": "Invalid IMEI",
        "invalid_imei_msg": "IMEI must be numeric.",
        "not_connected_title": "Not Connected",
        "not_connected_msg": "Please connect the serial port first.",
        "invalid_regex_fmt": "Invalid regex filter: {error}",
        "data_channel_failed_fmt": "Data channel send failed: {error}",
        "sent_log_fmt": "{timestamp} Sent[{channel}]: {command}",
        "log_label": "Log",
        "size_label": "Size",
    },
    "zh": {
        "help": "帮助",
        "modify": "修改说明",
        "instructions": "使用说明",
        "about": "关于",
        "setting": "设置",
        "language": "语言",
        "english": "English",
        "chinese": "中文",
        "timestamp": "时间戳",
        "show_timestamp": "显示时间戳",
        "display_data": "数据显示",
        "display_text": "文本",
        "display_hex": "HEX",
        "port": "端口",
        "baud": "波特率",
        "refresh": "刷新",
        "connect": "连接",
        "disconnect": "断开",
        "disconnected": "未连接",
        "connected_fmt": "已连接: {port} / {baudrate}",
        "connected_status_fmt": "已连接 {port}, 波特率 {baudrate}",
        "filter": "过滤",
        "keyword": "关键字",
        "regex": "正则",
        "filter_keyword_placeholder": "关键字过滤，多个关键字用英文逗号分隔",
        "filter_regex_placeholder": "正则过滤，例如: ERROR|FAIL|F10[23]",
        "save_filtered_only": "仅保存过滤结果",
        "pause": "暂停",
        "resume": "恢复",
        "start_save": "开始保存",
        "stop_save": "停止保存",
        "open_folder": "打开文件夹",
        "manual_extend": "+",
        "manual_extend_tooltip": "立即创建新的扩展日志文件",
        "clear": "清空",
        "at_commands": "AT 命令",
        "at_command_placeholder": "AT 命令、F102/F103；勾选 HEX 时发送 HEX 字节；可用 命令 -->备注",
        "send": "发送",
        "send_with_enter": "带回车换行",
        "hex": "HEX",
        "invalid_hex_title": "HEX 无效",
        "invalid_hex_msg": "请输入偶数个有效 HEX 字符，例如 01 03 0D 0A。",
        "fixed_at_commands": "固定 AT 命令",
        "at_command_row_placeholder_fmt": "AT 命令 {index}",
        "group_label_fmt": "组{index}",
        "expand": "增加",
        "delete": "删除",
        "collapse": "收起",
        "fixed_at_max_reached_fmt": "Fixed AT 已达到最大行数: {count}",
        "fixed_at_min_reached_fmt": "Fixed AT 至少保留 {count} 行。",
        "no_empty_fixed_at_row": "只能删除底部空白行。",
        "interval": "间隔",
        "count": "次数",
        "auto_send": "自动发送",
        "stop_auto": "停止自动",
        "imei": "IMEI",
        "ready": "就绪",
        "language_switched": "语言已切换",
        "ports_found_fmt": "找到 {count} 个端口",
        "no_serial_port": "未找到串口",
        "serial_setting_changed_fmt": "串口设置切换为 {port} / {baudrate}，正在重连...",
        "no_command_selected_title": "未选择命令",
        "no_command_selected_msg": "请至少勾选一条固定 AT 命令。",
        "no_port_title": "未选择端口",
        "no_port_msg": "请选择串口。",
        "invalid_baud_title": "波特率无效",
        "invalid_baud_msg": "当前选择的波特率无效。",
        "save_log_title": "保存日志",
        "text_files_filter": "文本文件 (*.txt);;所有文件 (*)",
        "auto_send_started": "自动发送已开始",
        "auto_sending": "自动发送中",
        "auto_send_stopped": "自动发送已停止",
        "auto_send_completed": "自动发送已完成",
        "auto_send_failed": "自动发送已停止: 发送失败",
        "auto_send_serial_changed": "自动发送已停止: 串口设置变化",
        "auto_send_serial_disconnected": "自动发送已停止: 串口断开",
        "auto_send_serial_error": "自动发送已停止: 串口错误",
        "disconnected_auto_send_stopped": "已断开，自动发送已停止",
        "serial_error_auto_send_stopped": "串口错误，自动发送已停止",
        "serial_error": "串口错误",
        "display_resumed": "显示已恢复",
        "display_paused": "显示已暂停",
        "display_paused_saving_fmt": "显示已暂停，日志继续保存: {file_name} | 大小: {size}",
        "recording_fmt": "正在保存日志到 {file_name} | 大小: {size}",
        "stopped_saving_fmt": "已停止保存日志: {file_name}",
        "log_saving_stopped": "日志保存已停止",
        "log_display_cleared": "日志显示已清空",
        "manual_extend_done_fmt": "已手动扩展到: {file_name}",
        "manual_extend_unavailable": "请先开始保存日志",
        "folder_not_found_title": "文件夹不存在",
        "folder_not_found_msg": "日志文件夹不存在。",
        "missing_imei_title": "缺少 IMEI",
        "missing_imei_msg": "F102/F103 数据通道需要填写 IMEI。",
        "invalid_imei_title": "IMEI 无效",
        "invalid_imei_msg": "IMEI 必须为数字。",
        "not_connected_title": "未连接",
        "not_connected_msg": "请先连接串口。",
        "invalid_regex_fmt": "正则表达式无效: {error}",
        "data_channel_failed_fmt": "数据通道发送失败: {error}",
        "sent_log_fmt": "{timestamp} 已发送[{channel}]: {command}",
        "log_label": "日志",
        "size_label": "大小",
    },
}


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def app_data_dir(create=False):
    data_dir = os.path.join(app_base_dir(), APP_DATA_DIR_NAME)
    if create:
        os.makedirs(data_dir, exist_ok=True)
    return data_dir


def ensure_parent_dir(file_path):
    folder = os.path.dirname(file_path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def format_log_timestamp():
    return "[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "]"


def split_at_history_entry(entry):
    text = (entry or "").replace("\r", "").replace("\n", "").strip()
    if AT_HISTORY_REMARK_DELIMITER not in text:
        return text, ""

    command, remark = text.split(AT_HISTORY_REMARK_DELIMITER, 1)
    return command.strip(), remark.strip()


def normalize_at_history_entry(entry):
    command, remark = split_at_history_entry(entry)
    if not command:
        return ""
    if remark:
        return f"{command} {AT_HISTORY_REMARK_DELIMITER}{remark}"
    return command


class ATCommandHistoryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        entry = index.data(Qt.UserRole) or index.data(Qt.DisplayRole) or ""
        command, remark = split_at_history_entry(entry)

        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        item_option.text = ""
        widget = item_option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, item_option, painter, widget)

        text_rect = item_option.rect.adjusted(6, 0, -6, 0)
        command_column_width = item_option.fontMetrics.horizontalAdvance(
            "W" * AT_HISTORY_COMMAND_COLUMN_CHARS
        )
        command_column_width = min(command_column_width, max(160, int(text_rect.width() * 0.68)))
        command_rect = QRect(text_rect.left(), text_rect.top(), command_column_width - 10, text_rect.height())
        remark_rect = QRect(
            text_rect.left() + command_column_width,
            text_rect.top(),
            max(0, text_rect.width() - command_column_width),
            text_rect.height(),
        )

        command_text = item_option.fontMetrics.elidedText(command, Qt.ElideRight, command_rect.width())
        painter.save()
        painter.setPen(item_option.palette.color(QPalette.Text))
        painter.drawText(command_rect, Qt.AlignVCenter | Qt.AlignLeft, command_text)

        if remark:
            remark_text = f"{AT_HISTORY_REMARK_DELIMITER}{remark}"
            remark_text = item_option.fontMetrics.elidedText(remark_text, Qt.ElideRight, remark_rect.width())
            painter.setPen(item_option.palette.color(QPalette.Mid))
            painter.drawText(remark_rect, Qt.AlignVCenter | Qt.AlignLeft, remark_text)
        painter.restore()


class SerialReader(QThread):
    """串口读取线程：后台读取串口数据，按行发送给主界面。"""

    data_received = pyqtSignal(str, str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.buffer = b""
        self.max_buffer_size = 10240
        self.last_buffer_update_time = None

    def decode_line(self, line_bytes):
        try:
            return line_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return line_bytes.decode("latin-1")

    def emit_line(self, line_bytes):
        line_bytes = line_bytes.strip(b"\r")
        text_line = self.decode_line(line_bytes).strip()
        if not text_line:
            return

        hex_line = " ".join(f"{byte:02X}" for byte in line_bytes)
        self.data_received.emit(format_log_timestamp(), text_line, hex_line)

    def run(self):
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.running = True

            while self.running:
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)

                    self.buffer += data
                    self.last_buffer_update_time = time.monotonic()
                    if len(self.buffer) > self.max_buffer_size:
                        self.buffer = self.buffer[-self.max_buffer_size:]

                    while b"\n" in self.buffer:
                        line, self.buffer = self.buffer.split(b"\n", 1)
                        self.emit_line(line)
                        if not self.buffer:
                            self.last_buffer_update_time = None
                else:
                    if self.buffer and self.last_buffer_update_time:
                        idle_ms = (time.monotonic() - self.last_buffer_update_time) * 1000
                        if idle_ms >= SERIAL_PARTIAL_LINE_FLUSH_MS:
                            line = self.buffer.strip()
                            self.buffer = b""
                            self.last_buffer_update_time = None
                            if line:
                                self.emit_line(line)
                            continue

                    self.msleep(10)

        except (serial.SerialException, OSError) as e:
            if self.running or self.serial is None:
                self.error_occurred.emit(str(e))

    def stop(self):
        self.running = False
        if self.serial and self.serial.is_open:
            self.serial.close()


class SerialPortTool(QWidget):
    """串口日志过滤工具主窗口。"""

    def __init__(self):
        super().__init__()
        self.serial_thread = None
        self.log_file = None
        self.data_dir = app_data_dir(create=False)
        self.history_file = os.path.join(self.data_dir, "at_command_history.txt")
        self.fixed_at_file = os.path.join(self.data_dir, "fixed_at_groups.json")
        self.legacy_fixed_at_file = os.path.join(self.data_dir, "fixed_at_commands.txt")
        self.language_file = os.path.join(self.data_dir, "language_setting.txt")
        self.last_log_dir_file = os.path.join(self.data_dir, "last_log_dir.txt")
        self.language = self.load_language_setting()
        self.show_timestamp = True
        self.display_hex_enabled = False
        self.max_log_lines = LOG_NORMAL_MAX_LINES
        self.log_reading_max_lines = LOG_READING_MAX_LINES
        self.last_log_dir = self.load_last_log_dir()
        self.last_baudrate = None
        self.last_port = ""
        self.is_paused = False
        self.refreshing_ports = False
        self.current_log_path = ""
        self.base_log_path = ""
        self.log_extend_index = 0
        self.current_log_size = 0
        self.log_size_timer = QTimer(self)
        self.log_size_timer.timeout.connect(self.refresh_log_file_size)
        self.log_first_size_timer = QTimer(self)
        self.log_first_size_timer.setSingleShot(True)
        self.log_first_size_timer.timeout.connect(self.refresh_log_file_size)
        self.log_rotate_timer = QTimer(self)
        self.log_rotate_timer.timeout.connect(self.check_log_file_size)
        self.updating_command_history = False
        self.fixed_at_rows = []
        self.fixed_at_groups = self.create_default_fixed_at_groups()
        self.current_fixed_at_group = 0
        self.fixed_at_group_buttons = []
        self.loading_fixed_at_commands = False
        self.auto_send_queue = []
        self.auto_send_index = 0
        self.auto_send_active = False
        self.auto_send_total = 0
        self.auto_send_success_count = 0
        self.auto_send_commands_per_round = 0
        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.timeout.connect(self.process_auto_send_next)
        self.last_regex_error = ""

        self.initUI()
        self.load_command_history()
        self.load_fixed_at_commands()

    def initUI(self):
        self.setWindowTitle("RichLink Serial Port Tool V" + version + " --Mangetic-20260817")
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setGeometry(420, 140, 1020, 720)
        self.setMinimumSize(860, 620)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 8, 10, 8)
        self.main_layout.setSpacing(8)
        self.setLayout(self.main_layout)

        self.build_menu()
        self.build_connection_bar()
        self.build_filter_bar()
        self.build_content_area()
        self.build_status_bar()
        self.apply_style()
        self.apply_language(show_status=False)
        self.refresh_ports()

    def tr_text(self, key, **kwargs):
        text = TEXTS.get(self.language, TEXTS["en"]).get(key, TEXTS["en"].get(key, key))
        return text.format(**kwargs) if kwargs else text

    def create_default_fixed_at_groups(self):
        return [
            {
                "name": f"Group {group_index + 1}",
                "rows": [
                    {"command": "", "checked": False}
                    for _ in range(FIXED_AT_DEFAULT_ROWS)
                ],
            }
            for group_index in range(FIXED_AT_GROUP_COUNT)
        ]

    def normalize_fixed_at_groups(self, groups):
        normalized_groups = []
        source_groups = groups if isinstance(groups, list) else []

        for group_index in range(FIXED_AT_GROUP_COUNT):
            source_group = source_groups[group_index] if group_index < len(source_groups) else {}
            source_rows = source_group.get("rows", []) if isinstance(source_group, dict) else []
            rows = []

            if isinstance(source_rows, list):
                for row in source_rows[:FIXED_AT_MAX_ROWS]:
                    if isinstance(row, dict):
                        rows.append(
                            {
                                "command": str(row.get("command", "")),
                                "checked": bool(row.get("checked", False)),
                            }
                        )
                    else:
                        rows.append({"command": str(row), "checked": False})

            while len(rows) < FIXED_AT_DEFAULT_ROWS:
                rows.append({"command": "", "checked": False})

            normalized_groups.append(
                {
                    "name": source_group.get("name", f"Group {group_index + 1}") if isinstance(source_group, dict) else f"Group {group_index + 1}",
                    "rows": rows,
                }
            )

        return normalized_groups

    def load_language_setting(self):
        if os.path.exists(self.language_file):
            try:
                with open(self.language_file, "r", encoding="utf-8") as file:
                    language = file.read().strip()
                    if language in TEXTS:
                        return language
            except OSError:
                pass
        return "en"

    def save_language_setting(self):
        try:
            ensure_parent_dir(self.language_file)
            with open(self.language_file, "w", encoding="utf-8") as file:
                file.write(self.language)
        except OSError:
            pass

    def load_last_log_dir(self):
        if os.path.exists(self.last_log_dir_file):
            try:
                with open(self.last_log_dir_file, "r", encoding="utf-8") as file:
                    folder = file.read().strip()
                    if folder and os.path.isdir(folder):
                        return folder
            except OSError:
                pass
        return ""

    def save_last_log_dir(self):
        if not self.last_log_dir:
            return

        try:
            ensure_parent_dir(self.last_log_dir_file)
            with open(self.last_log_dir_file, "w", encoding="utf-8") as file:
                file.write(self.last_log_dir)
        except OSError:
            pass

    def set_language(self, language):
        if language not in TEXTS:
            return

        self.language = language
        self.save_language_setting()
        self.apply_language(show_status=True)

    def toggle_timestamp_display(self):
        self.show_timestamp = self.timestamp_action.isChecked()

    def set_display_mode(self, mode):
        self.display_hex_enabled = mode == "hex"
        self.display_text_action.setChecked(not self.display_hex_enabled)
        self.display_hex_action.setChecked(self.display_hex_enabled)

    def apply_language(self, show_status=True):
        self.help_menu.setTitle(self.tr_text("help"))
        self.instructions_action.setText(self.tr_text("instructions"))
        self.about_action.setText(self.tr_text("about"))
        self.setting_menu.setTitle(self.tr_text("setting"))
        self.language_menu.setTitle(self.tr_text("language"))
        self.english_action.setText(self.tr_text("english"))
        self.chinese_action.setText(self.tr_text("chinese"))
        self.timestamp_action.setText(self.tr_text("show_timestamp"))
        self.display_data_menu.setTitle(self.tr_text("display_data"))
        self.display_text_action.setText(self.tr_text("display_text"))
        self.display_hex_action.setText(self.tr_text("display_hex"))
        self.english_action.setChecked(self.language == "en")
        self.chinese_action.setChecked(self.language == "zh")
        self.timestamp_action.setChecked(self.show_timestamp)
        self.display_text_action.setChecked(not self.display_hex_enabled)
        self.display_hex_action.setChecked(self.display_hex_enabled)

        self.port_label.setText(self.tr_text("port"))
        self.baud_label.setText(self.tr_text("baud"))
        self.refresh_button.setText(self.tr_text("refresh"))
        self.connect_button.setText(self.tr_text("connect"))
        self.disconnect_button.setText(self.tr_text("disconnect"))
        self.filter_label.setText(self.tr_text("filter"))
        self.filter_mode_combo.setItemText(0, self.tr_text("keyword"))
        self.filter_mode_combo.setItemText(1, self.tr_text("regex"))
        self.save_filtered_checkbox.setText(self.tr_text("save_filtered_only"))
        self.pause_button.setText(self.tr_text("resume") if self.is_paused else self.tr_text("pause"))
        self.set_save_active(bool(self.log_file))
        self.manual_extend_button.setText(self.tr_text("manual_extend"))
        self.manual_extend_button.setToolTip(self.tr_text("manual_extend_tooltip"))
        self.open_log_folder_button.setText(self.tr_text("open_folder"))
        self.clear_button.setText(self.tr_text("clear"))
        self.command_group.setTitle(self.tr_text("at_commands"))
        self.command_input.setPlaceholderText(self.tr_text("at_command_placeholder"))
        self.send_button.setText(self.tr_text("send"))
        self.newline_checkbox.setText(self.tr_text("send_with_enter"))
        self.hex_checkbox.setText(self.tr_text("hex"))
        self.fixed_at_group.setTitle(self.tr_text("fixed_at_commands"))
        self.side_button.setText("》" if self.scroll_area.isVisible() else "+\n+\n+")
        self.expand_fixed_at_button.setText(self.tr_text("expand"))
        self.delete_fixed_at_button.setText(self.tr_text("delete"))
        self.interval_label.setText(self.tr_text("interval"))
        self.count_label.setText(self.tr_text("count"))
        self.auto_send_button.setText(self.tr_text("stop_auto") if self.auto_send_active else self.tr_text("auto_send"))
        self.imei_input.setPlaceholderText(self.tr_text("imei"))
        self.imei_label.setText(self.tr_text("imei"))
        self.update_filter_placeholder()

        for i, row in enumerate(self.fixed_at_rows, 1):
            row["input"].setPlaceholderText(self.tr_text("at_command_row_placeholder_fmt", index=i))
            row["send_button"].setText(self.tr_text("send"))

        self.update_fixed_at_group_buttons()

        if self.is_serial_connected():
            port = self.get_selected_port()
            baudrate = self.baudrate_combo.currentText().strip()
            self.connection_label.setText(self.tr_text("connected_fmt", port=port, baudrate=baudrate))
        else:
            self.connection_label.setText(self.tr_text("disconnected"))

        if show_status:
            self.set_status(self.tr_text("language_switched"))

    def build_menu(self):
        menu_bar = QMenuBar(self)
        self.help_menu = QMenu("Help", self)
        self.setting_menu = QMenu("Setting", self)

        self.instructions_action = QAction("Instructions", self)
        self.about_action = QAction("About", self)
        self.language_menu = QMenu("Language", self)
        self.english_action = QAction("English", self)
        self.chinese_action = QAction("中文", self)
        self.timestamp_action = QAction("Show Timestamp", self)
        self.timestamp_action.setCheckable(True)
        self.display_data_menu = QMenu("Data Display", self)
        self.display_mode_group = QActionGroup(self)
        self.display_text_action = QAction("Text", self)
        self.display_text_action.setCheckable(True)
        self.display_hex_action = QAction("HEX", self)
        self.display_hex_action.setCheckable(True)
        self.display_mode_group.addAction(self.display_text_action)
        self.display_mode_group.addAction(self.display_hex_action)
        self.english_action.setCheckable(True)
        self.chinese_action.setCheckable(True)

        self.instructions_action.triggered.connect(self.show_instructions)
        self.about_action.triggered.connect(self.show_about)
        self.english_action.triggered.connect(lambda _checked=False: self.set_language("en"))
        self.chinese_action.triggered.connect(lambda _checked=False: self.set_language("zh"))
        self.timestamp_action.triggered.connect(lambda _checked=False: self.toggle_timestamp_display())
        self.display_text_action.triggered.connect(lambda _checked=False: self.set_display_mode("text"))
        self.display_hex_action.triggered.connect(lambda _checked=False: self.set_display_mode("hex"))

        self.language_menu.addAction(self.english_action)
        self.language_menu.addAction(self.chinese_action)
        self.setting_menu.addMenu(self.language_menu)
        self.setting_menu.addAction(self.timestamp_action)
        self.display_data_menu.addAction(self.display_text_action)
        self.display_data_menu.addAction(self.display_hex_action)
        self.setting_menu.addMenu(self.display_data_menu)
        self.help_menu.addAction(self.instructions_action)
        self.help_menu.addAction(self.about_action)
        menu_bar.addMenu(self.help_menu)
        menu_bar.addMenu(self.setting_menu)
        self.main_layout.setMenuBar(menu_bar)

    def build_connection_bar(self):
        connection_panel = QFrame()
        connection_panel.setObjectName("topPanel")

        connection_layout = QHBoxLayout()
        connection_layout.setContentsMargins(10, 8, 10, 8)
        connection_layout.setSpacing(8)

        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(220)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setFixedWidth(78)

        self.baudrate_combo = QComboBox()
        self.baudrate_combo.setFixedWidth(110)
        self.baudrate_combo.addItems(["115200", "9600", "19200", "38400", "57600", "460800", "921600"])

        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)

        self.connection_label = QLabel("Disconnected")
        self.connection_label.setObjectName("connectionLabel")

        self.port_label = QLabel("Port")
        self.baud_label = QLabel("Baud")

        connection_layout.addWidget(self.port_label)
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(self.refresh_button)
        connection_layout.addSpacing(10)
        connection_layout.addWidget(self.baud_label)
        connection_layout.addWidget(self.baudrate_combo)
        connection_layout.addSpacing(10)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)
        connection_layout.addStretch(1)
        connection_layout.addWidget(self.connection_label)

        connection_panel.setLayout(connection_layout)
        self.main_layout.addWidget(connection_panel)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.connect_serial)
        self.disconnect_button.clicked.connect(self.disconnect_serial)
        self.port_combo.currentIndexChanged.connect(self.handle_serial_settings_changed)
        self.baudrate_combo.currentIndexChanged.connect(self.handle_serial_settings_changed)

    def build_filter_bar(self):
        filter_panel = QFrame()
        filter_panel.setObjectName("filterPanel")

        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter keywords, split by comma")

        self.filter_mode_combo = QComboBox()
        self.filter_mode_combo.setFixedWidth(96)
        self.filter_mode_combo.addItem("Keyword", "keyword")
        self.filter_mode_combo.addItem("Regex", "regex")
        self.save_filtered_checkbox = QCheckBox("Save filtered only")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setCheckable(True)

        self.save_button = QPushButton("Start Save")
        self.save_button.setProperty("recording", False)
        self.manual_extend_button = QPushButton("+")
        self.manual_extend_button.setFixedWidth(28)
        self.manual_extend_button.setEnabled(False)
        self.open_log_folder_button = QPushButton("Open Folder")
        self.open_log_folder_button.setEnabled(False)
        self.clear_button = QPushButton("Clear")

        self.filter_label = QLabel("Filter")

        filter_layout.addWidget(self.filter_label)
        filter_layout.addWidget(self.filter_mode_combo)
        filter_layout.addWidget(self.filter_input, 1)
        filter_layout.addWidget(self.save_filtered_checkbox)
        filter_layout.addWidget(self.pause_button)
        filter_layout.addWidget(self.save_button)
        filter_layout.addWidget(self.manual_extend_button)
        filter_layout.addWidget(self.open_log_folder_button)
        filter_layout.addWidget(self.clear_button)

        filter_panel.setLayout(filter_layout)
        self.main_layout.addWidget(filter_panel)

        self.pause_button.toggled.connect(self.toggle_pause)
        self.save_button.clicked.connect(self.toggle_save_log)
        self.manual_extend_button.clicked.connect(self.manual_extend_log_file)
        self.open_log_folder_button.clicked.connect(self.open_log_folder)
        self.clear_button.clicked.connect(self.clear_log)
        self.filter_mode_combo.currentIndexChanged.connect(self.update_filter_placeholder)

    def update_filter_placeholder(self):
        if self.filter_mode_combo.currentData() == "regex":
            self.filter_input.setPlaceholderText(self.tr_text("filter_regex_placeholder"))
        else:
            self.filter_input.setPlaceholderText(self.tr_text("filter_keyword_placeholder"))

    def build_content_area(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_panel.setLayout(left_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.document().setMaximumBlockCount(self.max_log_lines)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.zoomIn = lambda *args, **kwargs: None
        self.log_text.zoomOut = lambda *args, **kwargs: None
        self.log_text.verticalScrollBar().valueChanged.connect(self.update_log_line_limit_for_scroll)
        left_layout.addWidget(self.log_text, 1)

        self.command_group = QGroupBox("AT Commands")
        command_layout = QVBoxLayout()
        command_layout.setSpacing(6)

        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText(self.tr_text("at_command_placeholder"))
        self.send_button = QPushButton("Send")
        self.newline_checkbox = QCheckBox("Send with Enter")
        self.newline_checkbox.setChecked(True)
        self.hex_checkbox = QCheckBox("HEX")
        self.hex_checkbox.setChecked(False)

        command_input_layout.addWidget(self.command_input, 1)
        command_input_layout.addWidget(self.send_button)
        command_input_layout.addWidget(self.hex_checkbox)
        command_input_layout.addWidget(self.newline_checkbox)

        self.command_history_combo = QComboBox()
        self.command_history_combo.setEditable(False)
        self.command_history_combo.setItemDelegate(ATCommandHistoryDelegate(self.command_history_combo))
        self.command_history_combo.view().setTextElideMode(Qt.ElideNone)
        self.command_history_combo.currentIndexChanged.connect(self.load_selected_command)
        self.command_history_combo.activated.connect(self.load_selected_command)

        command_layout.addLayout(command_input_layout)
        command_layout.addWidget(self.command_history_combo)
        self.command_group.setLayout(command_layout)
        left_layout.addWidget(self.command_group)

        self.side_button = QPushButton("+\n+\n+")
        self.side_button.setFixedWidth(24)
        self.side_button.setObjectName("sideToggleButton")
        self.side_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.side_button.clicked.connect(self.toggle_fixed_at_commands)

        self.fixed_at_group = QGroupBox("Fixed AT Commands")
        fixed_at_layout = QVBoxLayout()
        fixed_at_layout.setSpacing(4)
        fixed_at_layout.setContentsMargins(6, 6, 6, 6)
        fixed_at_layout.setAlignment(Qt.AlignTop)
        self.fixed_at_inputs = []

        self.fixed_at_rows_layout = QVBoxLayout()
        self.fixed_at_rows_layout.setSpacing(2)
        self.fixed_at_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.fixed_at_rows_layout.setAlignment(Qt.AlignTop)

        group_buttons_layout = QHBoxLayout()
        group_buttons_layout.setSpacing(3)
        self.fixed_at_group_buttons = []
        for group_index in range(FIXED_AT_GROUP_COUNT):
            group_button = QPushButton()
            group_button.setCheckable(True)
            group_button.setFixedHeight(26)
            group_button.clicked.connect(lambda _, index=group_index: self.switch_fixed_at_group(index))
            group_buttons_layout.addWidget(group_button)
            self.fixed_at_group_buttons.append(group_button)
        fixed_at_layout.addLayout(group_buttons_layout)
        fixed_at_layout.addLayout(self.fixed_at_rows_layout)

        auto_settings_layout = QHBoxLayout()
        auto_settings_layout.setSpacing(3)
        self.auto_interval_spin = QSpinBox()
        self.auto_interval_spin.setRange(100, 3600000)
        self.auto_interval_spin.setSingleStep(100)
        self.auto_interval_spin.setValue(1000)
        self.auto_interval_spin.setFixedWidth(86)
        self.auto_count_spin = QSpinBox()
        self.auto_count_spin.setRange(1, 9999)
        self.auto_count_spin.setValue(1)
        self.auto_count_spin.setFixedWidth(72)
        self.interval_label = QLabel("Interval")
        self.ms_label = QLabel("ms")
        self.count_label = QLabel("Count")

        auto_settings_layout.addWidget(self.interval_label)
        auto_settings_layout.addWidget(self.auto_interval_spin)
        auto_settings_layout.addWidget(self.ms_label)
        auto_settings_layout.addSpacing(10)
        auto_settings_layout.addWidget(self.count_label)
        auto_settings_layout.addWidget(self.auto_count_spin)
        auto_settings_layout.addStretch(1)

        auto_send_layout = QHBoxLayout()
        auto_send_layout.setSpacing(4)
        self.expand_fixed_at_button = QPushButton("Add")
        self.expand_fixed_at_button.setFixedHeight(28)
        self.expand_fixed_at_button.setFixedWidth(58)
        self.delete_fixed_at_button = QPushButton("Delete")
        self.delete_fixed_at_button.setFixedHeight(28)
        self.delete_fixed_at_button.setFixedWidth(58)
        self.auto_send_button = QPushButton("Auto Send")
        self.auto_send_button.setObjectName("autoSendButton")
        self.auto_send_button.setProperty("running", False)
        auto_send_layout.addWidget(self.expand_fixed_at_button)
        auto_send_layout.addWidget(self.delete_fixed_at_button)
        auto_send_layout.addSpacing(12)
        auto_send_layout.addWidget(self.auto_send_button)
        auto_send_layout.addStretch(1)

        fixed_at_layout.addLayout(auto_settings_layout)
        fixed_at_layout.addLayout(auto_send_layout)

        imei_layout = QHBoxLayout()
        imei_layout.setSpacing(4)
        self.imei_input = QLineEdit()
        self.imei_input.setPlaceholderText("IMEI")
        self.imei_label = QLabel("IMEI")
        imei_layout.addWidget(self.imei_label)
        imei_layout.addWidget(self.imei_input, 1)
        fixed_at_layout.addLayout(imei_layout)

        self.fixed_at_group.setLayout(fixed_at_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.fixed_at_group)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setMinimumWidth(FIXED_AT_COMPACT_EXPANDED_WIDTH - FIXED_AT_COLLAPSED_WIDTH - 6)
        self.scroll_area.setVisible(False)

        right_panel = QWidget()
        right_layout = QHBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.side_button)
        right_layout.addWidget(self.scroll_area, 1)
        right_panel.setLayout(right_layout)
        right_panel.setMinimumWidth(FIXED_AT_COLLAPSED_WIDTH)
        right_panel.setMaximumWidth(FIXED_AT_COLLAPSED_WIDTH)
        self.fixed_at_panel_shell = right_panel

        self.content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(left_panel)
        self.content_splitter.addWidget(right_panel)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 0)
        self.content_splitter.setSizes([992, FIXED_AT_COLLAPSED_WIDTH])
        self.main_layout.addWidget(self.content_splitter, 1)

        self.send_button.clicked.connect(self.send_command)
        self.command_input.returnPressed.connect(self.send_command)
        self.command_input.textChanged.connect(lambda _text: self.update_command_color(self.command_input))
        self.expand_fixed_at_button.clicked.connect(self.expand_fixed_at_rows)
        self.delete_fixed_at_button.clicked.connect(self.delete_empty_fixed_at_row)
        self.auto_send_button.clicked.connect(self.toggle_auto_send)

    def build_status_bar(self):
        self.status_label = QLabel(self.tr_text("ready"))
        self.status_label.setObjectName("statusLabel")
        self.main_layout.addWidget(self.status_label)

    def apply_style(self):
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 10pt;
            }
            QLineEdit, QComboBox, QTextEdit {
                border: 1px solid #b8c0cc;
                border-radius: 4px;
                padding: 4px;
                background: #ffffff;
            }
            QTextEdit {
                background: #fbfcfe;
                border-color: #b8c0cc;
            }
            QLabel, QCheckBox {
                background: transparent;
            }
            QPushButton {
                border: 1px solid #9aa7b7;
                border-radius: 4px;
                padding: 5px 10px;
                background: #f4f7fb;
            }
            QPushButton:hover {
                background: #e6eef8;
            }
            QPushButton#sideToggleButton {
                padding: 0px;
                font-weight: 700;
            }
            QPushButton:pressed {
                background: #d9e5f2;
            }
            QPushButton:checked {
                background: #ffe9ba;
                border-color: #d39a25;
            }
            QPushButton[recording="true"] {
                color: #0f5132;
                background: #dff3e8;
                border-color: #2e9d69;
                font-weight: 600;
            }
            QPushButton#autoSendButton {
                color: #15406f;
                background: #dcecff;
                border-color: #6fa4d8;
                font-weight: 600;
            }
            QPushButton#autoSendButton:hover {
                background: #cfe4fb;
            }
            QPushButton#autoSendButton[running="true"] {
                color: #7a3d00;
                background: #ffe2b8;
                border-color: #d28a2e;
                font-weight: 700;
            }
            QPushButton[fixedGroupActive="true"] {
                color: #0f3f74;
                background: #dcecff;
                border-color: #5f9dd7;
                font-weight: 700;
            }
            QPushButton:disabled {
                color: #98a3ad;
                background: #e9eef2;
                border-color: #c6d0d8;
            }
            QSplitter::handle {
                background: #d6dde7;
            }
            QSplitter::handle:hover {
                background: #b7c4d5;
            }
            QSpinBox:disabled {
                color: #26384d;
                background: #f7fbff;
                border-color: #aebdcc;
            }
            QGroupBox {
                border: 1px solid #c8d0da;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QLabel#connectionLabel {
                color: #5a6573;
                font-weight: 600;
            }
            QLabel#statusLabel {
                color: #66717f;
                padding: 2px 0;
                background: transparent;
            }
            """
        )

    def show_modify(self):
        if self.language == "zh":
            modify_text = (
                "V 10.0\n"
                "1. 优化长时间日志显示和串口读取缓存压力。\n"
                "2. 完善基础日志过滤、保存和串口命令发送流程。\n"
                "\nV 11.0\n"
                "1. 重构主界面布局：连接栏、过滤/保存栏、日志区、AT 命令区和右侧 Fixed AT 面板。\n"
                "2. 增加 Start Save / Stop Save 状态、Open Folder 按钮和更清晰的底部状态提示。\n"
                "3. Pause 只冻结界面显示，日志保存继续进行。\n"
                "4. 日志保存使用 append 持续写入，避免外部清空文件后产生空字节。\n"
                "5. 增加日志分卷：单文件超过 200MB 后扩展为 -extend-N。\n"
                "6. 定时刷新保存日志大小，并重新打开文件句柄，便于 Windows 更新文件大小。\n"
                "7. 增加 Windows AppUserModelID，并沿用 icon.ico 作为窗口和任务栏图标。\n"
                "\nV 12.0 --Mangetic-20260716\n"
                "1. Filter 增加 Keyword / Regex 模式下拉框，Keyword 支持逗号分隔，Regex 支持正则表达式。\n"
                "2. F102/F103 命令走 8088 数据通道，其他命令继续走串口通道。\n"
                "3. F102/F103 命令不追加回车换行，输入框以 F102/F103 开头时显示蓝色。\n"
                "4. Fixed AT 默认 10 行，每行增加勾选框。\n"
                "5. Auto Send 支持毫秒级间隔、发送次数、实时进度、成功计数和失败停止。\n"
                "6. 断开串口、切换串口设置或串口错误时自动停止 Auto Send。\n"
                "7. 日志保存中，底部状态始终保留当前日志文件名和大小。\n"
                "8. 保存日志大小每 1 分钟刷新；200MB 分卷检查每 1 小时执行一次。\n"
                "\nV 13.0\n"
                "1. 增加 Setting 菜单，Language 放入 Setting 内，可在 English / 中文之间切换。\n"
                "2. 主界面按钮、标签、输入提示、常用弹窗和状态栏提示支持即时切换。\n"
                "3. 语言选择保存到 tool_data/language_setting.txt，下次打开自动沿用。\n"
                "4. 工具运行数据统一保存到同目录 tool_data 文件夹，避免和 EXE 放在一起显得杂乱。\n"
                "\nV 14.0 --Mangetic-20260803\n"
                "1. Fixed AT 右侧面板支持鼠标拖动调整宽度，并随窗口大小在 315/360 宽度之间切换。\n"
                "2. Fixed AT 增加 5 个分组，每组独立保存命令、勾选状态和行数。\n"
                "3. Fixed AT 支持增加/删除空白底部行，默认 10 行，最大 100 行。\n"
                "4. Auto Send 只执行当前分组中已勾选的命令。\n"
                "5. 底部 AT Commands 增加 HEX 勾选发送，仅影响底部命令输入框，不影响 Fixed AT。\n"
                "6. 日志区支持手动拖动查看历史日志；新日志继续追加和保存，但不会强制跳到底部。\n"
                "7. 日志显示默认轻量保留 3000 行，手动查看历史时扩展到 30000 行，回到底部后恢复轻量裁剪。\n"
                "8. Setting 增加时间戳显示开关和 Text / HEX 数据显示模式；HEX 模式下 UI 和保存文件均按 HEX 输出。\n"
                "9. 串口下拉框支持显示 COM 全名，并按 COM 号优先展示。\n"
                "\nV 15.0 --Mangetic-20260817\n"
                "1. 底部 AT 命令历史支持备注格式：命令 -->备注。\n"
                "2. 历史下拉框按命令列和备注列对齐显示；选择历史项时只回填命令部分。\n"
                "3. 实际发送只使用 --> 前面的命令，备注不会发送到串口、HEX 或 F102/F103 数据通道。\n"
                "4. 修复工具刚打开后，下拉框第一条历史命令需要先选其他项才能回填的问题。\n"
                "5. 开始保存日志后增加 5 秒单次大小刷新，之后仍保持 1 分钟常规刷新。\n"
            )
        else:
            modify_text = (
                "V 10.0\n"
                "1. Optimize long-running log display and reduce serial read buffer pressure.\n"
                "2. Improve basic log filtering, saving, and serial command workflows.\n"
                "\nV 11.0\n"
                "1. Rebuild the main UI layout: connection bar, filter/save bar, log view, AT command area, and right Fixed AT panel.\n"
                "2. Add Start Save / Stop Save state, Open Folder button, and clearer bottom status messages.\n"
                "3. Pause only freezes the display; log saving continues in the background.\n"
                "4. Save log in append mode to avoid empty-byte issues after external file clearing.\n"
                "5. Add log file rotation: files larger than 200MB are extended as -extend-N.\n"
                "6. Refresh saved log file size periodically and reopen the file handle to help Windows update file size.\n"
                "7. Add Windows AppUserModelID and keep icon.ico for window/taskbar icon.\n"
                "\nV 12.0 --Mangetic-20260716\n"
                "1. Add Keyword / Regex filter mode dropdown. Keyword uses comma separation; Regex uses regular-expression syntax such as ERROR|FAIL.\n"
                "2. Add F102/F103 data-channel routing through the 8088 API; other commands continue to use the serial channel.\n"
                "3. F102/F103 commands do not append CR/LF, and AT inputs turn blue when they start with F102/F103.\n"
                "4. Fixed AT panel uses 10 compact default rows with per-row selection checkboxes.\n"
                "5. Auto Send supports millisecond interval, repeat count, real-time progress, success count, and failure stop handling.\n"
                "6. Disconnect, serial setting changes, or serial errors automatically stop Auto Send.\n"
                "7. Bottom status always keeps current saved log file name and size when logging is active.\n"
                "8. Saved log size refresh runs every 1 minute; 200MB rotation check runs every 1 hour.\n"
                "\nV 13.0\n"
                "1. Add Setting menu and move Language into Setting for English / Chinese switching.\n"
                "2. Main buttons, labels, placeholders, common dialogs, and status messages can switch immediately.\n"
                "3. Language selection is saved to tool_data/language_setting.txt and restored on next launch.\n"
                "4. Runtime data files are stored under the tool_data folder beside the executable to keep the EXE folder clean.\n"
                "\nV 14.0 --Mangetic-20260803\n"
                "1. The Fixed AT right panel can be resized with the mouse and adapts between 315/360 width by window size.\n"
                "2. Fixed AT adds 5 groups. Each group saves its own commands, check states, and row count.\n"
                "3. Fixed AT supports Add/Delete for empty bottom rows, default 10 rows, maximum 100 rows.\n"
                "4. Auto Send only runs checked commands in the current Fixed AT group.\n"
                "5. Bottom AT Commands adds optional HEX sending; it only affects the bottom command input, not Fixed AT.\n"
                "6. The log view no longer forces auto-scroll when the user scrolls up; new logs still append and save normally.\n"
                "7. Log display keeps 3000 lines in normal mode, expands to 30000 while reading history, and returns to light trimming at the bottom.\n"
                "8. Setting adds timestamp display and Text / HEX data display mode. HEX display writes both UI and saved logs as HEX.\n"
                "9. The Port dropdown supports full Windows COM names and shows the COM number first.\n"
                "\nV 15.0 --Mangetic-20260817\n"
                "1. Bottom AT command history supports command remarks with the format: command -->remark.\n"
                "2. The history dropdown displays command and remark in aligned columns; selecting a history item only fills the command part.\n"
                "3. Sending still uses only the command before -->, so remarks are not sent to serial, HEX, or F102/F103 data channel.\n"
                "4. Fix the first history item not filling the AT command input after the tool starts.\n"
                "5. Add a one-shot log size refresh 5 seconds after saving starts, then keep the normal 1-minute refresh interval.\n"
            )

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(modify_text)
        text_edit.setFixedWidth(620)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_text("modify"))
        dialog_layout = QVBoxLayout()
        dialog_layout.addWidget(text_edit)
        dialog.setLayout(dialog_layout)
        dialog.exec_()

    def show_instructions(self):
        if self.language == "zh":
            instructions_text = (
                "使用说明:\n\n"
                "1. 点击 Refresh 刷新当前可用串口，选择 Port 和 Baud 后点击 Connect 连接。\n"
                "2. Filter 支持 Keyword 和 Regex。Keyword 多个关键字用英文逗号分隔；Regex 可使用 ERROR|FAIL 这类正则表达式。\n"
                "3. Start Save 开始保存日志，Stop Save 停止保存；Open Folder 可打开当前日志所在文件夹。\n"
                "4. 保存日志时，单个文件超过 200MB 后会自动生成 -extend-N 分卷；点击 + 可手动立即分卷。\n"
                "5. Pause 只冻结界面显示，不影响日志文件持续保存。拖动日志滚动条查看历史日志时，新日志仍会追加和保存，但界面不会强制跳到底部。\n"
                "6. 底部 AT Commands 可发送普通 AT 或 F102/F103 命令；勾选 Send with Enter 会追加 CR/LF。\n"
                "7. 底部 AT Commands 勾选 HEX 后，会把输入内容按 HEX 字节发送，例如 01 03 0D 0A；HEX 只影响底部输入框，不影响右侧 Fixed AT。\n"
                "8. F102/F103 命令会走数据通道，需要填写 IMEI，且不会追加回车换行。\n"
                "9. 右侧 Fixed AT 点击 +++ 展开，点击 》 收起；展开后可以拖动宽度。\n"
                "10. Fixed AT 支持 G1-G5 五个分组，每组独立保存命令、勾选状态和行数。\n"
                "11. Fixed AT 的 Add 可增加命令行，Delete 只会删除底部空白行；默认 10 行，最大 100 行。\n"
                "12. Auto Send 只发送当前分组中已勾选的命令，可设置 Interval(ms) 和 Count。\n"
                "13. Setting > Language 可切换 English / 中文，切换后立即生效。\n"
                "14. Setting > Show Timestamp 可临时关闭/开启时间戳；该设置不保存，下次打开默认开启。\n"
                "15. Setting > Data Display 可在 Text / HEX 显示之间切换；HEX 模式下 UI 和保存文件都按 HEX 输出，该设置不保存。\n"
            )
        else:
            instructions_text = (
                "Instructions:\n\n"
                "1. Click Refresh to update available serial ports, select Port and Baud, then click Connect.\n"
                "2. Filter supports Keyword and Regex. Keyword uses commas; Regex can use expressions such as ERROR|FAIL.\n"
                "3. Start Save begins log saving, Stop Save stops it, and Open Folder opens the current log folder.\n"
                "4. Saved logs rotate automatically as -extend-N after one file exceeds 200MB; click + to extend manually.\n"
                "5. Pause only freezes display; log saving continues. When you scroll up to read history, new logs still append and save but the view will not force-scroll to the bottom.\n"
                "6. Bottom AT Commands can send normal AT or F102/F103 commands; Send with Enter appends CR/LF.\n"
                "7. When HEX is checked in bottom AT Commands, input is sent as HEX bytes, for example 01 03 0D 0A. HEX only affects the bottom input, not Fixed AT.\n"
                "8. F102/F103 commands use the data channel, require IMEI, and do not append CR/LF.\n"
                "9. Open the right Fixed AT panel with +++ and close it with 》; the panel width can be resized.\n"
                "10. Fixed AT supports G1-G5 groups. Each group saves its own commands, check states, and row count.\n"
                "11. Fixed AT Add inserts command rows; Delete only removes an empty bottom row. Default is 10 rows, maximum is 100 rows.\n"
                "12. Auto Send only sends checked commands in the current group, using Interval(ms) and Count.\n"
                "13. Use Setting > Language to switch between English and Chinese immediately.\n"
                "14. Setting > Show Timestamp temporarily toggles timestamps. It is not saved and defaults to enabled next launch.\n"
                "15. Setting > Data Display switches Text / HEX display. HEX mode writes both UI and saved logs as HEX and is not saved.\n"
            )
        QMessageBox.information(self, self.tr_text("instructions"), instructions_text)

    def show_about(self):
        about_text = (
            "<div style='text-align: left;'>"
            "Rich link Serial Port Tool<br><br>"
            "Version " + version + "<br><br>"
            "Developed by Mangetic<br><br>"
            "Compilation date " + Compilation_date +
            "</div>"
        )
        QMessageBox.about(self, self.tr_text("about"), about_text)

    def refresh_ports(self):
        current_port = self.get_selected_port()
        ports = list(serial.tools.list_ports.comports())
        port_items = [self.format_port_item(port) for port in ports]

        self.refreshing_ports = True
        self.port_combo.clear()
        for item_text, device_name in port_items:
            self.port_combo.addItem(item_text, device_name)
        if current_port:
            index = self.port_combo.findData(current_port)
            if index != -1:
                self.port_combo.setCurrentIndex(index)
        self.refreshing_ports = False

        if port_items:
            self.set_status(self.tr_text("ports_found_fmt", count=len(port_items)))
        else:
            self.set_status(self.tr_text("no_serial_port"))

    def format_port_item(self, port_info):
        device = getattr(port_info, "device", "") or ""
        description = getattr(port_info, "description", "") or ""
        if description and device and description != device:
            clean_description = description
            if clean_description.endswith(f"({device})"):
                clean_description = clean_description[: -len(f"({device})")].strip()
            return f"{device} - {clean_description}", device
        return device, device

    def get_selected_port(self):
        selected_data = self.port_combo.currentData()
        if selected_data:
            return str(selected_data).strip()
        return self.port_combo.currentText().strip()

    def handle_serial_settings_changed(self):
        if self.refreshing_ports:
            return

        if not self.is_serial_connected():
            return

        port = self.get_selected_port()
        baudrate = self.baudrate_combo.currentText()
        if port == self.last_port and baudrate == str(self.last_baudrate):
            return

        if self.auto_send_active:
            self.stop_auto_send(self.tr_text("auto_send_serial_changed"))

        self.append_info(self.tr_text("serial_setting_changed_fmt", port=port, baudrate=baudrate))
        self.disconnect_serial(show_status=False)
        self.connect_serial()

    def add_fixed_at_row(self, checked=False, command="", save=True):
        if len(self.fixed_at_rows) >= FIXED_AT_MAX_ROWS:
            self.set_status(self.tr_text("fixed_at_max_reached_fmt", count=FIXED_AT_MAX_ROWS))
            return None

        row_widget = QWidget()
        row_widget.setFixedHeight(30)
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        index_label = QLabel(str(len(self.fixed_at_rows) + 1))
        index_label.setFixedWidth(18)

        select_checkbox = QCheckBox()
        select_checkbox.setFixedWidth(18)
        select_checkbox.setChecked(checked)
        select_checkbox.stateChanged.connect(self.save_fixed_at_commands)

        at_input = QLineEdit()
        row_index = len(self.fixed_at_rows) + 1
        at_input.setPlaceholderText(self.tr_text("at_command_row_placeholder_fmt", index=row_index))
        at_input.setAlignment(Qt.AlignLeft)
        at_input.setFixedHeight(26)
        at_input.setText(command)
        at_input.setCursorPosition(0)
        at_input.textChanged.connect(self.save_fixed_at_commands)
        at_input.textChanged.connect(lambda _text, inp=at_input: self.update_command_color(inp))

        send_btn = QPushButton(self.tr_text("send"))
        send_btn.setFixedWidth(54)
        send_btn.setFixedHeight(26)
        send_btn.clicked.connect(lambda _, inp=at_input: self.send_fixed_command(inp))

        row_layout.addWidget(index_label)
        row_layout.addWidget(select_checkbox)
        row_layout.addWidget(at_input, 1)
        row_layout.addWidget(send_btn)
        row_widget.setLayout(row_layout)

        self.fixed_at_rows_layout.addWidget(row_widget)
        self.fixed_at_rows.append(
            {
                "widget": row_widget,
                "index_label": index_label,
                "checkbox": select_checkbox,
                "input": at_input,
                "send_button": send_btn,
            }
        )
        self.fixed_at_inputs.append(at_input)
        self.update_command_color(at_input)

        if save and not self.loading_fixed_at_commands:
            self.save_fixed_at_commands()

        return row_widget

    def clear_fixed_at_rows(self):
        while self.fixed_at_rows:
            row = self.fixed_at_rows.pop()
            self.fixed_at_rows_layout.removeWidget(row["widget"])
            row["widget"].deleteLater()
        self.fixed_at_inputs.clear()

    def expand_fixed_at_rows(self):
        if len(self.fixed_at_rows) >= FIXED_AT_MAX_ROWS:
            self.set_status(self.tr_text("fixed_at_max_reached_fmt", count=FIXED_AT_MAX_ROWS))
            return

        self.add_fixed_at_row(save=True)
        self.sync_current_fixed_at_group()
        self.save_fixed_at_commands()

    def delete_empty_fixed_at_row(self):
        if len(self.fixed_at_rows) <= FIXED_AT_DEFAULT_ROWS:
            self.set_status(self.tr_text("fixed_at_min_reached_fmt", count=FIXED_AT_DEFAULT_ROWS))
            return

        last_row = self.fixed_at_rows[-1]
        if last_row["input"].text().strip():
            self.set_status(self.tr_text("no_empty_fixed_at_row"))
            return

        self.fixed_at_rows.pop()
        self.fixed_at_rows_layout.removeWidget(last_row["widget"])
        if last_row["input"] in self.fixed_at_inputs:
            self.fixed_at_inputs.remove(last_row["input"])
        last_row["widget"].deleteLater()
        self.sync_current_fixed_at_group()
        self.save_fixed_at_commands()

    def capture_fixed_at_rows(self):
        return [
            {
                "command": row["input"].text(),
                "checked": row["checkbox"].isChecked(),
            }
            for row in self.fixed_at_rows
        ]

    def sync_current_fixed_at_group(self):
        if 0 <= self.current_fixed_at_group < len(self.fixed_at_groups):
            self.fixed_at_groups[self.current_fixed_at_group]["rows"] = self.capture_fixed_at_rows()

    def load_fixed_at_group_rows(self):
        self.loading_fixed_at_commands = True
        self.clear_fixed_at_rows()
        rows = self.fixed_at_groups[self.current_fixed_at_group]["rows"]
        for row in rows:
            self.add_fixed_at_row(
                checked=bool(row.get("checked", False)),
                command=str(row.get("command", "")),
                save=False,
            )
        self.loading_fixed_at_commands = False
        self.update_fixed_at_group_buttons()

    def switch_fixed_at_group(self, group_index):
        if group_index == self.current_fixed_at_group:
            self.update_fixed_at_group_buttons()
            return

        if not 0 <= group_index < len(self.fixed_at_groups):
            return

        self.sync_current_fixed_at_group()
        self.current_fixed_at_group = group_index
        self.load_fixed_at_group_rows()
        self.save_fixed_at_commands()

    def update_fixed_at_group_buttons(self):
        for index, button in enumerate(self.fixed_at_group_buttons):
            button.setText(self.tr_text("group_label_fmt", index=index + 1))
            active = index == self.current_fixed_at_group
            button.setChecked(active)
            button.setProperty("fixedGroupActive", active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def update_command_color(self, line_edit):
        command_text, _remark = split_at_history_entry(line_edit.text())
        command = self.normalize_protocol_command(command_text)
        if self.is_protocol_data_command(command):
            line_edit.setStyleSheet("color: #1f62c2;")
        else:
            line_edit.setStyleSheet("")

    def set_auto_send_running(self, running):
        self.auto_send_button.setProperty("running", running)
        self.auto_send_button.style().unpolish(self.auto_send_button)
        self.auto_send_button.style().polish(self.auto_send_button)
        self.auto_send_button.update()

    def toggle_auto_send(self):
        if self.auto_send_active:
            self.stop_auto_send(self.tr_text("auto_send_stopped"))
            return

        selected_commands = [
            row["input"].text().strip()
            for row in self.fixed_at_rows
            if row["checkbox"].isChecked() and row["input"].text().strip()
        ]

        if not selected_commands:
            QMessageBox.warning(self, self.tr_text("no_command_selected_title"), self.tr_text("no_command_selected_msg"))
            return

        self.auto_send_queue = selected_commands * self.auto_count_spin.value()
        self.auto_send_index = 0
        self.auto_send_total = len(self.auto_send_queue)
        self.auto_send_success_count = 0
        self.auto_send_commands_per_round = len(selected_commands)
        self.auto_send_active = True
        self.auto_send_button.setText(self.tr_text("stop_auto"))
        self.set_auto_send_running(True)
        self.auto_interval_spin.setEnabled(False)
        self.auto_count_spin.setEnabled(False)
        self.expand_fixed_at_button.setEnabled(False)
        self.delete_fixed_at_button.setEnabled(False)
        self.update_auto_send_status(self.tr_text("auto_send_started"))
        self.process_auto_send_next()

    def process_auto_send_next(self):
        if not self.auto_send_active:
            return

        if self.auto_send_index >= len(self.auto_send_queue):
            self.stop_auto_send(self.tr_text("auto_send_completed"))
            return

        command = self.auto_send_queue[self.auto_send_index]
        self.auto_send_index += 1

        if self.send_routed_command(command, add_history=False):
            self.auto_send_success_count += 1
        else:
            self.stop_auto_send(self.tr_text("auto_send_failed"))
            return

        self.update_auto_send_status(self.tr_text("auto_sending"))

        if self.auto_send_index < len(self.auto_send_queue):
            self.auto_send_timer.start(self.auto_interval_spin.value())
        else:
            self.stop_auto_send(self.tr_text("auto_send_completed"))

    def stop_auto_send(self, message):
        self.auto_send_timer.stop()
        progress_message = self.format_auto_send_status(message)
        self.auto_send_queue = []
        self.auto_send_index = 0
        self.auto_send_active = False
        self.auto_send_total = 0
        self.auto_send_success_count = 0
        self.auto_send_commands_per_round = 0
        self.auto_send_button.setText(self.tr_text("auto_send"))
        self.set_auto_send_running(False)
        self.auto_interval_spin.setEnabled(True)
        self.auto_count_spin.setEnabled(True)
        self.expand_fixed_at_button.setEnabled(True)
        self.delete_fixed_at_button.setEnabled(True)
        self.set_status(progress_message)

    def update_auto_send_status(self, prefix):
        self.set_status(self.format_auto_send_status(prefix))

    def format_auto_send_status(self, prefix):
        total = self.auto_send_total or len(self.auto_send_queue)
        if total <= 0:
            return prefix

        attempted = min(self.auto_send_index, total)
        success = min(self.auto_send_success_count, attempted)
        if self.auto_send_commands_per_round > 0:
            round_index = ((attempted - 1) // self.auto_send_commands_per_round) + 1 if attempted else 1
            command_index = ((attempted - 1) % self.auto_send_commands_per_round) + 1 if attempted else 1
            round_total = self.auto_count_spin.value()
            if self.language == "zh":
                return (
                    f"{prefix}: {attempted}/{total}, 成功 {success}, "
                    f"轮次 {round_index}/{round_total}, 命令 {command_index}/{self.auto_send_commands_per_round}"
                )
            return (
                f"{prefix}: {attempted}/{total}, ok {success}, "
                f"round {round_index}/{round_total}, cmd {command_index}/{self.auto_send_commands_per_round}"
            )

        if self.language == "zh":
            return f"{prefix}: {attempted}/{total}, 成功 {success}"
        return f"{prefix}: {attempted}/{total}, ok {success}"

    def get_fixed_at_expanded_width(self):
        if self.width() >= FIXED_AT_WIDE_WINDOW_THRESHOLD:
            return FIXED_AT_WIDE_EXPANDED_WIDTH
        return FIXED_AT_COMPACT_EXPANDED_WIDTH

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "scroll_area") or not self.scroll_area.isVisible():
            return

        expanded_width = self.get_fixed_at_expanded_width()
        previous_min_width = self.fixed_at_panel_shell.minimumWidth()
        self.fixed_at_panel_shell.setMinimumWidth(expanded_width)
        sizes = self.content_splitter.sizes()
        if len(sizes) >= 2 and (previous_min_width != expanded_width or sizes[1] < expanded_width):
            total_width = sum(sizes)
            self.content_splitter.setSizes([max(400, total_width - expanded_width), expanded_width])

    def toggle_fixed_at_commands(self):
        visible = not self.scroll_area.isVisible()
        self.scroll_area.setVisible(visible)
        self.side_button.setText("》" if visible else "+\n+\n+")
        if visible:
            self.fixed_at_panel_shell.setMaximumWidth(16777215)
            expanded_width = self.get_fixed_at_expanded_width()
            self.fixed_at_panel_shell.setMinimumWidth(expanded_width)
            sizes = self.content_splitter.sizes()
            total_width = sum(sizes) if sizes else self.width()
            right_width = min(expanded_width, max(FIXED_AT_COLLAPSED_WIDTH, total_width - 400))
            self.content_splitter.setSizes([max(400, total_width - right_width), right_width])
            for at_input in self.fixed_at_inputs:
                at_input.setCursorPosition(0)
        else:
            self.fixed_at_panel_shell.setMinimumWidth(0)
            self.fixed_at_panel_shell.setMaximumWidth(FIXED_AT_COLLAPSED_WIDTH)
            self.fixed_at_panel_shell.setMinimumWidth(FIXED_AT_COLLAPSED_WIDTH)
            sizes = self.content_splitter.sizes()
            total_width = sum(sizes) if sizes else self.width()
            self.content_splitter.setSizes([max(400, total_width - FIXED_AT_COLLAPSED_WIDTH), FIXED_AT_COLLAPSED_WIDTH])

    def is_valid_baudrate(self, baudrate):
        valid_baudrates = ["115200", "9600", "19200", "38400", "57600", "460800", "921600"]
        return baudrate in valid_baudrates

    def is_serial_connected(self):
        return bool(self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open)

    def connect_serial(self):
        port = self.get_selected_port()
        baudrate = self.baudrate_combo.currentText().strip()

        if not port:
            QMessageBox.warning(self, self.tr_text("no_port_title"), self.tr_text("no_port_msg"))
            return

        if not self.is_valid_baudrate(baudrate):
            QMessageBox.warning(self, self.tr_text("invalid_baud_title"), self.tr_text("invalid_baud_msg"))
            return

        if self.is_serial_connected():
            self.disconnect_serial(show_status=False)

        baudrate_int = int(baudrate)
        self.serial_thread = SerialReader(port, baudrate_int)
        self.serial_thread.data_received.connect(self.update_log)
        self.serial_thread.error_occurred.connect(self.show_error)
        self.serial_thread.start()

        self.last_port = port
        self.last_baudrate = baudrate_int
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.connection_label.setText(self.tr_text("connected_fmt", port=port, baudrate=baudrate))
        self.set_status(self.tr_text("connected_status_fmt", port=port, baudrate=baudrate))

    def disconnect_serial(self, show_status=True):
        auto_send_was_active = self.auto_send_active
        if self.auto_send_active:
            self.stop_auto_send(self.tr_text("auto_send_serial_disconnected"))

        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.connection_label.setText(self.tr_text("disconnected"))
        if show_status:
            if auto_send_was_active:
                self.set_status(self.tr_text("disconnected_auto_send_stopped"))
            else:
                self.set_status(self.tr_text("disconnected"))

    def update_log(self, timestamp, text_data, hex_data):
        display_data = hex_data if self.display_hex_enabled else text_data
        log_line = self.format_log_line(timestamp, display_data)
        matched = self.is_log_matched(log_line)

        if matched:
            if self.is_paused:
                pass
            else:
                self.append_plain_log(log_line)

        if self.log_file:
            if self.save_filtered_checkbox.isChecked():
                if matched:
                    self.write_log_line(log_line)
            else:
                self.write_log_line(log_line)

    def is_log_matched(self, data):
        filter_text = self.filter_input.text().strip()
        if not filter_text:
            self.last_regex_error = ""
            return True

        if self.filter_mode_combo.currentData() == "regex":
            try:
                matched = re.search(filter_text, data) is not None
                self.last_regex_error = ""
                return matched
            except re.error as e:
                error_text = str(e)
                if error_text != self.last_regex_error:
                    self.last_regex_error = error_text
                    self.set_status(self.tr_text("invalid_regex_fmt", error=error_text))
                return False

        filters = [f.strip() for f in filter_text.split(",") if f.strip()]
        return not filters or any(f in data for f in filters)

    def toggle_pause(self, checked):
        self.is_paused = checked
        self.pause_button.setText(self.tr_text("resume") if checked else self.tr_text("pause"))
        self.update_activity_status(self.tr_text("display_resumed"))

    def show_error(self, error_message):
        auto_send_was_active = self.auto_send_active
        if self.auto_send_active:
            self.stop_auto_send(self.tr_text("auto_send_serial_error"))

        self.append_error(f"Error: {error_message}")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.connection_label.setText(self.tr_text("disconnected"))
        if auto_send_was_active:
            self.set_status(self.tr_text("serial_error_auto_send_stopped"))
        else:
            self.set_status(self.tr_text("serial_error"))

    def toggle_save_log(self):
        if self.log_file:
            self.stop_save_log()
        else:
            self.save_log()

    def save_log(self):
        options = QFileDialog.Options()
        default_dir = self.last_log_dir if self.last_log_dir else ""

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr_text("save_log_title"),
            default_dir,
            self.tr_text("text_files_filter"),
            options=options,
        )

        if file_path:
            if self.log_file:
                self.log_file.close()

            current_log_text = self.log_text.toPlainText()
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(current_log_text)
                if current_log_text and not current_log_text.endswith("\n"):
                    file.write("\n")

            self.base_log_path = file_path
            self.log_extend_index = 0
            self.open_log_file(file_path)
            self.last_log_dir = os.path.dirname(file_path)
            self.save_last_log_dir()
            self.open_log_folder_button.setEnabled(True)
            self.set_save_active(True)
            self.log_size_timer.start(LOG_FILE_SIZE_REFRESH_INTERVAL_MS)
            self.log_first_size_timer.start(LOG_FILE_FIRST_SIZE_REFRESH_DELAY_MS)
            self.log_rotate_timer.start(LOG_FILE_ROTATE_CHECK_INTERVAL_MS)
            self.refresh_log_file_size()
            self.check_log_file_size()
            self.update_activity_status()

    def open_log_file(self, file_path):
        self.log_file = open(file_path, "a", encoding="utf-8")
        self.current_log_path = file_path
        if os.path.exists(file_path):
            self.current_log_size = os.path.getsize(file_path)
        else:
            self.current_log_size = 0

    def write_log_line(self, data):
        if not self.log_file:
            return

        self.log_file.write(data + "\n")
        self.log_file.flush()

    def refresh_log_file_size(self):
        if not self.log_file or not self.current_log_path:
            return

        try:
            self.log_file.flush()
            self.reopen_current_log_file()
            self.sync_current_log_size()
        except OSError:
            return

        self.update_activity_status()

    def check_log_file_size(self):
        if not self.log_file or not self.current_log_path:
            return

        try:
            self.log_file.flush()
            self.sync_current_log_size()
        except OSError:
            return

        if self.current_log_size > LOG_FILE_MAX_BYTES:
            self.rotate_log_file()
        else:
            self.update_activity_status()

    def sync_current_log_size(self):
        if self.current_log_path and os.path.exists(self.current_log_path):
            self.current_log_size = os.path.getsize(self.current_log_path)

    def reopen_current_log_file(self):
        if not self.log_file or not self.current_log_path:
            return

        self.log_file.close()
        self.log_file = open(self.current_log_path, "a", encoding="utf-8")

    def rotate_log_file(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None

        next_path = self.get_next_extended_log_path()
        self.open_log_file(next_path)
        self.log_rotate_timer.start(LOG_FILE_ROTATE_CHECK_INTERVAL_MS)
        self.update_activity_status()

    def manual_extend_log_file(self):
        if not self.log_file or not self.current_log_path:
            self.set_status(self.tr_text("manual_extend_unavailable"))
            return

        self.rotate_log_file()
        self.log_size_timer.start(LOG_FILE_SIZE_REFRESH_INTERVAL_MS)
        self.update_activity_status(
            self.tr_text("manual_extend_done_fmt", file_name=os.path.basename(self.current_log_path))
        )

    def get_next_extended_log_path(self):
        base_path = self.base_log_path or self.current_log_path
        root, ext = os.path.splitext(base_path)

        while True:
            self.log_extend_index += 1
            next_path = f"{root}-extend-{self.log_extend_index}{ext}"
            if not os.path.exists(next_path):
                return next_path

    def stop_save_log(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None

        self.set_save_active(False)
        self.log_size_timer.stop()
        self.log_first_size_timer.stop()
        self.log_rotate_timer.stop()
        if self.current_log_path:
            self.update_activity_status(self.tr_text("stopped_saving_fmt", file_name=os.path.basename(self.current_log_path)))
        else:
            self.update_activity_status(self.tr_text("log_saving_stopped"))

    def set_save_active(self, active):
        self.save_button.setText(self.tr_text("stop_save") if active else self.tr_text("start_save"))
        self.save_button.setProperty("recording", active)
        self.save_button.style().unpolish(self.save_button)
        self.save_button.style().polish(self.save_button)
        self.manual_extend_button.setEnabled(active)

    def update_activity_status(self, fallback_message=None):
        if self.is_paused:
            if self.log_file and self.current_log_path:
                file_name = os.path.basename(self.current_log_path)
                self.set_status(
                    self.tr_text(
                        "display_paused_saving_fmt",
                        file_name=file_name,
                        size=self.format_file_size(self.current_log_size),
                    )
                )
            else:
                self.set_status(self.tr_text("display_paused"))
            return

        if fallback_message:
            self.set_status(fallback_message)
            return

        if self.log_file and self.current_log_path:
            file_name = os.path.basename(self.current_log_path)
            self.set_status(
                self.tr_text("recording_fmt", file_name=file_name, size=self.format_file_size(self.current_log_size))
            )
            return

    def format_file_size(self, size):
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        if size >= 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size}B"

    def open_log_folder(self):
        if not self.current_log_path:
            return

        folder = os.path.dirname(self.current_log_path)
        if not os.path.isdir(folder):
            QMessageBox.warning(self, self.tr_text("folder_not_found_title"), self.tr_text("folder_not_found_msg"))
            return

        os.startfile(folder)

    def send_command(self):
        history_entry = normalize_at_history_entry(self.command_input.text())
        cleaned_command, _remark = split_at_history_entry(history_entry)
        if not cleaned_command:
            return

        sent = self.send_routed_command(
            cleaned_command,
            add_history=False,
            use_newline_checkbox=True,
            use_hex=self.hex_checkbox.isChecked(),
        )
        if sent:
            self.add_command_history(history_entry)
        if self.command_input.text().strip() != cleaned_command:
            self.command_input.setText(cleaned_command)

    def send_fixed_command(self, at_input):
        cleaned_command = at_input.text().strip()
        if not cleaned_command:
            return

        self.send_routed_command(cleaned_command, add_history=False, use_newline_checkbox=False)

    def send_routed_command(self, cleaned_command, add_history=False, use_newline_checkbox=False, use_hex=False):
        if use_hex:
            hex_payload = self.parse_hex_command(cleaned_command)
            if hex_payload is None:
                QMessageBox.warning(self, self.tr_text("invalid_hex_title"), self.tr_text("invalid_hex_msg"))
                return False

            if self.write_serial_bytes(hex_payload):
                if add_history:
                    self.add_command_history(cleaned_command)
                self.append_sent_log(self.normalize_hex_display(cleaned_command), "HEX")
                return True
            return False

        protocol_command = self.normalize_protocol_command(cleaned_command)

        if self.is_protocol_data_command(protocol_command):
            if self.write_data_channel_command(protocol_command):
                if add_history:
                    self.add_command_history(cleaned_command)
                self.append_sent_log(protocol_command, "Data")
                return True
            return False

        command = cleaned_command
        if use_newline_checkbox:
            if self.newline_checkbox.isChecked():
                command += "\r\n"
        else:
            command += "\r\n"

        if self.write_serial_command(command):
            if add_history:
                self.add_command_history(cleaned_command)
            self.append_sent_log(cleaned_command, "Serial")
            return True

        return False

    def normalize_protocol_command(self, command):
        return re.sub(r"\s+", "", command).upper()

    def is_protocol_data_command(self, command):
        return command.startswith("F102") or command.startswith("F103")

    def parse_hex_command(self, command):
        compact_command = re.sub(r"0[xX]", "", command)
        compact_command = re.sub(r"[\s,;:_-]+", "", compact_command)
        if not compact_command or len(compact_command) % 2:
            return None
        if not re.fullmatch(r"[0-9a-fA-F]+", compact_command):
            return None

        try:
            return bytes.fromhex(compact_command)
        except ValueError:
            return None

    def normalize_hex_display(self, command):
        compact_command = re.sub(r"0[xX]", "", command)
        compact_command = re.sub(r"[\s,;:_-]+", "", compact_command).upper()
        return " ".join(compact_command[index:index + 2] for index in range(0, len(compact_command), 2))

    def write_data_channel_command(self, command):
        imei = self.imei_input.text().strip()
        if not imei:
            QMessageBox.warning(self, self.tr_text("missing_imei_title"), self.tr_text("missing_imei_msg"))
            return False

        if not imei.isdigit():
            QMessageBox.warning(self, self.tr_text("invalid_imei_title"), self.tr_text("invalid_imei_msg"))
            return False

        payload = {"imei": int(imei), "cmd": command}

        try:
            resp = requests.post(SEND_URL, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            self.append_error(self.tr_text("data_channel_failed_fmt", error=e))
            return False

    def append_sent_log(self, command, channel):
        timestamp = format_log_timestamp()
        if self.language == "zh":
            body = f"已发送[{channel}]: {command}"
        else:
            body = f"Sent[{channel}]: {command}"
        message = self.format_log_line(timestamp, body)
        self.append_html_log(f"<span style='color:#1f62c2;'>{message}</span>")

    def write_serial_command(self, command):
        return self.write_serial_bytes(command.encode("utf-8"))

    def write_serial_bytes(self, payload):
        if not self.is_serial_connected():
            QMessageBox.warning(self, self.tr_text("not_connected_title"), self.tr_text("not_connected_msg"))
            return False

        try:
            self.serial_thread.serial.write(payload)
            self.serial_thread.serial.flush()
            return True
        except (serial.SerialException, OSError) as e:
            self.show_error(str(e))
            return False

    def load_fixed_at_commands(self):
        loaded_groups = None
        current_group = 0

        if os.path.exists(self.fixed_at_file):
            try:
                with open(self.fixed_at_file, "r", encoding="utf-8") as file:
                    data = json.load(file)
                loaded_groups = data.get("groups", [])
                current_group = int(data.get("current_group", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                loaded_groups = None
                current_group = 0

        if loaded_groups is None and os.path.exists(self.legacy_fixed_at_file):
            try:
                with open(self.legacy_fixed_at_file, "r", encoding="utf-8") as file:
                    commands = [line.rstrip("\n") for line in file.readlines()]
                migrated_rows = [
                    {"command": command.strip(), "checked": False}
                    for command in commands[:FIXED_AT_MAX_ROWS]
                ]
                while len(migrated_rows) < FIXED_AT_DEFAULT_ROWS:
                    migrated_rows.append({"command": "", "checked": False})
                loaded_groups = self.create_default_fixed_at_groups()
                loaded_groups[0]["rows"] = migrated_rows
            except OSError:
                loaded_groups = None

        self.fixed_at_groups = self.normalize_fixed_at_groups(loaded_groups)
        if not 0 <= current_group < len(self.fixed_at_groups):
            current_group = 0
        self.current_fixed_at_group = current_group
        self.load_fixed_at_group_rows()

    def save_fixed_at_commands(self):
        if self.loading_fixed_at_commands:
            return

        self.sync_current_fixed_at_group()
        ensure_parent_dir(self.fixed_at_file)
        with open(self.fixed_at_file, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "version": version,
                    "current_group": self.current_fixed_at_group,
                    "groups": self.fixed_at_groups,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )

    def load_command_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as file:
                lines = [normalize_at_history_entry(line) for line in file.readlines()]
                lines = [line for line in lines if line]
                self.updating_command_history = True
                self.command_history_combo.blockSignals(True)
                for line in reversed(lines):
                    self.command_history_combo.addItem(line, line)
                self.command_history_combo.blockSignals(False)
                self.updating_command_history = False

    def add_command_history(self, command):
        cleaned_command = normalize_at_history_entry(command)
        if not cleaned_command:
            return

        self.updating_command_history = True
        self.command_history_combo.blockSignals(True)
        existing_index = self.find_command_history_index(cleaned_command)
        if existing_index == -1:
            self.command_history_combo.insertItem(0, cleaned_command, cleaned_command)
            self.command_history_combo.setCurrentIndex(0)
        else:
            self.command_history_combo.setCurrentIndex(existing_index)
        self.command_history_combo.blockSignals(False)
        self.updating_command_history = False
        self.save_command_history(cleaned_command)

    def find_command_history_index(self, command):
        for index in range(self.command_history_combo.count()):
            entry = self.command_history_combo.itemData(index, Qt.UserRole) or self.command_history_combo.itemText(index)
            if entry == command:
                return index
        return -1

    def save_command_history(self, command):
        cleaned_command = normalize_at_history_entry(command)
        if not cleaned_command:
            return

        lines = []
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as file:
                lines = [normalize_at_history_entry(line) for line in file.readlines()]
                lines = [line for line in lines if line]

        if cleaned_command not in lines:
            ensure_parent_dir(self.history_file)
            with open(self.history_file, "a", encoding="utf-8") as file:
                file.write(cleaned_command + "\n")

    def load_selected_command(self, _index=None):
        if self.updating_command_history:
            return

        current_index = self.command_history_combo.currentIndex()
        selected_entry = self.command_history_combo.itemData(current_index, Qt.UserRole)
        if not selected_entry:
            selected_entry = self.command_history_combo.currentText()
        selected_command, _remark = split_at_history_entry(selected_entry)
        self.command_input.setText(selected_command)

    def clear_log(self):
        self.log_text.clear()
        self.set_log_line_limit(self.max_log_lines)
        self.update_activity_status(self.tr_text("log_display_cleared"))

    def append_info(self, message):
        timestamp = format_log_timestamp()
        self.append_html_log(f"<span style='color:#6a4bbc;'>{self.format_log_line(timestamp, message)}</span>")

    def append_error(self, message):
        timestamp = format_log_timestamp()
        self.append_html_log(f"<span style='color:#c0392b;'>{self.format_log_line(timestamp, message)}</span>")

    def append_plain_log(self, text):
        text = self.sanitize_display_text(text)
        scroll_bar = self.log_text.verticalScrollBar()
        previous_value = scroll_bar.value()
        was_at_bottom = previous_value >= scroll_bar.maximum() - LOG_AUTO_SCROLL_MARGIN
        self.set_log_line_limit(self.max_log_lines if was_at_bottom else self.log_reading_max_lines)

        cursor = QTextCursor(self.log_text.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text, QTextCharFormat())
        cursor.insertBlock()

        if was_at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())
        elif self.is_log_reading_limit_reached():
            self.set_log_line_limit(self.max_log_lines)
            scroll_bar.setValue(scroll_bar.maximum())
        else:
            scroll_bar.setValue(previous_value)

    def sanitize_display_text(self, text):
        text = text.replace("\r", " ").replace("\n", " ")
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    def format_log_line(self, timestamp, message):
        if self.show_timestamp:
            return f"{timestamp} {message}"
        return message

    def append_html_log(self, html):
        scroll_bar = self.log_text.verticalScrollBar()
        previous_value = scroll_bar.value()
        was_at_bottom = previous_value >= scroll_bar.maximum() - LOG_AUTO_SCROLL_MARGIN
        self.set_log_line_limit(self.max_log_lines if was_at_bottom else self.log_reading_max_lines)

        cursor = QTextCursor(self.log_text.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        cursor.insertBlock()

        if was_at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())
        else:
            scroll_bar.setValue(previous_value)

    def update_log_line_limit_for_scroll(self):
        scroll_bar = self.log_text.verticalScrollBar()
        if scroll_bar.value() >= scroll_bar.maximum() - LOG_AUTO_SCROLL_MARGIN:
            self.set_log_line_limit(self.max_log_lines)
        else:
            self.set_log_line_limit(self.log_reading_max_lines)

    def set_log_line_limit(self, max_lines):
        document = self.log_text.document()
        if document.maximumBlockCount() != max_lines:
            document.setMaximumBlockCount(max_lines)

    def is_log_reading_limit_reached(self):
        document = self.log_text.document()
        return (
            document.maximumBlockCount() == self.log_reading_max_lines
            and document.blockCount() >= self.log_reading_max_lines
        )

    def set_status(self, message):
        if self.log_file and self.current_log_path:
            file_name = os.path.basename(self.current_log_path)
            try:
                self.log_file.flush()
                self.sync_current_log_size()
            except (OSError, ValueError):
                pass

            has_size = "Size:" in message or "大小:" in message or f"{self.tr_text('size_label')}:" in message
            if file_name not in message or not has_size:
                message = (
                    f"{message} | {self.tr_text('log_label')}: {file_name} | "
                    f"{self.tr_text('size_label')}: {self.format_file_size(self.current_log_size)}"
                )

        self.status_label.setText(message)

    def closeEvent(self, event):
        self.log_size_timer.stop()
        self.log_first_size_timer.stop()
        self.log_rotate_timer.stop()
        self.auto_send_timer.stop()

        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None

        if self.log_file:
            self.log_file.close()
            self.log_file = None

        event.accept()

    def wheelEvent(self, event):
        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            event.ignore()
            return
        super().wheelEvent(event)


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def set_windows_app_icon_id():
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


if __name__ == "__main__":
    set_windows_app_icon_id()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("icon.ico")))
    tool = SerialPortTool()
    tool.show()
    sys.exit(app.exec_())
