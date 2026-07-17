from html import escape
from pathlib import Path


OUT_DIR = Path(r"C:\Users\G1006871\Desktop\BIANYI\outputs")
SVG_CN = OUT_DIR / "三工位OBD测试工装双层概念图_V6_分层可编辑.svg"
SVG_EN = OUT_DIR / "OBD_double_layer_fixture_V6_layered_editable.svg"

W, H = 1920, 1080

COLORS = {
    "bg": "#f4f7fa",
    "surface": "#e8edf2",
    "line": "#c8d4e0",
    "ink": "#1e2a34",
    "muted": "#5b697a",
    "dark": "#22303d",
    "dark2": "#303e4c",
    "red": "#de483e",
    "orange": "#ee8426",
    "yellow": "#e0b12a",
    "green": "#1fa05a",
    "blue": "#0091dc",
    "gray": "#9fb1c3",
    "gold": "#c9922f",
    "white": "#ffffff",
}


def e(value):
    return escape(str(value))


def rect(x, y, w, h, rx=16, fill="white", stroke="line", sw=2, extra=""):
    fill = COLORS.get(fill, fill)
    stroke = COLORS.get(stroke, stroke)
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'


def text(x, y, value, size=18, fill="ink", weight=400, anchor="start"):
    fill = COLORS.get(fill, fill)
    return (
        f'<text x="{x}" y="{y}" font-family="Microsoft YaHei, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{e(value)}</text>'
    )


def circle(cx, cy, r, fill, stroke="none", sw=0):
    fill = COLORS.get(fill, fill)
    stroke = COLORS.get(stroke, stroke)
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def line(x1, y1, x2, y2, color, width=4, dash=""):
    color = COLORS.get(color, color)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"{dash_attr}/>'


def path(points, color, width=7, endpoints=True):
    color = COLORS.get(color, color)
    d = "M " + " L ".join(f"{x},{y}" for x, y in points)
    parts = [
        f'<path d="{d}" fill="none" stroke="#000000" stroke-opacity=".24" stroke-width="{width + 4}" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>',
    ]
    if endpoints:
        for x, y in (points[0], points[-1]):
            parts.append(circle(x, y, 8, color, "white", 2))
    return "\n".join(parts)


def tag(cx, cy, label, color="blue", width=None):
    color = COLORS.get(color, color)
    w = width or max(80, len(label) * 14)
    return (
        f'<g class="tag" data-label="{e(label)}">'
        f'{rect(cx - w / 2, cy - 16, w, 32, 7, "white", "#bdd9ef", 1)}'
        f'{text(cx, cy + 6, label, 16, color, 700, "middle")}'
        f'</g>'
    )


def obd_socket(cx, cy, scale=1.0):
    w, h = 150 * scale, 64 * scale
    x, y = cx - w / 2, cy - h / 2
    pins = []
    for row in range(2):
        for col in range(8):
            px = x + 18 * scale + col * (w - 36 * scale) / 7
            py = y + 18 * scale + row * 24 * scale
            pins.append(circle(round(px, 2), round(py, 2), 4.8 * scale, "#c4cfda"))
    return (
        f'<g class="obd_ii_female_port">'
        f'{rect(x, y, w, h, 9, "#121b24", "#8c9eb0", 2)}'
        + "".join(pins)
        + f'{text(cx, y + h + 26, "OBD-II 母口", 15, "#dce8f3", 400, "middle")}'
        + "</g>"
    )


def tablet_clamp(x, y, w, h):
    return (
        f'<g class="tablet_clamp">'
        f'{rect(x, y, w, h, 13, "#f7f9fb", "gray", 2)}'
        f'{rect(x + 18, y + 14, w - 36, 22, 8, "#ccd8e4", "#ccd8e4", 0)}'
        f'{rect(x + 38, y + 46, w - 76, h - 62, 8, "#aebed0", "#aebed0", 0)}'
        f'{text(x + w / 2, y + h - 6, "平板夹 / 设备固定", 15, "muted", 400, "middle")}'
        f'</g>'
    )


def screw_terminal(cx, cy, label, color):
    return (
        f'<g class="screw_terminal" data-label="{e(label)}">'
        f'{circle(cx, cy, 20, "#f7f9fb", color, 5)}'
        f'{circle(cx, cy, 9, color)}'
        f'{text(cx, cy + 48, label, 16, color, 700, "middle")}'
        f'</g>'
    )


def through_terminal(cx, cy, label):
    return (
        f'<g class="through_terminal" data-label="{e(label)}">'
        f'{circle(cx, cy, 12, "#eff9ff", "blue", 4)}'
        f'{circle(cx, cy, 5, "blue")}'
        f'{tag(cx, cy + 34, label, "blue", 108)}'
        f'</g>'
    )


def copper_post(cx, y1, y2):
    return (
        f'<g class="copper_post">'
        f'{line(cx, y1, cx, y2, "gold", 12)}'
        f'{circle(cx, y1, 18, "#fff1c6", "gold", 4)}{circle(cx, y1, 7, "gold")}'
        f'{circle(cx, y2, 18, "#fff1c6", "gold", 4)}{circle(cx, y2, 7, "gold")}'
        f'</g>'
    )


def f1_module(i, y):
    return (
        f'<g class="f1_log_module" data-module="{i}">'
        f'{rect(1485, y - 70, 310, 140, 18, "white", "line", 2)}'
        f'{rect(1520, y - 38, 68, 76, 9, "dark", "#46586a", 2)}'
        f'{text(1554, y + 8, "F-1", 22, "#53f485", 700, "middle")}'
        f'{text(1615, y - 6, f"日志模块 {i}", 24, "ink", 700)}'
        f'{text(1615, y + 28, "固定座 / OBD数据采集", 16, "muted")}'
        f'</g>'
    )


def build_svg():
    sx = [685, 955, 1225]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        "<defs>",
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
        '<feDropShadow dx="8" dy="12" stdDeviation="9" flood-color="#000000" flood-opacity=".14"/>'
        "</filter>",
        '<style>text{dominant-baseline:auto}.editable-layer *{vector-effect:non-scaling-stroke;}</style>',
        "</defs>",
        '<g id="layer_background" class="editable-layer">',
        rect(0, 0, W, H, 0, "bg", "bg", 0),
        rect(35, 32, W - 70, H - 74, 38, "surface", "#d7e2eb", 2),
        text(78, 112, "三工位 OBD 测试工装双层概念图", 42, "ink", 700),
        text(80, 150, "第一层安装接口与夹具，第二层做底部走线；两层通过铜柱分隔、穿板端子连接", 19, "muted"),
        "</g>",
    ]

    out += [
        '<g id="layer_power_source" class="editable-layer">',
        rect(70, 165, 410, 157, 24, "white", "line", 2),
        rect(100, 202, 350, 76, 14, "dark", "#46586a", 2),
        text(126, 264, "外置 220V 便携电源", 31, "#f0f8ff", 700),
        text(126, 312, "AC 220V 输出 / 移动供电", 19, "#6fbfe6"),
        circle(421, 235, 19, "#fff5f4", "red", 3),
        text(421, 242, "AC", 17, "red", 700, "middle"),
        path([(275, 322), (275, 385), (275, 430)], "red", 8),
        tag(335, 382, "220V AC", "red", 88),
        rect(70, 430, 410, 270, 24, "white", "line", 2),
        rect(70, 430, 14, 270, 7, "orange", "orange", 0),
        text(112, 515, "逆变 / 12V分配模块", 31, "ink", 700),
        text(112, 547, "220VAC 输入，输出 4 路 12V DC", 19, "muted"),
    ]
    for i, y in enumerate([568, 608, 648, 688], start=1):
        out += [
            rect(112, y - 16, 114, 32, 7, "#fffaf0", "yellow", 2),
            text(169, y + 6, f"12V OUT-{i}", 16, "yellow", 700, "middle"),
            line(245, y, 430, y, "yellow", 6),
        ]
    out.append("</g>")

    out += [
        '<g id="layer_bottom_wiring_board" class="editable-layer">',
        rect(535, 585, 840, 380, 30, "#eef5fa", "#9bb2c8", 3),
        rect(565, 625, 780, 305, 22, "#dfeaf3", "#9bb2c8", 2),
        text(595, 710, "第二层：底部走线层", 32, "ink", 700),
        text(598, 733, "12V电源、PWR/GND、OBD数据线从底部集中走线，减少上层交叉", 18, "muted"),
        "</g>",
        '<g id="layer_top_fixture_board" class="editable-layer">',
        rect(535, 145, 840, 430, 30, "dark", "#4e647a", 3),
        rect(565, 185, 780, 355, 22, "dark2", "#677c91", 2),
        text(595, 268, "第一层：安装 / 接口层", 32, "#f5f8fc", 700),
        text(598, 292, "3组OBD-II母口 / 平板夹 / 设备槽位", 18, "#a8e0f6"),
        rect(990, 206, 285, 90, 14, "#f7f9fb", "#b2bfcd", 2),
        text(1018, 270, "顶部正负极端子", 23, "ink", 700),
        screw_terminal(1185, 269, "+12V", COLORS["red"]),
        screw_terminal(1240, 269, "GND", "#1a1f25"),
        "</g>",
    ]

    out.append('<g id="layer_workstations" class="editable-layer">')
    for idx, cx in enumerate(sx, start=1):
        out += [
            f'<g id="workstation_{idx}">',
            rect(cx - 118, 310, 236, 215, 18, "#263646", "#5b7288", 2),
            text(cx, 357, f"工位 {idx}", 24, "#f5f8fc", 700, "middle"),
            tablet_clamp(cx - 94, 372, 188, 84),
            obd_socket(cx, 493, 0.86),
            through_terminal(cx, 650, f"穿板端子-{idx}"),
            circle(cx, 558, 12, "#eff9ff", "blue", 4),
            circle(cx, 558, 5, "blue"),
            line(cx, 570, cx, 635, "blue", 4, "12 8"),
            "</g>",
        ]
    out.append("</g>")

    out.append('<g id="layer_copper_standoffs" class="editable-layer">')
    for cx in [575, 795, 1115, 1335]:
        out.append(copper_post(cx, 575, 625))
    out += [tag(670, 604, "铜柱隔离", "gold", 92), tag(1215, 628, "上层端子供电", "yellow", 126), "</g>"]

    out.append('<g id="layer_wires_power" class="editable-layer">')
    out += [
        path([(430, 568), (500, 568), (500, 770), (1185, 770), (1185, 625)], "yellow", 7),
        tag(610, 770, "12V OUT-1", "yellow", 112),
        path([(430, 608), (500, 608), (500, 805), (685, 805), (685, 650)], "orange", 7),
        tag(610, 805, "12V OUT-2", "orange", 112),
        path([(430, 648), (500, 648), (500, 840), (955, 840), (955, 650)], "orange", 7),
        tag(610, 840, "12V OUT-3", "orange", 112),
        path([(430, 688), (500, 688), (500, 875), (1225, 875), (1225, 650)], "orange", 7),
        tag(610, 875, "12V OUT-4", "orange", 112),
        "</g>",
    ]

    out.append('<g id="layer_wires_data" class="editable-layer">')
    out += [
        path([(685, 650), (685, 900), (1418, 900), (1418, 355), (1485, 355)], "green", 7),
        path([(955, 650), (955, 872), (1426, 872), (1426, 585), (1485, 585)], "green", 7),
        path([(1225, 650), (1225, 844), (1434, 844), (1434, 815), (1485, 815)], "green", 7),
        tag(1010, 914, "底部OBD数据走线 -> F-1", "green", 220),
        "</g>",
    ]

    out += [
        '<g id="layer_f1_modules" class="editable-layer">',
        rect(1430, 165, 405, 800, 30, "white", "line", 2),
        rect(1430, 165, 14, 800, 7, "green", "green", 0),
        text(1480, 268, "安服优 F-1", 32, "ink", 700),
        text(1480, 290, "日志存储模块固定区（三组）", 18, "muted"),
        f1_module(1, 355),
        f1_module(2, 585),
        f1_module(3, 815),
        "</g>",
        '<g id="layer_legend" class="editable-layer">',
        rect(92, 750, 388, 180, 20, "white", "line", 2),
        text(124, 830, "双层结构说明", 24, "ink", 700),
        text(126, 856, "第一层", 17, "blue", 700),
        text(198, 856, "接口/夹具/设备槽位", 16, "ink"),
        text(126, 886, "第二层", 17, "orange", 700),
        text(198, 886, "底部走线与分配", 16, "ink"),
        text(126, 916, "铜柱", 17, "yellow", 700),
        text(198, 916, "上下层机械隔离", 16, "ink"),
        text(126, 946, "穿板端子", 17, "blue", 700),
        text(198, 946, "上下层电气连接", 16, "ink"),
        "</g>",
        "</svg>",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    svg = build_svg()
    SVG_CN.write_text(svg, encoding="utf-8")
    SVG_EN.write_text(svg, encoding="utf-8")
    print(SVG_CN)
    print(SVG_EN)
