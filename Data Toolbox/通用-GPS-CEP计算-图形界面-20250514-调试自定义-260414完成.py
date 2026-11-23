import os
import sys
import time
import chardet
import matplotlib.pyplot as plt
from geopy.distance import geodesic
import numpy as np
import openpyxl
from datetime import datetime
from tkinter import Tk, filedialog, StringVar, messagebox
from tkinter import ttk
from matplotlib.font_manager import FontProperties
import re

# 编译命令
# pyinstaller -F -w --clean -n "CEP分析工具" -i cep_tool_icon.ico --add-data "cep_tool_icon.ico;." "通用-GPS-CEP计算-图形界面-20250514-调试自定义-260414完成.py"

# 设置中文字体
font = FontProperties(fname='C:/Windows/Fonts/simhei.ttf')  # 使用黑体字体

APP_TITLE = "CEP 分析工具"
APP_ICON = "cep_tool_icon.ico"
DEFAULT_ANCHOR_NAME = "自定义锚点"

default_name_key = "$GNGGA"


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)

# 文件编码转换
def convert_to_utf8(file_path):
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding = chardet.detect(raw_data)['encoding']
    if encoding != 'utf-8':
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

# 提取NMEA行并解析经纬度


def is_valid_number(s):
    # ✅ 只允许数字和一个小数点
    return (
        s.count('.') <= 1 and
        re.fullmatch(r'[0-9.]+', s) is not None
    )

def parse_nmea(file_path, keyword):
    coordinates = []
    heights = []
    num_sats_list = []
    gps_times = []

    raw_lats = []
    raw_lons = []

    with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
        for line in f:
            if keyword in line:
                parts = line.split(',')

                if len(parts) >= 12:
                    try:
                        gps_time = parts[1].strip()
                        lat_str = parts[2].strip()
                        lon_str = parts[4].strip()

                        # ✅ ✅ ✅ 新增：非法字符过滤（关键）
                        if not (is_valid_number(lat_str) and is_valid_number(lon_str)):
                            print("非法GNGGA:", line.strip())
                            continue

                        # 👉 保存原始值（只保存合法的）
                        raw_lats.append(lat_str)
                        raw_lons.append(lon_str)

                        # ===== 修复后的解析逻辑 =====
                        lat_raw = float(lat_str)
                        lat_dir = parts[3]

                        lat_deg = int(lat_raw / 100)
                        lat_min = lat_raw - lat_deg * 100
                        lat = lat_deg + lat_min / 60
                        if lat_dir == 'S':
                            lat = -lat

                        lon_raw = float(lon_str)
                        lon_dir = parts[5]

                        lon_deg = int(lon_raw / 100)
                        lon_min = lon_raw - lon_deg * 100
                        lon = lon_deg + lon_min / 60
                        if lon_dir == 'W':
                            lon = -lon

                        # ✅ 合法性检查
                        if abs(lat) > 90 or abs(lon) > 180:
                            print("异常坐标:", lat, lon)
                            continue

                        try:
                            height = float(parts[9])
                            heights.append(height)

                            num_sats = int(parts[7])
                            num_sats_list.append(num_sats)

                        except:
                            continue

                        coordinates.append((lat, lon))
                        gps_times.append(gps_time)

                    except Exception as e:
                        print("解析异常:", line.strip())
                        continue

    return coordinates, heights, num_sats_list, raw_lats, raw_lons, gps_times


# 保存可用卫星数到Excel文件
def save_num_sats_to_excel(num_sats_list, coordinates, gps_times, sats_output_file):
    # Create a new workbook
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Satellite Data"

    # Add header
    sheet.append(["时间", "可用卫星数", "纬度", "经度"])

    # Write num_sats and parsed coordinate values to rows
    row_count = max(len(num_sats_list), len(coordinates), len(gps_times))
    for i in range(row_count):
        gps_time = gps_times[i] if i < len(gps_times) else None
        num_sats = num_sats_list[i] if i < len(num_sats_list) else None
        lat, lon = coordinates[i] if i < len(coordinates) else (None, None)
        sheet.append([gps_time, num_sats, lat, lon])

    for cell in sheet["C"][1:]:
        cell.number_format = "0.00000000"
    for cell in sheet["D"][1:]:
        cell.number_format = "0.00000000"

    # Save the workbook
    workbook.save(sats_output_file)
    # print(f"数据已保存到 {sats_output_file}")


def calculate_average_height(heights):
    return sum(heights) / len(heights) if heights else 0

def calculate_distances(fixed_point, coordinates):
    return [geodesic(fixed_point, coord).meters for coord in coordinates]

def calculate_cep(distances):
    sorted_distances = sorted(distances)
    n = len(sorted_distances)
    return (
        sorted_distances[int(0.50 * n)],
        sorted_distances[int(0.68 * n)],
        sorted_distances[int(0.95 * n)],
        sorted_distances[int(0.99 * n)],
        # max(sorted_distances),  # MAC 不再显示最大值
        np.mean(distances)
    )

def plot_points(fixed_point, coordinates, distances, ceps, output_file, file_name, avg_height):
    # cep50, cep68, cep95, cep99, max_d, _ = ceps # MAC 不再显示最大值
    cep50, cep68, cep95, cep99, avg = ceps
    fixed_lat, fixed_lon = fixed_point
    x_coords = [(geodesic((fixed_lat, fixed_lon), (fixed_lat, lon)).meters * (1 if lon >= fixed_lon else -1)) for lat, lon in coordinates]
    y_coords = [(geodesic((fixed_lat, fixed_lon), (lat, fixed_lon)).meters * (1 if lat >= fixed_lat else -1)) for lat, lon in coordinates]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter([0], [0], color='black', label='基准点', s=10)
    for x, y, d in zip(x_coords, y_coords, distances):
        color = 'blue' if d <= cep50 else 'green' if d <= cep68 else 'orange' if d <= cep95 else 'red' if d <= cep99 else 'purple'
        ax.scatter(x, y, color=color, s=5)
    # 去掉MAC的圈
    # for r, label, color in zip([cep50, cep68, cep95, cep99, max_d],
    #                             ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'MAX'],
    #                             ['blue', 'green', 'orange', 'red', 'purple']):
    for r, label, color in zip([cep50, cep68, cep95, cep99],
                               ['CEP50', 'CEP68', 'CEP95', 'CEP99'],
                               ['blue', 'green', 'orange', 'red']):
        ax.add_artist(plt.Circle((0, 0), r, color=color, fill=False, linestyle='--', label=f'{label}: {r:.2f}m'))

    # 设置图像范围，确保圆完整显示
    # margin = max_d * 0.1  # 添加10%的边距
    # ax.set_xlim(-max_d - margin, max_d + margin)
    # ax.set_ylim(-max_d - margin, max_d + margin)
    # 去掉MAX的显示后，范围以CEP99为基准
    margin = cep99 * 0.1
    ax.set_xlim(-cep99 - margin, cep99 + margin)
    ax.set_ylim(-cep99 - margin, cep99 + margin)

    ax.set_title(f'CEP坐标分布 - {file_name}', fontproperties=font)
    ax.set_aspect('equal')
    ax.set_xlabel('东-西距离（m）', fontproperties=font)
    ax.set_ylabel('南-北距离（m）', fontproperties=font)
    ax.legend(prop=font)
    ax.grid()

    plt.text(0.95, 0.01, datetime.now().strftime('生成时间 %Y-%m-%d %H:%M:%S'),
             transform=ax.transAxes, ha='right', va='bottom', fontsize=8, color='red', fontproperties=font)

    plt.text(0.03, 0.97, f'平均高度: {avg_height:.2f} 米', transform=ax.transAxes,
             ha='left', va='top', fontsize=10, color='blue', fontproperties=font)

    fig.savefig(output_file, dpi=100, bbox_inches='tight')
    plt.close(fig)

def plot_bar_chart(ceps, output_file, file_name):
    # labels = ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'MAX', 'AVG'] # MAC 不再显示最大值
    labels = ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'AVG']
    fig, ax = plt.subplots(figsize=(8, 6))
    # bars = ax.bar(labels, ceps, color=['blue', 'green', 'orange', 'red', 'purple', 'gray']) # MAC 不再显示最大值
    bars = ax.bar(labels, ceps, color=['blue', 'green', 'orange', 'red', 'gray'])

    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.2f}m', xy=(bar.get_x() + bar.get_width()/2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontproperties=font)

    ax.set_title(f'CEP统计 - {file_name}', fontproperties=font)
    ax.set_ylabel('单位(米)', fontproperties=font)
    ax.grid(axis='y')
    plt.text(0.95, 0.01, datetime.now().strftime('生成时间 %Y-%m-%d %H:%M:%S'),
             transform=ax.transAxes, ha='right', va='bottom', fontsize=8, color='red', fontproperties=font)
    fig.savefig(output_file, dpi=100, bbox_inches='tight')
    plt.close(fig)

# GUI主函数
def run_gui():
    def select_file():
        file_path = filedialog.askopenfilename(
            title="选择 NMEA 数据文件",
            filetypes=[
                ("NMEA / 文本文件", "*.txt *.log *.nmea"),
                ("所有文件", "*.*"),
            ],
        )
        if file_path:
            file_path_var.set(file_path)
            status_var.set("已选择文件")

    def get_custom_anchor():
        try:
            custom_lat = float(custom_lat_var.get().strip())
            custom_lon = float(custom_lon_var.get().strip())
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的锚点经纬度")
            return None

        if not (-90 <= custom_lat <= 90 and -180 <= custom_lon <= 180):
            messagebox.showerror("输入错误", "纬度范围为 -90~90，经度范围为 -180~180")
            return None

        return custom_lat, custom_lon

    def start_analysis():
        start_time = time.time()
        file_path = file_path_var.get().strip()
        if not file_path:
            messagebox.showwarning("缺少文件", "请先选择 NMEA 数据文件")
            return

        fixed_point = get_custom_anchor()
        if fixed_point is None:
            return

        point_name = DEFAULT_ANCHOR_NAME
        print(fixed_point, "锚点")

        keyword = keyword_var.get() or default_name_key
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = "D:/python脚本生成文件集/CEP_script/"
        os.makedirs(output_dir, exist_ok=True)
        scatter_path = f"{output_dir}{file_name}-{point_name}-散点图-{current_time}.png"
        bar_path = f"{output_dir}{file_name}-{point_name}-柱状图-{current_time}.png"
        sats_output_file = f"{output_dir}{file_name}-{point_name}-可用卫星数.xlsx"

        status_var.set("正在解析和计算...")
        root.update_idletasks()

        convert_to_utf8(file_path)
        coordinates, heights, num_sats_list, raw_lats, raw_lons, gps_times = parse_nmea(file_path, keyword)
        # 计算每个点到固定点的距离，并计算CEP统计数据
        distances = calculate_distances(fixed_point, coordinates)
        # print (distances)
        # 当前点到固定点的距离
        # for i, ((lat, lon), d, raw_lat, raw_lon) in enumerate(zip(coordinates, distances, raw_lats, raw_lons)):
        #     print(f"点{i + 1}:")
        #     print(f"  原始经纬度: lat={raw_lat}, lon={raw_lon}")
        #     print(f"  解析后: ({lat}, {lon})")
        #     print(f"  距离: {d:.3f} 米")
        #     print("-" * 40)


        ceps = calculate_cep(distances)
        avg_height = calculate_average_height(heights)

        save_num_sats_to_excel(num_sats_list, coordinates, gps_times, sats_output_file)  # 保存可用卫星数到Excel文件

        print(f"平均高度: {avg_height:.2f} 米")
        print("最大高度:", max(heights))
        print("最小高度:", min(heights))

        plot_points(fixed_point, coordinates, distances, ceps, scatter_path, file_name, avg_height)
        plot_bar_chart(ceps, bar_path, file_name)

        os.startfile(output_dir)
        status_var.set("处理完成")
        messagebox.showinfo("处理成功", "分析完成，结果已生成")
        print(f"运行耗时: {time.time() - start_time:.2f} 秒")

    root = Tk()
    root.title(f"{APP_TITLE} - 自定义锚点")
    root.geometry("680x520")
    root.minsize(620, 500)
    root.configure(bg="#f4f7fb")

    icon_path = resource_path(APP_ICON)
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", font=("Microsoft YaHei UI", 10))
    style.configure("App.TFrame", background="#f4f7fb")
    style.configure("Header.TFrame", background="#0f3447")
    style.configure("Title.TLabel", background="#0f3447", foreground="#ffffff", font=("Microsoft YaHei UI", 20, "bold"))
    style.configure("Subtitle.TLabel", background="#0f3447", foreground="#bfe8e2", font=("Microsoft YaHei UI", 10))
    style.configure("Section.TLabelframe", background="#f4f7fb", borderwidth=1, relief="solid")
    style.configure("Section.TLabelframe.Label", background="#f4f7fb", foreground="#163447", font=("Microsoft YaHei UI", 11, "bold"))
    style.configure("Field.TLabel", background="#f4f7fb", foreground="#334155")
    style.configure("Path.TLabel", background="#f4f7fb", foreground="#475569")
    style.configure("Status.TLabel", background="#f4f7fb", foreground="#0f766e")
    style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(18, 9))
    style.configure("Secondary.TButton", padding=(14, 8))

    main_frame = ttk.Frame(root, style="App.TFrame", padding=22)
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=1)

    header_frame = ttk.Frame(main_frame, style="Header.TFrame", padding=(20, 18))
    header_frame.grid(row=0, column=0, sticky="ew")
    header_frame.columnconfigure(0, weight=1)
    ttk.Label(header_frame, text="CEP 分析工具", style="Title.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(header_frame, text="自定义锚点 · NMEA 数据分析 · 图表与卫星数导出", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))

    custom_lat_var = StringVar(root)
    custom_lon_var = StringVar(root)

    anchor_frame = ttk.LabelFrame(main_frame, text="自定义锚点", style="Section.TLabelframe", padding=(18, 14))
    anchor_frame.grid(row=1, column=0, sticky="ew", pady=(18, 12))
    anchor_frame.columnconfigure(1, weight=1)
    anchor_frame.columnconfigure(3, weight=1)

    ttk.Label(anchor_frame, text="纬度", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
    ttk.Entry(anchor_frame, textvariable=custom_lat_var).grid(row=0, column=1, sticky="ew", padx=(0, 18))
    ttk.Label(anchor_frame, text="经度", style="Field.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 10))
    ttk.Entry(anchor_frame, textvariable=custom_lon_var).grid(row=0, column=3, sticky="ew")

    settings_frame = ttk.LabelFrame(main_frame, text="数据设置", style="Section.TLabelframe", padding=(18, 14))
    settings_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    settings_frame.columnconfigure(1, weight=1)

    ttk.Label(settings_frame, text="NMEA 关键字", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 14))
    keyword_var = StringVar(root, value="$GNGGA")
    ttk.Entry(settings_frame, textvariable=keyword_var).grid(row=0, column=1, sticky="ew")

    file_frame = ttk.LabelFrame(main_frame, text="输入文件", style="Section.TLabelframe", padding=(18, 14))
    file_frame.grid(row=3, column=0, sticky="ew", pady=(0, 12))
    file_frame.columnconfigure(0, weight=1)

    file_path_var = StringVar(root)
    ttk.Button(file_frame, text="选择文件", command=select_file, style="Secondary.TButton").grid(row=0, column=0, sticky="w")
    file_label = ttk.Label(file_frame, textvariable=file_path_var, style="Path.TLabel", wraplength=560)
    file_label.grid(row=1, column=0, sticky="ew", pady=(10, 0))

    footer_frame = ttk.Frame(main_frame, style="App.TFrame")
    footer_frame.grid(row=4, column=0, sticky="ew", pady=(6, 0))
    footer_frame.columnconfigure(0, weight=1)

    status_var = StringVar(root, value="待处理")
    ttk.Label(footer_frame, textvariable=status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Button(footer_frame, text="开始分析", command=start_analysis, style="Primary.TButton").grid(row=0, column=1, sticky="e")

    root.mainloop()

# 启动 GUI
if __name__ == '__main__':
    run_gui()


# 7月9日更新
# 自定义锚点功能
# 增加了可用卫星数的统计和保存到Excel文件

# 2026年4月14日 增加了一点数据过滤条件
