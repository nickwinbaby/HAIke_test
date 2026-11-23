import pandas as pd
import simplekml
import os
from tkinter import Tk, filedialog

# ================== 选择Excel文件 ==================
Tk().withdraw()
file_path = filedialog.askopenfilename(
    title="选择Excel文件",
    filetypes=[("Excel files", "*.xlsx *.xls")]
)

if not file_path:
    print("❌ 未选择文件")
    exit()

# ================== 读取Excel ==================
df = pd.read_excel(file_path)

# 去掉列名空格（防止出错）
df.columns = df.columns.str.strip()

# ================== 输出目录 ==================
output_dir = r"D:\python脚本生成文件集\GPS-KML文件生成"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 文件名
base_name = os.path.splitext(os.path.basename(file_path))[0]

# ================== 创建KML对象 ==================
kml_line = simplekml.Kml()
kml_point = simplekml.Kml()

coords = []

# ================== 遍历数据 ==================
for index, row in df.iterrows():
    try:
        # ----------- 获取方向字段 -----------
        lon_dir_raw = str(row["经度"]).strip()   # F列
        lat_dir_raw = str(row["纬度"]).strip()   # G列

        # ----------- 获取数值 -----------
        lon_val = row["经度值"]   # J列
        lat_val = row["纬度值"]   # K列

        # 空值跳过
        if pd.isna(lon_val) or pd.isna(lat_val):
            continue

        lon_val = float(lon_val)
        lat_val = float(lat_val)

        # ----------- 判断经度方向 -----------
        if ("西" in lon_dir_raw) or ("W" in lon_dir_raw.upper()) or ("-" in lon_dir_raw):
            lon = -abs(lon_val)
        else:
            lon = abs(lon_val)

        # ----------- 判断纬度方向 -----------
        if ("南" in lat_dir_raw) or ("S" in lat_dir_raw.upper()) or ("-" in lat_dir_raw):
            lat = -abs(lat_val)
        else:
            lat = abs(lat_val)

        # 保存轨迹点
        coords.append((lon, lat))

        # ----------- 备注信息 -----------
        description = f"""
GPS时间: {row.get('GPS时间', '')}
卫星数: {row.get('卫星数', '')}
高度: {row.get('高度', '')}
GPS速度: {row.get('GPS速度', '')}
航向角: {row.get('航向角', '')}
PDOP: {row.get('PDOP', '')}
HDOP: {row.get('HDOP', '')}
HACC: {row.get('HACC', '')}
"""

        # ----------- 创建点 -----------
        # kml_point.newpoint(
        #     coords=[(lon, lat)],
        #     description=description
        # )
        #
        point_name = f"点{index + 1}"

        kml_point.newpoint(
            name=point_name,
            coords=[(lon, lat)],
            description=description
        )


    except Exception as e:
        print(f"⚠️ 第{index+2}行处理失败: {e}")

# ================== 创建轨迹线 ==================
if coords:
    line = kml_line.newlinestring(
        name="Tracker",
        coords=coords
    )
    line.style.linestyle.width = 3

# ================== 保存文件 ==================
tracker_file = os.path.join(output_dir, f"{base_name}_tracker.kml")
point_file = os.path.join(output_dir, f"{base_name}_point.kml")

kml_line.save(tracker_file)
kml_point.save(point_file)

print("✅ 生成完成！")
print("轨迹文件:", tracker_file)
print("点位文件:", point_file)