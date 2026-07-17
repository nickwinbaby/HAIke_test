import csv
import os
import sys
from datetime import datetime

import psutil
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_TITLE = "进程物理内存监控工具"


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class ProcessMemoryMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sample_memory)
        self.peak_rss = 0
        self.csv_file = None
        self.csv_writer = None
        self.text_log_file = None
        self.init_ui()

    def init_ui(self):
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setWindowTitle(APP_TITLE)
        self.setGeometry(520, 260, 760, 520)
        self.setMinimumSize(680, 460)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)
        self.setLayout(main_layout)

        target_group = QGroupBox("Target")
        target_layout = QGridLayout()

        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("输入 PID 或进程名，例如 1234 或 串口log过滤")

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setValue(2)
        self.interval_spin.setSuffix(" s")

        self.log_csv_checkbox = QCheckBox("Save CSV")
        self.csv_path_input = QLineEdit()
        self.csv_path_input.setReadOnly(True)
        self.csv_path_input.setPlaceholderText("未选择 CSV 文件")
        self.choose_csv_button = QPushButton("Browse")

        self.save_log_checkbox = QCheckBox("Save Log")
        self.log_path_input = QLineEdit()
        self.log_path_input.setReadOnly(True)
        self.log_path_input.setPlaceholderText("未选择日志文件")
        self.choose_log_button = QPushButton("Browse")

        target_layout.addWidget(QLabel("PID / Name"), 0, 0)
        target_layout.addWidget(self.target_input, 0, 1, 1, 4)
        target_layout.addWidget(QLabel("Interval"), 0, 5)
        target_layout.addWidget(self.interval_spin, 0, 6)
        target_layout.addWidget(self.log_csv_checkbox, 1, 0)
        target_layout.addWidget(self.csv_path_input, 1, 1, 1, 5)
        target_layout.addWidget(self.choose_csv_button, 1, 6)
        target_layout.addWidget(self.save_log_checkbox, 2, 0)
        target_layout.addWidget(self.log_path_input, 2, 1, 1, 5)
        target_layout.addWidget(self.choose_log_button, 2, 6)
        target_group.setLayout(target_layout)
        main_layout.addWidget(target_group)

        metrics_group = QGroupBox("Physical Memory")
        metrics_layout = QGridLayout()

        self.current_label = QLabel("-- MB")
        self.peak_label = QLabel("-- MB")
        self.process_count_label = QLabel("0")
        self.status_label = QLabel("Stopped")

        for label in [self.current_label, self.peak_label, self.process_count_label, self.status_label]:
            label.setObjectName("metricValue")

        metrics_layout.addWidget(QLabel("Current RSS"), 0, 0)
        metrics_layout.addWidget(self.current_label, 0, 1)
        metrics_layout.addWidget(QLabel("Peak RSS"), 0, 2)
        metrics_layout.addWidget(self.peak_label, 0, 3)
        metrics_layout.addWidget(QLabel("Matched Processes"), 1, 0)
        metrics_layout.addWidget(self.process_count_label, 1, 1)
        metrics_layout.addWidget(QLabel("Status"), 1, 2)
        metrics_layout.addWidget(self.status_label, 1, 3)
        metrics_group.setLayout(metrics_layout)
        main_layout.addWidget(metrics_group)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.clear_button = QPushButton("Clear")
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch(1)
        main_layout.addLayout(button_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        main_layout.addWidget(self.log_text, 1)

        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.clear_button.clicked.connect(self.clear_log)
        self.choose_csv_button.clicked.connect(self.choose_csv_file)
        self.choose_log_button.clicked.connect(self.choose_log_file)

        self.apply_style()

    def apply_style(self):
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI", "Microsoft YaHei";
                font-size: 10pt;
            }
            QLineEdit, QTextEdit, QSpinBox {
                border: 1px solid #b8c0cc;
                border-radius: 4px;
                padding: 4px;
                background: #ffffff;
            }
            QPushButton {
                border: 1px solid #9aa7b7;
                border-radius: 4px;
                padding: 5px 12px;
                background: #f4f7fb;
            }
            QPushButton:hover {
                background: #e6eef8;
            }
            QPushButton:pressed {
                background: #d9e5f2;
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
            QLabel#metricValue {
                font-size: 13pt;
                font-weight: 600;
                color: #264766;
            }
            """
        )

    def choose_csv_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if file_path:
            self.csv_path_input.setText(file_path)
            self.log_csv_checkbox.setChecked(True)

    def choose_log_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if file_path:
            self.log_path_input.setText(file_path)
            self.save_log_checkbox.setChecked(True)

    def start_monitoring(self):
        target = self.target_input.text().strip()
        if not target:
            QMessageBox.warning(self, "Missing Target", "请输入 PID 或进程名。")
            return

        if self.log_csv_checkbox.isChecked() and not self.csv_path_input.text().strip():
            self.choose_csv_file()
            if not self.csv_path_input.text().strip():
                return

        if self.save_log_checkbox.isChecked() and not self.log_path_input.text().strip():
            self.choose_log_file()
            if not self.log_path_input.text().strip():
                return

        self.peak_rss = 0
        self.open_csv_if_needed()
        self.open_text_log_if_needed()
        self.target_input.setEnabled(False)
        self.interval_spin.setEnabled(False)
        self.log_csv_checkbox.setEnabled(False)
        self.choose_csv_button.setEnabled(False)
        self.save_log_checkbox.setEnabled(False)
        self.choose_log_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Running")
        self.append_log("Monitoring started")
        self.sample_memory()
        self.timer.start(self.interval_spin.value() * 1000)

    def stop_monitoring(self):
        self.timer.stop()
        self.close_csv()
        self.close_text_log()
        self.target_input.setEnabled(True)
        self.interval_spin.setEnabled(True)
        self.log_csv_checkbox.setEnabled(True)
        self.choose_csv_button.setEnabled(True)
        self.save_log_checkbox.setEnabled(True)
        self.choose_log_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopped")
        self.append_log("Monitoring stopped")

    def sample_memory(self):
        target = self.target_input.text().strip()
        processes = self.find_processes(target)

        if not processes:
            self.current_label.setText("-- MB")
            self.process_count_label.setText("0")
            self.status_label.setText("No match")
            self.append_log(f"No matched process: {target}")
            self.write_csv_row(target, 0, 0, "")
            return

        total_rss = 0
        process_desc = []
        for proc in processes:
            try:
                rss = proc.memory_info().rss
                name = proc.name()
                total_rss += rss
                process_desc.append(f"{proc.pid}:{name}:{format_bytes(rss)}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if total_rss > self.peak_rss:
            self.peak_rss = total_rss

        self.current_label.setText(format_bytes(total_rss))
        self.peak_label.setText(format_bytes(self.peak_rss))
        self.process_count_label.setText(str(len(processes)))
        self.status_label.setText("Running")

        detail = "; ".join(process_desc)
        self.append_log(f"Current={format_bytes(total_rss)} Peak={format_bytes(self.peak_rss)} Processes={len(processes)} {detail}")
        self.write_csv_row(target, total_rss, len(processes), detail)

    def find_processes(self, target):
        if target.isdigit():
            try:
                proc = psutil.Process(int(target))
                return [proc] if proc.is_running() else []
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                return []

        target_lower = target.lower()
        matched = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name") or ""
                if target_lower in name.lower():
                    matched.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return matched

    def open_csv_if_needed(self):
        if not self.log_csv_checkbox.isChecked():
            return

        file_path = self.csv_path_input.text().strip()
        new_file = not os.path.exists(file_path) or os.path.getsize(file_path) == 0
        self.csv_file = open(file_path, "a", newline="", encoding="utf-8-sig")
        self.csv_writer = csv.writer(self.csv_file)
        if new_file:
            self.csv_writer.writerow(["timestamp", "target", "rss_bytes", "rss_mb", "process_count", "detail"])
            self.csv_file.flush()

    def write_csv_row(self, target, rss_bytes, process_count, detail):
        if not self.csv_writer:
            return

        self.csv_writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            target,
            rss_bytes,
            round(rss_bytes / (1024 * 1024), 3),
            process_count,
            detail,
        ])
        self.csv_file.flush()

    def close_csv(self):
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

    def open_text_log_if_needed(self):
        if not self.save_log_checkbox.isChecked():
            return

        file_path = self.log_path_input.text().strip()
        self.text_log_file = open(file_path, "a", encoding="utf-8")

    def write_text_log(self, line):
        if not self.text_log_file:
            return

        self.text_log_file.write(line + "\n")
        self.text_log_file.flush()

    def close_text_log(self):
        if self.text_log_file:
            self.text_log_file.close()
            self.text_log_file = None

    def append_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} - {message}"
        self.log_text.append(line)
        self.write_text_log(line)

    def clear_log(self):
        self.log_text.clear()

    def closeEvent(self, event):
        self.timer.stop()
        self.close_csv()
        self.close_text_log()
        event.accept()


def format_bytes(value):
    if value >= 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024 * 1024):.2f} GB"
    return f"{value / (1024 * 1024):.2f} MB"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("icon.ico")))
    tool = ProcessMemoryMonitor()
    tool.show()
    sys.exit(app.exec_())
