"""将 Excel A/B 列中的纬度、经度转换为点和轨迹线 KML 文件。"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Iterable, Iterator
from xml.etree import ElementTree as ET

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - 仅在用户环境缺少依赖时触发
    load_workbook = None

try:
    import xlrd
except ImportError:  # pragma: no cover - 仅在读取旧版 .xls 时需要
    xlrd = None


APP_TITLE = "Excel 经纬度转 KML 工具"
KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
SUPPORTED_SUFFIXES = {".xlsx", ".xlsm", ".xls"}

ET.register_namespace("", KML_NAMESPACE)


@dataclass(frozen=True)
class Coordinate:
    """一条通过校验的经纬度记录。"""

    excel_row: int
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ConversionResult:
    """转换结果及生成文件位置。"""

    point_path: Path
    line_path: Path
    valid_count: int
    skipped_rows: tuple[int, ...]


def _parse_number(value: object) -> float:
    """把 Excel 单元格内容转换为有限浮点数。"""

    if isinstance(value, bool) or value is None:
        raise ValueError("不是有效数字")

    if isinstance(value, str):
        value = value.strip().replace("，", ",")
        if not value:
            raise ValueError("单元格为空")
        # 允许用户在数字中使用千位分隔符，虽然经纬度通常不会用到。
        value = value.replace(",", "")

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("数字不是有限值")
    return number


def _xlsx_rows(excel_path: Path) -> Iterator[tuple[int, object, object]]:
    """逐行读取新版 Excel 的 A/B 列。"""

    if load_workbook is None:
        raise RuntimeError("缺少 openpyxl，请先执行：pip install openpyxl")

    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        for row_number, (latitude_value, longitude_value) in enumerate(
            worksheet.iter_rows(min_col=1, max_col=2, values_only=True), start=1
        ):
            yield row_number, latitude_value, longitude_value
    finally:
        workbook.close()


def _xls_rows(excel_path: Path) -> Iterator[tuple[int, object, object]]:
    """逐行读取 Excel 97-2003 文件的 A/B 列。"""

    if xlrd is None:
        raise RuntimeError("读取 .xls 需要 xlrd，请先执行：pip install xlrd")

    workbook = xlrd.open_workbook(str(excel_path), on_demand=True)
    try:
        worksheet = workbook.sheet_by_index(0)
        for row_index in range(worksheet.nrows):
            latitude_value = worksheet.cell_value(row_index, 0) if worksheet.ncols >= 1 else None
            longitude_value = worksheet.cell_value(row_index, 1) if worksheet.ncols >= 2 else None
            yield row_index + 1, latitude_value, longitude_value
    finally:
        workbook.release_resources()


def read_coordinates(excel_path: Path) -> tuple[list[Coordinate], list[int]]:
    """读取第一个工作表的 A/B 列，返回合法坐标与被跳过的行号。"""

    suffix = excel_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("请选择 .xlsx、.xlsm 或 .xls 格式的 Excel 文件")

    rows = _xls_rows(excel_path) if suffix == ".xls" else _xlsx_rows(excel_path)
    coordinates: list[Coordinate] = []
    skipped_rows: list[int] = []

    for row_number, latitude_value, longitude_value in rows:
        # 完全空白的行不计入异常行。
        if latitude_value in (None, "") and longitude_value in (None, ""):
            continue

        try:
            latitude = _parse_number(latitude_value)
            longitude = _parse_number(longitude_value)
            if not -90 <= latitude <= 90:
                raise ValueError("纬度超出 -90～90")
            if not -180 <= longitude <= 180:
                raise ValueError("经度超出 -180～180")
        except (TypeError, ValueError):
            skipped_rows.append(row_number)
            continue

        coordinates.append(
            Coordinate(
                excel_row=row_number,
                latitude=latitude,
                longitude=longitude,
            )
        )

    if not coordinates:
        raise ValueError("Excel 的 A/B 列中没有找到有效坐标（A=纬度，B=经度）")
    return coordinates, skipped_rows


def _sub_element(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, f"{{{KML_NAMESPACE}}}{tag}")
    if text is not None:
        element.text = text
    return element


def _format_number(value: float) -> str:
    """输出紧凑、稳定的坐标文本。"""

    return format(value, ".15g")


def _coordinate_text(coordinate: Coordinate) -> str:
    # KML 坐标顺序必须是：经度,纬度,高度。
    return (
        f"{_format_number(coordinate.longitude)},"
        f"{_format_number(coordinate.latitude)},0"
    )


def build_point_kml(coordinates: Iterable[Coordinate], document_name: str) -> ET.ElementTree:
    """创建包含独立点标记的 KML 文档。"""

    root = ET.Element(f"{{{KML_NAMESPACE}}}kml")
    document = _sub_element(root, "Document")
    _sub_element(document, "name", f"{document_name} - 坐标点")

    style = _sub_element(document, "Style")
    style.set("id", "pointStyle")
    icon_style = _sub_element(style, "IconStyle")
    _sub_element(icon_style, "color", "ff00a5ff")
    _sub_element(icon_style, "scale", "0.8")

    for index, coordinate in enumerate(coordinates, start=1):
        placemark = _sub_element(document, "Placemark")
        _sub_element(placemark, "name", f"点 {index}")
        _sub_element(placemark, "styleUrl", "#pointStyle")
        _sub_element(
            placemark,
            "description",
            (
                f"Excel 行号：{coordinate.excel_row}\n"
                f"纬度：{_format_number(coordinate.latitude)}\n"
                f"经度：{_format_number(coordinate.longitude)}"
            ),
        )
        point = _sub_element(placemark, "Point")
        _sub_element(point, "coordinates", _coordinate_text(coordinate))

    return ET.ElementTree(root)


def build_line_kml(coordinates: Iterable[Coordinate], document_name: str) -> ET.ElementTree:
    """创建按 Excel 行顺序连接所有坐标的轨迹线 KML 文档。"""

    coordinate_list = list(coordinates)
    root = ET.Element(f"{{{KML_NAMESPACE}}}kml")
    document = _sub_element(root, "Document")
    _sub_element(document, "name", f"{document_name} - 轨迹线")

    style = _sub_element(document, "Style")
    style.set("id", "lineStyle")
    line_style = _sub_element(style, "LineStyle")
    _sub_element(line_style, "color", "ff0000ff")
    _sub_element(line_style, "width", "4")

    placemark = _sub_element(document, "Placemark")
    _sub_element(placemark, "name", f"{document_name} 轨迹")
    _sub_element(placemark, "styleUrl", "#lineStyle")
    line_string = _sub_element(placemark, "LineString")
    _sub_element(line_string, "tessellate", "1")
    _sub_element(line_string, "altitudeMode", "clampToGround")
    _sub_element(
        line_string,
        "coordinates",
        "\n" + "\n".join(_coordinate_text(item) for item in coordinate_list) + "\n",
    )

    return ET.ElementTree(root)


def _write_kml(tree: ET.ElementTree, output_path: Path) -> None:
    """缩进并以 UTF-8 写入 KML。"""

    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def convert_excel_to_kml(excel_path: str | Path) -> ConversionResult:
    """读取 Excel 并在同目录生成点、线两个 KML 文件。"""

    source_path = Path(excel_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"文件不存在：{source_path}")

    coordinates, skipped_rows = read_coordinates(source_path)
    point_path = source_path.with_name(f"{source_path.stem}_点.kml")
    line_path = source_path.with_name(f"{source_path.stem}_线.kml")

    _write_kml(build_point_kml(coordinates, source_path.stem), point_path)
    _write_kml(build_line_kml(coordinates, source_path.stem), line_path)

    return ConversionResult(
        point_path=point_path,
        line_path=line_path,
        valid_count=len(coordinates),
        skipped_rows=tuple(skipped_rows),
    )


def open_folder(path: Path) -> None:
    """使用当前操作系统打开文件夹。"""

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class KmlConverterApp(tk.Tk):
    """Excel 经纬度转 KML 图形界面。"""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("720x430")
        self.minsize(640, 390)
        self.configure(bg="#f3f6fa")

        self.excel_path = tk.StringVar()
        self.status_text = tk.StringVar(value="请选择一个 Excel 文件")
        self.last_output_dir: Path | None = None

        self._configure_style()
        self._build_ui()
        self._center_window()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 19, "bold"), background="#f3f6fa")
        style.configure("Hint.TLabel", font=("Microsoft YaHei UI", 10), foreground="#5e6b7a", background="#f3f6fa")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", font=("Microsoft YaHei UI", 10), background="#ffffff")
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 10), foreground="#245b95", background="#edf5ff")
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(20, 10))
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 10), padding=(13, 8))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=(30, 24))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="A 列读取纬度，B 列读取经度；每一行作为一个坐标点。",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 20))

        card = ttk.Frame(outer, style="Card.TFrame", padding=22)
        card.pack(fill="x")

        ttk.Label(card, text="Excel 文件", style="Card.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.path_entry = ttk.Entry(card, textvariable=self.excel_path, font=("Microsoft YaHei UI", 10))
        self.path_entry.grid(row=1, column=0, sticky="ew", pady=(8, 18), padx=(0, 10), ipady=6)
        ttk.Button(card, text="选择文件", command=self.select_file, style="Secondary.TButton").grid(
            row=1, column=1, sticky="e", pady=(8, 18)
        )

        ttk.Label(
            card,
            text="支持 .xlsx / .xlsm / .xls。第一行可以是表头，空行或非数字行会自动跳过。",
            style="Card.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(22, 0))
        self.convert_button = ttk.Button(
            button_row,
            text="生成点和线 KML",
            command=self.start_conversion,
            style="Primary.TButton",
        )
        self.convert_button.pack(side="left")
        self.open_button = ttk.Button(
            button_row,
            text="打开输出目录",
            command=self.open_output_directory,
            state="disabled",
            style="Secondary.TButton",
        )
        self.open_button.pack(side="left", padx=(12, 0))
        card.columnconfigure(0, weight=1)

        status_box = ttk.Frame(outer, padding=(14, 12), style="Card.TFrame")
        status_box.pack(fill="x", pady=(18, 0))
        ttk.Label(status_box, textvariable=self.status_text, style="Status.TLabel", wraplength=610).pack(
            fill="x"
        )

    def _center_window(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def select_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择包含经纬度的 Excel 文件",
            filetypes=[
                ("Excel 文件", "*.xlsx *.xlsm *.xls"),
                ("所有文件", "*.*"),
            ],
        )
        if selected:
            self.excel_path.set(selected)
            self.status_text.set("文件已选择，点击“生成点和线 KML”开始转换。")

    def start_conversion(self) -> None:
        raw_path = self.excel_path.get().strip().strip('"')
        if not raw_path:
            messagebox.showwarning("未选择文件", "请先选择一个 Excel 文件。")
            return

        self.convert_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.status_text.set("正在读取 Excel 并生成 KML，请稍候……")
        threading.Thread(target=self._convert_worker, args=(raw_path,), daemon=True).start()

    def _convert_worker(self, raw_path: str) -> None:
        try:
            result = convert_excel_to_kml(raw_path)
        except Exception as exc:  # GUI 边界：向用户显示可理解的错误
            self.after(0, self._conversion_failed, str(exc))
        else:
            self.after(0, self._conversion_succeeded, result)

    def _conversion_failed(self, error_message: str) -> None:
        self.convert_button.configure(state="normal")
        self.status_text.set(f"生成失败：{error_message}")
        messagebox.showerror("生成失败", error_message)

    def _conversion_succeeded(self, result: ConversionResult) -> None:
        self.convert_button.configure(state="normal")
        self.open_button.configure(state="normal")
        self.last_output_dir = result.point_path.parent

        skipped_text = ""
        if result.skipped_rows:
            preview = ", ".join(str(row) for row in result.skipped_rows[:12])
            if len(result.skipped_rows) > 12:
                preview += "……"
            skipped_text = f"；跳过 {len(result.skipped_rows)} 行（{preview}）"

        self.status_text.set(
            f"生成成功：{result.valid_count} 个坐标点{skipped_text}\n"
            f"点：{result.point_path.name}    线：{result.line_path.name}"
        )
        messagebox.showinfo(
            "生成成功",
            (
                f"已生成 {result.valid_count} 个坐标点。\n\n"
                f"点文件：{result.point_path}\n"
                f"线文件：{result.line_path}"
                + (f"\n\n已跳过 {len(result.skipped_rows)} 行无效数据。" if result.skipped_rows else "")
            ),
        )

    def open_output_directory(self) -> None:
        if self.last_output_dir and self.last_output_dir.is_dir():
            try:
                open_folder(self.last_output_dir)
            except OSError as exc:
                messagebox.showerror("无法打开目录", str(exc))


def main() -> None:
    app = KmlConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
