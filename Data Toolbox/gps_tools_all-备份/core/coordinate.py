"""WGS84、GCJ-02、BD-09 与角度表示格式转换。"""

import math
import re


PI = 3.1415926535897932384626
A = 6378245.0
EE = 0.00669342162296594323
X_PI = PI * 3000.0 / 180.0


def out_of_china(lat, lon):
    """判断是否在中国（大致矩形范围），在中国外则不做转换。"""
    return not (lat > 0.8293 and lat < 55.8271 and lon > 72.004 and lon < 137.8347)


def _transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat, lon):
    """WGS84 转 GCJ02。"""
    if out_of_china(lat, lon):
        return lat, lon

    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    d_lon = (d_lon * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    return lat + d_lat, lon + d_lon


def gcj02_to_wgs84(lat, lon):
    """GCJ02 转 WGS84。"""
    if out_of_china(lat, lon):
        return lat, lon

    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    d_lon = (d_lon * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    return lat - d_lat, lon - d_lon


def gcj02_to_bd09(lat, lon):
    """GCJ-02 转 BD-09（百度坐标）。"""
    z = math.sqrt(lon * lon + lat * lat) + 0.00002 * math.sin(lat * X_PI)
    theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * X_PI)
    return z * math.sin(theta) + 0.006, z * math.cos(theta) + 0.0065


def bd09_to_gcj02(lat, lon):
    """BD-09 转 GCJ-02。"""
    x = lon - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.sin(theta), z * math.cos(theta)


def wgs84_to_bd09(lat, lon):
    """WGS84 经 GCJ-02 转 BD-09。"""
    gcj_lat, gcj_lon = wgs84_to_gcj02(lat, lon)
    return gcj02_to_bd09(gcj_lat, gcj_lon)


def bd09_to_wgs84(lat, lon):
    """BD-09 经 GCJ-02 转 WGS84。"""
    gcj_lat, gcj_lon = bd09_to_gcj02(lat, lon)
    return gcj02_to_wgs84(gcj_lat, gcj_lon)


def _angle_parts(text):
    """提取角度文本中的数字、符号和方位。"""
    raw = str(text).strip().upper()
    if not raw:
        raise ValueError("角度不能为空")
    directions = re.findall(r"[NSEW]", raw)
    if len(directions) > 1:
        raise ValueError("角度中只能包含一个 N/S/E/W 方向")
    direction = directions[0] if directions else ""
    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", raw)
    return raw, direction, numbers


def _signed_angle(degrees, minutes, seconds, raw, direction):
    if not 0 <= minutes < 60:
        raise ValueError("分必须在 0 到 60 之间")
    if not 0 <= seconds < 60:
        raise ValueError("秒必须在 0 到 60 之间")
    negative = degrees < 0 or direction in {"S", "W"}
    if degrees < 0 and direction in {"N", "E"}:
        raise ValueError("负号与 N/E 方向冲突")
    value = abs(degrees) + minutes / 60.0 + seconds / 3600.0
    value = -value if negative else value
    if not -180 <= value <= 180:
        raise ValueError("角度换算结果必须在 -180 到 180 之间")
    return value


def dms_to_decimal(text):
    """度分秒转十进制度，如 34°11′21.67″。"""
    raw, direction, numbers = _angle_parts(text)
    if len(numbers) != 3:
        raise ValueError("度分秒格式应包含度、分、秒，例如 34°11′21.67″")
    return _signed_angle(float(numbers[0]), float(numbers[1]), float(numbers[2]), raw, direction)


def dm_to_decimal(text):
    """度分转十进制度，如 34°11.3612′。"""
    raw, direction, numbers = _angle_parts(text)
    if len(numbers) != 2:
        raise ValueError("度分格式应包含度、分，例如 34°11.3612′")
    return _signed_angle(float(numbers[0]), float(numbers[1]), 0.0, raw, direction)


def angle_list_to_decimal(text, angle_format):
    """批量转换以逗号分隔的角度，返回对应十进制度列表。"""
    raw = str(text).strip()
    if not raw:
        raise ValueError("角度不能为空")
    items = [item.strip() for item in re.split(r"[,，]", raw)]
    if any(not item for item in items):
        raise ValueError("逗号前后都需要填写角度值")
    converter = dms_to_decimal if angle_format == "dms" else dm_to_decimal
    values = []
    for index, item in enumerate(items, start=1):
        try:
            values.append(converter(item))
        except ValueError as exc:
            raise ValueError(f"第 {index} 个角度：{exc}") from exc
    return values


def convert_coordinate(lat, lon, direction):
    """校验坐标并按指定方向转换。"""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("纬度范围需在[-90,90]，经度范围需在[-180,180]")
    if direction == "wgs2gcj":
        return wgs84_to_gcj02(lat, lon)
    if direction == "gcj2wgs":
        return gcj02_to_wgs84(lat, lon)
    if direction == "wgs2bd":
        return wgs84_to_bd09(lat, lon)
    if direction == "bd2wgs":
        return bd09_to_wgs84(lat, lon)
    raise ValueError(f"未知转换方向：{direction}")

