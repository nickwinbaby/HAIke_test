"""将工具导出的 Excel 数据生成 KML。"""

from dataclasses import dataclass
import os

import pandas as pd
import simplekml


@dataclass(frozen=True)
class ExcelKmlResult:
    tracker_file: str
    point_file: str
    point_count: int
    warnings: tuple[str, ...]


def generate_excel_kml(file_path, output_dir, data_format="tool4"):
    """按 4.0 工具格式或仅经纬度格式生成轨迹和点位 KML。"""
    df = pd.read_excel(file_path)
    df.columns = df.columns.str.strip()
    os.makedirs(output_dir, exist_ok=True)

    if data_format == "tool4":
        required_columns = {"经度", "纬度", "经度值", "纬度值"}
    elif data_format == "simple":
        # 简单格式只强制要求坐标；备注列存在时写入，不存在时正常生成。
        required_columns = {"经度", "纬度"}
    else:
        raise ValueError(f"未知 Excel 数据格式：{data_format}")
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError("Excel 缺少必要列：" + "、".join(sorted(missing)))

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    kml_line = simplekml.Kml()
    kml_point = simplekml.Kml()
    coords = []
    warnings = []

    for index, row in df.iterrows():
        try:
            if data_format == "tool4":
                lon_dir_raw = str(row["经度"]).strip()
                lat_dir_raw = str(row["纬度"]).strip()
                lon_val = row["经度值"]
                lat_val = row["纬度值"]
            else:
                lon_val = row["经度"]
                lat_val = row["纬度"]

            if pd.isna(lon_val) or pd.isna(lat_val):
                continue

            lon_val = float(lon_val)
            lat_val = float(lat_val)

            if data_format == "tool4":
                if ("西" in lon_dir_raw) or ("W" in lon_dir_raw.upper()) or ("-" in lon_dir_raw):
                    lon = -abs(lon_val)
                else:
                    lon = abs(lon_val)

                if ("南" in lat_dir_raw) or ("S" in lat_dir_raw.upper()) or ("-" in lat_dir_raw):
                    lat = -abs(lat_val)
                else:
                    lat = abs(lat_val)
            else:
                lon, lat = lon_val, lat_val
                if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ValueError("经纬度超出有效范围")

            coords.append((lon, lat))
            if data_format == "tool4":
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
            else:
                remark = row.get("备注", "")
                description = "" if pd.isna(remark) or str(remark).strip() == "" else f"备注: {remark}"
            # 点位名称按成功生成的顺序使用纯数字，不添加“点”等前缀。
            point_name = str(len(coords))
            point = kml_point.newpoint(name=point_name, coords=[(lon, lat)])
            if description:
                point.description = description
        except Exception as exc:
            warnings.append(f"第{index + 2}行处理失败: {exc}")

    if coords:
        line = kml_line.newlinestring(name="Tracker", coords=coords)
        line.style.linestyle.width = 3

    tracker_file = os.path.join(output_dir, f"{base_name}_tracker.kml")
    point_file = os.path.join(output_dir, f"{base_name}_point.kml")
    kml_line.save(tracker_file)
    kml_point.save(point_file)
    return ExcelKmlResult(tracker_file, point_file, len(coords), tuple(warnings))

