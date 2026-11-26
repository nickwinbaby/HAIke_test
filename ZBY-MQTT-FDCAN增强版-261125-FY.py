#!/usr/bin/env python3
# mqtt_aes_tool_pro_v2_final.py
# PyInstaller --noconfirm --clean --onefile --windowed --name "ZBY MQTT Data Tools-FY-20261125" --icon "bulid_photos\MQTT_ZBY.ico" --add-data "bulid_photos\MQTT_ZBY.ico;bulid_photos" --add-data "bulid_photos\MQTT_ZBY.png;bulid_photos" --add-data "bulid_photos\Mangetic.png;bulid_photos" "ZBY-MQTT-FDCAN增强版-261125-FY.py"
# 单文件：严格显示 FIFO（默认2000条），保存全部数据，GT115_ZBY/Raw Data 下拉，JSON 彩色渲染
# 新增：
# 1. GT115_ZBY 模式下，QoS 后显示：解密成功 / 解密失败
# 2. 解密失败时，显示并保存原始 HEX 数据；解密成功时不显示原始 HEX
#
# 依赖: paho-mqtt, pycryptodome, pillow
# pip install paho-mqtt pycryptodome pillow

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
import json
import os
import sys
import queue
import logging
import uuid
import ctypes
from ctypes import wintypes
import re
import tempfile
import math
from contextlib import ExitStack
from itertools import chain
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from PIL import Image, ImageTk

# ----------------------------
# CONFIG
# ----------------------------
FIXED_KEY_HEX = "d3f67a2e5b8c901f4a6d0e3c7b291f5d8e4c2a1b0f9e8d7c6b5a493827161514"
DEFAULT_MAX_MESSAGES = 2000
PAUSED_OUTPUT_LIMIT = 4000
TOPICS_SAVE_FILE = "topics.json"
FIELD_TRANSLATIONS_FILE = "field_translations.json"
UNRECOGNIZED_FIELDS_FILE = "unrecognized_fields.json"
RECONNECT_INTERVAL = 5  # seconds between reconnect attempts
CONNECT_TIMEOUT_MS = 10000
DISCONNECT_TIMEOUT_MS = 3000
SUBSCRIPTION_ACK_TIMEOUT_MS = 5000
APP_NAME = "ZBY MQTT Data Tools"
APP_RELEASE_DATE = "2026-11-25"
APP_NOTICE = "※瑞联内部工具，谢绝外发※"
APP_CONTACT = "guomengyao@gosuncn.com"
WATERMARK_RELATIVE_PATH = os.path.join("bulid_photos", "Mangetic.png")
WATERMARK_SIZE = (240, 80)
WATERMARK_OPACITY = 0.18
WATERMARK_MARGIN = 14
WINDOW_ICON_ICO = os.path.join("bulid_photos", "MQTT_ZBY.ico")
WINDOW_ICON_PNG = os.path.join("bulid_photos", "MQTT_ZBY.png")
WINDOWS_APP_ID = "RichLink.ZBY.MQTT.DataTools"

# 常用车载 / GPS / MQTT 字段翻译。其他字段会拆分驼峰或下划线后组合翻译。
DEFAULT_FIELD_TRANSLATIONS = {
    "lon": "经度", "lng": "经度", "longitude": "经度",
    "lat": "纬度", "latitude": "纬度", "speed": "速度",
    "seatbelt": "安全带", "driver": "驾驶员", "passenger": "乘员",
    "gear": "档位", "requestid": "请求ID", "filter": "过滤条件",
    "canid": "CAN ID", "deviceid": "设备ID", "vehicleid": "车辆ID",
    "timestamp": "时间戳", "time": "时间", "date": "日期",
    "status": "状态", "state": "状态", "enabled": "启用",
    "event": "事件", "data": "数据", "sensor": "传感器",
    "sensordataeventenabled": "传感器数据事件启用",
    "direction": "方向", "heading": "航向", "altitude": "海拔",
    "accuracy": "精度", "satellites": "卫星数", "satellitecount": "卫星数",
    "mileage": "里程", "totalmileage": "总里程", "voltage": "电压",
    "battery": "电量", "batterylevel": "电量", "temperature": "温度",
    "humidity": "湿度", "pressure": "压力", "alarm": "报警",
    "fault": "故障", "ignition": "点火状态", "acc": "ACC状态",
    "gps": "GPS状态", "location": "位置", "address": "地址",
    "online": "在线状态", "network": "网络", "signal": "信号",
    "rssi": "信号强度", "qos": "服务质量", "topic": "主题",
    "payload": "载荷", "message": "消息", "type": "类型",
    "code": "代码", "result": "结果", "success": "成功",
    "error": "错误", "reason": "原因", "mode": "模式",
    "protocol": "协议", "version": "版本", "firmware": "固件",
    "hardware": "硬件", "config": "配置", "command": "命令",
    "response": "响应", "seq": "序号", "index": "索引",
    "count": "数量", "length": "长度", "duration": "时长",
    "interval": "间隔", "frequency": "频率", "unit": "单位",
    "value": "数值", "min": "最小值", "max": "最大值",
    "average": "平均值", "createdat": "创建时间", "updatedat": "更新时间",
    "starttime": "开始时间", "endtime": "结束时间",
    "imei": "IMEI", "imsi": "IMSI", "iccid": "ICCID", "vin": "VIN",
    # 动力电池监控协议 1.0.6（2026-11-13），第 2～7 章。
    "apn": "接入点名称（APN）",
    "battvol": "12V 电瓶电压",
    "cantype": "CAN 报文类型",
    "url": "固件下载地址",
    "eventid": "事件 ID",
    "eventtype": "事件类型",
    "speedbefore": "事件前车速",
    "speedafter": "事件后车速",
    "acceleration": "加速度",
    "deceleration": "减速度",
    "turn": "转弯测量值",
    "sensorvalue": "传感器测量值",
    "collisionvalue": "碰撞测量值",
    "throttlebefore": "窗口起始踏板位置",
    "throttleafter": "窗口末端踏板位置",
    "throttleincrement": "油门踏板位置增量",
    "severity": "严重等级",
    "reporttime": "上报时间",
    "eventdurationms": "事件持续时间（毫秒）",
    "collectiontime": "首条样本采集时间",
    "collectiontimems": "首条样本采集时间毫秒部分",
    "collectiondurationms": "采集区间时长（毫秒）",
    "intervalms": "采样间隔（毫秒）",
    "sensorstudystatus": "传感器学习／标定状态",
    "packetindex": "分包序号",
    "packetcount": "分包总数",
    "samplecount": "样本数量",
    "samples": "采样数据",
    "server": "MQTT 服务器",
    "port": "MQTT 端口",
    "username": "MQTT 用户名",
    "password": "MQTT 密码",
    "drivingbehavior": "驾驶行为配置",
    "harshacceleration": "急加速",
    "harshbraking": "急减速",
    "harshcornering": "急转弯",
    "harshlanechange": "急变道",
    "suspectedcollision": "疑似碰撞",
    "fatiguedriving": "疲劳驾驶",
    "prolongedidling": "长时间怠速",
    "suddenthrottle": "油门猛踩",
    "params": "参数",
    "threshold": "阈值",
    "drivingtime": "驾驶时长阈值",
    "idletime": "怠速时长阈值",
    "normalincrementthreshold": "普通油门增量阈值",
    "severeincrementthreshold": "严重油门增量阈值",
    "endpedalpositionthreshold": "窗口末端踏板位置阈值",
    "minimumholdtime": "油门最小保持时间",
    "detectionwindow": "油门检测窗口",
    "reportsuppressiontime": "油门重复上报抑制时间",
}

FIELD_TOKEN_TRANSLATIONS = {
    "id": "ID", "lon": "经度", "lng": "经度", "longitude": "经度",
    "lat": "纬度", "latitude": "纬度", "speed": "速度",
    "seat": "座椅", "belt": "带", "driver": "驾驶员", "passenger": "乘员",
    "gear": "档位", "request": "请求", "response": "响应", "filter": "过滤",
    "can": "CAN", "device": "设备", "vehicle": "车辆", "sensor": "传感器",
    "data": "数据", "event": "事件", "enabled": "启用", "enable": "启用",
    "status": "状态", "state": "状态", "time": "时间", "stamp": "戳",
    "start": "开始", "end": "结束", "total": "总", "count": "数量",
    "level": "等级", "battery": "电量", "signal": "信号", "network": "网络",
    "location": "位置", "direction": "方向", "heading": "航向", "altitude": "海拔",
    "accuracy": "精度", "satellite": "卫星", "mileage": "里程",
    "temperature": "温度", "humidity": "湿度", "pressure": "压力",
    "alarm": "报警", "fault": "故障", "config": "配置", "command": "命令",
    "type": "类型", "code": "代码", "value": "数值", "result": "结果",
}

LOC_SEATBELT_VALUES = {"unfastened": "未系", "fastened": "已系", "unsupported": "不支持"}
LOC_FIELD_VALUES = {
    "$.seatbelt.driver": LOC_SEATBELT_VALUES,
    "$.seatbelt.passenger": LOC_SEATBELT_VALUES,
    "$.gear": {"P": "驻车", "R": "倒车", "N": "空挡", "D": "前进", "unsupported": "不支持"},
}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

def hex_to_bytes(hex_str):
    return bytes.fromhex(hex_str)

KEY_BYTES = hex_to_bytes(FIXED_KEY_HEX)

# 固定 IV
IV_BYTES = bytes.fromhex("19e4f7a83d0b6c25a81234567890abcd")



# 日志分析与导出。离线处理当前工具保存的原文日志，也兼容旧版 Topic: 日志。
BEIJING_TZ = timezone(timedelta(hours=8))
LOG_HEADER = re.compile(
    r"^\s*\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:[.,]\d+)?\]?"
    r"\s+(?:Topic|主题|主題)\s*[:：][ \t]*(.*?)[ \t]*$",
    re.IGNORECASE,
)
LOG_QOS = re.compile(r"\s+QoS\s*[:：]\s*[012](?:\s|$)", re.IGNORECASE)
LOG_NOTICE = re.compile(r"^\s*\[(?:信息|错误|警告|发送|INFO|ERROR|WARN|SEND)\]", re.IGNORECASE)
EVENT_COLUMNS = ("eventId", "eventType", "事件中文", "time（北京时间）")
EVENT_COORD_COLUMNS = ("lon（经度）", "lat（纬度）")
HEARTBEAT_LOG_TOPIC = re.compile(r"(?:heartbeat|hertbeat|heartbeatsta_u)/([0-9]*)", re.IGNORECASE)
HEARTBEAT_EXPORT_COLUMNS = (
    "接收时间（北京时间）", "Topic", "车型", "status（十进制）", "status（十六进制）",
    "status（32 位二进制）", "源文件", "行号",
)

# 动力电池监控协议 1.0.6 §4.3.3，工作表顺序与协议一致。
DRIVING_EVENTS = {
    "harshAcceleration": ("急加速", (
        ("speedBefore", "加速前车速（km/h）"), ("speedAfter", "加速后车速（km/h）"),
        ("acceleration", "加速度（mg）"),
    )),
    "harshBraking": ("急减速", (
        ("speedBefore", "减速前车速（km/h）"), ("speedAfter", "减速后车速（km/h）"),
        ("deceleration", "减速度大小（mg）"),
    )),
    "harshCornering": ("急转弯", (("turn", "转弯测量值（mg）"),)),
    "harshLaneChange": ("急变道", (("sensorValue", "变道测量值（mg）"),)),
    "suspectedCollision": ("疑似碰撞", (("collisionValue", "碰撞测量值（mg）"),)),
    "suddenThrottle": ("猛踩油门", (
        ("throttleBefore", "窗口起始踏板位置（%）"),
        ("throttleAfter", "窗口末端踏板位置（%）"),
        ("throttleIncrement", "踏板位置增量（百分点）"),
        ("severity", "严重等级"),
    )),
    "prolongedIdling": ("长时间怠速", ()),
    "fatigueDriving": ("疲劳驾驶", ()),
}
EVENT_TYPE_TRANSLATIONS = {event_type: details[0] for event_type, details in DRIVING_EVENTS.items()}
SENSOR_EVENT_FIELDS = (
    "eventId", "eventType", "reportTime", "time", "eventDurationMs", "collectionTime",
    "collectionTimeMs", "collectionDurationMs", "intervalMs", "sensorStudyStatus",
    "packetIndex", "packetCount", "sampleCount", "samples",
)
SENSOR_EVENT_TIMES = ("reportTime", "time", "collectionTime")
SENSOR_EVENT_TOPIC = "sensor/event/"
HEARTBEAT_STATUS_PROFILES = {
    "GT115": (
        ("can_connect", 0, 0, "CAN 断线状态", {0: "正常", 1: "断线"}),
        ("can_recv", 1, 1, "CAN 中断接收标识", {0: "未进入中断函数", 1: "已进入 CAN 中断函数"}),
        ("gps_loc", 2, 2, "GPS 定位标识", {0: "不定位", 1: "已定位"}),
        ("fota_sta", 3, 5, "FOTA 升级状态", {
            0: "无升级任务", 3: "请求升级包", 4: "下载升级包完成", 5: "升级成功",
        }),
        ("can_match", 6, 6, "CAN 波特率匹配成功状态", {0: "匹配失败", 1: "匹配成功"}),
        ("can_type", 7, 9, "CAN 波特率匹配类型", {
            0: "无匹配", 1: "50 Kbps", 2: "250 Kbps", 3: "500 Kbps",
            4: "125 Kbps", 5: "1000 Kbps",
        }),
        ("reserved", 10, 15, "保留", {}),
        ("wake_type", 16, 23, "唤醒类型", {1: "Sensor 唤醒", 0x10: "CAN 唤醒"}),
        ("reset_type", 24, 31, "重启类型", {
            0: "normal", 1: "watchdog", 2: "upgrade", 4: "pinReset", 0xFF: "init",
        }),
    ),
    "GD202": (
        ("can_connect", 0, 0, "CAN 线路状态", {
            0: "CAN 正常活跃", 1: "超时 1 分钟无 CAN 数据，断线待休眠",
        }),
        ("can_recv", 1, 1, "CAN 中断接收", {
            0: "本心跳周期未收到 CAN 数据", 1: "本心跳周期收到 CAN 数据，上报后清零",
        }),
        ("gps_loc", 2, 2, "GPS 定位状态", {0: "未定位", 1: "已定位"}),
        ("fota_sta", 3, 5, "FOTA 升级状态", {
            0: "无任务", 1: "请求升级", 2: "校验中", 3: "请求文件",
            4: "文件完成", 5: "升级成功", 6: "升级失败", 7: "文件大小错误",
        }),
        ("can_match", 6, 6, "CAN 波特率匹配", {0: "匹配失败", 1: "匹配成功"}),
        ("can_type", 7, 8, "CAN 类型", {0: "未知", 1: "经典 CAN", 2: "FD CAN"}),
        ("can_bsp_arb", 9, 11, "仲裁域波特率", {
            0: "未知", 1: "50 Kbps", 2: "500 Kbps", 3: "250 Kbps",
            4: "125 Kbps", 5: "1 Mbps",
        }),
        ("can_bsp_data", 12, 13, "CAN FD 数据域波特率", {
            0: "未知", 1: "2 Mbps", 2: "4 Mbps", 3: "5 Mbps",
        }),
        ("wake_type", 14, 15, "唤醒类型", {1: "CAN 唤醒", 2: "Sensor 唤醒"}),
        ("reboot_type", 16, 22, "设备重启原因", {}),
        ("retain", 23, 31, "保留位", {}),
    ),
}


def iter_mqtt_log(path):
    """逐条读日志，每条记录的正文严格限制在当前消息内。"""
    topic = timestamp = start_line = None
    lines = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            match = LOG_HEADER.match(line.rstrip("\r\n"))
            if match or LOG_NOTICE.match(line):
                if topic is not None:
                    yield start_line, timestamp, topic, "".join(lines)
                topic = None
                start_line = None
                lines = []
                if match:
                    timestamp, header = match.groups()
                    topic = LOG_QOS.split(header, maxsplit=1)[0].strip()
                    if topic:
                        start_line = line_number
                        lines = [line]
                    else:
                        topic = None
            elif topic is not None:
                lines.append(line)
        if topic is not None:
            yield start_line, timestamp, topic, "".join(lines)


def mqtt_log_payload(record):
    _, separator, body = record.partition("\n")
    if not separator:
        return None
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        return None


def analysis_topic(mode, entered):
    value = entered.strip()
    if mode == "heartbeat":
        if re.fullmatch(r"[0-9]+", value):
            return value
        heartbeat = HEARTBEAT_LOG_TOPIC.fullmatch(value)
        if heartbeat:
            return heartbeat[1]
        raise ValueError("请输入设备 IMEI 或完整心跳 Topic。全部设备请输入 heartbeat/。")
    if mode == "filter":
        if not value:
            raise ValueError("请输入 Topic。")
        return value
    family = {"kml": "loc/", "events": "driving/event/", "sensor": SENSOR_EVENT_TOPIC}[mode]
    if value.isascii() and value.isdecimal():
        value = family + value
    if mode in ("events", "sensor") and value == family:
        return value
    device = value[len(family):]
    if not value.startswith(family) or not re.fullmatch(r"[0-9]+", device):
        hint = f"请输入 IMEI 或完整 Topic（{family}设备号）。"
        if mode in ("events", "sensor"):
            hint += f"也可输入 {family} 分析全部设备。"
        raise ValueError(hint)
    return value


def topic_matches(topic, target):
    if target.endswith("/"):
        return topic.startswith(target) and len(topic) > len(target)
    return topic == target


def filter_mqtt_log(source, target, output):
    count = 0
    with output.open("w", encoding="utf-8") as stream:
        for _, _, topic, record in iter_mqtt_log(source):
            if topic_matches(topic, target):
                stream.write(record.rstrip("\r\n") + "\n\n")
                count += 1
    if not count:
        raise ValueError("日志中没有匹配的消息。")
    return f"已导出 {count} 条消息。"


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    # 超出浮点数范围的整数也不能存成 Excel 或 KML 数值。
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def format_beijing_unix_time(value):
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    value = finite_number(value)
    if value is None:
        return value
    if abs(value) >= 100_000_000_000:
        value /= 1000
    try:
        return datetime.fromtimestamp(value, BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def parse_heartbeat_status(value, model="GT115"):
    if isinstance(value, str):
        value = value.strip().replace("_", "")
        try:
            if value.lower().startswith(("0x", "0b")):
                number = int(value, 0)
            else:
                number = int(value, 10)
        except ValueError as exc:
            raise ValueError("请输入十进制、十六进制或 32 位二进制整数。") from exc
    elif isinstance(value, int) and not isinstance(value, bool):
        number = value
    else:
        raise ValueError("请输入有效的整数状态值。")
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError("状态值范围为 0 到 4294967295。")
    fields = HEARTBEAT_STATUS_PROFILES.get(model)
    if fields is None:
        raise ValueError("车型仅支持 GT115 或 GD202。")
    binary = f"{number:032b}"
    rows = []
    for name, low, high, label, meanings in fields:
        width = high - low + 1
        raw = (number >> low) & ((1 << width) - 1)
        meaning = meanings.get(raw, "保留位" if name in ("reserved", "retain") else "未知值")
        rows.append((name, label, f"bit{high}" if low == high else f"bit{high}:{low}", raw, meaning))
    return number, binary, rows


def location_coordinates(payload):
    lon = finite_number(payload.get("lon"))
    lat = finite_number(payload.get("lat"))
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None, None
    return lon, lat


def format_source_lines(lines, limit=20):
    shown = ", ".join(str(line) for line in lines[:limit])
    if len(lines) > limit:
        shown += f" 等（共 {len(lines)} 行）"
    return f"日志第 {shown} 行。" if shown else ""


def export_location_kml(source, target, point_path, track_path, speed_factor=1):
    points = []
    skipped_lines = []
    for line_number, timestamp, topic, record in iter_mqtt_log(source):
        if topic != target:
            continue
        payload = mqtt_log_payload(record)
        lon, lat = location_coordinates(payload) if isinstance(payload, dict) else (None, None)
        if lon is None:
            skipped_lines.append(line_number)
            continue
        speed = finite_number(payload.get("speed"))
        points.append((timestamp, lon, lat, speed))

    if not points:
        detail = format_source_lines(skipped_lines)
        raise ValueError("该 loc 主题没有有效经纬度。请检查 IMEI 和原文日志。\n" + detail)

    point_doc = ET.Element("Document")
    style = ET.SubElement(point_doc, "Style", id="pointStyle")
    icon = ET.SubElement(style, "IconStyle")
    ET.SubElement(icon, "color").text = "ff00ff00"
    ET.SubElement(icon, "scale").text = "0.6"
    for index, (timestamp, lon, lat, speed) in enumerate(points, 1):
        mark = ET.SubElement(point_doc, "Placemark")
        ET.SubElement(mark, "name").text = f"Point {index}"
        ET.SubElement(mark, "styleUrl").text = "#pointStyle"
        description = f"时间 {timestamp}<br/>经度 {lon}<br/>纬度 {lat}"
        if speed is not None:
            description += f"<br/>速度 {speed * speed_factor:.1f} km/h"
        ET.SubElement(mark, "description").text = description
        point = ET.SubElement(mark, "Point")
        ET.SubElement(point, "coordinates").text = f"{lon},{lat},0"

    track_doc = ET.Element("Document")
    style = ET.SubElement(track_doc, "Style", id="redLine")
    line_style = ET.SubElement(style, "LineStyle")
    ET.SubElement(line_style, "color").text = "ff0000ff"
    ET.SubElement(line_style, "width").text = "3"
    mark = ET.SubElement(track_doc, "Placemark")
    ET.SubElement(mark, "name").text = target
    ET.SubElement(mark, "styleUrl").text = "#redLine"
    geometry = ET.SubElement(mark, "LineString" if len(points) > 1 else "Point")
    if len(points) > 1:
        ET.SubElement(geometry, "tessellate").text = "1"
    ET.SubElement(geometry, "coordinates").text = " ".join(
        f"{lon},{lat},0" for _, lon, lat, _ in points
    )
    for path, doc in ((point_path, point_doc), (track_path, track_doc)):
        root = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
        root.append(doc)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    summary = f"已导出 {len(points)} 个定位点。"
    if skipped_lines:
        summary += f"\n跳过 {len(skipped_lines)} 条无有效坐标的消息。{format_source_lines(skipped_lines)}"
    return summary


def beijing_event_time(value):
    value = finite_number(value)
    if value is None:
        return None
    try:
        when = datetime.fromtimestamp(value, BEIJING_TZ).replace(tzinfo=None)
        return when if when >= datetime(1900, 1, 1) else None
    except (OverflowError, OSError, ValueError):
        return None


def driving_event_rows(source, target):
    overview = []
    details = {kind: [] for kind in DRIVING_EVENTS}
    seen = {}
    invalid_lines = []
    unknown_lines = []
    invalid = unknown = repeated = conflicts = 0
    for line_number, _, topic, record in iter_mqtt_log(source):
        if not topic_matches(topic, target) or not re.fullmatch(r"driving/event/[0-9]+", topic):
            continue
        payload = mqtt_log_payload(record)
        if not isinstance(payload, dict):
            invalid += 1
            invalid_lines.append(line_number)
            continue
        event_id = payload.get("eventId")
        kind = payload.get("eventType")
        when = beijing_event_time(payload.get("time"))
        if not isinstance(event_id, str) or not event_id.strip() or not isinstance(kind, str) or when is None:
            invalid += 1
            invalid_lines.append(line_number)
            continue
        token = (topic, event_id)
        # 协议重发保持 eventId。不同设备可以拥有相同的 eventId。
        if token in seen:
            if seen[token] == payload:
                repeated += 1
            else:
                conflicts += 1
            continue
        seen[token] = payload
        row = (event_id, kind, EVENT_TYPE_TRANSLATIONS.get(kind, "未知事件"), when)
        overview.append(row)
        if kind not in DRIVING_EVENTS:
            unknown += 1
            unknown_lines.append(line_number)
            continue
        gps = payload.get("gps")
        data = payload.get("data")
        position = location_coordinates(gps) if isinstance(gps, dict) else (None, None)
        if not isinstance(data, dict):
            data = {}
        metrics = tuple(finite_number(data.get(key)) for key, _ in DRIVING_EVENTS[kind][1])
        details[kind].append(row + position + metrics)

    if not overview:
        raise ValueError("该主题没有可导出的事件。请检查 Topic 以及 eventId、eventType 和 Unix time。")
    tabs = [("事件总览", EVENT_COLUMNS, overview)]
    for kind, (title, fields) in DRIVING_EVENTS.items():
        headings = EVENT_COLUMNS + EVENT_COORD_COLUMNS + tuple(label for _, label in fields)
        tabs.append((title, headings, details[kind]))
    return tabs, (invalid, unknown, repeated, conflicts, invalid_lines, unknown_lines)



XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
EXCEL_DATE_FORMAT = "yyyy-mm-dd hh:mm:ss"
INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def write_log_workbook(path, tabs):
    """使用标准库写入日志报表，供 Python 源码和打包版共用。"""
    types = ET.Element("Types", xmlns=CONTENT_TYPES_NS)
    ET.SubElement(types, "Default", Extension="rels",
                  ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(types, "Default", Extension="xml", ContentType="application/xml")
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml."
    ET.SubElement(types, "Override", PartName="/xl/workbook.xml", ContentType=mime + "sheet.main+xml")
    ET.SubElement(types, "Override", PartName="/xl/styles.xml", ContentType=mime + "styles+xml")

    package_rels = ET.Element("Relationships", xmlns=PACKAGE_REL_NS)
    ET.SubElement(package_rels, "Relationship", Id="rId1",
                  Type=OFFICE_REL_NS + "/officeDocument", Target="xl/workbook.xml")
    workbook = ET.Element("workbook", {"xmlns": XLSX_NS, "xmlns:r": OFFICE_REL_NS})
    ET.SubElement(ET.SubElement(workbook, "bookViews"), "workbookView", activeTab="0")
    sheets = ET.SubElement(workbook, "sheets")
    workbook_rels = ET.Element("Relationships", xmlns=PACKAGE_REL_NS)
    ET.SubElement(workbook_rels, "Relationship", Id="rIdStyles",
                  Type=OFFICE_REL_NS + "/styles", Target="styles.xml")

    styles = f"""<styleSheet xmlns="{XLSX_NS}">
      <numFmts count="2"><numFmt numFmtId="164" formatCode="{EXCEL_DATE_FORMAT}"/>
        <numFmt numFmtId="165" formatCode="0.######"/></numFmts>
      <fonts count="2">
        <font><sz val="11"/><name val="Microsoft YaHei"/></font>
        <font><b/><sz val="11"/><color rgb="FF000000"/><name val="Microsoft YaHei"/></font>
      </fonts>
      <fills count="3">
        <fill><patternFill patternType="none"/></fill>
        <fill><patternFill patternType="gray125"/></fill>
        <fill><patternFill patternType="solid"><fgColor rgb="FF9DC3E6"/><bgColor indexed="64"/></patternFill></fill>
      </fills>
      <borders count="2">
        <border><left/><right/><top/><bottom/><diagonal/></border>
        <border>
          <left style="thin"><color rgb="FFD9E2EC"/></left>
          <right style="thin"><color rgb="FFD9E2EC"/></right>
          <top style="thin"><color rgb="FFD9E2EC"/></top>
          <bottom style="thin"><color rgb="FFD9E2EC"/></bottom>
          <diagonal/>
        </border>
      </borders>
      <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
      <cellXfs count="6">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
        <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
          <alignment horizontal="center" vertical="center"/>
        </xf>
        <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
        <xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
        <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
        <xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
      </cellXfs>
      <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
    </styleSheet>"""

    def save_xml(archive, name, node):
        archive.writestr(name, ET.tostring(node, encoding="utf-8", xml_declaration=True))

    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for index, (name, headings, rows) in enumerate(tabs, 1):
            filename = f"worksheets/sheet{index}.xml"
            rid = f"rId{index}"
            ET.SubElement(sheets, "sheet", {"name": name, "sheetId": str(index), "r:id": rid})
            ET.SubElement(workbook_rels, "Relationship", Id=rid,
                          Type=OFFICE_REL_NS + "/worksheet", Target=filename)
            ET.SubElement(types, "Override", PartName=f"/xl/{filename}",
                          ContentType=mime + "worksheet+xml")
            save_xml(archive, "xl/" + filename, log_worksheet(headings, rows))
        archive.writestr("xl/styles.xml", styles)
        save_xml(archive, "[Content_Types].xml", types)
        save_xml(archive, "_rels/.rels", package_rels)
        save_xml(archive, "xl/workbook.xml", workbook)
        save_xml(archive, "xl/_rels/workbook.xml.rels", workbook_rels)


def excel_column_name(number):
    letters = []
    while number:
        number, offset = divmod(number - 1, 26)
        letters.append(chr(ord("A") + offset))
    return "".join(reversed(letters))


def log_worksheet(headings, rows):
    if len(rows) > 1048575:
        raise ValueError("导出数据超过单个 Excel 工作表的行数上限，请缩小筛选范围。")
    if len(headings) > 16384:
        raise ValueError("导出字段超过单个 Excel 工作表的列数上限。")
    worksheet = ET.Element("worksheet", xmlns=XLSX_NS)
    views = ET.SubElement(worksheet, "sheetViews")
    view = ET.SubElement(views, "sheetView", workbookViewId="0", showGridLines="1")
    ET.SubElement(view, "pane", ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
    columns = ET.SubElement(worksheet, "cols")
    column_widths = {
        "eventId": 42, "eventType": 25, "事件中文": 16, "time（北京时间）": 26,
        "lon（经度）": 17, "lat（纬度）": 17, "接收时间（北京时间）": 28,
        "Topic": 34, "status（32 位二进制）": 39, "源文件": 34,
        "CAN 线路状态": 44, "CAN 中断接收": 55, "CAN 中断接收标识": 30,
        "FOTA 升级状态": 32, "事件 ID": 42,
    }
    coordinate_indices = {index for index, heading in enumerate(headings) if heading in EVENT_COORD_COLUMNS}
    status_text_indices = {
        index for index, heading in enumerate(headings)
        if heading in ("status（十六进制）", "status（32 位二进制）")
    }
    for index, heading in enumerate(headings, 1):
        width = column_widths.get(heading, max(14, len(heading) * 2 + 3))
        if heading.endswith("（北京时间）"):
            width = max(26, width)
        ET.SubElement(columns, "col", min=str(index), max=str(index), width=str(width), customWidth="1")
    column_names = [excel_column_name(index) for index in range(1, len(headings) + 1)]
    data = ET.SubElement(worksheet, "sheetData")
    excel_epoch = datetime(1899, 12, 30)
    for row_number, values in enumerate(chain((headings,), rows), 1):
        row = ET.SubElement(data, "row", r=str(row_number))
        if row_number == 1:
            row.attrib.update(ht="24", customHeight="1")
        for index, value in enumerate(values):
            cell = ET.SubElement(row, "c", r=f"{column_names[index]}{row_number}")
            cell.set("s", "1" if row_number == 1 else "4")
            if value is None:
                continue
            if isinstance(value, str):
                if row_number > 1 and index in status_text_indices:
                    cell.set("s", "5")
                cell.set("t", "inlineStr")
                inline = ET.SubElement(cell, "is")
                node = ET.SubElement(inline, "t", {"xml:space": "preserve"})
                node.text = INVALID_XML.sub("\ufffd", value)[:32767]
            elif isinstance(value, bool):
                cell.set("t", "b")
                ET.SubElement(cell, "v").text = "1" if value else "0"
            else:
                if isinstance(value, datetime):
                    cell.set("s", "2")
                    serial = (value - excel_epoch).total_seconds() / 86400
                    value = serial - 1 if serial < 61 else serial
                elif index in coordinate_indices:
                    cell.set("s", "3")
                ET.SubElement(cell, "v").text = str(value)
    ET.SubElement(worksheet, "autoFilter", ref=f"A1:{column_names[-1]}{len(rows) + 1}")
    return worksheet


def export_driving_events(source, target, output):
    tabs, (invalid, unknown, repeated, conflicts, invalid_lines, unknown_lines) = driving_event_rows(source, target)
    write_log_workbook(output, tabs)
    text = f"已导出 {len(tabs[0][2])} 条事件到 9 个工作表。"
    if invalid or unknown or repeated or conflicts:
        text += (f"\n无效 {invalid} 条，重复 {repeated} 条，ID 冲突 {conflicts} 条。"
                 f"未知类型 {unknown} 条保留在总览。")
    if invalid_lines:
        text += "\n无效事件：" + format_source_lines(invalid_lines)
    if unknown_lines:
        text += "\n未知事件类型：" + format_source_lines(unknown_lines)
    return text


def sensor_field_aliases(field_translations):
    aliases = {DEFAULT_FIELD_TRANSLATIONS[field.lower()]: field for field in SENSOR_EVENT_FIELDS}
    for field in SENSOR_EVENT_FIELDS:
        for label in (DEFAULT_FIELD_TRANSLATIONS[field.lower()], field_translations.get(field)):
            if label:
                label = label.strip()
                aliases.setdefault(label, field)
                if field in SENSOR_EVENT_TIMES:
                    aliases.setdefault(label + "（北京时间）", field)
    return aliases


def sensor_field_name(key, aliases):
    if key in SENSOR_EVENT_FIELDS:
        return key
    # 译文遇到同名字段时会附加 [原字段]，优先按原字段识别。
    match = re.search(r" \[([A-Za-z][A-Za-z0-9]*)\](?: \(\d+\))?$", key)
    if match and match[1] in SENSOR_EVENT_FIELDS:
        return match[1]
    return aliases.get(key.strip(), key)


def sensor_event_cell(field, value):
    if field in SENSOR_EVENT_TIMES and type(value) in (int, float, str):
        formatted = format_beijing_unix_time(value)
        try:
            when = datetime.fromisoformat(formatted or str(value))
            if when.tzinfo is not None:
                when = when.astimezone(BEIJING_TZ).replace(tzinfo=None)
            if when >= datetime(1900, 1, 1):
                return when
        except (ValueError, OverflowError):
            pass
    if field == "eventType" and isinstance(value, str):
        return EVENT_TYPE_TRANSLATIONS.get(value, value)
    if field == "sensorStudyStatus" and type(value) is int:
        label = {0: "未标定", 1: "学习中", 2: "学习成功"}.get(value)
        if label:
            return f"{label}（{value}）"
    if isinstance(value, (dict, list)) or (isinstance(value, float) and not math.isfinite(value)):
        return json.dumps(value, ensure_ascii=False)
    return value


def export_sensor_events(source, target, output, field_translations):
    aliases = sensor_field_aliases(field_translations)
    records = []
    extra_fields = {}
    invalid_lines = []
    for line_number, timestamp, topic, record in iter_mqtt_log(source):
        if not topic_matches(topic, target) or not re.fullmatch(r"sensor/event/[0-9]+", topic):
            continue
        payload = mqtt_log_payload(record)
        if not isinstance(payload, dict):
            invalid_lines.append(line_number)
            continue
        values = {}
        for key, value in payload.items():
            field = sensor_field_name(key, aliases)
            if field == "samples":
                continue
            cell = sensor_event_cell(field, value)
            if field in values:
                if values[field] == cell:
                    continue
                field = f"{key}（原始字段）"
            if field not in SENSOR_EVENT_FIELDS:
                extra_fields.setdefault(field, None)
            values[field] = cell
        records.append((timestamp, topic, line_number, values))

    note = ""
    if invalid_lines:
        note = f"\n跳过 {len(invalid_lines)} 条无法读取 JSON 对象的消息。" + format_source_lines(invalid_lines)
    if not records:
        raise ValueError("该主题没有可导出的传感器事件。" + note)

    fields = tuple(field for field in SENSOR_EVENT_FIELDS if field != "samples")
    headings = ("接收时间（北京时间）", "Topic", "行号") + tuple(
        DEFAULT_FIELD_TRANSLATIONS[field.lower()] + ("（北京时间）" if field in SENSOR_EVENT_TIMES else "")
        for field in fields
    )
    headings += tuple(f"字段：{field}" if field in headings else field for field in extra_fields)
    rows = [
        (sensor_event_cell("time", timestamp), topic, line_number)
        + tuple(values.get(field) for field in (*fields, *extra_fields))
        for timestamp, topic, line_number, values in records
    ]
    write_log_workbook(output, [("传感器事件", headings, rows)])
    return f"已导出 {len(rows)} 条传感器事件。" + note


def export_heartbeat_status(sources, device, model, output):
    fields = HEARTBEAT_STATUS_PROFILES[model]
    headings = HEARTBEAT_EXPORT_COLUMNS + tuple(label for _, _, _, label, _ in fields)
    rows = []
    invalid_count = 0
    invalid_examples = []
    for source in sources:
        for line_number, timestamp, topic, record in iter_mqtt_log(source):
            match = HEARTBEAT_LOG_TOPIC.fullmatch(topic)
            if not match or not match[1] or (device and match[1] != device):
                continue
            payload = mqtt_log_payload(record)
            try:
                value = payload.get("status") if isinstance(payload, dict) else None
                number, binary, decoded = parse_heartbeat_status(value, model)
            except ValueError:
                invalid_count += 1
                if len(invalid_examples) < 8:
                    invalid_examples.append(f"{source.name} 第 {line_number} 行")
                continue
            try:
                received_at = datetime.fromisoformat(timestamp)
            except ValueError:
                received_at = timestamp
            base = (received_at, topic, model, number, f"0x{number:08X}", binary, source.name, line_number)
            meanings = tuple(f"{meaning}（{raw}）" for _, _, _, raw, meaning in decoded)
            rows.append(base + meanings)

    invalid_note = ""
    if invalid_count:
        examples = "、".join(invalid_examples)
        more = "等" if invalid_count > len(invalid_examples) else ""
        invalid_note = f"\n跳过 {invalid_count} 条无效 status。{examples}{more}。"
    if not rows:
        raise ValueError("所选日志中没有符合筛选条件的有效心跳。" + invalid_note)
    write_log_workbook(output, [("心跳明细", headings, rows)])
    return f"已导出 {len(rows)} 条 {model} 心跳。" + invalid_note


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """返回开发环境或 PyInstaller 单文件环境中的资源路径。"""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)


def topic_file_path():
    return os.path.join(app_base_dir(), TOPICS_SAVE_FILE)


def field_translations_file_path():
    return os.path.join(app_base_dir(), FIELD_TRANSLATIONS_FILE)


def unrecognized_fields_file_path():
    return os.path.join(app_base_dir(), UNRECOGNIZED_FIELDS_FILE)

def decrypt_encrypted_string(encrypted_bytes: bytes) -> str:
    """
    AES256-CBC 解密，固定 KEY_BYTES 和 IV_BYTES。
    encrypted_bytes: 接收到的原始加密 bytes 数据
    返回解密后的 UTF-8 字符串
    """
    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, IV_BYTES)
    plain = cipher.decrypt(encrypted_bytes)

    try:
        plain = unpad(plain, AES.block_size)
    except ValueError:
        # 如果 padding 不正确，不中断，继续尝试 decode
        pass

    return plain.decode("utf-8", errors="ignore")


def encrypt_json_payload(json_text: str):
    """
    校验 JSON 格式，再将用户输入的原文按 AES-256-CBC + PKCS7 加密。

    JSON 中的空格、换行也是明文的一部分，不做压缩或重排，
    以便与在线 AES 工具按原文加密的结果保持一致。

    返回:
        encrypted_bytes -> 用于 MQTT 发布的密文字节
        source_json     -> 实际参与加密的 UTF-8 JSON 原文
    """
    source_json = json_text.strip()
    json.loads(source_json)
    plain_bytes = source_json.encode("utf-8")
    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, IV_BYTES)
    encrypted_bytes = cipher.encrypt(pad(plain_bytes, AES.block_size, style="pkcs7"))
    return encrypted_bytes, source_json

def parse_gt115_payload(payload_bytes: bytes):
    """
    GT115_ZBY 模式统一解析函数

    返回:
        obj             -> 用于显示/保存的数据对象
        decrypt_status  -> "解密成功" / "解密失败"
        failed_hex      -> 如果失败，返回原始HEX；成功则为 None

    判定标准：
    - 先 AES 解密
    - 再 json.loads()
    - 只有 JSON 解析成功才算“解密成功”
    """
    failed_hex = payload_bytes.hex().upper()

    try:
        decrypted = decrypt_encrypted_string(payload_bytes)
        obj = json.loads(decrypted)
        return obj, "解密成功", None
    except Exception as e:
        obj = {
            "decrypt_status": "解密失败",
            "error": str(e),
            "raw_hex": failed_hex
        }
        return obj, "解密失败", failed_hex

def enable_entry_undo(entry, variable):
    """为单行输入框记录文本变化，支持 Tk 的撤销快捷键。"""
    history = deque([variable.get()], maxlen=100)
    pending = None

    def save_snapshot():
        nonlocal pending
        pending = None
        value = variable.get()
        if value != history[-1]:
            history.append(value)

    def record_change(*_):
        nonlocal pending
        # 粘贴替换选区可能先删除再插入，合并同一轮事件中的写入。
        if pending is None and variable.get() != history[-1]:
            pending = entry.after_idle(save_snapshot)

    def undo(_event):
        if pending is not None:
            entry.after_cancel(pending)
            save_snapshot()
        if len(history) > 1:
            history.pop()
            variable.set(history[-1])
            entry.icursor(tk.END)
        return "break"

    trace = variable.trace_add("write", record_change)

    def cleanup(_event):
        if pending is not None:
            entry.after_cancel(pending)
        variable.trace_remove("write", trace)

    entry.bind("<<Undo>>", undo)
    entry.bind("<Destroy>", cleanup, add="+")


# ----------------------------
# 主应用
# ----------------------------
class MQTT_AES_Pro_v2(tk.Tk):
    def __init__(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
            except (AttributeError, OSError):
                pass
        super().__init__()
        self.title(f"{APP_NAME}    {APP_RELEASE_DATE}    {APP_NOTICE}    {APP_CONTACT}")
        self.geometry("1220x720")
        self.minsize(980, 620)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._native_icon_handles = []
        self._window_menu_subclass = None
        self._icon_refresh_after_id = None
        self._configure_window_icon()
        self.bind("<Map>", self._on_window_mapped, add="+")

        # MQTT
        self.client = None
        self.client_thread = None
        self.mqtt_connected = False
        self.connection_phase = "disconnected"
        self._connection_timeout_after_id = None
        self.auto_reconnect_enabled = True
        self._stop_event = threading.Event()
        self._connection_cancel = None
        self._mqtt_ui_queue = queue.SimpleQueue()
        self._subscription_targets = set()
        self._active_subscriptions = set()
        self._uncertain_subscriptions = set()
        self._pending_subscriptions = {}

        # Display FIFO
        self.max_messages = DEFAULT_MAX_MESSAGES
        self.message_blocks = deque()

        # Counters
        self.total_received = 0
        self.total_saved = 0

        # UI queue: mqtt -> ui
        # item: (timestamp, topic, qos, payload_obj, decrypt_status)
        self.ui_queue = queue.Queue(maxsize=20000)

        # Save file
        self.saving_enabled = False
        self.save_file = None
        self.translation_save_file = None
        self._base_log_path = None
        self._log_segment_number = 0
        self.save_lock = threading.Lock()

        # GT mode
        self.gt_mode_var = tk.StringVar(value="ZBY 解密")
        self._receive_mode = self.gt_mode_var.get()
        self.gt_mode_var.trace_add("write", self._update_receive_mode)

        # FDCAN工具
        self.fdcan_visible = False

        # 订阅主题自动保存
        self._loading_topics = False
        self._topics_load_failed = False
        self._topics_save_after_id = None
        self.notes_visible = False

        # 字段翻译模式与本地词典
        self.translation_mode = False
        self._output_scroll_source = None
        self.heartbeat_model_var = tk.StringVar(value="选择车型")
        self._last_heartbeat_value = None
        self.field_translations = {}
        self.unrecognized_fields = {}
        self._translation_save_after_id = None

        # Build UI
        self._configure_styles()
        self._build_ui()

        # Start ui queue processing
        self.after(60, self._process_ui_queue)

        # Load topics
        self._load_topics_from_disk()
        self._load_field_translations()
        # 首次显示后固定左右面板比例，避免 Panedwindow 初始宽度为 1 的闪动。
        self.after(20, self._stabilize_initial_layout)

    # -------------------------
    # UI building
    # -------------------------
    def _configure_window_icon(self):
        """设置 Tk 窗口、Windows 标题栏和任务栏运行图标。"""
        ico_path = resource_path(WINDOW_ICON_ICO)
        png_path = resource_path(WINDOW_ICON_PNG)

        if os.path.isfile(png_path):
            try:
                with Image.open(png_path) as source:
                    source = source.convert("RGBA")
                    resampling = getattr(Image, "Resampling", Image).LANCZOS
                    source.thumbnail((256, 256), resampling)
                    self._window_icon_photo = ImageTk.PhotoImage(source)
                self.iconphoto(True, self._window_icon_photo)
            except (OSError, ValueError, tk.TclError) as e:
                logging.warning("PNG 窗口图标加载失败: %s", e)

        if not os.path.isfile(ico_path):
            logging.warning("ICO 窗口图标不存在: %s", ico_path)
            return

        try:
            self.iconbitmap(default=ico_path)
        except tk.TclError as e:
            logging.warning("Tk ICO 窗口图标设置失败: %s", e)

        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            load_image = user32.LoadImageW
            load_image.argtypes = [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            load_image.restype = ctypes.c_void_p
            handles = [
                load_image(None, ico_path, 1, 16, 16, 0x10),
                load_image(None, ico_path, 1, 32, 32, 0x10),
            ]
            self._native_icon_handles = [handle for handle in handles if handle]
            self._schedule_window_icon_refresh()
        except (AttributeError, OSError, TypeError) as e:
            logging.warning("Windows 原生窗口图标设置失败: %s", e)

    def _on_window_mapped(self, event):
        if event.widget is self:
            self._schedule_window_icon_refresh()
            if sys.platform == "win32" and self._window_menu_subclass is None:
                self._disable_windows_system_menu()

    def _disable_windows_system_menu(self):
        """拦截主窗口的原生系统菜单，保留标题栏操作。"""
        get_ancestor = ctypes.windll.user32.GetAncestor
        get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
        get_ancestor.restype = wintypes.HWND
        hwnd = get_ancestor(self.winfo_id(), 2)  # GA_ROOT
        if not hwnd:
            return

        comctl32 = ctypes.windll.comctl32
        subclass_proc = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM, ctypes.c_size_t, ctypes.c_size_t,
        )
        install = comctl32.SetWindowSubclass
        install.argtypes = [wintypes.HWND, subclass_proc, ctypes.c_size_t, ctypes.c_size_t]
        install.restype = wintypes.BOOL
        remove = comctl32.RemoveWindowSubclass
        remove.argtypes = [wintypes.HWND, subclass_proc, ctypes.c_size_t]
        remove.restype = wintypes.BOOL
        forward = comctl32.DefSubclassProc
        forward.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        forward.restype = ctypes.c_ssize_t

        @subclass_proc
        def handle_message(window, message, wparam, lparam, subclass_id, _):
            if message == 0x0112 and (wparam & 0xFFF0) in (0xF090, 0xF100):
                # WM_SYSCOMMAND: SC_MOUSEMENU / SC_KEYMENU
                return 0
            if message == 0x0082:  # WM_NCDESTROY
                remove(window, handle_message, subclass_id)
            return forward(window, message, wparam, lparam)

        if install(hwnd, handle_message, 1, 0):
            self._window_menu_subclass = handle_message  # 保持回调存活直到窗口销毁
        else:
            logging.warning("无法为主窗口屏蔽 Windows 系统菜单")

    def _schedule_window_icon_refresh(self):
        """在 Windows 顶级窗口真正创建后补设图标，避免 Tk 映射时覆盖。"""
        if self._icon_refresh_after_id is not None:
            try:
                self.after_cancel(self._icon_refresh_after_id)
            except (tk.TclError, ValueError):
                pass
        self._icon_refresh_after_id = self.after_idle(self._refresh_window_icon_after_map)

    def _refresh_window_icon_after_map(self):
        self._icon_refresh_after_id = None
        ico_path = resource_path(WINDOW_ICON_ICO)
        try:
            if os.path.isfile(ico_path):
                self.iconbitmap(default=ico_path)
        except tk.TclError:
            pass
        try:
            if hasattr(self, "_window_icon_photo"):
                self.iconphoto(True, self._window_icon_photo)
        except tk.TclError:
            pass
        self._apply_native_window_icons()
        # Tk 的外层 HWND 可能比 <Map> 晚一个消息循环完成，再补设一次。
        self.after(120, self._apply_native_window_icons)

    def _apply_native_window_icons(self):
        if sys.platform != "win32" or len(self._native_icon_handles) < 2:
            return
        try:
            user32 = ctypes.windll.user32
            get_ancestor = user32.GetAncestor
            get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            get_ancestor.restype = ctypes.c_void_p
            send_message = user32.SendMessageW
            send_message.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            send_message.restype = ctypes.c_void_p
            child_hwnd = self.winfo_id()
            root_hwnd = get_ancestor(child_hwnd, 2)
            for target_hwnd in {child_hwnd, root_hwnd}:
                if not target_hwnd:
                    continue
                send_message(target_hwnd, 0x0080, 0, self._native_icon_handles[0])
                send_message(target_hwnd, 0x0080, 1, self._native_icon_handles[1])
        except (AttributeError, OSError, TypeError, tk.TclError):
            pass

    def _configure_styles(self):
        """配置统一的浅色卡片风格。"""
        self.configure(bg="#F3F6FA")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # 移除 clam 主题在按钮、下拉菜单和复选框获得焦点时的虚线框。
        style.layout("TButton", [
            ("Button.border", {
                "sticky": "nswe",
                "border": "1",
                "children": [
                    ("Button.padding", {
                        "sticky": "nswe",
                        "children": [("Button.label", {"sticky": "nswe"})],
                    }),
                ],
            }),
        ])
        style.layout("TMenubutton", [
            ("Menubutton.border", {
                "sticky": "nswe",
                "children": [
                    ("Menubutton.indicator", {"side": "right", "sticky": ""}),
                    ("Menubutton.padding", {
                        "sticky": "we",
                        "children": [("Menubutton.label", {"side": "left", "sticky": ""})],
                    }),
                ],
            }),
        ])
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {
                "sticky": "nswe",
                "children": [
                    ("Checkbutton.indicator", {"side": "left", "sticky": ""}),
                    ("Checkbutton.label", {"side": "left", "sticky": "w"}),
                ],
            }),
        ])

        normal_font = ("Microsoft YaHei UI", 9)
        bold_font = ("Microsoft YaHei UI", 9, "bold")
        style.configure(".", font=normal_font)
        style.configure("App.TFrame", background="#F3F6FA")
        style.configure("Header.TFrame", background="#17324D")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure(
            "Card.TLabelframe",
            background="#FFFFFF",
            bordercolor="#D9E2EC",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background="#FFFFFF",
            foreground="#183B56",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure("Card.TLabel", background="#FFFFFF", foreground="#334E68")
        style.configure("Muted.TLabel", background="#FFFFFF", foreground="#829AB1")
        style.configure("Footer.TLabel", background="#F3F6FA", foreground="#486581")
        style.configure("Card.TCheckbutton", background="#FFFFFF", foreground="#334E68")
        style.map("Card.TCheckbutton", background=[("active", "#FFFFFF")])
        style.configure("TEntry", padding=3, fieldbackground="#FFFFFF", foreground="#102A43")
        style.configure("TSpinbox", padding=3, fieldbackground="#FFFFFF")
        style.configure(
            "Heartbeat.TCombobox", fieldbackground="#FFFFFF", foreground="#102A43",
        )
        style.map(
            "Heartbeat.TCombobox",
            fieldbackground=[("readonly", "#FFFFFF")],
            foreground=[("readonly", "#102A43")],
            selectbackground=[("readonly", "#FFFFFF")],
            selectforeground=[("readonly", "#102A43")],
        )
        style.configure("TButton", padding=(8, 4), borderwidth=1)
        style.configure("Compact.TButton", padding=(6, 2), borderwidth=1, font=("Microsoft YaHei UI", 8))
        style.configure(
            "DataTool.TButton",
            padding=(5, 1),
            borderwidth=0,
            relief="flat",
            background="#17324D",
            foreground="#D6E4F0",
            font=("Microsoft YaHei UI", 8),
        )
        style.map(
            "DataTool.TButton",
            background=[("active", "#234766"), ("pressed", "#2B5678")],
            foreground=[("active", "#FFFFFF"), ("disabled", "#829AB1")],
        )
        style.layout("DataTool.TButton", [
            ("Button.padding", {
                "sticky": "nswe",
                "children": [("Button.label", {"sticky": "nswe"})],
            }),
        ])
        style.configure(
            "ToggleActive.TButton",
            padding=(6, 2),
            borderwidth=1,
            background="#DBEAFE",
            foreground="#1D4ED8",
            bordercolor="#60A5FA",
            font=("Microsoft YaHei UI", 8, "bold"),
        )
        style.map(
            "ToggleActive.TButton",
            background=[("active", "#BFDBFE"), ("pressed", "#93C5FD")],
            foreground=[("disabled", "#94A3B8")],
        )
        style.configure("RowDelete.TButton", padding=(4, 1), borderwidth=1, foreground="#B42318", font=("Microsoft YaHei UI", 8))
        style.configure("Enabled.TButton", padding=(4, 1), borderwidth=1, background="#DCFCE7", foreground="#166534", font=("Microsoft YaHei UI", 8))
        style.map("Enabled.TButton", background=[("active", "#BBF7D0")])
        style.configure("Disabled.TButton", padding=(4, 1), borderwidth=1, background="#F1F5F9", foreground="#64748B", font=("Microsoft YaHei UI", 8))
        style.map("Disabled.TButton", background=[("active", "#E2E8F0")])
        style.configure(
            "Primary.TButton",
            background="#2563EB",
            foreground="#FFFFFF",
            bordercolor="#2563EB",
            font=bold_font,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1D4ED8"), ("disabled", "#AFC5EC")],
            foreground=[("disabled", "#F8FAFC")],
        )
        style.configure(
            "Disconnect.TButton",
            background="#FEE2E2",
            foreground="#B91C1C",
            bordercolor="#FCA5A5",
            font=bold_font,
        )
        style.map(
            "Disconnect.TButton",
            background=[("active", "#FECACA"), ("pressed", "#FCA5A5")],
        )
        style.configure("Danger.TButton", foreground="#B42318")
        style.configure("Pane.TPanedwindow", background="#F3F6FA")

    def _make_text_box(self, parent, **kwargs):
        """创建统一样式的文本框。"""
        options = {
            "font": ("Consolas", 9),
            "background": "#F8FAFC",
            "foreground": "#102A43",
            "insertbackground": "#2563EB",
            "relief": "flat",
            "borderwidth": 0,
            "highlightthickness": 1,
            "highlightbackground": "#CBD5E1",
            "highlightcolor": "#2563EB",
            "padx": 5,
            "pady": 4,
        }
        options.update(kwargs)
        return tk.Text(parent, **options)

    def _setup_output_watermark(self, parent):
        """在输出区右下角放置半透明水印。"""
        image_path = resource_path(WATERMARK_RELATIVE_PATH)
        if not os.path.exists(image_path):
            logging.warning("水印图片不存在: %s", image_path)
            return
        try:
            with Image.open(image_path) as source:
                source = source.convert("RGBA")
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                source.thumbnail(WATERMARK_SIZE, resampling)
                prepared = Image.new("RGBA", WATERMARK_SIZE, (0, 0, 0, 0))
                paste_x = (WATERMARK_SIZE[0] - source.width) // 2
                paste_y = (WATERMARK_SIZE[1] - source.height) // 2
                prepared.alpha_composite(source, (paste_x, paste_y))
                alpha = prepared.getchannel("A").point(
                    lambda value: int(value * WATERMARK_OPACITY)
                )
                prepared.putalpha(alpha)
                self.output_watermark_photo = ImageTk.PhotoImage(prepared)
        except Exception as e:
            logging.exception("水印图片加载失败: %s", e)
            return

        background = self.text_display.cget("background")
        self.output_watermark_label = tk.Label(
            parent,
            image=self.output_watermark_photo,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            takefocus=0,
        )
        horizontal_inset = (
            int(self.text_display.cget("padx"))
            + int(self.text_display.cget("highlightthickness"))
            + int(self.text_display.cget("borderwidth"))
        )
        vertical_inset = (
            int(self.text_display.cget("pady"))
            + int(self.text_display.cget("highlightthickness"))
            + int(self.text_display.cget("borderwidth"))
        )
        self.output_watermark_label.place(
            in_=self.text_display, relx=1.0, rely=1.0,
            x=-(WATERMARK_MARGIN - horizontal_inset),
            y=-(WATERMARK_MARGIN - vertical_inset),
            anchor="se", width=WATERMARK_SIZE[0], height=WATERMARK_SIZE[1],
        )
        self._watermark_raised = False
        self._watermark_refresh_pending = False
        self.output_watermark_label.lower(self.text_display)
        self.text_display.bind("<<Selection>>", self._queue_watermark_refresh, add="+")
        self.text_display.bind("<Configure>", self._queue_watermark_refresh, add="+")
        self.output_watermark_label.bind("<Configure>", self._queue_watermark_refresh, add="+")
        self._queue_watermark_refresh()

        for sequence in (
            "<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>",
            "<Double-Button-1>", "<Triple-Button-1>", "<ButtonPress-3>",
            "<ButtonRelease-3>", "<MouseWheel>",
        ):
            self.output_watermark_label.bind(
                sequence,
                lambda event, event_sequence=sequence: self._forward_watermark_event(
                    event_sequence, event
                ),
            )

    def _queue_watermark_refresh(self, event=None):
        if hasattr(self, "output_watermark_label") and not self._watermark_refresh_pending:
            self._watermark_refresh_pending = True
            self.after_idle(self._refresh_output_watermark)

    def _refresh_output_watermark(self):
        self._watermark_refresh_pending = False
        mark = self.output_watermark_label
        output = self.text_display
        left = mark.winfo_x() - output.winfo_x()
        top = mark.winfo_y() - output.winfo_y()
        bottom = top + mark.winfo_height()
        show = mark.winfo_ismapped() and left >= 0 and top >= 0 and not output.tag_ranges("sel")
        y = top
        while show and y < bottom:
            bounds = output.dlineinfo(f"@0,{y}")
            if not bounds:
                break
            line_x, line_y, line_width, line_height, _ = bounds
            line_bottom = line_y + line_height
            if line_bottom <= y:
                break
            if line_y < bottom and line_x + line_width > left:
                show = False
            y = line_bottom
        if show != self._watermark_raised:
            if show:
                mark.lift(output)
            else:
                mark.lower(output)
            self._watermark_raised = show

    def _forward_watermark_event(self, sequence, event):
        x = event.x_root - self.text_display.winfo_rootx()
        y = event.y_root - self.text_display.winfo_rooty()
        if sequence == "<ButtonPress-1>":
            self.text_display.focus_set()
        options = {"x": x, "y": y, "state": event.state}
        if sequence == "<MouseWheel>":
            options["delta"] = event.delta
        self.text_display.event_generate(sequence, **options)
        return "break"

    def _open_log_tool(self, mode, *, heartbeat_model="GT115", parent=None):
        title, action_label, target_label = {
            "filter": ("Topic 筛选", "导出 TXT", "Topic 或主题前缀"),
            "kml": ("经纬度提取", "导出 KML", "IMEI 或 loc/主题"),
            "events": ("驾驶行为分析", "导出 Excel", "IMEI 或 driving/event/主题"),
            "sensor": ("传感器事件解析", "导出 Excel", "IMEI 或 sensor/event/主题"),
            "heartbeat": ("心跳批量解析", "导出 Excel", "IMEI 或心跳 Topic"),
        }[mode]
        owner = parent if parent is not None else self
        dialog = tk.Toplevel(owner)
        dialog.title(title)
        dialog.transient(owner)
        dialog.configure(background="#F3F6FA")
        dialog.geometry("720x340")
        dialog.minsize(660, 300)
        page = ttk.Frame(dialog, style="App.TFrame")
        page.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(page, style="Header.TFrame", height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        ttk.Label(
            header, text=title, background="#17324D", foreground="#FFFFFF",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side=tk.LEFT, padx=14)
        ttk.Label(
            header, text="日志数据导出", background="#17324D", foreground="#BCCCDC",
        ).pack(side=tk.RIGHT, padx=14)
        body = ttk.Frame(page, style="Card.TFrame", padding=(14, 12))
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        body.columnconfigure(1, weight=1)
        source_text, destination_text = tk.StringVar(dialog), tk.StringVar(dialog)
        default_target = {
            "kml": "loc/", "events": "driving/event/", "heartbeat": "heartbeat/", "sensor": SENSOR_EVENT_TOPIC,
        }.get(mode, "")
        target_text = tk.StringVar(dialog, default_target)
        status = tk.StringVar(dialog)
        old_speed_scale = tk.BooleanVar(dialog, True)
        model_var = tk.StringVar(dialog, heartbeat_model)
        selected_logs = ()
        result = queue.SimpleQueue()

        def select_source():
            nonlocal selected_logs
            filetypes = [("日志文件", ("*.txt", "*.log")), ("所有文件", "*.*")]
            if mode == "heartbeat":
                paths = filedialog.askopenfilenames(parent=dialog, title="选择 MQTT 原文日志", filetypes=filetypes)
                if paths:
                    selected_logs = tuple(dict.fromkeys(Path(path).resolve() for path in paths))
                    display = str(selected_logs[0]) if len(selected_logs) == 1 else f"已选 {len(selected_logs)} 个日志文件"
                    source_text.set(display)
                    destination_text.set(str(selected_logs[0].parent))
                return
            path = filedialog.askopenfilename(parent=dialog, title="选择 MQTT 原文日志", filetypes=filetypes)
            if path:
                source_text.set(path)
                destination_text.set(str(Path(path).parent))

        def select_destination():
            path = filedialog.askdirectory(
                parent=dialog, title="选择输出目录", initialdir=destination_text.get() or None,
            )
            if path:
                destination_text.set(path)

        for row, (label, variable, browse) in enumerate((
            ("输入日志", source_text, select_source), ("输出目录", destination_text, select_destination),
            (target_label, target_text, None),
        )):
            ttk.Label(body, text=label, style="Card.TLabel", width=18).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=5
            )
            entry_state = "readonly" if mode == "heartbeat" and row == 0 else "normal"
            entry = ttk.Entry(body, textvariable=variable, state=entry_state)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if variable is target_text:
                enable_entry_undo(entry, variable)
            if browse is not None:
                ttk.Button(body, text="浏览…", command=browse, style="Compact.TButton").grid(
                    row=row, column=2, padx=(8, 0), pady=5
                )

        hint = {
            "filter": "完整主题精确匹配，主题末尾加 / 时按前缀筛选。",
            "kml": "输入设备 IMEI，或在 loc/ 后补充设备号。",
            "events": "输入设备 IMEI，或使用 driving/event/ 分析全部设备。",
            "sensor": "支持原文和译文日志。输入 IMEI 可筛选设备，默认解析全部设备。",
            "heartbeat": "可多选日志。填写 IMEI 只解析该设备，heartbeat/ 解析全部设备。",
        }[mode]
        ttk.Label(body, text=hint, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(7, 0)
        )
        if mode == "heartbeat":
            ttk.Label(body, text="车型", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 0))
            ttk.Combobox(
                body, textvariable=model_var, values=tuple(HEARTBEAT_STATUS_PROFILES),
                state="readonly", style="Heartbeat.TCombobox", width=8,
            ).grid(row=4, column=1, sticky="w", pady=(8, 0))
        elif mode == "kml":
            toggle_row = ttk.Frame(body, style="Card.TFrame")
            toggle_row.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
            toggle_bg = ttk.Style(dialog).lookup("Card.TFrame", "background") or "#FFFFFF"
            speed_toggle = tk.Canvas(
                toggle_row, width=18, height=18, highlightthickness=0,
                borderwidth=0, background=toggle_bg, takefocus=True, cursor="hand2",
            )
            speed_toggle.pack(side=tk.LEFT, padx=(0, 5))
            speed_label = ttk.Label(
                toggle_row, text="旧版日志车速 ×0.1", style="Card.TLabel", cursor="hand2"
            )
            speed_label.pack(side=tk.LEFT)

            def refresh_speed_toggle():
                self._draw_circle_toggle(speed_toggle, old_speed_scale.get())

            def toggle_speed_scale(event=None):
                old_speed_scale.set(not old_speed_scale.get())
                refresh_speed_toggle()
                return "break"

            speed_toggle.bind("<Button-1>", toggle_speed_scale)
            speed_toggle.bind("<space>", toggle_speed_scale)
            speed_label.bind("<Button-1>", toggle_speed_scale)
            refresh_speed_toggle()

        def poll():
            try:
                summary, error = result.get_nowait()
            except queue.Empty:
                dialog.after(80, poll)
                return
            run_button.state(["!disabled"])
            dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
            if error is not None:
                status.set("处理失败")
                messagebox.showerror(title, error, parent=dialog)
            else:
                status.set(summary.splitlines()[0])
                messagebox.showinfo(title, summary, parent=dialog)

        def run():
            try:
                sources = selected_logs if mode == "heartbeat" else (Path(source_text.get().strip()).resolve(),)
                if not sources or not all(path.is_file() for path in sources):
                    raise ValueError("请选择有效的输入日志文件。")
                source = sources[0]
                if not destination_text.get().strip():
                    raise ValueError("请选择输出目录。")
                directory = Path(destination_text.get().strip()).resolve()
                if not directory.is_dir():
                    raise ValueError("输出目录不存在。")
                target = analysis_topic(mode, target_text.get())
                model = model_var.get()
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                paths = {
                    "filter": (directory / f"{source.stem}-筛选-{timestamp}.txt",),
                    "kml": (
                        directory / f"{source.stem}_point-{timestamp}.kml",
                        directory / f"{source.stem}_tracker-{timestamp}.kml",
                    ),
                    "events": (directory / f"{source.stem}-驾驶行为-{timestamp}.xlsx",),
                    "sensor": (directory / f"{source.stem}-传感器事件-{timestamp}.xlsx",),
                    "heartbeat": (directory / f"心跳解析-{model}-{timestamp}.xlsx",),
                }[mode]
                if any(path.resolve() in sources or (path.exists() and any(path.samefile(log) for log in sources))
                       for path in paths):
                    raise ValueError("请为导出选择其他目录，避免覆盖输入日志。")
                existing = [path.name for path in paths if path.exists()]
                if existing and not messagebox.askyesno(
                    title, "覆盖现有文件？\n\n" + "\n".join(existing), parent=dialog
                ):
                    return
            except (OSError, ValueError) as exc:
                messagebox.showerror(title, str(exc), parent=dialog)
                return
            scale = 0.1 if old_speed_scale.get() else 1
            sensor_translations = dict(self.field_translations) if mode == "sensor" else {}
            run_button.state(["disabled"])
            status.set("正在处理日志…")
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)

            def worker():
                try:
                    # 所有输出先生成在临时目录，解析失败时保留既有文件。
                    with tempfile.TemporaryDirectory(dir=directory) as staging:
                        staged = [Path(staging) / path.name for path in paths]
                        if mode == "filter":
                            summary = filter_mqtt_log(source, target, staged[0])
                        elif mode == "kml":
                            summary = export_location_kml(source, target, *staged, speed_factor=scale)
                        elif mode == "heartbeat":
                            summary = export_heartbeat_status(sources, target, model, staged[0])
                        elif mode == "sensor":
                            summary = export_sensor_events(source, target, staged[0], sensor_translations)
                        else:
                            summary = export_driving_events(source, target, staged[0])
                        for temp, path in zip(staged, paths):
                            if temp.name in existing:
                                temp.replace(path)
                            else:
                                # Windows 上 rename 在目标已被其他进程创建时会报错。
                                temp.rename(path)
                    result.put((summary + "\n\n" + "\n".join(map(str, paths)), None))
                except Exception as exc:
                    logging.exception("日志处理失败")
                    result.put((None, str(exc)))

            threading.Thread(target=worker, daemon=True).start()
            dialog.after(80, poll)

        footer = ttk.Frame(page, style="App.TFrame")
        footer.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(footer, textvariable=status, style="Footer.TLabel").pack(side=tk.LEFT)
        run_button = ttk.Button(footer, text=action_label, style="Primary.TButton", command=run)
        run_button.pack(side=tk.RIGHT)

    def _open_heartbeat_tool(self):
        dialog = tk.Toplevel(self)
        dialog.title("心跳状态解析")
        dialog.transient(self)
        dialog.geometry("820x740")
        dialog.minsize(740, 650)
        dialog.configure(background="#F3F6FA")

        page = ttk.Frame(dialog, style="Card.TFrame")
        page.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(page, style="Header.TFrame", height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        ttk.Label(
            header, text="心跳状态解析", background="#17324D", foreground="#FFFFFF",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side=tk.LEFT, padx=14)
        ttk.Label(
            header, text="CANFD 嵌入式总线系统状态字段", background="#17324D",
            foreground="#BCCCDC",
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(header, text="车型", background="#17324D", foreground="#BCCCDC").pack(
            side=tk.RIGHT, padx=(6, 4)
        )
        selected_model = self.heartbeat_model_var.get()
        model = tk.StringVar(dialog, selected_model if selected_model in HEARTBEAT_STATUS_PROFILES else "GT115")
        model_menu = ttk.Combobox(
            header, textvariable=model, values=tuple(HEARTBEAT_STATUS_PROFILES),
            state="readonly", width=8, style="Heartbeat.TCombobox",
        )
        model_menu.pack(side=tk.RIGHT, padx=(0, 14), pady=8)
        ttk.Button(
            header, text="批量解析", style="DataTool.TButton",
            command=lambda: self._open_log_tool("heartbeat", heartbeat_model=model.get(), parent=dialog),
        ).pack(side=tk.RIGHT, padx=(0, 10))

        body = ttk.Frame(page, style="Card.TFrame", padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        input_card = ttk.LabelFrame(body, text="数据输入", style="Card.TLabelframe", padding=10)
        input_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for column in range(3):
            input_card.columnconfigure(column, weight=1, uniform="status-input")
        values = {
            "decimal": tk.StringVar(dialog, "0"),
            "hex": tk.StringVar(dialog),
            "binary": tk.StringVar(dialog),
        }
        for column, (key, label) in enumerate((
            ("decimal", "十进制（u32）"),
            ("hex", "十六进制"),
            ("binary", "二进制（32 位）"),
        )):
            section = ttk.Frame(input_card, style="Card.TFrame")
            section.grid(row=0, column=column, sticky="ew", padx=5)
            ttk.Label(section, text=label, style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
            ttk.Entry(section, textvariable=values[key], font=("Consolas", 10)).pack(fill=tk.X)

        bit_card = ttk.LabelFrame(body, text="32 位状态图", style="Card.TLabelframe", padding=10)
        bit_card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        bit_card.columnconfigure(0, weight=1)
        bit_string = tk.StringVar(dialog)
        ttk.Label(
            bit_card, textvariable=bit_string, style="Muted.TLabel", anchor="e",
            font=("Consolas", 8),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 2))
        bit_canvas = tk.Canvas(bit_card, height=64, background="#FFFFFF", highlightthickness=0)
        bit_canvas.grid(row=1, column=0, sticky="ew")

        status_card = ttk.LabelFrame(body, text="状态摘要", style="Card.TLabelframe", padding=10)
        status_card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        status_summary = ttk.Frame(status_card, style="Card.TFrame")
        status_summary.pack(fill=tk.X, ipady=3)

        summary_card = ttk.LabelFrame(body, text="字段详细解析", style="Card.TLabelframe", padding=7)
        summary_card.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        summary_card.columnconfigure(0, weight=1)
        summary_card.rowconfigure(0, weight=1)
        style = ttk.Style(dialog)
        style.configure(
            "Heartbeat.Treeview", rowheight=23,
            font=("Microsoft YaHei UI", 8),
            background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#102A43",
        )
        style.configure(
            "Heartbeat.Treeview.Heading", font=("Microsoft YaHei UI", 8, "bold"),
            background="#EEF3F8", foreground="#334E68", relief="flat",
        )
        style.map("Heartbeat.Treeview", background=[("selected", "#DBEAFE")],
                  foreground=[("selected", "#102A43")])
        tree = ttk.Treeview(
            summary_card, columns=("field", "definition", "range", "raw", "meaning"),
            show="headings", height=14, style="Heartbeat.Treeview",
        )
        for column, heading, width in (
            ("field", "字段名", 82), ("definition", "定义", 140),
            ("range", "位域", 68), ("raw", "值", 48), ("meaning", "状态", 260),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=42 if column in ("field", "raw") else 58,
                        anchor="w", stretch=column == "meaning")
        tree.tag_configure("odd", background="#F0F6FC")
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(summary_card, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        error_text = tk.StringVar(dialog)
        ttk.Label(body, textvariable=error_text, foreground="#B42318").grid(
            row=4, column=0, sticky="w", padx=4
        )

        updating = False

        def update_view(source):
            nonlocal updating
            if updating:
                return
            try:
                text = values[source].get().strip()
                if source == "binary":
                    clean = text.removeprefix("0b").replace("_", "")
                    if not clean or re.fullmatch(r"[01]{1,32}", clean) is None:
                        raise ValueError("请输入最多 32 位的二进制数。")
                    number = int(clean, 2)
                    number, binary, rows = parse_heartbeat_status(
                        number, model.get()
                    )
                elif source == "hex":
                    clean = text[2:] if text.lower().startswith("0x") else text
                    if not clean or re.fullmatch(r"[0-9a-fA-F]{1,8}", clean) is None:
                        raise ValueError("请输入最多 8 位的十六进制数。")
                    number = int(clean, 16)
                    number, binary, rows = parse_heartbeat_status(
                        number, model.get()
                    )
                else:
                    number, binary, rows = parse_heartbeat_status(
                        text, model.get()
                    )
            except ValueError as exc:
                error_text.set(str(exc))
                return

            updating = True
            values["decimal"].set(str(number))
            values["hex"].set(f"0x{number:08X}")
            values["binary"].set(binary)
            updating = False
            error_text.set("")
            tree.delete(*tree.get_children())
            for index, row in enumerate(rows):
                if model.get() == "GD202" and row[0] == "wake_type":
                    row = (*row[:3], "", row[4])
                tree.insert("", tk.END, values=row, tags=("odd",) if index % 2 else ())
            bit_string.set("   ".join(binary[index:index + 4] for index in range(0, 32, 4)))
            bit_canvas.delete("all")
            width = max(32, bit_canvas.winfo_width())
            cell_width = width / 32
            for index, bit in enumerate(binary):
                x0 = index * cell_width + 1
                x1 = (index + 1) * cell_width - 1
                active = bit == "1"
                bit_canvas.create_rectangle(
                    x0, 5, x1, 35, fill="#2563EB" if active else "#F1F5F9",
                    outline="#D9E2EC",
                )
                bit_canvas.create_text(
                    (x0 + x1) / 2, 20, text=bit,
                    fill="#FFFFFF" if active else "#64748B", font=("Consolas", 8),
                )
                bit_canvas.create_text(
                    (x0 + x1) / 2, 48, text=str(31 - index),
                    fill="#829AB1", font=("Consolas", 6),
                )
            for child in status_summary.winfo_children():
                child.destroy()
            self._populate_heartbeat_summary(
                status_summary, rows, model.get()
            )

        for key, variable in values.items():
            variable.trace_add("write", lambda *_args, source=key: update_view(source))
        bit_canvas.bind("<Configure>", lambda _event: update_view("decimal"))
        model_menu.bind("<<ComboboxSelected>>", lambda _event: update_view("decimal"))
        update_view("decimal")

    @staticmethod
    def _heartbeat_summary(rows, model):
        meanings = {name: (raw, meaning) for name, _label, _bits, raw, meaning in rows}
        chips = []

        def add(text, tone):
            colors = {
                "good": ("#E7F7EE", "#167447"),
                "bad": ("#FDECEC", "#B42318"),
                "info": ("#EAF2FF", "#2457A6"),
                "muted": ("#F1F4F8", "#64748B"),
            }
            chips.append((text, colors[tone]))

        can_down, _ = meanings["can_connect"]
        add("CAN 正常" if can_down == 0 else ("CAN 断线" if model == "GT115" else "CAN 待休眠"),
            "good" if can_down == 0 else "bad")
        if meanings["can_recv"][0]:
            add("收到 CAN 数据", "info")
        gps_fixed, _ = meanings["gps_loc"]
        add("GPS 已定位" if gps_fixed else "GPS 未定位", "good" if gps_fixed else "muted")

        fota_value, fota_meaning = meanings["fota_sta"]
        if model == "GT115":
            fota_labels = {0: "无任务", 3: "请求升级包", 4: "下载完成", 5: "升级成功"}
        else:
            fota_labels = {
                0: "无任务", 1: "请求升级", 2: "校验中", 3: "请求文件",
                4: "文件完成", 5: "升级成功", 6: "升级失败", 7: "文件大小错误",
            }
        fota_text = fota_labels.get(fota_value, fota_meaning)
        add(f"FOTA {fota_text}", "bad" if fota_value == 6 else "info" if fota_value else "muted")

        matched, _ = meanings["can_match"]
        add("波特率已匹配" if matched else "波特率未匹配", "good" if matched else "bad")
        can_value, _ = meanings["can_type"]
        if model == "GT115":
            rates = {0: "未知", 1: "50K", 2: "250K", 3: "500K", 4: "125K", 5: "1M"}
            add(f"CAN {rates.get(can_value, '未知')}", "info" if can_value else "muted")
        else:
            can_types = {0: "未知", 1: "经典 CAN", 2: "FD CAN"}
            add(can_types.get(can_value, "CAN 类型未知"), "info" if can_value else "muted")
            arb_value, _ = meanings["can_bsp_arb"]
            arb_rates = {0: "未知", 1: "50K", 2: "500K", 3: "250K", 4: "125K", 5: "1M"}
            add(f"仲裁 {arb_rates.get(arb_value, '未知')}", "info" if arb_value else "muted")
            data_value, _ = meanings["can_bsp_data"]
            data_rates = {0: "未知", 1: "2M", 2: "4M", 3: "5M"}
            add(f"数据 {data_rates.get(data_value, '未知')}", "info" if data_value else "muted")

        wake_value, wake_meaning = meanings["wake_type"]
        add(wake_meaning if wake_meaning != "未知值" else "唤醒未知", "muted" if wake_value == 0 else "info")

        return chips

    def _populate_heartbeat_summary(self, parent, rows, model, *, live=False):
        for text, (background, foreground) in self._heartbeat_summary(rows, model):
            label = tk.Label(
                parent, text=text, background=background, foreground=foreground,
                font=("Microsoft YaHei UI", 9 if live else 8),
                padx=5 if live else 6, pady=1 if live else 3,
            )
            if not live:
                label.pack(side=tk.LEFT, padx=(0, 4), pady=1)
        if live:
            self._layout_live_heartbeat_summary()

    def _layout_live_heartbeat_summary(self, event=None):
        frame = self.heartbeat_summary_frame
        available = frame.winfo_width()
        if available <= 1:
            return
        x, y, row_height = 0, 0, 0
        for label in frame.winfo_children():
            width = min(label.winfo_reqwidth(), available)
            height = label.winfo_reqheight()
            if x and x + width > available:
                x, y, row_height = 0, y + row_height + 2, 0
            label.place(x=x, y=y, width=width)
            x += width + 3
            row_height = max(row_height, height)
        height = max(1, y + row_height)
        if int(frame.cget("height")) != height:
            frame.configure(height=height)

    def _build_ui(self):
        app_frame = ttk.Frame(self, style="App.TFrame")
        app_frame.pack(fill=tk.BOTH, expand=True)

        # 页头
        header = ttk.Frame(app_frame, style="Header.TFrame", height=46)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="ZBY MQTT 数据工具",
            background="#17324D",
            foreground="#FFFFFF",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side=tk.LEFT, padx=(12, 7), pady=7)
        tk.Label(
            header,
            text="AES 加解密 · JSON 发送 · FDCAN 解析",
            background="#17324D",
            foreground="#BCCCDC",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT, pady=0)
        tk.Frame(header, width=1, height=18, background="#54718B").pack(
            side=tk.LEFT, padx=(12, 2), pady=0
        )
        self.connection_status_label = tk.Label(
            header,
            text="●  未连接",
            background="#17324D",
            foreground="#FDA29B",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.connection_status_label.pack(side=tk.RIGHT, padx=13)

        menu_actions = ttk.Frame(header, style="Header.TFrame")
        menu_actions.pack(side=tk.LEFT, padx=(4, 8), pady=0)
        for label, mode in (
            ("Topic 筛选", "filter"), ("经纬度 KML", "kml"),
            ("驾驶分析", "events"), ("传感器事件", "sensor"),
        ):
            ttk.Button(
                menu_actions, text=label, style="DataTool.TButton",
                command=lambda selected=mode: self._open_log_tool(selected),
            ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            menu_actions, text="心跳状态", style="DataTool.TButton",
            command=self._open_heartbeat_tool,
        ).pack(side=tk.LEFT, padx=2)

        # MQTT 连接设置
        connect_card = ttk.LabelFrame(app_frame, text=" MQTT 连接设置 ", style="Card.TLabelframe")
        connect_card.pack(fill=tk.X, padx=10, pady=(7, 5))
        connect_card.columnconfigure(1, weight=2)
        connect_card.columnconfigure(5, weight=1)
        connect_card.columnconfigure(7, weight=1)

        ttk.Label(connect_card, text="服务器", style="Card.TLabel").grid(row=0, column=0, padx=(8, 4), pady=4, sticky="w")
        self.entry_host = ttk.Entry(connect_card, width=22)
        self.entry_host.insert(0, "zte-cid.com")
        self.entry_host.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="ew")

        ttk.Label(connect_card, text="端口", style="Card.TLabel").grid(row=0, column=2, padx=(0, 4), pady=4)
        self.entry_port = ttk.Entry(connect_card, width=6)
        self.entry_port.insert(0, "1883")
        self.entry_port.grid(row=0, column=3, padx=(0, 8), pady=4)

        ttk.Label(connect_card, text="用户名", style="Card.TLabel").grid(row=0, column=4, padx=(0, 4), pady=4)
        self.entry_username = ttk.Entry(connect_card, width=11)
        self.entry_username.insert(0, "admin")
        self.entry_username.grid(row=0, column=5, padx=(0, 8), pady=4, sticky="ew")

        ttk.Label(connect_card, text="密码", style="Card.TLabel").grid(row=0, column=6, padx=(0, 4), pady=4)
        self.entry_password = ttk.Entry(connect_card, width=11, show="●")
        self.entry_password.insert(0, "Zbwd@010")
        self.entry_password.grid(row=0, column=7, padx=(0, 8), pady=4, sticky="ew")

        self.btn_connection = ttk.Button(
            connect_card,
            text="连接",
            style="Primary.TButton",
            command=self._toggle_connection,
            width=10,
        )
        self.btn_connection.grid(row=0, column=8, columnspan=2, padx=(0, 6), pady=4)

        self.auto_reconnect_var = tk.BooleanVar(value=self.auto_reconnect_enabled)
        auto_reconnect_frame = ttk.Frame(connect_card, style="Card.TFrame")
        auto_reconnect_frame.grid(row=0, column=10, padx=(0, 6), pady=4)
        self.auto_reconnect_button = tk.Canvas(
            auto_reconnect_frame,
            width=18,
            height=18,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.auto_reconnect_button.pack(side=tk.LEFT)
        self.auto_reconnect_button.bind("<Button-1>", lambda event: self._toggle_auto_reconnect())
        ttk.Label(auto_reconnect_frame, text="自动重连", style="Card.TLabel").pack(side=tk.LEFT, padx=(3, 0))
        self._refresh_auto_reconnect_button()
        ttk.Label(connect_card, text="显示行数", style="Card.TLabel").grid(row=0, column=11, padx=(0, 3), pady=4)
        self.spin_max = ttk.Spinbox(connect_card, from_=100, to=10000, width=6)
        self.spin_max.set(str(self.max_messages))
        self.spin_max.grid(row=0, column=12, padx=(0, 3), pady=4)
        ttk.Button(connect_card, text="应用", style="Compact.TButton", command=self._apply_max_messages).grid(row=0, column=13, padx=(0, 4), pady=4)
        self.btn_fdcan = ttk.Button(connect_card, text="FDCAN 解析", style="Compact.TButton", command=self.toggle_fdcan_panel)
        self.btn_fdcan.grid(row=0, column=14, padx=(0, 8), pady=4)

        self.main_pane = ttk.Panedwindow(app_frame, orient=tk.HORIZONTAL, style="Pane.TPanedwindow")
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)

        # 左侧：订阅和发送
        left_frame = ttk.Frame(self.main_pane, width=450, style="App.TFrame")
        self.main_pane.add(left_frame, weight=0)

        subscribe_card = ttk.LabelFrame(left_frame, text=" 订阅主题 ", style="Card.TLabelframe")
        subscribe_card.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        sub_header = ttk.Frame(subscribe_card, style="Card.TFrame", height=20)
        sub_header.pack(fill=tk.X, padx=(7, 20), pady=(4, 1))
        sub_header.pack_propagate(False)
        self.sub_header = sub_header
        self.sub_header_labels = {
            "enabled_button": ttk.Label(sub_header, text="状态", style="Muted.TLabel", anchor="center"),
            "topic_entry": ttk.Label(sub_header, text="MQTT 主题", style="Muted.TLabel", anchor="w"),
            "delete_button": ttk.Label(sub_header, text="删除", style="Muted.TLabel", anchor="center"),
            "note_entry": ttk.Label(sub_header, text="用途备注", style="Muted.TLabel", anchor="w"),
        }

        sub_list = ttk.Frame(subscribe_card, style="Card.TFrame")
        sub_list.pack(fill=tk.BOTH, expand=True, padx=7)
        self.sub_canvas = tk.Canvas(
            sub_list,
            height=135,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=27,
            confine=True,
        )
        sub_scroll = ttk.Scrollbar(sub_list, orient=tk.VERTICAL, command=self.sub_canvas.yview)
        self.sub_canvas.configure(yscrollcommand=sub_scroll.set)
        self.sub_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sub_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.sub_frame = ttk.Frame(self.sub_canvas, style="Card.TFrame")
        self.sub_canvas_window = self.sub_canvas.create_window((0, 0), window=self.sub_frame, anchor="nw")
        self.sub_frame.bind("<Configure>", self._refresh_subscription_scrollregion)
        self.sub_canvas.bind("<Configure>", self._resize_subscription_canvas)
        self.sub_canvas.bind("<MouseWheel>", self._scroll_subscriptions)

        self.sub_entries = []
        self._add_subscription_row("test/topic", "", True, schedule_save=False)

        btn_sub_controls = ttk.Frame(subscribe_card, style="Card.TFrame")
        btn_sub_controls.pack(fill=tk.X, padx=7, pady=(3, 6))
        ttk.Button(btn_sub_controls, text="＋ 添加主题", style="Compact.TButton", command=lambda: self._add_subscription_row("")).pack(side=tk.LEFT)
        self.notes_toggle_button = ttk.Button(
            btn_sub_controls,
            text="显示备注",
            style="Compact.TButton",
            command=self._toggle_notes_visibility,
        )
        self.notes_toggle_button.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_sub_controls, text="订阅勾选主题", style="Primary.TButton", command=self.subscribe_all).pack(side=tk.RIGHT)
        ttk.Button(btn_sub_controls, text="取消所有订阅", style="Compact.TButton", command=self.unsubscribe_all).pack(side=tk.RIGHT, padx=4)

        publish_frame = ttk.LabelFrame(left_frame, text=" AES 加密发送 ", style="Card.TLabelframe")
        publish_frame.pack(fill=tk.X)
        ttk.Label(publish_frame, text="发送主题", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(5, 2))
        publish_topic = tk.StringVar(publish_frame)
        self.publish_topic_entry = ttk.Entry(publish_frame, textvariable=publish_topic)
        self.publish_topic_entry.pack(fill=tk.X, padx=7, pady=(0, 4))
        enable_entry_undo(self.publish_topic_entry, publish_topic)
        self.publish_topic_entry.bind("<Return>", self._confirm_publish_input)
        ttk.Label(publish_frame, text="JSON 数据", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(0, 2))
        self.publish_data_text = self._make_text_box(
            publish_frame, height=2, wrap="char", undo=True, autoseparators=True, maxundo=100
        )
        self.publish_data_text.pack(fill=tk.X, padx=7, pady=(0, 4))
        self.publish_data_text.bind("<Control-Return>", self._publish_shortcut)
        self.publish_data_text.bind("<Return>", self._confirm_publish_input)
        publish_controls = ttk.Frame(publish_frame, style="Card.TFrame")
        publish_controls.pack(fill=tk.X, padx=7, pady=(0, 6))
        self.btn_publish = ttk.Button(publish_controls, text="加密并发送", style="Primary.TButton", command=self.publish_encrypted_json)
        self.btn_publish.pack(side=tk.LEFT)
        self.publish_status_label = ttk.Label(publish_controls, text="Ctrl+Enter 快捷发送", style="Muted.TLabel")
        self.publish_status_label.pack(side=tk.LEFT, padx=6)

        # 中间可选：FDCAN 解析
        self.fdcan_frame = ttk.LabelFrame(self.main_pane, text=" FDCAN 数据解析 ", style="Card.TLabelframe", width=330)
        ttk.Label(self.fdcan_frame, text="输入 HEX 数据", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(5, 2))
        self.fdcan_input = self._make_text_box(self.fdcan_frame, height=7)
        self.fdcan_input.pack(fill=tk.X, padx=7, pady=(0, 4))
        ttk.Button(self.fdcan_frame, text="开始解析", style="Primary.TButton", command=self.parse_fdcan).pack(anchor=tk.W, padx=7, pady=(0, 5))
        ttk.Label(self.fdcan_frame, text="解析结果", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(0, 2))
        self.fdcan_output = self._make_text_box(self.fdcan_frame, wrap="char")
        self.fdcan_output.pack(fill=tk.BOTH, expand=True, padx=7, pady=(0, 7))

        # 右侧：接收消息
        right_frame = ttk.LabelFrame(self.main_pane, text=" 接收消息 ", style="Card.TLabelframe")
        self.main_pane.add(right_frame, weight=1)
        self.receive_pane = ttk.Frame(right_frame, style="Card.TFrame")
        self.receive_pane.pack(fill=tk.BOTH, expand=True, padx=7, pady=(6, 7))
        self.receive_pane.grid_propagate(False)
        self.receive_pane.rowconfigure(1, weight=1)
        self.receive_pane.columnconfigure(0, weight=1, uniform="output")
        self.receive_pane.bind("<Configure>", self._resize_receive_split, add="+")

        heartbeat_status = ttk.Frame(self.receive_pane, style="Card.TFrame", padding=(2, 3))
        heartbeat_status.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        heartbeat_status.columnconfigure(1, weight=1)
        self.heartbeat_time_label = ttk.Label(heartbeat_status, style="Muted.TLabel")
        self.heartbeat_time_label.grid(row=0, column=0, sticky="w", padx=(2, 5))
        self.heartbeat_status_label = ttk.Label(
            heartbeat_status, text="未监听心跳", style="Card.TLabel",
            font=("Microsoft YaHei UI", 10),
        )
        self.heartbeat_status_label.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.heartbeat_summary_frame = ttk.Frame(
            heartbeat_status, style="Card.TFrame", width=1, height=1,
        )
        self.heartbeat_summary_frame.bind("<Configure>", self._layout_live_heartbeat_summary)
        heartbeat_model_menu = ttk.Combobox(
            heartbeat_status, textvariable=self.heartbeat_model_var,
            values=tuple(HEARTBEAT_STATUS_PROFILES), state="readonly", width=8,
            style="Heartbeat.TCombobox",
        )
        heartbeat_model_menu.grid(row=0, column=2, sticky="e")
        heartbeat_model_menu.bind("<<ComboboxSelected>>", self._start_heartbeat_monitoring)

        text_frame = ttk.Frame(self.receive_pane, style="Card.TFrame")
        text_frame.grid(row=1, column=0, sticky="nsew")
        self.text_display = self._make_text_box(
            text_frame,
            width=1,
            height=1,
            wrap="char",
            state=tk.DISABLED,
            highlightcolor="#CBD5E1",
        )
        self.text_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_display.yview)
        vsb.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0))
        self._wire_output_scrollbar(self.text_display, vsb)
        self._setup_output_watermark(text_frame)

        bold_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font.configure(weight="bold")
        self.text_display.tag_configure("timestamp", font=bold_font, foreground="#486581")
        self.text_display.tag_configure("topic", foreground="#2563EB")
        self.text_display.tag_configure("qos", foreground="#7C3AED")
        self.text_display.tag_configure("json_key", foreground="#C2410C")
        self.text_display.tag_configure("json_value", foreground="#047857")
        self.text_display.tag_configure("hex_error", foreground="#DC2626")
        self.text_display.tag_configure("sent_message", foreground="#2563EB")

        # 翻译面板预先创建，输入隐藏口令后再加入分隔窗口。
        self.translation_frame = ttk.Frame(self.receive_pane, style="Card.TFrame")
        self.translation_display = self._make_text_box(
            self.translation_frame,
            width=1,
            height=1,
            wrap="char",
            state=tk.DISABLED,
            highlightcolor="#CBD5E1",
        )
        self.translation_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        translation_scroll = ttk.Scrollbar(
            self.translation_frame,
            orient=tk.VERTICAL,
            command=self.translation_display.yview,
        )
        translation_scroll.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0))
        self._wire_output_scrollbar(self.translation_display, translation_scroll)
        self.translation_display.tag_configure("translation_header", foreground="#2563EB")
        for tag in ("json_key", "json_value", "hex_error", "sent_message"):
            self.translation_display.tag_configure(
                tag, foreground=self.text_display.tag_cget(tag, "foreground")
            )

        # 底部工具栏
        bottom_controls = ttk.Frame(app_frame, style="App.TFrame")
        bottom_controls.pack(fill=tk.X, padx=10, pady=(5, 7))
        ttk.Button(bottom_controls, text="清空显示", style="Compact.TButton", command=self.clear_display).pack(side=tk.LEFT)
        self.btn_save = ttk.Button(bottom_controls, text="开始保存日志", style="Compact.TButton", command=self.start_save)
        self.btn_save.pack(side=tk.LEFT, padx=(6, 3))
        self.btn_extend_log = ttk.Button(
            bottom_controls, text="＋", width=2, style="Compact.TButton",
            command=self.extend_log, state=tk.DISABLED,
        )
        self.btn_extend_log.pack(side=tk.LEFT)
        self.btn_stop_save = ttk.Button(bottom_controls, text="停止保存", style="Compact.TButton", command=self.stop_save, state=tk.DISABLED)
        self.btn_stop_save.pack(side=tk.LEFT, padx=3)
        ttk.Label(bottom_controls, text="接收模式", style="Footer.TLabel").pack(side=tk.LEFT, padx=(12, 4))
        self.gt_mode_menu = ttk.OptionMenu(bottom_controls, self.gt_mode_var, self.gt_mode_var.get(), "ZBY 解密", "原始 HEX")
        self.gt_mode_menu.pack(side=tk.LEFT)
        self.msg_count_label = ttk.Label(bottom_controls, text=self._msg_count_text(), style="Footer.TLabel")
        self.msg_count_label.pack(side=tk.RIGHT)

    def _msg_count_text(self):
        return f"已接收：{self.total_received}    已保存：{self.total_saved}"

    def _update_msg_count_label(self):
        self.msg_count_label.config(text=self._msg_count_text())

    def _set_connection_status(self, text, color):
        self.connection_status_label.config(text=f"●  {text}", foreground=color)

    def _set_connection_phase(self, phase):
        self.connection_phase = phase
        settings = {
            "disconnected": ("连接", "Primary.TButton", tk.NORMAL),
            "connecting": ("连接", "Primary.TButton", tk.DISABLED),
            "connected": ("断开", "Disconnect.TButton", tk.NORMAL),
            "disconnecting": ("断开", "Disconnect.TButton", tk.DISABLED),
        }
        text, style, state = settings.get(phase, settings["disconnected"])
        self.btn_connection.config(text=text, style=style, state=state)

    def _toggle_connection(self):
        if self.connection_phase == "disconnected":
            self.connect_mqtt()
        elif self.connection_phase == "connected":
            self.disconnect_mqtt()

    def _clear_connection_timeout(self):
        if self._connection_timeout_after_id is None:
            return
        try:
            self.after_cancel(self._connection_timeout_after_id)
        except (tk.TclError, ValueError):
            pass
        self._connection_timeout_after_id = None

    def _start_connection_timeout(self, phase, timeout_ms):
        self._clear_connection_timeout()
        client = self.client
        self._connection_timeout_after_id = self.after(
            timeout_ms,
            lambda: self._handle_connection_timeout(client, phase),
        )

    def _handle_connection_timeout(self, client, expected_phase):
        if client is not self.client or self.connection_phase != expected_phase:
            return
        self._connection_timeout_after_id = None
        self._connection_cancel.set()
        self._finish_mqtt_session(client)
        if expected_phase == "connecting":
            self._set_connection_status("连接超时", "#FDA29B")
            self._append_plain("[错误] MQTT 连接超时，已停止本次连接。")
        else:
            self._set_connection_status("未连接", "#FDA29B")
            self._append_plain("[信息] MQTT 断开等待超时，已恢复为未连接状态。")

    def _draw_circle_toggle(self, canvas, enabled):
        canvas.delete("all")
        if enabled:
            canvas.create_oval(2, 2, 16, 16, fill="#22C55E", outline="#16A34A", width=1)
            canvas.create_text(9, 9, text="✓", fill="#FFFFFF", font=("Arial", 8, "bold"))
        else:
            canvas.create_oval(2, 2, 16, 16, fill="#FFFFFF", outline="#94A3B8", width=1)

    def _refresh_auto_reconnect_button(self):
        enabled = bool(self.auto_reconnect_var.get())
        self._draw_circle_toggle(self.auto_reconnect_button, enabled)

    def _toggle_auto_reconnect(self):
        self.auto_reconnect_var.set(not self.auto_reconnect_var.get())
        self.auto_reconnect_enabled = bool(self.auto_reconnect_var.get())
        self._refresh_auto_reconnect_button()

    # -------------------------
    # subscription rows
    # -------------------------
    def _stabilize_initial_layout(self, attempt=0):
        pane_width = self.main_pane.winfo_width()
        if pane_width < 600:
            if attempt < 12:
                self.after(50, lambda: self._stabilize_initial_layout(attempt + 1))
            return
        try:
            left_width = max(430, min(int(pane_width * 0.49), pane_width - 420))
            self.main_pane.sashpos(0, left_width)
        except Exception:
            pass
        self.update_idletasks()
        self._refresh_subscription_scrollregion()
        self._align_subscription_header()

    def _refresh_subscription_scrollregion(self, event=None):
        bbox = self.sub_canvas.bbox(self.sub_canvas_window)
        if not bbox:
            return
        visible_height = max(1, self.sub_canvas.winfo_height())
        content_height = max(bbox[3], visible_height)
        self.sub_canvas.configure(scrollregion=(0, 0, bbox[2], content_height))
        if bbox[3] <= visible_height:
            self.sub_canvas.yview_moveto(0.0)
        self.after_idle(self._align_subscription_header)

    def _resize_subscription_canvas(self, event):
        self.sub_canvas.itemconfigure(self.sub_canvas_window, width=event.width)
        self.after_idle(self._align_subscription_header)

    def _align_subscription_header(self):
        if not self.sub_entries:
            return
        first_item = self.sub_entries[0]
        for key, label in self.sub_header_labels.items():
            if key == "note_entry" and not self.notes_visible:
                label.place_forget()
                continue
            widget = first_item[key]
            x = widget.winfo_x()
            width = widget.winfo_width()
            if key == "enabled_button":
                # 状态表头使用整列宽度，不受圆形图标宽度限制。
                x = 0
                width = max(28, first_item["topic_entry"].winfo_x())
            elif key == "delete_button":
                # 删除表头使用垃圾桶图标所在的整列宽度。
                x = max(0, widget.winfo_x() - 4)
                if self.notes_visible:
                    width = max(28, first_item["note_entry"].winfo_x() - x)
                else:
                    width = max(28, first_item["row"].winfo_width() - x)
            label.place(
                x=x,
                y=0,
                width=max(1, width),
                height=18,
            )

    def _scroll_subscriptions(self, event):
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            first, last = self.sub_canvas.yview()
            if direction < 0 and first <= 0.0001:
                self.sub_canvas.yview_moveto(0.0)
            elif direction > 0 and last >= 0.9999:
                self.sub_canvas.yview_moveto(max(0.0, 1.0 - (last - first)))
            else:
                self.sub_canvas.yview_scroll(direction, "units")
        return "break"

    def _toggle_notes_visibility(self):
        self.notes_visible = not self.notes_visible
        self._apply_notes_visibility()

    def _apply_notes_visibility(self):
        for item in self.sub_entries:
            row = item["row"]
            note_entry = item["note_entry"]
            if self.notes_visible:
                row.columnconfigure(1, weight=3)
                row.columnconfigure(3, weight=2)
                note_entry.grid()
            else:
                note_entry.grid_remove()
                row.columnconfigure(1, weight=1)
                row.columnconfigure(3, weight=0, minsize=0)
        if hasattr(self, "notes_toggle_button"):
            self.notes_toggle_button.config(
                text="隐藏备注" if self.notes_visible else "显示备注",
                style="ToggleActive.TButton" if self.notes_visible else "Compact.TButton",
            )
        self.update_idletasks()
        self._refresh_subscription_scrollregion()
        self._align_subscription_header()

    def _schedule_topics_save(self, *args):
        if self._loading_topics or self._topics_load_failed:
            return
        if self._topics_save_after_id is not None:
            try:
                self.after_cancel(self._topics_save_after_id)
            except Exception:
                pass
        self._topics_save_after_id = self.after(450, self._auto_save_topics)

    def _auto_save_topics(self):
        self._topics_save_after_id = None
        self._save_topics_to_disk(silent=True)

    def _refresh_subscription_enabled_button(self, item):
        enabled = bool(item["enabled_var"].get())
        self._draw_circle_toggle(item["enabled_button"], enabled)

    def _toggle_subscription_enabled(self, item):
        item["enabled_var"].set(not item["enabled_var"].get())
        self._refresh_subscription_enabled_button(item)

    def _create_trash_icon(self, parent, command):
        canvas = tk.Canvas(
            parent,
            width=20,
            height=20,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        color = "#DC2626"
        canvas.create_line(5, 6, 15, 6, fill=color, width=1.5)
        canvas.create_line(8, 4, 12, 4, fill=color, width=1.5)
        canvas.create_rectangle(6, 7, 14, 16, outline=color, width=1.3)
        canvas.create_line(9, 9, 9, 14, fill=color, width=1)
        canvas.create_line(11, 9, 11, 14, fill=color, width=1)
        canvas.bind("<Button-1>", lambda event: command())
        return canvas

    def _add_subscription_row(self, default="", note="", enabled=True, schedule_save=True):
        row = ttk.Frame(self.sub_frame, style="Card.TFrame")
        row.columnconfigure(0, minsize=28)
        row.columnconfigure(1, weight=3)
        row.columnconfigure(2, minsize=28)
        row.columnconfigure(3, weight=2)

        enabled_var = tk.BooleanVar(value=bool(enabled))
        topic_var = tk.StringVar(value=default)
        note_var = tk.StringVar(value=note)
        item = {
            "row": row,
            "enabled_var": enabled_var,
            "topic_var": topic_var,
            "note_var": note_var,
        }

        enabled_button = tk.Canvas(
            row,
            width=20,
            height=20,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        enabled_button.grid(row=0, column=0, padx=(2, 6), pady=1)
        enabled_button.bind("<Button-1>", lambda event, current=item: self._toggle_subscription_enabled(current))
        topic_entry = ttk.Entry(row, textvariable=topic_var)
        topic_entry.grid(row=0, column=1, padx=2, pady=1, sticky="ew")
        delete_button = self._create_trash_icon(
            row,
            lambda current=item: self._remove_subscription_row(current),
        )
        delete_button.grid(row=0, column=2, padx=4, pady=1)
        note_entry = ttk.Entry(row, textvariable=note_var)
        note_entry.grid(row=0, column=3, padx=(2, 7), pady=1, sticky="ew")

        item.update({
            "enabled_button": enabled_button,
            "topic_entry": topic_entry,
            "note_entry": note_entry,
            "delete_button": delete_button,
        })
        self._refresh_subscription_enabled_button(item)
        row.pack(fill=tk.X)
        self.sub_entries.append(item)
        if not self.notes_visible:
            note_entry.grid_remove()
            row.columnconfigure(1, weight=1)
            row.columnconfigure(3, weight=0, minsize=0)

        for widget in (row, enabled_button, topic_entry, delete_button, note_entry):
            widget.bind("<MouseWheel>", self._scroll_subscriptions)
        enabled_var.trace_add("write", self._schedule_topics_save)
        topic_var.trace_add("write", self._schedule_topics_save)
        note_var.trace_add("write", self._schedule_topics_save)

        self.after_idle(self._refresh_subscription_scrollregion)
        self.after_idle(self._align_subscription_header)
        if schedule_save:
            self._schedule_topics_save()
            self.after_idle(self._scroll_subscription_to_bottom)
            topic_entry.focus_set()

    def _scroll_subscription_to_bottom(self):
        self._refresh_subscription_scrollregion()
        if self.sub_frame.winfo_reqheight() > self.sub_canvas.winfo_height():
            self.sub_canvas.yview_moveto(1.0)
        else:
            self.sub_canvas.yview_moveto(0.0)

    def _remove_subscription_row(self, item=None):
        if not self.sub_entries:
            return
        if item is None:
            item = self.sub_entries[-1]
        if item not in self.sub_entries:
            return
        topic = item["topic_var"].get().strip()
        self.sub_entries.remove(item)
        if topic and topic not in self._checked_topics():
            self._subscription_targets.discard(topic)
            if self.mqtt_connected:
                self._reconcile_subscriptions({topic})
        item["row"].destroy()
        self.after_idle(self._refresh_subscription_scrollregion)
        self.after_idle(self._align_subscription_header)
        self._schedule_topics_save()

    # -------------------------
    # Field translation
    # -------------------------
    @staticmethod
    def _load_translation_json(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                saved = json.load(file)
            if isinstance(saved, dict):
                return saved
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logging.exception("读取字段翻译记录失败: %s", path)
        return {}

    def _load_field_translations(self):
        self.field_translations = {
            key: value.strip()
            for key, value in self._load_translation_json(field_translations_file_path()).items()
            if isinstance(value, str) and value.strip()
        }
        previous_unknowns = self._load_translation_json(unrecognized_fields_file_path())
        for field_name, contexts in previous_unknowns.items():
            if isinstance(contexts, dict) and self._find_field_translation(field_name) is None:
                self.unrecognized_fields[field_name] = {
                    topic: [path for path in paths if isinstance(path, str)]
                    for topic, paths in contexts.items()
                    if isinstance(paths, list)
                }
        if self.unrecognized_fields != previous_unknowns:
            self._schedule_field_translations_save()

    def _schedule_field_translations_save(self):
        if self._translation_save_after_id is not None:
            return
        self._translation_save_after_id = self.after(
            350,
            self._save_field_translations,
        )

    def _save_field_translations(self):
        self._translation_save_after_id = None
        self._save_translation_json(field_translations_file_path(), self.field_translations)
        unknown_path = unrecognized_fields_file_path()
        if self.unrecognized_fields or os.path.exists(unknown_path):
            self._save_translation_json(unknown_path, self.unrecognized_fields)

    @staticmethod
    def _save_translation_json(path, entries):
        temp_path = path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(entries, file, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(temp_path, path)
        except OSError:
            logging.exception("保存字段翻译记录失败: %s", path)

    @staticmethod
    def _split_field_tokens(field_name):
        separated = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", field_name)
        separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
        return [token for token in re.split(r"[^A-Za-z0-9]+", separated) if token]

    def _find_field_translation(self, field_name):
        saved = self.field_translations.get(field_name)
        if saved and saved != field_name:
            return saved
        translated = DEFAULT_FIELD_TRANSLATIONS.get(field_name.lower())
        if translated:
            return translated
        if (
            not field_name.isascii()
            or not re.search(r"[A-Za-z]", field_name)
            or re.fullmatch(r"(?:0[xX])?[0-9A-Fa-f]{8}", field_name)
        ):
            return field_name
        tokens = self._split_field_tokens(field_name)
        matches = [FIELD_TOKEN_TRANSLATIONS.get(token.lower()) for token in tokens]
        return "".join(matches) if matches and all(matches) else None

    def _record_unrecognized_field(self, field_name, topic_family, field_path):
        contexts = self.unrecognized_fields.setdefault(field_name, {})
        paths = contexts.setdefault(topic_family, [])
        if field_path not in paths:
            paths.append(field_path)
            self._schedule_field_translations_save()

    def _translate_json_fields(self, value, topic_family, path="$", *, record=True):
        if isinstance(value, dict):
            translated_dict = {}
            event_topic = topic_family in ("sensor/event", "driving/event")
            for original_key, child_value in value.items():
                if original_key.isidentifier():
                    field_path = f"{path}.{original_key}"
                else:
                    field_path = f"{path}[{json.dumps(original_key, ensure_ascii=False)}]"
                translated_key = self._find_field_translation(original_key)
                if translated_key is None and record:
                    self._record_unrecognized_field(original_key, topic_family, field_path)
                if record and translated_key != original_key:
                    self._cache_field_translation(original_key, translated_key or original_key)
                if translated_key is None:
                    translated_key = original_key
                if event_topic:
                    if original_key in ("reportTime", "time") or (
                        topic_family == "sensor/event" and original_key == "collectionTime"
                    ):
                        beijing_time = format_beijing_unix_time(child_value)
                        if beijing_time is not None:
                            translated_key += "（北京时间）"
                            child_value = beijing_time
                    elif original_key == "eventType" and isinstance(child_value, str):
                        child_value = EVENT_TYPE_TRANSLATIONS.get(child_value, child_value)
                elif topic_family == "loc" and isinstance(child_value, str):
                    translations = LOC_FIELD_VALUES.get(field_path)
                    if translations is not None:
                        child_value = translations.get(child_value, child_value)
                if translated_key in translated_dict:
                    base_key = f"{translated_key} [{original_key}]"
                    translated_key = base_key
                    suffix = 2
                    while translated_key in translated_dict:
                        translated_key = f"{base_key} ({suffix})"
                        suffix += 1
                translated_dict[translated_key] = self._translate_json_fields(
                    child_value, topic_family, field_path, record=record
                )
            return translated_dict
        if isinstance(value, list):
            translated_list = []
            for item in value:
                translated_list.append(
                    self._translate_json_fields(item, topic_family, f"{path}[]", record=record)
                )
            return translated_list
        return value

    def _cache_field_translation(self, field_name, translated):
        if self.field_translations.get(field_name) != translated:
            self.field_translations[field_name] = translated
            self._schedule_field_translations_save()

    def _translated_payload(self, topic, payload, decrypt_status, *, record):
        if decrypt_status == "解密失败" or not isinstance(payload, (dict, list)):
            return payload
        # 协议主题以设备序列号结尾。按主题前缀汇总，便于跨设备核对同一字段。
        topic_family = topic.rpartition("/")[0] or topic
        return self._translate_json_fields(payload, topic_family, record=record)

    def _enable_translation_mode(self):
        self._attach_translation_log()
        if self.translation_mode:
            self.publish_status_label.config(text="翻译模式已开启")
            return
        follow = self._output_follows_latest()
        self.translation_mode = True
        self.receive_pane.columnconfigure(2, weight=1, uniform="output")
        self.translation_frame.grid(row=1, column=2, sticky="nsew")
        self._resize_receive_split()
        self.publish_status_label.config(text="翻译模式已开启")
        if follow:
            self.after_idle(lambda: self._finish_paired_output(True))
        else:
            self.after_idle(lambda: self._sync_output_scroll(self.text_display))

    def _resize_receive_split(self, event=None):
        if self.translation_mode:
            width = event.width if event is not None else self.receive_pane.winfo_width()
            # 宽度为奇数时，中间留白多占一像素，左右两栏仍严格等宽。
            self.receive_pane.columnconfigure(1, minsize=6 + width % 2)

    def _insert_translation_block(self, header_text, topic, payload_obj, decrypt_status):
        translated = self._translated_payload(topic, payload_obj, decrypt_status, record=True)
        output = self.translation_display
        output.configure(state=tk.NORMAL)
        output.insert(tk.END, header_text, "translation_header")
        self._insert_output_payload(output, translated, decrypt_status)
        output.configure(state=tk.DISABLED)

    # -------------------------
    # append plain message
    # -------------------------
    def _append_plain(self, text, tag=None):
        self.after(0, self._insert_plain_output, text, tag)

    def _insert_plain_output(self, text, tag=None):
        follow = self._output_follows_latest()
        for output in (self.text_display, self.translation_display):
            output.configure(state=tk.NORMAL)
            output.insert(tk.END, text + "\n", tag or ())
            output.configure(state=tk.DISABLED)
        self._finish_paired_output(follow)

    # -------------------------
    # UI queue processing
    # -------------------------
    def _process_ui_queue(self):
        if self._stop_event.is_set():
            return
        try:
            while not self._mqtt_ui_queue.empty():
                client, callback, args = self._mqtt_ui_queue.get_nowait()
                if client is None or client is self.client:
                    try:
                        callback(*args)
                    except Exception:
                        logging.exception("处理 MQTT 状态失败")

            for _ in range(50):
                try:
                    item = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                self._render_received_message(*item)
            self._update_msg_count_label()
        finally:
            self.after(60, self._process_ui_queue)

    def _render_received_message(self, timestamp, topic, qos, payload, status):
        self._capture_heartbeat_status(timestamp, topic, payload)
        starts = [
            (output, output.index("end-1c"))
            for output in (self.text_display, self.translation_display)
        ]
        block_count = len(self.message_blocks)
        try:
            self._insert_message_block(timestamp, topic, qos, payload, status)
        except Exception:
            logging.exception("显示 MQTT 消息失败")
            self.text_display.mark_unset("mqtt_message_start")
            for output, start in starts:
                output.configure(state=tk.NORMAL)
                output.delete(start, tk.END)
                output.configure(state=tk.DISABLED)
            while len(self.message_blocks) > block_count:
                self.text_display.tag_delete(self.message_blocks.pop()["tag"])
            self._insert_plain_output(f"{timestamp}  主题: {topic}  QoS: {qos}  [显示失败]")

    def _start_heartbeat_monitoring(self, _event):
        if self._last_heartbeat_value is None:
            self.heartbeat_status_label.config(text="等待心跳")
            return
        model = self.heartbeat_model_var.get()
        _, _, rows = parse_heartbeat_status(self._last_heartbeat_value, model)
        self._show_heartbeat_summary(rows, model)

    def _show_heartbeat_summary(self, rows, model):
        self.heartbeat_status_label.grid_remove()
        frame = self.heartbeat_summary_frame
        if not frame.winfo_manager():
            frame.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        chips = self._heartbeat_summary(rows, model)
        current_chips = [
            (label.cget("text"), (label.cget("background"), label.cget("foreground")))
            for label in frame.winfo_children()
        ]
        if chips != current_chips:
            for label in frame.winfo_children():
                label.destroy()
            self._populate_heartbeat_summary(frame, rows, model, live=True)

    def _capture_heartbeat_status(self, timestamp, topic, payload):
        model = self.heartbeat_model_var.get()
        if model not in HEARTBEAT_STATUS_PROFILES:
            return
        compact_topic = re.sub(r"[^a-z]", "", topic.lower())
        if not any(token in compact_topic for token in ("heartbeat", "hertbeat")):
            return
        if not isinstance(payload, dict) or "status" not in payload:
            return
        try:
            number, _, rows = parse_heartbeat_status(payload["status"], model)
        except ValueError:
            return
        self._last_heartbeat_value = number
        self.heartbeat_time_label.config(text=timestamp)
        self._show_heartbeat_summary(rows, model)

    # -------------------------
    # display trimming by lines
    # -------------------------
    @staticmethod
    def _output_at_bottom(output):
        return output.yview()[1] >= 1.0

    @staticmethod
    def _output_line_count(output):
        line, column = map(int, output.index("end-1c").split("."))
        return line if column else line - 1

    def _output_follows_latest(self):
        return self._output_at_bottom(self._output_scroll_source or self.text_display)

    def _wire_output_scrollbar(self, output, scrollbar):
        def update_scrollbar(first, last):
            scrollbar.set(first, last)
            if output is self.text_display:
                self._queue_watermark_refresh()

        def scroll(*args):
            output.yview(*args)
            self._sync_output_scroll(output)

        def sync_after_input(event):
            self.after_idle(lambda: self._sync_output_scroll(output))

        output.configure(yscrollcommand=update_scrollbar)
        scrollbar.configure(command=scroll)
        for sequence in ("<MouseWheel>", "<Prior>", "<Next>", "<Control-Home>",
                         "<Control-End>", "<B1-Motion>", "<ButtonRelease-1>"):
            output.bind(sequence, sync_after_input, add="+")

    def _sync_output_scroll(self, source):
        self._output_scroll_source = source
        if self._output_at_bottom(source):
            self._finish_paired_output(True)
        elif self.translation_mode:
            target = self.translation_display if source is self.text_display else self.text_display
            top_line = source.index("@0,0").split(".")[0]
            if target.index("@0,0").split(".")[0] != top_line:
                target.yview(f"{top_line}.0")

    def _finish_paired_output(self, follow):
        total_lines = self._output_line_count(self.text_display)
        paused_limit = max(PAUSED_OUTPUT_LIMIT, self.max_messages)
        if follow or total_lines > paused_limit:
            for output in (self.text_display, self.translation_display):
                self._trim_display_by_lines(output, total_lines)
                output.see(tk.END)
        self._queue_watermark_refresh()

    def _trim_display_by_lines(self, output, total_lines):
        excess = total_lines - self.max_messages
        if excess <= 0:
            return

        previous_state = str(output.cget("state"))
        output.configure(state=tk.NORMAL)
        try:
            output.delete("1.0", f"{excess + 1}.0")
        finally:
            output.configure(state=previous_state)

        if output is self.text_display:
            while self.message_blocks:
                tag = self.message_blocks[0]["tag"]
                if output.tag_ranges(tag):
                    break
                output.tag_delete(tag)
                self.message_blocks.popleft()

    # -------------------------
    # insert a complete message block
    # -------------------------
    def _insert_message_block(self, timestamp, topic, qos, payload_obj, decrypt_status=""):
        """
        Insert full message and tag the entire region with unique tag.
        """
        block_tag = f"blk_{uuid.uuid4().hex}"
        start_mark = "mqtt_message_start"

        follow = self._output_follows_latest()
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.mark_set(start_mark, "end-1c")
        self.text_display.mark_gravity(start_mark, tk.LEFT)

        status_text = f" {decrypt_status}" if decrypt_status else ""
        header_text = f"{timestamp}  主题: {topic}  QoS: {qos}{status_text}\n"
        self.text_display.insert(tk.END, header_text)

        try:
            start_idx = self.text_display.index(start_mark)
            header_end = self.text_display.index("end-1c")
            header_line = self.text_display.get(start_idx, header_end)

            topic_label_pos = header_line.find("主题:")
            qos_label_pos = header_line.find("QoS:")

            if topic_label_pos != -1:
                ts_end_idx = f"{start_idx} + {topic_label_pos} chars"
                self.text_display.tag_add("timestamp", start_idx, ts_end_idx)

                topic_val_start = topic_label_pos + len("主题: ")
                topic_val_end = qos_label_pos if qos_label_pos != -1 else len(header_line)
                tstart = f"{start_idx} + {topic_val_start} chars"
                tend = f"{start_idx} + {topic_val_end} chars"
                self.text_display.tag_add("topic", tstart, tend)

            if qos_label_pos != -1:
                qos_value_text = f"{qos}{status_text}"
                qstart = f"{start_idx} + {qos_label_pos + len('QoS: ')} chars"
                qend = f"{qstart} + {len(qos_value_text)} chars"
                self.text_display.tag_add("qos", qstart, qend)
        except Exception:
            pass

        self._insert_output_payload(self.text_display, payload_obj, decrypt_status)
        if isinstance(payload_obj, (dict, list)):
            pretty = json.dumps(payload_obj, ensure_ascii=False, indent=2)
            raw = payload_obj
            json_flag = True
        else:
            pretty = None
            raw = str(payload_obj)
            json_flag = False

        try:
            s_idx = self.text_display.index(start_mark)
            e_idx = self.text_display.index("end-1c")
            self.text_display.tag_add(block_tag, s_idx, e_idx)
        except Exception as e:
            logging.exception("Failed to tag block: %s", e)

        self.message_blocks.append({
            "tag": block_tag,
            "json_flag": json_flag,
            "raw": raw,
            "pretty": pretty
        })

        try:
            self.text_display.mark_unset(start_mark)
        except Exception:
            pass

        self.text_display.configure(state=tk.DISABLED)
        self._insert_translation_block(header_text, topic, payload_obj, decrypt_status)
        self._finish_paired_output(follow)

    # -------------------------
    # Recursive JSON colorful insertion
    # -------------------------
    def _insert_output_payload(self, output, payload_obj, decrypt_status):
        if isinstance(payload_obj, (dict, list)):
            self._insert_json_colorful(output, payload_obj)
            output.insert(tk.END, "\n")
            if decrypt_status == "解密失败" and isinstance(payload_obj, dict) and "raw_hex" in payload_obj:
                output.insert(tk.END, "原始 HEX: ")
                output.insert(tk.END, payload_obj["raw_hex"], "hex_error")
                output.insert(tk.END, "\n")
        else:
            output.insert(tk.END, str(payload_obj) + "\n")

    def _insert_json_colorful(self, output, obj, indent_level=0):
        indent = "  " * indent_level
        if isinstance(obj, dict):
            output.insert(tk.END, "{\n")
            items = list(obj.items())
            for i, (k, v) in enumerate(items):
                output.insert(tk.END, indent + "  ")

                key_text = json.dumps(k, ensure_ascii=False)
                kstart = output.index("end-1c")
                output.insert(tk.END, key_text)
                kend = output.index("end-1c")
                output.tag_add("json_key", kstart, kend)

                output.insert(tk.END, ": ")

                if isinstance(v, (dict, list)):
                    self._insert_json_colorful(output, v, indent_level + 1)
                else:
                    val_text = json.dumps(v, ensure_ascii=False)
                    vstart = output.index("end-1c")
                    output.insert(tk.END, val_text)
                    vend = output.index("end-1c")
                    output.tag_add("json_value", vstart, vend)

                if i != len(items) - 1:
                    output.insert(tk.END, ",\n")
                else:
                    output.insert(tk.END, "\n")

            output.insert(tk.END, indent + "}")

        elif isinstance(obj, list):
            output.insert(tk.END, "[\n")
            compact_rows = bool(obj) and all(
                isinstance(row, list) and not any(isinstance(value, (dict, list)) for value in row)
                for row in obj
            )
            if compact_rows:
                for index in range(0, len(obj), 2):
                    output.insert(tk.END, indent + "  ")
                    pair = obj[index:index + 2]
                    for pair_index, row in enumerate(pair):
                        if pair_index:
                            output.insert(tk.END, "  ")
                        value_text = json.dumps(row, ensure_ascii=False, separators=(", ", ": "))
                        value_start = output.index("end-1c")
                        output.insert(tk.END, value_text, "json_value")
                        output.tag_add("json_value", value_start, "end-1c")
                        if index + pair_index < len(obj) - 1:
                            output.insert(tk.END, ",")
                    output.insert(tk.END, "\n")
                output.insert(tk.END, indent + "]")
                return

            for i, v in enumerate(obj):
                output.insert(tk.END, indent + "  ")
                if isinstance(v, (dict, list)):
                    self._insert_json_colorful(output, v, indent_level + 1)
                else:
                    val_text = json.dumps(v, ensure_ascii=False)
                    vstart = output.index("end-1c")
                    output.insert(tk.END, val_text)
                    vend = output.index("end-1c")
                    output.tag_add("json_value", vstart, vend)

                if i != len(obj) - 1:
                    output.insert(tk.END, ",\n")
                else:
                    output.insert(tk.END, "\n")

            output.insert(tk.END, indent + "]")

        else:
            val_text = json.dumps(obj, ensure_ascii=False)
            vstart = output.index("end-1c")
            output.insert(tk.END, val_text)
            vend = output.index("end-1c")
            output.tag_add("json_value", vstart, vend)

    # -------------------------
    # MQTT
    # -------------------------
    def connect_mqtt(self):
        if self.client is not None or self._stop_event.is_set():
            return
        host = self.entry_host.get().strip()
        try:
            port = int(self.entry_port.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("输入错误", "端口号须为 1 到 65535 的整数。")
            return
        if not host:
            messagebox.showerror("输入错误", "请输入 MQTT 服务器地址。")
            return

        client = mqtt.Client()
        username = self.entry_username.get().strip()
        if username:
            client.username_pw_set(username, self.entry_password.get().strip())
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        client.on_unsubscribe = self._on_unsubscribe
        # Paho 只排队，由会话线程的 loop 处理写入，避免 UI 同时写套接字。
        client.on_socket_register_write = lambda *args: None

        cancel = threading.Event()
        self.client = client
        self._connection_cancel = cancel
        self._subscription_targets = self._checked_topics()
        self._begin_mqtt_attempt()
        self._append_plain("[信息] 正在连接 MQTT 服务器……")
        self.client_thread = threading.Thread(
            target=self._run_mqtt_session, args=(client, cancel, host, port), daemon=True
        )
        self.client_thread.start()

    def _queue_mqtt_ui(self, client, callback, *args):
        self._mqtt_ui_queue.put((client, callback, args))

    def _begin_mqtt_attempt(self):
        self._set_connection_phase("connecting")
        self._set_connection_status("正在连接", "#FEC84B")
        self._start_connection_timeout("connecting", CONNECT_TIMEOUT_MS)

    def _run_mqtt_session(self, client, cancel, host, port):
        # 每个会话只有一个网络循环，Paho 不再另起自动重连线程。
        try:
            while not cancel.is_set():
                try:
                    rc = client.connect(host, port, 60)
                    while rc == mqtt.MQTT_ERR_SUCCESS and not cancel.is_set():
                        rc = client.loop(timeout=0.2)
                    if rc != mqtt.MQTT_ERR_SUCCESS and not cancel.is_set():
                        self._queue_mqtt_ui(client, self._report_mqtt_error, mqtt.error_string(rc))
                except (OSError, ValueError, RuntimeError) as exc:
                    if not cancel.is_set():
                        self._queue_mqtt_ui(client, self._report_mqtt_error, str(exc))

                if cancel.is_set() or not self.auto_reconnect_enabled:
                    break
                self._queue_mqtt_ui(client, self._wait_for_mqtt_retry)
                if cancel.wait(RECONNECT_INTERVAL) or not self.auto_reconnect_enabled:
                    break
                self._queue_mqtt_ui(client, self._begin_mqtt_attempt)
        finally:
            try:
                if client.disconnect() == mqtt.MQTT_ERR_SUCCESS:
                    client.loop_write()
            except (OSError, ValueError, RuntimeError):
                logging.exception("断开 MQTT 连接失败")
            finally:
                self._queue_mqtt_ui(client, self._finish_mqtt_session, client)

    def _report_mqtt_error(self, detail):
        self._mark_mqtt_link_down()
        if self.connection_phase != "disconnecting":
            self._set_connection_status("连接异常", "#FDA29B")
            self._append_plain(f"[错误] MQTT 连接异常：{detail}")

    def _wait_for_mqtt_retry(self):
        if self.connection_phase == "disconnecting":
            return
        self._mark_mqtt_link_down()
        self._set_connection_phase("connecting")
        self._set_connection_status("等待重连", "#FEC84B")
        self._append_plain(f"[信息] {RECONNECT_INTERVAL} 秒后尝试自动重连。")

    def _finish_mqtt_session(self, client):
        if client is not self.client:
            return
        self._mark_mqtt_link_down()
        self._clear_connection_timeout()
        self.client = None
        self.client_thread = None
        self._connection_cancel = None
        self._set_connection_phase("disconnected")
        self._set_connection_status("未连接", "#FDA29B")

    def disconnect_mqtt(self):
        if self.client is None:
            return
        self._mark_mqtt_link_down()
        self._set_connection_phase("disconnecting")
        self._set_connection_status("正在断开", "#FEC84B")
        self._start_connection_timeout("disconnecting", DISCONNECT_TIMEOUT_MS)
        self._connection_cancel.set()
        self._append_plain("[信息] 正在断开 MQTT 连接。")

    def _on_connect(self, client, userdata, flags, rc):
        self._queue_mqtt_ui(client, self._apply_mqtt_connect, rc)

    def _apply_mqtt_connect(self, rc):
        if self.connection_phase != "connecting":
            return
        self._clear_connection_timeout()
        if rc != 0:
            self._report_mqtt_error(f"服务器拒绝连接，返回码={rc}")
            return
        self._reset_subscription_state()
        self.mqtt_connected = True
        self._set_connection_phase("connected")
        self._set_connection_status("已连接", "#6CE9A6")
        self._append_plain("[信息] MQTT 服务器连接成功。")
        self._reconcile_subscriptions(self._subscription_targets)

    def _on_disconnect(self, client, userdata, rc):
        self._queue_mqtt_ui(client, self._apply_mqtt_disconnect)

    def _apply_mqtt_disconnect(self):
        self._mark_mqtt_link_down()
        self._append_plain("[信息] MQTT 连接已断开。")
        if self.connection_phase != "disconnecting":
            self._set_connection_phase("connecting")
            self._set_connection_status("未连接", "#FDA29B")

    def _mark_mqtt_link_down(self):
        self.mqtt_connected = False
        self._reset_subscription_state()
        if self.connection_phase != "disconnecting":
            self._clear_connection_timeout()

    def _reset_subscription_state(self):
        for _, _, timer in self._pending_subscriptions.values():
            self.after_cancel(timer)
        self._pending_subscriptions.clear()
        self._active_subscriptions.clear()
        self._uncertain_subscriptions.clear()

    def _update_receive_mode(self, *args):
        self._receive_mode = self.gt_mode_var.get()

    def _on_message(self, client, userdata, msg):
        if client is not self.client or self._stop_event.is_set():
            return
        payload_bytes = msg.payload
        decrypt_status = ""
        failed_hex = None

        mode = self._receive_mode

        if mode == "ZBY 解密":
            obj, decrypt_status, failed_hex = parse_gt115_payload(payload_bytes)
        else:
            # Raw Data mode 下直接显示原始 HEX
            obj = payload_bytes.hex().upper()
            decrypt_status = ""

        tz = timezone(timedelta(hours=8))
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        if client is not self.client or self._stop_event.is_set():
            return
        self.total_received += 1

        self._save_received_message(
            timestamp, msg.topic, msg.qos, obj, decrypt_status, failed_hex, client=client
        )

        try:
            self.ui_queue.put_nowait((timestamp, msg.topic, msg.qos, obj, decrypt_status))
        except queue.Full:
            logging.warning("UI queue full; dropping message for display")

    @staticmethod
    def _format_saved_payload(payload, failed_hex, *, sample_aliases=None):
        if isinstance(payload, dict) and payload and sample_aliases is not None:
            fields = []
            for key, value in payload.items():
                if sensor_field_name(key, sample_aliases) == "samples" and isinstance(value, list) and value:
                    groups = [json.dumps(row, ensure_ascii=False) for row in value]
                    lines = [",  ".join(groups[index:index + 2]) for index in range(0, len(groups), 2)]
                    pretty = "[\n    " + ",\n    ".join(lines) + "\n  ]"
                else:
                    pretty = json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n  ")
                fields.append(f"  {json.dumps(key, ensure_ascii=False)}: {pretty}")
            body = "{\n" + ",\n".join(fields) + "\n}"
        elif isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            body = str(payload)
        if failed_hex:
            body += f"\n\n原始 HEX: {failed_hex}"
        return body + "\n\n"

    def _save_received_message(
        self, timestamp, topic, qos, payload, decrypt_status, failed_hex, *, client=None
    ):
        error = None
        with self.save_lock:
            if not self.saving_enabled or self._stop_event.is_set():
                return
            if client is not None and client is not self.client:
                return
            writes = []
            try:
                status = f" {decrypt_status}" if decrypt_status else ""
                header = f"{timestamp}  主题: {topic}  QoS: {qos}{status}\n"
                sample_aliases = sensor_field_aliases(self.field_translations) if topic.startswith(SENSOR_EVENT_TOPIC) else None
                entries = [(
                    self.save_file,
                    self._format_saved_payload(payload, failed_hex, sample_aliases=sample_aliases),
                )]
                if self.translation_save_file is not None:
                    # MQTT 回调线程只读词典，词条采集和保存仍在界面线程处理。
                    translated = self._translated_payload(topic, payload, decrypt_status, record=False)
                    entries.append((
                        self.translation_save_file,
                        self._format_saved_payload(translated, failed_hex, sample_aliases=sample_aliases),
                    ))
                for output, body in entries:
                    data = (header + body).replace("\n", os.linesep).encode("utf-8")
                    offset = output.seek(0, os.SEEK_END)
                    writes.append((output, offset, data))
                    if output.write(data) != len(data):
                        raise OSError("日志只写入了部分数据")
                    os.fsync(output.fileno())
                self.total_saved += 1
            except (OSError, ValueError, RecursionError) as exc:
                restored = self._rollback_log_writes(writes)
                self._close_log_files_locked()
                error = str(exc)
                if not restored:
                    error += "。日志回退失败，请检查两个文件的末尾"
                logging.exception("保存 MQTT 日志失败")
        if error is not None:
            self._queue_mqtt_ui(None, self._update_save_buttons)
            self._queue_mqtt_ui(None, self._insert_plain_output, f"[错误] 日志写入失败，已停止保存：{error}")

    @staticmethod
    def _rollback_log_writes(writes):
        restored = True
        for output, offset, data in reversed(writes):
            try:
                size = output.seek(0, os.SEEK_END)
                if size == offset:
                    continue
                if not offset < size <= offset + len(data):
                    raise OSError("日志末尾已被其他写入改变")
                output.seek(offset)
                if output.read(size - offset) != data[:size - offset]:
                    raise OSError("日志末尾与本次写入不一致")
                output.truncate(offset)
                os.fsync(output.fileno())
            except (OSError, ValueError):
                restored = False
                logging.exception("回退本次 MQTT 日志写入失败")
        return restored

    def _publish_shortcut(self, event=None):
        """Ctrl+Enter 快捷发送。"""
        if event is not None and self._confirm_publish_input(event) == "break":
            return "break"
        self.publish_encrypted_json()
        return "break"

    @staticmethod
    def _confirm_publish_input(event):
        """回车交给正在组字的 Windows 输入法，普通回车继续由 Tk 处理。"""
        if sys.platform != "win32":
            return None
        imm32 = ctypes.windll.imm32
        get_context = imm32.ImmGetContext
        get_context.argtypes = [wintypes.HWND]
        get_context.restype = wintypes.HANDLE
        get_composition = imm32.ImmGetCompositionStringW
        get_composition.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        get_composition.restype = wintypes.LONG
        notify = imm32.ImmNotifyIME
        notify.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        notify.restype = wintypes.BOOL
        release_context = imm32.ImmReleaseContext
        release_context.argtypes = [wintypes.HWND, wintypes.HANDLE]
        release_context.restype = wintypes.BOOL

        hwnd = event.widget.winfo_id()
        context = get_context(hwnd)
        if context:
            try:
                # GCS_COMPSTR, NI_COMPOSITIONSTR, CPS_COMPLETE
                if get_composition(context, 0x0008, None, 0) > 0 and notify(context, 0x0015, 0x0001, 0):
                    return "break"
            finally:
                release_context(hwnd, context)
        return None

    def publish_encrypted_json(self):
        """JSON -> UTF-8 -> PKCS7 -> AES-256-CBC -> MQTT 密文字节。"""
        topic = self.publish_topic_entry.get().strip()
        json_text = self.publish_data_text.get("1.0", "end-1c").strip()

        # 隐藏入口：两个输入框同时输入 fanyi，仅开启翻译页，不发送 MQTT。
        if topic.lower() == "fanyi" and json_text.lower() == "fanyi":
            self._enable_translation_mode()
            return

        if not self.client or not self.mqtt_connected:
            self.publish_status_label.config(text="未连接 MQTT")
            messagebox.showwarning("发送失败", "请先连接 MQTT 服务器。")
            return

        if not topic:
            self.publish_status_label.config(text="发送主题为空")
            messagebox.showwarning("发送失败", "请输入发送主题。")
            self.publish_topic_entry.focus_set()
            return

        if not json_text:
            self.publish_status_label.config(text="JSON 为空")
            messagebox.showwarning("发送失败", "请输入 JSON 数据。")
            self.publish_data_text.focus_set()
            return

        try:
            encrypted_bytes, source_json = encrypt_json_payload(json_text)
        except json.JSONDecodeError as e:
            detail = f"无法解析 JSON，请检查引号、逗号和括号。\n位置：第 {e.lineno} 行，第 {e.colno} 列。"
            self.publish_status_label.config(text="JSON 格式错误")
            messagebox.showerror("JSON 格式错误", detail)
            return
        except Exception as e:
            self.publish_status_label.config(text="加密失败")
            messagebox.showerror("加密失败", str(e))
            return

        encrypted_hex = encrypted_bytes.hex().upper()
        try:
            info = self.client.publish(topic, payload=encrypted_bytes, qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(mqtt.error_string(info.rc))
        except Exception as e:
            self.publish_status_label.config(text="发送失败")
            messagebox.showerror("MQTT 发送失败", str(e))
            return

        self.publish_status_label.config(text=f"已提交 {len(encrypted_bytes)} 字节")
        self._append_plain(
            f"[发送] 主题: {topic}  QoS: 1\n"
            f"JSON 原文: {source_json}\n"
            f"AES 密文 HEX: {encrypted_hex}",
            tag="sent_message",
        )

    # -------------------------
    # subscribe / unsubscribe
    # -------------------------
    def _checked_topics(self):
        topics = set()
        for item in self.sub_entries:
            topic = item["topic_var"].get().strip()
            if topic and item["enabled_var"].get():
                topics.add(topic)
        return topics

    def subscribe_all(self):
        if not self.mqtt_connected:
            messagebox.showwarning("无法订阅", "请先连接 MQTT 服务器。")
            return
        self._subscription_targets = self._checked_topics()
        self._reconcile_subscriptions(
            self._subscription_targets | self._active_subscriptions | self._uncertain_subscriptions
        )

    def unsubscribe_all(self):
        if not self.mqtt_connected:
            messagebox.showwarning("无法取消订阅", "请先连接 MQTT 服务器。")
            return
        self._subscription_targets.clear()
        self._reconcile_subscriptions(self._active_subscriptions | self._uncertain_subscriptions)

    def _reconcile_subscriptions(self, topics):
        if not self.mqtt_connected or self.client is None:
            return
        pending = {topic for topic, _, _ in self._pending_subscriptions.values()}
        for topic in sorted(topics - pending):
            subscribe = topic in self._subscription_targets
            if (
                topic not in self._uncertain_subscriptions
                and subscribe == (topic in self._active_subscriptions)
            ):
                continue
            action = "订阅" if subscribe else "取消订阅"
            try:
                if subscribe:
                    rc, mid = self.client.subscribe(topic, 1)
                else:
                    rc, mid = self.client.unsubscribe(topic)
                if rc != mqtt.MQTT_ERR_SUCCESS:
                    self._append_plain(f"[错误] {action}请求失败：{topic}，{mqtt.error_string(rc)}")
                    continue
                timer = self.after(
                    SUBSCRIPTION_ACK_TIMEOUT_MS, self._expire_subscription, self.client, mid
                )
                self._pending_subscriptions[mid] = (topic, subscribe, timer)
            except (OSError, ValueError, RuntimeError) as exc:
                self._append_plain(f"[错误] {action}请求失败：{topic}，{exc}")

    def _expire_subscription(self, client, mid):
        if client is not self.client:
            return
        request = self._pending_subscriptions.pop(mid, None)
        if request is None:
            return
        topic, subscribe, _ = request
        self._uncertain_subscriptions.add(topic)
        action = "订阅" if subscribe else "取消订阅"
        self._append_plain(f"[错误] {action}确认超时：{topic}。结果未知，可手动重试。")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        accepted = bool(granted_qos) and all(qos < 128 for qos in granted_qos)
        self._queue_mqtt_ui(client, self._confirm_subscription, mid, accepted)

    def _on_unsubscribe(self, client, userdata, mid):
        self._queue_mqtt_ui(client, self._confirm_subscription, mid, True)

    def _confirm_subscription(self, mid, accepted):
        request = self._pending_subscriptions.pop(mid, None)
        if request is None:
            return
        topic, subscribe, timer = request
        self.after_cancel(timer)
        if not self.mqtt_connected:
            return
        if not accepted:
            self._append_plain(f"[错误] 服务器拒绝订阅：{topic}")
            return
        self._uncertain_subscriptions.discard(topic)
        if subscribe:
            self._active_subscriptions.add(topic)
            self._append_plain(f"[信息] 已订阅：{topic}")
        else:
            self._active_subscriptions.discard(topic)
            self._append_plain(f"[信息] 已取消订阅：{topic}")
        if self.mqtt_connected:
            self._reconcile_subscriptions({topic})

    # -------------------------
    # clear / save log
    # -------------------------
    def clear_display(self):
        for output in (self.text_display, self.translation_display):
            output.configure(state=tk.NORMAL)
            output.delete("1.0", tk.END)
            output.configure(state=tk.DISABLED)
        for block in self.message_blocks:
            self.text_display.tag_delete(block["tag"])
        self.message_blocks.clear()
        self._update_msg_count_label()
        self._append_plain("[信息] 显示内容已清空。")

    def start_save(self):
        if self.saving_enabled:
            messagebox.showinfo("提示", "当前已在保存日志。")
            return

        path = filedialog.asksaveasfilename(
            title="选择日志保存位置",
            initialfile="MQTT_TOOLS",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not path:
            return

        stem, suffix = os.path.splitext(path)
        if not suffix:
            path = stem + ".txt"
        translated = None
        try:
            with ExitStack() as pending:
                original = pending.enter_context(open(path, "a+b", buffering=0))
                if self.translation_mode:
                    translated = pending.enter_context(self._open_translation_log(original))
                with self.save_lock:
                    pending.pop_all()
                    self.save_file = original
                    self.translation_save_file = translated
                    self._base_log_path = os.path.abspath(path)
                    self._log_segment_number = 0
                    self.saving_enabled = True
        except (OSError, ValueError) as e:
            messagebox.showerror("保存失败", f"无法打开日志文件：{e}")
            return

        self._update_save_buttons()
        self._append_plain(f"[信息] 已开始保存原文日志：{path}")
        if translated is not None:
            self._append_plain(f"[信息] 已开始保存译文日志：{translated.name}")
        self._update_msg_count_label()

    def extend_log(self):
        try:
            with self.save_lock:
                if not self.saving_enabled:
                    return
                stem, suffix = os.path.splitext(self._base_log_path)
                segment_number = self._log_segment_number
                while True:
                    segment_number += 1
                    path = f"{stem}-extend-{segment_number}{suffix}"
                    if os.path.lexists(self._translation_log_path(path)):
                        continue
                    try:
                        with ExitStack() as pending:
                            original = open(path, "x+b", buffering=0)
                            pending.callback(os.unlink, path)
                            pending.enter_context(original)
                            translated = None
                            if self.translation_mode:
                                translated = pending.enter_context(
                                    self._open_translation_log(original, exclusive=True)
                                )
                            pending.pop_all()
                    except FileExistsError:
                        continue
                    break
                old_files = self.save_file, self.translation_save_file
                self.save_file, self.translation_save_file = original, translated
                self._log_segment_number = segment_number
        except (OSError, ValueError) as exc:
            messagebox.showerror("切换日志失败", f"无法创建新分卷，继续写入当前日志。\n{exc}")
            return

        self._close_log_outputs(*old_files)
        self._append_plain(f"[信息] 已切换原文日志：{path}")
        if translated is not None:
            self._append_plain(f"[信息] 已切换译文日志：{translated.name}")

    @staticmethod
    def _translation_log_path(path):
        stem, suffix = os.path.splitext(path)
        return f"{stem}-FY{suffix}"

    def _open_translation_log(self, original, *, exclusive=False):
        with ExitStack() as pending:
            mode = "x+b" if exclusive else "a+b"
            translated = pending.enter_context(
                open(self._translation_log_path(original.name), mode, buffering=0)
            )
            if os.path.samestat(os.fstat(original.fileno()), os.fstat(translated.fileno())):
                raise OSError("原文日志和译文日志指向了同一个文件")
            pending.pop_all()
            return translated

    def _attach_translation_log(self):
        try:
            with self.save_lock:
                if not self.saving_enabled or self.translation_save_file is not None:
                    return
                output = self._open_translation_log(self.save_file)
                self.translation_save_file = output
        except (OSError, ValueError) as exc:
            self._append_plain(f"[错误] 无法开始保存译文日志：{exc}")
            return
        self._append_plain(f"[信息] 已开始保存译文日志：{output.name}")

    def stop_save(self):
        if not self.saving_enabled:
            return

        self._close_log_files()
        self._update_save_buttons()
        self._append_plain("[信息] 已停止保存日志。")
        self._update_msg_count_label()

    def _update_save_buttons(self):
        self.btn_save.config(state=tk.DISABLED if self.saving_enabled else tk.NORMAL)
        self.btn_extend_log.config(state=tk.NORMAL if self.saving_enabled else tk.DISABLED)
        self.btn_stop_save.config(state=tk.NORMAL if self.saving_enabled else tk.DISABLED)

    def _close_log_files(self):
        with self.save_lock:
            self._close_log_files_locked()

    def _close_log_files_locked(self):
        files = self.save_file, self.translation_save_file
        self.saving_enabled = False
        self.save_file = None
        self.translation_save_file = None
        self._close_log_outputs(*files)

    @staticmethod
    def _close_log_outputs(*files):
        for output in files:
            if output is not None:
                try:
                    output.close()
                except OSError:
                    logging.exception("关闭 MQTT 日志失败")

    # -------------------------
    # apply max messages
    # -------------------------
    def _apply_max_messages(self):
        try:
            val = int(self.spin_max.get())
            if val < 10:
                raise ValueError("不能小于 10")
            self.max_messages = val
            self._finish_paired_output(self._output_follows_latest())
            self._append_plain(f"[信息] 最大显示行数已设为 {self.max_messages}。")
            self._update_msg_count_label()
        except Exception as e:
            messagebox.showerror("输入错误", f"最大显示行数无效：{e}")

    # -------------------------
    # topics save/load
    # -------------------------
    def _save_topics_to_disk(self, silent=True):
        if self._topics_load_failed:
            return
        arr = []
        for item in self.sub_entries:
            topic = item["topic_var"].get().strip()
            if not topic:
                continue
            arr.append({
                "enabled": bool(item["enabled_var"].get()),
                "topic": topic,
                "note": item["note_var"].get().strip(),
            })
        path = topic_file_path()
        pending_path = None
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=folder or ".",
                prefix="topics-", suffix=".tmp", delete=False,
            ) as f:
                pending_path = f.name
                json.dump(arr, f, ensure_ascii=False, indent=2)
            os.replace(pending_path, path)
            pending_path = None
            if not silent:
                self._append_plain(f"[信息] 已保存 {len(arr)} 个订阅主题：{path}")
        except (OSError, ValueError) as e:
            logging.exception("订阅主题自动保存失败: %s", e)
            if not silent:
                messagebox.showerror("保存失败", f"订阅主题保存失败：{e}")
        finally:
            if pending_path is not None:
                try:
                    os.unlink(pending_path)
                except OSError:
                    logging.warning("无法清理临时主题配置：%s", pending_path)

    def _load_topics_from_disk(self):
        path = topic_file_path()
        self._loading_topics = True
        migrate = False
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)
            if not isinstance(arr, list):
                raise ValueError("主题配置须为列表")
            entries = []
            for item in arr:
                if isinstance(item, str):
                    entries.append((item, "", True))
                    migrate = True
                elif (
                    isinstance(item, dict)
                    and isinstance(item.get("topic"), str)
                    and isinstance(item.get("note", ""), str)
                    and isinstance(item.get("enabled", True), bool)
                ):
                    entries.append((item["topic"], item.get("note", ""), item.get("enabled", True)))
                else:
                    raise ValueError("主题配置含有不兼容的条目")

            for item in self.sub_entries:
                item["row"].destroy()
            self.sub_entries.clear()
            for topic, note, enabled in entries or [("", "", True)]:
                self._add_subscription_row(topic, note, enabled, schedule_save=False)
            self._append_plain(f"[信息] 已加载 {len(arr)} 个订阅主题。")
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            self._topics_load_failed = True
            logging.exception("读取主题配置失败")
            self._append_plain(f"[错误] 主题配置读取失败，已暂停保存以保护原文件。修复后请重启：{exc}")
        finally:
            self._loading_topics = False
            self.after_idle(self._refresh_subscription_scrollregion)
            if migrate:
                self._schedule_topics_save()

    # -------------------------
    # shutdown
    # -------------------------
    def on_close(self):
        """
        安全非阻塞关闭
        """
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._connection_cancel is not None:
            self._connection_cancel.set()
        self._mark_mqtt_link_down()
        self._clear_connection_timeout()
        self.btn_connection.config(state=tk.DISABLED)
        self._close_log_files()
        self._finish_close(self.client_thread)

    def _finish_close(self, worker, retries=20):
        if worker is not None and worker.is_alive() and retries:
            self.after(100, self._finish_close, worker, retries - 1)
            return
        self._final_destroy()

    def _final_destroy(self):
        try:
            try:
                self._save_topics_to_disk()
            except Exception:
                pass
            if self._translation_save_after_id is not None:
                self.after_cancel(self._translation_save_after_id)
                self._save_field_translations()
        finally:
            try:
                self.destroy()
            except Exception:
                pass



    # -------------------------
    # FDCAN
    # -------------------------
    def toggle_fdcan_panel(self):
        if not hasattr(self, "fdcan_frame"):
            return
        if not self.fdcan_visible:
            self.main_pane.insert(1, self.fdcan_frame)
            self.fdcan_visible = True
            self.btn_fdcan.config(text="关闭 FDCAN")
        else:
            self.main_pane.forget(self.fdcan_frame)
            self.fdcan_visible = False
            self.btn_fdcan.config(text="FDCAN 解析")

    def parse_fdcan(self):
        raw = self.fdcan_input.get("1.0", tk.END).strip()
        raw = raw.replace(" ", "").replace("\r", "").replace("\n", "").upper()

        self.fdcan_output.delete("1.0", tk.END)

        try:
            data = bytes.fromhex(raw)
        except Exception:
            self.fdcan_output.insert(tk.END, "解析状态：失败\n\n失败原因：非法HEX字符串")
            return

        pos = 0
        idx = 1
        total = len(data)
        result = []

        while pos < total:
            length_pos = pos
            length = data[pos]
            pos += 1

            if length == 0:
                self.fdcan_output.insert(
                    tk.END,
                    f"解析状态：失败\n\n失败原因：长度字段为0\n数据序号：{idx}\n位置：字节[{length_pos}]"
                )
                return

            remain = total - pos
            if length > remain:
                self.fdcan_output.insert(
                    tk.END,
                    f"解析状态：失败\n\n失败原因：长度不足\n数据序号：{idx}\n长度字段位置：字节[{length_pos}]\n声明长度：{length}\n剩余长度：{remain}"
                )
                return

            payload = data[pos:pos + length]
            pos += length

            result.append(
                f"数据{idx}：\n长度：{length}\n数据内容：{payload.hex().upper()}\n"
            )
            idx += 1

        self.fdcan_output.insert(
            tk.END,
            f"解析状态：成功\n\n总长度：{total} 字节\n解析条数：{idx-1}\n\n" + "\n".join(result)
        )

# ----------------------------
# run
# ----------------------------
if __name__ == "__main__":
    app = MQTT_AES_Pro_v2()
    app.mainloop()
