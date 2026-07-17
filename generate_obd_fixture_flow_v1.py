from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


OUT_DIR = Path(r"C:\Users\G1006871\Desktop\BIANYI\outputs")
PNG_OUT = OUT_DIR / "三工位OBD测试工装流程图_V1.png"
SVG_OUT = OUT_DIR / "三工位OBD测试工装流程图_V1.svg"

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
PURPLE = "#7856cd"
GRAY = "#9fb1c3"
WHITE = "#ffffff"


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_TITLE = font(42, True)
F_H1 = font(32, True)
F_H2 = font(24, True)
F_BODY = font(19)
F_SMALL = font(16)
F_TAG = font(17, True)
F_TINY = font(14)


def rounded(draw, box, radius=18, fill=WHITE, outline=LINE, width=2, shadow=True):
    if shadow:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(layer)
        x1, y1, x2, y2 = box
        sd.rounded_rectangle(
            (x1 + 8, y1 + 12, x2 + 8, y2 + 12),
            radius,
            fill=(0, 0, 0, 34),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(13))
        img.alpha_composite(layer)
    draw.rounded_rectangle(
        box,
        radius,
        fill=hex_to_rgb(fill),
        outline=hex_to_rgb(outline),
        width=width,
    )


def text_center(draw, box, value, fnt, fill=INK):
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), value, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (x1 + (x2 - x1 - tw) / 2, y1 + (y2 - y1 - th) / 2 - 2),
        value,
        font=fnt,
        fill=hex_to_rgb(fill),
    )


def tag(draw, center, value, color, pad_x=12):
    x, y = center
    bbox = draw.textbbox((0, 0), value, font=F_TAG)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    box = (x - tw / 2 - pad_x, y - th / 2 - 7, x + tw / 2 + pad_x, y + th / 2 + 7)
    draw.rounded_rectangle(
        box,
        8,
        fill=(255, 255, 255, 242),
        outline=hex_to_rgb("#bdd9ef"),
        width=1,
    )
    draw.text((x - tw / 2, y - th / 2 - 1), value, font=F_TAG, fill=hex_to_rgb(color))


def cable(draw, pts, color, width=8, label=None, label_xy=None):
    rgb = hex_to_rgb(color)
    draw.line(pts, fill=(0, 0, 0, 38), width=width + 5, joint="curve")
    draw.line(pts, fill=rgb, width=width, joint="curve")
    for x, y in [pts[0], pts[-1]]:
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=rgb, outline=(255, 255, 255), width=2)
    if label and label_xy:
        tag(draw, label_xy, label, color)


def terminal(draw, x, y, label, color):
    draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill=hex_to_rgb("#f7f9fb"), outline=hex_to_rgb(color), width=5)
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=hex_to_rgb(color))
    text_center(draw, (x - 34, y + 28, x + 34, y + 58), label, F_TAG, color)


def draw_obd_socket(draw, cx, cy, scale=1.0, title="OBD-II 母口"):
    w, h = int(150 * scale), int(66 * scale)
    x1, y1 = cx - w // 2, cy - h // 2
    x2, y2 = cx + w // 2, cy + h // 2
    draw.rounded_rectangle((x1, y1, x2, y2), 10, fill=hex_to_rgb("#121b24"), outline=hex_to_rgb("#8c9eb0"), width=2)
    for row in range(2):
        for col in range(8):
            px = x1 + 20 + col * (w - 40) / 7
            py = y1 + 20 + row * 25
            draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=hex_to_rgb("#c4cfda"))
    text_center(draw, (x1, y2 + 8, x2, y2 + 34), title, F_SMALL, "#dce8f3")


def draw_clamp(draw, box):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1, x2, y2), 14, fill=hex_to_rgb("#f7f9fb"), outline=hex_to_rgb("#9fb1c3"), width=2)
    draw.rounded_rectangle((x1 + 18, y1 + 15, x2 - 18, y1 + 38), 8, fill=hex_to_rgb("#ccd8e4"))
    draw.rounded_rectangle((x1 + 38, y1 + 47, x2 - 38, y2 - 18), 8, fill=hex_to_rgb("#aebed0"))
    text_center(draw, (x1, y1 + 82, x2, y2 - 8), "平板夹 / 设备固定", F_SMALL, MUTED)


def draw_device_slot(draw, box, idx):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1, x2, y2), 16, fill=hex_to_rgb("#ffffff"), outline=hex_to_rgb("#c8d4e0"), width=2)
    draw.rounded_rectangle((x1 + 18, y1 + 18, x2 - 18, y2 - 18), 12, fill=hex_to_rgb("#eef3f7"), outline=hex_to_rgb("#b7c6d4"), width=2)
    draw.text((x1 + 28, y1 + 38), f"设备槽位 {idx}", font=F_H2, fill=hex_to_rgb(INK))
    draw.text((x1 + 28, y1 + 72), "预留安装孔 / 扎带固定", font=F_SMALL, fill=hex_to_rgb(MUTED))


def draw_png():
    global img
    img = Image.new("RGBA", (W, H), hex_to_rgb(BG) + (255,))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((35, 32, W - 35, H - 42), 38, fill=hex_to_rgb(TABLE), outline=hex_to_rgb("#d7e2eb"), width=2)
    draw.text((78, 66), "三工位 OBD 测试工装流程图", font=F_TITLE, fill=hex_to_rgb(INK))
    draw.text((80, 112), "220V便携电源 -> 4路12V分配 -> 3组OBD-II工位 / 顶部正负极端子 / F-1日志模块", font=F_BODY, fill=hex_to_rgb(MUTED))

    # Left power chain.
    rounded(draw, (70, 170, 480, 335), 24)
    draw.rounded_rectangle((100, 205, 450, 282), 14, fill=hex_to_rgb(DARK), outline=hex_to_rgb("#46586a"), width=2)
    draw.text((126, 243), "外置 220V 便携电源", font=F_H1, fill=hex_to_rgb("#f0f8ff"))
    draw.text((126, 292), "AC 220V 输出 / 移动供电", font=F_BODY, fill=hex_to_rgb("#94d8f5"))
    draw.ellipse((402, 218, 440, 256), fill=hex_to_rgb("#fff5f4"), outline=hex_to_rgb(RED), width=3)
    text_center(draw, (402, 218, 440, 256), "AC", F_TAG, RED)

    rounded(draw, (70, 435, 480, 710), 24)
    draw.rounded_rectangle((70, 435, 84, 710), 7, fill=hex_to_rgb(ORANGE))
    draw.text((112, 485), "逆变 / 12V分配模块", font=F_H1, fill=hex_to_rgb(INK))
    draw.text((112, 526), "220VAC 输入，输出 4 路 12V DC", font=F_BODY, fill=hex_to_rgb(MUTED))
    for i, y in enumerate([575, 615, 655, 695], start=1):
        draw.rounded_rectangle((112, y - 16, 226, y + 16), 8, fill=hex_to_rgb("#fffaf0"), outline=hex_to_rgb(YELLOW), width=2)
        text_center(draw, (112, y - 16, 226, y + 16), f"12V OUT-{i}", F_TAG, YELLOW)
        draw.line((245, y, 430, y), fill=hex_to_rgb(YELLOW), width=6)

    # Main fixture panel.
    rounded(draw, (535, 150, 1375, 960), 30, fill=DARK, outline="#4e647a", width=3)
    draw.rounded_rectangle((565, 190, 1345, 925), 22, fill=hex_to_rgb(DARK_2), outline=hex_to_rgb("#677c91"), width=2)
    draw.text((595, 240), "测试工装面板", font=F_TITLE, fill=hex_to_rgb("#f5f8fc"))
    draw.text((598, 286), "3组OBD-II母口 + 3组平板夹 + 3组设备槽位", font=F_BODY, fill=hex_to_rgb("#a8e0f6"))

    draw.rounded_rectangle((1000, 214, 1265, 300), 14, fill=hex_to_rgb("#f7f9fb"), outline=hex_to_rgb("#b2bfcd"), width=2)
    draw.text((1024, 248), "顶部螺帽式连接端子", font=F_H2, fill=hex_to_rgb(INK))
    terminal(draw, 1178, 272, "+12V", RED)
    terminal(draw, 1232, 272, "GND", "#1a1f25")

    station_x = [685, 955, 1225]
    obd_ports = []
    for idx, cx in enumerate(station_x, start=1):
        draw.rounded_rectangle((cx - 118, 335, cx + 118, 890), 20, fill=hex_to_rgb("#263646"), outline=hex_to_rgb("#5b7288"), width=2)
        text_center(draw, (cx - 118, 356, cx + 118, 392), f"工位 {idx}", F_H2, "#f5f8fc")
        draw_clamp(draw, (cx - 95, 410, cx + 95, 535))
        draw_obd_socket(draw, cx, 620, 1.0)
        draw_device_slot(draw, (cx - 95, 710, cx + 95, 842), idx)
        obd_ports.append((cx, 620))
        tag(draw, (cx, 674), f"OBD接口-{idx}", BLUE)

    # Right F-1 modules.
    rounded(draw, (1430, 150, 1835, 960), 30)
    draw.rounded_rectangle((1430, 150, 1444, 960), 7, fill=hex_to_rgb(GREEN))
    draw.text((1480, 218), "安服优 F-1", font=F_H1, fill=hex_to_rgb(INK))
    draw.text((1480, 256), "日志存储模块固定区（三组）", font=F_BODY, fill=hex_to_rgb(MUTED))
    f1_ports = []
    for i, y in enumerate([350, 575, 800], start=1):
        rounded(draw, (1485, y - 76, 1792, y + 76), 20, fill="#ffffff", outline="#c8d4e0", width=2)
        draw.rounded_rectangle((1518, y - 43, 1588, y + 43), 10, fill=hex_to_rgb(DARK), outline=hex_to_rgb("#46586a"), width=2)
        text_center(draw, (1518, y - 43, 1588, y + 43), "F-1", F_H2, "#53f485")
        draw.text((1615, y - 30), f"日志模块 {i}", font=F_H2, fill=hex_to_rgb(INK))
        draw.text((1615, y + 5), "固定座 / OBD数据采集", font=F_SMALL, fill=hex_to_rgb(MUTED))
        f1_ports.append((1485, y))

    # Cables.
    cable(draw, [(275, 335), (275, 395), (275, 435)], RED, 9, "220V AC", (335, 390))
    cable(draw, [(430, 575), (500, 575), (500, 145), (1178, 145), (1178, 252)], YELLOW, 8, "12V OUT-1 -> 顶部端子", (805, 166))
    cable(draw, [(430, 615), (520, 615), (520, 620), (567, 620)], ORANGE, 8, "12V OUT-2", (542, 594))
    cable(draw, [(430, 655), (545, 655), (545, 690), (837, 690), (837, 620)], ORANGE, 8, "12V OUT-3", (735, 690))
    cable(draw, [(430, 695), (505, 695), (505, 880), (1107, 880), (1107, 620)], ORANGE, 8, "12V OUT-4", (820, 880))

    for (sx, sy), (ex, ey), idx, offset in zip(obd_ports, f1_ports, [1, 2, 3], [-58, -34, -10]):
        mid_x = 1400 + idx * 8
        cable(draw, [(sx + 118, sy + offset), (mid_x, sy + offset), (mid_x, ey), (ex, ey)], GREEN, 7)

    # Legend.
    rounded(draw, (92, 760, 480, 930), 20, shadow=False)
    draw.text((124, 806), "线束说明", font=F_H2, fill=hex_to_rgb(INK))
    for i, (name, col) in enumerate([("220V AC", RED), ("12V DC / PWR-GND", ORANGE), ("F-1 与 OBD 数据连接", GREEN), ("机械固定/槽位", GRAY)]):
        yy = 842 + i * 32
        draw.line((126, yy, 176, yy), fill=hex_to_rgb(col), width=7)
        draw.text((195, yy - 11), name, font=F_SMALL, fill=hex_to_rgb(INK))

    img.convert("RGB").save(PNG_OUT, quality=96)


def svg_rect(x, y, w, h, rx=18, fill=WHITE, stroke=LINE, sw=2, cls=""):
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def svg_text(x, y, value, size=18, fill=INK, weight=400, anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-family="Microsoft YaHei, Arial" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def svg_path(points, color, width=8, cls="wire"):
    d = "M " + " L ".join(f"{x},{y}" for x, y in points)
    ports = "".join(
        f'<circle cx="{x}" cy="{y}" r="9" fill="{color}" stroke="#fff" stroke-width="2"/>' for x, y in [points[0], points[-1]]
    )
    return f'<path class="{cls}" d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>{ports}'


def svg_tag(x, y, value, color):
    w = max(78, len(value) * 15)
    return (
        f'<g class="tag"><rect x="{x-w/2}" y="{y-17}" width="{w}" height="34" rx="8" fill="#fff" stroke="#bdd9ef"/>'
        f'{svg_text(x, y+6, value, 17, color, 700, "middle")}</g>'
    )


def svg_terminal(x, y, label, color):
    return (
        f'<circle cx="{x}" cy="{y}" r="20" fill="#f7f9fb" stroke="{color}" stroke-width="5"/>'
        f'<circle cx="{x}" cy="{y}" r="9" fill="{color}"/>'
        f'{svg_text(x, y+52, label, 17, color, 700, "middle")}'
    )


def svg_obd(cx, cy):
    x, y = cx - 75, cy - 33
    dots = []
    for row in range(2):
        for col in range(8):
            px = x + 20 + col * 110 / 7
            py = y + 20 + row * 25
            dots.append(f'<circle cx="{px}" cy="{py}" r="5" fill="#c4cfda"/>')
    return (
        f'<g class="obd-socket">{svg_rect(x, y, 150, 66, 10, "#121b24", "#8c9eb0", 2)}'
        + "".join(dots)
        + svg_text(cx, cy + 59, "OBD-II 母口", 16, "#dce8f3", 400, "middle")
        + "</g>"
    )


def draw_svg():
    station_x = [685, 955, 1225]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        "<defs><style>.card{filter:drop-shadow(8px 12px 12px rgba(0,0,0,.14));}.wire{filter:drop-shadow(0 4px 3px rgba(0,0,0,.18));}text{dominant-baseline:auto;}</style></defs>",
        svg_rect(0, 0, W, H, 0, BG, BG, 0),
        svg_rect(35, 32, W - 70, H - 74, 38, TABLE, "#d7e2eb", 2),
        svg_text(78, 112, "三工位 OBD 测试工装流程图", 42, INK, 700),
        svg_text(80, 150, "220V便携电源 -> 4路12V分配 -> 3组OBD-II工位 / 顶部正负极端子 / F-1日志模块", 19, MUTED),
    ]

    out += [
        f'<g class="card portable-power">{svg_rect(70,170,410,165,24)}{svg_rect(100,205,350,77,14,DARK,"#46586a",2)}'
        + svg_text(126, 257, "外置 220V 便携电源", 32, "#f0f8ff", 700)
        + svg_text(126, 313, "AC 220V 输出 / 移动供电", 19, "#94d8f5")
        + '<circle cx="421" cy="237" r="19" fill="#fff5f4" stroke="#de483e" stroke-width="3"/>'
        + svg_text(421, 244, "AC", 17, RED, 700, "middle")
        + "</g>",
        f'<g class="card inverter">{svg_rect(70,435,410,275,24)}{svg_rect(70,435,14,275,7,ORANGE,ORANGE,0)}'
        + svg_text(112, 520, "逆变 / 12V分配模块", 32, INK, 700)
        + svg_text(112, 560, "220VAC 输入，输出 4 路 12V DC", 19, MUTED)
        + "</g>",
    ]
    for i, y in enumerate([575, 615, 655, 695], start=1):
        out.append(svg_rect(112, y - 16, 114, 32, 8, "#fffaf0", YELLOW, 2))
        out.append(svg_text(169, y + 6, f"12V OUT-{i}", 17, YELLOW, 700, "middle"))
        out.append(f'<line x1="245" y1="{y}" x2="430" y2="{y}" stroke="{YELLOW}" stroke-width="6" stroke-linecap="round"/>')

    out += [
        f'<g class="card fixture">{svg_rect(535,150,840,810,30,DARK,"#4e647a",3)}{svg_rect(565,190,780,735,22,DARK_2,"#677c91",2)}'
        + svg_text(595, 268, "测试工装面板", 42, "#f5f8fc", 700)
        + svg_text(598, 306, "3组OBD-II母口 + 3组平板夹 + 3组设备槽位", 19, "#a8e0f6")
        + svg_rect(1000, 214, 265, 86, 14, "#f7f9fb", "#b2bfcd", 2)
        + svg_text(1024, 260, "顶部螺帽式连接端子", 24, INK, 700)
        + svg_terminal(1178, 272, "+12V", RED)
        + svg_terminal(1232, 272, "GND", "#1a1f25")
    ]
    for idx, cx in enumerate(station_x, start=1):
        out.append(svg_rect(cx - 118, 335, 236, 555, 20, "#263646", "#5b7288", 2))
        out.append(svg_text(cx, 382, f"工位 {idx}", 24, "#f5f8fc", 700, "middle"))
        out.append(svg_rect(cx - 95, 410, 190, 125, 14, "#f7f9fb", GRAY, 2))
        out.append(svg_rect(cx - 77, 425, 154, 23, 8, "#ccd8e4", "#ccd8e4", 0))
        out.append(svg_rect(cx - 57, 457, 114, 60, 8, "#aebed0", "#aebed0", 0))
        out.append(svg_text(cx, 526, "平板夹 / 设备固定", 16, MUTED, 400, "middle"))
        out.append(svg_obd(cx, 620))
        out.append(svg_tag(cx, 674, f"OBD接口-{idx}", BLUE))
        out.append(svg_rect(cx - 95, 710, 190, 132, 16, "#ffffff", LINE, 2))
        out.append(svg_rect(cx - 77, 728, 154, 96, 12, "#eef3f7", "#b7c6d4", 2))
        out.append(svg_text(cx - 67, 768, f"设备槽位 {idx}", 24, INK, 700))
        out.append(svg_text(cx - 67, 802, "预留安装孔 / 扎带固定", 16, MUTED))
    out.append("</g>")

    out += [
        f'<g class="card f1-zone">{svg_rect(1430,150,405,810,30)}{svg_rect(1430,150,14,810,7,GREEN,GREEN,0)}'
        + svg_text(1480, 240, "安服优 F-1", 32, INK, 700)
        + svg_text(1480, 275, "日志存储模块固定区（三组）", 19, MUTED)
    ]
    for i, y in enumerate([350, 575, 800], start=1):
        out.append(svg_rect(1485, y - 76, 307, 152, 20, "#ffffff", LINE, 2))
        out.append(svg_rect(1518, y - 43, 70, 86, 10, DARK, "#46586a", 2))
        out.append(svg_text(1553, y + 8, "F-1", 24, "#53f485", 700, "middle"))
        out.append(svg_text(1615, y - 8, f"日志模块 {i}", 24, INK, 700))
        out.append(svg_text(1615, y + 30, "固定座 / OBD数据采集", 16, MUTED))
    out.append("</g>")

    out += [
        svg_path([(275, 335), (275, 395), (275, 435)], RED, 9),
        svg_tag(335, 390, "220V AC", RED),
        svg_path([(430, 575), (500, 575), (500, 145), (1178, 145), (1178, 252)], YELLOW, 8),
        svg_tag(805, 166, "12V OUT-1 -> 顶部端子", YELLOW),
        svg_path([(430, 615), (520, 615), (520, 620), (567, 620)], ORANGE, 8),
        svg_tag(542, 594, "12V OUT-2", ORANGE),
        svg_path([(430, 655), (545, 655), (545, 690), (837, 690), (837, 620)], ORANGE, 8),
        svg_tag(735, 690, "12V OUT-3", ORANGE),
        svg_path([(430, 695), (505, 695), (505, 880), (1107, 880), (1107, 620)], ORANGE, 8),
        svg_tag(820, 880, "12V OUT-4", ORANGE),
        svg_path([(803, 562), (1408, 562), (1408, 350), (1485, 350)], GREEN, 7),
        svg_path([(1073, 586), (1416, 586), (1416, 575), (1485, 575)], GREEN, 7),
        svg_path([(1343, 610), (1424, 610), (1424, 800), (1485, 800)], GREEN, 7),
    ]

    out += [
        svg_rect(92, 760, 388, 170, 20),
        svg_text(124, 818, "线束说明", 24, INK, 700),
    ]
    for i, (name, col) in enumerate([("220V AC", RED), ("12V DC / PWR-GND", ORANGE), ("F-1 与 OBD 数据连接", GREEN), ("机械固定/槽位", GRAY)]):
        yy = 842 + i * 32
        out.append(f'<line x1="126" y1="{yy}" x2="176" y2="{yy}" stroke="{col}" stroke-width="7" stroke-linecap="round"/>')
        out.append(svg_text(195, yy + 6, name, 16, INK))

    out.append("</svg>")
    SVG_OUT.write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    draw_png()
    draw_svg()
    print(PNG_OUT)
    print(SVG_OUT)
