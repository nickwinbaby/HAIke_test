import os
import sys
import ctypes
import subprocess
from datetime import datetime

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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


version = "11.0"
Compilation_date = "2026-7-15 15:00:00"
LOG_FILE_MAX_BYTES = 200 * 1024 * 1024
LOG_FILE_SIZE_CHECK_INTERVAL_MS = 10 * 60 * 1000
WINDOWS_APP_ID = "RichLink.SerialPortTool.V11"


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
        self.log_size_timer.timeout.connect(self.check_log_file_size)

        self.initUI()
        self.load_command_history()
        self.load_fixed_at_commands()

    def initUI(self):
        self.setWindowTitle("瑞联串口工具 V" + version + " --Mangetic-20260715")
        self.setWindowIcon(QIcon(app_icon_path()))
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
        self.port_combo.setFixedWidth(110)

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

        self.save_filtered_checkbox = QCheckBox("Save filtered only")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setCheckable(True)

        self.save_button = QPushButton("Start Save")
        self.save_button.setProperty("recording", False)
        self.open_log_folder_button = QPushButton("Open Folder")
        self.open_log_folder_button.setEnabled(False)
        self.clear_button = QPushButton("Clear")

        filter_layout.addWidget(QLabel("Filter"))
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

        command_group = QGroupBox("Command")
        command_layout = QVBoxLayout()
        command_layout.setSpacing(6)

        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("AT command")
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
        fixed_at_layout = QFormLayout()
        fixed_at_layout.setSpacing(6)
        self.fixed_at_inputs = []

        for i in range(13):
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            at_input = QLineEdit()
            at_input.setPlaceholderText(f"AT command {i + 1}")
            at_input.setAlignment(Qt.AlignLeft)
            at_input.textChanged.connect(self.save_fixed_at_commands)

            send_btn = QPushButton("Send")
            send_btn.setFixedWidth(54)
            send_btn.clicked.connect(lambda _, inp=at_input: self.send_fixed_command(inp))

            row_layout.addWidget(at_input, 1)
            row_layout.addWidget(send_btn)
            row_widget.setLayout(row_layout)

            fixed_at_layout.addRow(QLabel(str(i + 1)), row_widget)
            self.fixed_at_inputs.append(at_input)

        self.fixed_at_group.setLayout(fixed_at_layout)

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
            QPushButton:disabled {
                color: #98a3ad;
                background: #e9eef2;
                border-color: #c6d0d8;
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
            "5. Save filtered only 勾选后，只保存匹配过滤条件的日志。\n"
            "6. Start Save 用于选择文件并开始保存，保存中同一按钮会变成 Stop Save。\n"
            "7. Pause 只暂停界面显示，不影响日志文件持续保存。\n"
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

        self.append_info(f"Serial setting changed to {port} / {baudrate}, reconnecting...")
        self.disconnect_serial(show_status=False)
        self.connect_serial()

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
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.connection_label.setText("Disconnected")
        if show_status:
            self.set_status("Disconnected")

    def update_log(self, data):
        filter_text = self.filter_input.text()
        filters = [f.strip() for f in filter_text.split(",") if f.strip()]
        matched = not filters or any(f in data for f in filters)

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

    def toggle_pause(self, checked):
        self.is_paused = checked
        self.pause_button.setText("Resume" if checked else "Pause")
        self.update_activity_status("Display resumed")

    def show_error(self, error_message):
        self.append_error(f"Error: {error_message}")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.connection_label.setText("Disconnected")
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
            self.log_size_timer.start(LOG_FILE_SIZE_CHECK_INTERVAL_MS)
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

    def check_log_file_size(self):
        if not self.log_file or not self.current_log_path:
            return

        try:
            self.log_file.flush()
            self.reopen_current_log_file()
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

        if self.log_file and self.current_log_path:
            file_name = os.path.basename(self.current_log_path)
            self.set_status(f"Recording log to {file_name} | Size: {self.format_file_size(self.current_log_size)}")
            return

        if fallback_message:
            self.set_status(fallback_message)

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

        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def send_command(self):
        cleaned_command = self.command_input.text().strip()
        if not cleaned_command:
            return

        command = cleaned_command
        if self.newline_checkbox.isChecked():
            command += "\r\n"

        if self.write_serial_command(command):
            self.add_command_history(cleaned_command)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.append_html_log(f"<span style='color:#1f62c2;'>{timestamp} - Sent: {cleaned_command}</span>")

    def send_fixed_command(self, at_input):
        cleaned_command = at_input.text().strip()
        if not cleaned_command:
            return

        command = cleaned_command + "\r\n"
        if self.write_serial_command(command):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.append_html_log(f"<span style='color:#1f62c2;'>{timestamp} - Sent: {cleaned_command}</span>")

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
        if os.path.exists(self.fixed_at_file):
            with open(self.fixed_at_file, "r", encoding="utf-8") as file:
                for i, line in enumerate(file):
                    if i < len(self.fixed_at_inputs):
                        self.fixed_at_inputs[i].setText(line.strip())
                        self.fixed_at_inputs[i].setCursorPosition(0)

    def save_fixed_at_commands(self):
        with open(self.fixed_at_file, "w", encoding="utf-8") as file:
            for at_input in self.fixed_at_inputs:
                file.write(at_input.text() + "\n")

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
        self.status_label.setText(message)

    def closeEvent(self, event):
        self.log_size_timer.stop()

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


def app_icon_path():
    if sys.platform == "darwin":
        mac_icon = resource_path("icon.icns")
        if os.path.exists(mac_icon):
            return mac_icon
    return resource_path("icon.ico")


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
    app.setWindowIcon(QIcon(app_icon_path()))
    tool = SerialPortTool()
    tool.show()
    sys.exit(app.exec_())
