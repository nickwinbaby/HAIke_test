"""电子围栏几何计算与 KML 文件生成。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
EARTH_RADIUS_METERS = 6_371_008.8
CIRCLE_VERTEX_COUNT = 72
FILL_COLOR = "B3FFCC66"
LINE_COLOR = "FFB35C12"

ET.register_namespace("", KML_NAMESPACE)


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float


def parse_coordinate(latitude_text, longitude_text):
    """解析并校验一组纬度、经度。"""
    try:
        latitude = float(str(latitude_text).strip())
        longitude = float(str(longitude_text).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("纬度和经度都必须填写有效数字") from exc
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("纬度范围必须在 -90 到 90 之间")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("经度范围必须在 -180 到 180 之间")
    return GeoPoint(latitude, longitude)


def circle_ring(center, radius_meters, vertex_count=CIRCLE_VERTEX_COUNT):
    """在 WGS84 平均半径球面上计算圆形围栏边界。"""
    if not math.isfinite(radius_meters) or radius_meters <= 0:
        raise ValueError("圆形半径必须是大于 0 的米数")
    if vertex_count < 12:
        raise ValueError("圆形边界点数量不能少于 12")

    angular_distance = radius_meters / EARTH_RADIUS_METERS
    latitude1 = math.radians(center.latitude)
    longitude1 = math.radians(center.longitude)
    boundary = []
    for index in range(vertex_count):
        bearing = 2 * math.pi * index / vertex_count
        latitude2 = math.asin(
            math.sin(latitude1) * math.cos(angular_distance)
            + math.cos(latitude1) * math.sin(angular_distance) * math.cos(bearing)
        )
        longitude2 = longitude1 + math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(latitude1),
            math.cos(angular_distance) - math.sin(latitude1) * math.sin(latitude2),
        )
        longitude_degrees = (math.degrees(longitude2) + 540) % 360 - 180
        boundary.append(GeoPoint(math.degrees(latitude2), longitude_degrees))
    boundary.append(boundary[0])
    return boundary


def rectangle_ring(top_left, bottom_right):
    """根据西北角和东南角构造闭合矩形。"""
    if top_left.latitude <= bottom_right.latitude:
        raise ValueError("左上角纬度应大于右下角纬度")
    if top_left.longitude >= bottom_right.longitude:
        raise ValueError("左上角经度应小于右下角经度")
    top_right = GeoPoint(top_left.latitude, bottom_right.longitude)
    bottom_left = GeoPoint(bottom_right.latitude, top_left.longitude)
    return [top_left, top_right, bottom_right, bottom_left, top_left]


def polygon_ring(points: Iterable[GeoPoint]):
    """校验并闭合多边形边界。"""
    ring = list(points)
    if len(ring) < 3:
        raise ValueError("多边形至少需要 3 个有效坐标点")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def parse_polygon_text(text):
    """解析每行一组“纬度,经度”的多边形顶点。"""
    points = []
    for index, line in enumerate(str(text).splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [part for part in line.replace("，", ",").replace(" ", ",").split(",") if part]
        if len(parts) != 2:
            raise ValueError(f"多边形第 {index} 行应为“纬度,经度”")
        try:
            points.append(parse_coordinate(parts[0], parts[1]))
        except ValueError as exc:
            raise ValueError(f"多边形第 {index} 行：{exc}") from exc
    return polygon_ring(points)


def _sub_element(parent, tag, text=None):
    element = ET.SubElement(parent, f"{{{KML_NAMESPACE}}}{tag}")
    if text is not None:
        element.text = text
    return element


def _format_number(value):
    return format(value, ".12g")


def _coordinate_text(point):
    return f"{_format_number(point.longitude)},{_format_number(point.latitude)},0"


def build_fence_kml(ring, fence_name):
    """构造包含一个填充电子围栏的 KML 文档。"""
    closed_ring = polygon_ring(ring)
    root = ET.Element(f"{{{KML_NAMESPACE}}}kml")
    document = _sub_element(root, "Document")
    _sub_element(document, "name", fence_name)
    style = _sub_element(document, "Style")
    style.set("id", "fenceStyle")
    line_style = _sub_element(style, "LineStyle")
    _sub_element(line_style, "color", LINE_COLOR)
    _sub_element(line_style, "width", "2")
    poly_style = _sub_element(style, "PolyStyle")
    _sub_element(poly_style, "color", FILL_COLOR)
    _sub_element(poly_style, "fill", "1")
    _sub_element(poly_style, "outline", "1")
    placemark = _sub_element(document, "Placemark")
    _sub_element(placemark, "name", fence_name)
    _sub_element(placemark, "styleUrl", "#fenceStyle")
    polygon = _sub_element(placemark, "Polygon")
    _sub_element(polygon, "tessellate", "1")
    _sub_element(polygon, "altitudeMode", "clampToGround")
    outer_boundary = _sub_element(polygon, "outerBoundaryIs")
    linear_ring = _sub_element(outer_boundary, "LinearRing")
    _sub_element(
        linear_ring,
        "coordinates",
        "\n" + "\n".join(_coordinate_text(point) for point in closed_ring) + "\n",
    )
    return ET.ElementTree(root)


def write_fence_kml(ring, fence_name, output_path):
    """写入电子围栏 KML，并返回绝对路径。"""
    path = Path(output_path).expanduser().resolve()
    if path.suffix.lower() != ".kml":
        path = path.with_suffix(".kml")
    tree = build_fence_kml(ring, fence_name)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def build_point_kml(points, document_name="地图标注点"):
    """将地图上选择的经纬度点生成 KML。"""
    point_list = list(points)
    if not point_list:
        raise ValueError("至少需要一个标注点")
    root = ET.Element(f"{{{KML_NAMESPACE}}}kml")
    document = _sub_element(root, "Document")
    _sub_element(document, "name", document_name)
    for index, point in enumerate(point_list, start=1):
        placemark = _sub_element(document, "Placemark")
        _sub_element(placemark, "name", f"点 {index}")
        _sub_element(placemark, "description", f"纬度: {point.latitude:.6f}\n经度: {point.longitude:.6f}")
        point_node = _sub_element(placemark, "Point")
        _sub_element(point_node, "coordinates", _coordinate_text(point))
    return ET.ElementTree(root)


def write_point_kml(points, document_name, output_path):
    path = Path(output_path).expanduser().resolve()
    if path.suffix.lower() != ".kml":
        path = path.with_suffix(".kml")
    tree = build_point_kml(points, document_name)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path

