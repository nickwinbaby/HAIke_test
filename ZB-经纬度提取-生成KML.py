import re
import os
from tkinter import Tk, filedialog

# =========================
# 选择TXT文件
# =========================
Tk().withdraw()
txt_path = filedialog.askopenfilename(
    title="选择TXT文件",
    filetypes=[("Text Files", "*.txt")]
)

if not txt_path:
    print("未选择文件")
    exit()

# =========================
# 读取TXT内容
# =========================
with open(txt_path, "r", encoding="utf-8") as f:
    content = f.read()

# =========================
# 提取 时间 + 经纬度 + speed
# =========================
pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"lon":\s*([0-9\.]+).*?"lat":\s*([0-9\.]+).*?"speed":\s*([0-9\.]+)'
matches = re.findall(pattern, content, re.S)

if not matches:
    print("未找到经纬度数据")
    exit()

coords = []
points = []

for time_str, lon, lat, speed in matches:
    coords.append(f"{lon},{lat},0")
    points.append((time_str, lon, lat, speed))

# =========================
# 生成 点 KML
# =========================
point_placemarks = ""

for i, (time_str, lon, lat, speed) in enumerate(points):
    speed_kmh = float(speed) * 0.1

    point_placemarks += f"""
    <Placemark>
        <name>Point {i+1}</name>
        <description><![CDATA[
        时间: {time_str}<br/>
        速度: {speed_kmh:.1f} km/h<br/>
        经度: {lon}<br/>
        纬度: {lat}
        ]]></description>
        <Point>
            <coordinates>{lon},{lat},0</coordinates>
        </Point>
    </Placemark>
    """

point_kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>

<Style id="pointStyle">
    <IconStyle>
        <color>ff00ff00</color>
        <scale>0.6</scale>
    </IconStyle>
</Style>

{point_placemarks}

</Document>
</kml>
'''

# =========================
# 生成 轨迹 KML
# =========================
track_kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>

<Style id="redLine">
    <LineStyle>
        <color>ff0000ff</color>
        <width>3</width>
    </LineStyle>
</Style>

<Placemark>
    <name>GPS Track</name>
    <styleUrl>#redLine</styleUrl>
    <LineString>
        <tessellate>1</tessellate>
        <coordinates>
            {' '.join(coords)}
        </coordinates>
    </LineString>
</Placemark>

</Document>
</kml>
'''

# =========================
# 输出目录
# =========================
output_dir = r"D:\python脚本生成文件集\GPS_ZB"
os.makedirs(output_dir, exist_ok=True)

# =========================
# 文件名
# =========================
base_name = os.path.splitext(os.path.basename(txt_path))[0]

point_path = os.path.join(output_dir, base_name + "_point.kml")
track_path = os.path.join(output_dir, base_name + "_tracker.kml")

# =========================
# 保存文件
# =========================
with open(point_path, "w", encoding="utf-8") as f:
    f.write(point_kml)

with open(track_path, "w", encoding="utf-8") as f:
    f.write(track_kml)

print("生成成功：")
print("点文件：", point_path)
print("轨迹文件：", track_path)

# =========================
# 打开目录
# =========================
os.startfile(output_dir)