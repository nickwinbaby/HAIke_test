"""从 NMEA 文本生成轨迹和点位 KML。"""

from dataclasses import dataclass
from datetime import datetime
import codecs
import os
import re
import xml.etree.ElementTree as ET


GGA_PATTERN = re.compile(
    r'\$(?:GNGGA|GPGGA|BDGGA),(\d{6}\.\d+),(\d{2})(\d{2}\.\d+),([NS]),(\d{3})(\d{2}\.\d+),([EW]),\d+,\d+,\d*\.\d*,(-?\d*\.\d*),M'
)
RMC_PATTERN = re.compile(
    r'\$(?:GNRMC|GPRMC|BDGGA),(\d{6}\.\d+),[AV],(\d{2})(\d{2}\.\d+),([NS]),(\d{3})(\d{2}\.\d+),([EW]),(\d*\.\d*),.*,?(\d{6})'
)


@dataclass(frozen=True)
class NmeaKmlResult:
    tracker_file: str
    point_file: str
    point_count: int


def convert_to_utf8(input_file):
    """以 UTF-8 容错方式读取并返回所有行。"""
    with open(input_file, "rb") as file_obj:
        file_obj.read()
    with codecs.open(input_file, "r", encoding="utf-8", errors="replace") as file_obj:
        return file_obj.readlines()


def parse_nmea(nmea_lines):
    """解析 NMEA GGA 和 RMC 语句，提取 KML 所需字段。"""
    gps_data = []
    date_info = ""
    speed_info = "0.0"

    for line in nmea_lines:
        rmc_match = RMC_PATTERN.search(line)
        if rmc_match:
            date_info = f"{rmc_match.group(9)[4:6]}-{rmc_match.group(9)[2:4]}-{rmc_match.group(9)[:2]}"
            speed_info = rmc_match.group(8) if rmc_match.group(8) else "0.0"

        gga_match = GGA_PATTERN.search(line)
        if gga_match:
            time_utc = f"{gga_match.group(1)[:2]}:{gga_match.group(1)[2:4]}:{gga_match.group(1)[4:6]}"
            latitude = float(gga_match.group(2)) + float(gga_match.group(3)) / 60.0
            if gga_match.group(4) == "S":
                latitude = -latitude
            longitude = float(gga_match.group(5)) + float(gga_match.group(6)) / 60.0
            if gga_match.group(7) == "W":
                longitude = -longitude
            altitude = float(gga_match.group(8)) if gga_match.group(8) else 0.0
            gps_data.append(
                (round(latitude, 6), round(longitude, 6), altitude, time_utc, date_info, speed_info)
            )
    return gps_data


def generate_kml_tracker(gps_data, output_file):
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(kml, "Document")
    placemark = ET.SubElement(document, "Placemark")
    ET.SubElement(placemark, "name").text = "GPS Tracker"
    linestring = ET.SubElement(placemark, "LineString")
    ET.SubElement(linestring, "coordinates").text = " ".join(
        f"{lon},{lat},{alt}" for lat, lon, alt, _, _, _ in gps_data
    )
    style = ET.SubElement(placemark, "Style")
    linestyle = ET.SubElement(style, "LineStyle")
    ET.SubElement(linestyle, "color").text = "ffff0000"
    ET.SubElement(linestyle, "width").text = "3"
    ET.ElementTree(kml).write(output_file, encoding="utf-8", xml_declaration=True)


def generate_kml_points(gps_data, output_file):
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(kml, "Document")
    for index, (lat, lon, alt, time_utc, date_info, speed_info) in enumerate(gps_data, start=1):
        placemark = ET.SubElement(document, "Placemark")
        ET.SubElement(placemark, "name").text = str(index)
        ET.SubElement(placemark, "description").text = (
            f"UTC Time: {time_utc}\nDate: {date_info}\nSpeed: {speed_info} knots\n"
            f"Latitude: {lat}\nLongitude: {lon}\nAltitude: {alt}m"
        )
        point = ET.SubElement(placemark, "Point")
        ET.SubElement(point, "coordinates").text = f"{lon},{lat},{alt}"
    ET.ElementTree(kml).write(output_file, encoding="utf-8", xml_declaration=True)


def generate_nmea_kml(file_path, output_dir, now=None):
    """执行完整的 NMEA -> KML 处理流程。"""
    os.makedirs(output_dir, exist_ok=True)
    gps_data = parse_nmea(convert_to_utf8(file_path))
    if not gps_data:
        raise ValueError("未找到有效的GPS数据")

    file_name = os.path.splitext(os.path.basename(file_path))[0]
    current_time = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    tracker_file = os.path.join(output_dir, f"{file_name}-{current_time}-tracker.kml")
    point_file = os.path.join(output_dir, f"{file_name}-{current_time}-points.kml")
    generate_kml_tracker(gps_data, tracker_file)
    generate_kml_points(gps_data, point_file)
    return NmeaKmlResult(tracker_file, point_file, len(gps_data))

