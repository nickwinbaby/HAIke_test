# -*- coding: utf-8 -*-

import sys
import re
import html
import struct
import pandas as pd
import os
import requests

# import subprocess
# from PyQt5.QtWidgets import QFileDialog
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import QFrame, QSpinBox, QMessageBox
from zlib import adler32
# from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QDateTimeEdit, QPushButton,
    QLabel, QTextEdit, QComboBox, QCheckBox, QHBoxLayout, QGroupBox, QFileDialog, QGridLayout
)
from PyQt5.QtCore import QDateTime, QTimer
from PyQt5.QtGui import QIcon, QFontMetrics

# 打包命令
# pyinstaller -F -w --clean -n "4.0协议服务器数据批量解析-20260626" -i protocol_parser.ico --add-data "protocol_parser.ico;." "4.0协议服务器获取数据批量解析-20260626.py"

APP_ICON_RELATIVE_PATH = "protocol_parser.ico"


def _bootstrap_utf8_runtime():
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _normalize_hex_text(text):
    return re.sub(r"\s+", "", text or "").upper()


def read_text_utf8(file_path):
    with open(file_path, "r", encoding="utf-8") as file_obj:
        return file_obj.read()


def write_text_utf8(file_path, content):
    with open(file_path, "w", encoding="utf-8", newline="") as file_obj:
        file_obj.write(content)


_bootstrap_utf8_runtime()


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_app_icon():
    icon_path = resource_path(APP_ICON_RELATIVE_PATH)
    return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()


def set_windows_app_user_model_id():
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mangetic.ProtocolParser.4")
    except Exception:
        pass


class StripedTextEdit(QTextEdit):
    DEFAULT_COL_CAP = 180
    RAW_DATA_COL_CAP = 280
    TIME_COL_CAP = 150
    SHORT_COL_CAP = 110
    LONG_TEXT_COL_CAP = 190
    CELL_LINE_BREAK = "[[BR]]"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._table_rows = None

    def clear(self):
        self._table_rows = None
        super().clear()

    def _column_cap(self, label):
        if label == "原始数据":
            return self.RAW_DATA_COL_CAP
        if "时间" in label:
            return self.TIME_COL_CAP
        if label in {"支持FOTA", "统计来源", "配置版本", "AP版本"}:
            return self.LONG_TEXT_COL_CAP
        return self.DEFAULT_COL_CAP

    @staticmethod
    def _split_display_row(line, split_raw_data=False):
        """按解析结果使用的连续空格拆分数据行。"""
        if split_raw_data:
            raw_start = line.upper().find("5555")
            if raw_start > 0:
                prefix = line[:raw_start].rstrip()
                cells = re.split(r" {2,}", prefix) if prefix else []
                cells.append(line[raw_start:])
                return cells

        return re.split(r" {2,}", line.rstrip())

    @classmethod
    def _split_display_header(cls, line):
        """
        拆分表头时单独处理末尾的“原始数据”列。

        旧的解析函数有些给“原始数据”预留了空格，有些没有预留。
        如果前一个表头没有空格，两个标题会粘成一个单元格；这里按字段名
        明确切开，确保表头列数和数据行列数一致。
        """
        header = line.rstrip()
        for marker in ("原始数据", "Raw Data"):
            marker_start = header.rfind(marker)
            if marker_start < 0:
                continue

            prefix = header[:marker_start].rstrip()
            cells = cls._split_display_row(prefix) if prefix else []
            cells.append(marker)
            return cells

        return cls._split_display_row(header)

    def setText(self, text):
        if text is None:
            self._table_rows = None
            super().clear()
            return

        if not isinstance(text, str):
            text = str(text)

        if not text:
            self._table_rows = None
            super().clear()
            return

        lines = text.splitlines()
        if len(lines) <= 1:
            self._table_rows = None
            super().setPlainText(text)
            return

        header_row = self._split_display_header(lines[0])
        has_raw_data_column = header_row[-1] in {"原始数据", "Raw Data"}
        rows = [header_row]
        rows.extend(
            self._split_display_row(line, split_raw_data=has_raw_data_column)
            for line in lines[1:]
        )
        col_count = max(len(row) for row in rows)

        normalized_rows = []
        for row in rows:
            normalized_rows.append(row + [""] * (col_count - len(row)))
        self._table_rows = [row[:] for row in normalized_rows]

        metrics = QFontMetrics(self.font())
        col_widths = [0] * col_count
        header_row = normalized_rows[0]
        for idx in range(col_count):
            label = header_row[idx].strip() if idx < len(header_row) else ""
            cap = self._column_cap(label)
            max_px = 0
            for row in normalized_rows:
                cell = row[idx].strip()
                if not cell:
                    continue
                cell_parts = [part.strip() for part in cell.split(self.CELL_LINE_BREAK) if part.strip()]
                if cell_parts:
                    max_px = max(max_px, max(metrics.horizontalAdvance(part) for part in cell_parts))
            header_px = metrics.horizontalAdvance(label) if label else 0
            col_widths[idx] = min(max(max_px, header_px) + 18, cap)

        parts = [
            "<table cellspacing=\"0\" cellpadding=\"0\" "
            "style=\"border-collapse: collapse; font-size: 10pt; line-height: 1.35; table-layout: fixed;\">",
            "<colgroup>",
        ]
        for width in col_widths:
            parts.append(f"<col style=\"width: {width}px;\">")
        parts.append("</colgroup>")

        for index, row in enumerate(normalized_rows):
            bg = "#DCEBFF" if index == 0 else ("#FFFFFF" if index % 2 == 1 else "#F4F8FF")
            weight = "font-weight: 600;" if index == 0 else ""
            row_html = []
            for cell in row:
                if cell:
                    safe_cell = html.escape(cell).replace(self.CELL_LINE_BREAK, "<br>")
                    title_text = html.escape(cell.replace(self.CELL_LINE_BREAK, "\n"))
                    white_space = "normal" if self.CELL_LINE_BREAK in cell else "nowrap"
                else:
                    safe_cell = "&nbsp;"
                    title_text = ""
                    white_space = "nowrap"
                row_html.append(
                    # 暂时屏蔽单元格悬浮提示，保留 title_text 相关代码，后续可随时恢复。
                    # f"<td title=\"{title_text}\" style=\"background-color: {bg}; white-space: {white_space}; "
                    f"<td style=\"background-color: {bg}; white-space: {white_space}; "
                    f"overflow: hidden; text-overflow: ellipsis; padding: 1px 8px; "
                    f"border-bottom: 1px solid #E1E7F0; text-align: left; vertical-align: top; {weight}\">"
                    f"{safe_cell}</td>"
                )
            parts.append(f"<tr>{''.join(row_html)}</tr>")
        parts.append("</table>")
        super().setHtml("".join(parts))

# 一级菜单选项：对应界面上的 Select Data Type 下拉框。
DATA_TYPE_OPTIONS = [
    "Select Type",
    "RAW DATA & Protocol",
    "0 - Connect or disconnect",
    "1 - Trip data",
    "2 - Driving behavior",
    "3 - Location data",
    "4 - Vehicle data",
    "5 - Secure data",
    "6 - Device state",
    "7 - Device request message",
    "8 - Active server request",
    "9 - Accessories information",
    "10 - Tachograph",
]

# 二级菜单选项：key 是一级菜单，value 是该一级菜单下可选择的 Select Subtype 列表。
# 新增协议章节时，通常需要先在这里把二级菜单名称加进去。
SUBTYPE_OPTIONS = {
    # RAW DATA
    "RAW DATA & Protocol": [
        "RAW DATA",
        "Protocol consistency",
    ],

    # Chapter 0 - Connect or disconnect
    "0 - Connect or disconnect": [
        "Connect",
        "Disconnect",
    ],

    # Chapter 1 - Trip data
    "1 - Trip data": [
        "1.1 - trip summary",
        "1.2 - Ignition on",
        "1.3 - Ignition off",
        "1.4 - trip start",
        "1.5 - trip end",
    ],

    # Chapter 2 - Driving behavior
    "2 - Driving behavior": [
        "2.1 - Sudden acc",
        "2.2 - Sudden dec",
        "2.3 - Sharp turn",
        "2.4 - Exceed idle",
        "2.5 - Driving tired",
        "2.6 - Over speed",
        "2.7 - Sudden Lane Change",
        "2.8 - Severe Rapid Acceleration",
        "2.9 - Severe Rapid Deceleration",
        "2.10 - Deceleration Without Brake",
        "2.11 - Severe Sharp Turn",
        "2.12 - High-speed Sharp Turn",
        "2.13 - Rapid Start",
        "2.14 - Rapid Stop",
        "2.15 - Throttle Stomp",
        "2.16 - Frequent Braking",
        "2.17 - Long-time Idle",
        "2.18 - Excessive Idle Ratio",
        "2.19 - High RPM Driving",
        "2.20 - High RPM at Idle",
        "2.21 - High Engine Load",
        "2.22 - Inefficient Driving",
        "2.23 - Low-speed Frequent Stop-start",
        "2.24 - Excessive Speed Fluctuation",
    ],

    # Chapter 3 - Location data
    "3 - Location data": [
        "3.1 - GPS data",
        "3.2 - LBS data",
    ],

    # Chapter 4 - Vehicle data
    "4 - Vehicle data": [
        "4.1 - VIN Cold",
        "4.2 - Data flow",
        "4.3 - CAN parameter support status",
        "4.4 - Raw can frame",
        "4.5 - Config data flow",
        "4.6 - Vehicle Information KLV",
    ],

    # Chapter 5 - Secure data
    "5 - Secure data": [
        "5.1 - DTC code",
        "5.2 - Battery low",
        "5.3 - Vibration event",
        "5.4 - Suspected collision",
        "5.5 - Unplug warning",
        "5.6 - Jamming detection",
        "5.7 - Device tamper warning",
        "5.8 - Temperature warning",
        "5.9 - Air pressure warning",
        "5.10 - Shock warning",
        "5.11 - Ambient light detection warning",
        "5.12 - Humidity warning",
        "5.13 - Device warning message",
        "5.14 - DTC code (for J1939)",
        "5.15 - Fence warning",
    ],

    # Chapter 6 - Device state
    "6 - Device state": [
        "6.1 - Sleep state",
        "6.2 - Wakeup state",
        "6.3 - GPS not fix",
        "6.4 - Reboot event",
        "6.5 - Mcu upgrade state",
        "6.6 - SMS",
        "6.7 - Device info",
        "6.8 - Sensor normal",
        "6.9 - Sensor event",
        "6.10 - Modem Upgrade state",
        "6.11 - Relay control status",
        "6.12 - Self learning status",
        "6.13 - Upgrade status of other components",
        "6.14 - Workmode Switch Status",
        "6.15 - Device Collected Temperature",
        "6.16 - Device Collected Air Pressure",
        "6.17 - Movement Detection",
        "6.18 - Heartbeat message (for Router)-暂不开发",
        "6.19 - Modem Chipset High temperature warning (for Router)-暂不开发",
        "6.20 - Weak Signal Warning (for Router)-暂不开发",
        "6.21 - Sub-Device Disconnected Warning (for Router)-暂不开发",
        "6.22 - Sensor Data for Debugging",
        "6.23 - Switched Input Detection",
        "6.24 - Pulse Detection",
        "6.25 - Profile Download Result",
        "6.26 - BLE Relay Binding Update",
        "6.27 - SOS Warning Detection",
        "6.28 - Few Sensor Data",
        "6.29 - Device Collected Data",
        "6.30 - Flight Mode Detection",
        "Bosch crash data",
    ],

    # Chapter 7 - Device request message
    "7 - Device request message": [
        "7.1 -Request MCU update package(TCP)",
        "7.2 - Request AGPS data",
        "7.3 - MCU Update package verification(TCP)",
        "7.4 - MCU Log Report",
        "7.5 - Check new update package(Router)-暂不开发",
        "7.6 - Response to the New Update Package(Router)-暂不开发",
    ],

    # Chapter 8 - Active server request
    "8 - Active server request": [
        "8.1 - Request MCU update (via TCP)",
        "8.2 - Set parameters",
        "8.3 - Inquiry parameters",
        "8.4 - Request FOTA Update (via HTTP/FTP)",
        "8.5 - Request Device information (for Router)",
        "8.6 - Request Device CFG File (for Router)",
        "8.7 - Request Device Log Snapshot",
        "8.8 - whitelist management",
        "8.9 - whitelist query",
        "8.10 - Request eSIM profile update",
        "8.11.2 - Management fence device response",
        "8.12.2 - Query fence device response",
        "8.13 - Request RAW CAN Frame",
        "8.14 - Data Flow Management",
        "8.15 - Data Flow Query",
    ],

    # Chapter 9 - Accessories information
    "9 - Accessories information": [
        "9.1 - Ibutton id",
        "9.2 - Ble sensor data",
        "9.3 - Rs485 temperature humidity",
        "9.4 - Ble sensor warning",
        "9.5 - Rfid data",
        "9.6 - BLE Temperature Humidity Sensor Data",
        "9.7 - Ble tag",
    ],

    # Chapter 10 - Tachograph
    "10 - Tachograph": [
        "10.1 - Data Transparent Transmission",
    ],
}

# 二级菜单与复选框分组的对应关系：key 是 Select Subtype，value 是复选框字段组名称。
# value 会对应 __init__ 中通过 self._create_checkboxes(..., "{value}_{key}_checkbox") 创建的控件组。
# 主要是根据创建的规则来拉取对应显示的复选框
# 用到的是这句 group_name = attr_template.split("{key}", 1)[0].rstrip("_")
CHECKBOX_GROUP_BY_SUBTYPE = {
    # Chapter 0
    "Connect": "connect",
    "Disconnect": "disconnect",

    # Chapter 1
    "1.1 - trip summary": "trip",
    "1.2 - Ignition on": "eng",
    "1.3 - Ignition off": "eng",
    "1.4 - trip start": "passive_trip",
    "1.5 - trip end": "passive_trip",

    # Chapter 2
    "2.1 - Sudden acc": "sudden",
    "2.2 - Sudden dec": "sudden",
    "2.3 - Sharp turn": "sharp_turn",
    "2.4 - Exceed idle": "exceed_idle",
    "2.5 - Driving tired": "driving_tired",
    "2.6 - Over speed": "over_speed",
    "2.7 - Sudden Lane Change": "sudden_lane_change",
    "2.8 - Severe Rapid Acceleration": "sudden",
    "2.9 - Severe Rapid Deceleration": "sudden",
    "2.10 - Deceleration Without Brake": "deceleration_without_brake",
    "2.11 - Severe Sharp Turn": "severe_sharp_turn",
    "2.12 - High-speed Sharp Turn": "high_speed_sharp_turn",
    "2.13 - Rapid Start": "rapid_start",
    "2.14 - Rapid Stop": "rapid_stop",
    "2.15 - Throttle Stomp": "throttle_stomp",
    "2.16 - Frequent Braking": "frequent_braking",
    "2.17 - Long-time Idle": "long_time_idle",
    "2.18 - Excessive Idle Ratio": "excessive_idle_ratio",
    "2.19 - High RPM Driving": "high_rpm_driving",
    "2.20 - High RPM at Idle": "high_rpm_at_idle",
    "2.21 - High Engine Load": "high_engine_load",
    "2.22 - Inefficient Driving": "inefficient_driving",
    "2.23 - Low-speed Frequent Stop-start": "low_speed_frequent_stop_start",
    "2.24 - Excessive Speed Fluctuation": "excessive_speed_fluctuation",

    # Chapter 3
    "3.1 - GPS data": "gps_location_data",
    "3.2 - LBS data": "lbs_location_data",

    # Chapter 4
    "4.1 - VIN Cold": "vin",
    "4.2 - Data flow": "dataflow",
    "4.3 - CAN parameter support status": "can_parameter_support_status",
    "4.4 - Raw can frame": "raw_can_frame",
    "4.5 - Config data flow": "config_dataflow",
    "4.6 - Vehicle Information KLV": "vehicle_Information_klv",

    # Chapter 5
    "5.1 - DTC code": "dtc_code",
    "5.2 - Battery low": "battery_low",
    "5.3 - Vibration event": "vibration_event",
    "5.4 - Suspected collision": "suspected_collision",
    "5.5 - Unplug warning": "unplug_warning",
    "5.6 - Jamming detection": "jamming_detection",
    "5.7 - Device tamper warning": "device_tamper_warning",
    "5.8 - Temperature warning": "temperature_warning",
    "5.9 - Air pressure warning": "air_pressure_warning",
    "5.10 - Shock warning": "shock_warning",
    "5.11 - Ambient light detection warning": "ambient_light_detection_warning",
    "5.12 - Humidity warning": "humidity_warning",
    "5.13 - Device warning message": "device_warning_message",
    "5.14 - DTC code (for J1939)": "j1939_dtc_code",
    "5.15 - Fence warning": "fence_warning",

    # Chapter 6
    "6.1 - Sleep state": "sleep_state",
    "6.2 - Wakeup state": "wakeup_state",
    "6.3 - GPS not fix": "gps_not_fix",
    "6.4 - Reboot event": "reboot_event",
    "6.5 - Mcu upgrade state": "mcu_upgrade_state",
    "6.6 - SMS": "sms",
    "6.7 - Device info": "device_info",
    "6.8 - Sensor normal": "sensor_normal",
    "6.9 - Sensor event": "sensor_event",
    "6.10 - Modem Upgrade state": "modem_upgrade_state",
    "6.11 - Relay control status": "relay_control_status",
    "6.12 - Self learning status": "self_learning_status",
    "6.13 - Upgrade status of other components": "other_components_upgrade_status",
    "6.14 - Workmode Switch Status": "workmode_switch_status",
    "6.15 - Device Collected Temperature": "device_collected_temperature",
    "6.16 - Device Collected Air Pressure": "device_collected_air_pressure",
    "6.17 - Movement Detection": "movement_detection",
    "6.22 - Sensor Data for Debugging": "sensor_data_for_debugging",
    "6.23 - Switched Input Detection": "switched_input_detection",
    "6.24 - Pulse Detection": "pulse_detection",
    "6.25 - Profile Download Result": "profile_download_result",
    "6.26 - BLE Relay Binding Update": "ble_relay_binding_update",
    "6.27 - SOS Warning Detection": "sos_warning_detection",
    "6.28 - Few Sensor Data": "few_sensor_data",
    "6.29 - Device Collected Data": "device_collected_data",
    "6.30 - Flight Mode Detection": "flight_mode_detection",
    "Bosch crash data": "bosch_crash",

    # Chapter 7
    "7.1 -Request MCU update package(TCP)": "request_mcu_update_package_tcp",
    "7.2 - Request AGPS data": "request_agps_data",
    "7.3 - MCU Update package verification(TCP)": "mcu_update_package_verification_tcp",
    "7.4 - MCU Log Report": "mcu_log_report",
    "7.5 - Check new update package(Router)-暂不开发": "check_new_update_package_router",
    "7.6 - Response to the New Update Package(Router)-暂不开发": "response_to_new_update_package_router",

    # Chapter 8
    "8.1 - Request MCU update (via TCP)": "request_mcu_update_via_tcp",
    "8.2 - Set parameters": "set_parameters",
    "8.3 - Inquiry parameters": "inquiry_parameters",
    "8.4 - Request FOTA Update (via HTTP/FTP)": "request_fota_update_http_ftp",
    "8.5 - Request Device information (for Router)": "request_device_information_router",
    "8.6 - Request Device CFG File (for Router)": "request_device_cfg_file_router",
    "8.7 - Request Device Log Snapshot": "request_device_log_snapshot",
    "8.8 - whitelist management": "whitelist_management",
    "8.9 - whitelist query": "whitelist_query",
    "8.10 - Request eSIM profile update": "request_esim_profile_update",
    "8.11.2 - Management fence device response": "message_fence_device_response",
    "8.12.2 - Query fence device response": "query_fence_to_device",
    "8.13 - Request RAW CAN Frame": "request_raw_can_frame",
    "8.14 - Data Flow Management": "data_flow_management",
    "8.15 - Data Flow Query": "data_flow_query",

    # Chapter 9
    "9.1 - Ibutton id": "ibutton_id",
    "9.2 - Ble sensor data": "ble_sensor_data",
    "9.3 - Rs485 temperature humidity": "rs485_temperature_humidity",
    "9.4 - Ble sensor warning": "ble_sensor_warning",
    "9.5 - Rfid data": "rfid_data",
    "9.6 - BLE Temperature Humidity Sensor Data": "ble_temperature_humidity_sensor",
    "9.7 - Ble tag": "ble_tag_data",

    # Chapter 10
    "10.1 - Data Transparent Transmission": "tachograph_data_transparent_transmission",
}

# 一级菜单 + 二级菜单 与实际解析函数的对应关系。
# 点击 Fetch Data 后，fetch_data 会根据 (data_type, sub_type) 找到函数名，再调用对应 process/display 函数。
PROCESS_HANDLER_BY_SELECTION = {
    # RAW DATA
    ("RAW DATA & Protocol", "RAW DATA"): "display_raw_data",
    ("RAW DATA & Protocol", "Protocol consistency"): "display_protocol_consistency",

    # Chapter 0
    ("0 - Connect or disconnect", "Connect"): "process_connect_data",
    ("0 - Connect or disconnect", "Disconnect"): "process_disconnect_data",

    # Chapter 1
    ("1 - Trip data", "1.1 - trip summary"): "process_trip_summary",
    ("1 - Trip data", "1.2 - Ignition on"): "process_ignition_on",
    ("1 - Trip data", "1.3 - Ignition off"): "process_ignition_off",
    ("1 - Trip data", "1.4 - trip start"): "process_trip_start",
    ("1 - Trip data", "1.5 - trip end"): "process_trip_end",

    # Chapter 2
    ("2 - Driving behavior", "2.1 - Sudden acc"): "process_sudden_acc",
    ("2 - Driving behavior", "2.2 - Sudden dec"): "process_sudden_dec",
    ("2 - Driving behavior", "2.3 - Sharp turn"): "process_sharp_turn",
    ("2 - Driving behavior", "2.4 - Exceed idle"): "process_exceed_idle",
    ("2 - Driving behavior", "2.5 - Driving tired"): "process_driving_tired",
    ("2 - Driving behavior", "2.6 - Over speed"): "process_over_speed",
    ("2 - Driving behavior", "2.7 - Sudden Lane Change"): "process_sudden_lane_change",
    ("2 - Driving behavior", "2.8 - Severe Rapid Acceleration"): "process_severe_rapid_acceleration",
    ("2 - Driving behavior", "2.9 - Severe Rapid Deceleration"): "process_severe_rapid_deceleration",
    ("2 - Driving behavior", "2.10 - Deceleration Without Brake"): "process_deceleration_without_brake",
    ("2 - Driving behavior", "2.11 - Severe Sharp Turn"): "process_severe_sharp_turn",
    ("2 - Driving behavior", "2.12 - High-speed Sharp Turn"): "process_high_speed_sharp_turn",
    ("2 - Driving behavior", "2.13 - Rapid Start"): "process_rapid_start",
    ("2 - Driving behavior", "2.14 - Rapid Stop"): "process_rapid_stop",
    ("2 - Driving behavior", "2.15 - Throttle Stomp"): "process_throttle_stomp",
    ("2 - Driving behavior", "2.16 - Frequent Braking"): "process_frequent_braking",
    ("2 - Driving behavior", "2.17 - Long-time Idle"): "process_long_time_idle",
    ("2 - Driving behavior", "2.18 - Excessive Idle Ratio"): "process_excessive_idle_ratio",
    ("2 - Driving behavior", "2.19 - High RPM Driving"): "process_high_rpm_driving",
    ("2 - Driving behavior", "2.20 - High RPM at Idle"): "process_high_rpm_at_idle",
    ("2 - Driving behavior", "2.21 - High Engine Load"): "process_high_engine_load",
    ("2 - Driving behavior", "2.22 - Inefficient Driving"): "process_inefficient_driving",
    ("2 - Driving behavior", "2.23 - Low-speed Frequent Stop-start"): "process_low_speed_frequent_stop_start",
    ("2 - Driving behavior", "2.24 - Excessive Speed Fluctuation"): "process_excessive_speed_fluctuation",

    # Chapter 3
    ("3 - Location data", "3.1 - GPS data"): "process_gps_data_3",
    ("3 - Location data", "3.2 - LBS data"): "process_lbs_data",

    # Chapter 4
    ("4 - Vehicle data", "4.1 - VIN Cold"): "process_vin_code",
    ("4 - Vehicle data", "4.2 - Data flow"): "process_data_flow",
    ("4 - Vehicle data", "4.3 - CAN parameter support status"): "process_can_parameter_support_status",
    ("4 - Vehicle data", "4.4 - Raw can frame"): "process_raw_can_frame",
    ("4 - Vehicle data", "4.5 - Config data flow"): "process_config_data_flow",
    ("4 - Vehicle data", "4.6 - Vehicle Information KLV"): "process_vehicle_Information_klv",

    # Chapter 5
    ("5 - Secure data", "5.1 - DTC code"): "process_dtc_code",
    ("5 - Secure data", "5.2 - Battery low"): "process_battery_low",
    ("5 - Secure data", "5.3 - Vibration event"): "process_vibration_event",
    ("5 - Secure data", "5.4 - Suspected collision"): "process_suspected_collision",
    ("5 - Secure data", "5.5 - Unplug warning"): "process_unplug_warning",
    ("5 - Secure data", "5.6 - Jamming detection"): "process_jamming_detection",
    ("5 - Secure data", "5.7 - Device tamper warning"): "process_device_tamper_warning",
    ("5 - Secure data", "5.8 - Temperature warning"): "process_temperature_warning",
    ("5 - Secure data", "5.9 - Air pressure warning"): "process_air_pressure_warning",
    ("5 - Secure data", "5.10 - Shock warning"): "process_shock_warning",
    ("5 - Secure data", "5.11 - Ambient light detection warning"): "process_ambient_light_detection_warning",
    ("5 - Secure data", "5.12 - Humidity warning"): "process_humidity_warning",
    ("5 - Secure data", "5.13 - Device warning message"): "process_device_warning_message",
    ("5 - Secure data", "5.14 - DTC code (for J1939)"): "process_j1939_dtc_code",
    ("5 - Secure data", "5.15 - Fence warning"): "process_fence_warning",

    # Chapter 6
    ("6 - Device state", "6.1 - Sleep state"): "process_sleep_state",
    ("6 - Device state", "6.2 - Wakeup state"): "process_wakeup_state",
    ("6 - Device state", "6.3 - GPS not fix"): "process_gps_not_fix",
    ("6 - Device state", "6.4 - Reboot event"): "process_reboot_event",
    ("6 - Device state", "6.5 - Mcu upgrade state"): "process_mcu_upgrade_state",
    ("6 - Device state", "6.6 - SMS"): "process_sms",
    ("6 - Device state", "6.7 - Device info"): "process_device_info",
    ("6 - Device state", "6.8 - Sensor normal"): "process_sensor_normal",
    ("6 - Device state", "6.9 - Sensor event"): "process_sensor_event",
    ("6 - Device state", "6.10 - Modem Upgrade state"): "process_modem_upgrade_state",
    ("6 - Device state", "6.11 - Relay control status"): "process_relay_control_status",
    ("6 - Device state", "6.12 - Self learning status"): "process_self_learning_status",
    ("6 - Device state", "6.13 - Upgrade status of other components"): "process_other_components_upgrade_status",
    ("6 - Device state", "6.14 - Workmode Switch Status"): "process_workmode_switch_status",
    ("6 - Device state", "6.15 - Device Collected Temperature"): "process_device_collected_temperature",
    ("6 - Device state", "6.16 - Device Collected Air Pressure"): "process_device_collected_air_pressure",
    ("6 - Device state", "6.17 - Movement Detection"): "process_movement_detection",
    ("6 - Device state", "6.22 - Sensor Data for Debugging"): "process_sensor_data_for_debugging",
    ("6 - Device state", "6.23 - Switched Input Detection"): "process_switched_input_detection",
    ("6 - Device state", "6.24 - Pulse Detection"): "process_pulse_detection",
    ("6 - Device state", "6.25 - Profile Download Result"): "process_profile_download_result",
    ("6 - Device state", "6.26 - BLE Relay Binding Update"): "process_ble_relay_binding_update",
    ("6 - Device state", "6.27 - SOS Warning Detection"): "process_sos_warning_detection",
    ("6 - Device state", "6.28 - Few Sensor Data"): "process_few_sensor_data",
    ("6 - Device state", "6.29 - Device Collected Data"): "process_device_collected_data",
    ("6 - Device state", "6.30 - Flight Mode Detection"): "process_flight_mode_detection",
    ("6 - Device state", "Bosch crash data"): "process_bosch_crash_data",

    # Chapter 7
    ("7 - Device request message", "7.1 -Request MCU update package(TCP)"): "process_request_mcu_update_package_tcp",
    ("7 - Device request message", "7.2 - Request AGPS data"): "process_request_agps_data",
    ("7 - Device request message", "7.3 - MCU Update package verification(TCP)"): "process_mcu_update_package_verification_tcp",
    ("7 - Device request message", "7.4 - MCU Log Report"): "process_mcu_log_report",

    # Chapter 8
    ("8 - Active server request", "8.1 - Request MCU update (via TCP)"): "process_request_mcu_update_via_tcp",
    ("8 - Active server request", "8.2 - Set parameters"): "process_set_parameters",
    ("8 - Active server request", "8.3 - Inquiry parameters"): "process_inquiry_parameters",
    ("8 - Active server request", "8.4 - Request FOTA Update (via HTTP/FTP)"): "process_request_fota_update_http_ftp",
    ("8 - Active server request", "8.5 - Request Device information (for Router)"): "process_request_device_information_router",
    ("8 - Active server request", "8.6 - Request Device CFG File (for Router)"): "process_request_device_cfg_file_router",
    ("8 - Active server request", "8.7 - Request Device Log Snapshot"): "process_request_device_log_snapshot",
    ("8 - Active server request", "8.8 - whitelist management"): "process_whitelist_management",
    ("8 - Active server request", "8.9 - whitelist query"): "process_whitelist_query",
    ("8 - Active server request", "8.10 - Request eSIM profile update"): "process_request_esim_profile_update",
    ("8 - Active server request", "8.11.2 - Management fence device response"): "process_message_fence_response",
    ("8 - Active server request", "8.12.2 - Query fence device response"): "process_query_fence_to_device",
    ("8 - Active server request", "8.13 - Request RAW CAN Frame"): "process_request_raw_can_frame",
    ("8 - Active server request", "8.14 - Data Flow Management"): "process_data_flow_management",
    ("8 - Active server request", "8.15 - Data Flow Query"): "process_data_flow_query",

    # Chapter 9
    ("9 - Accessories information", "9.1 - Ibutton id"): "process_ibutton_id",
    ("9 - Accessories information", "9.2 - Ble sensor data"): "process_ble_sensor_data",
    ("9 - Accessories information", "9.3 - Rs485 temperature humidity"): "process_rs485_temperature_humidity",
    ("9 - Accessories information", "9.4 - Ble sensor warning"): "process_ble_sensor_warning",
    ("9 - Accessories information", "9.5 - Rfid data"): "process_rfid_data",
    ("9 - Accessories information", "9.6 - BLE Temperature Humidity Sensor Data"): "process_ble_temperature_humidity_sensor_data",
    ("9 - Accessories information", "9.7 - Ble tag"): "process_ble_tag_data",

    # Chapter 10
    ("10 - Tachograph", "10.1 - Data Transparent Transmission"): "process_tachograph_data_transparent_transmission",
}



# ════════════════════════════════════════════════════════
# 1.self.dropdown1.addItems 定义一级目录
# 2.def fetch_data(self): if data_type not in 定义一级目录的显示
# 3.def update_dropdown2(self): 定义一级目录的二级目录显示
# 4.update_checkbox_visibility 定义二级目录的显示框内容
# 5.def fetch_data(self) 下面 定义二级目录的判断，进入具体函数
# 6.xxx复选框合集，定义页面可选择的展示内容，默认rawdata不展示
# 7.menu_protocol_code_map 添加界面右侧 Code 框显示的协议码
# 8.packet_protocol_name_map 添加 Protocol consistency 结果里显示的协议名称

# 7.需要在 第N章 添加按键
# 8.在数据流二级目录复选框处修改了整个复选框的布局的显示（单排显示几个）***********************************
# 9.尝试在device_info 使用for循环定义按键，简化代码
# 10.尝试在data_flow 使用字典的方式调用 build_checkbox 函数,简化代码
# ════════════════════════════════════════════════════════
# modify 260407
    # 修改下拉菜单大小和位置（全屏右对齐）
    # 修改下拉菜单标识，对应章节
    # 添加了第零章的connect和disconnect的专用复选框
# modify 260409
    # 完善可配置数据流50条 4-5 章
    # 添加急变道功能 2-7章
# modify 260415
    # 添加can数据支持状态 4-3章
    # 添加 raw_can_frame 4-4章
# modify 260416
    # 添加"4.6 - Vehicle Information KLV"
    # 添加"5.7 - Device tamper warning",
    # 添加"5.8 - Temperature warning",
    # 添加"5.13 - Device warning message"
    # 修改KLV 部分计算方式
# modify 260422
    # 添加 7.1 7.2 7.3 7.4 章节
    # 7.5 7.6 只打基础，不写具体解析，留给后续完善
# modify 260427
    # 修改LBS 适应新协议
    # 修改连接帧，兼容AP VERSION
# modify 260507
    # 增加电子围栏上报功能
# modify 260507
    # 增加电子围栏消息下发结果反馈
    # 增加电子围栏查询功能
# modify 260513
    # 增加协议码的匹配和显示
    # 增加协议一致性的frame num ,checks num ,补位 检查
    # 增加短信功能上报
    # 增加自学习功能上报
# modify 260514
    # 增加参数下发和查询
# modify 260521
    # 增加右侧ASCII转IMEI
# modify 260602
    # 修改部分功能
# modify 260617
    # 修改自动运行时间上限为1小时
# modify 260624
    # 代码优化，取消多余的if else 函数
    # 增加湿度告警
    # 增加右侧原始数据解析 mojor minor
# modify 260626
    # 增加短信 判断如果是 UCS2，强制用 utf-16be 解码
    # 增加 其他组件升级状态显示 6.13
    # 增加 DTC CODE 5.14
    # 增加 感光告警 5.11
    # event 增加变道
# modify 2026-09-02
    # 0 - Connect / Disconnect
    #   - 保持原有连接、断开两种状态的解析逻辑，菜单选择与右侧 Code 显示继续对齐。
    # 1 - Trip data
    #   - trip summary、ignition on、ignition off、trip start、trip end 保持原始字段切片与复选框展示逻辑。
    # 2 - Driving behavior
    #   - 2.1 Sudden acc: 保持原有事件解析。
    #   - 2.2 Sudden dec: 保持原有事件解析。
    #   - 2.3 Sharp turn: 保持原有事件解析。
    #   - 2.4 Exceed idle: 保持原有事件解析。
    #   - 2.5 Driving tired: 保持原有事件解析。
    #   - 2.6 Over speed: 保持原有事件解析。
    #   - 2.7 Sudden Lane Change: 保持原有事件解析。
    #   - 2.8 Severe Rapid Acceleration: 恢复为直接解析，按 IMEI、触发时间、前后车速、峰值输出。
    #   - 2.9 Severe Rapid Deceleration: 恢复为直接解析，字段结构与 2.8 对齐。
    #   - 2.10 Deceleration Without Brake: 恢复为直接解析，增加制动状态和确认窗口时长。
    #   - 2.11 Severe Sharp Turn: 恢复为直接解析，按事件车速和阈值输出。
    #   - 2.12 High-speed Sharp Turn: 恢复为直接解析，按平均车速和横向加速度峰值输出。
    #   - 2.13 Rapid Start: 恢复为直接解析，按触发车速输出。
    #   - 2.14 Rapid Stop: 恢复为直接解析，按减速开始车速输出。
    #   - 2.15 Throttle Stomp: 恢复为直接解析，增加油门前值、窗口尾值、增量和严重级别。
    #   - 2.16 Frequent Braking: 恢复为直接解析，按统计窗口时长和有效制动次数输出。
    #   - 2.17 Long-time Idle: 恢复为直接解析，按怠速等级和连续怠速时长输出。
    #   - 2.18 Excessive Idle Ratio: 恢复为直接解析，按起止时间、怠速时长、运行时长、怠速比和阈值输出。
    #   - 2.19 High RPM Driving: 恢复为直接解析，按平均转速输出。
    #   - 2.20 High RPM at Idle: 恢复为直接解析，按平均转速输出。
    #   - 2.21 High Engine Load: 恢复为直接解析，按负载均值和严重级别输出。
    #   - 2.22 Inefficient Driving: 恢复为直接解析，按单位里程油耗和阈值输出。
    #   - 2.23 Low-speed Frequent Stop-start: 恢复为直接解析，按点火开关次数输出。
    #   - 2.24 Excessive Speed Fluctuation: 恢复为直接解析，按窗口平均车速和相邻车速变化输出。
    # 3 - Location data
    #   - GPS / LBS 保持原有字段切片、有效性判断和时间转换逻辑。
    # 4 - Vehicle data
    #   - Data flow、CAN parameter support status、Raw can frame、Config data flow、Vehicle Information KLV 保持原有解析。
    # 5 - Secure data
    #   - 新增 5.11 感光告警，新增 5.14 DTC code (for J1939)；GPS data 仍按原要求略过不处理。
    # 6 - Device state
    #   - 状态类字段继续按复选框控制显示，保持原有字段格式。
    # 7 - Device request
    #   - 参数下发、查询和返回解析保持独立入口，不改业务链路。
    # 8 - Server request
    #   - 服务端请求与返回结果解析保持原逻辑。
    # 9 - Accessories
    #   - 配件类章节保持原有解析流程与展示方式。
    # RAW DATA & Protocol
    #   - RAW DATA 直显、Protocol consistency 一致性检查、协议码与协议名映射保持当前逻辑。
# modify 2026-09-03
#   - 统一源码 UTF-8 声明与文本读写方式，降低中文注释和字典保存的编码风险
#   - 增加运行时 UTF-8 保护，尽量让控制台输出按 UTF-8 显示
#   - 补充第六章相关更新记录，包括 6.10、6.13、6.14-6.30 的新增内容
#   - 增加程序防护相关说明，遇到无法解析或异常长度时优先避免程序崩溃
#   - 增加报文正式解析前的帧头、帧尾、长度、Adler32 校验和 FF 补位校验
#   - 修复章节切换时复选框异常显示问题，优化时间、Code 和模式控件的布局对齐
#   - 暂时屏蔽 Output 单元格的悬浮完整内容提示，保留原代码便于后续恢复
#   - 本次只做稳妥化和记录整理，原有业务解析逻辑不变

# 将十六进制字符串转换为北京时间
def hex_to_beijing_time(hex_str):
    timestamp = int(hex_str, 16)
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')


# 将十六进制字符串转换为UTC时间，不额外增加8小时
def hex_to_utc_time(hex_str):
    timestamp = int(hex_str, 16)
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return utc_time.strftime('%Y-%m-%d %H:%M:%S')

# 将十六进制字符串转换为十进制
def ascii_to_decimal(ascii_hex):
    try:
        decoded = bytes.fromhex(ascii_hex).decode('utf-8', errors='strict')

        # 允许常见字符（数字 + 字母 + 常见符号）
        if all(32 <= ord(c) <= 126 for c in decoded):
            return decoded.strip()
        else:
            return f"{ascii_hex}(解析失败输出-HEX)"

    except Exception:
        return f"{ascii_hex}(解析失败输出-HEX)"


def read_prefixed_ascii_field(line, offset, limit, length_mask=None):
    if offset + 2 > limit:
        return "N/A", offset

    field_len = int(line[offset:offset + 2], 16)
    if length_mask is not None:
        field_len &= length_mask
    offset += 2

    if field_len == 0:
        return "N/A", offset

    value_end = offset + field_len * 2
    if value_end > limit:
        return f"长度异常({field_len})", limit

    return ascii_to_decimal(line[offset:value_end]), value_end


def decode_float32_hex(value_hex):
    if value_hex.upper() == "FFFFFFFF":
        return "N/A"
    try:
        return round(struct.unpack(">f", bytes.fromhex(value_hex))[0], 2)
    except Exception:
        return f"{value_hex}(解析失败输出-HEX)"


# GPS数据解析
def parse_gps_data(hex_string):
    # 将字符串转为字节列表
    bytes_data = bytes.fromhex(hex_string)

    if len(bytes_data) < 23:
        raise ValueError("输入数据不足23字节")

    result = {}

    # 00-03字节 # 这个是一个UNIX 时间戳的方法 转换为北京时间
    time_raw = int.from_bytes(bytes_data[0:4], byteorder='big')
    # gps_beijing_time = datetime.utcfromtimestamp(time_raw) + timedelta(hours=8)
    gps_beijing_time = datetime.fromtimestamp(time_raw, timezone.utc) + timedelta(hours=8)
    result['Time'] = gps_beijing_time.strftime("%Y-%m-%d %H:%M:%S")

    # 第04字节位拆解
    b4 = bytes_data[4]
    b4_bin = f"{b4:08b}"

    result['Positioning'] = 'GPS' if b4_bin[0] == '0' else 'GSM'
    result['Time Type'] = 'Real time' if b4_bin[1] == '0' else 'Last time'
    result['Longitude Direction'] = 'East' if b4_bin[2] == '0' else 'West'
    result['Latitude Direction'] = 'South' if b4_bin[3] == '0' else 'North'
    satellite_count = b4 & 0x0F
    result['Sate Num'] = satellite_count

    # 高度 = 第05字节 + 第06字节的07-01位
    b5 = bytes_data[5]
    b6 = bytes_data[6]
    b6_bin = f"{b6:08b}"
    height = (b5 << 7) + int(b6_bin[:7], 2)
    result['Height'] = height - 10000

    # 经度 = 第06字节的00位 + 07-09字节
    lon_prefix = b6 & 0x01
    longitude = (lon_prefix << 24) + (bytes_data[7] << 16) + (bytes_data[8] << 8) + bytes_data[9]
    result['Longitude'] = round(longitude * 0.00001, 6)

    # 纬度 = 10-12字节
    latitude = (bytes_data[10] << 16) + (bytes_data[11] << 8) + bytes_data[12]
    result['Latitude'] = round(latitude * 0.00001, 6)

    # GPS速度 = 第13字节 + 第14字节07-04位
    b13 = bytes_data[13]
    b14 = bytes_data[14]
    gps_speed = (b13 << 4) + (b14 >> 4)
    result['GPS Speed'] = round(gps_speed * 0.1, 1)

    # 保留位（不处理，但提取）
    reserved_bits = (b14 >> 2) & 0b11
    result['Reserved'] = reserved_bits

    # Heading = 第14字节01-00位 + 第15字节
    heading = ((b14 & 0b11) << 8) + bytes_data[15]
    result['Heading'] = heading

    # PDOP = 第16字节 + 第17字节07-04位
    pdop = (bytes_data[16] << 4) + (bytes_data[17] >> 4)
    result['PDOP'] = round(pdop * 0.1, 1)

    # HDOP = 第17字节03-00位 + 第18字节
    hdop = ((bytes_data[17] & 0x0F) << 8) + bytes_data[18]
    result['HDOP'] = round(hdop * 0.1, 1)

    # VDOP = 第19字节 + 第20字节07-04位
    vdop = (bytes_data[19] << 4) + (bytes_data[20] >> 4)
    result['VDOP'] = round(vdop * 0.1, 1)

    # HACC = 第21字节 + 第22字节
    hacc = (bytes_data[21] << 8) + bytes_data[22]
    result['HACC'] = round(hacc * 0.1, 1)

    return result

# config dataflow key 校验
# ===================== 工具函数：统一处理所有KEY =====================
def parse_value(v_hex, invalid, calc):
    # 无效值判断
    if isinstance(invalid, set):
        if v_hex.upper() in invalid:
            return v_hex
    else:
        if v_hex.upper() == invalid:
            return v_hex

    # 转换 + 计算
    try:
        val = int(v_hex, 16)
        return calc(val)
    except:
        return v_hex

#  KLV解析规则
def handle_value(k, v_hex):
    """
    根据不同K解析V
    """

    try:
        # ===== 5.1TLVs for Sensor Data 200-214 =======================================
        if k == 200:
            # Battery Voltage of Tag (mV -> V)
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.001:.3f} Volt")
        elif k == 201:
            # Anti-tamper Status of Tag
            if v_hex == "00":
                return "Not tamper"
            elif v_hex == "01":
                return "Tamper"
            elif v_hex == "FF":
                return "Not support"
            else:
                return f"Reserved ({v_hex})"
        elif k == 202:
            # Asensor Status of Tag
            if v_hex == "00":
                return "Stationary"
            elif v_hex == "01":
                return "Movement"
            elif v_hex == "FF":
                return "Not support"
            else:
                return f"Reserved ({v_hex})"
        elif k == 204:
            # Beacon Temperature
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 40:.1f} °C")
        elif k == 205:
            # Gsensor Data of Beacon (X/Y/Z mg)
            return f"Gsensor Data: {v_hex}"
        elif k == 206:
            # Angle of Beacon
            return f"Beacon Angle: {v_hex}"
        elif k == 207:
            # Tilt Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 208:
            # Motion Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 209:
            # Crash Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 210:
            # Falling Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 211:
            # Door State of Beacon
            return "Closed" if v_hex == "01" else "Not closed"
        elif k == 212:
            # Asensor Data
            return f"Asensor Data: {v_hex}"
        elif k == 213:
            # Collected Temperature + Time
            return f"Collected Temperature Data: {v_hex}"
        elif k == 214:
            # Collected Air Pressure + Time
            return f"Collected Air Pressure Data: {v_hex}"
        elif k == 215:
            # Collected Humidity + Time
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.1f} %")
        # ===== 5.2TLVs for Location Data 400-411 =======================================
        elif k == 400:
            # One GPS Data
            return f"GPS Data: {v_hex}"
        elif k == 401:
            # Longitude 经度
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.00001:.5f} Degree")
        elif k == 402:
            # Latitude 纬度
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.00001:.5f} Degree")
        elif k == 403:
            # Radius 半径
            return parse_value(v_hex, "FFFF", lambda x: f"{x} meter")
        elif k == 404:
            # Circular Geo-fence
            return f"Circular Geo-fence: {v_hex}"
        elif k == 405:
            # Rectangular Geo-fence
            return f"Rectangular Geo-fence: {v_hex}"
        elif k == 406:
            # Polygon Geo-fence
            return f"Polygon Geo-fence: {v_hex}"
        elif k == 407:
            # Altitude 海拔
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 10000} meter")
        elif k == 408:
            # Location Data 1
            return f"Location Data: {v_hex}"
        elif k == 409:
            # Position Time UTC 时间戳
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Second")
        elif k == 410:
            # Heading 方向角
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Degree")
        elif k == 411:
            # LBS Data
            return f"LBS Data: {v_hex}"
        # ===== device warning message 500-505 ================================================
        elif k == 500:
            # Temperature Warning 温度告警
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 40:.1f} ℃")
        elif k == 501:
            # Air Pressure Warning 气压告警
            return parse_value(v_hex, "FFFF", lambda x: f"{x} mBar")
        elif k == 502:
            # Humidity Warning 湿度告警
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.1f} %")
        elif k == 503:
            # Warning Judged from Asensor Data 震动/冲击告警
            if v_hex == "00":
                return "Slight Vibration (轻微震动)"
            elif v_hex == "01":
                return "Medium Vibration (中等震动)"
            elif v_hex == "02":
                return "Severe Vibration (剧烈震动)"
            elif v_hex == "03":
                return "Shock (冲击)"
            else:
                return f"Reserved ({v_hex})"
        elif k == 504:
            # Device Tamper Warning 防拆告警
            return "Device tampered warning (设备被拆)" if v_hex == "01" else "Normal"
        elif k == 505:
            # Ambient Light Warning 环境光告警
            return "Ambient light warning (光线异常)" if v_hex == "01" else "Normal"
        # ===== 5.4TLVs for Fixed Vehicle Information 901-902 ==================================
        elif k == 901:
            # VIN Code 车辆识别码
            return f"VIN: {v_hex}"
        elif k == 902:
            # Engine Serial Number 发动机序列号
            return f"Engine SN: {v_hex}"
        # ===== config data flow KLV 1001 - 1055 ========================================
        elif k == 1001:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} RPM")
        elif k == 1002:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} km/h")
        elif k == 1003:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1004:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1005:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1006:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} g/s")
        elif k == 1007:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1008:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Kpa")
        elif k == 1009:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} V")
        elif k == 1010:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.01:.2f} %")
        elif k == 1011:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} KM")

        # 1012 特殊（多无效值）→ 照样支持
        elif k == 1012:
            return parse_value(v_hex, {"FFFF", "0000", "0001", "FFFE"}, lambda x: f"{x} KM")

        elif k == 1013:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} meter")
        elif k == 1014:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} ml")

        # 1016 复杂逻辑 → 单独写最清晰
        elif k == 1016:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                val = int(v_hex, 16)
                driver = val & 0b11
                passenger = (val >> 2) & 0b11

                def s(b):
                    if b == 0b00: return "Not Tied"
                    if b == 0b01: return "Tied"
                    if b == 0b11: return "Not supported"
                    return "Invalid"

                return f"Driver:{s(driver)}, Passenger:{s(passenger)}"
            except:
                return v_hex

        elif k == 1017:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} KM")

        # 1018 特殊枚举 → 单独写
        elif k == 1018:
            if v_hex.upper() == "FF": return v_hex
            if v_hex == "01": return "KM"
            if v_hex == "02": return "Mile"
            return v_hex

        elif k == 1019:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} ml/100KM")
        elif k == 1020:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1021:
            return parse_value(v_hex, "FF", lambda x: f"{x} %")
        elif k == 1022:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 1000:.2f} A")

        # ===================== 1022 ~ 1055 全部生成完毕 =====================
        # 懒得写了 AI 给写的
        elif k == 1022:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 1000:.2f} A")
        elif k == 1023:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} Volt")
        elif k == 1024:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                s = {0: "Not Charging", 1: "Level 1 Charging", 2: "Level 2 Charging", 3: "Level 3 Quick Charging"}
                return s.get(int(v_hex, 16), v_hex)
            except:
                return v_hex
        elif k == 1025:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} KM")
        elif k == 1026:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1027:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} KM")
        elif k == 1028:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} Second")
        elif k == 1029:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                m = {
                    0x00: "Not available", 0x01: "Gasoline", 0x02: "Methanol", 0x03: "Ethanol", 0x04: "Diesel",
                    0x05: "LPG", 0x06: "CNG", 0x07: "Propane", 0x08: "Electric", 0x09: "Bifuel running Gasoline",
                    0x0A: "Bifuel running Methanol", 0x0B: "Bifuel running Ethanol", 0x0C: "Bifuel running LPG",
                    0x0D: "Bifuel running CNG", 0x0E: "Bifuel running Propane", 0x17: "Natural Gas (NG)",
                    0x18: "Bi-fuel NG", 0x19: "Bi-fuel diesel", 0x1A: "Natural Gas", 0x1B: "Dual Fuel Diesel-CNG",
                    0x1C: "Dual Fuel Diesel-LNG", 0x1D: "Fuel cell hydrogen", 0x1E: "Hydrogen ICE", 0x1F: "Kerosene",
                    0x20: "Heavy Fuel Oil"
                }
                return m.get(int(v_hex, 16), v_hex)
            except:
                return v_hex
        elif k == 1030:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                v = int(v_hex, 16)
                left = "On" if (v & 1) else "Off"
                right = "On" if (v & 2) else "Off"
                return f"Left:{left}, Right:{right}"
            except:
                return v_hex
        elif k == 1031:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1032:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.01 - 100:.2f} %")
        elif k == 1033:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.01 - 100:.2f} %")
        elif k == 1034:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                g = {0: "Gear P", 2: "Gear R", 3: "Gear N", 4: "Gear D"}
                return g.get(int(v_hex, 16), v_hex)
            except:
                return v_hex
        elif k == 1035:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1036:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 1000:.2f} Degree")
        elif k == 1037:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                return "High beam On" if int(v_hex, 16) == 1 else "High beam Off"
            except:
                return v_hex
        elif k == 1038:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} kPa")
        elif k == 1039:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} mL/100KM")
        elif k == 1040:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} mL")
        elif k == 1041:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1042:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Minute")
        elif k == 1043:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1044:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1045:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1046:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1047:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1048:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1050:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1051:
            if v_hex.upper() == "FF": return v_hex
            try:
                return f"{int(v_hex, 16) - 125} Gear value"
            except:
                return v_hex
        elif k == 1052:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} kPa")
        elif k == 1053:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} kPa")
        elif k == 1054:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1055:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")



# 1001 - 1020 隐藏，用简单方式来继续处理
        # elif k == 1001:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16)} RPM"
        #     except:
        #         return v_hex
        # elif k == 1002:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16)} km/h"
        #     except:
        #         return v_hex
        # elif k == 1003:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16) * 0.1 - 40:.2f} ℃"
        #     except:
        #         return v_hex
        # elif k == 1004:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} %"
        # elif k == 1005:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} %"
        # elif k == 1006:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} g/s"
        # elif k == 1007:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1 - 40:.2f} ℃"
        # elif k == 1008:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} Kpa"
        # elif k == 1009:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} V"
        # elif k == 1010:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.01:.2f} %"
        # elif k == 1011:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} KM"
        # elif k == 1012:
        #     if v_hex.upper() in {"FFFF", "0000", "0001", "FFFE"}:
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16)} KM"
        #     except:
        #         return v_hex
        # elif k == 1013:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) } meter"
        # elif k == 1014:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} ml"
        # elif k == 1016:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #
        #     try:
        #         val = int(v_hex, 16)
        #         # 解析主驾（bit0-1）
        #         driver = val & 0b11
        #         # 解析副驾（bit2-3）
        #         passenger = (val >> 2) & 0b11
        #
        #         # 转成文字
        #         def get_status(bits):
        #             if bits == 0b00:
        #                 return "Not Tied"
        #             elif bits == 0b01:
        #                 return "Tied"
        #             elif bits == 0b11:
        #                 return "Not supported"
        #             else:
        #                 return "Invalid"
        #
        #         d_stat = get_status(driver)
        #         p_stat = get_status(passenger)
        #         return f"Driver:{d_stat}, Passenger:{p_stat}"
        #
        #     except:
        #         return v_hex
        # elif k == 1017:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} KM"
        # elif k == 1018:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #     elif v_hex == "01":
        #         return "KM"
        #     elif v_hex == "02":
        #         return "Mile"
        #     else:
        #         return v_hex
        # elif k == 1019:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} ml/100KM"
        # elif k == 1020:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} %"
        # elif k == 1021:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} %"
        # elif k == 1021:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16) * 0.1 - 1000:.2f } A"
        #     except:
        #         return v_hex


        else:
            return v_hex  # 默认直接返回
    except:
        return v_hex

KLV_DISPLAY_NAMES = {
    200: "Tag 电池电压",
    201: "Tag 防拆状态",
    202: "Tag 运动状态",
    203: "Beacon 工作模式",
    204: "Beacon 温度",
    205: "Beacon Gsensor 数据",
    206: "Beacon 角度",
    207: "Beacon 倾斜事件计数",
    208: "Beacon 运动事件计数",
    209: "Beacon 碰撞事件计数",
    210: "Beacon 跌落事件计数",
    211: "Beacon 门状态",
    212: "Asensor 数据",
    213: "采集温度",
    214: "采集气压",
    215: "采集湿度",
    400: "One GPS Data",
    401: "经度",
    402: "纬度",
    403: "半径",
    404: "圆形围栏",
    405: "矩形围栏",
    406: "多边形围栏",
    407: "海拔",
    408: "Location Data 1",
    409: "定位时间",
    410: "方向角",
    411: "LBS 数据",
    500: "温度告警",
    501: "气压告警",
    502: "湿度告警",
    503: "震动/冲击告警",
    504: "防拆告警",
    505: "环境光告警",
    901: "VIN 码",
    902: "发动机序列号",
    1001: "发动机转速",
    1002: "车辆速度",
    1003: "发动机冷却液温度",
    1004: "节气门位置",
    1005: "计算发动机负荷 / 行程平均负荷系数",
    1006: "空气流量传感器流量 / 进气质量流量",
    1007: "进气温度 / 发动机 1 号进气歧管温度",
    1008: "进气歧管绝对压力 / 进气压力",
    1009: "车载蓄电池电压",
    1010: "油箱液位输入",
    1011: "故障码清除后行驶里程",
    1012: "故障指示灯点亮后行驶里程",
    1013: "历史总里程 / 设备安装后累计里程",
    1014: "历史总耗油量 / 设备安装后累计耗油量",
    1016: "安全带状态",
    1017: "里程表读数",
    1018: "里程表单位",
    1019: "平均油耗",
    1020: "电池剩余电量",
    1021: "电池健康度",
    1022: "电池包电流",
    1023: "电池包电压",
    1024: "电池包充电状态",
    1025: "剩余续航里程",
    1026: "电池包温度",
    1027: "距下次保养剩余里程",
    1028: "发动机启动后运行时长",
    1029: "燃料类型",
    1030: "转向灯状态",
    1031: "发动机机油温度",
    1032: "1 组长期燃油修正",
    1033: "2 组长期燃油修正",
    1034: "档位位置",
    1035: "制动踏板位置",
    1036: "方向盘转角",
    1037: "远光灯状态",
    1038: "发动机机油压力",
    1039: "瞬时油耗",
    1040: "总耗油量",
    1041: "柴油尿素箱液位",
    1042: "剩余充电时长",
    1043: "加速踏板位置",
    1044: "驾驶员车门状态",
    1045: "乘客车门状态",
    1046: "左后车门状态",
    1047: "右后车门状态",
    1048: "后备箱状态",
    1050: "离合器打滑百分比",
    1051: "变速箱当前档位",
    1052: "制动主缸压力",
    1053: "制动副缸压力",
    1054: "发动机冷却液液位",
    1055: "二号油箱液位",
}

def parse_klv(data, separator=" , "):
    i = 0
    result = []

    while i + 6 <= len(data):  # 至少 K(4) + L(2)
        try:
            # 1️⃣ K
            k_hex = data[i:i + 4]
            k = int(k_hex, 16)
            i += 4

            # 2️⃣ L
            l_hex = data[i:i + 2]
            l = int(l_hex, 16)
            i += 2

            # 3️⃣ V长度
            v_len = l * 2
            if i + v_len > len(data):
                break

            v_hex = data[i:i + v_len]
            i += v_len

            # 4️⃣ 解析V
            v_value = handle_value(k, v_hex)

            label = KLV_DISPLAY_NAMES.get(k)
            if label:
                result.append(f"{k} - {label} - {v_value}")
            else:
                result.append(f"{k} - {v_value}")

        except:
            break

    return separator.join(result)

# can 支持参数状态 -函数框

gasoline_map = {
    1: ["VIN", "ODO", "FLI(%)", "FLI(Liter)", "Seatbelt_Driver", "Seatbelt_Passenger", "TPMS_P", "TPMS_T"],
    2: ["DTC", "MILStatus", "DistanceTraveledWhileMILActivated", "DistanceTraveledSinceDTCsCleared",
        "RemainingDistance", "DistanceTillNextServicing", "OilTemp", "OBDType"],
    3: ["EngineRPM", "VehicleSpeed", "MassAirFlow", "IntakeAirTemp",
        "IntakeManifoldAbsolutePressure", "TimeSinceEngineStart", "CalculatedLoad", "EngineCoolantTemp"],
    4: ["ThrottlePosition", "EngineRunTime", "AmbientTemperature", "LongTermFuelTrim",
        "ExtendedMassAirFlowInformation", "EngineOilPressure", "EngineInstantaneousFuelEconomy", "DieselExhaustFluidTankVolume"],
    5: ["PercentClutchSlip", "TotalFuelUsed", "BrakePrimaryPressure", "BrakeSecondaryPressure",
        "EngineCoolantLevel", "FuelLevel2", "Reserved", "Reserved"]
}

ev_map = {
    1: ["VIN", "Ready", "SOC", "SOH", "ChargingState", "ChargeMinutesRemaining", "ODO", "VehicleSpeed"],
    2: ["BatteryPackCurrent", "BatteryPackVoltage", "BatteryPackTemperature", "RemainingDistance",
        "DistanceTillNextServicing", "Seatbelt_Driver", "Seatbelt_Passenger", "TPMS_P"],
    3: ["ODOUnit", "DoorsStatus", "TrunkStatus", "GearPosition",
        "ParkStatus", "MotorRPM", "BrakePedal", "WheelSpeed"],
    4: ["SteeringAngle", "HighBeamStatus", "LeftTurnSignal", "RightTurnSignal",
        "TPMS_T", "ACCPedal", "ACCPedaPercent", "BrakePedalPercent"]
}


def parse_can_list(line, start, mapping):
    result = []

    if start + 2 > len(line):
        return result, start

    length = int(line[start:start+2], 16)

    # 长度为0
    if length == 0:
        return result, start + 2

    # ✅ 正确：包含 byte0 + 数据
    total_bytes = 1 + length

    for i in range(1, length + 1):   # ✅ 关键修复
        byte_hex = line[start + i*2 : start + i*2 + 2]
        byte_val = int(byte_hex, 16)

        if i not in mapping:
            continue

        fields = mapping[i]

        for bit in range(8):
            if byte_val & (1 << (7 - bit)):
                result.append(f"byte{i}-bit{7-bit}:{fields[bit]}")

    # ✅ 正确 offset
    new_start = start + total_bytes * 2

    return result, new_start


# 构建按键函数
# def build_checkbox(fields, context):
#     row = []
#     for checkbox, value, fmt in fields:
#         if getattr(context, checkbox).isChecked():
#             row.append(fmt.format(value))
#     return row


# 创建按键
def build_checkbox(fields, context):
    row = []
    for checkbox, label, width in fields:
        if getattr(context, checkbox).isChecked():
            row.append(f"{label:<{width}}")
    return row


# 8.2 章参数下发
def f1_02_parse_tlv_status_fields(line):
    result_mapping = {
        "00": "failure",
        "01": "successful",
        "02": "work m2 invalid",
        "03": "work m3 invalid",
        "04": "work m4 invalid",
        "05": "main power dis"
    }

    offset = 0
    results = []

    effective_data_length = int(line[54:58], 16)
    parameters_effective_data = line[62:62 + (effective_data_length - 2) * 2]

    while offset + 6 <= len(parameters_effective_data):  # 确保剩下至少6个字符可读
        param = parameters_effective_data[offset:offset + 4]
        status_code = parameters_effective_data[offset + 4:offset + 6]

        status_text = result_mapping.get(status_code, "unknown")

        # results.append((param, status_code, status_text))
        results.append(f"{param.upper()}:{status_text}")
        offset += 6  # 每次向后推进6位

    return results


# 8.3 章处理 可变长度字段
def handle_variable_length_field(data, calc_func):
    length_byte = int(data[:2], 16)  # 取长度字段
    data_length = length_byte * 2  # 转换为十六进制字符长度
    data_value = data[2:2 + data_length]  # 提取有效数据部分
    value = calc_func(data_value)  # 调用传入函数处理（如 ASCII 解码）
    return value, data_length

def parse_024A(value_hex):
    try:
        pos = 0

        # A：APN长度
        if pos + 2 > len(value_hex):
            return f"{value_hex}(HEX,缺少APN长度)"

        apn_len = int(value_hex[pos:pos + 2], 16)
        pos += 2

        if apn_len >= 32:
            return f"{value_hex}(HEX,APN长度异常:{apn_len})"

        apn_hex = value_hex[pos:pos + apn_len * 2]
        if len(apn_hex) < apn_len * 2:
            return f"{value_hex}(HEX,APN内容长度不足)"

        pos += apn_len * 2
        apn = ascii_to_decimal(apn_hex)

        # B：用户名长度
        if pos + 2 > len(value_hex):
            return f"APN:{apn}, User:, Password:"

        username_len = int(value_hex[pos:pos + 2], 16)
        pos += 2

        if username_len >= 32:
            return f"{value_hex}(HEX,用户名长度异常:{username_len})"

        username_hex = value_hex[pos:pos + username_len * 2]
        if len(username_hex) < username_len * 2:
            return f"{value_hex}(HEX,用户名内容长度不足)"

        pos += username_len * 2
        username = ascii_to_decimal(username_hex)

        # C：密码长度
        if pos + 2 > len(value_hex):
            return f"APN:{apn}, User:{username}, Password:"

        password_len = int(value_hex[pos:pos + 2], 16)
        pos += 2

        if password_len >= 32:
            return f"{value_hex}(HEX,密码长度异常:{password_len})"

        password_hex = value_hex[pos:pos + password_len * 2]
        if len(password_hex) < password_len * 2:
            return f"{value_hex}(HEX,密码内容长度不足)"

        password = ascii_to_decimal(password_hex)

        return f"APN:{apn}, User:{username}, Password:{password}"

    except Exception as e:
        return f"{value_hex}(HEX,024A解析失败:{e})"

# 8.3 章参数查询
def f1_03_parse_custom_fields(line):
    results = []

    field_defs = {
        "0001": (1, lambda v: int(v, 16) * 10),
        "0002": (1, lambda v: int(v, 16) * 10),
        "0003": (1, lambda v: int(v, 16) * 10),
        "0004": (2, lambda v: int(v, 16)),
        "0005": (1, lambda v: int(v, 16)),
        "0006": (1, lambda v: int(v, 16) * 0.1),
        "0007": (1, lambda v: {"01": "0.0625g", "02": "0.125g", "03": "0.250g", "04": "0.375g", "05": "0.625g",
                               "06": "0.9375g", "07": "1.25g"}.get(v.upper(), "unknown")),
        "0008": (1, lambda v: int(v, 16) * 100),
        "0009": (2, lambda v: int(v, 16)),
        "000B": (2, lambda v: int(v, 16)),
        "000C": (2, lambda v: int(v, 16)),
        "000D": (2, lambda v: int(v, 16)),
        "000E": (2, lambda v: int(v, 16)),
        "000F": (2, lambda v: int(v, 16) * 0.1),
        "0010": (2, lambda v: {"0000": "Enable OBD", "0001": "Disable OBD"}.get(v.upper(), "Unknown")),
        "0012": (1, lambda v: {"01": "ASS OFF", "02": "ASS ON"}.get(v.upper(), "Unknown")),
        "0016": (1, lambda v: {"01": "factory reset"}.get(v.upper(), "Unknown")),
        "0017": (1, lambda v: {"01": "reboot device"}.get(v.upper(), "Unknown")),
        "0018": (1, lambda v: int(v, 16)),
        "0207": (
        1, lambda v: {"00": "Not controlled", "01": "HOTSPOT on", "02": "HOTSPOT off"}.get(v.upper(), "Unknown")),
        "020F": (1, lambda v: {"00": "Tracker", "01": "ACC", "02": "OBD", "03": "Mixed", "04": "Standalone "}.get(
            v.upper(), "Unknown")),
        "0220": (1, lambda v: int(v, 16) * 0.1),
        "0225": (2, lambda v: int(v, 16) * 3),
        "0226": (2, lambda v: int(v, 16)),
        "0227": (1, lambda v: {"00": "recover", "01": "cut off"}.get(v.upper(), "Unknown")),
        "0228": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0229": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "022A": (2, lambda v: int(v, 16)),
        "022B": (2, lambda v: int(v, 16)),
        "0230": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0231": (1, lambda v: {"01": "mode1 ", "02": "mode2", "03": "mode3", "04": "mode4"}.get(v.upper(), "Unknown")),
        "0232": (1, lambda v: int(v, 16)),
        "0233": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0235": (1, lambda v: int(v, 16)),
        "0236": (4, lambda v: int(v, 16) * 0.1 - 40),
        "0237": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0238": (1, lambda v: int(v, 16)),
        "0239": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "023A": (2, lambda v: int(v, 16)),
        "023C": (2, lambda v: int(v, 16)),
        "023D": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0247": (1, lambda v: int(v, 16) * 0.1),
        "0250": (1, lambda v: {"01": "factory reset"}.get(v.upper(), "Unknown")),
        "0251": (1, lambda v: {"01": "reboot device"}.get(v.upper(), "Unknown")),
        "0252": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0253": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0255": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0256": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0257": (1, lambda v: int(v, 16)),
        "0271": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0272": (1, lambda v: int(v, 16)),
        "0273": (1, lambda v: {"01": " Hard reset the device"}.get(v.upper(), "Unknown")),
        "0274": (1, lambda v: int(v, 16)),
        "0275": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0276": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0277": (1, lambda v: int(v, 16)),
        "0278": (1, lambda v: int(v, 16)),
        "0279": (1, lambda v: {"00": "INFO ", "01": "DEBUG"}.get(v.upper(), "Unknown")),
        "040D": (1, lambda v: {"01": "Terminate current MCU FOTA task"}.get(v.upper(), "Unknown")),
        "0414": (1, lambda v: {"00": "Not controlled by the server", "01": "5GHz HOTSPOT on",
                               "02": "5GHz HOTSPOT off"}.get(v.upper(), "Unknown")),
        "0415": (2, lambda v: int(v, 16)),
        "0416": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0417": (
        1, lambda v: {"00": "Deep Sleep", "01": "Light Sleep", "02": "GPS Online Sleep"}.get(v.upper(), "Unknown")),
        "0418": (1, lambda v: {"00": "Disable", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0419": (4, lambda v: int(v, 16) * 0.1),
        "041A": (1, lambda v: {"01": "force to re-learning"}.get(v.upper(), "Unknown")),
        "041B": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "041C": (1, lambda v: {"00": "00 ", "01": "01", "02": "02"}.get(v.upper(), "Unknown")),
        "041D": (2, lambda v: int(v, 16)),
        "041F": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0420": (4, lambda v: int(v, 16)),
        "0421": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0422": (1, lambda v: {"00": "Disable iButton and RFID",
                               "01": "Only report iButton ID",
                               "02": "report iButton ID, and wire relay",
                               "03": "Only report RFID card",
                               "04": "report RFID card, and wire relay",
                               "05": "report iButton ID, and ble relay",
                               "06": "report RFID card, and wire relay",
                               }.get(v.upper(), "Unknown")),
        "0423": (1, lambda v: {"00": "Disable RFID function ", "01": "Only report RFID",
                               "02": "Report RFID, and control relay"}.get(v.upper(), "Unknown")),
        "0425": (2, lambda v: int(v, 16)),
        "0426": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0428": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "042A": (2, lambda v: int(v, 16)),
        "0434": (7, lambda v: f"{int(v[0:2], 16)} - {v[2:].upper()}"),

        # 动态字段处理
        "0200": (99, ascii_to_decimal),
        "0202": (99, ascii_to_decimal),
        "0203": (99, ascii_to_decimal),
        "0204": (99, ascii_to_decimal),
        "0206": (99, ascii_to_decimal),
        "0221": (99, ascii_to_decimal),
        "023B": (99, ascii_to_decimal),
        "0240": (99, ascii_to_decimal),
        "0241": (99, ascii_to_decimal),
        "024A": (99, parse_024A),
        "0254": (99, ascii_to_decimal),
        "0407": (99, ascii_to_decimal),
        "041E": (99, ascii_to_decimal),
        "0424": (99, ascii_to_decimal),
    }

    effective_data_length = int(line[54:58], 16)
    payload = line[62:62 + (effective_data_length - 2) * 2]

    offset = 0
    while offset + 4 <= len(payload):
        param = payload[offset:offset + 4].upper()

        if param in field_defs:
            num, func = field_defs[param]

            if num == 99:
                length_hex = payload[offset + 4:offset + 6]

                if len(length_hex) < 2:
                    results.append(f"{param}:数据错误，缺少长度字段")
                    break

                data_len = int(length_hex, 16)
                end_pos = offset + 6 + data_len * 2

                if end_pos > len(payload):
                    results.append(f"{param}:数据错误，返回值长度不足，无法解析")
                    break

                value_hex = payload[offset + 6:end_pos]

                try:
                    value = func(value_hex)
                    results.append(f"{param}:{value}")
                except Exception:
                    results.append(f"{param}:数据错误，无法被ASCII解析")
                    break

                offset += 4 + 2 + data_len * 2

            else:
                length = num * 2
                end_pos = offset + 4 + length

                if end_pos > len(payload):
                    results.append(f"{param}:数据错误，返回值长度不足，无法解析")
                    break

                value_hex = payload[offset + 4:end_pos]

                try:
                    value = func(value_hex)
                    results.append(f"{param}:{value}")
                except Exception:
                    results.append(f"{param}:数据错误，无法解析")
                    break

                offset += 4 + length

        else:
            results.append(f"{param}:未识别字段")
            break

    return results


# sensor_normal_event 事件取正负值
def parse_signed_16bit(hex_str):
    value = int(hex_str, 16)
    if value & 0x8000:  # 判断最高位是否为1
        return value - 0x10000  # 65536
    return value


class DataFetcherApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("4.0协议服务器数据批量解析 - Mangetic - 260904 ")
        self.setWindowIcon(get_app_icon())
        self.setGeometry(400, 300, 600, 600)

        self.imei_input = QLineEdit(self)
        self.imei_input.setPlaceholderText("Enter IMEI number(s), comma separated")

        self.start_time_input = QDateTimeEdit(self)
        self.start_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_time_input.setDateTime(QDateTime.currentDateTime())
        self.start_time_input.setFixedWidth(175)

        self.stop_time_input = QDateTimeEdit(self)
        self.stop_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.stop_time_input.setDateTime(QDateTime.currentDateTime())
        self.stop_time_input.setFixedWidth(175)

        self.fetch_button = QPushButton("Fetch Data", self)
        self.fetch_button.clicked.connect(self.fetch_data)

        self.clear_button = QPushButton("Clear Output", self)
        self.clear_button.clicked.connect(self.clear_output)
        self.local_parse_button = QPushButton("解析本地HEX", self)
        self.local_parse_button.clicked.connect(self.parse_local_hex_data)

        # 添加导出EXCEL按键
        self.export_button = QPushButton("导出为 Excel", self)
        self.export_button.clicked.connect(self.export_to_excel)

        self.dropdown1 = QComboBox(self)
        # self.dropdown1.addItems(["Select Type", "RAW DATA", "Trip data", "2 - Driving behavior", "3 - Location data",
        #                          "4 - Vehicle data", "5 - Secure data", "6 - Device state", "8 - Active server request",
        #                          "9 - Accessories information"])
        self.dropdown1.addItems(DATA_TYPE_OPTIONS)



        self.dropdown1.currentIndexChanged.connect(self.update_dropdown2)

        self.dropdown2 = QComboBox(self)
        self.dropdown2.addItem("Select Option")
        # 定义一个下拉的可选复选框
        self.dropdown2.currentIndexChanged.connect(self.update_checkbox_visibility)

        # 协议码显示框，只显示，不允许手动输入
        self.protocol_code_display = QLineEdit(self)
        self.protocol_code_display.setReadOnly(True)
        self.protocol_code_display.setFixedWidth(160)
        self.protocol_code_display.setPlaceholderText("协议")

        self.input_mode_label = QLabel("模式")
        self.input_mode_combo = QComboBox(self)
        self.input_mode_combo.addItems(["服务器获取", "本地HEX"])
        self.input_mode_combo.currentIndexChanged.connect(self.update_input_mode)

        self.local_hex_input = QLineEdit(self)
        self.local_hex_input.setPlaceholderText("粘贴完整HEX原始数据，可多行；选择协议后直接解析")
        self.local_hex_input.setFixedHeight(26)
        self.local_hex_input.setPlaceholderText("粘贴一条完整HEX原始数据，自动识别协议后解析")

        self.local_hex_group = QGroupBox("本地HEX输入")
        local_hex_layout = QHBoxLayout()
        local_hex_layout.setContentsMargins(6, 4, 6, 4)
        local_hex_layout.setSpacing(6)
        local_hex_layout.addWidget(self.local_hex_input, 1)
        local_hex_layout.addWidget(self.local_parse_button)
        self.local_hex_group.setLayout(local_hex_layout)
        self.local_hex_group.setVisible(False)
        self.local_hex_group.setFixedHeight(58)


        self.result_label = QLabel("Results will appear here.", self)
        self.result_label.setWordWrap(True)

        self.raw_data_display = StripedTextEdit(self)
        self.raw_data_display.setReadOnly(True)
        self.raw_data_display.setLineWrapMode(QTextEdit.NoWrap)

        # 显示字段复选框
        self.checkbox_group = QGroupBox("显示字段")
        # 创建网格布局
        self.checkbox_layout = QGridLayout()
        self.checkbox_sets = {}

        # ════════════════════════════════════════════════════════
        #       第零章：复选框合集
        # ════════════════════════════════════════════════════════
        # connect 专用复选框
        connect_fields = {
            "imei":("IMEI",True),
            "time":("时间",True),
            "hardware_version":("硬件版本",True),
            "mcu_ap_version":("MCU/AP版本",True),
            "mdm_version":("MDM版本",True),
            "cfg_version":("配置版本",True),
            "support_status_fota":("支持状态FOTA",True),
            "ap_version":("AP版本",True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(connect_fields, "connect_{key}_checkbox")

        # disconnect专用复选框
        disconnect_fields = {
            "imei": ("IMEI", True),
            "time": ("时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(disconnect_fields, "disconnect_{key}_checkbox")


        # ════════════════════════════════════════════════════════
        #       第一章：复选框合集
        # ════════════════════════════════════════════════════════

        # trip summary 专用复选框
        trip_fields = {
            "imei": ("IMEI", True),
            "start_time": ("点火时间", True),
            "end_time": ("熄火时间", True),
            "source": ("统计来源", True),
            "mileage": ("行驶里程", True),
            "fuel_consumption": ("行程油耗", True),
            "max_speed": ("最高车速", True),
            "idle_time": ("怠速时间", True),
            "idle_fuel_consumption": ("怠速油耗", True),
            "num_of_acceleration": ("急加速次数", True),
            "num_of_deceleration": ("急减速次数", True),
            "num_of_sharp_turn": ("急转弯次数", True),
            "histor_total_mil": ("历史总里程", True),
            "histor_total_fuel": ("历史总油耗", True),
            "histor_total_driving_time": ("历史总行驶时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(trip_fields, "trip_{key}_checkbox")

        # 点熄火专用复选框
        eng_fields = {
            "imei": ("IMEI", True),
            "type": ("协议类型", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(eng_fields, "eng_{key}_checkbox")

        # 拖车功能专用复选框
        passive_trip_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(passive_trip_fields, "passive_trip_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第二章：复选框合集
        # ════════════════════════════════════════════════════════

        # 急加减速专用复选框
        sudden_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "before_speed": ("触发前车速", True),
            "after_speed": ("触发后车速", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sudden_fields, "sudden_{key}_checkbox")

        # 急转弯专用复选框
        sharp_turn_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "Turn": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sharp_turn_fields, "sharp_turn_{key}_checkbox")

        # 怠速专用复选框
        exceed_idle_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(exceed_idle_fields, "exceed_idle_{key}_checkbox")

        # 疲劳驾驶专用复选框
        driving_tired_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(driving_tired_fields, "driving_tired_{key}_checkbox")

        # 超速专用复选框
        over_speed_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(over_speed_fields, "over_speed_{key}_checkbox")

        # 急变道专用复选框
        sudden_lane_change = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sudden_lane_change, "sudden_lane_change_{key}_checkbox")

        # 2.10 无制动减速专用复选框
        deceleration_without_brake_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "before_speed": ("触发前车速", True),
            "after_speed": ("触发后车速", True),
            "value": ("减速度值", True),
            "brake_status": ("制动状态", True),
            "window_duration": ("确认窗时长", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(deceleration_without_brake_fields, "deceleration_without_brake_{key}_checkbox")

        # 2.11 严重急转弯专用复选框
        severe_sharp_turn_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "Turn": ("触发值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(severe_sharp_turn_fields, "severe_sharp_turn_{key}_checkbox")

        # 2.12 高速急转弯专用复选框
        high_speed_sharp_turn_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "event_average_speed": ("事件平均车速", True),
            "peak_lateral_acceleration": ("横向加速度峰值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(high_speed_sharp_turn_fields, "high_speed_sharp_turn_{key}_checkbox")

        # 2.13 急启动专用复选框
        rapid_start_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "speed_at_trigger": ("触发车速", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(rapid_start_fields, "rapid_start_{key}_checkbox")

        # 2.14 急停止专用复选框
        rapid_stop_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "deceleration_start_speed": ("减速开始车速", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(rapid_stop_fields, "rapid_stop_{key}_checkbox")

        # 2.15 猛踩油门专用复选框
        throttle_stomp_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "throttle_before": ("前窗油门", True),
            "window_end_throttle": ("窗尾油门", True),
            "throttle_increment": ("油门增量", True),
            "severity": ("严重级别", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(throttle_stomp_fields, "throttle_stomp_{key}_checkbox")

        # 2.16 频繁制动专用复选框
        frequent_braking_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "window_duration": ("统计窗时长", True),
            "valid_brake_count": ("有效制动次数", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(frequent_braking_fields, "frequent_braking_{key}_checkbox")

        # 2.17 长时间怠速专用复选框
        long_time_idle_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "idle_level": ("怠速级别", True),
            "continuous_idle_duration": ("连续怠速时长", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(long_time_idle_fields, "long_time_idle_{key}_checkbox")

        # 2.18 怠速占比过高专用复选框
        excessive_idle_ratio_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "start_time": ("统计开始时间", True),
            "end_time": ("统计结束时间", True),
            "idle_time": ("怠速时间", True),
            "engine_running_time": ("发动机运行时间", True),
            "idle_ratio": ("怠速比", True),
            "idle_ratio_threshold": ("怠速比阈值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(excessive_idle_ratio_fields, "excessive_idle_ratio_{key}_checkbox")

        # 2.19 高转速行驶专用复选框
        high_rpm_driving_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "average_rpm": ("平均转速", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(high_rpm_driving_fields, "high_rpm_driving_{key}_checkbox")

        # 2.20 怠速高转速专用复选框
        high_rpm_at_idle_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "average_rpm": ("平均转速", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(high_rpm_at_idle_fields, "high_rpm_at_idle_{key}_checkbox")

        # 2.21 高发动机负荷专用复选框
        high_engine_load_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "load_mean": ("负荷平均值", True),
            "severity": ("严重级别", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(high_engine_load_fields, "high_engine_load_{key}_checkbox")

        # 2.22 低效驾驶专用复选框
        inefficient_driving_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "fuel_per_distance": ("单位里程油耗", True),
            "threshold": ("平台阈值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(inefficient_driving_fields, "inefficient_driving_{key}_checkbox")

        # 2.23 低速频繁启停专用复选框
        low_speed_frequent_stop_start_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "ignition_switch_count": ("点火开关次数", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(low_speed_frequent_stop_start_fields, "low_speed_frequent_stop_start_{key}_checkbox")

        # 2.24 车速波动过大专用复选框
        excessive_speed_fluctuation_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "window_average_speed": ("窗口平均车速", True),
            "adjacent_speed_change": ("相邻车速变化", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(excessive_speed_fluctuation_fields, "excessive_speed_fluctuation_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第三章：复选框合集
        # ════════════════════════════════════════════════════════

        # GPS专用复选框
        gps_location_data_fields = {
            "imei": ("IMEI", True),
            "num": ("GPS数", True),
            "time": ("GPS时间", True),
            "source": ("位置源", True),
            "validity": ("有效性", True),
            "longitude": ("经度", True),
            "latitude": ("纬度", True),
            "sate_num": ("卫星数", True),
            "height": ("高度", True),
            "longitude_value": ("经度值", True),
            "latitude_value": ("纬度值", True),
            "gps_speed": ("GPS速度", True),
            "heading": ("航向角", True),
            "pdop": ("PDOP", True),
            "hdop": ("HDOP", True),
            "vdop": ("VDOP", True),
            "hacc": ("HACC", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(gps_location_data_fields, "gps_location_data_{key}_checkbox")

        # LBS 专用复选框
        lbs_location_data_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "mcc_mnc": ("PLMN", True),
            "radio_type": ("类型", True),
            "carrier_name": ("运营商", True),
            "consider_ip": ("参考IP", True),
            # "cell_num": ("小区个数", True),
            "cell_list": ("小区列表", True),
            # "wifi_num": ("WIFI列表", True),
            "wifi_list": ("WIFI列表", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(lbs_location_data_fields, "lbs_location_data_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第四章：复选框合集
        # ════════════════════════════════════════════════════════

        # VIN码专用复选框
        vin_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "type": ("协议类型", True),
            "length": ("VIN长度", True),
            "vin_value": ("VIN码", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(vin_fields, "vin_{key}_checkbox")

        # 数据流专用复选框
        dataflow_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "engine_coolant_temperature": ("发动机冷却液温度", True),
            "throttle_position": ("节气门位置", True),
            "engine_duty": ("发动机负荷", True),
            "intake_air_flow": ("进气流量", True),
            "intake_air_temperature": ("进气温度", True),
            "intake_air_pressure": ("进气压力", True),
            "battery_voltage": ("电池电压", True),
            "fuel_level": ("油量", True),
            "distance_dtcs_cleared": ("DTC清除后距离", True),
            "distance_mil": ("故障灯点亮后距离", True),
            "historical_total_mileage": ("历史总里程", True),
            "historical_total_fuel_consumption": ("历史总油耗", True),
            "historical_total_driving_time": ("历史总行驶时间", True),
            "seatbelt_status": ("安全带状态", True),
            "odometer": ("里程表", True),
            "average_fuel_consumption": ("平均油耗", True),
            "odometer_unit": ("里程单位", True),
            "soc": ("SOC", True),
            "soh": ("SOH", True),
            "battery_pack_current": ("电池电流", True),
            "battery_pack_voltage": ("电池电压", True),
            "battery_pack_charging": ("充电状态", True),
            "remaining_distance": ("剩余里程", True),
            "battery_pack_temperature": ("电池包温度", True),
            "distance_till_next_servicing": ("下次保养里程", True),
            "engine_run_time": ("发动机运行时间", True),
            "fuel_type": ("油品类型", True),
            "turn_signals_status": ("转向灯状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(dataflow_fields, "dataflow_{key}_checkbox")

        # can 支持参数状态专用复选框
        can_parameter_support_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "vin": ("vin", True),
            "gasoline_ev": ("gasoline_ev", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(can_parameter_support_status_fields, "can_parameter_support_status_{key}_checkbox")

        # 原始CAN消息帧
        raw_can_frame_fields = {
            "imei": ("IMEI", True),
            "time": ("IMEI", True),
            "canbuspins": ("canbuspins", True),
            "num_canframe": ("num", True),
            "canframeid_raw": ("canframeid_raw", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(raw_can_frame_fields, "raw_can_frame_{key}_checkbox")

        # config 数据流专用复选框
        config_dataflow_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "klv": ("数据流", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(config_dataflow_fields, "config_dataflow_{key}_checkbox")

        # 动态数据流 KLV
        vehicle_Information_klv_fields = {
            "imei": ("IMEI", True),
            # "time": ("触发时间", True),
            "klv_data": ("消息内容", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(vehicle_Information_klv_fields, "vehicle_Information_klv_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第五章：复选框合集
        # ════════════════════════════════════════════════════════

        # DTC码专用复选框
        dtc_code_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "obd_dtc_num": ("DTC个数", True),
            "obd_dtc_data": ("DTC码", True),
            "private_code_num": ("私有DTC个数", False),
            "private_code_data": ("私有DTC", False),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(dtc_code_fields, "dtc_code_{key}_checkbox")

        # 低电压专用复选框
        battery_low_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "battery_voltage": ("电压", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(battery_low_fields, "battery_low_{key}_checkbox")

        # 震动事件专用复选框
        vibration_event_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "vibration_value": ("震动值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(vibration_event_fields, "vibration_event_{key}_checkbox")

        # 疑似碰撞专用复选框
        suspected_collision_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "collision_value": ("碰撞值", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(suspected_collision_fields, "suspected_collision_{key}_checkbox")

        # 拔出告警专用复选框
        unplug_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "unplug_state": ("拔出状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(unplug_warning_fields, "unplug_warning_{key}_checkbox")

        # 干扰检测专用复选框
        jamming_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "jamming_status": ("干扰状态", True),
            "jamming_type": ("干扰类型", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(jamming_detection_fields, "jamming_detection_{key}_checkbox")

        # 设备防拆告警
        device_tamper_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_tamper_warning_fields, "device_tamper_warning_{key}_checkbox")

        # 温度告警
        temperature_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "temperature_value": ("温度值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(temperature_warning_fields, "temperature_warning_{key}_checkbox")

        # 气压告警
        air_pressure_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(air_pressure_warning_fields, "air_pressure_warning_{key}_checkbox")

        # 冲击告警
        shock_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "num": ("NUM", True),
            "sensor_data": ("冲击值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(shock_warning_fields, "shock_warning_{key}_checkbox")

        # 5.11 Ambient light detection warning
        ambient_light_detection_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("Trigger Time", True),
            "raw_data": ("Raw Data", False),
        }
        self._create_checkboxes(ambient_light_detection_warning_fields, "ambient_light_detection_warning_{key}_checkbox")

        # 5.12 Humidity warning
        humidity_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "humidity_value": ("湿度值", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(humidity_warning_fields, "humidity_warning_{key}_checkbox")

        # 5.13 设备告警信息
        device_warning_message_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "klv_data": ("告警信息", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_warning_message_fields, "device_warning_message_{key}_checkbox")

        # 5.14 DTC code (for J1939)
        j1939_dtc_code_fields = {
            "imei": ("IMEI", True),
            "time": ("Trigger Time", True),
            "dtc_information": ("DTC Information", True),
            "raw_data": ("Raw Data", False)
        }
        self._create_checkboxes(j1939_dtc_code_fields, "j1939_dtc_code_{key}_checkbox")

        # 电子围栏告警 5.15 - Fence warning
        fence_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "id": ("ID", True),
            "type": ("Type", True),
            "location": ("Location", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(fence_warning_fields, "fence_warning_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第六章：复选框合集
        # ════════════════════════════════════════════════════════

        # 休眠状态专用复选框
        sleep_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "sleep_voltage": ("电压", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(sleep_state_fields, "sleep_state_{key}_checkbox")

        # 唤醒状态专用复选框
        wakeup_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "wakeup_voltage": ("电压", True),
            "wakeup_type": ("唤醒类型", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(wakeup_state_fields, "wakeup_state_{key}_checkbox")

        # 长时间无法定位专用复选框
        gps_not_fix_fielad = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(gps_not_fix_fielad, "gps_not_fix_{key}_checkbox")

        # 重启事件专用复选框
        reboot_event_fields = {
            "imei": ("IMEI", True),
            "power_on_time": ("上电时间", True),
            "power_off_time": ("断电时间", True),
            "reboot_reason": ("重启原因", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(reboot_event_fields, "reboot_event_{key}_checkbox")

        # MCU升级状态专用复选框
        mcu_upgrade_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "upgrade_state": ("升级状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(mcu_upgrade_state_fields, "mcu_upgrade_state_{key}_checkbox")

        # 6.6 SMS专用复选框
        sms_fields = {
            "imei": ("IMEI", True),
            "utc_time": ("触发时间", True),
            "sms_time": ("短信时间", True),
            "phone_num": ("电话号码", True),
            "encoding": ("编码格式", True),
            "message": ("消息", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sms_fields, "sms_{key}_checkbox")

        # 6.7 设备信息专用复选框
        device_info_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            # "length_of_phone_number": ("手机号长度", True),
            "phone_number": ("手机号", True),
            # "length_of_iccid": ("ICCID长度", True),
            "iccid": ("ICCID", True),
            # "length_of_imsi": ("IMSI长度", True),
            "imsi": ("IMSI", True),
            # "length_of_wifi_mac": ("WiFi MAC长度", True),
            "wifi_mac": ("WiFi MAC", True),
            # "length_of_bt_mac": ("蓝牙MAC长度", True),
            "bt_mac": ("蓝牙MAC", True),
            # "length_of_wifi_mac_5g": ("5G WiFi MAC长度", True),
            "wifi_mac_5g": ("5G WiFi MAC", True),
            "softerware_ble_version": ("BLE版本", True),
            "softerware_gnss_version": ("GNSS版本", True),
            "softerware_boot_version": ("BOOT版本", True),
            "softerware_ap_version": ("AP版本", True),
            "mcc": ("MCC", True),
            # "length_of_mnc": ("MNC长度", True),
            "mnc": ("MNC", True),
            "cfg_file_version": ("配置版本", True),
            "gl103_workmode": ("GL103模式", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(device_info_fields, "device_info_{key}_checkbox")

        # 6.8 sensor_normal事件专用复选框
        sensor_normal_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "time_interval": ("时间间隔", True),
            "sensor_status": ("sensor状态", True),
            "number": ("sensor数量", True),
            "x_axis": ("X轴", True),
            "y_axis": ("Y轴", True),
            "z_axis": ("Z轴", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sensor_normal_fields, "sensor_normal_{key}_checkbox")

        # 6.9 sensor_event 事件专用复选框
        sensor_event_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "happen_time": ("发生时间", True),
            "event_time": ("事件时间", True),
            "collection_time": ("采集时间", True),
            "collection_time_ms": ("采集时间(ms)", True),
            "time_interval": ("时间间隔", True),
            "event_type": ("事件类型", True),
            "sensor_state": ("sensor状态", True),
            "sensor_num": ("sensor数量", True),
            "x_axis": ("X轴", True),
            "y_axis": ("Y轴", True),
            "z_axis": ("Z轴", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(sensor_event_fields, "sensor_event_{key}_checkbox")

        # 6.10 Modem Upgrade state
        modem_upgrade_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "upgrade_state": ("升级状态", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(modem_upgrade_state_fields, "modem_upgrade_state_{key}_checkbox")

        # 6.11 继电器控制状态专用复选框
        relay_control_status_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "relay_control_status": ("控制状态", True),
            "event_trigger_reason": ("原因", True),
            "ibutton_id": ("iButton ID", True),
            "rfid_id": ("RFID ID", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(relay_control_status_fields, "relay_control_status_{key}_checkbox")

        # 6.12 自学习专用复选框
        self_learning_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "calibration_status": ("学习状态", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(self_learning_status_fields, "self_learning_status_{key}_checkbox")

        # 6.13 Upgrade status of other components
        other_components_upgrade_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "upgrade_state": ("升级状态", True),
            "type": ("类型", True),
            "raw_data": ("Raw Data", False)
        }
        self._create_checkboxes(other_components_upgrade_status_fields, "other_components_upgrade_status_{key}_checkbox")

        # 6.14-6.30 新增第六章协议
        workmode_switch_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "workmode": ("当前模式", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(workmode_switch_status_fields, "workmode_switch_status_{key}_checkbox")

        device_collected_temperature_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "package_num": ("温度包数量", True),
            "collection_time": ("采集时间", True),
            "temperature": ("温度", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_collected_temperature_fields, "device_collected_temperature_{key}_checkbox")

        device_collected_air_pressure_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "package_num": ("气压包数量", True),
            "collection_time": ("采集时间", True),
            "air_pressure": ("气压", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_collected_air_pressure_fields, "device_collected_air_pressure_{key}_checkbox")

        movement_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "movement_state": ("运动状态", True),
            "location_data": ("Location Data 1", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(movement_detection_fields, "movement_detection_{key}_checkbox")

        sensor_data_for_debugging_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "package_num": ("包数量", True),
            "package_index": ("包序号", True),
            "collection_time": ("采集时间", True),
            "milliseconds": ("毫秒", True),
            "x_axis": ("X轴", True),
            "y_axis": ("Y轴", True),
            "z_axis": ("Z轴", True),
            "x_gyro": ("X陀螺仪", True),
            "y_gyro": ("Y陀螺仪", True),
            "z_gyro": ("Z陀螺仪", True),
            "speed_source": ("速度来源", True),
            "gps_status": ("GPS状态", True),
            "sensor_status": ("传感器状态", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(sensor_data_for_debugging_fields, "sensor_data_for_debugging_{key}_checkbox")

        switched_input_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "event_type": ("事件类型", True),
            "input_pin": ("输入状态", True),
            "gps_data": ("GPS位置", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(switched_input_detection_fields, "switched_input_detection_{key}_checkbox")

        pulse_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "input_pin": ("输入状态", True),
            "gps_data": ("GPS位置", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(pulse_detection_fields, "pulse_detection_{key}_checkbox")

        profile_download_result_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "iccid_length": ("ICCID长度", True),
            "iccid": ("ICCID", True),
            "result": ("下载结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(profile_download_result_fields, "profile_download_result_{key}_checkbox")

        ble_relay_binding_update_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "binding_state": ("绑定状态", True),
            "mac_address": ("BLE中继MAC", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(ble_relay_binding_update_fields, "ble_relay_binding_update_{key}_checkbox")

        sos_warning_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "event_type": ("事件类型", True),
            "input_pin": ("触发输入", True),
            "gps_data": ("GPS位置", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(sos_warning_detection_fields, "sos_warning_detection_{key}_checkbox")

        few_sensor_data_fields = {
            "imei": ("IMEI", True),
            "klv_data": ("KLV数据", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(few_sensor_data_fields, "few_sensor_data_{key}_checkbox")

        device_collected_data_fields = {
            "imei": ("IMEI", True),
            "klv_data": ("KLV数据", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(device_collected_data_fields, "device_collected_data_{key}_checkbox")

        flight_mode_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "flight_mode_state": ("飞行模式状态", True),
            "location_data": ("Location Data 1", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(flight_mode_detection_fields, "flight_mode_detection_{key}_checkbox")

        # 博世碰撞专用复选框
        bosch_collision_fields = {
            "imei": ("IMEI", True),
            "report_time": ("触发时间", True),
            "event_time": ("事件时间", True),
            "crash_index": ("碰撞指数", True),
            "crash_status": ("碰撞状态", True),
            "crash_event_counter": ("事件计数器", True),
            "crash_frame_counter": ("事件结构", True),
            "error_status": ("错误状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(bosch_collision_fields, "bosch_crash_{key}_checkbox")


        # ════════════════════════════════════════════════════════
        #       第七章：复选框合集
        # ════════════════════════════════════════════════════════

        # 请求MCU更新包（TCP）专用复选框
        request_mcu_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "file_name_length": ("长度", True),
            "file_name": ("文件名", True),
            "staring_position": ("起始位置", True),
            "request_length_bytes": ("数据长度", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_mcu_update_package_fields, "request_mcu_update_package_tcp_{key}_checkbox")

    # 请求AGPS专用复选框
        request_agps_data_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "longitude": ("经度", True),
            "longitude_value": ("经度数值", True),
            "latitude": ("纬度", True),
            "latitude_value": ("纬度数值", True),
            "ages_service_type": ("服务器类型", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_agps_data_fields, "request_agps_data_{key}_checkbox")

    # MCU更新包验证（TCP）专用复选框
        mcu_update_package_validation_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "file_name_length": ("长度", True),
            "file_name": ("文件名称", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(mcu_update_package_validation_fields, "mcu_update_package_verification_tcp_{key}_checkbox")

    # MCU日志上报 专用复选框
        mcu_log_report_fields = {
            "imei": ("IMEI", True),
            "log_type": ("日志类型", True),
            "log_id": ("日志ID", True),
            "offset": ("日志偏移", True),
            "logdata": ("日志数据", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(mcu_log_report_fields, "mcu_log_report_{key}_checkbox")

    # 检查新的更新包（路由器） 专用复选框
        check_new_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "mdm_version": ("MDM版本", True),
            "ap_version": ("AP版本", True),
            "cfg_version": ("CFG版本", True),
            "request_type": ("请求类型", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(check_new_update_package_fields, "check_new_update_package_router_{key}_checkbox")

    #  对新更新包的响应（适用于路由器) 专用复选框
        response_new_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "fota_task_id": ("任务ID", True),
            "response_fota_task": ("响应结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(response_new_update_package_fields, "response_to_new_update_package_router_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第八章：复选框合集
        # ════════════════════════════════════════════════════════

        request_mcu_update_via_tcp_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "server_address_port": ("服务器地址端口", True),
            "file_name": ("文件名", True),
            "current_state": ("当前状态", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_mcu_update_via_tcp_fields, "request_mcu_update_via_tcp_{key}_checkbox")

        # 8.2 设置参数专用复选框
        set_parameters_fields = {
            "imei": ("IMEI", True),
            "set_result": ("设置结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(set_parameters_fields, "set_parameters_{key}_checkbox")

        # 8.3 参数查询专用复选框
        inquiry_parameters_fields = {
            "imei": ("IMEI", True),
            "inquiry_result": ("查询结果", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(inquiry_parameters_fields, "inquiry_parameters_{key}_checkbox")

        request_fota_update_http_ftp_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "origin_version": ("原始版本", True),
            "target_version": ("目标版本", True),
            "fota_type": ("FOTA类型", True),
            "transfer_protocol": ("传输协议", True),
            "url": ("URL", True),
            "update_file_md5": ("升级文件MD5", True),
            "current_state": ("当前状态", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_fota_update_http_ftp_fields, "request_fota_update_http_ftp_{key}_checkbox")

        request_device_information_router_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "report_time": ("上报时间", True),
            "wifi_mac_24g": ("Wi-Fi MAC(2.4GHz)", True),
            "wifi_mac_5g": ("Wi-Fi MAC(5GHz)", True),
            "modem_version": ("Modem软件版本", True),
            "hardware_version": ("硬件版本", True),
            "ap_version": ("AP软件版本", True),
            "cfg_version": ("CFG文件版本", True),
            "rsrp": ("RSRP", True),
            "rscp": ("RSCP", True),
            "rssi": ("RSSI", True),
            "modem_temperature": ("Modem芯片温度", True),
            "wan_ipv4": ("WAN IPv4", True),
            "wan_ipv6": ("WAN IPv6", True),
            "sim_card": ("当前SIM卡", True),
            "lan1_status": ("LAN1状态", True),
            "lan2_status": ("LAN2状态", True),
            "gps_data": ("GPS数据", True),
            "ssh_username": ("SSH用户名", True),
            "ssh_password": ("SSH密码", True),
            "mobile_ipv4": ("Mobile IPv4", True),
            "mobile_ipv6": ("Mobile IPv6", True),
            "ssh_port": ("SSH端口", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_device_information_router_fields, "request_device_information_router_{key}_checkbox")

        request_device_cfg_file_router_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "cfg_file_type": ("CFG文件类型", True),
            "upload_url": ("上传URL", True),
            "report_time": ("上报时间", True),
            "result": ("结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_device_cfg_file_router_fields, "request_device_cfg_file_router_{key}_checkbox")

        request_device_log_snapshot_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "starting_address": ("起始地址", True),
            "snapshot_length": ("日志快照长度", True),
            "snapshot_data": ("快照数据", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(request_device_log_snapshot_fields, "request_device_log_snapshot_{key}_checkbox")

        # 8.8 白名单配置响应专用复选框
        whitelist_management_fields = {
            "imei": ("IMEI", True),
            "operation_result": ("操作结果", True),
            "type": ("类型", True),
            "num_of_ids": ("已有ID数量", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(whitelist_management_fields, "whitelist_management_{key}_checkbox")

        # 8.9 配件白名单查询-RFID-IBUTTON
        whitelist_query_fields = {
            "imei": ("IMEI", True),
            "type": ("类型", True),
            "length_id": ("ID长度", True),
            "multi_frame_flag": ("消息帧数", True),
            "current_response_message": ("消息索引", True),
            "number_of_ids": ("ID数量", True),
            "ids": ("ID列表", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(whitelist_query_fields, "whitelist_query_{key}_checkbox")

        request_esim_profile_update_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "sim_name": ("SIM名称", True),
            "iccid": ("ICCID", True),
            "activation_code": ("激活码", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(
            request_esim_profile_update_fields,
            "request_esim_profile_update_{key}_checkbox"
        )

        # 电子围栏响应 8.11.2
        message_fence_device_response_fields = {
            "imei": ("IMEI", True),
            "operation_result": ("操作结果", True),
            "num": ("围栏个数", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(message_fence_device_response_fields, "message_fence_device_response_{key}_checkbox")

        # 电子围栏查询 8.12.2
        query_fence_to_device_fields = {
            "imei": ("IMEI", True),
            "total_num": ("围栏总数", True),
            "start_id": ("开始ID", True),
            "message_num": ("消息数", True),
            "fence_data": ("围栏消息", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(query_fence_to_device_fields, "query_fence_to_device_{key}_checkbox")

        request_raw_can_frame_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "communication_type": ("CAN通信类型", True),
            "canbus_pins": ("CANBus Pins", True),
            "request_can_id": ("请求CAN ID", True),
            "request_can_data": ("请求CAN数据", True),
            "request_timeout": ("请求超时(ms)", True),
            "response_can_id_count": ("响应CAN ID数量", True),
            "response_can_ids": ("响应CAN ID列表", True),
            "capture_duration": ("捕获时长(s)", True),
            "result": ("结果", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(
            request_raw_can_frame_fields,
            "request_raw_can_frame_{key}_checkbox"
        )

        data_flow_management_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "operation_type": ("操作类型", True),
            "tlv_count": ("操作TLV数量", True),
            "tlv_keys": ("TLV Key列表", True),
            "operation_result": ("操作结果", True),
            "stored_tlv_count": ("设备存储TLV数量", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(
            data_flow_management_fields,
            "data_flow_management_{key}_checkbox"
        )

        data_flow_query_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "operation_result": ("操作结果", True),
            "stored_tlv_count": ("设备存储TLV数量", True),
            "tlv_keys": ("TLV Key列表", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(
            data_flow_query_fields,
            "data_flow_query_{key}_checkbox"
        )

        # ════════════════════════════════════════════════════════
        #       第九章：复选框合集
        # ════════════════════════════════════════════════════════

        # 9.1 ibutton 上报
        ibutton_id_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "ibutton_id": ("iButton ID", True),
            "authentication_status": ("身份验证状态", True),
            "gps_data": ("GPS数据", False),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ibutton_id_fields, "ibutton_id_{key}_checkbox")

        # 9.2 胎压上报
        ble_sensor_data_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "front_left_pressure": ("左前胎压", True),
            "front_right_pressure": ("右前胎压", True),
            "rear_left_pressure": ("左后胎压", True),
            "rear_right_pressure": ("右后胎压", True),
            "front_left_temperature": ("左前胎温", True),
            "front_right_temperature": ("右前胎温", True),
            "rear_left_temperature": ("左后胎温", True),
            "rear_right_temperature": ("右后胎温", True),
            "front_left_battery": ("左前电池", True),
            "front_right_battery": ("右前电池", True),
            "rear_left_battery": ("左后电池", True),
            "rear_right_battery": ("右后电池", True),
            "tire_status_of_tire": ("胎压状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ble_sensor_data_fields, "ble_sensor_data_{key}_checkbox")

        # 温湿度传感器
        rs485_temperature_humidity_fields = {
            "imei": ("IMEI", True),
            "num": ("传感器数量", True),
            "time": ("上报时间", True),
            "temperature": ("温度", True),
            "humidity": ("湿度", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(rs485_temperature_humidity_fields, "rs485_temperature_humidity_{key}_checkbox")

        # 9.4 胎压告警
        ble_sensor_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "warning_type": ("告警类型", True),
            "warning_position": ("告警位置", True),
            "warning_pressure": ("告警胎压", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ble_sensor_warning_fields, "ble_sensor_warning_{key}_checkbox")

        # 9.5 RFID数据上报
        rfid_data_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "rfid_id": ("RFID ID", True),
            "authentication_status": ("身份验证状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(rfid_data_fields, "rfid_data_{key}_checkbox")

        # 9.6 BLE温湿度传感器数据上报
        ble_temperature_humidity_sensor_fields = {
            "imei": ("IMEI", True),
            "total_report_messages": ("总上报报文数", True),
            "current_report_index": ("当前上报报文索引", True),
            "package_data_num": ("温湿度数据包数量", True),
            "package_data_length": ("数据包长度", True),
            "collection_time": ("采集时间(北京时间)", True),
            "temperature": ("温度(℃)", True),
            "humidity": ("湿度(%)", True),
            "battery_level": ("BLE THS电池电量(%)", True),
            "ble_ths_id_length": ("BLE THS ID长度", True),
            "ble_ths_id": ("BLE THS ID", True),
            "mac_address": ("传感器MAC地址", True),
            "door_state": ("门状态(ADS100)", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(
            ble_temperature_humidity_sensor_fields,
            "ble_temperature_humidity_sensor_{key}_checkbox"
        )

        # 9.7 BLE TAG 数据上报
        ble_tag_data_fields = {
            "imei": ("IMEI", True),
            "tag_num": ("标签数量", True),
            "UUID": ("UUID", True),
            "major": ("Major", True),
            "minor": ("Minor", True),
            "RSSI": ("RSSI", True),
            "battery": ("电池电量", True),
            "anti_tamper_status": ("防拆状态", True),
            "asensor_status": ("传感器状态", True),
            "raw_data": ("原始数据", False)
        }

        self._create_checkboxes(ble_tag_data_fields, "ble_tag_data_{key}_checkbox")

        # ════════════════════════════════════════════════════════
        #       第十章：复选框合集
        # ════════════════════════════════════════════════════════

        tachograph_data_transparent_transmission_fields = {
            "imei": ("IMEI", True),
            "frame_type": ("帧类型", True),
            "collection_time": ("采集时间", True),
            "data_length": ("数据长度", True),
            "data": ("数据", True),
            "raw_data": ("原始数据", False)
        }
        self._create_checkboxes(
            tachograph_data_transparent_transmission_fields,
            "tachograph_data_transparent_transmission_{key}_checkbox"
        )






        # EXCEL按键
        # 把导出EXCEL 这个按键添加到checkbox 这个布局中
        self.checkbox_layout.addWidget(self.export_button)

        # 把上面这个布局（包含按钮和其他控件）设置为复选框组 self.checkbox_group 的内部布局。
        self.checkbox_group.setLayout(self.checkbox_layout)
        # 设置复选框组的可见性为 False，初始时不显示
        self.checkbox_group.setVisible(False)
        self.export_button.setVisible(False)
        # 创建一个新的垂直布局对象 layout，用于后续把整个窗口的控件按垂直顺序排列
        layout = QVBoxLayout()

        # IMEI 输入框单独一行
        imei_layout = QHBoxLayout()
        imei_layout.addWidget(QLabel("IMEI Number(s):"))
        imei_layout.addWidget(self.imei_input)
        layout.addLayout(imei_layout)

        # 添加 "Auto EX" 按钮
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(5000)  # 5秒
        self.auto_timer_running = False  # 标志位
        # 新增：记录自动启动时刻，用于判断是否满1小时
        self.auto_timer.timeout.connect(self.auto_execute)
        self.auto_timer.timeout.connect(self.auto_execute)

        # 时间选择框：Start Time 和 Stop Time 一行
        time_layout = QHBoxLayout()
        time_layout.setSpacing(6)
        start_time_label = QLabel("Start Time:")
        start_time_label.setFixedWidth(65)
        time_layout.addWidget(start_time_label)
        time_layout.addWidget(self.start_time_input)
        stop_time_label = QLabel("Stop Time:")
        stop_time_label.setFixedWidth(65)
        time_layout.addWidget(stop_time_label)
        time_layout.addWidget(self.stop_time_input)

        # 添加 "Real Time" 按钮
        real_time_button = QPushButton("Real Time")
        real_time_button.setFixedWidth(120)
        real_time_button.clicked.connect(self.update_stop_time_to_now)
        time_layout.addWidget(real_time_button)

        # Auto EX 按钮
        self.auto_ex_button = QPushButton("Auto EX")
        self.auto_ex_button.setFixedWidth(120)
        self.auto_ex_button.clicked.connect(self.toggle_auto_execution)
        time_layout.addWidget(self.auto_ex_button)
        self.input_mode_label.setFixedWidth(30)
        time_layout.addWidget(self.input_mode_label)
        self.input_mode_combo.setFixedWidth(160)
        time_layout.addWidget(self.input_mode_combo)
        time_layout.addStretch()

        layout.addLayout(time_layout)

        # 定义按钮点击事件的槽函数
        def update_stop_time_to_current(self):
            self.stop_time_input.setDateTime(QDateTime.currentDateTime())

        # # 数据类型选择框：Select Data Type 和 Select Subtype 一行
        # data_layout = QHBoxLayout()
        # data_layout.addWidget(QLabel("Select Data Type:"))
        # data_layout.addWidget(self.dropdown1)
        # data_layout.addWidget(QLabel("Select Subtype:"))
        # data_layout.addWidget(self.dropdown2)
        # layout.addLayout(data_layout)

        # 自定义 宽度
        data_layout = QHBoxLayout()

        # 最后加一个 stretch，防止布局被拉伸
        # 全部左对齐：addStretch() 放最后
        # 全部右对齐：addStretch() 放最前

        # ========== 全部左对齐：标签1 + 下拉框1 ==========
        type_label = QLabel("Select Data Type:")
        type_label.setFixedWidth(130)
        data_layout.addWidget(type_label)

        self.dropdown1.setFixedWidth(220)
        self.dropdown1.setFixedHeight(28)
        data_layout.addWidget(self.dropdown1)

        # ========== 标签2 + 下拉框2 也靠左 ==========
        subtype_label = QLabel("Select Subtype:")
        subtype_label.setFixedWidth(110)
        data_layout.addWidget(subtype_label)

        self.dropdown2.setFixedWidth(340)
        self.dropdown2.setFixedHeight(28)
        data_layout.addWidget(self.dropdown2)

        # 在 Select Subtype 右侧增加协议码显示框
        code_label = QLabel("Code:")
        code_label.setFixedWidth(52)
        data_layout.addWidget(code_label)

        data_layout.addWidget(self.protocol_code_display)
        data_layout.addStretch()



        layout.addLayout(data_layout)

        layout.addWidget(self.local_hex_group)

        # 显示字段复选框
        layout.addWidget(self.checkbox_group)

        # 按钮行
        action_layout = QHBoxLayout()
        action_layout.addWidget(self.fetch_button)
        action_layout.addWidget(self.clear_button)
        layout.addLayout(action_layout)

        # 结果显示
        layout.addWidget(self.result_label)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.raw_data_display)

        # ===== 主布局：左侧原功能 + 右侧展开按钮 + 隐藏工具栏 =====
        main_layout = QHBoxLayout()

        # 左侧原来的主界面
        main_layout.addLayout(layout, 4)

        # 右侧展开/收起按钮
        # self.command_panel_toggle_btn = QPushButton("展开\n发送\n工具")
        self.command_panel_toggle_btn = QPushButton("协\n议\n下\n发\n查\n询\n工\n具")
        self.command_panel_toggle_btn.setFixedWidth(25)
        self.command_panel_toggle_btn.clicked.connect(self.toggle_command_panel)
        main_layout.addWidget(self.command_panel_toggle_btn)

        # 右侧发送工具栏，默认隐藏
        self.command_panel = self.create_command_panel()
        self.command_panel.setVisible(False)
        main_layout.addWidget(self.command_panel, 1)

        self.setLayout(main_layout)
        self.update_input_mode()

    def update_input_mode(self):
        is_local_mode = self.input_mode_combo.currentText() == "本地HEX"
        self.local_hex_group.setVisible(is_local_mode)
        self.fetch_button.setEnabled(not is_local_mode)
        self.local_parse_button.setEnabled(is_local_mode)
        self.imei_input.setEnabled(not is_local_mode)
        self.start_time_input.setEnabled(not is_local_mode)
        self.stop_time_input.setEnabled(not is_local_mode)

    def _resolve_local_hex_selection(self, line):
        if len(line) < 62:
            return None

        frame_type = line[48:50].upper()
        if frame_type == "01":
            return "0 - Connect or disconnect", "Connect"
        if frame_type == "0E":
            return "0 - Connect or disconnect", "Disconnect"
        if frame_type not in {"03", "04"}:
            return None

        code = line[58:62].upper()
        handler_by_code = {
            "0000": "process_trip_summary",
            "0001": "process_ignition_on",
            "0002": "process_ignition_off",
            "0003": "process_trip_start",
            "0004": "process_trip_end",
            "0100": "process_sudden_acc",
            "0101": "process_sudden_dec",
            "0102": "process_sharp_turn",
            "0103": "process_exceed_idle",
            "0104": "process_driving_tired",
            "0105": "process_over_speed",
            "0107": "process_sudden_lane_change",
            "0108": "process_severe_rapid_acceleration",
            "0109": "process_severe_rapid_deceleration",
            "010A": "process_deceleration_without_brake",
            "010B": "process_severe_sharp_turn",
            "010C": "process_high_speed_sharp_turn",
            "010D": "process_rapid_start",
            "010E": "process_rapid_stop",
            "010F": "process_throttle_stomp",
            "0110": "process_frequent_braking",
            "0111": "process_long_time_idle",
            "0112": "process_excessive_idle_ratio",
            "0113": "process_high_rpm_driving",
            "0114": "process_high_rpm_at_idle",
            "0115": "process_high_engine_load",
            "0116": "process_inefficient_driving",
            "0117": "process_low_speed_frequent_stop_start",
            "0118": "process_excessive_speed_fluctuation",
            "0200": "process_gps_data_3",
            "0201": "process_lbs_data",
            "0300": "process_vin_code",
            "0301": "process_data_flow",
            "0304": "process_can_parameter_support_status",
            "0305": "process_raw_can_frame",
            "0306": "process_config_data_flow",
            "0307": "process_vehicle_Information_klv",
            "0500": "process_dtc_code",
            "0501": "process_battery_low",
            "0502": "process_vibration_event",
            "0505": "process_suspected_collision",
            "0507": "process_unplug_warning",
            "050B": "process_jamming_detection",
            "050C": "process_device_tamper_warning",
            "050D": "process_temperature_warning",
            "050E": "process_air_pressure_warning",
            "050F": "process_shock_warning",
            "0510": "process_ambient_light_detection_warning",
            "0511": "process_humidity_warning",
            "0512": "process_device_warning_message",
            "050A": "process_j1939_dtc_code",
            "0513": "process_fence_warning",
            "0402": "process_sleep_state",
            "0403": "process_wakeup_state",
            "0404": "process_gps_not_fix",
            "0405": "process_reboot_event",
            "0406": "process_mcu_upgrade_state",
            "040B": "process_sms",
            "040C": "process_device_info",
            "040D": "process_sensor_normal",
            "040E": "process_sensor_event",
            "0413": "process_modem_upgrade_state",
            "0414": "process_relay_control_status",
            "0407": "process_self_learning_status",
            "0415": "process_other_components_upgrade_status",
            "0416": "process_workmode_switch_status",
            "0417": "process_device_collected_temperature",
            "0418": "process_device_collected_air_pressure",
            "0419": "process_movement_detection",
            "04F0": "process_sensor_data_for_debugging",
            "0425": "process_switched_input_detection",
            "0426": "process_pulse_detection",
            "0427": "process_profile_download_result",
            "0428": "process_ble_relay_binding_update",
            "0429": "process_sos_warning_detection",
            "042A": "process_few_sensor_data",
            "042B": "process_device_collected_data",
            "042C": "process_flight_mode_detection",
            "0410": "process_bosch_crash_data",
            "F001": "process_request_mcu_update_package_tcp",
            "F002": "process_request_agps_data",
            "F003": "process_mcu_update_package_verification_tcp",
            "F004": "process_mcu_log_report",
            "F100": "process_request_mcu_update_via_tcp",
            "F102": "process_set_parameters",
            "F103": "process_inquiry_parameters",
            "F108": "process_request_fota_update_http_ftp",
            "F109": "process_request_device_information_router",
            "F10A": "process_request_device_cfg_file_router",
            "F10B": "process_request_device_log_snapshot",
            "F10C": "process_whitelist_management",
            "F10D": "process_whitelist_query",
            "F10E": "process_request_esim_profile_update",
            "F10F": "process_message_fence_response",
            "F110": "process_query_fence_to_device",
            "F111": "process_request_raw_can_frame",
            "F112": "process_data_flow_management",
            "F113": "process_data_flow_query",
            "0601": "process_ibutton_id",
            "0602": "process_ble_sensor_data",
            "0603": "process_rs485_temperature_humidity",
            "0604": "process_ble_sensor_warning",
            "0605": "process_rfid_data",
            "0606": "process_ble_temperature_humidity_sensor_data",
            "0607": "process_ble_tag_data",
            "0701": "process_tachograph_data_transparent_transmission",
        }

        handler_name = handler_by_code.get(code)
        if not handler_name:
            return None

        for selection, current_handler_name in PROCESS_HANDLER_BY_SELECTION.items():
            if current_handler_name == handler_name:
                return selection
        return None

    def parse_local_hex_data(self):
        data_type = self.dropdown1.currentText()
        sub_type = self.dropdown2.currentText()

        raw_text = self.local_hex_input.text().strip()
        if not raw_text:
            self.result_label.setText("Please paste local HEX data.")
            return

        raw_data_string = [_normalize_hex_text(raw_text)]
        if not raw_data_string:
            self.result_label.setText("No valid HEX data.")
            return

        detected = self._resolve_local_hex_selection(raw_data_string[0])
        if detected:
            data_type, sub_type = detected
            self.dropdown1.setCurrentText(data_type)
            self.update_dropdown2()
            self.dropdown2.setCurrentText(sub_type)
            self.update_checkbox_visibility()

        if data_type not in SUBTYPE_OPTIONS:
            self.result_label.setText("Please select a valid data type.")
            return

        handler_name = PROCESS_HANDLER_BY_SELECTION.get((data_type, sub_type))
        if not handler_name:
            self.result_label.setText("No parser bound to the selected type.")
            return

        if handler_name != "display_protocol_consistency":
            valid_lines, validation_errors = self._prepare_valid_protocol_lines(raw_data_string)
            if validation_errors:
                self.result_label.setText(
                    f"协议校验失败，已停止解析：{validation_errors[0]}"
                )
                self.raw_data_display.setText("\n".join(validation_errors))
                return
            raw_data_string = valid_lines

        try:
            getattr(self, handler_name)(raw_data_string)
        except Exception as e:
            self.result_label.setText(f"解析失败，已停止当前章节：{handler_name}，错误：{e}")
            self.raw_data_display.setText("")

    def _create_checkboxes(self, fields, attr_template):
        group_name = attr_template.split("{key}", 1)[0].rstrip("_")
        widgets = []
        for key, (label, checked) in fields.items():
            checkbox = QCheckBox(label, self.checkbox_group)
            checkbox.setChecked(checked)
            checkbox.setVisible(False)
            setattr(self, attr_template.format(key=key), checkbox)
            widgets.append(checkbox)
        self.checkbox_sets[group_name] = widgets

    def _clear_checkbox_layout(self):
        while self.checkbox_layout.count():
            item = self.checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)

    def _add_checkbox_group(self, group_name, max_columns=4):
        widgets = self.checkbox_sets.get(group_name, [])
        for index, checkbox in enumerate(widgets):
            row = index // max_columns
            col = index % max_columns
            self.checkbox_layout.addWidget(checkbox, row, col)
            checkbox.setVisible(True)
        return (len(widgets) + max_columns - 1) // max_columns

    def _auto_parse_str(self):
        raw_txt = self.parse_input.toPlainText()
        txt = re.sub(r'\s+', '', raw_txt).upper()

        if len(txt) < 48:
            self.parse_result.setText("Length < 48")
            return

        imei = ascii_to_decimal(txt[18:48])
        result_parts = [f"IMEI: {imei}"]

        if len(txt) < 50:
            result_parts.append("Type: Length < 50")
            self.parse_result.setText("    ".join(result_parts))
            return

        frame_type = txt[48:50]
        frame_type_map = {
            "01": "connect",
            "02": "connack",
            "03": "publish",
            "04": "puback",
            "05": "publish_noack",
            "0C": "pingreq",
            "0D": "pingresp",
            "0E": "disconnect",
        }
        frame_type_name = frame_type_map.get(frame_type, f"unknown({frame_type})")
        result_parts.append(f"Type: {frame_type_name}")

        if frame_type == "03":
            if len(txt) < 62:
                result_parts.append("Code: Length < 62")
            else:
                result_parts.append(f"Code: {txt[58:62]}")

        self.parse_result.setText("    ".join(result_parts))

    def update_stop_time_to_now(self):
        current_time = QDateTime.currentDateTime()
        self.stop_time_input.setDateTime(current_time)

    # 实现自动更新时间执行获取数据
    def auto_execute(self):
        # 先判断是否运行满1小时（3600秒）
        if self.auto_start_datetime is not None:
            now = QDateTime.currentDateTime()
            # 计算已运行总秒数
            run_seconds = self.auto_start_datetime.secsTo(now)
            if run_seconds >= 3600:
            # if run_seconds >= 20:
                # 达到一小时，自动停止
                self.auto_timer.stop()
                self.auto_timer_running = False
                self.auto_start_datetime = None
                self.auto_ex_button.setText("Auto EX")
                # 一小时到了弹出提示框
                QMessageBox.information(self, "提示", "Auto EX已自动运行满1小时，已停止")
                return  # 直接退出，不再执行本次数据获取逻辑

        # 正常未超时，执行原有业务逻辑
        self.update_stop_time_to_now()
        self.fetch_data()

    def update_protocol_code_display(self):
        """
        根据当前选择的二级菜单，显示对应的协议码
        """
        sub_type = self.dropdown2.currentText()

        # 二级菜单与协议码显示的对应关系：用于更新界面右侧 Code 框。
        # key 是 Select Subtype 的显示名称，value 是协议文档中的 DATA_TYPE_MAJOR + DATA_TYPE_MINOR。
        menu_protocol_code_map = {

            # ════════════════ 第0章 ════════════════
            # "Connect": "00 01",
            # "Disconnect": "00 01",

            # ════════════════ 第1章 Trip data ════════════════
            "1.1 - trip summary": "00 00",
            "1.2 - Ignition on": "00 01",
            "1.3 - Ignition off": "00 02",
            "1.4 - trip start": "00 03",
            "1.5 - trip end": "00 04",

            # ════════════════ 第2章 Driving behavior ════════════════
            "2.1 - Sudden acc": "01 00",
            "2.2 - Sudden dec": "01 01",
            "2.3 - Sharp turn": "01 02",
            "2.4 - Exceed idle": "01 03",
            "2.5 - Driving tired": "01 04",
            "2.6 - Over speed": "01 05",
            "2.7 - Sudden Lane Change": "01 07",
            "2.8 - Severe Rapid Acceleration": "01 08",
            "2.9 - Severe Rapid Deceleration": "01 09",
            "2.10 - Deceleration Without Brake": "01 0A",
            "2.11 - Severe Sharp Turn": "01 0B",
            "2.12 - High-speed Sharp Turn": "01 0C",
            "2.13 - Rapid Start": "01 0D",
            "2.14 - Rapid Stop": "01 0E",
            "2.15 - Throttle Stomp": "01 0F",
            "2.16 - Frequent Braking": "01 10",
            "2.17 - Long-time Idle": "01 11",
            "2.18 - Excessive Idle Ratio": "01 12",
            "2.19 - High RPM Driving": "01 13",
            "2.20 - High RPM at Idle": "01 14",
            "2.21 - High Engine Load": "01 15",
            "2.22 - Inefficient Driving": "01 16",
            "2.23 - Low-speed Frequent Stop-start": "01 17",
            "2.24 - Excessive Speed Fluctuation": "01 18",

            # ════════════════ 第3章 Location data ════════════════
            "3.1 - GPS data": "02 00",
            "3.2 - LBS data": "02 01",

            # ════════════════ 第4章 Vehicle data ════════════════
            "4.1 - VIN Cold": "03 00",
            "4.2 - Data flow": "03 01",
            "4.3 - CAN parameter support status": "03 04",
            "4.4 - Raw can frame": "03 05",
            "4.5 - Config data flow": "03 06",
            "4.6 - Vehicle Information KLV": "03 07",

            # ════════════════ 第5章 Secure data ════════════════
            "5.1 - DTC code": "05 00",
            "5.2 - Battery low": "05 01",
            "5.3 - Vibration event": "05 02",
            "5.4 - Suspected collision": "05 05",
            "5.5 - Unplug warning": "05 07",
            "5.6 - Jamming detection": "05 0B",
            "5.7 - Device tamper warning": "05 0C",
            "5.8 - Temperature warning": "05 0D",
            "5.9 - Air pressure warning": "05 0E",
            "5.10 - Shock warning": "05 0F",
            "5.11 - Ambient light detection warning": "05 10",
            "5.12 - Humidity warning": "05 11",
            "5.13 - Device warning message": "05 12",
            "5.14 - DTC code (for J1939)": "05 0A",
            "5.15 - Fence warning": "05 13",

            # ════════════════ 第6章 Device state ════════════════
            "6.1 - Sleep state": "04 02",
            "6.2 - Wakeup state": "04 03",
            "6.3 - GPS not fix": "04 04",
            "6.4 - Reboot event": "04 05",
            "6.5 - Mcu upgrade state": "04 06",
            "6.6 - SMS": "04 0B",
            "6.7 - Device info": "04 0C",
            "6.8 - Sensor normal": "04 0D",
            "6.9 - Sensor event": "04 0E",
            "6.10 - Modem Upgrade state": "04 13",
            "6.11 - Relay control status": "04 14",
            "6.12 - Self learning status": "04 07",
            "6.13 - Upgrade status of other components": "04 15",
            "6.14 - Workmode Switch Status": "04 16",
            "6.15 - Device Collected Temperature": "04 17",
            "6.16 - Device Collected Air Pressure": "04 18",
            "6.17 - Movement Detection": "04 19",
            "6.18 - Heartbeat message (for Router)-暂不开发": "04 21",
            "6.19 - Modem Chipset High temperature warning (for Router)-暂不开发": "04 22",
            "6.20 - Weak Signal Warning (for Router)-暂不开发": "04 23",
            "6.21 - Sub-Device Disconnected Warning (for Router)-暂不开发": "04 24",
            "6.22 - Sensor Data for Debugging": "04 F0",
            "6.23 - Switched Input Detection": "04 25",
            "6.24 - Pulse Detection": "04 26",
            "6.25 - Profile Download Result": "04 27",
            "6.26 - BLE Relay Binding Update": "04 28",
            "6.27 - SOS Warning Detection": "04 29",
            "6.28 - Few Sensor Data": "04 2A",
            "6.29 - Device Collected Data": "04 2B",
            "6.30 - Flight Mode Detection": "04 2C",
            "Bosch crash data": "",

            # ════════════════ 第7章 Device request message ════════════════
            "7.1 -Request MCU update package(TCP)": "F0 01",
            "7.2 - Request AGPS data": "F0 02",
            "7.3 - MCU Update package verification(TCP)": "F0 03",
            "7.4 - MCU Log Report": "F0 04",
            "7.5 - Check new update package(Router)-暂不开发": "F0 05",
            "7.6 - Response to the New Update Package(Router)-暂不开发": "F0 06",

            # ════════════════ 第8章 Active server request ════════════════
            "8.1 - Request MCU update (via TCP)": "F1 00",
            "8.2 - Set parameters": "F1 02",
            "8.3 - Inquiry parameters": "F1 03",
            "8.4 - Request FOTA Update (via HTTP/FTP)": "F1 08",
            "8.5 - Request Device information (for Router)": "F1 09",
            "8.6 - Request Device CFG File (for Router)": "F1 0A",
            "8.7 - Request Device Log Snapshot": "F1 0B",
            "8.8 - whitelist management": "F1 0C",
            "8.9 - whitelist query": "F1 0D",
            "8.10 - Request eSIM profile update": "F1 0E",
            "8.11.2 - Management fence device response": "F1 0F",
            "8.12.2 - Query fence device response": "F1 10",
            "8.13 - Request RAW CAN Frame": "F1 11",
            "8.14 - Data Flow Management": "F1 12",
            "8.15 - Data Flow Query": "F1 13",

            # ════════════════ 第9章 Accessories information ════════════════
            "9.1 - Ibutton id": "06 01",
            "9.2 - Ble sensor data": "06 02",
            "9.3 - Rs485 temperature humidity": "06 03",
            "9.4 - Ble sensor warning": "06 04",
            "9.5 - Rfid data": "06 05",
            "9.6 - BLE Temperature Humidity Sensor Data": "06 06",
            "9.7 - Ble tag": "06 07",

            # ════════════════ 第10章 Tachograph ════════════════
            "10.1 - Data Transparent Transmission": "07 01",
        }

        code = menu_protocol_code_map.get(sub_type, "")
        self.protocol_code_display.setText(code)

    def toggle_auto_execution(self):
        if self.auto_timer_running:
            # 正在运行 → 手动停止
            self.auto_timer.stop()
            self.auto_timer_running = False
            self.auto_start_datetime = None  # 清空计时起点
            self.auto_ex_button.setText("Auto EX")
        else:
            # 未运行 → 开启自动执行，记录启动时间
            self.auto_start_datetime = QDateTime.currentDateTime()
            self.auto_timer.start()
            self.auto_timer_running = True
            self.auto_ex_button.setText("Stop Auto EX")

    # 导出EXCEL函数
    # def export_to_excel(self):
    #     text = self.raw_data_display.toPlainText()
    #     if not text.strip():
    #         self.result_label.setText("没有数据可导出")
    #         return
    #
    #     # 分行解析
    #     lines = text.strip().split('\n')
    #     if not lines or len(lines) < 2:
    #         self.result_label.setText("数据不足，无法导出")
    #         return
    #
    #     # 第一行为表头，其他为数据
    #     print("1111")
    #     headers = re.split(r'\s{2,}', lines[0].strip())  # 多个空格分隔
    #     print("2222")
    #     data_rows = [re.split(r'\s{2,}', line.strip()) for line in lines[1:]]
    #     print("666666")
    #
    #     clean_data_rows = [row for row in data_rows if len(row) == len(headers)]
    #     df = pd.DataFrame(clean_data_rows, columns=headers)
    #     # df = pd.DataFrame(data_rows, columns=headers)
    #     print("777777")
    #
    #     # 弹出保存文件对话框
    #     print("33333")
    #     file_path, _ = QFileDialog.getSaveFileName(self, "保存 Excel 文件", "", "Excel 文件 (*.xlsx)")
    #     print("444444")
    #     if file_path:
    #         try:
    #             df.to_excel(file_path, index=False)
    #             self.result_label.setText(f"导出成功: {file_path}")
    #         except Exception as e:
    #             self.result_label.setText(f"导出失败: {str(e)}")
    # 导出EXCEL函数-新
    def export_to_excel(self):
        text = self.raw_data_display.toPlainText()
        if not text.strip():
            self.result_label.setText("没有数据可导出")
            return

        # 按行分割文本
        lines = text.strip().split('\n')
        if not lines or len(lines) < 2:
            self.result_label.setText("数据不足，无法导出")
            return

        # 解析表头
        headers = re.split(r'\s{2,}', lines[0].strip())
        data_rows = []
        skipped_lines = []

        # 解析每一行数据
        for i, line in enumerate(lines[1:], start=2):
            row = re.split(r'\s{2,}', line.strip())
            if len(row) != len(headers):
                skipped_lines.append(i)
                print(f"⚠️ 第{i}行列数不匹配（{len(row)}列，应为{len(headers)}列）: {row}")
                continue
            data_rows.append(row)

        if not data_rows:
            self.result_label.setText("所有数据行格式异常，导出失败")
            return

        # 创建 DataFrame
        df = pd.DataFrame(data_rows, columns=headers)

        # 选择保存路径
        file_path, _ = QFileDialog.getSaveFileName(self, "保存 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if file_path:
            try:
                df.to_excel(file_path, index=False)
                if skipped_lines:
                    self.result_label.setText(f"导出成功: {file_path}（跳过 {len(skipped_lines)} 行格式错误）")
                else:
                    self.result_label.setText(f"导出成功: {file_path}")

                # 打开文件所在的文件夹
                file_path_start = os.path.dirname(file_path)  # 获取文件夹路径
                os.startfile(file_path_start)

            except Exception as e:
                self.result_label.setText(f"导出失败: {str(e)}")

    def export_to_excel(self):
        table_rows = getattr(self.raw_data_display, "_table_rows", None)
        skipped_lines = []

        if table_rows and len(table_rows) >= 2:
            headers = [cell.strip() for cell in table_rows[0]]
            data_rows = [
                [cell.replace(StripedTextEdit.CELL_LINE_BREAK, "\n") for cell in row]
                for row in table_rows[1:]
            ]
        else:
            text = self.raw_data_display.toPlainText()
            if not text.strip():
                self.result_label.setText("没有数据可导出")
                return

            lines = text.strip().split("\n")
            if len(lines) < 2:
                self.result_label.setText("数据不足，无法导出")
                return

            headers = re.split(r"\s{2,}", lines[0].strip())
            data_rows = []
            for i, line in enumerate(lines[1:], start=2):
                row = re.split(r"\s{2,}", line.strip())
                if len(row) != len(headers):
                    skipped_lines.append(i)
                    continue
                data_rows.append(row)

            if not data_rows:
                self.result_label.setText("所有数据行格式异常，导出失败")
                return

        df = pd.DataFrame(data_rows, columns=headers)

        file_path, _ = QFileDialog.getSaveFileName(self, "保存 Excel 文件", "", "Excel 文件 (*.xlsx)")
        if file_path:
            try:
                df.to_excel(file_path, index=False)
                if skipped_lines:
                    self.result_label.setText(f"导出成功: {file_path}（跳过 {len(skipped_lines)} 行格式错误）")
                else:
                    self.result_label.setText(f"导出成功: {file_path}")

                file_path_start = os.path.dirname(file_path)
                os.startfile(file_path_start)
            except Exception as e:
                self.result_label.setText(f"导出失败: {str(e)}")

    def update_dropdown2(self):
        selected = self.dropdown1.currentText()
        self.dropdown2.clear()
        self.dropdown2.addItems(SUBTYPE_OPTIONS.get(selected, ["Select Option"]))

    def update_checkbox_visibility(self):
        sub_type = self.dropdown2.currentText()

        self.update_protocol_code_display()
        self._clear_checkbox_layout()
        self.checkbox_group.setVisible(True)

        group_name = CHECKBOX_GROUP_BY_SUBTYPE.get(sub_type)
        next_row = 0
        if group_name:
            next_row = self._add_checkbox_group(group_name)

        self.checkbox_layout.addWidget(self.export_button, next_row, 0, 1, 4)
        self.export_button.setVisible(True)

    def fetch_data(self):
        data_type = self.dropdown1.currentText()
        sub_type = self.dropdown2.currentText()

        if data_type not in SUBTYPE_OPTIONS:
            self.result_label.setText("Please select a valid data type.")
            return

        imei_num_list = [self.clean_imei(imei.strip()) for imei in self.imei_input.text().split(",")]
        imei_num_list = [imei for imei in imei_num_list if imei]

        start_dt = self.start_time_input.dateTime().toPyDateTime() - timedelta(hours=8)
        stop_dt = self.stop_time_input.dateTime().toPyDateTime() - timedelta(hours=8)

        start_timestamp = int(start_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        stop_timestamp = int(stop_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

        raw_data = self.server_get_data(imei_num_list, start_timestamp, stop_timestamp)
        handler_name = PROCESS_HANDLER_BY_SELECTION.get((data_type, sub_type))
        if handler_name:
            if handler_name != "display_protocol_consistency":
                valid_lines, validation_errors = self._prepare_valid_protocol_lines(raw_data)
                if validation_errors:
                    self.result_label.setText(
                        f"协议校验失败：有效{len(valid_lines)}条，跳过{len(validation_errors)}条"
                    )
                    if not valid_lines:
                        self.raw_data_display.setText("\n".join(validation_errors[:1000]))
                        return
                    raw_data = valid_lines

            try:
                getattr(self, handler_name)(raw_data)
            except Exception as e:
                self.result_label.setText(f"解析失败，已停止当前章节：{handler_name}，错误：{e}")
                self.raw_data_display.setText("")

    def clean_imei(self, imei):
        return re.sub(r'[^0-9]+$', '', imei)

    def server_get_data(self, imei_num_list, start_timestamp, stop_timestamp):
        all_raw_data_string = []
        self.result_label.setText("Fetching data... Please wait.")
        self.raw_data_display.clear()

        for imei_num in imei_num_list:
            url = "http://10.85.40.3:8082/testAPI/rawData"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer YOUR_ACCESS_TOKEN'  # Replace this with actual token
            }

            offset = 0
            limit = 1000
            while True:
                payload = {
                    'imei': imei_num,
                    'start': start_timestamp,
                    'stop': stop_timestamp,
                    'offset': offset,
                    'limit': limit
                }

                try:
                    response = requests.post(url, headers=headers, json=payload)
                    if response.status_code == 200:
                        try:
                            batch = response.json()
                        except ValueError as e:
                            print("JSON decode error:", e)
                            break

                        if not isinstance(batch, list):
                            print("Unexpected response format:", type(batch))
                            break

                        lines = []
                        for entry in batch:
                            if isinstance(entry, dict) and "rawDataString" in entry:
                                lines.append(entry["rawDataString"])
                        all_raw_data_string.extend(lines)
                        if len(lines) < limit:
                            break
                        offset += limit
                    else:
                        print("Request failed:", response.status_code, response.text)
                        break
                except requests.exceptions.RequestException as e:
                    print("Request error:", e)
                    break

        return all_raw_data_string

    # ══════════════════════ RAW DATA ════════════════════════

    def display_raw_data(self, data):
        self.result_label.setText(f"Total raw lines: {len(data)}")
        self.raw_data_display.setText("\n".join(data[:1000]))

    def _iter_valid_raw_lines(self, raw_data_string):
        """
        统一的有效长度前置防护：
        1. 去空格并统一为大写
        2. 读取有效数据长度字段
        3. 确认实际长度至少覆盖到有效数据结束位置

        这样可以先挡住明显截断或越界的报文，再进入各章节的正常解析逻辑。
        """
        for raw_line in raw_data_string:
            if not raw_line:
                continue

            line = raw_line.replace(" ", "").upper()
            if len(line) < 58:
                continue

            try:
                effective_data_length = int(line[54:58], 16)
            except ValueError:
                continue

            payload_end = 58 + effective_data_length * 2
            if payload_end > len(line):
                continue

            yield line

    def _validate_protocol_line(self, raw_line):
        """校验单条协议报文，校验失败时不进入具体章节解析。"""
        line = _normalize_hex_text(raw_line)
        errors = []

        if not line:
            return False, line, "报文为空"
        if len(line) % 2 != 0:
            errors.append("HEX长度不是偶数")
        if not re.fullmatch(r"[0-9A-F]+", line):
            errors.append("包含非法HEX字符")
        if not line.startswith("5555"):
            errors.append("帧头不是5555")
        if not line.endswith("AAAA"):
            errors.append("帧尾不是AAAA")

        if len(line) < 58:
            errors.append(f"报文长度不足，当前为{len(line) // 2}字节")
            return False, line, "；".join(errors)

        try:
            message_length = int(line[4:8], 16)
        except ValueError:
            errors.append("消息长度字段无效")
            return False, line, "；".join(errors)

        actual_length = len(line) // 2
        if message_length != actual_length:
            errors.append(
                f"消息长度校验失败，报文声明{message_length}字节，实际{actual_length}字节"
            )

        try:
            effective_data_length = int(line[54:58], 16)
        except ValueError:
            errors.append("有效数据长度字段无效")
            return False, line, "；".join(errors)

        payload_end = 58 + effective_data_length * 2
        checksum_end = payload_end + 8
        frame_end_start = len(line) - 4

        if checksum_end > frame_end_start:
            errors.append(
                f"有效数据长度异常，需要到{payload_end // 2}字节，"
                f"但帧尾前只有{frame_end_start // 2}字节"
            )
            return False, line, "；".join(errors)

        checksum = line[payload_end:checksum_end].upper()
        try:
            calculated_checksum = adler32(
                bytes.fromhex(line[4:payload_end])
            ) & 0xFFFFFFFF
            calculated_checksum_hex = f"{calculated_checksum:08X}"
            if checksum != calculated_checksum_hex:
                errors.append(
                    f"Adler32校验失败，报文为{checksum}，计算为{calculated_checksum_hex}"
                )
        except ValueError:
            errors.append("校验数据不是有效HEX")

        # 校验有效数据、checksum之后的FF补位是否符合16字节对齐规则。
        actual_padding = line[checksum_end:frame_end_start].upper()
        encrypted_part = line[48:checksum_end]
        remainder = len(encrypted_part) % 32
        expected_padding = "" if remainder == 0 else "F" * (32 - remainder)
        if actual_padding != expected_padding:
            errors.append(
                f"FF补位校验失败，报文为{actual_padding or '无'}，"
                f"应为{expected_padding or '无'}"
            )

        if errors:
            return False, line, "；".join(errors)
        return True, line, "校验通过"

    def _prepare_valid_protocol_lines(self, raw_data_string):
        """过滤未通过协议校验的报文，并返回每条报文的失败原因。"""
        valid_lines = []
        validation_errors = []

        for index, raw_line in enumerate(raw_data_string or [], start=1):
            is_valid, line, error_message = self._validate_protocol_line(raw_line)
            if is_valid:
                valid_lines.append(line)
            else:
                validation_errors.append(f"第{index}条：{error_message}")

        return valid_lines, validation_errors

    def display_protocol_consistency(self, raw_data_string):
        """
        协议一致性检测：
        1. 解析基础字段
        2. 校验消息长度
        3. 使用 Adler32 校验 checksum
        4. 比对原始 FF 补位和计算补位是否一致
        """
        headers = [
            f"{'消息长度':<8}",
            f"{'协议版本':<10}",
            f"{'加密方式':<14}",
            f"{'电池电量':<8}",
            f"{'帧类型':<7}",
            f"{'帧序号':<7}",
            f"{'有效长度':<6}",
            f"{'数据类型':<26}",
            f"{'长度校验':<6}",
            f"{'checksum校验':<12}",
            f"{'FF补位校验':<8}",
        ]

        result_lines = ["".join(headers)]

        # 帧类型映射
        frame_type_map = {
            "01": "CONNECT",
            "02": "CONNACK",
            "03": "PUBLISH",
            "04": "PUBACK",
            "05": "PUBLISH_NOACK",
            "0C": "PINGREQ",
            "0D": "PINGRESP",
            "0E": "DISCONNECT"
        }

        # 协议码映射：key为协议码，value为显示名称
        # 报文协议码与协议名称的对应关系：用于 Protocol consistency 输出中展示数据类型名称。
        # key 是报文中的 4 位协议码，例如 0510；value 是输出时显示的协议名称。
        packet_protocol_name_map = {
            "0000": "trip summary",
            "0001": "Ignition on",
            "0002": "Ignition off",
            "0003": "trip start",
            "0004": "trip end",

            "0100": "Sudden acc",
            "0101": "Sudden dec",
            "0102": "Sharp turn",
            "0103": "Exceed idle",
            "0104": "Driving tired",
            "0105": "Over speed",
            "0107": "Sudden Lane Change",
            "0108": "Severe Rapid Acceleration",
            "0109": "Severe Rapid Deceleration",
            "010A": "Deceleration Without Brake",
            "010B": "Severe Sharp Turn",
            "010C": "High-speed Sharp Turn",
            "010D": "Rapid Start",
            "010E": "Rapid Stop",
            "010F": "Throttle Stomp",
            "0110": "Frequent Braking",
            "0111": "Long-time Idle",
            "0112": "Excessive Idle Ratio",
            "0113": "High RPM Driving",
            "0114": "High RPM at Idle",
            "0115": "High Engine Load",
            "0116": "Inefficient Driving",
            "0117": "Low-speed Frequent Stop-start",
            "0118": "Excessive Speed Fluctuation",
            "0200": "GPS data",
            "0201": "LBS data",

            "0300": "VIN Cold",
            "0301": "Data flow",
            "0304": "CAN parameter support status",
            "0305": "Raw can frame",
            "0306": "Config data flow",
            "0307": "Vehicle Information KLV",

            "0500": "DTC code",
            "0501": "Battery low",
            "0502": "Vibration event",
            "0505": "Suspected collision",
            "0507": "Unplug warning",
            "050B": "Jamming detection",
            "050C": "Device tamper warning",
            "050D": "Temperature warning",
            "050E": "Air pressure warning",
            "050F": "Shock warning",
            "0510": "Ambient light detection warning",
            "0511": "Humidity warning",
            "0512": "Device warning message",
            "050A": "J1939 DTC code",
            "0513": "Fence warning",

            "0402": "Sleep state",
            "0403": "Wakeup state",
            "0404": "GPS not fix",
            "0405": "Reboot event",
            "0406": "Mcu upgrade state",
            "040B": "SMS",
            "040C": "Device info",
            "040D": "Sensor normal",
            "040E": "Sensor event",
            "0414": "Relay control status",
            "0407": "Self learning status",
            "0415": "Upgrade status of other components",

            "F001": "Request MCU update package",
            "F002": "Request AGPS data",
            "F003": "MCU Update package verification",
            "F004": "MCU Log Report",
            "F005": "Check new update package",
            "F006": "Response to the New Update Package",

            "F100": "Request MCU update (via TCP)",
            "F102": "Set parameters",
            "F103": "Inquiry parameters",
            "F108": "Request FOTA Update (via HTTP/FTP)",
            "F109": "Request Device information (for Router)",
            "F10A": "Request Device CFG File (for Router)",
            "F10B": "Request Device Log Snapshot",
            "F10C": "whitelist management",
            "F10D": "whitelist query",
            "F10E": "Request eSIM profile update",
            "F10F": "Management fence device response",
            "F110": "Query fence device response",
            "F111": "Request RAW CAN Frame",
            "F112": "Data Flow Management",
            "F113": "Data Flow Query",

            "0601": "Ibutton id",
            "0602": "Ble sensor data",
            "0603": "Rs485 temperature humidity",
            "0604": "Ble sensor warning",
            "0605": "Rfid data",
            "0606": "BLE Temperature Humidity Sensor Data",
            "0607": "Ble tag",
            "0701": "Data Transparent Transmission",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            try:
                line = line.replace(" ", "").upper()

                if len(line) < 62:
                    result_lines.append(f"{'数据过短':<12}{line}")
                    continue

                # 消息总长度
                msg_length = int(line[4:8], 16)
                actual_length = len(line) // 2
                length_check_result = "PASS" if msg_length == actual_length else f"FAILFAIL({actual_length})"

                # 协议版本
                protocol_version_hex = line[8:12]
                byte1 = int(protocol_version_hex[0:2], 16)
                byte2 = int(protocol_version_hex[2:4], 16)

                major_version = (byte1 >> 4) & 0x0F
                minor_version = byte1 & 0x0F
                revision_version = byte2 & 0x3F
                protocol_version = f"V{major_version}.{minor_version}.{revision_version}"

                # 加密方式
                encryption_type = line[12:14].upper()
                encryption_map = {
                    "00": "DES-3 ECB",
                    "01": "AES-128 ECB",
                    "02": "AES-256 ECB",
                    "03": "AES-256 CBC",
                    "FF": "Without Encryption"
                }
                encryption_algorithm = encryption_map.get(encryption_type, f"Unknown({encryption_type})")

                # 电池电量
                battery_level_hex = line[16:18].upper()
                if battery_level_hex == "FF":
                    battery_level = "Not support"
                else:
                    battery_level = f"{int(battery_level_hex, 16)}%"

                # 帧类型
                frame_type = line[48:50].upper()
                frame_type_name = frame_type_map.get(frame_type, f"Unknown({frame_type})")

                # 帧序号
                frame_num = line[50:54].upper()

                # 有效数据长度
                effective_data_length = int(line[54:58], 16)

                # 数据类型显示
                data_type_display = frame_type_name

                if frame_type in ["03", "04"]:
                    data_type = line[58:62].upper()
                    data_type_name = packet_protocol_name_map.get(data_type, f"Unknown({data_type})")
                    data_type_display = data_type_name

                # 参与 Adler32 校验的数据
                encrypted_data = line[4:58 + effective_data_length * 2]

                checksum_start = len(encrypted_data) + 4
                checksum = line[checksum_start:checksum_start + 8].upper()

                # 原始FF补位
                raw_data_ff = line[checksum_start + 8:-4].upper()

                # 计算 Adler32
                calc_checksum = adler32(bytes.fromhex(encrypted_data)) & 0xFFFFFFFF
                calc_checksum_hex = f"{calc_checksum:08X}"

                checksum_result = "PASS" if checksum == calc_checksum_hex else f"FAILFAIL({calc_checksum_hex})"

                # 计算 FF 补位
                need_encrypt_data = line[48:58 + effective_data_length * 2 + 8]
                need_encrypt_data_len = len(need_encrypt_data)

                padding_hex = ""
                remainder = need_encrypt_data_len % 32

                if remainder != 0:
                    padding_len = 32 - remainder
                    padding_hex = "FF" * (padding_len // 2)

                ff_result = "PASS" if raw_data_ff == padding_hex else f"FAILFAIL({padding_hex})"

                row = [
                    f"{msg_length:<12}",
                    f"{protocol_version:<14}",
                    f"{encryption_algorithm:<18}",
                    f"{battery_level:<12}",
                    f"{frame_type:<10}",
                    f"{frame_num:<10}",
                    f"{effective_data_length:<10}",
                    f"{data_type_display:<30}",
                    f"{length_check_result:<10}",
                    f"{checksum_result:<14}",
                    f"{ff_result:<12}",
                ]

                result_lines.append("".join(row))

            except Exception as e:
                result_lines.append(f"{'解析异常':<12}{str(e):<30}{line}")

        self.result_label.setText(f"共检测 {len(raw_data_string)} 条协议数据")
        self.raw_data_display.setText("\n".join(result_lines[:1000]))

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第零章：万始花香总盛开，一切虚无零落尽 —— 开天
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════
    # 0.1 connect 帧
    def process_connect_data(self, raw_data_string):
        headers = []
        if self.connect_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.connect_time_checkbox.isChecked():
            headers.append(f"{'时间':<20}")
        if self.connect_hardware_version_checkbox.isChecked():
            headers.append(f"{'硬件版本':<16}")
        if self.connect_mcu_ap_version_checkbox.isChecked():
            headers.append(f"{'MCU/AP版本':<30}")
        if self.connect_mdm_version_checkbox.isChecked():
            headers.append(f"{'MDM版本':<30}")
        if self.connect_cfg_version_checkbox.isChecked():
            headers.append(f"{'配置版本':<10}")
        if self.connect_support_status_fota_checkbox.isChecked():
            headers.append(f"{'支持FOTA':<20}")
        if self.connect_ap_version_checkbox.isChecked():
            headers.append(f"{'AP版本':<30}")
        if self.connect_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        connect_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50].upper() == "01":
                imei = ascii_to_decimal(line[18:48])
                hardware_version = line[58:62]

                offset = 62

                # === 1. MCU AP Version ===
                mcu_ap_version_num = int(line[offset:offset + 2], 16)
                offset += 2  # 偏移后移 2 位

                if mcu_ap_version_num != 0:
                    mcu_ap_version = ascii_to_decimal(line[offset:offset + mcu_ap_version_num * 2])
                    offset += mcu_ap_version_num * 2  # 继续后移
                else:
                    mcu_ap_version = "N/A"

                # === 2. MDM Version ===
                mdm_version_num = int(line[offset:offset + 2], 16)
                offset += 2

                if mdm_version_num != 0:
                    mdm_version = ascii_to_decimal(line[offset:offset + mdm_version_num * 2])
                    offset += mdm_version_num * 2
                else:
                    mdm_version = "N/A"

                # === 3. Time (固定取 16 位 / 8字节) ===
                time_str = hex_to_beijing_time(line[offset:offset + 8])
                offset += 8

                # === 4. cfg version ===
                cfg_version_num = int(line[offset:offset + 2], 16)
                offset += 2

                if cfg_version_num != 0:
                    cfg_version = ascii_to_decimal(line[offset:offset + cfg_version_num * 2])
                    offset += cfg_version_num * 2
                else:
                    cfg_version = "N/A"

                # === 5. support FOTA ===
                fota_support = int(line[offset:offset + 2], 16)
                offset += 2

                mcu_tcp_support = (fota_support >> 0) & 1
                mcu_http_support = (fota_support >> 1) & 1

                # 输出成你能看懂的文字
                support_status_fota = ""
                if mcu_tcp_support and mcu_http_support:
                    support_status_fota = "TCP + HTTP"
                elif mcu_tcp_support:
                    support_status_fota = "TCP"
                elif mcu_http_support:
                    support_status_fota = "HTTP"
                else:
                    support_status_fota = "NOT FOTA"

                # AP版本是可选字段，部分数据里不存在。
                # 先根据有效数据长度计算边界，避免把 checksum / FF 补位误读成 AP 版本。
                effective_data_length = int(line[54:58], 16)
                payload_end = min(len(line), 58 + effective_data_length * 2)

                ap_version = "AP version not supported  "
                if offset + 2 <= payload_end:
                    ap_version_len = int(line[offset:offset + 2], 16)
                    offset += 2
                    ap_version_end = offset + ap_version_len * 2
                    if ap_version_len > 0 and ap_version_end <= payload_end:
                        ap_version = ascii_to_decimal(line[offset:ap_version_end])
                        offset = ap_version_end

                row = []
                if self.connect_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.connect_time_checkbox.isChecked():
                    row.append(f"{time_str:<22}")
                if self.connect_hardware_version_checkbox.isChecked():
                    row.append(f"{hardware_version:<20}")
                if self.connect_mcu_ap_version_checkbox.isChecked():
                    row.append(f"{mcu_ap_version:<32}")
                if self.connect_mdm_version_checkbox.isChecked():
                    row.append(f"{mdm_version:<32}")
                if self.connect_cfg_version_checkbox.isChecked():
                    row.append(f"{cfg_version:<14}")
                if self.connect_support_status_fota_checkbox.isChecked():
                    row.append(f"{support_status_fota:<22}")
                if self.connect_ap_version_checkbox.isChecked():
                    row.append(f"{ap_version:<32}")
                if self.connect_raw_data_checkbox.isChecked():
                    row.append(line)

                connect_times_1.append("".join(row))

        if connect_times_1:
            self.result_label.setText(f"共找到 {len(connect_times_1) - 1} 个连接事件")
            self.raw_data_display.setText("\n".join(connect_times_1))
        else:
            self.result_label.setText("未找到连接事件")
            self.raw_data_display.setText("")

    # 0.2 disconnect 帧
    def process_disconnect_data(self, raw_data_string):
        headers = []
        if self.disconnect_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.disconnect_time_checkbox.isChecked():
            headers.append(f"{'时间':<20}")
        if self.disconnect_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        disconnect_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            # print(line)
            # print(line[48:50])
            if line[48:50].upper()  == "0E":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[58:66])
                # print(line, imei, time_str)

                row = []
                if self.disconnect_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.disconnect_time_checkbox.isChecked():
                    row.append(f"{time_str:<20}")
                if self.disconnect_raw_data_checkbox.isChecked():
                    row.append(line)

                disconnect_times_1.append("".join(row))
        if disconnect_times_1:
            self.result_label.setText(f"共找到 {len(disconnect_times_1) - 1} 个断开连接事件")
            self.raw_data_display.setText("\n".join(disconnect_times_1))
        else:
            self.result_label.setText("未找到断开连接事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第一章：长相思兮长相忆，短相思兮无穷极 —— 相思
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 1.1 行程总结
    def process_trip_summary(self, raw_data_string):
        headers = []
        if self.trip_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.trip_start_time_checkbox.isChecked():
            headers.append(f"{'点火时间':<19}")
        if self.trip_end_time_checkbox.isChecked():
            headers.append(f"{'熄火时间':<19}")
        if self.trip_source_checkbox.isChecked():
            headers.append(f"{'统计来源':<6}")
        if self.trip_mileage_checkbox.isChecked():
            headers.append(f"{'行驶里程':<6}")
        if self.trip_fuel_consumption_checkbox.isChecked():
            headers.append(f"{'行程油耗':<6}")
        if self.trip_max_speed_checkbox.isChecked():
            headers.append(f"{'最高车速':<6}")
        if self.trip_idle_time_checkbox.isChecked():
            headers.append(f"{'怠速时间':<6}")
        if self.trip_idle_fuel_consumption_checkbox.isChecked():
            headers.append(f"{'怠速油耗':<6}")
        if self.trip_num_of_acceleration_checkbox.isChecked():
            headers.append(f"{'急加速次数':<7}")
        if self.trip_num_of_deceleration_checkbox.isChecked():
            headers.append(f"{'急减速次数':<7}")
        if self.trip_num_of_sharp_turn_checkbox.isChecked():
            headers.append(f"{'急转弯次数':<7}")
        if self.trip_histor_total_mil_checkbox.isChecked():
            headers.append(f"{'历史总里程':<7}")
        if self.trip_histor_total_fuel_checkbox.isChecked():
            headers.append(f"{'历史总油耗':<7}")
        if self.trip_histor_total_driving_time_checkbox.isChecked():
            headers.append(f"{'历史总行驶时间':<7}")
        if self.trip_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        trip_summary_event_times_1 = ["".join(headers)]
        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0000":
                imei = ascii_to_decimal(line[18:48])
                ignition_on_time_str = hex_to_beijing_time(line[62:70])
                # gps_location_when_ignition_on = line[70:118]  # GPS位置内容暂时忽略
                ignition_off_time_str = hex_to_beijing_time(line[118:126])
                # gps_location_when_ignition_off = line[126:174] # GPS位置内容暂时忽略

                # 取值先切片，输出16进制，然后转换为10进制，再转换为二进制
                # driving_distance_bin = bin(int(line[174:180], 16))[2:]
                driving_distance_bin = format(int(line[174:180], 16), '024b')

                source = driving_distance_bin[0]
                mileage = int(driving_distance_bin[-23:], 2)

                statistics_source = "OBD" if source == "0" else "GPS"
                trip_distance = mileage

                # trip_fuel_consumption = int(line[180:186], 16)
                trip_fuel_consumption = line[180:186] if line[180:186].upper() == "FFFFFF" else int(line[180:186], 16)
                max_speed = int(line[186:190], 16)
                idle_time = int(line[190:194], 16)
                # idle_fuel_consumption = int(line[194:198], 16)
                idle_fuel_consumption = line[194:198] if line[194:198].upper() == "FFFF" else int(line[194:198], 16)
                num_of_acceleration = int(line[198:200], 16)
                num_of_deceleration = int(line[200:202], 16)
                num_of_sharp_turn = int(line[202:204], 16)
                histor_total_mil = int(line[204:212], 16)
                # histor_total_fuel = int(line[212:220], 16)
                histor_total_fuel = line[212:220] if line[212:220].upper() == "FFFFFFFF" else int(line[212:220], 16)
                histor_total_driving_time = int(line[220:228], 16)

                row = []
                if self.trip_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.trip_start_time_checkbox.isChecked():
                    row.append(f"{ignition_on_time_str:<23}")
                if self.trip_end_time_checkbox.isChecked():
                    row.append(f"{ignition_off_time_str:<23}")
                if self.trip_source_checkbox.isChecked():
                    row.append(f"{statistics_source:<10}")
                if self.trip_mileage_checkbox.isChecked():
                    row.append(f"{trip_distance:<10}")
                if self.trip_fuel_consumption_checkbox.isChecked():
                    row.append(f"{trip_fuel_consumption:<10}")
                if self.trip_max_speed_checkbox.isChecked():
                    row.append(f"{max_speed:<10}")
                if self.trip_idle_time_checkbox.isChecked():
                    row.append(f"{idle_time:<10}")
                if self.trip_idle_fuel_consumption_checkbox.isChecked():
                    row.append(f"{idle_fuel_consumption:<10}")
                if self.trip_num_of_acceleration_checkbox.isChecked():
                    row.append(f"{num_of_acceleration:<12}")
                if self.trip_num_of_deceleration_checkbox.isChecked():
                    row.append(f"{num_of_deceleration:<12}")
                if self.trip_num_of_sharp_turn_checkbox.isChecked():
                    row.append(f"{num_of_sharp_turn:<12}")
                if self.trip_histor_total_mil_checkbox.isChecked():
                    row.append(f"{histor_total_mil:<12}")
                if self.trip_histor_total_fuel_checkbox.isChecked():
                    row.append(f"{histor_total_fuel:<12}")
                if self.trip_histor_total_driving_time_checkbox.isChecked():
                    row.append(f"{histor_total_driving_time:<12}")
                if self.trip_raw_data_checkbox.isChecked():
                    row.append(line)

                trip_summary_event_times_1.append("".join(row))

        if trip_summary_event_times_1:
            self.result_label.setText(f"共找到 {len(trip_summary_event_times_1) - 1} 个行程事件")
            self.raw_data_display.setText("\n".join(trip_summary_event_times_1))
        else:
            self.result_label.setText("未找到行程事件")
            self.raw_data_display.setText("")

    # 1.2 点火事件
    def process_ignition_on(self, raw_data_string):
        headers = []
        if self.eng_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.eng_type_checkbox.isChecked():
            headers.append(f"{'类型':<10}")
        if self.eng_time_checkbox.isChecked():
            headers.append(f"{'北京时间':<23}")
        if self.eng_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        ignition_on_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0001":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[64:72])

                type_code = line[62:64]
                ignition_type = {
                    "00": "RPM",
                    "04": "GPS",
                    "05": "SENSOR",
                    "06": "ACC ON",
                    "07": "Ready ON"
                }.get(type_code, type_code)

                row = []
                if self.eng_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.eng_type_checkbox.isChecked():
                    row.append(f"{ignition_type:<12}")
                if self.eng_time_checkbox.isChecked():
                    row.append(f"{time_str:<27}")
                if self.eng_raw_data_checkbox.isChecked():
                    row.append(line)

                ignition_on_event_times_1.append("".join(row))

        if ignition_on_event_times_1:
            self.result_label.setText(f"共找到 {len(ignition_on_event_times_1) - 1} 个点火事件")
            self.raw_data_display.setText("\n".join(ignition_on_event_times_1))
        else:
            self.result_label.setText("未找到点火事件")
            self.raw_data_display.setText("")

    # 1.3 熄火事件
    def process_ignition_off(self, raw_data_string):
        headers = []
        if self.eng_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.eng_type_checkbox.isChecked():
            headers.append(f"{'类型':<10}")
        if self.eng_time_checkbox.isChecked():
            headers.append(f"{'北京时间':<23}")
        if self.eng_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        ignition_off_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0002":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[64:72])

                type_code = line[62:64]
                ignition_type = {
                    "00": "RPM=0",
                    "02": "RPM不变",
                    "08": "GPS",
                    "09": "SENSOR",
                    "0a": "ACC OFF",
                    "0b": "主电断开",
                    "0c": "低电压",
                    "0d": "Ready OFF"
                }.get(type_code, type_code)

                row = []
                if self.eng_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.eng_type_checkbox.isChecked():
                    row.append(f"{ignition_type:<12}")
                if self.eng_time_checkbox.isChecked():
                    row.append(f"{time_str:<27}")
                if self.eng_raw_data_checkbox.isChecked():
                    row.append(line)

                ignition_off_event_times_1.append("".join(row))

        if ignition_off_event_times_1:
            self.result_label.setText(f"共找到 {len(ignition_off_event_times_1) - 1} 个熄火事件")
            self.raw_data_display.setText("\n".join(ignition_off_event_times_1))
        else:
            self.result_label.setText("未找到熄火事件")
            self.raw_data_display.setText("")

    # 1.4 拖车开始
    def process_trip_start(self, raw_data_string):
        headers = []
        if self.passive_trip_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.passive_trip_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<23}")
        if self.passive_trip_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        trip_start_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0003":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.passive_trip_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.passive_trip_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.passive_trip_raw_data_checkbox.isChecked():
                    row.append(line)

                trip_start_event_times_1.append("".join(row))

        if trip_start_event_times_1:
            self.result_label.setText(f"共找到 {len(trip_start_event_times_1) - 1} 个拖车开始事件")
            self.raw_data_display.setText("\n".join(trip_start_event_times_1))
        else:
            self.result_label.setText("未找到拖车开始事件")
            self.raw_data_display.setText("")

    # 1.5 拖车结束
    def process_trip_end(self, raw_data_string):
        headers = []
        if self.passive_trip_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.passive_trip_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<23}")
        if self.passive_trip_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        trip_end_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0004":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.passive_trip_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.passive_trip_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.passive_trip_raw_data_checkbox.isChecked():
                    row.append(line)

                trip_end_event_times_1.append("".join(row))

        if trip_end_event_times_1:
            self.result_label.setText(f"共找到 {len(trip_end_event_times_1) - 1} 个拖车结束事件")
            self.raw_data_display.setText("\n".join(trip_end_event_times_1))
        else:
            self.result_label.setText("未找到拖车结束事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第二章：相思一夜情多少，地角天涯未是长 —— 断肠
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 2.1 急加速事件
    def process_sudden_acc(self, raw_data_string):
        headers = []
        if self.sudden_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sudden_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sudden_before_speed_checkbox.isChecked():
            headers.append(f"{'触发前车速':<7}")
        if self.sudden_after_speed_checkbox.isChecked():
            headers.append(f"{'触发后车速':<7}")
        if self.sudden_value_checkbox.isChecked():
            headers.append(f"{'触发值':<5}")
        if self.sudden_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sudden_acc_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0100":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                before_speed = int(line[118:120], 16)
                after_speed = int(line[120:122], 16)
                value = int(line[122:124], 16) * 10  # 精度乘以10

                row = []
                if self.sudden_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sudden_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sudden_before_speed_checkbox.isChecked():
                    row.append(f"{before_speed:<12}")
                if self.sudden_after_speed_checkbox.isChecked():
                    row.append(f"{after_speed:<12}")
                if self.sudden_value_checkbox.isChecked():
                    row.append(f"{value:<8}")
                if self.sudden_raw_data_checkbox.isChecked():
                    row.append(line)

                sudden_acc_event_times_1.append("".join(row))

        if sudden_acc_event_times_1:
            self.result_label.setText(f"共找到 {len(sudden_acc_event_times_1) - 1} 个急加速事件")
            self.raw_data_display.setText("\n".join(sudden_acc_event_times_1))
        else:
            self.result_label.setText("未找到急加速事件")
            self.raw_data_display.setText("")

    # 2.2 急减速事件
    def process_sudden_dec(self, raw_data_string):
        headers = []
        if self.sudden_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sudden_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sudden_before_speed_checkbox.isChecked():
            headers.append(f"{'触发前车速':<7}")
        if self.sudden_after_speed_checkbox.isChecked():
            headers.append(f"{'触发后车速':<7}")
        if self.sudden_value_checkbox.isChecked():
            headers.append(f"{'触发值':<5}")
        if self.sudden_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sudden_dec_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0101":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                before_speed = int(line[118:120], 16)
                after_speed = int(line[120:122], 16)
                value = int(line[122:124], 16) * 10  # 精度乘以10

                row = []
                if self.sudden_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sudden_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sudden_before_speed_checkbox.isChecked():
                    row.append(f"{before_speed:<12}")
                if self.sudden_after_speed_checkbox.isChecked():
                    row.append(f"{after_speed:<12}")
                if self.sudden_value_checkbox.isChecked():
                    row.append(f"{value:<8}")
                if self.sudden_raw_data_checkbox.isChecked():
                    row.append(line)

                sudden_dec_event_times_1.append("".join(row))

        if sudden_dec_event_times_1:
            self.result_label.setText(f"共找到 {len(sudden_dec_event_times_1) - 1} 个急减速事件")
            self.raw_data_display.setText("\n".join(sudden_dec_event_times_1))
        else:
            self.result_label.setText("未找到急减速事件")
            self.raw_data_display.setText("")

    # 2.3 急转弯事件
    def process_sharp_turn(self, raw_data_string):
        headers = []
        if self.sharp_turn_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sharp_turn_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sharp_turn_Turn_checkbox.isChecked():
            headers.append(f"{'触发值':<5}")
        if self.sharp_turn_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sharp_turn_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0102":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                value = int(line[118:120], 16) * 10

                row = []
                if self.sharp_turn_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sharp_turn_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sharp_turn_Turn_checkbox.isChecked():
                    row.append(f"{value:<8}")
                if self.sharp_turn_raw_data_checkbox.isChecked():
                    row.append(line)

                sharp_turn_event_times_1.append("".join(row))

        if sharp_turn_event_times_1:
            self.result_label.setText(f"共找到 {len(sharp_turn_event_times_1) - 1} 个急转弯事件")
            self.raw_data_display.setText("\n".join(sharp_turn_event_times_1))
        else:
            self.result_label.setText("未找到急转弯事件")
            self.raw_data_display.setText("")

    # 2.4 怠速事件
    def process_exceed_idle(self, raw_data_string):
        headers = []
        if self.exceed_idle_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.exceed_idle_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.exceed_idle_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        exceed_idle_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0103":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.exceed_idle_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.exceed_idle_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.exceed_idle_raw_data_checkbox.isChecked():
                    row.append(line)

                exceed_idle_event_times_1.append("".join(row))

        if exceed_idle_event_times_1:
            self.result_label.setText(f"共找到 {len(exceed_idle_event_times_1) - 1} 个怠速事件")
            self.raw_data_display.setText("\n".join(exceed_idle_event_times_1))
        else:
            self.result_label.setText("未找到怠速事件")
            self.raw_data_display.setText("")

    # 2.5 疲劳驾驶事件
    def process_driving_tired(self, raw_data_string):
        headers = []
        if self.driving_tired_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.driving_tired_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.driving_tired_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        driving_tired_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0104":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.driving_tired_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.driving_tired_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.driving_tired_raw_data_checkbox.isChecked():
                    row.append(line)

                driving_tired_event_times_1.append("".join(row))

        if driving_tired_event_times_1:
            self.result_label.setText(f"共找到 {len(driving_tired_event_times_1) - 1} 个疲劳驾驶事件")
            self.raw_data_display.setText("\n".join(driving_tired_event_times_1))
        else:
            self.result_label.setText("未找到疲劳驾驶事件")
            self.raw_data_display.setText("")

    # 2.6 超速事件
    def process_over_speed(self, raw_data_string):
        headers = []
        if self.over_speed_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.over_speed_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.over_speed_value_checkbox.isChecked():
            headers.append(f"{'触发值':<5}")
        if self.over_speed_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        over_speed_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0105":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                value = int(line[70:72], 16)

                row = []
                if self.over_speed_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.over_speed_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.over_speed_value_checkbox.isChecked():
                    row.append(f"{value:<8}")
                if self.over_speed_raw_data_checkbox.isChecked():
                    row.append(line)

                over_speed_event_times_1.append("".join(row))

        if over_speed_event_times_1:
            self.result_label.setText(f"共找到 {len(over_speed_event_times_1) - 1} 个超速事件")
            self.raw_data_display.setText("\n".join(over_speed_event_times_1))
        else:
            self.result_label.setText("未找到超速事件")
            self.raw_data_display.setText("")

    # 2.7 急变道事件
    def process_sudden_lane_change(self, raw_data_string):
        headers = []
        if self.sudden_lane_change_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sudden_lane_change_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sudden_lane_change_value_checkbox.isChecked():
            headers.append(f"{'触发值':<5}")
        if self.sudden_lane_change_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sudden_lane_change_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0107":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                value = int(line[118:120], 16) * 10

                row = []
                if self.sudden_lane_change_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sudden_lane_change_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sudden_lane_change_value_checkbox.isChecked():
                    row.append(f"{value:<8}")
                if self.sudden_lane_change_raw_data_checkbox.isChecked():
                    row.append(line)

                sudden_lane_change_times_1.append("".join(row))

        if sudden_lane_change_times_1:
            self.result_label.setText(f"共找到 {len(sudden_lane_change_times_1) - 1} 个急变道事件")
            self.raw_data_display.setText("\n".join(sudden_lane_change_times_1))
        else:
            self.result_label.setText("未找到急变道事件")
            self.raw_data_display.setText("")

    # 2.8 Severe Rapid Acceleration
    def process_severe_rapid_acceleration(self, raw_data_string):
        headers = []
        if self.sudden_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sudden_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sudden_before_speed_checkbox.isChecked():
            headers.append(f"{'触发前车速':<7}")
        if self.sudden_after_speed_checkbox.isChecked():
            headers.append(f"{'触发后车速':<7}")
        if self.sudden_value_checkbox.isChecked():
            headers.append(f"{'峰值加速度':<7}")
        if self.sudden_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        severe_rapid_acceleration_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0108":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                before_speed = int(line[118:120], 16)
                after_speed = int(line[120:122], 16)
                value = int(line[122:124], 16) * 10

                row = []
                if self.sudden_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sudden_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sudden_before_speed_checkbox.isChecked():
                    row.append(f"{before_speed:<12}")
                if self.sudden_after_speed_checkbox.isChecked():
                    row.append(f"{after_speed:<12}")
                if self.sudden_value_checkbox.isChecked():
                    row.append(f"{value:<12}")
                if self.sudden_raw_data_checkbox.isChecked():
                    row.append(line)

                severe_rapid_acceleration_times_1.append("".join(row))

        if severe_rapid_acceleration_times_1:
            self.result_label.setText(f"共找到 {len(severe_rapid_acceleration_times_1) - 1} 个严重急加速事件")
            self.raw_data_display.setText("\n".join(severe_rapid_acceleration_times_1))
        else:
            self.result_label.setText("未找到严重急加速事件")
            self.raw_data_display.setText("")

    # 2.9 Severe Rapid Deceleration
    def process_severe_rapid_deceleration(self, raw_data_string):
        headers = []
        if self.sudden_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sudden_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sudden_before_speed_checkbox.isChecked():
            headers.append(f"{'触发前车速':<7}")
        if self.sudden_after_speed_checkbox.isChecked():
            headers.append(f"{'触发后车速':<7}")
        if self.sudden_value_checkbox.isChecked():
            headers.append(f"{'峰值减速度':<7}")
        if self.sudden_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        severe_rapid_deceleration_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0109":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                before_speed = int(line[118:120], 16)
                after_speed = int(line[120:122], 16)
                value = int(line[122:124], 16) * 10

                row = []
                if self.sudden_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sudden_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sudden_before_speed_checkbox.isChecked():
                    row.append(f"{before_speed:<12}")
                if self.sudden_after_speed_checkbox.isChecked():
                    row.append(f"{after_speed:<12}")
                if self.sudden_value_checkbox.isChecked():
                    row.append(f"{value:<12}")
                if self.sudden_raw_data_checkbox.isChecked():
                    row.append(line)

                severe_rapid_deceleration_times_1.append("".join(row))

        if severe_rapid_deceleration_times_1:
            self.result_label.setText(f"共找到 {len(severe_rapid_deceleration_times_1) - 1} 个严重急减速事件")
            self.raw_data_display.setText("\n".join(severe_rapid_deceleration_times_1))
        else:
            self.result_label.setText("未找到严重急减速事件")
            self.raw_data_display.setText("")

    # 2.10 无制动减速事件
    def process_deceleration_without_brake(self, raw_data_string):
        headers = []
        if self.deceleration_without_brake_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.deceleration_without_brake_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<23}")
        if self.deceleration_without_brake_before_speed_checkbox.isChecked():
            headers.append(f"{'触发前车速':<12}")
        if self.deceleration_without_brake_after_speed_checkbox.isChecked():
            headers.append(f"{'触发后车速':<12}")
        if self.deceleration_without_brake_value_checkbox.isChecked():
            headers.append(f"{'减速度值':<12}")
        if self.deceleration_without_brake_brake_status_checkbox.isChecked():
            headers.append(f"{'制动状态':<12}")
        if self.deceleration_without_brake_window_duration_checkbox.isChecked():
            headers.append(f"{'确认窗时长':<12}")
        if self.deceleration_without_brake_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        deceleration_without_brake_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "010A":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                before_speed = int(line[118:120], 16)
                after_speed = int(line[120:122], 16)
                value = int(line[122:124], 16) * 10
                brake_status_hex = line[124:126]
                if brake_status_hex == "00":
                    brake_status = "未踩下"
                elif brake_status_hex == "01":
                    brake_status = "踩下"
                else:
                    brake_status = brake_status_hex
                window_duration = int(line[126:128], 16) * 100

                row = []
                if self.deceleration_without_brake_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.deceleration_without_brake_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.deceleration_without_brake_before_speed_checkbox.isChecked():
                    row.append(f"{before_speed:<12}")
                if self.deceleration_without_brake_after_speed_checkbox.isChecked():
                    row.append(f"{after_speed:<12}")
                if self.deceleration_without_brake_value_checkbox.isChecked():
                    row.append(f"{value:<12}")
                if self.deceleration_without_brake_brake_status_checkbox.isChecked():
                    row.append(f"{brake_status:<12}")
                if self.deceleration_without_brake_window_duration_checkbox.isChecked():
                    row.append(f"{window_duration:<12}")
                if self.deceleration_without_brake_raw_data_checkbox.isChecked():
                    row.append(line)

                deceleration_without_brake_event_times_1.append("".join(row))

        if deceleration_without_brake_event_times_1:
            self.result_label.setText(f"共找到 {len(deceleration_without_brake_event_times_1) - 1} 个无制动减速事件")
            self.raw_data_display.setText("\n".join(deceleration_without_brake_event_times_1))
        else:
            self.result_label.setText("未找到无制动减速事件")
            self.raw_data_display.setText("")

    # 2.11 严重急转弯事件
    def process_severe_sharp_turn(self, raw_data_string):
        headers = []
        if self.severe_sharp_turn_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.severe_sharp_turn_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.severe_sharp_turn_Turn_checkbox.isChecked():
            headers.append(f"{'触发值':<12}")
        if self.severe_sharp_turn_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        severe_sharp_turn_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "010B":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                value = int(line[118:120], 16) * 10

                row = []
                if self.severe_sharp_turn_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.severe_sharp_turn_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.severe_sharp_turn_Turn_checkbox.isChecked():
                    row.append(f"{value:<12}")
                if self.severe_sharp_turn_raw_data_checkbox.isChecked():
                    row.append(line)

                severe_sharp_turn_event_times_1.append("".join(row))

        if severe_sharp_turn_event_times_1:
            self.result_label.setText(f"共找到 {len(severe_sharp_turn_event_times_1) - 1} 个严重急转弯事件")
            self.raw_data_display.setText("\n".join(severe_sharp_turn_event_times_1))
        else:
            self.result_label.setText("未找到严重急转弯事件")
            self.raw_data_display.setText("")

    # 2.12 高速急转弯事件
    def process_high_speed_sharp_turn(self, raw_data_string):
        headers = []
        if self.high_speed_sharp_turn_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.high_speed_sharp_turn_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.high_speed_sharp_turn_event_average_speed_checkbox.isChecked():
            headers.append(f"{'事件平均车速':<12}")
        if self.high_speed_sharp_turn_peak_lateral_acceleration_checkbox.isChecked():
            headers.append(f"{'横向加速度峰值':<12}")
        if self.high_speed_sharp_turn_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        high_speed_sharp_turn_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "010C":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                event_average_speed = int(line[118:120], 16)
                peak_lateral_acceleration = int(line[120:122], 16) * 10

                row = []
                if self.high_speed_sharp_turn_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.high_speed_sharp_turn_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.high_speed_sharp_turn_event_average_speed_checkbox.isChecked():
                    row.append(f"{event_average_speed:<12}")
                if self.high_speed_sharp_turn_peak_lateral_acceleration_checkbox.isChecked():
                    row.append(f"{peak_lateral_acceleration:<12}")
                if self.high_speed_sharp_turn_raw_data_checkbox.isChecked():
                    row.append(line)

                high_speed_sharp_turn_event_times_1.append("".join(row))

        if high_speed_sharp_turn_event_times_1:
            self.result_label.setText(f"共找到 {len(high_speed_sharp_turn_event_times_1) - 1} 个高速急转弯事件")
            self.raw_data_display.setText("\n".join(high_speed_sharp_turn_event_times_1))
        else:
            self.result_label.setText("未找到高速急转弯事件")
            self.raw_data_display.setText("")

    # 2.13 急启动事件
    def process_rapid_start(self, raw_data_string):
        headers = []
        if self.rapid_start_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.rapid_start_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.rapid_start_speed_at_trigger_checkbox.isChecked():
            headers.append(f"{'触发车速':<12}")
        if self.rapid_start_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        rapid_start_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "010D":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                speed_at_trigger = int(line[118:120], 16)

                row = []
                if self.rapid_start_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.rapid_start_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.rapid_start_speed_at_trigger_checkbox.isChecked():
                    row.append(f"{speed_at_trigger:<12}")
                if self.rapid_start_raw_data_checkbox.isChecked():
                    row.append(line)

                rapid_start_event_times_1.append("".join(row))

        if rapid_start_event_times_1:
            self.result_label.setText(f"共找到 {len(rapid_start_event_times_1) - 1} 个急启动事件")
            self.raw_data_display.setText("\n".join(rapid_start_event_times_1))
        else:
            self.result_label.setText("未找到急启动事件")
            self.raw_data_display.setText("")

    # 2.14 急停止事件
    def process_rapid_stop(self, raw_data_string):
        headers = []
        if self.rapid_stop_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.rapid_stop_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.rapid_stop_deceleration_start_speed_checkbox.isChecked():
            headers.append(f"{'减速开始车速':<12}")
        if self.rapid_stop_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        rapid_stop_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "010E":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                deceleration_start_speed = int(line[118:120], 16)

                row = []
                if self.rapid_stop_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.rapid_stop_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.rapid_stop_deceleration_start_speed_checkbox.isChecked():
                    row.append(f"{deceleration_start_speed:<12}")
                if self.rapid_stop_raw_data_checkbox.isChecked():
                    row.append(line)

                rapid_stop_event_times_1.append("".join(row))

        if rapid_stop_event_times_1:
            self.result_label.setText(f"共找到 {len(rapid_stop_event_times_1) - 1} 个急停止事件")
            self.raw_data_display.setText("\n".join(rapid_stop_event_times_1))
        else:
            self.result_label.setText("未找到急停止事件")
            self.raw_data_display.setText("")

    # 2.15 猛踩油门事件
    def process_throttle_stomp(self, raw_data_string):
        headers = []
        if self.throttle_stomp_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.throttle_stomp_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.throttle_stomp_throttle_before_checkbox.isChecked():
            headers.append(f"{'前窗油门':<12}")
        if self.throttle_stomp_window_end_throttle_checkbox.isChecked():
            headers.append(f"{'窗尾油门':<12}")
        if self.throttle_stomp_throttle_increment_checkbox.isChecked():
            headers.append(f"{'油门增量':<12}")
        if self.throttle_stomp_severity_checkbox.isChecked():
            headers.append(f"{'严重级别':<12}")
        if self.throttle_stomp_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        throttle_stomp_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "010F":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                throttle_before = int(line[118:120], 16)
                window_end_throttle = int(line[120:122], 16)
                throttle_increment = int(line[122:124], 16)
                severity_hex = line[124:126]
                if severity_hex == "00":
                    severity = "正常"
                elif severity_hex == "01":
                    severity = "严重"
                else:
                    severity = severity_hex

                row = []
                if self.throttle_stomp_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.throttle_stomp_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.throttle_stomp_throttle_before_checkbox.isChecked():
                    row.append(f"{throttle_before:<12}")
                if self.throttle_stomp_window_end_throttle_checkbox.isChecked():
                    row.append(f"{window_end_throttle:<12}")
                if self.throttle_stomp_throttle_increment_checkbox.isChecked():
                    row.append(f"{throttle_increment:<12}")
                if self.throttle_stomp_severity_checkbox.isChecked():
                    row.append(f"{severity:<12}")
                if self.throttle_stomp_raw_data_checkbox.isChecked():
                    row.append(line)

                throttle_stomp_event_times_1.append("".join(row))

        if throttle_stomp_event_times_1:
            self.result_label.setText(f"共找到 {len(throttle_stomp_event_times_1) - 1} 个猛踩油门事件")
            self.raw_data_display.setText("\n".join(throttle_stomp_event_times_1))
        else:
            self.result_label.setText("未找到猛踩油门事件")
            self.raw_data_display.setText("")

    # 2.16 频繁制动事件
    def process_frequent_braking(self, raw_data_string):
        headers = []
        if self.frequent_braking_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.frequent_braking_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.frequent_braking_window_duration_checkbox.isChecked():
            headers.append(f"{'统计窗时长':<12}")
        if self.frequent_braking_valid_brake_count_checkbox.isChecked():
            headers.append(f"{'有效制动次数':<12}")
        if self.frequent_braking_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        frequent_braking_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0110":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                window_duration = int(line[118:120], 16)
                valid_brake_count = int(line[120:122], 16)

                row = []
                if self.frequent_braking_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.frequent_braking_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.frequent_braking_window_duration_checkbox.isChecked():
                    row.append(f"{window_duration:<12}")
                if self.frequent_braking_valid_brake_count_checkbox.isChecked():
                    row.append(f"{valid_brake_count:<12}")
                if self.frequent_braking_raw_data_checkbox.isChecked():
                    row.append(line)

                frequent_braking_event_times_1.append("".join(row))

        if frequent_braking_event_times_1:
            self.result_label.setText(f"共找到 {len(frequent_braking_event_times_1) - 1} 个频繁制动事件")
            self.raw_data_display.setText("\n".join(frequent_braking_event_times_1))
        else:
            self.result_label.setText("未找到频繁制动事件")
            self.raw_data_display.setText("")

    # 2.17 长时间怠速事件
    def process_long_time_idle(self, raw_data_string):
        headers = []
        if self.long_time_idle_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.long_time_idle_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.long_time_idle_idle_level_checkbox.isChecked():
            headers.append(f"{'怠速级别':<12}")
        if self.long_time_idle_continuous_idle_duration_checkbox.isChecked():
            headers.append(f"{'连续怠速时长':<12}")
        if self.long_time_idle_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        long_time_idle_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0111":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                idle_level_hex = line[118:120]
                if idle_level_hex == "01":
                    idle_level = "低"
                elif idle_level_hex == "02":
                    idle_level = "中"
                elif idle_level_hex == "03":
                    idle_level = "高"
                else:
                    idle_level = idle_level_hex
                continuous_idle_duration = int(line[120:124], 16)

                row = []
                if self.long_time_idle_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.long_time_idle_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.long_time_idle_idle_level_checkbox.isChecked():
                    row.append(f"{idle_level:<12}")
                if self.long_time_idle_continuous_idle_duration_checkbox.isChecked():
                    row.append(f"{continuous_idle_duration:<12}")
                if self.long_time_idle_raw_data_checkbox.isChecked():
                    row.append(line)

                long_time_idle_event_times_1.append("".join(row))

        if long_time_idle_event_times_1:
            self.result_label.setText(f"共找到 {len(long_time_idle_event_times_1) - 1} 个长时间怠速事件")
            self.raw_data_display.setText("\n".join(long_time_idle_event_times_1))
        else:
            self.result_label.setText("未找到长时间怠速事件")
            self.raw_data_display.setText("")

    # 2.18 怠速占比过高事件
    def process_excessive_idle_ratio(self, raw_data_string):
        headers = []
        if self.excessive_idle_ratio_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.excessive_idle_ratio_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.excessive_idle_ratio_start_time_checkbox.isChecked():
            headers.append(f"{'统计开始时间':<23}")
        if self.excessive_idle_ratio_end_time_checkbox.isChecked():
            headers.append(f"{'统计结束时间':<23}")
        if self.excessive_idle_ratio_idle_time_checkbox.isChecked():
            headers.append(f"{'怠速时间':<12}")
        if self.excessive_idle_ratio_engine_running_time_checkbox.isChecked():
            headers.append(f"{'发动机运行时间':<12}")
        if self.excessive_idle_ratio_idle_ratio_checkbox.isChecked():
            headers.append(f"{'怠速比':<12}")
        if self.excessive_idle_ratio_idle_ratio_threshold_checkbox.isChecked():
            headers.append(f"{'怠速比阈值':<12}")
        if self.excessive_idle_ratio_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        excessive_idle_ratio_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0112":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                start_time = hex_to_beijing_time(line[118:126])
                end_time = hex_to_beijing_time(line[126:134])
                idle_time = int(line[134:138], 16)
                engine_running_time = int(line[138:142], 16)
                idle_ratio = int(line[142:144], 16)
                idle_ratio_threshold = int(line[144:146], 16)

                row = []
                if self.excessive_idle_ratio_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.excessive_idle_ratio_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.excessive_idle_ratio_start_time_checkbox.isChecked():
                    row.append(f"{start_time:<23}")
                if self.excessive_idle_ratio_end_time_checkbox.isChecked():
                    row.append(f"{end_time:<23}")
                if self.excessive_idle_ratio_idle_time_checkbox.isChecked():
                    row.append(f"{idle_time:<12}")
                if self.excessive_idle_ratio_engine_running_time_checkbox.isChecked():
                    row.append(f"{engine_running_time:<12}")
                if self.excessive_idle_ratio_idle_ratio_checkbox.isChecked():
                    row.append(f"{idle_ratio:<12}")
                if self.excessive_idle_ratio_idle_ratio_threshold_checkbox.isChecked():
                    row.append(f"{idle_ratio_threshold:<12}")
                if self.excessive_idle_ratio_raw_data_checkbox.isChecked():
                    row.append(line)

                excessive_idle_ratio_event_times_1.append("".join(row))

        if excessive_idle_ratio_event_times_1:
            self.result_label.setText(f"共找到 {len(excessive_idle_ratio_event_times_1) - 1} 个怠速占比过高事件")
            self.raw_data_display.setText("\n".join(excessive_idle_ratio_event_times_1))
        else:
            self.result_label.setText("未找到怠速占比过高事件")
            self.raw_data_display.setText("")

    # 2.19 高转速行驶事件
    def process_high_rpm_driving(self, raw_data_string):
        headers = []
        if self.high_rpm_driving_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.high_rpm_driving_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.high_rpm_driving_average_rpm_checkbox.isChecked():
            headers.append(f"{'平均转速':<12}")
        if self.high_rpm_driving_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        high_rpm_driving_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0113":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                average_rpm = int(line[118:122], 16)

                row = []
                if self.high_rpm_driving_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.high_rpm_driving_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.high_rpm_driving_average_rpm_checkbox.isChecked():
                    row.append(f"{average_rpm:<12}")
                if self.high_rpm_driving_raw_data_checkbox.isChecked():
                    row.append(line)

                high_rpm_driving_event_times_1.append("".join(row))

        if high_rpm_driving_event_times_1:
            self.result_label.setText(f"共找到 {len(high_rpm_driving_event_times_1) - 1} 个高转速行驶事件")
            self.raw_data_display.setText("\n".join(high_rpm_driving_event_times_1))
        else:
            self.result_label.setText("未找到高转速行驶事件")
            self.raw_data_display.setText("")

    # 2.20 怠速高转速事件
    def process_high_rpm_at_idle(self, raw_data_string):
        headers = []
        if self.high_rpm_at_idle_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.high_rpm_at_idle_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.high_rpm_at_idle_average_rpm_checkbox.isChecked():
            headers.append(f"{'平均转速':<12}")
        if self.high_rpm_at_idle_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        high_rpm_at_idle_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0114":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                average_rpm = int(line[118:122], 16)

                row = []
                if self.high_rpm_at_idle_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.high_rpm_at_idle_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.high_rpm_at_idle_average_rpm_checkbox.isChecked():
                    row.append(f"{average_rpm:<12}")
                if self.high_rpm_at_idle_raw_data_checkbox.isChecked():
                    row.append(line)

                high_rpm_at_idle_event_times_1.append("".join(row))

        if high_rpm_at_idle_event_times_1:
            self.result_label.setText(f"共找到 {len(high_rpm_at_idle_event_times_1) - 1} 个怠速高转速事件")
            self.raw_data_display.setText("\n".join(high_rpm_at_idle_event_times_1))
        else:
            self.result_label.setText("未找到怠速高转速事件")
            self.raw_data_display.setText("")

    # 2.21 高发动机负荷事件
    def process_high_engine_load(self, raw_data_string):
        headers = []
        if self.high_engine_load_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.high_engine_load_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.high_engine_load_load_mean_checkbox.isChecked():
            headers.append(f"{'负荷平均值':<12}")
        if self.high_engine_load_severity_checkbox.isChecked():
            headers.append(f"{'严重级别':<12}")
        if self.high_engine_load_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        high_engine_load_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0115":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                load_mean = int(line[118:120], 16)
                severity_hex = line[120:122]
                if severity_hex == "00":
                    severity = "正常"
                elif severity_hex == "01":
                    severity = "严重"
                else:
                    severity = severity_hex

                row = []
                if self.high_engine_load_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.high_engine_load_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.high_engine_load_load_mean_checkbox.isChecked():
                    row.append(f"{load_mean:<12}")
                if self.high_engine_load_severity_checkbox.isChecked():
                    row.append(f"{severity:<12}")
                if self.high_engine_load_raw_data_checkbox.isChecked():
                    row.append(line)

                high_engine_load_event_times_1.append("".join(row))

        if high_engine_load_event_times_1:
            self.result_label.setText(f"共找到 {len(high_engine_load_event_times_1) - 1} 个高发动机负荷事件")
            self.raw_data_display.setText("\n".join(high_engine_load_event_times_1))
        else:
            self.result_label.setText("未找到高发动机负荷事件")
            self.raw_data_display.setText("")

    # 2.22 低效驾驶事件
    def process_inefficient_driving(self, raw_data_string):
        headers = []
        if self.inefficient_driving_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.inefficient_driving_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.inefficient_driving_fuel_per_distance_checkbox.isChecked():
            headers.append(f"{'单位里程油耗':<12}")
        if self.inefficient_driving_threshold_checkbox.isChecked():
            headers.append(f"{'平台阈值':<12}")
        if self.inefficient_driving_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        inefficient_driving_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0116":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                fuel_per_distance = f"{int(line[118:122], 16) * 0.01:.2f}"
                threshold = f"{int(line[122:126], 16) * 0.01:.2f}"

                row = []
                if self.inefficient_driving_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.inefficient_driving_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.inefficient_driving_fuel_per_distance_checkbox.isChecked():
                    row.append(f"{fuel_per_distance:<12}")
                if self.inefficient_driving_threshold_checkbox.isChecked():
                    row.append(f"{threshold:<12}")
                if self.inefficient_driving_raw_data_checkbox.isChecked():
                    row.append(line)

                inefficient_driving_event_times_1.append("".join(row))

        if inefficient_driving_event_times_1:
            self.result_label.setText(f"共找到 {len(inefficient_driving_event_times_1) - 1} 个低效驾驶事件")
            self.raw_data_display.setText("\n".join(inefficient_driving_event_times_1))
        else:
            self.result_label.setText("未找到低效驾驶事件")
            self.raw_data_display.setText("")

    # 2.23 低速频繁启停事件
    def process_low_speed_frequent_stop_start(self, raw_data_string):
        headers = []
        if self.low_speed_frequent_stop_start_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.low_speed_frequent_stop_start_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.low_speed_frequent_stop_start_ignition_switch_count_checkbox.isChecked():
            headers.append(f"{'点火开关次数':<12}")
        if self.low_speed_frequent_stop_start_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        low_speed_frequent_stop_start_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0117":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                ignition_switch_count = int(line[118:120], 16)

                row = []
                if self.low_speed_frequent_stop_start_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.low_speed_frequent_stop_start_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.low_speed_frequent_stop_start_ignition_switch_count_checkbox.isChecked():
                    row.append(f"{ignition_switch_count:<12}")
                if self.low_speed_frequent_stop_start_raw_data_checkbox.isChecked():
                    row.append(line)

                low_speed_frequent_stop_start_event_times_1.append("".join(row))

        if low_speed_frequent_stop_start_event_times_1:
            self.result_label.setText(f"共找到 {len(low_speed_frequent_stop_start_event_times_1) - 1} 个低速频繁启停事件")
            self.raw_data_display.setText("\n".join(low_speed_frequent_stop_start_event_times_1))
        else:
            self.result_label.setText("未找到低速频繁启停事件")
            self.raw_data_display.setText("")

    # 2.24 车速波动过大事件
    def process_excessive_speed_fluctuation(self, raw_data_string):
        headers = []
        if self.excessive_speed_fluctuation_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.excessive_speed_fluctuation_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.excessive_speed_fluctuation_window_average_speed_checkbox.isChecked():
            headers.append(f"{'窗口平均车速':<12}")
        if self.excessive_speed_fluctuation_adjacent_speed_change_checkbox.isChecked():
            headers.append(f"{'相邻车速变化':<12}")
        if self.excessive_speed_fluctuation_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        excessive_speed_fluctuation_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0118":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                window_average_speed = int(line[118:120], 16)
                adjacent_speed_change = f"{int(line[120:122], 16) * 0.1:.1f}"

                row = []
                if self.excessive_speed_fluctuation_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.excessive_speed_fluctuation_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.excessive_speed_fluctuation_window_average_speed_checkbox.isChecked():
                    row.append(f"{window_average_speed:<12}")
                if self.excessive_speed_fluctuation_adjacent_speed_change_checkbox.isChecked():
                    row.append(f"{adjacent_speed_change:<12}")
                if self.excessive_speed_fluctuation_raw_data_checkbox.isChecked():
                    row.append(line)

                excessive_speed_fluctuation_event_times_1.append("".join(row))

        if excessive_speed_fluctuation_event_times_1:
            self.result_label.setText(f"共找到 {len(excessive_speed_fluctuation_event_times_1) - 1} 个车速波动过大事件")
            self.raw_data_display.setText("\n".join(excessive_speed_fluctuation_event_times_1))
        else:
            self.result_label.setText("未找到车速波动过大事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第三章：眼见为虚，心听则实 —— 盲龙
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 3.1 GPS消息
    def process_gps_data_3(self, raw_data_string):

        headers = []
        keys = []  # 用于记录字段 key，跟 headers 一一对应

        if self.gps_location_data_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.gps_location_data_num_checkbox.isChecked():
            headers.append(f"{'GPS数量':<7}")
        if self.gps_location_data_time_checkbox.isChecked():
            headers.append(f"{'GPS时间':<19}")
        if self.gps_location_data_source_checkbox.isChecked():
            headers.append(f"{'位置源':<5}")
        if self.gps_location_data_validity_checkbox.isChecked():
            headers.append(f"{'有效性':<9}")
        if self.gps_location_data_longitude_checkbox.isChecked():
            headers.append(f"{'经度':<5}")
        if self.gps_location_data_latitude_checkbox.isChecked():
            headers.append(f"{'纬度':<5}")
        if self.gps_location_data_sate_num_checkbox.isChecked():
            headers.append(f"{'卫星数':<5}")
        if self.gps_location_data_height_checkbox.isChecked():
            headers.append(f"{'高度':<4}")
        if self.gps_location_data_longitude_value_checkbox.isChecked():
            headers.append(f"{'经度值':<10}")
        if self.gps_location_data_latitude_value_checkbox.isChecked():
            headers.append(f"{'纬度值':<10}")
        if self.gps_location_data_gps_speed_checkbox.isChecked():
            headers.append(f"{'GPS速度':<7}")
        if self.gps_location_data_heading_checkbox.isChecked():
            headers.append(f"{'航向角':<6}")
        if self.gps_location_data_pdop_checkbox.isChecked():
            headers.append(f"{'PDOP':<6}")
        if self.gps_location_data_hdop_checkbox.isChecked():
            headers.append(f"{'HDOP':<6}")
        if self.gps_location_data_vdop_checkbox.isChecked():
            headers.append(f"{'VDOP':<6}")
        if self.gps_location_data_hacc_checkbox.isChecked():
            headers.append(f"{'HACC':<6}")
        if self.gps_location_data_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        gps_location_data_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0200":
                imei = ascii_to_decimal(line[18:48])
                gps_count = int(line[62:64], 16)
                if gps_count == 0:
                    gps_location_data_event_times_1.append("没有 GPS 数据")
                else:
                    for i in range(gps_count):
                        start = 64 + i * 48
                        end = start + 48
                        gps_data = line[start:end]
                        # print(gps_data)
                        if not isinstance(gps_data, str):
                            gps_data = str(gps_data)
                        try:
                            parsed = parse_gps_data(gps_data)
                            row = []

                            if self.gps_location_data_imei_checkbox.isChecked():
                                row.append(f"{imei:<20}")
                            if self.gps_location_data_num_checkbox.isChecked():
                                row.append(f"{gps_count:<9}")
                            if self.gps_location_data_time_checkbox.isChecked():
                                row.append(f"{parsed.get('Time', ''):<21}")
                            if self.gps_location_data_source_checkbox.isChecked():
                                row.append(f"{parsed.get('Positioning', ''):<8}")
                            if self.gps_location_data_validity_checkbox.isChecked():
                                row.append(f"{parsed.get('Time Type', ''):<12}")
                            if self.gps_location_data_longitude_checkbox.isChecked():
                                row.append(f"{parsed.get('Longitude Direction', ''):<7}")
                            if self.gps_location_data_latitude_checkbox.isChecked():
                                row.append(f"{parsed.get('Latitude Direction', ''):<7}")
                            if self.gps_location_data_sate_num_checkbox.isChecked():
                                row.append(f"{parsed.get('Sate Num', ''):<8}")
                            if self.gps_location_data_height_checkbox.isChecked():
                                row.append(f"{parsed.get('Height', ''):<6}")
                            if self.gps_location_data_longitude_value_checkbox.isChecked():
                                row.append(f"{parsed.get('Longitude', ''):<13}")
                            if self.gps_location_data_latitude_value_checkbox.isChecked():
                                row.append(f"{parsed.get('Latitude', ''):<13}")
                            if self.gps_location_data_gps_speed_checkbox.isChecked():
                                row.append(f"{parsed.get('GPS Speed', ''):<9}")
                            if self.gps_location_data_heading_checkbox.isChecked():
                                row.append(f"{parsed.get('Heading', ''):<9}")
                            if self.gps_location_data_pdop_checkbox.isChecked():
                                row.append(f"{parsed.get('PDOP', ''):<6}")
                            if self.gps_location_data_hdop_checkbox.isChecked():
                                row.append(f"{parsed.get('HDOP', ''):<6}")
                            if self.gps_location_data_vdop_checkbox.isChecked():
                                row.append(f"{parsed.get('VDOP', ''):<6}")
                            if self.gps_location_data_hacc_checkbox.isChecked():
                                row.append(f"{parsed.get('HACC', ''):<6}")
                            if self.gps_location_data_raw_data_checkbox.isChecked():
                                row.append(line)

                            gps_location_data_event_times_1.append("".join(row))

                        except Exception as e:
                            gps_location_data_event_times_1.append(f"GPS {i + 1} 解析失败: {str(e)}")

        if gps_location_data_event_times_1:
            self.result_label.setText(f"共找到 {len(gps_location_data_event_times_1) - 1} 个GPS数据包")
            self.raw_data_display.setText("\n".join(gps_location_data_event_times_1))
        else:
            self.result_label.setText("未找到GPS数据事件")
            self.raw_data_display.setText("")

    # 3.2 lbs事件
    def process_lbs_data(self, raw_data_string):
        headers = []
        if self.lbs_location_data_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.lbs_location_data_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<18}")
        if self.lbs_location_data_mcc_mnc_checkbox.isChecked():
            headers.append(f"{'PLMN':<8}")
        if self.lbs_location_data_radio_type_checkbox.isChecked():
            headers.append(f"{'类型':<4}")
        if self.lbs_location_data_carrier_name_checkbox.isChecked():
            headers.append(f"{'运营商':<11}")
        if self.lbs_location_data_consider_ip_checkbox.isChecked():
            headers.append(f"{'参考地址':<6}")
        # if self.lbs_location_data_cell_num_checkbox.isChecked():
        #     headers.append(f"{'小区数量':<6}")
        if self.lbs_location_data_cell_list_checkbox.isChecked():
            headers.append(f"{'小区列表(Cell id-PLMN-Location Code-RSSI)':<50}")
        # if self.lbs_location_data_wifi_num_checkbox.isChecked():
        #     headers.append(f"{'WiFi数量':<8}")
        if self.lbs_location_data_wifi_list_checkbox.isChecked():
            headers.append(f"{'WiFi列表':<40}")
        if self.lbs_location_data_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        lbs_location_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0201":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                # --------------------- 以下全部是我补全 ---------------------
                ptr = 62  # 时间结束位置：32-35字节 → 字符串62-70
                ptr += 8

                # 3. Home MCC 36-38 → 6位字符串
                home_mcc_hex = line[ptr:ptr + 6]
                home_mcc = bytes.fromhex(home_mcc_hex).decode("ascii").strip()
                ptr += 6

                # 4. Length of Home MNC
                home_mnc_len = int(line[ptr:ptr + 2], 16)
                ptr += 2

                # 5. Home MNC
                home_mnc_hex = line[ptr:ptr + home_mnc_len * 2]
                home_mnc = bytes.fromhex(home_mnc_hex).decode("ascii").strip()
                ptr += home_mnc_len * 2

                mcc_mnc = f"{home_mcc}{home_mnc}"

                # 6. Radio Type 02=GSM 03=WCDMA 04=LTE 05=5G
                radio_type_hex = line[ptr:ptr + 2]
                radio_map = {"02": "GSM", "03": "WCDMA", "04": "LTE", "05": "5G NR"}
                radio_type = radio_map.get(radio_type_hex, "未知")
                ptr += 2

                # 7. Carrier Name 长度 + 内容
                carrier_len = int(line[ptr:ptr + 2], 16)
                ptr += 2
                carrier_hex = line[ptr:ptr + carrier_len * 2]
                carrier_name = bytes.fromhex(carrier_hex).decode("ascii").strip()
                ptr += carrier_len * 2

                # 8. Consider Ip
                consider_ip = line[ptr:ptr + 2]
                ptr += 2

                # ===================== 解析 基站列表（循环） =====================
                cell_num = int(line[ptr:ptr + 2], 16)
                ptr += 2
                cell_list = []
                for i in range(cell_num):
                    cell_id = line[ptr:ptr + 16]
                    ptr += 16
                    cell_mcc_hex = line[ptr:ptr + 6]
                    cell_mcc = bytes.fromhex(cell_mcc_hex).decode("ascii").strip()
                    ptr += 6
                    cell_mnc_len = int(line[ptr:ptr + 2], 16)
                    ptr += 2
                    cell_mnc_hex = line[ptr:ptr + cell_mnc_len * 2]
                    cell_mnc = bytes.fromhex(cell_mnc_hex).decode("ascii").strip()
                    ptr += cell_mnc_len * 2
                    lac = line[ptr:ptr + 8]
                    ptr += 8
                    rssi = line[ptr:ptr + 2]
                    ptr += 2
                    cell_info = f"CELL{i + 1}：{cell_id}-{cell_mcc}{cell_mnc}-{lac}-{rssi} "
                    cell_list.append(cell_info)
                cell_list_str = "；".join(cell_list).upper()

                # ===================== 解析 WIFI列表（循环） =====================
                wifi_num = int(line[ptr:ptr + 2], 16)
                ptr += 2
                wifi_list = []
                for i in range(wifi_num):
                    mac = line[ptr:ptr + 12]
                    ptr += 12
                    wifi_rssi = line[ptr:ptr + 2]
                    ptr += 2
                    wifi_channel = line[ptr:ptr + 2]
                    ptr += 2
                    ssid_len = int(line[ptr:ptr + 2], 16)
                    ptr += 2
                    ssid_hex = line[ptr:ptr + ssid_len * 2]
                    ssid = bytes.fromhex(ssid_hex).decode("ascii", errors="ignore").strip()
                    ptr += ssid_len * 2
                    wifi_info = f"wifi{i + 1}：{mac}-{wifi_rssi}-{wifi_channel}-{ssid}"
                    wifi_list.append(wifi_info)
                wifi_list_str = "；".join(wifi_list).upper()

                row = []
                if self.lbs_location_data_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.lbs_location_data_time_checkbox.isChecked():
                    row.append(f"{time_str:<22}")
                if self.lbs_location_data_mcc_mnc_checkbox.isChecked():
                    row.append(f"{mcc_mnc:<8}")
                if self.lbs_location_data_radio_type_checkbox.isChecked():
                    row.append(f"{radio_type:<6}")
                if self.lbs_location_data_carrier_name_checkbox.isChecked():
                    row.append(f"{carrier_name:<14}")
                if self.lbs_location_data_consider_ip_checkbox.isChecked():
                    row.append(f"{consider_ip:<10}")
                # if self.lbs_location_data_cell_num_checkbox.isChecked():
                #     row.append(f"{cell_num:<10}")
                if self.lbs_location_data_cell_list_checkbox.isChecked():
                    row.append(f"CN-{cell_num}>> {cell_list_str}  ")
                # if self.lbs_location_data_wifi_num_checkbox.isChecked():
                #     row.append(f"{wifi_num:<10}")
                if self.lbs_location_data_wifi_list_checkbox.isChecked():
                    row.append(f"WN-{wifi_num}>> {wifi_list_str}  ")
                if self.lbs_location_data_raw_data_checkbox.isChecked():
                    row.append(line)

                lbs_location_event_times_1.append("".join(row))

        if lbs_location_event_times_1:
            self.result_label.setText(f"共找到 {len(lbs_location_event_times_1) - 1} 个LBS数据包")
            self.raw_data_display.setText("\n".join(lbs_location_event_times_1))
        else:
            self.result_label.setText("未找到LBS数据事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第四章：乾坤一簌天下游，月如钩，难别求 —— 风流
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 4.1 VIN码事件
    def process_vin_code(self, raw_data_string):
        headers = []
        if self.vin_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.vin_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.vin_type_checkbox.isChecked():
            headers.append(f"{'协议类型':<12}")
        if self.vin_length_checkbox.isChecked():
            headers.append(f"{'VIN长度':<8}")
        if self.vin_vin_value_checkbox.isChecked():
            headers.append(f"{'VIN码':<20}")
        if self.vin_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        vin_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0300":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                type_code_hex = line[70:72]
                if type_code_hex == "00":
                    type_code = "PT_NORMAL"
                elif type_code_hex == "01":
                    type_code = "PT_KWP"
                elif type_code_hex == "02":
                    type_code = "PT_ISO"
                elif type_code_hex == "03":
                    type_code = "PT_VPW"
                elif type_code_hex == "04":
                    type_code = "PT_PWM"
                elif type_code_hex == "19":
                    type_code = "PT_KWP_QUICK"
                elif type_code_hex == "99":
                    type_code = "PT_OBD_CAN"
                elif type_code_hex == "20":
                    type_code = "PT_J1939"
                else:
                    type_code = "UNKNOWN"
                vin_length = int(line[72:74], 16)
                vin_value = ascii_to_decimal(line[74: 74 + (vin_length * 2)])

                row = []

                if self.vin_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.vin_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.vin_type_checkbox.isChecked():
                    row.append(f"{type_code:<16}")
                if self.vin_length_checkbox.isChecked():
                    row.append(f"{vin_length:<10}")
                if self.vin_vin_value_checkbox.isChecked():
                    row.append(f"{vin_value:<21}")
                if self.vin_raw_data_checkbox.isChecked():
                    row.append(line)

                vin_event_times_1.append("".join(row))

        if vin_event_times_1:
            self.result_label.setText(f"共找到 {len(vin_event_times_1) - 1} 个VIN码事件")
            self.raw_data_display.setText("\n".join(vin_event_times_1))
        else:
            self.result_label.setText("未找到VIN码事件")
            self.raw_data_display.setText("")

    # 4.2 数据流事件
    def process_data_flow(self, raw_data_string):
        dataflow_header_fields = [
            ("dataflow_imei_checkbox", "IMEI", 20),
            ("dataflow_time_checkbox", "触发时间", 19),
            ("dataflow_rpm_checkbox", "转速", 5),
            ("dataflow_speed_checkbox", "车速", 5),
            ("dataflow_engine_coolant_temperature_checkbox", "发动机冷却液温度", 18),
            ("dataflow_throttle_position_checkbox", "节气门位置", 12),
            ("dataflow_engine_duty_checkbox", "发动机负荷", 12),
            ("dataflow_intake_air_flow_checkbox", "进气流量", 12),
            ("dataflow_intake_air_temperature_checkbox", "进气温度", 12),
            ("dataflow_intake_air_pressure_checkbox", "进气压力", 12),
            ("dataflow_battery_voltage_checkbox", "电池电压", 12),
            ("dataflow_fuel_level_checkbox", "油量", 10),
            ("dataflow_distance_dtcs_cleared_checkbox", "DTC清除后距离", 16),
            ("dataflow_distance_mil_checkbox", "故障灯点亮后距离", 18),
            ("dataflow_historical_total_mileage_checkbox", "历史总里程", 14),
            ("dataflow_historical_total_fuel_consumption_checkbox", "历史总油耗", 14),
            ("dataflow_historical_total_driving_time_checkbox", "历史总行驶时间", 16),
            ("dataflow_seatbelt_status_checkbox", "安全带状态", 12),
            ("dataflow_odometer_checkbox", "里程表", 14),
            ("dataflow_average_fuel_consumption_checkbox", "平均油耗", 14),
            ("dataflow_odometer_unit_checkbox", "里程单位", 12),
            ("dataflow_soc_checkbox", "SOC", 8),
            ("dataflow_soh_checkbox", "SOH", 8),
            ("dataflow_battery_pack_current_checkbox", "电池电流", 12),
            ("dataflow_battery_pack_voltage_checkbox", "电池电压", 12),
            ("dataflow_battery_pack_charging_checkbox", "充电状态", 10),
            ("dataflow_remaining_distance_checkbox", "剩余里程", 12),
            ("dataflow_battery_pack_temperature_checkbox", "电池包温度", 14),
            ("dataflow_distance_till_next_servicing_checkbox", "下次保养里程", 14),
            ("dataflow_engine_run_time_checkbox", "发动机运行时间", 16),
            ("dataflow_fuel_type_checkbox", "油品类型", 10),
            ("dataflow_turn_signals_status_checkbox", "转向灯状态", 12),
            ("dataflow_raw_data_checkbox", "原始数据", 100)
        ]
        headers = build_checkbox(dataflow_header_fields, self)

        # headers = []
        # if self.dataflow_imei_checkbox.isChecked():
        #     headers.append(f"{'IMEI':<20}")
        # if self.dataflow_time_checkbox.isChecked():
        #     headers.append(f"{'触发时间':<19}")
        # if self.dataflow_rpm_checkbox.isChecked():
        #     headers.append(f"{'转速':<5}")
        # if self.dataflow_speed_checkbox.isChecked():
        #     headers.append(f"{'车速':<5}")
        # if self.dataflow_engine_coolant_temperature_checkbox.isChecked():
        #     headers.append(f"{'A':<7}")
        # if self.dataflow_throttle_position_checkbox.isChecked():
        #     headers.append(f"{'B':<7}")
        # if self.dataflow_engine_duty_checkbox.isChecked():
        #     headers.append(f"{'C':<7}")
        # if self.dataflow_intake_air_flow_checkbox.isChecked():
        #     headers.append(f"{'D':<7}")
        # if self.dataflow_intake_air_temperature_checkbox.isChecked():
        #     headers.append(f"{'E':<7}")
        # if self.dataflow_intake_air_pressure_checkbox.isChecked():
        #     headers.append(f"{'F':<7}")
        # if self.dataflow_battery_voltage_checkbox.isChecked():
        #     headers.append(f"{'G':<7}")
        # if self.dataflow_fuel_level_checkbox.isChecked():
        #     headers.append(f"{'H':<7}")
        # if self.dataflow_distance_dtcs_cleared_checkbox.isChecked():
        #     headers.append(f"{'I':<7}")
        # if self.dataflow_distance_mil_checkbox.isChecked():
        #     headers.append(f"{'J':<7}")
        # if self.dataflow_historical_total_mileage_checkbox.isChecked():
        #     headers.append(f"{'K1':<13}")
        # if self.dataflow_historical_total_fuel_consumption_checkbox.isChecked():
        #     headers.append(f"{'K2':<13}")
        # if self.dataflow_historical_total_driving_time_checkbox.isChecked():
        #     headers.append(f"{'K3':<13}")
        # if self.dataflow_seatbelt_status_checkbox.isChecked():
        #     headers.append(f"{'L':<7}")
        # if self.dataflow_odometer_checkbox.isChecked():
        #     headers.append(f"{'M':<13}")
        # if self.dataflow_average_fuel_consumption_checkbox.isChecked():
        #     headers.append(f"{'N':<13}")
        # if self.dataflow_odometer_unit_checkbox.isChecked():
        #     headers.append(f"{'O':<7}")
        # if self.dataflow_soc_checkbox.isChecked():
        #     headers.append(f"{'P':<7}")
        # if self.dataflow_soh_checkbox.isChecked():
        #     headers.append(f"{'Q':<7}")
        # if self.dataflow_battery_pack_current_checkbox.isChecked():
        #     headers.append(f"{'R':<7}")
        # if self.dataflow_battery_pack_voltage_checkbox.isChecked():
        #     headers.append(f"{'S':<7}")
        # if self.dataflow_battery_pack_charging_checkbox.isChecked():
        #     headers.append(f"{'T':<5}")
        # if self.dataflow_remaining_distance_checkbox.isChecked():
        #     headers.append(f"{'U':<7}")
        # if self.dataflow_battery_pack_temperature_checkbox.isChecked():
        #     headers.append(f"{'V':<7}")
        # if self.dataflow_distance_till_next_servicing_checkbox.isChecked():
        #     headers.append(f"{'W':<7}")
        # if self.dataflow_engine_run_time_checkbox.isChecked():
        #     headers.append(f"{'X':<13}")
        # if self.dataflow_fuel_type_checkbox.isChecked():
        #     headers.append(f"{'Y':<5}")
        # if self.dataflow_turn_signals_status_checkbox.isChecked():
        #     headers.append(f"{'Z':<5}")
        # if self.dataflow_raw_data_checkbox.isChecked():
        #     headers.append(f"{'原始数据'}")

        dataflow_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0301":
                imei = ascii_to_decimal(line[18:48])  # imei号
                time_str = hex_to_beijing_time(line[62:70])  # 触发时间
                rpm = "FFFF" if line[120:124].upper() == "FFFF" else int(line[120:124], 16)  # 转速
                speed = "FFFF" if line[124:128].upper() == "FFFF" else int(line[124:128], 16)  # 车速
                engine_coolant_temperature = "FFFF" if line[128:132].upper() == "FFFF" else int(line[128:132],
                                                                                                16) - 40  # 发动机冷却液温度 偏移-40

                throttle_position = "FFFF" if line[132:136].upper() == "FFFF" else round(int(line[132:136], 16) * 0.1,
                                                                                         1)  # 节气门位置
                engine_duty = "FFFF" if line[136:140].upper() == "FFFF" else round(int(line[136:140], 16) * 0.1,
                                                                                   1)  # 发动机负荷
                intake_air_flow = "FFFF" if line[140:144].upper() == "FFFF" else round(int(line[140:144], 16) * 0.1,
                                                                                       1)  # 进气流量
                intake_air_temperature = "FFFF" if line[144:148].upper() == "FFFF" else int(line[144:148],
                                                                                            16) - 40  # 进气温度 偏移-40
                intake_air_pressure = "FFFF" if line[148:152].upper() == "FFFF" else int(line[148:152], 16)  # 进气压力

                battery_voltage = "FFFF" if line[152:156].upper() == "FFFF" else round(int(line[152:156], 16) * 0.1,
                                                                                       1)  # 电池电压
                fuel_level = "FFFF" if line[156:160].upper() == "FFFF" else round(int(line[156:160], 16) * 0.01, 2)
                distance_dtcs_cleared = "FFFF" if line[160:164].upper() == "FFFF" else int(line[160:164], 16)  # 故障码清除里程

                distance_mil_hex = line[164:168]  # 故障灯点亮里程
                if distance_mil_hex.upper() == "FFFF":
                    distance_mil = "FFFF"
                elif distance_mil_hex.upper() == "FFFE":
                    distance_mil = "FFFE"
                elif distance_mil_hex == "0000":
                    distance_mil = "0000"
                else:
                    distance_mil = int(line[164:168], 16)

                historical_total_mileage = int(line[168:176], 16)  # 历史总里程

                historical_total_fuel_consumption = int(line[176:184], 16)  # 历史总油耗
                historical_total_driving_time = int(line[184:192], 16)  # 历史总驾驶时间
                seatbelt_hex = line[192:194].upper()
                if seatbelt_hex == "FF":
                    seatbelt_status = "FF"
                else:
                    seatbelt_int = int(seatbelt_hex, 16)
                    seatbelt_bin = format(seatbelt_int, '08b')
                    seatbelt_bits_0_to_3 = seatbelt_bin[-4:]
                    seatbelt_status = str(seatbelt_bits_0_to_3)

                odometer = "FFFFFFFF" if line[194:202].upper() == "FFFFFFFF" else int(line[194:202], 16)  # 里程表读数
                average_fuel_consumption = "FFFFFFFF" if line[202:210].upper() == "FFFFFFFF" else int(line[202:210],
                                                                                                      16)  # 平均油耗
                odometer_unit_hex = line[210:212]
                if odometer_unit_hex == "01":
                    odometer_unit = "KM"
                elif odometer_unit_hex == "02":
                    odometer_unit = "Mile"
                elif odometer_unit_hex.lower() == "ff":
                    odometer_unit = "FF"
                else:
                    odometer_unit = odometer_unit_hex

                soc = "FFFF" if line[212:216].upper() == "FFFF" else round(int(line[212:216], 16) * 0.1, 1)  # SOC

                soh = "FF" if line[216:218].upper() == "FF" else int(line[216:218], 16)  # SOH

                battery_pack_current = "FFFF" if line[218:222].upper() == "FFFF" else round(
                    (int(line[218:222], 16)  - 10000) * 0.1, 1)  # 电池组电流
                battery_pack_voltage = "FFFF" if line[222:226].upper() == "FFFF" else round(
                    int(line[222:226], 16) * 0.1, 1)  # 电池组电压

                battery_pack_charging_hex = line[226:228]  # 电池组充电状态
                if battery_pack_charging_hex == "00":
                    battery_pack_charging = "NA"
                elif battery_pack_charging_hex == "01":
                    battery_pack_charging = "L1"
                elif battery_pack_charging_hex == "02":
                    battery_pack_charging = "L2"
                elif battery_pack_charging_hex == "03":
                    battery_pack_charging = "L3"
                elif battery_pack_charging_hex.lower() == "ff":
                    battery_pack_charging = "FF"
                else:
                    battery_pack_charging = battery_pack_charging_hex

                remaining_distance = "FFFF" if line[228:232].upper() == "FFFF" else int(line[228:232], 16)  # 剩余里程
                battery_pack_temperature = "FFFF" if line[232:236].upper() == "FFFF" else int(line[232:236],
                                                                                              16) - 40  # 电池组温度 偏移-40
                distance_till_next_servicing = "FFFF" if line[236:240].upper() == "FFFF" else int(line[236:240],
                                                                                                  16)  # 下次保养里程
                engine_run_time = "FFFFFFFF" if line[240:248].upper() == "FFFFFFFF" else int(line[240:248],
                                                                                             16)  # 发动机运行时间
                fuel_type = "FF" if line[248:250].upper() == "FF" else line[248:250]  # 燃油类型
                turn_signals_status_hex = line[250:252].upper()
                if turn_signals_status_hex == "FF":
                    turn_signals_status = "FF"
                else:
                    turn_signals_status_int = int(turn_signals_status_hex, 16)
                    turn_signals_status_bin = format(turn_signals_status_int, '08b')
                    turn_signals_status_bits_0_to_1 = turn_signals_status_bin[-2:]
                    turn_signals_status = str(turn_signals_status_bits_0_to_1)

                dataflow_tail_fields = [
                    ("dataflow_imei_checkbox", imei, 20),
                    ("dataflow_time_checkbox", time_str, 23),
                    ("dataflow_rpm_checkbox", rpm, 7),
                    ("dataflow_speed_checkbox", speed, 7),
                    ("dataflow_engine_coolant_temperature_checkbox", engine_coolant_temperature, 18),
                    ("dataflow_throttle_position_checkbox", throttle_position, 12),
                    ("dataflow_engine_duty_checkbox", engine_duty, 12),
                    ("dataflow_intake_air_flow_checkbox", intake_air_flow, 12),
                    ("dataflow_intake_air_temperature_checkbox", intake_air_temperature, 12),
                    ("dataflow_intake_air_pressure_checkbox", intake_air_pressure, 12),
                    ("dataflow_battery_voltage_checkbox", battery_voltage, 12),
                    ("dataflow_fuel_level_checkbox", fuel_level, 10),
                    ("dataflow_distance_dtcs_cleared_checkbox", distance_dtcs_cleared, 16),
                    ("dataflow_distance_mil_checkbox", distance_mil, 18),
                    ("dataflow_historical_total_mileage_checkbox", historical_total_mileage, 14),
                    ("dataflow_historical_total_fuel_consumption_checkbox", historical_total_fuel_consumption, 14),
                    ("dataflow_historical_total_driving_time_checkbox", historical_total_driving_time, 16),
                    ("dataflow_seatbelt_status_checkbox", seatbelt_status, 12),
                    ("dataflow_odometer_checkbox", odometer, 14),
                    ("dataflow_average_fuel_consumption_checkbox", average_fuel_consumption, 14),
                    ("dataflow_odometer_unit_checkbox", odometer_unit, 12),
                    ("dataflow_soc_checkbox", soc, 8),
                    ("dataflow_soh_checkbox", soh, 8),
                    ("dataflow_battery_pack_current_checkbox", battery_pack_current, 12),
                    ("dataflow_battery_pack_voltage_checkbox", battery_pack_voltage, 12),
                    ("dataflow_battery_pack_charging_checkbox", battery_pack_charging, 10),
                    ("dataflow_remaining_distance_checkbox", remaining_distance, 12),
                    ("dataflow_battery_pack_temperature_checkbox", battery_pack_temperature, 14),
                    ("dataflow_distance_till_next_servicing_checkbox", distance_till_next_servicing, 14),
                    ("dataflow_engine_run_time_checkbox", engine_run_time, 16),
                    ("dataflow_fuel_type_checkbox", fuel_type, 10),
                    ("dataflow_turn_signals_status_checkbox", turn_signals_status, 12),
                    ("dataflow_raw_data_checkbox", line, 100)
                ]

                row = build_checkbox(dataflow_tail_fields, self)

                # row = []
                # if self.dataflow_imei_checkbox.isChecked():
                #     row.append(f"{imei:<20}")
                # if self.dataflow_time_checkbox.isChecked():
                #     row.append(f"{time_str:<23}")
                # if self.dataflow_rpm_checkbox.isChecked():
                #     row.append(f"{rpm:<7}")
                # if self.dataflow_speed_checkbox.isChecked():
                #     row.append(f"{speed:<7}")
                # if self.dataflow_engine_coolant_temperature_checkbox.isChecked():
                #     row.append(f"{engine_coolant_temperature:<7}")
                # if self.dataflow_throttle_position_checkbox.isChecked():
                #     row.append(f"{throttle_position:<7}")
                # if self.dataflow_engine_duty_checkbox.isChecked():
                #     row.append(f"{engine_duty:<7}")
                # if self.dataflow_intake_air_flow_checkbox.isChecked():
                #     row.append(f"{intake_air_flow:<7}")
                # if self.dataflow_intake_air_temperature_checkbox.isChecked():
                #     row.append(f"{intake_air_temperature:<7}")
                # if self.dataflow_intake_air_pressure_checkbox.isChecked():
                #     row.append(f"{intake_air_pressure:<7}")
                # if self.dataflow_battery_voltage_checkbox.isChecked():
                #     row.append(f"{battery_voltage:<7}")
                # if self.dataflow_fuel_level_checkbox.isChecked():
                #     row.append(f"{fuel_level:<7}")
                # if self.dataflow_distance_dtcs_cleared_checkbox.isChecked():
                #     row.append(f"{distance_dtcs_cleared:<7}")
                # if self.dataflow_distance_mil_checkbox.isChecked():
                #     row.append(f"{distance_mil:<7}")
                # if self.dataflow_historical_total_mileage_checkbox.isChecked():
                #     row.append(f"{historical_total_mileage:<13}")
                # if self.dataflow_historical_total_fuel_consumption_checkbox.isChecked():
                #     row.append(f"{historical_total_fuel_consumption:<13}")
                # if self.dataflow_historical_total_driving_time_checkbox.isChecked():
                #     row.append(f"{historical_total_driving_time:<13}")
                # if self.dataflow_seatbelt_status_checkbox.isChecked():
                #     row.append(f"{seatbelt_status:<7}")
                # if self.dataflow_odometer_checkbox.isChecked():
                #     row.append(f"{odometer:<13}")
                # if self.dataflow_average_fuel_consumption_checkbox.isChecked():
                #     row.append(f"{average_fuel_consumption:<13}")
                # if self.dataflow_odometer_unit_checkbox.isChecked():
                #     row.append(f"{odometer_unit:<7}")
                # if self.dataflow_soc_checkbox.isChecked():
                #     row.append(f"{soc:<7}")
                # if self.dataflow_soh_checkbox.isChecked():
                #     row.append(f"{soh:<7}")
                # if self.dataflow_battery_pack_current_checkbox.isChecked():
                #     row.append(f"{battery_pack_current:<7}")
                # if self.dataflow_battery_pack_voltage_checkbox.isChecked():
                #     row.append(f"{battery_pack_voltage:<7}")
                # if self.dataflow_battery_pack_charging_checkbox.isChecked():
                #     row.append(f"{battery_pack_charging:<5}")
                # if self.dataflow_remaining_distance_checkbox.isChecked():
                #     row.append(f"{remaining_distance:<7}")
                # if self.dataflow_battery_pack_temperature_checkbox.isChecked():
                #     row.append(f"{battery_pack_temperature:<7}")
                # if self.dataflow_distance_till_next_servicing_checkbox.isChecked():
                #     row.append(f"{distance_till_next_servicing:<7}")
                # if self.dataflow_engine_run_time_checkbox.isChecked():
                #     row.append(f"{engine_run_time:<13}")
                # if self.dataflow_fuel_type_checkbox.isChecked():
                #     row.append(f"{fuel_type:<5}")
                # if self.dataflow_turn_signals_status_checkbox.isChecked():
                #     row.append(f"{turn_signals_status:<5}")
                # if self.dataflow_raw_data_checkbox.isChecked():
                #     row.append(line)

                dataflow_event_times_1.append("".join(row))

        if dataflow_event_times_1:
            self.result_label.setText(f"共找到 {len(dataflow_event_times_1) - 1} 个数据流事件")
            self.raw_data_display.setText("\n".join(dataflow_event_times_1))
        else:
            self.result_label.setText("未找到数据流事件")
            self.raw_data_display.setText("")

    # 4.3 CAN 支持参数列表
    def process_can_parameter_support_status(self,raw_data_string):
        headers = []
        if self.can_parameter_support_status_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.can_parameter_support_status_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<20}")
        if self.can_parameter_support_status_vin_checkbox.isChecked():
            headers.append(f"{'VIN':<20}")
        if self.can_parameter_support_status_gasoline_ev_checkbox.isChecked():
            headers.append(f"{'GASOLINE_EV'}")
        if self.can_parameter_support_status_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        can_parameter_support_status_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0304":
                imei = ascii_to_decimal(line[18:48])  # imei号
                time_str = hex_to_beijing_time(line[62:70])  # 触发时间
                vin_length = int(line[70:72], 16)
                vin_value = ascii_to_decimal(line[72: 72 + (vin_length * 2)])

                # ✅ CAN 起始位置
                start = 72 + (vin_length * 2)

                # ===== 解析 Gasoline =====
                gasoline_list, next_start = parse_can_list(
                    line, start, gasoline_map
                )

                # ===== 解析 EV =====
                ev_list, final_start = parse_can_list(
                    line, next_start, ev_map
                )

                # ===== 拼接字符串 =====
                gasoline_str = "，".join(gasoline_list) if gasoline_list else "无支持项"
                ev_str = "，".join(ev_list) if ev_list else "无支持项"

                Gasoline_EV_value_list = (
                    f"CAN parameter list for Gasoline Vehicle（{gasoline_str}）"
                    f" CAN parameter list for EV Vehicle（{ev_str}）"
                )

                row = []
                if self.can_parameter_support_status_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.can_parameter_support_status_time_checkbox.isChecked():
                    row.append(f"{time_str:<20}")
                if self.can_parameter_support_status_vin_checkbox.isChecked():
                    row.append(f"{vin_value:<20}")
                if self.can_parameter_support_status_gasoline_ev_checkbox.isChecked():
                    row.append(Gasoline_EV_value_list)
                if self.can_parameter_support_status_raw_data_checkbox.isChecked():
                    row.append(line)

                can_parameter_support_status_times_1.append("".join(row))

        if can_parameter_support_status_times_1:
            self.result_label.setText(f"共找到 {len(can_parameter_support_status_times_1) - 1} 个CAN参数支持状态事件")
            self.raw_data_display.setText("\n".join(can_parameter_support_status_times_1))
        else:
            self.result_label.setText("未找到CAN参数支持状态")
            self.raw_data_display.setText("")

    # 4.4 raw can frame
    def process_raw_can_frame(self,raw_data_string):
        headers = []
        if self.raw_can_frame_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.raw_can_frame_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<20}")
        if self.raw_can_frame_canbuspins_checkbox.isChecked():
            headers.append(f"{'pin':<10}")
        if self.raw_can_frame_num_canframe_checkbox.isChecked():
            headers.append(f"{'num':<10}")
        if self.raw_can_frame_canframeid_raw_checkbox.isChecked():
            headers.append(f"{'CANID_RAW'}")
        if self.raw_can_frame_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        raw_can_frame_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0305":
                imei = ascii_to_decimal(line[18:48])  # imei号
                time_str = hex_to_beijing_time(line[62:70])  # 触发时间
                canbuspins = int(line[70:72], 16)
                num_canframe = int(line[72:74],16)

                start = 74
                canframeid_raw_list = []

                for i in range(num_canframe):
                    offset = start + i * 24
                    # 防止越界（非常重要）
                    if offset + 24 > len(line):
                        break
                    # CAN ID（8个hex字符）
                    can_id = line[offset: offset + 8]
                    # RAW CAN FRAME（16个hex字符）
                    raw_frame = line[offset + 8: offset + 24]
                    # 拼接
                    canframeid_raw_list.append(can_id + "-" + raw_frame + " ")

                canframeid_raw = "".join(canframeid_raw_list).upper()

                row = []
                if self.raw_can_frame_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.raw_can_frame_time_checkbox.isChecked():
                    row.append(f"{time_str:<24}")
                if self.raw_can_frame_canbuspins_checkbox.isChecked():
                    row.append(f"{canbuspins:<10}")
                if self.raw_can_frame_num_canframe_checkbox.isChecked():
                    row.append(f"{num_canframe:<10}")
                if self.raw_can_frame_canframeid_raw_checkbox.isChecked():
                    row.append(canframeid_raw)
                if self.raw_can_frame_raw_data_checkbox.isChecked():
                    row.append(line)

                raw_can_frame_times_1.append("".join(row))

        if raw_can_frame_times_1:
            self.result_label.setText(f"共找到 {len(raw_can_frame_times_1) - 1} 个raw can frame状态事件")
            self.raw_data_display.setText("\n".join(raw_can_frame_times_1))
        else:
            self.result_label.setText("未找到raw can frame状态事件")
            self.raw_data_display.setText("")

    # 4.5 config 数据流klv
    def process_config_data_flow(self, raw_data_string):
        headers = []
        if self.config_dataflow_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.config_dataflow_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.config_dataflow_klv_checkbox.isChecked():
            headers.append(f"{'KLV数据'}")
        if self.config_dataflow_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        config_dataflow_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0306":
                imei = ascii_to_decimal(line[18:48])  # imei号
                time_str = hex_to_beijing_time(line[62:70])  # 触发时间

                # ✅ 解析KLV（从第70位开始）
                valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
                klv_data = line[70:58+valid_data_length]
                klv = parse_klv(klv_data, separator=StripedTextEdit.CELL_LINE_BREAK)

                row = []
                if self.config_dataflow_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.config_dataflow_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.config_dataflow_klv_checkbox.isChecked():
                    row.append(klv)
                if self.config_dataflow_raw_data_checkbox.isChecked():
                    row.append(line)

                config_dataflow_times_1.append("".join(row))

        if config_dataflow_times_1:
            self.result_label.setText(f"共找到 {len(config_dataflow_times_1) - 1} 个配置数据流事件")
            self.raw_data_display.setText("\n".join(config_dataflow_times_1))
        else:
            self.result_label.setText("未找到配置数据流事件")
            self.raw_data_display.setText("")

    # 4.6 处理车辆信息klv
    def process_vehicle_Information_klv(self, raw_data_string):
        headers = []
        if self.vehicle_Information_klv_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        # if self.vehicle_Information_klv_time_checkbox.isChecked():
        #     headers.append(f"{'触发时间':<19}")
        if self.vehicle_Information_klv_klv_data_checkbox.isChecked():
            headers.append(f"{'消息内容'}")
        if self.vehicle_Information_klv_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        vehicle_Information_klv_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0307":
                imei = ascii_to_decimal(line[18:48])  # imei号

                # ✅ 解析KLV（从第70位开始）
                valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
                klv_source_data = line[62:58+valid_data_length]
                klv_data = parse_klv(klv_source_data)

                row = []
                if self.vehicle_Information_klv_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                # if self.vehicle_Information_klv_time_checkbox.isChecked():
                #     row.append(f"{time_str:<23}")
                if self.vehicle_Information_klv_klv_data_checkbox.isChecked():
                    row.append(f"{klv_data:<10}")
                if self.vehicle_Information_klv_raw_data_checkbox.isChecked():
                    row.append(line)

                vehicle_Information_klv_times_1.append("".join(row))

        if vehicle_Information_klv_times_1:
            self.result_label.setText(f"共找到 {len(vehicle_Information_klv_times_1) - 1} 个消息发送事件")
            self.raw_data_display.setText("\n".join(vehicle_Information_klv_times_1))
        else:
            self.result_label.setText("未找到消息发送事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第五章：书香百味有多少，天下何人配白衣 —— 无双
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 5.1 dtc事件
    def process_dtc_code(self, raw_data_string):
        headers = []
        if self.dtc_code_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.dtc_code_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.dtc_code_obd_dtc_num_checkbox.isChecked():
            headers.append(f"{'故障码数量':<6}")
        if self.dtc_code_obd_dtc_data_checkbox.isChecked():
            headers.append(f"{'故障码数据':<25}")
        if self.dtc_code_private_code_num_checkbox.isChecked():
            headers.append(f"{'私有码数量':<6}")
        if self.dtc_code_private_code_data_checkbox.isChecked():
            headers.append(f"{'私有码数据':<25}")
        if self.dtc_code_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        dtc_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0500":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                obd_dtc_num = int(line[70:72], 16)
                obd_dtc_data = line[72:72 + (obd_dtc_num * 6)]
                private_code_num = int(line[72 + (obd_dtc_num * 6):74 + (obd_dtc_num * 6)], 16)
                private_code_data = line[74 + (obd_dtc_num * 6):74 + (obd_dtc_num * 6) + (private_code_num * 8)]

                row = []
                if self.dtc_code_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.dtc_code_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.dtc_code_obd_dtc_num_checkbox.isChecked():
                    row.append(f"{obd_dtc_num:<11}")
                if self.dtc_code_obd_dtc_data_checkbox.isChecked():
                    row.append(f"{obd_dtc_data:<30}")
                if self.dtc_code_private_code_num_checkbox.isChecked():
                    row.append(f"{private_code_num:<11}")
                if self.dtc_code_private_code_data_checkbox.isChecked():
                    row.append(f"{private_code_data:<30}")
                if self.dtc_code_raw_data_checkbox.isChecked():
                    row.append(line)

                dtc_event_times_1.append("".join(row))

        if dtc_event_times_1:
            self.result_label.setText(f"共找到 {len(dtc_event_times_1) - 1} 个故障码事件")
            self.raw_data_display.setText("\n".join(dtc_event_times_1))
        else:
            self.result_label.setText("未找到故障码事件")
            self.raw_data_display.setText("")

    # 5.2 低电压事件
    def process_battery_low(self, raw_data_string):
        headers = []
        if self.battery_low_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.battery_low_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.battery_low_battery_voltage_checkbox.isChecked():
            headers.append(f"{'电源电压':<6}")
        if self.battery_low_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        low_voltage_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0501":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                voltage = round(int(line[118:122], 16) * 0.1, 1)  # 电压

                row = []
                if self.battery_low_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.battery_low_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.battery_low_battery_voltage_checkbox.isChecked():
                    row.append(f"{voltage:<10}")
                if self.battery_low_raw_data_checkbox.isChecked():
                    row.append(line)

                low_voltage_event_times_1.append("".join(row))

        if low_voltage_event_times_1:
            self.result_label.setText(f"共找到 {len(low_voltage_event_times_1) - 1} 个低电压事件")
            self.raw_data_display.setText("\n".join(low_voltage_event_times_1))
        else:
            self.result_label.setText("未找到低电压事件")
            self.raw_data_display.setText("")

    # 5.3 震动事件
    def process_vibration_event(self, raw_data_string):
        headers = []
        if self.vibration_event_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.vibration_event_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.vibration_event_vibration_value_checkbox.isChecked():
            headers.append(f"{'震动值':<8}")
        if self.vibration_event_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        vibration_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0502":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                vibration_value = int(line[118:122], 16)

                row = []
                if self.vibration_event_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.vibration_event_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.vibration_event_vibration_value_checkbox.isChecked():
                    row.append(f"{vibration_value:<11}")
                if self.vibration_event_raw_data_checkbox.isChecked():
                    row.append(line)

                vibration_event_times_1.append("".join(row))

        if vibration_event_times_1:
            self.result_label.setText(f"共找到 {len(vibration_event_times_1) - 1} 个震动事件")
            self.raw_data_display.setText("\n".join(vibration_event_times_1))
        else:
            self.result_label.setText("未找到震动事件")
            self.raw_data_display.setText("")

    # 5.4 疑似碰撞
    def process_suspected_collision(self, raw_data_string):
        headers = []
        if self.suspected_collision_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.suspected_collision_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.suspected_collision_collision_value_checkbox.isChecked():
            headers.append(f"{'碰撞值':<8}")
        if self.suspected_collision_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        suspected_collision_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0505":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                collision_value = round(int(line[118:120], 16) * 0.1, 1)

                row = []
                if self.suspected_collision_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.suspected_collision_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.suspected_collision_collision_value_checkbox.isChecked():
                    row.append(f"{collision_value:<11}")
                if self.suspected_collision_raw_data_checkbox.isChecked():
                    row.append(line)

                suspected_collision_event_times_1.append("".join(row))

        if suspected_collision_event_times_1:
            self.result_label.setText(f"共找到 {len(suspected_collision_event_times_1) - 1} 个疑似碰撞事件")
            self.raw_data_display.setText("\n".join(suspected_collision_event_times_1))
        else:
            self.result_label.setText("未找到疑似碰撞事件")
            self.raw_data_display.setText("")

    # 5.5 拔出告警
    def process_unplug_warning(self, raw_data_string):
        headers = []
        if self.unplug_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.unplug_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.unplug_warning_unplug_state_checkbox.isChecked():
            headers.append(f"{'拔出状态':<8}")
        if self.unplug_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        unplug_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62] == "0507":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                unplug_state_hex = line[118:120]
                if unplug_state_hex == "00":
                    unplug_state = "正常拔出"
                elif unplug_state_hex == "01":
                    unplug_state = "点火中拔出"
                else:
                    unplug_state = "N/A"

                row = []
                if self.unplug_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.unplug_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.unplug_warning_unplug_state_checkbox.isChecked():
                    row.append(f"{unplug_state:<12}")
                if self.unplug_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                unplug_warning_event_times_1.append("".join(row))

        if unplug_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(unplug_warning_event_times_1) - 1} 个拔出告警事件")
            self.raw_data_display.setText("\n".join(unplug_warning_event_times_1))
        else:
            self.result_label.setText("未找到拔出告警事件")
            self.raw_data_display.setText("")

    # 5.6 干扰状态
    def process_jamming_detection(self, raw_data_string):
        headers = []
        if self.jamming_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.jamming_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.jamming_detection_jamming_status_checkbox.isChecked():
            headers.append(f"{'干扰状态':<8}")
        if self.jamming_detection_jamming_type_checkbox.isChecked():
            headers.append(f"{'干扰类型':<8}")
        if self.jamming_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        jamming_detection_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "050B":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                jamming_state_hex = line[118:120]
                if jamming_state_hex == "00":
                    jamming_state = "start"
                elif jamming_state_hex == "01":
                    jamming_state = "end"
                else:
                    jamming_state = "N/A"

                jamming_type_hex = line[120:122]
                if jamming_type_hex == "00":
                    jamming_type = "CELL"
                elif jamming_type_hex == "01":
                    jamming_type = "GNSS"
                else:
                    jamming_type = "N/A"

                row = []
                if self.jamming_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.jamming_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.jamming_detection_jamming_status_checkbox.isChecked():
                    row.append(f"{jamming_state:<12}")
                if self.jamming_detection_jamming_status_checkbox.isChecked():
                    row.append(f"{jamming_type:<12}")
                if self.jamming_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                jamming_detection_event_times_1.append("".join(row))

        if jamming_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(jamming_detection_event_times_1) - 1} 个干扰状态事件")
            self.raw_data_display.setText("\n".join(jamming_detection_event_times_1))
        else:
            self.result_label.setText("未找到干扰状态事件")
            self.raw_data_display.setText("")

    # 5.7 设备防拆告警
    def process_device_tamper_warning(self, raw_data_string):
        header = []
        if self.device_tamper_warning_imei_checkbox.isChecked():
            header.append(f"{'IMEI':<20}")
        if self.device_tamper_warning_time_checkbox.isChecked():
            header.append(f"{'触发时间':<19}")
        if self.device_tamper_warning_raw_data_checkbox.isChecked():
            header.append(f"{'原始数据'}")

        device_tamper_warning_event_times_1 = ["".join(header)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "050C":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.device_tamper_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.device_tamper_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.device_tamper_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                device_tamper_warning_event_times_1.append("".join(row))

        if device_tamper_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(device_tamper_warning_event_times_1) - 1} 个设备防拆告警事件")
            self.raw_data_display.setText("\n".join(device_tamper_warning_event_times_1))
        else:
            self.result_label.setText("未找到设备防拆告警事件")
            self.raw_data_display.setText("")

    # 5.8 温度告警
    def process_temperature_warning(self, raw_data_string):
        headers = []
        if self.temperature_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.temperature_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.temperature_warning_temperature_value_checkbox.isChecked():
            headers.append(f"{'温度值':<8}")
        if self.temperature_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        temperature_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "050D":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                temperature_value = round(int(line[118:122], 16) * 0.1 - 40, 1)   # 温度值，单位为摄氏度

                row = []
                if self.temperature_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.temperature_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.temperature_warning_temperature_value_checkbox.isChecked():
                    row.append(f"{temperature_value:<11}")
                if self.temperature_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                temperature_warning_event_times_1.append("".join(row))

        if temperature_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(temperature_warning_event_times_1) - 1} 个温度告警事件")
            self.raw_data_display.setText("\n".join(temperature_warning_event_times_1))
        else:
            self.result_label.setText("未找到温度告警事件")
            self.raw_data_display.setText("")

    # 5.9 气压告警信息
    def process_air_pressure_warning(self, raw_data_string):
        headers = []
        if self.air_pressure_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.air_pressure_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.air_pressure_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        air_pressure_warning_event_times_1 = ["".join(headers)]

        # for line in self._iter_valid_raw_lines(raw_data_string):
        #     if line[48:50] == "03" and line[58:62].upper() == "050E":
        #         imei = ascii_to_decimal(line[18:48])
        #         time_str = hex_to_beijing_time(line[62:70])
        #
        #         row = []
        #         if self.air_pressure_warning_imei_checkbox.isChecked():
        #             row.append(f"{imei:<20}")
        #         if self.air_pressure_warning_time_checkbox.isChecked():
        #             row.append(f"{time_str:<23}")
        #         if self.air_pressure_warning_raw_data_checkbox.isChecked():
        #             row.append(line)
        #
        #         air_pressure_warning_event_times_1.append("".join(row))

        if air_pressure_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(air_pressure_warning_event_times_1) - 1} 个气压告警事件")
            self.raw_data_display.setText("\n".join(air_pressure_warning_event_times_1))
        else:
            self.result_label.setText("未找到气压告警事件")
            self.raw_data_display.setText("")

    # 5.10 冲击告警
    def process_shock_warning(self, raw_data_string):
        headers = []
        if self.shock_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.shock_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.shock_warning_num_checkbox.isChecked():
            headers.append(f"{'NUM':<8}")
        if self.shock_warning_sensor_data_checkbox.isChecked():
            headers.append(f"{'冲击值':<10}")
        if self.shock_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        shock_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "050F":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                num = int(line[70:72], 16)
                sensor_data_list = []
                for i in range(num):
                    # 每组传感器数据 6 字节 = 12 个字符
                    start = 72 + i * 12
                    end = start + 12
                    data_hex = line[start:end]

                    # X Y Z 三轴解析（2 字节/轴，有符号数）
                    x = int(data_hex[0:4], 16)
                    y = int(data_hex[4:8], 16)
                    z = int(data_hex[8:12], 16)

                    x = x - 65536 if x > 32767 else x
                    y = y - 65536 if y > 32767 else y
                    z = z - 65536 if z > 32767 else z

                    # 把每组拼成小段字符串
                    group_str = f"X:{x}mg,Y:{y}mg,Z:{z}mg"
                    sensor_data_list.append(group_str)

                # 把所有组拼成 **一个完整字符串**
                sensor_data_str = "，".join(sensor_data_list)

                row = []
                if self.shock_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.shock_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.shock_warning_num_checkbox.isChecked():
                    row.append(f"{num:<8}")
                if self.shock_warning_sensor_data_checkbox.isChecked():
                    row.append(sensor_data_str)
                if self.shock_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                shock_warning_event_times_1.append("".join(row))

        if shock_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(shock_warning_event_times_1) - 1} 个冲击告警事件")
            self.raw_data_display.setText("\n".join(shock_warning_event_times_1))
        else:
            self.result_label.setText("未找到冲击告警事件")
            self.raw_data_display.setText("")

    # 5.11 环境光检测警告
    def process_ambient_light_detection_warning(self, raw_data_string):
        headers = []
        if self.ambient_light_detection_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.ambient_light_detection_warning_time_checkbox.isChecked():
            headers.append(f"{'Trigger Time':<19}")
        if self.ambient_light_detection_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'Raw Data'}")

        ambient_light_detection_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0510":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.ambient_light_detection_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.ambient_light_detection_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.ambient_light_detection_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                ambient_light_detection_warning_event_times_1.append("".join(row))

        if ambient_light_detection_warning_event_times_1:
            self.result_label.setText(
                f"Found {len(ambient_light_detection_warning_event_times_1) - 1} ambient light detection warning events"
            )
            self.raw_data_display.setText("\n".join(ambient_light_detection_warning_event_times_1))
        else:
            self.result_label.setText("No ambient light detection warning events found")
            self.raw_data_display.setText("")

    # 5.12 湿度警告
    def process_humidity_warning(self, raw_data_string):
        headers = []
        if self.humidity_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.humidity_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.humidity_warning_humidity_value_checkbox.isChecked():
            headers.append(f"{'湿度':<12}")
        if self.humidity_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'Raw Data'}")

        humidity_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0511":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                humidity_hex = line[118:122].upper()
                humidity_value = "FFFF" if humidity_hex == "FFFF" else round(int(humidity_hex, 16) * 0.1, 1)

                row = []
                if self.humidity_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.humidity_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.humidity_warning_humidity_value_checkbox.isChecked():
                    row.append(f"{humidity_value:<14}")
                if self.humidity_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                humidity_warning_event_times_1.append("".join(row))

        if humidity_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(humidity_warning_event_times_1) - 1} 个湿度告警事件")
            self.raw_data_display.setText("\n".join(humidity_warning_event_times_1))
        else:
            self.result_label.setText("未找到湿度告警事件")
            self.raw_data_display.setText("")

    # 5.13 设备告警信息 KLV
    def process_device_warning_message(self, raw_data_string):
        headers = []
        if self.device_warning_message_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.device_warning_message_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.device_warning_message_klv_data_checkbox.isChecked():
            headers.append(f"{'告警类型':<20}")
        if self.device_warning_message_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        device_warning_message_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0512":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                # ✅ 解析KLV（从第70位开始）
                valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
                klv_source_data = line[118:58+valid_data_length]
                klv_data = parse_klv(klv_source_data)


                row = []
                if self.device_warning_message_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.device_warning_message_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.device_warning_message_klv_data_checkbox.isChecked():
                    row.append(f"{klv_data:<20}")
                if self.device_warning_message_raw_data_checkbox.isChecked():
                    row.append(line)

                device_warning_message_event_times_1.append("".join(row))

        if device_warning_message_event_times_1:
            self.result_label.setText(f"共找到 {len(device_warning_message_event_times_1) - 1} 个设备告警信息事件")
            self.raw_data_display.setText("\n".join(device_warning_message_event_times_1))
        else:
            self.result_label.setText("未找到设备告警信息")
            self.raw_data_display.setText("")

    # 5.14 DTC code (for J1939)
    def process_j1939_dtc_code(self, raw_data_string):
        headers = []
        if self.j1939_dtc_code_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.j1939_dtc_code_time_checkbox.isChecked():
            headers.append(f"{'Trigger Time':<19}")
        if self.j1939_dtc_code_dtc_information_checkbox.isChecked():
            headers.append(f"{'DTC Information':<60}")
        if self.j1939_dtc_code_raw_data_checkbox.isChecked():
            headers.append(f"{'Raw Data'}")

        j1939_dtc_code_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "050A":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                try:
                    valid_data_length = int(line[54:58], 16) * 2
                    dtc_information = line[70:58 + valid_data_length].upper()
                except Exception:
                    dtc_information = line[70:].upper()

                row = []
                if self.j1939_dtc_code_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.j1939_dtc_code_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.j1939_dtc_code_dtc_information_checkbox.isChecked():
                    row.append(f"{dtc_information:<64}")
                if self.j1939_dtc_code_raw_data_checkbox.isChecked():
                    row.append(line)

                j1939_dtc_code_event_times_1.append("".join(row))

        if j1939_dtc_code_event_times_1:
            self.result_label.setText(f"Found {len(j1939_dtc_code_event_times_1) - 1} J1939 DTC code events")
            self.raw_data_display.setText("\n".join(j1939_dtc_code_event_times_1))
        else:
            self.result_label.setText("No J1939 DTC code events found")
            self.raw_data_display.setText("")

    # 5.15 电子围栏告警
    def process_fence_warning(self, raw_data_string):
        headers = []
        if self.fence_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.fence_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.fence_warning_id_checkbox.isChecked():
            headers.append(f"{'ID':<6}")
        if self.fence_warning_type_checkbox.isChecked():
            headers.append(f"{'Type':<8}")
        if self.fence_warning_location_checkbox.isChecked():
            headers.append(f"{'Location':<20}")
        if self.fence_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        fence_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0513":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                geo_id = str(line[70:72])

                warning_type_code = line[72:74]
                if warning_type_code == "00":
                    warning_type = "进入"
                elif warning_type_code == "01":
                    warning_type = "离开"
                else:
                    warning_type = warning_type_code  # 其他值保持原始

                location_str = line[74:126]
                # 解析定位字符串
                location_str = line[74:126]
                gps_data = parse_gps_data(location_str)

                # 组合成友好格式
                location_show = (
                    f"{gps_data['Time']} "
                    f"[{gps_data['Longitude']:.6f}, {gps_data['Latitude']:.6f}] "
                    f"Speed:{gps_data['GPS Speed']:.1f}"
                )


                row = []
                if self.fence_warning_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.fence_warning_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.fence_warning_id_checkbox.isChecked():
                    row.append(f"{geo_id:<6}")
                if self.fence_warning_type_checkbox.isChecked():
                    row.append(f"{warning_type:<6}")
                if self.fence_warning_location_checkbox.isChecked():
                    row.append(f"{location_show:<20}")
                if self.fence_warning_raw_data_checkbox.isChecked():
                    row.append(line)

                fence_warning_event_times_1.append("".join(row))

        if fence_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(fence_warning_event_times_1) - 1} 个电子围栏事件")
            self.raw_data_display.setText("\n".join(fence_warning_event_times_1))
        else:
            self.result_label.setText("未找到电子围栏事件")
            self.raw_data_display.setText("")


    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第六章：枪似游龙万兵手，命若黄泉不回头 —— 白龙
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 6.1 休眠事件
    def process_sleep_state(self, raw_data_string):
        headers = []
        if self.sleep_state_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sleep_state_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sleep_state_sleep_voltage_checkbox.isChecked():
            headers.append(f"{'休眠电压':<8}")
        if self.sleep_state_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sleep_state_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0402":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                sleep_voltage = round(int(line[70:74], 16) * 0.1, 1)  # 电压

                row = []
                if self.sleep_state_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sleep_state_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sleep_state_sleep_voltage_checkbox.isChecked():
                    row.append(f"{sleep_voltage:<12}")
                if self.sleep_state_raw_data_checkbox.isChecked():
                    row.append(line)

                sleep_state_event_times_1.append("".join(row))

        if sleep_state_event_times_1:
            self.result_label.setText(f"共找到 {len(sleep_state_event_times_1) - 1} 个休眠状态事件")
            self.raw_data_display.setText("\n".join(sleep_state_event_times_1))
        else:
            self.result_label.setText("未找到休眠状态事件")
            self.raw_data_display.setText("")

    # 6.2 唤醒状态
    def process_wakeup_state(self, raw_data_string):
        headers = []
        if self.wakeup_state_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.wakeup_state_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.wakeup_state_wakeup_voltage_checkbox.isChecked():
            headers.append(f"{'唤醒电压':<8}")
        if self.wakeup_state_wakeup_type_checkbox.isChecked():
            headers.append(f"{'唤醒类型':<31}")
        if self.wakeup_state_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        wakeup_state_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0403":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                wakeup_voltage = round(int(line[70:74], 16) * 0.1, 1)
                wakeup_state_hex = line[74:76]
                if wakeup_state_hex == "01":
                    wakeup_state = "Time wakeup"
                elif wakeup_state_hex == "03":
                    wakeup_state = "main battery voltage"
                elif wakeup_state_hex == "04":
                    wakeup_state = "busline"
                elif wakeup_state_hex == "05":
                    wakeup_state = "vibration"
                elif wakeup_state_hex == "06":
                    wakeup_state = " low voltage"
                elif wakeup_state_hex == "11":
                    wakeup_state = "backup battery"
                elif wakeup_state_hex == "12":
                    wakeup_state = "ACC"
                elif wakeup_state_hex == "13":
                    wakeup_state = "optical sensor - device tamper"
                elif wakeup_state_hex == "14":
                    wakeup_state = "butten"
                elif wakeup_state_hex == "15":
                    wakeup_state = "optical sensor - ambient light"
                elif wakeup_state_hex == "16":
                    wakeup_state = "MDM - RING"
                else:
                    wakeup_state = "unknown"

                row = []
                if self.wakeup_state_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.wakeup_state_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.wakeup_state_wakeup_voltage_checkbox.isChecked():
                    row.append(f"{wakeup_voltage:<12}")
                if self.wakeup_state_wakeup_type_checkbox.isChecked():
                    row.append(f"{wakeup_state:<35}")
                if self.wakeup_state_raw_data_checkbox.isChecked():
                    row.append(line)

                wakeup_state_event_times_1.append("".join(row))

        if wakeup_state_event_times_1:
            self.result_label.setText(f"共找到 {len(wakeup_state_event_times_1) - 1} 个唤醒状态事件")
            self.raw_data_display.setText("\n".join(wakeup_state_event_times_1))
        else:
            self.result_label.setText("未找到唤醒状态事件")
            self.raw_data_display.setText("")

    # 6.3 长时间无法定位
    def process_gps_not_fix(self, raw_data_string):
        headers = []
        if self.gps_not_fix_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.gps_not_fix_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.gps_not_fix_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        gps_not_fix_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0404":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                row = []
                if self.gps_not_fix_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.gps_not_fix_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.gps_not_fix_raw_data_checkbox.isChecked():
                    row.append(line)

                gps_not_fix_event_times_1.append("".join(row))

        if gps_not_fix_event_times_1:
            self.result_label.setText(f"共找到 {len(gps_not_fix_event_times_1) - 1} 个长时间无法定位事件")
            self.raw_data_display.setText("\n".join(gps_not_fix_event_times_1))
        else:
            self.result_label.setText("未找到长时间无法定位事件")
            self.raw_data_display.setText("")

    # 6.4 重启事件
    def process_reboot_event(self, raw_data_string):
        headers = []
        if self.reboot_event_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.reboot_event_power_on_time_checkbox.isChecked():
            headers.append(f"{'上电时间':<19}")
        if self.reboot_event_power_off_time_checkbox.isChecked():
            headers.append(f"{'断电时间':<19}")
        if self.reboot_event_reboot_reason_checkbox.isChecked():
            headers.append(f"{'重启原因':<31}")
        if self.reboot_event_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        reboot_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0405":
                imei = ascii_to_decimal(line[18:48])
                power_on_time = hex_to_beijing_time(line[62:70])
                power_off_time = hex_to_beijing_time(line[70:78])
                reboot_reason_hex = line[78:80].upper()
                reboot_reason_map = {
                    "00": "正常重启",
                    "01": "software dog",
                    "02": "upgrade",
                    "03": "plugged",
                    "04": "reboot key",
                    "06": "SMS",
                    "07": "SMS rsest",
                    "08": "flash reboot",
                    "09": "flash reset",
                    "0A": "5th sleep",
                    "0B": "Platform reboot",
                    "0C": "Platform reset",
                    "0D": "7 days",
                    "0F": "AT CMD FAIL",
                    "10": "长时间与服务器失联",
                    "11": "长时间无法锁定任务",
                    "40": "GPS线程异常",
                    "41": "OBD线程异常",
                    "42": "通信线程异常",
                    "43": "休眠唤醒线程异常",
                    "44": "其他线程异常",
                    "45": "optical sensor - device tamper",
                    "46": "by butten",
                    "47": "optical sensor - ambient light",
                    "48": "定时重启",
                    "49": "workmode switch",
                    "4A": "vibration"
                }

                reboot_reason = reboot_reason_map.get(reboot_reason_hex.upper(), "N/A")

                row = []
                if self.reboot_event_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.reboot_event_power_on_time_checkbox.isChecked():
                    row.append(f"{power_on_time:<23}")
                if self.reboot_event_power_off_time_checkbox.isChecked():
                    row.append(f"{power_off_time:<23}")
                if self.reboot_event_reboot_reason_checkbox.isChecked():
                    row.append(f"{reboot_reason:<35}")
                if self.reboot_event_raw_data_checkbox.isChecked():
                    row.append(line)

                reboot_event_times_1.append("".join(row))

        if reboot_event_times_1:
            self.result_label.setText(f"共找到 {len(reboot_event_times_1) - 1} 个重启事件")
            self.raw_data_display.setText("\n".join(reboot_event_times_1))
        else:
            self.result_label.setText("未找到重启事件")
            self.raw_data_display.setText("")

    # 6.5 MCU升级状态
    def process_mcu_upgrade_state(self, raw_data_string):
        headers = []
        if self.mcu_upgrade_state_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.mcu_upgrade_state_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.mcu_upgrade_state_upgrade_state_checkbox.isChecked():
            headers.append(f"{'升级状态':<31}")
        if self.mcu_upgrade_state_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        mcu_upgrade_state_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0406":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                upgrade_status_hex = line[70:72].upper()
                upgrade_status_map = {
                    "00": "success",
                    "01": "已下载，等待更新",
                    "11": "failure，帧的CRC校验错误",
                    "12": "failure，文件的CRC校验错误",
                    "21": "failure，文件名验证错误",
                    "22": "failure，长度错误",
                    "31": "failure，与硬件不匹配",
                    "32": "failure，超过2分钟未更新数据",
                    "33": "failure，请求错误，3小时后终止任务",
                    "34": "failure，服务器终止任务",
                    "35": "failure，电压过低",
                }
                upgrade_status = upgrade_status_map.get(upgrade_status_hex, "N/A")

                row = []
                if self.mcu_upgrade_state_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.mcu_upgrade_state_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.mcu_upgrade_state_upgrade_state_checkbox.isChecked():
                    row.append(f"{upgrade_status:<35}")
                if self.mcu_upgrade_state_raw_data_checkbox.isChecked():
                    row.append(line)

                mcu_upgrade_state_event_times_1.append("".join(row))

        if mcu_upgrade_state_event_times_1:
            self.result_label.setText(f"共找到 {len(mcu_upgrade_state_event_times_1) - 1} 个MCU升级状态事件")
            self.raw_data_display.setText("\n".join(mcu_upgrade_state_event_times_1))
        else:
            self.result_label.setText("未找到MCU升级状态事件")
            self.raw_data_display.setText("")

    # 6.6 短信消息
    def process_sms(self, raw_data_string):
        headers = []
        if self.sms_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sms_utc_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sms_sms_time_checkbox.isChecked():
            headers.append(f"{'短信时间':<19}")
        if self.sms_phone_num_checkbox.isChecked():
            headers.append(f"{'电话号码':<19}")
        if self.sms_encoding_checkbox.isChecked():
            headers.append(f"{'编码格式':<10}")
        if self.sms_message_checkbox.isChecked():
            headers.append(f"{'消息':<19}")
        if self.sms_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sms_event_time_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "040B":
                imei = ascii_to_decimal(line[18:48])
                utc_time = hex_to_beijing_time(line[62:70])
                sms_time = hex_to_utc_time(line[70:78])

                ptr = 78

                # 1. 手机号长度 N (1字节 HEX)
                phone_len_hex = line[ptr:ptr + 2]
                phone_len = int(phone_len_hex, 16)
                ptr += 2  # 长度字段固定占1字节

                # 2. 手机号（长度 N 字节）
                phone_number = ""
                if phone_len > 0:
                    phone_hex = line[ptr:ptr + phone_len * 2]
                    phone_number = bytes.fromhex(phone_hex).decode("utf-8")
                    ptr += phone_len * 2

                # 3. SMS编码长度 N1 (1字节 HEX)
                sms_enc_len_hex = line[ptr:ptr + 2]
                sms_enc_len = int(sms_enc_len_hex, 16)
                ptr += 2

                # 4. SMS编码（长度 N1 字节）
                sms_encoding = ""
                if sms_enc_len > 0:
                    enc_hex = line[ptr:ptr + sms_enc_len * 2]
                    enc_bytes = bytes.fromhex(enc_hex)
                    # 编码标识容错读取
                    try:
                        sms_encoding = enc_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        sms_encoding = enc_bytes.decode("gb18030", errors="replace")
                    ptr += sms_enc_len * 2

                # 5. SMS内容长度 N2 (2字节 HEX，协议写的是两个字节)
                sms_msg_len_hex = line[ptr:ptr + 4]
                sms_msg_len = int(sms_msg_len_hex, 16)
                ptr += 4

                # 6. SMS内容（长度 N2 字节）
                sms_message = ""
                if sms_msg_len > 0:
                    msg_hex = line[ptr:ptr + sms_msg_len * 2]
                    msg_bytes = bytes.fromhex(msg_hex)
                    # 根据编码类型分别解析
                    if sms_encoding.strip().upper() == "UCS2":
                        # UCS2 短信标准为大端 UTF-16BE
                        try:
                            sms_message = msg_bytes.decode("utf-16be")
                        except UnicodeDecodeError:
                            sms_message = msg_bytes.decode("utf-16be", errors="replace")
                    else:
                        # 普通ASCII/GBK文本兜底
                        try:
                            sms_message = msg_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            sms_message = msg_bytes.decode("gb18030", errors="replace")
                    ptr += sms_msg_len * 2

                # 7. SMS是否结束标记 (1字节 HEX)
                sms_end_hex = line[ptr:ptr + 2]
                end_status = "end" if sms_end_hex == "00" else "not end" if sms_end_hex == "01" else "unknown"

                row = []
                if self.sms_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sms_utc_time_checkbox.isChecked():
                    row.append(f"{utc_time:<23}")
                if self.sms_sms_time_checkbox.isChecked():
                    row.append(f"{sms_time:<23}")
                if self.sms_phone_num_checkbox.isChecked():
                    row.append(f"{phone_number:<23}")
                if self.sms_encoding_checkbox.isChecked():
                    row.append(f"{sms_encoding:<14}")
                if self.sms_message_checkbox.isChecked():
                    row.append(f"{sms_message:<23}")
                if self.sms_raw_data_checkbox.isChecked():
                    row.append(line)

                sms_event_time_1.append("".join(row))

        if sms_event_time_1:
            self.result_label.setText(f"共找到 {len(sms_event_time_1) - 1} 个SMS事件")
            self.raw_data_display.setText("\n".join(sms_event_time_1))
        else:
            self.result_label.setText("未找到SMS事件")
            self.raw_data_display.setText("")

    # 6.7 设备信息
    def process_device_info(self, raw_data_string):
        device_info_header_fields = [
            ("device_info_imei_checkbox", "IMEI", 20),
            ("device_info_time_checkbox", "触发时间", 19),
            ("device_info_phone_number_checkbox", "号码", 14),
            ("device_info_iccid_checkbox", "ICCID", 22),
            ("device_info_imsi_checkbox", "IMSI", 17),
            ("device_info_wifi_mac_checkbox", "WIFI MAC", 19),
            ("device_info_bt_mac_checkbox", "BT MAC", 19),
            ("device_info_wifi_mac_5g_checkbox", "WIFI MAC 5G", 19),
            ("device_info_softerware_ble_version_checkbox", "BLE VER", 25),
            ("device_info_softerware_gnss_version_checkbox", "GNSS VER", 25),
            ("device_info_softerware_boot_version_checkbox", "BOOT VER", 25),
            ("device_info_softerware_ap_version_checkbox", "AP VER", 25),
            ("device_info_mcc_checkbox", "MCC", 6),
            ("device_info_mnc_checkbox", "MNC", 6),
            ("device_info_cfg_file_version_checkbox", "CFG VER", 10),
            ("device_info_gl103_workmode_checkbox", "103 MODE", 20),
            ("device_info_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]
        headers = []
        for attr, label, width in device_info_header_fields:
            checkbox = getattr(self, attr)
            if checkbox.isChecked():
                if width:
                    headers.append(f"{label:<{width}}")
                else:
                    headers.append(label)

        device_info_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "040C":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                phone_number_len = int(line[70:72], 16)
                phone_number_str = line[72:72 + phone_number_len * 2]
                phone_number = ascii_to_decimal(phone_number_str) if phone_number_len != 0 else "N/A"
                # phone_number = ascii_to_decimal(phone_number_str)

                end_phone_number = 72 + phone_number_len * 2

                iccid_len_str = line[end_phone_number:end_phone_number + 2]
                iccid_len = int(iccid_len_str, 16)
                iccid_str = line[end_phone_number + 2:end_phone_number + 2 + iccid_len * 2]
                iccid = ascii_to_decimal(iccid_str) if iccid_len != 0 else "N/A"
                # iccid = ascii_to_decimal(iccid_str)

                end_iccid = end_phone_number + 2 + iccid_len * 2

                imsi_len_str = line[end_iccid:end_iccid + 2]
                imsi_len = int(imsi_len_str, 16)
                imsi_str = line[end_iccid + 2:end_iccid + 2 + imsi_len * 2]
                imsi = ascii_to_decimal(imsi_str) if imsi_len != 0 else "N/A"
                # imsi = ascii_to_decimal(imsi_str)

                end_imsi = end_iccid + 2 + imsi_len * 2

                wifi_mac_len_hex = line[end_imsi:end_imsi + 2]
                wifi_mac_len = int(wifi_mac_len_hex, 16)
                wifi_mac_str = line[end_imsi + 2:end_imsi + 2 + wifi_mac_len * 2]
                wifi_mac = ascii_to_decimal(wifi_mac_str) if wifi_mac_len != 0 else "N/A"
                # wifi_mac = ascii_to_decimal(wifi_mac_str)

                end_wifi_mac = end_imsi + 2 + wifi_mac_len * 2

                bt_mac_len_hex = line[end_wifi_mac:end_wifi_mac + 2]
                bt_mac_len = int(bt_mac_len_hex, 16)
                bt_mac_str = line[end_wifi_mac + 2:end_wifi_mac + 2 + bt_mac_len * 2]
                bt_mac = ascii_to_decimal(bt_mac_str) if bt_mac_len != 0 else "N/A"
                # bt_mac = ascii_to_decimal(bt_mac_str)

                end_bt_mac = end_wifi_mac + 2 + bt_mac_len * 2

                wifi_mac_5g_len_hex = line[end_bt_mac:end_bt_mac + 2]
                wifi_mac_5g_len = int(wifi_mac_5g_len_hex, 16)
                wifi_mac_5g_str = line[end_bt_mac + 2:end_bt_mac + 2 + wifi_mac_5g_len * 2]
                wifi_mac_5g = ascii_to_decimal(wifi_mac_5g_str) if wifi_mac_5g_len != 0 else "N/A"
                # wifi_mac_5g = ascii_to_decimal(wifi_mac_5g_str)

                end_wifi_mac_5g = end_bt_mac + 2 + wifi_mac_5g_len * 2

                software_ble_version_len_hex = line[end_wifi_mac_5g:end_wifi_mac_5g + 2]
                software_ble_version_len_bit = format(int(software_ble_version_len_hex, 16), '08b')
                low_6_bits_ble = software_ble_version_len_bit[-6:]  # 取第5到第0位（低6位）
                software_ble_version_len_result = int(low_6_bits_ble, 2)
                software_ble_version_str = line[
                                           end_wifi_mac_5g + 2:end_wifi_mac_5g + 2 + software_ble_version_len_result * 2]
                software_ble_version = ascii_to_decimal(
                    software_ble_version_str) if software_ble_version_len_result != 0 else "N/A"
                # software_ble_version = ascii_to_decimal(software_ble_version_str)

                end_ble_version = end_wifi_mac_5g + 2 + software_ble_version_len_result * 2

                software_gnss_version_len_hex = line[end_ble_version:end_ble_version + 2]
                software_gnss_version_len_bit = format(int(software_gnss_version_len_hex, 16), '08b')
                low_6_bits_gnss = software_gnss_version_len_bit[-6:]
                software_gnss_version_len_result = int(low_6_bits_gnss, 2)
                software_gnss_version_str = line[
                                            end_ble_version + 2:end_ble_version + 2 + software_gnss_version_len_result * 2]
                software_gnss_version = ascii_to_decimal(
                    software_gnss_version_str) if software_gnss_version_len_result != 0 else "N/A"
                # software_gnss_version = ascii_to_decimal(software_gnss_version_str)

                end_gnss_version = end_ble_version + 2 + software_gnss_version_len_result * 2

                software_boot_version_len_hex = line[end_gnss_version:end_gnss_version + 2]
                software_boot_version_len_bit = format(int(software_boot_version_len_hex, 16), '08b')
                low_6_bits_boot = software_boot_version_len_bit[-6:]
                software_boot_version_len_result = int(low_6_bits_boot, 2)
                software_boot_version_str = line[
                                            end_gnss_version + 2:end_gnss_version + 2 + software_boot_version_len_result * 2]
                software_boot_version = ascii_to_decimal(
                    software_boot_version_str) if software_boot_version_len_result != 0 else "N/A"
                # software_boot_version = ascii_to_decimal(software_boot_version_str)

                end_boot_version = end_gnss_version + 2 + software_boot_version_len_result * 2
                software_ap_version_len_hex = line[end_boot_version:end_boot_version + 2]
                software_ap_version_len_bit = format(int(software_ap_version_len_hex, 16), '08b')
                low_6_bits_ap = software_ap_version_len_bit[-6:]
                software_ap_version_len_result = int(low_6_bits_ap, 2)
                software_ap_version_str = line[
                                          end_boot_version + 2:end_boot_version + 2 + software_ap_version_len_result * 2]
                software_ap_version = ascii_to_decimal(
                    software_ap_version_str) if software_ap_version_len_result != 0 else "N/A"
                # software_ap_version = ascii_to_decimal(software_ap_version_str)

                end_ap_version = end_boot_version + 2 + software_ap_version_len_result * 2

                mcc_str = line[end_ap_version:end_ap_version + 6]
                if mcc_str:
                    try:
                        mcc = ascii_to_decimal(mcc_str)
                    except (ValueError, UnicodeDecodeError):
                        mcc = mcc_str
                else:
                    mcc = mcc_str
                # mcc = ascii_to_decimal(mcc_str)

                mnc_len = line[end_ap_version + 6:end_ap_version + 6 + 2]
                mnc_str = line[end_ap_version + 6 + 2:end_ap_version + 6 + 2 + int(mnc_len, 16) * 2]
                if mnc_str:
                    try:
                        mnc = ascii_to_decimal(mnc_str)
                    except (ValueError, UnicodeDecodeError):
                        mnc = mnc_str
                else:
                    mnc = mnc_str
                # mnc = ascii_to_decimal(mnc_str)

                end_mnc = end_ap_version + 6 + 2 + int(mnc_len, 16) * 2

                cfg_file_version_len = line[end_mnc:end_mnc + 2]
                cfg_file_version_len_bit = format(int(cfg_file_version_len, 16), '08b')
                low_6_bits_cfg = cfg_file_version_len_bit[-6:]
                cfg_file_version_len_result = int(low_6_bits_cfg, 2)
                cfg_file_version_str = line[end_mnc + 2:end_mnc + 2 + cfg_file_version_len_result * 2]
                cfg_file_version = ascii_to_decimal(cfg_file_version_str) if cfg_file_version_len_result != 0 else "N/A"
                # cfg_file_version = ascii_to_decimal(cfg_file_version_str)

                gl103_workmode_str = line[
                                     end_mnc + 2 + cfg_file_version_len_result * 2:end_mnc + 2 + cfg_file_version_len_result * 2 + 2]
                if gl103_workmode_str == "01":
                    gl103_workmode = "mode 1"
                elif gl103_workmode_str == "02":
                    gl103_workmode = "mode 2"
                elif gl103_workmode_str == "03":
                    gl103_workmode = "mode 3"
                elif gl103_workmode_str == "04":
                    gl103_workmode = "mode 4"
                elif gl103_workmode_str.upper() == "FF":
                    gl103_workmode = "Not Applicable"
                else:
                    gl103_workmode = gl103_workmode_str

                device_info_tail_fields = [
                    (self.device_info_imei_checkbox, imei, 20),
                    (self.device_info_time_checkbox, time_str, 23),
                    (self.device_info_phone_number_checkbox, phone_number, 16),
                    (self.device_info_iccid_checkbox, iccid, 22),
                    (self.device_info_imsi_checkbox, imsi, 17),
                    (self.device_info_wifi_mac_checkbox, wifi_mac, 19),
                    (self.device_info_bt_mac_checkbox, bt_mac, 19),
                    (self.device_info_wifi_mac_5g_checkbox, wifi_mac_5g, 19),
                    (self.device_info_softerware_ble_version_checkbox, software_ble_version, 25),
                    (self.device_info_softerware_gnss_version_checkbox, software_gnss_version, 25),
                    (self.device_info_softerware_boot_version_checkbox, software_boot_version, 25),
                    (self.device_info_softerware_ap_version_checkbox, software_ap_version, 25),
                    (self.device_info_mcc_checkbox, mcc, 6),
                    (self.device_info_mnc_checkbox, mnc, 6),
                    (self.device_info_cfg_file_version_checkbox, cfg_file_version, 10),
                    (self.device_info_gl103_workmode_checkbox, gl103_workmode, 20),
                    (self.device_info_raw_data_checkbox, line, 100),
                ]

                row = []
                for checkbox, value, width in device_info_tail_fields:
                    if checkbox.isChecked():
                        row.append(f"{value:<{width}}")

                if self.device_info_raw_data_checkbox.isChecked():
                    row.append(line)

                device_info_event_times_1.append("".join(row))

        if device_info_event_times_1:
            self.result_label.setText(f"共找到 {len(device_info_event_times_1) - 1} 个设备信息事件")
            self.raw_data_display.setText("\n".join(device_info_event_times_1))
        else:
            self.result_label.setText("未找到设备信息事件")
            self.raw_data_display.setText("")

    # 6.8 sensor_normal 事件
    def process_sensor_normal(self, raw_data_string):
        sensor_normal_header_fields = [
            ("sensor_normal_imei_checkbox", "IMEI", 20),
            ("sensor_normal_time_checkbox", "触发时间", 19),
            ("sensor_normal_time_interval_checkbox", "时间间隔", 6),
            ("sensor_normal_sensor_status_checkbox", "状态", 12),
            ("sensor_normal_number_checkbox", "sensor数量", 12),
            ("sensor_normal_x_axis_checkbox", "X轴", 8),
            ("sensor_normal_y_axis_checkbox", "Y轴", 8),
            ("sensor_normal_z_axis_checkbox", "Z轴", 8),
            ("sensor_normal_rpm_checkbox", "转速", 8),
            ("sensor_normal_speed_checkbox", "车速", 8),
            ("sensor_normal_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]

        headers = build_checkbox(sensor_normal_header_fields, self)

        sensor_normal_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "040D":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                time_interval = int(line[70:74], 16)
                sensor_status_hex = line[74:76]
                sensor_status_map = {
                    "00": "Not Cal",
                    "01": "learning",
                    "02": "success"
                }
                sensor_status = sensor_status_map.get(sensor_status_hex, "N/A")

                sensor_number = int(line[76:78], 16)
                if sensor_number == 0:
                    sensor_normal_event_times_1.append("未找到sensor_normal事件")
                    continue

                for i in range(sensor_number):
                    start = 78 + i * 28 * 2
                    end = start + 56
                    sensor_data = line[start:end]
                    x_axis = parse_signed_16bit(sensor_data[0:4])
                    y_axis = parse_signed_16bit(sensor_data[4:8])
                    z_axis = parse_signed_16bit(sensor_data[8:12])
                    rpm = int(sensor_data[12:16], 16)
                    speed = int(sensor_data[16:20], 16)

                    sensor_normal_tail_fields = [
                        ("sensor_normal_imei_checkbox", imei, 20),
                        ("sensor_normal_time_checkbox", time_str, 23),
                        ("sensor_normal_time_interval_checkbox", time_interval, 10),
                        ("sensor_normal_sensor_status_checkbox", sensor_status, 14),
                        ("sensor_normal_number_checkbox", sensor_number, 14),
                        ("sensor_normal_x_axis_checkbox", x_axis, 9),
                        ("sensor_normal_y_axis_checkbox", y_axis, 9),
                        ("sensor_normal_z_axis_checkbox", z_axis, 9),
                        ("sensor_normal_rpm_checkbox", rpm, 10),
                        ("sensor_normal_speed_checkbox", speed, 10),
                        ("sensor_normal_raw_data_checkbox", line, 100),
                    ]

                    row = build_checkbox(sensor_normal_tail_fields, self)

                    sensor_normal_event_times_1.append("".join(row))

        if sensor_normal_event_times_1:
            self.result_label.setText(f"共找到 {len(sensor_normal_event_times_1) - 1} 个sensor_normal事件")
            self.raw_data_display.setText("\n".join(sensor_normal_event_times_1))
        else:
            self.result_label.setText("未找到sensor_normal事件")
            self.raw_data_display.setText("")

    # 6.9 sensor_event 事件
    def process_sensor_event(self, raw_data_string):
        sensor_event_header_fields = [
            ("sensor_event_imei_checkbox", "IMEI", 20),
            ("sensor_event_time_checkbox", "上报时间", 19),
            ("sensor_event_happen_time_checkbox", "发生时间", 19),
            ("sensor_event_event_time_checkbox", "事件时间(ms)", 10),
            ("sensor_event_collection_time_checkbox", "采集时间", 19),
            ("sensor_event_collection_time_ms_checkbox", "采集时间(ms)", 10),
            ("sensor_event_time_interval_checkbox", "时间间隔", 6),
            ("sensor_event_event_type_checkbox", "事件类型", 6),
            ("sensor_event_sensor_state_checkbox", "状态", 12),
            ("sensor_event_sensor_num_checkbox", "sensor数量", 12),
            ("sensor_event_x_axis_checkbox", "X轴", 8),
            ("sensor_event_y_axis_checkbox", "Y轴", 8),
            ("sensor_event_z_axis_checkbox", "Z轴", 8),
            ("sensor_event_rpm_checkbox", "转速", 8),
            ("sensor_event_speed_checkbox", "车速", 8),
            ("sensor_event_raw_data_checkbox", "原始数据", 100),
        ]

        headers = build_checkbox(sensor_event_header_fields, self)

        sensor_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "040E":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                happen_time = hex_to_beijing_time(line[70:78])
                event_time = int(line[78:82], 16)
                collection_time = hex_to_beijing_time(line[82:90])
                collection_time_ms = int(line[90:94], 16)
                time_interval = int(line[94:98], 16)
                event_type_hex = line[98:100]
                event_type_map = {
                    "00": "Acc",
                    "01": "Dec",
                    "02": "Turn",
                    "03": "Crash",
                    "04": "S-Lane "
                }
                event_type = event_type_map.get(event_type_hex, "N/A")
                sensor_status_hex = line[100:102]
                sensor_status_map = {
                    "00": "Not",
                    "01": "learning",
                    "02": "success"
                }
                sensor_status = sensor_status_map.get(sensor_status_hex, "N/A")
                sensor_number = int(line[102:104], 16)
                if sensor_number == 0:
                    sensor_event_times_1.append("未找到sensor_event事件")
                    continue
                for i in range(sensor_number):
                    start = 104 + i * 10 * 2
                    end = start + 20
                    sensor_data = line[start:end]

                    x_axis = parse_signed_16bit(sensor_data[0:4])
                    y_axis = parse_signed_16bit(sensor_data[4:8])
                    z_axis = parse_signed_16bit(sensor_data[8:12])
                    rpm = int(sensor_data[12:16], 16)
                    speed = int(sensor_data[16:20], 16)

                    sensor_event_tail_fields = [
                        ("sensor_event_imei_checkbox", imei, 20),
                        ("sensor_event_time_checkbox", time_str, 23),
                        ("sensor_event_happen_time_checkbox", happen_time, 23),
                        ("sensor_event_event_time_checkbox", event_time, 14),
                        ("sensor_event_collection_time_checkbox", collection_time, 23),
                        ("sensor_event_collection_time_ms_checkbox", collection_time_ms, 14),
                        ("sensor_event_time_interval_checkbox", time_interval, 10),
                        ("sensor_event_event_type_checkbox", event_type, 10),
                        ("sensor_event_sensor_state_checkbox", sensor_status, 14),
                        ("sensor_event_sensor_num_checkbox", sensor_number, 14),
                        ("sensor_event_x_axis_checkbox", x_axis, 9),
                        ("sensor_event_y_axis_checkbox", y_axis, 9),
                        ("sensor_event_z_axis_checkbox", z_axis, 9),
                        ("sensor_event_rpm_checkbox", rpm, 10),
                        ("sensor_event_speed_checkbox", speed, 10),
                        ("sensor_event_raw_data_checkbox", line, 100),
                    ]

                    row = build_checkbox(sensor_event_tail_fields, self)

                    sensor_event_times_1.append("".join(row))
        if sensor_event_times_1:
            self.result_label.setText(f"共找到 {len(sensor_event_times_1) - 1} 个sensor_event事件")
            self.raw_data_display.setText("\n".join(sensor_event_times_1))
        else:
            self.result_label.setText("未找到sensor_event事件")
            self.raw_data_display.setText("")

    # 6.10 Modem Upgrade state
    def process_modem_upgrade_state(self, raw_data_string):
        headers = []
        if self.modem_upgrade_state_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.modem_upgrade_state_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.modem_upgrade_state_upgrade_state_checkbox.isChecked():
            headers.append(f"{'升级状态':<10}")
        if self.modem_upgrade_state_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        modem_upgrade_state_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0413":
                if len(line) < 72:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                upgrade_state_hex = line[70:72].upper()
                upgrade_state_map = {
                    "00": "success",
                    "01": "fail",
                }
                upgrade_state = upgrade_state_map.get(upgrade_state_hex, upgrade_state_hex)

                row = []
                if self.modem_upgrade_state_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.modem_upgrade_state_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.modem_upgrade_state_upgrade_state_checkbox.isChecked():
                    row.append(f"{upgrade_state:<12}")
                if self.modem_upgrade_state_raw_data_checkbox.isChecked():
                    row.append(line)

                modem_upgrade_state_event_times_1.append("".join(row))

        if modem_upgrade_state_event_times_1:
            self.result_label.setText(f"共找到 {len(modem_upgrade_state_event_times_1) - 1} 个Modem升级状态事件")
            self.raw_data_display.setText("\n".join(modem_upgrade_state_event_times_1))
        else:
            self.result_label.setText("未找到Modem升级状态事件")
            self.raw_data_display.setText("")

    # 6.11 继电器控制状态
    def process_relay_control_status(self, raw_data_string):
        relay_control_status_header_fields = [
            ("relay_control_status_imei_checkbox", "IMEI", 20),
            ("relay_control_status_time_checkbox", "上报时间", 19),
            ("relay_control_status_relay_control_status_checkbox", "控制状态", 12),
            ("relay_control_status_event_trigger_reason_checkbox", "原因", 20),
            ("relay_control_status_ibutton_id_checkbox", "iButton ID", 20),
            ("relay_control_status_rfid_id_checkbox", "RFID ID", 14),
            ("relay_control_status_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]
        headers = build_checkbox(relay_control_status_header_fields, self)
        relay_control_status_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0414":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                relay_control_status_hex = line[70:72]
                relay_control_status_map = {
                    "00": "恢复",
                    "01": "切断",
                }
                relay_control_status = relay_control_status_map.get(relay_control_status_hex, "N/A")

                event_trigger_reason_hex = line[120:122]
                event_trigger_reason_map = {
                    "00": "属iButton白名单",
                    "01": "平台命令",
                    "02": "属RFID白名单",
                    "03": "熄火断开",
                    "04": "工具断开",
                }
                event_trigger_reason = event_trigger_reason_map.get(event_trigger_reason_hex, "N/A")

                ibutton_id = line[122:138].upper()
                rfid_id = line[138:146].upper()

                relay_control_status_tail_fields = [
                    ("relay_control_status_imei_checkbox", imei, 20),
                    ("relay_control_status_time_checkbox", time_str, 23),
                    ("relay_control_status_relay_control_status_checkbox", relay_control_status, 14),
                    ("relay_control_status_event_trigger_reason_checkbox", event_trigger_reason, 18),
                    ("relay_control_status_ibutton_id_checkbox", ibutton_id, 20),
                    ("relay_control_status_rfid_id_checkbox", rfid_id, 14),
                    ("relay_control_status_raw_data_checkbox", line, 100),
                ]
                row = build_checkbox(relay_control_status_tail_fields, self)
                relay_control_status_event_times_1.append("".join(row))

        if relay_control_status_event_times_1:
            self.result_label.setText(f"共找到 {len(relay_control_status_event_times_1) - 1} 个继电器控制状态事件")
            self.raw_data_display.setText("\n".join(relay_control_status_event_times_1))
        else:
            self.result_label.setText("未找到继电器控制状态事件")
            self.raw_data_display.setText("")

    # 6.12 自学习状态监测
    def process_self_learning_status(self,raw_data_string):
        headers = []
        if self.self_learning_status_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.self_learning_status_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.self_learning_status_calibration_status_checkbox.isChecked():
            headers.append(f"{'学习状态':<19}")
        if self.self_learning_status_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据':<20}")

        self_learning_status_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0407":
                imei = ascii_to_decimal(line[18:48])
                report_time = hex_to_beijing_time(line[62:70])
                calibration_status_hex = line[70:72]
                calibration_status = "learning success" if calibration_status_hex == "01" else "unknown"

                row = []

                if self.self_learning_status_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.self_learning_status_time_checkbox.isChecked():
                    row.append(f"{report_time:<23}")
                if self.self_learning_status_calibration_status_checkbox.isChecked():
                    row.append(f"{calibration_status:<23}")
                if self.self_learning_status_raw_data_checkbox.isChecked():
                    row.append(line)

                self_learning_status_event_times_1.append("".join(row))

        if self_learning_status_event_times_1:
            self.result_label.setText(f"共找到 {len(self_learning_status_event_times_1) - 1} 个自学习事件")
            self.raw_data_display.setText("\n".join(self_learning_status_event_times_1))
        else:
            self.result_label.setText("未找到自学习事件")
            self.raw_data_display.setText("")

    # 6.13 Upgrade status of other components
    def process_other_components_upgrade_status(self, raw_data_string):
        headers = []
        if self.other_components_upgrade_status_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.other_components_upgrade_status_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.other_components_upgrade_status_upgrade_state_checkbox.isChecked():
            headers.append(f"{'升级状态':<6}")
        if self.other_components_upgrade_status_type_checkbox.isChecked():
            headers.append(f"{'类型':<12}")
        if self.other_components_upgrade_status_raw_data_checkbox.isChecked():
            headers.append(f"{'Raw Data'}")

        other_components_upgrade_status_event_times_1 = ["".join(headers)]

        upgrade_state_map = {
            "00": "Success",
            "01": "Fail",
            "02": "Fail, MD5 verification of FOTA package failed",
        }
        type_map = {
            "00": "BLE",
            "01": "GNSS",
            "02": "BOOT",
            "03": "AP",
            "04": "CFG file",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0415":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                upgrade_state_hex = line[70:72].upper()
                type_hex = line[72:74].upper()
                upgrade_state = upgrade_state_map.get(upgrade_state_hex, f"Reserved({upgrade_state_hex})")
                upgrade_type = type_map.get(type_hex, f"Reserved({type_hex})")

                row = []
                if self.other_components_upgrade_status_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.other_components_upgrade_status_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.other_components_upgrade_status_upgrade_state_checkbox.isChecked():
                    row.append(f"{upgrade_state:<10}")
                if self.other_components_upgrade_status_type_checkbox.isChecked():
                    row.append(f"{upgrade_type:<12}")
                if self.other_components_upgrade_status_raw_data_checkbox.isChecked():
                    row.append(line)

                other_components_upgrade_status_event_times_1.append("".join(row))

        if other_components_upgrade_status_event_times_1:
            self.result_label.setText(
                f"共找到 {len(other_components_upgrade_status_event_times_1) - 1} 个升级状态事件"
            )
            self.raw_data_display.setText("\n".join(other_components_upgrade_status_event_times_1))
        else:
            self.result_label.setText("未找到升级事件状态")
            self.raw_data_display.setText("")

    # 6.14 Workmode Switch Status
    def process_workmode_switch_status(self, raw_data_string):
        headers = []
        if self.workmode_switch_status_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.workmode_switch_status_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.workmode_switch_status_workmode_checkbox.isChecked():
            headers.append(f"{'当前模式':<12}")
        if self.workmode_switch_status_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        workmode_switch_status_event_times_1 = ["".join(headers)]

        workmode_map = {
            "01": "Workmode 1",
            "02": "Workmode 2",
            "03": "Workmode 3",
            "04": "Workmode 4",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0416":
                if len(line) < 72:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                workmode_hex = line[70:72].upper()
                workmode = workmode_map.get(workmode_hex, "FF" if workmode_hex == "FF" else workmode_hex)

                row = []
                if self.workmode_switch_status_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.workmode_switch_status_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.workmode_switch_status_workmode_checkbox.isChecked():
                    row.append(f"{workmode:<14}")
                if self.workmode_switch_status_raw_data_checkbox.isChecked():
                    row.append(line)

                workmode_switch_status_event_times_1.append("".join(row))

        if workmode_switch_status_event_times_1:
            self.result_label.setText(f"共找到 {len(workmode_switch_status_event_times_1) - 1} 个工作模式切换事件")
            self.raw_data_display.setText("\n".join(workmode_switch_status_event_times_1))
        else:
            self.result_label.setText("未找到工作模式切换事件")
            self.raw_data_display.setText("")

    # 6.15 Device Collected Temperature
    def process_device_collected_temperature(self, raw_data_string):
        headers = []
        if self.device_collected_temperature_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.device_collected_temperature_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.device_collected_temperature_package_num_checkbox.isChecked():
            headers.append(f"{'温度包数量':<10}")
        if self.device_collected_temperature_collection_time_checkbox.isChecked():
            headers.append(f"{'采集时间':<19}")
        if self.device_collected_temperature_temperature_checkbox.isChecked():
            headers.append(f"{'温度':<10}")
        if self.device_collected_temperature_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        device_collected_temperature_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0417":
                if len(line) < 72:
                    continue
                imei = ascii_to_decimal(line[18:48])
                report_time = hex_to_beijing_time(line[62:70])
                package_num = int(line[70:72], 16)
                offset = 72

                if package_num == 0:
                    continue

                for _ in range(package_num):
                    if offset + 12 > len(line):
                        break
                    collection_time = hex_to_beijing_time(line[offset:offset + 8])
                    temperature_hex = line[offset + 8:offset + 12].upper()
                    temperature = "FFFF" if temperature_hex == "FFFF" else round(int(temperature_hex, 16) * 0.1 - 40, 1)
                    offset += 12

                    row = []
                    if self.device_collected_temperature_imei_checkbox.isChecked():
                        row.append(f"{imei:<20}")
                    if self.device_collected_temperature_time_checkbox.isChecked():
                        row.append(f"{report_time:<23}")
                    if self.device_collected_temperature_package_num_checkbox.isChecked():
                        row.append(f"{package_num:<12}")
                    if self.device_collected_temperature_collection_time_checkbox.isChecked():
                        row.append(f"{collection_time:<23}")
                    if self.device_collected_temperature_temperature_checkbox.isChecked():
                        row.append(f"{temperature:<12}")
                    if self.device_collected_temperature_raw_data_checkbox.isChecked():
                        row.append(line)

                    device_collected_temperature_event_times_1.append("".join(row))

        if device_collected_temperature_event_times_1:
            self.result_label.setText(f"共找到 {len(device_collected_temperature_event_times_1) - 1} 个设备采集温度事件")
            self.raw_data_display.setText("\n".join(device_collected_temperature_event_times_1))
        else:
            self.result_label.setText("未找到设备采集温度事件")
            self.raw_data_display.setText("")

    # 6.16 Device Collected Air Pressure
    def process_device_collected_air_pressure(self, raw_data_string):
        headers = []
        if self.device_collected_air_pressure_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.device_collected_air_pressure_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.device_collected_air_pressure_package_num_checkbox.isChecked():
            headers.append(f"{'气压包数量':<10}")
        if self.device_collected_air_pressure_collection_time_checkbox.isChecked():
            headers.append(f"{'采集时间':<19}")
        if self.device_collected_air_pressure_air_pressure_checkbox.isChecked():
            headers.append(f"{'气压':<10}")
        if self.device_collected_air_pressure_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        device_collected_air_pressure_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0418":
                if len(line) < 72:
                    continue
                imei = ascii_to_decimal(line[18:48])
                report_time = hex_to_beijing_time(line[62:70])
                package_num = int(line[70:72], 16)
                offset = 72

                if package_num == 0:
                    continue

                for _ in range(package_num):
                    if offset + 12 > len(line):
                        break
                    collection_time = hex_to_beijing_time(line[offset:offset + 8])
                    air_pressure_hex = line[offset + 8:offset + 12].upper()
                    air_pressure = "FFFF" if air_pressure_hex == "FFFF" else int(air_pressure_hex, 16)
                    offset += 12

                    row = []
                    if self.device_collected_air_pressure_imei_checkbox.isChecked():
                        row.append(f"{imei:<20}")
                    if self.device_collected_air_pressure_time_checkbox.isChecked():
                        row.append(f"{report_time:<23}")
                    if self.device_collected_air_pressure_package_num_checkbox.isChecked():
                        row.append(f"{package_num:<12}")
                    if self.device_collected_air_pressure_collection_time_checkbox.isChecked():
                        row.append(f"{collection_time:<23}")
                    if self.device_collected_air_pressure_air_pressure_checkbox.isChecked():
                        row.append(f"{air_pressure:<12}")
                    if self.device_collected_air_pressure_raw_data_checkbox.isChecked():
                        row.append(line)

                    device_collected_air_pressure_event_times_1.append("".join(row))

        if device_collected_air_pressure_event_times_1:
            self.result_label.setText(f"共找到 {len(device_collected_air_pressure_event_times_1) - 1} 个设备采集气压事件")
            self.raw_data_display.setText("\n".join(device_collected_air_pressure_event_times_1))
        else:
            self.result_label.setText("未找到设备采集气压事件")
            self.raw_data_display.setText("")

    # 6.17 Movement Detection
    def process_movement_detection(self, raw_data_string):
        headers = []
        if self.movement_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.movement_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.movement_detection_movement_state_checkbox.isChecked():
            headers.append(f"{'运动状态':<18}")
        if self.movement_detection_location_data_checkbox.isChecked():
            headers.append(f"{'Location Data 1'}")
        if self.movement_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        movement_detection_event_times_1 = ["".join(headers)]

        movement_state_map = {
            "00": "Quit movement state",
            "01": "Enter movement state",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0419":
                if len(line) < 110:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                movement_state_hex = line[70:72].upper()
                movement_state = movement_state_map.get(movement_state_hex, movement_state_hex)
                location_data_hex = line[72:110]
                location_data = parse_klv(location_data_hex) if location_data_hex else ""
                if not location_data:
                    location_data = location_data_hex

                row = []
                if self.movement_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.movement_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.movement_detection_movement_state_checkbox.isChecked():
                    row.append(f"{movement_state:<22}")
                if self.movement_detection_location_data_checkbox.isChecked():
                    row.append(f"{location_data:<25}")
                if self.movement_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                movement_detection_event_times_1.append("".join(row))

        if movement_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(movement_detection_event_times_1) - 1} 个运动检测事件")
            self.raw_data_display.setText("\n".join(movement_detection_event_times_1))
        else:
            self.result_label.setText("未找到运动检测事件")
            self.raw_data_display.setText("")

    # 6.22 Sensor Data for Debugging
    def process_sensor_data_for_debugging(self, raw_data_string):
        headers = []
        if self.sensor_data_for_debugging_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sensor_data_for_debugging_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sensor_data_for_debugging_package_num_checkbox.isChecked():
            headers.append(f"{'包数量':<8}")
        if self.sensor_data_for_debugging_package_index_checkbox.isChecked():
            headers.append(f"{'包序号':<8}")
        if self.sensor_data_for_debugging_collection_time_checkbox.isChecked():
            headers.append(f"{'采集时间':<19}")
        if self.sensor_data_for_debugging_milliseconds_checkbox.isChecked():
            headers.append(f"{'毫秒':<8}")
        if self.sensor_data_for_debugging_x_axis_checkbox.isChecked():
            headers.append(f"{'X轴':<8}")
        if self.sensor_data_for_debugging_y_axis_checkbox.isChecked():
            headers.append(f"{'Y轴':<8}")
        if self.sensor_data_for_debugging_z_axis_checkbox.isChecked():
            headers.append(f"{'Z轴':<8}")
        if self.sensor_data_for_debugging_x_gyro_checkbox.isChecked():
            headers.append(f"{'X陀螺仪':<10}")
        if self.sensor_data_for_debugging_y_gyro_checkbox.isChecked():
            headers.append(f"{'Y陀螺仪':<10}")
        if self.sensor_data_for_debugging_z_gyro_checkbox.isChecked():
            headers.append(f"{'Z陀螺仪':<10}")
        if self.sensor_data_for_debugging_speed_source_checkbox.isChecked():
            headers.append(f"{'速度来源':<10}")
        if self.sensor_data_for_debugging_gps_status_checkbox.isChecked():
            headers.append(f"{'GPS状态':<12}")
        if self.sensor_data_for_debugging_sensor_status_checkbox.isChecked():
            headers.append(f"{'传感器状态':<14}")
        if self.sensor_data_for_debugging_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sensor_data_for_debugging_event_times_1 = ["".join(headers)]

        speed_source_map = {
            0: "Unknown",
            1: "CAN",
            2: "GPS",
        }
        gps_status_map = {
            0: "GPS not located",
            1: "GPS located",
        }
        sensor_status_map = {
            0: "Not calibrated",
            1: "learning",
            2: "learning success",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "04F0":
                if len(line) < 72:
                    continue
                imei = ascii_to_decimal(line[18:48])
                report_time = hex_to_beijing_time(line[62:70])
                package_num = int(line[70:72], 16)
                offset = 72

                for package_index in range(1, package_num + 1):
                    if offset + 38 > len(line):
                        break

                    try:
                        collection_time = hex_to_beijing_time(line[offset:offset + 8])
                        milliseconds = int(line[offset + 8:offset + 12], 16)
                        x_axis = parse_signed_16bit(line[offset + 12:offset + 16])
                        y_axis = parse_signed_16bit(line[offset + 16:offset + 20])
                        z_axis = parse_signed_16bit(line[offset + 20:offset + 24])
                        x_gyro = parse_signed_16bit(line[offset + 24:offset + 28])
                        y_gyro = parse_signed_16bit(line[offset + 28:offset + 32])
                        z_gyro = parse_signed_16bit(line[offset + 32:offset + 36])
                        status_hex = line[offset + 36:offset + 38]
                        status_val = int(status_hex, 16)
                    except Exception:
                        break

                    speed_source = speed_source_map.get(status_val & 0x03, "Reserved")
                    gps_status = gps_status_map.get((status_val >> 2) & 0x03, "Reserved")
                    sensor_status = sensor_status_map.get((status_val >> 4) & 0x0F, "Reserved")

                    row = []
                    if self.sensor_data_for_debugging_imei_checkbox.isChecked():
                        row.append(f"{imei:<20}")
                    if self.sensor_data_for_debugging_time_checkbox.isChecked():
                        row.append(f"{report_time:<23}")
                    if self.sensor_data_for_debugging_package_num_checkbox.isChecked():
                        row.append(f"{package_num:<8}")
                    if self.sensor_data_for_debugging_package_index_checkbox.isChecked():
                        row.append(f"{package_index:<8}")
                    if self.sensor_data_for_debugging_collection_time_checkbox.isChecked():
                        row.append(f"{collection_time:<23}")
                    if self.sensor_data_for_debugging_milliseconds_checkbox.isChecked():
                        row.append(f"{milliseconds:<8}")
                    if self.sensor_data_for_debugging_x_axis_checkbox.isChecked():
                        row.append(f"{x_axis:<8}")
                    if self.sensor_data_for_debugging_y_axis_checkbox.isChecked():
                        row.append(f"{y_axis:<8}")
                    if self.sensor_data_for_debugging_z_axis_checkbox.isChecked():
                        row.append(f"{z_axis:<8}")
                    if self.sensor_data_for_debugging_x_gyro_checkbox.isChecked():
                        row.append(f"{x_gyro:<10}")
                    if self.sensor_data_for_debugging_y_gyro_checkbox.isChecked():
                        row.append(f"{y_gyro:<10}")
                    if self.sensor_data_for_debugging_z_gyro_checkbox.isChecked():
                        row.append(f"{z_gyro:<10}")
                    if self.sensor_data_for_debugging_speed_source_checkbox.isChecked():
                        row.append(f"{speed_source:<14}")
                    if self.sensor_data_for_debugging_gps_status_checkbox.isChecked():
                        row.append(f"{gps_status:<16}")
                    if self.sensor_data_for_debugging_sensor_status_checkbox.isChecked():
                        row.append(f"{sensor_status:<16}")
                    if self.sensor_data_for_debugging_raw_data_checkbox.isChecked():
                        row.append(line)

                    sensor_data_for_debugging_event_times_1.append("".join(row))
                    offset += 38

        if sensor_data_for_debugging_event_times_1:
            self.result_label.setText(
                f"共找到 {len(sensor_data_for_debugging_event_times_1) - 1} 个Sensor Debug事件"
            )
            self.raw_data_display.setText("\n".join(sensor_data_for_debugging_event_times_1))
        else:
            self.result_label.setText("未找到Sensor Debug事件")
            self.raw_data_display.setText("")

    # 6.23 Switched Input Detection
    def process_switched_input_detection(self, raw_data_string):
        headers = []
        if self.switched_input_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.switched_input_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.switched_input_detection_event_type_checkbox.isChecked():
            headers.append(f"{'事件类型':<22}")
        if self.switched_input_detection_input_pin_checkbox.isChecked():
            headers.append(f"{'输入状态':<18}")
        if self.switched_input_detection_gps_data_checkbox.isChecked():
            headers.append(f"{'GPS位置':<25}")
        if self.switched_input_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        switched_input_detection_event_times_1 = ["".join(headers)]

        event_type_map = {
            "00": "0V -> 12V",
            "01": "12V -> 0V",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0425":
                if len(line) < 122:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                event_type_hex = line[70:72].upper()
                event_type = event_type_map.get(event_type_hex, event_type_hex)
                input_pin_hex = line[72:76].upper()
                input_byte0 = int(input_pin_hex[0:2], 16)
                input_byte1 = int(input_pin_hex[2:4], 16)
                input_desc = []
                if input_byte0 & 0x01:
                    input_desc.append("DIN1")
                if input_byte0 & 0x02:
                    input_desc.append("DIN2")
                if input_byte0 & 0x04:
                    input_desc.append("DIN3")
                if input_byte1 & 0x01:
                    input_desc.append("AIN1")
                if input_byte1 & 0x02:
                    input_desc.append("AIN2")
                if input_byte1 & 0x04:
                    input_desc.append("AIN3")
                input_pin = ", ".join(input_desc) if input_desc else input_pin_hex

                gps_hex = line[76:124]
                try:
                    gps_data = parse_gps_data(gps_hex)
                    gps_show = (
                        f"{gps_data['Time']} "
                        f"[{gps_data['Longitude']:.6f}, {gps_data['Latitude']:.6f}] "
                        f"Speed:{gps_data['GPS Speed']:.1f}"
                    )
                except Exception:
                    gps_show = gps_hex

                row = []
                if self.switched_input_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.switched_input_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.switched_input_detection_event_type_checkbox.isChecked():
                    row.append(f"{event_type:<24}")
                if self.switched_input_detection_input_pin_checkbox.isChecked():
                    row.append(f"{input_pin:<22}")
                if self.switched_input_detection_gps_data_checkbox.isChecked():
                    row.append(f"{gps_show:<25}")
                if self.switched_input_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                switched_input_detection_event_times_1.append("".join(row))

        if switched_input_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(switched_input_detection_event_times_1) - 1} 个切换输入检测事件")
            self.raw_data_display.setText("\n".join(switched_input_detection_event_times_1))
        else:
            self.result_label.setText("未找到切换输入检测事件")
            self.raw_data_display.setText("")

    # 6.24 Pulse Detection
    def process_pulse_detection(self, raw_data_string):
        headers = []
        if self.pulse_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.pulse_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.pulse_detection_input_pin_checkbox.isChecked():
            headers.append(f"{'输入状态':<18}")
        if self.pulse_detection_gps_data_checkbox.isChecked():
            headers.append(f"{'GPS位置':<25}")
        if self.pulse_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        pulse_detection_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0426":
                if len(line) < 120:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                input_pin_hex = line[70:72].upper()
                input_val = int(input_pin_hex, 16)
                input_desc = []
                if input_val & 0x01:
                    input_desc.append("DIN1")
                if input_val & 0x02:
                    input_desc.append("DIN2")
                if input_val & 0x04:
                    input_desc.append("DIN3")
                input_pin = ", ".join(input_desc) if input_desc else input_pin_hex

                gps_hex = line[72:120]
                try:
                    gps_data = parse_gps_data(gps_hex)
                    gps_show = (
                        f"{gps_data['Time']} "
                        f"[{gps_data['Longitude']:.6f}, {gps_data['Latitude']:.6f}] "
                        f"Speed:{gps_data['GPS Speed']:.1f}"
                    )
                except Exception:
                    gps_show = gps_hex

                row = []
                if self.pulse_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.pulse_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.pulse_detection_input_pin_checkbox.isChecked():
                    row.append(f"{input_pin:<22}")
                if self.pulse_detection_gps_data_checkbox.isChecked():
                    row.append(f"{gps_show:<25}")
                if self.pulse_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                pulse_detection_event_times_1.append("".join(row))

        if pulse_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(pulse_detection_event_times_1) - 1} 个脉冲检测事件")
            self.raw_data_display.setText("\n".join(pulse_detection_event_times_1))
        else:
            self.result_label.setText("未找到脉冲检测事件")
            self.raw_data_display.setText("")

    # 6.25 Profile Download Result
    def process_profile_download_result(self, raw_data_string):
        headers = []
        if self.profile_download_result_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.profile_download_result_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.profile_download_result_iccid_length_checkbox.isChecked():
            headers.append(f"{'ICCID长度':<10}")
        if self.profile_download_result_iccid_checkbox.isChecked():
            headers.append(f"{'ICCID':<24}")
        if self.profile_download_result_result_checkbox.isChecked():
            headers.append(f"{'下载结果':<10}")
        if self.profile_download_result_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        profile_download_result_event_times_1 = ["".join(headers)]

        result_map = {
            "00": "Failed",
            "01": "Successful",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0427":
                if len(line) < 106:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                iccid_len = int(line[70:72], 16)
                iccid_start = 72
                iccid_end = iccid_start + iccid_len * 2
                if iccid_end + 2 > len(line):
                    continue
                iccid = ascii_to_decimal(line[iccid_start:iccid_end]) if iccid_len != 0 else "N/A"
                result_hex = line[iccid_end:iccid_end + 2].upper()
                result = result_map.get(result_hex, result_hex)

                row = []
                if self.profile_download_result_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.profile_download_result_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.profile_download_result_iccid_length_checkbox.isChecked():
                    row.append(f"{iccid_len:<10}")
                if self.profile_download_result_iccid_checkbox.isChecked():
                    row.append(f"{iccid:<24}")
                if self.profile_download_result_result_checkbox.isChecked():
                    row.append(f"{result:<12}")
                if self.profile_download_result_raw_data_checkbox.isChecked():
                    row.append(line)

                profile_download_result_event_times_1.append("".join(row))

        if profile_download_result_event_times_1:
            self.result_label.setText(f"共找到 {len(profile_download_result_event_times_1) - 1} 个Profile下载结果事件")
            self.raw_data_display.setText("\n".join(profile_download_result_event_times_1))
        else:
            self.result_label.setText("未找到Profile下载结果事件")
            self.raw_data_display.setText("")

    # 6.26 BLE Relay Binding Update
    def process_ble_relay_binding_update(self, raw_data_string):
        headers = []
        if self.ble_relay_binding_update_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.ble_relay_binding_update_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.ble_relay_binding_update_binding_state_checkbox.isChecked():
            headers.append(f"{'绑定状态':<10}")
        if self.ble_relay_binding_update_mac_address_checkbox.isChecked():
            headers.append(f"{'BLE中继MAC':<20}")
        if self.ble_relay_binding_update_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        ble_relay_binding_update_event_times_1 = ["".join(headers)]

        binding_state_map = {
            "00": "Not binding",
            "01": "Binding",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0428":
                if len(line) < 84:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                binding_state_hex = line[70:72].upper()
                binding_state = binding_state_map.get(binding_state_hex, binding_state_hex)
                if binding_state_hex == "00":
                    mac_address = "N/A"
                else:
                    mac_hex = line[72:84].upper()
                    mac_address = ":".join(mac_hex[i:i + 2] for i in range(0, len(mac_hex), 2))

                row = []
                if self.ble_relay_binding_update_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.ble_relay_binding_update_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.ble_relay_binding_update_binding_state_checkbox.isChecked():
                    row.append(f"{binding_state:<12}")
                if self.ble_relay_binding_update_mac_address_checkbox.isChecked():
                    row.append(f"{mac_address:<20}")
                if self.ble_relay_binding_update_raw_data_checkbox.isChecked():
                    row.append(line)

                ble_relay_binding_update_event_times_1.append("".join(row))

        if ble_relay_binding_update_event_times_1:
            self.result_label.setText(f"共找到 {len(ble_relay_binding_update_event_times_1) - 1} 个BLE中继绑定事件")
            self.raw_data_display.setText("\n".join(ble_relay_binding_update_event_times_1))
        else:
            self.result_label.setText("未找到BLE中继绑定事件")
            self.raw_data_display.setText("")

    # 6.27 SOS Warning Detection
    def process_sos_warning_detection(self, raw_data_string):
        headers = []
        if self.sos_warning_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.sos_warning_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.sos_warning_detection_event_type_checkbox.isChecked():
            headers.append(f"{'事件类型':<24}")
        if self.sos_warning_detection_input_pin_checkbox.isChecked():
            headers.append(f"{'触发输入':<18}")
        if self.sos_warning_detection_gps_data_checkbox.isChecked():
            headers.append(f"{'GPS位置':<25}")
        if self.sos_warning_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        sos_warning_detection_event_times_1 = ["".join(headers)]

        event_type_map = {
            "00": "DIN low -> high",
            "01": "DIN high -> low",
            "02": "BLE Keyfob",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0429":
                if len(line) < 124:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                event_type_hex = line[70:72].upper()
                event_type = event_type_map.get(event_type_hex, event_type_hex)
                input_hex = line[72:76].upper()
                input_byte0 = int(input_hex[0:2], 16)
                input_byte1 = int(input_hex[2:4], 16)
                input_desc = []
                if input_byte0 & 0x01:
                    input_desc.append("DIN1")
                if input_byte0 & 0x02:
                    input_desc.append("DIN2")
                if input_byte0 & 0x04:
                    input_desc.append("DIN3")
                if input_byte1 & 0x01:
                    input_desc.append("Keyfob")
                input_pin = ", ".join(input_desc) if input_desc else input_hex

                gps_hex = line[76:124]
                try:
                    gps_data = parse_gps_data(gps_hex)
                    gps_show = (
                        f"{gps_data['Time']} "
                        f"[{gps_data['Longitude']:.6f}, {gps_data['Latitude']:.6f}] "
                        f"Speed:{gps_data['GPS Speed']:.1f}"
                    )
                except Exception:
                    gps_show = gps_hex

                row = []
                if self.sos_warning_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.sos_warning_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.sos_warning_detection_event_type_checkbox.isChecked():
                    row.append(f"{event_type:<24}")
                if self.sos_warning_detection_input_pin_checkbox.isChecked():
                    row.append(f"{input_pin:<18}")
                if self.sos_warning_detection_gps_data_checkbox.isChecked():
                    row.append(f"{gps_show:<25}")
                if self.sos_warning_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                sos_warning_detection_event_times_1.append("".join(row))

        if sos_warning_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(sos_warning_detection_event_times_1) - 1} 个SOS告警事件")
            self.raw_data_display.setText("\n".join(sos_warning_detection_event_times_1))
        else:
            self.result_label.setText("未找到SOS告警事件")
            self.raw_data_display.setText("")

    # 6.28 Few Sensor Data
    def process_few_sensor_data(self, raw_data_string):
        headers = []
        if self.few_sensor_data_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.few_sensor_data_klv_data_checkbox.isChecked():
            headers.append(f"{'KLV数据'}")
        if self.few_sensor_data_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        few_sensor_data_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "042A":
                if len(line) < 70:
                    continue
                imei = ascii_to_decimal(line[18:48])
                effective_data_length = int(line[54:58], 16) * 2
                klv_source_data = line[70:58 + effective_data_length]
                klv_data = parse_klv(klv_source_data, separator=StripedTextEdit.CELL_LINE_BREAK)

                row = []
                if self.few_sensor_data_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.few_sensor_data_klv_data_checkbox.isChecked():
                    row.append(klv_data)
                if self.few_sensor_data_raw_data_checkbox.isChecked():
                    row.append(line)

                few_sensor_data_event_times_1.append("".join(row))

        if few_sensor_data_event_times_1:
            self.result_label.setText(f"共找到 {len(few_sensor_data_event_times_1) - 1} 个少量传感器数据事件")
            self.raw_data_display.setText("\n".join(few_sensor_data_event_times_1))
        else:
            self.result_label.setText("未找到少量传感器数据事件")
            self.raw_data_display.setText("")

    # 6.29 Device Collected Data
    def process_device_collected_data(self, raw_data_string):
        headers = []
        if self.device_collected_data_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.device_collected_data_klv_data_checkbox.isChecked():
            headers.append(f"{'KLV数据'}")
        if self.device_collected_data_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        device_collected_data_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "042B":
                if len(line) < 62:
                    continue
                imei = ascii_to_decimal(line[18:48])
                effective_data_length = int(line[54:58], 16) * 2
                klv_source_data = line[62:58 + effective_data_length]
                klv_data = parse_klv(klv_source_data, separator=StripedTextEdit.CELL_LINE_BREAK)

                row = []
                if self.device_collected_data_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.device_collected_data_klv_data_checkbox.isChecked():
                    row.append(klv_data)
                if self.device_collected_data_raw_data_checkbox.isChecked():
                    row.append(line)

                device_collected_data_event_times_1.append("".join(row))

        if device_collected_data_event_times_1:
            self.result_label.setText(f"共找到 {len(device_collected_data_event_times_1) - 1} 个设备采集数据事件")
            self.raw_data_display.setText("\n".join(device_collected_data_event_times_1))
        else:
            self.result_label.setText("未找到设备采集数据事件")
            self.raw_data_display.setText("")

    # 6.30 Flight Mode Detection
    def process_flight_mode_detection(self, raw_data_string):
        headers = []
        if self.flight_mode_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.flight_mode_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.flight_mode_detection_flight_mode_state_checkbox.isChecked():
            headers.append(f"{'飞行模式状态':<16}")
        if self.flight_mode_detection_location_data_checkbox.isChecked():
            headers.append(f"{'Location Data 1'}")
        if self.flight_mode_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        flight_mode_detection_event_times_1 = ["".join(headers)]

        flight_mode_map = {
            "00": "Exit Flight Mode",
            "01": "Enter Flight Mode",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "042C":
                if len(line) < 110:
                    continue
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                flight_mode_hex = line[70:72].upper()
                flight_mode_state = flight_mode_map.get(flight_mode_hex, flight_mode_hex)
                location_data_hex = line[72:110]
                location_data = parse_klv(location_data_hex) if location_data_hex else ""
                if not location_data:
                    location_data = location_data_hex

                row = []
                if self.flight_mode_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.flight_mode_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.flight_mode_detection_flight_mode_state_checkbox.isChecked():
                    row.append(f"{flight_mode_state:<20}")
                if self.flight_mode_detection_location_data_checkbox.isChecked():
                    row.append(f"{location_data:<25}")
                if self.flight_mode_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                flight_mode_detection_event_times_1.append("".join(row))

        if flight_mode_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(flight_mode_detection_event_times_1) - 1} 个飞行模式检测事件")
            self.raw_data_display.setText("\n".join(flight_mode_detection_event_times_1))
        else:
            self.result_label.setText("未找到飞行模式检测事件")
            self.raw_data_display.setText("")

    # 6.99博世碰撞事件
    def process_bosch_crash_data(self, raw_data_string):
        bosch_crash_header_fields = [
            ("bosch_crash_imei_checkbox", "IMEI", 20),
            ("bosch_crash_report_time_checkbox", "触发时间", 19),
            ("bosch_crash_event_time_checkbox", "事件时间", 19),
            ("bosch_crash_crash_index_checkbox", "碰撞指数", 12),
            ("bosch_crash_crash_status_checkbox", "碰撞状态", 12),
            ("bosch_crash_crash_event_counter_checkbox", "事件计数器", 18),
            ("bosch_crash_crash_frame_counter_checkbox", "事件结构", 18),
            ("bosch_crash_error_status_checkbox", "错误状态", 12),
            ("bosch_crash_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(bosch_crash_header_fields, self)
        bosch_crash_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0410":
                imei = ascii_to_decimal(line[18:48])
                report_time = hex_to_beijing_time(line[62:70])
                event_time = hex_to_beijing_time(line[70:78])
                crash_index = int(line[78:80], 16)
                crash_status = line[80:82]
                crash_event_counter = line[82:84]
                crash_frame_counter = line[84:86]
                error_status_hex = line[86:88]
                error_status_map = {
                    "00": "SUCCESS",
                    "01": "SIGNAL",
                    "02": "ERROR",
                }
                print(error_status_hex,"error_status_hex")
                error_status = error_status_map.get(error_status_hex, "N/A")


                bosch_crash_tail_fields = [
                    ("bosch_crash_imei_checkbox", imei, 20),
                    ("bosch_crash_report_time_checkbox", report_time, 23),
                    ("bosch_crash_event_time_checkbox", event_time, 23),
                    ("bosch_crash_crash_index_checkbox", crash_index, 16),
                    ("bosch_crash_crash_status_checkbox", crash_status, 16),
                    ("bosch_crash_crash_event_counter_checkbox", crash_event_counter, 23),
                    ("bosch_crash_crash_frame_counter_checkbox", crash_frame_counter, 22),
                    ("bosch_crash_error_status_checkbox", error_status, 16),
                    ("bosch_crash_raw_data_checkbox", line, 100),
                ]
                row = build_checkbox(bosch_crash_tail_fields, self)
                bosch_crash_event_times_1.append("".join(row))

        if bosch_crash_event_times_1:
            self.result_label.setText(f"共找到 {len(bosch_crash_event_times_1) - 1} 个博世碰撞事件")
            self.raw_data_display.setText("\n".join(bosch_crash_event_times_1))
        else:
            self.result_label.setText("未找到博世碰撞事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第七章：有过痛苦方知众生痛苦，有过牵挂，了无牵挂，若是修佛先修心，一枪风雪一枪冰 —— 望穿
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 7.1 请求升级TCP
    def process_request_mcu_update_package_tcp(self, raw_data_string):
        headers = []
        if self.request_mcu_update_package_tcp_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.request_mcu_update_package_tcp_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.request_mcu_update_package_tcp_file_name_length_checkbox.isChecked():
            headers.append(f"{'长度':<6}")
        if self.request_mcu_update_package_tcp_file_name_checkbox.isChecked():
            headers.append(f"{'文件名':<6}")
        if self.request_mcu_update_package_tcp_staring_position_checkbox.isChecked():
            headers.append(f"{'起始位置':<8}")
        if self.request_mcu_update_package_tcp_request_length_bytes_checkbox.isChecked():
            headers.append(f"{'数据长度':<8}")
        if self.request_mcu_update_package_tcp_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        mcu_update_package_tcp_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "F001":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                file_name_len = int(line[70:72], 16)
                file_name = ascii_to_decimal(line[72:72 + file_name_len * 2]) if file_name_len != 0 else "N/A"
                offset = 72 + file_name_len * 2
                starting_position = (line[offset:offset + 8]).upper()
                offset += 8
                request_length_bytes = int(line[offset:offset + 4], 16)

                row = []
                if self.request_mcu_update_package_tcp_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.request_mcu_update_package_tcp_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.request_mcu_update_package_tcp_file_name_length_checkbox.isChecked():
                    row.append(f"{file_name_len:<8}")
                if self.request_mcu_update_package_tcp_file_name_checkbox.isChecked():
                    row.append(f"{file_name:<9}")
                if self.request_mcu_update_package_tcp_staring_position_checkbox.isChecked():
                    row.append(f"{starting_position:<12}")
                if self.request_mcu_update_package_tcp_request_length_bytes_checkbox.isChecked():
                    row.append(f"{request_length_bytes:<12}")
                if self.request_mcu_update_package_tcp_raw_data_checkbox.isChecked():
                    row.append(line)

                mcu_update_package_tcp_event_times_1.append("".join(row))

        if mcu_update_package_tcp_event_times_1:
            self.result_label.setText(f"共找到 {len(mcu_update_package_tcp_event_times_1) - 1} 个MCU升级包TCP事件")
            self.raw_data_display.setText("\n".join(mcu_update_package_tcp_event_times_1))
        else:
            self.result_label.setText("未找到MCU升级包TCP事件")
            self.raw_data_display.setText("")

    # 7.2 请求AGPS数据
    def process_request_agps_data(self, raw_data_string):
            headers = []
            if self.request_agps_data_imei_checkbox.isChecked():
                headers.append(f"{'IMEI':<20}")
            if self.request_agps_data_time_checkbox.isChecked():
                headers.append(f"{'触发时间':<19}")
            if self.request_agps_data_longitude_checkbox.isChecked():
                headers.append(f"{'经度':<4}")
            if self.request_agps_data_longitude_value_checkbox.isChecked():
                headers.append(f"{'经度值':<11}")
            if self.request_agps_data_latitude_checkbox.isChecked():
                headers.append(f"{'纬度':<4}")
            if self.request_agps_data_latitude_value_checkbox.isChecked():
                headers.append(f"{'纬度值':<11}")
            if self.request_agps_data_ages_service_type_checkbox.isChecked():
                headers.append(f"{'服务器类型':<10}")
            if self.request_agps_data_raw_data_checkbox.isChecked():
                headers.append(f"{'原始数据'}")

            request_agps_data_event_times_1 = ["".join(headers)]

            for line in self._iter_valid_raw_lines(raw_data_string):
                if line[48:50] == "03" and line[58:62].upper() == "F002":
                    imei = ascii_to_decimal(line[18:48])
                    time_str = hex_to_beijing_time(line[62:70])

                    # 3. 解析经度（36-39字节）
                    long_hex = line[70:78]  # 1. 从报文里截取经度的8位十六进制字符串
                    long_val = int(long_hex, 16)  # 2. 转成32位整数（方便位运算）
                    long_dir_bit = (long_val >> 31) & 1  # 3. 取出最高位 → 代表东经/西经
                    long_num = long_val & 0x7FFFFFFF  # 4. 取出后面31位 → 真正的经度数值
                    actual_long = long_num / 100000  # 5. 除以10万 → 得到真实经度度数
                    long_dir = "东经" if long_dir_bit == 0 else "西经"  # 6. 判断方向

                    # 4. 解析纬度（40-43字节）
                    lat_hex = line[78:86]
                    lat_val = int(lat_hex, 16)
                    lat_dir_bit = (lat_val >> 31) & 1
                    lat_num = lat_val & 0x7FFFFFFF
                    actual_lat = lat_num / 100000
                    lat_dir = "南纬" if lat_dir_bit == 0 else "北纬"

                    # 5. 解析 AGPS 服务类型
                    agps_type = line[86:88]
                    agps_name = "U-Blox" if agps_type == "00" else "ZKE" if agps_type == "01" else "未知"

                    row = []
                    if self.request_agps_data_imei_checkbox.isChecked():
                        row.append(f"{imei:<20}")
                    if self.request_agps_data_time_checkbox.isChecked():
                        row.append(f"{time_str:<23}")
                    if self.request_agps_data_longitude_checkbox.isChecked():
                        row.append(f"{long_dir:<6}")
                    if self.request_agps_data_longitude_value_checkbox.isChecked():
                        row.append(f"{actual_long:<14}")
                    if self.request_agps_data_latitude_checkbox.isChecked():
                        row.append(f"{lat_dir:<6}")
                    if self.request_agps_data_latitude_value_checkbox.isChecked():
                        row.append(f"{actual_lat:<14}")
                    if self.request_agps_data_ages_service_type_checkbox.isChecked():
                        row.append(f"{agps_name:<15}")
                    if self.request_agps_data_raw_data_checkbox.isChecked():
                        row.append(line)

                    request_agps_data_event_times_1.append("".join(row))

            if request_agps_data_event_times_1:
                self.result_label.setText(f"共找到 {len(request_agps_data_event_times_1) - 1} 个AGPS请求事件")
                self.raw_data_display.setText("\n".join(request_agps_data_event_times_1))
            else:
                self.result_label.setText("未找到AGPS请求事件")
                self.raw_data_display.setText("")

    # 7.3 升级包验证TCP
    def process_mcu_update_package_verification_tcp(self, raw_data_string):
        headers = []
        if self.mcu_update_package_verification_tcp_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.mcu_update_package_verification_tcp_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.mcu_update_package_verification_tcp_file_name_length_checkbox.isChecked():
            headers.append(f"{'长度':<6}")
        if self.mcu_update_package_verification_tcp_file_name_checkbox.isChecked():
            headers.append(f"{'文件名':<6}")
        if self.mcu_update_package_verification_tcp_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        mcu_update_package_verification_tcp_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "F003":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                file_name_len = int(line[70:72], 16)
                file_name = ascii_to_decimal(line[72:72 + file_name_len * 2]) if file_name_len != 0 else "N/A"

                row = []
                if self.mcu_update_package_verification_tcp_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.mcu_update_package_verification_tcp_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.mcu_update_package_verification_tcp_file_name_length_checkbox.isChecked():
                    row.append(f"{file_name_len:<8}")
                if self.mcu_update_package_verification_tcp_file_name_checkbox.isChecked():
                    row.append(f"{file_name:<9}")
                if self.mcu_update_package_verification_tcp_raw_data_checkbox.isChecked():
                    row.append(line)

                mcu_update_package_verification_tcp_event_times_1.append("".join(row))

        if mcu_update_package_verification_tcp_event_times_1:
            self.result_label.setText(f"共找到 {len(mcu_update_package_verification_tcp_event_times_1) - 1} 个MCU升级包校验TCP事件")
            self.raw_data_display.setText("\n".join(mcu_update_package_verification_tcp_event_times_1))
        else:
            self.result_label.setText("未找到MCU升级包校验TCP事件")
            self.raw_data_display.setText("")

    # 7.4 MCU日志上传
    def process_mcu_log_report(self, raw_data_string):
        headers = []
        if self.mcu_log_report_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.mcu_log_report_log_type_checkbox.isChecked():
            headers.append(f"{'日志类型':<10}")
        if self.mcu_log_report_log_id_checkbox.isChecked():
            headers.append(f"{'日志ID':<10}")
        if self.mcu_log_report_offset_checkbox.isChecked():
            headers.append(f"{'日志偏移':<10}")
        if self.mcu_log_report_logdata_checkbox.isChecked():
            headers.append(f"{'日志数据'}")
        if self.mcu_log_report_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        mcu_log_report_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "F004":
                imei = ascii_to_decimal(line[18:48])
                log_type_hex = line[62:64].upper()
                log_type_map = {
                    "00": "CAN Log",
                    "01": "KEY Msg",
                }
                log_type = log_type_map.get(log_type_hex, "N/A")

                effective_data_length = int(line[54:58], 16)
                effective_data = line[58:58 + effective_data_length * 2]  # 按有效数据长度截取日志内容
                # print(effective_data,"有效数据长度")
                effective_data_len = len(effective_data)

                # 按协议表的字节位置截取（每个字节对应2个Hex字符）
                log_id_hex = line[64:72].upper()  # Log ID: 33-36字节 → 66~74
                offset_hex = line[72:80].upper()  # Offset: 37-40字节 → 74~82
                log_data_hex = line[80:58+effective_data_len].upper()  # Log data: 41-N字节 → 82~结束

                # ===================== 核心逻辑：log_type=00 直接无效 =====================
                if log_id_hex == "00":
                    log_id = "00"
                    offset = "日志无效"
                    log_data_parsed = "日志无效"

                else:
                    # 非00类型：正常解析Log ID和Offset
                    log_id = log_id_hex
                    offset = offset_hex

                    # ===================== 按类型解析Log Data =====================
                    if log_type_hex == "00":
                        # CAN Log 格式：CANID(4字节) + LENGTH(1字节) + DATA(8字节)
                        can_frames = []
                        frame_len = 26  # 4+1+8字节 = 13字节 → 26个Hex字符
                        for i in range(0, len(log_data_hex), frame_len):
                            frame = log_data_hex[i:i + frame_len]
                            if len(frame) < frame_len:
                                continue  # 不完整帧跳过

                            can_id_hex = frame[0:8]  # 4字节 → 8Hex
                            length_hex = frame[8:10]  # 1字节 → 2Hex
                            data_hex = frame[10:26]  # 8字节 → 16Hex

                            can_id = int(can_id_hex, 16)
                            length = int(length_hex, 16)
                            actual_data = data_hex[:length * 2]  # 按实际长度截取

                            can_frames.append(f"ID:{can_id:08X},LEN:{length},DATA:{actual_data}")

                        log_data_parsed = ", ".join(can_frames) if can_frames else "无有效CAN数据"

                    elif log_type_hex == "01":
                        # KEY Message 格式：长度+内容；offset=0时前4字节是文件大小
                        if offset == "00000000":
                            # 首包：前4字节是文件大小
                            if len(log_data_hex) >= 8:
                                file_size_hex = log_data_hex[0:8]
                                file_size = int(file_size_hex, 16)
                                content_hex = log_data_hex[8:]
                                content_len = len(content_hex) // 2
                                try:
                                    content_str = bytes.fromhex(content_hex).decode("utf-8", errors="replace")
                                except:
                                    content_str = content_hex
                                log_data_parsed = f"文件大小:{file_size}字节, 内容长度:{content_len}字节, 内容:\n{content_str}\n{log_data_hex}\n"
                            else:
                                log_data_parsed = "KEY日志数据不完整"
                        else:
                            # 非首包：直接长度+内容
                            data_len = len(log_data_hex) // 2
                            try:
                                content_str = bytes.fromhex(log_data_hex).decode("utf-8", errors="replace")
                            except:
                                content_str = log_data_hex
                            log_data_parsed = f"内容长度:{data_len}字节, 内容:\n{content_str}\n{log_data_hex}\n"

                    else:
                        log_data_parsed = "未知日志类型"

                row = []
                if self.mcu_log_report_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.mcu_log_report_log_type_checkbox.isChecked():
                    row.append(f"{log_type:<14}")
                if self.mcu_log_report_log_id_checkbox.isChecked():
                    row.append(f"{log_id:<12}")
                if self.mcu_log_report_offset_checkbox.isChecked():
                    row.append(f"{offset:<14}")
                if self.mcu_log_report_logdata_checkbox.isChecked():
                    row.append(log_data_parsed)
                if self.mcu_log_report_raw_data_checkbox.isChecked():
                    row.append(line)

                mcu_log_report_event_times_1.append("".join(row))

        if mcu_log_report_event_times_1:
            self.result_label.setText(f"共找到 {len(mcu_log_report_event_times_1) - 1} 个MCU日志上报事件")
            self.raw_data_display.setText("\n".join(mcu_log_report_event_times_1))
        else:
            self.result_label.setText("未找到MCU日志上报事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第八章：翻云起雾藏杀意，横扫千军几万里 —— 鲲鹏
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 8.1 Request MCU update (via TCP)
    def process_request_mcu_update_via_tcp(self, raw_data_string):
        header_fields = [
            ("request_mcu_update_via_tcp_imei_checkbox", "IMEI", 20),
            ("request_mcu_update_via_tcp_frame_type_checkbox", "帧类型", 12),
            ("request_mcu_update_via_tcp_server_address_port_checkbox", "服务器地址端口", 36),
            ("request_mcu_update_via_tcp_file_name_checkbox", "文件名", 32),
            ("request_mcu_update_via_tcp_current_state_checkbox", "当前状态", 70),
            ("request_mcu_update_via_tcp_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        request_mcu_update_event_times_1 = ["".join(headers)]

        frame_type_map = {
            "03": "PUBLISH",
            "04": "PUBACK",
        }
        current_state_map = {
            "00": "Update immediately",
            "01": "In driving now, update later",
            "02": "Reporting data is not completed, waiting for upgrade",
            "03": "The length of the effective is incorrect",
            "04": "CRC is 0, invalid",
            "05": "Upgraded version is consistent with the current version",
            "06": "Update is ongoing - MCU Update task in process",
            "07": "Update is ongoing - Modem Update task in process",
            "08": "The voltage of internal battery is too low",
        }

        def read_length_string(line, offset, limit):
            if offset + 2 > limit:
                return "N/A", offset

            str_len = int(line[offset:offset + 2], 16)
            offset += 2
            if str_len == 0:
                return "N/A", offset

            value_end = offset + str_len * 2
            if value_end > limit:
                return f"长度异常({str_len})", limit

            return ascii_to_decimal(line[offset:value_end]), value_end

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F100":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map.get(frame_type_hex, f"Unknown({frame_type_hex})")
            server_address_port = "N/A"
            file_name = "N/A"
            current_state = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "03":
                offset = 62
                server_address_port, offset = read_length_string(line, offset, payload_end)
                file_name, offset = read_length_string(line, offset, payload_end)
            elif frame_type_hex == "04":
                current_state_hex = line[62:64].upper() if payload_end >= 64 else ""
                current_state = current_state_map.get(current_state_hex, f"Unknown({current_state_hex})")

            tail_fields = [
                ("request_mcu_update_via_tcp_imei_checkbox", imei, 20),
                ("request_mcu_update_via_tcp_frame_type_checkbox", frame_type, 12),
                ("request_mcu_update_via_tcp_server_address_port_checkbox", server_address_port, 36),
                ("request_mcu_update_via_tcp_file_name_checkbox", file_name, 32),
                ("request_mcu_update_via_tcp_current_state_checkbox", current_state, 70),
                ("request_mcu_update_via_tcp_raw_data_checkbox", line, 100),
            ]
            row = build_checkbox(tail_fields, self)
            request_mcu_update_event_times_1.append("".join(row))

        event_count = len(request_mcu_update_event_times_1) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个8.1 MCU升级请求事件"
            if event_count else "未找到8.1 MCU升级请求事件"
        )
        self.raw_data_display.setText("\n".join(request_mcu_update_event_times_1))

    # 8.2章参数下发
    def process_set_parameters(self, raw_data_string):
        headers = []
        if self.set_parameters_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.set_parameters_set_result_checkbox.isChecked():
            headers.append(f"{'设置结果':<50}")
        if self.set_parameters_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        set_parameters_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "04" and line[58:62].upper() == "F102":
                imei = ascii_to_decimal(line[18:48])

                result_strings = f1_02_parse_tlv_status_fields(line)

                row = []
                if self.set_parameters_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.set_parameters_set_result_checkbox.isChecked():
                    # 将多个结果拼接成用逗号分隔的字符串
                    row.append(f"{'; '.join(result_strings):<54}")
                if self.set_parameters_raw_data_checkbox.isChecked():
                    row.append(line)

                set_parameters_event_times_1.append("".join(row))

        if set_parameters_event_times_1:
            self.result_label.setText(f"共找到 {len(set_parameters_event_times_1) - 1} 个参数下发事件")
            self.raw_data_display.setText("\n".join(set_parameters_event_times_1))
        else:
            self.result_label.setText("未找到参数下发事件")
            self.raw_data_display.setText("")

    # 8.3章参数查询
    def process_inquiry_parameters(self, raw_data_string):
        headers = []
        if self.inquiry_parameters_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.inquiry_parameters_inquiry_result_checkbox.isChecked():
            headers.append(f"{'查询结果':<50}")
        if self.inquiry_parameters_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        get_parameters_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            # print(line)
            if line[48:50] == "04" and line[58:62].upper() == "F103":
                imei = ascii_to_decimal(line[18:48])

                result_strings = f1_03_parse_custom_fields(line)

                row = []
                if self.inquiry_parameters_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.inquiry_parameters_inquiry_result_checkbox.isChecked():
                    # 将多个结果拼接成用逗号分隔的字符串
                    row.append(f"{'; '.join(result_strings):<54}")
                if self.inquiry_parameters_raw_data_checkbox.isChecked():
                    row.append(line)

                get_parameters_event_times_1.append("".join(row))

        if get_parameters_event_times_1:
            self.result_label.setText(f"共找到 {len(get_parameters_event_times_1) - 1} 个参数查询事件")
            self.raw_data_display.setText("\n".join(get_parameters_event_times_1))
        else:
            self.result_label.setText("未找到参数查询事件")
            self.raw_data_display.setText("")

    # 8.4 Request FOTA Update (via HTTP/FTP)
    def process_request_fota_update_http_ftp(self, raw_data_string):
        header_fields = [
            ("request_fota_update_http_ftp_imei_checkbox", "IMEI", 20),
            ("request_fota_update_http_ftp_frame_type_checkbox", "帧类型", 12),
            ("request_fota_update_http_ftp_origin_version_checkbox", "原始版本", 24),
            ("request_fota_update_http_ftp_target_version_checkbox", "目标版本", 24),
            ("request_fota_update_http_ftp_fota_type_checkbox", "FOTA类型", 16),
            ("request_fota_update_http_ftp_transfer_protocol_checkbox", "传输协议", 12),
            ("request_fota_update_http_ftp_url_checkbox", "URL", 40),
            ("request_fota_update_http_ftp_update_file_md5_checkbox", "升级文件MD5", 34),
            ("request_fota_update_http_ftp_current_state_checkbox", "当前状态", 70),
            ("request_fota_update_http_ftp_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]

        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}
        fota_type_map = {
            0: "Modem FOTA",
            1: "MCU FOTA",
            2: "BLE FOTA",
            3: "GNSS FOTA",
            4: "Boot FOTA",
            5: "AP FOTA",
            6: "CFG file FOTA",
        }
        transfer_protocol_map = {0: "HTTP", 1: "FTP"}
        current_state_map = {
            "00": "Success",
            "01": "Error",
            "06": "MCU update is ongoing",
            "07": "Modem update is ongoing",
            "08": "BLE update is ongoing",
            "09": "GNSS update is ongoing",
            "0A": "BOOT update is ongoing",
            "0B": "AP update is ongoing",
            "0C": "Internal battery voltage is too low",
            "0D": "CFG update is ongoing",
            "0E": "FOTA business is disabled by webUI",
            "0F": "Main power voltage is too low",
            "10": "Main power was disconnected",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F108":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            origin_version = "N/A"
            target_version = "N/A"
            fota_type = "N/A"
            transfer_protocol = "N/A"
            url = "N/A"
            update_file_md5 = "N/A"
            current_state = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "03":
                offset = 62
                origin_version, offset = read_prefixed_ascii_field(
                    line, offset, payload_end, length_mask=0x3F
                )
                target_version, offset = read_prefixed_ascii_field(
                    line, offset, payload_end, length_mask=0x3F
                )

                if offset + 2 <= payload_end:
                    type_value = int(line[offset:offset + 2], 16)
                    offset += 2
                    fota_type = fota_type_map.get(
                        type_value & 0x07, f"Unknown({type_value & 0x07})"
                    )
                    transfer_protocol = transfer_protocol_map.get(
                        (type_value >> 6) & 0x03,
                        f"Unknown({(type_value >> 6) & 0x03})"
                    )

                url, offset = read_prefixed_ascii_field(line, offset, payload_end)
                if offset + 64 <= payload_end:
                    update_file_md5 = line[offset:offset + 64].upper()
            elif frame_type_hex == "04":
                if payload_end >= 64:
                    current_state_hex = line[62:64].upper()
                    current_state = current_state_map.get(
                        current_state_hex, f"Unknown({current_state_hex})"
                    )

            tail_fields = [
                ("request_fota_update_http_ftp_imei_checkbox", imei, 20),
                ("request_fota_update_http_ftp_frame_type_checkbox", frame_type, 12),
                ("request_fota_update_http_ftp_origin_version_checkbox", origin_version, 24),
                ("request_fota_update_http_ftp_target_version_checkbox", target_version, 24),
                ("request_fota_update_http_ftp_fota_type_checkbox", fota_type, 16),
                ("request_fota_update_http_ftp_transfer_protocol_checkbox", transfer_protocol, 12),
                ("request_fota_update_http_ftp_url_checkbox", url, 40),
                ("request_fota_update_http_ftp_update_file_md5_checkbox", update_file_md5, 34),
                ("request_fota_update_http_ftp_current_state_checkbox", current_state, 70),
                ("request_fota_update_http_ftp_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        self.result_label.setText(
            f"共找到 {len(result_rows) - 1} 个8.4 FOTA升级事件"
            if len(result_rows) > 1 else "未找到8.4 FOTA升级事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.5 Request Device information (for Router)
    def process_request_device_information_router(self, raw_data_string):
        header_fields = [
            ("request_device_information_router_imei_checkbox", "IMEI", 20),
            ("request_device_information_router_frame_type_checkbox", "帧类型", 12),
            ("request_device_information_router_report_time_checkbox", "上报时间", 23),
            ("request_device_information_router_wifi_mac_24g_checkbox", "Wi-Fi MAC(2.4GHz)", 24),
            ("request_device_information_router_wifi_mac_5g_checkbox", "Wi-Fi MAC(5GHz)", 24),
            ("request_device_information_router_modem_version_checkbox", "Modem软件版本", 24),
            ("request_device_information_router_hardware_version_checkbox", "硬件版本", 20),
            ("request_device_information_router_ap_version_checkbox", "AP软件版本", 20),
            ("request_device_information_router_cfg_version_checkbox", "CFG文件版本", 20),
            ("request_device_information_router_rsrp_checkbox", "RSRP", 12),
            ("request_device_information_router_rscp_checkbox", "RSCP", 12),
            ("request_device_information_router_rssi_checkbox", "RSSI", 12),
            ("request_device_information_router_modem_temperature_checkbox", "Modem芯片温度", 16),
            ("request_device_information_router_wan_ipv4_checkbox", "WAN IPv4", 18),
            ("request_device_information_router_wan_ipv6_checkbox", "WAN IPv6", 40),
            ("request_device_information_router_sim_card_checkbox", "当前SIM卡", 16),
            ("request_device_information_router_lan1_status_checkbox", "LAN1状态", 12),
            ("request_device_information_router_lan2_status_checkbox", "LAN2状态", 12),
            ("request_device_information_router_gps_data_checkbox", "GPS数据", 52),
            ("request_device_information_router_ssh_username_checkbox", "SSH用户名", 18),
            ("request_device_information_router_ssh_password_checkbox", "SSH密码", 18),
            ("request_device_information_router_mobile_ipv4_checkbox", "Mobile IPv4", 18),
            ("request_device_information_router_mobile_ipv6_checkbox", "Mobile IPv6", 40),
            ("request_device_information_router_ssh_port_checkbox", "SSH端口", 12),
            ("request_device_information_router_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]
        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}
        sim_card_map = {
            "00": "No SIM",
            "01": "SIM1",
            "02": "SIM2",
            "03": "SIM1 and SIM2",
        }
        insert_map = {"00": "not inserted", "01": "inserted"}

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F109":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            values = {
                "report_time": "N/A",
                "wifi_mac_24g": "N/A",
                "wifi_mac_5g": "N/A",
                "modem_version": "N/A",
                "hardware_version": "N/A",
                "ap_version": "N/A",
                "cfg_version": "N/A",
                "rsrp": "N/A",
                "rscp": "N/A",
                "rssi": "N/A",
                "modem_temperature": "N/A",
                "wan_ipv4": "N/A",
                "wan_ipv6": "N/A",
                "sim_card": "N/A",
                "lan1_status": "N/A",
                "lan2_status": "N/A",
                "gps_data": "N/A",
                "ssh_username": "N/A",
                "ssh_password": "N/A",
                "mobile_ipv4": "N/A",
                "mobile_ipv6": "N/A",
                "ssh_port": "N/A",
            }
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "04":
                offset = 62
                if offset + 8 <= payload_end:
                    values["report_time"] = hex_to_utc_time(line[offset:offset + 8])
                    offset += 8

                values["wifi_mac_24g"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["wifi_mac_5g"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["modem_version"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end, length_mask=0x3F
                )
                values["hardware_version"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end, length_mask=0x3F
                )
                values["ap_version"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end, length_mask=0x3F
                )
                values["cfg_version"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end, length_mask=0x3F
                )

                for key in ("rsrp", "rscp", "rssi"):
                    if offset + 8 <= payload_end:
                        values[key] = decode_float32_hex(line[offset:offset + 8])
                        offset += 8

                if offset + 2 <= payload_end:
                    temperature_hex = line[offset:offset + 2].upper()
                    values["modem_temperature"] = (
                        "N/A" if temperature_hex == "FF" else int(temperature_hex, 16)
                    )
                    offset += 2

                values["wan_ipv4"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["wan_ipv6"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )

                if offset + 2 <= payload_end:
                    sim_hex = line[offset:offset + 2].upper()
                    values["sim_card"] = sim_card_map.get(sim_hex, f"Unknown({sim_hex})")
                    offset += 2
                if offset + 2 <= payload_end:
                    lan1_hex = line[offset:offset + 2].upper()
                    values["lan1_status"] = insert_map.get(lan1_hex, f"Unknown({lan1_hex})")
                    offset += 2
                if offset + 2 <= payload_end:
                    lan2_hex = line[offset:offset + 2].upper()
                    values["lan2_status"] = insert_map.get(lan2_hex, f"Unknown({lan2_hex})")
                    offset += 2

                if offset + 48 <= payload_end:
                    values["gps_data"] = line[offset:offset + 48].upper()
                    offset += 48

                values["ssh_username"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["ssh_password"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["mobile_ipv4"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["mobile_ipv6"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                values["ssh_port"], offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )

            tail_fields = [
                ("request_device_information_router_imei_checkbox", imei, 20),
                ("request_device_information_router_frame_type_checkbox", frame_type, 12),
                ("request_device_information_router_report_time_checkbox", values["report_time"], 23),
                ("request_device_information_router_wifi_mac_24g_checkbox", values["wifi_mac_24g"], 24),
                ("request_device_information_router_wifi_mac_5g_checkbox", values["wifi_mac_5g"], 24),
                ("request_device_information_router_modem_version_checkbox", values["modem_version"], 24),
                ("request_device_information_router_hardware_version_checkbox", values["hardware_version"], 20),
                ("request_device_information_router_ap_version_checkbox", values["ap_version"], 20),
                ("request_device_information_router_cfg_version_checkbox", values["cfg_version"], 20),
                ("request_device_information_router_rsrp_checkbox", values["rsrp"], 12),
                ("request_device_information_router_rscp_checkbox", values["rscp"], 12),
                ("request_device_information_router_rssi_checkbox", values["rssi"], 12),
                ("request_device_information_router_modem_temperature_checkbox", values["modem_temperature"], 16),
                ("request_device_information_router_wan_ipv4_checkbox", values["wan_ipv4"], 18),
                ("request_device_information_router_wan_ipv6_checkbox", values["wan_ipv6"], 40),
                ("request_device_information_router_sim_card_checkbox", values["sim_card"], 16),
                ("request_device_information_router_lan1_status_checkbox", values["lan1_status"], 12),
                ("request_device_information_router_lan2_status_checkbox", values["lan2_status"], 12),
                ("request_device_information_router_gps_data_checkbox", values["gps_data"], 52),
                ("request_device_information_router_ssh_username_checkbox", values["ssh_username"], 18),
                ("request_device_information_router_ssh_password_checkbox", values["ssh_password"], 18),
                ("request_device_information_router_mobile_ipv4_checkbox", values["mobile_ipv4"], 18),
                ("request_device_information_router_mobile_ipv6_checkbox", values["mobile_ipv6"], 40),
                ("request_device_information_router_ssh_port_checkbox", values["ssh_port"], 12),
                ("request_device_information_router_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        self.result_label.setText(
            f"共找到 {len(result_rows) - 1} 个8.5设备信息事件"
            if len(result_rows) > 1 else "未找到8.5设备信息事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.6 Request Device CFG File (for Router)
    def process_request_device_cfg_file_router(self, raw_data_string):
        header_fields = [
            ("request_device_cfg_file_router_imei_checkbox", "IMEI", 20),
            ("request_device_cfg_file_router_frame_type_checkbox", "帧类型", 12),
            ("request_device_cfg_file_router_cfg_file_type_checkbox", "CFG文件类型", 16),
            ("request_device_cfg_file_router_upload_url_checkbox", "上传URL", 40),
            ("request_device_cfg_file_router_report_time_checkbox", "上报时间", 23),
            ("request_device_cfg_file_router_result_checkbox", "结果", 16),
            ("request_device_cfg_file_router_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]
        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}
        cfg_file_type_map = {"00": "Factory CFG", "01": "User CFG"}
        result_map = {"00": "Upload success", "01": "Upload fail"}

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F10A":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            cfg_file_type = "N/A"
            upload_url = "N/A"
            report_time = "N/A"
            result = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "03":
                offset = 62
                if offset + 2 <= payload_end:
                    cfg_type_hex = line[offset:offset + 2].upper()
                    cfg_file_type = cfg_file_type_map.get(
                        cfg_type_hex, f"Unknown({cfg_type_hex})"
                    )
                    offset += 2
                upload_url, offset = read_prefixed_ascii_field(line, offset, payload_end)
            elif frame_type_hex == "04":
                offset = 62
                if offset + 8 <= payload_end:
                    report_time = hex_to_utc_time(line[offset:offset + 8])
                    offset += 8
                if offset + 2 <= payload_end:
                    result_hex = line[offset:offset + 2].upper()
                    result = result_map.get(result_hex, f"Unknown({result_hex})")

            tail_fields = [
                ("request_device_cfg_file_router_imei_checkbox", imei, 20),
                ("request_device_cfg_file_router_frame_type_checkbox", frame_type, 12),
                ("request_device_cfg_file_router_cfg_file_type_checkbox", cfg_file_type, 16),
                ("request_device_cfg_file_router_upload_url_checkbox", upload_url, 40),
                ("request_device_cfg_file_router_report_time_checkbox", report_time, 23),
                ("request_device_cfg_file_router_result_checkbox", result, 16),
                ("request_device_cfg_file_router_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        self.result_label.setText(
            f"共找到 {len(result_rows) - 1} 个8.6设备CFG文件事件"
            if len(result_rows) > 1 else "未找到8.6设备CFG文件事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.7 Request Device Log Snapshot
    def process_request_device_log_snapshot(self, raw_data_string):
        header_fields = [
            ("request_device_log_snapshot_imei_checkbox", "IMEI", 20),
            ("request_device_log_snapshot_frame_type_checkbox", "帧类型", 12),
            ("request_device_log_snapshot_starting_address_checkbox", "起始地址", 12),
            ("request_device_log_snapshot_snapshot_length_checkbox", "日志快照长度", 16),
            ("request_device_log_snapshot_snapshot_data_checkbox", "快照数据", 80),
            ("request_device_log_snapshot_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]
        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F10B":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            starting_address = "N/A"
            snapshot_length = "N/A"
            snapshot_data = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2
            offset = 62

            if frame_type_hex == "03":
                if offset + 8 <= payload_end:
                    starting_address = line[offset:offset + 8].upper()
                    offset += 8
                if offset + 2 <= payload_end:
                    snapshot_length = int(line[offset:offset + 2], 16)
                    offset += 2
            else:
                if offset + 2 <= payload_end:
                    snapshot_length = int(line[offset:offset + 2], 16)
                    offset += 2

            if isinstance(snapshot_length, int):
                data_end = offset + snapshot_length * 2
                if data_end <= payload_end:
                    snapshot_data = line[offset:data_end].upper()
                else:
                    snapshot_data = f"长度异常({snapshot_length})"

            tail_fields = [
                ("request_device_log_snapshot_imei_checkbox", imei, 20),
                ("request_device_log_snapshot_frame_type_checkbox", frame_type, 12),
                ("request_device_log_snapshot_starting_address_checkbox", starting_address, 12),
                ("request_device_log_snapshot_snapshot_length_checkbox", snapshot_length, 16),
                ("request_device_log_snapshot_snapshot_data_checkbox", snapshot_data, 80),
                ("request_device_log_snapshot_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        self.result_label.setText(
            f"共找到 {len(result_rows) - 1} 个8.7设备日志快照事件"
            if len(result_rows) > 1 else "未找到8.7设备日志快照事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.8 白名单响应
    def process_whitelist_management(self, raw_data_string):
        whilelist_management_header_fields = [
            ("whitelist_management_imei_checkbox", "IMEI", 20),
            ("whitelist_management_operation_result_checkbox", "操作结果", 30),
            ("whitelist_management_type_checkbox", "类型", 10),
            ("whitelist_management_num_of_ids_checkbox", "已有ID数量", 10),
            ("whitelist_management_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]
        headers = build_checkbox(whilelist_management_header_fields, self)
        whitelist_management_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "04" and line[58:62].upper() == "F10C":
                imei = ascii_to_decimal(line[18:48])

                operation_result_hex = line[62:64].upper()
                operation_result_map = {
                    "00": "操作失败，原因未知",
                    "01": "操作成功",
                    "02": "操作失败。要写的ID太多",
                }
                id_type_hex = line[64:66].upper()
                id_type_map = {
                    "00": "RFID",
                    "01": "IBUTTON",
                }
                id_type = id_type_map.get(id_type_hex, "N/A")

                num_of_ids = int(line[66:70], 16)

                operation_result = operation_result_map.get(operation_result_hex, "N/A")

                whitelist_management_tail_fields = [
                    ("whitelist_management_imei_checkbox", imei, 20),
                    ("whitelist_management_operation_result_checkbox", operation_result, 30),
                    ("whitelist_management_type_checkbox", id_type, 12),
                    ("whitelist_management_num_of_ids_checkbox", num_of_ids, 14),
                    ("whitelist_management_raw_data_checkbox", line, 100),
                ]
                row = build_checkbox(whitelist_management_tail_fields, self)
                whitelist_management_event_times_1.append("".join(row))

        if whitelist_management_event_times_1:
            self.result_label.setText(f"共找到 {len(whitelist_management_event_times_1) - 1} 个白名单响应事件")
            self.raw_data_display.setText("\n".join(whitelist_management_event_times_1))
        else:
            self.result_label.setText("未找到白名单响应事件")
            self.raw_data_display.setText("")

    # 8.9 白名单查询 IBUTON RFID
    def process_whitelist_query(self, raw_data_string):
        whitelist_query_header_fields = [
            ("whitelist_query_imei_checkbox", "IMEI", 20),
            ("whitelist_query_type_checkbox", "类型", 10),
            ("whitelist_query_length_id_checkbox", "长度ID", 10),
            ("whitelist_query_multi_frame_flag_checkbox", "消息帧数", 10),
            ("whitelist_query_current_response_message_checkbox", "消息索引", 8),
            ("whitelist_query_number_of_ids_checkbox", "ID数量", 10),
            ("whitelist_query_ids_checkbox", "ID列表", 50),
            ("whitelist_query_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]
        headers = build_checkbox(whitelist_query_header_fields, self)
        whitelist_query_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "04" and line[58:62].upper() == "F10D":
                imei = ascii_to_decimal(line[18:48])

                type_hex = line[62:64].upper()
                type_map = {
                    "00": "RFID",
                    "01": "IBUTTON",
                }
                query_type = type_map.get(type_hex, "N/A")

                length_id = int(line[64:66], 16)

                multi_frame_flag = int(line[66:68], 16)

                current_response_message = int(line[68:70], 16)

                number_of_ids = int(line[70:74], 16)

                if number_of_ids == 0:
                    ids_info = "NO DATA"
                elif number_of_ids > 0:
                    # ids_info = line[74:74 + number_of_ids * length_id * 2]
                    start = 74
                    group_len = length_id * 2
                    ids_info = '-'.join(
                        [line[start + i * group_len: start + (i + 1) * group_len] for i in range(number_of_ids)]
                    )
                else:
                    ids_info = "N/A"

                whitelist_query_tail_fields = [
                    ("whitelist_query_imei_checkbox", imei, 20),
                    ("whitelist_query_type_checkbox", query_type, 12),
                    ("whitelist_query_length_id_checkbox", length_id, 12),
                    ("whitelist_query_multi_frame_flag_checkbox", multi_frame_flag, 14),
                    ("whitelist_query_current_response_message_checkbox", current_response_message, 12),
                    ("whitelist_query_number_of_ids_checkbox", number_of_ids, 12),
                    ("whitelist_query_ids_checkbox", ids_info, 52),
                    ("whitelist_query_raw_data_checkbox", line, 100),
                ]
                row = build_checkbox(whitelist_query_tail_fields, self)
                whitelist_query_event_times_1.append("".join(row))

        if whitelist_query_event_times_1:
            self.result_label.setText(f"共找到 {len(whitelist_query_event_times_1) - 1} 个白名单查询事件")
            self.raw_data_display.setText("\n".join(whitelist_query_event_times_1))
        else:
            self.result_label.setText("未找到白名单查询事件")
            self.raw_data_display.setText("")

    # 8.10 Request eSIM profile update
    def process_request_esim_profile_update(self, raw_data_string):
        header_fields = [
            ("request_esim_profile_update_imei_checkbox", "IMEI", 20),
            ("request_esim_profile_update_frame_type_checkbox", "帧类型", 12),
            ("request_esim_profile_update_sim_name_checkbox", "SIM名称", 24),
            ("request_esim_profile_update_iccid_checkbox", "ICCID", 24),
            ("request_esim_profile_update_activation_code_checkbox", "激活码", 52),
            ("request_esim_profile_update_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]
        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F10E":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            sim_name = "N/A"
            iccid = "N/A"
            activation_code = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "03":
                offset = 62
                sim_name, offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                iccid, offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )
                activation_code, offset = read_prefixed_ascii_field(
                    line, offset, payload_end
                )

            tail_fields = [
                ("request_esim_profile_update_imei_checkbox", imei, 20),
                ("request_esim_profile_update_frame_type_checkbox", frame_type, 12),
                ("request_esim_profile_update_sim_name_checkbox", sim_name, 24),
                ("request_esim_profile_update_iccid_checkbox", iccid, 24),
                ("request_esim_profile_update_activation_code_checkbox", activation_code, 52),
                ("request_esim_profile_update_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        event_count = len(result_rows) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个8.10 eSIM配置文件更新事件"
            if event_count else "未找到8.10 eSIM配置文件更新事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.11.2 Management fence device response
    def process_message_fence_response(self, raw_data_string):
        headers = []
        if self.message_fence_device_response_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.message_fence_device_response_operation_result_checkbox.isChecked():
            headers.append(f"{'操作结果':<6}")
        if self.message_fence_device_response_num_checkbox.isChecked():
            headers.append(f"{'围栏个数':<6}")
        if self.message_fence_device_response_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据':<20}")

        process_message_fence_response_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "04" and line[58:62].upper() == "F10F":
                imei = ascii_to_decimal(line[18:48])
                operation_result = line[62:64]
                operation_status = {"00": "失败", "01": "成功"}.get(operation_result, "未知")
                fence_num = int(line[64:66], 16)

                row = []
                if self.message_fence_device_response_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.message_fence_device_response_operation_result_checkbox.isChecked():
                    row.append(f"{operation_status:<8}")
                if self.message_fence_device_response_num_checkbox.isChecked():
                    row.append(f"{fence_num:<10}")
                if self.message_fence_device_response_raw_data_checkbox.isChecked():
                    row.append(line)

                process_message_fence_response_event_times_1.append("".join(row))

        if process_message_fence_response_event_times_1:
            self.result_label.setText(f"共找到 {len(process_message_fence_response_event_times_1) - 1} 个电子围栏响应事件")
            self.raw_data_display.setText("\n".join(process_message_fence_response_event_times_1))
        else:
            self.result_label.setText("未找到电子围栏响应事件")
            self.raw_data_display.setText("")

    # 8.12.2 Query fence device response
    def process_query_fence_to_device(self, raw_data_string):
        headers = []
        if self.query_fence_to_device_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.query_fence_to_device_total_num_checkbox.isChecked():
            headers.append(f"{'围栏总数':<6}")
        if self.query_fence_to_device_start_id_checkbox.isChecked():
            headers.append(f"{'开始ID':<6}")
        if self.query_fence_to_device_message_num_checkbox.isChecked():
            headers.append(f"{'消息数':<5}")
        if self.query_fence_to_device_fence_data_checkbox.isChecked():
            headers.append(f"{'围栏消息':<120}")
        if self.query_fence_to_device_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据':<20}")

        process_query_fence_to_device_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "04" and line[58:62].upper() == "F110":
                imei = ascii_to_decimal(line[18:48])
                operate_num = int(line[62:64], 16)
                start_id = int(line[64:66], 16)
                message_num = int(line[66:68], 16)

                effective_data_length = int(line[54:58], 16)
                effective_data = line[58:58 + effective_data_length * 2]  # 按有效数据长度截取日志内容
                effective_data_len = len(effective_data)
                log_data_hex = line[68:58 + effective_data_len].upper()  # Log data: 41-N字节 → 82~结束
                print(log_data_hex)

                klv_data = log_data_hex
                offset = 0

                while offset + 4 <= len(klv_data):
                    geo_id_hex = klv_data[offset:offset + 2]
                    offset += 2

                    data_len_hex = klv_data[offset:offset + 2]
                    data_len = int(data_len_hex, 16)
                    offset += 2

                    data_end = offset + data_len * 2
                    if data_end > len(klv_data):
                        break

                    data = klv_data[offset:data_end]
                    offset = data_end

                    if len(data) < 10:
                        continue

                    geo_mode_hex = data[0:2]
                    point_num_hex = data[2:4]
                    key_hex = data[4:8]
                    value_len_hex = data[8:10]
                    value_hex = data[10:]

                    geo_id = int(geo_id_hex, 16)
                    geo_mode = {
                        "00": "禁用",
                        "01": "进入",
                        "02": "退出",
                        "03": "进出"
                    }.get(geo_mode_hex.upper(), "未知")

                    point_num = int(point_num_hex, 16)
                    key_dec = int(key_hex, 16)
                    value_len = int(value_len_hex, 16)

                    if point_num == 1:
                        fence_type = "圆形"
                    elif point_num == 2:
                        fence_type = "矩形"
                    elif 3 <= point_num <= 10:
                        fence_type = "多边形"
                    else:
                        fence_type = "未知"

                    gps_info_list = []
                    gps_offset = 0

                    if point_num == 1:
                        # 圆形：经度4字节 + 纬度4字节 + 半径3字节
                        if len(value_hex) >= 22:
                            lon_hex = value_hex[gps_offset:gps_offset + 8]
                            gps_offset += 8

                            lat_hex = value_hex[gps_offset:gps_offset + 8]
                            gps_offset += 8

                            radius_hex = value_hex[gps_offset:gps_offset + 6]

                            lon_raw = int(lon_hex, 16)
                            lat_raw = int(lat_hex, 16)

                            lon_dir_bit = (lon_raw >> 31) & 1
                            lat_dir_bit = (lat_raw >> 31) & 1

                            lon_value = (lon_raw & 0x7FFFFFFF) / 100000
                            lat_value = (lat_raw & 0x7FFFFFFF) / 100000

                            lon_dir = "西经" if lon_dir_bit == 1 else "东经"
                            lat_dir = "北纬" if lat_dir_bit == 1 else "南纬"

                            radius = int(radius_hex, 16)

                            gps_info_list.append(
                                f"经度:{lon_dir}{lon_value:.5f},"
                                f"纬度:{lat_dir}{lat_value:.5f},"
                                f"半径:{radius}"
                            )

                    elif 2 <= point_num <= 10:
                        # 矩形/多边形：每组 经度4字节 + 纬度4字节
                        for i in range(point_num):
                            if gps_offset + 16 > len(value_hex):
                                break

                            lon_hex = value_hex[gps_offset:gps_offset + 8]
                            gps_offset += 8

                            lat_hex = value_hex[gps_offset:gps_offset + 8]
                            gps_offset += 8

                            lon_raw = int(lon_hex, 16)
                            lat_raw = int(lat_hex, 16)

                            lon_dir_bit = (lon_raw >> 31) & 1
                            lat_dir_bit = (lat_raw >> 31) & 1

                            lon_value = (lon_raw & 0x7FFFFFFF) / 100000
                            lat_value = (lat_raw & 0x7FFFFFFF) / 100000

                            lon_dir = "西经" if lon_dir_bit == 1 else "东经"
                            lat_dir = "北纬" if lat_dir_bit == 1 else "南纬"

                            gps_info_list.append(
                                f"点{i + 1}:经度:{lon_dir}{lon_value:.5f},"
                                f"纬度:{lat_dir}{lat_value:.5f}"
                            )

                    fence_data = (
                        f"围栏ID:{geo_id},"
                        f"长度:{data_len},"
                        f"上报方式:{geo_mode},"
                        f"类型:{fence_type},"
                        f"KEY:{key_dec},"
                        f"经纬度数据长度:{value_len},"
                        f"{'；'.join(gps_info_list)}  "
                    )

                    row = []

                    if self.query_fence_to_device_imei_checkbox.isChecked():
                        row.append(f"{imei:<20}")
                    if self.query_fence_to_device_total_num_checkbox.isChecked():
                        row.append(f"{operate_num:<10}")
                    if self.query_fence_to_device_start_id_checkbox.isChecked():
                        row.append(f"{start_id:<8}")
                    if self.query_fence_to_device_message_num_checkbox.isChecked():
                        row.append(f"{message_num:<8}")
                    if self.query_fence_to_device_fence_data_checkbox.isChecked():
                        row.append(f"{fence_data:<120}")
                    if self.query_fence_to_device_raw_data_checkbox.isChecked():
                        row.append(line)

                    process_query_fence_to_device_event_times_1.append("".join(row))

        if len(process_query_fence_to_device_event_times_1) > 1:
            self.result_label.setText(
                f"共找到 {len(process_query_fence_to_device_event_times_1) - 1} 个电子围栏查询事件"
            )
            self.raw_data_display.setText("\n".join(process_query_fence_to_device_event_times_1))
        else:
            self.result_label.setText("未找到电子围栏查询事件")
            self.raw_data_display.setText("\n".join(process_query_fence_to_device_event_times_1))


    # 8.13 Request RAW CAN Frame
    def process_request_raw_can_frame(self, raw_data_string):
        header_fields = [
            ("request_raw_can_frame_imei_checkbox", "IMEI", 20),
            ("request_raw_can_frame_frame_type_checkbox", "帧类型", 12),
            ("request_raw_can_frame_communication_type_checkbox", "CAN通信类型", 20),
            ("request_raw_can_frame_canbus_pins_checkbox", "CANBus Pins", 18),
            ("request_raw_can_frame_request_can_id_checkbox", "请求CAN ID", 18),
            ("request_raw_can_frame_request_can_data_checkbox", "请求CAN数据", 24),
            ("request_raw_can_frame_request_timeout_checkbox", "请求超时(ms)", 16),
            ("request_raw_can_frame_response_can_id_count_checkbox", "响应CAN ID数量", 18),
            ("request_raw_can_frame_response_can_ids_checkbox", "响应CAN ID列表", 60),
            ("request_raw_can_frame_capture_duration_checkbox", "捕获时长(s)", 16),
            ("request_raw_can_frame_result_checkbox", "结果", 16),
            ("request_raw_can_frame_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]

        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}
        communication_type_map = {
            "00": "Request/Response",
            "01": "Listen-only",
        }
        canbus_pins_map = {
            "00": "CANbus 6/14",
            "01": "CANbus 3/11",
        }
        result_map = {"00": "Failed", "01": "Success"}

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F111":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            communication_type = "N/A"
            canbus_pins = "N/A"
            request_can_id = "N/A"
            request_can_data = "N/A"
            request_timeout = "N/A"
            response_can_id_count = "N/A"
            response_can_ids = "N/A"
            capture_duration = "N/A"
            result = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "03":
                offset = 62
                if offset + 2 <= payload_end:
                    communication_type_hex = line[offset:offset + 2].upper()
                    communication_type = communication_type_map.get(
                        communication_type_hex, f"Unknown({communication_type_hex})"
                    )
                    offset += 2
                if offset + 2 <= payload_end:
                    canbus_pins_hex = line[offset:offset + 2].upper()
                    canbus_pins = canbus_pins_map.get(
                        canbus_pins_hex, f"Unknown({canbus_pins_hex})"
                    )
                    offset += 2
                if offset + 8 <= payload_end:
                    request_can_id = line[offset:offset + 8].upper()
                    offset += 8
                if offset + 16 <= payload_end:
                    request_can_data = line[offset:offset + 16].upper()
                    offset += 16
                if offset + 4 <= payload_end:
                    request_timeout = int(line[offset:offset + 4], 16)
                    offset += 4
                if offset + 2 <= payload_end:
                    response_can_id_count = int(line[offset:offset + 2], 16)
                    offset += 2

                    can_ids = []
                    for _ in range(response_can_id_count):
                        if offset + 8 > payload_end:
                            break
                        can_ids.append(line[offset:offset + 8].upper())
                        offset += 8

                    if response_can_id_count == 0:
                        response_can_ids = "No filter"
                    elif len(can_ids) == response_can_id_count:
                        response_can_ids = ", ".join(can_ids)
                    else:
                        response_can_ids = (
                            f"长度异常({response_can_id_count})，已读取：{', '.join(can_ids)}"
                        )

                if offset + 4 <= payload_end:
                    capture_duration = int(line[offset:offset + 4], 16)
            else:
                if 62 + 2 <= payload_end:
                    result_hex = line[62:64].upper()
                    result = result_map.get(result_hex, f"Unknown({result_hex})")

            tail_fields = [
                ("request_raw_can_frame_imei_checkbox", imei, 20),
                ("request_raw_can_frame_frame_type_checkbox", frame_type, 12),
                ("request_raw_can_frame_communication_type_checkbox", communication_type, 20),
                ("request_raw_can_frame_canbus_pins_checkbox", canbus_pins, 18),
                ("request_raw_can_frame_request_can_id_checkbox", request_can_id, 18),
                ("request_raw_can_frame_request_can_data_checkbox", request_can_data, 24),
                ("request_raw_can_frame_request_timeout_checkbox", request_timeout, 16),
                ("request_raw_can_frame_response_can_id_count_checkbox", response_can_id_count, 18),
                ("request_raw_can_frame_response_can_ids_checkbox", response_can_ids, 60),
                ("request_raw_can_frame_capture_duration_checkbox", capture_duration, 16),
                ("request_raw_can_frame_result_checkbox", result, 16),
                ("request_raw_can_frame_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        event_count = len(result_rows) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个8.13 RAW CAN请求事件"
            if event_count else "未找到8.13 RAW CAN请求事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.14 Data Flow Management
    def process_data_flow_management(self, raw_data_string):
        header_fields = [
            ("data_flow_management_imei_checkbox", "IMEI", 20),
            ("data_flow_management_frame_type_checkbox", "帧类型", 12),
            ("data_flow_management_operation_type_checkbox", "操作类型", 30),
            ("data_flow_management_tlv_count_checkbox", "操作TLV数量", 16),
            ("data_flow_management_tlv_keys_checkbox", "TLV Key列表", 60),
            ("data_flow_management_operation_result_checkbox", "操作结果", 24),
            ("data_flow_management_stored_tlv_count_checkbox", "设备存储TLV数量", 22),
            ("data_flow_management_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]

        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}
        operation_type_map = {
            "00": "Add TLVs (reserved)",
            "01": "Overwrite TLV list",
        }
        operation_result_map = {
            "00": "Failed",
            "01": "Success",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F112":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            operation_type = "N/A"
            tlv_count = "N/A"
            tlv_keys = "N/A"
            operation_result = "N/A"
            stored_tlv_count = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "03":
                offset = 62
                if offset + 2 <= payload_end:
                    operation_type_hex = line[offset:offset + 2].upper()
                    operation_type = operation_type_map.get(
                        operation_type_hex, f"Unknown({operation_type_hex})"
                    )
                    offset += 2
                if offset + 4 <= payload_end:
                    tlv_count = int(line[offset:offset + 4], 16)
                    offset += 4

                    keys = []
                    for _ in range(tlv_count):
                        if offset + 4 > payload_end:
                            break
                        key_hex = line[offset:offset + 4].upper()
                        keys.append(f"{key_hex}({int(key_hex, 16)})")
                        offset += 4

                    if tlv_count == 0:
                        tlv_keys = "No TLV"
                    elif len(keys) == tlv_count:
                        tlv_keys = ", ".join(keys)
                    else:
                        tlv_keys = (
                            f"长度异常({tlv_count})，已读取：{', '.join(keys)}"
                        )
            else:
                offset = 62
                if offset + 2 <= payload_end:
                    result_hex = line[offset:offset + 2].upper()
                    operation_result = operation_result_map.get(
                        result_hex, f"Unknown({result_hex})"
                    )
                    offset += 2
                if offset + 4 <= payload_end:
                    stored_tlv_count = int(line[offset:offset + 4], 16)

            tail_fields = [
                ("data_flow_management_imei_checkbox", imei, 20),
                ("data_flow_management_frame_type_checkbox", frame_type, 12),
                ("data_flow_management_operation_type_checkbox", operation_type, 30),
                ("data_flow_management_tlv_count_checkbox", tlv_count, 16),
                ("data_flow_management_tlv_keys_checkbox", tlv_keys, 60),
                ("data_flow_management_operation_result_checkbox", operation_result, 24),
                ("data_flow_management_stored_tlv_count_checkbox", stored_tlv_count, 22),
                ("data_flow_management_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        event_count = len(result_rows) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个8.14数据流管理事件"
            if event_count else "未找到8.14数据流管理事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # 8.15 Data Flow Query
    def process_data_flow_query(self, raw_data_string):
        header_fields = [
            ("data_flow_query_imei_checkbox", "IMEI", 20),
            ("data_flow_query_frame_type_checkbox", "帧类型", 12),
            ("data_flow_query_operation_result_checkbox", "操作结果", 24),
            ("data_flow_query_stored_tlv_count_checkbox", "设备存储TLV数量", 22),
            ("data_flow_query_tlv_keys_checkbox", "TLV Key列表", 60),
            ("data_flow_query_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]

        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}
        operation_result_map = {
            "00": "Failed",
            "01": "Success",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "F113":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            operation_result = "N/A"
            stored_tlv_count = "N/A"
            tlv_keys = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2

            if frame_type_hex == "04":
                offset = 62
                if offset + 2 <= payload_end:
                    result_hex = line[offset:offset + 2].upper()
                    operation_result = operation_result_map.get(
                        result_hex, f"Unknown({result_hex})"
                    )
                    offset += 2
                if offset + 4 <= payload_end:
                    stored_tlv_count = int(line[offset:offset + 4], 16)
                    offset += 4

                    keys = []
                    for _ in range(stored_tlv_count):
                        if offset + 4 > payload_end:
                            break
                        key_hex = line[offset:offset + 4].upper()
                        keys.append(f"{key_hex}({int(key_hex, 16)})")
                        offset += 4

                    if stored_tlv_count == 0:
                        tlv_keys = "No TLV"
                    elif len(keys) == stored_tlv_count:
                        tlv_keys = ", ".join(keys)
                    else:
                        tlv_keys = (
                            f"长度异常({stored_tlv_count})，已读取：{', '.join(keys)}"
                        )

            tail_fields = [
                ("data_flow_query_imei_checkbox", imei, 20),
                ("data_flow_query_frame_type_checkbox", frame_type, 12),
                ("data_flow_query_operation_result_checkbox", operation_result, 24),
                ("data_flow_query_stored_tlv_count_checkbox", stored_tlv_count, 22),
                ("data_flow_query_tlv_keys_checkbox", tlv_keys, 60),
                ("data_flow_query_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        event_count = len(result_rows) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个8.15数据流查询事件"
            if event_count else "未找到8.15数据流查询事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第九章：纵使韩信断了枪，也徒留我一人伤 —— 百鬼夜行
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 9.1 ibutton id
    def process_ibutton_id(self, raw_data_string):
        headers = []
        if self.ibutton_id_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.ibutton_id_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.ibutton_id_ibutton_id_checkbox.isChecked():
            headers.append(f"{'iButton ID':<18}")
        if self.ibutton_id_authentication_status_checkbox.isChecked():
            headers.append(f"{'认证状态':<30}")
        if self.ibutton_id_gps_data_checkbox.isChecked():
            headers.append(f"{'GPS经纬度':<25}")
        if self.ibutton_id_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        ibutton_id_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0601":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                ibutton_id = (line[118:134]).upper()
                authentication_status_hex = line[134:136].upper()
                authentication_status_map = {
                    "00": "00-无需验证",
                    "01": "01-ibutton ID在白名单",
                    "02": "02-ibutton ID不在白名单",
                }
                authentication_status = authentication_status_map.get(authentication_status_hex, "N/A")

                # GPS信息
                ibutton_id_gps_data = parse_gps_data(line[70:118])
                longitude = ibutton_id_gps_data.get('Longitude', '')
                latitude = ibutton_id_gps_data.get('Latitude', '')
                gps_data = f"{longitude},{latitude}"

                row = []
                if self.ibutton_id_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.ibutton_id_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.ibutton_id_ibutton_id_checkbox.isChecked():
                    row.append(f"{ibutton_id:<18}")
                if self.ibutton_id_authentication_status_checkbox.isChecked():
                    row.append(f"{authentication_status:<28}")
                if self.ibutton_id_gps_data_checkbox.isChecked():
                    row.append(f"{gps_data:<25}")
                if self.ibutton_id_raw_data_checkbox.isChecked():
                    row.append(line)

                ibutton_id_event_times_1.append("".join(row))

        if ibutton_id_event_times_1:
            self.result_label.setText(f"共找到 {len(ibutton_id_event_times_1) - 1} 个iButton ID事件")
            self.raw_data_display.setText("\n".join(ibutton_id_event_times_1))
        else:
            self.result_label.setText("未找到iButton ID事件")
            self.raw_data_display.setText("")

    # 9.2 胎压上报
    def process_ble_sensor_data(self, raw_data_string):
        ble_sensor_data_header_fields = [
            ("ble_sensor_data_imei_checkbox", "IMEI", 20),
            ("ble_sensor_data_time_checkbox", "触发时间", 19),
            ("ble_sensor_data_front_left_pressure_checkbox", "左前胎压", 10),
            ("ble_sensor_data_front_right_pressure_checkbox", "右前胎压", 10),
            ("ble_sensor_data_rear_left_pressure_checkbox", "左后胎压", 10),
            ("ble_sensor_data_rear_right_pressure_checkbox", "右后胎压", 10),
            ("ble_sensor_data_front_left_temperature_checkbox", "左前温度", 10),
            ("ble_sensor_data_front_right_temperature_checkbox", "右前温度", 10),
            ("ble_sensor_data_rear_left_temperature_checkbox", "左后温度", 10),
            ("ble_sensor_data_rear_right_temperature_checkbox", "右后温度", 10),
            ("ble_sensor_data_front_left_battery_checkbox", "左前电量", 10),
            ("ble_sensor_data_front_right_battery_checkbox", "右前电量", 10),
            ("ble_sensor_data_rear_left_battery_checkbox", "左后电量", 10),
            ("ble_sensor_data_rear_right_battery_checkbox", "右后电量", 10),
            ("ble_sensor_data_tire_status_of_tire_checkbox", "胎压状态值", 55),
            ("ble_sensor_data_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]

        hearders = build_checkbox(ble_sensor_data_header_fields, self)

        ble_sensor_data_event_times_1 = ["".join(hearders)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0602":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                # 胎压
                front_left_pressure = (
                    line[70:78].upper() if line[70:78].upper() == "FFFFFFFF" else int(line[70:78], 16))
                front_right_pressure = (
                    line[78:86].upper() if line[78:86].upper() == "FFFFFFFF" else int(line[78:86], 16))
                rear_left_pressure = (
                    line[86:94].upper() if line[86:94].upper() == "FFFFFFFF" else int(line[86:94], 16))
                rear_right_pressure = (
                    line[94:102].upper() if line[94:102].upper() == "FFFFFFFF" else int(line[94:102], 16))
                # 温度
                front_left_temperature = line[102:106].upper() if line[102:106].upper() == "FFFF" else round(
                    int(line[102:106], 16) * 0.01 - 60, 2)
                front_right_temperature = line[106:110].upper() if line[106:110].upper() == "FFFF" else round(
                    int(line[106:110], 16) * 0.01 - 60, 2)
                rear_left_temperature = line[110:114].upper() if line[110:114].upper() == "FFFF" else round(
                    int(line[110:114], 16) * 0.01 - 60, 2)
                rear_right_temperature = line[114:118].upper() if line[114:118].upper() == "FFFF" else round(
                    int(line[114:118], 16) * 0.01 - 60, 2)
                # 电量
                front_left_battery = (
                    line[118:120].upper() if line[118:120].upper() == "FF" else int(line[118:120], 16))
                front_right_battery = (
                    line[120:122].upper() if line[120:122].upper() == "FF" else int(line[120:122], 16))
                rear_left_battery = (line[122:124].upper() if line[122:124].upper() == "FF" else int(line[122:124], 16))
                rear_right_battery = (
                    line[124:126].upper() if line[124:126].upper() == "FF" else int(line[124:126], 16))
                # 漏气状态
                tire_status_of_tire_hex = line[126:128]
                tire_status_bin = format(int(tire_status_of_tire_hex, 16), '08b')

                tire_leak_map = {
                    0: "左前轮",
                    1: "右前轮",
                    2: "左后轮",
                    3: "右后轮"
                }
                # 构建漏气信息列表（只显示异常）
                leak_status = [
                    f"{tire_leak_map[bit_index]}: 漏气"
                    for bit_index in range(4)
                    if tire_status_bin[7 - bit_index] == "1"
                ]
                leak_status_str = " | ".join(leak_status) if leak_status else "全部轮胎正常"

                ble_sensor_data_tail_fields = [
                    ("ble_sensor_data_imei_checkbox", imei, 20),
                    ("ble_sensor_data_time_checkbox", time_str, 23),
                    ("ble_sensor_data_front_left_pressure_checkbox", front_left_pressure, 14),
                    ("ble_sensor_data_front_right_pressure_checkbox", front_right_pressure, 14),
                    ("ble_sensor_data_rear_left_pressure_checkbox", rear_left_pressure, 14),
                    ("ble_sensor_data_rear_right_pressure_checkbox", rear_right_pressure, 14),
                    ("ble_sensor_data_front_left_temperature_checkbox", front_left_temperature, 14),
                    ("ble_sensor_data_front_right_temperature_checkbox", front_right_temperature, 14),
                    ("ble_sensor_data_rear_left_temperature_checkbox", rear_left_temperature, 14),
                    ("ble_sensor_data_rear_right_temperature_checkbox", rear_right_temperature, 14),
                    ("ble_sensor_data_front_left_battery_checkbox", front_left_battery, 14),
                    ("ble_sensor_data_front_right_battery_checkbox", front_right_battery, 14),
                    ("ble_sensor_data_rear_left_battery_checkbox", rear_left_battery, 14),
                    ("ble_sensor_data_rear_right_battery_checkbox", rear_right_battery, 14),
                    ("ble_sensor_data_tire_status_of_tire_checkbox", leak_status_str, 60),
                    ("ble_sensor_data_raw_data_checkbox", line, 100)
                ]

                row = build_checkbox(ble_sensor_data_tail_fields, self)

                ble_sensor_data_event_times_1.append("".join(row))

        if ble_sensor_data_event_times_1:
            self.result_label.setText(f"共找到 {len(ble_sensor_data_event_times_1) - 1} 个胎压上报事件")
            self.raw_data_display.setText("\n".join(ble_sensor_data_event_times_1))
        else:
            self.result_label.setText("未找到胎压上报事件")
            self.raw_data_display.setText("")

    # 9.3 温湿度传感器
    def process_rs485_temperature_humidity(self, raw_data_string):
        rs485_temperature_humidity_header_fields = [
            ("rs485_temperature_humidity_imei_checkbox", "IMEI", 20),
            ("rs485_temperature_humidity_num_checkbox", "个数", 6),
            ("rs485_temperature_humidity_time_checkbox", "触发时间", 19),
            ("rs485_temperature_humidity_temperature_checkbox", "温度(℃)", 10),
            ("rs485_temperature_humidity_humidity_checkbox", "湿度(%)", 10),
            ("rs485_temperature_humidity_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]

        headers = build_checkbox(rs485_temperature_humidity_header_fields, self)
        rs485_temperature_humidity_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0603":
                imei = ascii_to_decimal(line[18:48])
                num = int(line[62:64], 16)

                if num == 0:
                    rs485_temperature_humidity_tail_fields = [
                        ("rs485_temperature_humidity_imei_checkbox", imei, 20),
                        ("rs485_temperature_humidity_num_checkbox", num, 8),
                        ("rs485_temperature_humidity_time_checkbox", "N/A", 23),
                        ("rs485_temperature_humidity_temperature_checkbox", "N/A", 13),
                        ("rs485_temperature_humidity_humidity_checkbox", "N/A", 12),
                        ("rs485_temperature_humidity_raw_data_checkbox", "N/A", 100)
                    ]
                    row = build_checkbox(rs485_temperature_humidity_tail_fields, self)
                    rs485_temperature_humidity_event_times_1.append("".join(row))
                else:
                    for i in range(num):
                        start = 64 + i * 8 * 2
                        end = start + 16
                        data_segment = line[start:end]
                        time = hex_to_beijing_time(data_segment[0:8])

                        temperature_hex = data_segment[8:12].upper()
                        temperature = "FFFF" if temperature_hex.upper() == "FFFF" else round(
                            (int(temperature_hex, 16) * 0.1 - 40), 1)

                        humidity_hex = data_segment[12:16].upper()
                        humidity = "FFFF" if humidity_hex.upper() == "FFFF" else round(
                            int(humidity_hex, 16) * 0.1, 1)

                        rs485_temperature_humidity_tail_fields = [
                            ("rs485_temperature_humidity_imei_checkbox", imei, 20),
                            ("rs485_temperature_humidity_num_checkbox", num, 8),
                            ("rs485_temperature_humidity_time_checkbox", time, 23),
                            ("rs485_temperature_humidity_temperature_checkbox", temperature, 13),
                            ("rs485_temperature_humidity_humidity_checkbox", humidity, 12),
                            ("rs485_temperature_humidity_raw_data_checkbox", line, 100)
                        ]

                        row = build_checkbox(rs485_temperature_humidity_tail_fields, self)
                        rs485_temperature_humidity_event_times_1.append("".join(row))

        if rs485_temperature_humidity_event_times_1:
            self.result_label.setText(f"共找到 {len(rs485_temperature_humidity_event_times_1) - 1} 个温湿度传感器事件")
            self.raw_data_display.setText("\n".join(rs485_temperature_humidity_event_times_1))
        else:
            self.result_label.setText("未找到温湿度传感器事件")
            self.raw_data_display.setText("")

    # 9.4 胎压告警
    def process_ble_sensor_warning(self, raw_data_string):
        ble_sensor_warning_header_fields = [
            ("ble_sensor_warning_imei_checkbox", "IMEI", 20),
            ("ble_sensor_warning_time_checkbox", "触发时间", 19),
            ("ble_sensor_warning_warning_type_checkbox", "告警类型", 14),
            ("ble_sensor_warning_warning_position_checkbox", "告警位置", 29),
            ("ble_sensor_warning_warning_pressure_checkbox", "告警胎压", 14),
            ("ble_sensor_warning_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]

        headers = build_checkbox(ble_sensor_warning_header_fields, self)

        ble_sensor_warning_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0604":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                warning_type_hex = line[70:72]
                if warning_type_hex == "00":
                    warning_type = "低压"
                elif warning_type_hex == "01":
                    warning_type = "丢失"
                else:
                    warning_type = "N/A"

                warning_position_hex = line[72:74]
                warning_position_bin = format(int(warning_position_hex, 16), '08b')
                warning_position_map = {
                    0: "左前轮",
                    1: "右前轮",
                    2: "左后轮",
                    3: "右后轮"
                }

                # 收集所有报警位置（bit位为1的）
                warning_positions = [
                    warning_position_map[bit_index]
                    for bit_index in range(4)
                    if warning_position_bin[7 - bit_index] == "1"
                ]
                warning_position_str = " | ".join(warning_positions) if warning_positions else "全部轮胎正常"

                warning_pressure = line[74:82].upper() if line[74:82].upper() == "FFFFFFFF" else int(line[74:82], 16)
                # print(line[74:78])
                # print(warning_pressure)

                ble_sensor_warning_tail_fields = [
                    ("ble_sensor_warning_imei_checkbox", imei, 20),
                    ("ble_sensor_warning_time_checkbox", time_str, 23),
                    ("ble_sensor_warning_warning_type_checkbox", warning_type, 18),
                    ("ble_sensor_warning_warning_position_checkbox", warning_position_str, 32),
                    ("ble_sensor_warning_warning_pressure_checkbox", warning_pressure, 18),
                    ("ble_sensor_warning_raw_data_checkbox", line, 100)
                ]

                row = build_checkbox(ble_sensor_warning_tail_fields, self)

                ble_sensor_warning_event_times_1.append("".join(row))

        if ble_sensor_warning_event_times_1:
            self.result_label.setText(f"共找到 {len(ble_sensor_warning_event_times_1) - 1} 个胎压告警事件")
            self.raw_data_display.setText("\n".join(ble_sensor_warning_event_times_1))
        else:
            self.result_label.setText("未找到胎压告警事件")
            self.raw_data_display.setText("")

    # 9.5 RFID 事件
    def process_rfid_data(self, raw_data_string):
        rfid_header_fields = [
            ("rfid_data_imei_checkbox", "IMEI", 20),
            ("rfid_data_time_checkbox", "触发时间", 19),
            ("rfid_data_rfid_id_checkbox", "RFID_ID", 10),
            ("rfid_data_authentication_status_checkbox", "认证状态", 30),
            ("rfid_data_raw_data_checkbox", "原始数据", 100),  # 无需对齐
        ]

        headers = build_checkbox(rfid_header_fields, self)

        rfid_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] == "03" and line[58:62].upper() == "0605":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                rfid_id = line[118:126].upper()
                authentication_status_hex = line[126:128].upper()
                authentication_status_map = {
                    "00": "00-无需验证",
                    "01": "01-ibutton ID在白名单",
                    "02": "02-ibutton ID不在白名单",
                }
                authentication_status = authentication_status_map.get(authentication_status_hex, "N/A")

                rfid_tail_fields = [
                    ("rfid_data_imei_checkbox", imei, 20),
                    ("rfid_data_time_checkbox", time_str, 23),
                    ("rfid_data_rfid_id_checkbox", rfid_id, 10),
                    ("rfid_data_authentication_status_checkbox", authentication_status, 28),
                    ("rfid_data_raw_data_checkbox", line, 100)
                ]

                row = build_checkbox(rfid_tail_fields, self)

                rfid_event_times_1.append("".join(row))

        if rfid_event_times_1:
            self.result_label.setText(f"共找到 {len(rfid_event_times_1) - 1} 个RFID事件")
            self.raw_data_display.setText("\n".join(rfid_event_times_1))
        else:
            self.result_label.setText("未找到RFID事件")
            self.raw_data_display.setText("")

    # 9.6 BLE温湿度传感器数据
    def process_ble_temperature_humidity_sensor_data(self, raw_data_string):
        header_fields = [
            ("ble_temperature_humidity_sensor_imei_checkbox", "IMEI", 20),
            ("ble_temperature_humidity_sensor_total_report_messages_checkbox", "总上报报文数", 14),
            ("ble_temperature_humidity_sensor_current_report_index_checkbox", "当前上报报文索引", 19),
            ("ble_temperature_humidity_sensor_package_data_num_checkbox", "温湿度数据包数量", 18),
            ("ble_temperature_humidity_sensor_package_data_length_checkbox", "数据包长度", 14),
            ("ble_temperature_humidity_sensor_collection_time_checkbox", "采集时间(北京时间)", 23),
            ("ble_temperature_humidity_sensor_temperature_checkbox", "温度(℃)", 12),
            ("ble_temperature_humidity_sensor_humidity_checkbox", "湿度(%)", 12),
            ("ble_temperature_humidity_sensor_battery_level_checkbox", "BLE THS电池电量(%)", 20),
            ("ble_temperature_humidity_sensor_ble_ths_id_length_checkbox", "BLE THS ID长度", 16),
            ("ble_temperature_humidity_sensor_ble_ths_id_checkbox", "BLE THS ID", 16),
            ("ble_temperature_humidity_sensor_mac_address_checkbox", "传感器MAC地址", 20),
            ("ble_temperature_humidity_sensor_door_state_checkbox", "门状态(ADS100)", 16),
            ("ble_temperature_humidity_sensor_raw_data_checkbox", "原始数据", 100),
        ]
        headers = build_checkbox(header_fields, self)
        result_rows = ["".join(headers)]

        door_state_map = {
            "00": "未关闭",
            "01": "已关闭",
        }

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[48:50] != "03" or line[58:62].upper() != "0606":
                continue

            try:
                effective_data_end = 58 + int(line[54:58], 16) * 2
                total_report_messages = int(line[62:64], 16)
                current_report_index = int(line[64:66], 16)
                package_data_num = int(line[66:68], 16)
            except (IndexError, ValueError):
                continue

            imei = ascii_to_decimal(line[18:48])
            offset = 68
            shared_fields_displayed = False

            def package_content_is_valid(package_content):
                """检查包内容是否至少包含固定字段和按长度计算出的MAC。"""
                if len(package_content) < 32:
                    return False
                try:
                    ths_id_length = int(package_content[18:20], 16)
                except ValueError:
                    return False
                return 20 + ths_id_length * 2 + 12 <= len(package_content)

            def has_package_length_prefix():
                """兼容协议文档中的长度前缀格式，并避免把采集时间误当成长度。"""
                probe_offset = offset
                for _ in range(package_data_num):
                    if probe_offset + 2 > effective_data_end:
                        return False
                    try:
                        declared_length = int(line[probe_offset:probe_offset + 2], 16)
                    except ValueError:
                        return False

                    package_start = probe_offset + 2
                    package_end = package_start + declared_length * 2
                    if declared_length < 16 or package_end > effective_data_end:
                        return False
                    package_content = line[package_start:package_end]
                    if not package_content_is_valid(package_content):
                        return False
                    probe_offset = package_end

                return probe_offset == effective_data_end

            length_prefix_format = has_package_length_prefix()

            for _ in range(package_data_num):
                if length_prefix_format:
                    if offset + 2 > effective_data_end:
                        break

                    try:
                        package_data_length = int(line[offset:offset + 2], 16)
                    except ValueError:
                        break

                    package_start = offset + 2
                    package_end = package_start + package_data_length * 2
                    if package_end > effective_data_end:
                        break
                else:
                    # 部分设备实际上省略了文档中的长度字节，直接连续上报各个数据包。
                    package_start = offset
                    if package_start + 20 > effective_data_end:
                        break
                    try:
                        ths_id_length = int(line[package_start + 18:package_start + 20], 16)
                    except ValueError:
                        break

                    package_end = package_start + (16 + ths_id_length) * 2
                    if package_end > effective_data_end:
                        break

                    # 无长度前缀格式只能通过已定义的门状态TLV判断可选尾部。
                    while package_end + 6 <= effective_data_end and line[package_end:package_end + 4].upper() == "00D3":
                        try:
                            tlv_length = int(line[package_end + 4:package_end + 6], 16)
                        except ValueError:
                            break
                        tlv_end = package_end + 6 + tlv_length * 2
                        if tlv_end > effective_data_end:
                            break
                        package_end = tlv_end

                    package_data_length = (package_end - package_start) // 2

                package = line[package_start:package_end]
                offset = package_end

                # 固定字段（时间、温湿度、电量、ID长度）共10字节，后面还需要6字节MAC。
                if len(package) < 32:
                    continue

                collection_time_hex = package[0:8]
                try:
                    collection_time = hex_to_beijing_time(collection_time_hex)
                except (OverflowError, ValueError):
                    collection_time = collection_time_hex

                temperature_hex = package[8:12].upper()
                temperature = (
                    "FFFF" if temperature_hex == "FFFF" else
                    round(int(temperature_hex, 16) * 0.1 - 40, 1)
                )

                humidity_hex = package[12:16].upper()
                humidity = (
                    "FFFF" if humidity_hex == "FFFF" else
                    round(int(humidity_hex, 16) * 0.1, 1)
                )

                battery_hex = package[16:18].upper()
                battery_level = "FF" if battery_hex == "FF" else int(battery_hex, 16)

                try:
                    ble_ths_id_length = int(package[18:20], 16)
                except ValueError:
                    continue

                ble_ths_id_start = 20
                ble_ths_id_end = ble_ths_id_start + ble_ths_id_length * 2
                mac_end = ble_ths_id_end + 12
                if mac_end > len(package):
                    continue

                ble_ths_id_hex = package[ble_ths_id_start:ble_ths_id_end]
                try:
                    ble_ths_id = bytes.fromhex(ble_ths_id_hex).decode("ascii")
                except (UnicodeDecodeError, ValueError):
                    ble_ths_id = ble_ths_id_hex.upper()
                if not ble_ths_id:
                    ble_ths_id = "N/A"

                mac_hex = package[ble_ths_id_end:mac_end].upper()
                mac_address = ":".join(
                    mac_hex[index:index + 2] for index in range(0, len(mac_hex), 2)
                )

                door_state = "N/A"
                tlv_offset = mac_end
                while tlv_offset + 6 <= len(package):
                    tlv_key = package[tlv_offset:tlv_offset + 4].upper()
                    try:
                        tlv_length = int(package[tlv_offset + 4:tlv_offset + 6], 16)
                    except ValueError:
                        door_state = "TLV长度异常"
                        break

                    tlv_value_start = tlv_offset + 6
                    tlv_value_end = tlv_value_start + tlv_length * 2
                    if tlv_value_end > len(package):
                        door_state = "TLV长度异常"
                        break

                    if tlv_key == "00D3":
                        if tlv_length == 1:
                            door_state_hex = package[tlv_value_start:tlv_value_end].upper()
                            door_state = door_state_map.get(
                                door_state_hex, f"Unknown({door_state_hex})"
                            )
                        else:
                            door_state = f"长度异常({tlv_length})"

                    tlv_offset = tlv_value_end

                shared_field_value = lambda value: value if not shared_fields_displayed else "-"
                tail_fields = [
                    ("ble_temperature_humidity_sensor_imei_checkbox", shared_field_value(imei), 20),
                    ("ble_temperature_humidity_sensor_total_report_messages_checkbox", shared_field_value(total_report_messages), 10),
                    ("ble_temperature_humidity_sensor_current_report_index_checkbox", shared_field_value(current_report_index), 14),
                    ("ble_temperature_humidity_sensor_package_data_num_checkbox", shared_field_value(package_data_num), 12),
                    ("ble_temperature_humidity_sensor_package_data_length_checkbox", package_data_length, 14),
                    ("ble_temperature_humidity_sensor_collection_time_checkbox", collection_time, 23),
                    ("ble_temperature_humidity_sensor_temperature_checkbox", temperature, 12),
                    ("ble_temperature_humidity_sensor_humidity_checkbox", humidity, 12),
                    ("ble_temperature_humidity_sensor_battery_level_checkbox", battery_level, 14),
                    ("ble_temperature_humidity_sensor_ble_ths_id_length_checkbox", ble_ths_id_length, 12),
                    ("ble_temperature_humidity_sensor_ble_ths_id_checkbox", ble_ths_id, 16),
                    ("ble_temperature_humidity_sensor_mac_address_checkbox", mac_address, 20),
                    ("ble_temperature_humidity_sensor_door_state_checkbox", door_state, 14),
                    ("ble_temperature_humidity_sensor_raw_data_checkbox", line, 100),
                ]
                result_rows.append("".join(build_checkbox(tail_fields, self)))
                shared_fields_displayed = True

        event_count = len(result_rows) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个BLE温湿度传感器事件"
            if event_count else "未找到BLE温湿度传感器事件"
        )
        # 即使没有匹配事件，也保留表头，便于确认当前勾选字段。
        self.raw_data_display.setText("\n".join(result_rows))

    # 9.7 ble tag 事件
    def process_ble_tag_data(self, raw_data_string):
        ble_tag_header_fields = [
            ("ble_tag_data_imei_checkbox", "IMEI", 20),
            ("ble_tag_data_tag_num_checkbox", "标签数量", 6),
            ("ble_tag_data_UUID_checkbox", "UUID", 34),
            ("ble_tag_data_major_checkbox", "Major", 8),
            ("ble_tag_data_minor_checkbox", "Minor", 8),
            ("ble_tag_data_RSSI_checkbox", "RSSI", 10),
            ("ble_tag_data_battery_checkbox", "电池电量", 10),
            ("ble_tag_data_anti_tamper_status_checkbox", "防拆状态", 8),
            ("ble_tag_data_asensor_status_checkbox", "传感器状态", 8),
            ("ble_tag_data_raw_data_checkbox", "原始数据", 100),  # 无需对齐

        ]

        headers = build_checkbox(ble_tag_header_fields, self)

        ble_tag_event_times_1 = ["".join(headers)]

        for line in self._iter_valid_raw_lines(raw_data_string):
            print(line,"ble tag 打印")
            if line[48:50] == "03" and line[58:62].upper() == "0607":
                imei = ascii_to_decimal(line[18:48])
                tag_num = int(line[62:64], 16)

                for i in range(tag_num):
                    start = 64 + i * 27 * 2
                    end = start + 54
                    tag_data = line[start:end]
                    uuid = tag_data[0:32].upper()
                    major = int(tag_data[32:36], 16)
                    minor = int(tag_data[36:40], 16)
                    rssi = int(tag_data[40:48], 16)
                    print(tag_data[48:50], "电池打印")
                    battery = round(int(tag_data[48:50], 16) * 0.1, 1)
                    anti_tamper_status_hex = tag_data[50:52].upper()
                    anti_tamper_status_map = {
                        "00": "not tamper",
                        "01": "tamper",
                        "FF": "not support",
                    }
                    anti_tamper_status = anti_tamper_status_map.get(anti_tamper_status_hex, "N/A")
                    asensor_status_hex = tag_data[52:54].upper()
                    asensor_status_map = {
                        "00": "Stationary",
                        "01": "Movement",
                        "FF": "not support"
                    }
                    asensor_status = asensor_status_map.get(asensor_status_hex, "N/A")

                    ble_tag_tail_fields = [
                        ("ble_tag_data_imei_checkbox", imei, 20),
                        ("ble_tag_data_tag_num_checkbox", tag_num, 10),
                        ("ble_tag_data_UUID_checkbox", uuid, 34),
                        ("ble_tag_data_major_checkbox", major, 8),
                        ("ble_tag_data_minor_checkbox", minor, 8),
                        ("ble_tag_data_RSSI_checkbox", rssi, 10),
                        ("ble_tag_data_battery_checkbox", battery, 10),
                        ("ble_tag_data_anti_tamper_status_checkbox", anti_tamper_status, 55),
                        ("ble_tag_data_asensor_status_checkbox", asensor_status, 55),
                        ("ble_tag_data_raw_data_checkbox", line, 100)

                    ]

                    row = build_checkbox(ble_tag_tail_fields, self)

                    ble_tag_event_times_1.append("".join(row))

        if ble_tag_event_times_1:
            self.result_label.setText(f"共找到 {len(ble_tag_event_times_1) - 1} 个BLE Tag事件")
            self.raw_data_display.setText("\n".join(ble_tag_event_times_1))
        else:
            self.result_label.setText("未找到BLE Tag事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    #       第十章：Tachograph
    # ════════════════════════════════════════════════════════

    # 10.1 Data Transparent Transmission
    def process_tachograph_data_transparent_transmission(self, raw_data_string):
        header_fields = [
            ("tachograph_data_transparent_transmission_imei_checkbox", "IMEI", 20),
            ("tachograph_data_transparent_transmission_frame_type_checkbox", "帧类型", 12),
            ("tachograph_data_transparent_transmission_collection_time_checkbox", "采集时间", 23),
            ("tachograph_data_transparent_transmission_data_length_checkbox", "数据长度", 12),
            ("tachograph_data_transparent_transmission_data_checkbox", "数据", 80),
            ("tachograph_data_transparent_transmission_raw_data_checkbox", "原始数据", 100),
        ]
        result_rows = ["".join(build_checkbox(header_fields, self))]
        frame_type_map = {"03": "PUBLISH", "04": "PUBACK"}

        for line in self._iter_valid_raw_lines(raw_data_string):
            if line[58:62].upper() != "0701":
                continue

            frame_type_hex = line[48:50].upper()
            if frame_type_hex not in frame_type_map:
                continue

            imei = ascii_to_decimal(line[18:48])
            frame_type = frame_type_map[frame_type_hex]
            collection_time = "N/A"
            data_length = "N/A"
            data = "N/A"
            payload_end = 58 + int(line[54:58], 16) * 2
            offset = 62

            if frame_type_hex == "04":
                if offset + 8 <= payload_end:
                    collection_time_hex = line[offset:offset + 8]
                    try:
                        collection_time = hex_to_utc_time(collection_time_hex)
                    except (OverflowError, OSError, ValueError):
                        collection_time = f"异常({collection_time_hex})"
                    offset += 8

            if offset + 4 <= payload_end:
                data_length = int(line[offset:offset + 4], 16)
                offset += 4
                data_end = offset + data_length * 2
                if data_end <= payload_end:
                    data = line[offset:data_end].upper() or "N/A"
                else:
                    data = f"长度异常({data_length})"

            tail_fields = [
                ("tachograph_data_transparent_transmission_imei_checkbox", imei, 20),
                ("tachograph_data_transparent_transmission_frame_type_checkbox", frame_type, 12),
                ("tachograph_data_transparent_transmission_collection_time_checkbox", collection_time, 23),
                ("tachograph_data_transparent_transmission_data_length_checkbox", data_length, 12),
                ("tachograph_data_transparent_transmission_data_checkbox", data, 80),
                ("tachograph_data_transparent_transmission_raw_data_checkbox", line, 100),
            ]
            result_rows.append("".join(build_checkbox(tail_fields, self)))

        event_count = len(result_rows) - 1
        self.result_label.setText(
            f"共找到 {event_count} 个10.1 Tachograph透明传输事件"
            if event_count else "未找到10.1 Tachograph透明传输事件"
        )
        self.raw_data_display.setText("\n".join(result_rows))

    # ======================================= 解析代码结束

    def clear_output(self):
        self.raw_data_display.clear()
        self.result_label.setText("Results will appear here.")

    # 以前内容全部是 右侧发送命令栏的窗口  =======================================
    def create_command_panel(self):
        """
        创建右侧参数下发/查询工具栏
        """
        panel = QFrame(self)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setFixedWidth(420)

        panel_layout = QVBoxLayout(panel)

        title = QLabel("参数下发 / 查询工具")
        panel_layout.addWidget(title)

        # IMEI 输入
        self.cmd_imei_input = QLineEdit()
        self.cmd_imei_input.setPlaceholderText("例如：864114070683622,864114070683623")
        panel_layout.addWidget(self.cmd_imei_input)

        # 命令输入区域
        self.cmd_rows_layout = QVBoxLayout()
        panel_layout.addLayout(self.cmd_rows_layout)

        self.cmd_rows = []
        self.add_cmd_row()

        add_cmd_btn = QPushButton("增加命令行")
        add_cmd_btn.clicked.connect(self.add_cmd_row)
        panel_layout.addWidget(add_cmd_btn)

        # 每条命令间隔
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("每条间隔(秒)："))
        self.auto_send_interval = QSpinBox()
        self.auto_send_interval.setRange(1, 3600)
        self.auto_send_interval.setValue(1)
        self.auto_send_interval.setFixedWidth(80)
        interval_layout.addWidget(self.auto_send_interval)
        panel_layout.addLayout(interval_layout)

        # 循环次数
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("循环次数："))
        self.auto_send_loop_count = QSpinBox()
        self.auto_send_loop_count.setRange(1, 9999)
        self.auto_send_loop_count.setValue(1)
        self.auto_send_loop_count.setFixedWidth(80)
        loop_layout.addWidget(self.auto_send_loop_count)
        panel_layout.addLayout(loop_layout)

        # 自动发送按钮
        self.auto_send_btn = QPushButton("开始自动发送")
        self.auto_send_btn.clicked.connect(self.toggle_auto_send_cmd)
        panel_layout.addWidget(self.auto_send_btn)

        # 状态与定时器
        self.cmd_auto_running = False
        self.auto_cmd_queue = []
        self.auto_cmd_index = 0
        self.auto_current_loop = 1
        self.auto_total_loop = 1
        self.auto_imei_list = []
        self.cmd_auto_timer = QTimer(self)
        self.cmd_auto_timer.timeout.connect(self.send_next_cmd)

        # ========== 底部字符串解析区 无按钮，输入实时解析 ==========
        parse_group = QGroupBox("ASCII/Frame解析 [18:48] [48:50] [58:62]")
        parse_layout = QVBoxLayout()

        # 粘贴输入框
        self.parse_input = QTextEdit()
        self.parse_input.setPlaceholderText("粘贴原始字符串，自动解析IMEI、消息类型，publish时显示协议码")
        self.parse_input.setMaximumHeight(80)
        # 内容变化自动执行解析，不用单独函数
        self.parse_input.textChanged.connect(self._auto_parse_str)

        # 解析结果显示
        self.parse_result = QLineEdit()
        self.parse_result.setPlaceholderText("解析结果")
        self.parse_result.setReadOnly(True)

        parse_layout.addWidget(QLabel("原始报文："))
        parse_layout.addWidget(self.parse_input)
        parse_layout.addWidget(QLabel("转换结果："))
        parse_layout.addWidget(self.parse_result)

        parse_group.setLayout(parse_layout)
        panel_layout.addWidget(parse_group)

        panel_layout.addStretch()
        return panel

    def toggle_command_panel(self):
        """
        展开/收起右侧发送工具栏：
        只改变宽度，不改变高度；
        收起后强制恢复展开前宽度。
        """
        current_height = self.height()
        panel_width = 420  # 和 panel.setFixedWidth(420) 保持一致

        # 第一次展开前，记录原始宽度
        if not hasattr(self, "collapsed_window_width"):
            self.collapsed_window_width = self.width()

        if self.command_panel.isVisible():
            # ===== 收起 =====
            self.command_panel.setVisible(False)
            # self.command_panel_toggle_btn.setText("展开\n发送\n工具")
            self.command_panel_toggle_btn.setText("协\n议\n下\n发\n查\n询\n工\n具")

            if not self.isMaximized() and not self.isFullScreen():
                target_width = self.collapsed_window_width

                # 等Qt布局刷新后，再强制改回原始宽度
                QTimer.singleShot(
                    0,
                    lambda: self.resize(target_width, current_height)
                )

        else:
            # ===== 展开 =====
            # 只有在真正收起状态下，才更新原始宽度
            # 防止第二次展开时把1200误记成原始宽度
            if not self.isMaximized() and not self.isFullScreen():
                if not self.command_panel.isVisible():
                    # 这里不要每次覆盖，只在当前宽度明显小于展开宽度时更新
                    if self.width() < self.collapsed_window_width + panel_width:
                        self.collapsed_window_width = self.width()

            self.command_panel.setVisible(True)
            # self.command_panel_toggle_btn.setText("收起\n发送\n工具")
            self.command_panel_toggle_btn.setText("协\n议\n下\n发\n查\n询\n工\n具")

            if not self.isMaximized() and not self.isFullScreen():
                target_width = self.collapsed_window_width + panel_width

                QTimer.singleShot(
                    0,
                    lambda: self.resize(target_width, current_height)
                )

    def add_cmd_row(self):
        """
        增加命令输入行，最多10行
        """
        if len(self.cmd_rows) >= 10:
            self.result_label.setText("最多只能添加10个命令输入框")
            return

        row_layout = QHBoxLayout()

        type_display = QLineEdit()
        type_display.setReadOnly(True)
        type_display.setFixedWidth(55)
        type_display.setPlaceholderText("类型")

        cmd_input = QLineEdit()
        cmd_input.setPlaceholderText("例如：F1030428")

        send_btn = QPushButton("发送")
        send_btn.setFixedWidth(60)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedWidth(60)

        row_layout.addWidget(type_display)
        row_layout.addWidget(cmd_input)
        row_layout.addWidget(send_btn)
        row_layout.addWidget(delete_btn)

        self.cmd_rows_layout.addLayout(row_layout)

        row_obj = {
            "layout": row_layout,
            "type_display": type_display,
            "cmd_input": cmd_input,
            "send_btn": send_btn,
            "delete_btn": delete_btn,
        }

        self.cmd_rows.append(row_obj)

        cmd_input.textChanged.connect(lambda: self.update_cmd_type_display(row_obj))
        send_btn.clicked.connect(lambda: self.send_single_cmd(row_obj))
        delete_btn.clicked.connect(lambda: self.delete_cmd_row(row_obj))

    def delete_cmd_row(self, row_obj):
        """
        删除一行命令输入
        """
        if row_obj not in self.cmd_rows:
            return

        # 至少保留一行
        if len(self.cmd_rows) <= 1:
            row_obj["cmd_input"].clear()
            row_obj["type_display"].clear()
            self.result_label.setText("至少保留一个命令输入框，已清空当前行")
            return

        self.cmd_rows.remove(row_obj)

        layout = row_obj["layout"]

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.cmd_rows_layout.removeItem(layout)

        self.result_label.setText("已删除命令行")

    # def update_cmd_type_display(self, row_obj):
    #     """
    #     根据命令前4位显示 设置 / 查询
    #     """
    #     cmd = row_obj["cmd_input"].text().replace(" ", "").upper()
    #
    #     if cmd.startswith("F102"):
    #         row_obj["type_display"].setText("设置")
    #     elif cmd.startswith("F103"):
    #         row_obj["type_display"].setText("查询")
    #     else:
    #         row_obj["type_display"].setText("")

    def update_cmd_type_display(self, row_obj):
        """
        根据命令前4位显示命令类型
        """
        cmd = row_obj["cmd_input"].text().replace(" ", "").upper()

        if cmd.startswith("F102"):
            row_obj["type_display"].setText("设置")

        elif cmd.startswith("F103"):
            row_obj["type_display"].setText("查询")

        else:
            # 显示前4字节
            row_obj["type_display"].setText(cmd[:4])

    def get_cmd_imei_list(self):
        """
        获取右侧工具栏IMEI列表
        """
        imei_text = self.cmd_imei_input.text().strip()

        if not imei_text:
            return []

        imei_list = []

        for imei in imei_text.split(","):
            imei = imei.strip()
            if imei:
                imei_list.append(imei)

        return imei_list

    def is_valid_cmd(self, cmd):
        """
        判断命令是否合法：
        1. 不能为空
        2. 必须是F102或F103开头
        3. 必须是合法HEX
        """
        cmd = cmd.replace(" ", "").upper()

        if not cmd:
            return False

        # 限制F102 F103
        # if not (cmd.startswith("F102") or cmd.startswith("F103")):
        #     return False

        if len(cmd) % 2 != 0:
            return False

        try:
            bytes.fromhex(cmd)
        except Exception:
            return False

        return True

    def send_single_cmd(self, row_obj):
        """
        单行发送
        """
        imei_list = self.get_cmd_imei_list()
        cmd = row_obj["cmd_input"].text().replace(" ", "").upper()

        if not imei_list:
            self.result_label.setText("发送失败：IMEI为空")
            return

        if not self.is_valid_cmd(cmd):
            self.result_label.setText("发送失败：命令为空、不是F102/F103开头，或不是合法HEX")
            return

        self.send_cmd_to_server(imei_list, cmd)

    def start_auto_send(self):
        """
        开始自动循环发送：
        例如6条命令，循环10次，则总共发送60次。
        每条命令之间间隔 auto_send_interval 秒。
        """
        imei_list = self.get_cmd_imei_list()

        if not imei_list:
            self.result_label.setText("自动发送失败：IMEI为空")
            return

        valid_cmds = []

        for row_obj in self.cmd_rows:
            cmd = row_obj["cmd_input"].text().replace(" ", "").upper()

            if self.is_valid_cmd(cmd):
                valid_cmds.append(cmd)

        if not valid_cmds:
            self.result_label.setText("自动发送失败：没有有效命令")
            return

        self.auto_imei_list = imei_list
        self.auto_cmd_queue = valid_cmds
        self.auto_cmd_index = 0

        self.auto_current_loop = 1
        self.auto_total_loop = self.auto_send_loop_count.value()

        self.cmd_auto_running = True
        self.auto_send_btn.setText("停止自动发送")

        interval_sec = self.auto_send_interval.value()

        self.result_label.setText(
            f"开始自动发送：{len(valid_cmds)}条命令，循环{self.auto_total_loop}次，每条间隔{interval_sec}秒"
        )

        # 立即发送第一条
        self.send_next_cmd()

        # 后续按间隔发送
        self.cmd_auto_timer.start(interval_sec * 1000)

    def send_next_cmd(self):
        """
        每次只发送一条命令。
        一轮发完后，如果还有循环次数，则从第一条重新开始。
        """
        if not self.cmd_auto_running:
            return

        # 当前轮发完
        if self.auto_cmd_index >= len(self.auto_cmd_queue):
            self.auto_current_loop += 1

            # 所有循环结束
            if self.auto_current_loop > self.auto_total_loop:
                self.cmd_auto_timer.stop()
                self.cmd_auto_running = False
                self.auto_send_btn.setText("开始自动发送")
                self.result_label.setText("自动发送完成")
                return

            # 开始下一轮
            self.auto_cmd_index = 0

        cmd = self.auto_cmd_queue[self.auto_cmd_index]

        self.result_label.setText(
            f"自动发送中：第{self.auto_current_loop}/{self.auto_total_loop}轮，"
            f"第{self.auto_cmd_index + 1}/{len(self.auto_cmd_queue)}条 CMD:{cmd}"
        )

        self.send_cmd_to_server(self.auto_imei_list, cmd)

        self.auto_cmd_index += 1

    def send_cmd_to_server(self, imei_list, cmd):
        """
        POST发送命令，并显示服务器返回的 message 信息
        """
        url = "http://10.85.40.3:8088/client/send"

        success_count = 0
        fail_count = 0
        message_list = []

        for imei in imei_list:
            payload = {
                "imei": imei,
                "cmd": cmd
            }

            try:
                response = requests.post(url, json=payload, timeout=5)

                # 默认没有message
                callback_message = ""

                try:
                    resp_json = response.json()
                    callback_message = resp_json.get("message", "")
                    server_code = resp_json.get("code", "")
                    flow_id = ""

                    if isinstance(resp_json.get("data"), dict):
                        flow_id = resp_json.get("data", {}).get("flowId", "")

                except Exception:
                    server_code = ""
                    flow_id = ""
                    callback_message = ""

                if response.status_code == 200:
                    success_count += 1
                    send_status = "HTTP成功"
                else:
                    fail_count += 1
                    send_status = f"HTTP失败({response.status_code})"

                msg = f"IMEI:{imei} {send_status}"

                if server_code != "":
                    msg += f" code:{server_code}"

                if flow_id:
                    msg += f" flowId:{flow_id}"

                if callback_message:
                    msg += f" message:{callback_message}"

                message_list.append(msg)

            except Exception as e:
                fail_count += 1
                message_list.append(f"IMEI:{imei} 请求异常:{e}")

        self.result_label.setText(
            f"CMD:{cmd} 成功:{success_count} 失败:{fail_count} | " + " ; ".join(message_list)
        )

    def toggle_auto_send_cmd(self):
        """
        开始/停止自动发送
        """
        if self.cmd_auto_running:
            self.cmd_auto_timer.stop()
            self.cmd_auto_running = False

            self.auto_cmd_queue = []
            self.auto_cmd_index = 0
            self.auto_current_loop = 1
            self.auto_total_loop = 1
            self.auto_imei_list = []

            self.auto_send_btn.setText("开始自动发送")
            self.result_label.setText("自动发送已停止")
        else:
            self.start_auto_send()

if __name__ == "__main__":
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setWindowIcon(get_app_icon())
    window = DataFetcherApp()
    window.show()
    sys.exit(app.exec_())
