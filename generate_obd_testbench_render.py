from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os


OUT_DIR = r"C:\Users\G1006871\Desktop\BIANYI\outputs"
OUT_PATH = os.path.join(OUT_DIR, "OBD测试工装核心连接图_V15.png")
W, H = 1600, 900


def font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_BIG = font(35, True)
F_DEVICE = font(24, True)
F_BODY = font(18)
F_SMALL = font(16)
F_TAG = font(15, True)

BG = (244, 247, 250)
TABLE = (232, 237, 242)
INK = (30, 40, 52)
MUTED = (91, 105, 122)
PANEL = (255, 255, 255)
LINE = (200, 212, 224)
USB = (0, 145, 220)
CAN = (31, 160, 90)
DEBUG = (120, 86, 205)
POWER = (222, 72, 62)
ACC = (238, 132, 38)
AUX = (224, 177, 36)
DARK = (33, 44, 56)


def text_center(draw, box, text, fnt, fill=INK):
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x1 + (x2 - x1 - tw) / 2, y1 + (y2 - y1 - th) / 2), text, font=fnt, fill=fill)


def card(draw, box, radius=22, fill=PANEL, outline=LINE, width=2):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(layer)
    x1, y1, x2, y2 = box
    sd.rounded_rectangle((x1 + 8, y1 + 12, x2 + 8, y2 + 12), radius, fill=(0, 0, 0, 32))
    layer = layer.filter(ImageFilter.GaussianBlur(12))
    img.alpha_composite(layer)
    draw.rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)


def label(draw, xy, text, color):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=F_SMALL)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box = (x - tw / 2 - 10, y - th / 2 - 6, x + tw / 2 + 10, y + th / 2 + 6)
    draw.rounded_rectangle(box, 8, fill=(255, 255, 255, 242), outline=(214, 224, 233), width=1)
    draw.text((x - tw / 2, y - th / 2), text, font=F_SMALL, fill=color)


def port(draw, xy, color):
    x, y = xy
    draw.rounded_rectangle((x - 8, y - 8, x + 8, y + 8), 4, fill=color, outline=(255, 255, 255), width=2)


def cable(draw, pts, color, text, label_xy, width=7):
    draw.line(pts, fill=(0, 0, 0, 42), width=width + 5, joint="curve")
    draw.line(pts, fill=color, width=width, joint="curve")
    for x, y in [pts[0], pts[-1]]:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color, outline=(255, 255, 255), width=2)
    if text and label_xy:
        label(draw, label_xy, text, color)


def laptop(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 24)
    screen = (x1 + 28, y1 + 26, x2 - 28, y2 - 70)
    draw.rounded_rectangle(screen, 12, fill=(25, 39, 55), outline=(70, 88, 106), width=2)
    draw.text((screen[0] + 24, screen[1] + 36), "PC电脑", font=F_BIG, fill=(240, 248, 255))
    draw.text((screen[0] + 24, screen[1] + 84), "控制 CAN / UART / PPS / Relay", font=F_BODY, fill=(148, 216, 245))
    for i, c in enumerate([USB, CAN, ACC]):
        draw.ellipse((screen[0] + 22 + i * 24, screen[1] + 18, screen[0] + 34 + i * 24, screen[1] + 30), fill=c)
    draw.rectangle((x1 + 112, y2 - 56, x2 - 112, y2 - 36), fill=(204, 216, 228))
    draw.rounded_rectangle((x1 + 78, y2 - 40, x2 - 78, y2 - 24), 8, fill=(174, 190, 204))


def canalyst(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 20)
    draw.rounded_rectangle((x1, y1, x1 + 12, y2), 7, fill=CAN)
    draw.rounded_rectangle((x1 + 30, y1 + 34, x1 + 90, y1 + 86), 10, fill=(234, 249, 240), outline=CAN, width=3)
    text_center(draw, (x1 + 30, y1 + 34, x1 + 90, y1 + 86), "CAN", F_TAG, CAN)
    draw.text((x1 + 110, y1 + 34), "CANalyst-II分析仪", font=F_DEVICE, fill=INK)
    draw.text((x1 + 110, y1 + 68), "USB转CAN，接OBD CAN口", font=F_BODY, fill=MUTED)


def pps(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 22)
    draw.rounded_rectangle((x1 + 28, y1 + 28, x2 - 28, y1 + 100), 12, fill=(22, 34, 42), outline=(75, 90, 105), width=2)
    draw.text((x1 + 50, y1 + 46), "13.8V", font=F_DEVICE, fill=(83, 244, 133))
    draw.text((x1 + 172, y1 + 46), "2.00A", font=F_DEVICE, fill=(83, 244, 133))
    draw.text((x1 + 38, y1 + 126), "可编程程控电源 PPS", font=F_DEVICE, fill=INK)
    draw.text((x1 + 38, y1 + 160), "USB通讯，POWER/GND输出", font=F_BODY, fill=MUTED)
    draw.ellipse((x2 - 82, y2 - 42, x2 - 60, y2 - 20), fill=POWER, outline=(255, 255, 255), width=2)
    draw.ellipse((x2 - 48, y2 - 42, x2 - 26, y2 - 20), fill=(26, 30, 35), outline=(255, 255, 255), width=2)


def ac_power(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 18)
    draw.rounded_rectangle((x1, y1, x1 + 10, y2), 6, fill=POWER)
    draw.ellipse((x1 + 28, y1 + 24, x1 + 78, y1 + 74), fill=(255, 245, 244), outline=POWER, width=3)
    text_center(draw, (x1 + 28, y1 + 24, x1 + 78, y1 + 74), "AC", F_TAG, POWER)
    text_center(draw, (x1 + 92, y1 + 18, x2 - 82, y2 - 18), "220V电源", F_DEVICE, INK)
    # small socket icon to avoid empty right side
    sx1, sy1, sx2, sy2 = x2 - 66, y1 + 28, x2 - 28, y2 - 28
    draw.rounded_rectangle((sx1, sy1, sx2, sy2), 6, fill=(255, 250, 250), outline=POWER, width=2)
    draw.line((sx1 + 14, sy1 + 14, sx1 + 14, sy2 - 14), fill=POWER, width=3)
    draw.line((sx2 - 14, sy1 + 14, sx2 - 14, sy2 - 14), fill=POWER, width=3)


def uart(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 18)
    draw.rounded_rectangle((x1, y1, x1 + 10, y2), 6, fill=DEBUG)
    # small USB-UART board
    bx1, by1 = x1 + 28, y1 + 32
    draw.rectangle((bx1, by1, bx1 + 58, by1 + 42), fill=(239, 241, 245), outline=DEBUG, width=3)
    for i in range(5):
        draw.rectangle((bx1 + 8 + i * 9, by1 - 10, bx1 + 13 + i * 9, by1), fill=(160, 173, 188))
        draw.rectangle((bx1 + 8 + i * 9, by1 + 42, bx1 + 13 + i * 9, by1 + 52), fill=(160, 173, 188))
    draw.text((x1 + 100, y1 + 29), "UART转USB模块", font=F_DEVICE, fill=INK)
    draw.text((x1 + 100, y1 + 63), "TX/RX/GND Debug口", font=F_BODY, fill=MUTED)


def relay(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 20)
    draw.rounded_rectangle((x1, y1, x1 + 12, y2), 7, fill=ACC)
    draw.rounded_rectangle((x1 + 34, y1 + 36, x1 + 64, y1 + 88), 7, fill=(252, 252, 252), outline=ACC, width=3)
    draw.text((x1 + 100, y1 + 36), "继电器Relay模块", font=F_DEVICE, fill=INK)
    draw.text((x1 + 100, y1 + 70), "PC控制，输出ACC", font=F_BODY, fill=MUTED)
    draw.text((x1 + 36, y1 + 103), "ACC", font=F_SMALL, fill=MUTED)


def dc_power(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 18)
    draw.rounded_rectangle((x1, y1, x1 + 10, y2), 6, fill=AUX)
    draw.rounded_rectangle((x1 + 32, y1 + 29, x1 + 86, y1 + 81), 8, fill=(24, 34, 44), outline=(70, 84, 98), width=2)
    text_center(draw, (x1 + 32, y1 + 29, x1 + 86, y1 + 81), "12V", F_TAG, (84, 242, 132))
    text_center(draw, (x1 + 108, y1 + 18, x2 - 18, y2 - 18), "12V外置电源", F_DEVICE, INK)


def obd(draw, box):
    x1, y1, x2, y2 = box
    card(draw, box, 28, fill=DARK, outline=(78, 100, 122), width=3)
    draw.rounded_rectangle((x1 + 24, y1 + 28, x2 - 24, y2 - 28), 18, fill=(48, 61, 75), outline=(103, 124, 145), width=2)
    draw.text((x1 + 42, y1 + 42), "后装 OBD 设备", font=F_BIG, fill=(245, 248, 252))
    draw.text((x1 + 44, y1 + 92), "CAN / Debug / Power / ACC", font=F_BODY, fill=(168, 224, 246))
    # connector
    px, py = x1 + 90, y2 - 82
    draw.rounded_rectangle((px - 44, py - 26, px + 70, py + 26), 8, fill=(18, 27, 36), outline=(140, 158, 176), width=2)
    for row in range(2):
        for col in range(6):
            draw.ellipse((px - 28 + col * 17, py - 12 + row * 19, px - 19 + col * 17, py - 3 + row * 19), fill=(196, 207, 218))
    # harness panel, single ACC
    hx1, hy1, hx2, hy2 = x2 - 178, y1 + 112, x2 - 28, y2 - 46
    draw.rounded_rectangle((hx1, hy1, hx2, hy2), 12, fill=(247, 249, 251), outline=(178, 191, 205), width=2)
    draw.text((hx1 + 18, hy1 + 16), "OBD线束", font=F_BODY, fill=INK)
    for i, (txt, col) in enumerate([("CAN_H", CAN), ("CAN_L", CAN), ("ACC", ACC), ("POWER", POWER)]):
        y = hy1 + 55 + i * 35
        draw.line((hx1 + 18, y, hx1 + 52, y), fill=col, width=7)
        draw.text((hx1 + 64, y - 12), txt, font=F_SMALL, fill=INK)


os.makedirs(OUT_DIR, exist_ok=True)
img = Image.new("RGBA", (W, H), BG + (255,))
draw = ImageDraw.Draw(img)

# core canvas only
draw.rounded_rectangle((32, 32, W - 32, H - 32), 34, fill=TABLE, outline=(215, 226, 235), width=2)
for x in range(80, W + 200, 120):
    draw.line((x, 32, x - 230, H - 32), fill=(224, 231, 238), width=2)

pc_box = (70, 80, 430, 285)
can_box = (560, 78, 900, 188)
obd_box = (970, 165, 1515, 505)
ac_box = (70, 420, 350, 515)
pps_box = (70, 590, 430, 805)
uart_box = (560, 300, 900, 405)
relay_box = (1040, 590, 1395, 710)
dc_box = (1040, 750, 1395, 840)

laptop(draw, pc_box)
canalyst(draw, can_box)
obd(draw, obd_box)
ac_power(draw, ac_box)
pps(draw, pps_box)
uart(draw, uart_box)
relay(draw, relay_box)
dc_power(draw, dc_box)

P = {
    "pc_can": (430, 138),
    "pc_relay": (430, 198),
    "pc_uart": (430, 250),
    "pc_pps": (430, 282),
    "can_usb": (560, 138),
    "can_out": (900, 132),
    "obd_can": (970, 286),
    "obd_power": (970, 405),
    "obd_debug": (970, 350),
    "obd_acc": (1310, 505),
    "ac_out": (250, 515),
    "pps_ac": (250, 590),
    "pps_usb": (430, 650),
    "pps_power": (430, 776),
    "uart_usb": (560, 350),
    "uart_out": (900, 350),
    "relay_ctrl": (1395, 610),
    "relay_acc": (1395, 650),
    "relay_power": (1218, 710),
    "dc_power": (1218, 750),
}

for key, xy in P.items():
    color = USB
    if "can" in key:
        color = CAN
    if "uart" in key or "debug" in key:
        color = DEBUG
    if "power" in key or "ac" in key:
        color = POWER
    if "acc" in key or "relay" in key:
        color = ACC
    if key in ("relay_power", "dc_power"):
        color = AUX
    port(draw, xy, color)

cable(draw, [P["pc_can"], P["can_usb"]], USB, "USB", (495, 110), 7)
cable(draw, [P["can_out"], (935, 132), (935, 286), P["obd_can"]], CAN, "CAN_H / CAN_L", (937, 210), 8)
cable(draw, [P["pc_pps"], P["pps_usb"]], USB, "USB通讯", (398, 466), 7)
cable(draw, [P["pc_uart"], (515, 250), (515, 350), P["uart_usb"]], USB, "USB", (536, 300), 7)
cable(draw, [P["uart_out"], P["obd_debug"]], DEBUG, "TX / RX / GND", (935, 375), 8)
cable(draw, [P["ac_out"], P["pps_ac"]], POWER, "220V电源", (294, 552), 8)
cable(draw, [P["pps_power"], (940, 776), (940, 405), P["obd_power"]], POWER, "POWER / GND", (720, 796), 9)

# PC control to relay, routed along the outer perimeter like the marked reference.
relay_outer = [P["pc_relay"], (500, 198), (500, 66), (1535, 66), (1535, 610), P["relay_ctrl"]]
draw.line(relay_outer, fill=USB, width=4, joint="curve")
label(draw, (1010, 66), "控制IO / 串口", USB)

# Single ACC line and vertical 12V supply connection.
cable(draw, [P["relay_acc"], (1460, 650), (1460, 505), P["obd_acc"]], ACC, "ACC信号线", (1460, 580), 9)
cable(draw, [P["dc_power"], P["relay_power"]], AUX, "12V供电", (1218, 730), 8)

img.convert("RGB").save(OUT_PATH, quality=95)
print(OUT_PATH)
