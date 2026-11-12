# -*- coding: utf-8 -*-
"""生成 app.ico / app.png —— 只用标准库（zlib 手搓 PNG，ICO 内嵌 PNG）。

不依赖 Pillow。改配色或形状直接改下面的常量，重跑本脚本即可。
"""
import struct
import zlib

SS = 2          # 超采样倍数（抗锯齿）
BASE = 512      # 逻辑画布边长

INK = (15, 46, 77)          # 底色 深蓝
EDGE = (62, 127, 184)       # 外圈描边
FRAME = (120, 200, 255)     # 帧头/帧尾
BAR1 = (255, 255, 255)      # 报文体
BAR2 = (150, 205, 245)
BAR3 = (96, 160, 210)


def rrect(buf, W, x0, y0, x1, y1, r, color):
    """实心圆角矩形（逻辑坐标，内部乘 SS）。"""
    x0, y0, x1, y1, r = x0 * SS, y0 * SS, x1 * SS, y1 * SS, r * SS
    cx0, cy0, cx1, cy1 = x0 + r, y0 + r, x1 - r, y1 - r
    px = bytes(color) + b"\xff"
    for y in range(int(y0), int(y1)):
        dy = 0
        if y < cy0:
            dy = cy0 - y
        elif y > cy1:
            dy = y - cy1
        for x in range(int(x0), int(x1)):
            dx = 0
            if x < cx0:
                dx = cx0 - x
            elif x > cx1:
                dx = x - cx1
            if (dx or dy) and dx * dx + dy * dy > r * r:
                continue
            o = (y * W + x) * 4
            buf[o:o + 4] = px


def png_bytes(w, h, rgba):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def render():
    W = BASE * SS
    buf = bytearray(W * W * 4)

    # 底板：先浅蓝大圆角，再深蓝内芯 —— 得到描边效果
    rrect(buf, W, 12, 12, BASE - 12, BASE - 12, 108, EDGE)
    rrect(buf, W, 22, 22, BASE - 22, BASE - 22, 98, INK)

    # 帧结构：■ ───── ■
    cy = 172
    rrect(buf, W, 102, cy - 38, 174, cy + 38, 12, FRAME)
    rrect(buf, W, 338, cy - 38, 410, cy + 38, 12, FRAME)
    rrect(buf, W, 196, cy - 9, 316, cy + 9, 8, FRAME)

    # 报文体三条
    for yy, col, x1 in ((280, BAR1, 402), (330, BAR2, 402), (380, BAR3, 316)):
        rrect(buf, W, 104, yy, x1, yy + 26, 12, col)

    # 降采样（box filter）
    out = bytearray(BASE * BASE * 4)
    n = SS * SS
    for y in range(BASE):
        for x in range(BASE):
            r = g = b = a = 0
            base = ((y * SS) * W + x * SS) * 4
            for dy in range(SS):
                row = base + dy * W * 4
                for dx in range(SS):
                    o = row + dx * 4
                    r += buf[o]
                    g += buf[o + 1]
                    b += buf[o + 2]
                    a += buf[o + 3]
            o2 = (y * BASE + x) * 4
            out[o2:o2 + 4] = bytes((r // n, g // n, b // n, a // n))
    return out


def main():
    rgba = render()
    full = png_bytes(BASE, BASE, rgba)
    with open("app.png", "wb") as f:
        f.write(full)

    blobs = []
    for s in [16, 24, 32, 48, 64, 128, 256]:
        if s == BASE:
            blobs.append((s, full))
            continue
        small = bytearray(s * s * 4)
        for y in range(s):
            sy = y * BASE // s
            for x in range(s):
                sx = x * BASE // s
                so = (sy * BASE + sx) * 4
                do = (y * s + x) * 4
                small[do:do + 4] = rgba[so:so + 4]
        blobs.append((s, png_bytes(s, s, small)))

    offset = 6 + 16 * len(blobs)
    dirs, data = b"", b""
    for s, blob in blobs:
        w = 0 if s >= 256 else s
        dirs += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        data += blob
    ico = struct.pack("<HHH", 0, 1, len(blobs)) + dirs + data
    with open("app.ico", "wb") as f:
        f.write(ico)
    print("app.ico %d bytes / app.png %d bytes" % (len(ico), len(full)))


if __name__ == "__main__":
    main()
