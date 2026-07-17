import os
import time
import chardet
import matplotlib.pyplot as plt
from geopy.distance import geodesic
import numpy as np
from datetime import datetime
from tkinter import Tk, filedialog, messagebox, StringVar, OptionMenu, Button, Label
from matplotlib.font_manager import FontProperties

run_start_time = time.time()

# 设置中文字体
font = FontProperties(fname='C:/Windows/Fonts/simhei.ttf')  # 使用黑体字体

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

# 提取$GNGGA行并解析经纬度
def parse_gngga(file_path):
    coordinates = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if "$GNGGA" in line:
                parts = line.split(',')
                if len(parts) > 5:
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

                        coordinates.append((lat, lon))
                    except ValueError:
                        continue
    return coordinates

# 计算距离
def calculate_distances(fixed_point, coordinates):
    distances = [geodesic(fixed_point, coord).meters for coord in coordinates]
    return distances

# 计算CEP值
def calculate_cep(distances):
    sorted_distances = sorted(distances)
    n = len(sorted_distances)

    cep50 = sorted_distances[int(0.50 * n)]
    cep68 = sorted_distances[int(0.68 * n)]
    cep95 = sorted_distances[int(0.95 * n)]
    cep99 = sorted_distances[int(0.99 * n)]
    max_distance = max(sorted_distances)
    mean_distance = np.mean(distances)

    return cep50, cep68, cep95, cep99, max_distance, mean_distance

# 绘制散点图和CEP圆
def plot_points(fixed_point, coordinates, distances, ceps, output_file, file_name):
    cep50, cep68, cep95, cep99, max_distance, _ = ceps

    # 转换经纬度为以固定点为圆心的平面距离
    fixed_lat, fixed_lon = fixed_point
    x_coords = [(geodesic((fixed_lat, fixed_lon), (fixed_lat, lon)).meters * (1 if lon >= fixed_lon else -1)) for
                lat, lon in coordinates]
    y_coords = [(geodesic((fixed_lat, fixed_lon), (lat, fixed_lon)).meters * (1 if lat >= fixed_lat else -1)) for
                lat, lon in coordinates]

    # 创建图像
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter([0], [0], color='black', label='CEP计算结果', s=10)

    for x, y, distance in zip(x_coords, y_coords, distances):
        color = 'blue' if distance <= cep50 else \
            'green' if distance <= cep68 else \
                'orange' if distance <= cep95 else \
                    'red' if distance <= cep99 else \
                        'purple'
        ax.scatter(x, y, color=color, s=5)

    # 绘制CEP圆
    for radius, label, color in zip([cep50, cep68, cep95, cep99, max_distance],
                                    ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'MAX'],
                                    ['blue', 'green', 'orange', 'red', 'purple']):
        circle = plt.Circle((0, 0), radius, color=color, fill=False, linestyle='--', label=f'{label}: {radius:.2f}m')
        ax.add_artist(circle)

    # 添加生成时间
    timestamp = datetime.now().strftime('生成时间 %Y-%m-%d %H:%M:%S')
    plt.text(0.95, 0.01, timestamp, verticalalignment='bottom', horizontalalignment='right',
             transform=ax.transAxes, color='red', fontsize=8, fontproperties=font)

    # 设置标题，包含文件名
    title = f'CEP范围内的坐标点分布 - ({file_name})'
    ax.set_title(title, fontproperties=font)

    ax.set_aspect('equal')
    ax.set_xlim(-max_distance, max_distance)
    ax.set_ylim(-max_distance, max_distance)
    ax.legend(prop=font)
    ax.set_xlabel('东-西距离（m）', fontproperties=font)
    ax.set_ylabel('南-北距离（m）', fontproperties=font)
    # 显示网格
    ax.grid()

    # 保存图像为固定大小
    fig.savefig(output_file, dpi=100, bbox_inches='tight')
    plt.close(fig)

# 绘制柱状图
def plot_bar_chart(ceps, output_file, file_name):
    labels = ['CEP50', 'CEP68', 'CEP95', 'CEP99', 'MAX', 'AVG']
    values = ceps

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, values, color=['blue', 'green', 'orange', 'red', 'purple', 'grey'])

    # 在每个柱的顶部添加标注
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.2f}m',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom', fontproperties=font)

    # 添加生成时间
    timestamp = datetime.now().strftime('生成时间 %Y-%m-%d %H:%M:%S')
    plt.text(0.95, 0.01, timestamp, verticalalignment='bottom', horizontalalignment='right',
             transform=ax.transAxes, color='red', fontsize=8, fontproperties=font)

    ax.set_xlabel('CEP类别', fontproperties=font)
    ax.set_ylabel('单位(米)', fontproperties=font)
    ax.set_title(f'CEP距离统计柱状图 - ({file_name})', fontproperties=font)
    ax.grid(axis='y')

    # 保存图像为固定大小
    fig.savefig(output_file, dpi=100, bbox_inches='tight')
    plt.close(fig)

# 主函数
def main():
    global fixed_point

    # 创建Tkinter窗口
    root = Tk()
    root.title("CEP计算器-能能出品-2025-3-18")

    # 选择固定点
    fixed_point_var = StringVar(root)
    fixed_point_var.set("全天空基点-泰维篮球场")  # 默认值

    fixed_points = {
        "全天空基点-泰维篮球场": (34.18969283, 108.8803075),
        "半天空基点-物联西侧": (34.1878804, 108.875722),
        "峡谷基点-产业园篮球场": (34.1875013, 108.8764035)
    }

    def select_file():
        file_path = filedialog.askopenfilename(title='选择文件', filetypes=[('Text Files', '*.txt')])
        file_path_var.set(file_path)

    def start_processing():
        file_path = file_path_var.get()
        if not file_path:
            messagebox.showwarning("Warning", "请选择输入文件")
            return

        fixed_point = fixed_points[fixed_point_var.get()]

        # 获取文件名（不带后缀）
        file_name = os.path.splitext(os.path.basename(file_path))[0]

        file_path_start = "D:/python脚本生成文件集/CEP_script/"
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 如果目录不存在，自动创建目录
        if not os.path.exists(file_path_start):
            os.makedirs(file_path_start)

        output_file_scatter = f'{file_path_start }{file_name}-{fixed_point_var.get()}-CEP离散点分布-{current_time}.png'
        output_file_bar = f'{file_path_start }{file_name}-{fixed_point_var.get()}-CEP距离柱状图-{current_time}.png'

        # 转换文件编码
        convert_to_utf8(file_path)

        # 提取经纬度
        coordinates = parse_gngga(file_path)

        # 计算距离
        distances = calculate_distances(fixed_point, coordinates)

        # 计算CEP
        ceps = calculate_cep(distances)

        # 绘制散点图和CEP圆
        plot_points(fixed_point, coordinates, distances, ceps, output_file_scatter, file_name)

        # 绘制柱状图
        plot_bar_chart(ceps, output_file_bar, file_name)

        messagebox.showinfo("Success", "处理成功")

    # 文件路径变量
    file_path_var = StringVar()

    # 创建界面元素
    Label(root, text="选择固定点:").grid(row=0, column=0, padx=10, pady=10)
    OptionMenu(root, fixed_point_var, *fixed_points.keys()).grid(row=0, column=1, padx=10, pady=10)

    Label(root, text="选择输入文件:").grid(row=1, column=0, padx=10, pady=10)
    Button(root, text="浏览", command=select_file).grid(row=1, column=1, padx=10, pady=10)
    Label(root, textvariable=file_path_var).grid(row=1, column=2, padx=10, pady=10)

    Button(root, text="开始处理", command=start_processing).grid(row=2, column=0, columnspan=3, pady=20)

    root.mainloop()

# 运行主函数
if __name__ == '__main__':
    main()

run_end_time = time.time()

elapsed_time = run_end_time - run_start_time
print(f"程序运行耗时: {elapsed_time:.2f} 秒")