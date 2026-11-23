"""CEP 数据解析、计算、绘图及表格导出。"""

from dataclasses import dataclass
from datetime import datetime
import os
import re

import chardet
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from geopy.distance import geodesic
import numpy as np
import openpyxl


DEFAULT_ANCHOR_NAME = "自定义锚点"
DEFAULT_KEYWORD = "$GNGGA"
FONT = FontProperties(fname="C:/Windows/Fonts/simhei.ttf")


@dataclass(frozen=True)
class CepResult:
    scatter_file: str
    bar_file: str
    satellite_file: str
    point_count: int
    average_height: float
    max_height: float
    min_height: float
    ceps: tuple[float, float, float, float, float]


def convert_to_utf8(file_path):
    """检测编码；非 UTF-8 时原地转为 UTF-8。"""
    with open(file_path, "rb") as file_obj:
        raw_data = file_obj.read()
        encoding = chardet.detect(raw_data)["encoding"]
    if encoding != "utf-8":
        with open(file_path, "r", encoding=encoding) as file_obj:
            content = file_obj.read()
        with open(file_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)


def is_valid_number(value):
    return value.count(".") <= 1 and re.fullmatch(r"[0-9.]+", value) is not None


def parse_nmea(file_path, keyword):
    coordinates = []
    heights = []
    num_sats_list = []
    gps_times = []
    raw_lats = []
    raw_lons = []

    with open(file_path, "r", encoding="latin-1", errors="ignore") as file_obj:
        for line in file_obj:
            if keyword not in line:
                continue
            parts = line.split(",")
            if len(parts) < 12:
                continue
            try:
                gps_time = parts[1].strip()
                lat_str = parts[2].strip()
                lon_str = parts[4].strip()
                if not (is_valid_number(lat_str) and is_valid_number(lon_str)):
                    print("非法GNGGA:", line.strip())
                    continue

                raw_lats.append(lat_str)
                raw_lons.append(lon_str)
                lat_raw = float(lat_str)
                lat_dir = parts[3]
                lat_deg = int(lat_raw / 100)
                lat_min = lat_raw - lat_deg * 100
                lat = lat_deg + lat_min / 60
                if lat_dir == "S":
                    lat = -lat

                lon_raw = float(lon_str)
                lon_dir = parts[5]
                lon_deg = int(lon_raw / 100)
                lon_min = lon_raw - lon_deg * 100
                lon = lon_deg + lon_min / 60
                if lon_dir == "W":
                    lon = -lon

                if abs(lat) > 90 or abs(lon) > 180:
                    print("异常坐标:", lat, lon)
                    continue

                try:
                    height = float(parts[9])
                    heights.append(height)
                    num_sats = int(parts[7])
                    num_sats_list.append(num_sats)
                except Exception:
                    continue

                coordinates.append((lat, lon))
                gps_times.append(gps_time)
            except Exception:
                print("解析异常:", line.strip())
                continue

    return coordinates, heights, num_sats_list, raw_lats, raw_lons, gps_times


def save_num_sats_to_excel(num_sats_list, coordinates, gps_times, output_file):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Satellite Data"
    sheet.append(["时间", "可用卫星数", "纬度", "经度"])
    row_count = max(len(num_sats_list), len(coordinates), len(gps_times))
    for index in range(row_count):
        gps_time = gps_times[index] if index < len(gps_times) else None
        num_sats = num_sats_list[index] if index < len(num_sats_list) else None
        lat, lon = coordinates[index] if index < len(coordinates) else (None, None)
        sheet.append([gps_time, num_sats, lat, lon])
    for cell in sheet["C"][1:]:
        cell.number_format = "0.00000000"
    for cell in sheet["D"][1:]:
        cell.number_format = "0.00000000"
    workbook.save(output_file)


def calculate_average_height(heights):
    return sum(heights) / len(heights) if heights else 0


def calculate_distances(fixed_point, coordinates):
    return [geodesic(fixed_point, coordinate).meters for coordinate in coordinates]


def calculate_cep(distances):
    sorted_distances = sorted(distances)
    count = len(sorted_distances)
    return (
        sorted_distances[int(0.50 * count)],
        sorted_distances[int(0.68 * count)],
        sorted_distances[int(0.95 * count)],
        sorted_distances[int(0.99 * count)],
        np.mean(distances),
    )


def plot_points(fixed_point, coordinates, distances, ceps, output_file, file_name, avg_height):
    cep50, cep68, cep95, cep99, _ = ceps
    fixed_lat, fixed_lon = fixed_point
    x_coords = [
        geodesic((fixed_lat, fixed_lon), (fixed_lat, lon)).meters * (1 if lon >= fixed_lon else -1)
        for _, lon in coordinates
    ]
    y_coords = [
        geodesic((fixed_lat, fixed_lon), (lat, fixed_lon)).meters * (1 if lat >= fixed_lat else -1)
        for lat, _ in coordinates
    ]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter([0], [0], color="black", label="基准点", s=10)
    for x_coord, y_coord, distance in zip(x_coords, y_coords, distances):
        color = (
            "blue" if distance <= cep50 else
            "green" if distance <= cep68 else
            "orange" if distance <= cep95 else
            "red" if distance <= cep99 else "purple"
        )
        ax.scatter(x_coord, y_coord, color=color, s=5)

    for radius, label, color in zip(
        [cep50, cep68, cep95, cep99],
        ["CEP50", "CEP68", "CEP95", "CEP99"],
        ["blue", "green", "orange", "red"],
    ):
        ax.add_artist(
            plt.Circle((0, 0), radius, color=color, fill=False, linestyle="--", label=f"{label}: {radius:.2f}m")
        )

    margin = cep99 * 0.1
    ax.set_xlim(-cep99 - margin, cep99 + margin)
    ax.set_ylim(-cep99 - margin, cep99 + margin)
    ax.set_title(f"CEP坐标分布 - {file_name}", fontproperties=FONT)
    ax.set_aspect("equal")
    ax.set_xlabel("东-西距离（m）", fontproperties=FONT)
    ax.set_ylabel("南-北距离（m）", fontproperties=FONT)
    ax.legend(prop=FONT)
    ax.grid()
    plt.text(
        0.95, 0.01, datetime.now().strftime("生成时间 %Y-%m-%d %H:%M:%S"),
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="red", fontproperties=FONT,
    )
    plt.text(
        0.03, 0.97, f"平均高度: {avg_height:.2f} 米", transform=ax.transAxes,
        ha="left", va="top", fontsize=10, color="blue", fontproperties=FONT,
    )
    fig.savefig(output_file, dpi=100, bbox_inches="tight")
    plt.close(fig)


def plot_bar_chart(ceps, output_file, file_name):
    labels = ["CEP50", "CEP68", "CEP95", "CEP99", "AVG"]
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, ceps, color=["blue", "green", "orange", "red", "gray"])
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.2f}m", xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontproperties=FONT,
        )
    ax.set_title(f"CEP统计 - {file_name}", fontproperties=FONT)
    ax.set_ylabel("单位(米)", fontproperties=FONT)
    ax.grid(axis="y")
    plt.text(
        0.95, 0.01, datetime.now().strftime("生成时间 %Y-%m-%d %H:%M:%S"),
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="red", fontproperties=FONT,
    )
    fig.savefig(output_file, dpi=100, bbox_inches="tight")
    plt.close(fig)


def analyze_cep(file_path, fixed_point, keyword, output_dir, now=None):
    """执行原 CEP 脚本的解析、计算和三类文件导出。"""
    os.makedirs(output_dir, exist_ok=True)
    convert_to_utf8(file_path)
    coordinates, heights, num_sats_list, _, _, gps_times = parse_nmea(file_path, keyword or DEFAULT_KEYWORD)
    distances = calculate_distances(fixed_point, coordinates)
    ceps = calculate_cep(distances)
    avg_height = calculate_average_height(heights)

    file_name = os.path.splitext(os.path.basename(file_path))[0]
    current_time = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    scatter_file = os.path.join(output_dir, f"{file_name}-{DEFAULT_ANCHOR_NAME}-散点图-{current_time}.png")
    bar_file = os.path.join(output_dir, f"{file_name}-{DEFAULT_ANCHOR_NAME}-柱状图-{current_time}.png")
    satellite_file = os.path.join(output_dir, f"{file_name}-{DEFAULT_ANCHOR_NAME}-可用卫星数.xlsx")

    save_num_sats_to_excel(num_sats_list, coordinates, gps_times, satellite_file)
    plot_points(fixed_point, coordinates, distances, ceps, scatter_file, file_name, avg_height)
    plot_bar_chart(ceps, bar_file, file_name)
    return CepResult(
        scatter_file, bar_file, satellite_file, len(coordinates), avg_height,
        max(heights), min(heights), tuple(float(value) for value in ceps),
    )

