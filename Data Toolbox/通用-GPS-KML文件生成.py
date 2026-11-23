import re
import codecs
import os
import xml.etree.ElementTree as ET
from tkinter import Tk, filedialog
from datetime import datetime

directory = 'D:/python脚本生成文件集/GPS-KML文件生成'

# 如果目录不存在，自动创建目录
if not os.path.exists(directory):
    os.makedirs(directory)


def convert_to_utf8(input_file):
    # 将输入文件转换为UTF-8 格式并返回转换后的内容
    with open(input_file, 'rb') as f:
        raw_data = f.read()

    with codecs.open(input_file, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()


def parse_nmea(nmea_lines):
    """解析NMEA GGA和RMC语句，提取经纬度、时间、海拔、日期和速度"""
    gps_data = []
    gga_pattern = re.compile(
        r'\$(?:GNGGA|GPGGA|BDGGA),(\d{6}\.\d+),(\d{2})(\d{2}\.\d+),([NS]),(\d{3})(\d{2}\.\d+),([EW]),\d+,\d+,\d*\.\d*,(-?\d*\.\d*),M')
    rmc_pattern = re.compile(
        r'\$(?:GNRMC|GPRMC|BDGGA),(\d{6}\.\d+),[AV],(\d{2})(\d{2}\.\d+),([NS]),(\d{3})(\d{2}\.\d+),([EW]),(\d*\.\d*),.*,?(\d{6})')

    date_info = ""  # 存储日期信息
    speed_info = "0.0"  # 存储速度信息

    for line in nmea_lines:
        rmc_match = rmc_pattern.search(line)
        if rmc_match:
            date_info = f"{rmc_match.group(9)[4:6]}-{rmc_match.group(9)[2:4]}-{rmc_match.group(9)[:2]}"  # DDMMYY
            speed_info = rmc_match.group(8) if rmc_match.group(8) else "0.0"  # 速度 (节)

        gga_match = gga_pattern.search(line)
        if gga_match:
            time_utc = f"{gga_match.group(1)[:2]}:{gga_match.group(1)[2:4]}:{gga_match.group(1)[4:6]}"  # HHMMSS
            latitude = float(gga_match.group(2)) + float(gga_match.group(3)) / 60.0
            if gga_match.group(4) == 'S':
                latitude = -latitude
            longitude = float(gga_match.group(5)) + float(gga_match.group(6)) / 60.0
            if gga_match.group(7) == 'W':
                longitude = -longitude
            altitude = float(gga_match.group(8)) if gga_match.group(8) else 0.0
            latitude = round(latitude, 6)
            longitude = round(longitude, 6)
            gps_data.append((latitude, longitude, altitude, time_utc, date_info, speed_info))

    return gps_data


def generate_kml_tracker(gps_data, output_file):
    """生成仅包含轨迹的 KML 文件"""
    kml = ET.Element('kml', xmlns='http://www.opengis.net/kml/2.2')
    document = ET.SubElement(kml, 'Document')
    placemark = ET.SubElement(document, 'Placemark')
    ET.SubElement(placemark, 'name').text = 'GPS Tracker'
    linestring = ET.SubElement(placemark, 'LineString')
    ET.SubElement(linestring, 'coordinates').text = " ".join(
        f"{lon},{lat},{alt}" for lat, lon, alt, _, _, _ in gps_data)

    # 设置线条样式（蓝色，宽度3）
    style = ET.SubElement(placemark, 'Style')
    linestyle = ET.SubElement(style, 'LineStyle')
    ET.SubElement(linestyle, 'color').text = 'ffff0000'  # 蓝色 (AABBGGRR)
    ET.SubElement(linestyle, 'width').text = '3'

    tree = ET.ElementTree(kml)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)


def generate_kml_points(gps_data, output_file):
    """生成包含详细 GPS 点信息的 KML 文件"""
    kml = ET.Element('kml', xmlns='http://www.opengis.net/kml/2.2')
    document = ET.SubElement(kml, 'Document')

    for lat, lon, alt, time_utc, date_info, speed_info in gps_data:
        placemark = ET.SubElement(document, 'Placemark')
        ET.SubElement(placemark,
                      'description').text = f"UTC Time: {time_utc}\nDate: {date_info}\nSpeed: {speed_info} knots\nLatitude: {lat}\nLongitude: {lon}\nAltitude: {alt}m"
        point = ET.SubElement(placemark, 'Point')
        ET.SubElement(point, 'coordinates').text = f"{lon},{lat},{alt}"

    tree = ET.ElementTree(kml)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)


def main():
    """主函数，选择文件并生成 KML"""
    Tk().withdraw()
    file_path = filedialog.askopenfilename(title="选择NMEA TXT文件", filetypes=[("Text Files", "*.txt")])
    if not file_path:
        print("未选择文件，退出。")
        return

    print(f"正在处理文件: {file_path}")
    lines = convert_to_utf8(file_path)
    gps_data = parse_nmea(lines)

    if not gps_data:
        print("未找到有效的GPS数据。")
        return

    # 获取文件名（不带后缀）
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    # 获取当前时间并格式化为字符串
    current_time = datetime.now().strftime('%Y%m%d_%H%M%S')

    generate_kml_tracker(gps_data, f'{directory}/{file_name}-{current_time}-tracker.kml')
    generate_kml_points(gps_data, f'{directory}/{file_name}-{current_time}-points.kml')

    print("KML 文件生成完成：tracker.kml, points.kml")


if __name__ == "__main__":
    main()

os.startfile(directory)
