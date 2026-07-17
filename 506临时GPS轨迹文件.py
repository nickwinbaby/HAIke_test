import pandas as pd
import simplekml
from tkinter import Tk, filedialog
import os
import json

# ======================
# 配置
# ======================
# 图标可替换，如果用 arrow.png 需要 HEADING_OFFSET
# 推荐使用 track.png 或 triangle.png，这样北向0无需修正
ICON_URL = "http://maps.google.com/mapfiles/kml/shapes/track.png"
HEADING_OFFSET = 0  # 如果箭头不正北，可调（一般 track.png = 0 就正北）

# ======================
# 选择文件
# ======================
def select_file():
    root = Tk()
    root.withdraw()
    return filedialog.askopenfilename(
        title="选择数据文件",
        filetypes=[("Data files", "*.xlsx *.xls *.csv")]
    )

file_path = select_file()

if not file_path:
    print("未选择文件")
    exit()

# ======================
# 读取文件
# ======================
ext = os.path.splitext(file_path)[1].lower()

try:
    if ext == ".xlsx":
        df = pd.read_excel(file_path, engine="openpyxl")
    elif ext == ".xls":
        df = pd.read_excel(file_path, engine="xlrd")
    elif ext == ".csv":
        df = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
    else:
        print("不支持的文件格式")
        exit()
except Exception as e:
    print("读取失败:", e)
    exit()

# ======================
# 从第2行开始
# ======================
data = df.iloc[1:].reset_index(drop=True)

# ======================
# 转换字段
# ======================
lon_col = pd.to_numeric(data.iloc[:, 2], errors='coerce')   # C
lat_col = pd.to_numeric(data.iloc[:, 3], errors='coerce')   # D
speed_col = pd.to_numeric(data.iloc[:, 4], errors='coerce') # E
heading_col = pd.to_numeric(data.iloc[:, 5], errors='coerce') # F
time_col = data.iloc[:, 7]  # H列

# ======================
# 构建 JSON 数据
# ======================
records = []
for lon, lat, speed, heading, t in zip(lon_col, lat_col, speed_col, heading_col, time_col):
    if pd.isna(lon) or pd.isna(lat):
        continue
    rec = {
        "lon": float(lon),
        "lat": float(lat),
        "speed": None if pd.isna(speed) else float(speed),
        "heading": None if pd.isna(heading) else float(heading),
        "time": str(t)
    }
    records.append(rec)

# 保存 JSON
json_path = os.path.splitext(file_path)[0] + ".json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

# ======================
# 文件名
# ======================
base_name = os.path.splitext(file_path)[0]
point_file = base_name + "-POINT.kml"
track_file = base_name + "-TRACKER.kml"

# ======================
# 速度颜色函数
# ======================
speeds = [r["speed"] for r in records if r["speed"] is not None]
min_speed = min(speeds) if speeds else 0
max_speed = max(speeds) if speeds else 1

def speed_to_color(speed):
    if speed is None:
        return simplekml.Color.white
    ratio = (speed - min_speed) / (max_speed - min_speed + 1e-6)
    if ratio < 0.5:
        r = int(255 * ratio * 2)
        g = int(255 * ratio * 2)
        b = 255
    else:
        r = 255
        g = int(255 * (1 - (ratio - 0.5) * 2))
        b = 0
    return simplekml.Color.rgb(r, g, b)

# ======================
# POINT KML
# ======================
kml_point = simplekml.Kml()

for r in records:
    p = kml_point.newpoint(coords=[(r["lon"], r["lat"])])
    # 描述
    p.description = f"""
时间: {r['time']}
速度: {r['speed']}
航向角: {r['heading']}
"""
    # 图标
    p.style.iconstyle.icon.href = ICON_URL
    # 修正航向角
    if r["heading"] is not None:
        heading_corrected = (r["heading"] + HEADING_OFFSET) % 360
        p.style.iconstyle.heading = heading_corrected
    # 颜色和大小
    p.style.iconstyle.color = speed_to_color(r["speed"])
    p.style.iconstyle.scale = 1

kml_point.save(point_file)

# ======================
# TRACKER KML
# ======================
kml_line = simplekml.Kml()
coords = []
prev = None

for r in records:
    current = (r["lon"], r["lat"])
    # 防飞线，可调
    if prev:
        if abs(current[0] - prev[0]) > 0.05 or abs(current[1] - prev[1]) > 0.05:
            prev = current
            continue
    coords.append(current)
    prev = current

line = kml_line.newlinestring(name="TRACK")
line.coords = coords
line.style.linestyle.color = simplekml.Color.red
line.style.linestyle.width = 4

# 给轨迹加完整描述
desc = ""
for r in records:
    desc += f"{r['time']} | 速度:{r['speed']} | 航向:{r['heading']}\n"
line.description = desc

kml_line.save(track_file)

# ======================
# 完成
# ======================
print("完成：")
print(point_file)
print(track_file)
print(json_path)