import serial
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from datetime import datetime
import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QTextEdit, QLabel,
                             QLineEdit, QFileDialog, QCheckBox, QGroupBox, QFormLayout, QScrollArea, QMenuBar, QMenu,
                             QAction, QMessageBox, QDialog)
import serial.tools.list_ports
import os
from PyQt5.QtGui import QIcon

version = "10.0"
Compilation_date = "2026-6-17 10:35:30"


class SerialReader(QThread):
    """串口读取线程：负责后台读取串口数据，避免阻塞主界面"""

    data_received = pyqtSignal(str)      # 接收到一行完整数据后发送给主线程
    error_occurred = pyqtSignal(str)     # 串口异常时发送错误信息

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.buffer = ""                 # 缓存未接收完整的一行数据
        self.max_buffer_size = 10240      # 防止没有换行符时 buffer 无限增长

    def run(self):
        """线程入口：循环读取串口数据，并按换行符拆成一行行日志"""
        try:
            self.serial = serial.Serial(self.port, self.baudrate)
            self.running = True

            while self.running:
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)

                    # 优先按 utf-8 解码，失败后按 latin-1 兜底
                    try:
                        decoded_data = data.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_data = data.decode('latin-1')

                    self.buffer += decoded_data

                    # 防止设备长期不发 \n 导致 buffer 越来越大
                    if len(self.buffer) > self.max_buffer_size:
                        self.buffer = self.buffer[-self.max_buffer_size:]

                    # 每遇到一个换行符，就认为是一条完整日志
                    while '\n' in self.buffer:
                        line, self.buffer = self.buffer.split('\n', 1)
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        self.data_received.emit(f"{timestamp} - {line.strip()}")

        except serial.SerialException as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        """停止线程并关闭串口"""
        self.running = False
        if self.serial and self.serial.is_open:
            self.serial.close()


class SerialPortTool(QWidget):
    """主窗口：串口连接、日志显示、AT命令发送、日志保存"""

    def __init__(self):
        super().__init__()
        self.serial_thread = None
        self.log_file = None
        self.history_file = 'at_command_history.txt'
        self.fixed_at_file = 'fixed_at_commands.txt'
        self.max_log_lines = 3000          # 日志框最大保留行数
        self.last_log_dir = ''
        self.initUI()
        self.load_command_history()
        self.load_fixed_at_commands()

    def initUI(self):
        """初始化界面布局和信号连接"""
        self.setWindowTitle('瑞联串口工具 V' + version + '-Mangetic ★★★★★广告位招租★★★★★')
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setGeometry(500, 300, 600, 500)

        self.main_layout = QHBoxLayout()
        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()

        # 菜单栏
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
        modify_action.triggered.connect(self.show_modify)
        instructions_action.triggered.connect(self.show_instructions)
        about_action.triggered.connect(self.show_about)

        # 串口和波特率区域
        port_baud_group = QGroupBox()
        port_baud_layout = QVBoxLayout()
        image_path = resource_path('gosuncn2.png').replace('\\', '/')
        port_baud_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid gray;
                border-radius: 5px;
                margin-top: 0px;
                background-image: url({image_path});
                background-repeat: no-repeat;
                background-position: right center;
            }}
        """)

        port_layout = QHBoxLayout()
        port_label = QLabel('Port:      ')
        self.port_combo = QComboBox()
        self.port_combo.setFixedWidth(100)
        self.port_combo.addItems([port.device for port in serial.tools.list_ports.comports()])
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_combo)
        port_layout.addStretch(1)

        baudrate_layout = QHBoxLayout()
        baudrate_label = QLabel('Baud Rate: ')
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.setFixedWidth(100)
        self.baudrate_combo.addItems(['115200', '9600', '19200', '38400', '57600', '460800', '921600'])
        baudrate_layout.addWidget(baudrate_label)
        baudrate_layout.addWidget(self.baudrate_combo)
        baudrate_layout.addStretch(1)

        port_baud_layout.addLayout(port_layout)
        port_baud_layout.addLayout(baudrate_layout)
        port_baud_group.setLayout(port_baud_layout)

        # 日志过滤输入框，多个关键字用英文逗号分隔
        filter_layout = QHBoxLayout()
        filter_label = QLabel('Filter:')
        self.filter_input = QLineEdit()
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_input)

        # 按钮区域
        button_layout = QHBoxLayout()
        self.connect_button = QPushButton('Connect')
        self.disconnect_button = QPushButton('Disconnect')
        self.save_button = QPushButton('Save Log')
        self.clear_button = QPushButton('Clear information')
        self.disconnect_button.setEnabled(False)
        self.save_filtered_checkbox = QCheckBox('Save Filtered Log')
        self.save_filtered_checkbox.setChecked(False)
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.save_filtered_checkbox)

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
        for btn in [self.connect_button, self.disconnect_button, self.save_button, self.clear_button]:
            btn.setStyleSheet(button_style)

        # 日志显示框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        # 关键优化：让 Qt 自动限制最大行数，避免每次 toPlainText().split() 复制全部日志
        self.log_text.document().setMaximumBlockCount(self.max_log_lines)

        # 禁止 QTextEdit 默认缩放行为
        self.log_text.zoomIn = lambda *args, **kwargs: None
        self.log_text.zoomOut = lambda *args, **kwargs: None

        # 命令输入区域
        command_layout = QVBoxLayout()
        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()

        # 自动去除输入框前后空格
        self.command_input.textChanged.connect(lambda: self.command_input.setText(self.command_input.text().strip()))

        self.send_button = QPushButton('Send')
        self.newline_checkbox = QCheckBox('Send with Enter')
        self.newline_checkbox.setChecked(True)
        command_input_layout.addWidget(self.command_input)
        command_input_layout.addWidget(self.send_button)
        command_input_layout.addWidget(self.newline_checkbox)

        # 历史 AT 命令下拉框
        self.command_history_combo = QComboBox()
        self.command_history_combo.currentIndexChanged.connect(self.load_selected_command)
        command_layout.addLayout(command_input_layout)
        command_layout.addWidget(self.command_history_combo)

        self.left_layout.addWidget(port_baud_group)
        self.left_layout.addLayout(filter_layout)
        self.left_layout.addLayout(button_layout)
        self.left_layout.addWidget(self.log_text)
        self.left_layout.addLayout(command_layout)

        # 右侧固定 AT 命令区域
        self.fixed_at_group = QGroupBox("Save AT Commands")
        fixed_at_layout = QFormLayout()
        self.fixed_at_inputs = []
        for i in range(13):
            at_input = QLineEdit()
            at_input.setFixedWidth(212)
            at_input.textChanged.connect(self.save_fixed_at_commands)
            send_btn = QPushButton(f'Send {i + 1}')
            send_btn.setFixedWidth(50)
            send_btn.clicked.connect(lambda _, inp=at_input: self.send_fixed_command(inp))
            fixed_at_layout.addRow(at_input, send_btn)
            self.fixed_at_inputs.append(at_input)
        self.fixed_at_group.setLayout(fixed_at_layout)
        self.fixed_at_group.setVisible(False)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.fixed_at_group)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVisible(False)

        # 侧边栏展开/收起按钮
        self.side_button = QPushButton('>')
        self.side_button.setFixedWidth(20)
        self.side_button.setCheckable(True)
        self.side_button.clicked.connect(self.toggle_fixed_at_commands)

        self.right_layout.addWidget(self.side_button)
        self.right_layout.addWidget(self.scroll_area)

        self.main_layout.addLayout(self.left_layout, 2)
        self.main_layout.addLayout(self.right_layout, 1)
        self.setLayout(self.main_layout)

        # 按钮信号绑定
        self.connect_button.clicked.connect(self.connect_serial)
        self.disconnect_button.clicked.connect(self.disconnect_serial)
        self.save_button.clicked.connect(self.save_log)
        self.send_button.clicked.connect(self.send_command)
        self.clear_button.clicked.connect(self.clear_log)

    def show_modify(self):
        """显示版本修改记录"""
        modify_text = ("V 1.0\n1.增加了串口及串口波特率选择；\n2.增加了串口连接、断开、保存日志功能；\n\n"
                       "V 2.0\n1.增加AT命令发送功能及历史记录；\n2.扩展侧栏，修改窗口展开关闭大小；\n\n"
                       "V 3.0\n1.修改展开后窗口大小锁定问题；\n2.增加过滤日志按需保存功能；\n\n"
                       "V 4.0\n1.修改固定按键圆角样式；\n2.增加使用说明，修改记录，版本信息功能；\n3.调整端口、波特率布局，增加gosuncn logo；\n\n"
                       "V 5.0\n1.修改串口波特率选择框左移对齐；\n2.修改logo右对齐；\n\n"
                       "V 6.0\n1.增加清理显示框按键；\n2.增加历史发送AT保留文件去重功能；\n3.增加AT命令输入框前后空格自动去除功能；\n4.增加使用错误端口/波特率弹窗提醒功能；\n\n"
                       "V 7.0\n1.增加 波特率/端口 修改后自动重连功能；\n2.解决串口波特率选择非实际波特率异常卡死问题；\n\n"
                       "V 8.0\n1.修改log_text窗口最大显示3000行，超过自动清空；\n2.增加log保存路径记忆功能\n\n"
                       "V 9.0\n1.增加AT命令打印在log_text区域功能；\n2.增加发送AT命令颜色显示功能；\n"
                       "V 10.0\n1.轻量化，防止buffer被撑爆-有可能不稳定\n")
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

    def show_instructions(self):
        """显示使用说明"""
        instructions_text = ("使用说明:\n\n1.展开侧边栏，可以打开AT面板，AT面板历史AT会保存；\n"
                             "2.底部命令发送框默认带回车换行发送；\n"
                             "3.过滤框可以输入关键字，过滤日志显示；过滤关键字段使用“,”进行分隔；\n"
                             "4.保存日志默认保存所有日志，勾选过滤日志，只保存过滤后的日志；\n")
        QMessageBox.information(self, 'Instructions', instructions_text)

    def show_about(self):
        """显示软件版本信息"""
        about_text = ("<div style='text-align: left;'>Rich link Serial Port Tool<br><br>"
                      "Version " + version + "<br><br>Developed by Mulinxi<br><br>"
                      "Compilation date " + Compilation_date + "</div>")
        QMessageBox.about(self, 'About', about_text)

    def load_selected_command(self):
        """选择历史 AT 命令后，自动填充到底部输入框"""
        selected_command = self.command_history_combo.currentText()
        self.command_input.setText(selected_command)

    def toggle_fixed_at_commands(self):
        """展开或收起右侧固定 AT 命令面板"""
        if self.side_button.isChecked():
            self.scroll_area.setVisible(True)
            self.side_button.setText('<')
            self.setFixedSize(900, 500)
            self.setMaximumSize(16777215, 16777215)
        else:
            self.scroll_area.setVisible(False)
            self.side_button.setText('>')
            self.setFixedSize(600, 500)
            self.setMaximumSize(16777215, 16777215)

    def is_valid_baudrate(self, baudrate):
        """校验波特率是否在允许范围内"""
        valid_baudrates = ['115200', '9600', '19200', '38400', '57600', '460800', '921600']
        return baudrate in valid_baudrates

    def connect_serial(self):
        """连接串口并启动后台读取线程"""
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

        self.last_baudrate = baudrate
        self.last_port = port

    def disconnect_serial(self):
        """断开串口连接；保留 log_file，不关闭，方便重新连接后继续写同一个日志文件"""
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def update_log(self, data):
        """更新日志显示框，并根据设置写入日志文件"""
        filter_text = self.filter_input.text()

        # 过滤空关键字，避免 [''] 这种情况造成逻辑不清晰
        filters = [f.strip() for f in filter_text.split(',') if f.strip()]

        # 没有过滤条件时显示全部；有过滤条件时只显示匹配内容
        matched = not filters or any(f in data for f in filters)

        if matched:
            self.log_text.append(data)

        # 保存日志：未勾选过滤保存时保存全部；勾选后只保存匹配日志
        if self.log_file:
            if self.save_filtered_checkbox.isChecked():
                if matched:
                    self.log_file.write(data + '\n')
            else:
                self.log_file.write(data + '\n')

            self.log_file.flush()

    def show_error(self, error_message):
        """串口错误提示，同时恢复连接按钮状态"""
        self.log_text.append(f"Error: {error_message}")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def save_log(self):
        """选择日志保存文件；后续串口日志会继续写入该文件"""
        options = QFileDialog.Options()
        default_dir = self.last_log_dir if self.last_log_dir else ''

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log",
            default_dir,
            "Text Files (*.txt);;All Files (*)",
            options=options
        )

        if file_path:
            # 如果之前已经打开过日志文件，先关闭旧文件，避免文件句柄泄漏
            if self.log_file:
                self.log_file.close()

            self.log_file = open(file_path, 'w', encoding='utf-8')
            self.log_file.write(self.log_text.toPlainText())
            self.log_file.flush()
            self.last_log_dir = os.path.dirname(file_path)

    def send_command(self):
        """发送底部输入框中的 AT 命令，并在日志框中用蓝色显示"""
        command = self.command_input.text().strip()
        if not command:
            return

        if self.newline_checkbox.isChecked():
            command += '\r\n'

        if self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open:
            self.serial_thread.serial.write(command.encode('utf-8'))
            self.command_history_combo.addItem(command)
            self.save_command_history(command)

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.log_text.append(f"<span style='color:blue;'>{timestamp} - Sent: {command.strip()}</span>")

    def send_fixed_command(self, at_input):
        """发送右侧固定 AT 命令，并在日志框中用蓝色显示"""
        command = at_input.text().strip() + '\r\n'

        if self.serial_thread and self.serial_thread.serial and self.serial_thread.serial.is_open:
            self.serial_thread.serial.write(command.encode('utf-8'))

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.log_text.append(f"<span style='color:blue;'>{timestamp} - Sent: {command.strip()}</span>")

    def load_fixed_at_commands(self):
        """启动时加载右侧固定 AT 命令"""
        if os.path.exists(self.fixed_at_file):
            with open(self.fixed_at_file, 'r', encoding='utf-8') as file:
                for i, line in enumerate(file):
                    if i < len(self.fixed_at_inputs):
                        self.fixed_at_inputs[i].setText(line.strip())

    def save_fixed_at_commands(self):
        """固定 AT 命令输入框变化时，自动保存到本地文件"""
        with open(self.fixed_at_file, 'w', encoding='utf-8') as file:
            for at_input in self.fixed_at_inputs:
                file.write(at_input.text() + '\n')

    def load_command_history(self):
        """启动时加载历史发送过的 AT 命令"""
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                for line in reversed(lines):
                    self.command_history_combo.addItem(line.strip())

    def save_command_history(self, command):
        """保存 AT 命令历史，并自动去重"""
        cleaned_command = command.replace('\r', '').replace('\n', '')

        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w', encoding='utf-8') as file:
                file.write(cleaned_command + '\n')
        else:
            with open(self.history_file, 'r+', encoding='utf-8') as file:
                lines = file.readlines()
                if cleaned_command + '\n' not in lines:
                    file.write(cleaned_command + '\n')

    def clear_log(self):
        """清空日志显示框，不影响已经打开的日志文件"""
        self.log_text.clear()

    def check_log_content(self):
        """检查是否接收到数据；当前代码中未主动调用，保留原功能"""
        if self.log_text.toPlainText().strip() == "":
            QMessageBox.warning(self, 'No Data Received', 'Please check the port or baud rate')
            self.disconnect_serial()
            self.disconnect_button.setEnabled(False)
            self.connect_button.setEnabled(True)

    def closeEvent(self, event):
        """关闭窗口时释放串口线程和日志文件资源"""
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait()
            self.serial_thread = None

        if self.log_file:
            self.log_file.close()
            self.log_file = None

        event.accept()

    def wheelEvent(self, event):
        """禁止 Ctrl + 鼠标滚轮缩放"""
        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            event.ignore()
            return
        super().wheelEvent(event)


# 辅助函数：兼容 PyInstaller 打包后的资源路径

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    tool = SerialPortTool()
    tool.show()
    sys.exit(app.exec_())
