# -*- coding: utf-8 -*-
"""
JT/T 808 协议 HEX 解析 GUI 工具。

功能重点：
1. 输入的 HEX 会先自动去掉回车、换行、空格、Tab。
2. 支持 7E 帧边界、7D01/7D02 转义还原、异或校验。
3. 解析 JT/T 808-2013 常规消息头，并兼容 2019 版本标识位的头部长度。
4. 对常见标准消息体做结构化解析，未知消息体保留原始 HEX。
"""

import json
import os
import getpass
import re
import csv
import zlib
import queue
import threading
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk


SAMPLE_HEX = "7E00010005115436621650000220D1814000617E"
ICON_FILENAME = "_GT117-YK-808-icon-preview.ico"


def resource_path(filename):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, filename)

MESSAGE_ID_NAMES = {
    0x0001: "终端通用应答",
    0x0002: "终端心跳",
    0x0003: "终端注销",
    0x0004: "查询服务器时间",
    0x0005: "终端补传分包请求",
    0x0100: "终端注册",
    0x0102: "终端鉴权",
    0x0104: "查询终端参数应答",
    0x0107: "查询终端属性应答",
    0x0108: "终端升级结果通知",
    0x0200: "位置信息汇报",
    0x0201: "位置信息查询应答",
    0x0F3B: "压缩数据上报",
    0x0F42: "查询TBOX信息指令",
    0x0303: "信息点播/取消",
    0x0500: "车辆控制应答",
    0x0700: "行驶记录仪数据上传",
    0x0702: "驾驶员身份信息采集上报",
    0x0301: "事件报告",
    0x0302: "提问应答",
    0x0704: "定位数据批量上传",
    0x0705: "CAN总线数据上传",
    0x0800: "多媒体事件信息上传",
    0x0801: "多媒体数据上传",
    0x8001: "平台通用应答",
    0x8003: "服务器补传分包请求",
    0x8004: "查询服务器时间应答",
    0x8100: "终端注册应答",
    0x8103: "设置终端参数",
    0x8104: "查询终端参数",
    0x8105: "终端控制",
    0x8106: "查询指定终端参数",
    0x8107: "查询终端属性",
    0x8108: "下发终端升级包",
    0x8140: "平台数据同步",
    0x8201: "位置信息查询",
    0x8202: "临时位置跟踪控制",
    0x8203: "人工确认报警消息",
    0x8204: "服务器向终端发起链路检测请求",
    0x8300: "文本信息下发",
    0x8301: "事件设置",
    0x8302: "提问下发",
    0x8303: "信息点播菜单设置",
    0x8304: "信息服务",
    0x8400: "电话回拨",
    0x8401: "设置电话本",
    0x8500: "车辆控制",
    0x8600: "设置圆形区域",
    0x8601: "删除圆形区域",
    0x8602: "设置矩形区域",
    0x8603: "删除矩形区域",
    0x8604: "设置多边形区域",
    0x8605: "删除多边形区域",
    0x8606: "设置路线",
    0x8607: "删除路线",
    0x8700: "行驶记录仪数据采集命令",
    0x8701: "行驶记录仪参数下传命令",
    0x8702: "上报驾驶员身份信息请求",
    0x8800: "多媒体数据上传应答",
    0x8801: "摄像头立即拍摄命令",
    0x0805: "摄像头立即拍摄命令应答",
}

RESULT_NAMES = {
    0x00: "Success",
    0x01: "Failure",
    0x02: "Message error",
    0x03: "Unsupported",
    0x04: "Alarm processing confirmation",
}

REGISTER_RESULT_NAMES = {
    0x00: "Success",
    0x01: "Vehicle registered",
    0x02: "No vehicle in database",
    0x03: "Terminal registered",
    0x04: "No terminal in database",
}

ENCRYPTION_NAMES = {
    0: "None",
    1: "RSA",
}

ALARM_BIT_NAMES = {
    0: "紧急报警",
    1: "超速报警",
    2: "疲劳驾驶",
    3: "危险预警",
    4: "GNSS模块故障",
    5: "GNSS天线未接或被剪断",
    6: "GNSS天线短路",
    7: "终端主电源欠压",
    8: "终端主电源掉电",
    9: "终端LCD或显示器故障",
    10: "TTS模块故障",
    11: "摄像头故障",
    18: "当天累计驾驶超时",
    19: "超时停车",
    20: "进出区域",
    21: "进出路线",
    22: "路段行驶时间不足/过长",
    23: "路线偏离报警",
    24: "车辆VSS故障",
    25: "车辆油量异常",
    26: "车辆被盗",
    27: "车辆非法点火",
    28: "车辆非法位移",
    29: "碰撞侧翻报警",
    30: "非法开门报警",
}

STATUS_BIT_NAMES = {
    0: "ACC开",
    1: "定位",
    2: "南纬",
    3: "西经",
    4: "运营状态",
    5: "经纬度已保密插件加密",
    10: "车辆油路断开",
    11: "车辆电路断开",
    12: "车门加锁",
    13: "前门开",
    14: "中门开",
    15: "后门开",
    16: "驾驶席门开",
    17: "自定义门开",
    18: "使用GPS卫星定位",
    19: "使用北斗卫星定位",
    20: "使用GLONASS卫星定位",
    21: "使用Galileo卫星定位",
}

STATUS_BIT_VALUE_LABELS = {
    0: ("熄火", "点火"),
    1: ("未定位", "定位"),
    2: ("北纬", "南纬"),
    3: ("东经", "西经"),
    13: ("门1关（前门）", "门1开（前门）"),
    14: ("门2关（中门）", "门2开（中门）"),
    15: ("门3关（后门）", "门3开（后门）"),
}

TERMINAL_TYPE_BIT_NAMES = {
    0: "适用客运车辆",
    1: "适用危险品车辆",
    2: "适用普通货运车辆",
    3: "适用出租车辆",
    6: "支持硬盘录像",
    7: "分体机",
    8: "适用挂车",
}

GNSS_MODULE_BIT_NAMES = {
    0: "支持GPS定位",
    1: "支持北斗定位",
    2: "支持GLONASS定位",
    3: "支持Galileo定位",
}

COMM_MODULE_BIT_NAMES = {
    0: "支持GPRS通信",
    1: "支持CDMA通信",
    2: "支持TD-SCDMA通信",
    3: "支持WCDMA通信",
    4: "支持CDMA2000通信",
    5: "支持TD-LTE通信",
    7: "支持其他通信方式",
}

UPGRADE_TYPE_NAMES = {
    0x00: "终端",
    0x0C: "道路运输证IC卡读卡器",
    0x34: "卫星定位模块/北斗卫星定位模块",
}

UPGRADE_RESULT_NAMES = {
    0x00: "成功",
    0x01: "失败",
    0x02: "取消",
}

PHONEBOOK_SETTING_TYPE_NAMES = {
    0x00: "删除终端上所有存储的联系人",
    0x01: "更新电话本",
    0x02: "追加电话本",
    0x03: "修改电话本",
}


class ParseError(ValueError):
    """用于把解析错误清晰显示到 GUI。"""


def clean_hex_text(text):
    """去掉常见空白，并兼容用户从文档里复制出的引号和 0x 前缀。"""
    cleaned = text.strip().strip("\"'“”‘’")
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"(?i)0x", "", cleaned)
    return cleaned.upper()


def ensure_hex_bytes(hex_text):
    cleaned = clean_hex_text(hex_text)
    if not cleaned:
        raise ParseError("请输入 HEX 数据。")
    if len(cleaned) % 2:
        raise ParseError("HEX 长度必须为偶数。")
    if re.search(r"[^0-9A-F]", cleaned):
        raise ParseError("输入中包含非 HEX 字符，请只输入 0-9、A-F。")
    try:
        return cleaned, bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ParseError(f"HEX 转字节失败：{exc}") from exc


def xor_checksum(data):
    value = 0
    for item in data:
        value ^= item
    return value


def unescape_808(data):
    result = bytearray()
    i = 0
    while i < len(data):
        current = data[i]
        if current == 0x7D:
            if i + 1 >= len(data):
                raise ParseError("转义字节 7D 后缺少后续字节。")
            next_byte = data[i + 1]
            if next_byte == 0x02:
                result.append(0x7E)
            elif next_byte == 0x01:
                result.append(0x7D)
            else:
                raise ParseError(f"非法转义序列：7D{next_byte:02X}")
            i += 2
        else:
            result.append(current)
            i += 1
    return bytes(result)


def bytes_to_bcd(data):
    chars = []
    for item in data:
        chars.append(f"{(item >> 4) & 0x0F:X}")
        chars.append(f"{item & 0x0F:X}")
    return "".join(chars)


def read_u8(data, offset):
    require_length(data, offset, 1)
    return data[offset], offset + 1


def read_u16(data, offset):
    require_length(data, offset, 2)
    return int.from_bytes(data[offset:offset + 2], "big"), offset + 2


def read_u32(data, offset):
    require_length(data, offset, 4)
    return int.from_bytes(data[offset:offset + 4], "big"), offset + 4


def read_bytes(data, offset, size):
    require_length(data, offset, size)
    return data[offset:offset + size], offset + size


def require_length(data, offset, size):
    if offset + size > len(data):
        raise ParseError(f"数据长度不足：偏移 {offset} 需要 {size} 字节，实际剩余 {len(data) - offset} 字节。")


def hex_slice(data):
    return data.hex().upper()


def safe_decode(data):
    stripped = data.rstrip(b"\x00")
    if not stripped:
        return ""
    for encoding in ("gbk", "ascii", "utf-8"):
        try:
            return stripped.decode(encoding)
        except UnicodeDecodeError:
            continue
    return hex_slice(data)


def format_bits(value, width):
    return f"{value:0{width}b}"


def parse_message_body_property(prop, protocol="2013"):
    binary = format_bits(prop, 16)
    prop_hex = f"{prop:04X}"
    encrypt_type = (prop >> 10) & 0x07
    version_flag = protocol == "2019" and bool((prop >> 14) & 0x01)
    return {
        f"[{prop_hex}]消息体属性HEX": f"0x{prop_hex}",
        f"[{binary}]消息体属性二进制": binary,
        "协议标准": "JT/T 808-2019" if protocol == "2019" else "JT/T 808-2013",
        "版本号": "JTT2019" if version_flag else ("未启用版本标识" if protocol == "2019" else "不适用"),
        "[bit15]保留": (prop >> 15) & 0x01,
        "[bit14]版本标识" if protocol == "2019" else "[bit14]保留": (prop >> 14) & 0x01,
        "[bit13]是否分包": bool((prop >> 13) & 0x01),
        "[bit10~bit12]数据加密": ENCRYPTION_NAMES.get(encrypt_type, f"Unknown({encrypt_type})"),
        "[bit0~bit9]消息体长度": prop & 0x03FF,
    }


def parse_header(packet_without_checksum, protocol="2013"):
    msg_id, offset = read_u16(packet_without_checksum, 0)
    prop, offset = read_u16(packet_without_checksum, offset)
    prop_obj = parse_message_body_property(prop, protocol)
    version_flag = protocol == "2019" and bool((prop >> 14) & 0x01)

    protocol_version = None
    if version_flag:
        protocol_version, offset = read_u8(packet_without_checksum, offset)
        phone_len = 10
    else:
        phone_len = 6

    require_length(packet_without_checksum, offset, phone_len + 2)
    phone_raw = packet_without_checksum[offset:offset + phone_len]
    phone = bytes_to_bcd(phone_raw)
    offset += phone_len
    serial, offset = read_u16(packet_without_checksum, offset)

    package_info = None
    if (prop >> 13) & 0x01:
        total, offset = read_u16(packet_without_checksum, offset)
        index, offset = read_u16(packet_without_checksum, offset)
        package_info = {
            f"[{total:04X}]消息包总数": total,
            f"[{index:04X}]包序号": index,
        }

    body_length = prop & 0x03FF
    body = packet_without_checksum[offset:offset + body_length]
    if len(body) != body_length:
        raise ParseError(f"消息体长度不足：属性中声明 {body_length} 字节，实际 {len(body)} 字节。")

    extra = packet_without_checksum[offset + body_length:]
    if extra:
        raise ParseError(f"消息体后存在多余数据：{hex_slice(extra)}")

    header = {
        f"[{msg_id:04X}]消息Id": msg_id,
        "消息名称": MESSAGE_ID_NAMES.get(msg_id, f"Unknown(0x{msg_id:04X})"),
        "解析标准": "JT/T 808-2019" if protocol == "2019" else "JT/T 808-2013",
        "消息体属性对象": prop_obj,
    }
    if protocol_version is not None:
        header[f"[{protocol_version:02X}]协议版本号"] = protocol_version
    header[f"[{hex_slice(phone_raw)}]终端手机号"] = phone
    header[f"[{serial:04X}]消息流水号"] = serial
    if package_info:
        header["分包对象"] = package_info

    return msg_id, body, header


def parse_common_response(body, response_name):
    if len(body) != 5:
        return {
            response_name: hex_slice(body),
            "解析提示": f"标准通用应答长度应为 5 字节，当前为 {len(body)} 字节。",
        }
    response_serial = int.from_bytes(body[0:2], "big")
    response_msg_id = int.from_bytes(body[2:4], "big")
    result = body[4]
    return {
        response_name: hex_slice(body),
        f"[{body[0:2].hex().upper()}]应答流水号": response_serial,
        f"[{body[2:4].hex().upper()}]应答消息Id": response_msg_id,
        f"[{body[4]:02X}]结果": RESULT_NAMES.get(result, f"Unknown({result})"),
    }


def parse_terminal_register(body, protocol="2013"):
    result = {"终端注册": hex_slice(body)}
    if protocol == "2019":
        manufacturer_len = 11
        model_len = 30
        terminal_id_len = 30
        min_len = 76
        layout_name = "JT/T 808-2019：制造商ID11字节，型号30字节，终端ID30字节"
    else:
        manufacturer_len = 5
        model_len = 20
        terminal_id_len = 7
        min_len = 37
        layout_name = "JT/T 808-2013：制造商ID5字节，型号20字节，终端ID7字节"

    if len(body) < min_len:
        result["解析提示"] = f"{layout_name}，最短 {min_len} 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    province, offset = read_u16(body, offset)
    city, offset = read_u16(body, offset)
    manufacturer, offset = read_bytes(body, offset, manufacturer_len)
    model, offset = read_bytes(body, offset, model_len)
    terminal_id, offset = read_bytes(body, offset, terminal_id_len)
    plate_color, offset = read_u8(body, offset)
    plate = body[offset:]

    result.update({
        "字段长度布局": layout_name,
        f"[{body[0:2].hex().upper()}]省域ID": province,
        f"[{body[2:4].hex().upper()}]市县域ID": city,
        f"[{hex_slice(manufacturer)}]制造商ID": safe_decode(manufacturer),
        f"[{hex_slice(model)}]终端型号": safe_decode(model),
        f"[{hex_slice(terminal_id)}]终端ID": safe_decode(terminal_id),
        f"[{plate_color:02X}]车牌颜色": plate_color,
        f"[{hex_slice(plate)}]车辆标识": safe_decode(plate),
    })
    return result


def parse_authentication(body, protocol="2013"):
    if protocol != "2019":
        return {
            "终端鉴权": hex_slice(body),
            "字段长度布局": "JT/T 808-2013：消息体直接为鉴权码",
            f"[{hex_slice(body)}]鉴权码": safe_decode(body),
        }

    result = {
        "终端鉴权": hex_slice(body),
        "字段长度布局": "JT/T 808-2019：鉴权码长度 + 鉴权码 + IMEI + 软件版本号",
    }
    if len(body) < 36:
        result["解析提示"] = f"2019 鉴权消息至少需要 1+n+15+20 字节，当前为 {len(body)} 字节。"
        result[f"[{hex_slice(body)}]原始鉴权数据"] = safe_decode(body)
        return result

    offset = 0
    auth_len, offset = read_u8(body, offset)
    if len(body) < 1 + auth_len + 15 + 20:
        result["解析提示"] = f"鉴权码长度声明 {auth_len} 字节后，剩余数据不足 IMEI 和软件版本号。"
        result[f"[{hex_slice(body)}]原始鉴权数据"] = safe_decode(body)
        return result
    auth_code, offset = read_bytes(body, offset, auth_len)
    imei, offset = read_bytes(body, offset, 15)
    software_version, offset = read_bytes(body, offset, 20)
    extra = body[offset:]
    result.update({
        f"[{auth_len:02X}]鉴权码长度": auth_len,
        f"[{hex_slice(auth_code)}]鉴权码内容": safe_decode(auth_code),
        f"[{hex_slice(imei)}]终端IMEI": safe_decode(imei),
        f"[{hex_slice(software_version)}]软件版本号": decode_trimmed_text(software_version),
    })
    if extra:
        result["扩展数据"] = hex_slice(extra)
    return result


def parse_bit_field(value, mapping):
    bits = {
        f"bit{bit}": bool((value >> bit) & 0x01)
        for bit in range(0, max(mapping.keys()) + 1 if mapping else 0)
    }
    labels = [name for bit, name in mapping.items() if (value >> bit) & 0x01]
    return bits, labels


def decode_trimmed_text(data):
    return safe_decode(data).rstrip("\x00").strip()


def parse_terminal_property_response(body, protocol="2013"):
    result = {"查询终端属性应答": hex_slice(body)}
    if len(body) < 48:
        result["解析提示"] = f"终端属性应答长度过短，当前为 {len(body)} 字节。"
        return result

    def try_layout(model_len, terminal_id_len, layout_name):
        offset = 0
        terminal_type, offset = read_u16(body, offset)
        manufacturer_id, offset = read_bytes(body, offset, 5)
        model, offset = read_bytes(body, offset, model_len)
        terminal_id, offset = read_bytes(body, offset, terminal_id_len)
        iccid, offset = read_bytes(body, offset, 10)
        hw_len, offset = read_u8(body, offset)
        hw_version, offset = read_bytes(body, offset, hw_len)
        fw_len, offset = read_u8(body, offset)
        fw_version, offset = read_bytes(body, offset, fw_len)
        gnss_attr, offset = read_u8(body, offset)
        comm_attr, offset = read_u8(body, offset)
        return {
            "layout_name": layout_name,
            "model_len": model_len,
            "terminal_id_len": terminal_id_len,
            "terminal_type": terminal_type,
            "manufacturer_id": manufacturer_id,
            "model": model,
            "terminal_id": terminal_id,
            "iccid": iccid,
            "hw_len": hw_len,
            "hw_version": hw_version,
            "fw_len": fw_len,
            "fw_version": fw_version,
            "gnss_attr": gnss_attr,
            "comm_attr": comm_attr,
            "extra": body[offset:],
            "offset": offset,
        }

    if protocol == "2019":
        layouts = [
            (30, 30, "JT/T 808-2019：型号30字节，终端ID30字节"),
        ]
    else:
        layouts = [
            (20, 15, "JT/T 808-2013：型号20字节，终端ID15字节"),
            (20, 7, "JT/T 808-2013 早期/窄终端ID兼容：型号20字节，终端ID7字节"),
        ]

    parsed = None
    parse_errors = []
    for model_len, terminal_id_len, layout_name in layouts:
        try:
            candidate = try_layout(model_len, terminal_id_len, layout_name)
            if not candidate["extra"]:
                parsed = candidate
                break
            if parsed is None or len(candidate["extra"]) < len(parsed["extra"]):
                parsed = candidate
        except ParseError as exc:
            parse_errors.append(f"{layout_name}: {exc}")

    if parsed is None:
        result["解析提示"] = "无法匹配终端属性应答字段长度布局。"
        result["尝试记录"] = parse_errors
        return result

    terminal_type = parsed["terminal_type"]
    manufacturer_id = parsed["manufacturer_id"]
    model = parsed["model"]
    terminal_id = parsed["terminal_id"]
    iccid = parsed["iccid"]
    hw_len = parsed["hw_len"]
    hw_version = parsed["hw_version"]
    fw_len = parsed["fw_len"]
    fw_version = parsed["fw_version"]
    gnss_attr = parsed["gnss_attr"]
    comm_attr = parsed["comm_attr"]
    extra = parsed["extra"]

    terminal_bits, terminal_labels = parse_bit_field(terminal_type, TERMINAL_TYPE_BIT_NAMES)
    gnss_bits, gnss_labels = parse_bit_field(gnss_attr, GNSS_MODULE_BIT_NAMES)
    comm_bits, comm_labels = parse_bit_field(comm_attr, COMM_MODULE_BIT_NAMES)

    result.update({
        "字段长度布局": parsed["layout_name"],
        f"[{body[0:2].hex().upper()}]终端类型": terminal_type,
        "终端类型对象": terminal_bits,
        "终端类型说明": terminal_labels,
        f"[{hex_slice(manufacturer_id)}]制造商ID": decode_trimmed_text(manufacturer_id),
        f"[{hex_slice(model)}]终端型号": decode_trimmed_text(model),
        f"[{hex_slice(terminal_id)}]终端ID": decode_trimmed_text(terminal_id),
        f"[{hex_slice(iccid)}]终端SIM卡ICCID": bytes_to_bcd(iccid),
        f"[{hw_len:02X}]终端硬件版本号长度": hw_len,
        f"[{hex_slice(hw_version)}]终端硬件版本号": decode_trimmed_text(hw_version),
        f"[{fw_len:02X}]终端固件版本号长度": fw_len,
        f"[{hex_slice(fw_version)}]终端固件版本号": decode_trimmed_text(fw_version),
        f"[{gnss_attr:02X}]GNSS模块属性": gnss_attr,
        "GNSS模块属性对象": gnss_bits,
        "GNSS模块属性说明": gnss_labels,
        f"[{comm_attr:02X}]通信模块属性": comm_attr,
        "通信模块属性对象": comm_bits,
        "通信模块属性说明": comm_labels,
    })
    if extra:
        result["扩展数据"] = hex_slice(extra)
    return result


def parse_upgrade_package(body):
    result = {"下发终端升级包": hex_slice(body)}
    if len(body) < 11:
        result["解析提示"] = f"标准升级包最短 11 字节，不含升级数据时也需要基本头部。当前为 {len(body)} 字节。"
        return result

    offset = 0
    upgrade_type, offset = read_u8(body, offset)
    manufacturer_id, offset = read_bytes(body, offset, 5)
    version_len, offset = read_u8(body, offset)
    version, offset = read_bytes(body, offset, version_len)
    package_len, offset = read_u32(body, offset)
    package_data = body[offset:offset + package_len]
    if len(package_data) != package_len:
        result["解析提示"] = f"升级数据包长度声明 {package_len} 字节，实际 {len(package_data)} 字节。"
        return result

    result.update({
        f"[{upgrade_type:02X}]升级类型": UPGRADE_TYPE_NAMES.get(upgrade_type, f"Unknown({upgrade_type})"),
        f"[{hex_slice(manufacturer_id)}]制造商ID": decode_trimmed_text(manufacturer_id),
        f"[{version_len:02X}]终端固件版本号长度": version_len,
        f"[{hex_slice(version)}]终端固件版本号": decode_trimmed_text(version),
        f"[{package_len:08X}]升级数据包长度": package_len,
        f"[{hex_slice(package_data)}]升级数据包": hex_slice(package_data),
    })
    return result


def parse_upgrade_result_notification(body):
    result = {"终端升级结果通知": hex_slice(body)}
    if len(body) < 2:
        result["解析提示"] = f"升级结果通知最短 2 字节，当前为 {len(body)} 字节。"
        return result
    upgrade_type, offset = read_u8(body, 0)
    upgrade_result, offset = read_u8(body, offset)
    result.update({
        f"[{upgrade_type:02X}]升级类型": UPGRADE_TYPE_NAMES.get(upgrade_type, f"Unknown({upgrade_type})"),
        f"[{upgrade_result:02X}]升级结果": UPGRADE_RESULT_NAMES.get(upgrade_result, f"Unknown({upgrade_result})"),
    })
    if offset < len(body):
        result["扩展数据"] = hex_slice(body[offset:])
    return result


def active_bit_names(value, names):
    active = {}
    for bit, name in names.items():
        active[f"bit{bit}"] = bool((value >> bit) & 0x01)
        if active[f"bit{bit}"]:
            active[f"bit{bit}说明"] = name
    return active


def parse_location_status(value):
    status = {}
    for bit, name in STATUS_BIT_NAMES.items():
        bit_value = (value >> bit) & 0x01
        labels = STATUS_BIT_VALUE_LABELS.get(bit)
        if labels:
            status[f"bit{bit}"] = f"{bit_value}-{labels[bit_value]}"
        elif bit_value:
            status[f"bit{bit}"] = f"1-{name}"
        else:
            status[f"bit{bit}"] = "0"
    return status


def status_text_for_excel(status_obj, bit):
    value = status_obj.get(f"bit{bit}", "")
    if isinstance(value, str) and "-" in value:
        return value.split("-", 1)[1]
    return value or "N/A"


def format_number(value, digits=4):
    if isinstance(value, float):
        text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


LOCATION_EXTRA_PID_COLUMNS = [0x01, 0x02, 0x07, 0x2A, 0x2B, 0x30, 0x31]
LOCATION_E6_PID_COLUMNS = [0x08, 0x14, 0x15]
LOCATION_BASE_HEADERS = ["纬度", "经度", "高度", "速度", "方向", "时间", "点火状态", "定位"]

LOCATION_TYPE_NAMES = {
    1: "圆形区域",
    2: "矩形区域",
    3: "多边形区域",
    4: "路线",
}

LOCATION_ENTER_EXIT_NAMES = {
    0: "进",
    1: "出",
}

ROUTE_TIME_RESULT_NAMES = {
    0: "不足",
    1: "过长",
}


def decode_e6_pid_value(pid, data):
    if data and all(item == 0xFF for item in data):
        return "无效", ""

    raw = int.from_bytes(data, "big") if data else 0
    rules = {
        1: ("仪表车速", "km/h", lambda x: x / 256),
        4: ("发动机实际扭矩百分比", "%", lambda x: x - 125),
        5: ("发动机转速", "rpm", lambda x: x * 0.125),
        6: ("冷却水温", "℃", lambda x: x - 40),
        8: ("ECU 总油耗", "L", lambda x: x * 0.5),
        9: ("油门踏板位置", "%", lambda x: x * 0.4),
        14: ("尿素箱液位", "%", lambda x: x * 0.4),
        20: ("发动机燃油消耗率", "L/h", lambda x: x * 0.05),
        21: ("发动机瞬时油耗率", "km/L", lambda x: x / 512),
        26: ("发动机进气压力", "kPa", lambda x: x * 2),
        31: ("发动机进气温度", "℃", lambda x: x - 40),
        39: ("仪表燃油液位", "%", lambda x: x * 0.4),
        41: ("仪表总里程", "km", lambda x: x * 0.125),
        42: ("积分里程", "km", lambda x: x / 1000),
        43: ("积分油耗", "L", lambda x: x * 0.0005),
        44: ("尿素实际喷射量", "ml/h", lambda x: x * 0.01),
        45: ("累计尿素消耗量", "g", lambda x: x),
    }
    bit_rules = {
        10: ("驻车制动开关", "", {0: "驻车制动开关在关闭状态", 1: "驻车制动开关在打开状态"}),
        12: ("离合开关状态", "", {0: "离合器踏板被松开", 1: "离合器踏板被踩下", 2: "错误", 3: "不可用"}),
    }
    if pid in rules:
        name, unit, converter = rules[pid]
        return format_number(converter(raw)), name + (f"({unit})" if unit else "")
    if pid in bit_rules:
        name, unit, states = bit_rules[pid]
        return states.get(raw, str(raw)), name + (f"({unit})" if unit else "")
    return hex_slice(data), f"未知PID({pid})"


def parse_location_area_route_alarm(value):
    location_type = value[0]
    area_route_id = int.from_bytes(value[1:5], "big")
    direction = value[5]
    return {
        f"[{value[0]:02X}]位置类型": f"{location_type}-{LOCATION_TYPE_NAMES.get(location_type, '未知')}",
        f"[{value[1:5].hex().upper()}]区域或路线ID": area_route_id,
        f"[{value[5]:02X}]进出方向": f"{direction}-{LOCATION_ENTER_EXIT_NAMES.get(direction, '未知')}",
        "单元格值": (
            f"类型={LOCATION_TYPE_NAMES.get(location_type, f'未知({location_type})')};"
            f"ID={area_route_id};"
            f"方向={LOCATION_ENTER_EXIT_NAMES.get(direction, f'未知({direction})')}"
        ),
    }


def parse_route_time_alarm(value):
    route_id = int.from_bytes(value[0:4], "big")
    route_time = int.from_bytes(value[4:6], "big")
    result = value[6]
    return {
        f"[{value[0:4].hex().upper()}]路段ID": route_id,
        f"[{value[4:6].hex().upper()}]路段行驶时间(s)": route_time,
        f"[{value[6]:02X}]结果": f"{result}-{ROUTE_TIME_RESULT_NAMES.get(result, '未知')}",
        "单元格值": (
            f"路段ID={route_id};"
            f"行驶时间={route_time}s;"
            f"结果={ROUTE_TIME_RESULT_NAMES.get(result, f'未知({result})')}"
        ),
    }


def parse_e6_private_klv(value):
    result = {
        "E6原始值": hex_slice(value),
        "KLV列表": [],
    }
    offset = 0
    while offset < len(value):
        item_start = offset
        if offset + 3 > len(value):
            result["解析提示"] = f"E6 KLV 数据不足：偏移 {offset} 后不足 PID 和长度字段。"
            break
        pid_raw = value[offset:offset + 2]
        pid = int.from_bytes(pid_raw, "big")
        offset += 2
        data_len = value[offset]
        offset += 1
        if offset + data_len > len(value):
            result["解析提示"] = f"E6 PID {hex_slice(pid_raw)} 长度声明 {data_len} 字节，实际剩余 {len(value) - offset} 字节。"
            break
        data = value[offset:offset + data_len]
        offset += data_len
        decoded_value, label = decode_e6_pid_value(pid, data)
        result["KLV列表"].append({
            "E6内部偏移": item_start,
            f"[{hex_slice(pid_raw)}]PID": pid,
            f"[{data_len:02X}]数据长度": data_len,
            f"[{hex_slice(data)}]数据": hex_slice(data),
            "解析值": decoded_value,
            "单元格值": decoded_value,
            "字段描述": label,
        })
    return result


def parse_location_extra(extra):
    result = {"附加信息原始": hex_slice(extra)}
    offset = 0
    items = []

    while offset < len(extra):
        item_start = offset
        item_id, offset = read_u8(extra, offset)
        item_len, offset = read_u8(extra, offset)
        require_length(extra, offset, item_len)
        value = extra[offset:offset + item_len]
        offset += item_len

        item = {
            f"[{item_id:02X}]附加信息ID": item_id,
            f"[{item_len:02X}]附加信息长度": item_len,
            "原始值": hex_slice(value),
        }
        if item_id == 0x01 and item_len == 4:
            item["里程(km)"] = int.from_bytes(value, "big") / 10
            item["单元格值"] = format_number(item["里程(km)"])
        elif item_id == 0x02 and item_len == 2:
            item["油量(L)"] = int.from_bytes(value, "big") / 10
            item["单元格值"] = format_number(item["油量(L)"])
        elif item_id == 0x07 and item_len == 2:
            item["新能源动力电池包电量SOC(%)"] = int.from_bytes(value, "big") / 10
            item["单元格值"] = format_number(item["新能源动力电池包电量SOC(%)"])
        elif item_id == 0x03 and item_len == 2:
            item["行驶记录速度(km/h)"] = int.from_bytes(value, "big") / 10
            item["单元格值"] = format_number(item["行驶记录速度(km/h)"])
        elif item_id == 0x04 and item_len == 2:
            item["需要人工确认报警事件ID"] = int.from_bytes(value, "big")
            item["单元格值"] = item["需要人工确认报警事件ID"]
        elif item_id == 0x12 and item_len == 6:
            item["进出区域路线报警对象"] = parse_location_area_route_alarm(value)
            item["单元格值"] = item["进出区域路线报警对象"]["单元格值"]
        elif item_id == 0x13 and item_len == 7:
            item["路线行驶时间报警对象"] = parse_route_time_alarm(value)
            item["单元格值"] = item["路线行驶时间报警对象"]["单元格值"]
        elif item_id == 0x25 and item_len == 4:
            item["扩展车辆信号状态"] = int.from_bytes(value, "big")
            item["单元格值"] = item["扩展车辆信号状态"]
        elif item_id == 0x2A and item_len == 2:
            item["IO状态"] = int.from_bytes(value, "big")
            item["单元格值"] = item["IO状态"]
        elif item_id == 0x2B and item_len == 4:
            ad0 = int.from_bytes(value[0:2], "big")
            ad1 = int.from_bytes(value[2:4], "big")
            item["模拟量AD0"] = ad0
            item["模拟量AD1"] = ad1
            item["单元格值"] = f"AD0={ad0};AD1={ad1}"
        elif item_id == 0x30 and item_len == 1:
            item["无线通信网络信号强度"] = value[0]
            item["单元格值"] = value[0]
        elif item_id == 0x31 and item_len == 1:
            item["GNSS定位卫星数"] = value[0]
            item["单元格值"] = value[0]
        elif item_id == 0xE6:
            e6_obj = parse_e6_private_klv(value)
            item["E6私有协议对象"] = e6_obj
        else:
            item["解析提示"] = "未知或暂未细分的附加信息项"
            item["单元格值"] = hex_slice(value)
        item["附加信息区偏移"] = item_start
        items.append(item)

    result["附加信息列表"] = items
    return result


def parse_location_report(body, name="位置信息汇报"):
    result = {name: hex_slice(body)}
    if len(body) < 28:
        result["解析提示"] = f"位置基础信息至少 28 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    alarm, offset = read_u32(body, offset)
    status, offset = read_u32(body, offset)
    latitude_raw, offset = read_u32(body, offset)
    longitude_raw, offset = read_u32(body, offset)
    altitude, offset = read_u16(body, offset)
    speed_raw, offset = read_u16(body, offset)
    direction, offset = read_u16(body, offset)
    time_raw = body[offset:offset + 6]
    offset += 6
    extra = body[offset:]

    result.update({
        f"[{body[0:4].hex().upper()}]报警标志": alarm,
        "报警标志对象": active_bit_names(alarm, ALARM_BIT_NAMES),
        f"[{body[4:8].hex().upper()}]状态": status,
        "状态对象": parse_location_status(status),
        f"[{body[8:12].hex().upper()}]纬度": latitude_raw / 1_000_000,
        f"[{body[12:16].hex().upper()}]经度": longitude_raw / 1_000_000,
        f"[{body[16:18].hex().upper()}]高程(m)": altitude,
        f"[{body[18:20].hex().upper()}]速度(km/h)": speed_raw / 10,
        f"[{body[20:22].hex().upper()}]方向": direction,
        f"[{hex_slice(time_raw)}]时间": bytes_to_bcd(time_raw),
    })
    if extra:
        result["附加信息对象"] = parse_location_extra(extra)
    return result


F3B_CSV_COLUMNS = [
    ("516129", "时间", "BCD/文本时间"),
    ("516130", "纬度", "度"),
    ("516131", "经度", "度"),
    ("516132", "GPS速度", "km/h"),
    ("516133", "定位状态", "bit0~13方向;bit14南纬;bit15西经"),
    ("516134", "高度", "m"),
    ("1624", "仪表车速", "km/h"),
    ("190", "发动机转速", "rpm"),
    ("513", "发动机实际扭矩", "%"),
    ("91", "油门踏板开度", "%"),
    ("183", "燃油消耗率", "L/h"),
    ("516097", "开关信号", "bit0驻车/bit1离合/bit2制动"),
    ("102", "发动机进气歧管压力", "kPa"),
    ("100", "发动机机油压力", "kPa"),
    ("110", "发动机冷却液温度", "℃"),
    ("520_10", "缓速器实际扭矩百分比", "%"),
    ("516120", "发动机/缓速器扭矩模式", ""),
    ("1715", "需求缓速器扭矩百分比", "%"),
    ("1717", "当前转速下缓速器最大扭矩百分比", "%"),
    ("523", "当前档位", ""),
    ("1807", "方向盘转角", "°"),
    ("521", "制动踏板位置", "%"),
    ("516125", "VCU坡度", "%"),
]

F3B_CSV_COLUMN_MAP = {
    code: {"name": name, "unit": unit}
    for code, name, unit in F3B_CSV_COLUMNS
}


def is_invalid_ff_text(value):
    text = str(value or "").strip()
    return bool(text) and len(text) % 2 == 0 and re.fullmatch(r"(?:FF)+", text, re.IGNORECASE)


F3B_HIGH_DENSITY_TYPE_NAMES = {
    0b0001: "100ms",
    0b0010: "500ms",
    0b0011: "1s",
    0b0100: "5s",
    0b0101: "10s",
    0b0110: "30s",
    0b0111: "1m",
    0b1000: "2m",
}

F3B_SWITCH_SIGNAL_BITS = {
    0: {0: "驻车制动开关关闭", 1: "驻车制动开关打开"},
    1: {0: "离合开关松开", 1: "离合开关踩下"},
    2: {0: "制动踏板开关松下", 1: "制动踏板开关踩下"},
    3: {0: "点火开关位置 IGN OFF", 1: "点火开关位置 IGN ON"},
    4: {0: "ABS 未介入信号", 1: "ABS 介入信号"},
    5: {0: "TCS 未介入信号", 1: "TCS 介入信号"},
    6: {0: "变速器空挡关", 1: "变速器空挡开"},
    7: {0: "挂车连接信号无效", 1: "挂车连接信号有效"},
    8: {0: "车门关信号无效", 1: "车门关信号有效"},
    13: {0: "巡航激活状态未激活", 1: "巡航激活状态有效"},
    14: {0: "挂车驻车状态关闭", 1: "挂车驻车状态有效"},
    15: {0: "倒挡开关状态关闭", 1: "倒挡开关状态有效"},
}

F3B_FUEL_LEAK_WARNING_NAMES = {
    0b00: "No Warning",
    0b01: "Warning",
    0b10: "Reserved",
    0b11: "Don't care",
}

F3B_EP_MODE_NAMES = {
    0b00: "ECO驾驶模式",
    0b01: "Power驾驶模式",
    0b10: "保留",
    0b11: "无效",
}

F3B_TORQUE_MODE_NAMES = {
    0b0000: "低怠速调速器/无请求(默认模式)",
    0b0001: "加速踏板/操作员选择",
    0b0010: "巡航控制",
    0b0011: "PTO 调速器",
    0b0100: "道路速度调速器",
    0b0101: "ASR 控制",
    0b0110: "传动控制",
    0b0111: "ABS 控制",
    0b1000: "转矩限制",
    0b1001: "高速调速器",
    0b1010: "制动系统",
    0b1011: "远程加速器",
    0b1100: "未定义",
    0b1101: "未定义",
    0b1110: "其他",
    0b1111: "不可用",
}


def parse_0f3b_compress_flag(flag):
    bit0 = flag & 0x01
    high_density_type = (flag >> 1) & 0x0F
    return {
        f"[{flag:02X}]压缩标志HEX": f"0x{flag:02X}",
        f"[{flag:08b}]压缩标志二进制": f"{flag:08b}",
        "[bit0]是否压缩": "1-Zip压缩" if bit0 else "0-不压缩",
        "[bit1~bit4]高密采集类型": (
            f"{high_density_type:04b}-{F3B_HIGH_DENSITY_TYPE_NAMES.get(high_density_type, '未定义')}"
        ),
    }


def f3b_value_with_unit(value, unit):
    text = str(value).strip()
    return f"{text} {unit}" if unit and text else text


def parse_f3b_int_text(value, binary_width=None):
    text = str(value or "").strip()
    if not text or is_invalid_ff_text(text):
        return None
    if binary_width and re.fullmatch(rf"[01]{{{binary_width}}}", text):
        return int(text, 2)
    if text.lower().startswith("0x"):
        return int(text, 16)
    if re.search(r"[A-Fa-f]", text):
        return int(text, 16)
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return int(float(text))
    return None


def format_f3b_time(value):
    text = str(value or "").strip()
    if len(text) == 12 and text.isdigit():
        return f"20{text[0:2]}-{text[2:4]}-{text[4:6]} {text[6:8]}:{text[8:10]}:{text[10:12]}"
    if len(text) == 14 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]} {text[8:10]}:{text[10:12]}:{text[12:14]}"
    return text


def format_f3b_location_status(value):
    raw = parse_f3b_int_text(value, binary_width=16)
    if raw is None:
        return str(value).strip()
    direction = raw & 0x3FFF
    lat_dir = "南纬" if (raw >> 14) & 0x01 else "北纬"
    lon_dir = "西经" if (raw >> 15) & 0x01 else "东经"
    return f"{direction}° {lat_dir} {lon_dir}"


def format_f3b_switch_signal_object(value):
    raw = parse_f3b_int_text(value, binary_width=16)
    if raw is None:
        return {}

    result = {}
    for bit in range(0, 9):
        bit_value = (raw >> bit) & 0x01
        result[f"bit{bit}"] = f"{bit_value}-{F3B_SWITCH_SIGNAL_BITS[bit][bit_value]}"

    fuel_warning = (raw >> 9) & 0x03
    ep_mode = (raw >> 11) & 0x03
    result["bit9~bit10"] = f"{fuel_warning:02b}-{F3B_FUEL_LEAK_WARNING_NAMES.get(fuel_warning, 'Unknown')}"
    result["bit11~bit12"] = f"{ep_mode:02b}-{F3B_EP_MODE_NAMES.get(ep_mode, 'Unknown')}"

    for bit in range(13, 16):
        bit_value = (raw >> bit) & 0x01
        result[f"bit{bit}"] = f"{bit_value}-{F3B_SWITCH_SIGNAL_BITS[bit][bit_value]}"
    return result


def format_f3b_switch_signal(value):
    switch_obj = format_f3b_switch_signal_object(value)
    if not switch_obj:
        return str(value).strip()
    return "\n".join(f"{key}: {item}" for key, item in switch_obj.items())


def format_f3b_torque_mode(value):
    raw = parse_f3b_int_text(value, binary_width=4)
    if raw is None:
        return str(value).strip()
    mode = raw & 0x0F
    return f"{mode:04b}-{F3B_TORQUE_MODE_NAMES.get(mode, 'Unknown')}"


def format_f3b_csv_value(code, value, unit):
    text = str(value or "").strip()
    if is_invalid_ff_text(text):
        return "无效"
    if code == "516129":
        return format_f3b_time(text)
    if code in ("516130", "516131"):
        try:
            return f"{float(text):.6f} 度"
        except ValueError:
            return f3b_value_with_unit(text, "度")
    if code == "516132":
        return f3b_value_with_unit(text, "km/h")
    if code == "516133":
        return format_f3b_location_status(text)
    if code == "516134":
        return f3b_value_with_unit(text, "m")
    if code == "516097":
        return format_f3b_switch_signal(text)
    if code == "516120":
        return format_f3b_torque_mode(text)
    return f3b_value_with_unit(text, unit)


def format_f3b_summary_number(data, scale=1, unit=""):
    if data and all(item == 0xFF for item in data):
        return "无效"
    value = int.from_bytes(data, "big") * scale
    return f3b_value_with_unit(format_number(value), unit)


TBOX_SUB_MESSAGE_NAMES = {
    0x08: "终端设备属性上传",
    0x24: "设置海外模式应答",
    0x25: "查询海外模式应答",
}

TBOX_OVERSEAS_MODE_NAMES = {
    0x01: "国内",
    0x02: "海外",
}

TBOX_CONFIG_RESULT_NAMES = {
    0x00: "设置失败",
    0x01: "设置成功",
}

TBOX_JSON_FIELD_NAMES = {
    "appVer": "APP软件版本",
    "manuf": "厂商标识",
    "countryCode": "国别编码",
    "overseasMode": "海外模式",
    "ip_address": "公网IP地址",
    "ip_info": "IP归属地(国家/地区)",
}


def describe_tbox_overseas_mode(value):
    return f"{value}-{TBOX_OVERSEAS_MODE_NAMES.get(value, f'Unknown({value})')}"


def parse_tbox_json_content(content):
    text = decode_trimmed_text(content)
    result = {
        "JSON文本": text,
    }
    if not text:
        result["解析提示"] = "JSON 内容为空。"
        return result
    try:
        json_obj = json.loads(text)
    except json.JSONDecodeError as exc:
        result["JSON解析错误"] = str(exc)
        return result

    result["JSON对象"] = json_obj
    if isinstance(json_obj, dict):
        field_obj = {}
        for raw_key, label in TBOX_JSON_FIELD_NAMES.items():
            if raw_key not in json_obj:
                continue
            value = json_obj[raw_key]
            if raw_key == "overseasMode":
                try:
                    value = describe_tbox_overseas_mode(int(value))
                except (TypeError, ValueError):
                    value = f"{value}-Unknown({value})"
            field_obj[f"{raw_key}-{label}"] = value
        if field_obj:
            result["字段对象"] = field_obj
    else:
        result["解析提示"] = "JSON 内容不是对象结构。"
    return result


def parse_0f42_tbox_info(body):
    result = {"查询TBOX信息指令": hex_slice(body)}
    records = []
    offset = 0
    index = 1

    while offset < len(body):
        record_start = offset
        if len(body) - offset < 5:
            result["解析提示"] = f"0F42 子消息头不足 5 字节，偏移 {offset} 剩余 {len(body) - offset} 字节。"
            result["未解析尾部HEX"] = hex_slice(body[offset:])
            break

        serial = int.from_bytes(body[offset:offset + 2], "big")
        sub_msg_id = body[offset + 2]
        content_len = int.from_bytes(body[offset + 3:offset + 5], "big")
        offset += 5

        record = {
            "序号": index,
            f"[{body[record_start:record_start + 2].hex().upper()}]流水号": serial,
            f"[{sub_msg_id:02X}]子消息ID": TBOX_SUB_MESSAGE_NAMES.get(sub_msg_id, f"Unknown(0x{sub_msg_id:02X})"),
            f"[{body[record_start + 3:record_start + 5].hex().upper()}]内容长度": content_len,
        }

        if len(body) - offset < content_len:
            record["解析错误"] = f"内容长度声明 {content_len} 字节，实际剩余 {len(body) - offset} 字节。"
            record["剩余内容HEX"] = hex_slice(body[offset:])
            records.append(record)
            break

        content = body[offset:offset + content_len]
        offset += content_len
        record["内容HEX"] = hex_slice(content)

        if sub_msg_id == 0x08:
            record["终端设备属性对象"] = parse_tbox_json_content(content)
        elif sub_msg_id == 0x24:
            if content_len >= 1:
                config_result = content[0]
                record[f"[{config_result:02X}]配置结果"] = TBOX_CONFIG_RESULT_NAMES.get(
                    config_result,
                    f"Unknown({config_result})",
                )
            if content_len != 1:
                record["解析提示"] = f"设置海外模式应答内容长度应为 1，当前为 {content_len}。"
        elif sub_msg_id == 0x25:
            if content_len >= 3:
                overseas_mode = content[0]
                country_code = int.from_bytes(content[1:3], "big")
                record[f"[{overseas_mode:02X}]海外模式"] = describe_tbox_overseas_mode(overseas_mode)
                record[f"[{content[1:3].hex().upper()}]国别编码"] = country_code
            else:
                record["解析错误"] = f"查询海外模式应答内容长度应为 3，当前为 {content_len}。"
            if content_len != 3:
                record["解析提示"] = f"查询海外模式应答内容长度固定为 3，当前为 {content_len}。"
        else:
            record["内容文本"] = decode_trimmed_text(content)
            record["解析提示"] = "未知 TBOX 子消息，已保留原始内容。"

        records.append(record)
        index += 1

    result["TBOX子消息数量"] = len(records)
    result["TBOX子消息列表"] = records
    return result


def parse_0f3b_compressed_report(body):
    result = {"压缩数据上报": hex_slice(body)}
    if len(body) < 9:
        result["解析提示"] = f"0F3B 消息体至少 9 字节固定头，当前为 {len(body)} 字节。"
        return result

    frequency = int.from_bytes(body[0:2], "big")
    compress_flag = body[2]
    reserved = body[3:7]
    content_len = int.from_bytes(body[7:9], "big")
    compress_flag_obj = parse_0f3b_compress_flag(compress_flag)
    is_compressed = bool(compress_flag & 0x01)
    result.update({
        f"[{body[0:2].hex().upper()}]采集频率": f"{frequency} x 10ms",
        f"[{body[0:2].hex().upper()}]采集周期": f"{frequency * 10}ms",
        "压缩标志对象": compress_flag_obj,
        f"[{hex_slice(reserved)}]保留字段": hex_slice(reserved),
        f"[{body[7:9].hex().upper()}]内容长度": content_len,
        "内容长度说明": "Zip压缩后长度" if is_compressed else "未压缩明文长度",
    })

    actual_len = len(body) - 9
    if actual_len < content_len:
        result["解析提示"] = f"内容长度声明 {content_len} 字节，实际剩余 {actual_len} 字节。"
        return result

    content = body[9:9 + content_len]
    trailing = body[9 + content_len:]
    result["内容数据HEX"] = hex_slice(content)
    result["内容数据实际长度"] = len(content)
    if trailing:
        result["尾部多余数据"] = hex_slice(trailing)

    if is_compressed:
        result["压缩数据HEX"] = hex_slice(content)
        try:
            plain = zlib.decompress(content)
        except zlib.error as exc:
            result["解析错误"] = f"zlib 解压失败：{exc}"
            return result
        result["解压后HEX"] = hex_slice(plain)
        result["解压后长度"] = len(plain)
    else:
        plain = content
        result["明文HEX"] = hex_slice(plain)
        result["明文长度"] = len(plain)
        result["解压后长度"] = len(plain)

    if len(plain) < 22:
        result["解析提示"] = f"内容明文不足 22 字节，当前为 {len(plain)} 字节。"
        return result

    summary = {
        f"[{hex_slice(plain[0:2])}]当日里程": format_f3b_summary_number(plain[0:2], 0.1, "km"),
        f"[{hex_slice(plain[2:6])}]仪表总里程": format_f3b_summary_number(plain[2:6], 0.1, "km"),
        f"[{hex_slice(plain[6:10])}]ECU总里程": format_f3b_summary_number(plain[6:10], 0.1, "km"),
        f"[{hex_slice(plain[10:12])}]当日油耗": format_f3b_summary_number(plain[10:12], 0.1, "L"),
        f"[{hex_slice(plain[12:16])}]仪表总油耗": format_f3b_summary_number(plain[12:16], 1, "L"),
        f"[{hex_slice(plain[16:20])}]ECU总油耗": format_f3b_summary_number(plain[16:20], 1, "L"),
        "内容行数": int.from_bytes(plain[20:22], "big"),
    }
    summary.update({
        "当日里程(km)": summary[f"[{hex_slice(plain[0:2])}]当日里程"],
        "仪表总里程(km)": summary[f"[{hex_slice(plain[2:6])}]仪表总里程"],
        "ECU总里程(km)": summary[f"[{hex_slice(plain[6:10])}]ECU总里程"],
        "当日油耗(L)": summary[f"[{hex_slice(plain[10:12])}]当日油耗"],
        "仪表总油耗(L)": summary[f"[{hex_slice(plain[12:16])}]仪表总油耗"],
        "ECU总油耗(L)": summary[f"[{hex_slice(plain[16:20])}]ECU总油耗"],
    })
    result["汇总对象"] = summary

    csv_text = plain[22:].decode("utf-8", errors="replace").rstrip("\x00")
    result["CSV明文"] = csv_text
    csv_rows = list(csv.reader(csv_text.splitlines()))
    if not csv_rows or not csv_rows[0]:
        result["解析提示"] = "22 字节汇总字段之后未找到 CSV 表头。"
        return result

    headers = [item.strip() for item in csv_rows[0]]
    details = []
    for row_index, row in enumerate(csv_rows[1:], start=1):
        raw_values = {}
        parsed_values = {}
        parsed_row = {
            "CSV行号": row_index,
            "字段原始值对象": raw_values,
            "字段值对象": parsed_values,
            "未知字段对象": {},
        }
        for column_index, code in enumerate(headers):
            value = row[column_index].strip() if column_index < len(row) else ""
            column_info = F3B_CSV_COLUMN_MAP.get(code)
            if column_info:
                parsed_value = format_f3b_csv_value(code, value, column_info["unit"])
                raw_values[code] = value
                parsed_values[code] = parsed_value
                key = f"[{code}]{column_info['name']}"
                if column_info["unit"]:
                    key += f"({column_info['unit']})"
                if code == "516097" and not is_invalid_ff_text(value):
                    parsed_row[key] = format_f3b_switch_signal_object(value)
                else:
                    parsed_row[key] = parsed_value
            else:
                parsed_row["未知字段对象"][code] = value
        if not parsed_row["未知字段对象"]:
            parsed_row.pop("未知字段对象")
        details.append(parsed_row)

    result["CSV表头列表"] = headers
    result["CSV明细列表"] = details
    data_row_count = len(details)
    declared = summary["内容行数"]
    if declared and declared != data_row_count + 1:
        result["解析提示"] = f"汇总字段声明内容行数 {declared}，实际 CSV 为 1 行表头 + {data_row_count} 行数据。"
    return result


def parse_register_response(body):
    result = {"终端注册应答": hex_slice(body)}
    if len(body) < 3:
        result["解析提示"] = f"注册应答最短 3 字节，当前为 {len(body)} 字节。"
        return result
    response_serial = int.from_bytes(body[0:2], "big")
    register_result = body[2]
    result.update({
        f"[{body[0:2].hex().upper()}]应答流水号": response_serial,
        f"[{body[2]:02X}]结果": REGISTER_RESULT_NAMES.get(register_result, f"Unknown({register_result})"),
    })
    if len(body) > 3:
        auth = body[3:]
        result[f"[{hex_slice(auth)}]鉴权码"] = safe_decode(auth)
    return result


TERMINAL_PARAMETER_NAMES = {
    0x00000001: ("终端心跳发送间隔", "DWORD", "秒"),
    0x00000002: ("TCP消息应答超时时间", "DWORD", "秒"),
    0x00000003: ("TCP消息重传次数", "DWORD", "次"),
    0x00000004: ("UDP消息应答超时时间", "DWORD", "秒"),
    0x00000005: ("UDP消息重传次数", "DWORD", "次"),
    0x00000010: ("主服务器APN", "STRING", ""),
    0x00000011: ("主服务器用户名", "STRING", ""),
    0x00000012: ("主服务器密码", "STRING", ""),
    0x00000013: ("主服务器地址", "STRING", ""),
    0x00000014: ("备份服务器APN", "STRING", ""),
    0x00000015: ("备份服务器用户名", "STRING", ""),
    0x00000016: ("备份服务器密码", "STRING", ""),
    0x00000017: ("备份服务器地址", "STRING", ""),
    0x00000018: ("服务器TCP端口", "WORD", ""),
    0x00000019: ("服务器UDP端口", "WORD", ""),
    0x00000020: ("位置汇报策略", "BYTE", ""),
    0x00000021: ("位置汇报方案", "BYTE", ""),
    0x00000022: ("驾驶员未登录汇报时间间隔", "DWORD", "秒"),
    0x00000023: ("驾驶员未登录汇报距离间隔", "DWORD", "米"),
    0x00000024: ("驾驶员未登录汇报次数", "DWORD", "次"),
    0x00000025: ("休眠时汇报时间间隔", "DWORD", "秒"),
    0x00000026: ("紧急报警时汇报时间间隔", "DWORD", "秒"),
    0x00000027: ("终端电话监听号码", "STRING", ""),
    0x00000028: ("终端电话回拨号码", "STRING", ""),
    0x00000029: ("位置汇报方式", "DWORD", "秒"),
    0x0000002A: ("电话回拨/监听功能", "BYTE", ""),
    0x00000083: ("车辆标识/VIN", "STRING", ""),
}


def decode_terminal_parameter(param_id, value):
    name, data_type, unit = TERMINAL_PARAMETER_NAMES.get(
        param_id,
        (f"未知参数(0x{param_id:08X})", "", ""),
    )
    if data_type == "STRING":
        decoded = decode_trimmed_text(value)
    elif data_type == "BYTE":
        decoded = int.from_bytes(value, "big") if value else 0
    elif data_type == "WORD":
        decoded = int.from_bytes(value, "big") if value else 0
    elif data_type == "DWORD":
        decoded = int.from_bytes(value, "big") if value else 0
    else:
        if len(value) in (1, 2, 4, 8):
            decoded = int.from_bytes(value, "big")
        else:
            decoded = decode_trimmed_text(value)

    display = str(decoded)
    if unit and data_type in ("BYTE", "WORD", "DWORD"):
        display = f"{display} {unit}"
    return {
        "参数名称": name,
        "参数类型": data_type or "自动",
        "参数值": decoded,
        "参数值显示": display,
        "参数单位": unit,
    }


def build_terminal_parameter_item(param_id, param_len, value):
    decoded = decode_terminal_parameter(param_id, value)
    return {
        f"[{param_id:08X}]参数ID": param_id,
        f"[{param_len:02X}]参数长度": param_len,
        "参数名称": decoded["参数名称"],
        "参数类型": decoded["参数类型"],
        "参数值HEX": hex_slice(value),
        "参数值": decoded["参数值"],
        "参数值文本": decoded["参数值显示"],
        "参数单位": decoded["参数单位"],
    }


def parse_query_param_response(body):
    result = {"查询终端参数应答": hex_slice(body)}
    if len(body) < 3:
        result["解析提示"] = f"参数应答最短 3 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    response_serial, offset = read_u16(body, offset)
    count, offset = read_u8(body, offset)
    params = []
    for _ in range(count):
        if offset >= len(body):
            break
        param_id, offset = read_u32(body, offset)
        param_len, offset = read_u8(body, offset)
        require_length(body, offset, param_len)
        value = body[offset:offset + param_len]
        offset += param_len
        params.append(build_terminal_parameter_item(param_id, param_len, value))

    result.update({
        f"[{body[0:2].hex().upper()}]应答流水号": response_serial,
        f"[{body[2]:02X}]应答参数个数": count,
        "参数列表": params,
    })
    if len(params) != count:
        result["解析提示"] = f"声明 {count} 个参数，实际解析 {len(params)} 个。"
    return result


def parse_set_params(body):
    result = {"设置终端参数": hex_slice(body)}
    if not body:
        result["解析提示"] = "参数个数为空。"
        return result

    offset = 0
    count, offset = read_u8(body, offset)
    params = []
    for _ in range(count):
        if offset >= len(body):
            break
        param_id, offset = read_u32(body, offset)
        param_len, offset = read_u8(body, offset)
        require_length(body, offset, param_len)
        value = body[offset:offset + param_len]
        offset += param_len
        params.append(build_terminal_parameter_item(param_id, param_len, value))

    result.update({
        f"[{body[0]:02X}]参数总数": count,
        "参数列表": params,
    })
    if len(params) != count:
        result["解析提示"] = f"声明 {count} 个参数，实际解析 {len(params)} 个。"
    return result


def parse_retransmission_request(body, name):
    result = {name: hex_slice(body)}
    if len(body) < 3:
        result["解析提示"] = f"补传分包请求最短 3 字节，当前为 {len(body)} 字节。"
        return result
    offset = 0
    original_serial, offset = read_u16(body, offset)
    count, offset = read_u8(body, offset)
    packet_ids = []
    for _ in range(count):
        if offset + 2 > len(body):
            break
        packet_id, offset = read_u16(body, offset)
        packet_ids.append(packet_id)
    result.update({
        f"[{body[0:2].hex().upper()}]原始消息流水号": original_serial,
        f"[{body[2]:02X}]重传包总数": count,
        "重传包ID列表": packet_ids,
    })
    if len(packet_ids) != count:
        result["解析提示"] = f"声明 {count} 个重传包 ID，实际解析 {len(packet_ids)} 个。"
    return result


def parse_query_specific_params(body):
    result = {"查询指定终端参数": hex_slice(body)}
    if not body:
        result["解析提示"] = "缺少参数总数。"
        return result
    offset = 0
    count, offset = read_u8(body, offset)
    param_ids = []
    for _ in range(count):
        if offset + 4 > len(body):
            break
        param_id, offset = read_u32(body, offset)
        param_ids.append(f"0x{param_id:08X}")
    result.update({
        f"[{body[0]:02X}]参数总数": count,
        "参数ID列表": param_ids,
    })
    if len(param_ids) != count:
        result["解析提示"] = f"声明 {count} 个参数 ID，实际解析 {len(param_ids)} 个。"
    return result


def parse_terminal_control(body):
    result = {"终端控制": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少命令字。"
        return result
    command_word = body[0]
    command_param = body[1:]
    result.update({
        f"[{command_word:02X}]命令字": command_word,
        f"[{hex_slice(command_param)}]命令参数": decode_trimmed_text(command_param),
    })
    return result


def parse_server_time_response(body):
    result = {"查询服务器时间应答": hex_slice(body)}
    if len(body) != 6:
        result["解析提示"] = f"服务器时间应答标准长度为 6 字节 BCD，当前为 {len(body)} 字节。"
        return result
    result[f"[{hex_slice(body)}]UTC时间"] = "20" + bytes_to_bcd(body)
    return result


def parse_text_info(body):
    result = {"文本信息下发": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少标志字段。"
        return result
    flag = body[0]
    text = body[1:]
    result.update({
        f"[{flag:02X}]标志": flag,
        "标志对象": {
            "bit0紧急": bool(flag & 0x01),
            "bit2终端显示器显示": bool(flag & 0x04),
            "bit3终端TTS播读": bool(flag & 0x08),
            "bit4广告屏显示": bool(flag & 0x10),
        },
        f"[{hex_slice(text)}]文本信息": safe_decode(text),
    })
    return result


def parse_event_setting(body):
    result = {"事件设置": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少设置类型。"
        return result
    offset = 0
    setting_type, offset = read_u8(body, offset)
    result[f"[{setting_type:02X}]设置类型"] = setting_type
    if offset >= len(body):
        return result

    count, offset = read_u8(body, offset)
    events = []
    for _ in range(count):
        if offset + 2 > len(body):
            break
        event_id, offset = read_u8(body, offset)
        event_len, offset = read_u8(body, offset)
        if offset + event_len > len(body):
            break
        event_content, offset = read_bytes(body, offset, event_len)
        events.append({
            f"[{event_id:02X}]事件ID": event_id,
            f"[{event_len:02X}]事件内容长度": event_len,
            f"[{hex_slice(event_content)}]事件内容": safe_decode(event_content),
        })
    result[f"[{count:02X}]事件总数"] = count
    result["事件列表"] = events
    if len(events) != count:
        result["解析提示"] = f"声明 {count} 个事件，实际解析 {len(events)} 个。"
    return result


def parse_info_demand_cancel(body):
    result = {"信息点播/取消": hex_slice(body)}
    if len(body) < 2:
        result["解析提示"] = f"标准长度为 2 字节，当前为 {len(body)} 字节。"
        return result
    result.update({
        f"[{body[0]:02X}]信息类型": body[0],
        f"[{body[1]:02X}]点播/取消标志": "取消" if body[1] == 0 else "点播",
    })
    return result


def parse_info_service(body):
    result = {"信息服务": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少信息类型。"
        return result
    result.update({
        f"[{body[0]:02X}]信息类型": body[0],
        f"[{hex_slice(body[1:])}]信息内容": safe_decode(body[1:]),
    })
    return result


def parse_phone_callback(body):
    result = {"电话回拨": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少标志字段。"
        return result
    result.update({
        f"[{body[0]:02X}]标志": "普通通话" if body[0] == 0 else "监听",
        f"[{hex_slice(body[1:])}]电话号码": safe_decode(body[1:]),
    })
    return result


def parse_phonebook_setting(body):
    result = {"设置电话本": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少设置类型。"
        return result
    offset = 0
    setting_type, offset = read_u8(body, offset)
    result[f"[{setting_type:02X}]设置类型"] = PHONEBOOK_SETTING_TYPE_NAMES.get(setting_type, f"Unknown({setting_type})")
    if offset >= len(body):
        return result
    count, offset = read_u8(body, offset)
    contacts = []
    for _ in range(count):
        if offset + 3 > len(body):
            break
        flag, offset = read_u8(body, offset)
        phone_len, offset = read_u8(body, offset)
        if offset + phone_len + 1 > len(body):
            break
        phone, offset = read_bytes(body, offset, phone_len)
        contact_len, offset = read_u8(body, offset)
        if offset + contact_len > len(body):
            break
        contact, offset = read_bytes(body, offset, contact_len)
        contacts.append({
            f"[{flag:02X}]标志": flag,
            f"[{phone_len:02X}]电话号码长度": phone_len,
            f"[{hex_slice(phone)}]电话号码": safe_decode(phone),
            f"[{contact_len:02X}]联系人长度": contact_len,
            f"[{hex_slice(contact)}]联系人": safe_decode(contact),
        })
    result[f"[{count:02X}]联系人总数"] = count
    result["联系人列表"] = contacts
    if len(contacts) != count:
        result["解析提示"] = f"声明 {count} 个联系人，实际解析 {len(contacts)} 个。"
    return result


def format_bcd_datetime_yyMMddHHmmss(data):
    text = bytes_to_bcd(data)
    if len(text) != 12:
        return text
    return f"20{text[0:2]}-{text[2:4]}-{text[4:6]} {text[6:8]}:{text[8:10]}:{text[10:12]}"


def parse_platform_data_sync(body):
    result = {"平台数据同步": hex_slice(body)}
    if len(body) < 20:
        result["解析提示"] = f"平台数据同步消息体固定长度为 20 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    time_raw, offset = read_bytes(body, offset, 6)
    response_serial, offset = read_u16(body, offset)
    gps_mileage_raw, offset = read_u32(body, offset)
    integral_mileage_raw, offset = read_u32(body, offset)
    integral_fuel_raw, offset = read_u32(body, offset)

    result.update({
        "方向": "平台下发",
        "回复": "终端通用应答(0x0001)",
        f"[{hex_slice(time_raw)}]时间": format_bcd_datetime_yyMMddHHmmss(time_raw),
        f"[{body[6:8].hex().upper()}]响应序号": response_serial,
        f"[{body[8:12].hex().upper()}]GPS里程(km)": format_number(gps_mileage_raw * 0.1, 1),
        f"[{body[12:16].hex().upper()}]积分里程(km)": format_number(integral_mileage_raw * 0.1, 1),
        f"[{body[16:20].hex().upper()}]积分油耗(mL)": integral_fuel_raw,
    })
    if len(body) > 20:
        result["尾部多余数据"] = hex_slice(body[20:])
        result["解析提示"] = f"平台数据同步消息体固定长度为 20 字节，当前为 {len(body)} 字节，尾部已保留。"
    return result


def parse_vehicle_control(body):
    result = {"车辆控制": hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少控制标志。"
        return result
    result.update({
        f"[{body[0]:02X}]控制标志": body[0],
        "控制标志对象": {
            "bit0车门": "车门加锁" if body[0] & 0x01 else "车门解锁",
        },
    })
    return result


def parse_vehicle_control_response(body):
    result = {"车辆控制应答": hex_slice(body)}
    if len(body) < 2:
        result["解析提示"] = "缺少应答流水号。"
        return result
    result[f"[{body[0:2].hex().upper()}]应答流水号"] = int.from_bytes(body[0:2], "big")
    result["位置数据对象"] = parse_location_report(body[2:], "位置数据") if len(body) > 2 else {}
    return result


def parse_alarm_manual_confirm(body):
    result = {"人工确认报警消息": hex_slice(body)}
    if len(body) < 6:
        result["解析提示"] = f"标准长度为 6 字节，当前为 {len(body)} 字节。"
        return result
    result.update({
        f"[{body[0:2].hex().upper()}]报警消息流水号": int.from_bytes(body[0:2], "big"),
        f"[{body[2:6].hex().upper()}]人工确认报警类型": int.from_bytes(body[2:6], "big"),
    })
    return result


def parse_temp_location_tracking(body):
    result = {"临时位置跟踪控制": hex_slice(body)}
    if len(body) < 6:
        result["解析提示"] = f"标准长度至少 6 字节，当前为 {len(body)} 字节。"
        return result
    interval = int.from_bytes(body[0:2], "big")
    validity = int.from_bytes(body[2:6], "big")
    result.update({
        f"[{body[0:2].hex().upper()}]时间间隔(s)": interval,
        f"[{body[2:6].hex().upper()}]位置跟踪有效期(s)": validity,
    })
    return result


def parse_batch_location(body):
    result = {"定位数据批量上传": hex_slice(body)}
    if len(body) < 3:
        result["解析提示"] = f"批量位置最短 3 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    count, offset = read_u16(body, offset)
    data_type, offset = read_u8(body, offset)
    locations = []
    for index in range(count):
        if offset >= len(body):
            break
        location_len, offset = read_u16(body, offset)
        require_length(body, offset, location_len)
        location_body = body[offset:offset + location_len]
        offset += location_len
        locations.append({
            "序号": index + 1,
            f"[{location_len:04X}]位置数据体长度": location_len,
            "位置数据体对象": parse_location_report(location_body, "位置数据体"),
        })

    result.update({
        f"[{body[0:2].hex().upper()}]数据项个数": count,
        f"[{body[2]:02X}]位置数据类型": "正常位置批量汇报" if data_type == 0 else f"盲区补报({data_type})",
        "位置数据项列表": locations,
    })
    if len(locations) != count:
        result["解析提示"] = f"声明 {count} 条位置数据，实际解析 {len(locations)} 条。"
    return result


def parse_can_bus_upload(body):
    result = {"CAN总线数据上传": hex_slice(body)}
    if len(body) < 7:
        result["解析提示"] = f"CAN 数据上传最短 7 字节，当前为 {len(body)} 字节。"
        return result
    offset = 0
    count, offset = read_u16(body, offset)
    time_raw, offset = read_bytes(body, offset, 5)
    items = []
    for index in range(count):
        if offset + 12 > len(body):
            break
        can_id, offset = read_u32(body, offset)
        can_data, offset = read_bytes(body, offset, 8)
        items.append({
            "序号": index + 1,
            f"[{can_id:08X}]CAN ID": can_id,
            f"[{hex_slice(can_data)}]CAN数据": hex_slice(can_data),
        })
    result.update({
        f"[{body[0:2].hex().upper()}]数据项个数": count,
        f"[{hex_slice(time_raw)}]CAN数据接收时间": bytes_to_bcd(time_raw),
        "CAN数据列表": items,
    })
    if len(items) != count:
        result["解析提示"] = f"声明 {count} 条 CAN 数据，实际解析 {len(items)} 条。"
    return result


def parse_multimedia_event(body):
    result = {"多媒体事件信息上传": hex_slice(body)}
    if len(body) < 8:
        result["解析提示"] = f"多媒体事件信息标准长度为 8 字节，当前为 {len(body)} 字节。"
        return result
    result.update({
        f"[{body[0:4].hex().upper()}]多媒体数据ID": int.from_bytes(body[0:4], "big"),
        f"[{body[4]:02X}]多媒体类型": body[4],
        f"[{body[5]:02X}]多媒体格式编码": body[5],
        f"[{body[6]:02X}]事件项编码": body[6],
        f"[{body[7]:02X}]通道ID": body[7],
    })
    if len(body) > 8:
        result["扩展数据"] = hex_slice(body[8:])
    return result


def parse_multimedia_upload(body):
    result = {"多媒体数据上传": hex_slice(body)}
    if len(body) < 36:
        result["解析提示"] = f"多媒体数据上传至少包含 8 字节多媒体头 + 28 字节位置基础信息，当前为 {len(body)} 字节。"
        return result
    result.update(parse_multimedia_event(body[:8]))
    result["位置数据对象"] = parse_location_report(body[8:36], "位置数据")
    result[f"[{hex_slice(body[36:])}]多媒体数据包"] = hex_slice(body[36:])
    return result


def parse_multimedia_upload_response(body):
    result = {"多媒体数据上传应答": hex_slice(body)}
    if len(body) < 5:
        result["解析提示"] = f"多媒体数据上传应答最短 5 字节，当前为 {len(body)} 字节。"
        return result
    offset = 0
    multimedia_id, offset = read_u32(body, offset)
    count, offset = read_u8(body, offset)
    packet_ids = []
    for _ in range(count):
        if offset + 2 > len(body):
            break
        packet_id, offset = read_u16(body, offset)
        packet_ids.append(packet_id)
    result.update({
        f"[{multimedia_id:08X}]多媒体数据ID": multimedia_id,
        f"[{count:02X}]重传包总数": count,
        "重传包ID列表": packet_ids,
    })
    if len(packet_ids) != count:
        result["解析提示"] = f"声明 {count} 个重传包 ID，实际解析 {len(packet_ids)} 个。"
    return result


def parse_camera_shoot_response(body):
    result = {"摄像头立即拍摄命令应答": hex_slice(body)}
    if len(body) < 3:
        result["解析提示"] = f"拍摄命令应答最短 3 字节，当前为 {len(body)} 字节。"
        return result
    offset = 0
    response_serial, offset = read_u16(body, offset)
    shoot_result, offset = read_u8(body, offset)
    multimedia_ids = []
    while offset + 4 <= len(body):
        multimedia_id, offset = read_u32(body, offset)
        multimedia_ids.append(multimedia_id)
    result.update({
        f"[{body[0:2].hex().upper()}]应答流水号": response_serial,
        f"[{shoot_result:02X}]结果": shoot_result,
        "多媒体ID列表": multimedia_ids,
    })
    return result


AREA_SETTING_TYPE_NAMES = {
    0: "更新区域",
    1: "追加区域",
    2: "修改区域",
}

AREA_ATTRIBUTE_NAMES = {
    0: "根据时间",
    1: "限速",
    2: "进区域报警给驾驶员",
    3: "进区域报警给平台",
    4: "出区域报警给驾驶员",
    5: "出区域报警给平台",
    6: "南纬",
    7: "西经",
    8: "禁止开门",
    14: "进区域关闭通信模块",
    15: "进区域采集GNSS详细定位数据",
}


def parse_area_attributes(value):
    active = [
        name for bit, name in AREA_ATTRIBUTE_NAMES.items()
        if (value >> bit) & 0x01
    ]
    return {
        f"[{value:04X}]区域属性HEX": f"0x{value:04X}",
        f"[{value:016b}]区域属性二进制": f"{value:016b}",
        "生效属性": active or ["无"],
    }


def parse_set_circular_area(body):
    result = {"设置圆形区域": hex_slice(body)}
    if len(body) < 2:
        result["解析提示"] = f"设置圆形区域至少需要 2 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    setting_type, offset = read_u8(body, offset)
    area_count, offset = read_u8(body, offset)
    areas = []

    for index in range(area_count):
        area_start = offset
        if offset + 18 > len(body):
            result["解析提示"] = (
                f"第 {index + 1} 个圆形区域固定字段不足 18 字节，"
                f"偏移 {offset} 实际剩余 {len(body) - offset} 字节。"
            )
            break

        area_id, offset = read_u32(body, offset)
        attributes, offset = read_u16(body, offset)
        latitude_raw, offset = read_u32(body, offset)
        longitude_raw, offset = read_u32(body, offset)
        radius, offset = read_u32(body, offset)

        area = {
            "序号": index + 1,
            "帧内偏移": area_start,
            f"[{body[area_start:area_start + 4].hex().upper()}]区域ID": area_id,
            f"[{body[area_start + 4:area_start + 6].hex().upper()}]区域属性": attributes,
            "区域属性对象": parse_area_attributes(attributes),
            f"[{body[area_start + 6:area_start + 10].hex().upper()}]中心点纬度": latitude_raw / 1000000,
            f"[{body[area_start + 10:area_start + 14].hex().upper()}]中心点经度": longitude_raw / 1000000,
            f"[{body[area_start + 14:area_start + 18].hex().upper()}]半径(m)": radius,
        }

        if (attributes >> 0) & 0x01:
            if offset + 12 > len(body):
                area["解析提示"] = "区域属性要求时间范围，但剩余数据不足 12 字节。"
                areas.append(area)
                break
            start_time_raw, offset = read_bytes(body, offset, 6)
            end_time_raw, offset = read_bytes(body, offset, 6)
            area[f"[{hex_slice(start_time_raw)}]起始时间"] = format_bcd_datetime_yyMMddHHmmss(start_time_raw)
            area[f"[{hex_slice(end_time_raw)}]结束时间"] = format_bcd_datetime_yyMMddHHmmss(end_time_raw)

        if (attributes >> 1) & 0x01:
            if offset + 3 > len(body):
                area["解析提示"] = "区域属性要求限速参数，但剩余数据不足 3 字节。"
                areas.append(area)
                break
            max_speed, offset = read_u16(body, offset)
            overspeed_duration, offset = read_u8(body, offset)
            area[f"[{body[offset - 3:offset - 1].hex().upper()}]最高速度(km/h)"] = max_speed
            area[f"[{body[offset - 1]:02X}]超速持续时间(s)"] = overspeed_duration

        areas.append(area)

    result.update({
        f"[{setting_type:02X}]设置属性": f"{setting_type}-{AREA_SETTING_TYPE_NAMES.get(setting_type, '未知')}",
        f"[{area_count:02X}]区域总数": area_count,
        "圆形区域列表": areas,
    })
    if len(areas) != area_count:
        result["解析提示"] = f"声明 {area_count} 个圆形区域，实际解析 {len(areas)} 个。"
    if offset < len(body):
        result["未解析尾部HEX"] = hex_slice(body[offset:])
    return result


def parse_area_time_speed_fields(body, offset, attributes, area):
    if (attributes >> 0) & 0x01:
        start_time_raw, offset = read_bytes(body, offset, 6)
        end_time_raw, offset = read_bytes(body, offset, 6)
        area[f"[{hex_slice(start_time_raw)}]起始时间"] = format_bcd_datetime_yyMMddHHmmss(start_time_raw)
        area[f"[{hex_slice(end_time_raw)}]结束时间"] = format_bcd_datetime_yyMMddHHmmss(end_time_raw)

    if (attributes >> 1) & 0x01:
        max_speed, offset = read_u16(body, offset)
        overspeed_duration, offset = read_u8(body, offset)
        area[f"[{max_speed:04X}]最高速度(km/h)"] = max_speed
        area[f"[{overspeed_duration:02X}]超速持续时间(s)"] = overspeed_duration
    return offset


def parse_set_rectangular_area(body):
    result = {"设置矩形区域": hex_slice(body)}
    if len(body) < 2:
        result["解析提示"] = f"设置矩形区域至少需要 2 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    setting_type, offset = read_u8(body, offset)
    area_count, offset = read_u8(body, offset)
    areas = []

    for index in range(area_count):
        area_start = offset
        if offset + 22 > len(body):
            result["解析提示"] = (
                f"第 {index + 1} 个矩形区域固定字段不足 22 字节，"
                f"偏移 {offset} 实际剩余 {len(body) - offset} 字节。"
            )
            break

        area_id, offset = read_u32(body, offset)
        attributes, offset = read_u16(body, offset)
        top_lat_raw, offset = read_u32(body, offset)
        top_lon_raw, offset = read_u32(body, offset)
        bottom_lat_raw, offset = read_u32(body, offset)
        bottom_lon_raw, offset = read_u32(body, offset)

        area = {
            "序号": index + 1,
            "帧内偏移": area_start,
            f"[{body[area_start:area_start + 4].hex().upper()}]区域ID": area_id,
            f"[{body[area_start + 4:area_start + 6].hex().upper()}]区域属性": attributes,
            "区域属性对象": parse_area_attributes(attributes),
            f"[{body[area_start + 6:area_start + 10].hex().upper()}]左上点纬度": top_lat_raw / 1000000,
            f"[{body[area_start + 10:area_start + 14].hex().upper()}]左上点经度": top_lon_raw / 1000000,
            f"[{body[area_start + 14:area_start + 18].hex().upper()}]右下点纬度": bottom_lat_raw / 1000000,
            f"[{body[area_start + 18:area_start + 22].hex().upper()}]右下点经度": bottom_lon_raw / 1000000,
        }

        try:
            offset = parse_area_time_speed_fields(body, offset, attributes, area)
        except ParseError as exc:
            area["解析提示"] = str(exc)
            areas.append(area)
            break
        areas.append(area)

    result.update({
        f"[{setting_type:02X}]设置属性": f"{setting_type}-{AREA_SETTING_TYPE_NAMES.get(setting_type, '未知')}",
        f"[{area_count:02X}]区域总数": area_count,
        "矩形区域列表": areas,
    })
    if len(areas) != area_count:
        result["解析提示"] = f"声明 {area_count} 个矩形区域，实际解析 {len(areas)} 个。"
    if offset < len(body):
        result["未解析尾部HEX"] = hex_slice(body[offset:])
    return result


def parse_set_polygon_area(body):
    result = {"设置多边形区域": hex_slice(body)}
    if len(body) < 8:
        result["解析提示"] = f"设置多边形区域至少需要 8 字节，当前为 {len(body)} 字节。"
        return result

    offset = 0
    area_id, offset = read_u32(body, offset)
    attributes, offset = read_u16(body, offset)
    area = {
        f"[{body[0:4].hex().upper()}]区域ID": area_id,
        f"[{body[4:6].hex().upper()}]区域属性": attributes,
        "区域属性对象": parse_area_attributes(attributes),
    }

    try:
        offset = parse_area_time_speed_fields(body, offset, attributes, area)
        vertex_count_offset = offset
        vertex_count, offset = read_u16(body, offset)
    except ParseError as exc:
        result["区域对象"] = area
        result["解析提示"] = str(exc)
        return result

    vertices = []
    for index in range(vertex_count):
        vertex_start = offset
        try:
            latitude_raw, offset = read_u32(body, offset)
            longitude_raw, offset = read_u32(body, offset)
        except ParseError as exc:
            result["解析提示"] = (
                f"声明 {vertex_count} 个顶点，解析第 {index + 1} 个顶点时失败：{exc}"
            )
            break
        vertices.append({
            "序号": index + 1,
            "帧内偏移": vertex_start,
            f"[{body[vertex_start:vertex_start + 4].hex().upper()}]顶点纬度": latitude_raw / 1000000,
            f"[{body[vertex_start + 4:vertex_start + 8].hex().upper()}]顶点经度": longitude_raw / 1000000,
        })

    area[f"[{body[vertex_count_offset:vertex_count_offset + 2].hex().upper()}]区域总顶点数"] = vertex_count
    area["顶点列表"] = vertices
    result["区域对象"] = area
    if len(vertices) != vertex_count:
        result["解析提示"] = f"声明 {vertex_count} 个顶点，实际解析 {len(vertices)} 个。"
    if offset < len(body):
        result["未解析尾部HEX"] = hex_slice(body[offset:])
    return result


def parse_delete_id_list(body, name):
    result = {name: hex_slice(body)}
    if len(body) < 1:
        result["解析提示"] = "缺少区域/路线数。"
        return result
    offset = 0
    count, offset = read_u8(body, offset)
    ids = []
    for _ in range(count):
        if offset + 4 > len(body):
            break
        item_id, offset = read_u32(body, offset)
        ids.append(item_id)
    result.update({
        f"[{count:02X}]区域/路线总数": count,
        "ID列表": [f"0x{item_id:08X}" for item_id in ids],
    })
    if len(ids) != count:
        result["解析提示"] = f"声明 {count} 个 ID，实际解析 {len(ids)} 个。"
    return result


def parse_raw_with_note(body, name, note):
    return {
        name: hex_slice(body),
        "解析提示": note,
    }


def parse_empty_body(body, name):
    if body:
        return {name: hex_slice(body), "解析提示": f"该标准消息体应为空，当前存在 {len(body)} 字节数据。"}
    return {name: "", "说明": "空消息体"}


def parse_body(msg_id, body, protocol="2013"):
    if msg_id == 0x0001:
        return parse_common_response(body, "终端通用应答")
    if msg_id == 0x8001:
        return parse_common_response(body, "平台通用应答")
    if msg_id in (0x0002, 0x0003, 0x0004, 0x8104, 0x8107, 0x8201, 0x8204, 0x8702):
        return parse_empty_body(body, MESSAGE_ID_NAMES.get(msg_id, f"Unknown(0x{msg_id:04X})"))
    if msg_id == 0x0005:
        return parse_retransmission_request(body, "终端补传分包请求")
    if msg_id == 0x0100:
        return parse_terminal_register(body, protocol)
    if msg_id == 0x0102:
        return parse_authentication(body, protocol)
    if msg_id == 0x0104:
        return parse_query_param_response(body)
    if msg_id == 0x0107:
        return parse_terminal_property_response(body, protocol)
    if msg_id == 0x0108:
        return parse_upgrade_result_notification(body)
    if msg_id == 0x0200:
        return parse_location_report(body)
    if msg_id == 0x0201:
        result = {"位置信息查询应答": hex_slice(body)}
        if len(body) >= 2:
            result[f"[{body[0:2].hex().upper()}]应答流水号"] = int.from_bytes(body[0:2], "big")
            result["位置数据对象"] = parse_location_report(body[2:], "位置数据")
        else:
            result["解析提示"] = "缺少应答流水号。"
        return result
    if msg_id == 0x0F3B:
        return parse_0f3b_compressed_report(body)
    if msg_id == 0x0F42:
        return parse_0f42_tbox_info(body)
    if msg_id == 0x0301:
        if len(body) == 1:
            return {"事件报告": hex_slice(body), f"[{body[0]:02X}]事件ID": body[0]}
        return {"事件报告": hex_slice(body), "解析提示": f"标准事件报告长度为 1 字节，当前为 {len(body)} 字节。"}
    if msg_id == 0x0302:
        result = {"提问应答": hex_slice(body)}
        if len(body) >= 3:
            result[f"[{body[0:2].hex().upper()}]应答流水号"] = int.from_bytes(body[0:2], "big")
            result[f"[{body[2]:02X}]答案ID"] = body[2]
        else:
            result["解析提示"] = f"提问应答最短 3 字节，当前为 {len(body)} 字节。"
        return result
    if msg_id == 0x0303:
        return parse_info_demand_cancel(body)
    if msg_id == 0x0500:
        return parse_vehicle_control_response(body)
    if msg_id == 0x0700:
        return parse_raw_with_note(body, "行驶记录仪数据上传", "已识别标准消息 ID，消息体按行驶记录仪透传数据保留原始 HEX。")
    if msg_id == 0x0702:
        return parse_raw_with_note(body, "驾驶员身份信息采集上报", "已识别标准消息 ID，驾驶员身份信息字段受状态和证件数据影响，当前保留原始 HEX。")
    if msg_id == 0x0704:
        return parse_batch_location(body)
    if msg_id == 0x0705:
        return parse_can_bus_upload(body)
    if msg_id == 0x0800:
        return parse_multimedia_event(body)
    if msg_id == 0x0801:
        return parse_multimedia_upload(body)
    if msg_id == 0x8003:
        return parse_retransmission_request(body, "服务器补传分包请求")
    if msg_id == 0x8004:
        return parse_server_time_response(body)
    if msg_id == 0x8100:
        return parse_register_response(body)
    if msg_id == 0x8103:
        return parse_set_params(body)
    if msg_id == 0x8105:
        return parse_terminal_control(body)
    if msg_id == 0x8106:
        return parse_query_specific_params(body)
    if msg_id == 0x8108:
        return parse_upgrade_package(body)
    if msg_id == 0x8140:
        return parse_platform_data_sync(body)
    if msg_id == 0x8202:
        return parse_temp_location_tracking(body)
    if msg_id == 0x8203:
        return parse_alarm_manual_confirm(body)
    if msg_id == 0x8300:
        return parse_text_info(body)
    if msg_id == 0x8301:
        return parse_event_setting(body)
    if msg_id == 0x8302:
        return parse_raw_with_note(body, "提问下发", "已识别标准消息 ID，可变候选答案列表暂按原始 HEX 保留。")
    if msg_id == 0x8303:
        return parse_raw_with_note(body, "信息点播菜单设置", "已识别标准消息 ID，可变菜单项暂按原始 HEX 保留。")
    if msg_id == 0x8304:
        return parse_info_service(body)
    if msg_id == 0x8400:
        return parse_phone_callback(body)
    if msg_id == 0x8401:
        return parse_phonebook_setting(body)
    if msg_id == 0x8500:
        return parse_vehicle_control(body)
    if msg_id == 0x8600:
        return parse_set_circular_area(body)
    if msg_id == 0x8602:
        return parse_set_rectangular_area(body)
    if msg_id == 0x8604:
        return parse_set_polygon_area(body)
    if msg_id in (0x8601, 0x8603, 0x8605, 0x8607):
        return parse_delete_id_list(body, MESSAGE_ID_NAMES.get(msg_id, f"Unknown(0x{msg_id:04X})"))
    if msg_id == 0x8606:
        return parse_raw_with_note(body, MESSAGE_ID_NAMES.get(msg_id, f"Unknown(0x{msg_id:04X})"), "已识别标准区域/路线设置消息，字段为可变结构，当前保留原始 HEX。")
    if msg_id in (0x8700, 0x8701):
        return parse_raw_with_note(body, MESSAGE_ID_NAMES.get(msg_id, f"Unknown(0x{msg_id:04X})"), "已识别标准行驶记录仪消息，当前保留原始 HEX。")
    if msg_id == 0x8800:
        return parse_multimedia_upload_response(body)
    if msg_id == 0x8801:
        return parse_raw_with_note(body, "摄像头立即拍摄命令", "已识别标准消息 ID，当前保留拍摄参数原始 HEX。")
    if msg_id == 0x0805:
        return parse_camera_shoot_response(body)

    return {
        MESSAGE_ID_NAMES.get(msg_id, f"Unknown(0x{msg_id:04X})"): hex_slice(body),
        "解析提示": "该消息 ID 暂未做消息体细分，已保留原始 HEX。",
    }


def normalize_protocol(protocol):
    protocol_text = str(protocol or "2013")
    return "2019" if "2019" in protocol_text else "2013"


def parse_one_frame(frame, protocol="2013"):
    protocol = normalize_protocol(protocol)
    if len(frame) < 2:
        raise ParseError("帧长度过短。")
    if frame[0] != 0x7E or frame[-1] != 0x7E:
        raise ParseError("标准 808 帧必须以 7E 开始并以 7E 结束。")

    escaped_payload = frame[1:-1]
    payload = unescape_808(escaped_payload)
    if len(payload) < 13:
        raise ParseError("帧内容过短，无法包含标准消息头和校验码。")

    packet_without_checksum = payload[:-1]
    received_checksum = payload[-1]
    calculated_checksum = xor_checksum(packet_without_checksum)
    msg_id, body, header = parse_header(packet_without_checksum, protocol)

    result = {"[7E]开始": 126}
    result.update(header)
    result["数据体对象"] = parse_body(msg_id, body, protocol)
    result[f"[{received_checksum:02X}]校验码"] = received_checksum
    result["校验结果对象"] = {
        "接收校验码": received_checksum,
        "计算校验码": calculated_checksum,
        "是否通过": received_checksum == calculated_checksum,
    }
    result["[7E]结束"] = 126
    return result


def split_frames(data):
    if not data:
        return []
    if data[0] == 0x7E and data[-1] == 0x7E and data.count(0x7E) == 2:
        return [data]

    frames = []
    start = None
    for index, byte in enumerate(data):
        if byte == 0x7E:
            if start is None:
                start = index
            else:
                if index > start:
                    frames.append(data[start:index + 1])
                start = index
    return frames


def parse_808_hex(hex_text, protocol="2013"):
    protocol = normalize_protocol(protocol)
    cleaned, data = ensure_hex_bytes(hex_text)
    frames = split_frames(data)
    if not frames:
        raise ParseError("未找到完整的 7E...7E 帧。")

    parsed_frames = [parse_one_frame(frame, protocol) for frame in frames]
    if len(parsed_frames) == 1 and len(frames[0]) == len(data):
        return parsed_frames[0]
    return {
        "清洗后HEX": cleaned,
        "帧数量": len(parsed_frames),
        "解析结果列表": parsed_frames,
    }


def extract_zipsend_hex(line):
    match = re.search(r"AT\+ZIPSEND\s*=\s*[^,]*,\s*([0-9A-Fa-f\s]+)", line, re.IGNORECASE)
    if not match:
        return None
    candidate = clean_hex_text(match.group(1))
    return candidate or None


def has_parse_warning(value):
    warning_keywords = ("解析提示", "解析错误", "解析失败", "数据长度不足", "无法匹配", "非法")
    if isinstance(value, dict):
        for key, item in value.items():
            if any(keyword in str(key) for keyword in warning_keywords):
                return True
            if has_parse_warning(item):
                return True
    elif isinstance(value, list):
        return any(has_parse_warning(item) for item in value)
    elif isinstance(value, str):
        return any(keyword in value for keyword in warning_keywords)
    return False


def find_top_value_by_suffix(data, suffix):
    for key, value in data.items():
        if isinstance(key, str) and key.endswith(suffix):
            return key, value
    return "", ""


def find_body_value_by_name(body_obj, name):
    if not isinstance(body_obj, dict):
        return ""
    for key, value in body_obj.items():
        if isinstance(key, str) and key.endswith(name):
            return value
    return ""


def build_location_pid_maps(body_obj):
    extra_obj = body_obj.get("附加信息对象", {}) if isinstance(body_obj, dict) else {}
    items = extra_obj.get("附加信息列表", []) if isinstance(extra_obj, dict) else []
    normal_map = {}
    e6_map = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = None
        for key, value in item.items():
            if isinstance(key, str) and key.endswith("附加信息ID"):
                item_id = value
                break
        if item_id == 0xE6:
            e6_obj = item.get("E6私有协议对象", {})
            for klv_item in e6_obj.get("KLV列表", []):
                if not isinstance(klv_item, dict):
                    continue
                pid = None
                for key, value in klv_item.items():
                    if isinstance(key, str) and key.endswith("PID"):
                        pid = value
                        break
                if pid is not None:
                    e6_map[pid] = klv_item.get("单元格值", klv_item.get("解析值", ""))
        elif item_id is not None:
            normal_map[item_id] = item.get("单元格值", "")
    return normal_map, e6_map


def build_sheet1_row(index, raw_hex, protocol, parsed=None, error_text=""):
    if parsed is None:
        return [
            index,
            "",
            "",
            "",
            "JT/T 808-2019" if normalize_protocol(protocol) == "2019" else "JT/T 808-2013",
            "",
            "",
            "",
            "",
            f"解析失败：{error_text}",
            "",
            "",
            raw_hex,
        ]

    msg_id_key, msg_id = find_top_value_by_suffix(parsed, "消息Id")
    phone_key, phone = find_top_value_by_suffix(parsed, "终端手机号")
    serial_key, serial = find_top_value_by_suffix(parsed, "消息流水号")
    checksum_key, checksum = find_top_value_by_suffix(parsed, "校验码")
    prop_obj = parsed.get("消息体属性对象", {})
    body_obj = parsed.get("数据体对象", {})

    msg_id_text = f"0x{msg_id:04X}" if isinstance(msg_id, int) else ""
    checksum_text = f"0x{checksum:02X}" if isinstance(checksum, int) else str(checksum or "")
    prop_text = json.dumps(prop_obj, ensure_ascii=False, separators=(",", ":"))
    body_text = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))

    return [
        index,
        "7E" if parsed.get("[7E]开始") == 126 else "",
        msg_id_text,
        parsed.get("消息名称", ""),
        parsed.get("解析标准", "JT/T 808-2019" if normalize_protocol(protocol) == "2019" else "JT/T 808-2013"),
        prop_text,
        prop_obj.get("[bit10~bit12]数据加密", ""),
        phone,
        serial,
        body_text,
        checksum_text,
        "7E" if parsed.get("[7E]结束") == 126 else "",
        raw_hex,
    ]


def default_location_pid_columns():
    return (
        [("normal", pid) for pid in LOCATION_EXTRA_PID_COLUMNS]
        + [("e6", pid) for pid in LOCATION_E6_PID_COLUMNS]
    )


def ordered_location_pid_columns(normal_pids=None, e6_pids=None):
    normal_pid_set = set(normal_pids or [])
    e6_pid_set = set(e6_pids or [])

    normal_columns = list(LOCATION_EXTRA_PID_COLUMNS)
    normal_columns.extend(sorted(pid for pid in normal_pid_set if pid not in normal_columns))

    e6_columns = sorted(set(LOCATION_E6_PID_COLUMNS) | e6_pid_set)
    return [("normal", pid) for pid in normal_columns] + [("e6", pid) for pid in e6_columns]


def build_location_row(parsed, location_pid_columns=None):
    body_obj = parsed.get("数据体对象", {})
    normal_pid_map, e6_pid_map = build_location_pid_maps(body_obj)
    status_obj = body_obj.get("状态对象", {})
    if location_pid_columns is None:
        location_pid_columns = default_location_pid_columns()

    row = [
        find_body_value_by_name(body_obj, "纬度"),
        find_body_value_by_name(body_obj, "经度"),
        find_body_value_by_name(body_obj, "高程(m)"),
        find_body_value_by_name(body_obj, "速度(km/h)"),
        find_body_value_by_name(body_obj, "方向"),
        find_body_value_by_name(body_obj, "时间"),
        status_text_for_excel(status_obj, 0),
        status_text_for_excel(status_obj, 1),
    ]
    for source, pid in location_pid_columns:
        value_map = e6_pid_map if source == "e6" else normal_pid_map
        row.append(value_map.get(pid, "N/A"))
    return row


def format_0f3b_csv_header(code, name, unit):
    suffix = f"({unit})" if unit else ""
    return f"{code} {name}{suffix}"


def f3b_sheet_headers():
    fixed_headers = [
        "序号", "消息ID", "消息名称", "解析标准", "手机号", "消息流水号",
        "采集频率", "压缩标志", "保留字段", "压缩内容长度", "解压后长度",
        "当日里程(km)", "仪表总里程(km)", "ECU总里程(km)",
        "当日油耗(L)", "仪表总油耗(L)", "ECU总油耗(L)", "内容行数",
        "CSV行号",
    ]
    dynamic_headers = [
        format_0f3b_csv_header(code, name, unit)
        for code, name, unit in F3B_CSV_COLUMNS
    ]
    return fixed_headers + dynamic_headers + ["其他CSV字段JSON"]


def find_object_value_by_suffix(obj, suffix):
    if not isinstance(obj, dict):
        return ""
    for key, value in obj.items():
        if isinstance(key, str) and key.endswith(suffix):
            return value
    return ""


def build_0f3b_rows(index, parsed, raw_hex, protocol):
    msg_id = find_top_value_by_suffix(parsed, "消息Id")[1]
    phone = find_top_value_by_suffix(parsed, "终端手机号")[1]
    serial = find_top_value_by_suffix(parsed, "消息流水号")[1]
    body_obj = parsed.get("数据体对象", {})
    summary = body_obj.get("汇总对象", {}) if isinstance(body_obj, dict) else {}
    detail_rows = body_obj.get("CSV明细列表", []) if isinstance(body_obj, dict) else []
    if not detail_rows:
        detail_rows = [{"CSV行号": "", "字段值对象": {}, "未知字段对象": {}}]

    base = [
        index,
        f"0x{msg_id:04X}" if isinstance(msg_id, int) else "",
        parsed.get("消息名称", ""),
        parsed.get("解析标准", "JT/T 808-2019" if normalize_protocol(protocol) == "2019" else "JT/T 808-2013"),
        phone,
        serial,
        find_object_value_by_suffix(body_obj, "采集频率"),
        json.dumps(body_obj.get("压缩标志对象", {}), ensure_ascii=False, separators=(",", ":")),
        find_object_value_by_suffix(body_obj, "保留字段"),
        find_object_value_by_suffix(body_obj, "内容长度"),
        body_obj.get("解压后长度", "") if isinstance(body_obj, dict) else "",
        summary.get("当日里程(km)", ""),
        summary.get("仪表总里程(km)", ""),
        summary.get("ECU总里程(km)", ""),
        summary.get("当日油耗(L)", ""),
        summary.get("仪表总油耗(L)", ""),
        summary.get("ECU总油耗(L)", ""),
        summary.get("内容行数", ""),
    ]

    rows = []
    for detail in detail_rows:
        values = detail.get("字段值对象", {}) if isinstance(detail, dict) else {}
        unknown = detail.get("未知字段对象", {}) if isinstance(detail, dict) else {}
        rows.append(
            base
            + [detail.get("CSV行号", "") if isinstance(detail, dict) else ""]
            + [values.get(code, "N/A") for code, _name, _unit in F3B_CSV_COLUMNS]
            + [json.dumps(unknown, ensure_ascii=False, separators=(",", ":")) if unknown else ""]
        )
    return rows


def autofit_worksheet(ws, max_width=80):
    for column_cells in ws.columns:
        column_letter = column_cells[0].column_letter
        width = 10
        for cell in column_cells:
            if cell.value is not None:
                width = max(width, min(max_width, len(str(cell.value)) + 2))
        ws.column_dimensions[column_letter].width = width


def format_pid_header(pid):
    names = {
        0x01: "里程",
        0x02: "油量",
        0x07: "新能源动力电池包电量SOC",
        0x30: "信号",
        0x31: "卫星数",
        0x08: "总油耗",
        0x14: "平均油耗",
        0x15: "瞬时油耗",
    }
    suffix = names.get(pid)
    return f"0x{pid:02X} {suffix}" if suffix else f"0x{pid:02X}"


def format_pid_excel_header(pid):
    return f"0x{pid:02X}"


def ensure_location_pid_columns(ws, location_pid_columns, normal_pid_map, e6_pid_map, styles):
    seen = set(location_pid_columns)
    for source, pid_map in (("normal", normal_pid_map), ("e6", e6_pid_map)):
        for pid in pid_map:
            key = (source, pid)
            if key in seen:
                continue
            location_pid_columns.append(key)
            seen.add(key)

            column_index = len(LOCATION_BASE_HEADERS) + len(location_pid_columns)
            header_cell = ws.cell(row=1, column=column_index, value=format_pid_excel_header(pid))
            header_cell.fill = styles["header_fill"]
            header_cell.font = styles["header_font"]
            header_cell.alignment = styles["header_alignment"]

            for row_index in range(2, ws.max_row + 1):
                cell = ws.cell(row=row_index, column=column_index, value="N/A")
                cell.alignment = styles["wrap_alignment"]
                if source == "e6":
                    cell.fill = styles["e6_fill"]


def apply_location_e6_fill(ws, row_index, location_pid_columns, e6_fill):
    for offset, (source, _pid) in enumerate(location_pid_columns, start=len(LOCATION_BASE_HEADERS) + 1):
        if source == "e6":
            ws.cell(row=row_index, column=offset).fill = e6_fill


def count_zipsend_frames(input_path):
    total = 0
    with open(input_path, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            if extract_zipsend_hex(line):
                total += 1
    return total


def report_batch_progress(progress_callback, stage, **payload):
    if progress_callback:
        progress_callback({"stage": stage, **payload})


def batch_parse_zipsend_file(input_path, output_path, protocol="2013", progress_callback=None):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise ParseError("缺少 openpyxl 库，无法生成 Excel。请先安装 openpyxl。") from exc

    report_batch_progress(progress_callback, "counting", current=0, total=0)
    total_count = count_zipsend_frames(input_path)
    report_batch_progress(progress_callback, "start", current=0, total=total_count)

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "sheet1"
    ws2 = wb.create_sheet("location")
    ws3 = wb.create_sheet("sheet3")

    sheet1_headers = [
        "序号", "消息头", "消息ID", "消息名称", "解析标准", "消息体属性", "数据加密",
        "手机号", "消息流水号", "消息体对象", "校验码", "消息尾", "完整HEX数据",
    ]
    location_pid_columns = ordered_location_pid_columns()
    location_headers = LOCATION_BASE_HEADERS + [format_pid_excel_header(pid) for _source, pid in location_pid_columns]
    ws1.append(sheet1_headers)
    ws2.append(location_headers)
    sheet3_headers = f3b_sheet_headers()
    ws3.append(sheet3_headers)
    sheet3_csv_row_col = sheet3_headers.index("CSV行号") + 1

    header_fill = PatternFill("solid", fgColor="D9EAF7")
    error_fill = PatternFill("solid", fgColor="FFC7CE")
    e6_fill = PatternFill("solid", fgColor="DDEBF7")
    csv_row_fill = PatternFill("solid", fgColor="FFE699")
    f3b_block_fills = (
        PatternFill("solid", fgColor="EAF3F8"),
        PatternFill("solid", fgColor="FFF2CC"),
    )
    header_font = Font(bold=True)
    invalid_value_font = Font(color="C00000")
    wrap_alignment = Alignment(vertical="top", wrap_text=True)
    excel_styles = {
        "header_fill": header_fill,
        "header_font": header_font,
        "header_alignment": Alignment(horizontal="center", vertical="center"),
        "wrap_alignment": wrap_alignment,
        "e6_fill": e6_fill,
    }

    for ws in (ws1, ws2, ws3):
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
    ws3.cell(row=1, column=sheet3_csv_row_col).fill = csv_row_fill

    parsed_count = 0
    error_count = 0
    location_count = 0
    f3b_count = 0
    f3b_detail_count = 0
    location_records = []
    normal_location_pids = set()
    e6_location_pids = set()

    with open(input_path, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            raw_hex = extract_zipsend_hex(line)
            if not raw_hex:
                continue

            parsed_count += 1
            row_has_error = False
            try:
                parsed = parse_808_hex(raw_hex, protocol)
                if "解析结果列表" in parsed:
                    parsed = parsed["解析结果列表"][0]
                row_has_error = has_parse_warning(parsed) or not parsed.get("校验结果对象", {}).get("是否通过", False)
                row = build_sheet1_row(parsed_count, raw_hex, protocol, parsed=parsed)
                msg_id = find_top_value_by_suffix(parsed, "消息Id")[1]
                if msg_id == 0x0200:
                    body_obj = parsed.get("数据体对象", {})
                    normal_pid_map, e6_pid_map = build_location_pid_maps(body_obj)
                    normal_location_pids.update(normal_pid_map)
                    e6_location_pids.update(e6_pid_map)
                    location_records.append(parsed)
                    location_count += 1
                elif msg_id == 0x0F3B:
                    f3b_rows = build_0f3b_rows(parsed_count, parsed, raw_hex, protocol)
                    block_fill = f3b_block_fills[f3b_count % len(f3b_block_fills)]
                    for f3b_row in f3b_rows:
                        ws3.append(f3b_row)
                        for cell in ws3[ws3.max_row]:
                            cell.fill = block_fill
                        f3b_detail_count += 1
                    f3b_count += 1
            except Exception as exc:
                row_has_error = True
                row = build_sheet1_row(parsed_count, raw_hex, protocol, error_text=str(exc))

            ws1.append(row)
            current_row = ws1.max_row
            for cell in ws1[current_row]:
                cell.alignment = wrap_alignment
                if row_has_error:
                    cell.fill = error_fill
            if row_has_error:
                error_count += 1
            report_batch_progress(
                progress_callback,
                "parsing",
                current=parsed_count,
                total=total_count,
                error_count=error_count,
                location_count=location_count,
                f3b_count=f3b_count,
                f3b_detail_count=f3b_detail_count,
            )

    location_pid_columns = ordered_location_pid_columns(normal_location_pids, e6_location_pids)
    location_headers = LOCATION_BASE_HEADERS + [format_pid_excel_header(pid) for _source, pid in location_pid_columns]
    for column_index, header in enumerate(location_headers, start=1):
        cell = ws2.cell(row=1, column=column_index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for parsed in location_records:
        ws2.append(build_location_row(parsed, location_pid_columns))
        apply_location_e6_fill(ws2, ws2.max_row, location_pid_columns, e6_fill)

    report_batch_progress(progress_callback, "formatting", current=parsed_count, total=total_count)
    for ws in (ws1, ws2, ws3):
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap_alignment
        autofit_worksheet(ws)
    for row in ws3.iter_rows(min_row=2):
        for cell in row:
            if cell.column == sheet3_csv_row_col:
                cell.fill = csv_row_fill
            if is_invalid_ff_text(cell.value):
                cell.font = invalid_value_font
    ws3.column_dimensions["C"].width = 14

    report_batch_progress(progress_callback, "saving", current=parsed_count, total=total_count)
    wb.save(output_path)
    return {
        "input_path": input_path,
        "output_path": output_path,
        "parsed_count": parsed_count,
        "error_count": error_count,
        "location_count": location_count,
        "f3b_count": f3b_count,
        "f3b_detail_count": f3b_detail_count,
    }


def value_to_key_text(value):
    if value is None or value == "":
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def append_key_line(lines, label, value, indent=0):
    lines.append(f"{'  ' * indent}{label}: {value_to_key_text(value)}")


def find_body_raw_hex(body_obj):
    if not isinstance(body_obj, dict):
        return ""
    for key, value in body_obj.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key in ("解析提示", "解析错误", "说明"):
            continue
        if re.fullmatch(r"[0-9A-Fa-f]*", value) and len(value) % 2 == 0:
            return value.upper()
    return ""


def append_body_raw_hex(lines, body_obj, indent=0):
    raw_hex = find_body_raw_hex(body_obj)
    if raw_hex:
        append_key_line(lines, "消息体原始HEX", raw_hex, indent)


def append_f3b_detail_key_lines(lines, detail):
    row_no = detail.get("CSV行号", "")
    append_key_line(lines, "CSV行号", row_no, 1)
    values = detail.get("字段值对象", {}) if isinstance(detail, dict) else {}
    invalid_fields = []
    for code, name, _unit in F3B_CSV_COLUMNS:
        value = values.get(code, "")
        if value in ("", None, "N/A"):
            continue
        label = f"{code} {name}"
        text = value_to_key_text(value)
        if value == "无效":
            invalid_fields.append(label)
        if code == "516097" and "\n" in text:
            lines.append(f"  {label}:")
            for item in text.splitlines():
                lines.append(f"    {item}")
        else:
            append_key_line(lines, label, text, 1)
    if invalid_fields:
        lines.append("  无效字段:")
        for label in invalid_fields:
            lines.append(f"    {label}")


def build_0f3b_key_info(lines, body_obj):
    append_key_line(lines, "消息体", "压缩数据上报")
    append_body_raw_hex(lines, body_obj)
    append_key_line(lines, "采集频率", find_object_value_by_suffix(body_obj, "采集频率"))
    append_key_line(lines, "采集周期", find_object_value_by_suffix(body_obj, "采集周期"))
    flag_obj = body_obj.get("压缩标志对象", {})
    if isinstance(flag_obj, dict):
        for key, value in flag_obj.items():
            append_key_line(lines, key, value)
    append_key_line(lines, "内容长度", find_object_value_by_suffix(body_obj, "内容长度"))
    append_key_line(lines, "内容长度说明", body_obj.get("内容长度说明", ""))
    append_key_line(lines, "解压后长度", body_obj.get("解压后长度", ""))

    summary = body_obj.get("汇总对象", {})
    if isinstance(summary, dict):
        lines.append("")
        lines.append("汇总信息")
        for key in (
            "当日里程(km)", "仪表总里程(km)", "ECU总里程(km)",
            "当日油耗(L)", "仪表总油耗(L)", "ECU总油耗(L)", "内容行数",
        ):
            append_key_line(lines, key, summary.get(key, "N/A"), 1)

    details = body_obj.get("CSV明细列表", [])
    if details:
        lines.append("")
        lines.append("CSV明细")
        for detail in details:
            append_f3b_detail_key_lines(lines, detail)
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()


def build_0f42_key_info(lines, body_obj):
    append_key_line(lines, "消息体", "查询TBOX信息指令")
    append_body_raw_hex(lines, body_obj)
    records = body_obj.get("TBOX子消息列表", []) if isinstance(body_obj, dict) else []
    append_key_line(lines, "TBOX子消息数量", len(records))
    for record in records:
        lines.append("")
        append_key_line(lines, "子消息序号", record.get("序号", ""), 1)
        sub_key, sub_name = find_top_value_by_suffix(record, "子消息ID")
        serial_key, serial = find_top_value_by_suffix(record, "流水号")
        len_key, content_len = find_top_value_by_suffix(record, "内容长度")
        append_key_line(lines, "流水号", serial, 1)
        append_key_line(lines, "子消息ID", f"{sub_key[:4]} {sub_name}" if sub_key else sub_name, 1)
        append_key_line(lines, "内容长度", content_len, 1)
        attr_obj = record.get("终端设备属性对象", {})
        field_obj = attr_obj.get("字段对象", {}) if isinstance(attr_obj, dict) else {}
        if field_obj:
            for key, value in field_obj.items():
                append_key_line(lines, key, value, 1)
        elif "配置结果" in "".join(record.keys()):
            result_key, result_value = find_top_value_by_suffix(record, "配置结果")
            append_key_line(lines, "配置结果", result_value, 1)
        elif "海外模式" in "".join(record.keys()):
            mode_key, mode_value = find_top_value_by_suffix(record, "海外模式")
            country_key, country_value = find_top_value_by_suffix(record, "国别编码")
            append_key_line(lines, "海外模式", mode_value, 1)
            append_key_line(lines, "国别编码", country_value, 1)


def build_circular_area_key_info(lines, body_obj):
    append_key_line(lines, "消息体", "设置圆形区域")
    append_body_raw_hex(lines, body_obj)
    setting_key, setting_value = find_top_value_by_suffix(body_obj, "设置属性")
    count_key, count_value = find_top_value_by_suffix(body_obj, "区域总数")
    append_key_line(lines, "设置属性", setting_value)
    append_key_line(lines, "区域总数", count_value)

    areas = body_obj.get("圆形区域列表", []) if isinstance(body_obj, dict) else []
    for area in areas:
        if not isinstance(area, dict):
            continue
        lines.append("")
        append_key_line(lines, f"区域{area.get('序号', '')}", "")
        append_key_line(lines, "区域ID", find_object_value_by_suffix(area, "区域ID"), 1)
        attr_obj = area.get("区域属性对象", {})
        if isinstance(attr_obj, dict):
            append_key_line(lines, "生效属性", attr_obj.get("生效属性", []), 1)
        append_key_line(lines, "中心点纬度", find_object_value_by_suffix(area, "中心点纬度"), 1)
        append_key_line(lines, "中心点经度", find_object_value_by_suffix(area, "中心点经度"), 1)
        append_key_line(lines, "半径(m)", find_object_value_by_suffix(area, "半径(m)"), 1)
        for key, value in area.items():
            if any(marker in str(key) for marker in ("起始时间", "结束时间", "最高速度", "超速持续时间")):
                append_key_line(lines, key, value, 1)


def build_rectangular_area_key_info(lines, body_obj):
    append_key_line(lines, "消息体", "设置矩形区域")
    append_body_raw_hex(lines, body_obj)
    append_key_line(lines, "设置属性", find_top_value_by_suffix(body_obj, "设置属性")[1])
    append_key_line(lines, "区域总数", find_top_value_by_suffix(body_obj, "区域总数")[1])
    for area in body_obj.get("矩形区域列表", []):
        lines.append("")
        append_key_line(lines, f"区域{area.get('序号', '')}", "")
        append_key_line(lines, "区域ID", find_object_value_by_suffix(area, "区域ID"), 1)
        append_key_line(lines, "生效属性", area.get("区域属性对象", {}).get("生效属性", []), 1)
        for suffix in ("左上点纬度", "左上点经度", "右下点纬度", "右下点经度"):
            append_key_line(lines, suffix, find_object_value_by_suffix(area, suffix), 1)
        for key, value in area.items():
            if any(marker in str(key) for marker in ("起始时间", "结束时间", "最高速度", "超速持续时间")):
                append_key_line(lines, key, value, 1)


def build_polygon_area_key_info(lines, body_obj):
    append_key_line(lines, "消息体", "设置多边形区域")
    append_body_raw_hex(lines, body_obj)
    area = body_obj.get("区域对象", {}) if isinstance(body_obj, dict) else {}
    if not isinstance(area, dict):
        return
    append_key_line(lines, "区域ID", find_object_value_by_suffix(area, "区域ID"))
    append_key_line(lines, "生效属性", area.get("区域属性对象", {}).get("生效属性", []))
    for key, value in area.items():
        if any(marker in str(key) for marker in ("起始时间", "结束时间", "最高速度", "超速持续时间", "区域总顶点数")):
            append_key_line(lines, key, value)
    vertices = area.get("顶点列表", [])
    if vertices:
        lines.append("顶点列表")
        for vertex in vertices:
            append_key_line(
                lines,
                f"顶点{vertex.get('序号', '')}",
                f"{find_object_value_by_suffix(vertex, '顶点纬度')}, "
                f"{find_object_value_by_suffix(vertex, '顶点经度')}",
                1,
            )


def build_terminal_parameter_key_info(lines, body_obj):
    params = body_obj.get("参数列表", []) if isinstance(body_obj, dict) else []
    if not params:
        return False

    append_key_line(lines, "参数数量", body_obj.get("[07]应答参数个数", body_obj.get("[01]参数总数", len(params))))
    for index, item in enumerate(params, start=1):
        if not isinstance(item, dict):
            continue
        param_id = find_top_value_by_suffix(item, "参数ID")[1]
        param_id_text = f"{param_id:08X}" if isinstance(param_id, int) else str(param_id)
        name = item.get("参数名称", f"未知参数(0x{param_id_text})")
        value_text = item.get("参数值文本", item.get("参数值", "N/A"))

        lines.append("")
        append_key_line(lines, f"参数{index:02d} [{param_id_text}] {name}", value_text, 1)
    return True


def build_location_key_info(lines, body_obj):
    append_key_line(lines, "消息体", "位置信息汇报")
    append_body_raw_hex(lines, body_obj)
    for name in ("纬度", "经度", "高程(m)", "速度(km/h)", "方向", "时间"):
        append_key_line(lines, name, find_body_value_by_name(body_obj, name))
    status_obj = body_obj.get("状态对象", {})
    if isinstance(status_obj, dict):
        append_key_line(lines, "点火状态", status_text_for_excel(status_obj, 0))
        append_key_line(lines, "定位", status_text_for_excel(status_obj, 1))

    extra_obj = body_obj.get("附加信息对象", {}) if isinstance(body_obj, dict) else {}
    items = extra_obj.get("附加信息列表", []) if isinstance(extra_obj, dict) else []
    normal_items = []
    e6_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = find_top_value_by_suffix(item, "附加信息ID")[1]
        if item_id == 0xE6:
            e6_items.append(item)
        else:
            normal_items.append(item)

    if normal_items:
        lines.append("")
        lines.append("附加信息")
        for item in normal_items:
            item_id = find_top_value_by_suffix(item, "附加信息ID")[1]
            value = item.get("单元格值", item.get("原始值", "N/A"))
            append_key_line(lines, format_pid_header(item_id) if isinstance(item_id, int) else "未知附加信息", value, 1)

    if e6_items:
        lines.append("")
        lines.append("E6私有协议")
        for item in e6_items:
            e6_obj = item.get("E6私有协议对象", {})
            klv_items = e6_obj.get("KLV列表", []) if isinstance(e6_obj, dict) else []
            append_key_line(lines, "E6 KLV数量", len(klv_items), 1)
            for klv_item in klv_items:
                if not isinstance(klv_item, dict):
                    continue
                pid = find_top_value_by_suffix(klv_item, "PID")[1]
                pid_text = f"0x{pid:02X}" if isinstance(pid, int) and pid <= 0xFF else f"0x{pid:04X}" if isinstance(pid, int) else "Unknown"
                desc = klv_item.get("字段描述", "")
                value = klv_item.get("单元格值", klv_item.get("解析值", "N/A"))
                label = f"{pid_text} {desc}".strip()
                append_key_line(lines, label, value, 1)


def build_generic_body_key_info(lines, body_obj):
    if not isinstance(body_obj, dict):
        append_key_line(lines, "消息体", body_obj)
        return
    append_body_raw_hex(lines, body_obj)
    if build_terminal_parameter_key_info(lines, body_obj):
        return
    for key, value in body_obj.items():
        if isinstance(value, (dict, list)):
            continue
        if isinstance(key, str) and any(marker in key for marker in ("原始", "HEX")):
            continue
        append_key_line(lines, key, value)


def build_key_info_for_frame(parsed):
    lines = []
    msg_id_key, msg_id = find_top_value_by_suffix(parsed, "消息Id")
    phone_key, phone = find_top_value_by_suffix(parsed, "终端手机号")
    serial_key, serial = find_top_value_by_suffix(parsed, "消息流水号")
    msg_id_text = f"0x{msg_id:04X}" if isinstance(msg_id, int) else value_to_key_text(msg_id)

    append_key_line(lines, "消息ID", msg_id_text)
    append_key_line(lines, "消息名称", parsed.get("消息名称", ""))
    append_key_line(lines, "解析标准", parsed.get("解析标准", ""))
    append_key_line(lines, "手机号", phone)
    append_key_line(lines, "消息流水号", serial)

    prop_obj = parsed.get("消息体属性对象", {})
    if isinstance(prop_obj, dict):
        append_key_line(lines, "消息体属性HEX", find_object_value_by_suffix(prop_obj, "消息体属性HEX"))
        append_key_line(lines, "消息体属性二进制", find_object_value_by_suffix(prop_obj, "消息体属性二进制"))
        append_key_line(lines, "数据加密", prop_obj.get("[bit10~bit12]数据加密", ""))
        append_key_line(lines, "消息体长度", prop_obj.get("[bit0~bit9]消息体长度", ""))

    body_obj = parsed.get("数据体对象", {})
    lines.append("")
    if msg_id == 0x0F3B and isinstance(body_obj, dict):
        build_0f3b_key_info(lines, body_obj)
    elif msg_id == 0x0F42 and isinstance(body_obj, dict):
        build_0f42_key_info(lines, body_obj)
    elif msg_id == 0x8600 and isinstance(body_obj, dict):
        build_circular_area_key_info(lines, body_obj)
    elif msg_id == 0x8602 and isinstance(body_obj, dict):
        build_rectangular_area_key_info(lines, body_obj)
    elif msg_id == 0x8604 and isinstance(body_obj, dict):
        build_polygon_area_key_info(lines, body_obj)
    elif msg_id == 0x0200 and isinstance(body_obj, dict):
        build_location_key_info(lines, body_obj)
    else:
        build_generic_body_key_info(lines, body_obj)

    checksum_obj = parsed.get("校验结果对象", {})
    if isinstance(checksum_obj, dict):
        lines.append("")
        append_key_line(lines, "校验结果", "通过" if checksum_obj.get("是否通过") else "不通过")

    return "\n".join(lines).strip()


def build_key_info(parsed):
    if "解析结果列表" not in parsed:
        return build_key_info_for_frame(parsed)
    lines = [
        f"帧数量: {parsed.get('帧数量', 0)}",
        "",
    ]
    for index, frame in enumerate(parsed.get("解析结果列表", []), start=1):
        lines.append(f"第 {index} 帧")
        lines.append(build_key_info_for_frame(frame))
        lines.append("")
    return "\n".join(lines).strip()


class BatchProgressDialog:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("批量解析进度")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.ignore_close)

        frame = ttk.Frame(self.window, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="正在准备批量解析...")
        self.detail_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status_var, width=46).pack(fill=tk.X)
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=360)
        self.progress.pack(fill=tk.X, pady=(12, 8))
        ttk.Label(frame, textvariable=self.detail_var).pack(fill=tk.X)

        self.progress.start(12)
        self.center_on_parent(parent)

    def center_on_parent(self, parent):
        self.window.update_idletasks()
        parent.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        self.window.geometry(f"+{x}+{y}")

    def ignore_close(self):
        self.status_var.set("正在解析中，请等待完成...")

    def set_counting(self):
        self.status_var.set("正在扫描文件，统计 AT+ZIPSEND 数据...")
        self.detail_var.set("")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

    def set_progress(self, current, total, detail=""):
        total = max(int(total or 0), 1)
        current = min(int(current or 0), total)
        if str(self.progress.cget("mode")) != "determinate":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=total)
        self.progress.configure(maximum=total, value=current)
        percent = current * 100 / total if total else 0
        self.status_var.set(f"正在解析：{current}/{total}（{percent:.1f}%）")
        self.detail_var.set(detail)

    def set_status(self, text):
        self.status_var.set(text)

    def close(self):
        try:
            self.progress.stop()
            self.window.destroy()
        except tk.TclError:
            pass


class JT808ParserApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GT117-YK-808 标准808协议解析工具-Mangetic-260928")
        icon_path = resource_path(ICON_FILENAME)
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(default=icon_path)
            except tk.TclError:
                pass
        self.root.geometry("1060x720")
        self.root.minsize(860, 560)
        self.auto_parse_job = None
        self.batch_parse_running = False
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(main)
        toolbar.pack(fill=tk.X, pady=(8, 8))

        ttk.Label(toolbar, text="协议标准").pack(side=tk.LEFT, padx=(0, 4))
        self.protocol_var = tk.StringVar(value="JT/T 808-2013")
        self.protocol_combo = ttk.Combobox(
            toolbar,
            textvariable=self.protocol_var,
            values=("JT/T 808-2013", "JT/T 808-2019"),
            state="readonly",
            width=16,
        )
        self.protocol_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.protocol_combo.bind("<<ComboboxSelected>>", lambda _event: self.parse_input())

        self.batch_button = ttk.Button(toolbar, text="批量解析EXCEL", command=self.batch_parse_file)
        self.batch_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="清空输入", command=self.clear_input).pack(side=tk.LEFT, padx=(0, 8))

        self.status_var = tk.StringVar(value="请在上方输入 808 协议 HEX 数据，输入后会自动解析。")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.LEFT, padx=(8, 0))

        input_frame = ttk.LabelFrame(main, text="输入 HEX")
        input_frame.pack(fill=tk.X, pady=(0, 8))

        self.input_text = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, font=("Consolas", 11), undo=True, height=6)
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.input_text.bind("<<Modified>>", self.on_input_modified)
        self.input_text.edit_modified(False)
        self.bind_text_shortcuts(self.input_text, allow_edit=True)

        panes = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        output_frame = ttk.LabelFrame(panes, text="解析结果 JSON")
        key_output_frame = ttk.LabelFrame(panes, text="解析结果 JSON-关键信息")
        panes.add(output_frame, weight=1)
        panes.add(key_output_frame, weight=1)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, font=("Consolas", 10), undo=True)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.output_text.tag_configure("error", foreground="#B00020", font=("Consolas", 10, "bold"))
        self.output_text.tag_configure("invalid", foreground="#B00020", font=("Consolas", 10, "bold"))
        self.output_text.tag_configure("hint", foreground="#7A4A00", font=("Consolas", 10))
        self.output_text.tag_configure("key", foreground="#1F5AA6", font=("Consolas", 10))
        self.bind_text_shortcuts(self.output_text, allow_edit=False)

        self.key_output_text = scrolledtext.ScrolledText(key_output_frame, wrap=tk.WORD, font=("Consolas", 10), undo=True)
        self.key_output_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.key_output_text.tag_configure("error", foreground="#B00020", font=("Consolas", 10, "bold"))
        self.key_output_text.tag_configure("invalid", foreground="#B00020", font=("Consolas", 10, "bold"))
        self.key_output_text.tag_configure("hint", foreground="#7A4A00", font=("Consolas", 10))
        self.key_output_text.tag_configure("key", foreground="#1F5AA6", font=("Consolas", 10))
        self.bind_text_shortcuts(self.key_output_text, allow_edit=False)

    def bind_text_shortcuts(self, widget, allow_edit=True):
        widget.bind("<Control-a>", lambda _event, current=widget: self.text_select_all(current))
        widget.bind("<Control-A>", lambda _event, current=widget: self.text_select_all(current))
        widget.bind("<Control-c>", lambda _event, current=widget: self.text_copy(current))
        widget.bind("<Control-C>", lambda _event, current=widget: self.text_copy(current))
        if allow_edit:
            widget.bind("<Control-x>", lambda _event, current=widget: self.text_cut(current))
            widget.bind("<Control-X>", lambda _event, current=widget: self.text_cut(current))
            widget.bind("<Control-v>", lambda _event, current=widget: self.text_paste(current))
            widget.bind("<Control-V>", lambda _event, current=widget: self.text_paste(current))
        widget.bind("<Button-3>", lambda event, current=widget, editable=allow_edit: self.show_text_menu(event, current, editable))

    def text_select_all(self, widget):
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
        return "break"

    def text_copy(self, widget):
        try:
            selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)
        return "break"

    def text_cut(self, widget):
        try:
            selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)
        widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        widget.edit_modified(True)
        return "break"

    def text_paste(self, widget):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        try:
            widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        widget.insert(tk.INSERT, text)
        widget.edit_modified(True)
        return "break"

    def show_text_menu(self, event, widget, allow_edit=True):
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="复制", command=lambda: self.text_copy(widget))
        if allow_edit:
            menu.add_command(label="剪切", command=lambda: self.text_cut(widget))
            menu.add_command(label="粘贴", command=lambda: self.text_paste(widget))
        menu.add_separator()
        menu.add_command(label="全选", command=lambda: self.text_select_all(widget))
        menu.tk_popup(event.x_root, event.y_root)

    def is_key_line(self, line):
        key_markers = (
            "消息名称",
            "消息体原始HEX",
            "解析标准",
            "消息体属性对象",
            "终端手机号",
            "消息流水号",
            "数据体对象",
            "校验结果对象",
            "压缩标志对象",
            "汇总对象",
            "字段原始值对象",
            "字段值对象",
            "终端设备属性对象",
            "TBOX子消息列表",
            "TBOX子消息数量",
            "JSON文本",
            "JSON对象",
            "字段对象",
            "内容HEX",
            "压缩数据HEX",
            "解压后HEX",
            "CSV明文",
            "CSV行号",
            "无效字段",
        )
        if any(marker in line for marker in key_markers):
            return True
        return bool(re.search(r'^\s*"\[[0-9A-Fa-f]+\][^"]+":', line))

    def is_invalid_line(self, line):
        stripped = line.strip().rstrip(",")
        if "无效字段" in stripped:
            return True
        return bool(re.search(r':\s*"?无效"?$', stripped))

    def show_text(self, widget, content):
        widget.delete("1.0", tk.END)
        error_keywords = ("解析失败", "未知错误", "解析错误", "解析提示", "数据长度不足", "无法匹配", "非法", "不足")
        warning_keywords = ("尝试记录", "建议")
        invalid_block = False
        for line in content.splitlines(True):
            stripped = line.strip()
            if not stripped:
                invalid_block = False
            if "无效字段" in stripped:
                invalid_block = True

            if any(keyword in line for keyword in error_keywords):
                widget.insert(tk.END, line, "error")
            elif invalid_block or self.is_invalid_line(line):
                widget.insert(tk.END, line, "invalid")
            elif any(keyword in line for keyword in warning_keywords):
                widget.insert(tk.END, line, "hint")
            elif self.is_key_line(line):
                widget.insert(tk.END, line, "key")
            else:
                widget.insert(tk.END, line)

    def show_output(self, content):
        self.show_text(self.output_text, content)

    def show_key_output(self, content):
        self.show_text(self.key_output_text, content)

    def on_input_modified(self, _event=None):
        if not self.input_text.edit_modified():
            return
        self.input_text.edit_modified(False)
        if self.auto_parse_job is not None:
            self.root.after_cancel(self.auto_parse_job)
        self.auto_parse_job = self.root.after(350, self.parse_input)

    def load_sample(self):
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert(tk.END, SAMPLE_HEX)
        self.parse_input()

    def clear_input(self):
        if self.auto_parse_job is not None:
            self.root.after_cancel(self.auto_parse_job)
            self.auto_parse_job = None
        self.input_text.delete("1.0", tk.END)
        self.input_text.edit_modified(False)
        self.output_text.delete("1.0", tk.END)
        self.key_output_text.delete("1.0", tk.END)
        self.status_var.set("已清空。")

    def parse_input(self):
        self.auto_parse_job = None
        source = self.input_text.get("1.0", tk.END)
        if not clean_hex_text(source):
            self.output_text.delete("1.0", tk.END)
            self.key_output_text.delete("1.0", tk.END)
            self.status_var.set("请在上方输入 808 协议 HEX 数据，输入后会自动解析。")
            return
        try:
            result = parse_808_hex(source, self.protocol_var.get())
            formatted = json.dumps(result, ensure_ascii=False, indent=2)
            self.show_output(formatted)
            self.show_key_output(build_key_info(result))
            if "解析提示" in formatted or "解析错误" in formatted or "数据长度不足" in formatted:
                self.status_var.set(f"解析完成，但存在红色提示；当前标准：{self.protocol_var.get()}。")
            else:
                self.status_var.set(f"解析完成，当前标准：{self.protocol_var.get()}。")
        except ParseError as exc:
            error_text = (
                f"解析失败：{exc}\n\n"
                f"当前选择标准：{self.protocol_var.get()}\n"
                "建议：如果该帧在另一个标准下能够解析，请切换顶部“协议标准”后重新解析。"
            )
            self.show_output(error_text)
            self.show_key_output(f"解析失败：{exc}")
            self.status_var.set("解析失败。")
        except Exception as exc:
            self.show_output(f"未知错误：{exc}")
            self.show_key_output(f"未知错误：{exc}")
            self.status_var.set("解析失败。")

    def copy_output(self):
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "当前没有可复制的解析结果。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status_var.set("解析结果已复制到剪贴板。")

    def batch_parse_file(self):
        if self.batch_parse_running:
            messagebox.showinfo("提示", "批量解析正在进行中，请等待完成。")
            return

        input_path = filedialog.askopenfilename(
            title="选择包含 AT+ZIPSEND 的日志文件",
            filetypes=[
                ("日志/文本文件", "*.txt *.log *.csv *.dat"),
                ("所有文件", "*.*"),
            ],
        )
        if not input_path:
            return

        input_stem = os.path.splitext(os.path.basename(input_path))[0]
        default_name = f"{input_stem}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
        output_path = filedialog.asksaveasfilename(
            title="保存解析结果 Excel",
            initialdir=os.path.dirname(input_path),
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
        )
        if not output_path:
            return

        protocol = self.protocol_var.get()
        progress_dialog = BatchProgressDialog(self.root)
        progress_queue = queue.Queue()
        self.batch_parse_running = True
        self.batch_button.state(["disabled"])
        self.status_var.set("正在批量解析文件，请稍等...")

        def progress_callback(payload):
            progress_queue.put(("progress", payload))

        def worker():
            try:
                summary = batch_parse_zipsend_file(input_path, output_path, protocol, progress_callback=progress_callback)
                progress_queue.put(("done", summary))
            except Exception as exc:
                progress_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.poll_batch_parse_queue(progress_queue, progress_dialog, protocol)

    def update_batch_progress_dialog(self, progress_dialog, payload):
        stage = payload.get("stage")
        if stage == "counting":
            progress_dialog.set_counting()
            return

        current = payload.get("current", 0)
        total = payload.get("total", 0)
        if stage == "start" and not total:
            progress_dialog.set_status("未找到 AT+ZIPSEND 数据，正在生成空 Excel...")
            return
        if stage == "formatting":
            progress_dialog.set_status("正在整理 Excel 格式...")
            return
        if stage == "saving":
            progress_dialog.set_status("正在保存 Excel 文件...")
            return

        detail = (
            f"错误 {payload.get('error_count', 0)} 条，"
            f"0200位置 {payload.get('location_count', 0)} 条，"
            f"0F3B {payload.get('f3b_count', 0)} 条"
        )
        progress_dialog.set_progress(current, total, detail)

    def finish_batch_parse(self, progress_dialog):
        self.batch_parse_running = False
        self.batch_button.state(["!disabled"])
        progress_dialog.close()

    def show_batch_parse_success(self, summary, protocol):
        self.status_var.set(
            f"批量解析完成：{summary['parsed_count']} 条，错误 {summary['error_count']} 条，"
            f"0200位置 {summary['location_count']} 条，0F3B {summary['f3b_count']} 条。"
        )
        summary_text = (
            "批量解析完成\n"
            f"当前标准：{protocol}\n"
            f"输入文件：{summary['input_path']}\n"
            f"输出文件：{summary['output_path']}\n"
            f"解析条数：{summary['parsed_count']}\n"
            f"错误条数：{summary['error_count']}\n"
            f"0200位置条数：{summary['location_count']}\n"
            f"0F3B条数：{summary['f3b_count']}\n"
            f"sheet3明细行数：{summary['f3b_detail_count']}"
        )
        self.show_output(summary_text)
        self.show_key_output(summary_text)
        messagebox.showinfo(
            "批量解析完成",
            f"已生成 Excel：\n{summary['output_path']}\n\n"
            f"解析条数：{summary['parsed_count']}\n"
            f"错误条数：{summary['error_count']}\n"
            f"0200位置条数：{summary['location_count']}\n"
            f"0F3B条数：{summary['f3b_count']}\n"
            f"sheet3明细行数：{summary['f3b_detail_count']}",
        )

    def poll_batch_parse_queue(self, progress_queue, progress_dialog, protocol):
        try:
            while True:
                kind, payload = progress_queue.get_nowait()
                if kind == "progress":
                    self.update_batch_progress_dialog(progress_dialog, payload)
                elif kind == "done":
                    self.finish_batch_parse(progress_dialog)
                    self.show_batch_parse_success(payload, protocol)
                    return
                elif kind == "error":
                    self.finish_batch_parse(progress_dialog)
                    self.show_output(f"解析失败：{payload}")
                    self.show_key_output(f"解析失败：{payload}")
                    self.status_var.set("批量解析失败。")
                    messagebox.showerror("批量解析失败", payload)
                    return
        except queue.Empty:
            pass

        self.root.after(100, lambda: self.poll_batch_parse_queue(progress_queue, progress_dialog, protocol))


def main():
    root = tk.Tk()
    app = JT808ParserApp(root)
    root.mainloop()
    return app


if __name__ == "__main__":
    main()
