#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JT/T 808 (高新兴瑞联808协议1.0) 参数设置/查询 调试工具

组成：
  1) TCP 服务端  —— 模拟平台，监听端口等设备连上来（808 里平台是服务端）
  2) HTTP 服务端 —— 提供网页界面 + SSE 实时日志

用法：
  python jt808_debugger.py                  # 默认 TCP 1808、网页 8080
  python jt808_debugger.py --tcp 1808 --http 8080
  python jt808_debugger.py --no-browser     # 不自动打开浏览器

只用 Python 标准库，无需 pip install。
"""

import argparse
import json
import os
import queue
import socket
import struct
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ============================================================================
# 808 协议常量
# ============================================================================
FRAME_FLAG = 0x7E
ESCAPE_FLAG = 0x7D
ESCAPE_FLAG_XOR = 0x02      # 0x7E 转义后
ESCAPE_XOR = 0x01           # 0x7D 转义后
HEADER_LEN = 12             # 消息头（无分包）
PHONE_LEN = 6               # 终端手机号 BCD[6]

MSG_TERMINAL_ACK = 0x0001       # 终端通用应答
MSG_HEARTBEAT = 0x0002          # 终端心跳
MSG_REGISTER = 0x0100           # 终端注册
MSG_AUTH = 0x0102               # 终端鉴权
MSG_QUERY_PARAM_ACK = 0x0104    # 查询终端参数应答
MSG_TERMINAL_PROPERTY_ACK = 0x0107  # 查询终端属性应答
MSG_UPGRADE_RESULT = 0x0108     # 终端升级结果通知
MSG_LOCATION = 0x0200           # 位置信息汇报

MSG_PLATFORM_ACK = 0x8001       # 平台通用应答
MSG_REGISTER_ACK = 0x8100       # 终端注册应答
MSG_SET_PARAM = 0x8103          # 设置终端参数
MSG_QUERY_PARAM = 0x8104        # 查询终端参数
MSG_TERMINAL_CONTROL = 0x8105   # 终端控制
MSG_QUERY_SPEC_PARAM = 0x8106   # 查询指定终端参数
MSG_QUERY_PROPERTY = 0x8107     # 查询终端属性

MSG_NAMES = {
    MSG_TERMINAL_ACK: "终端通用应答",
    MSG_HEARTBEAT: "终端心跳",
    MSG_REGISTER: "终端注册",
    MSG_AUTH: "终端鉴权",
    MSG_QUERY_PARAM_ACK: "查询终端参数应答",
    MSG_TERMINAL_PROPERTY_ACK: "查询终端属性应答",
    MSG_UPGRADE_RESULT: "终端升级结果通知",
    MSG_LOCATION: "位置信息汇报",
    MSG_PLATFORM_ACK: "平台通用应答",
    MSG_REGISTER_ACK: "终端注册应答",
    MSG_SET_PARAM: "设置终端参数",
    MSG_QUERY_PARAM: "查询终端参数",
    MSG_TERMINAL_CONTROL: "终端控制",
    MSG_QUERY_SPEC_PARAM: "查询指定终端参数",
    MSG_QUERY_PROPERTY: "查询终端属性",
}

ACK_RESULT_NAMES = {
    0: "成功/确认", 1: "失败", 2: "消息有误", 3: "不支持", 4: "报警处理确认",
}

REGISTER_RESULT_NAMES = {
    0: "成功", 1: "车辆已被注册", 2: "数据库中无该车辆",
    3: "终端已被注册", 4: "数据库中无该终端",
}

# ============================================================================
# 终端参数表（协议 8.9 表 12 / 8.9 表 102）
#   supported=False 表示当前 GD303 固件的 gsw_modem_validate_set_param_item()
#   未实现该 ID，下发会被整帧拒绝（回 MSG_ERR），界面上给出提示。
# ============================================================================
PARAMS = [
    {"id": 0x0001, "name": "终端心跳发送间隔",   "type": "u32", "unit": "s",
     "min": 10, "max": 3600, "default": 30,        "supported": True},
    {"id": 0x0010, "name": "主服务器 APN",       "type": "str", "maxlen": 31,
     "default": "CMNET",                           "supported": True},
    {"id": 0x0011, "name": "主服务器拨号用户名", "type": "str", "maxlen": 31,
     "default": "",                                "supported": True},
    {"id": 0x0012, "name": "主服务器拨号密码",   "type": "str", "maxlen": 31,
     "default": "",                                "supported": True},
    {"id": 0x0013, "name": "主服务器 IP/域名",   "type": "str", "maxlen": 63,
     "default": "xatst.richlinkcloud.com",         "supported": True,
     "hint": "不含端口，端口走 0x0018"},
    {"id": 0x0014, "name": "备份服务器 APN",     "type": "str", "maxlen": 31,
     "default": "",                                "supported": False},
    {"id": 0x0015, "name": "备份服务器拨号用户名", "type": "str", "maxlen": 31,
     "default": "",                                "supported": False},
    {"id": 0x0016, "name": "备份服务器拨号密码", "type": "str", "maxlen": 31,
     "default": "",                                "supported": False},
    {"id": 0x0017, "name": "备份服务器 IP/域名", "type": "str", "maxlen": 63,
     "default": "",                                "supported": False,
     "hint": "不含端口"},
    {"id": 0x0018, "name": "服务器 TCP 端口",    "type": "u32",
     "min": 1, "max": 65535, "default": 1808,      "supported": True},
    {"id": 0x0029, "name": "缺省时间汇报间隔",   "type": "u32", "unit": "s",
     "min": 8, "max": 1800, "default": 30,         "supported": True},
    {"id": 0x0083, "name": "机动车号牌/车辆标识", "type": "str", "maxlen": 20,
     "default": "",                                "supported": True},
    {"id": 0xF001, "name": "当前仪表里程基准",   "type": "u32", "unit": "0.1km",
     "min": 0, "max": 0xFFFFFFFF, "default": 0,    "supported": False},
]
PARAM_MAP = {p["id"]: p for p in PARAMS}

CONTROL_CMDS = [
    {"v": 1,    "name": "MCU 无线升级"},
    {"v": 2,    "name": "控制终端连接指定服务器"},
    {"v": 3,    "name": "终端关机"},
    {"v": 4,    "name": "终端复位"},
    {"v": 5,    "name": "终端恢复出厂设置"},
    {"v": 6,    "name": "关闭数据通信"},
    {"v": 7,    "name": "关闭所有无线通信"},
    {"v": 0xF0, "name": "Modem 无线升级"},
]


# ============================================================================
# BCD / 转义 / 校验
# ============================================================================
def phone_to_bcd(ident):
    """
    设备标识 -> 终端手机号 BCD[6]。
    协议 9.1 第 8 条：取 SIM 卡 IMSI（15 位）的后 12 位直接编码，不补位。
    也允许直接填 12 位。
    """
    digits = "".join(ch for ch in str(ident) if ch.isdigit())
    if len(digits) == 15:
        digits = digits[-12:]
    if len(digits) != 12:
        raise ValueError("设备标识需为 15 位 IMSI 或 12 位手机号，当前 %d 位数字" % len(digits))
    out = bytearray()
    for i in range(0, 12, 2):
        hi = int(digits[i])
        lo = int(digits[i + 1])
        out.append((hi << 4) | lo)
    return bytes(out)


def bcd_to_phone(data):
    """BCD[6] -> 12 位数字串"""
    return "".join("%X%X" % ((b >> 4) & 0x0F, b & 0x0F) for b in data)


def bcd_to_imei_tail(data):
    """BCD[7] -> 14 位终端ID（IMEI 后 14 位）"""
    return "".join("%X%X" % ((b >> 4) & 0x0F, b & 0x0F) for b in data)


def xor_checksum(data):
    cs = 0
    for b in data:
        cs ^= b
    return cs


def escape_data(data):
    """发送转义：0x7E -> 0x7D 0x02；0x7D -> 0x7D 0x01"""
    out = bytearray()
    for b in data:
        if b == FRAME_FLAG:
            out += bytes([ESCAPE_FLAG, ESCAPE_FLAG_XOR])
        elif b == ESCAPE_FLAG:
            out += bytes([ESCAPE_FLAG, ESCAPE_XOR])
        else:
            out.append(b)
    return bytes(out)


def unescape_data(data):
    """接收还原，失败返回 None"""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == ESCAPE_FLAG:
            if i + 1 >= n:
                return None
            nxt = data[i + 1]
            if nxt == ESCAPE_FLAG_XOR:
                out.append(FRAME_FLAG)
            elif nxt == ESCAPE_XOR:
                out.append(ESCAPE_FLAG)
            else:
                return None
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


def to_hex(data, sep=" "):
    return sep.join("%02X" % b for b in data)


# ============================================================================
# 组包
# ============================================================================
class SeqCounter:
    """下行流水号，1~0xFFFF 循环"""

    def __init__(self):
        self._v = 0
        self._lock = threading.Lock()

    def next(self):
        with self._lock:
            self._v = (self._v % 0xFFFF) + 1
            return self._v

    def peek_next(self):
        with self._lock:
            return (self._v % 0xFFFF) + 1


SEQ = SeqCounter()


def build_frame(msg_id, phone_bcd, seq, body, encrypt=0, subpkg=0):
    """组完整帧：7E | 头 | 体 | 校验 | 7E"""
    if len(body) > 0x3FF:
        raise ValueError("消息体过长 %d > 1023" % len(body))
    prop = (len(body) & 0x3FF) | ((encrypt & 0x07) << 10)
    if subpkg > 0:
        prop |= (1 << 13)
    header = struct.pack(">HH", msg_id, prop) + phone_bcd + struct.pack(">H", seq & 0xFFFF)
    raw = header + body
    if subpkg > 0:
        # 分包封装项：总包数 + 包序号（本工具不使用分包，保留参数位）
        raw = header + struct.pack(">HH", subpkg, 1) + body
    cs = xor_checksum(raw)
    return bytes([FRAME_FLAG]) + escape_data(raw + bytes([cs])) + bytes([FRAME_FLAG])


def put_u32(v):
    return struct.pack(">I", v & 0xFFFFFFFF)


def put_u16(v):
    return struct.pack(">H", v & 0xFFFF)


def build_8103(items):
    """设置终端参数：参数总数(1) + N * {ID(4) + 长度(1) + 值}"""
    body = bytearray([len(items) & 0xFF])
    for pid, value in items:
        info = PARAM_MAP.get(pid)
        if info is None:
            raise ValueError("未知参数 ID 0x%04X" % pid)
        if info["type"] == "u32":
            try:
                v = int(value)
            except (TypeError, ValueError):
                raise ValueError("参数 0x%04X 需为整数" % pid)
            if v < info["min"] or v > info["max"]:
                raise ValueError("参数 0x%04X 超出范围 %d~%d（当前 %d）"
                                 % (pid, info["min"], info["max"], v))
            raw = put_u32(v)
        else:
            raw = encode_str(value)
            if len(raw) == 0:
                # 0x0011/0x0012 允许空（固件会用 "NULL" 代替）；其余不允许空
                if pid not in (0x0011, 0x0012, 0x0014, 0x0015, 0x0016):
                    raise ValueError("参数 0x%04X 不允许为空" % pid)
            if len(raw) > info.get("maxlen", 63):
                raise ValueError("参数 0x%04X 长度 %d 超过上限 %d"
                                 % (pid, len(raw), info["maxlen"]))
            if pid in (0x0013, 0x0017) and (b":" in raw or b";" in raw):
                raise ValueError("参数 0x%04X 只填 IP 或域名，不含端口、不可用分号拼接" % pid)
        if len(raw) > 0xFF:
            raise ValueError("参数 0x%04X 值过长" % pid)
        body += put_u32(pid)
        body.append(len(raw))
        body += raw
    return bytes(body)


def build_8106(ids):
    """查询指定终端参数：参数总数(1) + N * ID(4)"""
    body = bytearray([len(ids) & 0xFF])
    for pid in ids:
        body += put_u32(pid)
    return bytes(body)


def build_8001(ack_seq, ack_msg_id, result):
    """平台通用应答：应答流水号(2) + 应答ID(2) + 结果(1)"""
    return put_u16(ack_seq) + put_u16(ack_msg_id) + bytes([result & 0xFF])


def build_8100(ack_seq, result, auth_code=""):
    """终端注册应答：应答流水号(2) + 结果(1) + [鉴权码]"""
    body = put_u16(ack_seq) + bytes([result & 0xFF])
    if result == 0:
        body += encode_str(auth_code)
    return body


def build_8105(cmd_word, params_str):
    """终端控制：命令字(1) + 命令参数(STRING, GBK)"""
    body = bytes([cmd_word & 0xFF])
    if cmd_word not in (3, 4, 5, 6, 7) and params_str:
        body += encode_str(params_str, gbk=True)
    return body


def encode_str(s, gbk=False):
    if s is None:
        return b""
    s = str(s)
    for enc in (["gbk", "utf-8"] if gbk else ["ascii", "gbk", "utf-8"]):
        try:
            return s.encode(enc)
        except UnicodeEncodeError:
            continue
    return s.encode("utf-8", errors="replace")


def decode_str(data, gbk=False):
    if not data:
        return ""
    for enc in (["gbk", "utf-8"] if gbk else ["ascii", "utf-8", "gbk"]):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return to_hex(data)


# ============================================================================
# 解包
# ============================================================================
def parse_frame(raw):
    """
    解析已去转义的帧（不含首尾 7E）。
    返回 dict，失败抛 ValueError。
    """
    if len(raw) < HEADER_LEN + 1:
        raise ValueError("帧长度不足 %d" % len(raw))
    body_and_cs = raw[:-1]
    expect_cs = xor_checksum(body_and_cs)
    got_cs = raw[-1]
    msg_id, prop = struct.unpack(">HH", raw[0:4])
    body_len = prop & 0x3FF
    encrypt = (prop >> 10) & 0x07
    subpkg = (prop >> 13) & 0x01
    phone = bcd_to_phone(raw[4:10])
    seq = struct.unpack(">H", raw[10:12])[0]

    hdr_len = HEADER_LEN
    extra = {}
    if subpkg:
        if len(raw) < HEADER_LEN + 4 + 1:
            raise ValueError("分包帧长度不足")
        total, index = struct.unpack(">HH", raw[HEADER_LEN:HEADER_LEN + 4])
        extra["subpkg_total"] = total
        extra["subpkg_index"] = index
        hdr_len = HEADER_LEN + 4

    body = raw[hdr_len:hdr_len + body_len]
    if len(body) != body_len:
        raise ValueError("消息体长度不符：声明 %d，实际 %d" % (body_len, len(body)))

    return {
        "msgId": msg_id,
        "msgName": MSG_NAMES.get(msg_id, "未知消息"),
        "phone": phone,
        "seq": seq,
        "bodyLen": body_len,
        "encrypt": encrypt,
        "subpkg": bool(subpkg),
        "checksumOk": (expect_cs == got_cs),
        "checksumExpect": expect_cs,
        "checksumGot": got_cs,
        "body": body,
        **extra,
    }


def render_param_item(pid, value):
    """按参数类型渲染 0x0104 里的参数值"""
    info = PARAM_MAP.get(pid)
    if info is None:
        return to_hex(value)
    if info["type"] == "u32":
        if len(value) != 4:
            return "%s (长度%d异常)" % (to_hex(value), len(value))
        return str(struct.unpack(">I", value)[0])
    return decode_str(value)


def parse_body(msg_id, body):
    """解析消息体，返回 (dict, 说明列表)"""
    d = {}
    notes = []
    try:
        if msg_id == MSG_TERMINAL_ACK:
            if len(body) >= 5:
                ack_seq, ack_id = struct.unpack(">HH", body[0:4])
                res = body[4]
                d = {"ackSeq": ack_seq, "ackMsgId": ack_id, "ackMsgName": MSG_NAMES.get(ack_id, "?"),
                     "result": res, "resultName": ACK_RESULT_NAMES.get(res, "?")}
        elif msg_id == MSG_HEARTBEAT:
            notes.append("心跳消息体为空")
        elif msg_id == MSG_REGISTER:
            if len(body) >= 37:
                prov, city = struct.unpack(">HH", body[0:4])
                mfr = body[4:9]
                model = body[9:29]
                term_id = body[29:36]
                plate_color = body[36]
                plate = body[37:]
                d = {
                    "provinceId": prov, "cityId": city,
                    "manufacturerId": decode_str(mfr.rstrip(b"\x00")),
                    "terminalModel": decode_str(model.rstrip(b"\x00")),
                    "terminalId": bcd_to_imei_tail(term_id),
                    "plateColor": plate_color,
                    "plateId": decode_str(plate, gbk=(plate_color != 0)),
                }
                if plate_color == 0:
                    notes.append("车牌颜色 0 -> 车辆标识按 VIN 解析")
        elif msg_id == MSG_AUTH:
            d = {"authCode": decode_str(body)}
        elif msg_id == MSG_QUERY_PARAM_ACK:
            if len(body) >= 3:
                ack_seq = struct.unpack(">H", body[0:2])[0]
                count = body[2]
                items = []
                off = 3
                for _ in range(count):
                    if off + 5 > len(body):
                        notes.append("参数项被截断，已声明 %d 项，实际解析 %d 项" % (count, len(items)))
                        break
                    pid = struct.unpack(">I", body[off:off + 4])[0]
                    ln = body[off + 4]
                    val = body[off + 5:off + 5 + ln]
                    off += 5 + ln
                    info = PARAM_MAP.get(pid)
                    items.append({
                        "id": pid,
                        "name": info["name"] if info else "未知参数",
                        "len": ln,
                        "raw": to_hex(val),
                        "value": render_param_item(pid, val),
                        "type": info["type"] if info else "?",
                    })
                d = {"ackSeq": ack_seq, "count": count, "items": items}
        elif msg_id == MSG_TERMINAL_PROPERTY_ACK:
            if len(body) >= 2 + 5 + 20 + 7 + 10:
                off = 0
                ttype = struct.unpack(">H", body[off:off + 2])[0]; off += 2
                mfr = body[off:off + 5]; off += 5
                model = body[off:off + 20]; off += 20
                term_id = body[off:off + 7]; off += 7
                iccid = body[off:off + 10]; off += 10
                hw, fw, gnss, comm = "", "", None, None
                if off < len(body):
                    hl = body[off]; off += 1
                    hw = decode_str(body[off:off + hl]); off += hl
                if off < len(body):
                    fl = body[off]; off += 1
                    fw = decode_str(body[off:off + fl]); off += fl
                if off < len(body):
                    gnss = body[off]; off += 1
                if off < len(body):
                    comm = body[off]; off += 1
                d = {
                    "terminalType": ttype,
                    "manufacturerId": decode_str(mfr.rstrip(b"\x00")),
                    "terminalModel": decode_str(model.rstrip(b"\x00")),
                    "terminalId": bcd_to_imei_tail(term_id),
                    "iccid": bcd_to_phone(iccid[:10]) if len(iccid) == 10 else to_hex(iccid),
                    "hwVersion": hw, "fwVersion": fw,
                    "gnssCapability": gnss, "commCapability": comm,
                }
        elif msg_id == MSG_UPGRADE_RESULT:
            if len(body) >= 2:
                d = {"upgradeType": body[0], "upgradeResult": body[1]}
        elif msg_id == MSG_LOCATION:
            if len(body) >= 28:
                alarm, status = struct.unpack(">II", body[0:8])
                lat, lon = struct.unpack(">II", body[8:16])
                alt, speed, direction = struct.unpack(">HHH", body[16:22])
                t = body[22:28]
                d = {
                    "alarm": alarm, "status": status,
                    "lat": lat / 1e6, "lon": lon / 1e6,
                    "alt": alt, "speed": speed / 10.0, "direction": direction,
                    "time": "%02X%02X-%02X-%02X %02X:%02X:%02X" % (t[0], t[1], t[2], t[3], t[4], t[5]),
                    "extraLen": max(0, len(body) - 28),
                }
        elif msg_id == MSG_SET_PARAM:
            if len(body) >= 1:
                count = body[0]
                items = []
                off = 1
                for _ in range(count):
                    if off + 5 > len(body):
                        break
                    pid = struct.unpack(">I", body[off:off + 4])[0]
                    ln = body[off + 4]
                    val = body[off + 5:off + 5 + ln]
                    off += 5 + ln
                    info = PARAM_MAP.get(pid)
                    items.append({"id": pid, "name": info["name"] if info else "未知参数",
                                  "len": ln, "raw": to_hex(val),
                                  "value": render_param_item(pid, val)})
                d = {"count": count, "items": items}
        elif msg_id == MSG_QUERY_SPEC_PARAM:
            if len(body) >= 1:
                count = body[0]
                ids = []
                for i in range(count):
                    if 1 + i * 4 + 4 <= len(body):
                        ids.append(struct.unpack(">I", body[1 + i * 4:1 + i * 4 + 4])[0])
                d = {"count": count, "ids": ["0x%04X" % x for x in ids]}
        elif msg_id == MSG_PLATFORM_ACK:
            if len(body) >= 5:
                ack_seq, ack_id = struct.unpack(">HH", body[0:4])
                res = body[4]
                d = {"ackSeq": ack_seq, "ackMsgId": ack_id, "ackMsgName": MSG_NAMES.get(ack_id, "?"),
                     "result": res, "resultName": ACK_RESULT_NAMES.get(res, "?")}
        elif msg_id == MSG_REGISTER_ACK:
            if len(body) >= 3:
                ack_seq = struct.unpack(">H", body[0:2])[0]
                res = body[2]
                d = {"ackSeq": ack_seq, "result": res,
                     "resultName": REGISTER_RESULT_NAMES.get(res, "?"),
                     "authCode": decode_str(body[3:])}
        elif msg_id == MSG_TERMINAL_CONTROL:
            if len(body) >= 1:
                d = {"cmdWord": body[0], "params": decode_str(body[1:], gbk=True)}
        elif msg_id == MSG_QUERY_PARAM:
            notes.append("消息体为空")
        elif msg_id == MSG_QUERY_PROPERTY:
            notes.append("消息体为空")
        else:
            notes.append("未实现该消息体的解析")
    except Exception as exc:  # 解析异常不应影响日志展示
        notes.append("解析异常：%s" % exc)
    return d, notes


# ============================================================================
# 事件广播（SSE）
# ============================================================================
class Hub:
    def __init__(self):
        self._lock = threading.Lock()
        self._queues = []

    def subscribe(self):
        q = queue.Queue(maxsize=4000)
        with self._lock:
            self._queues.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._queues:
                self._queues.remove(q)

    def publish(self, evt):
        with self._lock:
            qs = list(self._queues)
        for q in qs:
            try:
                q.put_nowait(evt)
            except queue.Full:
                pass


HUB = Hub()


# ============================================================================
# 设备连接管理
# ============================================================================
class DeviceConn:
    _next_id = 0

    def __init__(self, sock, addr):
        DeviceConn._next_id += 1
        self.id = DeviceConn._next_id
        self.sock = sock
        self.addr = addr
        self.buf = b""
        self.phone = ""
        self.rx_frames = 0
        self.tx_frames = 0
        self.alive = True
        self.send_lock = threading.Lock()
        self.connected_at = time.time()

    def desc(self):
        return "%s:%d" % (self.addr[0], self.addr[1])

    def send(self, data):
        with self.send_lock:
            if not self.alive:
                raise RuntimeError("连接已断开")
            self.sock.sendall(data)
            self.tx_frames += 1

    def close(self):
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class TcpServer:
    def __init__(self, port, hub):
        self.port = port
        self.hub = hub
        self.conns = []
        self._lock = threading.Lock()
        self._srv = None
        self._running = False
        self.auto_ack = True

    def start(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Windows 的 SO_REUSEADDR 语义与 Linux 不同：它允许两个进程同时 bind 同一端口，
        # 第二个实例不会报错，连接会被随机分给其中任意一个，导致设备连上来却"看不到"。
        # 所以 Windows 下用 SO_EXCLUSIVEADDRUSE 独占端口，重复启动立刻报错。
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._srv.bind(("0.0.0.0", self.port))
        except OSError as e:
            self._srv.close()
            raise RuntimeError(
                "端口 %d 已被占用，无法启动。\n"
                "常见原因：已有一个本工具实例在跑（Windows 上不会报错，会两个都绑上，"
                "设备连接随机分配，表现为\"连不上\"）。\n"
                "处理：先执行 `netstat -ano | findstr :%d` 查占用进程，"
                "`taskkill /PID <PID> /F` 杀掉多余实例后重试，或改用 --tcp 1809。\n"
                "原始错误：%s" % (self.port, self.port, e)
            )
        self._srv.listen(8)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._info("TCP 监听已启动，端口 %d，等待设备连入" % self.port)

    def stop(self):
        self._running = False
        try:
            if self._srv:
                self._srv.close()
        except OSError:
            pass
        with self._lock:
            conns = list(self.conns)
        for c in conns:
            c.close()

    def _accept_loop(self):
        while self._running:
            try:
                sock, addr = self._srv.accept()
            except OSError:
                break
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # 心跳/空闲检测交给设备侧，本工具不主动超时
            conn = DeviceConn(sock, addr)
            with self._lock:
                self.conns.append(conn)
            self._info("设备已连接 #%d  %s" % (conn.id, conn.desc()))
            self._publish_conns()
            threading.Thread(target=self._recv_loop, args=(conn,), daemon=True).start()

    def _recv_loop(self, conn):
        while conn.alive:
            try:
                data = conn.sock.recv(4096)
            except OSError:
                break
            if not data:
                break
            conn.buf += data
            for raw in self._split_frames(conn):
                self._handle_frame(conn, raw)
        conn.close()
        with self._lock:
            if conn in self.conns:
                self.conns.remove(conn)
        self._info("设备已断开 #%d  %s" % (conn.id, conn.desc()))
        self._publish_conns()

    @staticmethod
    def _split_frames(conn):
        """按 0x7E 切帧"""
        out = []
        while True:
            i = conn.buf.find(bytes([FRAME_FLAG]))
            if i < 0:
                conn.buf = b""
                break
            if i > 0:
                conn.buf = conn.buf[i:]
            j = conn.buf.find(bytes([FRAME_FLAG]), 1)
            if j < 0:
                break
            payload = conn.buf[1:j]
            conn.buf = conn.buf[j:]
            if payload:
                out.append(payload)
        return out

    def _handle_frame(self, conn, payload):
        conn.rx_frames += 1
        raw = unescape_data(payload)
        entry = {
            "ts": time.strftime("%H:%M:%S") + ".%03d" % (int(time.time() * 1000) % 1000),
            "dir": "RX",
            "conn": "#%d %s" % (conn.id, conn.desc()),
            "wireHex": to_hex(payload),
        }
        if raw is None:
            entry.update({"ok": False, "error": "转义还原失败"})
            entry["rawHex"] = to_hex(payload)
            self.hub.publish({"type": "log", "data": entry})
            return
        entry["rawHex"] = to_hex(raw)
        try:
            info = parse_frame(raw)
        except ValueError as exc:
            entry.update({"ok": False, "error": "解包失败：%s" % exc})
            self.hub.publish({"type": "log", "data": entry})
            return

        body = info.pop("body")
        parsed, notes = parse_body(info["msgId"], body)
        info["phone"] = info["phone"]
        conn.phone = info["phone"]
        entry.update({
            "ok": info.get("checksumOk", False),
            "msgId": info["msgId"],
            "msgName": info["msgName"],
            "phone": info["phone"],
            "seq": info["seq"],
            "bodyLen": info["bodyLen"],
            "checksumOk": info["checksumOk"],
            "parsed": parsed,
            "notes": notes,
        })
        if not info["checksumOk"]:
            entry["error"] = "校验码错误：期望 %02X，实际 %02X" % (
                info["checksumExpect"], info["checksumGot"])
        entry["bodyHex"] = to_hex(body)
        self.hub.publish({"type": "log", "data": entry})
        self._publish_conns()

        # 可选：自动回 0x8001
        if self.auto_ack and info["msgId"] in (
                MSG_REGISTER, MSG_AUTH, MSG_LOCATION, MSG_TERMINAL_PROPERTY_ACK,
                MSG_UPGRADE_RESULT, MSG_HEARTBEAT):
            try:
                self.send_command(
                    msg_id=MSG_PLATFORM_ACK,
                    phone=info["phone"],
                    body=build_8001(info["seq"], info["msgId"], 0),
                    note="自动应答 0x%04X" % info["msgId"],
                    conn_id=conn.id,
                )
            except Exception:
                pass

    def _info(self, text):
        self.hub.publish({"type": "log", "data": {
            "ts": time.strftime("%H:%M:%S") + ".%03d" % (int(time.time() * 1000) % 1000),
            "dir": "INFO", "text": text,
        }})

    def _publish_conns(self):
        with self._lock:
            data = [{
                "id": c.id, "desc": c.desc(), "phone": c.phone,
                "rx": c.rx_frames, "tx": c.tx_frames,
                "alive": c.alive,
            } for c in self.conns]
        self.hub.publish({"type": "conns", "data": data})

    def send_command(self, msg_id, phone, body, note="", conn_id=None):
        """组帧并发送到指定连接（默认最后一个连入的设备）"""
        pbd = phone_to_bcd(phone)
        with self._lock:
            candidates = [c for c in self.conns if c.alive]
        if not candidates:
            raise RuntimeError("当前没有已连接的设备，请先让设备连到本机 %d 端口" % self.port)
        if conn_id is not None:
            target = next((c for c in candidates if c.id == conn_id), None)
            if target is None:
                raise RuntimeError("指定的连接 #%s 已断开" % conn_id)
        else:
            target = candidates[-1]

        seq = SEQ.next()
        frame = build_frame(msg_id, pbd, seq, body)
        target.send(frame)
        self.hub.publish({"type": "log", "data": {
            "ts": time.strftime("%H:%M:%S") + ".%03d" % (int(time.time() * 1000) % 1000),
            "dir": "TX",
            "conn": "#%d %s" % (target.id, target.desc()),
            "msgId": msg_id,
            "msgName": MSG_NAMES.get(msg_id, "未知消息"),
            "phone": bcd_to_phone(pbd),
            "seq": seq,
            "bodyLen": len(body),
            "bodyHex": to_hex(body),
            "rawHex": to_hex(frame),
            "note": note,
            "ok": True,
        }})
        self._publish_conns()
        return seq

    def send_raw(self, hex_str, conn_id=None):
        """发送原始报文：接受 7E 包裹或裸 头+体+校验"""
        h = hex_str.replace(" ", "").replace("\r", "").replace("\n", "").replace("-", "")
        if len(h) % 2 != 0:
            raise ValueError("十六进制字符数必须为偶数")
        data = bytes.fromhex(h)
        if not data.startswith(bytes([FRAME_FLAG])):
            # 裸帧，自动补校验与首尾标识
            if len(data) < HEADER_LEN:
                raise ValueError("裸帧长度不足 %d 字节" % HEADER_LEN)
            prop = struct.unpack(">H", data[2:4])[0]
            body_len = prop & 0x3FF
            need = HEADER_LEN + body_len
            if len(data) == need:
                data = data + bytes([xor_checksum(data)])
            elif len(data) == need + 1:
                pass
            else:
                raise ValueError("裸帧长度 %d 与消息体声明 %d 不匹配" % (len(data), body_len))
            data = bytes([FRAME_FLAG]) + escape_data(data) + bytes([FRAME_FLAG])
        with self._lock:
            candidates = [c for c in self.conns if c.alive]
        if not candidates:
            raise RuntimeError("当前没有已连接的设备")
        target = candidates[-1]
        if conn_id is not None:
            target = next((c for c in candidates if c.id == conn_id), target)
        target.send(data)
        self.hub.publish({"type": "log", "data": {
            "ts": time.strftime("%H:%M:%S") + ".%03d" % (int(time.time() * 1000) % 1000),
            "dir": "TX", "conn": "#%d %s" % (target.id, target.desc()),
            "msgName": "原始报文", "rawHex": to_hex(data), "note": "手动发送", "ok": True,
        }})
        self._publish_conns()


SERVER = None  # 在 main 中初始化


# ============================================================================
# 本机 IP
# ============================================================================
def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


# ============================================================================
# HTTP 服务（网页 + API + SSE）
# ============================================================================
INDEX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 不刷屏

    def handle_one_request(self):
        """浏览器/curl 断开时静默处理，不打印堆栈"""
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            self.close_connection = True

    # ---------- helpers ----------
    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    # ---------- routes ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_index()
        elif path == "/api/params":
            self._send_json({
                "params": PARAMS,
                "controlCmds": CONTROL_CMDS,
                "ackResults": ACK_RESULT_NAMES,
                "registerResults": REGISTER_RESULT_NAMES,
                "msgNames": {str(k): v for k, v in MSG_NAMES.items()},
                "nextSeq": SEQ.peek_next(),
            })
        elif path == "/api/status":
            with SERVER._lock:
                conns = [{"id": c.id, "desc": c.desc(), "phone": c.phone,
                          "rx": c.rx_frames, "tx": c.tx_frames, "alive": c.alive}
                         for c in SERVER.conns]
            self._send_json({
                "tcpPort": SERVER.port,
                "localIps": local_ips(),
                "autoAck": SERVER.auto_ack,
                "conns": conns,
                "nextSeq": SEQ.peek_next(),
            })
        elif path == "/api/events":
            self._serve_sse()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            payload = self._read_json()
        except Exception as exc:
            self._send_json({"error": "请求体解析失败：%s" % exc}, 400)
            return

        try:
            if path == "/api/send":
                self._handle_send(payload)
            elif path == "/api/preview":
                self._handle_preview(payload)
            elif path == "/api/autoack":
                SERVER.auto_ack = bool(payload.get("enabled", True))
                self._send_json({"ok": True, "autoAck": SERVER.auto_ack})
            elif path == "/api/disconnect":
                cid = payload.get("id")
                with SERVER._lock:
                    target = next((c for c in SERVER.conns if c.id == cid), None)
                if target:
                    target.close()
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)

    # ---------- 具体处理 ----------
    def _handle_preview(self, p):
        """只组帧不发送，用于把报文填进"原始报文"框复制出去"""
        items = []
        for it in p.get("items", []):
            if it.get("checked"):
                items.append((int(it["id"]), it.get("value", "")))
        if not items:
            raise ValueError("请至少勾选一个参数")
        body = build_8103(items)
        seq = SEQ.peek_next()
        pbd = phone_to_bcd(p.get("phone", "")) if p.get("phone") else bytes(6)
        frame = build_frame(MSG_SET_PARAM, pbd, seq, body)
        self._send_json({"ok": True, "hex": to_hex(frame), "seq": seq})

    def _handle_send(self, p):
        phone = p.get("phone", "").strip()
        phone_to_bcd(phone)  # 提前校验
        action = p.get("action")
        conn_id = p.get("connId")

        if action == "8103":
            items = []
            for it in p.get("items", []):
                if not it.get("checked"):
                    continue
                items.append((int(it["id"]), it.get("value", "")))
            if not items:
                raise ValueError("请至少勾选一个要设置的参数")
            body = build_8103(items)
            seq = SERVER.send_command(MSG_SET_PARAM, phone, body,
                                     note="设置 %d 项参数" % len(items), conn_id=conn_id)
        elif action == "8104":
            seq = SERVER.send_command(MSG_QUERY_PARAM, phone, b"",
                                     note="查询全部终端参数", conn_id=conn_id)
        elif action == "8106":
            ids = [int(x) for x in p.get("ids", [])]
            if not ids:
                raise ValueError("请至少选择一个要查询的参数")
            if len(ids) > 8:
                raise ValueError("固件一次最多解析 8 项（JT808_PARAM_ITEM_MAX），当前 %d 项" % len(ids))
            body = build_8106(ids)
            seq = SERVER.send_command(MSG_QUERY_SPEC_PARAM, phone, body,
                                     note="查询 %d 项指定参数" % len(ids), conn_id=conn_id)
        elif action == "8001":
            body = build_8001(int(p["ackSeq"]), int(p["ackMsgId"]), int(p["result"]))
            seq = SERVER.send_command(MSG_PLATFORM_ACK, phone, body, note="手动平台通用应答",
                                     conn_id=conn_id)
        elif action == "8100":
            body = build_8100(int(p["ackSeq"]), int(p["result"]), p.get("authCode", ""))
            seq = SERVER.send_command(MSG_REGISTER_ACK, phone, body, note="终端注册应答",
                                     conn_id=conn_id)
        elif action == "8107":
            seq = SERVER.send_command(MSG_QUERY_PROPERTY, phone, b"",
                                     note="查询终端属性", conn_id=conn_id)
        elif action == "8105":
            body = build_8105(int(p["cmdWord"], 16) if isinstance(p["cmdWord"], str) else int(p["cmdWord"]),
                              p.get("params", ""))
            seq = SERVER.send_command(MSG_TERMINAL_CONTROL, phone, body, note="终端控制",
                                     conn_id=conn_id)
        elif action == "raw":
            SERVER.send_raw(p.get("hex", ""), conn_id=conn_id)
            self._send_json({"ok": True, "seq": None})
            return
        else:
            raise ValueError("未知操作 %s" % action)

        self._send_json({"ok": True, "seq": seq})

    def _serve_index(self):
        try:
            with open(INDEX_FILE, "rb") as f:
                data = f.read()
        except OSError:
            self._send_json({"error": "index.html 缺失，请与脚本放在同一目录"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q = HUB.subscribe()
        try:
            # 首包推送当前连接列表
            with SERVER._lock:
                conns = [{"id": c.id, "desc": c.desc(), "phone": c.phone,
                          "rx": c.rx_frames, "tx": c.tx_frames, "alive": c.alive}
                         for c in SERVER.conns]
            self._sse_write({"type": "conns", "data": conns})
            self._sse_write({"type": "log", "data": {
                "ts": time.strftime("%H:%M:%S"), "dir": "INFO", "text": "日志通道已连接"}})
            while True:
                try:
                    evt = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self._sse_write(evt)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            HUB.unsubscribe(q)

    def _sse_write(self, obj):
        data = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
        self.wfile.write(data.encode("utf-8"))
        self.wfile.flush()


# ============================================================================
# 入口
# ============================================================================
def main():
    global SERVER
    ap = argparse.ArgumentParser(description="JT/T 808 参数设置/查询 调试工具")
    ap.add_argument("--tcp", type=int, default=1808, help="设备接入的 TCP 端口（默认 1808）")
    ap.add_argument("--http", type=int, default=8080, help="网页端口（默认 8080）")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    SERVER = TcpServer(args.tcp, HUB)
    try:
        SERVER.start()
    except RuntimeError as exc:
        print("[错误] %s" % exc)
        sys.exit(1)
    except OSError as exc:
        print("[错误] TCP 端口 %d 启动失败：%s" % (args.tcp, exc))
        print("       端口可能被占用，换一个： python jt808_debugger.py --tcp 1809")
        sys.exit(1)

    http_srv = ThreadingHTTPServer(("127.0.0.1", args.http), Handler)
    http_srv.daemon_threads = True

    url = "http://127.0.0.1:%d/" % args.http
    print("=" * 68)
    print(" JT/T 808 参数设置/查询 调试工具")
    print("=" * 68)
    print(" 网页界面 : %s" % url)
    print(" 设备接入 : TCP %d  （设备 TSP 服务器地址改成本机 IP）" % args.tcp)
    for ip in local_ips():
        print("            可填地址： %s" % ip)
    print(" 停止     : Ctrl + C")
    print("=" * 68)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        http_srv.serve_forever()
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        SERVER.stop()
        http_srv.shutdown()


if __name__ == "__main__":
    main()
