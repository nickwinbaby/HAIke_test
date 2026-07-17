from pathlib import Path

from PIL import Image, ImageDraw

import generate_obd_fixture_flow_v1 as ui


OUT_DIR = Path(r"C:\Users\G1006871\Desktop\BIANYI\outputs")
PNG_OUT = OUT_DIR / "三工位OBD测试工装双层概念图_V2.png"
SVG_OUT = OUT_DIR / "三工位OBD测试工装双层概念图_V2.svg"

W, H = 1920, 1080


def dashed_line(draw, points, fill, width=4, dash=12, gap=8):
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            continue
        ux, uy = dx / length, dy / length
        pos = 0
        while pos < length:
            end = min(pos + dash, length)
            draw.line(
                (x1 + ux * pos, y1 + uy * pos, x1 + ux * end, y1 + uy * end),
                fill=ui.hex_to_rgb(fill),
                width=width,
            )
            pos += dash + gap


def copper_post(draw, x, y1, y2, label=False):
    gold = "#c9922f"
    draw.line((x, y1, x, y2), fill=ui.hex_to_rgb(gold), width=12)
    for y in (y1, y2):
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=ui.hex_to_rgb("#fff1c6"), outline=ui.hex_to_rgb(gold), width=4)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=ui.hex_to_rgb(gold))
    if label:
        ui.tag(draw, (x + 95, (y1 + y2) / 2), "铜柱隔离", gold)


def via(draw, x, y, label=None):
    draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=ui.hex_to_rgb("#eff9ff"), outline=ui.hex_to_rgb(ui.BLUE), width=4)
    draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=ui.hex_to_rgb(ui.BLUE))
    if label:
        ui.tag(draw, (x, y + 34), label, ui.BLUE)


def draw_power_card(draw):
    ui.rounded(draw, (70, 165, 480, 322), 24)
    draw.rounded_rectangle((100, 202, 450, 278), 14, fill=ui.hex_to_rgb(ui.DARK), outline=ui.hex_to_rgb("#46586a"), width=2)
    draw.text((126, 240), "外置 220V 便携电源", font=ui.F_H1, fill=ui.hex_to_rgb("#f0f8ff"))
    draw.text((126, 292), "AC 220V 输出 / 移动供电", font=ui.F_BODY, fill=ui.hex_to_rgb("#6fbfe6"))
    draw.ellipse((402, 216, 440, 254), fill=ui.hex_to_rgb("#fff5f4"), outline=ui.hex_to_rgb(ui.RED), width=3)
    ui.text_center(draw, (402, 216, 440, 254), "AC", ui.F_TAG, ui.RED)

    ui.rounded(draw, (70, 430, 480, 700), 24)
    draw.rounded_rectangle((70, 430, 84, 700), 7, fill=ui.hex_to_rgb(ui.ORANGE))
    draw.text((112, 480), "逆变 / 12V分配模块", font=ui.F_H1, fill=ui.hex_to_rgb(ui.INK))
    draw.text((112, 520), "220VAC 输入，输出 4 路 12V DC", font=ui.F_BODY, fill=ui.hex_to_rgb(ui.MUTED))
    for i, y in enumerate([568, 608, 648, 688], start=1):
        draw.rounded_rectangle((112, y - 16, 226, y + 16), 8, fill=ui.hex_to_rgb("#fffaf0"), outline=ui.hex_to_rgb(ui.YELLOW), width=2)
        ui.text_center(draw, (112, y - 16, 226, y + 16), f"12V OUT-{i}", ui.F_TAG, ui.YELLOW)
        draw.line((245, y, 430, y), fill=ui.hex_to_rgb(ui.YELLOW), width=6)


def draw_f1_zone(draw):
    ui.rounded(draw, (1430, 165, 1835, 965), 30)
    draw.rounded_rectangle((1430, 165, 1444, 965), 7, fill=ui.hex_to_rgb(ui.GREEN))
    draw.text((1480, 230), "安服优 F-1", font=ui.F_H1, fill=ui.hex_to_rgb(ui.INK))
    draw.text((1480, 267), "日志存储模块固定区（三组）", font=ui.F_BODY, fill=ui.hex_to_rgb(ui.MUTED))
    for i, y in enumerate([355, 585, 815], start=1):
        ui.rounded(draw, (1485, y - 76, 1792, y + 76), 20)
        draw.rounded_rectangle((1518, y - 43, 1588, y + 43), 10, fill=ui.hex_to_rgb(ui.DARK), outline=ui.hex_to_rgb("#46586a"), width=2)
        ui.text_center(draw, (1518, y - 43, 1588, y + 43), "F-1", ui.F_H2, "#53f485")
        draw.text((1615, y - 30), f"日志模块 {i}", font=ui.F_H2, fill=ui.hex_to_rgb(ui.INK))
        draw.text((1615, y + 5), "固定座 / OBD数据采集", font=ui.F_SMALL, fill=ui.hex_to_rgb(ui.MUTED))


def draw_fixture_layers(draw):
    # Bottom routing layer.
    ui.rounded(draw, (535, 585, 1375, 965), 30, fill="#eef5fa", outline="#9bb2c8", width=3)
    draw.rounded_rectangle((565, 625, 1345, 930), 22, fill=ui.hex_to_rgb("#dfeaf3"), outline=ui.hex_to_rgb("#9bb2c8"), width=2)
    draw.text((595, 672), "第二层：底部走线层", font=ui.F_H1, fill=ui.hex_to_rgb(ui.INK))
    draw.text((598, 707), "12V电源、PWR/GND、OBD数据线从底部集中走线，减少上层交叉", font=ui.F_BODY, fill=ui.hex_to_rgb(ui.MUTED))

    # Top mounting layer.
    ui.rounded(draw, (535, 145, 1375, 575), 30, fill=ui.DARK, outline="#4e647a", width=3)
    draw.rounded_rectangle((565, 185, 1345, 540), 22, fill=ui.hex_to_rgb(ui.DARK_2), outline=ui.hex_to_rgb("#677c91"), width=2)
    draw.text((595, 232), "第一层：安装 / 接口层", font=ui.F_H1, fill=ui.hex_to_rgb("#f5f8fc"))
    draw.text((598, 270), "3组OBD-II母口 / 平板夹 / 设备槽位", font=ui.F_BODY, fill=ui.hex_to_rgb("#a8e0f6"))

    draw.rounded_rectangle((990, 206, 1275, 296), 14, fill=ui.hex_to_rgb("#f7f9fb"), outline=ui.hex_to_rgb("#b2bfcd"), width=2)
    draw.text((1016, 244), "顶部正负极端子", font=ui.F_H2, fill=ui.hex_to_rgb(ui.INK))
    ui.terminal(draw, 1185, 269, "+12V", ui.RED)
    ui.terminal(draw, 1240, 269, "GND", "#1a1f25")

    station_x = [685, 955, 1225]
    for idx, cx in enumerate(station_x, start=1):
        draw.rounded_rectangle((cx - 118, 310, cx + 118, 525), 18, fill=ui.hex_to_rgb("#263646"), outline=ui.hex_to_rgb("#5b7288"), width=2)
        ui.text_center(draw, (cx - 118, 325, cx + 118, 360), f"工位 {idx}", ui.F_H2, "#f5f8fc")
        ui.draw_clamp(draw, (cx - 94, 372, cx + 94, 456))
        ui.draw_obd_socket(draw, cx, 493, 0.86)
        via(draw, cx, 558)
        dashed_line(draw, [(cx, 570), (cx, 635)], ui.BLUE, width=4)
        via(draw, cx, 650, f"穿板端子-{idx}")

    # Copper standoffs between layers.
    for x, show_label in [(575, True), (1335, False), (795, False), (1115, False)]:
        copper_post(draw, x, 575, 625, show_label)

    # Bottom layer routing traces.
    for i, (y, cx) in enumerate([(770, 1185), (805, 685), (840, 955), (875, 1225)], start=1):
        ui.cable(draw, [(430, 528 + i * 40), (500, 528 + i * 40), (500, y), (cx, y), (cx, 650 if i > 1 else 625)], ui.ORANGE if i > 1 else ui.YELLOW, 7)
        ui.tag(draw, (610, y), f"12V OUT-{i}", ui.ORANGE if i > 1 else ui.YELLOW)
    ui.tag(draw, (1215, 624), "上层端子供电", ui.YELLOW)

    # Bottom data routing to F-1 modules.
    for idx, (cx, y, fy) in enumerate([(685, 900, 355), (955, 872, 585), (1225, 844, 815)], start=1):
        ui.cable(draw, [(cx, 650), (cx, y), (1410 + idx * 8, y), (1410 + idx * 8, fy), (1485, fy)], ui.GREEN, 7)
    ui.tag(draw, (1010, 910), "底部OBD数据走线 -> F-1", ui.GREEN)

    # Layer note.
    ui.rounded(draw, (92, 750, 480, 930), 20, shadow=False)
    draw.text((124, 800), "双层结构说明", font=ui.F_H2, fill=ui.hex_to_rgb(ui.INK))
    notes = [
        ("第一层", "接口/夹具/设备槽位"),
        ("第二层", "底部走线与分配"),
        ("铜柱", "上下层机械隔离"),
        ("穿板端子", "上下层电气连接"),
    ]
    for i, (k, v) in enumerate(notes):
        yy = 837 + i * 30
        draw.text((126, yy), k, font=ui.F_TAG, fill=ui.hex_to_rgb(ui.BLUE if i in (0, 3) else ui.ORANGE if i == 1 else ui.YELLOW))
        draw.text((198, yy), v, font=ui.F_SMALL, fill=ui.hex_to_rgb(ui.INK))


def draw_png():
    ui.img = Image.new("RGBA", (W, H), ui.hex_to_rgb(ui.BG) + (255,))
    draw = ImageDraw.Draw(ui.img)
    draw.rounded_rectangle((35, 32, W - 35, H - 42), 38, fill=ui.hex_to_rgb(ui.TABLE), outline=ui.hex_to_rgb("#d7e2eb"), width=2)
    draw.text((78, 66), "三工位 OBD 测试工装双层概念图", font=ui.F_TITLE, fill=ui.hex_to_rgb(ui.INK))
    draw.text((80, 112), "第一层安装接口与夹具，第二层做底部走线；两层通过铜柱分隔、穿板端子连接", font=ui.F_BODY, fill=ui.hex_to_rgb(ui.MUTED))

    draw_power_card(draw)
    draw_fixture_layers(draw)
    draw_f1_zone(draw)

    ui.cable(draw, [(275, 322), (275, 385), (275, 430)], ui.RED, 9, "220V AC", (335, 382))

    ui.img.convert("RGB").save(PNG_OUT, quality=96)


def draw_svg():
    # SVG is an editable concept copy of the PNG layout. It keeps the main layers,
    # standoffs, through-board points, and routing traces as separate objects.
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<defs><style>text{font-family:"Microsoft YaHei",Arial;}.wire{fill:none;stroke-linecap:round;stroke-linejoin:round;}.card{filter:drop-shadow(8px 12px 12px rgba(0,0,0,.14));}</style></defs>',
        ui.svg_rect(0, 0, W, H, 0, ui.BG, ui.BG, 0),
        ui.svg_rect(35, 32, W - 70, H - 74, 38, ui.TABLE, "#d7e2eb", 2),
        ui.svg_text(78, 112, "三工位 OBD 测试工装双层概念图", 42, ui.INK, 700),
        ui.svg_text(80, 150, "第一层安装接口与夹具，第二层做底部走线；两层通过铜柱分隔、穿板端子连接", 19, ui.MUTED),
        ui.svg_rect(70, 165, 410, 157, 24),
        ui.svg_rect(100, 202, 350, 76, 14, ui.DARK, "#46586a", 2),
        ui.svg_text(126, 258, "外置 220V 便携电源", 32, "#f0f8ff", 700),
        ui.svg_rect(70, 430, 410, 270, 24),
        ui.svg_text(112, 520, "逆变 / 12V分配模块", 32, ui.INK, 700),
        ui.svg_rect(535, 585, 840, 380, 30, "#eef5fa", "#9bb2c8", 3),
        ui.svg_rect(535, 145, 840, 430, 30, ui.DARK, "#4e647a", 3),
        ui.svg_text(595, 232, "第一层：安装 / 接口层", 32, "#f5f8fc", 700),
        ui.svg_text(595, 672, "第二层：底部走线层", 32, ui.INK, 700),
        ui.svg_rect(1430, 165, 405, 800, 30),
        ui.svg_text(1480, 240, "安服优 F-1", 32, ui.INK, 700),
    ]
    for i, cx in enumerate([685, 955, 1225], start=1):
        svg += [
            ui.svg_rect(cx - 118, 310, 236, 215, 18, "#263646", "#5b7288", 2),
            ui.svg_text(cx, 352, f"工位 {i}", 24, "#f5f8fc", 700, "middle"),
            ui.svg_obd(cx, 493),
            f'<circle cx="{cx}" cy="650" r="12" fill="#eff9ff" stroke="{ui.BLUE}" stroke-width="4"/>',
            f'<line x1="{cx}" y1="570" x2="{cx}" y2="635" stroke="{ui.BLUE}" stroke-width="4" stroke-dasharray="12 8"/>',
        ]
    for x in [575, 795, 1115, 1335]:
        svg.append(f'<line x1="{x}" y1="575" x2="{x}" y2="625" stroke="#c9922f" stroke-width="12" stroke-linecap="round"/>')
        svg.append(f'<circle cx="{x}" cy="575" r="18" fill="#fff1c6" stroke="#c9922f" stroke-width="4"/>')
        svg.append(f'<circle cx="{x}" cy="625" r="18" fill="#fff1c6" stroke="#c9922f" stroke-width="4"/>')
    for y, cx, color in [(760, 1180, ui.YELLOW), (795, 685, ui.ORANGE), (830, 955, ui.ORANGE), (865, 1225, ui.ORANGE)]:
        svg.append(ui.svg_path([(430, y - 192), (500, y - 192), (500, y), (cx, y), (cx, 650 if cx != 1180 else 625)], color, 7))
    for idx, (cx, y, fy) in enumerate([(685, 900, 355), (955, 872, 585), (1225, 844, 815)], start=1):
        svg.append(ui.svg_path([(cx, 650), (cx, y), (1410 + idx * 8, y), (1410 + idx * 8, fy), (1485, fy)], ui.GREEN, 7))
    for i, y in enumerate([355, 585, 815], start=1):
        svg += [
            ui.svg_rect(1485, y - 76, 307, 152, 20),
            ui.svg_rect(1518, y - 43, 70, 86, 10, ui.DARK, "#46586a", 2),
            ui.svg_text(1553, y + 8, "F-1", 24, "#53f485", 700, "middle"),
            ui.svg_text(1615, y - 8, f"日志模块 {i}", 24, ui.INK, 700),
        ]
    svg.append("</svg>")
    SVG_OUT.write_text("\n".join(svg), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    draw_png()
    draw_svg()
    print(PNG_OUT)
    print(SVG_OUT)
