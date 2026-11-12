# -*- coding: utf-8 -*-
"""
JT808 设备模拟器 —— 冒充一台车上终端，把位置打到追踪台上去。

用途：
  1. 手上没设备时，用它验证平台能不能收、地图能不能画；
  2. 验证围栏判定（可以让车故意在围栏内/外走一圈）。

用法：
    python sim_device.py                       # 连 127.0.0.1:7611，绕圈跑
    python sim_device.py --host 10.0.0.5 --port 7611 --phone 13800138000
    python sim_device.py --route line          # 直线跑
    python sim_device.py --once                # 只发一个点，然后退出

坐标为 WGS84，与平台内部约定一致。
"""
import argparse
import math
import socket
import struct
import sys
import time

sys.path.insert(0, ".")
from server import checksum, split_frames, unescape_bytes  # noqa: E402


def bcd(s, n=12):
    s = "".join(c for c in str(s) if c.isdigit())
    s = s.ljust(n, "0")[:n]
    if len(s) % 2:
        s += "0"
    return bytes(int(s[i:i + 2], 16) for i in range(0, len(s), 2))


def frame(msg_id, phone, seq, body):
    """与 server.build_packet 等价，这里单独实现一遍便于对照。"""
    FLAG, ESC, EF, EE = 0x7E, 0x7D, 0x02, 0x01
    prop = len(body) & 0x3FF
    head = struct.pack(">HH", msg_id, prop) + bcd(phone) + struct.pack(">H", seq & 0xFFFF)
    raw = head + body
    raw += bytes([checksum(raw)])
    out = bytearray([FLAG])
    for b in raw:
        if b == FLAG:
            out += bytes([ESC, EF])
        elif b == ESC:
            out += bytes([ESC, EE])
        else:
            out.append(b)
    out.append(FLAG)
    return bytes(out)


def bcd_time(t=None):
    t = t or time.localtime()
    return bytes([
        ((t.tm_year // 10) % 10 << 4) | (t.tm_year % 10),
        (t.tm_mon // 10 << 4) | (t.tm_mon % 10),
        (t.tm_mday // 10 << 4) | (t.tm_mday % 10),
        (t.tm_hour // 10 << 4) | (t.tm_hour % 10),
        (t.tm_min // 10 << 4) | (t.tm_min % 10),
        (t.tm_sec // 10 << 4) | (t.tm_sec % 10),
    ])


def body_0200(lat, lon, speed=30.0, altitude=20, direction=0,
              status=0x03, alarm=0, mileage=None):
    """0x0200 消息体。

    固定 28 字节布局（与 server.parse_0200 严格对应）：
      报警 4B | 状态 4B | 纬度 4B | 经度 4B | 高程 2B | 速度 2B | 方向 2B | 时间 6B
    status 默认 0x03 = ACC 开 + 已定位。
    """
    b = struct.pack(">II", alarm, status)
    b += struct.pack(">II", int(round(lat * 1e6)), int(round(lon * 1e6)))
    b += struct.pack(">HHH", altitude, int(round(speed * 10)), int(direction) % 360)
    b += bcd_time()
    if mileage is not None:
        b += bytes([0x01, 0x04]) + struct.pack(">I", int(mileage * 10))
    return b


def body_0100(phone, plate=""):
    """0x0100 注册体，严格按国标布局：
       省域 2B | 市域 2B | 制造商 5B | 终端型号 20B | 终端ID 7B | 车牌色 1B | 车牌
    """
    b = struct.pack(">HH", 32, 3201)                 # 江苏 / 南京
    b += b"SIM01"                                     # 制造商 5B
    b += b"JT808-SIM".ljust(20, b"\x00")              # 终端型号 20B
    b += bcd(phone, 14)                               # 终端ID 7B（BCD）
    b += bytes([0x02])                                # 车牌颜色 2=蓝色
    b += plate.encode("gbk")[:15].ljust(15, b"\x00")
    return b


class Sim:
    def __init__(self, host, port, phone, plate):
        self.host, self.port, self.phone, self.plate = host, port, phone, plate
        self.seq = 0
        self.sock = None
        self.ack_code = None

    def next_seq(self):
        self.seq = (self.seq + 1) & 0xFFFF
        return self.seq

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=8)
        self.sock.settimeout(8)
        print("[sim] 已连接 %s:%d" % (self.host, self.port))

    def send(self, msg_id, body):
        seq = self.next_seq()
        self.sock.sendall(frame(msg_id, self.phone, seq, body))
        return seq

    def drain(self, timeout=1.2):
        """读一下应答，顺便把 0x8100 的鉴权码捞出来。"""
        self.sock.settimeout(timeout)
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            try:
                d = self.sock.recv(2048)
                if not d:
                    break
                buf += d
            except socket.timeout:
                break
        frames, _ = split_frames(buf)
        for raw in frames:
            try:
                p = parse_packet(raw)
            except Exception:
                continue
            if p["msg_id"] == 0x8100 and len(p["body"]) >= 3:
                self.ack_code = struct.unpack(">H", p["body"][1:3])[0]
                print("[sim] 注册应答 0x8100 成功，鉴权码 %04X" % self.ack_code)
            elif p["msg_id"] == 0x8001:
                print("[sim] 通用应答 0x8001")
        return buf

    def register(self):
        self.send(0x0100, body_0100(self.phone, self.plate))
        print("[sim] 发 0x0100 注册，终端 %s 车牌 %s" % (self.phone, self.plate))
        self.drain()

    def heartbeat(self):
        self.send(0x0002, b"")
        print("[sim] 发 0x0002 心跳")

    def location(self, lat, lon, **kw):
        self.send(0x0200, body_0200(lat, lon, **kw))
        print("[sim] 发 0x0200 位置 (%.6f, %.6f) 速度 %.1f" %
              (lat, lon, kw.get("speed", 30.0)))
        self.drain(0.25)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def circle_route(c_lat, c_lon, r_m, n, i):
    """绕圆心走一圈，半径 r_m。"""
    ang = 2 * math.pi * i / max(1, n)
    dlat = (r_m * math.cos(ang)) / 111320.0
    dlon = (r_m * math.sin(ang)) / (111320.0 * math.cos(math.radians(c_lat)))
    return c_lat + dlat, c_lon + dlon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7611)
    ap.add_argument("--phone", default="13800138000")
    ap.add_argument("--plate", default="苏A12345")
    ap.add_argument("--lat", type=float, default=31.230416)
    ap.add_argument("--lon", type=float, default=121.473701)
    ap.add_argument("--route", default="circle", choices=["circle", "line", "still"])
    ap.add_argument("--radius", type=float, default=260.0, help="绕圈半径（米）")
    ap.add_argument("--speed", type=float, default=36.0)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    sim = Sim(args.host, args.port, args.phone, args.plate)
    sim.connect()
    sim.register()

    if args.once:
        sim.location(args.lat, args.lon, speed=0)
        time.sleep(0.6)
        sim.drain(1.0)
        sim.close()
        print("[sim] 单点发送完毕")
        return

    i = 0
    try:
        while True:
            if args.route == "circle":
                lat, lon = circle_route(args.lat, args.lon, args.radius, 48, i)
            elif args.route == "line":
                lat = args.lat + i * 0.00012
                lon = args.lon + i * 0.00012
            else:
                lat, lon = args.lat, args.lon
            sim.seq % 20 == 0 and sim.heartbeat()
            sim.location(lat, lon, speed=args.speed if args.route != "still" else 0,
                         direction=(i * 7) % 360, mileage=i * 0.02)
            i += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[sim] 停止")
    finally:
        sim.close()


if __name__ == "__main__":
    main()