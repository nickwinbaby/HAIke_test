"""圆形、矩形和多边形电子围栏 KML 生成器。"""

from __future__ import annotations

import math
import os
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Iterable
from xml.etree import ElementTree as ET


APP_TITLE = "电子围栏 KML 生成工具 - Mangetic - 2026-9-29 "
KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
EARTH_RADIUS_METERS = 6_371_008.8
CIRCLE_VERTEX_COUNT = 72
FILL_TRANSPARENCY_PERCENT = 30
# KML uses AABBGGRR. 70% opacity (30% transparency) is alpha B3.
FILL_COLOR = "B3FFCC66"
LINE_COLOR = "FFB35C12"

ET.register_namespace("", KML_NAMESPACE)


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float


def parse_coordinate(latitude_text: str, longitude_text: str) -> GeoPoint:
    """Parse and range-check a latitude/longitude pair."""

    try:
        latitude = float(latitude_text.strip())
        longitude = float(longitude_text.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError("纬度和经度都必须填写有效数字。") from exc

    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("纬度范围必须在 -90 到 90 之间。")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("经度范围必须在 -180 到 180 之间。")
    return GeoPoint(latitude, longitude)


def _format_number(value: float) -> str:
    return format(value, ".12g")


def _coordinate_text(point: GeoPoint) -> str:
    # KML coordinate order is longitude, latitude, altitude.
    return f"{_format_number(point.longitude)},{_format_number(point.latitude)},0"


def circle_ring(center: GeoPoint, radius_meters: float, vertex_count: int = CIRCLE_VERTEX_COUNT) -> list[GeoPoint]:
    """Build a geodesic circle boundary on the WGS84 mean-radius sphere."""

    if not math.isfinite(radius_meters) or radius_meters <= 0:
        raise ValueError("圆形半径必须是大于 0 的米数。")
    if vertex_count < 12:
        raise ValueError("圆形边界点数量不能少于 12。")

    angular_distance = radius_meters / EARTH_RADIUS_METERS
    latitude1 = math.radians(center.latitude)
    longitude1 = math.radians(center.longitude)
    boundary: list[GeoPoint] = []

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


def rectangle_ring(top_left: GeoPoint, bottom_right: GeoPoint) -> list[GeoPoint]:
    """Build a rectangle from its north-west and south-east corners."""

    if top_left.latitude <= bottom_right.latitude:
        raise ValueError("左上角纬度应大于右下角纬度（左上角在北侧）。")
    if top_left.longitude >= bottom_right.longitude:
        raise ValueError("左上角经度应小于右下角经度（右下角在东侧）。")

    top_right = GeoPoint(top_left.latitude, bottom_right.longitude)
    bottom_left = GeoPoint(bottom_right.latitude, top_left.longitude)
    return [top_left, top_right, bottom_right, bottom_left, top_left]


def polygon_ring(points: Iterable[GeoPoint]) -> list[GeoPoint]:
    """Validate and close a polygon ring."""

    ring = list(points)
    if len(ring) < 3:
        raise ValueError("多边形至少需要 3 个有效坐标点。")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _sub_element(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, f"{{{KML_NAMESPACE}}}{tag}")
    if text is not None:
        element.text = text
    return element


def build_fence_kml(ring: Iterable[GeoPoint], fence_name: str) -> ET.ElementTree:
    """Create a KML document containing one filled electronic fence."""

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


def write_fence_kml(ring: Iterable[GeoPoint], fence_name: str, output_path: str | Path) -> Path:
    """Write a KML document and return its resolved path."""

    path = Path(output_path).expanduser().resolve()
    if path.suffix.lower() != ".kml":
        path = path.with_suffix(".kml")
    tree = build_fence_kml(ring, fence_name)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


class FenceKmlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self._set_window_icon()
        self.geometry("760x620")
        self.minsize(560, 430)
        self.configure(bg="#f3f6fa")

        self.shape_var = tk.StringVar(value="circle")
        self.name_var = tk.StringVar(value="电子围栏")
        self.center_lat_var = tk.StringVar()
        self.center_lon_var = tk.StringVar()
        self.radius_var = tk.StringVar(value="100")
        self.nw_lat_var = tk.StringVar()
        self.nw_lon_var = tk.StringVar()
        self.se_lat_var = tk.StringVar()
        self.se_lon_var = tk.StringVar()
        self.polygon_rows: list[tuple[tk.StringVar, tk.StringVar, ttk.Frame]] = []

        self._configure_style()
        self._build_ui()
        self._center_window()

    def _set_window_icon(self) -> None:
        """Set the same ICO for the title bar and Windows taskbar entry."""

        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent
        icon_path = base_dir / "electronic fence.ico"
        if not icon_path.is_file():
            return
        try:
            self.iconbitmap(default=str(icon_path))
        except tk.TclError:
            # Keep the tool usable on platforms/Tk builds that cannot load ICO.
            pass

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 19, "bold"), background="#f3f6fa")
        style.configure("Hint.TLabel", font=("Microsoft YaHei UI", 10), foreground="#5e6b7a", background="#f3f6fa")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", font=("Microsoft YaHei UI", 10), background="#ffffff")
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(18, 9))
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 10), padding=(11, 6))
        style.configure("TRadiobutton", font=("Microsoft YaHei UI", 10), background="#ffffff")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=(18, 14))
        outer.pack(fill="both", expand=True)

        shape_card = ttk.Frame(outer, style="Card.TFrame", padding=(18, 14))
        shape_card.pack(fill="x")
        ttk.Label(shape_card, text="围栏类型", style="Card.TLabel").pack(anchor="w", pady=(0, 8))
        selector = ttk.Frame(shape_card, style="Card.TFrame")
        selector.pack(fill="x")
        for value, label in (("circle", "圆形"), ("rectangle", "矩形"), ("polygon", "多边形")):
            ttk.Radiobutton(
                selector,
                text=label,
                value=value,
                variable=self.shape_var,
                command=self._show_shape,
            ).pack(side="left", padx=(0, 24))

        self.input_card = ttk.Frame(outer, style="Card.TFrame", padding=(18, 16))
        self.input_card.pack(fill="x", pady=(8, 8))
        self.shape_frames: dict[str, ttk.Frame] = {}
        self._build_circle_form()
        self._build_rectangle_form()
        self._build_polygon_form()
        self._show_shape()

        bottom = ttk.Frame(outer, style="Card.TFrame", padding=(18, 10))
        bottom.pack(fill="x")
        name_row = ttk.Frame(bottom, style="Card.TFrame")
        name_row.pack(fill="x")
        ttk.Label(name_row, text="围栏名称", style="Card.TLabel").pack(side="left")
        ttk.Entry(name_row, textvariable=self.name_var, width=34).pack(side="left", padx=(12, 0), ipady=3)
        ttk.Button(name_row, text="生成 KML 文件", command=self.generate, style="Primary.TButton").pack(side="right")
        ttk.Label(
            outer,
            text=f"填充透明度 {FILL_TRANSPARENCY_PERCENT}%    |    圆形半径单位：米    |    坐标顺序：纬度、经度",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 0))
        self.status_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status_var, style="Hint.TLabel").pack(anchor="w", pady=(4, 0))

    def _build_circle_form(self) -> None:
        frame = ttk.Frame(self.input_card, style="Card.TFrame")
        self.shape_frames["circle"] = frame
        ttk.Label(frame, text="圆形围栏", font=("Microsoft YaHei UI", 12, "bold"), style="Card.TLabel").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 16)
        )
        self._coordinate_fields(frame, "", self.center_lat_var, self.center_lon_var, 1)
        ttk.Label(frame, text="半径（米）", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(16, 5))
        ttk.Entry(frame, textvariable=self.radius_var, width=24).grid(row=2, column=1, sticky="w", pady=(16, 5), ipady=4)

    def _build_rectangle_form(self) -> None:
        frame = ttk.Frame(self.input_card, style="Card.TFrame")
        self.shape_frames["rectangle"] = frame
        ttk.Label(frame, text="矩形围栏", font=("Microsoft YaHei UI", 12, "bold"), style="Card.TLabel").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 16)
        )
        self._coordinate_fields(frame, "左上角（纬度、经度）", self.nw_lat_var, self.nw_lon_var, 1)
        self._coordinate_fields(frame, "右下角（纬度、经度）", self.se_lat_var, self.se_lon_var, 2)
        ttk.Label(
            frame,
            text="左上角需位于北侧和西侧，右下角位于南侧和东侧。",
            style="Hint.TLabel",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 0))

    def _build_polygon_form(self) -> None:
        frame = ttk.Frame(self.input_card, style="Card.TFrame")
        self.shape_frames["polygon"] = frame
        self._section_title(frame, "多边形围栏")
        ttk.Label(frame, text="按边界顺序填写各顶点；至少需要 3 个点。", style="Hint.TLabel").pack(anchor="w", pady=(0, 12))

        header = ttk.Frame(frame, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 4))
        ttk.Label(header, text="序号", width=8, style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="纬度", width=24, style="Card.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="经度", width=24, style="Card.TLabel").grid(row=0, column=2, sticky="w")

        list_area = ttk.Frame(frame, style="Card.TFrame")
        list_area.pack(fill="both", expand=True)
        # Keep the vertex list compact; the outer form scrollbar handles the rest.
        self.polygon_canvas = tk.Canvas(list_area, height=190, highlightthickness=0, background="#ffffff")
        scrollbar = ttk.Scrollbar(list_area, orient="vertical", command=self.polygon_canvas.yview)
        self.polygon_table = ttk.Frame(self.polygon_canvas, style="Card.TFrame")
        self.polygon_window = self.polygon_canvas.create_window((0, 0), window=self.polygon_table, anchor="nw")
        self.polygon_canvas.configure(yscrollcommand=scrollbar.set)
        self.polygon_table.bind("<Configure>", lambda _event: self.polygon_canvas.configure(scrollregion=self.polygon_canvas.bbox("all")))
        self.polygon_canvas.bind("<Configure>", lambda event: self.polygon_canvas.itemconfigure(self.polygon_window, width=event.width))
        self.polygon_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        actions = ttk.Frame(frame, style="Card.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="＋ 添加顶点", command=self.add_polygon_row, style="Secondary.TButton").pack(side="left")
        self.polygon_count_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.polygon_count_var, style="Hint.TLabel").pack(side="left", padx=12)
        for _ in range(4):
            self.add_polygon_row()

    @staticmethod
    def _section_title(parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, font=("Microsoft YaHei UI", 12, "bold"), style="Card.TLabel").pack(anchor="w", pady=(0, 16))

    @staticmethod
    def _coordinate_fields(
        parent: ttk.Frame,
        label: str,
        latitude_var: tk.StringVar,
        longitude_var: tk.StringVar,
        row: int,
    ) -> None:
        # Keep the coordinate labels close to their inputs instead of letting the
        # descriptive first column consume the remaining row width.
        if label:
            ttk.Label(parent, text=label, style="Card.TLabel").grid(
                row=row, column=0, sticky="w", pady=7, padx=(0, 12)
            )
            label_column = 0
            latitude_column = 1
            latitude_entry_column = 2
            longitude_column = 3
            longitude_entry_column = 4
        else:
            label_column = None
            latitude_column = 0
            latitude_entry_column = 1
            longitude_column = 2
            longitude_entry_column = 3

        ttk.Label(parent, text="纬度", style="Card.TLabel").grid(
            row=row, column=latitude_column, sticky="w", pady=7, padx=(0, 5)
        )
        ttk.Entry(parent, textvariable=latitude_var, width=18).grid(
            row=row, column=latitude_entry_column, sticky="w", padx=(0, 16), ipady=4
        )
        ttk.Label(parent, text="经度", style="Card.TLabel").grid(
            row=row, column=longitude_column, sticky="w", padx=(0, 5)
        )
        ttk.Entry(parent, textvariable=longitude_var, width=18).grid(
            row=row, column=longitude_entry_column, sticky="w", ipady=4
        )

    def add_polygon_row(self) -> None:
        index = len(self.polygon_rows)
        latitude_var = tk.StringVar()
        longitude_var = tk.StringVar()
        row = ttk.Frame(self.polygon_table, style="Card.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=f"顶点 {index + 1}", width=8, style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(row, textvariable=latitude_var, width=24).grid(row=0, column=1, sticky="ew", padx=(0, 8), ipady=3)
        ttk.Entry(row, textvariable=longitude_var, width=24).grid(row=0, column=2, sticky="ew", padx=(0, 8), ipady=3)
        remove_button = ttk.Button(row, text="移除", command=lambda: self.remove_polygon_row(row), style="Secondary.TButton")
        remove_button.grid(row=0, column=3, sticky="e")
        row.columnconfigure(1, weight=1)
        row.columnconfigure(2, weight=1)
        self.polygon_rows.append((latitude_var, longitude_var, row))
        self._refresh_polygon_rows()

    def remove_polygon_row(self, row_widget: ttk.Frame) -> None:
        if len(self.polygon_rows) <= 3:
            messagebox.showwarning("不能移除", "多边形至少需要保留 3 个坐标点。", parent=self)
            return
        row_index = next(
            index for index, (_, _, candidate) in enumerate(self.polygon_rows)
            if candidate is row_widget
        )
        self.polygon_rows.pop(row_index)
        row_widget.destroy()
        self._refresh_polygon_rows()

    def _refresh_polygon_rows(self) -> None:
        for index, (_, _, row) in enumerate(self.polygon_rows, start=1):
            label = row.grid_slaves(row=0, column=0)
            if label:
                label[0].configure(text=f"顶点 {index}")
        self.polygon_count_var.set(f"当前 {len(self.polygon_rows)} 个顶点")

    def _show_shape(self) -> None:
        for frame in self.shape_frames.values():
            frame.pack_forget()
        self.shape_frames[self.shape_var.get()].pack(fill="x", expand=False)
        self.update_idletasks()

    def _get_ring(self) -> list[GeoPoint]:
        shape = self.shape_var.get()
        if shape == "circle":
            center = parse_coordinate(self.center_lat_var.get(), self.center_lon_var.get())
            try:
                radius = float(self.radius_var.get().strip())
            except ValueError as exc:
                raise ValueError("圆形半径必须填写有效数字（单位：米）。") from exc
            return circle_ring(center, radius)

        if shape == "rectangle":
            top_left = parse_coordinate(self.nw_lat_var.get(), self.nw_lon_var.get())
            bottom_right = parse_coordinate(self.se_lat_var.get(), self.se_lon_var.get())
            return rectangle_ring(top_left, bottom_right)

        points: list[GeoPoint] = []
        for index, (latitude_var, longitude_var, _row) in enumerate(self.polygon_rows, start=1):
            if not latitude_var.get().strip() and not longitude_var.get().strip():
                continue
            try:
                points.append(parse_coordinate(latitude_var.get(), longitude_var.get()))
            except ValueError as exc:
                raise ValueError(f"多边形顶点 {index}：{exc}") from exc
        return polygon_ring(points)

    def generate(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("缺少名称", "请填写围栏名称。", parent=self)
            return
        try:
            ring = self._get_ring()
        except ValueError as exc:
            messagebox.showerror("参数有误", str(exc), parent=self)
            return

        output_path = filedialog.asksaveasfilename(
            parent=self,
            title="保存电子围栏 KML",
            defaultextension=".kml",
            initialfile=f"{name}.kml",
            filetypes=(("KML 文件", "*.kml"), ("所有文件", "*.*")),
        )
        if not output_path:
            return

        try:
            saved_path = write_fence_kml(ring, name, output_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("生成失败", str(exc), parent=self)
            return

        self.status_var.set(f"已生成：{saved_path}")
        messagebox.showinfo("生成成功", f"电子围栏 KML 已生成：\n{saved_path}", parent=self)

    def _center_window(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")


def main() -> None:
    app = FenceKmlApp()
    app.mainloop()


if __name__ == "__main__":
    main()
