from html import escape
from pathlib import Path


OUT_DIR = Path(r"C:\Users\G1006871\Desktop\BIANYI\outputs")
SVG_CN = OUT_DIR / "三工位OBD测试工装双层概念图_V3_真正可编辑.svg"
SVG_EN = OUT_DIR / "OBD_double_layer_fixture_V3_editable_vector.svg"

W, H = 1920, 1080

BG = "#f4f7fa"
TABLE = "#e8edf2"
LINE = "#c8d4e0"
INK = "#1e2a34"
MUTED = "#5b697a"
DARK = "#22303d"
DARK_2 = "#303e4c"
RED = "#de483e"
ORANGE = "#ee8426"
YELLOW = "#e0b12a"
GREEN = "#1fa05a"
BLUE = "#0091dc"
GRAY = "#9fb1c3"
WHITE = "#ffffff"
GOLD = "#c9922f"


def rect(x, y, w, h, rx=18, fill=WHITE, stroke=LINE, sw=2, cls="", filt=False):
    f = ' filter="url(#shadow)"' if filt else ""
    return (
        f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{f}/>'
    )


def text(x, y, value, size=18, fill=INK, weight=400, anchor="start", cls=""):
    return (
        f'<text class="{cls}" x="{x}" y="{y}" font-family="Microsoft YaHei, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">'
        f'{escape(value)}</text>'
    )


def line(x1, y1, x2, y2, color, width=4, dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round"{dash_attr}/>'
    )


def circle(cx, cy, r, fill, stroke="none", sw=0, cls=""):
    return f'<circle class="{cls}" cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def path(points, color, width=8, cls="wire", endpoints=True):
    d = "M " + " L ".join(f"{x},{y}" for x, y in points)
    parts = [
        f'<path class="{cls} shadow-line" d="{d}" fill="none" stroke="#000" stroke-opacity=".25" '
        f'stroke-width="{width + 5}" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<path class="{cls}" d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>',
    ]
    if endpoints:
        for x, y in (points[0], points[-1]):
            parts.append(circle(x, y, 9, color, WHITE, 2, "wire-port"))
    return "\n".join(parts)


def tag(cx, cy, value, color, w=None):
    width = w or max(86, len(value) * 14)
    return (
        f'<g class="tag" data-label="{escape(value)}">'
        f'{rect(cx - width / 2, cy - 17, width, 34, 8, WHITE, "#bdd9ef", 1)}'
        f'{text(cx, cy + 6, value, 17, color, 700, "middle")}'
        f'</g>'
    )


def terminal(cx, cy, label, color):
    return (
        f'<g class="terminal" data-label="{escape(label)}">'
        f'{circle(cx, cy, 20, "#f7f9fb", color, 5)}'
        f'{circle(cx, cy, 9, color)}'
        f'{text(cx, cy + 55, label, 17, color, 700, "middle")}'
        f'</g>'
    )


def obd_socket(cx, cy, scale=0.86):
    w, h = 150 * scale, 66 * scale
    x, y = cx - w / 2, cy - h / 2
    pins = []
    for row in range(2):
        for col in range(8):
            px = x + 20 * scale + col * (w - 40 * scale) / 7
            py = y + 20 * scale + row * 25 * scale
            pins.append(circle(px, py, 5 * scale, "#c4cfda"))
    return (
        f'<g class="obd-socket" data-name="OBD-II母口">'
        f'{rect(x, y, w, h, 10, "#121b24", "#8c9eb0", 2)}'
        + "".join(pins)
        + f'{text(cx, y + h + 30, "OBD-II 母口", 16, "#dce8f3", 400, "middle")}'
        + "</g>"
    )


def clamp(x, y, w, h):
    return (
        f'<g class="tablet-clamp">'
        f'{rect(x, y, w, h, 14, "#f7f9fb", GRAY, 2)}'
        f'{rect(x + 18, y + 15, w - 36, 23, 8, "#ccd8e4", "#ccd8e4", 0)}'
        f'{rect(x + 38, y + 47, w - 76, h - 65, 8, "#aebed0", "#aebed0", 0)}'
        f'{text(x + w / 2, y + h - 2, "平板夹 / 设备固定", 16, MUTED, 400, "middle")}'
        f'</g>'
    )


def via(cx, cy, label=None):
    parts = [
        f'<g class="through-board-terminal">',
        circle(cx, cy, 12, "#eff9ff", BLUE, 4),
        circle(cx, cy, 5, BLUE),
    ]
    if label:
        parts.append(tag(cx, cy + 36, label, BLUE, 112))
    parts.append("</g>")
    return "\n".join(parts)


def copper_post(x, y1=575, y2=625):
    return (
        f'<g class="copper-post">'
        f'{line(x, y1, x, y2, GOLD, 12)}'
        f'{circle(x, y1, 18, "#fff1c6", GOLD, 4)}{circle(x, y1, 7, GOLD)}'
        f'{circle(x, y2, 18, "#fff1c6", GOLD, 4)}{circle(x, y2, 7, GOLD)}'
        f'</g>'
    )


def f1_module(i, y):
    return (
        f'<g class="f1-module" data-name="日志模块{i}">'
        f'{rect(1485, y - 76, 307, 152, 20, WHITE, LINE, 2, filt=True)}'
        f'{rect(1518, y - 43, 70, 86, 10, DARK, "#46586a", 2)}'
        f'{text(1553, y + 8, "F-1", 24, "#53f485", 700, "middle")}'
        f'{text(1615, y - 8, f"日志模块 {i}", 24, INK, 700)}'
        f'{text(1615, y + 30, "固定座 / OBD数据采集", 16, MUTED)}'
        f'</g>'
    )


def build_svg():
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        "<defs>",
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
        '<feDropShadow dx="8" dy="12" stdDeviation="9" flood-color="#000000" flood-opacity=".14"/>'
        "</filter>",
        '<style>.wire,.wire-port,.tag,.terminal,.copper-post,.through-board-terminal,.f1-module,.station,.layer{vector-effect:non-scaling-stroke;} text{dominant-baseline:auto;}</style>',
        "</defs>",
        rect(0, 0, W, H, 0, BG, BG, 0),
        rect(35, 32, W - 70, H - 74, 38, TABLE, "#d7e2eb", 2),
        text(78, 112, "三工位 OBD 测试工装双层概念图", 42, INK, 700),
        text(80, 150, "第一层安装接口与夹具，第二层做底部走线；两层通过铜柱分隔、穿板端子连接", 19, MUTED),
    ]

    # Left power chain.
    out += [
        f'<g class="power-source">{rect(70, 165, 410, 157, 24, WHITE, LINE, 2, filt=True)}'
        f'{rect(100, 202, 350, 76, 14, DARK, "#46586a", 2)}'
        f'{text(126, 264, "外置 220V 便携电源", 32, "#f0f8ff", 700)}'
        f'{text(126, 312, "AC 220V 输出 / 移动供电", 19, "#6fbfe6")}'
        f'{circle(421, 235, 19, "#fff5f4", RED, 3)}{text(421, 242, "AC", 17, RED, 700, "middle")}</g>',
        f'<g class="power-distribution">{rect(70, 430, 410, 270, 24, WHITE, LINE, 2, filt=True)}'
        f'{rect(70, 430, 14, 270, 7, ORANGE, ORANGE, 0)}'
        f'{text(112, 515, "逆变 / 12V分配模块", 32, INK, 700)}'
        f'{text(112, 547, "220VAC 输入，输出 4 路 12V DC", 19, MUTED)}',
    ]
    for i, y in enumerate([568, 608, 648, 688], start=1):
        out += [
            rect(112, y - 16, 114, 32, 8, "#fffaf0", YELLOW, 2),
            text(169, y + 6, f"12V OUT-{i}", 17, YELLOW, 700, "middle"),
            line(245, y, 430, y, YELLOW, 6),
        ]
    out.append("</g>")

    # Fixture layers.
    out += [
        f'<g class="layer bottom-routing-layer">{rect(535, 585, 840, 380, 30, "#eef5fa", "#9bb2c8", 3, filt=True)}'
        f'{rect(565, 625, 780, 305, 22, "#dfeaf3", "#9bb2c8", 2)}'
        f'{text(595, 710, "第二层：底部走线层", 32, INK, 700)}'
        f'{text(598, 730, "12V电源、PWR/GND、OBD数据线从底部集中走线，减少上层交叉", 19, MUTED)}</g>',
        f'<g class="layer top-interface-layer">{rect(535, 145, 840, 430, 30, DARK, "#4e647a", 3, filt=True)}'
        f'{rect(565, 185, 780, 355, 22, DARK_2, "#677c91", 2)}'
        f'{text(595, 268, "第一层：安装 / 接口层", 32, "#f5f8fc", 700)}'
        f'{text(598, 292, "3组OBD-II母口 / 平板夹 / 设备槽位", 19, "#a8e0f6")}'
        f'{rect(990, 206, 285, 90, 14, "#f7f9fb", "#b2bfcd", 2)}'
        f'{text(1016, 270, "顶部正负极端子", 24, INK, 700)}'
        f'{terminal(1185, 269, "+12V", RED)}{terminal(1240, 269, "GND", "#1a1f25")}</g>',
    ]

    for idx, cx in enumerate([685, 955, 1225], start=1):
        out += [
            f'<g class="station" data-station="{idx}">',
            rect(cx - 118, 310, 236, 215, 18, "#263646", "#5b7288", 2),
            text(cx, 357, f"工位 {idx}", 24, "#f5f8fc", 700, "middle"),
            clamp(cx - 94, 372, 188, 84),
            obd_socket(cx, 493, 0.86),
            via(cx, 558),
            line(cx, 570, cx, 635, BLUE, 4, "12 8"),
            via(cx, 650, f"穿板端子-{idx}"),
            "</g>",
        ]

    out += [copper_post(x) for x in [575, 795, 1115, 1335]]
    out.append(tag(670, 604, "铜柱隔离", GOLD, 92))
    out.append(tag(1215, 628, "上层端子供电", YELLOW, 126))

    # Right F-1 zone.
    out += [
        f'<g class="f1-zone">{rect(1430, 165, 405, 800, 30, WHITE, LINE, 2, filt=True)}'
        f'{rect(1430, 165, 14, 800, 7, GREEN, GREEN, 0)}'
        f'{text(1480, 268, "安服优 F-1", 32, INK, 700)}'
        f'{text(1480, 290, "日志存储模块固定区（三组）", 19, MUTED)}'
        f'{f1_module(1, 355)}{f1_module(2, 585)}{f1_module(3, 815)}</g>'
    ]

    # Wires.
    out += [
        f'<g class="wires ac-power">{path([(275, 322), (275, 385), (275, 430)], RED, 9)}{tag(335, 382, "220V AC", RED, 88)}</g>',
        f'<g class="wires bottom-power">',
        path([(430, 568), (500, 568), (500, 770), (1185, 770), (1185, 625)], YELLOW, 7),
        tag(610, 770, "12V OUT-1", YELLOW, 112),
        path([(430, 608), (500, 608), (500, 805), (685, 805), (685, 650)], ORANGE, 7),
        tag(610, 805, "12V OUT-2", ORANGE, 112),
        path([(430, 648), (500, 648), (500, 840), (955, 840), (955, 650)], ORANGE, 7),
        tag(610, 840, "12V OUT-3", ORANGE, 112),
        path([(430, 688), (500, 688), (500, 875), (1225, 875), (1225, 650)], ORANGE, 7),
        tag(610, 875, "12V OUT-4", ORANGE, 112),
        "</g>",
        f'<g class="wires obd-data">',
        path([(685, 650), (685, 900), (1418, 900), (1418, 355), (1485, 355)], GREEN, 7),
        path([(955, 650), (955, 872), (1426, 872), (1426, 585), (1485, 585)], GREEN, 7),
        path([(1225, 650), (1225, 844), (1434, 844), (1434, 815), (1485, 815)], GREEN, 7),
        tag(1010, 914, "底部OBD数据走线 -> F-1", GREEN, 220),
        "</g>",
    ]

    # Legend.
    out += [
        f'<g class="legend">{rect(92, 750, 388, 180, 20, WHITE, LINE, 2)}'
        f'{text(124, 830, "双层结构说明", 24, INK, 700)}'
        f'{text(126, 856, "第一层", 17, BLUE, 700)}{text(198, 856, "接口/夹具/设备槽位", 16, INK)}'
        f'{text(126, 886, "第二层", 17, ORANGE, 700)}{text(198, 886, "底部走线与分配", 16, INK)}'
        f'{text(126, 916, "铜柱", 17, YELLOW, 700)}{text(198, 916, "上下层机械隔离", 16, INK)}'
        f'{text(126, 946, "穿板端子", 17, BLUE, 700)}{text(198, 946, "上下层电气连接", 16, INK)}</g>',
    ]

    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    svg = build_svg()
    SVG_CN.write_text(svg, encoding="utf-8")
    SVG_EN.write_text(svg, encoding="utf-8")
    print(SVG_CN)
    print(SVG_EN)
