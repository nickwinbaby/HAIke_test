import sys
import re
import pandas as pd
import os
import requests

import subprocess
# from PyQt5.QtWidgets import QFileDialog
from datetime import datetime, timezone, timedelta
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QDateTimeEdit, QPushButton,
    QLabel, QTextEdit, QComboBox, QCheckBox, QHBoxLayout, QGroupBox, QFileDialog, QGridLayout
)
from PyQt5.QtCore import QDateTime, QTimer


# ════════════════════════════════════════════════════════
# 1.self.dropdown1.addItems 定义一级目录
# 2.def fetch_data(self): if data_type not in 定义一级目录的显示
# 3.def update_dropdown2(self): 定义一级目录的二级目录显示
# 4.update_checkbox_visibility 定义二级目录的显示框内容
# 5.def fetch_data(self) 下面 定义二级目录的判断，进入具体函数
# 6.xxx复选框合集，定义页面可选择的展示内容，默认rawdata不展示

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
    # 添加"4.6 - Message send to server"
    # 添加"5.7 - Device tamper warning",
    # 添加"5.8 - Temperature warning",
    # 添加"5.13 - Device warning message"
    # 修改KLV 部分计算方式
# modify 260422
    # 添加 7.1 7.2 7.3 7.4 章节
    # 7.5 7.6 只打基础，不写具体解析，留给后续完善
# modify 260427
    # 修改LBS 适应新协议




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

def parse_klv(data):
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

            result.append(f"{k} - {v_value}")

        except:
            break

    return " , ".join(result)

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

        self.setWindowTitle("4.0协议服务器数据批量解析 - Mangetic - 260427")
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
        # self.dropdown1.addItems(["Select Type", "RAW DATA", "Trip data", "2 - Driving behavior", "3 - Location data",
        #                          "4 - Vehicle data", "5 - Secure data", "6 - Device state", "8 - Active server request",
        #                          "9 - Accessories information"])
        self.dropdown1.addItems([ "Select Type", "RAW DATA",
                                  "0 - Connect or disconnect",
                                  "1 - Trip data",
                                  "2 - Driving behavior",
                                  "3 - Location data",
                                  "4 - Vehicle data",
                                  "5 - Secure data",
                                  "6 - Device state",
                                  "7 - Device request message",
                                  "8 - Active server request",
                                  "9 - Accessories information"
                                  ])



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
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in connect_fields.items():
            var_name = f"connect_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # disconnect专用复选框
        disconnect_fields = {
            "imei": ("IMEI", True),
            "time": ("时间", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in disconnect_fields.items():
            var_name = f"disconnect_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)


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

        # 急变道专用复选框
        sudden_lane_change = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "value": ("触发值", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in sudden_lane_change.items():
            var_name = f"sudden_lane_change_{key}_checkbox"
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

        # can 支持参数状态专用复选框
        can_parameter_support_status_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "vin": ("vin", True),
            "gasoline_ev": ("gasoline_ev", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in can_parameter_support_status_fields.items():
            var_name = f"can_parameter_support_status_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 原始CAN消息帧
        raw_can_frame_fields = {
            "imei": ("IMEI", True),
            "time": ("IMEI", True),
            "canbuspins": ("canbuspins", True),
            "num_canframe": ("num", True),
            "canframeid_raw": ("canframeid_raw", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in raw_can_frame_fields.items():
            var_name = f"raw_can_frame_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # config 数据流专用复选框
        config_dataflow_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "klv": ("数据流", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in config_dataflow_fields.items():
            var_name = f"config_dataflow_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 消息发送到服务器专用复选框
        message_send_to_server_fields = {
            "imei": ("IMEI", True),
            # "time": ("触发时间", True),
            "klv_data": ("消息内容", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in message_send_to_server_fields.items():
            var_name = f"message_send_to_server_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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

        # 设备防拆告警
        device_tamper_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in device_tamper_warning_fields.items():
            var_name = f"device_tamper_warning_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 温度告警
        temperature_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "temperature_value": ("温度值", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in temperature_warning_fields.items():
            var_name = f"temperature_warning_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 气压告警
        air_pressure_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in air_pressure_warning_fields.items():
            var_name = f"air_pressure_warning_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 冲击告警
        shock_warning_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "num": ("NUM", True),
            "sensor_data": ("冲击值", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in shock_warning_fields.items():
            var_name = f"shock_warning_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 设备告警信息
        device_warning_message_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "klv_data": ("告警信息", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in device_warning_message_fields.items():
            var_name = f"device_warning_message_{key}_checkbox"
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

        # 继电器控制状态专用复现框
        relay_control_status_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "relay_control_status": ("控制状态", True),
            "event_trigger_reason": ("原因", True),
            "ibutton_id": ("iButton ID", True),
            "rfid_id": ("RFID ID", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in relay_control_status_fields.items():
            var_name = f"relay_control_status_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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

        for key, (label, checked) in bosch_collision_fields.items():
            var_name = f"bosch_crash_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)


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
        for key, (label, checked) in request_mcu_update_package_fields.items():
            var_name = f"request_mcu_update_package_tcp_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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
        for key, (label, checked) in request_agps_data_fields.items():
            var_name = f"request_agps_data_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

    # MCU更新包验证（TCP）专用复选框
        mcu_update_package_validation_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "file_name_length": ("长度", True),
            "file_name": ("文件名称", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in mcu_update_package_validation_fields.items():
            var_name = f"mcu_update_package_verification_tcp_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

    # MCU日志上报 专用复选框
        mcu_log_report_fields = {
            "imei": ("IMEI", True),
            "log_type": ("日志类型", True),
            "log_id": ("日志ID", True),
            "offset": ("日志偏移", True),
            "logdata": ("日志数据", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in mcu_log_report_fields.items():
            var_name = f"mcu_log_report_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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
        for key, (label, checked) in check_new_update_package_fields.items():
            var_name = f"check_new_update_package_router_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

    #  对新更新包的响应（适用于路由器) 专用复选框
        response_new_update_package_fields = {
            "imei": ("IMEI", True),
            "time": ("触发时间", True),
            "fota_task_id": ("任务ID", True),
            "response_fota_task": ("响应结果", True),
            "raw_data": ("原始数据", False)
        }
        for key, (label, checked) in response_new_update_package_fields.items():
            var_name = f"response_to_new_update_package_router_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

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

        # 白名单配置响应专用复选框
        whitelist_management_fields = {
            "imei": ("IMEI", True),
            "operation_result": ("操作结果", True),
            "type": ("类型", True),
            "num_of_ids": ("已有ID数量", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in whitelist_management_fields.items():
            var_name = f"whitelist_management_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # 配件白名单查询-RFID-IBUTTON
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

        for key, (label, checked) in whitelist_query_fields.items():
            var_name = f"whitelist_query_{key}_checkbox"
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

        # 温湿度传感器
        rs485_temperature_humidity_fields = {
            "imei": ("IMEI", True),
            "num": ("传感器数量", True),
            "time": ("上报时间", True),
            "temperature": ("温度", True),
            "humidity": ("湿度", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in rs485_temperature_humidity_fields.items():
            var_name = f"rs485_temperature_humidity_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # RFID数据上报
        rfid_data_fields = {
            "imei": ("IMEI", True),
            "time": ("上报时间", True),
            "rfid_id": ("RFID ID", True),
            "authentication_status": ("身份验证状态", True),
            "raw_data": ("原始数据", False)
        }

        for key, (label, checked) in rfid_data_fields.items():
            var_name = f"rfid_data_{key}_checkbox"
            checkbox = QCheckBox(label)
            checkbox.setChecked(checked)
            setattr(self, var_name, checkbox)

        # BLE TAG 数据上报
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

        for key, (label, checked) in ble_tag_data_fields.items():
            var_name = f"ble_tag_data_{key}_checkbox"
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
        data_layout.addStretch()

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

        self.dropdown2.setFixedWidth(250)
        self.dropdown2.setFixedHeight(28)
        data_layout.addWidget(self.dropdown2)



        layout.addLayout(data_layout)

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
        elif selected == "0 - Connect or disconnect":
            self.dropdown2.addItems(["Connect",
                                     "Disconnect"])
        elif selected == "1 - Trip data": # 一共五个章节完成
            self.dropdown2.addItems(["1.1 - trip summary",
                                     "1.2 - Ignition on",
                                     "1.3 - Ignition off",
                                     "1.4 - trip start",
                                     "1.5 - trip end"])
        elif selected == "2 - Driving behavior": # 一共七个章节完成
            self.dropdown2.addItems(["2.1 - Sudden acc",
                                     "2.2 - Sudden dec",
                                     "2.3 - Sharp turn",
                                     "2.4 - Exceed idle",
                                     "2.5 - Driving tired",
                                     "2.6 - Over speed",
                                     "2.7 - Sudden Lane Change"])
        elif selected == "3 - Location data":  # 一共四个章节，LBS暂时不管，可配置的暂时不管
            self.dropdown2.addItems(["3.1 - GPS data",
                                     "3.2 - LBS data"])
        elif selected == "4 - Vehicle data":
            self.dropdown2.addItems(["4.1 - VIN Cold",
                                     "4.2 - Data flow",
                                     "4.3 - CAN parameter support status",
                                     "4.4 - Raw can frame",
                                     "4.5 - Config data flow",
                                     "4.6 - Message send to server"
                                     ])
        elif selected == "5 - Secure data":
            self.dropdown2.addItems(["5.1 - DTC code",
                                     "5.2 - Battery low",
                                     "5.3 - Vibration event",
                                     "5.4 - Suspected collision",
                                     "5.5 - Unplug warning",
                                     "5.6 - Jamming detection",
                                     "5.7 - Device tamper warning",
                                     "5.8 - Temperature warning",
                                     "5.9 - Air pressure warning",
                                     "5.10 - Shock warning",
                                     "5.13 - Device warning message"
                                     ])
        elif selected == "6 - Device state":
            self.dropdown2.addItems(["6.1 - Sleep state",
                                     "6.2 - Wakeup state",
                                     "6.3 - GPS not fix",
                                     "6.4 - Reboot event",
                                     "6.5 - Mcu upgrade state",
                                     "6.7 - Device info",
                                     "6.8 - Sensor normal",
                                     "6.9 - Sensor event",
                                     "6.11 - Relay control status",
                                     "Bosch crash data"])

        elif selected == "7 - Device request message":
            self.dropdown2.addItems(["7.1 -Request MCU update package(TCP)",
                                    "7.2 - Request AGPS data",
                                    "7.3 - MCU Update package verification(TCP)",
                                    "7.4 - MCU Log Report",
                                    "7.5 - Check new update package(Router)-暂不开发",
                                    "7.6 - Response to the New Update Package(Router)-暂不开发"
                                    ])

        elif selected == "8 - Active server request":
            self.dropdown2.addItems(["8.2 - Set parameters",
                                     "8.3 - Inquiry parameters",
                                     "8.8 - whitelist management",
                                     "8.9 - whitelist query"])

        elif selected == "9 - Accessories information":
            self.dropdown2.addItems(["9.1 - Ibutton id",
                                     "9.2 - Ble sensor data",
                                     "9.3 - Rs485 temperature humidity",
                                     "9.4 - Ble sensor warning",
                                     "9.5 - Rfid data",
                                     "9.7 - Ble tag"])

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
        if data_type == "0 - Connect or disconnect":
            if sub_type == "Connect":
                for cb in [self.connect_imei_checkbox,
                           self.connect_time_checkbox,
                           self.connect_hardware_version_checkbox,
                           self.connect_mcu_ap_version_checkbox,
                           self.connect_mdm_version_checkbox,
                           self.connect_cfg_version_checkbox,
                           self.connect_support_status_fota_checkbox,
                           self.connect_raw_data_checkbox
                           ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "Disconnect":
                for cb in [self.disconnect_imei_checkbox,
                           self.disconnect_time_checkbox,
                           self.disconnect_raw_data_checkbox
                           ]:
                    self.checkbox_layout.addWidget(cb)

        # 第一章  显示内容

        if data_type == "1 - Trip data":
            if sub_type == "1.1 - trip summary":
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

            elif sub_type in ["1.2 - Ignition on", "1.3 - Ignition off"]:
                for cb in [
                    self.eng_imei_checkbox,
                    self.eng_type_checkbox,
                    self.eng_time_checkbox,
                    self.eng_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type in ["1.4 - trip start", "1.5 - trip end"]:
                for cb in [
                    self.passive_trip_imei_checkbox,
                    self.passive_trip_time_checkbox,
                    self.passive_trip_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第二章  显示内容

        elif data_type == "2 - Driving behavior":
            if sub_type in ["2.1 - Sudden acc", "2.2 - Sudden dec"]:
                for cb in [
                    self.sudden_imei_checkbox,
                    self.sudden_time_checkbox,
                    self.sudden_before_speed_checkbox,
                    self.sudden_after_speed_checkbox,
                    self.sudden_value_checkbox,
                    self.sudden_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "2.3 - Sharp turn":
                for cb in [
                    self.sharp_turn_imei_checkbox,
                    self.sharp_turn_time_checkbox,
                    self.sharp_turn_Turn_checkbox,
                    self.sharp_turn_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "2.4 - Exceed idle":
                for cb in [
                    self.exceed_idle_imei_checkbox,
                    self.exceed_idle_time_checkbox,
                    self.exceed_idle_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "2.5 - Driving tired":
                for cb in [
                    self.driving_tired_imei_checkbox,
                    self.driving_tired_time_checkbox,
                    self.driving_tired_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "2.6 - Over speed":
                for cb in [
                    self.over_speed_imei_checkbox,
                    self.over_speed_time_checkbox,
                    self.over_speed_value_checkbox,
                    self.over_speed_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "2.7 - Sudden Lane Change":
                for cb in [
                    self.sudden_lane_change_imei_checkbox,
                    self.sudden_lane_change_time_checkbox,
                    self.sudden_lane_change_value_checkbox,
                    self.sudden_lane_change_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第三章  显示内容

        elif data_type == "3 - Location data":
            if sub_type == "3.1 - GPS data":
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
            elif sub_type == "3.2 - LBS data":
                for cb in [
                    self.lbs_location_data_imei_checkbox,
                    self.lbs_location_data_time_checkbox,
                    self.lbs_location_data_mcc_mnc_checkbox,
                    self.lbs_location_data_radio_type_checkbox,
                    self.lbs_location_data_carrier_name_checkbox,
                    self.lbs_location_data_consider_ip_checkbox,
                    # self.lbs_location_data_cell_num_checkbox,
                    self.lbs_location_data_cell_list_checkbox,
                    # self.lbs_location_data_wifi_num_checkbox,
                    self.lbs_location_data_wifi_list_checkbox,
                    self.lbs_location_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第四章  显示内容

        elif data_type == "4 - Vehicle data":
            if sub_type == "4.1 - VIN Cold":
                for cb in [
                    self.vin_imei_checkbox,
                    self.vin_time_checkbox,
                    self.vin_type_checkbox,
                    self.vin_length_checkbox,
                    self.vin_vin_value_checkbox,
                    self.vin_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "4.2 - Data flow":
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

            elif sub_type == "4.3 - CAN parameter support status":
                for cb in [
                    self.can_parameter_support_status_imei_checkbox,
                    self.can_parameter_support_status_time_checkbox,
                    self.can_parameter_support_status_vin_checkbox,
                    self.can_parameter_support_status_gasoline_ev_checkbox,
                    self.can_parameter_support_status_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "4.4 - Raw can frame":
                for cb in [
                    self.raw_can_frame_imei_checkbox,
                    self.raw_can_frame_time_checkbox,
                    self.raw_can_frame_canbuspins_checkbox,
                    self.raw_can_frame_num_canframe_checkbox,
                    self.raw_can_frame_canframeid_raw_checkbox,
                    self.raw_can_frame_raw_data_checkbox,
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "4.5 - Config data flow":
                for cb in [
                    self.config_dataflow_imei_checkbox,
                    self.config_dataflow_time_checkbox,
                    self.config_dataflow_klv_checkbox,
                    self.config_dataflow_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "4.6 - Message send to server":
                for cb in [
                    self.message_send_to_server_imei_checkbox,
                    # self.message_send_to_server_time_checkbox,
                    self.message_send_to_server_klv_data_checkbox,
                    self.message_send_to_server_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第五章  显示内容

        elif data_type == "5 - Secure data":
            if sub_type == "5.1 - DTC code":
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

            elif sub_type == "5.2 - Battery low":
                for cb in [
                    self.battery_low_imei_checkbox,
                    self.battery_low_time_checkbox,
                    self.battery_low_battery_voltage_checkbox,
                    self.battery_low_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "5.3 - Vibration event":
                for cb in [
                    self.vibration_event_imei_checkbox,
                    self.vibration_event_time_checkbox,
                    self.vibration_event_vibration_value_checkbox,
                    self.vibration_event_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "5.4 - Suspected collision":
                for cb in [
                    self.suspected_collision_imei_checkbox,
                    self.suspected_collision_time_checkbox,
                    self.suspected_collision_collision_value_checkbox,
                    self.suspected_collision_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.5 - Unplug warning":
                for cb in [
                    self.unplug_warning_imei_checkbox,
                    self.unplug_warning_time_checkbox,
                    self.unplug_warning_unplug_state_checkbox,
                    self.unplug_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.6 - Jamming detection":
                for cb in [
                    self.jamming_detection_imei_checkbox,
                    self.jamming_detection_time_checkbox,
                    self.jamming_detection_jamming_status_checkbox,
                    self.jamming_detection_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.7 - Device tamper warning":
                for cb in [
                    self.device_tamper_warning_imei_checkbox,
                    self.device_tamper_warning_time_checkbox,
                    self.device_tamper_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.8 - Temperature warning":
                for cb in [
                    self.temperature_warning_imei_checkbox,
                    self.temperature_warning_time_checkbox,
                    self.temperature_warning_temperature_value_checkbox,
                    self.temperature_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.9 - Air pressure warning":
                for cb in [
                    self.air_pressure_warning_imei_checkbox,
                    self.air_pressure_warning_time_checkbox,
                    self.air_pressure_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.10 - Shock warning":
                for cb in [
                    self.shock_warning_imei_checkbox,
                    self.shock_warning_time_checkbox,
                    self.shock_warning_num_checkbox,
                    self.shock_warning_sensor_data_checkbox,
                    self.shock_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "5.13 - Device warning message":
                for cb in [
                    self.device_warning_message_imei_checkbox,
                    self.device_warning_message_time_checkbox,
                    self.device_warning_message_klv_data_checkbox,
                    self.device_warning_message_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第六章  显示内容

        elif data_type == "6 - Device state":
            if sub_type == "6.1 - Sleep state":
                for cb in [
                    self.sleep_state_imei_checkbox,
                    self.sleep_state_time_checkbox,
                    self.sleep_state_sleep_voltage_checkbox,
                    self.sleep_state_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)
            elif sub_type == "6.2 - Wakeup state":
                for cb in [
                    self.wakeup_state_imei_checkbox,
                    self.wakeup_state_time_checkbox,
                    self.wakeup_state_wakeup_voltage_checkbox,
                    self.wakeup_state_wakeup_type_checkbox,
                    self.wakeup_state_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "6.3 - GPS not fix":
                for cb in [
                    self.gps_not_fix_imei_checkbox,
                    self.gps_not_fix_time_checkbox,
                    self.gps_not_fix_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "6.4 - Reboot event":
                for cb in [
                    self.reboot_event_imei_checkbox,
                    self.reboot_event_power_on_time_checkbox,
                    self.reboot_event_power_off_time_checkbox,
                    self.reboot_event_reboot_reason_checkbox,
                    self.reboot_event_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "6.5 - Mcu upgrade state":
                for cb in [
                    self.mcu_upgrade_state_imei_checkbox,
                    self.mcu_upgrade_state_time_checkbox,
                    self.mcu_upgrade_state_upgrade_state_checkbox,
                    self.mcu_upgrade_state_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "6.7 - Device info":
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

            elif sub_type == "6.8 - Sensor normal":
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

            elif sub_type == "6.9 - Sensor event":
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

            elif sub_type == "6.11 - Relay control status":
                for cb in [
                    self.relay_control_status_imei_checkbox,
                    self.relay_control_status_time_checkbox,
                    self.relay_control_status_relay_control_status_checkbox,
                    self.relay_control_status_event_trigger_reason_checkbox,
                    self.relay_control_status_ibutton_id_checkbox,
                    self.relay_control_status_rfid_id_checkbox,
                    self.relay_control_status_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            # 博世碰撞
            elif sub_type == "Bosch crash data":
                for cb in [
                    self.bosch_crash_imei_checkbox,
                    self.bosch_crash_report_time_checkbox,
                    self.bosch_crash_event_time_checkbox,
                    self.bosch_crash_crash_index_checkbox,
                    self.bosch_crash_crash_status_checkbox,
                    self.bosch_crash_crash_event_counter_checkbox,
                    self.bosch_crash_crash_frame_counter_checkbox,
                    self.bosch_crash_error_status_checkbox,
                    self.bosch_crash_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第七章  显示内容

        elif data_type == "7 - Device request message":
            if sub_type == "7.1 -Request MCU update package(TCP)":
                for cb in [
                    self.request_mcu_update_package_tcp_imei_checkbox,
                    self.request_mcu_update_package_tcp_time_checkbox,
                    self.request_mcu_update_package_tcp_file_name_length_checkbox,
                    self.request_mcu_update_package_tcp_file_name_checkbox,
                    self.request_mcu_update_package_tcp_staring_position_checkbox,
                    self.request_mcu_update_package_tcp_request_length_bytes_checkbox,
                    self.request_mcu_update_package_tcp_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "7.2 - Request AGPS data":
                for cb in [
                    self.request_agps_data_imei_checkbox,
                    self.request_agps_data_time_checkbox,
                    self.request_agps_data_longitude_checkbox,
                    self.request_agps_data_longitude_value_checkbox,
                    self.request_agps_data_latitude_checkbox,
                    self.request_agps_data_latitude_value_checkbox,
                    self.request_agps_data_ages_service_type_checkbox,
                    self.request_agps_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "7.3 - MCU Update package verification(TCP)":
                for cb in [
                    self.mcu_update_package_verification_tcp_imei_checkbox,
                    self.mcu_update_package_verification_tcp_time_checkbox,
                    self.mcu_update_package_verification_tcp_file_name_length_checkbox,
                    self.mcu_update_package_verification_tcp_file_name_checkbox,
                    self.mcu_update_package_verification_tcp_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "7.4 - MCU Log Report":
                for cb in [
                    self.mcu_log_report_imei_checkbox,
                    self.mcu_log_report_log_type_checkbox,
                    self.mcu_log_report_log_id_checkbox,
                    self.mcu_log_report_offset_checkbox,
                    self.mcu_log_report_logdata_checkbox,
                    self.mcu_log_report_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "7.5 - Check new update package(Router)":
                for cb in [
                    self.check_new_update_package_router_imei_checkbox,
                    self.check_new_update_package_router_time_checkbox,
                    self.check_new_update_package_router_mdm_version_checkbox,
                    self.check_new_update_package_router_ap_version_checkbox,
                    self.check_new_update_package_router_cfg_version_checkbox,
                    self.check_new_update_package_router_request_type_checkbox,
                    self.check_new_update_package_router_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "7.6 - Response to the New Update Package(Router)":
                for cb in [
                    self.response_to_new_update_package_router_imei_checkbox,
                    self.response_to_new_update_package_router_time_checkbox,
                    self.response_to_new_update_package_router_fota_task_id_checkbox,
                    self.response_to_new_update_package_router_response_fota_task_checkbox,
                    self.response_to_new_update_package_router_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第八章  显示内容

        elif data_type == "8 - Active server request":
            if sub_type == "8.2 - Set parameters":
                for cb in [
                    self.set_parameters_imei_checkbox,
                    self.set_parameters_set_result_checkbox,
                    self.set_parameters_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "8.3 - Inquiry parameters":
                for cb in [
                    self.inquiry_parameters_imei_checkbox,
                    self.inquiry_parameters_inquiry_result_checkbox,
                    self.inquiry_parameters_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "8.8 - whitelist management":
                for cb in [
                    self.whitelist_management_imei_checkbox,
                    self.whitelist_management_operation_result_checkbox,
                    self.whitelist_management_type_checkbox,
                    self.whitelist_management_num_of_ids_checkbox,
                    self.whitelist_management_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "8.9 - whitelist query":
                for cb in [
                    self.whitelist_query_imei_checkbox,
                    self.whitelist_query_type_checkbox,
                    self.whitelist_query_length_id_checkbox,
                    self.whitelist_query_multi_frame_flag_checkbox,
                    self.whitelist_query_current_response_message_checkbox,
                    self.whitelist_query_number_of_ids_checkbox,
                    self.whitelist_query_ids_checkbox,
                    self.whitelist_query_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

        # 第九章  显示内容

        elif data_type == "9 - Accessories information":
            if sub_type == "9.2 - Ble sensor data":
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

            elif sub_type == "9.1 - Ibutton id":
                for cb in [
                    self.ibutton_id_imei_checkbox,
                    self.ibutton_id_time_checkbox,
                    self.ibutton_id_ibutton_id_checkbox,
                    self.ibutton_id_authentication_status_checkbox,
                    self.ibutton_id_gps_data_checkbox,
                    self.ibutton_id_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "9.3 - Rs485 temperature humidity":
                for cb in [
                    self.rs485_temperature_humidity_imei_checkbox,
                    self.rs485_temperature_humidity_num_checkbox,
                    self.rs485_temperature_humidity_time_checkbox,
                    self.rs485_temperature_humidity_temperature_checkbox,
                    self.rs485_temperature_humidity_humidity_checkbox,
                    self.rs485_temperature_humidity_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "9.4 - Ble sensor warning":
                for cb in [
                    self.ble_sensor_warning_imei_checkbox,
                    self.ble_sensor_warning_time_checkbox,
                    self.ble_sensor_warning_warning_type_checkbox,
                    self.ble_sensor_warning_warning_position_checkbox,
                    self.ble_sensor_warning_warning_pressure_checkbox,
                    self.ble_sensor_warning_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "9.5 - Rfid data":
                for cb in [
                    self.rfid_data_imei_checkbox,
                    self.rfid_data_time_checkbox,
                    self.rfid_data_rfid_id_checkbox,
                    self.rfid_data_authentication_status_checkbox,
                    self.rfid_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)

            elif sub_type == "9.7 - Ble tag":
                for cb in [
                    self.ble_tag_data_imei_checkbox,
                    self.ble_tag_data_tag_num_checkbox,
                    self.ble_tag_data_UUID_checkbox,
                    self.ble_tag_data_major_checkbox,
                    self.ble_tag_data_minor_checkbox,
                    self.ble_tag_data_RSSI_checkbox,
                    self.ble_tag_data_battery_checkbox,
                    self.ble_tag_data_anti_tamper_status_checkbox,
                    self.ble_tag_data_asensor_status_checkbox,
                    self.ble_tag_data_raw_data_checkbox
                ]:
                    self.checkbox_layout.addWidget(cb)





        # 最后加上导出按钮（确保它始终存在）
        self.checkbox_layout.addWidget(self.export_button)

        # else:
        #     self.checkbox_group.setVisible(False)

    def fetch_data(self):
        data_type = self.dropdown1.currentText()
        sub_type = self.dropdown2.currentText()

        if data_type not in ["RAW DATA",
                             "0 - Connect or disconnect",
                             "1 - Trip data",
                             "2 - Driving behavior",
                             "3 - Location data",
                             "4 - Vehicle data",
                             "5 - Secure data",
                             "6 - Device state",
                             "7 - Device request message",
                             "8 - Active server request",
                             "9 - Accessories information"]:
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

        elif data_type == "0 - Connect or disconnect" and sub_type == "Connect":
            self.process_connect_data(raw_data)
        elif data_type == "0 - Connect or disconnect" and sub_type == "Disconnect":
            self.process_disconnect_data(raw_data)

        elif data_type == "1 - Trip data" and sub_type == "1.1 - trip summary":
            self.process_trip_summary(raw_data)
        elif data_type == "1 - Trip data" and sub_type == "1.2 - Ignition on":
            self.process_ignition_on(raw_data)
        elif data_type == "1 - Trip data" and sub_type == "1.3 - Ignition off":
            self.process_ignition_off(raw_data)
        elif data_type == "1 - Trip data" and sub_type == "1.4 - trip start":
            self.process_trip_start(raw_data)
        elif data_type == "1 - Trip data" and sub_type == "1.5 - trip end":
            self.process_trip_end(raw_data)

        elif data_type == "2 - Driving behavior" and sub_type == "2.1 - Sudden acc":
            self.process_sudden_acc(raw_data)
        elif data_type == "2 - Driving behavior" and sub_type == "2.2 - Sudden dec":
            self.process_sudden_dec(raw_data)
        elif data_type == "2 - Driving behavior" and sub_type == "2.3 - Sharp turn":
            self.process_sharp_turn(raw_data)
        elif data_type == "2 - Driving behavior" and sub_type == "2.4 - Exceed idle":
            self.process_exceed_idle(raw_data)
        elif data_type == "2 - Driving behavior" and sub_type == "2.5 - Driving tired":
            self.process_driving_tired(raw_data)
        elif data_type == "2 - Driving behavior" and sub_type == "2.6 - Over speed":
            self.process_over_speed(raw_data)
        elif data_type == "2 - Driving behavior" and sub_type == "2.7 - Sudden Lane Change":
            self.process_sudden_lane_change(raw_data)

        elif data_type == "3 - Location data" and sub_type == "3.1 - GPS data":
            self.process_gps_data_3(raw_data)
        elif data_type == "3 - Location data" and sub_type == "3.2 - LBS data":
            self.process_lbs_data(raw_data)

        elif data_type == "4 - Vehicle data" and sub_type == "4.1 - VIN Cold":
            self.process_vin_code(raw_data)
        elif data_type == "4 - Vehicle data" and sub_type == "4.2 - Data flow":
            self.process_data_flow(raw_data)
        elif data_type == "4 - Vehicle data" and sub_type == "4.3 - CAN parameter support status":
            self.process_can_parameter_support_status(raw_data)
        elif data_type == "4 - Vehicle data" and sub_type == "4.4 - Raw can frame":
            self.process_raw_can_frame(raw_data)
        elif data_type == "4 - Vehicle data" and sub_type == "4.5 - Config data flow":
            self.process_config_data_flow(raw_data)
        elif data_type == "4 - Vehicle data" and sub_type == "4.6 - Message send to server":
            self.process_message_send_to_server(raw_data)

        elif data_type == "5 - Secure data" and sub_type == "5.1 - DTC code":
            self.process_dtc_code(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.2 - Battery low":
            self.process_battery_low(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.3 - Vibration event":
            self.process_vibration_event(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.4 - Suspected collision":
            self.process_suspected_collision(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.5 - Unplug warning":
            self.process_unplug_warning(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.6 - Jamming detection":
            self.process_jamming_detection(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.7 - Device tamper warning":
            self.process_device_tamper_warning(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.8 - Temperature warning":
            self.process_temperature_warning(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.9 - Air pressure warning":
            self.process_air_pressure_warning(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.10 - Shock warning":
            self.process_shock_warning(raw_data)
        elif data_type == "5 - Secure data" and sub_type == "5.13 - Device warning message":
            self.process_device_warning_message(raw_data)

        elif data_type == "6 - Device state" and sub_type == "6.1 - Sleep state":
            self.process_sleep_state(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.2 - Wakeup state":
            self.process_wakeup_state(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.3 - GPS not fix":
            self.process_gps_not_fix(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.4 - Reboot event":
            self.process_reboot_event(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.5 - Mcu upgrade state":
            self.process_mcu_upgrade_state(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.7 - Device info":
            self.process_device_info(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.8 - Sensor normal":
            self.process_sensor_normal(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.9 - Sensor event":
            self.process_sensor_event(raw_data)
        elif data_type == "6 - Device state" and sub_type == "6.11 - Relay control status":
            self.process_relay_control_status(raw_data)
        # 博世碰撞
        elif data_type == "6 - Device state" and sub_type == "Bosch crash data":
            self.process_bosch_crash_data(raw_data)

        elif data_type == "7 - Device request message" and sub_type == "7.1 -Request MCU update package(TCP)":
            self.process_request_mcu_update_package_tcp(raw_data)
        elif data_type == "7 - Device request message" and sub_type == "7.2 - Request AGPS data":
            self.process_request_agps_data(raw_data)
        elif data_type == "7 - Device request message" and sub_type == "7.3 - MCU Update package verification(TCP)":
            self.process_mcu_update_package_verification_tcp(raw_data)
        elif data_type == "7 - Device request message" and sub_type == "7.4 - MCU Log Report":
            self.process_mcu_log_report(raw_data)
        elif data_type == "7 - Device request message" and sub_type == "7.5 - Check new update package(Router)":
            self.process_check_new_update_package_router(raw_data)
        elif data_type == "7 - Device request message" and sub_type == "7.6 - Response to the New Update Package(Router)":
            self.process_response_to_the_new_update_package_router(raw_data)

        elif data_type == "8 - Active server request" and sub_type == "8.2 - Set parameters":
            self.process_set_parameters(raw_data)
        elif data_type == "8 - Active server request" and sub_type == "8.3 - Inquiry parameters":
            self.process_inquiry_parameters(raw_data)
        elif data_type == "8 - Active server request" and sub_type == "8.8 - whitelist management":
            self.process_whitelist_management(raw_data)
        elif data_type == "8 - Active server request" and sub_type == "8.9 - whitelist query":
            self.process_whitelist_query(raw_data)

        elif data_type == "9 - Accessories information" and sub_type == "9.1 - Ibutton id":
            self.process_ibutton_id(raw_data)
        elif data_type == "9 - Accessories information" and sub_type == "9.2 - Ble sensor data":
            self.process_ble_sensor_data(raw_data)
        elif data_type == "9 - Accessories information" and sub_type == "9.3 - Rs485 temperature humidity":
            self.process_rs485_temperature_humidity(raw_data)
        elif data_type == "9 - Accessories information" and sub_type == "9.4 - Ble sensor warning":
            self.process_ble_sensor_warning(raw_data)
        elif data_type == "9 - Accessories information" and sub_type == "9.5 - Rfid data":
            self.process_rfid_data(raw_data)
        elif data_type == "9 - Accessories information" and sub_type == "9.7 - Ble tag":
            self.process_ble_tag_data(raw_data)

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
    # ┃  ∝╬══════→ ┃ 第零章：万始花香总盛开，一切虚无零落尽 —— 开天
    # ┗━━━━━━━━━━━━━━━━━━┛
    # ════════════════════════════════════════════════════════
    # connect 帧
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
        if self.connect_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        connect_times_1 = ["".join(headers)]

        for line in raw_data_string:
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
                    support_status_fota = "支持 TCP + HTTP"
                elif mcu_tcp_support:
                    support_status_fota = "仅支持 TCP"
                elif mcu_http_support:
                    support_status_fota = "仅支持 HTTP"
                else:
                    support_status_fota = "不支持任何FOTA"

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
                    row.append(f"{support_status_fota:<20}")
                if self.connect_raw_data_checkbox.isChecked():
                    row.append(line)

                connect_times_1.append("".join(row))

        if connect_times_1:
            self.result_label.setText(f"共找到 {len(connect_times_1) - 1} 个连接事件")
            self.raw_data_display.setText("\n".join(connect_times_1))
        else:
            self.result_label.setText("未找到连接事件")
            self.raw_data_display.setText("")

    # disconnect 帧
    def process_disconnect_data(self, raw_data_string):
        headers = []
        if self.disconnect_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.disconnect_time_checkbox.isChecked():
            headers.append(f"{'时间':<20}")
        if self.disconnect_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        disconnect_times_1 = ["".join(headers)]

        for line in raw_data_string:
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
                # driving_distance_bin = bin(int(line[174:180], 16))[2:]
                driving_distance_bin = format(int(line[174:180], 16), '024b')

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

    # 急变道事件
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

        for line in raw_data_string:
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

        for line in raw_data_string:
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
                if odometer_unit_hex == "01":
                    odometer_unit = "KM"
                elif odometer_unit_hex == "02":
                    odometer_unit = "Mile"
                elif odometer_unit_hex.lower() == "ff":
                    odometer_unit = "Unkn"
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

    # CAN 支持参数列表
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

        for line in raw_data_string:
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

    # raw can frame
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

        for line in raw_data_string:
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

    # config 数据流
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

        for line in raw_data_string:
            if line[48:50] == "03" and line[58:62] == "0306":
                imei = ascii_to_decimal(line[18:48])  # imei号
                time_str = hex_to_beijing_time(line[62:70])  # 触发时间

                # ✅ 解析KLV（从第70位开始）
                valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
                klv_data = line[70:58+valid_data_length]
                klv = parse_klv(klv_data)

                row = []
                if self.config_dataflow_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.config_dataflow_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.config_dataflow_klv_checkbox.isChecked():
                    row.append(f"{klv:<100} "  "")  # 已解析KLV
                if self.config_dataflow_raw_data_checkbox.isChecked():
                    row.append(line)

                config_dataflow_times_1.append("".join(row))

        if config_dataflow_times_1:
            self.result_label.setText(f"共找到 {len(config_dataflow_times_1) - 1} 个配置数据流事件")
            self.raw_data_display.setText("\n".join(config_dataflow_times_1))
        else:
            self.result_label.setText("未找到配置数据流事件")
            self.raw_data_display.setText("")

    def process_message_send_to_server(self, raw_data_string):
        headers = []
        if self.message_send_to_server_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        # if self.message_send_to_server_time_checkbox.isChecked():
        #     headers.append(f"{'触发时间':<19}")
        if self.message_send_to_server_klv_data_checkbox.isChecked():
            headers.append(f"{'消息内容'}")
        if self.message_send_to_server_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        message_send_to_server_times_1 = ["".join(headers)]

        for line in raw_data_string:
            if line[48:50] == "03" and line[58:62] == "0307":
                imei = ascii_to_decimal(line[18:48])  # imei号

                # ✅ 解析KLV（从第70位开始）
                valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
                klv_source_data = line[62:58+valid_data_length]
                klv_data = parse_klv(klv_source_data)

                row = []
                if self.message_send_to_server_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                # if self.message_send_to_server_time_checkbox.isChecked():
                #     row.append(f"{time_str:<23}")
                if self.message_send_to_server_klv_data_checkbox.isChecked():
                    row.append(f"{klv_data:<10}")
                if self.message_send_to_server_raw_data_checkbox.isChecked():
                    row.append(line)

                message_send_to_server_times_1.append("".join(row))

        if message_send_to_server_times_1:
            self.result_label.setText(f"共找到 {len(message_send_to_server_times_1) - 1} 个消息发送事件")
            self.raw_data_display.setText("\n".join(message_send_to_server_times_1))
        else:
            self.result_label.setText("未找到消息发送事件")
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

    # 设备防拆告警
    def process_device_tamper_warning(self, raw_data_string):
        header = []
        if self.device_tamper_warning_imei_checkbox.isChecked():
            header.append(f"{'IMEI':<20}")
        if self.device_tamper_warning_time_checkbox.isChecked():
            header.append(f"{'触发时间':<19}")
        if self.device_tamper_warning_raw_data_checkbox.isChecked():
            header.append(f"{'原始数据'}")

        device_tamper_warning_event_times_1 = ["".join(header)]

        for line in raw_data_string:
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

        for line in raw_data_string:
            if line[48:50] == "03" and line[58:62].upper() == "050D":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])
                temperature_value = int(line[118:122], 16) * 0.1 - 40   # 温度值，单位为摄氏度

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

    # 气压告警信息
    def process_air_pressure_warning(self, raw_data_string):
        headers = []
        if self.air_pressure_warning_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.air_pressure_warning_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.air_pressure_warning_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        air_pressure_warning_event_times_1 = ["".join(headers)]

        # for line in raw_data_string:
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

    # 冲击告警
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

        for line in raw_data_string:
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

    # 设备告警信息
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

        for line in raw_data_string:
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

    # 继电器控制状态
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

        for line in raw_data_string:
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

    # 博世碰撞事件
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

        for line in raw_data_string:
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

    # 7.1
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

        for line in raw_data_string:
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

    # 7.2
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

            for line in raw_data_string:
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

    # 7.3
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

        for line in raw_data_string:
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

    # 7.4
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

        for line in raw_data_string:
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
                print(effective_data,"有效数据长度")
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

    # 白名单响应
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

        for line in raw_data_string:
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

    # 白名单查询 IBUTON RFID
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

        for line in raw_data_string:
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

    # 温湿度传感器
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

        for line in raw_data_string:
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

    # RFID 事件
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

        for line in raw_data_string:
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

    # ble tag 事件
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

        for line in raw_data_string:
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

    def clear_output(self):
        self.raw_data_display.clear()
        self.result_label.setText("Results will appear here.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataFetcherApp()
    window.show()
    sys.exit(app.exec_())
