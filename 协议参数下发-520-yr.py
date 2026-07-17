import sys
import os
import time
import re
import requests
from datetime import datetime, timezone
from openpyxl import Workbook

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QHBoxLayout, QHeaderView, QCheckBox, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QIcon


APP_ICON_FILE = "protocol_param_send.ico"


def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        bundled_path = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(bundled_path):
            return bundled_path

    base_dir = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
    local_path = os.path.join(base_dir, filename)
    if os.path.exists(local_path):
        return local_path

    return os.path.join(os.getcwd(), filename)


# =========================================================
# 一、默认值查询配置
# =========================================================
# 本配置由：
# 1. 新建 XLSX 工作表.xlsx：项目支持 Yes 关系
# 2. GoTrack_V4.0.3_2026-04-28_BETA_version.docx：KEY / Length / Default value / Description
# 自动整理生成。
#
# key 规则：0x00010000 -> 0001。
# length 规则：Length=1 表示 VALUE 取 1 字节，即 2 个 HEX 字符。
# length_type="dynamic" 表示 Length 是 xx，默认按照：第 1 字节为长度 L，后面 L 字节为字符串/HEX 内容。
# query_rule 规则：
#   hex_to_int                 : HEX 转十进制，例如 28 -> 40
#   hex_to_int_x0.1            : HEX 转十进制后 * 0.1，例如 6C -> 10.8
#   hex_to_int_x0.1_offset_xxx : HEX 转十进制后 * 0.1 + offset
#   hex_string                 : 不做数值转换，直接显示 HEX
#   hex_to_ascii_dynamic_len   : 动态长度字符串，先取长度字节，再转 ASCII，失败则显示 HEX

# DEFAULT_QUERY_CONFIG 这块是默认值查询的
# SET_QUERY_CONFIG 这块是设置查询的
# ILLEGAL_SET_CONFIG 非法值设置的

# 编译命令
# pyinstaller -F -w --clean -n "协议参数下发" -i "protocol_param_send.ico" --add-data "protocol_param_send.ico;." "协议参数下发-520-yr.py"


DEFAULT_QUERY_CONFIG = {'F000': {'name': 'Reset to default value',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': 'FFFF',
          'default': 65535,
          'query_rule': 'hex_to_int',
          'description': 'Reset to default value remotely is only for the MCU side, but not the modem side. “Reset to '
                         'default value” can not reset the parameters below: Server domain name (IP), Port number, '
                         'Telematic APN, Modem side parameters'},
 '0001': {'name': 'Threshold of rapid acceleration',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '1E',
          'default': 30,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 10 unit: mg default value: 30 (300mg) Range: 10-100'},
 '0002': {'name': 'Threshold of rapid deceleration',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '28',
          'default': 40,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 10 unit: mg default value: 40 (400mg), 0x28 Range: 10-100'},
 '0003': {'name': 'Threshold of sharp turn',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '28',
          'default': 40,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 10 unit:mg default value: 40 (400mg), 0x28 Range: 25-60'},
 '0004': {'name': 'Fatigue driving',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '3840',
          'default': 14400,
          'query_rule': 'hex_to_int',
          'description': 'Unit: Second Precision: 1 default value: 14400 (4 hours), 0x3840 Range: 3600-18000'},
 '0005': {'name': 'Over Speed',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '78',
          'default': 120,
          'query_rule': 'hex_to_int',
          'description': 'Unit: KM/H Precision: 1 Range: 50-249 Default Value: 120, 0x78'},
 '0006': {'name': 'Threshold for Low vehicle battery voltage warning (12V)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '6C',
          'default': 10.8,
          'query_rule': 'hex_to_int_x0.1',
          'description': 'Precision: 0.1 Unit: Volt Default value: 108 (10.8V), 0x6C Range: 80-120'},
 '0007': {'name': 'Wake vibration level',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '03',
          'default': 3,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configuration the threshold to detect the vibration. Default value: '
                         'level 3, 0x03. 0x01: 0.0625g 0x02: 0.125g 0x03: 0.250g 0x04: 0.375g 0x05: 0.625g 0x06: '
                         '0.9375g 0x07: 1.25g'},
 '0008': {'name': 'Threshold of suspected collision',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '0F',
          'default': 15,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 100 Unit: mg Default value: 15(1500mg), 0x0F Range: 6-160'},
 '0009': {'name': 'Threshold of exceed idle',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '00B4',
          'default': 180,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: Second Default value: 180 seconds, 0x00B4 Range: 30-1200'},
 '000B': {'name': 'GPS report frequency 1',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '000A',
          'default': 10,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: Second Default value: 10 seconds, 0x000A Range: 10-180 For example, If it '
                         'is set as 10, then device will report GPS frame(02, 00) every 10s.'},
 '000C': {'name': 'Vehicle data report  frequency',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '000F',
          'default': 15,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: second Default value: 15 seconds, 0x000F. Range: 5-3600'},
 '000D': {'name': 'Wakeup DISTURBANCE info report time',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0028',
          'default': 40,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: Second Default value: 40 seconds, 0x0028. Range: 0-300'},
 '000E': {'name': 'Heartbeat time (Wake up periodically)',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0018',
          'default': 24,
          'query_rule': 'hex_to_int',
          'description': 'Unit: Hour Precision: 1 Default value: 24 hours, 0x0018. Range: 1-24'},
 '000F': {'name': 'Car Emissions',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0012',
          'default': 1.8,
          'query_rule': 'hex_to_int_x0.1',
          'description': 'Unit: Liter Precision: 0.1 Range: 0-30 Default value: 18 (means 1.8L), 0x0012.'},
 '0010': {'name': 'Enable or Disable CAN Fuctions',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0000',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x0000: Enable CAN fuctions. 0x0001: Disable CAN fuctions. Default value is 0x0000. If this '
                         'parameter is set as 0x0001 to disable CAN functions, then device will stop reading / '
                         'requesting data from vehicle. Below messages will not be reported if it is set as 0x0001, '
                         'until it is set as 0x0000 again. '},
 '0012': {'name': 'ASS (Automatic start/stop system) setting',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01: ASS OFF 0x02: ASS ON Default value is 0x01. ASS means Automatic start/stop system. '
                         'There would be 2 minutes holding time if ASS setting is ON. That means the IGN off frame '
                         '(defined in chapter 1.3) will be reported 2 minutes later after the device detected the IGN '
                         'off event.'},
 '0016': {'name': 'Factory reset without ACK',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01 - factory reset include clear offline data Note: The command will be executed '
                         'immediately, not reply the platform'},
 '0017': {'name': 'Reboot without ACK',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01 - reboot devive,include “modem” and “MCU” Note: The command will be executed '
                         'immediately, not reply the platform'},
 '0018': {'name': 'Working time after ignition off (then go to sleep)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '05',
          'default': 5,
          'query_rule': 'hex_to_int',
          'description': 'Unit: minute Precision: 1 Default value: 5 minutes, 0x05 Range: 5-20'},
'0200': {'name': 'Change the IP address and port of Primary Server (For IPv4)',
         'length': None,
         'length_type': 'dynamic',
         'default_hex': '1C78617473742E726963686C696E6B636C6F75642E636F6D3A38393839',
         'default': 'xatst.richlinkcloud.com:8989',
         'query_rule': 'hex_to_ascii_dynamic_len',
         'set_rule': 'ascii_with_len',
         'description': 'Format: Lxxx.xxx.xxx.xxx:yyyy L(1byte): the length of IP address and the port. Note: The '
                        'length “L” cannot be larger than 63 Bytes.'},
 '0202': {'name': 'Wifi SSID for WiFi 2.4GHz',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': 'NULL',
          'default': 'NULL',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'Format: Lxxxxxxxxxx L(1byte): the byte length of Wifi SSID.'},
 '0203': {'name': 'Wifi Password for WiFi 2.4GHz',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': 'NULL',
          'default': 'NULL',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'Format: Lxxxxxxxxxx L(1byte): the byte length of Wifi Password.'},
 '0204': {'name': 'Wifi router APN',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': 'NULL',
          'default': 'NULL',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'Format: Lxxxxxxxxxx L(1byte): the byte length of APN Note: The length of APN should be <=32 '
                         'Bytes.'},
 '0206': {'name': 'Modem APN',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '0533676e6574',
          'default': '3gnet',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'set_rule': 'ascii_with_len',
          'description': 'Format: Lxxxxxxxxxx L(1byte): the byte length of Modem APN. Note: The length of APN should '
                         'be <=32 Bytes.'},
 '0207': {'name': 'Wifi ON / OFF for 2.4GHz',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Not controlled by the server 0x01: HOTSPOT on 0x02: HOTSPOT off'},
 '020F': {'name': 'The judgement for Ignition ON/OFF',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Tracker mode (not used) 0x01: ACC input enable mode (not used) 0x02: OBD mode (not '
                         'used) 0x03: Mixed mode 0x04: Standalone mode'},
 '0220': {'name': 'Threshold for Low voltage warning (24V)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': 'B4',
          'default': 18.0,
          'query_rule': 'hex_to_int_x0.1',
          'description': 'Precision: 0.1 Unit: Volt Default value: 180 (18V), 0xB4 Range: 160-200'},
 '0223': {'name': 'UUID filter for BLE accessories',
          'length': 6,
          'length_type': 'fixed',
          'default_hex': '01030001FFFF',
          'default': '01030001FFFF',
          'query_rule': 'hex_string',
          'description': 'This parameter is used to filter the target BLE accessories. Byte 0-3: The detailed UUID If '
                         'some bytes are not used, please fill in 0xFF in the end. Byte 4: AD Type 0x02: Incomplete '
                         'List of 16-bit Service Class UUIDs 0x03: Complete List of 16-bit Service Class UUIDs 0x04: '
                         'Incomplete List of 32-bit S'},
 '0224': {'name': 'Local name filter for BLE accessories',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '010803313031',
          'default': '010803313031',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'This parameter is used to filter the target BLE accessories. Format: TALxxxxxx T (1 byte): '
                         'the device corresponding to this configuration 0x00: BLE tire sensor 1 0x01: BLE temerature '
                         'humidity sensor 1 A (1 byte): AD type 0x08: Shortened Local Name 0x09: Complete Local Name L '
                         '(1 byte): the length of '},
 '0225': {'name': 'Report frequency for BLE tire sensor',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0001',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is used to set the report frequency for BLE tire sensor data, aka the message '
                         '(06, 02). Unit: minute Precision: 3 Offset: 0 Range: 1-480 Default value: 3 minutes, 0x0001. '
                         '(means report once every 3 minutes)'},
 '0227': {'name': 'Relay control',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is used to turn on/off the relay. 0x00: Turn on the relay. 0x01: Turn off the '
                         'relay. Note: 0x01 can be set successful when the vechile is IGN off. Default value is 0x00. '
                         'This parameter supports to set/inquiry.'},
 '0228': {'name': 'Switch for sensor data (normal)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable to report sensor data (normal) 0x01: Enable to report sensor data (normal) '
                         'Default value: Disable, 0x00.'},
 '0229': {'name': 'Switch for sensor data (event)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable to report sensor data (event) 0x01: Enable to report sensor data (event) '
                         'Default value: Disable, 0x00.'},
 '022A': {'name': 'GPS report frequency 2',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '000F',
          'default': 15,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: Degree default value: 15 degrees, 0x000F. Range: 1-360 For example, If it '
                         'is set as 15, then device will report 1 GPS position points when hearding is changed more '
                         'than 15 degrees.'},
 '022B': {'name': 'GPS report frequency 3',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0064',
          'default': 100,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: meter default value: 100 m, 0x0064 Range: 100-2000 For example, If it is '
                         'set as 100, then device will report 1 GPS position points when the distance from last '
                         'position is more than 100 meters.'},
 '022C': {'name': 'Enable/Disable the “Sensor Data for Debugging” Message Report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to enable or disable the message “Sensor Data for Debugging” '
                         'report. Definition: 0x00: Disable to report 0x01: Enable to report Default valus is 0x00.'},
 '0230': {'name': 'Switch for Jamming Detection Event',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable or disable the Jamming Detection Event report. 0x00: Disable '
                         '0x01: Enable Default value: Disable, 0x00.'},
 '0231': {'name': 'Workmode Switch for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to switch the workmode for GL103. 0x01: Workmode 1 0x02: Workmode 2 0x03: '
                         'Workmode 3 0x04: Workmode 4 Default value: Workmode 1, 0x01.'},
 '0232': {'name': 'Workmode 1:  The interval to wakeup from sleep to active 1, for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '18',
          'default': 24,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to set the wakeup interval for GL103 when it is in Workmode 1 (sleep to '
                         'active 1). Unit: Hour Precision: 1 Default value: 24 hours, 0x18 Range: 1-36'},
 '0233': {'name': 'The switch to enable/disable device tamper warning, for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable/disable device tamper warning for GL103. 0x00: Disable 0x01: '
                         'Enable Default value: Disable, 0x00'},
 '0235': {'name': 'Workmode 2: The interval to wakeup from sleep to active 3, for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '03',
          'default': 3,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to set the wakeup interval for GL103 when it is in Workmode 2 (sleep to '
                         'active 3). Unit: Hour Precision: 1 Default value: 3 hours, 0x03 Range: 1-24 Note: The value '
                         'of 0x0234 shall be <= the value of 0x0235.'},
 '0236': {'name': 'The safety range of temperature for temperature warning',
          'length': 4,
          'length_type': 'fixed',
          'default_hex': '009600DC',
          'default': '009600DC',
          'query_rule': 'hex_string',
          'description': 'This parameter is to set the safety range of temperature. Unit: degrees celsius Precision: '
                         '0.1 Offset: -40 The byte 2-3 is the minimum of the safety range. For example, the 0x00FA in '
                         'the example. The byte 0-1 is the maximum of the safety range. For example, the 0x01E0 in the '
                         'example. Default value f'},
 '0237': {'name': 'The switch to enable/disable temperature warning report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'The switch to enable/disable temperature warning report. 0x00: Disable 0x01: Enable Default '
                         'value: Disable, 0x00 Note: For GL103, If the parameter 0x02550000 is disabled, then this '
                         'parameter is not valid.'},
 '0238': {'name': 'Workmode 3: The interval to switch from active 4 to active 1, for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '1E',
          'default': 30,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to set the interval for GL103 when it is in Workmode 3 (active 4 to active '
                         '1). Unit: Minutes Precision: 1 Default value: 30 minutes, 0x1E Range: 15-180'},
 '0239': {'name': 'The switch to enable/disable air pressure warning report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'The switch to enable/disable air pressure warning report. 0x00: Disable 0x01: Enable Default '
                         'value: Enable, 0x01 Note: If the parameter 0x02560000 is disabled, then this parameter is '
                         'not valid.'},
 '023A': {'name': 'The threshold for air pressure warning',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '03F5',
          'default': 1013,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: mbar Default value: 1013 mbar, 0x03F5 Range: 300-1250'},
 '023B': {'name': 'Change the IP address and port of AGPS server',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '167561676e73732e616c6c79737461722e636f6d3a3830',
          'default': 'uagnss.allystar.com:80',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'set_rule': 'ascii_with_len',
          'description': 'Format: Lxxx.xxx.xxx.xxx:yyyy L(1byte): the length of IP address and the port. Note: The '
                         'length “L” cannot be larger than 63 Bytes.'},
 '023C': {'name': 'GPS report frequency (for Router)',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '003C',
          'default': 60,
          'query_rule': 'hex_to_int',
          'description': 'Precision: 1 Unit: minute Default value: 60 minutes, 0x003C Range: 1-1440 Notes: If it is '
                         'set as 6, then device will report 1 GPS position point every 6 minutes.'},
 '023D': {'name': 'The switch to enable/disable ambient light warning, for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable/disable device ambient light warning for GL103. 0x00: Disable '
                         '0x01: Enable Default value: Disable, 0x00'},
 '0240': {'name': 'Wifi SSID  for WiFi 5GHz',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': 'NULL',
          'default': 'NULL',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'Wifi SSID for WiFi 5GHz Format: Lxxxxxxxxxx L(1byte): the byte length of Wifi SSID.'},
 '0241': {'name': 'Wifi Password for WiFi 5GHz',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': 'NULL',
          'default': 'NULL',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'Wifi Password for WiFi 5GHz Format: Lxxxxxxxxxx L(1byte): the byte length of Wifi Password.'},
 '0247': {'name': 'Threshold for internal battery voltage warning',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '1B',
          'default': 2.7,
          'query_rule': 'hex_to_int_x0.1',
          'description': 'Precision: 0.1 Unit: Volt Default value: 28 (2.8V), 0x1B Range: 20-120'},
'024A': {'name': 'APN Setting 2',
         'length': None,
         'length_type': 'dynamic',
         'default_hex': 'NULL',
         'default': '3gnet,NULL,NULL',  # 格式：APN,用户名,密码
         'query_rule': 'parse_apn_user_pass',
         'set_rule': 'apn_user_pass',
         'description': 'Format: LAxxxxxxxxxxBxxxxCxxx L(1byte): 总长度 A:APN长度 B:用户名长度 C:密码长度'},
 '0250': {'name': 'Factory reset with ACK',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01 - factory reset include clear offline data Note: Device shall send ACK to server if set '
                         'with this parameter.'},
 '0251': {'name': 'Reboot with ACK',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01 - reboot devive,include “modem” and “MCU” Note: Device shall send ACK to server if set '
                         'with this parameter.'},
 '0252': {'name': 'Enable/Disable BLE Tire sensor function',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable/disable the BLE tire sensor function. 0x00: Disable 0x01: Enable '
                         'Default value: Disable, 0x00'},
 '0253': {'name': 'For GL103: Switch to enable/disable tracking mode',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable tracking mode 0x01: Enable tracking mode Default value: Disable, 0x00 Note: If '
                         'the platform set this parameter to 0x01, then device will enter tracking mode, to report GPS '
                         'frame. The report frequency shall follow the parameter “0x000B0000”. This parameter is ONLY '
                         'valid for workmode 1.'},
 '0254': {'name': 'GL103 Workmode 4: The Mac address to scan',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '060800200A8C6D',
          'default': '060800200A8C6D',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'Format: L(Mac1)(Mac2)… L(1 Byte): the length of Mac address. Each Mac address is 6 bytes, in '
                         'HEX. Note: It will be rewritten everytime server config it. “L” is no more than 60 Bytes, '
                         'represents 10 MAC addresses.'},
 '0255': {'name': 'GL103 Workmode 1: Enable/Disable the temperature report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This switch is to enable or disable the collection and report for temperature data in GL103 '
                         'workmode 1 0x00: Disable 0x01: Enable Default value: Disable, 0x00'},
 '0256': {'name': 'GL103 Workmode 1: Enable/Disable the Air Pressure report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This switch is to enable or disable the collection and report for Air Pressure data in GL103 '
                         'workmode 1 0x00: Disable 0x01: Enable Default value: Disable, 0x00'},
 '0257': {'name': 'GL103 Workmode 4: The time interval to wake-up',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '05',
          'default': 5,
          'query_rule': 'hex_to_int',
          'description': 'The time interval to wake-up and scan the BLE broadcast, when GL103 is in workmode 4. Unit: '
                         'Minutes Precision: 1 Offset: 0 Range: 3-60 Default value: 5 minutes, 0x05 Note: This '
                         'parameter shall be effective from next wake-up.'},
 '0270': {'name': 'WiFi ON/OFF',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'Bit 0: 2.4GHz Bit 1: 5GHz Definition: 0: OFF 1: ON For example, 0x01 means ONLY 2.4GHz WiFi '
                         'is ON. 0x00 means 2.4GHz and 5GHz WiFi is OFF. Please note: For GD506, WiFi 2.4GHz and 5GHz '
                         'cannot be ON at the same time.'},
 '0271': {'name': 'GPS report enable/disable (for Router)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable or disable the GPS frame report. 0x00: Disable 0x01: Enable '
                         'Default value: Disable, 0x00.'},
 '0272': {'name': 'Modem Chipset temperature warning threshold (for Router)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '6E',
          'default': 110,
          'query_rule': 'hex_to_int',
          'description': 'Unit: degrees celsius Precision: 1 Offset: 0 Data range: 50-115 Default value: 110 degree '
                         'celsius, 0x6E.'},
 '0273': {'name': 'Soft Reset (for Router)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01 – Soft reset the device. Note: For router, it is Soft Reset.'},
 '0274': {'name': 'Time Interval for checking new update package (for Router)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '18',
          'default': 24,
          'query_rule': 'hex_to_int',
          'description': 'Unit: Hour Precision: 1 Offset: 0 Data range: 1-168 Default value: 24 hours, 0x18'},
 '0275': {'name': 'Enable/Disable Log report function (for Router)',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '00',
          'default': '00',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'This parameter is to enable/disable the log report function. 0x00: Disable 0x01: Enable '
                         'Default value: Disable, 0x00'},
 '0276': {'name': 'SIM card switch to SIM1 when SIM2 is used (for Router)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable or disable the funtion as below. If SIM card was changed to SIM2 '
                         'automatically (not by user manual switch, then device start a timer to monitor it, if this '
                         'status maintain for a time interval (defined in 0x02770000), then switch to SIM 1 '
                         'automatically. Defintion: 0x00: Di'},
 '0277': {'name': 'The interval for Auto SIM switch (for Router)',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0168',
          'default': 360,
          'query_rule': 'hex_to_int',
          'description': 'The interval defintion: Unit: minute Precision: 1 Offset: 0 Data range: 1-1440 Default '
                         'value: 360 minutes, 0x0168.'},
 '0278': {'name': 'Heartbeat time interval (for Router)',
          'length': 4,
          'length_type': 'fixed',
          'default_hex': '00015180',
          'default': 86400,
          'query_rule': 'hex_to_int',
          'description': 'Unit: second Precision: 1 Offset: 0 Data range: 1-172800. Default value: 86400 seconds, '
                         '0x00015180'},
 '0279': {'name': 'Config the log level (for Router)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: INFO 0x01: DEBUG Other: reserved. Default value: INFO, 0x00.'},
 '0300': {'name': 'System time Sync Up',
          'length': 4,
          'length_type': 'fixed',
          'default_hex': '564EB453',
          'default': '564EB453',
          'query_rule': 'hex_string',
          'description': 'UTC time. The host machine sync up the system time to MCU. This frame shall be sent after '
                         'connection established each time. Example: 2020/11/20 13:49:7'},
 '0303': {'name': 'MCU Log Report',
          'length': 7,
          'length_type': 'fixed',
          'default_hex': '010104564EB453',
          'default': '010104564EB453',
          'query_rule': 'hex_string',
          'description': 'Byte order definition Byte 0: Log_Type 0x00: CAN Log. 0x01: Device Key Message. Others: '
                         'Reserved. Byte 1: Log_Upload_Switch 0x00: Disable 0x01: Enable Others: Reserved Byte 2: '
                         'Reserved for Log_Level Byte 3-6: Log_Date UTC timestamp. It means to get the related date '
                         'key message log data from device. '},
 '0407': {'name': 'Change the IP address and port of Secondary Server (for IPv4)',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '203a30',
          'default': ' :0',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'set_rule': 'ascii_with_len',
          'description': 'Format: Lxxx.xxx.xxx.xxx:yyyy L(1byte): the length of IP address and the port. Note: The '
                         'length “L” cannot be larger than 63 Bytes.'},
 '040D': {'name': 'Server request to terminate current MCU FOTA task',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to request device to terminate current FOTA task. 0x01: '
                         'Terminate current MCU FOTA task'},
 '0414': {'name': 'Wifi ON/OFF for 5GHz',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Not controlled by the server 0x01: 5GHz HOTSPOT on 0x02: 5GHz HOTSPOT off Default '
                         'value: 0x00'},
 '0415': {'name': 'The time interval to report RS485 temperature humidity data',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0001',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'Unit: minute Precision: 15 Offset: 0 Range: 1-100 Default value: 15 minutes, 0x0001. Note: '
                         'The value shall be the multiple of 15 minutes, like 30/45/60.'},
 '0416': {'name': 'Enable/Disable to report RS485 temperature humidity data',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable 0x01: Enable Default value: Disable, 0x00'},
 '0417': {'name': 'Sleep mode',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Deep Sleep 0x01: Light Sleep 0x02: GPS Online Sleep Default value: Deep Sleep, 0x00'},
 '0418': {'name': 'Enable/Disable to report humidity warning',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable 0x01: Enable Default value: Disable, 0x00 Note: If the parameter 0x04160000 is '
                         'disabled, then this parameter 0x04180000 is not valid, the warning shall not be reported.'},
 '0419': {'name': 'The safety range of humidity for humidity warning',
          'length': 4,
          'length_type': 'fixed',
          'default_hex': '012C03E8',
          'default': '012C03E8',
          'query_rule': 'hex_string',
          'description': 'This parameter is to set the safety range of humidity. Unit: % Precision: 0.1 Offset: 0 The '
                         'byte 2-3 is the minimum of the safety range. For example, the 0x00FA in the example. The '
                         'byte 0-1 is the maximum of the safety range. For example, the 0x01E0 in the example. Default '
                         'value for GATH02: 30.0 to '},
 '041A': {'name': 'Force the sensor to re-learning',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': '0x01: force to re-learning.'},
 '041B': {'name': 'Enable/Disable the GPS debug message report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable 0x01: Enable Default value: Disable, 0x00'},
 '041C': {'name': 'Device working mode after the main power is disconnected',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to set the work mode after the main power supply is disconnected. 0x00: If '
                         'the device is disconnected from the main power, it will automatically enter transport mode '
                         'after five minutes. 0x01: Live unplug-tracking mode. If the device is disconnected from the '
                         'main power, it will cont'},
 '041D': {'name': 'Sleep wake-up cycle timer configuration for long term unplug-tracking mode',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '000F',
          'default': 15,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to set the sleep wake-up cycle timer for long term unplug-tracking mode. '
                         'Unit: minute Precision: 1 Offset: 0 Range: 5-1440 Default value: 15 minutes, 0x000F. Notes: '
                         'This parameter is valid only when the parameter 0x041C0000 is set as 0x02.'},
 '041E': {'name': 'Device Self Diagnostic',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '050000000000',
          'default': '050000000000',
          'query_rule': 'hex_to_ascii_dynamic_len',
          'description': 'This parameter is for device to diagnostic itself. Format: Lxxxxxx L is the length of data. '
                         'Xxxx please refer to the Chapter 2 of Section VI. It is only for inquirying, not support to '
                         'set.'},
 '041F': {'name': 'Enable/disable BLE tire warning report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable/disable the BLE tire warning report. 0x00: Disable 0x01: Enable '
                         'Default value: 0x00, disable.'},
 '0420': {'name': 'The low pressure threshold for BLE tire detection',
          'length': 4,
          'length_type': 'fixed',
          'default_hex': '0002BF20',
          'default': 180000,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for device to set the low BLE tire data threshold. Unit: Pa Precision: 1 '
                         'Offset: 0 Data range: 100000 to 300000 Pa Default value: 180000 Pa, 0x0002BF20'},
 '0421': {'name': 'Enable/Disable CAN parameter support status report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for device to enable/disable the message “CAN parameter support status” '
                         'report. 0x00: Disable to report the message. 0x01: Enable to report the message, and not '
                         'affect the CAN lib. 0x02: Enable to report the message, and restart the CAN lib, which means '
                         'to clean all flags/status in'},
 '0422': {'name': '1-wire iButton/RFID reader use case setting',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for device to set the 1-wire iButton use case. 0x00: Disable iButton and '
                         'RFID reader function 0x01: Enable iButton function. And only report iButton ID. 0x02: Enable '
                         'iButton function. And report iButton ID, and control DOUT wire relay. 0x03: Enable RFID '
                         'reader function. And only re'},
 '0425': {'name': 'The time interval to report BLE temperature humidity data',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0001',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'Unit: minute Precision: 15 Offset: 0 Range: 1-16 Default value: 15 minutes, 0x0001. Note: '
                         'The value shall be the multiple of 15 minutes, like 30/45/60.'},
 '0426': {'name': 'Enable/Disable to report BLE temperature humidity data',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable 0x01: Enable Others: Reserved. Default value: Disable, 0x00'},
 '0427': {'name': 'Choose the model of BLE THS',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'Bit 0: Reserverd (not used) Bit 1: GATH01 Bit 2: GAD01 Others: Reserved. Definition: 0: Not '
                         'supported 1: Supported. Default value: 0x00'},
 '0428': {'name': 'Enable/Disable to report BLE asset tag data',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': '0x00: Disable 0x01: Enable Others: Reserved. Default value: Disable, 0x00'},
 '0429': {'name': 'Choose the model of BLE asset tag',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'Bit 0: Reserved Bit 1: Reserved Bit 2: GABB03 Bit 3: GABB04 Others: Reserved. 0: Not '
                         'supported 1: Supported. Default value: 0x00'},
 '042A': {'name': 'The time interval to report BLE asset tag data',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '003C',
          'default': 60,
          'query_rule': 'hex_to_int',
          'description': 'Unit: second Precision: 1 Offset: 0 Range: 1-3600 Default value: 60 seconds, 0x003C.'},
 '042C': {'name': 'Enable/Disable to report “switched input detection”',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to Enable/Disable to report “switched input detection”. 0x00: Disable '
                         '0x01: Enable Default value: 0x00, disable.'},
 '042D': {'name': 'Enable/Disable to report “pulse detection”',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to Enable/Disable to report “pulse detection”. 0x00: Disable 0x01: Enable '
                         'Default value: 0x00, disable.'},
 '042E': {'name': 'Enable/Disable movement detection for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to Enable/Disable movement detection for GL103. 0x00: Disable 0x01: Enable '
                         'Default value: 0x00, disable.'},
 '042F': {'name': 'Sensor Coordinate System Configuration',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the sensor coordinate system which shall be used. 0x00: ISO '
                         '8855 0x01: SAE J670 Default value: 0x00.'},
 '0430': {'name': 'Network Type Setting (GL103 NTN)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the network type when device supports cellular and NTN. 0x00: '
                         'Cellular and NTN. Cellular is preferred. 0x01: Cellular only. 0x02: NTN only. Default value: '
                         '0x00'},
 '0431': {'name': 'GPS Distance for Network Switch (GL103 NTN)',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '64',
          'default': 100,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the distance which is used for network switch judgement, if '
                         'device support cellular and NTN network. Precision: 1 Unit: KM Default value: 0x64, 100KM '
                         'Data range: 1-255'},
 '0432': {'name': 'The input IO Configuration for Switched Input Detection',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0000',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the input IOs to support Switched Input Detection function. '
                         'The length is 2 bytes. And each bit represents one input IO. The bit value definition is: 0b '
                         '= Disable, 1b = Enable The mapping rule is: Byte 1 Bit 0: DIN1 Bit 1: DIN2 Bit 2: DIN3 Bit '
                         '3-7: reserved Byte 0 Bit '},
 '0433': {'name': 'The input IO Configuration for Pulse Detection',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the input IOs to support Pulse Detection function. The length '
                         'is 1 bytes. And each bit represents one input IO. The bit value definition is: 0b = Disable, '
                         '1b = Enable The mapping rule is: Bit 0: DIN1 Bit 1: DIN2 Bit 2: DIN3 Bit 3-7: reserved '
                         'Example: 0000 0011 = 0x03, '},
 '0434': {'name': 'BLE Relay Binding to Device',
          'length': None,
          'length_type': 'dynamic',
          'default_hex': '00',
          'default': '00',
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the Mac addresss of BLE relay to device. Then device could '
                         'one-to-one binding with the specific BLE relay. Definition is as follows. Format: '
                         'L(Mac1)(Mac2)… L(1 Byte): the length of Mac address. Each Mac address is 6 bytes, in HEX. '
                         'Default value is 0x00, which means no '},
 '0435': {'name': 'Device LED Control',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '05',
          'default': 5,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable or disable the LED indication. Here the LED means all of the '
                         'LEDs on device. 0x00: Disable. The device LED will be off all the time. 0x01: Device LED '
                         'always working, when device is in working mode. 0x02: Device LED will be off 5 minutes later '
                         'after device was installed, o'},
 '0436': {'name': 'The Input Configuration for SOS Warning Detection',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '0000',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to configure the input to support SOS Warning Detection function. The '
                         'length is 2 bytes. And each bit represents one input. The bit value definition is: 0b = '
                         'Disable, 1b = Enable The mapping rule is: Byte 0 Bit 0: DIN1 Bit 1: DIN2 Bit 2: DIN3 Bit '
                         '3-7: reserved Byte 1 Bit 0: BLE Key'},
 '0437': {'name': 'Enable/Disable to Report Message "Few Sensor Data"',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable/disable message “Few Sensor Data” report. Defintion: 0x00: '
                         'Disable 0x01: Enable Default is disable.'},
 '0438': {'name': 'Enable/Disable to Detect and Report “Warning Judged from Asensor Data”',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is to enable/disable to detect and report warning “Warning Judged from '
                         'Asensor Data”. Defintion: 0x00: Disable 0x01: Enable Default value is disable (0x00).'},
 '0439': {'name': 'Check Interval for Geo-fence',
          'length': 4,
          'length_type': 'fixed',
          'default_hex': '0000003C',
          'default': 60,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to configure the check interval of the geo-fence event. Unit: '
                         'Second Precision: 1 Offset: 0 Data range: 8-84600 Default value: 60'},
 '043A': {'name': 'Enable/Disable the “GPS Data” Message Report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to enable or disable the message “GPS Data” report. Definition: '
                         '0x00: Disable to report GPS message. 0x01: Enable to report GPS message. Default valus is '
                         '0x01.'},
 '043B': {'name': 'Enable/Disable the “LBS Data” Message Report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to enable or disable the message “LBS Data” report. Definition: '
                         '0x00: Disable to report LBS data. 0x01: Enable to report LBS data, only when "Device '
                         'Collection Data" message report. 0x02: Enable to report LBS data, including when "Device '
                         'Collection Data" message report, '},
 '043C': {'name': 'Enable/Disable the “Location Data” Message Report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to enable or disable the message “Location Data” report. '
                         'Definition: 0x00: Disable to report 0x01: Enable to report Default value is 0x00.'},
 '043D': {'name': 'Enable/Disable the “RAW CAN Frame” Message Active Report',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to enable or disable the message “RAW CAN Frame” active report. '
                         'If this parameter is set as 0x01, then device shall report the message “RAW CAN Frame” to '
                         'server periodically. Definition: 0x00: Disable to active report. 0x01: Enable to active '
                         'report. Default value is 0x00'},
 '043E': {'name': 'Report  frequency for “Configurable Data Flow” message',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '000F',
          'default': 15,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to configure the report frequency for “Configurable Data Flow” '
                         'message. Precision: 1 Unit: Second Default value: 15 seconds, 0x000F. Range: 5-43200'},
 '043F': {'name': 'Enable/Disable AGPS function',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to enable/disable the AGPS function on device. Definition: '
                         '0x00: AGPS function OFF. 0x01: AGPS funxtion ON. Default value: 0x00.'},
 '0440': {'name': 'The Report Interval in Default Mode for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '18',
          'default': 24,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to set the report interval for GL103, when device is in default '
                         'mode. Unit: Hour Precision: 1 Range: 1-36 Default value: 24'},
 '0441': {'name': 'The Data Collection Number in Default Mode for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to set the data collection number for GL103, when device is in '
                         'default mode. Unit: Time Precision: 1 Range: 1-30 Default value: 1'},
 '0442': {'name': 'The Report Interval in Motion Mode for GL103',
          'length': 2,
          'length_type': 'fixed',
          'default_hex': '012C',
          'default': 300,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to set the report interval for GL103, when device is in motion '
                         'mode. Unit: Second Precision: 1 Range: 10-3600 Default value: 300'},
 '0443': {'name': 'The Data Collection Number in Motion Mode for GL103',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '01',
          'default': 1,
          'query_rule': 'hex_to_int',
          'description': 'This parameter is for server to set the data collection number for GL103, when device is in '
                         'motion mode. Unit: Time Precision: 1 Range: 1-30 Default value: 1'},
 '0445': {'name': 'When to install the FOTA package if FOTA package download successfully',
          'length': 1,
          'length_type': 'fixed',
          'default_hex': '00',
          'default': 0,
          'query_rule': 'hex_to_int',
          'description': 'When to install the FOTA package if FOTA package download successfully. 0x00: to install the '
                         'FOTA package after IGN off for a while. 0x01: to install the FOTA package immediately. '
                         'Default value is 0x00. Notes: Here FOTA means all components FOTA, including MCU, BLE, '
                         'Modem, etc.'}}


# =========================================================
# 二、设置与查询配置
# =========================================================
# 这部分不使用 Excel/Word 自动生成，仍然按你原来的手动维护逻辑。
# query_rule 是查询返回值解析规则。
# set_rule 是下发设置值编码规则。
# set_hex_width 是设置值转 HEX 后补齐宽度。

SET_QUERY_CONFIG = {
    # ==========================================
    # 0000 系列 数字类型
    # ==========================================
    '0001': {'name': 'Threshold of rapid acceleration',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '10,100'},
    '0002': {'name': 'Threshold of rapid deceleration',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '10,100'},
    '0003': {'name': 'Threshold of sharp turn',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '25,60'},
    '0004': {'name': 'Fatigue driving',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '3600,18000'},
    '0005': {'name': 'Over Speed',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '50,249'},
    '0006': {'name': 'Low vehicle battery voltage warning 12V',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '80,120'},
    '0007': {'name': 'Wake vibration level',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,2,3,4,5,6,7'},
    '0008': {'name': 'Threshold of suspected collision',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '6,160'},
    '0009': {'name': 'Threshold of exceed idle',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '30,1200'},
    '000B': {'name': 'GPS report frequency 1',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '10,180'},
    '000C': {'name': 'Vehicle data report frequency',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '5,3600'},
    '000D': {'name': 'Wakeup DISTURBANCE info report time',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '0,300'},
    '000E': {'name': 'Heartbeat time',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,24'},
    '000F': {'name': 'Car Emissions',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '0,30'},
    '0010': {'name': 'Enable or Disable CAN Fuctions',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '0,1'},
    '0012': {'name': 'ASS setting',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,2'},
    '0018': {'name': 'Working time after ignition off',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '5,20'},

    # ==========================================
    # 0200 系列 字符串/数字混合
    # ==========================================
    '0200': {'name': 'Primary Server IP Port',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'xatst.richlinkcloud.com:8989'},
    '0201': {'name': 'Secondary Server IP Port',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0202': {'name': 'Wifi SSID 2.4GHz',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0203': {'name': 'Wifi Password 2.4GHz',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0204': {'name': 'Wifi router APN',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0206': {'name': 'Modem APN',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'cmnet'},
    '0207': {'name': 'Wifi ON / OFF for 2.4GHz',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': 'null'},
    '020F': {'name': 'Ignition ON/OFF judgement',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2,3,4'},
    '0220': {'name': 'Low voltage warning 24V',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '160,200'},
    '0223': {'name': 'UUID filter for BLE accessories',
             'length': 6,
             'length_type': 'fixed',
             'query_rule': 'hex_to_string',
             'set_rule': 'hex_string',
             'set_hex_width': 12,
             'set_default': 'null'},
    '0224': {'name': 'Local name filter for BLE accessories',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0225': {'name': 'BLE tire sensor report frequency',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,480'},
    '0228': {'name': 'Sensor data normal switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0229': {'name': 'Sensor data event switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '022A': {'name': 'GPS report frequency 2',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,360'},
    '022B': {'name': 'GPS report frequency 3',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '100,2000'},
    '022C': {'name': 'Sensor Data Debug switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0230': {'name': 'Jamming Detection switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2,3'},
    '0231': {'name': 'GL103 Workmode Switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,2,3,4'},
    '0232': {'name': 'GL103 Workmode1 wakeup interval',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1-36'},
    '0233': {'name': 'GL103 tamper warning switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0235': {'name': 'GL103 Workmode2 wakeup interval',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,24'},
    '0236': {'name': 'Temperature safety range',
             'length': 4,
             'length_type': 'fixed',
             'query_rule': 'two_int_from_hex4',
             'set_rule': 'two_int_to_hex4',
             'set_hex_width': 8,
             'set_default': '30|40'},
    '0237': {'name': 'Temperature warning switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0238': {'name': 'GL103 Workmode3 interval',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '15,180'},
    '0239': {'name': 'Air pressure warning switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '023A': {'name': 'Air pressure warning threshold',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '300,1250'},
    '023B': {'name': 'AGPS server IP Port',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'agps.test.com:8888'},
    '023C': {'name': 'Router GPS report frequency',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,1440'},
    '023D': {'name': 'GL103 ambient light warning switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0240': {'name': 'Wifi SSID 5GHz',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0241': {'name': 'Wifi Password 5GHz',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0247': {'name': 'Internal battery voltage warning',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '20,120'},
    '024A': {'name': 'APN Setting 2',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'parse_apn_user_pass',
             'set_rule': 'apn_user_pass',
             'set_hex_width': 0,
             'set_default': 'cmnet,admin,123456'},
    '0252': {'name': 'BLE Tire sensor function switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0253': {'name': 'GL103 tracking mode switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0254': {'name': 'GL103 Workmode4 MAC scan',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'null'},
    '0255': {'name': 'GL103 temperature report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0256': {'name': 'GL103 Air Pressure report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0257': {'name': 'GL103 Workmode4 wake-up interval',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '3,60'},
    '0270': {'name': 'WiFi ON/OFF',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': 'null'},
    '0271': {'name': 'Router GPS report enable',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0272': {'name': 'Modem Chipset temperature threshold',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '50,115'},
    '0274': {'name': 'Router update check interval',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,168'},
    '0275': {'name': 'Router Log report switch',
             'length': 1,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0276': {'name': 'Auto SIM switch enable',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0277': {'name': 'Auto SIM switch interval',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,1440'},
    '0278': {'name': 'Router Heartbeat time',
             'length': 4,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 8,
             'set_default': '1,172800'},
    '0279': {'name': 'Router log level',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},

    # ==========================================
    # 0400 系列
    # ==========================================
    '0407': {'name': 'Secondary Server IP Port',
             'length': None,
             'length_type': 'dynamic',
             'query_rule': 'hex_to_ascii_dynamic_len',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             'set_default': 'xatst.richlinkcloud.com:6666'},
    '0414': {'name': 'Wifi ON/OFF for 5GHz',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2'},
    '0415': {'name': 'RS485 temp humidity report interval',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,100'},
    '0416': {'name': 'RS485 temp humidity report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0417': {'name': 'Sleep mode',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2'},
    '0418': {'name': 'Humidity warning switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0419': {'name': 'Humidity safety range',
             'length': 4,
             'length_type': 'fixed',
             'query_rule': 'two_int_from_hex4',
             'set_rule': 'two_int_to_hex4',
             'set_hex_width': 8,
             'set_default': '300|1000'},
    '041B': {'name': 'GPS debug message switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '041C': {'name': 'Main power disconnect work mode',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2'},
    '041D': {'name': 'Long term unplug-tracking cycle',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '5,1440'},
    '041F': {'name': 'BLE tire warning report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0420': {'name': 'BLE tire low pressure threshold',
             'length': 4,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 8,
             'set_default': '100000,300000'},
    '0421': {'name': 'CAN parameter status report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2'},
    '0422': {'name': 'iButton/RFID use case',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2,3,4,5,6'},
    '0425': {'name': 'BLE temp humidity report interval',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,16'},
    '0426': {'name': 'BLE temp humidity report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0427': {'name': 'BLE THS model select',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2,3'},
    '0428': {'name': 'BLE asset tag report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0429': {'name': 'BLE asset tag model select',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,12'},
    '042A': {'name': 'BLE asset tag report interval',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '1,3600'},
    '042C': {'name': 'Switched input detection switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '042D': {'name': 'Pulse detection switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '042E': {'name': 'GL103 movement detection switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '042F': {'name': 'Sensor Coordinate System',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0430': {'name': 'GL103 Network Type',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2'},
    '0431': {'name': 'GPS Distance for Network Switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,255'},
    '0432': {'name': 'Switched Input IO Config',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '0301'},
    '0433': {'name': 'Pulse Detection IO Config',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '03'},
    "0434": {"name": "BLE Relay Binding",
            "length": None,
            "length_type": "dynamic",
            "query_rule": "parse_raw_hex_with_len",
            "set_rule": "set_raw_hex_with_len",
            "set_hex_width": 0,
            "set_default": "1A2B3C4D5F6E"},
    '0435': {'name': 'Device LED Control',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2,3,4,5'},
    '0436': {'name': 'SOS Warning Input Config',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '0103'},
    '0437': {'name': 'Few Sensor Data report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0438': {'name': 'Asensor Data warning switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0439': {'name': 'Geo-fence Check Interval',
             'length': 4,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 8,
             'set_default': '8,84600'},
    '043A': {'name': 'GPS Data report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '043B': {'name': 'LBS Data report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1,2'},
    '043C': {'name': 'Location Data report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '043D': {'name': 'RAW CAN Frame report switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '043E': {'name': 'Configurable Data Flow report interval',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '5,43200'},
    '043F': {'name': 'AGPS function switch',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '0,1'},
    '0440': {'name': 'GL103 Default Mode Report Interval',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,36'},
    '0441': {'name': 'GL103 Default Mode Data Collection Num',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,30'},
    '0442': {'name': 'GL103 Motion Mode Report Interval',
             'length': 2,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             'set_default': '10,3600'},
    '0443': {'name': 'GL103 Motion Mode Data Collection Num',
             'length': 1,
             'length_type': 'fixed',
             'query_rule': 'hex_to_int',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             'set_default': '1,30'}
}

# =========================================================
# 三、非法值设置配置
# =========================================================
# 这部分也单独维护，不和默认值查询共用。
# 非法值设置只判断 F102 返回状态：
# line[58:62] == F102
# line[62:66] == KEY
# line[66:68] == 00 -> PASS，否则 FAIL。

ILLEGAL_SET_CONFIG = {
    # ==========================================
    # 0000 系列
    # ==========================================
    '0001': {'name': 'Threshold of rapid acceleration illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "9,101"},
    '0002': {'name': 'Threshold of rapid deceleration illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "9,101"},
    '0003': {'name': 'Threshold of sharp turn illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "24,61"},
    '0004': {'name': 'Fatigue driving illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "3599,18001"},
    '0005': {'name': 'Over Speed illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "49,250"},
    '0006': {'name': 'Low vehicle battery voltage warning 12V illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "79,121"},
    '0007': {'name': 'Wake vibration level illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,8"},
    '0008': {'name': 'Threshold of suspected collision illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "5,161"},
    '0009': {'name': 'Threshold of exceed idle illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "29,1201"},
    '000B': {'name': 'GPS report frequency 1 illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "9,181"},
    '000C': {'name': 'Vehicle data report frequency illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "4,3601"},
    '000D': {'name': 'Wakeup DISTURBANCE info report time illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "301,302"},
    '000E': {'name': 'Heartbeat time illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,25"},
    '000F': {'name': 'Car Emissions illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "31,32"},
    '0010': {'name': 'Enable or Disable CAN Fuctions illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "2,3"},
    '0012': {'name': 'ASS setting illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '0018': {'name': 'Working time after ignition off illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "4,21"},

    # ==========================================
    # 0200 系列
    # ==========================================
    '0200': {'name': 'Primary Server IP Port illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "fail.fail@123!@$^#"},
    '0201': {'name': 'Secondary Server IP Port illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0202': {'name': 'Wifi SSID 2.4GHz illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0203': {'name': 'Wifi Password 2.4GHz illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0204': {'name': 'Wifi router APN illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0206': {'name': 'Modem APN illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "1A2B3C4D5F.1A2B3C4D5F.1A2B3C4D5F.1A2B3C4D5F.1A2B3C4D5F.1A2B3C4D5F"},
    '0207': {'name': 'Wifi ON / OFF for 2.4GHz illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '020F': {'name': 'Ignition ON/OFF judgement illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "5,6"},
    '0220': {'name': 'Low voltage warning 24V illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "159,201"},
    '0223': {'name': 'UUID filter for BLE accessories illegal',
             'set_rule': 'hex_string',
             'set_hex_width': 12,
             "set_default": "null"},
    '0224': {'name': 'Local name filter for BLE accessories illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0225': {'name': 'BLE tire sensor report frequency illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,481"},
    '0228': {'name': 'Sensor data normal switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0229': {'name': 'Sensor data event switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '022A': {'name': 'GPS report frequency 2 illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,361"},
    '022B': {'name': 'GPS report frequency 3 illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "99,2001"},
    '022C': {'name': 'Sensor Data Debug switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0230': {'name': 'Jamming Detection switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "4,5"},
    '0231': {'name': 'GL103 Workmode Switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,5"},
    '0232': {'name': 'GL103 Workmode1 wakeup interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,37"},
    '0233': {'name': 'GL103 tamper warning switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0235': {'name': 'GL103 Workmode2 wakeup interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,25"},
    '0236': {'name': 'Temperature safety range illegal',
             'set_rule': 'two_int_to_hex4',
             'set_hex_width': 8,
             "set_default": "0|65535"},
    '0237': {'name': 'Temperature warning switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0238': {'name': 'GL103 Workmode3 interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "14,181"},
    '0239': {'name': 'Air pressure warning switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '023A': {'name': 'Air pressure warning threshold illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "299,1251"},
    '023B': {'name': 'AGPS server IP Port illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "failagps00failagps00failagps00failagps00failagps0012345.test.com:66666"},
    '023C': {'name': 'Router GPS report frequency illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,1441"},
    '023D': {'name': 'GL103 ambient light warning switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0240': {'name': 'Wifi SSID 5GHz illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0241': {'name': 'Wifi Password 5GHz illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0247': {'name': 'Internal battery voltage warning illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "19,121"},
    '024A': {'name': 'APN Setting 2 illegal',
             'set_rule': 'apn_user_pass',
             'set_hex_width': 0,
             "set_default": "cmnetcmnetcmnetcmnetcmnetcmnetcmnetcmnetcmnetcmnet,admin,123456"},
    '0252': {'name': 'BLE Tire sensor function switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0253': {'name': 'GL103 tracking mode switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0254': {'name': 'GL103 Workmode4 MAC scan illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "null"},
    '0255': {'name': 'GL103 temperature report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0256': {'name': 'GL103 Air Pressure report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0257': {'name': 'GL103 Workmode4 wake-up interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,61"},
    '0270': {'name': 'WiFi ON/OFF illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "null"},
    '0271': {'name': 'Router GPS report enable illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0272': {'name': 'Modem Chipset temperature threshold illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "49,116"},
    '0274': {'name': 'Router update check interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,169"},
    '0275': {'name': 'Router Log report switch illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "2,3"},
    '0276': {'name': 'Auto SIM switch enable illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0277': {'name': 'Auto SIM switch interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,1441"},
    '0278': {'name': 'Router Heartbeat time illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 8,
             "set_default": "0,172801"},
    '0279': {'name': 'Router log level illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},

    # ==========================================
    # 0400 系列
    # ==========================================
    '0407': {'name': 'Secondary Server IP Port illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "failxatst.richlinkcloudrichlinkcloudrichlinkcloudrichlinkcloud.com:66666"},
    '0414': {'name': 'Wifi ON/OFF for 5GHz illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '0415': {'name': 'RS485 temp humidity report interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,101"},
    '0416': {'name': 'RS485 temp humidity report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0417': {'name': 'Sleep mode illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '0418': {'name': 'Humidity warning switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0419': {'name': 'Humidity safety range illegal',
             'set_rule': 'two_int_to_hex4',
             'set_hex_width': 8,
             "set_default": "300|65535"},
    '041B': {'name': 'GPS debug message switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '041C': {'name': 'Main power disconnect work mode illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '041D': {'name': 'Long term unplug-tracking cycle illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "4,1441"},
    '041F': {'name': 'BLE tire warning report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0420': {'name': 'BLE tire low pressure threshold illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 8,
             "set_default": "99999,300001"},
    '0421': {'name': 'CAN parameter status report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '0422': {'name': 'iButton/RFID use case illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "7,8"},
    '0425': {'name': 'BLE temp humidity report interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,17"},
    '0426': {'name': 'BLE temp humidity report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0427': {'name': 'BLE THS model select illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "4,5"},
    '0428': {'name': 'BLE asset tag report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0429': {'name': 'BLE asset tag model select illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "13,14"},
    '042A': {'name': 'BLE asset tag report interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "0,3601"},
    '042C': {'name': 'Switched input detection switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '042D': {'name': 'Pulse detection switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '042E': {'name': 'GL103 movement detection switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '042F': {'name': 'Sensor Coordinate System illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0430': {'name': 'GL103 Network Type illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '0431': {'name': 'GPS Distance for Network Switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,256"},
    '0432': {'name': 'Switched Input IO Config illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "99"},
    '0433': {'name': 'Pulse Detection IO Config illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "99"},
    '0434': {'name': 'BLE Relay Binding illegal',
             'set_rule': 'ascii_with_len',
             'set_hex_width': 0,
             "set_default": "1Z2Z3Z4Z5Z6Z"},
    '0435': {'name': 'Device LED Control illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "6,7"},
    '0436': {'name': 'SOS Warning Input Config illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "99"},
    '0437': {'name': 'Few Sensor Data report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0438': {'name': 'Asensor Data warning switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0439': {'name': 'Geo-fence Check Interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 8,
             "set_default": "7,84601"},
    '043A': {'name': 'GPS Data report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '043B': {'name': 'LBS Data report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "3,4"},
    '043C': {'name': 'Location Data report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '043D': {'name': 'RAW CAN Frame report switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '043E': {'name': 'Configurable Data Flow report interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "4,43201"},
    '043F': {'name': 'AGPS function switch illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "2,3"},
    '0440': {'name': 'GL103 Default Mode Report Interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,37"},
    '0441': {'name': 'GL103 Default Mode Data Collection Num illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0,31"},
    '0442': {'name': 'GL103 Motion Mode Report Interval illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 4,
             "set_default": "9-3601"},
    '0443': {'name': 'GL103 Motion Mode Data Collection Num illegal',
             'set_rule': 'int_to_hex',
             'set_hex_width': 2,
             "set_default": "0-31"}
}


# =========================================================
# Project supported KEY config
# Generated from Excel sheet "Parameters":
# 1. Column C GoTrack = Yes
# 2. Column H Write/Read = Yes
# 3. Project columns follow the previous code order
# 4. GO TRACK uses the GoTrack column; GD201 uses Excel column GD201E
# 5. Column B Parameter Number: 0x00010000 -> 0001

PROJECT_KEYS = {
    'GO TRACK': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0202', '0203', '0206',
        '0207', '020F', '0220', '0223', '0224', '0225', '0227', '0228', '0229', '022A',
        '022B', '022C', '0230', '0231', '0232', '0233', '0235', '0236', '0237', '0238',
        '0239', '023A', '023B', '023C', '023D', '0240', '0241', '0247', '024A', '0252',
        '0253', '0254', '0255', '0256', '0257', '0270', '0271', '0272', '0274', '0275',
        '0276', '0277', '0278', '0279', '0300', '0407', '0415', '0416', '0417', '0418',
        '0419', '041B', '041C', '041D', '041F', '0420', '0421', '0422', '0425', '0427',
        '0429', '0426', '0428', '042A', '042C', '042D', '042E', '042F', '0430', '0431',
        '0432', '0433', '0434', '0435', '0436', '0437', '0438', '0439', '043A', '043B',
        '043C', '043D', '043E', '043F', '0440', '0441', '0442', '0443', '0444', '0445',
        '0449', '044A', '044B', '044C'
    ],
    'mojio': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0202', '0203', '0206',
        '0207', '0407'
    ],
    'GPSI': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '024A', '0427'
    ],
    'GD105': [
        '0004', '0005', '0006', '0009', '000C', '0010', '0012', '0018', '0220', '0300',
        '0421', '0445'
    ],
    'GL103': [
        '000B', '0200', '0206', '0231', '0232', '0233', '0235', '0236', '0237', '0238',
        '0239', '023A', '023B', '023D', '0247', '024A', '0253', '0254', '0255', '0256',
        '0257', '042E', '0430', '0431', '0438', '043A', '043B', '043C', '0440', '0441',
        '0442', '0443', '0444', '044A'
    ],
    'GD201': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '0220', '0225',
        '0228', '0229', '022A', '022B', '0230', '0236', '0237', '023B', '024A', '0252',
        '0417', '0418', '0419', '041C', '041D', '041F', '0420', '0421', '0425', '0427',
        '0429', '0426', '0428', '042A', '042F'
    ],
    'GD202': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0220', '0225', '0228',
        '0229', '022A', '022B', '0230', '0236', '0237', '023B', '024A', '0252', '0407',
        '0417', '0418', '0419', '041C', '041D', '041F', '0420', '0421', '0425', '0427',
        '0429', '0426', '0428', '042A', '042F', '0434', '0435', '0439', '043D', '043E',
        '043F', '0445'
    ],
    'GD302': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '0220', '0225',
        '0228', '0229', '022A', '022B', '024A', '0252'
    ],
    'GD303': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '0220', '0225',
        '0228', '0229', '022A', '022B', '0230', '0236', '0237', '023B', '024A', '0252',
        '0417', '0418', '0419', '041C', '041D', '041F', '0420', '0421', '0425', '0427',
        '0429', '0426', '0428', '042A', '042F', '0435'
    ],
    'GD506': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0202', '0203', '0206',
        '0220', '0225', '0228', '0229', '022A', '022B', '0230', '0236', '0237', '023B',
        '0240', '0241', '024A', '0252', '0270', '0417', '0418', '0419', '041C', '041D',
        '041F', '0420', '0421', '0425', '0427', '0429', '0426', '0428', '042A', '042F',
        '044B', '044C'
    ],
    'GT115': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '0220', '0225',
        '0227', '0228', '0229', '022A', '022B', '024A', '0252'
    ],
    'GT117': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '0220', '0225',
        '0227', '0228', '0229', '022A', '022B', '022C', '0230', '0236', '0237', '023B',
        '024A', '0252', '0415', '0416', '0417', '0418', '0419', '041C', '041D', '041F',
        '0420', '0421', '0422', '0425', '0427', '0429', '0426', '0428', '042A', '042F',
        '0432', '0433', '0434'
    ],
    'GT118': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0010', '0012', '0018', '0200', '0206', '0220', '0225',
        '0227', '0228', '0229', '022A', '022B', '0230', '0236', '0237', '023B', '024A',
        '0252', '0407', '0415', '0416', '0417', '0418', '0419', '041C', '041D', '041F',
        '0420', '0421', '0422', '0425', '0427', '0429', '0426', '0428', '042A', '042F',
        '0432', '0433', '0434', '0435', '0436', '0439', '043A', '043B', '043D', '043E'
    ],
    'GT119': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000D', '000E', '0012', '0018', '0200', '0206', '0220', '0225', '0228', '0229',
        '022A', '022B', '023B', '0252'
    ],
    'GT161': [
        '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '000B',
        '000C', '000D', '000E', '0012', '0018', '0200', '0206', '0220', '0225', '0227',
        '0228', '0229', '022A', '022B', '0230', '0236', '0237', '023B', '024A', '0252',
        '0407', '0417', '0418', '0419', '041F', '0420', '0425', '0427', '0429', '0426',
        '0428', '042A', '042F', '0432', '0433', '0435', '0436', '0439', '043A', '043B',
        '043F'
    ],
    'GR521': [
        '023C', '0270', '0271', '0272', '0275', '0276', '0277', '0278', '0279'
    ],
    'GR531': [
        '023C', '0270', '0271', '0272', '0275', '0276', '0277', '0278', '0279'
    ],
    'TEST-SET':[
    '024A','0230','0407','023B'
    ]
}

# Default query and set/query share the same project list.
PROJECT_DEFAULT_KEYS = PROJECT_KEYS
PROJECT_SET_KEYS = PROJECT_KEYS

# Keys listed here are removed from illegal-value setting for every project.
# Add globally unsupported illegal-value keys here, for example: '0227'.
# 过滤非法值的参数
ILLEGAL_EXCLUDE_KEYS = [
    '0427','0429','0432', '0433', '0436',
]

PROJECT_ILLEGAL_KEYS = {
    project: [key for key in keys if key not in ILLEGAL_EXCLUDE_KEYS]
    for project, keys in PROJECT_KEYS.items()
}


SEND_URL = "http://10.85.40.3:8088/client/send"
QUERY_URL = "http://10.85.40.3:8082/testAPI/rawData"
SAVE_DIR = r"D:\python脚本生成文件集\参数下发查询"


# =========================================================
# 五、通用工具函数
# =========================================================

def ascii_to_decimal(hex_str):
    """HEX ASCII 转字符串，用于解析 IMEI。"""
    try:
        return bytes.fromhex(hex_str).decode("ascii")
    except Exception:
        return ""


def utc_ms_now():
    """获取当前 UTC 毫秒时间戳。"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def open_save_dir():
    """生成 Excel 后自动打开保存目录。"""
    try:
        os.startfile(SAVE_DIR)
    except Exception:
        pass


def get_current_config(mode):
    """根据功能模式选择配置表。"""
    if mode == "默认值查询":
        return DEFAULT_QUERY_CONFIG
    elif mode == "设置与查询":
        return SET_QUERY_CONFIG
    else:
        return ILLEGAL_SET_CONFIG


def build_query_cmd(key):
    """查询命令：F103 + KEY。"""
    return f"F103{key}".upper()

# 参数设置与查询 设置参数
def encode_set_value(value, rule, width):
    """
    设置值编码。

    int_to_hex：
    输入十进制 40，转成 HEX 28。
    width=2，结果为 28。
    width=4，结果为 0028。
    """
    if rule == "int_to_hex":
        value_int = int(str(value).strip())
        return format(value_int, "X").zfill(width).upper()
    elif rule == "ascii_with_len":
        """
        字符串转ASCII + 长度

        例如：
        xatst.richlinkcloud.com:8989

        ->
        1C78617473742E726963686C696E6B636C6F75642E636F6D3A38393839
        """

        text = str(value)
        ascii_hex = text.encode("ascii").hex().upper()

        text_len = len(text)
        len_hex = format(text_len, "02X")

        return len_hex + ascii_hex
    elif rule == "two_int_to_hex4":
        """
        两个十进制数 → 各占2字节HEX

        输入:
        30|40

        输出:
        001E0028
        """
        parts = str(value).split("|")

        if len(parts) != 2:
            raise ValueError("格式应为 30|40")

        v1 = int(parts[0])
        v2 = int(parts[1])

        return format(v1, "04X") + format(v2, "04X")
    elif rule == "apn_user_pass":
        """
        APN,user,password

        cmnet,admin,123456

        ->

        1305636D6E65740561646D696E06313233343536
        """

        parts = [s.strip() for s in str(value).split(",")]

        if len(parts) != 3:
            raise ValueError("格式应为 apn,user,password")

        result = ""

        for text in parts:
            length_hex = format(len(text), "02X")
            ascii_hex = text.encode("ascii").hex().upper()
            result += length_hex + ascii_hex

        total_len = len(result) // 2
        total_len_hex = format(total_len, "02X")

        return total_len_hex + result

    elif rule == "set_raw_hex_with_len":
        """

        原始HEX + 长度


        1A2B3C4D5F6E


        ->


        061A2B3C4D5F6E

        """

        hex_str = str(value).replace(" ", "").upper()

        byte_len = len(hex_str) // 2

        len_hex = format(byte_len, "02X")

        return len_hex + hex_str

    raise ValueError(f"不支持的设置规则：{rule}")


def build_set_cmd(key, value, cfg):
    """
    设置命令组包：F102 + KEY + 0000 + VALUE_HEX。
    """
    value_hex = encode_set_value(value, cfg["set_rule"], cfg["set_hex_width"])
    return f"F102{key}0000{value_hex}".upper(), value_hex

# 参数设置查询，查询参数
def parse_query_value(value_hex, rule):
    """F103 查询返回值解析。"""
    value_hex = str(value_hex).replace(" ", "").upper()

    if rule == "hex_string":
        return value_hex

    elif rule == "hex_to_ascii_dynamic_len":
        # 动态长度字符串：第1字节是长度，后面才是真正内容
        try:
            # 第 0~1 位是长度 HEX
            length_hex = value_hex[0:2]
            data_len = int(length_hex, 16)

            # 从第 2 位开始，取 data_len * 2 个字符（真正的ASCII HEX）
            real_hex = value_hex[2: 2 + data_len * 2]

            # 转 ASCII
            return bytes.fromhex(real_hex).decode("ascii")
        except:
            return value_hex
    elif rule == "ascii_with_len":
        try:
            return bytes.fromhex(value_hex).decode("ascii")
        except Exception:
            return None
    elif rule == "two_int_from_hex4":
        """
        001E0028 -> 30|40
        """
        if len(value_hex) != 8:
            return value_hex

        v1 = int(value_hex[0:4], 16)
        v2 = int(value_hex[4:8], 16)

        return f"{v1}|{v2}"

    # ========================
    # 新增：解析 APN+用户+密码 复合格式
    # ========================
    elif rule == "parse_apn_user_pass":
        try:
            # 第1字节：总长度
            total_len = int(value_hex[0:2], 16)
            ptr = 2

            # A = APN 长度
            a_len = int(value_hex[ptr:ptr + 2], 16)
            ptr += 2
            apn_hex = value_hex[ptr:ptr + a_len * 2]
            apn = bytes.fromhex(apn_hex).decode("ascii")
            ptr += a_len * 2

            # B = 用户名长度
            b_len = int(value_hex[ptr:ptr + 2], 16)
            ptr += 2
            user_hex = value_hex[ptr:ptr + b_len * 2]
            user = bytes.fromhex(user_hex).decode("ascii")
            ptr += b_len * 2

            # C = 密码长度
            c_len = int(value_hex[ptr:ptr + 2], 16)
            ptr += 2
            pwd_hex = value_hex[ptr:ptr + c_len * 2]
            pwd = bytes.fromhex(pwd_hex).decode("ascii")

            return f"{apn},{user},{pwd}"
        except:
            return value_hex
    elif rule == "parse_raw_hex_with_len":
        """
        去掉前置长度字节，仅返回真实HEX
        """

        value_hex = value_hex.upper()

        if len(value_hex) < 2:
            return value_hex

        try:
            data_len = int(value_hex[:2], 16)

            real_hex = value_hex[2:2 + data_len * 2]

            return real_hex

        except:
            return value_hex


    try:
        raw_int = int(value_hex, 16)
    except Exception:
        return value_hex

    if rule == "hex_to_int":
        return raw_int

    if rule == "hex_to_int_x10":
        return raw_int * 10

    if rule == "hex_to_int_x0.1":
        return raw_int * 0.1

    match = re.match(r"hex_to_int_x0\.1_offset_(-?\d+(?:\.\d+)?)", str(rule))
    if match:
        return raw_int * 0.1 + float(match.group(1))

    return raw_int


def compare_value(expected, actual):
    """比对期望值和实际返回值。"""
    if actual is None or actual == "":
        return "FAIL"

    try:
        return "PASS" if float(expected) == float(actual) else "FAIL"
    except Exception:
        return "PASS" if str(expected).strip() == str(actual).strip() else "FAIL"


def send_cmd(imei, cmd):
    """调用 8088 接口发送命令。"""
    payload = {
        "imei": int(imei),
        "cmd": cmd
    }

    resp = requests.post(SEND_URL, json=payload, timeout=10)
    resp.raise_for_status()

    try:
        return resp.json()
    except Exception:
        return {}


def query_raw_data(imei, start_ms, stop_ms):
    """调用 8082 接口查询 rawData。"""
    payload = {
        "imei": int(imei),
        "start": start_ms,
        "stop": stop_ms,
        "offset": 0,
        "limit": 10000
    }

    resp = requests.post(QUERY_URL, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def extract_raw_data_list(resp_json):
    """递归提取接口返回里的 rawDataString。"""
    result = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "rawDataString":
                    result.append(str(v))
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(resp_json)
    return result


# =========================================================
# 六、F103 返回值解析
# =========================================================

def get_value_hex_from_line(line, cfg):
    """
    根据配置从 F103 返回中取 VALUE HEX。
    动态长度：第1字节是长度，后面跟着数据
    固定长度：直接取配置长度
    """
    length_type = cfg.get("length_type", "fixed")
    value_start = 66  # F103 返回固定从 66 开始

    # ==========================================
    # 动态长度解析（0200专用逻辑）
    # ==========================================
    if length_type == "dynamic" or cfg.get("length") is None:
        # 先读 1 字节长度
        if len(line) < value_start + 2:
            return ""

        len_hex = line[value_start:value_start + 2]
        try:
            data_len = int(len_hex, 16)
        except:
            return ""

        # 长度后面才是真正数据
        real_start = value_start + 2
        real_end = real_start + data_len * 2

        if len(line) < real_end:
            return ""

        # 返回：长度+内容（用于后续转 ASCII）
        return len_hex + line[real_start:real_end]

    # ==========================================
    # 固定长度解析（原来逻辑不变）
    # ==========================================
    value_hex_len = int(cfg["length"]) * 2
    value_end = value_start + value_hex_len

    if len(line) < value_end:
        return ""

    return line[value_start:value_end]


def find_f103_return_value(raw_list, imei, key, cfg):
    """
    查找 F103 查询返回值。

    判断规则：
    line[48:50] == 04
    line[58:62] == F103
    line[62:66] == KEY

    如果匹配多条，返回最后一条，认为最后一条是最新数据。
    """
    imei = str(imei)
    match_list = []

    for line in raw_list:
        line = line.replace(" ", "").upper()

        if len(line) < 68:
            continue

        if line[48:50] != "04":
            continue

        if line[58:62].upper() != "F103":
            continue

        line_imei = ascii_to_decimal(line[18:48])
        if line_imei != imei:
            continue

        return_key = line[62:66].upper()
        if return_key != key.upper():
            continue

        value_hex = get_value_hex_from_line(line, cfg)
        if value_hex == "":
            continue

        value = parse_query_value(value_hex, cfg.get("query_rule", "hex_to_int"))

        match_list.append({
            "value": value,
            "value_hex": value_hex,
            "raw_line": line
        })

    if not match_list:
        return None

    return match_list[-1]


# =========================================================
# 七、F102 非法值设置状态解析
# =========================================================

def find_f102_status_value(raw_list, imei, key):
    """
    查找 F102 设置响应状态。

    判断规则：
    line[48:50] == 04
    line[58:62] == F102
    line[62:66] == KEY
    line[66:68] 是返回状态

    状态值：
    00 -> PASS
    非00 -> FAIL
    """
    imei = str(imei)
    match_list = []

    for line in raw_list:
        line = line.replace(" ", "").upper()

        if len(line) < 68:
            continue

        if line[48:50] != "04":
            continue

        if line[58:62].upper() != "F102":
            continue

        line_imei = ascii_to_decimal(line[18:48])
        if line_imei != imei:
            continue

        return_key = line[62:66].upper()
        if return_key != key.upper():
            continue

        status_hex = line[66:68]

        match_list.append({
            "status_hex": status_hex,
            "raw_line": line
        })

    if not match_list:
        return None

    return match_list[-1]


# =========================================================
# 八、后台执行线程
# =========================================================

class WorkerThread(QThread):
    log_signal = pyqtSignal(str)
    row_signal = pyqtSignal(int, str, str)
    finish_signal = pyqtSignal(str)

    def __init__(self, mode, imei, rows, set_values):
        super().__init__()
        self.mode = mode
        self.imei = imei
        self.rows = rows
        self.set_values = set_values
        self.excel_rows = []
        # 保存执行日志，执行结束后会和 Excel 同名生成 TXT 文件。
        self.log_lines = []
        self.running = True
        self.config = get_current_config(mode)

    def add_log(self, text):
        """
        统一日志入口。
        1. 通过信号显示到界面日志框。
        2. 同步缓存到 self.log_lines，执行结束后保存为 TXT。
        """
        now = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[{now}] {text}")
        self.log_signal.emit(text)

    def stop(self):
        """停止执行。"""
        self.running = False

    def run(self):
        """线程入口。"""
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            self.add_log(f"开始执行：{self.mode}")
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

            if self.mode == "默认值查询":
                file_name = f"默认值查询_{now_str}.xlsx"
                self.run_default_query()
            elif self.mode == "设置与查询":
                file_name = f"设置与查询_{now_str}.xlsx"
                self.run_set_and_query()
            else:
                file_name = f"非法值设置_{now_str}.xlsx"
                self.run_illegal_set()

            save_path = os.path.join(SAVE_DIR, file_name)
            self.save_excel(save_path)
            txt_path = save_path.replace(".xlsx", ".txt")
            self.save_log_txt(txt_path)
            self.finish_signal.emit(save_path)

        except Exception as e:
            self.finish_signal.emit(f"执行异常：{e}")

    def run_default_query(self):
        """
        默认值查询。
        查询失败时，返回值显示：无返回值/查询失败。
        """
        for row_index, key in self.rows:
            if not self.running:
                break

            cfg = self.config[key]
            name = cfg["name"]
            default_value = cfg.get("default", "")

            self.add_log(f"开始默认值查询：{name} / KEY={key}")
            result_obj = self.execute_f103_query_once(key, cfg)

            if result_obj:
                actual_value = result_obj["value"]
                value_hex = result_obj["value_hex"]
                display_value = str(actual_value)
                compare_result = compare_value(default_value, actual_value)
            else:
                actual_value = ""
                value_hex = ""
                display_value = "无返回值/查询失败"
                compare_result = "FAIL"

            self.row_signal.emit(row_index, display_value, compare_result)

            self.excel_rows.append([
                name,
                key,
                cfg.get("default_hex", ""),
                default_value,
                value_hex,
                actual_value,
                compare_result
            ])

            time.sleep(1)

    def format_temp_safety_range(self, value_str):
        """
        处理 0236 温度上下限：输入 30,40 → 输出 001E0028
        """
        try:
            min_val, max_val = value_str.strip().split(',')
            min_hex = f"{int(min_val):04X}"  # 转 4 位 16 进制
            max_hex = f"{int(max_val):04X}"
            return (min_hex + max_hex).lower()  # 001e0028
        except:
            return None

    def run_set_and_query(self):
        """
        设置与查询。
        多个设置值用逗号隔开，逐个设置、逐个查询、逐个比对。
        最终只要有一个 FAIL，界面总结果就是 FAIL。
        """
        for row_index, key in self.rows:
            if not self.running:
                break

            cfg = self.config[key]
            name = cfg["name"]
            value_text = self.set_values.get(key, "").strip()

            if not value_text:
                self.add_log(f"KEY={key} 未填写设置值，跳过")
                continue

            # values = [v.strip() for v in value_text.split(",") if v.strip()]
            if cfg.get("set_rule") in ["apn_user_pass", "ascii_with_len"]:
                # 整体字符串，不拆分
                values = [value_text.strip()]
            else:
                values = [v.strip() for v in value_text.split(",") if v.strip()]
            actual_value_list = []
            result_list = []

            for value in values:
                if not self.running:
                    break

                try:
                    set_cmd, set_value_hex = build_set_cmd(key, value, cfg)
                except Exception as e:
                    self.add_log(f"KEY={key} 设置值非法：{value}，原因：{e}")
                    actual_value_list.append("")
                    result_list.append("FAIL")
                    continue

                try:
                    self.add_log(f"发送设置命令：KEY={key} 设置值={value} 设置HEX={set_value_hex} CMD={set_cmd}")
                    send_cmd(self.imei, set_cmd)
                except Exception as e:
                    self.add_log(f"设置接口异常：{e}")
                    actual_value_list.append("")
                    result_list.append("FAIL")
                    continue

                # 设置后等待设备处理，再进入 F103 查询闭环。
                time.sleep(2)
                result_obj = self.execute_f103_query_once(key, cfg)

                if result_obj:
                    actual_value = result_obj["value"]
                    value_hex = result_obj["value_hex"]
                    display_value = str(actual_value)
                else:
                    actual_value = ""
                    value_hex = ""
                    display_value = "无返回值/查询失败"

                compare_result = compare_value(value, actual_value) if actual_value != "" else "FAIL"
                actual_value_list.append(display_value)
                result_list.append(compare_result)

                self.add_log(
                    f"KEY={key} 设置值={value} 设置HEX={set_value_hex} "
                    f"返回值={display_value} 返回HEX={value_hex} 比对结果={compare_result}"
                )

                self.excel_rows.append([name, key, value, set_value_hex, value_hex, display_value, compare_result])
                time.sleep(1)

            final_result = "PASS" if result_list and all(r == "PASS" for r in result_list) else "FAIL"
            self.row_signal.emit(row_index, ",".join(actual_value_list), final_result)

    def run_illegal_set(self):
        """
        非法值设置。
        多个非法设置值用逗号隔开。
        返回值显示 F102 状态字节，00 为 PASS，否则 FAIL。
        """
        for row_index, key in self.rows:
            if not self.running:
                break

            cfg = self.config[key]
            name = cfg["name"]
            value_text = self.set_values.get(key, "").strip()

            if not value_text:
                self.add_log(f"KEY={key} 未填写非法设置值，跳过")
                continue

            if cfg.get("set_rule") in ["apn_user_pass", "ascii_with_len"]:
                values = [value_text.strip()]
            else:
                values = [v.strip() for v in value_text.split(",") if v.strip()]
            status_list = []
            result_list = []

            for value in values:
                if not self.running:
                    break

                try:
                    set_cmd, set_value_hex = build_set_cmd(key, value, cfg)
                except Exception as e:
                    self.add_log(f"KEY={key} 非法设置值格式错误：{value}，原因：{e}")
                    status_list.append("无返回值/查询失败")
                    result_list.append("FAIL")
                    continue

                self.add_log(f"发送非法值设置命令：KEY={key} 设置值={value} 设置HEX={set_value_hex} CMD={set_cmd}")
                result_obj = self.execute_f102_status_once(key, set_cmd)

                if result_obj:
                    status_hex = result_obj["status_hex"]
                    compare_result = "PASS" if status_hex == "00" else "FAIL"
                else:
                    status_hex = "无返回值/查询失败"
                    compare_result = "FAIL"

                status_list.append(status_hex)
                result_list.append(compare_result)

                self.add_log(
                    f"KEY={key} 非法值={value} 设置HEX={set_value_hex} "
                    f"F102返回状态={status_hex} 比对结果={compare_result}"
                )

                self.excel_rows.append([name, key, value, set_value_hex, status_hex, compare_result])
                time.sleep(1)

            final_result = "PASS" if result_list and all(r == "PASS" for r in result_list) else "FAIL"
            self.row_signal.emit(row_index, ",".join(status_list), final_result)

    def execute_f103_query_once(self, key, cfg):
        """
        双层重试版本：
        外层：重试3轮，每轮间隔10秒，每轮重新发送命令
        内层：原有逻辑不变，发1次 → 查询2次
        """
        outer_retry_max = 5
        outer_wait_seconds = 10

        for outer_attempt in range(outer_retry_max):
            if outer_attempt > 0:
                self.add_log(
                    f"==================== 外层重试：第 {outer_attempt + 1} 轮，等待 {outer_wait_seconds} 秒后重新发送命令 ====================")
                time.sleep(outer_wait_seconds)

            # ==================== 内层原有逻辑开始 ====================
            query_cmd = build_query_cmd(key)
            try:
                start_ms = utc_ms_now()
                self.add_log(f"发送查询命令：{query_cmd}")
                send_cmd(self.imei, query_cmd)
            except Exception as e:
                self.add_log(f"查询命令发送异常：{e}")
                continue

            retry_count = 3
            window_step_ms = 3000
            result_obj = None

            for attempt in range(retry_count):
                stop_ms = start_ms + (attempt + 1) * window_step_ms
                if attempt == 0:
                    time.sleep(1)
                else:
                    time.sleep(2)

                try:
                    self.add_log(f"查询F103 rawData：KEY={key}，start={start_ms}，stop={stop_ms}")
                    resp_json = query_raw_data(self.imei, start_ms, stop_ms)
                    raw_list = extract_raw_data_list(resp_json)
                    result_obj = find_f103_return_value(raw_list, self.imei, key, cfg)

                    if result_obj:
                        self.add_log(f"KEY={key} 查询成功，返回值={result_obj['value']} HEX={result_obj['value_hex']}")
                        self.add_log(f"✅ KEY={key} 在第 {outer_attempt + 1} 轮查询成功！")
                        return result_obj

                    self.add_log(f"KEY={key} 第 {attempt + 1} 次未查询到 F103 返回")

                except Exception as e:
                    self.add_log(f"F103 rawData 查询异常：{e}")

            self.add_log(f"KEY={key} F103查询失败，无返回值")
            # ==================== 内层原有逻辑结束 ====================

        self.add_log(f"❌ KEY={key} 外层重试 {outer_retry_max} 轮全部失败，最终查询失败")
        return None

    # 原来只查询3次的函数
    # def execute_f103_query_once(self, key, cfg):
    #     """
    #     F103 查询闭环：
    #     1. 记录 start_ms
    #     2. 发送 F103 + KEY
    #     3. 第一次查询 start_ms ~ start_ms+2秒
    #     4. 没查到，等待2秒
    #     5. 第二次查询 start_ms ~ start_ms+4秒
    #     6. 本次闭环内 start_ms 固定不变
    #     """
    #     query_cmd = build_query_cmd(key)
    #
    #     try:
    #         start_ms = utc_ms_now()
    #         self.add_log(f"发送查询命令：{query_cmd}")
    #         send_cmd(self.imei, query_cmd)
    #     except Exception as e:
    #         self.add_log(f"查询命令发送异常：{e}")
    #         return None
    #
    #     retry_count = 2
    #     window_step_ms = 2000
    #
    #     for attempt in range(retry_count):
    #         stop_ms = start_ms + (attempt + 1) * window_step_ms
    #
    #         if attempt == 0:
    #             time.sleep(1)
    #         else:
    #             time.sleep(2)
    #
    #         try:
    #             self.add_log(f"查询F103 rawData：KEY={key}，start={start_ms}，stop={stop_ms}")
    #             resp_json = query_raw_data(self.imei, start_ms, stop_ms)
    #             raw_list = extract_raw_data_list(resp_json)
    #             result_obj = find_f103_return_value(raw_list, self.imei, key, cfg)
    #
    #             if result_obj:
    #                 self.add_log(f"KEY={key} 查询成功，返回值={result_obj['value']} HEX={result_obj['value_hex']}")
    #                 return result_obj
    #
    #             self.add_log(f"KEY={key} 第 {attempt + 1} 次未查询到 F103 返回")
    #
    #         except Exception as e:
    #             self.add_log(f"F103 rawData 查询异常：{e}")
    #
    #     self.add_log(f"KEY={key} F103查询失败，无返回值")
    #     return None

    def execute_f102_status_once(self, key, set_cmd):
        """
        F102 设置状态查询闭环：
        start_ms 固定，重试时 stop_ms 递增。
        """
        try:
            start_ms = utc_ms_now()
            send_cmd(self.imei, set_cmd)
        except Exception as e:
            self.add_log(f"F102设置命令发送异常：{e}")
            return None

        retry_count = 2
        window_step_ms = 2000

        for attempt in range(retry_count):
            stop_ms = start_ms + (attempt + 1) * window_step_ms

            if attempt == 0:
                time.sleep(1)
            else:
                time.sleep(2)

            try:
                self.add_log(f"查询F102 rawData：KEY={key}，start={start_ms}，stop={stop_ms}")
                resp_json = query_raw_data(self.imei, start_ms, stop_ms)
                raw_list = extract_raw_data_list(resp_json)
                result_obj = find_f102_status_value(raw_list, self.imei, key)

                if result_obj:
                    self.add_log(f"KEY={key} F102状态返回成功，状态HEX={result_obj['status_hex']}")
                    return result_obj

                self.add_log(f"KEY={key} 第 {attempt + 1} 次未查询到 F102 状态返回")

            except Exception as e:
                self.add_log(f"F102 rawData 查询异常：{e}")

        self.add_log(f"KEY={key} F102状态查询失败，无返回值")
        return None

    def save_log_txt(self, txt_path):
        """
        保存执行日志 TXT。
        文件名和 Excel 一致，只是后缀为 .txt。
        """
        with open(txt_path, "w", encoding="utf-8") as f:
            for line in self.log_lines:
                f.write(line + "\n")

    def save_excel(self, save_path):
        """保存 Excel。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "测试结果"

        if self.mode == "默认值查询":
            ws.append(["NAME", "KEY", "默认HEX", "默认值", "返回HEX", "返回值", "比对结果"])
        elif self.mode == "设置与查询":
            ws.append(["NAME", "KEY", "设置值", "设置HEX", "返回HEX", "返回值", "比对结果"])
        else:
            ws.append(["NAME", "KEY", "非法设置值", "设置HEX", "F102返回状态", "比对结果"])

        for row in self.excel_rows:
            ws.append(row)

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

        wb.save(save_path)


# =========================================================
# 九、主界面
# =========================================================

class ParamToolUI(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()
        # mode = self.mode_combo.currentText()
        self.load_project_keys()

    def init_ui(self):
        """初始化界面。"""
        self.setWindowTitle("参数默认值查询 / 设置与查询 / 非法值设置工具 - Mangetic - 2026-07-15")
        self.setWindowIcon(QIcon(resource_path(APP_ICON_FILE)))
        self.resize(1200, 700)

        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()

        self.imei_input = QLineEdit()
        self.imei_input.setPlaceholderText("请输入 IMEI，例如 864114070683622")

        self.project_combo = QComboBox()
        # 项目名称可能比较长，这里加宽下拉框，避免项目名显示不完整。
        self.project_combo.setMinimumWidth(320)
        self.project_combo.addItems(PROJECT_DEFAULT_KEYS.keys())
        self.project_combo.currentTextChanged.connect(self.load_project_keys)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["默认值查询", "设置与查询", "非法值设置"])
        self.mode_combo.currentTextChanged.connect(self.load_project_keys)

        self.start_btn = QPushButton("开始执行")
        self.start_btn.clicked.connect(self.start_run)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_run)

        top_layout.addWidget(QLabel("IMEI："))
        top_layout.addWidget(self.imei_input)
        top_layout.addWidget(QLabel("项目："))
        top_layout.addWidget(self.project_combo)
        top_layout.addWidget(QLabel("功能："))
        top_layout.addWidget(self.mode_combo)
        top_layout.addWidget(self.start_btn)
        top_layout.addWidget(self.stop_btn)

        self.table = QTableWidget()
        self.table.setColumnCount(6)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 70)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 90)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 90)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.table)
        main_layout.addWidget(QLabel("执行日志："))
        main_layout.addWidget(self.log_text)
        self.setLayout(main_layout)

    def load_project_keys(self):
        """
        根据项目和模式加载参数
        """

        mode = self.mode_combo.currentText()

        # 根据模式刷新项目列表
        if mode == "默认值查询":
            project_dict = PROJECT_DEFAULT_KEYS
        elif mode == "设置与查询":
            project_dict = PROJECT_SET_KEYS
        else:
            project_dict = PROJECT_ILLEGAL_KEYS

        current_project = self.project_combo.currentText()

        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItems(project_dict.keys())

        index = self.project_combo.findText(current_project)
        if index >= 0:
            self.project_combo.setCurrentIndex(index)

        self.project_combo.blockSignals(False)

        project = self.project_combo.currentText()

        self.table.setRowCount(0)

        if mode == "默认值查询":
            self.table.setHorizontalHeaderLabels(["是否应用", "NAME", "KEY", "默认值", "返回值", "比对结果"])
            keys = PROJECT_DEFAULT_KEYS.get(project, [])
            config = DEFAULT_QUERY_CONFIG
        elif mode == "设置与查询":
            self.table.setHorizontalHeaderLabels(["是否应用", "NAME", "KEY", "设置值", "返回值", "比对结果"])
            keys = PROJECT_SET_KEYS.get(project, [])
            config = SET_QUERY_CONFIG
        else:
            self.table.setHorizontalHeaderLabels(["是否应用", "NAME", "KEY", "非法设置值", "返回值", "比对结果"])
            keys = PROJECT_ILLEGAL_KEYS.get(project, [])
            config = ILLEGAL_SET_CONFIG

        for key in keys:
            if key not in config:
                continue

            cfg = config[key]
            row = self.table.rowCount()
            self.table.insertRow(row)

            check = QCheckBox()
            check.setChecked(True)
            check.setStyleSheet("margin-left:20px;")

            self.table.setCellWidget(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(cfg["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(key))

            if mode == "默认值查询":
                item = QTableWidgetItem(str(cfg["default"]))
                # item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 3, item)

            elif mode == "设置与查询":
                default_set_value = cfg.get("set_default", "")
                self.table.setItem(row, 3, QTableWidgetItem(str(default_set_value)))

            elif mode == "非法值设置":
                default_illegal_value = cfg.get("set_default", "")
                self.table.setItem(row, 3, QTableWidgetItem(str(default_illegal_value)))

            self.table.setItem(row, 4, QTableWidgetItem(""))
            self.table.setItem(row, 5, QTableWidgetItem(""))

    def clear_result_before_run(self):
        """开始执行前清空返回值、比对结果和日志。"""
        for row in range(self.table.rowCount()):
            self.table.setItem(row, 4, QTableWidgetItem(""))
            self.table.setItem(row, 5, QTableWidgetItem(""))
        self.log_text.clear()

    def start_run(self):
        """开始执行。"""
        imei = self.imei_input.text().strip()

        if not imei:
            QMessageBox.warning(self, "提示", "请先输入 IMEI")
            return

        if not imei.isdigit():
            QMessageBox.warning(self, "提示", "IMEI 只能输入数字")
            return

        mode = self.mode_combo.currentText()
        selected_rows = []
        set_values = {}

        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            if check and check.isChecked():
                key = self.table.item(row, 2).text()
                selected_rows.append((row, key))
                value_item = self.table.item(row, 3)
                set_values[key] = value_item.text().strip() if value_item else ""

        if not selected_rows:
            QMessageBox.warning(self, "提示", "请至少勾选一个参数")
            return

        if mode in ["设置与查询", "非法值设置"]:
            for _, key in selected_rows:
                if not set_values.get(key):
                    QMessageBox.warning(self, "提示", f"KEY={key} 未填写设置值")
                    return

        self.clear_result_before_run()
        self.log(f"开始执行：{mode}")
        self.start_btn.setEnabled(False)

        self.worker = WorkerThread(mode, imei, selected_rows, set_values)
        self.worker.log_signal.connect(self.log)
        self.worker.row_signal.connect(self.update_row_result)
        self.worker.finish_signal.connect(self.finish_run)
        self.worker.start()

    def stop_run(self):
        """停止执行。"""
        if self.worker:
            self.worker.stop()
            self.log("已请求停止，当前步骤执行完成后会停止")

    def update_row_result(self, row, value, result):
        """
        更新表格返回值和比对结果。
        PASS：浅绿色背景 + 深绿色字体。
        FAIL：浅红色背景 + 深红色字体。
        """
        value_item = QTableWidgetItem(str(value))
        result_item = QTableWidgetItem(str(result))

        if str(result).upper() == "PASS":
            result_item.setForeground(QColor(0, 128, 0))
            result_item.setBackground(QColor(220, 255, 220))
        elif str(result).upper() == "FAIL":
            result_item.setForeground(QColor(180, 0, 0))
            result_item.setBackground(QColor(255, 220, 220))

        self.table.setItem(row, 4, value_item)
        self.table.setItem(row, 5, result_item)

    def finish_run(self, msg):
        """执行完成。"""
        self.start_btn.setEnabled(True)

        if msg.startswith("执行异常"):
            self.log(msg)
            QMessageBox.critical(self, "执行异常", msg)
        else:
            self.log(f"执行完成，Excel 已保存：{msg}")
            open_save_dir()
            QMessageBox.information(self, "完成", f"执行完成\nExcel 已保存：\n{msg}")

    def log(self, text):
        """打印日志。"""
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now}] {text}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path(APP_ICON_FILE)))
    win = ParamToolUI()
    win.show()
    sys.exit(app.exec_())
