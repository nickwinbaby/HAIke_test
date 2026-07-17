import os
import sys
import ctypes
import re
from datetime import datetime

import requests
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
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
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


version = "12.0"
Compilation_date = "2026-7-16 10:30:00"
LOG_FILE_MAX_BYTES = 200 * 1024 * 1024
LOG_FILE_SIZE_REFRESH_INTERVAL_MS = 60 * 1000
LOG_FILE_ROTATE_CHECK_INTERVAL_MS = 60 * 60 * 1000
WINDOWS_APP_ID = "RichLink.SerialPortTool.V12"
SEND_URL = "http://10.85.40.3:8088/client/send"


class SerialReader(QThread):
    """串口读取线程：后台读取串口数据，按行发送给主界面。"""

    data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.buffer = ""
        self.max_buffer_size = 10240

    def run(self):
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.running = True

            while self.running:
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)

                    try:
                        decoded_data = data.decode("utf-8")
                    except UnicodeDecodeError:
                        decoded_data = data.decode("latin-1")

                    self.buffer += decoded_data
                    if len(self.buffer) > self.max_buffer_size:
                        self.buffer = self.buffer[-self.max_buffer_size:]

                    while "\n" in self.buffer:
                        line, self.buffer = self.buffer.split("\n", 1)
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.data_received.emit(f"{timestamp} - {line.strip()}")
                else:
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
        self.history_file = "at_command_history.txt"
        self.fixed_at_file = "fixed_at_commands.txt"
        self.max_log_lines = 3000
        self.last_log_dir = ""
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
        self.log_rotate_timer = QTimer(self)
        self.log_rotate_timer.timeout.connect(self.check_log_file_size)
        self.fixed_at_rows = []
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
        self.setWindowTitle("RichLink Serial Port Tool V" + version + " --Mangetic-20260716")
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setGeometry(420, 180, 980, 640)
        self.setMinimumSize(820, 520)

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
        self.refresh_ports()

    def build_menu(self):
        menu_bar = QMenuBar(self)
        help_menu = QMenu("Help", self)

        modify_action = QAction("Modify", self)
        instructions_action = QAction("Instructions", self)
        about_action = QAction("About", self)

        modify_action.triggered.connect(self.show_modify)
        instructions_action.triggered.connect(self.show_instructions)
        about_action.triggered.connect(self.show_about)

        help_menu.addAction(modify_action)
        help_menu.addAction(instructions_action)
        help_menu.addAction(about_action)
        menu_bar.addMenu(help_menu)
        self.main_layout.setMenuBar(menu_bar)

    def build_connection_bar(self):
        connection_panel = QFrame()
        connection_panel.setObjectName("topPanel")

        connection_layout = QHBoxLayout()
        connection_layout.setContentsMargins(10, 8, 10, 8)
        connection_layout.setSpacing(8)

        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(96)

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

        connection_layout.addWidget(QLabel("Port"))
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(self.refresh_button)
        connection_layout.addSpacing(10)
        connection_layout.addWidget(QLabel("Baud"))
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
        self.open_log_folder_button = QPushButton("Open Folder")
        self.open_log_folder_button.setEnabled(False)
        self.clear_button = QPushButton("Clear")

        filter_layout.addWidget(QLabel("Filter"))
        filter_layout.addWidget(self.filter_mode_combo)
        filter_layout.addWidget(self.filter_input, 1)
        filter_layout.addWidget(self.save_filtered_checkbox)
        filter_layout.addWidget(self.pause_button)
        filter_layout.addWidget(self.save_button)
        filter_layout.addWidget(self.open_log_folder_button)
        filter_layout.addWidget(self.clear_button)

        filter_panel.setLayout(filter_layout)
        self.main_layout.addWidget(filter_panel)

        self.pause_button.toggled.connect(self.toggle_pause)
        self.save_button.clicked.connect(self.toggle_save_log)
        self.open_log_folder_button.clicked.connect(self.open_log_folder)
        self.clear_button.clicked.connect(self.clear_log)
        self.filter_mode_combo.currentIndexChanged.connect(self.update_filter_placeholder)

    def update_filter_placeholder(self):
        if self.filter_mode_combo.currentData() == "regex":
            self.filter_input.setPlaceholderText("Regex filter, example: ERROR|FAIL|F10[23]")
        else:
            self.filter_input.setPlaceholderText("Filter keywords, split by comma")

    def build_content_area(self):
        content_layout = QHBoxLayout()
        content_layout.setSpacing(6)

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
        left_layout.addWidget(self.log_text, 1)

        command_group = QGroupBox("AT Commands")
        command_layout = QVBoxLayout()
        command_layout.setSpacing(6)

        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("AT command, or F102/F103 command")
        self.send_button = QPushButton("Send")
        self.newline_checkbox = QCheckBox("Send with Enter")
        self.newline_checkbox.setChecked(True)

        command_input_layout.addWidget(self.command_input, 1)
        command_input_layout.addWidget(self.send_button)
        command_input_layout.addWidget(self.newline_checkbox)

        self.command_history_combo = QComboBox()
        self.command_history_combo.setEditable(False)
        self.command_history_combo.currentIndexChanged.connect(self.load_selected_command)

        command_layout.addLayout(command_input_layout)
        command_layout.addWidget(self.command_history_combo)
        command_group.setLayout(command_layout)
        left_layout.addWidget(command_group)

        self.side_button = QPushButton(">")
        self.side_button.setFixedWidth(24)
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
        auto_settings_layout.addWidget(QLabel("Interval"))
        auto_settings_layout.addWidget(self.auto_interval_spin)
        auto_settings_layout.addWidget(QLabel("ms"))
        auto_settings_layout.addSpacing(10)
        auto_settings_layout.addWidget(QLabel("Count"))
        auto_settings_layout.addWidget(self.auto_count_spin)
        auto_settings_layout.addStretch(1)

        auto_send_layout = QHBoxLayout()
        auto_send_layout.setSpacing(4)
        self.auto_send_button = QPushButton("Auto Send")
        self.auto_send_button.setObjectName("autoSendButton")
        self.auto_send_button.setProperty("running", False)
        auto_send_layout.addWidget(self.auto_send_button)
        auto_send_layout.addStretch(1)

        fixed_at_layout.addLayout(auto_settings_layout)
        fixed_at_layout.addLayout(auto_send_layout)

        imei_layout = QHBoxLayout()
        imei_layout.setSpacing(4)
        self.imei_input = QLineEdit()
        self.imei_input.setPlaceholderText("IMEI")
        imei_layout.addWidget(QLabel("IMEI"))
        imei_layout.addWidget(self.imei_input, 1)
        fixed_at_layout.addLayout(imei_layout)

        self.fixed_at_group.setLayout(fixed_at_layout)

        for _ in range(10):
            self.add_fixed_at_row(save=False)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.fixed_at_group)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFixedWidth(310)
        self.scroll_area.setVisible(False)

        content_layout.addWidget(left_panel, 1)
        content_layout.addWidget(self.side_button)
        content_layout.addWidget(self.scroll_area)
        self.main_layout.addLayout(content_layout, 1)

        self.send_button.clicked.connect(self.send_command)
        self.command_input.returnPressed.connect(self.send_command)
        self.command_input.textChanged.connect(lambda _text: self.update_command_color(self.command_input))
        self.auto_send_button.clicked.connect(self.toggle_auto_send)

    def build_status_bar(self):
        self.status_label = QLabel("Ready")
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
            QPushButton:disabled {
                color: #98a3ad;
                background: #e9eef2;
                border-color: #c6d0d8;
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
        modify_text = (
            "V 10.0\n"
            "1. 轻量化日志显示，限制串口读取 buffer，降低长时间运行卡顿风险。\n\n"
            "V 11.0\n"
            "1. 重构界面布局：顶部连接栏、中间日志区、底部命令区、右侧固定 AT 侧栏。\n"
            "2. 增加串口刷新按钮，连接状态和日志保存状态提示。\n"
            "3. 恢复端口/波特率变化后的自动重连。\n"
            "4. 固定 AT 空命令不再发送，底部命令历史去重更干净。\n"
            "5. Pause 改为冻结界面显示，不缓存等待日志，保存文件不受影响。\n"
            "6. 日志保存改为 append 持续写入，避免外部清空文件后产生空字节。\n"
            "7. 增加日志自动分卷：单文件超过 200MB 后扩展为 -extend-N 文件。\n"
            "8. 状态栏显示当前保存文件和大小；定时检查时重新打开日志句柄，便于 Windows 刷新文件大小。\n"
            "9. 增加 Windows 任务栏 AppUserModelID，并沿用 icon.ico 作为窗口图标。\n"
            "\nV 12.0\n"
            "1. Filter 增加 Regex 模式，支持正则表达式过滤。\n"
            "2. F102/F103 命令走 8088 数据通道发送，非 F102/F103 仍走串口通道。\n"
            "3. F102/F103 数据通道发送不追加回车换行。\n"
            "4. Fixed AT 默认 10 行，支持 Add 动态新增。\n"
            "5. Fixed AT 每行增加选择框，用于自动发送选择。\n"
            "6. 增加 Fixed AT 自动发送，支持间隔秒数和发送轮数。\n"
        )
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
            "5. Add Auto Send for selected Fixed AT rows. Interval is in milliseconds, default 1000ms, step 100ms.\n"
            "6. Auto Send now has a stable Start/Stop state, real-time progress, success count, and failure stop handling.\n"
            "7. Disconnect, serial setting changes, or serial errors automatically stop Auto Send.\n"
            "8. Bottom status always keeps current saved log file name and size when logging is active.\n"
            "9. Saved log size refresh runs every 1 minute; 200MB rotation check runs every 1 hour.\n"
        )

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(modify_text)
        text_edit.setFixedWidth(520)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        dialog = QDialog(self)
        dialog.setWindowTitle("Modify")
        dialog_layout = QVBoxLayout()
        dialog_layout.addWidget(text_edit)
        dialog.setLayout(dialog_layout)
        dialog.exec_()

    def show_instructions(self):
        instructions_text = (
            "使用说明:\n\n"
            "1. 点击 Refresh 可刷新当前可用串口。\n"
            "2. 底部输入框发送 AT 命令，Send with Enter 勾选后自动追加回车换行。\n"
            "3. 右侧固定 AT 面板点击 > 展开，固定 AT 默认发送时追加回车换行。\n"
            "4. Filter 支持多个关键字，使用英文逗号分隔。\n"
            "5. 勾选 Regex 后，Filter 按正则表达式匹配。\n"
            "6. F102/F103 命令会走数据通道发送，需要填写 IMEI，且不会追加回车换行。\n"
            "7. Save filtered only 勾选后，只保存匹配过滤条件的日志。\n"
            "8. Start Save 用于选择文件并开始保存，保存中同一按钮会变成 Stop Save。\n"
            "9. Pause 只暂停界面显示，不影响日志文件持续保存。\n"
            "10. Fixed AT 勾选行后，可通过 Auto Send 按间隔和次数自动发送。\n"
        )
        QMessageBox.information(self, "Instructions", instructions_text)

    def show_about(self):
        about_text = (
            "<div style='text-align: left;'>"
            "Rich link Serial Port Tool<br><br>"
            "Version " + version + "<br><br>"
            "Developed by Mulinxi<br><br>"
            "Compilation date " + Compilation_date +
            "</div>"
        )
        QMessageBox.about(self, "About", about_text)

    def refresh_ports(self):
        current_port = self.port_combo.currentText()
        ports = [port.device for port in serial.tools.list_ports.comports()]

        self.refreshing_ports = True
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current_port in ports:
            self.port_combo.setCurrentText(current_port)
        self.refreshing_ports = False

        if ports:
            self.set_status(f"{len(ports)} port(s) found")
        else:
            self.set_status("No serial port found")

    def handle_serial_settings_changed(self):
        if self.refreshing_ports:
            return

        if not self.is_serial_connected():
            return

        port = self.port_combo.currentText()
        baudrate = self.baudrate_combo.currentText()
        if port == self.last_port and baudrate == str(self.last_baudrate):
            return

        if self.auto_send_active:
            self.stop_auto_send("Auto send stopped: serial setting changed")

        self.append_info(f"Serial setting changed to {port} / {baudrate}, reconnecting...")
        self.disconnect_serial(show_status=False)
        self.connect_serial()

    def add_fixed_at_row(self, checked=False, command="", save=True):
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

        at_input = QLineEdit()
        at_input.setPlaceholderText(f"AT command {len(self.fixed_at_rows) + 1}")
        at_input.setAlignment(Qt.AlignLeft)
        at_input.setFixedHeight(26)
        at_input.setText(command)
        at_input.setCursorPosition(0)
        at_input.textChanged.connect(self.save_fixed_at_commands)
        at_input.textChanged.connect(lambda _text, inp=at_input: self.update_command_color(inp))

        send_btn = QPushButton("Send")
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

    def clear_fixed_at_rows(self):
        while self.fixed_at_rows:
            row = self.fixed_at_rows.pop()
            self.fixed_at_rows_layout.removeWidget(row["widget"])
            row["widget"].deleteLater()
        self.fixed_at_inputs.clear()

    def update_command_color(self, line_edit):
        command = self.normalize_protocol_command(line_edit.text().strip())
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
            self.stop_auto_send("Auto send stopped")
            return

        selected_commands = [
            row["input"].text().strip()
            for row in self.fixed_at_rows
            if row["checkbox"].isChecked() and row["input"].text().strip()
        ]

        if not selected_commands:
            QMessageBox.warning(self, "No Command Selected", "Please select at least one Fixed AT command.")
            return

        self.auto_send_queue = selected_commands * self.auto_count_spin.value()
        self.auto_send_index = 0
        self.auto_send_total = len(self.auto_send_queue)
        self.auto_send_success_count = 0
        self.auto_send_commands_per_round = len(selected_commands)
        self.auto_send_active = True
        self.auto_send_button.setText("Stop Auto")
        self.set_auto_send_running(True)
        self.auto_interval_spin.setEnabled(False)
        self.auto_count_spin.setEnabled(False)
        self.update_auto_send_status("Auto send started")
        self.process_auto_send_next()

    def process_auto_send_next(self):
        if not self.auto_send_active:
            return

        if self.auto_send_index >= len(self.auto_send_queue):
            self.stop_auto_send("Auto send completed")
            return

        command = self.auto_send_queue[self.auto_send_index]
        self.auto_send_index += 1

        if self.send_routed_command(command, add_history=False):
            self.auto_send_success_count += 1
        else:
            self.stop_auto_send("Auto send stopped: send failed")
            return

        self.update_auto_send_status("Auto sending")

        if self.auto_send_index < len(self.auto_send_queue):
            self.auto_send_timer.start(self.auto_interval_spin.value())
        else:
            self.stop_auto_send("Auto send completed")

    def stop_auto_send(self, message):
        self.auto_send_timer.stop()
        progress_message = self.format_auto_send_status(message)
        self.auto_send_queue = []
        self.auto_send_index = 0
        self.auto_send_active = False
        self.auto_send_total = 0
        self.auto_send_success_count = 0
        self.auto_send_commands_per_round = 0
        self.auto_send_button.setText("Auto Send")
        self.set_auto_send_running(False)
        self.auto_interval_spin.setEnabled(True)
        self.auto_count_spin.setEnabled(True)
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
            return (
                f"{prefix}: {attempted}/{total}, ok {success}, "
                f"round {round_index}/{round_total}, cmd {command_index}/{self.auto_send_commands_per_round}"
            )

        return f"{prefix}: {attempted}/{total}, ok {success}"

    def toggle_fixed_at_commands(self):
        visible = not self.scroll_area.isVisible()
        self.scroll_area.setVisible(visible)
        self.side_button.setText("<" if visible else ">")
        if visible:
            for at_input in self.fixed_at_inputs:
                at_input.setCursorPosition(0)

    def is_valid_baudrate(self, baudrate):
        valid_baudrates = ["115200", "9600", "19200", "38400", "57600", "460800", "921600"]
        return baudrate in valid_baudrates

    def is_serial_connected(self):
        return bool(self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open)

    def connect_serial(self):
        port = self.port_combo.currentText().strip()
        baudrate = self.baudrate_combo.currentText().strip()

        if not port:
            QMessageBox.warning(self, "No Port", "Please select a serial port.")
            return

        if not self.is_valid_baudrate(baudrate):
            QMessageBox.warning(self, "Invalid Baud Rate", "The selected baud rate is not valid.")
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
        self.connection_label.setText(f"Connected: {port} / {baudrate}")
        self.set_status(f"Connected to {port} at {baudrate}")

    def disconnect_serial(self, show_status=True):
        auto_send_was_active = self.auto_send_active
        if self.auto_send_active:
            self.stop_auto_send("Auto send stopped: serial disconnected")

        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.connection_label.setText("Disconnected")
        if show_status:
            if auto_send_was_active:
                self.set_status("Disconnected, auto send stopped")
            else:
                self.set_status("Disconnected")

    def update_log(self, data):
        matched = self.is_log_matched(data)

        if matched:
            if self.is_paused:
                pass
            else:
                self.append_plain_log(data)

        if self.log_file:
            if self.save_filtered_checkbox.isChecked():
                if matched:
                    self.write_log_line(data)
            else:
                self.write_log_line(data)

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
                    self.set_status(f"Invalid regex filter: {error_text}")
                return False

        filters = [f.strip() for f in filter_text.split(",") if f.strip()]
        return not filters or any(f in data for f in filters)

    def toggle_pause(self, checked):
        self.is_paused = checked
        self.pause_button.setText("Resume" if checked else "Pause")
        self.update_activity_status("Display resumed")

    def show_error(self, error_message):
        auto_send_was_active = self.auto_send_active
        if self.auto_send_active:
            self.stop_auto_send("Auto send stopped: serial error")

        self.append_error(f"Error: {error_message}")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.connection_label.setText("Disconnected")
        if auto_send_was_active:
            self.set_status("Serial error, auto send stopped")
        else:
            self.set_status("Serial error")

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
            "Save Log",
            default_dir,
            "Text Files (*.txt);;All Files (*)",
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
            self.open_log_folder_button.setEnabled(True)
            self.set_save_active(True)
            self.log_size_timer.start(LOG_FILE_SIZE_REFRESH_INTERVAL_MS)
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
        self.update_activity_status()

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
        self.log_rotate_timer.stop()
        if self.current_log_path:
            self.update_activity_status(f"Stopped saving log: {os.path.basename(self.current_log_path)}")
        else:
            self.update_activity_status("Log saving stopped")

    def set_save_active(self, active):
        self.save_button.setText("Stop Save" if active else "Start Save")
        self.save_button.setProperty("recording", active)
        self.save_button.style().unpolish(self.save_button)
        self.save_button.style().polish(self.save_button)

    def update_activity_status(self, fallback_message=None):
        if self.is_paused:
            if self.log_file and self.current_log_path:
                file_name = os.path.basename(self.current_log_path)
                self.set_status(f"Display paused, saving continues: {file_name} | Size: {self.format_file_size(self.current_log_size)}")
            else:
                self.set_status("Display paused")
            return

        if fallback_message:
            self.set_status(fallback_message)
            return

        if self.log_file and self.current_log_path:
            file_name = os.path.basename(self.current_log_path)
            self.set_status(f"Recording log to {file_name} | Size: {self.format_file_size(self.current_log_size)}")
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
            QMessageBox.warning(self, "Folder Not Found", "The log folder does not exist.")
            return

        os.startfile(folder)

    def send_command(self):
        cleaned_command = self.command_input.text().strip()
        if not cleaned_command:
            return

        self.send_routed_command(cleaned_command, add_history=True, use_newline_checkbox=True)

    def send_fixed_command(self, at_input):
        cleaned_command = at_input.text().strip()
        if not cleaned_command:
            return

        self.send_routed_command(cleaned_command, add_history=False, use_newline_checkbox=False)

    def send_routed_command(self, cleaned_command, add_history=False, use_newline_checkbox=False):
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

    def write_data_channel_command(self, command):
        imei = self.imei_input.text().strip()
        if not imei:
            QMessageBox.warning(self, "Missing IMEI", "F102/F103 data channel requires IMEI.")
            return False

        if not imei.isdigit():
            QMessageBox.warning(self, "Invalid IMEI", "IMEI must be numeric.")
            return False

        payload = {"imei": int(imei), "cmd": command}

        try:
            resp = requests.post(SEND_URL, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            self.append_error(f"Data channel send failed: {e}")
            return False

    def append_sent_log(self, command, channel):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append_html_log(f"<span style='color:#1f62c2;'>{timestamp} - Sent[{channel}]: {command}</span>")

    def write_serial_command(self, command):
        if not self.is_serial_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect the serial port first.")
            return False

        try:
            self.serial_thread.serial.write(command.encode("utf-8"))
            return True
        except (serial.SerialException, OSError) as e:
            self.show_error(str(e))
            return False

    def load_fixed_at_commands(self):
        self.loading_fixed_at_commands = True
        commands = []
        if os.path.exists(self.fixed_at_file):
            with open(self.fixed_at_file, "r", encoding="utf-8") as file:
                commands = [line.rstrip("\n") for line in file.readlines()]

        self.clear_fixed_at_rows()
        row_count = max(10, len(commands))
        for i in range(row_count):
            command = commands[i].strip() if i < len(commands) else ""
            self.add_fixed_at_row(checked=False, command=command, save=False)
        self.loading_fixed_at_commands = False

    def save_fixed_at_commands(self):
        if self.loading_fixed_at_commands:
            return

        with open(self.fixed_at_file, "w", encoding="utf-8") as file:
            for row in self.fixed_at_rows:
                file.write(row["input"].text() + "\n")

    def load_command_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as file:
                lines = [line.strip() for line in file.readlines() if line.strip()]
                for line in reversed(lines):
                    self.command_history_combo.addItem(line)

    def add_command_history(self, command):
        if self.command_history_combo.findText(command) == -1:
            self.command_history_combo.insertItem(0, command)
        self.save_command_history(command)

    def save_command_history(self, command):
        cleaned_command = command.replace("\r", "").replace("\n", "").strip()
        if not cleaned_command:
            return

        lines = []
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as file:
                lines = [line.strip() for line in file.readlines() if line.strip()]

        if cleaned_command not in lines:
            with open(self.history_file, "a", encoding="utf-8") as file:
                file.write(cleaned_command + "\n")

    def load_selected_command(self):
        selected_command = self.command_history_combo.currentText()
        self.command_input.setText(selected_command)

    def clear_log(self):
        self.log_text.clear()
        self.update_activity_status("Log display cleared")

    def append_info(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append_html_log(f"<span style='color:#6a4bbc;'>{timestamp} - {message}</span>")

    def append_error(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append_html_log(f"<span style='color:#c0392b;'>{timestamp} - {message}</span>")

    def append_plain_log(self, text):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text, QTextCharFormat())
        cursor.insertBlock()
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def append_html_log(self, html):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        cursor.insertBlock()
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def set_status(self, message):
        if self.log_file and self.current_log_path:
            file_name = os.path.basename(self.current_log_path)
            try:
                self.log_file.flush()
                self.sync_current_log_size()
            except OSError:
                pass

            if file_name not in message or "Size:" not in message:
                message = f"{message} | Log: {file_name} | Size: {self.format_file_size(self.current_log_size)}"

        self.status_label.setText(message)

    def closeEvent(self, event):
        self.log_size_timer.stop()
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
