"""通用数据格式转换核心逻辑。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")


def hex_to_ascii(value: str) -> str:
    """将空格/逗号分隔或连续HEX转换为严格ASCII文本。"""
    source = value.strip()
    if not source:
        raise ValueError("请输入HEX数据")
    source = re.sub(r"(?i)0x", "", source)
    compact = re.sub(r"[\s,;:_-]+", "", source)
    if not compact or re.search(r"[^0-9a-fA-F]", compact):
        raise ValueError("HEX数据只能包含0-9、A-F及常用分隔符")
    if len(compact) % 2:
        raise ValueError("HEX数据长度必须是偶数，每两个字符表示一个字节")
    raw = bytes.fromhex(compact)
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(f"第{exc.start + 1}个字节不是ASCII字符（范围应为00-7F）") from exc


def ascii_to_hex(value: str) -> str:
    """将严格ASCII文本转换为大写、空格分隔的HEX。"""
    if value == "":
        raise ValueError("请输入ASCII文本")
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"第{exc.start + 1}个字符不是ASCII字符（范围应为00-7F）") from exc
    return " ".join(f"{byte:02X}" for byte in raw)


def hex_timestamp_to_int(value: str) -> int:
    """解析HEX时间戳并返回内部使用的十进制整数。"""
    source = value.strip()
    if not source:
        raise ValueError("请输入HEX时间戳")
    source = re.sub(r"(?i)0x", "", source)
    compact = re.sub(r"[\s,;:_-]+", "", source)
    if not compact or re.search(r"[^0-9a-fA-F]", compact):
        raise ValueError("HEX时间戳只能包含0-9、A-F及常用分隔符")
    return int(compact, 16)


def hex_to_beijing(value: str, unit: str = "自动识别") -> datetime:
    """将HEX表示的Unix时间戳转换为北京时间，不暴露中间十进制值。"""
    timestamp = hex_timestamp_to_int(value)
    converted, _detected = unix_to_beijing(timestamp, unit)
    return converted


def unix_to_beijing(value: str | int | float, unit: str = "自动识别") -> tuple[datetime, str]:
    """将Unix秒或毫秒时间戳转换为北京时间，并返回识别出的单位。"""
    text = str(value).strip()
    if not text:
        raise ValueError("请输入Unix时间戳")
    try:
        timestamp = float(text)
    except ValueError as exc:
        raise ValueError("Unix时间戳必须是数字") from exc
    if unit not in ("自动识别", "秒", "毫秒"):
        raise ValueError("未知的时间戳单位")
    detected = unit
    if unit == "自动识别":
        detected = "毫秒" if abs(timestamp) >= 100_000_000_000 else "秒"
    seconds = timestamp / 1000 if detected == "毫秒" else timestamp
    try:
        converted = datetime.fromtimestamp(seconds, tz=BEIJING_TIMEZONE)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("时间戳超出系统支持范围") from exc
    return converted, detected


def beijing_to_unix(value: str, unit: str = "秒") -> int:
    """将北京时间转换为Unix秒或毫秒时间戳。"""
    text = value.strip()
    if not text:
        raise ValueError("请输入北京时间")
    if unit not in ("秒", "毫秒"):
        raise ValueError("输出单位只能选择秒或毫秒")
    parsed = None
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, pattern)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError("北京时间格式应为 YYYY-MM-DD HH:MM:SS 或带毫秒 .SSS")
    timestamp = parsed.replace(tzinfo=BEIJING_TIMEZONE).timestamp()
    return int(timestamp * 1000) if unit == "毫秒" else int(timestamp)


def format_beijing_time(value: datetime, include_milliseconds: bool = True) -> str:
    if include_milliseconds:
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return value.strftime("%Y-%m-%d %H:%M:%S")

