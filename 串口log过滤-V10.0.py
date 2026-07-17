import serial
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from datetime import datetime
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QTextEdit, QLabel,
                             QLineEdit, QFileDialog, QCheckBox, QGroupBox, QFormLayout, QScrollArea, QMenuBar, QMenu,
                             QAction, QMessageBox, QDialog, QPlainTextEdit)  # <-- 引入 QPlainTextEdit
import serial.tools.list_ports
import os
from PyQt5.QtGui import QIcon

#  编译命令 pyinstaller --onefile --windowed 串口log过滤.py
# pyinstaller --onefile --windowed --icon=icon.ico 串口log过滤.py
# pyinstaller --clean --onefile --windowed --icon=icon.ico 串口log过滤.py
# 编译完成后，修改spec中的datas=[('icon.ico', '.')], 重新编译
# datas = [('icon.ico', '.'), ('gosuncn1.png', '.')],
# pyinstaller 串口log过滤.spec

version = "9.0"
Compilation_date = "2025-6-6 13:55:30"


class SerialReader(QThread):
    data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.buffer = ""

    def run(self):
        try:
            self.serial = serial.Serial(self.port, self.baudrate)
            self.running = True
            while self.running:
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)
                    try:
                        decoded_data = data.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_data = data.decode('latin-1')
                    self.buffer += decoded_data
                    while '\n' in self.buffer:
                        line, self.buffer = self.buffer.split('\n', 1)
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        self.data_received.emit(f"{timestamp} - {line.strip()}")
        except serial.SerialException as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self.running = False
        if self.serial and self.serial.is_open:
            self.serial.close()


class SerialPortTool(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.serial_thread = None
        self.log_file = None
        self.history_file = 'at_command_history.txt'
        self.fixed_at_file = 'fixed_at_commands.txt'
        self.load_command_history()
        self.load_fixed_at_commands()
        self.max_log_lines = 3000  # Maximum number of lines to display in the log
        self.last_log_dir = ''  # Store the last used directory for saving logs

        # 日志缓冲：把高频到达的数据先放缓冲里，定时批量写入 UI，避免频繁 append 导致主线程压力大
        self._log_buffer = []
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_log_buffer)
        self._flush_timer.start(100)  # 100ms 批量刷新一次（你可以调整到 50/200ms）

        # 初始化检查日志定时器占位（用于 connect_serial 创建时替换）
        self.check_log_timer = None

    def initUI(self):
        self.setWindowTitle('瑞联串口工具 V' + version + '-木林夕')
        # self.setWindowIcon(QIcon('icon.ico'))  # Replace with the path to your icon file
        # 声明图标
        self.setWindowIcon(QIcon(resource_path("icon.ico")))  # 春哥牛逼
        self.setGeometry(500, 300, 600, 500)

        self.main_layout = QHBoxLayout()
        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()

        # 工具简介按键框
        menu_bar = QMenuBar(self)
        help_menu = QMenu('Help', self)

        about_action = QAction('About', self)
        modify_action = QAction('Modify', self)
        instructions_action = QAction('Instructions', self)

        help_menu.addAction(modify_action)
        help_menu.addAction(instructions_action)
        help_menu.addAction(about_action)
        menu_bar.addMenu(help_menu)
        self.main_layout.setMenuBar(menu_bar)

        # 工具简介按键框
        modify_action.triggered.connect(self.show_modify)
        instructions_action.triggered.connect(self.show_instructions)
        about_action.triggered.connect(self.show_about)

        # Port and Baud rate selection with border 222
        # 设置串口和波特率背景样式
        # port_baud_group = QGroupBox("Port and Baud Rate")
        port_baud_group = QGroupBox()
        port_baud_layout = QVBoxLayout()

        # 原因不详，这里的路径需要使用绝对路径，否则打包后无法显示图片，还需要将路径中的“\”替换为“/”
        image_path = resource_path('gosuncn2.png').replace('\\', '/')
        # image_path = resource_path('gosuncn1.png')
        # Use the verified path in the stylesheet
        port_baud_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid gray;
                border-radius: 5px;
                margin-top: 0px;
                background-image: url({image_path});
                background-repeat: no-repeat;
                background-position: right centor;
            }}
        """)

        # Port selection
        port_layout = QHBoxLayout()
        port_label = QLabel('Port:      ')
        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(100)
        self.port_combo.addItems([port.device for port in serial.tools.list_ports.comports()])
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_combo)
        port_layout.addStretch(1)  # Add stretch to align left

        # Baud rate selection
        baudrate_layout = QHBoxLayout()
        baudrate_label = QLabel('Baud Rate: ')
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.setFixedWidth(100)
        self.baudrate_combo.addItems(['115200', '9600', '19200', '38400', '57600', '460800', '921600'])
        baudrate_layout.addWidget(baudrate_label)
        baudrate_layout.addWidget(self.baudrate_combo)
        baudrate_layout.addStretch(1)  # Add stretch to align left

        # Baud rate selection 333
        # 整合串口和波特率样式框
        port_baud_layout.addLayout(port_layout)
        port_baud_layout.addLayout(baudrate_layout)
        port_baud_group.setLayout(port_baud_layout)

        # Filter input
        filter_layout = QHBoxLayout()
        filter_label = QLabel('Filter:')
        self.filter_input = QLineEdit()
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_input)

        # Connect/Disconnect buttons
        button_layout = QHBoxLayout()
        self.connect_button = QPushButton('Connect')
        self.disconnect_button = QPushButton('Disconnect')
        self.save_button = QPushButton('Save Log')
        self.clear_button = QPushButton('Clear information')
        self.disconnect_button.setEnabled(False)
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.clear_button)

        # Add this in the initUI method
        self.save_filtered_checkbox = QCheckBox('Save Filtered Log')
        self.save_filtered_checkbox.setChecked(False)  # Default to unchecked
        button_layout.addWidget(self.save_filtered_checkbox)

        # Apply shadow effect to buttons 444
        # 设置按钮阴影效果和点击效果
        button_style = """
        QPushButton {
            border: 1px solid black;
            border-radius: 5px;
            padding: 5px;
            background-color: white;
        }
        QPushButton:hover {
            background-color: lightblue;
        }
        QPushButton:pressed {
            background-color: lightgray;
        }
        """
        self.connect_button.setStyleSheet(button_style)
        self.disconnect_button.setStyleSheet(button_style)
        self.save_button.setStyleSheet(button_style)
        self.clear_button.setStyleSheet(button_style)

        # Log display
        # ====== 优化点：使用 QPlainTextEdit 替换 QTextEdit，保持变量名不变 ======
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        # 关闭 undo/redo 缓存，防止内存随着操作记录增长
        self.log_text.setUndoRedoEnabled(False)

        # Command input
        command_layout = QVBoxLayout()
        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        # 去除命令前后空格
        self.command_input.textChanged.connect(lambda: self.command_input.setText(self.command_input.text().strip()))
        self.send_button = QPushButton('Send')
        self.newline_checkbox = QCheckBox('Send with Enter')
        self.newline_checkbox.setChecked(True)
        command_input_layout.addWidget(self.command_input)
        command_input_layout.addWidget(self.send_button)
        command_input_layout.addWidget(self.newline_checkbox)

        self.command_history_combo = QComboBox()
        self.command_history_combo.currentIndexChanged.connect(self.load_selected_command)
        command_layout.addLayout(command_input_layout)
        command_layout.addWidget(self.command_history_combo)

        # self.left_layout.addLayout(port_layout)
        # self.left_layout.addLayout(baudrate_layout)
        # 设置串口和波特率背景样式
        self.left_layout.addWidget(port_baud_group)
        self.left_layout.addLayout(filter_layout)
        self.left_layout.addLayout(button_layout)
        self.left_layout.addWidget(self.log_text)
        self.left_layout.addLayout(command_layout)

        # Fixed AT commands section
        self.fixed_at_group = QGroupBox("Save AT Commands")
        fixed_at_layout = QFormLayout()
        self.fixed_at_inputs = []

        for i in range(13):
            at_input = QLineEdit()
            at_input.setFixedWidth(212)
            at_input.textChanged.connect(self.save_fixed_at_commands)
            send_button = QPushButton(f'Send {i + 1}')
            send_button.setFixedWidth(50)
            send_button.clicked.connect(lambda _, inp=at_input: self.send_fixed_command(inp))
            fixed_at_layout.addRow(at_input, send_button)
            self.fixed_at_inputs.append(at_input)

        self.fixed_at_group.setLayout(fixed_at_layout)
        self.fixed_at_group.setVisible(False)  # Hide by default

        # Scroll area for Fixed AT Commands
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.fixed_at_group)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVisible(False)  # Hide by default

        # Side button for Fixed AT Commands
        self.side_button = QPushButton('>')
        self.side_button.setFixedWidth(20)
        self.side_button.setCheckable(True)
        self.side_button.clicked.connect(self.toggle_fixed_at_commands)

        self.right_layout.addWidget(self.side_button)
        self.right_layout.addWidget(self.scroll_area)

        self.main_layout.addLayout(self.left_layout, 2)  # Set stretch factor to 2
        self.main_layout.addLayout(self.right_layout, 1)  # Set stretch factor to 1
        self.setLayout(self.main_layout)

        self.connect_button.clicked.connect(self.connect_serial)
        self.disconnect_button.clicked.connect(self.disconnect_serial)
        self.save_button.clicked.connect(self.save_log)
        self.send_button.clicked.connect(self.send_command)
        self.clear_button.clicked.connect(self.clear_log)

    # 关于工具的简介
    def show_modify(self):
        modify_text = ("V 1.0\n"
                       "1.增加了串口及串口波特率选择；\n"
                       "2.增加了串口连接、断开、保存日志功能；\n\n"
                       "V 2.0\n"
                       "1.增加AT命令发送功能及历史记录；\n"
                       "2.扩展侧栏，修改窗口展开关闭大小；\n\n"
                       "V 3.0\n"
                       "1.修改展开后窗口大小锁定问题；\n"
                       "2.增加过滤日志按需保存功能；\n\n"
                       "V 4.0\n"
                       "1.修改固定按键圆角样式；\n"
                       "2.增加使用说明，修改记录，版本信息功能；\n"
                       "3.调整端口、波特率布局，增加gosuncn logo；\n\n"
                       "V 5.0\n"
                       "1.修改串口波特率选择框左移对齐；\n"
                       "2.修改logo右对齐；\n\n"
                       "V 6.0\n"
                       "1.增加清理显示框按键；\n"
                       "2.增加历史发送AT保留文件去重功能；\n"
                       "3.增加AT命令输入框前后空格自动去除功能；\n"
                       "4.增加使用错误端口/波特率弹窗提醒功能；\n\n"
                       "V 7.0\n"
                       "1.增加 波特率/端口 修改后自动重连功能；\n"
                       "2.解决串口波特率选择非实际波特率异常卡死问题；\n\n"
                       "V 8.0\n"
                       "1.修改log_text窗口最大显示3000行，超过自动清空；\n"
                       "2.增加log保存路径记忆功能\n\n"
                       "V 9.0\n"
                       "1.增加AT命令打印在log_text区域功能；\n"
                       "2.增加发送AT命令颜色显示功能；\n"
                       )
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(modify_text)
        text_edit.setFixedWidth(400)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        dialog = QDialog(self)
        dialog.setWindowTitle('Modify')
        dialog_layout = QVBoxLayout()
        dialog_layout.addWidget(text_edit)
        dialog.setLayout(dialog_layout)
        dialog.exec_()

        # QMessageBox.about(self, 'Modify', modify_text)

    def show_instructions(self):
        instructions_text = ("使用说明:\n\n"
                             "1.展开侧边栏，可以打开AT面板，AT面板历史AT会保存；\n"
                             "2.底部命令发送框默认带回车换行发送；\n"
                             "3.过滤框可以输入关键字，过滤日志显示；过滤关键字段使用“，”进行分隔，多个过滤字段最后一个关键字后不用带“，”；\n"
                             "4.保存日志默认保存所有日志，勾选过滤日志，只保存过滤后的日志；\n"
                             )
        QMessageBox.information(self, 'Instructions', instructions_text)

    def show_about(self):
        about_text = ("<div "
                      "style='text-align: left;'>"
                      "Rich link Serial Port Tool<br><br>"
                      "Version " + version + "<br><br>"
                                             "Developed by Mulinxi<br><br>"
                                             "Compilation date " + Compilation_date +
                      "</div>")
        QMessageBox.about(self, 'About', about_text)

    # 问题点
    def load_selected_command(self):
        selected_command = self.command_history_combo.currentText()
        self.command_input.setText(selected_command)

    def toggle_fixed_at_commands(self):
        if self.side_button.isChecked():
            self.scroll_area.setVisible(True)
            self.side_button.setText('<')
            self.setFixedSize(900, 500)  # Increase the width by 300
            self.setMaximumSize(16777215, 16777215)  # Remove maximum size constraint
        else:
            self.scroll_area.setVisible(False)
            self.side_button.setText('>')
            self.setFixedSize(600, 500)  # Restore the original width
            self.setMaximumSize(16777215, 16777215)  # Remove maximum size constraint

    def is_valid_baudrate(self, baudrate):
        valid_baudrates = ['115200', '9600', '19200', '38400', '57600', '460800', '921600']
        return baudrate in valid_baudrates

    def connect_serial(self):
        port = self.port_combo.currentText()
        baudrate = self.baudrate_combo.currentText()
        if not self.is_valid_baudrate(baudrate):
            QMessageBox.warning(self, 'Invalid Baud Rate', 'The selected baud rate is not valid.')
            return
        baudrate = int(baudrate)
        self.serial_thread = SerialReader(port, baudrate)
        self.serial_thread.data_received.connect(self.update_log)
        self.serial_thread.error_occurred.connect(self.show_error)
        self.serial_thread.start()
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)

        # Start a QTimer to check log_text after 5 seconds
        # ====== 优化点：如果已有 check_log_timer，先停掉，避免重复创建 ======
        if hasattr(self, 'check_log_timer') and self.check_log_timer:
            try:
                if self.check_log_timer.isActive():
                    self.check_log_timer.stop()
            except Exception:
                pass
        self.check_log_timer = QTimer(self)
        self.check_log_timer.timeout.connect(self.check_log_content)
        self.check_log_timer.setSingleShot(True)
        self.check_log_timer.start(5000)

        # Connect the baud rate combo box to the change_baudrate method
        self.baudrate_combo.currentIndexChanged.connect(self.change_baudrate)
        self.port_combo.currentIndexChanged.connect(self.change_port)
        self.last_baudrate = baudrate  # Initialize the last baud rate
        self.last_port = port  # Initialize the last port

    def change_baudrate(self):
        if self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open:
            new_baudrate = self.baudrate_combo.currentText()
            if not self.is_valid_baudrate(new_baudrate):
                QMessageBox.warning(self, 'Invalid Baud Rate', 'The selected baud rate is not valid.')
                return
            new_baudrate = int(new_baudrate)

            # 只有波特率不同才需要重新设置
            if new_baudrate != self.last_baudrate:
                # 关闭现有串口
                self.disconnect_serial()

                # 更新波特率
                self.last_baudrate = new_baudrate
                # 改为纯文本输出，避免 HTML 解析导致内存增大
                self._log_buffer.append(f"Baud rate changed to {new_baudrate}")
                self._log_buffer.append("If there is no output, please check the baud rate or port")

                # 重新连接串口
                self.connect_serial()

    def change_port(self):
        if self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open:
            new_port = self.port_combo.currentText()
            if new_port != self.last_port:
                # 关闭现有串口
                self.disconnect_serial()

                # 更新端口
                self.last_port = new_port
                # 改为纯文本输出，避免 HTML 解析导致内存增大
                self._log_buffer.append(f"Port changed to {new_port}")
                self._log_buffer.append("If there is no output, please check the baud rate or port")

                # 重新连接串口
                self.connect_serial()

    def disconnect_serial(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None  # Release the thread object
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

        # 当断开时，确保日志文件被关闭（如果存在）
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None

    def update_log(self, data):
        filter_text = self.filter_input.text()
        filters = [f.strip() for f in filter_text.split(',') if f.strip()]
        # 使用缓冲，后续由定时器批量 flush 到 UI
        if not filters:
            # 如果没有过滤条件，则全部加入缓冲
            self._log_buffer.append(data)
        else:
            # 仅当任一过滤字段匹配时加入缓冲
            if any(f in data for f in filters):
                self._log_buffer.append(data)

        # 写文件按原逻辑（注意保存为纯文本）
        if self.log_file:
            if self.save_filtered_checkbox.isChecked():
                if not filters or any(f in data for f in filters):
                    self.log_file.write(data + '\n')
            else:
                self.log_file.write(data + '\n')
            self.log_file.flush()

    # 批量刷新缓冲到 UI（在主线程执行）
    def _flush_log_buffer(self):
        if not self._log_buffer:
            return
        # 将缓冲合并为一段文本一次性追加，减少 append 次数
        to_add = '\n'.join(self._log_buffer)
        self._log_buffer.clear()
        # 使用 QPlainTextEdit 的 appendPlainText（比 setPlainText 更高效——只是尾部追加）
        self.log_text.appendPlainText(to_add)
        self.check_log_threshold()

    # 超过最大显示，则自动触发一次清理窗口操作
    def check_log_threshold(self):
        # QPlainTextEdit 使用 blockCount 获取行数
        try:
            lines = self.log_text.blockCount()
        except Exception:
            # 兼容性保护
            lines = len(self.log_text.toPlainText().split('\n'))
        if lines > self.max_log_lines:
            self.clear_log()  # Clear log if it exceeds the maximum number of lines

    # # 进行log显示的行数限制
    # def trim_log(self):
    #     log_lines = self.log_text.toPlainText().split('\n')
    #     if len(log_lines) > self.max_log_lines:
    #         self.log_text.setPlainText('\n'.join(log_lines[-self.max_log_lines:]))

    def show_error(self, error_message):
        # 改为纯文本输出
        self._log_buffer.append(f"Error: {error_message}")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def save_log(self):
        options = QFileDialog.Options()
        default_dir = self.last_log_dir if self.last_log_dir else ''
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Log", "", "Text Files (*.txt);;All Files (*)",
                                                   options=options)
        if file_path:
            # 如果已有打开的 log_file，先关闭
            if self.log_file:
                try:
                    self.log_file.close()
                except Exception:
                    pass
            # 以 w 模式覆盖保存当前显示内容
            self.log_file = open(file_path, 'w', encoding='utf-8')
            try:
                self.log_file.write(self.log_text.toPlainText())
                self.log_file.flush()
            except Exception:
                pass
            self.last_log_dir = os.path.dirname(file_path)  # Update the last used directory


    def send_command(self):
        command = self.command_input.text().strip()  # Strip leading and trailing whitespace
        if not command.strip():  # Check if the command is empty or whitespace
            return
        if self.newline_checkbox.isChecked():
            command += '\r\n'
        if self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open:
            self.serial_thread.serial.write(command.encode('utf-8'))
            self.command_history_combo.addItem(command)
            self.save_command_history(command)
            # 打印发送的命令到日志显示区域（改为纯文本并走缓冲）
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # self.log_text.append(f"{timestamp} - Sent: {command.strip()}")
            self._log_buffer.append(f"{timestamp} - Sent: {command.strip()}")

    def send_fixed_command(self, at_input):
        # 确保发送的 AT 命令带上回车换行
        command = at_input.text().strip() + '\r\n'  # Strip leading and trailing whitespace
        if self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open:
            self.serial_thread.serial.write(command.encode('utf-8'))
            # 打印发送的 AT 命令到日志显示区域（走缓冲，纯文本）
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self._log_buffer.append(f"{timestamp} - Sent: {command.strip()}")

    def load_fixed_at_commands(self):
        if os.path.exists(self.fixed_at_file):
            with open(self.fixed_at_file, 'r', encoding='utf-8') as file:
                for i, line in enumerate(file):
                    if i < len(self.fixed_at_inputs):
                        self.fixed_at_inputs[i].setText(line.strip())

    def save_fixed_at_commands(self):
        with open(self.fixed_at_file, 'w', encoding='utf-8') as file:
            for at_input in self.fixed_at_inputs:
                file.write(at_input.text() + '\n')

    def load_command_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                for line in reversed(lines):
                    self.command_history_combo.addItem(line.strip())

    def save_command_history(self, command):
        cleaned_command = command.replace('\r', '').replace('\n', '')
        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w', encoding='utf-8') as file:
                file.write(cleaned_command + '\n')
        else:
            with open(self.history_file, 'r+', encoding='utf-8') as file:
                lines = file.readlines()
                if cleaned_command + '\n' not in lines:
                    file.write(cleaned_command + '\n')

    # Define the clear_log method
    def clear_log(self):
        # 直接清空 QPlainTextEdit（会释放文本内容）
        self.log_text.clear()

    # 增加一个检测日志为空的提示
    def check_log_content(self):
        if self.log_text.toPlainText().strip() == "":
            QMessageBox.warning(self, 'No Data Received', 'Please check the port or baud rate')
            self.disconnect_serial()
            self.disconnect_button.setEnabled(False)
            self.connect_button.setEnabled(True)

    def closeEvent(self, event):
        # 程序退出时，确保线程停止，定时器停止，日志文件关闭
        try:
            if self.serial_thread:
                self.serial_thread.stop()
                self.serial_thread.wait(timeout=2000)
        except Exception:
            pass
        try:
            if self._flush_timer and self._flush_timer.isActive():
                self._flush_timer.stop()
        except Exception:
            pass
        try:
            if self.check_log_timer and self.check_log_timer.isActive():
                self.check_log_timer.stop()
        except Exception:
            pass
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        event.accept()


# 春哥牛逼
# 这个函数 resource_path 是在使用 PyInstaller 打包 Python 程序时常见的一个辅助函数，它的作用是获取资源文件的路径，
# 无论是在开发环境还是在打包后的应用程序中。
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # app.setWindowIcon(QIcon(resource_path("icon.ico"))) #春哥牛逼
    tool = SerialPortTool()
    tool.show()
    sys.exit(app.exec_())
