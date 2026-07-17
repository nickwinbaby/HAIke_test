import sys
import re
import pandas as pd
import os

import subprocess
# from PyQt5.QtWidgets import QFileDialog
from datetime import datetime, timezone, timedelta
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QDateTimeEdit, QPushButton,
    QLabel, QTextEdit, QComboBox, QCheckBox, QHBoxLayout, QGroupBox, QFileDialog, QGridLayout
)
from PyQt5.QtCore import QDateTime, QTimer


# ════════════════════════════════════════════════════════
# 1.self.dropdown1.addItems 需要添加一级目录
# 2.if data_type not in 也需要添加一级目录（显示）
# 3.update_dropdown2 二级目录复选菜单
# 4.update_checkbox_visibility 多选框的显示
# 5.def fetch_data(self) 二级目录代码逻辑判断
# 6.需要在 第N章 添加按键
# 7.在数据流二级目录复选框处修改了整个复选框的布局的显示（单排显示几个）***********************************
# 8.尝试在device_info 使用for循环定义按键，简化代码
# 9.尝试在data_flow 使用字典的方式调用 build_checkbox 函数,简化代码
# ════════════════════════════════════════════════════════

# 将十六进制字符串转换为北京时间
def hex_to_beijing_time(hex_str):
    timestamp = int(hex_str, 16)
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')


# 将十六进制字符串转换为十进制
def ascii_to_decimal(ascii_hex):
    return bytes.fromhex(ascii_hex).decode()


# GPS数据解析
def parse_gps_data(hex_string):
    # 将字符串转为字节列表
    bytes_data = bytes.fromhex(hex_string)

    if len(bytes_data) < 23:
        raise ValueError("输入数据不足23字节")

    result = {}

    # 00-03字节 # 这个是一个UNIX 时间戳的方法 转换为北京时间
    time_raw = int.from_bytes(bytes_data[0:4], byteorder='big')
    gps_beijing_time = datetime.utcfromtimestamp(time_raw) + timedelta(hours=8)
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
        "0422": (1, lambda v: {"00": "Disable iButton function ", "01": "Only report iButton ID",
                               "02": "Report iButton ID, and control relay"}.get(v.upper(), "Unknown")),
        "0423": (1, lambda v: {"00": "Disable RFID function ", "01": "Only report RFID",
                               "02": "Report RFID, and control relay"}.get(v.upper(), "Unknown")),
        "0425": (2, lambda v: int(v, 16)),
        "0426": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0428": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "042A": (2, lambda v: int(v, 16)),

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
        "024A": (99, ascii_to_decimal),
        "0254": (99, ascii_to_decimal),
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
                # 读取长度字段（后2位）
                length_hex = payload[offset + 4:offset + 6]

                if len(length_hex) < 2:
                    break  # 防止越界

                data_len = int(length_hex, 16)
                value_hex = payload[offset + 6:offset + 6 + data_len * 2]

                # 执行转换逻辑，比如 ASCII 转字符串
                value = ascii_to_decimal(value_hex)  # 你已定义的函数
                results.append(f"{param}:{value}")

                offset += 4 + 2 + data_len * 2  # param + len + data
            else:
                length = num * 2
                value_hex = payload[offset + 4:offset + 4 + length]
                value = func(value_hex)
                results.append(f"{param}:{value}")

                offset += 4 + length
        else:
            # 不认识的字段，跳出循环
            # print(f"未识别字段: {param = }")
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

        self.setWindowTitle("服务器数据批量解析 - 木林夕 - 250516")
        self.setGeometry(400, 300, 600, 600)

        self.imei_input = QLineEdit(self)
        self.imei_input.setPlaceholderText("Enter IMEI number(s), comma separated")

        self.start_time_input = QDateTimeEdit(self)
        self.start_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_time_input.setDateTime(QDateTime.currentDateTime())

        self.stop_time_input = QDateTimeEdit(self)
        self.stop_time_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.stop_time_input.setDateTime(QDateTime.currentDateTime())

        self.fetch_button = QPushButton("Fetch Data", self)
        self.fetch_button.clicked.connect(self.fetch_data)

        self.clear_button = QPushButton("Clear Output", self)
        self.clear_button.clicked.connect(self.clear_output)

        # 添加导出EXCEL按键
        self.export_button = QPushButton("导出为 Excel", self)
        self.export_button.clicked.connect(self.export_to_excel)

        self.dropdown1 = QComboBox(self)
        self.dropdown1.addItems(["Select Type", "RAW DATA", "Trip data", "Driving behavior", "Location data",
                                 "Vehicle data", "Secure data", "Device state", "Active server request",
                                 "Accessories information"])
        self.dropdown1.currentIndexChanged.connect(self.update_dropdown2)

        self.dropdown2 = QComboBox(self)
        self.dropdown2.addItem("Select Option")
        # 定义一个下拉的可选复选框
        self.dropdown2.currentIndexChanged.connect(self.update_checkbox_visibility)

        self.result_label = QLabel("Results will appear here.", self)
        self.result_label.setWordWrap(True)

        self.raw_data_display = QTextEdit(self)
        self.raw_data_display.setReadOnly(True)

        # 显示字段复选框
        self.checkbox_group = QGroupBox("显示字段")
        # 创建网格布局
        self.checkbox_layout = QGridLayout()

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

        for key, (label, checked) in trip_fields.items():
            var_name = f"trip_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 点熄火专用复选框
        eng_fields = {
            "imei": ("IMEI", True),
            "type": ("协议类型", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in eng_fields.items():
            var_name = f"eng_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 拖车功能专用复选框
        passive_trip_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in passive_trip_fields.items():
            var_name = f"passive_trip_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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

        for key, (label, checked) in sudden_fields.items():
            var_name = f"sudden_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 急转弯专用复选框
        sharp_turn_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "Turn": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in sharp_turn_fields.items():
            var_name = f"sharp_turn_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 怠速专用复选框
        exceed_idle_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in exceed_idle_fields.items():
            var_name = f"exceed_idle_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 疲劳驾驶专用复选框
        driving_tired_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in driving_tired_fields.items():
            var_name = f"driving_tired_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 超速专用复选框
        over_speed_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in over_speed_fields.items():
            var_name = f"over_speed_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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

        for key, (label, checked) in gps_location_data_fields.items():
            var_name = f"gps_location_data_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # LBS 专用复选框
        lbs_location_data_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "num": ("LBS数", True),
            "collection_time": ("采集时间", True),
            "cell": ("小区", True),
            "tac": ("TAC", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in lbs_location_data_fields.items():
            var_name = f"lbs_location_data_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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
        for key, (label, checked) in vin_fields.items():
            var_name = f"vin_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 数据流专用复选框
        dataflow_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "rpm": ("转速", True),
            "speed": ("车速", True),
            "engine_coolant_temperature": ("发动机冷却液温度 - A", True),
            "throttle_position": ("节气门位置 - B", True),
            "engine_duty": ("发动机负荷 - C", True),
            "intake_air_flow": ("进气流量 - D", True),
            "intake_air_temperature": ("进气温度 - E", True),
            "intake_air_pressure": ("进气压力 - F", True),
            "battery_voltage": ("电池电压 - G", True),
            "fuel_level": ("油量 - H", True),
            "distance_dtcs_cleared": ("DTC清除后距离 - I", True),
            "distance_mil": ("故障灯点亮后距离 - J", True),
            "historical_total_mileage": ("历史总里程 - K1", True),
            "historical_total_fuel_consumption": ("历史总油耗 - K2", True),
            "historical_total_driving_time": ("历史总行驶时间 - K3", True),
            "seatbelt_status": ("安全带状态 - L", True),
            "odometer": ("里程表- M", True),
            "average_fuel_consumption": ("平均油耗 - N", True),
            "odometer_unit": ("里程单位 - O", True),
            "soc": ("SOC - P", True),
            "soh": ("SOH - Q", True),
            "battery_pack_current": ("电池电流 - R", True),
            "battery_pack_voltage": ("电池电压 - S", True),
            "battery_pack_charging": ("充电状态 - T", True),
            "remaining_distance": ("剩余里程 - U", True),
            "battery_pack_temperature": ("电池包温度 - V", True),
            "distance_till_next_servicing": ("下次保养里程 - W", True),
            "engine_run_time": ("发动机运行时间 - X", True),
            "fuel_type": ("油品类型 - Y", True),
            "turn_signals_status": ("转向灯状态 - Z", True),
            "raw_data": ("原始数据", False)
        }

        # 每行最多几个复选框
        max_columns = 4

        for index, (key, (label, checked)) in enumerate(dataflow_fields.items()):
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, f"dataflow_{key}_checkbox", checkbox)  # 动态保存为属性

            row = index // max_columns
            col = index % max_columns

            # 添加复选框到布局
            self.checkbox_layout.addWidget(checkbox, row, col)

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

        for key, (label, checked) in dtc_code_fields.items():
            var_name = f"dtc_code_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 低电压专用复选框
        battery_low_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "battery_voltage": ("电压", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in battery_low_fields.items():
            var_name = f"battery_low_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 震动事件专用复选框
        vibration_event_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "vibration_value": ("震动值", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in vibration_event_fields.items():
            var_name = f"vibration_event_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 疑似碰撞专用复选框
        suspected_collision_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "collision_value": ("碰撞值", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in suspected_collision_fields.items():
            var_name = f"suspected_collision_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 拔出告警专用复选框
        unplug_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "unplug_state": ("拔出状态", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in unplug_warning_fields.items():
            var_name = f"unplug_warning_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 干扰检测专用复选框
        jamming_detection_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "jamming_status": ("干扰状态", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in jamming_detection_fields.items():
            var_name = f"jamming_detection_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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
        for key, (label, checked) in sleep_state_fields.items():
            var_name = f"sleep_state_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 唤醒状态专用复选框
        wakeup_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "wakeup_voltage": ("电压", True),
            "wakeup_type": ("唤醒类型", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in wakeup_state_fields.items():
            var_name = f"wakeup_state_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 长时间无法定位专用复选框
        gps_not_fix_fielad = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in gps_not_fix_fielad.items():
            var_name = f"gps_not_fix_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 重启事件专用复选框
        reboot_event_fields = {
            "imei": ("IMEI", True),
            "power_on_time": ("上电时间", True),
            "power_off_time": ("断电时间", True),
            "reboot_reason": ("重启原因", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in reboot_event_fields.items():
            var_name = f"reboot_event_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # MCU升级状态专用复选框
        mcu_upgrade_state_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "upgrade_state": ("升级状态", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in mcu_upgrade_state_fields.items():
            var_name = f"mcu_upgrade_state_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 设备信息专用复选框
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

        for key, (label, checked) in device_info_fields.items():
            var_name = f"device_info_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # sensor_normal事件专用复选框
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

        for key, (label, checked) in sensor_normal_fields.items():
            var_name = f"sensor_normal_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # sensor_event 事件专用复选框
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

        for key, (label, checked) in sensor_event_fields.items():
            var_name = f"sensor_event_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # ════════════════════════════════════════════════════════
        #       第七章：复选框合集
        # ════════════════════════════════════════════════════════

        # ════════════════════════════════════════════════════════
        #       第八章：复选框合集
        # ════════════════════════════════════════════════════════

        # 设置参数专用复选框
        set_parameters_fields = {
            "imei": ("IMEI", True),
            "set_result": ("设置结果", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in set_parameters_fields.items():
            var_name = f"set_parameters_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 参数查询专用复选框
        inquiry_parameters_fields = {
            "imei": ("IMEI", True),
            "inquiry_result": ("查询结果", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in inquiry_parameters_fields.items():
            var_name = f"inquiry_parameters_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # ════════════════════════════════════════════════════════
        #       第九章：复选框合集
        # ════════════════════════════════════════════════════════

        # ibutton 上报
        ibutton_id_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "ibutton_id": ("iButton ID", True),
            "authentication_status": ("身份验证状态", True),
            "gps_data": ("GPS数据", False),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in ibutton_id_fields.items():
            var_name = f"ibutton_id_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 胎压上报
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

        for key, (label, checked) in ble_sensor_data_fields.items():
            var_name = f"ble_sensor_data_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 胎压告警
        ble_sensor_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "warning_type": ("告警类型", True),
            "warning_position": ("告警位置", True),
            "warning_pressure": ("告警胎压", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in ble_sensor_warning_fields.items():
            var_name = f"ble_sensor_warning_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # EXCEL按键
        # 把导出EXCEL 这个按键添加到checkbox 这个布局中
        self.checkbox_layout.addWidget(self.export_button)

        # 把上面这个布局（包含按钮和其他控件）设置为复选框组 self.checkbox_group 的内部布局。
        self.checkbox_group.setLayout(self.checkbox_layout)
        # 设置复选框组的可见性为 False，初始时不显示
        self.checkbox_group.setVisible(False)
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
        self.auto_timer.timeout.connect(self.auto_execute)

        # 时间选择框：Start Time 和 Stop Time 一行
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Start Time:"))
        time_layout.addWidget(self.start_time_input)
        time_layout.addWidget(QLabel("Stop Time:"))
        time_layout.addWidget(self.stop_time_input)

        # 添加 "Real Time" 按钮
        real_time_button = QPushButton("Real Time")
        real_time_button.clicked.connect(self.update_stop_time_to_now)
        time_layout.addWidget(real_time_button)

        # Auto EX 按钮
        self.auto_ex_button = QPushButton("Auto EX")
        self.auto_ex_button.clicked.connect(self.toggle_auto_execution)
        time_layout.addWidget(self.auto_ex_button)

        layout.addLayout(time_layout)

        # 定义按钮点击事件的槽函数
        def update_stop_time_to_current(self):
            self.stop_time_input.setDateTime(QDateTime.currentDateTime())

        # 数据类型选择框：Select Data Type 和 Select Subtype 一行
        data_layout = QHBoxLayout()
        data_layout.addWidget(QLabel("Select Data Type:"))
        data_layout.addWidget(self.dropdown1)
        data_layout.addWidget(QLabel("Select Subtype:"))
        data_layout.addWidget(self.dropdown2)
        layout.addLayout(data_layout)

        # 显示字段复选框
        layout.addWidget(self.checkbox_group)

        # 将导出EXCEL、Fetch 和 Clear 按钮放在同一行
        action_layout = QHBoxLayout()
        # action_layout.addWidget(self.export_button)
        action_layout.addWidget(self.fetch_button)
        action_layout.addWidget(self.clear_button)
        layout.addLayout(action_layout)

        # 显示结果
        layout.addWidget(self.result_label)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.raw_data_display)

        self.setLayout(layout)

    # 更新结束时间代码
    def update_stop_time_to_now(self):
        current_time = QDateTime.currentDateTime()
        self.stop_time_input.setDateTime(current_time)

    # 实现自动更新时间执行获取数据
    def auto_execute(self):
        self.update_stop_time_to_now()
        self.fetch_data()  # 假设你已有 fetch_data 方法

    def toggle_auto_execution(self):
        if self.auto_timer_running:
            self.auto_timer.stop()
            self.auto_ex_button.setText("Auto EX")
            self.auto_timer_running = False
        else:
            self.auto_timer.start()
            self.auto_ex_button.setText("Stop Auto")
            self.auto_timer_running = True

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

    def update_dropdown2(self):
        selected = self.dropdown1.currentText()
        self.dropdown2.clear()
        if selected == "RAW DATA":
            self.dropdown2.addItem("RAW DATA")
        elif selected == "Trip data":
            self.dropdown2.addItems(["trip summary", "Ignition on", "Ignition off", "trip start", "trip end"])
        elif selected == "Driving behavior":
            self.dropdown2.addItems(["Sudden acc", "Sudden dec", "Sharp turn", "Exceed idle", "Driving tired",
                                     "Over speed"])
        elif selected == "Location data":
            self.dropdown2.addItems(["GPS data", "LBS data"])
        elif selected == "Vehicle data":
            self.dropdown2.addItems(["VIN Cold", "Data flow"])
        elif selected == "Secure data":
            self.dropdown2.addItems(["DTC code", "Battery low", "Vibration event", "Suspected collision",
                                     "Unplug warning", "Jamming detection"])
        elif selected == "Device state":
            self.dropdown2.addItems(["Sleep state", "Wakeup state", "GPS not fix", "Reboot event", "Mcu upgrade state",
                                     "Device info", "Sensor normal", "Sensor event"])

        elif selected == "Active server request":
            self.dropdown2.addItems(["Set parameters", "Inquiry parameters"])

        elif selected == "Accessories information":
            self.dropdown2.addItems(["Ibutton id", "Ble sensor data", "Ble sensor warning"])

        else:
            self.dropdown2.addItem("Select Option")

    # 更新复选框的可见性
    def update_checkbox_visibility(self):
        # if self.dropdown1.currentText() == "Trip data":
        #     self.checkbox_group.setVisible(True)
        data_type = self.dropdown1.currentText()
        sub_type = self.dropdown2.currentText()

        self.checkbox_group.setVisible(True)

        # 清除旧的复选框
        # for i in reversed(range(self.checkbox_layout.count())):
        #     widget = self.checkbox_layout.itemAt(i).widget()
        #     if widget:
        #         self.checkbox_layout.removeWidget(widget)
        #         widget.setParent(None)
        while self.checkbox_layout.count():
            item = self.checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

            # # 根据选择添加新的复选框
            # sub_type = self.dropdown2.currentText()
        if data_type == "Trip data":
            if sub_type == "trip summary":
                for cb in [
                    self.trip_imei_checkbox,
                    self.trip_start_time_checkbox,
                    self.trip_end_time_checkbox,
                    self.trip_source_checkbox,
                    self.trip_mileage_checkbox,
                    self.trip_fuel_consumption_checkbox,
                    self.trip_max_speed_checkbox,
                    self.trip_idle_time_checkbox,
                    self.trip_idle_fuel_consumption_checkbox,
                    self.trip_num_of_acceleration_checkbox,
                    self.trip_num_of_deceleration_checkbox,
                    self.trip_num_of_sharp_turn_checkbox,
                    self.trip_histor_total_mil_checkbox,
                    self.trip_histor_total_fuel_checkbox,
                    self.trip_histor_total_driving_time_checkbox,
                    self.trip_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type in ["Ignition on", "Ignition off"]:
                for cb in [
                    self.eng_imei_checkbox,
                    self.eng_type_checkbox,
                    self.eng_time_checkbox,
                    self.eng_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type in ["trip start", "trip end"]:
                for cb in [
                    self.passive_trip_imei_checkbox,
                    self.passive_trip_time_checkbox,
                    self.passive_trip_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Driving behavior":
            if sub_type in ["Sudden acc", "Sudden dec"]:
                for cb in [
                    self.sudden_imei_checkbox,
                    self.sudden_time_checkbox,
                    self.sudden_before_speed_checkbox,
                    self.sudden_after_speed_checkbox,
                    self.sudden_value_checkbox,
                    self.sudden_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Sharp turn":
                for cb in [
                    self.sharp_turn_imei_checkbox,
                    self.sharp_turn_time_checkbox,
                    self.sharp_turn_Turn_checkbox,
                    self.sharp_turn_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Exceed idle":
                for cb in [
                    self.exceed_idle_imei_checkbox,
                    self.exceed_idle_time_checkbox,
                    self.exceed_idle_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Driving tired":
                for cb in [
                    self.driving_tired_imei_checkbox,
                    self.driving_tired_time_checkbox,
                    self.driving_tired_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Over speed":
                for cb in [
                    self.over_speed_imei_checkbox,
                    self.over_speed_time_checkbox,
                    self.over_speed_value_checkbox,
                    self.over_speed_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Location data":
            if sub_type == "GPS data":
                for cb in [
                    self.gps_location_data_imei_checkbox,
                    self.gps_location_data_num_checkbox,
                    self.gps_location_data_time_checkbox,
                    self.gps_location_data_source_checkbox,
                    self.gps_location_data_validity_checkbox,
                    self.gps_location_data_longitude_checkbox,
                    self.gps_location_data_latitude_checkbox,
                    self.gps_location_data_sate_num_checkbox,
                    self.gps_location_data_height_checkbox,
                    self.gps_location_data_longitude_value_checkbox,
                    self.gps_location_data_latitude_value_checkbox,
                    self.gps_location_data_gps_speed_checkbox,
                    self.gps_location_data_heading_checkbox,
                    self.gps_location_data_pdop_checkbox,
                    self.gps_location_data_hdop_checkbox,
                    self.gps_location_data_vdop_checkbox,
                    self.gps_location_data_hacc_checkbox,
                    self.gps_location_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "LBS data":
                for cb in [
                    self.lbs_location_data_imei_checkbox,
                    self.lbs_location_data_time_checkbox,
                    self.lbs_location_data_num_checkbox,
                    self.lbs_location_data_collection_time_checkbox,
                    self.lbs_location_data_cell_checkbox,
                    self.lbs_location_data_tac_checkbox,
                    self.lbs_location_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Vehicle data":
            if sub_type == "VIN Cold":
                for cb in [
                    self.vin_imei_checkbox,
                    self.vin_time_checkbox,
                    self.vin_type_checkbox,
                    self.vin_length_checkbox,
                    self.vin_vin_value_checkbox,
                    self.vin_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Data flow":
                for cb in [
                    self.dataflow_imei_checkbox,
                    self.dataflow_time_checkbox,
                    self.dataflow_rpm_checkbox,
                    self.dataflow_speed_checkbox,
                    self.dataflow_engine_coolant_temperature_checkbox,
                    self.dataflow_throttle_position_checkbox,
                    self.dataflow_engine_duty_checkbox,
                    self.dataflow_intake_air_flow_checkbox,
                    self.dataflow_intake_air_temperature_checkbox,
                    self.dataflow_intake_air_pressure_checkbox,
                    self.dataflow_battery_voltage_checkbox,
                    self.dataflow_fuel_level_checkbox,
                    self.dataflow_distance_dtcs_cleared_checkbox,
                    self.dataflow_distance_mil_checkbox,
                    self.dataflow_historical_total_mileage_checkbox,
                    self.dataflow_historical_total_fuel_consumption_checkbox,
                    self.dataflow_historical_total_driving_time_checkbox,
                    self.dataflow_seatbelt_status_checkbox,
                    self.dataflow_odometer_checkbox,
                    self.dataflow_average_fuel_consumption_checkbox,
                    self.dataflow_odometer_unit_checkbox,
                    self.dataflow_soc_checkbox,
                    self.dataflow_soh_checkbox,
                    self.dataflow_battery_pack_current_checkbox,
                    self.dataflow_battery_pack_voltage_checkbox,
                    self.dataflow_battery_pack_charging_checkbox,
                    self.dataflow_remaining_distance_checkbox,
                    self.dataflow_battery_pack_temperature_checkbox,
                    self.dataflow_distance_till_next_servicing_checkbox,
                    self.dataflow_engine_run_time_checkbox,
                    self.dataflow_fuel_type_checkbox,
                    self.dataflow_turn_signals_status_checkbox,
                    self.dataflow_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Secure data":
            if sub_type == "DTC code":
                for cb in [
                    self.dtc_code_imei_checkbox,
                    self.dtc_code_time_checkbox,
                    self.dtc_code_obd_dtc_num_checkbox,
                    self.dtc_code_obd_dtc_data_checkbox,
                    self.dtc_code_private_code_num_checkbox,
                    self.dtc_code_private_code_data_checkbox,
                    self.dtc_code_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Battery low":
                for cb in [
                    self.battery_low_imei_checkbox,
                    self.battery_low_time_checkbox,
                    self.battery_low_battery_voltage_checkbox,
                    self.battery_low_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Vibration event":
                for cb in [
                    self.vibration_event_imei_checkbox,
                    self.vibration_event_time_checkbox,
                    self.vibration_event_vibration_value_checkbox,
                    self.vibration_event_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Suspected collision":
                for cb in [
                    self.suspected_collision_imei_checkbox,
                    self.suspected_collision_time_checkbox,
                    self.suspected_collision_collision_value_checkbox,
                    self.suspected_collision_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "Unplug warning":
                for cb in [
                    self.unplug_warning_imei_checkbox,
                    self.unplug_warning_time_checkbox,
                    self.unplug_warning_unplug_state_checkbox,
                    self.unplug_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "Jamming detection":
                for cb in [
                    self.jamming_detection_imei_checkbox,
                    self.jamming_detection_time_checkbox,
                    self.jamming_detection_jamming_status_checkbox,
                    self.jamming_detection_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Device state":
            if sub_type == "Sleep state":
                for cb in [
                    self.sleep_state_imei_checkbox,
                    self.sleep_state_time_checkbox,
                    self.sleep_state_sleep_voltage_checkbox,
                    self.sleep_state_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "Wakeup state":
                for cb in [
                    self.wakeup_state_imei_checkbox,
                    self.wakeup_state_time_checkbox,
                    self.wakeup_state_wakeup_voltage_checkbox,
                    self.wakeup_state_wakeup_type_checkbox,
                    self.wakeup_state_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "GPS not fix":
                for cb in [
                    self.gps_not_fix_imei_checkbox,
                    self.gps_not_fix_time_checkbox,
                    self.gps_not_fix_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Reboot event":
                for cb in [
                    self.reboot_event_imei_checkbox,
                    self.reboot_event_power_on_time_checkbox,
                    self.reboot_event_power_off_time_checkbox,
                    self.reboot_event_reboot_reason_checkbox,
                    self.reboot_event_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Mcu upgrade state":
                for cb in [
                    self.mcu_upgrade_state_imei_checkbox,
                    self.mcu_upgrade_state_time_checkbox,
                    self.mcu_upgrade_state_upgrade_state_checkbox,
                    self.mcu_upgrade_state_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Device info":
                for cb in [
                    self.device_info_imei_checkbox,
                    self.device_info_time_checkbox,
                    # self.device_info_length_of_phone_number_checkbox,
                    self.device_info_phone_number_checkbox,
                    # self.device_info_length_of_iccid_checkbox,
                    self.device_info_iccid_checkbox,
                    # self.device_info_length_of_imsi_checkbox,
                    self.device_info_imsi_checkbox,
                    # self.device_info_length_of_wifi_mac_checkbox,
                    self.device_info_wifi_mac_checkbox,
                    # self.device_info_length_of_bt_mac_checkbox,
                    self.device_info_bt_mac_checkbox,
                    # self.device_info_length_of_wifi_mac_5g_checkbox,
                    self.device_info_wifi_mac_5g_checkbox,
                    self.device_info_softerware_ble_version_checkbox,
                    self.device_info_softerware_gnss_version_checkbox,
                    self.device_info_softerware_boot_version_checkbox,
                    self.device_info_softerware_ap_version_checkbox,
                    self.device_info_mcc_checkbox,
                    # self.device_info_length_of_mnc_checkbox,
                    self.device_info_mnc_checkbox,
                    self.device_info_cfg_file_version_checkbox,
                    self.device_info_gl103_workmode_checkbox,
                    self.device_info_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Sensor normal":
                for cb in [
                    self.sensor_normal_imei_checkbox,
                    self.sensor_normal_time_checkbox,
                    self.sensor_normal_time_interval_checkbox,
                    self.sensor_normal_sensor_status_checkbox,
                    self.sensor_normal_number_checkbox,
                    self.sensor_normal_x_axis_checkbox,
                    self.sensor_normal_y_axis_checkbox,
                    self.sensor_normal_z_axis_checkbox,
                    self.sensor_normal_rpm_checkbox,
                    self.sensor_normal_speed_checkbox,
                    self.sensor_normal_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Sensor event":
                for cb in [
                    self.sensor_event_imei_checkbox,
                    self.sensor_event_time_checkbox,
                    self.sensor_event_happen_time_checkbox,
                    self.sensor_event_event_time_checkbox,
                    self.sensor_event_collection_time_checkbox,
                    self.sensor_event_collection_time_ms_checkbox,
                    self.sensor_event_time_interval_checkbox,
                    self.sensor_event_event_type_checkbox,
                    self.sensor_event_sensor_state_checkbox,
                    self.sensor_event_sensor_num_checkbox,
                    self.sensor_event_x_axis_checkbox,
                    self.sensor_event_y_axis_checkbox,
                    self.sensor_event_z_axis_checkbox,
                    self.sensor_event_rpm_checkbox,
                    self.sensor_event_speed_checkbox,
                    self.sensor_event_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Active server request":
            if sub_type == "Set parameters":
                for cb in [
                    self.set_parameters_imei_checkbox,
                    self.set_parameters_set_result_checkbox,
                    self.set_parameters_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Inquiry parameters":
                for cb in [
                    self.inquiry_parameters_imei_checkbox,
                    self.inquiry_parameters_inquiry_result_checkbox,
                    self.inquiry_parameters_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        elif data_type == "Accessories information":
            if sub_type == "Ble sensor data":
                for cb in [
                    self.ble_sensor_data_imei_checkbox,
                    self.ble_sensor_data_time_checkbox,
                    self.ble_sensor_data_front_left_pressure_checkbox,
                    self.ble_sensor_data_front_right_pressure_checkbox,
                    self.ble_sensor_data_rear_left_pressure_checkbox,
                    self.ble_sensor_data_rear_right_pressure_checkbox,
                    self.ble_sensor_data_front_left_temperature_checkbox,
                    self.ble_sensor_data_front_right_temperature_checkbox,
                    self.ble_sensor_data_rear_left_temperature_checkbox,
                    self.ble_sensor_data_rear_right_temperature_checkbox,
                    self.ble_sensor_data_front_left_battery_checkbox,
                    self.ble_sensor_data_front_right_battery_checkbox,
                    self.ble_sensor_data_rear_left_battery_checkbox,
                    self.ble_sensor_data_rear_right_battery_checkbox,
                    self.ble_sensor_data_tire_status_of_tire_checkbox,
                    self.ble_sensor_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Ibutton id":
                for cb in [
                    self.ibutton_id_imei_checkbox,
                    self.ibutton_id_time_checkbox,
                    self.ibutton_id_ibutton_id_checkbox,
                    self.ibutton_id_authentication_status_checkbox,
                    self.ibutton_id_gps_data_checkbox,
                    self.ibutton_id_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "Ble sensor warning":
                for cb in [
                    self.ble_sensor_warning_imei_checkbox,
                    self.ble_sensor_warning_time_checkbox,
                    self.ble_sensor_warning_warning_type_checkbox,
                    self.ble_sensor_warning_warning_position_checkbox,
                    self.ble_sensor_warning_warning_pressure_checkbox,
                    self.ble_sensor_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)





        # 最后加上导出按钮（确保它始终存在）
        self.checkbox_layout.addWidget(self.export_button)

        # else:
        #     self.checkbox_group.setVisible(False)

    def fetch_data(self):
        data_type = self.dropdown1.currentText()
        sub_type = self.dropdown2.currentText()

        if data_type not in ["RAW DATA", "Trip data", "Driving behavior", "Location data", "Vehicle data",
                             "Secure data", "Device state", "Active server request", "Accessories information"]:
            self.result_label.setText("Please select a valid data type.")
            return

        if data_type == "RAW DATA" and sub_type != "RAW DATA":
            self.result_label.setText("Please select RAW DATA in both dropdowns to fetch raw data.")
            return

        imei_num_list = [self.clean_imei(imei.strip()) for imei in self.imei_input.text().split(",")]
        imei_num_list = [imei for imei in imei_num_list if imei]

        start_dt = self.start_time_input.dateTime().toPyDateTime() - timedelta(hours=8)
        stop_dt = self.stop_time_input.dateTime().toPyDateTime() - timedelta(hours=8)

        start_timestamp = int(start_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        stop_timestamp = int(stop_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

        raw_data = self.server_get_data(imei_num_list, start_timestamp, stop_timestamp)

        if data_type == "RAW DATA":
            self.display_raw_data(raw_data)

        elif data_type == "Trip data" and sub_type == "trip summary":
            self.process_trip_summary(raw_data)
        elif data_type == "Trip data" and sub_type == "Ignition on":
            self.process_ignition_on(raw_data)
        elif data_type == "Trip data" and sub_type == "Ignition off":
            self.process_ignition_off(raw_data)
        elif data_type == "Trip data" and sub_type == "trip start":
            self.process_trip_start(raw_data)
        elif data_type == "Trip data" and sub_type == "trip end":
            self.process_trip_end(raw_data)

        elif data_type == "Driving behavior" and sub_type == "Sudden acc":
            self.process_sudden_acc(raw_data)
        elif data_type == "Driving behavior" and sub_type == "Sudden dec":
            self.process_sudden_dec(raw_data)
        elif data_type == "Driving behavior" and sub_type == "Sharp turn":
            self.process_sharp_turn(raw_data)
        elif data_type == "Driving behavior" and sub_type == "Exceed idle":
            self.process_exceed_idle(raw_data)
        elif data_type == "Driving behavior" and sub_type == "Driving tired":
            self.process_driving_tired(raw_data)
        elif data_type == "Driving behavior" and sub_type == "Over speed":
            self.process_over_speed(raw_data)

        elif data_type == "Location data" and sub_type == "GPS data":
            self.process_gps_data_3(raw_data)
        elif data_type == "Location data" and sub_type == "LBS data":
            self.process_lbs_data(raw_data)

        elif data_type == "Vehicle data" and sub_type == "VIN Cold":
            self.process_vin_code(raw_data)
        elif data_type == "Vehicle data" and sub_type == "Data flow":
            self.process_data_flow(raw_data)

        elif data_type == "Secure data" and sub_type == "DTC code":
            self.process_dtc_code(raw_data)
        elif data_type == "Secure data" and sub_type == "Battery low":
            self.process_battery_low(raw_data)
        elif data_type == "Secure data" and sub_type == "Vibration event":
            self.process_vibration_event(raw_data)
        elif data_type == "Secure data" and sub_type == "Suspected collision":
            self.process_suspected_collision(raw_data)
        elif data_type == "Secure data" and sub_type == "Unplug warning":
            self.process_unplug_warning(raw_data)
        elif data_type == "Secure data" and sub_type == "Jamming detection":
            self.process_jamming_detection(raw_data)

        elif data_type == "Device state" and sub_type == "Sleep state":
            self.process_sleep_state(raw_data)
        elif data_type == "Device state" and sub_type == "Wakeup state":
            self.process_wakeup_state(raw_data)
        elif data_type == "Device state" and sub_type == "GPS not fix":
            self.process_gps_not_fix(raw_data)
        elif data_type == "Device state" and sub_type == "Reboot event":
            self.process_reboot_event(raw_data)
        elif data_type == "Device state" and sub_type == "Mcu upgrade state":
            self.process_mcu_upgrade_state(raw_data)
        elif data_type == "Device state" and sub_type == "Device info":
            self.process_device_info(raw_data)
        elif data_type == "Device state" and sub_type == "Sensor normal":
            self.process_sensor_normal(raw_data)
        elif data_type == "Device state" and sub_type == "Sensor event":
            self.process_sensor_event(raw_data)

        elif data_type == "Active server request" and sub_type == "Set parameters":
            self.process_set_parameters(raw_data)
        elif data_type == "Active server request" and sub_type == "Inquiry parameters":
            self.process_inquiry_parameters(raw_data)

        elif data_type == "Accessories information" and sub_type == "Ibutton id":
            self.process_ibutton_id(raw_data)
        elif data_type == "Accessories information" and sub_type == "Ble sensor data":
            self.process_ble_sensor_data(raw_data)
        elif data_type == "Accessories information" and sub_type == "Ble sensor warning":
            self.process_ble_sensor_warning(raw_data)

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
                        batch = response.json()
                        lines = [entry["rawDataString"] for entry in batch]
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

    def display_raw_data(self, data):
        self.result_label.setText(f"Total raw lines: {len(data)}")
        self.raw_data_display.setText("\n".join(data[:1000]))

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第一章：长相思兮长相忆，短相思兮无穷极 —— 相思
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 行程总结
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
        for line in raw_data_string:
            if line[48:50] == "03" and line[58:62] == "0000":
                imei = ascii_to_decimal(line[18:48])
                ignition_on_time_str = hex_to_beijing_time(line[62:70])
                # gps_location_when_ignition_on = line[70:118]  # GPS位置内容暂时忽略
                ignition_off_time_str = hex_to_beijing_time(line[118:126])
                # gps_location_when_ignition_off = line[126:174] # GPS位置内容暂时忽略

                # 取值先切片，输出16进制，然后转换为10进制，再转换为二进制
                driving_distance_bin = bin(int(line[174:180], 16))[2:]
                source = driving_distance_bin[0]
                mileage = int(driving_distance_bin[-23:], 2)

                statistics_source = "OBD" if source == "0" else "GPS"
                trip_distance = mileage

                trip_fuel_consumption = int(line[180:186], 16)
                max_speed = int(line[186:190], 16)
                idle_time = int(line[190:194], 16)
                idle_fuel_consumption = int(line[194:198], 16)
                num_of_acceleration = int(line[198:200], 16)
                num_of_deceleration = int(line[200:202], 16)
                num_of_sharp_turn = int(line[202:204], 16)
                histor_total_mil = int(line[204:212], 16)
                histor_total_fuel = int(line[212:220], 16)
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

    # 点火事件
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

        for line in raw_data_string:
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

    # 熄火事件
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

        for line in raw_data_string:
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

    # 拖车开始
    def process_trip_start(self, raw_data_string):
        headers = []
        if self.passive_trip_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.passive_trip_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<23}")
        if self.passive_trip_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        trip_start_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
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

    # 拖车结束
    def process_trip_end(self, raw_data_string):
        headers = []
        if self.passive_trip_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.passive_trip_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<23}")
        if self.passive_trip_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        trip_end_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
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

    # 急加速事件
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

        for line in raw_data_string:
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

    # 急减速事件
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

        for line in raw_data_string:
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

    # 急转弯事件
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

        for line in raw_data_string:
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

    # 怠速事件
    def process_exceed_idle(self, raw_data_string):
        headers = []
        if self.exceed_idle_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.exceed_idle_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.exceed_idle_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        exceed_idle_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
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

    # 疲劳驾驶事件
    def process_driving_tired(self, raw_data_string):
        headers = []
        if self.driving_tired_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.driving_tired_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.driving_tired_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        driving_tired_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
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

    # 超速事件
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

        for line in raw_data_string:
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

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第三章：眼见为虚，心听则实 —— 盲龙
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

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

        for line in raw_data_string:
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

    # lbs事件
    def process_lbs_data(self, raw_data_string):
        headers = []
        if self.lbs_location_data_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.lbs_location_data_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<18}")
        if self.lbs_location_data_num_checkbox.isChecked():
            headers.append(f"{'LBS数':<7}")
        if self.lbs_location_data_collection_time_checkbox.isChecked():
            headers.append(f"{'采集时间':<18}")
        if self.lbs_location_data_cell_checkbox.isChecked():
            headers.append(f"{'小区':<9}")
        if self.lbs_location_data_tac_checkbox.isChecked():
            headers.append(f"{'TAC':<7}")
        if self.lbs_location_data_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        lbs_location_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
            if line[48:50] == "03" and line[58:62] == "0201":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                lbs_num = int(line[70:72], 16)
                collections_time = hex_to_beijing_time(line[72:80])
                cell_id = line[80:88]
                tac = line[88:96]

                row = []
                if self.lbs_location_data_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.lbs_location_data_time_checkbox.isChecked():
                    row.append(f"{time_str:<22}")
                if self.lbs_location_data_num_checkbox.isChecked():
                    row.append(f"{lbs_num:<8}")
                if self.lbs_location_data_collection_time_checkbox.isChecked():
                    row.append(f"{collections_time:<22}")
                if self.lbs_location_data_cell_checkbox.isChecked():
                    row.append(f"{cell_id:<11}")
                if self.lbs_location_data_tac_checkbox.isChecked():
                    row.append(f"{tac:<9}")
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

    # VIN码事件
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

        for line in raw_data_string:
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

    # 数据流事件
    def process_data_flow(self, raw_data_string):
        dataflow_header_fields = [
            ("dataflow_imei_checkbox", "IMEI", 20),
            ("dataflow_time_checkbox", "触发时间", 19),
            ("dataflow_rpm_checkbox", "转速", 5),
            ("dataflow_speed_checkbox", "车速", 5),
            ("dataflow_engine_coolant_temperature_checkbox", "A", 7),
            ("dataflow_throttle_position_checkbox", "B", 7),
            ("dataflow_engine_duty_checkbox", "C", 7),
            ("dataflow_intake_air_flow_checkbox", "D", 7),
            ("dataflow_intake_air_temperature_checkbox", "E", 7),
            ("dataflow_intake_air_pressure_checkbox", "F", 7),
            ("dataflow_battery_voltage_checkbox", "G", 7),
            ("dataflow_fuel_level_checkbox", "H", 7),
            ("dataflow_distance_dtcs_cleared_checkbox", "I", 7),
            ("dataflow_distance_mil_checkbox", "J", 7),
            ("dataflow_historical_total_mileage_checkbox", "K1", 13),
            ("dataflow_historical_total_fuel_consumption_checkbox", "K2", 13),
            ("dataflow_historical_total_driving_time_checkbox", "K3", 13),
            ("dataflow_seatbelt_status_checkbox", "L", 7),
            ("dataflow_odometer_checkbox", "M", 13),
            ("dataflow_average_fuel_consumption_checkbox", "N", 13),
            ("dataflow_odometer_unit_checkbox", "O", 7),
            ("dataflow_soc_checkbox", "P", 7),
            ("dataflow_soh_checkbox", "Q", 7),
            ("dataflow_battery_pack_current_checkbox", "R", 7),
            ("dataflow_battery_pack_voltage_checkbox", "S", 7),
            ("dataflow_battery_pack_charging_checkbox", "T", 5),
            ("dataflow_remaining_distance_checkbox", "U", 7),
            ("dataflow_battery_pack_temperature_checkbox", "V", 7),
            ("dataflow_distance_till_next_servicing_checkbox", "W", 7),
            ("dataflow_engine_run_time_checkbox", "X", 13),
            ("dataflow_fuel_type_checkbox", "Y", 5),
            ("dataflow_turn_signals_status_checkbox", "Z", 5),
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

        for line in raw_data_string:
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

                seatbelt_int = int(line[192:194], 16)  # 安全带状态
                seatbelt_bin = format(seatbelt_int, '08b')
                seatbelt_bits_0_to_3 = seatbelt_bin[-4:]
                seatbelt_status = str(seatbelt_bits_0_to_3)

                odometer = "FFFFFFFF" if line[194:202].upper() == "FFFFFFFF" else int(line[194:202], 16)  # 里程表读数
                average_fuel_consumption = "FFFFFFFF" if line[202:210].upper() == "FFFFFFFF" else int(line[202:210],
                                                                                                      16)  # 平均油耗
                odometer_unit_hex = line[210:212]
                if odometer_unit_hex == "00":
                    odometer_unit = "KM"
                elif odometer_unit_hex == "01":
                    odometer_unit = "Mile"
                elif odometer_unit_hex.lower() == "ff":
                    odometer_unit = "Unkn"
                else:
                    odometer_unit = odometer_unit_hex

                soc = "FFFF" if line[212:216].upper() == "FFFF" else round(int(line[212:216], 16) * 0.1, 1)  # SOC

                soh = "FF" if line[216:218].upper() == "FF" else int(line[216:218], 16)  # SOH

                battery_pack_current = "FFFF" if line[218:222].upper() == "FFFF" else round(
                    int(line[218:222], 16) * 0.1 - 10000, 1)  # 电池组电流
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
                turn_signals_status_int = int(line[250:252], 16)  # 转向灯状态
                turn_signals_status_bin = format(turn_signals_status_int, '08b')
                turn_signals_status_bits_0_to_1 = turn_signals_status_bin[-2:]
                turn_signals_status = str(turn_signals_status_bits_0_to_1)

                dataflow_tail_fields = [
                    ("dataflow_imei_checkbox", imei, 20),
                    ("dataflow_time_checkbox", time_str, 23),
                    ("dataflow_rpm_checkbox", rpm, 7),
                    ("dataflow_speed_checkbox", speed, 7),
                    ("dataflow_engine_coolant_temperature_checkbox", engine_coolant_temperature, 7),
                    ("dataflow_throttle_position_checkbox", throttle_position, 7),
                    ("dataflow_engine_duty_checkbox", engine_duty, 7),
                    ("dataflow_intake_air_flow_checkbox", intake_air_flow, 7),
                    ("dataflow_intake_air_temperature_checkbox", intake_air_temperature, 7),
                    ("dataflow_intake_air_pressure_checkbox", intake_air_pressure, 7),
                    ("dataflow_battery_voltage_checkbox", battery_voltage, 7),
                    ("dataflow_fuel_level_checkbox", fuel_level, 7),
                    ("dataflow_distance_dtcs_cleared_checkbox", distance_dtcs_cleared, 7),
                    ("dataflow_distance_mil_checkbox", distance_mil, 7),
                    ("dataflow_historical_total_mileage_checkbox", historical_total_mileage, 13),
                    ("dataflow_historical_total_fuel_consumption_checkbox", historical_total_fuel_consumption, 13),
                    ("dataflow_historical_total_driving_time_checkbox", historical_total_driving_time, 13),
                    ("dataflow_seatbelt_status_checkbox", seatbelt_status, 7),
                    ("dataflow_odometer_checkbox", odometer, 13),
                    ("dataflow_average_fuel_consumption_checkbox", average_fuel_consumption, 13),
                    ("dataflow_odometer_unit_checkbox", odometer_unit, 7),
                    ("dataflow_soc_checkbox", soc, 7),
                    ("dataflow_soh_checkbox", soh, 7),
                    ("dataflow_battery_pack_current_checkbox", battery_pack_current, 7),
                    ("dataflow_battery_pack_voltage_checkbox", battery_pack_voltage, 7),
                    ("dataflow_battery_pack_charging_checkbox", battery_pack_charging, 5),
                    ("dataflow_remaining_distance_checkbox", remaining_distance, 7),
                    ("dataflow_battery_pack_temperature_checkbox", battery_pack_temperature, 7),
                    ("dataflow_distance_till_next_servicing_checkbox", distance_till_next_servicing, 7),
                    ("dataflow_engine_run_time_checkbox", engine_run_time, 13),
                    ("dataflow_fuel_type_checkbox", fuel_type, 5),
                    ("dataflow_turn_signals_status_checkbox", turn_signals_status, 5),
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

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第五章：书香百味有多少，天下何人配白衣 —— 无双
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # dtc事件
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

        for line in raw_data_string:
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

    # 低电压事件
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

        for line in raw_data_string:
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

    # 震动事件
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

        for line in raw_data_string:
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

    # 疑似碰撞
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

        for line in raw_data_string:
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

    # 拔出告警
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

        for line in raw_data_string:
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

    # 干扰状态
    def process_jamming_detection(self, raw_data_string):
        headers = []
        if self.jamming_detection_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.jamming_detection_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.jamming_detection_jamming_status_checkbox.isChecked():
            headers.append(f"{'干扰状态':<8}")
        if self.jamming_detection_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        jamming_detection_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
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

                row = []
                if self.jamming_detection_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.jamming_detection_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.jamming_detection_jamming_status_checkbox.isChecked():
                    row.append(f"{jamming_state:<12}")
                if self.jamming_detection_raw_data_checkbox.isChecked():
                    row.append(line)

                jamming_detection_event_times_1.append("".join(row))

        if jamming_detection_event_times_1:
            self.result_label.setText(f"共找到 {len(jamming_detection_event_times_1) - 1} 个干扰状态事件")
            self.raw_data_display.setText("\n".join(jamming_detection_event_times_1))
        else:
            self.result_label.setText("未找到干扰状态事件")
            self.raw_data_display.setText("")

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第六章：枪似游龙万兵手，命若黄泉不回头 —— 白龙
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # 休眠事件
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

        for line in raw_data_string:
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

    # 唤醒状态
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

        for line in raw_data_string:
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

    # 长时间无法定位
    def process_gps_not_fix(self, raw_data_string):
        headers = []
        if self.gps_not_fix_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.gps_not_fix_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.gps_not_fix_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        gps_not_fix_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
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

    # 重启事件
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

        for line in raw_data_string:
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

    # MCU升级状态
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

        for line in raw_data_string:
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

    # 设备信息
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

        for line in raw_data_string:
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

    # sensor_normal 事件
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

        for line in raw_data_string:
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

    # sensor_event 事件
    def process_sensor_event(self, raw_data_string):
        sensor_event_header_fields = [
            ("sensor_event_imei_checkbox", "IMEI", 20),
            ("sensor_event_time_checkbox", "触发时间", 19),
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

        for line in raw_data_string:
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

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第七章：有过痛苦方知众生痛苦，有过牵挂，了无牵挂，若是修佛先修心，一枪风雪一枪冰 —— 望穿
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第八章：翻云起雾藏杀意，横扫千军几万里 —— 鲲鹏
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

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

        for line in raw_data_string:
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

        for line in raw_data_string:
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

    # ════════════════════════════════════════════════════════
    # ┏━━━━━━━━━━━━━━━━━━┓
    # ┃  ∝╬══════→ ┃ 第九章：纵使韩信断了枪，也徒留我一人伤 —— 百鬼夜行
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════

    # ibutton id
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

        for line in raw_data_string:
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

    # 胎压上报
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

        for line in raw_data_string:
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

    # 胎压告警
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

        for line in raw_data_string:
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





    def clear_output(self):
        self.raw_data_display.clear()
        self.result_label.setText("Results will appear here.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataFetcherApp()
    window.show()
    sys.exit(app.exec_())
