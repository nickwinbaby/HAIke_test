"""电子围栏协议组包逻辑。

本模块把 4.0 KLV 和 JT/T 808 电子围栏的编码逻辑直接放在 GNSS 工具箱内，
不依赖原来的独立脚本。UI 只负责收集字段，所有校验和编码在这里完成，方便后续
继续增加字段或编写自动化测试。
"""

from __future__ import annotations

import re
from datetime import datetime


def _dec_to_hex(value, byte_len, field_name):
    if str(value).strip() == "":
        raise ValueError(f"{field_name} 不能为空")
    try:
        number = int(str(value).strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是十进制整数") from exc
    if number < 0 or number >= 256**byte_len:
        raise ValueError(f"{field_name} 超出 {byte_len} byte 范围")
    return f"{number:0{byte_len * 2}X}"


def _range_to_hex(value, minimum, maximum, byte_len, field_name):
    """将十进制字段编码为 HEX，并执行协议业务范围校验。"""
    if str(value).strip() == "":
        raise ValueError(f"{field_name} 不能为空")
    try:
        number = int(str(value).strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是十进制整数") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{field_name} 必须在 {minimum}～{maximum} 范围内")
    return f"{number:0{byte_len * 2}X}"


def _byte_len_hex(hex_string):
    if len(hex_string) % 2:
        raise ValueError("HEX 字符串长度必须为偶数")
    size = len(hex_string) // 2
    if size > 255:
        raise ValueError("长度超过 1 字节可表示范围")
    return f"{size:02X}"


def _gps_to_hex(value, direction, is_lat=True):
    text = str(value).strip()
    if not text:
        raise ValueError("经纬度不能为空")
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("-"):
        raise ValueError("经纬度请输入正数，方向由东经/西经/南纬/北纬选择")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise ValueError("经纬度格式非法")
    integer, _, fraction = text.partition(".")
    scaled = int(integer + (fraction + "00000")[:5])
    if scaled >= 2**31:
        raise ValueError("经纬度数值超出范围")
    bits = bin(scaled)[2:].zfill(32)
    sign_bit = "0" if (direction == "南纬" if is_lat else direction == "东经") else "1"
    return f"{int(sign_bit + bits[1:], 2):08X}"


def _gps_pair_hex(row, gps_index):
    point = row["gps"][gps_index]
    lon = _gps_to_hex(point["lon"], point.get("lon_dir", "东经"), is_lat=False)
    lat = _gps_to_hex(point["lat"], point.get("lat_dir", "北纬"), is_lat=True)
    return lon + lat


def _geo_id_hex(value, field_name="围栏ID"):
    return _range_to_hex(value, 1, 40, 1, field_name)


def _ensure_unique_geo_ids(values):
    normalized = [int(str(value).strip(), 10) for value in values]
    repeated = sorted({value for value in normalized if normalized.count(value) > 1})
    if repeated:
        raise ValueError("围栏ID不能重复：" + "、".join(str(value) for value in repeated))


def build_40_packet(*, major_minor="F10F", op_type="02", total_fence="1", msg_index="1",
                    rows=None, delete_ids=None):
    """生成4.0 KLV围栏有效数据，并按操作类型使用不同字段结构。"""
    operation = str(op_type).strip().upper()
    if operation not in {"00", "01", "02", "03"}:
        raise ValueError("操作类型只能是00、01、02或03")
    message_type = str(major_minor).strip().upper()
    if message_type != "F10F":
        raise ValueError("围栏管理消息类型必须为F10F")

    # 0x01删除所有：协议规定F1 0F 01之后不携带任何其他字段。
    if operation == "01":
        return message_type + operation

    # 其余操作的Start_Index不允许为00；暂不校验它与总数/本包数量的关系。
    prefix = (
        message_type
        + operation
        + _range_to_hex(total_fence, 1, 40, 1, "待操作围栏总数")
        + _range_to_hex(msg_index, 1, 255, 1, "此消息索引开始")
    )

    # 0x03删除部分：仅携带数量和Geo ID列表，不携带Length、Mode、点数或TLV。
    if operation == "03":
        ids = list(delete_ids or [])
        if not ids:
            raise ValueError("删除部分时至少需要填写一个围栏ID")
        if len(ids) > 40:
            raise ValueError("本消息中的围栏ID数量不能超过40")
        encoded_ids = [_geo_id_hex(value, f"第{index}个围栏ID") for index, value in enumerate(ids, 1)]
        _ensure_unique_geo_ids(ids)
        return prefix + _dec_to_hex(len(ids), 1, "此消息中围栏总数") + "".join(encoded_ids)

    rows = list(rows or [])
    if not rows:
        raise ValueError("至少填写一条围栏数据")
    if len(rows) > 40:
        raise ValueError("本消息中的围栏数量不能超过40")
    row_ids = [row.get("fence_id", "") for row in rows]
    for index, value in enumerate(row_ids, 1):
        _geo_id_hex(value, f"第{index}行 围栏ID")
    _ensure_unique_geo_ids(row_ids)
    prefix += _dec_to_hex(len(rows), 1, "此消息中围栏总数")
    pieces = []
    for index, row in enumerate(rows, 1):
        fence_id = _geo_id_hex(row.get("fence_id", ""), f"第{index}行 围栏ID")
        report = _dec_to_hex(row.get("report_type", "00"), 1, f"第{index}行 上报方式")
        fence_type = str(row.get("fence_type", "01")).zfill(2)
        fence_type_hex = _dec_to_hex(fence_type, 1, f"第{index}行 围栏类型/点数")
        key = _dec_to_hex(row.get("key", "404"), 2, f"第{index}行 KEY")
        if fence_type == "01":
            gps = _gps_pair_hex(row, 0)
            radius = _range_to_hex(
                row.get("radius", ""), 20, 16_777_215, 3, f"第{index}行 半径"
            )
            pieces.append(fence_id + "10" + report + fence_type_hex + key + "0B" + gps + radius)
        elif fence_type == "02":
            gps = _gps_pair_hex(row, 0) + _gps_pair_hex(row, 1)
            pieces.append(fence_id + "15" + report + fence_type_hex + key + "10" + gps)
        else:
            try:
                count = int(fence_type)
            except ValueError as exc:
                raise ValueError(f"第{index}行围栏类型无效") from exc
            if count < 3 or count > 11:
                raise ValueError(f"第{index}行多边形点数应为 3~11")
            gps = "".join(_gps_pair_hex(row, n) for n in range(count))
            first = _byte_len_hex(gps) + gps
            body = report + fence_type_hex + key + first
            pieces.append(fence_id + _byte_len_hex(body) + body)
    return prefix + "".join(pieces)


def _u32(value, field):
    try:
        number = int(round(float(value) * 1_000_000))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是有效数字") from exc
    if not -180_000_000 <= number <= 180_000_000:
        raise ValueError(f"{field} 超出坐标范围")
    return number.to_bytes(4, "big", signed=True).hex().upper()


def _u16(value, field):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是整数") from exc
    if not 0 <= number <= 65535:
        raise ValueError(f"{field} 超出 2 字节范围")
    return number.to_bytes(2, "big").hex().upper()


def _u32_int(value, field):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是整数") from exc
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError(f"{field} 超出 4 字节范围")
    return number.to_bytes(4, "big").hex().upper()


def _radius_u32(value, field):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是有效数字") from exc
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError(f"{field} 超出 4 字节范围")
    return number.to_bytes(4, "big").hex().upper()


def _bcd_datetime(value, field):
    text = str(value or "").strip().replace("-", "").replace(" ", "").replace(":", "")
    if not text:
        return "000000000000"
    if re.fullmatch(r"\d{12}", text):
        return text
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field} 请填写 YYYY-MM-DD HH:MM:SS 或 YYMMDDhhmmss") from exc
    text = parsed.strftime("%y%m%d%H%M%S")
    return text


def _attr_value(enter_alarm=False, leave_alarm=False, time_enabled=False, speed_enabled=False):
    value = (1 if time_enabled else 0) | (2 if speed_enabled else 0)
    value |= (1 << 3) if enter_alarm else 0
    value |= (1 << 5) if leave_alarm else 0
    return f"{value:04X}"


def _point_pair(point, index):
    try:
        lat, lon = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"第 {index} 个顶点格式无效") from exc
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"第 {index} 个顶点超出坐标范围")
    return _u32(lat, f"第 {index} 个顶点纬度") + _u32(lon, f"第 {index} 个顶点经度")


def build_808_body(*, shape, operation="0", fence_id="1", points=None, radius="", enter_alarm=False,
                   leave_alarm=False, time_enabled=False, speed_enabled=False, start_time="", end_time="",
                   speed="", speed_duration=""):
    """生成 JT/T 808 0x8600~0x8605 消息体（十六进制）。"""
    shape = {"circle": "circle", "rectangle": "rect", "polygon": "poly"}.get(shape, shape)
    points = list(points or [])
    op = int(str(operation or "0"), 0) if str(operation).strip().startswith("0x") else int(str(operation or "0"))
    if op not in (0, 1, 2):
        raise ValueError("操作类型只能是 0（更新）、1（追加）或 2（修改）")
    attr = _attr_value(enter_alarm, leave_alarm, time_enabled, speed_enabled)
    optional = ""
    if time_enabled:
        optional += _bcd_datetime(start_time, "开始时间") + _bcd_datetime(end_time, "结束时间")
    if speed_enabled:
        try:
            limit = int(speed)
            duration = int(speed_duration)
        except (TypeError, ValueError) as exc:
            raise ValueError("最高速度和超速持续时间必须是整数") from exc
        if not 0 <= limit <= 65535:
            raise ValueError("最高速度范围应为 0~65535")
        if not 0 <= duration <= 255:
            raise ValueError("超速持续时间范围应为 0~255 秒")
        optional += f"{limit:04X}{duration:02X}"
    if shape == "circle":
        if len(points) != 1:
            raise ValueError("圆形围栏需要 1 个圆心")
        message_id, area = "8600", _u32_int(fence_id, "区域 ID") + attr + _point_pair(points[0], 1) + _radius_u32(radius, "半径") + optional
    elif shape == "rect":
        if len(points) != 2:
            raise ValueError("矩形围栏需要左上角和右下角 2 个点")
        message_id, area = "8602", _u32_int(fence_id, "区域 ID") + attr + _point_pair(points[0], 1) + _point_pair(points[1], 2) + optional
    elif shape == "poly":
        if not 3 <= len(points) <= 10:
            raise ValueError("多边形围栏需要 3~10 个顶点")
        message_id, area = "8604", _u32_int(fence_id, "区域 ID") + attr + optional + _u16(len(points), "顶点数") + "".join(_point_pair(p, i) for i, p in enumerate(points, 1))
    else:
        raise ValueError(f"不支持的围栏类型：{shape}")
    if shape == "poly":
        return message_id, area
    return message_id, f"{op:02X}01" + area


def build_808_delete_body(*, shape, fence_ids=None):
    shape = {"circle": "circle", "rectangle": "rect", "polygon": "poly"}.get(shape, shape)
    message_id = {"circle": "8601", "rect": "8603", "poly": "8605"}.get(shape)
    if not message_id:
        raise ValueError(f"不支持的围栏类型：{shape}")
    raw_ids = list(fence_ids or [])
    # JT/T 808 删除围栏的区域总数为 0 时表示删除全部同类区域。
    # 为兼容现场常用输入，空列表或列表任意位置出现 0 都按删除全部处理。
    if not raw_ids or any(str(value).strip() == "0" for value in raw_ids):
        return message_id, "00"
    ids = [value for value in raw_ids if str(value).strip()]
    return message_id, f"{len(ids):02X}" + "".join(_u32_int(item, "区域 ID") for item in ids)


def build_808_frame(message_id, body_hex, terminal_id, serial="1"):
    """按 JT/T 808-2013 常规 12 字节终端号头生成并转义完整帧。"""
    digits = re.sub(r"\D", "", str(terminal_id or ""))
    if len(digits) == 15:
        digits = digits[-12:]
    if len(digits) != 12:
        raise ValueError("终端标识需填写 15 位 IMSI 或 12 位手机号")
    try:
        msg_id = int(str(message_id), 16)
        body = bytes.fromhex(str(body_hex))
        sequence = int(serial)
    except ValueError as exc:
        raise ValueError("消息 ID、消息体或流水号格式无效") from exc
    if len(body) > 1023:
        raise ValueError("消息体超过 JT/T 808 单帧 1023 字节上限")
    if not 0 <= sequence <= 65535:
        raise ValueError("消息流水号应为 0~65535")
    phone_bcd = bytes(int(digits[i:i + 2], 16) for i in range(0, 12, 2))
    prop = len(body)
    raw = msg_id.to_bytes(2, "big") + prop.to_bytes(2, "big") + phone_bcd + sequence.to_bytes(2, "big") + body
    checksum = 0
    for value in raw:
        checksum ^= value
    escaped = bytearray()
    for value in raw + bytes([checksum]):
        if value == 0x7E:
            escaped.extend((0x7D, 0x02))
        elif value == 0x7D:
            escaped.extend((0x7D, 0x01))
        else:
            escaped.append(value)
    return (bytes([0x7E]) + bytes(escaped) + bytes([0x7E])).hex().upper()
