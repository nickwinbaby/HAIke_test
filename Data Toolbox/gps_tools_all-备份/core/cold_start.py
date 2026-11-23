"""GNSS 冷热启动定位耗时分析核心逻辑。"""

from dataclasses import dataclass
from datetime import datetime
import os
import re


RE_BRACKET_TIME = re.compile(r"\[(.*?)\]")
RE_LINE_HEAD_DATETIME = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}[ -]\d{2}:\d{2}:\d{2}(?:[:.]\d+)?)")
VALID_GGA_FIX_QUALITY = {"1", "2", "3", "4", "5"}


@dataclass(frozen=True)
class ColdStartResult:
    report: str
    boot_total_count: int
    records: tuple[float, ...]


def extract_timestamp(line):
    bracket_match = RE_BRACKET_TIME.search(line)
    if bracket_match:
        timestamp = bracket_match.group(1).strip()
        formats = [
            "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d-%H:%M:%S.%f", "%Y/%m/%d-%H:%M:%S:%f", "%Y/%m/%d-%H:%M:%S",
            "%H:%M:%S.%f", "%H:%M:%S:%f", "%H:%M:%S",
        ]
        for format_string in formats:
            try:
                parsed = datetime.strptime(timestamp, format_string)
                if format_string.startswith("%H"):
                    now = datetime.now()
                    parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
                return parsed
            except ValueError:
                continue

    line_match = RE_LINE_HEAD_DATETIME.match(line.strip())
    if line_match:
        timestamp = line_match.group(1)
        fixed_timestamp = re.sub(r"(\d{2}:\d{2}:\d{2}):(\d{3,6})", r"\1.\2", timestamp)
        if "/" in timestamp and "-" in timestamp:
            format_string = "%Y/%m/%d-%H:%M:%S.%f" if "." in fixed_timestamp else "%Y/%m/%d-%H:%M:%S"
        else:
            format_string = "%Y-%m-%d %H:%M:%S.%f" if "." in fixed_timestamp else "%Y-%m-%d %H:%M:%S"
        try:
            return datetime.strptime(fixed_timestamp, format_string)
        except ValueError:
            pass
    return None


def parse_nmea_coordinate(value, direction, max_degree):
    value = value.strip()
    direction = direction.strip().upper()
    if not value or direction not in {"N", "S", "E", "W"}:
        return None
    try:
        raw_coord = float(value)
    except ValueError:
        return None
    degrees = int(raw_coord // 100)
    minutes = raw_coord - degrees * 100
    if degrees > max_degree or minutes >= 60:
        return None
    decimal = degrees + minutes / 60
    if direction in {"S", "W"}:
        decimal = -decimal
    return decimal


def has_valid_gga_coordinate(parts):
    if len(parts) <= 5:
        return False
    lat = parse_nmea_coordinate(parts[2], parts[3], 90)
    lon = parse_nmea_coordinate(parts[4], parts[5], 180)
    if lat is None or lon is None:
        return False
    return not (abs(lat) < 1e-12 and abs(lon) < 1e-12)


def is_valid_nmea(nmea_line, skip_loc_check=False):
    parts = nmea_line.split(",")
    if skip_loc_check:
        return has_valid_gga_coordinate(parts)
    return (
        len(parts) > 6
        and parts[6].strip() in VALID_GGA_FIX_QUALITY
        and has_valid_gga_coordinate(parts)
    )


def _read_lines(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file_obj:
            return file_obj.readlines(), None
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk", errors="ignore") as file_obj:
            return file_obj.readlines(), "警告：文件非UTF-8，已切换GBK编码读取\n\n"


def analyze_cold_start(file_path, boot_keyword, nmea_keyword, skip_loc_check=False):
    """按启动分段和定位判定规则生成统计报告。"""
    file_path = file_path.strip()
    boot_keyword = boot_keyword.strip()
    nmea_keyword = nmea_keyword.strip()
    if not file_path:
        raise ValueError("请先选择日志文件")
    if not boot_keyword:
        raise ValueError("启动关键字不能为空")
    if not nmea_keyword:
        raise ValueError("定位NMEA语句不能为空！示例：$GNGGA、$GGA")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    report = [
        f"=== 开始分析日志：{os.path.basename(file_path)} ===\n",
        f"启动匹配关键字：{boot_keyword}\n",
        f"定位NMEA语句：{nmea_keyword}\n",
    ]
    rule_desc = (
        "仅检查有效经纬度（不校验 GGA 定位有效性标志）"
        if skip_loc_check
        else "校验 GGA 定位有效性标志（1/2/3/4/5）和有效经纬度"
    )
    report.extend([f"定位判定规则：{rule_desc}\n", "=" * 45 + "\n"])

    lines, warning = _read_lines(file_path)
    if warning:
        report.append(warning)
    cold_start_records = []
    boot_total_count = 0
    line_index = 0
    total_lines = len(lines)

    while line_index < total_lines:
        while line_index < total_lines and boot_keyword not in lines[line_index]:
            line_index += 1
        if line_index >= total_lines:
            break

        boot_line = lines[line_index]
        boot_datetime = extract_timestamp(boot_line)
        boot_line_number = line_index + 1
        line_index += 1
        boot_total_count += 1

        if not boot_datetime:
            report.append(
                f"第 {boot_total_count} 次冷热启动 | 异常：该行无有效时间戳，无法计算耗时"
                f"  启动行：{boot_line_number}\n"
            )
            continue

        found_valid_nmea = False
        while line_index < total_lines:
            current_line = lines[line_index]
            if boot_keyword in current_line:
                break
            if nmea_keyword in current_line and is_valid_nmea(current_line, skip_loc_check):
                nmea_datetime = extract_timestamp(current_line)
                if nmea_datetime:
                    cost_seconds = (nmea_datetime - boot_datetime).total_seconds()
                    cold_start_records.append(cost_seconds)
                    report.append(
                        f"第 {boot_total_count} 次冷热启动 | 耗时：{cost_seconds:.3f} 秒"
                        f"  启动行：{boot_line_number} | 定位行：{line_index + 1}\n"
                    )
                    found_valid_nmea = True
                    break
            line_index += 1

        if not found_valid_nmea:
            report.append(
                f"第 {boot_total_count} 次冷热启动 | 异常：本次启动至下一次启动前，未检测到有效定位NMEA数据"
                f"  启动行：{boot_line_number}\n"
            )

    report.append("=" * 45 + "\n分析完成 · 统计汇总\n")
    report.append(f"总共检测到启动次数：{boot_total_count} 次\n")
    if not cold_start_records:
        report.append(
            f"无任何有效冷热启动耗时记录！排查方向：\n"
            f"1. 启动关键字「{boot_keyword}」是否和日志完全一致\n"
            f"2. 勾选【仅检查有效经纬度（不校验 GGA 定位有效性标志）】使用宽松匹配规则\n"
            f"3. 确认日志内存在{nmea_keyword}语句\n"
        )
    else:
        valid_count = len(cold_start_records)
        report.append(
            f"有效定位成功次数：{valid_count} 次\n"
            f"单次最小耗时：{min(cold_start_records):.3f} s\n"
            f"单次最大耗时：{max(cold_start_records):.3f} s\n"
            f"平均启动耗时：{sum(cold_start_records) / valid_count:.3f} s\n"
        )
    return ColdStartResult("".join(report), boot_total_count, tuple(cold_start_records))

