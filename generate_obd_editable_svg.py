from html import escape
from pathlib import Path


OUT = Path(r"C:\Users\G1006871\Desktop\BIANYI\outputs\OBD测试工装核心连接图_可编辑.svg")
W, H = 1600, 900


def tspan(text):
    return escape(text)


def rect(x, y, w, h, rx=18, fill="#fff", stroke="#c8d4e0", sw=2, cls=""):
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def text(x, y, value, size=18, fill="#1e2a34", weight=400, anchor="start", cls=""):
    return (
        f'<text class="{cls}" x="{x}" y="{y}" font-family="Microsoft YaHei, Arial" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{tspan(value)}</text>'
    )


def line_path(points, color, width=6, cls="wire"):
    d = "M " + " L ".join(f"{x},{y}" for x, y in points)
    return f'<path class="{cls}" d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def port(cx, cy, color):
    return f'<circle class="port" cx="{cx}" cy="{cy}" r="8" fill="{color}" stroke="#fff" stroke-width="2"/>'


def label(cx, cy, value, color):
    # Approximate width for edit-friendly centered label boxes.
    width = max(52, len(value) * 15)
    height = 28
    x = cx - width / 2
    y = cy - height / 2
    return (
        f'<g class="label" data-label="{tspan(value)}">'
        f'{rect(x, y, width, height, 7, "#ffffff", "#bdd9ef", 1)}'
        f'{text(cx, cy + 6, value, 16, color, 700, "middle")}'
        f'</g>'
    )


def device_card(x, y, w, h, title, subtitle="", accent="#0091dc", cls="device"):
    parts = [f'<g class="{cls}" data-name="{tspan(title)}">']
    parts.append(rect(x, y, w, h, 20, "#ffffff", "#c8d4e0", 2))
    parts.append(rect(x, y, 12, h, 6, accent, accent, 0))
    parts.append(text(x + 34, y + 44, title, 24, "#1e2a34", 700))
    if subtitle:
        parts.append(text(x + 34, y + 76, subtitle, 18, "#5b697a"))
    parts.append("</g>")
    return "\n".join(parts)


def pc():
    x, y, w, h = 70, 80, 360, 205
    parts = ['<g class="device pc" data-name="PC电脑">']
    parts.append(rect(x, y, w, h, 22, "#ffffff", "#c8d4e0", 2))
    parts.append(rect(x + 28, y + 26, w - 56, 108, 12, "#192737", "#46586a", 2))
    parts.append(text(x + 52, y + 88, "PC电脑", 35, "#f0f8ff", 700))
    parts.append(text(x + 52, y + 125, "控制 CAN / UART / PPS / Relay", 18, "#94d8f5"))
    parts.append(rect(x + 112, y + 150, 176, 18, 5, "#ccd8e4", "#ccd8e4", 0))
    parts.append(rect(x + 78, y + 168, 224, 16, 8, "#aebed0", "#aebed0", 0))
    parts.append("</g>")
    return "\n".join(parts)


def pps():
    x, y, w, h = 70, 590, 360, 215
    parts = ['<g class="device pps" data-name="PPS">']
    parts.append(rect(x, y, w, h, 22, "#ffffff", "#c8d4e0", 2))
    parts.append(rect(x + 28, y + 28, w - 56, 72, 12, "#16222a", "#4b5a69", 2))
    parts.append(text(x + 50, y + 72, "13.8V", 24, "#53f485", 700))
    parts.append(text(x + 172, y + 72, "2.00A", 24, "#53f485", 700))
    parts.append(text(x + 38, y + 150, "可编程程控电源 PPS", 24, "#1e2a34", 700))
    parts.append(text(x + 38, y + 182, "USB通讯，POWER/GND输出", 18, "#5b697a"))
    parts.append("</g>")
    return "\n".join(parts)


def ac_power():
    x, y, w, h = 70, 420, 280, 95
    parts = ['<g class="device ac-power" data-name="220V电源">']
    parts.append(rect(x, y, w, h, 18, "#ffffff", "#c8d4e0", 2))
    parts.append(rect(x, y, 10, h, 5, "#de483e", "#de483e", 0))
    parts.append(f'<circle cx="{x+52}" cy="{y+48}" r="24" fill="#fff5f4" stroke="#de483e" stroke-width="3"/>')
    parts.append(text(x + 52, y + 54, "AC", 15, "#de483e", 700, "middle"))
    parts.append(text(x + 190, y + 57, "220V电源", 24, "#1e2a34", 700, "middle"))
    parts.append(rect(x + 214, y + 28, 38, 39, 6, "#fffafa", "#de483e", 2))
    parts.append(f'<line x1="{x+228}" y1="{y+42}" x2="{x+228}" y2="{y+54}" stroke="#de483e" stroke-width="3"/>')
    parts.append(f'<line x1="{x+240}" y1="{y+42}" x2="{x+240}" y2="{y+54}" stroke="#de483e" stroke-width="3"/>')
    parts.append("</g>")
    return "\n".join(parts)


def obd():
    x, y, w, h = 970, 165, 545, 340
    parts = ['<g class="device obd" data-name="后装 OBD 设备">']
    parts.append(rect(x, y, w, h, 28, "#212c38", "#4e647a", 3))
    parts.append(rect(x + 24, y + 28, w - 48, h - 56, 18, "#303d4b", "#677c91", 2))
    parts.append(text(x + 42, y + 82, "后装 OBD 设备", 35, "#f5f8fc", 700))
    parts.append(text(x + 44, y + 114, "CAN / Debug / Power / ACC", 18, "#a8e0f6"))
    parts.append(rect(x + 46, y + h - 108, 114, 52, 8, "#121b24", "#8c9eb0", 2))
    # OBD connector pins
    for row in range(2):
        for col in range(6):
            parts.append(f'<circle cx="{x+62+col*17}" cy="{y+h-93+row*19}" r="5" fill="#c4cfda"/>')
    # Harness panel
    hx, hy = x + w - 178, y + 112
    parts.append(rect(hx, hy, 150, h - 158, 12, "#f7f9fb", "#b2bfcd", 2))
    parts.append(text(hx + 18, hy + 34, "OBD线束", 18, "#1e2a34"))
    for i, (name, col) in enumerate([("CAN_H", "#1fa05a"), ("CAN_L", "#1fa05a"), ("ACC", "#ee8426"), ("POWER", "#de483e")]):
        yy = hy + 55 + i * 35
        parts.append(f'<line x1="{hx+18}" y1="{yy}" x2="{hx+52}" y2="{yy}" stroke="{col}" stroke-width="7"/>')
        parts.append(text(hx + 64, yy + 5, name, 16, "#1e2a34"))
    parts.append("</g>")
    return "\n".join(parts)


def uart():
    return device_card(560, 300, 340, 105, "UART转USB模块", "TX/RX/GND Debug口", "#7856cd", "device uart")


def relay():
    return device_card(1040, 590, 355, 120, "继电器Relay模块", "PC控制，输出ACC", "#ee8426", "device relay")


def dc():
    x, y, w, h = 1040, 750, 355, 90
    parts = ['<g class="device dc-power" data-name="12V外置电源">']
    parts.append(rect(x, y, w, h, 18, "#ffffff", "#c8d4e0", 2))
    parts.append(rect(x, y, 10, h, 5, "#e0b12a", "#e0b12a", 0))
    parts.append(rect(x + 32, y + 29, 54, 52, 8, "#18222c", "#465462", 2))
    parts.append(text(x + 59, y + 59, "12V", 15, "#54f284", 700, "middle"))
    parts.append(text(x + 232, y + 56, "12V外置电源", 24, "#1e2a34", 700, "middle"))
    parts.append("</g>")
    return "\n".join(parts)


svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
    "<defs>",
    "<style>",
    ".device { filter: drop-shadow(8px 12px 12px rgba(0,0,0,.14)); }",
    ".wire { fill:none; stroke-linecap:round; stroke-linejoin:round; }",
    "text { dominant-baseline:auto; }",
    "</style>",
    "</defs>",
    f'<rect x="0" y="0" width="{W}" height="{H}" fill="#f4f7fa"/>',
    rect(32, 32, W - 64, H - 64, 34, "#e8edf2", "#d7e2eb", 2),
]

# Devices
svg += [pc(), ac_power(), pps(), device_card(560, 78, 340, 110, "CANalyst-II分析仪", "USB转CAN，接OBD CAN口", "#1fa05a", "device canalyst"), uart(), obd(), relay(), dc()]

# Ports
ports = {
    "pc_can": (430, 138, "#0091dc"), "pc_relay": (430, 198, "#0091dc"), "pc_uart": (430, 250, "#0091dc"), "pc_pps": (430, 282, "#0091dc"),
    "can_usb": (560, 138, "#0091dc"), "can_out": (900, 132, "#1fa05a"), "obd_can": (970, 286, "#1fa05a"),
    "obd_power": (970, 405, "#de483e"), "obd_debug": (970, 350, "#7856cd"), "obd_acc": (1310, 505, "#ee8426"),
    "ac_out": (250, 515, "#de483e"), "pps_ac": (250, 590, "#de483e"), "pps_usb": (430, 650, "#0091dc"), "pps_power": (430, 776, "#de483e"),
    "uart_usb": (560, 350, "#0091dc"), "uart_out": (900, 350, "#7856cd"),
    "relay_ctrl": (1395, 610, "#0091dc"), "relay_acc": (1395, 650, "#ee8426"),
    "relay_power": (1218, 710, "#e0b12a"), "dc_power": (1218, 750, "#e0b12a"),
}

# Wires, each as independently editable path.
svg += [
    line_path([(430, 138), (560, 138)], "#0091dc", 7, "wire usb pc-to-canalyst"), label(495, 110, "USB", "#0091dc"),
    line_path([(900, 132), (935, 132), (935, 286), (970, 286)], "#1fa05a", 8, "wire can canalyst-to-obd"), label(937, 210, "CAN_H / CAN_L", "#1fa05a"),
    line_path([(430, 282), (430, 650)], "#0091dc", 7, "wire usb pc-to-pps"), label(398, 466, "USB通讯", "#0091dc"),
    line_path([(430, 250), (515, 250), (515, 350), (560, 350)], "#0091dc", 7, "wire usb pc-to-uart"), label(536, 300, "USB", "#0091dc"),
    line_path([(900, 350), (970, 350)], "#7856cd", 8, "wire debug uart-to-obd"), label(935, 375, "TX / RX / GND", "#7856cd"),
    line_path([(250, 515), (250, 590)], "#de483e", 8, "wire ac-to-pps"), label(294, 552, "220V电源", "#de483e"),
    line_path([(430, 776), (940, 776), (940, 405), (970, 405)], "#de483e", 9, "wire power-pps-to-obd"), label(720, 796, "POWER / GND", "#de483e"),
    line_path([(430, 198), (500, 198), (500, 66), (1535, 66), (1535, 610), (1395, 610)], "#0091dc", 4, "wire control-pc-to-relay"), label(1010, 66, "控制IO / 串口", "#0091dc"),
    line_path([(1395, 650), (1460, 650), (1460, 505), (1310, 505)], "#ee8426", 9, "wire acc-relay-to-obd"), label(1460, 580, "ACC信号线", "#ee8426"),
    line_path([(1218, 750), (1218, 710)], "#e0b12a", 8, "wire power-12v-to-relay"), label(1218, 730, "12V供电", "#e0b12a"),
]
svg += [port(x, y, color) for x, y, color in ports.values()]
svg.append("</svg>")

OUT.write_text("\n".join(svg), encoding="utf-8")
print(OUT)
