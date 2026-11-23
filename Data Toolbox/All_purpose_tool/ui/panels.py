"""数据分析综合工具箱中的GNSS功能页面。"""

import os
import json
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.cep import analyze_cep
from core.cold_start import analyze_cold_start
from core.command_sender import normalize_command_payload, send_command_json
from core.coordinate import angle_list_to_decimal, convert_coordinate, out_of_china
from core.excel_kml import generate_excel_kml
from core.fence_kml import (
    GeoPoint,
    circle_ring,
    parse_coordinate,
    parse_polygon_text,
    rectangle_ring,
    write_fence_kml,
    write_point_kml,
)
from core.fence_packet import (
    build_40_packet,
    build_808_body,
    build_808_delete_body,
    build_808_frame,
)
from core.map_picker import MapPickerServer
from core.nmea_kml import generate_nmea_kml


FILE_TYPES_NMEA = [
    ("NMEA / 文本文件", "*.txt *.log *.nmea"),
    ("所有文件", "*.*"),
]


def _open_directory(path):
    if not path:
        return
    os.makedirs(path, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(path)


class ToolPanel(ttk.Frame):
    """带统一标题、状态和后台执行能力的页面基类。"""

    def __init__(self, master, title, subtitle, show_heading=True):
        super().__init__(master, padding=22, style="Page.TFrame")
        self.columnconfigure(0, weight=1)
        content_row = 2 if show_heading else 0
        if show_heading:
            ttk.Label(self, text=title, style="PageTitle.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(self, text=subtitle, style="PageSubtitle.TLabel").grid(
                row=1, column=0, sticky="w", pady=(5, 18)
            )
        scroll_host = ttk.Frame(self, style="Page.TFrame")
        scroll_host.grid(row=content_row, column=0, sticky="nsew")
        scroll_host.columnconfigure(0, weight=1)
        scroll_host.rowconfigure(0, weight=1)
        self.scroll_canvas = tk.Canvas(
            scroll_host, background="#f8fafc", highlightthickness=0, borderwidth=0
        )
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=self.scroll_canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.body = ttk.Frame(self.scroll_canvas, style="Page.TFrame", padding=(0, 0, 8, 0))
        self.body_window = self.scroll_canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>",
            self._sync_scroll_region,
        )
        self.scroll_canvas.bind(
            "<Configure>",
            self._resize_scroll_body,
        )
        self._install_wheel_router()
        self.body.columnconfigure(0, weight=1)
        self.rowconfigure(content_row, weight=1)
        self._scroll_refresh_job = None
        # 初始不显示状态；发生选择、处理、完成或错误时再给出提示。
        self.status_var = tk.StringVar(value="")

    def _sync_scroll_region(self, _event=None):
        # 不给Canvas窗口写死高度，让内嵌Frame始终使用自身请求高度。
        # 写死高度会导致grid_remove/grid恢复后新增内容被裁切，滚动条却误以为已到底。
        if self._scroll_refresh_job is not None:
            try:
                self.after_cancel(self._scroll_refresh_job)
            except tk.TclError:
                pass
        self._scroll_refresh_job = self.after_idle(self._apply_scroll_region)

    def _apply_scroll_region(self):
        self._scroll_refresh_job = None
        if not self.winfo_exists():
            return
        width = max(1, self.scroll_canvas.winfo_width())
        viewport_height = max(1, self.scroll_canvas.winfo_height())
        self.body.update_idletasks()
        requested_height = max(1, self.body.winfo_reqheight())
        target_height = max(requested_height, viewport_height)
        self.scroll_canvas.itemconfigure(
            self.body_window,
            width=width,
            height=target_height,
        )
        self.scroll_canvas.configure(scrollregion=(0, 0, width, target_height))

        # 内容放得下时让页面主体填满可用高度并隐藏总滚动条；窗口缩小、
        # 内容确实溢出时再自动恢复滚动条。输入框可借助grid权重同步伸缩。
        if requested_height <= viewport_height + 2:
            self.scroll_canvas.yview_moveto(0)
            if self.scrollbar.winfo_manager():
                self.scrollbar.grid_remove()
        elif not self.scrollbar.winfo_manager():
            self.scrollbar.grid(row=0, column=1, sticky="ns")

    def _resize_scroll_body(self, event):
        """同步宽度，高度由内容与当前可用空间共同决定。"""
        self.scroll_canvas.itemconfigure(
            self.body_window,
            width=event.width,
            height=0,
        )
        self.scroll_canvas.coords(self.body_window, 0, 0)
        self._sync_scroll_region()

    def _install_wheel_router(self):
        """让滚轮在输入框、列表、文本框等任意子控件上都能滚动所属页面。"""
        root = self.winfo_toplevel()
        if getattr(root, "_tool_panel_wheel_router_installed", False):
            return
        root._tool_panel_wheel_router_installed = True
        root.bind_all("<MouseWheel>", self._route_mousewheel, add="+")

    @staticmethod
    def _route_mousewheel(event):
        widget = event.widget
        while widget is not None:
            if isinstance(widget, ToolPanel):
                first, last = widget.scroll_canvas.yview()
                direction = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
                # 到达页面边界时不拦截，允许文本框等控件处理自身滚动。
                if (direction < 0 and first <= 0) or (direction > 0 and last >= 1):
                    return None
                widget.scroll_canvas.yview_scroll(direction, "units")
                return "break"
            widget = getattr(widget, "master", None)
        return None

    def section(self, title, row, padding=(16, 13)):
        frame = ttk.LabelFrame(self.body, text=title, padding=padding, style="Section.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        frame.columnconfigure(1, weight=1)
        return frame

    def add_status(self, row):
        ttk.Label(self.body, textvariable=self.status_var, style="Status.TLabel").grid(
            row=row, column=0, sticky="w", pady=(2, 0)
        )

    def browse_file(self, variable, title, filetypes):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if path:
            variable.set(path)
            self.status_var.set("已选择文件")

    def browse_directory(self, variable):
        path = filedialog.askdirectory(title="选择输出目录", initialdir=variable.get() or None)
        if path:
            variable.set(path)

    def run_background(self, button, task, on_success, running_text="处理中..."):
        button.configure(state="disabled")
        self.status_var.set(running_text)

        def worker():
            try:
                result = task()
            except Exception as exc:
                self.after(0, lambda error=exc: finish_error(error))
            else:
                self.after(0, lambda value=result: finish_success(value))

        def finish_error(exc):
            button.configure(state="normal")
            self.status_var.set("处理失败")
            messagebox.showerror("处理失败", str(exc), parent=self)

        def finish_success(result):
            button.configure(state="normal")
            on_success(result)

        threading.Thread(target=worker, daemon=True).start()


def _make_secondary_nav(parent, items, command):
    """创建中等权重二级导航，与一级菜单区分并保持明显可切换感。"""
    nav = tk.Frame(
        parent, background="#e8f0f5", height=48, borderwidth=0,
        highlightthickness=1, highlightbackground="#c9d7e2"
    )
    nav.grid(row=0, column=0, sticky="ew")
    nav.grid_propagate(False)
    buttons, indicators = {}, {}
    for column, (key, label) in enumerate(items):
        nav_column = column * 2
        nav.columnconfigure(nav_column, minsize=160)
        item = tk.Frame(nav, background="#e8f0f5", borderwidth=0, highlightthickness=0)
        item.grid(row=0, column=nav_column, sticky="nsew", pady=(5, 0))
        item.rowconfigure(0, weight=1)
        item.columnconfigure(0, weight=1)
        button = tk.Button(
            item, text=label, command=lambda page_key=key: command(page_key),
            font=("Microsoft YaHei UI", 10), foreground="#465b6e", background="#e8f0f5",
            activeforeground="#0f638e", activebackground="#dcecf5", relief="flat",
            overrelief="flat", borderwidth=0, highlightthickness=0, takefocus=False,
            padx=16, pady=0, cursor="hand2",
        )
        button.grid(row=0, column=0, sticky="nsew")
        indicator = tk.Frame(item, background="#e8f0f5", height=4, borderwidth=0)
        indicator.grid(row=1, column=0, sticky="ew")
        buttons[key] = button
        indicators[key] = indicator
        if column < len(items) - 1:
            separator = tk.Frame(nav, background="#bdccd8", width=1, borderwidth=0)
            separator.grid(row=0, column=nav_column + 1, sticky="ns", pady=12)
    return nav, buttons, indicators


def _select_secondary_nav(buttons, indicators, key):
    """用淡蓝色块和底部强调线突出当前二级功能。"""
    for page_key, button in buttons.items():
        selected = page_key == key
        button.configure(
            background="#d4e9f4" if selected else "#e8f0f5",
            foreground="#0b5f8a" if selected else "#465b6e",
            activebackground="#c9e3f1" if selected else "#dcecf5",
            activeforeground="#0b5f8a",
            font=("Microsoft YaHei UI", 10, "bold" if selected else "normal"),
        )
        indicators[page_key].configure(background="#1677a8" if selected else "#e8f0f5")


def _set_text_value(widget, value):
    """更新只读风格的Tk文本框内容。"""
    widget.configure(state="normal")
    widget.delete("1.0", tk.END)
    widget.insert("1.0", value)
    widget.configure(state="disabled")


def _format_send_result(result):
    """将请求与平台原始响应整理为页面可读文本。"""
    payload = json.dumps({"imei": result.imei, "cmd": result.cmd}, ensure_ascii=False)
    lines = [f"POST {result.url}", "Content-Type: application/json", f"请求JSON：{payload}"]
    if result.status is not None:
        lines.append(f"HTTP状态：{result.status}")
    else:
        lines.append("HTTP状态：未收到响应")
    if result.response_text:
        lines.append("返回内容：")
        lines.append(result.response_text)
    if result.error:
        lines.append(f"错误信息：{result.error}")
    return "\n".join(lines)


class _PacketSendMixin:
    """为协议组包页面提供统一的imei/cmd JSON发送区。"""

    def _build_send_section(self, row, endpoint):
        # 接口属于固定内部配置，不在界面展示或开放编辑。
        self.send_endpoint = endpoint
        self.send_imei_var = tk.StringVar()
        self.send_cmd_var = tk.StringVar()
        self.send_timeout_var = tk.StringVar(value="10")

        frame = self.section("数据发送", row)
        ttk.Label(frame, text="IMEI").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.send_imei_var, width=24).grid(
            row=0, column=1, sticky="w", padx=(10, 20), pady=4
        )
        ttk.Label(frame, text="超时（秒）").grid(row=0, column=2, sticky="e", pady=4)
        ttk.Entry(frame, textvariable=self.send_timeout_var, width=8).grid(
            row=0, column=3, sticky="w", padx=(10, 0), pady=4
        )
        ttk.Label(frame, text="CMD").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.send_cmd_var).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=4
        )

        self.send_button = ttk.Button(
            frame, text="发送数据", command=self.send_packet_data, style="Primary.TButton"
        )
        self.send_button.grid(row=2, column=0, sticky="w", pady=(9, 4))
        ttk.Label(
            frame, text='POST application/json：{"imei":"...","cmd":"..."}',
            style="Hint.TLabel"
        ).grid(row=2, column=1, columnspan=3, sticky="w", padx=(10, 0), pady=(9, 4))
        self.send_result_text = scrolledtext.ScrolledText(
            frame, height=6, font=("Consolas", 9), wrap="word", state="disabled"
        )
        self.send_result_text.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        frame.columnconfigure(1, weight=1)

    def _set_send_payload(self, cmd, imei=None):
        self.send_cmd_var.set(str(cmd or ""))
        if imei is not None:
            self.send_imei_var.set(str(imei or ""))
        _set_text_value(self.send_result_text, "")

    def _clear_send_payload(self, clear_imei=False):
        self.send_cmd_var.set("")
        if clear_imei:
            self.send_imei_var.set("")
        _set_text_value(self.send_result_text, "")

    def send_packet_data(self):
        try:
            url, imei, cmd = normalize_command_payload(
                self.send_endpoint, self.send_imei_var.get(), self.send_cmd_var.get()
            )
            timeout = float(self.send_timeout_var.get().strip())
            if not 1 <= timeout <= 120:
                raise ValueError("发送超时时间应为1～120秒")
        except ValueError as exc:
            messagebox.showerror("发送数据失败", str(exc), parent=self)
            return
        self.send_imei_var.set(imei)
        self.send_cmd_var.set(cmd)
        self.send_button.configure(state="disabled")
        self.status_var.set("正在发送数据...")
        _set_text_value(
            self.send_result_text,
            f"POST {url}\n请求JSON：{json.dumps({'imei': imei, 'cmd': cmd}, ensure_ascii=False)}"
            f"\n超时：{timeout:g}秒\n\n正在等待平台响应...",
        )

        def worker():
            result = send_command_json(url, imei, cmd, timeout=timeout)
            self.after(0, lambda: self._finish_packet_send(result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_packet_send(self, result):
        self.send_button.configure(state="normal")
        _set_text_value(self.send_result_text, _format_send_result(result))
        if result.http_ok:
            self.status_var.set(f"数据发送完成：HTTP {result.status}")
        elif result.status is not None:
            self.status_var.set(f"数据发送失败：HTTP {result.status}")
        else:
            self.status_var.set("数据发送失败：未收到平台响应")
        self._sync_scroll_region()


class CoordinatePanel(ToolPanel):
    def __init__(self, master):
        super().__init__(master, "坐标系转换", "WGS84、GCJ-02、BD-09 双向转换，以及度分秒/度分转十进制度。")
        self.direction = tk.StringVar(value="wgs2gcj")
        self.direction_label = tk.StringVar(value="WGS84 → GCJ-02")
        self.input_lat = tk.StringVar()
        self.input_lon = tk.StringVar()
        self.output_lat = tk.StringVar()
        self.output_lon = tk.StringVar()
        self.angle_format = tk.StringVar(value="度分秒（DMS）")
        self.angle_input = tk.StringVar()
        self.angle_output = tk.StringVar()

        direction_frame = self.section("转换方向", 0)
        ttk.Label(direction_frame, text="坐标系").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.direction_combo = ttk.Combobox(
            direction_frame,
            textvariable=self.direction_label,
            values=("WGS84 → GCJ-02", "GCJ-02 → WGS84", "WGS84 → BD-09", "BD-09 → WGS84"),
            state="readonly",
            width=26,
        )
        self.direction_combo.grid(row=0, column=1, sticky="w")
        self.direction_combo.bind("<<ComboboxSelected>>", self.on_direction_selected)

        input_frame = self.section("输入坐标", 1)
        ttk.Label(input_frame, text="纬度 Latitude").grid(row=0, column=0, sticky="w", padx=(0, 16), pady=5)
        ttk.Entry(input_frame, textvariable=self.input_lat).grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(input_frame, text="经度 Longitude").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=5)
        ttk.Entry(input_frame, textvariable=self.input_lon).grid(row=1, column=1, sticky="ew", pady=5)

        output_frame = self.section("转换结果", 2)
        ttk.Label(output_frame, text="转换后纬度").grid(row=0, column=0, sticky="w", padx=(0, 16), pady=5)
        ttk.Entry(output_frame, textvariable=self.output_lat, state="readonly").grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(output_frame, text="转换后经度").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=5)
        ttk.Entry(output_frame, textvariable=self.output_lon, state="readonly").grid(row=1, column=1, sticky="ew", pady=5)

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Button(actions, text="执行转换", command=self.convert, style="Primary.TButton").pack(side="left")
        ttk.Button(actions, text="清空", command=self.clear).pack(side="left", padx=10)

        angle_frame = self.section("角度格式转 WGS84 十进制度", 4)
        ttk.Label(angle_frame, text="输入格式").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Combobox(
            angle_frame,
            textvariable=self.angle_format,
            values=("度分秒（DMS）", "度分（DM）"),
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(angle_frame, text="角度值（可多个）").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(angle_frame, textvariable=self.angle_input).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(
            angle_frame,
            text="多个值用逗号分隔，例如：34°11′21.67″,108°52′43.07″；支持 N/S/E/W",
        ).grid(
            row=2, column=1, sticky="w", pady=(0, 8)
        )
        ttk.Label(angle_frame, text="十进制度结果").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(angle_frame, textvariable=self.angle_output, state="readonly").grid(
            row=3, column=1, sticky="ew", pady=5
        )
        ttk.Button(angle_frame, text="转换角度", command=self.convert_angle, style="Primary.TButton").grid(
            row=4, column=1, sticky="w", pady=(8, 0)
        )
        self.add_status(5)

    def on_direction_selected(self, _event=None):
        mapping = {
            "WGS84 → GCJ-02": "wgs2gcj",
            "GCJ-02 → WGS84": "gcj2wgs",
            "WGS84 → BD-09": "wgs2bd",
            "BD-09 → WGS84": "bd2wgs",
        }
        self.direction.set(mapping[self.direction_label.get()])

    def convert(self):
        try:
            lat = float(self.input_lat.get().strip())
            lon = float(self.input_lon.get().strip())
            result_lat, result_lon = convert_coordinate(lat, lon, self.direction.get())
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc), parent=self)
            return
        self.output_lat.set(f"{result_lat:.8f}")
        self.output_lon.set(f"{result_lon:.8f}")
        self.status_var.set("转换完成")
        if self.direction.get() in {"wgs2gcj", "gcj2wgs"} and out_of_china(lat, lon):
            messagebox.showinfo("提示", "该坐标不在中国境内，返回原始坐标！", parent=self)

    def convert_angle(self):
        try:
            angle_format = "dms" if self.angle_format.get().startswith("度分秒") else "dm"
            values = angle_list_to_decimal(self.angle_input.get(), angle_format)
        except ValueError as exc:
            messagebox.showerror("角度格式错误", str(exc), parent=self)
            return
        self.angle_output.set(",".join(f"{value:.8f}" for value in values))
        self.status_var.set(f"已转换 {len(values)} 个 WGS84 十进制度")

    def clear(self):
        self.input_lat.set("")
        self.input_lon.set("")
        self.output_lat.set("")
        self.output_lon.set("")
        self.angle_input.set("")
        self.angle_output.set("")
        self.status_var.set("已清空")


class ExcelKmlPanel(ToolPanel):
    def __init__(self, master):
        super().__init__(
            master, "Excel 生成 KML",
            "支持 4.0 工具导出数据和仅经纬度数据，生成轨迹与点位 KML。",
            show_heading=False,
        )
        self.file_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.data_format_label = tk.StringVar(value="4.0 工具导出的 GPS 数据")
        self.data_format_hint = tk.StringVar(value="4.0工具3.1章节导出的EXCEL")
        self.result_var = tk.StringVar(value="尚未生成文件")

        format_frame = self.section("Excel 数据格式", 0)
        ttk.Label(format_frame, text="数据类型").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.data_format_combo = ttk.Combobox(
            format_frame,
            textvariable=self.data_format_label,
            values=("4.0 工具导出的 GPS 数据", "仅经纬度数据"),
            state="readonly",
            width=32,
        )
        self.data_format_combo.grid(row=0, column=1, sticky="w")
        self.data_format_combo.bind("<<ComboboxSelected>>", self.on_data_format_selected)
        ttk.Label(
            format_frame,
            textvariable=self.data_format_hint,
            style="Hint.TLabel",
        ).grid(row=0, column=2, sticky="w", padx=(14, 0))

        file_frame = self.section("输入 Excel", 1)
        ttk.Entry(file_frame, textvariable=self.file_var).grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ttk.Button(
            file_frame, text="浏览", command=lambda: self.browse_file(
                self.file_var, "选择Excel文件", [("Excel files", "*.xlsx *.xls")]
            )
        ).grid(row=0, column=2)

        output_frame = self.section("输出目录", 2)
        ttk.Entry(output_frame, textvariable=self.output_var).grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ttk.Button(output_frame, text="更改", command=lambda: self.browse_directory(self.output_var)).grid(row=0, column=2)

        result_frame = self.section("生成结果", 3)
        ttk.Label(result_frame, textvariable=self.result_var, justify="left", wraplength=760).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=4, column=0, sticky="ew")
        self.start_button = ttk.Button(actions, text="生成 KML", command=self.start, style="Primary.TButton")
        self.start_button.pack(side="left")
        ttk.Button(actions, text="打开输出目录", command=lambda: _open_directory(self.output_var.get())).pack(side="left", padx=10)
        self.add_status(5)

    def on_data_format_selected(self, _event=None):
        if self.data_format_label.get().startswith("4.0"):
            self.data_format_hint.set("4.0工具3.1章节导出的EXCEL")
        else:
            self.data_format_hint.set("必需列：经度、纬度；备注列可选")

    def start(self):
        file_path = self.file_var.get().strip()
        output_dir = self.output_var.get().strip()
        if not file_path:
            messagebox.showwarning("缺少文件", "请先选择 Excel 文件", parent=self)
            return
        if not output_dir:
            messagebox.showwarning("缺少目录", "请选择输出目录", parent=self)
            return
        self.run_background(
            self.start_button,
            lambda: generate_excel_kml(
                file_path,
                output_dir,
                "tool4" if self.data_format_label.get().startswith("4.0") else "simple",
            ),
            self.finished,
            "正在读取 Excel 并生成 KML...",
        )

    def finished(self, result):
        warning_text = ""
        if result.warnings:
            warning_text = f"\n跳过 {len(result.warnings)} 行：" + "；".join(result.warnings[:3])
        self.result_var.set(
            f"有效点数：{result.point_count}\n轨迹：{result.tracker_file}\n点位：{result.point_file}{warning_text}"
        )
        self.status_var.set("生成完成")
        messagebox.showinfo("生成完成", "Excel KML 文件已生成", parent=self)


class NmeaKmlPanel(ToolPanel):
    def __init__(self, master):
        super().__init__(
            master, "TXT 生成 KML",
            "从 TXT/NMEA 文本中的 GGA/RMC 数据生成轨迹和点位详情。",
            show_heading=False,
        )
        self.file_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.result_var = tk.StringVar(value="尚未生成文件")

        file_frame = self.section("输入 TXT 文件", 0)
        ttk.Entry(file_frame, textvariable=self.file_var).grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ttk.Button(
            file_frame, text="浏览", command=lambda: self.browse_file(self.file_var, "选择 TXT/NMEA 文件", FILE_TYPES_NMEA)
        ).grid(row=0, column=2)

        output_frame = self.section("输出目录", 1)
        ttk.Entry(output_frame, textvariable=self.output_var).grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ttk.Button(output_frame, text="更改", command=lambda: self.browse_directory(self.output_var)).grid(row=0, column=2)

        result_frame = self.section("生成结果", 2)
        ttk.Label(result_frame, textvariable=self.result_var, justify="left", wraplength=760).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=3, column=0, sticky="ew")
        self.start_button = ttk.Button(actions, text="生成 KML", command=self.start, style="Primary.TButton")
        self.start_button.pack(side="left")
        ttk.Button(actions, text="打开输出目录", command=lambda: _open_directory(self.output_var.get())).pack(side="left", padx=10)
        self.add_status(4)

    def start(self):
        file_path = self.file_var.get().strip()
        output_dir = self.output_var.get().strip()
        if not file_path:
            messagebox.showwarning("缺少文件", "请先选择 TXT 数据文件", parent=self)
            return
        if not output_dir:
            messagebox.showwarning("缺少目录", "请选择输出目录", parent=self)
            return
        self.run_background(
            self.start_button,
            lambda: generate_nmea_kml(file_path, output_dir),
            self.finished,
            "正在解析 TXT 并生成 KML...",
        )

    def finished(self, result):
        self.result_var.set(
            f"有效点数：{result.point_count}\n轨迹：{result.tracker_file}\n点位：{result.point_file}"
        )
        self.status_var.set("生成完成")
        messagebox.showinfo("生成完成", "TXT KML 文件已生成", parent=self)


class KmlGenerationPanel(ttk.Frame):
    """KML生成一级菜单，默认显示TXT生成，亦可切换到Excel生成。"""

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        _nav, self.nav_buttons, self.nav_indicators = _make_secondary_nav(
            self, (("txt", "TXT → KML"), ("excel", "Excel → KML")), self.show_page
        )

        content = ttk.Frame(self, style="Page.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.pages = {
            "txt": NmeaKmlPanel(content),
            "excel": ExcelKmlPanel(content),
        }
        for key, page in self.pages.items():
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page("txt")

    def show_page(self, key):
        self.pages[key].tkraise()
        _select_secondary_nav(self.nav_buttons, self.nav_indicators, key)


class CepPanel(ToolPanel):
    def __init__(self, master):
        super().__init__(master, "CEP 分析", "自定义锚点，导出散点图、柱状图和可用卫星数 Excel。")
        self.lat_var = tk.StringVar()
        self.lon_var = tk.StringVar()
        self.keyword_var = tk.StringVar(value="$GNGGA")
        self.file_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.result_var = tk.StringVar(value="尚未执行分析")

        anchor_frame = self.section("自定义锚点", 0)
        ttk.Label(anchor_frame, text="纬度").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(anchor_frame, textvariable=self.lat_var, width=22).grid(row=0, column=1, sticky="ew", padx=(0, 20))
        ttk.Label(anchor_frame, text="经度").grid(row=0, column=2, sticky="w", padx=(0, 10))
        ttk.Entry(anchor_frame, textvariable=self.lon_var, width=22).grid(row=0, column=3, sticky="ew")
        anchor_frame.columnconfigure(1, weight=1)
        anchor_frame.columnconfigure(3, weight=1)

        settings_frame = self.section("数据设置", 1)
        ttk.Label(settings_frame, text="NMEA 关键字").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(settings_frame, textvariable=self.keyword_var).grid(row=0, column=1, sticky="ew")

        file_frame = self.section("输入与输出", 2)
        ttk.Label(file_frame, text="数据文件").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(file_frame, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", pady=4, padx=(0, 10))
        ttk.Button(
            file_frame, text="浏览", command=lambda: self.browse_file(self.file_var, "选择 NMEA 数据文件", FILE_TYPES_NMEA)
        ).grid(row=0, column=2, pady=4)
        ttk.Label(file_frame, text="输出目录").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(file_frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=4, padx=(0, 10))
        ttk.Button(file_frame, text="更改", command=lambda: self.browse_directory(self.output_var)).grid(row=1, column=2, pady=4)

        result_frame = self.section("分析结果", 3)
        ttk.Label(result_frame, textvariable=self.result_var, justify="left", wraplength=760).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=4, column=0, sticky="ew")
        self.start_button = ttk.Button(actions, text="开始分析", command=self.start, style="Primary.TButton")
        self.start_button.pack(side="left")
        ttk.Button(actions, text="打开输出目录", command=lambda: _open_directory(self.output_var.get())).pack(side="left", padx=10)
        self.add_status(5)

    def start(self):
        try:
            fixed_point = (float(self.lat_var.get().strip()), float(self.lon_var.get().strip()))
        except ValueError:
            messagebox.showerror("输入错误", "请输入有效的锚点经纬度", parent=self)
            return
        if not (-90 <= fixed_point[0] <= 90 and -180 <= fixed_point[1] <= 180):
            messagebox.showerror("输入错误", "纬度范围为 -90~90，经度范围为 -180~180", parent=self)
            return
        file_path = self.file_var.get().strip()
        if not file_path:
            messagebox.showwarning("缺少文件", "请先选择 NMEA 数据文件", parent=self)
            return
        output_dir = self.output_var.get().strip()
        if not output_dir:
            messagebox.showwarning("缺少目录", "请选择输出目录", parent=self)
            return
        self.run_background(
            self.start_button,
            lambda: analyze_cep(
                file_path, fixed_point, self.keyword_var.get() or "$GNGGA", output_dir
            ),
            self.finished,
            "正在解析、计算并绘图...",
        )

    def finished(self, result):
        cep50, cep68, cep95, cep99, average = result.ceps
        self.result_var.set(
            f"有效点数：{result.point_count}　平均高度：{result.average_height:.2f} m\n"
            f"CEP50：{cep50:.2f} m　CEP68：{cep68:.2f} m　CEP95：{cep95:.2f} m　"
            f"CEP99：{cep99:.2f} m　AVG：{average:.2f} m\n"
            f"散点图：{result.scatter_file}\n柱状图：{result.bar_file}\n卫星数：{result.satellite_file}"
        )
        self.status_var.set("分析完成")
        messagebox.showinfo("处理成功", "CEP 分析完成，结果已生成", parent=self)


class ColdStartPanel(ToolPanel):
    def __init__(self, master):
        super().__init__(master, "冷热启动时间分析", "按启动关键字分段，统计首次有效 GGA 定位耗时。")
        self.file_var = tk.StringVar()
        self.boot_var = tk.StringVar(value="Welcome to boot rom")
        self.nmea_var = tk.StringVar(value="$GNGGA")
        self.skip_var = tk.BooleanVar(value=False)

        settings_frame = self.section("分析设置", 0)
        ttk.Label(settings_frame, text="日志文件").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(settings_frame, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=4)
        ttk.Button(
            settings_frame, text="浏览", command=lambda: self.browse_file(
                self.file_var, "选择GNSS日志文件", [("日志文本", "*.txt *.log"), ("所有文件", "*.*")]
            )
        ).grid(row=0, column=2, pady=4)
        ttk.Label(settings_frame, text="启动关键字").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(settings_frame, textvariable=self.boot_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Label(settings_frame, text="定位NMEA语句").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(settings_frame, textvariable=self.nmea_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)
        self.skip_check = tk.Checkbutton(
            settings_frame,
            text="仅检查有效经纬度（不校验 GGA 定位有效性标志）",
            variable=self.skip_var,
            command=self._sync_skip_check,
            indicatoron=False,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            background="#f8fafc",
            activebackground="#f8fafc",
            foreground="#243746",
            activeforeground="#243746",
            selectcolor="#f8fafc",
            font=("Microsoft YaHei UI", 10),
            anchor="w",
            cursor="hand2",
            padx=0,
            pady=2,
            takefocus=False,
        )
        self.skip_check.grid(row=3, column=1, columnspan=2, sticky="w", pady=(7, 0))
        self._sync_skip_check()

        report_frame = ttk.LabelFrame(self.body, text="统计报告", padding=8, style="Section.TLabelframe")
        report_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        report_frame.rowconfigure(0, weight=1)
        report_frame.columnconfigure(0, weight=1)
        self.body.rowconfigure(1, weight=1)
        self.report_box = scrolledtext.ScrolledText(report_frame, font=("Consolas", 9), wrap="word", height=14)
        self.report_box.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        self.start_button = ttk.Button(actions, text="开始分析", command=self.start, style="Primary.TButton")
        self.start_button.pack(side="left")
        ttk.Button(actions, text="清空报告", command=lambda: self.report_box.delete("1.0", tk.END)).pack(side="left", padx=10)
        self.add_status(3)

    def start(self):
        self.run_background(
            self.start_button,
            lambda: analyze_cold_start(
                self.file_var.get(), self.boot_var.get(), self.nmea_var.get(), self.skip_var.get()
            ),
            self.finished,
            "正在分析日志...",
        )

    def _sync_skip_check(self):
        mark = "☑" if self.skip_var.get() else "☐"
        self.skip_check.configure(
            text=f"{mark} 仅检查有效经纬度（不校验 GGA 定位有效性标志）"
        )

    def finished(self, result):
        self.report_box.delete("1.0", tk.END)
        self.report_box.insert(tk.END, result.report)
        self.report_box.see(tk.END)
        self.status_var.set(f"分析完成：启动 {result.boot_total_count} 次，有效 {len(result.records)} 次")


class FenceKmlPanel(ToolPanel):
    """电子围栏绘制与 KML 生成页面。"""

    SHAPE_LABELS = {
        "circle": "圆形",
        "rectangle": "矩形",
        "polygon": "多边形",
    }
    LABEL_SHAPES = {
        "圆形": "circle",
        "矩形": "rectangle",
        "多边形": "polygon",
    }

    def __init__(self, master):
        super().__init__(
            master, "电子围栏绘制", "绘制圆形、矩形或多边形围栏，并生成电子围栏 KML。",
            show_heading=False,
        )
        self.shape_var = tk.StringVar(value="circle")
        self.shape_label_var = tk.StringVar(value=self.SHAPE_LABELS["circle"])
        self.name_var = tk.StringVar(value="电子围栏-圆形")
        self.center_lat_var = tk.StringVar()
        self.center_lon_var = tk.StringVar()
        self.radius_var = tk.StringVar()
        self.nw_lat_var = tk.StringVar()
        self.nw_lon_var = tk.StringVar()
        self.se_lat_var = tk.StringVar()
        self.se_lon_var = tk.StringVar()
        self.map_server = MapPickerServer()

        type_frame = self.section("围栏类型", 0)
        ttk.Label(type_frame, text="选择类型").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.shape_combo = ttk.Combobox(
            type_frame,
            textvariable=self.shape_label_var,
            values=tuple(self.SHAPE_LABELS.values()),
            state="readonly",
            width=20,
        )
        self.shape_combo.grid(row=0, column=1, sticky="w")
        self.shape_combo.bind("<<ComboboxSelected>>", self.on_shape_selected)

        self.input_frame = self.section("围栏参数", 1)
        self.shape_frames = {}
        self._build_circle_form()
        self._build_rectangle_form()
        self._build_polygon_form()
        self.show_shape(update_name=False)

        map_frame = self.section("地图绘制围栏", 2)
        ttk.Button(map_frame, text="打开电子围栏地图", command=self.open_map, style="Primary.TButton").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(
            map_frame,
            text="支持圆形拖拽、矩形拖拽和多边形逐点绘制；结果以 WGS84 回填。",
            wraplength=600,
        ).grid(row=0, column=1, sticky="w")

        output_frame = self.section("生成文件", 3)
        ttk.Label(output_frame, text="名称").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(output_frame, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=(0, 12))
        ttk.Button(output_frame, text="生成围栏 KML", command=self.generate_fence, style="Primary.TButton").grid(
            row=0, column=2
        )
        self.add_status(4)
        for row in range(5):
            self.body.rowconfigure(row, weight=0)
        self.after(350, self.poll_map_results)

    @staticmethod
    def _entry_row(parent, row, label1, variable1, label2, variable2):
        ttk.Label(parent, text=label1).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(parent, textvariable=variable1, width=20).grid(row=row, column=1, sticky="ew", padx=(0, 18), pady=5)
        ttk.Label(parent, text=label2).grid(row=row, column=2, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(parent, textvariable=variable2, width=20).grid(row=row, column=3, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)

    def _build_circle_form(self):
        frame = ttk.Frame(self.input_frame, style="Page.TFrame")
        self.shape_frames["circle"] = frame
        self._entry_row(frame, 0, "圆心纬度", self.center_lat_var, "圆心经度", self.center_lon_var)
        ttk.Label(frame, text="半径（米）").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(frame, textvariable=self.radius_var, width=20).grid(row=1, column=1, sticky="w", pady=5)

    def _build_rectangle_form(self):
        frame = ttk.Frame(self.input_frame, style="Page.TFrame")
        self.shape_frames["rectangle"] = frame
        self._entry_row(frame, 0, "左上角纬度", self.nw_lat_var, "左上角经度", self.nw_lon_var)
        self._entry_row(frame, 1, "右下角纬度", self.se_lat_var, "右下角经度", self.se_lon_var)

    def _build_polygon_form(self):
        frame = ttk.Frame(self.input_frame, style="Page.TFrame")
        self.shape_frames["polygon"] = frame
        ttk.Label(frame, text="每行填写一个顶点：纬度,经度（至少 3 点）").pack(anchor="w", pady=(0, 6))
        self.polygon_text = scrolledtext.ScrolledText(frame, height=5, font=("Consolas", 9), wrap="none")
        self.polygon_text.pack(fill="x")

    def on_shape_selected(self, _event=None):
        shape = self.LABEL_SHAPES.get(self.shape_label_var.get(), "circle")
        self.shape_var.set(shape)
        self.show_shape(update_name=True)

    def set_shape(self, shape, update_name=True):
        """统一切换类型，供下拉框和地图回填共同使用。"""
        if shape not in self.SHAPE_LABELS:
            raise ValueError(f"未知围栏类型：{shape}")
        self.shape_var.set(shape)
        self.shape_label_var.set(self.SHAPE_LABELS[shape])
        self.show_shape(update_name=update_name)

    def show_shape(self, update_name=True):
        for frame in self.shape_frames.values():
            frame.grid_forget()
        shape = self.shape_var.get()
        self.shape_frames[shape].grid(row=0, column=0, columnspan=4, sticky="ew")
        if update_name:
            self.name_var.set(f"电子围栏-{self.SHAPE_LABELS[shape]}")

    def open_map(self):
        try:
            url = self.map_server.open_window("fence")
        except Exception as exc:
            messagebox.showerror("地图打开失败", str(exc), parent=self)
            return
        self.status_var.set(f"围栏地图已打开；若浏览器未出现，可访问：{url}")

    def poll_map_results(self):
        try:
            results = self.map_server.pop_results()
            for payload in results:
                self.apply_map_result(payload)
        finally:
            if self.winfo_exists():
                self.after(350, self.poll_map_results)

    def apply_map_result(self, payload):
        fences = payload.get("fences", [])
        if not isinstance(fences, list) or not fences:
            self.status_var.set("地图未返回可回填的围栏")
            return

        try:
            parsed = []
            for selected in fences:
                map_shape = selected.get("shape")
                shape = {
                    "circle": "circle",
                    "rect": "rectangle",
                    "rectangle": "rectangle",
                    "poly": "polygon",
                    "polygon": "polygon",
                }.get(map_shape)
                if shape is None:
                    raise ValueError(f"地图返回了不支持的围栏类型：{map_shape}")

                points = selected.get("points") or []
                if shape == "circle":
                    if not points:
                        raise ValueError("圆形围栏缺少圆心坐标")
                    latitude, longitude = float(points[0][0]), float(points[0][1])
                    radius = float(selected.get("radius") or 0)
                    if radius <= 0:
                        raise ValueError("圆形围栏半径无效")
                    parsed.append((shape, (latitude, longitude, radius)))
                elif shape == "rectangle":
                    if len(points) < 2:
                        raise ValueError("矩形围栏缺少两个对角坐标")
                    latitudes = [float(points[0][0]), float(points[1][0])]
                    longitudes = [float(points[0][1]), float(points[1][1])]
                    parsed.append((shape, (
                        max(latitudes), min(longitudes),
                        min(latitudes), max(longitudes),
                    )))
                else:
                    if len(points) < 3:
                        raise ValueError("多边形围栏至少需要 3 个顶点")
                    polygon_lines = []
                    for index, point in enumerate(points, start=1):
                        if not isinstance(point, (list, tuple)) or len(point) < 2:
                            raise ValueError(f"多边形第 {index} 个顶点格式无效")
                        polygon_lines.append(f"{float(point[0]):.6f},{float(point[1]):.6f}")
                    parsed.append((shape, polygon_lines))
        except (TypeError, ValueError, IndexError) as exc:
            self.status_var.set(f"围栏回填失败：{exc}")
            messagebox.showerror("围栏回填失败", str(exc), parent=self)
            return

        # 三种围栏分别写入各自的参数区；最后绘制的类型显示在主界面上。
        for shape, values in parsed:
            if shape == "circle":
                latitude, longitude, radius = values
                self.center_lat_var.set(f"{latitude:.6f}")
                self.center_lon_var.set(f"{longitude:.6f}")
                self.radius_var.set(str(int(round(radius))))
            elif shape == "rectangle":
                nw_lat, nw_lon, se_lat, se_lon = values
                self.nw_lat_var.set(f"{nw_lat:.6f}")
                self.nw_lon_var.set(f"{nw_lon:.6f}")
                self.se_lat_var.set(f"{se_lat:.6f}")
                self.se_lon_var.set(f"{se_lon:.6f}")
            else:
                self.polygon_text.delete("1.0", tk.END)
                self.polygon_text.insert("1.0", "\n".join(values))

        last_shape = parsed[-1][0]
        self.set_shape(last_shape, update_name=True)
        labels = "、".join(self.SHAPE_LABELS[shape] for shape, _ in parsed)
        self.status_var.set(f"已回填 {len(parsed)} 种围栏：{labels}")

    def get_ring(self):
        shape = self.shape_var.get()
        if shape == "circle":
            center = parse_coordinate(self.center_lat_var.get(), self.center_lon_var.get())
            try:
                radius = float(self.radius_var.get().strip())
            except ValueError as exc:
                raise ValueError("圆形半径必须填写有效数字（米）") from exc
            return circle_ring(center, radius)
        if shape == "rectangle":
            top_left = parse_coordinate(self.nw_lat_var.get(), self.nw_lon_var.get())
            bottom_right = parse_coordinate(self.se_lat_var.get(), self.se_lon_var.get())
            return rectangle_ring(top_left, bottom_right)
        return parse_polygon_text(self.polygon_text.get("1.0", tk.END))

    def generate_fence(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("缺少名称", "请填写围栏名称", parent=self)
            return
        try:
            ring = self.get_ring()
        except ValueError as exc:
            messagebox.showerror("参数有误", str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="保存电子围栏 KML", defaultextension=".kml",
            initialfile=f"{name}.kml", filetypes=(("KML 文件", "*.kml"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            saved = write_fence_kml(ring, name, path)
        except OSError as exc:
            messagebox.showerror("生成失败", str(exc), parent=self)
            return
        self.status_var.set(f"围栏 KML 已生成：{saved}")
        messagebox.showinfo("生成成功", f"电子围栏 KML 已生成：\n{saved}", parent=self)


def _parse_protocol_points(text, expected=None):
    """解析“纬度,经度”列表，并按需要校验点数。"""
    points = []
    for index, raw in enumerate(str(text or "").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.replace("，", ",").split(",")]
        if len(parts) != 2:
            raise ValueError(f"第 {index} 行应填写：纬度,经度")
        try:
            latitude, longitude = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise ValueError(f"第 {index} 行经纬度不是有效数字") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError(f"第 {index} 行经纬度超出范围")
        points.append((latitude, longitude))
    if expected is not None and len(points) != expected:
        raise ValueError(f"当前围栏需要 {expected} 个坐标点，实际填写 {len(points)} 个")
    return points


class Fence40PacketPanel(_PacketSendMixin, ToolPanel):
    """4.0 F10F电子围栏KLV组包页面。"""

    REPORT_VALUES = ("00 禁用", "01 进入区域", "02 离开区域", "03 进入和离开区域")
    TYPE_VALUES = ("01 圆形", "02 矩形") + tuple(
        f"{value:02d} 多边形（{value}点{'，超协议测试' if value == 11 else ''}）"
        for value in range(3, 12)
    )
    OPERATION_VALUES = (
        "00 添加新的（Reserved测试）",
        "01 删除所有",
        "02 设置围栏列表",
        "03 删除部分",
    )

    def __init__(self, master):
        super().__init__(
            master, "4.0 协议围栏组包", "按Operation Type切换设置、删除全部和删除部分结构；11点保留作超协议测试。",
            show_heading=False,
        )
        self.rows = []
        self.delete_ids = []
        self.edit_index = None
        self.major_var = tk.StringVar(value="F10F")
        self.op_var = tk.StringVar(value="01 删除所有")
        self.total_var = tk.StringVar(value="1")
        self.index_var = tk.StringVar(value="1")
        self.fence_id_var = tk.StringVar(value="1")
        self.delete_id_var = tk.StringVar()
        self.report_var = tk.StringVar(value=self.REPORT_VALUES[0])
        self.type_var = tk.StringVar(value=self.TYPE_VALUES[0])
        self.radius_var = tk.StringVar()
        self.key_var = tk.StringVar(value="404")
        self.point_rows = []
        self.full_packet_value = ""

        base = self.section("大包基础字段", 0)
        self.base_field_widgets = {}
        definitions = (
            ("major_minor", self.major_var),
            ("操作类型", self.op_var),
            ("待操作围栏总数", self.total_var),
            ("此消息索引开始", self.index_var),
        )
        for column, (label, variable) in enumerate(definitions):
            label_widget = ttk.Label(base, text=label)
            label_widget.grid(row=0, column=column * 2, sticky="w", padx=(0, 6))
            if label == "操作类型":
                widget = ttk.Combobox(base, textvariable=variable, values=self.OPERATION_VALUES,
                                      state="readonly", width=24)
                widget.bind("<<ComboboxSelected>>", self._operation_changed)
            elif label == "待操作围栏总数":
                widget = ttk.Spinbox(
                    base, textvariable=variable, from_=1, to=40, increment=1, width=8,
                    validate="key", validatecommand=(self.register(self._validate_total_count), "%P"),
                )
            elif label == "此消息索引开始":
                widget = ttk.Spinbox(
                    base, textvariable=variable, from_=1, to=255, increment=1, width=8,
                    validate="key", validatecommand=(self.register(self._validate_start_index), "%P"),
                )
            else:
                widget = ttk.Entry(
                    base,
                    textvariable=variable,
                    width=10,
                    state="readonly",
                    style="ProtocolReadonly.TEntry",
                    takefocus=False,
                )
            widget.grid(row=0, column=column * 2 + 1, sticky="ew", padx=(0, 14))
            self.base_field_widgets[label] = (label_widget, widget)
        self.operation_note = ttk.Label(base, style="Hint.TLabel", wraplength=780)
        self.operation_note.grid(row=1, column=0, columnspan=8, sticky="w", pady=(9, 0))

        self.editor_frame = self.section("围栏数据", 1)
        editor = self.editor_frame
        ttk.Label(editor, text="围栏 ID（十进制1～40）").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(editor, textvariable=self.fence_id_var, width=12).grid(row=0, column=1, sticky="w", padx=(8, 20), pady=4)
        ttk.Label(editor, text="上报方式").grid(row=0, column=2, sticky="w", pady=4)
        ttk.Combobox(editor, textvariable=self.report_var, values=self.REPORT_VALUES,
                     state="readonly", width=18).grid(row=0, column=3, sticky="w", padx=(8, 20), pady=4)
        ttk.Label(editor, text="围栏类型 / 点数").grid(row=0, column=4, sticky="w", pady=4)
        type_combo = ttk.Combobox(editor, textvariable=self.type_var, values=self.TYPE_VALUES,
                                  state="readonly", width=24)
        type_combo.grid(row=0, column=5, sticky="w", padx=(8, 0), pady=4)
        type_combo.bind("<<ComboboxSelected>>", self._type_changed)
        ttk.Label(editor, text="KEY（十进制）").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(editor, textvariable=self.key_var, state="readonly", width=12).grid(
            row=1, column=1, sticky="w", padx=(8, 20), pady=4
        )
        self.point_hint = ttk.Label(editor, text="圆形：设置圆心的经纬度和方向", style="Hint.TLabel")
        self.point_hint.grid(row=1, column=2, columnspan=4, sticky="w", pady=4)
        self.points_frame = ttk.Frame(editor, style="Page.TFrame")
        self.points_frame.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(6, 8))
        buttons = ttk.Frame(editor, style="Page.TFrame")
        buttons.grid(row=3, column=0, columnspan=6, sticky="w")
        ttk.Button(buttons, text="添加围栏", command=self.add_or_update,
                   style="Primary.TButton").pack(side="left")
        ttk.Button(buttons, text="删除选中", command=self.delete_selected).pack(side="left", padx=8)
        ttk.Button(buttons, text="清空当前输入", command=self.clear_editor).pack(side="left")

        self.delete_frame = self.section("待删除的围栏 ID", 1)
        ttk.Label(self.delete_frame, text="围栏 ID（十进制1～40，可用逗号一次添加多个）").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(self.delete_frame, textvariable=self.delete_id_var).grid(
            row=0, column=1, sticky="ew", padx=(12, 8)
        )
        ttk.Button(self.delete_frame, text="添加到待删除列表", command=self.add_delete_ids).grid(
            row=0, column=2
        )
        self.delete_tree = ttk.Treeview(self.delete_frame, columns=("seq", "id"), show="headings", height=5)
        self.delete_tree.heading("seq", text="序号")
        self.delete_tree.heading("id", text="Geo ID（十进制）")
        self.delete_tree.column("seq", width=80, anchor="center")
        self.delete_tree.column("id", width=180, anchor="center")
        self.delete_tree.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(self.delete_frame, text="删除选中 ID", command=self.remove_delete_ids).grid(
            row=1, column=2, sticky="nw", padx=(8, 0), pady=(10, 0)
        )

        self.listing_frame = self.section("本消息围栏列表（最多40条，Geo ID不可重复）", 2)
        self.tree = ttk.Treeview(self.listing_frame, columns=("id", "report", "type", "points"),
                                 show="headings", height=5)
        for name, text, width in (("id", "围栏 ID", 100), ("report", "上报方式", 160),
                                  ("type", "围栏类型", 210), ("points", "坐标点", 90)):
            self.tree.heading(name, text=text)
            self.tree.column(name, width=width, anchor="center")
        self.tree.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.load_selected)
        self.listing_frame.columnconfigure(0, weight=1)

        output = self.section("组包输出", 3)
        ttk.Button(output, text="生成完整大包", command=self.build_packet,
                   style="Primary.TButton").grid(row=0, column=0, sticky="w")
        ttk.Button(output, text="复制结果", command=self.copy_result).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(output, text="清空输出", command=self.clear_output).grid(row=0, column=2, sticky="w")
        self.output_text = scrolledtext.ScrolledText(output, height=8, font=("Consolas", 10), wrap="word")
        self.output_text.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        output.columnconfigure(3, weight=1)
        self._build_send_section(4, "http://10.85.40.3:8088/client/send")
        self.add_status(5)
        self._rebuild_point_inputs(1)
        self._sync_operation()

    @staticmethod
    def _validate_total_count(proposed):
        return proposed == "" or (proposed.isdigit() and 1 <= int(proposed) <= 40)

    @staticmethod
    def _validate_start_index(proposed):
        return proposed == "" or (proposed.isdigit() and 1 <= int(proposed) <= 255)

    def _operation_changed(self, _event=None):
        self._sync_operation()

    def _sync_operation(self):
        operation = self.op_var.get().split()[0]
        needs_batch = operation != "01"
        for field in ("待操作围栏总数", "此消息索引开始"):
            for widget in self.base_field_widgets[field]:
                widget.grid() if needs_batch else widget.grid_remove()
        if operation == "01":
            self.operation_note.configure(text="01 删除所有：有效数据仅生成 F10F01，不携带总数、索引、Geo ID或围栏数据。")
            self.editor_frame.grid_remove(); self.listing_frame.grid_remove(); self.delete_frame.grid_remove()
        elif operation == "03":
            self.operation_note.configure(text="03 删除部分：只携带总数、Start_Index、本消息ID数量和Geo ID列表。")
            self.editor_frame.grid_remove(); self.listing_frame.grid_remove(); self.delete_frame.grid()
        else:
            note = "00为协议Reserved值，仅保留作兼容性测试，设备可能不支持。" if operation == "00" else "02设置围栏列表：生成完整围栏Mode、点数和TLV数据。"
            self.operation_note.configure(text=note)
            self.delete_frame.grid_remove(); self.editor_frame.grid(); self.listing_frame.grid()
        self._sync_scroll_region()

    def _type_code(self):
        return self.type_var.get().split()[0]

    def _type_changed(self, _event=None):
        code = self._type_code()
        count = 1 if code == "01" else 2 if code == "02" else int(code)
        if code == "01":
            self.key_var.set("404")
            self.point_hint.configure(text="圆形：设置圆心的经纬度和方向")
        elif code == "02":
            self.key_var.set("405")
            self.point_hint.configure(text="矩形：第一组为左上角，第二组为右下角（暂不校验顺序）")
        else:
            self.key_var.set("406")
            suffix = "；11点为超协议测试" if count == 11 else ""
            self.point_hint.configure(text=f"多边形：按顺序设置{count}个顶点{suffix}")
        self._rebuild_point_inputs(count)

    def _rebuild_point_inputs(self, count, values=None):
        if values is None and self.point_rows:
            try:
                values = self._read_point_inputs()
            except ValueError:
                values = []
        for child in self.points_frame.winfo_children():
            child.destroy()
        self.point_rows = []
        for column, title in enumerate(("", "经度方向", "经度值", "纬度方向", "纬度值")):
            ttk.Label(self.points_frame, text=title).grid(row=0, column=column, padx=5, sticky="w")
        for index in range(count):
            point = values[index] if values and index < len(values) else None
            latitude = float(point[0]) if point is not None else None
            longitude = float(point[1]) if point is not None else None
            lon_dir = tk.StringVar(value="东经" if longitude is None or longitude >= 0 else "西经")
            lon_value = tk.StringVar(value=f"{abs(longitude):.6f}" if longitude is not None else "")
            lat_dir = tk.StringVar(value="北纬" if latitude is None or latitude >= 0 else "南纬")
            lat_value = tk.StringVar(value=f"{abs(latitude):.6f}" if latitude is not None else "")
            self.point_rows.append((lon_dir, lon_value, lat_dir, lat_value))
            label = "圆心" if count == 1 else "左上角" if count == 2 and index == 0 else "右下角" if count == 2 else f"顶点{index + 1}"
            ttk.Label(self.points_frame, text=label, width=8).grid(row=index + 1, column=0, sticky="w", pady=2)
            ttk.Combobox(self.points_frame, textvariable=lon_dir, values=("东经", "西经"),
                         state="readonly", width=7).grid(row=index + 1, column=1, padx=5, pady=2)
            ttk.Entry(self.points_frame, textvariable=lon_value, width=15).grid(row=index + 1, column=2, padx=5, pady=2)
            ttk.Combobox(self.points_frame, textvariable=lat_dir, values=("南纬", "北纬"),
                         state="readonly", width=7).grid(row=index + 1, column=3, padx=5, pady=2)
            ttk.Entry(self.points_frame, textvariable=lat_value, width=15).grid(row=index + 1, column=4, padx=5, pady=2)
        if count == 1:
            ttk.Label(self.points_frame, text="半径（米，20～16777215）").grid(
                row=0, column=5, padx=(18, 5), sticky="w"
            )
            self.radius_entry = ttk.Entry(self.points_frame, textvariable=self.radius_var, width=18)
            self.radius_entry.grid(row=1, column=5, padx=(18, 5), pady=2, sticky="w")
        else:
            self.radius_entry = None

    def _read_point_inputs(self):
        points = []
        for index, (lon_dir, lon_var, lat_dir, lat_var) in enumerate(self.point_rows, 1):
            try:
                longitude = float(lon_var.get().strip()); latitude = float(lat_var.get().strip())
            except ValueError as exc:
                raise ValueError(f"第{index}个坐标必须填写有效数字") from exc
            if longitude < 0 or latitude < 0:
                raise ValueError("经纬度值请填写非负数，方向使用东/西经和南/北纬选择")
            if longitude > 180 or latitude > 90:
                raise ValueError(f"第{index}个坐标超出经纬度范围")
            points.append((latitude * (-1 if lat_dir.get() == "南纬" else 1),
                           longitude * (-1 if lon_dir.get() == "西经" else 1)))
        return points

    @staticmethod
    def _gps_records(points):
        return [{
            "lon_dir": "东经" if lon >= 0 else "西经", "lon": f"{abs(lon):.6f}",
            "lat_dir": "北纬" if lat >= 0 else "南纬", "lat": f"{abs(lat):.6f}",
        } for lat, lon in points]

    def _editor_row(self):
        code = self._type_code()
        points = self._read_point_inputs()
        return {
            "fence_id": self.fence_id_var.get().strip(), "report_type": self.report_var.get().split()[0],
            "fence_type": code, "key": self.key_var.get(), "radius": self.radius_var.get().strip(),
            "points": points, "gps": self._gps_records(points),
        }

    def add_or_update(self):
        try:
            row = self._editor_row()
            new_id = int(row["fence_id"])
            duplicate = any(int(item["fence_id"]) == new_id and index != self.edit_index
                            for index, item in enumerate(self.rows))
            if duplicate:
                raise ValueError(f"围栏ID {new_id} 已存在，请使用其他ID")
            build_40_packet(op_type="02", total_fence=1, msg_index=1, rows=[row])
        except (TypeError, ValueError) as exc:
            messagebox.showerror("围栏数据错误", str(exc), parent=self)
            return
        if self.edit_index is None:
            if len(self.rows) >= 40:
                messagebox.showwarning("数量超限", "单个页面最多添加40条围栏", parent=self); return
            self.rows.append(row)
        else:
            self.rows[self.edit_index] = row
        self.edit_index = None
        self._refresh_rows()
        self.clear_editor(prepare_next=True)
        self.status_var.set(f"当前消息已有{len(self.rows)}条围栏")

    def _refresh_rows(self):
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            label = "圆形" if row["fence_type"] == "01" else "矩形" if row["fence_type"] == "02" else f"多边形（{int(row['fence_type'])}点）"
            self.tree.insert("", "end", iid=str(index), values=(row["fence_id"], row["report_type"], label, len(row["points"])))

    def load_selected(self, _event=None):
        selected = self.tree.selection()
        if not selected: return
        self.edit_index = int(selected[0]); row = self.rows[self.edit_index]
        self.fence_id_var.set(row["fence_id"])
        self.report_var.set(next(value for value in self.REPORT_VALUES if value.startswith(row["report_type"])))
        self.type_var.set(next(value for value in self.TYPE_VALUES if value.startswith(row["fence_type"])))
        self.radius_var.set(row.get("radius", ""))
        self._type_changed()
        self._rebuild_point_inputs(len(row["points"]), row["points"])

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected: return
        for index in sorted((int(item) for item in selected), reverse=True): self.rows.pop(index)
        self.edit_index = None; self._refresh_rows(); self.clear_editor(prepare_next=True)

    def _next_free_id(self):
        used = {int(row["fence_id"]) for row in self.rows}
        return next((str(value) for value in range(1, 41) if value not in used), "")

    def clear_editor(self, prepare_next=False):
        """清空当前围栏表单；添加完成后可选择准备下一条默认输入。"""
        self.edit_index = None
        self.fence_id_var.set(self._next_free_id() if prepare_next else "")
        self.radius_var.set("")
        count = 1 if self._type_code() == "01" else 2 if self._type_code() == "02" else int(self._type_code())
        self._rebuild_point_inputs(count, [])
        if not prepare_next:
            for _lon_dir, lon_value, _lat_dir, lat_value in self.point_rows:
                lon_value.set("")
                lat_value.set("")
            self.status_var.set("当前围栏输入已清空")

    def add_delete_ids(self):
        raw_values = [value.strip() for value in self.delete_id_var.get().replace("，", ",").split(",") if value.strip()]
        if not raw_values:
            messagebox.showwarning("缺少Geo ID", "请填写至少一个待删除的围栏ID", parent=self)
            return False
        try:
            pending = []
            for raw in raw_values:
                value = int(raw)
                if not 1 <= value <= 40: raise ValueError("待删除围栏ID必须在1～40范围内")
                if value in self.delete_ids or value in pending: raise ValueError(f"围栏ID {value} 已在待删除列表中")
                pending.append(value)
        except ValueError as exc:
            messagebox.showerror("Geo ID错误", str(exc), parent=self); return False
        self.delete_ids.extend(pending)
        self.delete_id_var.set(""); self._refresh_delete_ids()
        self.status_var.set(f"待删除列表已有{len(self.delete_ids)}个Geo ID")
        return True

    def _refresh_delete_ids(self):
        self.delete_tree.delete(*self.delete_tree.get_children())
        for index, value in enumerate(self.delete_ids, 1):
            self.delete_tree.insert("", "end", iid=str(index - 1), values=(index, value))

    def remove_delete_ids(self):
        for index in sorted((int(item) for item in self.delete_tree.selection()), reverse=True):
            self.delete_ids.pop(index)
        self._refresh_delete_ids()

    def build_packet(self):
        operation = self.op_var.get().split()[0]
        try:
            if operation == "01":
                full = build_40_packet(major_minor=self.major_var.get(), op_type=operation)
                detail = "删除全部不携带其他字段。"
            elif operation == "03":
                # 允许填写ID后直接点生成，不强制用户先点“添加到待删除列表”。
                if self.delete_id_var.get().strip() and not self.add_delete_ids():
                    return
                full = build_40_packet(major_minor=self.major_var.get(), op_type=operation,
                                       total_fence=self.total_var.get(), msg_index=self.index_var.get(),
                                       delete_ids=self.delete_ids)
                detail = f"删除部分Geo ID：{','.join(map(str, self.delete_ids))}"
            else:
                if operation == "00":
                    messagebox.showwarning("Reserved操作", "00为协议Reserved值，仅用于测试，设备可能不支持。", parent=self)
                full = build_40_packet(major_minor=self.major_var.get(), op_type=operation,
                                       total_fence=self.total_var.get(), msg_index=self.index_var.get(), rows=self.rows)
                lines = []
                for index, row in enumerate(self.rows, 1):
                    single = build_40_packet(major_minor=self.major_var.get(), op_type=operation,
                                             total_fence=1, msg_index=1, rows=[row])
                    lines.append(f"第{index}行 KLV：{single[12:]}")
                detail = "\n".join(lines)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("组包失败", str(exc), parent=self); return
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", detail + "\n\n完整大包：\n" + full)
        self.full_packet_value = full
        self._set_send_payload(full)
        self.status_var.set(f"已生成Operation Type {operation}的F10F有效数据")
        self._sync_scroll_region()

    def copy_result(self):
        if not self.full_packet_value:
            messagebox.showinfo("提示", "请先生成完整大包", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(self.full_packet_value)
        self.status_var.set("完整大包数据已复制")

    def clear_output(self):
        self.output_text.delete("1.0", tk.END)
        self.full_packet_value = ""
        self._clear_send_payload()
        self.status_var.set("组包输出已清空")


class Fence808PacketPanel(_PacketSendMixin, ToolPanel):
    """JT/T 808-2013圆形、矩形、多边形围栏组包。"""

    def __init__(self, master):
        super().__init__(master, "808协议围栏组包", "", show_heading=False)
        self.action_var = tk.StringVar(value="设置")
        self.shape_var = tk.StringVar(value="圆形")
        self.operation_var = tk.StringVar(value="0 更新（清空同类后写）")
        self.terminal_var = tk.StringVar()
        self.serial_var = tk.StringVar(value="1")
        self.set_id_var = tk.StringVar(value="1")
        self.delete_id_var = tk.StringVar()
        self._last_action = self.action_var.get()
        self.radius_var = tk.StringVar()
        self.enter_var = tk.BooleanVar(value=True)
        self.leave_var = tk.BooleanVar(value=True)
        self.attribute_var = tk.StringVar()
        self.frame_value = ""
        self.map_server = MapPickerServer()

        base = self.section("JT/T 808-2013报文参数", 0)
        ttk.Label(base, text="IMSI / 12位手机号").grid(row=0, column=0, sticky="w")
        ttk.Entry(base, textvariable=self.terminal_var, width=22).grid(row=0, column=1, sticky="w", padx=(8, 22))
        ttk.Label(base, text="流水号").grid(row=0, column=2, sticky="w")
        ttk.Entry(base, textvariable=self.serial_var, width=10).grid(row=0, column=3, sticky="w", padx=(8, 22))
        ttk.Label(base, text="动作").grid(row=0, column=4, sticky="w")
        action = ttk.Combobox(base, textvariable=self.action_var, values=("设置", "删除"), state="readonly", width=9)
        action.grid(row=0, column=5, sticky="w", padx=(8, 18)); action.bind("<<ComboboxSelected>>", self._sync_form)
        ttk.Label(base, text="围栏类型").grid(row=0, column=6, sticky="w")
        shape = ttk.Combobox(
            base, textvariable=self.shape_var, values=("圆形", "矩形", "多边形"),
            state="readonly", width=9
        )
        shape.grid(row=0, column=7, sticky="w", padx=(8, 0)); shape.bind("<<ComboboxSelected>>", self._sync_form)

        self.set_frame = self.section("设置围栏", 1)
        self.set_frame.columnconfigure(1, weight=0)
        self.set_frame.columnconfigure(6, weight=1)
        self.operation_label = ttk.Label(self.set_frame, text="设置操作")
        self.operation_label.grid(row=0, column=0, sticky="w")
        self.operation_combo = ttk.Combobox(
            self.set_frame, textvariable=self.operation_var,
            values=("0 更新（清空同类后写）", "1 追加", "2 修改（按ID覆盖）"),
            state="readonly", width=25
        )
        self.operation_combo.grid(row=0, column=1, sticky="w", padx=(8, 20))
        ttk.Label(self.set_frame, text="区域ID").grid(row=0, column=2, sticky="w")
        ttk.Entry(self.set_frame, textvariable=self.set_id_var, width=13).grid(
            row=0, column=3, sticky="w", padx=(8, 20)
        )
        ttk.Checkbutton(
            self.set_frame, text="bit3 进区域报警给平台", variable=self.enter_var,
            command=self._sync_attribute, style="Clean.TCheckbutton"
        ).grid(row=0, column=4, sticky="w")
        ttk.Checkbutton(
            self.set_frame, text="bit5 出区域报警给平台", variable=self.leave_var,
            command=self._sync_attribute, style="Clean.TCheckbutton"
        ).grid(row=0, column=5, sticky="w", padx=(14, 0))
        ttk.Label(self.set_frame, textvariable=self.attribute_var, style="Hint.TLabel").grid(
            row=0, column=6, sticky="w", padx=(14, 0)
        )
        self.coord_frame = ttk.Frame(self.set_frame, style="Page.TFrame")
        self.coord_frame.grid(row=1, column=0, columnspan=7, sticky="ew", pady=(10, 0))
        self._build_coordinate_form()

        self.delete_frame = self.section("删除围栏", 1)
        ttk.Label(self.delete_frame, text="区域ID列表").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.delete_frame, textvariable=self.delete_id_var).grid(
            row=0, column=1, sticky="ew", padx=(12, 0)
        )
        ttk.Label(self.delete_frame,
                  text="多个ID用逗号或空格分隔；留空、只填0，或列表中包含0，均按删除全部同类区域处理。",
                  style="Hint.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        output = self.section("组包结果", 2)
        ttk.Button(output, text="生成808围栏报文", command=self.build_packet,
                   style="Primary.TButton").grid(row=0, column=0, sticky="w")
        ttk.Button(output, text="复制完整帧", command=self.copy_frame).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(output, text="清空输出", command=self.clear_output).grid(row=0, column=2, sticky="w")
        self.output_text = scrolledtext.ScrolledText(output, height=8, font=("Consolas", 10), wrap="word")
        self.output_text.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._configure_output_tags()
        output.columnconfigure(3, weight=1)
        self._build_send_section(3, "http://10.85.40.3:1813/client/sendRaw")
        self.add_status(4)
        self._sync_attribute()
        self._sync_form()
        self.after(350, self.poll_map_results)

    def _shape_code(self):
        return {"圆形": "circle", "矩形": "rect", "多边形": "poly"}[self.shape_var.get()]

    def _configure_output_tags(self):
        """为完整帧各协议字段配置稳定且易区分的前景色。"""
        colors = {
            "frame_flag": "#64748B",
            "message_id": "#C026D3",
            "body_property": "#2563EB",
            "terminal_id": "#0F766E",
            "serial": "#B45309",
            "operation": "#7C3AED",
            "region_count": "#DC2626",
            "region_id": "#EA580C",
            "region_property": "#059669",
            "latitude": "#0369A1",
            "longitude": "#9333EA",
            "radius": "#BE123C",
            "point_count": "#CA8A04",
            "checksum": "#E11D48",
            "extra": "#334155",
        }
        for tag, color in colors.items():
            self.output_text.tag_configure(tag, foreground=color, font=("Consolas", 10, "bold"))
        self.output_text.tag_configure("section", foreground="#12344D", font=("Microsoft YaHei UI", 10, "bold"))
        self.output_text.tag_configure("field_label", foreground="#475569", font=("Microsoft YaHei UI", 9))

    def _sync_attribute(self):
        value = (0x0008 if self.enter_var.get() else 0) | (0x0020 if self.leave_var.get() else 0)
        self.attribute_var.set(f"区域属性 = 0x{value:04X}")

    def _build_coordinate_form(self, values=None):
        for child in self.coord_frame.winfo_children(): child.destroy()
        for column in range(7):
            self.coord_frame.columnconfigure(column, weight=0)
        shape = self._shape_code(); values = values or []
        self.coordinate_vars = []
        self.polygon_text = None
        if shape == "poly":
            ttk.Label(self.coord_frame, text="多边形顶点（3～10个，每行：纬度,经度）").grid(
                row=0, column=0, sticky="w"
            )
            self.polygon_text = scrolledtext.ScrolledText(
                self.coord_frame, height=6, width=48, font=("Consolas", 10), wrap="none"
            )
            self.polygon_text.grid(row=1, column=0, sticky="ew", pady=(6, 0))
            if values:
                self.polygon_text.insert(
                    "1.0", "\n".join(f"{float(lat):.6f},{float(lon):.6f}" for lat, lon in values)
                )
            self.coord_frame.columnconfigure(0, weight=1)
            self._add_map_controls(row=1, column=1)
            return
        count = 1 if shape == "circle" else 2
        for col, title in enumerate(("", "纬度", "经度")):
            ttk.Label(self.coord_frame, text=title).grid(row=0, column=col, sticky="w", padx=(0, 12))
        for index in range(count):
            point = values[index] if index < len(values) else None
            lat = tk.StringVar(value=f"{float(point[0]):.6f}" if point is not None else "")
            lon = tk.StringVar(value=f"{float(point[1]):.6f}" if point is not None else "")
            self.coordinate_vars.append((lat,lon))
            label = "圆心" if shape == "circle" else "左上角" if index == 0 else "右下角"
            ttk.Label(self.coord_frame, text=label, width=9).grid(row=index+1,column=0,sticky="w",pady=3)
            ttk.Entry(self.coord_frame,textvariable=lat,width=18).grid(row=index+1,column=1,sticky="w",padx=(0,12),pady=3)
            ttk.Entry(self.coord_frame,textvariable=lon,width=18).grid(row=index+1,column=2,sticky="w",padx=(0,20),pady=3)
        if shape == "circle":
            ttk.Label(self.coord_frame,text="半径（米）").grid(row=1,column=3,sticky="w")
            ttk.Entry(self.coord_frame,textvariable=self.radius_var,width=14).grid(row=1,column=4,sticky="w",padx=(8,0))
        self._add_map_controls(row=1, column=5, rowspan=count)

    def _add_map_controls(self, row, column, rowspan=1):
        """把地图入口放在坐标输入区右侧，减少独占一整行造成的留白。"""
        actions = ttk.Frame(self.coord_frame, style="Page.TFrame")
        actions.grid(row=row, column=column, rowspan=rowspan, sticky="nw", padx=(22, 0))
        ttk.Button(
            actions, text="打开地图绘制并回填", command=self.open_map,
            style="Primary.TButton"
        ).pack(anchor="w")
        ttk.Label(
            actions, text="与围栏绘制使用同一张地图；按 WGS84 回填到当前 808 页面。",
            style="Hint.TLabel", wraplength=240, justify="left"
        ).pack(anchor="w", pady=(6, 0))

    def _sync_form(self, _event=None):
        action = self.action_var.get()
        if action != self._last_action:
            # 设置ID和删除ID是不同字段，切换动作时不继承另一种动作的旧输入。
            if action == "删除":
                self.delete_id_var.set("")
            else:
                self.set_id_var.set("1")
            self._last_action = action
        if action=="删除":
            self.set_frame.grid_remove(); self.delete_frame.grid()
        else:
            self.delete_frame.grid_remove(); self.set_frame.grid()
            if self._shape_code() == "poly":
                # JT/T 808-2013 的 0x8604 消息体不包含设置操作字段。
                self.operation_label.grid_remove(); self.operation_combo.grid_remove()
            else:
                self.operation_label.grid(); self.operation_combo.grid()
            self._build_coordinate_form()
        self._sync_scroll_region()

    def open_map(self):
        try:
            url=self.map_server.open_window("fence808")
        except Exception as exc:
            messagebox.showerror("地图打开失败",str(exc),parent=self); return
        self.status_var.set(f"808围栏地图已打开；若浏览器未出现，可访问：{url}")

    def poll_map_results(self):
        try:
            for payload in self.map_server.pop_results(): self.apply_map_result(payload)
        finally:
            if self.winfo_exists(): self.after(350,self.poll_map_results)

    def apply_map_result(self,payload):
        if payload.get("mode")!="fence808": return
        fences=payload.get("fences") or []
        wanted=self._shape_code()
        shape_aliases = {"circle": "circle", "rect": "rect", "rectangle": "rect",
                         "poly": "poly", "polygon": "poly"}
        supported = [item for item in fences if shape_aliases.get(item.get("shape"))]
        selected=next(
            (item for item in reversed(supported) if shape_aliases.get(item.get("shape"))==wanted),
            None,
        )
        if selected is None and supported:
            # 地图与围栏绘制页面相同，允许选择任意图形；若用户画的不是当前下拉框
            # 类型，则自动切换到最后绘制的类型后回填。
            selected = supported[-1]
            wanted = shape_aliases[selected.get("shape")]
            self.shape_var.set({"circle": "圆形", "rect": "矩形", "poly": "多边形"}[wanted])
            self._sync_form()
        if not selected:
            self.status_var.set("地图未返回当前类型的808围栏"); return
        points=selected.get("points") or []
        if wanted == "poly":
            if not 3 <= len(points) <= 10:
                messagebox.showerror(
                    "地图回填失败", f"808多边形围栏需要3～10个顶点，地图返回了{len(points)}个",
                    parent=self
                ); return
            values=[(float(p[0]),float(p[1])) for p in points]
        else:
            expected=1 if wanted=="circle" else 2
            if len(points)<expected:
                messagebox.showerror("地图回填失败","地图返回的坐标点数量不足",parent=self); return
            values=[(float(p[0]),float(p[1])) for p in points[:expected]]
        if wanted == "rect":
            latitudes = [point[0] for point in values]
            longitudes = [point[1] for point in values]
            # 808 矩形区域的协议顺序固定为左上角、右下角。
            values = [
                (max(latitudes), min(longitudes)),
                (min(latitudes), max(longitudes)),
            ]
        self._build_coordinate_form(values)
        if wanted=="circle": self.radius_var.set(str(int(round(float(selected.get("radius") or 0)))))
        shape_label = {"circle": "圆形", "rect": "矩形", "poly": "多边形"}[wanted]
        self.status_var.set(f"808{shape_label}围栏已从地图回填")

    def _manual_points(self):
        if self._shape_code() == "poly":
            points = []
            for line_number, line in enumerate(self.polygon_text.get("1.0", tk.END).splitlines(), 1):
                text = line.strip()
                if not text:
                    continue
                parts = [part.strip() for part in text.replace("，", ",").split(",")]
                if len(parts) != 2:
                    raise ValueError(f"多边形第{line_number}行应为“纬度,经度”")
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                except ValueError as exc:
                    raise ValueError(f"多边形第{line_number}行经纬度必须是有效数字") from exc
                if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    raise ValueError(f"多边形第{line_number}行经纬度超出范围")
                points.append((lat, lon))
            if not 3 <= len(points) <= 10:
                raise ValueError(f"多边形围栏需要3～10个顶点，当前{len(points)}个")
            return points
        result=[]
        for index,(lat_var,lon_var) in enumerate(self.coordinate_vars,1):
            try: lat,lon=float(lat_var.get().strip()),float(lon_var.get().strip())
            except ValueError as exc: raise ValueError(f"第{index}组经纬度必须是有效数字") from exc
            if not -90<=lat<=90 or not -180<=lon<=180: raise ValueError(f"第{index}组经纬度超出范围")
            result.append((lat,lon))
        return result

    @staticmethod
    def _delete_ids(text):
        raw=[value for value in re.split(r"[,，\s]+",str(text or "").strip()) if value]
        if not raw or "0" in raw: return []
        values=[]
        for value in raw:
            number=int(value)
            if not 1<=number<=0xFFFFFFFF: raise ValueError("删除区域ID应为1～4294967295；0表示删除全部")
            values.append(number)
        return values

    @staticmethod
    def _escape_808_field(data):
        """按808规则转义一个逻辑字段，确保转义后的两个字节仍保持字段颜色。"""
        escaped = bytearray()
        for value in data:
            if value == 0x7E:
                escaped.extend((0x7D, 0x02))
            elif value == 0x7D:
                escaped.extend((0x7D, 0x01))
            else:
                escaped.append(value)
        return bytes(escaped)

    @staticmethod
    def _body_field_segments(message_id, body):
        """按0x8600～0x8605格式拆分消息体，用于结果着色和字段说明。"""
        segments = []
        offset = 0

        def take(length, label, tag):
            nonlocal offset
            data = body[offset:offset + length]
            offset += len(data)
            if data:
                segments.append((label, data, tag))
            return data

        if message_id in {"8601", "8603", "8605"}:
            count_data = take(1, "区域数量", "region_count")
            count = count_data[0] if count_data else 0
            for index in range(count):
                take(4, f"区域ID {index + 1}", "region_id")
        elif message_id == "8600":
            take(1, "设置操作", "operation")
            take(1, "区域总数", "region_count")
            take(4, "区域ID", "region_id")
            take(2, "区域属性", "region_property")
            take(4, "圆心纬度", "latitude")
            take(4, "圆心经度", "longitude")
            take(4, "半径", "radius")
        elif message_id == "8602":
            take(1, "设置操作", "operation")
            take(1, "区域总数", "region_count")
            take(4, "区域ID", "region_id")
            take(2, "区域属性", "region_property")
            take(4, "左上角纬度", "latitude")
            take(4, "左上角经度", "longitude")
            take(4, "右下角纬度", "latitude")
            take(4, "右下角经度", "longitude")
        elif message_id == "8604":
            take(4, "区域ID", "region_id")
            take(2, "区域属性", "region_property")
            count_data = take(2, "顶点数量", "point_count")
            count = int.from_bytes(count_data, "big") if count_data else 0
            for index in range(count):
                take(4, f"顶点{index + 1}纬度", "latitude")
                take(4, f"顶点{index + 1}经度", "longitude")
        if offset < len(body):
            take(len(body) - offset, "扩展字段", "extra")
        return segments

    def _render_colored_frame(self, message_id, body_hex, terminal_id, serial):
        """显示转义后的完整帧，并保持每个逻辑字段的独立颜色。"""
        body = bytes.fromhex(body_hex)
        digits = re.sub(r"\D", "", str(terminal_id or ""))
        if len(digits) == 15:
            digits = digits[-12:]
        terminal = bytes(int(digits[index:index + 2], 16) for index in range(0, 12, 2))
        header_segments = [
            ("消息ID", int(message_id, 16).to_bytes(2, "big"), "message_id"),
            ("消息体属性", len(body).to_bytes(2, "big"), "body_property"),
            ("终端标识", terminal, "terminal_id"),
            ("消息流水号", int(serial).to_bytes(2, "big"), "serial"),
        ]
        body_segments = self._body_field_segments(message_id, body)
        raw = b"".join(data for _label, data, _tag in header_segments + body_segments)
        checksum = 0
        for value in raw:
            checksum ^= value
        segments = (
            [("帧起始", b"\x7E", "frame_flag")]
            + header_segments
            + body_segments
            + [("校验码", bytes([checksum]), "checksum"), ("帧结束", b"\x7E", "frame_flag")]
        )

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, "消息体：", "section")
        for index, (label, data, tag) in enumerate(body_segments):
            if index:
                self.output_text.insert(tk.END, " ")
            self.output_text.insert(tk.END, data.hex().upper(), tag)
        self.output_text.insert(tk.END, "\n\n完整帧（转义后）：\n", "section")
        for index, (_label, data, tag) in enumerate(segments):
            if index:
                self.output_text.insert(tk.END, " ")
            shown = data if tag == "frame_flag" else self._escape_808_field(data)
            self.output_text.insert(tk.END, shown.hex().upper(), tag)

        self.output_text.insert(tk.END, "\n\n字段说明：\n", "section")
        for label, data, tag in segments:
            shown = data if tag == "frame_flag" else self._escape_808_field(data)
            self.output_text.insert(tk.END, f"{label}：", "field_label")
            self.output_text.insert(tk.END, shown.hex().upper(), tag)
            if data != shown:
                self.output_text.insert(tk.END, f"（原始 {data.hex().upper()}）", "field_label")
            self.output_text.insert(tk.END, "\n")

    def build_packet(self):
        try:
            shape=self._shape_code()
            if self.action_var.get()=="删除":
                message_id,body=build_808_delete_body(
                    shape=shape, fence_ids=self._delete_ids(self.delete_id_var.get())
                )
            else:
                message_id,body=build_808_body(
                    shape=shape,operation=self.operation_var.get().split()[0],fence_id=self.set_id_var.get(),
                    points=self._manual_points(),radius=self.radius_var.get(),enter_alarm=self.enter_var.get(),
                    leave_alarm=self.leave_var.get(),
                )
            frame=build_808_frame(message_id,body,self.terminal_var.get(),self.serial_var.get())
        except (TypeError,ValueError) as exc:
            messagebox.showerror("组包失败",str(exc),parent=self); return
        self.frame_value=frame
        self._render_colored_frame(message_id, body, self.terminal_var.get(), self.serial_var.get())
        terminal_digits = re.sub(r"\D", "", self.terminal_var.get())
        send_imei = terminal_digits[-12:] if len(terminal_digits) == 15 else terminal_digits
        self._set_send_payload(frame, imei=send_imei)
        self.status_var.set(f"已生成0x{message_id}围栏报文")
        self._sync_scroll_region()

    def copy_frame(self):
        if not self.frame_value:
            messagebox.showinfo("提示","请先生成808围栏报文",parent=self); return
        self.clipboard_clear(); self.clipboard_append(self.frame_value); self.status_var.set("808完整帧已复制")

    def clear_output(self):
        self.output_text.delete("1.0",tk.END); self.frame_value=""
        self._clear_send_payload(clear_imei=True)
        self.status_var.set("组包输出已清空")


class ElectronicFencePanel(ttk.Frame):
    """电子围栏一级菜单，下面承载三个互相独立的子功能。"""

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # 使用轻量文字导航，避免二级菜单与顶部一级菜单争抢视觉权重。
        _nav, self.nav_buttons, self.nav_indicators = _make_secondary_nav(
            self,
            (("draw", "围栏绘制"), ("40", "4.0 协议围栏组包"), ("808", "808 协议围栏组包")),
            self.show_page,
        )

        content = ttk.Frame(self, style="Page.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.pages = {
            "draw": FenceKmlPanel(content),
            "40": Fence40PacketPanel(content),
            "808": Fence808PacketPanel(content),
        }
        for key, page in self.pages.items():
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page("draw")

    def show_page(self, key):
        """切换二级功能，并统一更新选中/未选中的导航样式。"""
        self.pages[key].tkraise()
        _select_secondary_nav(self.nav_buttons, self.nav_indicators, key)

class MapPointPanel(ToolPanel):
    """独立的地图经纬度标记页面。"""

    def __init__(self, master):
        super().__init__(master, "地图经纬度标记", "在地图上连续选点，查看 WGS84 经纬度并导出点位 KML。")
        self.name_var = tk.StringVar(value="地图标注点")
        self.map_markers = []
        self.map_server = MapPickerServer()

        open_frame = self.section("地图选点", 0)
        ttk.Button(open_frame, text="打开地图标记经纬度", command=self.open_map, style="Primary.TButton").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(
            open_frame,
            text="在地图上单击即可连续添加点；每个标记显示对应的 WGS84 纬度和经度。",
            wraplength=620,
        ).grid(row=0, column=1, sticky="w")

        list_frame = ttk.LabelFrame(self.body, text="经纬度点列表", padding=10, style="Section.TLabelframe")
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.body.rowconfigure(1, weight=1)
        self.marker_text = scrolledtext.ScrolledText(list_frame, height=15, font=("Consolas", 10), wrap="none")
        self.marker_text.grid(row=0, column=0, sticky="nsew")
        self.marker_text.insert("1.0", "尚未选择经纬度点")
        self.marker_text.configure(state="disabled")

        output_frame = self.section("导出点位", 2)
        ttk.Label(output_frame, text="名称").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(output_frame, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=(0, 12))
        ttk.Button(output_frame, text="导出标注点 KML", command=self.export_markers, style="Primary.TButton").grid(
            row=0, column=2, padx=(0, 8)
        )
        ttk.Button(output_frame, text="清空点列表", command=self.clear_markers).grid(row=0, column=3)
        self.add_status(3)
        self.after(350, self.poll_map_results)

    def open_map(self):
        try:
            url = self.map_server.open_window("point")
        except Exception as exc:
            messagebox.showerror("地图打开失败", str(exc), parent=self)
            return
        self.status_var.set(f"经纬度标记地图已打开；若浏览器未出现，可访问：{url}")

    def poll_map_results(self):
        try:
            for payload in self.map_server.pop_results():
                self.apply_map_result(payload)
        finally:
            if self.winfo_exists():
                self.after(350, self.poll_map_results)

    def apply_map_result(self, payload):
        markers = []
        for marker in payload.get("markers", []):
            try:
                markers.append(parse_coordinate(marker["lat"], marker["lon"]))
            except (KeyError, TypeError, ValueError):
                continue
        self.map_markers = markers
        self.render_markers()
        self.status_var.set(f"地图已回填：{len(markers)} 个经纬度点")

    def render_markers(self):
        self.marker_text.configure(state="normal")
        self.marker_text.delete("1.0", tk.END)
        if self.map_markers:
            self.marker_text.insert(
                "1.0",
                "\n".join(
                    f"点 {index:02d}    纬度 {point.latitude:.6f}    经度 {point.longitude:.6f}"
                    f"    纬度,经度 {point.latitude:.6f},{point.longitude:.6f}"
                    for index, point in enumerate(self.map_markers, start=1)
                ),
            )
        else:
            self.marker_text.insert("1.0", "尚未选择经纬度点")
        self.marker_text.configure(state="disabled")

    def clear_markers(self):
        self.map_markers = []
        self.render_markers()
        self.status_var.set("经纬度点列表已清空")

    def export_markers(self):
        if not self.map_markers:
            messagebox.showwarning("没有标注点", "请先打开地图并标注经纬度点，然后回填", parent=self)
            return
        name = self.name_var.get().strip() or "地图标注点"
        path = filedialog.asksaveasfilename(
            parent=self, title="保存标注点 KML", defaultextension=".kml",
            initialfile=f"{name}.kml", filetypes=(("KML 文件", "*.kml"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            saved = write_point_kml(self.map_markers, name, path)
        except OSError as exc:
            messagebox.showerror("生成失败", str(exc), parent=self)
            return
        self.status_var.set(f"标注点 KML 已生成：{saved}")
        messagebox.showinfo("生成成功", f"标注点 KML 已生成：\n{saved}", parent=self)


class TrackViewerPanel(ToolPanel):
    """在在线底图上导入并查看本地 KML 轨迹。"""

    def __init__(self, master):
        super().__init__(master, "轨迹查看", "打开地图并导入本机 KML，查看轨迹线、点位和多边形。")
        self.map_server = MapPickerServer()

        open_frame = self.section("KML 轨迹地图", 0)
        ttk.Button(open_frame, text="打开轨迹查看地图", command=self.open_map, style="Primary.TButton").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(
            open_frame,
            text="地图打开后点击“导入 KML”；可同时选择多个文件，文件只在本机浏览器中读取。",
            wraplength=650,
        ).grid(row=0, column=1, sticky="w")

        info_frame = self.section("支持内容", 1)
        ttk.Label(
            info_frame,
            text="支持 KML 中的 LineString、Point、Polygon 和 gx:Track；KML 坐标按 WGS84 读取并匹配高德底图显示。",
            wraplength=780,
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        self.add_status(2)

    def open_map(self):
        try:
            url = self.map_server.open_window("track")
        except Exception as exc:
            messagebox.showerror("地图打开失败", str(exc), parent=self)
            return
        self.status_var.set(f"轨迹查看地图已打开；若浏览器未出现，可访问：{url}")

