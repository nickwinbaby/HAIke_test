# -*- coding: utf-8 -*-
"""
JT808 电子围栏追踪台 —— 设备真的连上来，位置真的画在地图上。

做三件事：
  1. TCP 7611 起一个 JT/T 808 服务端，等设备来注册（0x0100）、心跳（0x0002）、
     位置汇报（0x0200），并按协议应答 0x8100 / 0x8001；
  2. HTTP 起页面和一套 REST 接口，浏览器打开就能看设备在哪、围栏在哪；
  3. 围栏存在本机 fences.json，逐个判定设备在内还是在外。

只依赖 Python 标准库，不用装任何第三方包。

用法：
    python server.py                    # 默认 网页 8088 / 设备 7611
    python server.py --web 9000 --tcp 7611
    python server.py --tcp 0            # 只起网页，不开设备口
"""
import argparse
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.parse
import webbrowser
from collections import OrderedDict, deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
FENCE_FILE = os.path.join(HERE, "fences.json")

# 编解码只有一份，放在 ../shared/，离线工具与本平台共用，改协议不用改两处
SHARED = os.path.abspath(os.path.join(HERE, "..", "shared"))

DEFAULT_WEB = 8088
DEFAULT_TCP = 7611

# 设备多久没动静算离线（秒）。国标默认心跳 3 分钟，这里放宽到 5 分钟。
OFFLINE_SEC = 300

# 单台设备保留多少个轨迹点
TRACK_MAX = 500


# ============================================================
# 一、JT/T 808 编解码（与 jt808_offline 的规则保持一致）
# ============================================================

FLAG = 0x7E
ESC = 0x7D
ESC_FLAG = 0x02
ESC_ESC = 0x01


class ProtocolError(Exception):
    pass


def escape_bytes(raw):
    out = bytearray()
    for b in raw:
        if b == FLAG:
            out += bytes([ESC, ESC_FLAG])
        elif b == ESC:
            out += bytes([ESC, ESC_ESC])
        else:
            out.append(b)
    return bytes(out)


def unescape_bytes(data):
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == ESC:
            i += 1
            if i >= n:
                raise ProtocolError("转义不完整（末尾是 0x7D）")
            if data[i] == ESC_FLAG:
                out.append(FLAG)
            elif data[i] == ESC_ESC:
                out.append(ESC)
            else:
                raise ProtocolError("非法转义序列 7D %02X" % data[i])
        else:
            out.append(b)
        i += 1
    return bytes(out)


def bcd_to_str(b):
    s = ""
    for x in b:
        s += "%02X" % x
    return s


def str_to_bcd(s, length=None):
    """字符串手机号 -> BCD 字节。

    国标是右补 0（13800138000 -> 138001380000），不是左补 ——
    左补出来是 013800138000，设备会认为不是自己的号码。
    """
    s = "".join(ch for ch in str(s) if ch.isdigit())
    if length:
        if len(s) > length:
            s = s[-length:]
        else:
            s = s.ljust(length, "0")      # 右补
    if len(s) % 2:
        s += "0"
    return bytes(int(s[i:i + 2], 16) for i in range(0, len(s), 2))


def checksum(raw):
    cs = 0
    for b in raw:
        cs ^= b
    return cs


def build_packet(msg_id, phone, seq, body, version_2019=False):
    """组一条完整下行帧（含首尾 7E 与转义）。"""
    phone_bcd = str_to_bcd(phone, 12)
    if len(phone_bcd) != 6:
        raise ProtocolError("终端手机号必须是 12 位 BCD，实际 %r" % (phone,))

    if version_2019:
        # 2019 版：属性高位置 1 表示版本标识存在，多 1 字节版本号
        prop = (len(body) & 0x3FF) | 0x4000
        header = struct.pack(">HH", msg_id, prop) + phone_bcd + \
            struct.pack(">HB", seq & 0xFFFF, 1)
    else:
        prop = len(body) & 0x3FF
        header = struct.pack(">HH", msg_id, prop) + phone_bcd + \
            struct.pack(">H", seq & 0xFFFF)

    raw = header + body
    raw += bytes([checksum(raw)])
    return bytes([FLAG]) + escape_bytes(raw) + bytes([FLAG])


def split_frames(buf):
    """从字节流里切出完整帧，返回 (帧列表, 剩余字节)。

    设备可能一次发多条、也可能半条卡在缓冲区里，所以必须按 7E 切。
    注意：结束 FLAG 同时也是下一帧的起始 FLAG，所以只能消费到 end-1，
    把那个 7E 留给下一轮当起点（否则每帧都会在缓冲区里留一个孤字节）。
    """
    frames = []
    while True:
        start = buf.find(bytes([FLAG]))
        if start < 0:
            return frames, b""
        end = buf.find(bytes([FLAG]), start + 1)
        if end < 0:
            return frames, buf[start:]
        chunk = buf[start + 1:end]
        buf = buf[end:]          # 结束位留作下一帧的起始位
        if not chunk:
            continue             # 连续 7E = 空帧
        try:
            frames.append(unescape_bytes(chunk))
        except ProtocolError:
            continue


def parse_packet(raw):
    """解析一条去转义后的帧体，返回 dict。校验失败抛 ProtocolError。"""
    if len(raw) < 13:
        raise ProtocolError("帧太短（%d 字节）" % len(raw))
    if checksum(raw[:-1]) != raw[-1]:
        raise ProtocolError("校验码错：算 %02X，报文 %02X"
                            % (checksum(raw[:-1]), raw[-1]))

    head = raw[:-1]
    msg_id, prop = struct.unpack(">HH", head[0:4])
    phone = bcd_to_str(head[4:10])
    body_attr = prop & 0x3FF
    ver_flag = bool(prop & 0x4000)
    off = 10
    if ver_flag:
        off += 1                      # 版本标识
    seq = struct.unpack(">H", head[off:off + 2])[0]
    off += 2
    body = head[off:off + body_attr]
    sub = None
    if prop & 0x2000:                 # 分包：总包数 2B + 包序号 2B
        if len(body) >= 4:
            sub = struct.unpack(">HH", body[0:4])
            body = body[4:]
    return {
        "msg_id": msg_id, "phone": phone, "seq": seq,
        "body": body, "sub": sub,
    }


# ------------------------------------------------------------
# 0x0200 位置汇报体
# ------------------------------------------------------------

# 下行应答里要显示的中文名（只收常用的，避免和前端那份表重复维护）
MSG_NAMES = {
    0x8103: "设置终端参数", 0x8104: "查询终端参数", 0x8105: "终端控制",
    0x8106: "查询指定终端参数", 0x8107: "查询终端属性",
    0x8201: "位置信息查询", 0x8202: "临时位置跟踪控制",
    0x8300: "文本信息下发", 0x8500: "车辆控制",
    0x8600: "设置圆形区域", 0x8601: "删除圆形区域",
    0x8602: "设置矩形区域", 0x8603: "删除矩形区域",
    0x8604: "设置多边形区域", 0x8605: "删除多边形区域",
    0x8801: "摄像头立即拍摄", 0x8802: "存储多媒体上传",
}

# 参数 ID → 中文名（与固件参数表一致，用于日志可读）
PARAM_NAMES = {
    0x0001: "终端心跳间隔", 0x0010: "主服务器APN", 0x0011: "拨号用户名",
    0x0012: "拨号密码", 0x0013: "主服务器地址", 0x0018: "服务器TCP端口",
    0x0029: "缺省汇报间隔", 0x0083: "机动车号牌", 0xF001: "当前仪表里程基准",
}


def describe_param_answer(body):
    """0x0104 查询终端参数应答 → 若干行可读文本。

    布局：[应答流水号2][参数总数1][(ID4 + 长度1 + 值) × n]
    """
    lines = []
    if len(body) < 3:
        return ["应答体不足 3 字节（实际 %d）" % len(body)]
    ack_seq = struct.unpack(">H", body[0:2])[0]
    count = body[2]
    lines.append("查询应答（流水号 %d，共 %d 项）" % (ack_seq, count))
    off, idx = 3, 0
    while off + 5 <= len(body) and idx < count:
        pid = struct.unpack(">I", body[off:off + 4])[0]
        vlen = body[off + 4]
        off += 5
        if off + vlen > len(body):
            lines.append("  0x%08X 声明长度 %d 超出报文" % (pid, vlen))
            break
        val = body[off:off + vlen]
        off += vlen
        idx += 1
        nm = PARAM_NAMES.get(pid, "未收录")
        if vlen == 4:
            shown = str(struct.unpack(">I", val)[0])
        elif vlen == 0:
            shown = "（空）"
        else:
            shown = val.split(b"\x00")[0].decode("gbk", "replace")
        lines.append("  0x%08X %s = %s" % (pid, nm, shown))
    if idx < count:
        lines.append("  只解析出 %d / %d 项" % (idx, count))
    return lines


def parse_0200(body):
    """0x0200 位置汇报体。

    固定 28 字节布局，一字不能歪：
      0..4   报警标志  DWORD
      4..8   状态      DWORD
      8..12  纬度      DWORD（×1e6）
      12..16 经度      DWORD（×1e6）
      16..18 高程      WORD
      18..20 速度      WORD（×0.1 km/h）
      20..22 方向      WORD
      22..28 时间      BCD[6]
    """
    if len(body) < 28:
        raise ProtocolError("0x0200 消息体至少 28 字节，实际 %d" % len(body))
    alarm, status = struct.unpack(">II", body[0:8])
    lat, lon = struct.unpack(">II", body[8:16])
    alt, spd, direc = struct.unpack(">HHH", body[16:22])
    t = body[22:28]

    def bcd(i):
        return (t[i] >> 4) * 10 + (t[i] & 0x0F)

    tm = "20%02d-%02d-%02d %02d:%02d:%02d" % (
        bcd(0), bcd(1), bcd(2), bcd(3), bcd(4), bcd(5))

    out = {
        "alarm": alarm,
        "status": status,
        "lat": lat / 1e6,
        "lon": lon / 1e6,
        "alt": alt,
        "speed": spd / 10.0,
        "dir": direc,
        "time": tm,
        "located": bool(status & 0x02),
        "acc": bool(status & 0x01),
        "mileage": None,
        "extras": {},
    }

    # 附加项 TLV：里程 0x01、油量 0x02、报警 0x03 等
    off = 28
    while off + 2 <= len(body):
        eid = body[off]
        elen = body[off + 1]
        data = body[off + 2:off + 2 + elen]
        if len(data) < elen:
            break
        out["extras"][eid] = data
        if eid == 0x01 and elen == 4:
            out["mileage"] = struct.unpack(">I", data)[0] / 10.0
        off += 2 + elen
    return out


# ============================================================
# 二、围栏判定（本工具侧）
# ============================================================

R_EARTH = 6371008.8     # 平均地球半径，米


def haversine(lat1, lon1, lat2, lon2):
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, a ** 0.5))


def point_in_polygon(lat, lon, pts):
    """射线法。pts 为 [[lat, lon], ...]，按顺序相连。"""
    inside = False
    n = len(pts)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        yi, xi = pts[i][0], pts[i][1]
        yj, xj = pts[j][0], pts[j][1]
        if ((yi > lat) != (yj > lat)):
            x_at = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_at:
                inside = not inside
        j = i
    return inside


def fence_test(fence, lat, lon):
    """返回 (是否在内, 到边界/中心的距离米)。"""
    shape = fence.get("shape")
    pts = fence.get("points") or []

    if shape == "circle":
        if not pts:
            return False, None
        c = pts[0]
        d = haversine(lat, lon, c[0], c[1])
        return d <= float(fence.get("radius") or 0), d

    if shape == "polygon":
        inside = point_in_polygon(lat, lon, pts)
        d = min([haversine(lat, lon, p[0], p[1]) for p in pts], default=None)
        return inside, d

    if shape == "rect":
        # 矩形用经纬度包围盒：顶点已归一化成 [minLat,minLon] .. [maxLat,maxLon]
        if len(pts) < 2:
            return False, None
        lat1, lon1 = pts[0]
        lat2, lon2 = pts[1]
        mn_lat, mx_lat = min(lat1, lat2), max(lat1, lat2)
        mn_lon, mx_lon = min(lon1, lon2), max(lon1, lon2)
        inside = (mn_lat <= lat <= mx_lat) and (mn_lon <= lon <= mx_lon)
        # 到四条边的最近距离
        d1 = haversine(lat, lon, lat, mn_lon)
        d2 = haversine(lat, lon, lat, mx_lon)
        d3 = haversine(lat, lon, mn_lat, lon)
        d4 = haversine(lat, lon, mx_lat, lon)
        return inside, min(d1, d2, d3, d4)

    return False, None


# ============================================================
# 三、共享状态
# ============================================================

class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.fences = []              # [{id, name, shape, points, radius, ...}]
        self.devices = OrderedDict()  # phone -> {...}
        self.seq = 1
        self.events = deque(maxlen=300)
        self.load()

    # ---- 围栏持久化 ----
    def load(self):
        if not os.path.isfile(FENCE_FILE):
            return
        try:
            with open(FENCE_FILE, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict) and isinstance(obj.get("fences"), list):
                self.fences = obj["fences"]
            elif isinstance(obj, list):
                self.fences = obj
        except Exception as e:
            print("[!] fences.json 读取失败：%s" % e)

    def save(self):
        try:
            tmp = FENCE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"fences": self.fences}, f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp, FENCE_FILE)
        except Exception as e:
            print("[!] fences.json 写入失败：%s" % e)

    def next_fence_id(self):
        used = set()
        for f in self.fences:
            try:
                used.add(int(f.get("id")))
            except (TypeError, ValueError):
                pass
        i = 1
        while i in used:
            i += 1
        return i

    def log(self, msg):
        line = time.strftime("%H:%M:%S") + "  " + msg
        print(line, flush=True)
        self.events.append({"t": time.strftime("%H:%M:%S"), "msg": msg})

    # ---- 设备 ----
    def touch_device(self, phone, patch=None, point=None):
        with self.lock:
            d = self.devices.get(phone)
            if d is None:
                d = {"phone": phone, "online": False, "track": []}
                self.devices[phone] = d
            d["last_seen"] = time.time()
            d["online"] = True
            if patch:
                d.update(patch)
            if point:
                d["track"].append(point)
                if len(d["track"]) > TRACK_MAX:
                    del d["track"][:len(d["track"]) - TRACK_MAX]
                d["last"] = point
                # 每来一个点就重算围栏结论
                d["fences"] = self._eval(point["lat"], point["lon"])
            return d

    def _eval(self, lat, lon):
        res = []
        for f in sorted(self.fences, key=lambda x: x.get("id") or 0):
            inside, dist = fence_test(f, lat, lon)
            res.append({
                "id": f.get("id"),
                "name": f.get("name") or ("围栏 %s" % f.get("id")),
                "shape": f.get("shape"),
                "inside": inside,
                "dist": None if dist is None else round(dist, 1),
            })
        return res

    def sweep(self):
        """把太久没动静的设备标成离线。"""
        now = time.time()
        with self.lock:
            for d in self.devices.values():
                if d.get("online") and now - d.get("last_seen", 0) > OFFLINE_SEC:
                    d["online"] = False


STORE = Store()

# 在线连接注册表：phone -> DeviceConn。
# 平台要能主动下行（0x8103 / 0x8105 / 0x8600...），必须能按手机号找到那条 socket。
CONNS = {}
CONN_LOCK = threading.Lock()


# ============================================================
# 四、TCP 设备服务
# ============================================================

class DeviceConn(threading.Thread):
    def __init__(self, sock, addr):
        super().__init__(daemon=True)
        self.sock = sock
        self.addr = addr
        self.phone = None
        self.authed = False

    def send(self, msg_id, seq, body=b""):
        if not self.phone:
            return
        try:
            pkt = build_packet(msg_id, self.phone, seq, body)
            self.sock.sendall(pkt)
        except Exception as e:
            STORE.log("下行失败 %04X -> %s：%s" % (msg_id, self.phone, e))

    def send_raw(self, pkt):
        """直接下发一条已经组好的完整帧（平台主动下发用）。"""
        self.sock.sendall(pkt)

    def run(self):
        STORE.log("设备连接 %s:%d" % self.addr)
        buf = b""
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    break
                buf += data
                frames, buf = split_frames(buf)
                for raw in frames:
                    try:
                        self.handle(raw)
                    except ProtocolError as e:
                        STORE.log("解析失败 %s：%s" % (self.addr[0], e))
                    except Exception as e:
                        STORE.log("处理异常 %s：%s" % (self.addr[0], e))
        except OSError:
            pass
        finally:
            try:
                self.sock.close()
            except Exception:
                pass
            if self.phone:
                with STORE.lock:
                    d = STORE.devices.get(self.phone)
                    if d:
                        d["online"] = False
                unregister_conn(self.phone, self)
                STORE.log("设备断开 %s" % self.phone)

    def handle(self, raw):
        p = parse_packet(raw)
        mid, seq, body, phone = p["msg_id"], p["seq"], p["body"], p["phone"]

        # ---- 0x0100 终端注册 ----
        # 布局：省域 2B | 市域 2B | 制造商 5B | 终端型号 20B | 终端ID 7B | 车牌色 1B | 车牌
        if mid == 0x0100:
            self.phone = phone
            prov, city = struct.unpack(">HH", body[0:4])
            maker = body[4:9].split(b"\x00")[0].decode("gbk", "replace")
            model = body[9:29].split(b"\x00")[0].decode("gbk", "replace")
            term = bcd_to_str(body[29:36]) if len(body) >= 36 else ""
            plate = b""
            if len(body) > 37:
                plate = body[37:].split(b"\x00")[0]
            STORE.touch_device(phone, {
                "province": prov, "city": city,
                "terminal": term, "maker": maker, "model": model,
                "plate": plate.decode("gbk", "replace"),
            })
            self.authed = True
            register_conn(phone, self)
            # 应答：0 成功 + 鉴权码（这里给固定值，与常见平台一致）
            body_out = struct.pack(">BH", 0, 0xBEEF)
            self.send(0x8100, seq, body_out)
            STORE.log("注册 %s 终端 %s，已应答 0x8100" % (phone, term))
            return

        # ---- 0x0002 心跳 ----
        if mid == 0x0002:
            STORE.touch_device(phone)
            self.send(0x8001, seq,
                      struct.pack(">HH", seq, mid) + struct.pack(">B", 0))
            return

        # ---- 0x0200 位置汇报 ----
        if mid == 0x0200:
            loc = parse_0200(body)
            pt = {
                "lat": loc["lat"], "lon": loc["lon"],
                "speed": loc["speed"], "dir": loc["dir"],
                "alt": loc["alt"], "time": loc["time"],
                "located": loc["located"], "acc": loc["acc"],
                "mileage": loc["mileage"],
                "ts": time.time(),
            }
            d = STORE.touch_device(phone, None, pt)
            # 应答
            self.send(0x8001, seq,
                      struct.pack(">HH", seq, mid) + struct.pack(">B", 0))
            hits = [f["id"] for f in d.get("fences", []) if f["inside"]]
            STORE.log("位置 %s (%.6f, %.6f) 速度 %.1fkm/h 围栏内 %s"
                      % (phone, pt["lat"], pt["lon"], pt["speed"],
                         hits if hits else "无"))
            return

        # ---- 0x0001 终端通用应答：下行指令的结果回执 ----
        if mid == 0x0001:
            if len(body) >= 5:
                ack_seq, ack_id, result = struct.unpack(">HHB", body[0:5])
                names = {0: "成功/确认", 1: "失败", 2: "消息有误", 3: "不支持",
                         4: "报警处理确认"}
                STORE.log("应答 %04X %s <- 流水号 %d：%s" % (
                    ack_id, MSG_NAMES.get(ack_id, "未知消息"),
                    ack_seq, names.get(result, "未定义(%d)" % result)))
            return

        # ---- 0x0104 查询终端参数应答：把设备当前参数值打进日志 ----
        if mid == 0x0104:
            STORE.touch_device(phone)
            for line in describe_param_answer(body):
                STORE.log("参数 %s %s" % (phone, line))
            self.send(0x8001, seq, struct.pack(">HH", seq, mid)
                      + struct.pack(">B", 0))
            return

        # 其余消息一律 8001 通用应答
        self.send(0x8001, seq, struct.pack(">HH", seq, mid)
                  + struct.pack(">B", 1))


def register_conn(phone, conn):
    with CONN_LOCK:
        old = CONNS.get(phone)
        CONNS[phone] = conn
    if old is not None and old is not conn:
        try:
            old.sock.close()
        except Exception:
            pass


def unregister_conn(phone, conn):
    with CONN_LOCK:
        if CONNS.get(phone) is conn:
            del CONNS[phone]


def send_to_device(phone, frame):
    """把一条组好的完整帧发给指定在线设备，返回 (ok, message)。"""
    with CONN_LOCK:
        conn = CONNS.get(phone)
    if conn is None:
        return False, "设备 %s 当前不在线（没有活动 TCP 连接）" % phone
    try:
        conn.send_raw(frame)
        return True, "已下发 %d 字节" % len(frame)
    except Exception as e:
        return False, "下发失败：%s" % e


def tcp_server(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(16)
    STORE.log("设备接入端口 %d 已开启（设备服务器地址填本机 IP:%d）" % (port, port))
    while True:
        try:
            s, addr = srv.accept()
            DeviceConn(s, addr).start()
        except OSError:
            break


# ============================================================
# 五、HTTP 服务
# ============================================================

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass      # 页面 3 秒轮询一次，日志别刷屏

    def _send(self, code, ctype, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except Exception:
                pass

    def _json(self, code, obj):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", current_page())
        if p == "/api/state":
            return self._json(200, self.state())
        if p == "/api/config":
            return self._json(200, {"tcp_port": CFG["tcp"],
                                    "web_port": CFG["web"],
                                    "lan_ip": CFG["lan_ip"]})
        if p.startswith(("/vendor/", "/assets/")):
            return self.serve_static(p)
        if p.startswith("/js/"):
            return self.serve_shared(p)
        return self._json(404, {"ok": False, "message": "not found"})

    CTYPES = {
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }

    def serve_static(self, path):
        """只放 vendor/ 与 assets/ 下的文件，且禁止路径穿越。"""
        rel = urllib.parse.unquote(path).lstrip("/")
        full = os.path.abspath(os.path.join(HERE, rel))
        if not full.startswith(HERE + os.sep) or not os.path.isfile(full):
            return self._json(404, {"ok": False, "message": "not found"})
        ext = os.path.splitext(full)[1].lower()
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            return self._json(404, {"ok": False, "message": "not found"})
        self._send(200, self.CTYPES.get(ext, "application/octet-stream"), data)

    def serve_shared(self, path):
        """/js/ 映射到 ../shared/：编解码只此一份，两个工具共用。"""
        rel = urllib.parse.unquote(path).lstrip("/")
        name = os.path.basename(rel)          # 只允许单层文件名，杜绝穿越
        full = os.path.abspath(os.path.join(SHARED, name))
        if not full.startswith(SHARED + os.sep) or not os.path.isfile(full):
            return self._json(404, {"ok": False, "message": "not found"})
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            return self._json(404, {"ok": False, "message": "not found"})
        self._send(200, self.CTYPES.get(".js"), data)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            req = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return self._json(400, {"ok": False, "message": "JSON 解析失败"})

        if u.path == "/api/fence/save":
            return self.save_fence(req)
        if u.path == "/api/fence/delete":
            return self.del_fence(req)
        if u.path == "/api/send":
            return self.send_down(req)
        if u.path == "/api/fence/clear":
            with STORE.lock:
                STORE.fences = []
                STORE.save()
            STORE.log("围栏已全部清空")
            return self._json(200, {"ok": True})
        if u.path == "/api/device/clear":
            with STORE.lock:
                STORE.devices.clear()
            return self._json(200, {"ok": True})
        return self._json(404, {"ok": False, "message": "not found"})

    def state(self):
        STORE.sweep()
        with STORE.lock:
            devs = []
            for d in STORE.devices.values():
                devs.append({
                    "phone": d.get("phone"),
                    "plate": d.get("plate"),
                    "online": d.get("online"),
                    "last_seen": d.get("last_seen"),
                    "last": d.get("last"),
                    "track": d.get("track", [])[-200:],
                    "fences": d.get("fences", []),
                })
            return {
                "ok": True,
                "fences": sorted(STORE.fences, key=lambda x: x.get("id") or 0),
                "devices": devs,
                "events": list(STORE.events)[-60:],
                "tcp_port": CFG["tcp"],
            }

    def save_fence(self, req):
        shape = req.get("shape")
        pts = req.get("points")
        if shape not in ("circle", "rect", "polygon") or not isinstance(pts, list) or not pts:
            return self._json(400, {"ok": False, "message": "围栏参数不完整"})
        f = {
            "id": req.get("id"),
            "name": req.get("name") or "",
            "shape": shape,
            "points": pts,
            "radius": req.get("radius") or 0,
            "props": req.get("props") or {},
        }
        with STORE.lock:
            if f["id"] in (None, "", 0):
                f["id"] = STORE.next_fence_id()
            else:
                try:
                    f["id"] = int(f["id"])
                except (TypeError, ValueError):
                    return self._json(400, {"ok": False, "message": "围栏 ID 非法"})
            if not f["name"]:
                f["name"] = "围栏 %s" % f["id"]
            # 同 ID 覆盖，否则追加
            for i, old in enumerate(STORE.fences):
                if int(old.get("id") or 0) == f["id"]:
                    STORE.fences[i] = f
                    break
            else:
                STORE.fences.append(f)
            STORE.fences.sort(key=lambda x: x.get("id") or 0)
            STORE.save()
            # 设备结论跟着重算
            for d in STORE.devices.values():
                last = d.get("last")
                if last:
                    d["fences"] = STORE._eval(last["lat"], last["lon"])
        STORE.log("围栏 %s 已保存（%s）" % (f["id"], shape))
        return self._json(200, {"ok": True, "fence": f})

    def del_fence(self, req):
        fid = req.get("id")
        if fid is None:
            return self._json(400, {"ok": False, "message": "缺少 id"})
        try:
            fid = int(fid)
        except (TypeError, ValueError):
            return self._json(400, {"ok": False, "message": "id 非法"})
        with STORE.lock:
            before = len(STORE.fences)
            STORE.fences = [f for f in STORE.fences
                            if int(f.get("id") or 0) != fid]
            gone = before != len(STORE.fences)
            if gone:
                STORE.save()
                for d in STORE.devices.values():
                    last = d.get("last")
                    if last:
                        d["fences"] = STORE._eval(last["lat"], last["lon"])
        STORE.log("围栏 %d %s" % (fid, "已删除" if gone else "不存在"))
        return self._json(200, {"ok": True, "deleted": gone})

    # ---- 平台主动下发 ----
    def send_down(self, req):
        """把前端组好的报文发给设备。

        req.phone  : 目标终端手机号
        req.hex    : 完整帧（含 7E），前端已组好，服务端不再重复加工
        req.msg_id : 仅用于日志显示
        """
        phone = str(req.get("phone") or "").strip()
        hexs = str(req.get("hex") or "").replace(" ", "").replace("\n", "").upper()
        if not phone:
            return self._json(400, {"ok": False, "message": "缺少目标手机号"})
        if not hexs or len(hexs) % 2:
            return self._json(400, {"ok": False, "message": "报文 hex 不完整"})
        try:
            frame = bytes.fromhex(hexs)
        except ValueError:
            return self._json(400, {"ok": False, "message": "报文含非十六进制字符"})
        if frame[:1] != bytes([FLAG]) or frame[-1:] != bytes([FLAG]):
            return self._json(400, {"ok": False, "message": "报文必须以 7E 开头结尾"})

        ok, msg = send_to_device(phone, frame)
        mid = req.get("msg_id")
        name = req.get("msg_name") or ""
        label = ("%s %s" % (mid, name)).strip() if mid else "报文"
        if ok:
            STORE.log("下发 %s -> %s，%s" % (label, phone, msg))
        else:
            STORE.log("下发 %s -> %s 失败：%s" % (label, phone, msg))
        return self._json(200 if ok else 409,
                          {"ok": ok, "message": msg, "bytes": len(frame)})


CFG = {"web": DEFAULT_WEB, "tcp": DEFAULT_TCP, "lan_ip": "127.0.0.1"}

# 页面按 index.html 的 mtime+size 缓存：改完存一下、刷新浏览器就是新版，
# 不用每次重启服务（重启会丢掉当前设备连接）。
_page_cache = {"key": None, "data": b""}
_page_lock = threading.Lock()


def current_page():
    path = os.path.join(HERE, "index.html")
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = (0, 0)
    with _page_lock:
        if _page_cache["key"] != key or not _page_cache["data"]:
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    _page_cache["data"] = f.read().encode("utf-8")
                _page_cache["key"] = key
            except OSError as e:
                print("[!] index.html 读取失败：%s" % e)
        return _page_cache["data"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", type=int, default=DEFAULT_WEB)
    ap.add_argument("--tcp", type=int, default=DEFAULT_TCP)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    CFG["web"], CFG["tcp"] = args.web, args.tcp
    CFG["lan_ip"] = local_ips()[0]

    page_path = os.path.join(HERE, "index.html")
    if not os.path.isfile(page_path):
        sys.exit("缺少 index.html：%s" % page_path)

    STORE.log("=" * 56)
    STORE.log("JT808 电子围栏追踪台启动")

    if args.tcp:
        threading.Thread(target=tcp_server, args=(args.tcp,),
                         daemon=True).start()
    else:
        STORE.log("未开启设备接入端口（--tcp 0）")

    httpd = ThreadingHTTPServer(("0.0.0.0", args.web), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    url = "http://127.0.0.1:%d/" % args.web
    STORE.log("网页 %s" % url)
    with STORE.lock:
        ips = local_ips()
    for ip in ips:
        STORE.log("  局域网访问 http://%s:%d/" % (ip, args.web))
    if args.tcp:
        for ip in ips:
            STORE.log("  设备服务器地址填 %s:%d" % (ip, args.tcp))
    STORE.log("=" * 56)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        STORE.log("已退出")


def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return ips or ["127.0.0.1"]


if __name__ == "__main__":
    main()