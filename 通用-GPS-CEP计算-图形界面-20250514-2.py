import os
import time
import chardet
import matplotlib.pyplot as plt
from geopy.distance import geodesic
import numpy as np
from datetime import datetime
from tkinter import Tk, filedialog, Label, Button, StringVar, OptionMenu, Entry
from matplotlib.font_manager import FontProperties

# 设置中文字体
font = FontProperties(fname='C:/Windows/Fonts/simhei.ttf')  # 使用黑体字体

# 固定点选项
fixed_points = {
    "全天空（泰维篮球场）": (34.18969283, 108.8803075),
    "半天空（物联西侧）": (34.1878804, 108.875722),
    "峡谷（产业园篮球场）": (34.1875013, 108.8764035),
    "仪表（北京）": (39.90556, 116.39139)
}

default_nmea_key = "$GNGGA"

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
def parse_nmea(file_path, keyword):
    coordinates = []
    heights = []
    with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
        for line in f:
            if keyword in line:
                parts = line.split(',')
                if len(parts) >= 12:
                    try:
                        lat_raw = float(parts[2])
                        lat_dir = parts[3]
                        lat = (lat_raw // 100) + ((lat_raw % 100) / 60)
                        if lat_dir == 'S':
                            lat = -lat
                        lon_raw = float(parts[4])
                        lon_dir = parts[5]
                        lon = (lon_raw // 100) + ((lon_raw % 100) / 60)
                        if lon_dir == 'W':
                            lon = -lon
                        try:
                            height = float(parts[9])
                            heights.append(height)
                        except:
                            continue
                        coordinates.append((lat, lon))
                    except:
                        continue
    return coordinates, heights

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
        max(sorted_distances),
        np.mean(distances)
    )

def plot_points(fixed_point, coordinates, distances, ceps, output_file, file_name, avg_height):
    cep50, cep68, cep95, cep99, max_d, _ = ceps
    fixed_lat, fixed_lon = fixed_point
    x_coords = [(geodesic((fixed_lat, fixed_lon), (fixed_lat, lon)).meters * (1 if lon >= fixed_lon else -1)) for lat, lon in coordinates]
    y_coords = [(geodesic((fixed_lat, fixed_lon), (lat, fixed_lon)).meters * (1 if lat >= fixed_lat else -1)) for lat, lon in coordinates]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter([0], [0], color='black', label='基准点', s=10)
    for x, y, d in zip(x_coords, y_coords, distances):
        color = 'blue' if d <= cep50 else 'green' if d <= cep68 else 'orange' if d <= cep95 else 'red' if d <= cep99 else 'purple'
        ax.scatter(x, y, color=color, s=5)

    for r, label, color in zip([cep50, cep68, cep95, cep99, max_d],
                                ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'MAX'],
                                ['blue', 'green', 'orange', 'red', 'purple']):
        ax.add_artist(plt.Circle((0, 0), r, color=color, fill=False, linestyle='--', label=f'{label}: {r:.2f}m'))

    # 设置图像范围，确保圆完整显示
    margin = max_d * 0.1  # 添加10%的边距
    ax.set_xlim(-max_d - margin, max_d + margin)
    ax.set_ylim(-max_d - margin, max_d + margin)

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
    labels = ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'MAX', 'AVG']
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, ceps, color=['blue', 'green', 'orange', 'red', 'purple', 'gray'])

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
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        file_path_var.set(file_path)

    def start_analysis():
        start_time = time.time()
        file_path = file_path_var.get()
        if not file_path:
            return

        point_name = point_var.get()
        fixed_point = fixed_points[point_name]
        keyword = keyword_var.get() or default_nmea_key
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = "D:/python脚本生成文件集/CEP_script/"
        os.makedirs(output_dir, exist_ok=True)
        scatter_path = f"{output_dir}{file_name}-{point_name}-散点图-{current_time}.png"
        bar_path = f"{output_dir}{file_name}-{point_name}-柱状图-{current_time}.png"

        convert_to_utf8(file_path)
        coordinates, heights = parse_nmea(file_path, keyword)
        distances = calculate_distances(fixed_point, coordinates)
        ceps = calculate_cep(distances)
        avg_height = calculate_average_height(heights)

        print(f"平均高度: {avg_height:.2f} 米")
        print("最大高度:", max(heights))
        print("最小高度:", min(heights))

        plot_points(fixed_point, coordinates, distances, ceps, scatter_path, file_name, avg_height)
        plot_bar_chart(ceps, bar_path, file_name)

        os.startfile(output_dir)
        print(f"运行耗时: {time.time() - start_time:.2f} 秒")

    root = Tk()
    root.title("CEP 分析工具-木林夕")
    root.geometry("500x300")

    Label(root, text="选择固定点:").pack()
    point_var = StringVar(root)
    point_var.set("半天空（物联西侧）")
    OptionMenu(root, point_var, *fixed_points.keys()).pack()

    Label(root, text="NMEA 关键字（默认 $GNGGA）:").pack()
    keyword_var = StringVar(root, value="$GNGGA")
    Entry(root, textvariable=keyword_var).pack()

    Label(root, text="选择 NMEA 数据文件:").pack()
    file_path_var = StringVar()
    Button(root, text="选择文件", command=select_file).pack()
    Label(root, textvariable=file_path_var).pack()

    Button(root, text="开始分析", command=start_analysis).pack(pady=10)
    root.mainloop()

# 启动 GUI
if __name__ == '__main__':
    run_gui()
