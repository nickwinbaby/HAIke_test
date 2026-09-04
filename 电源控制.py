import csv
import json
import math
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, ttk

import serial
import serial.tools.list_ports


def resource_path(filename):
    """Return a path that works both in source mode and PyInstaller one-file mode."""
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / filename


def writable_app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class SerialWorker(threading.Thread):
    def __init__(self, tasks, events):
        super().__init__(daemon=True)
        self.tasks = tasks
        self.events = events
        self.ser = None
        self.running = True
        self.last_write_time = 0.0
        self.min_interval = 0.08

    def run(self):
        while self.running:
            try:
                task = self.tasks.get(timeout=0.1)
            except queue.Empty:
                continue

            action = task[0]
            try:
                if action == "open":
                    _, port, baud = task
                    self.open_port(port, baud)
                elif action == "close":
                    self.close_port()
                    self.events.put(("disconnected", "已断开"))
                elif action == "write":
                    _, frame = task
                    self.write_frame(frame)
                elif action == "query":
                    _, frame, kind = task
                    self.query_frame(frame, kind)
                elif action == "stop":
                    self.running = False
                    self.close_port()
            except Exception as exc:
                self.events.put(("error", str(exc)))
                self.close_port()
                self.events.put(("disconnected", "串口异常，已自动断开"))

    def open_port(self, port, baud):
        self.close_port()
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.3,
            write_timeout=0.3,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        time.sleep(0.2)
        self.events.put(("connected", f"已连接 {port} @ {baud}, 8N1"))

    def close_port(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def _respect_interval(self):
        elapsed = time.monotonic() - self.last_write_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _send_and_read(self, frame, log=True):
        if not (self.ser and self.ser.is_open):
            return None

        self._respect_interval()
        payload = frame.encode("ascii")
        self.ser.write(payload)
        self.ser.flush()
        self.last_write_time = time.monotonic()
        if log:
            self.events.put(("log", f"TX: {frame}    HEX: {payload.hex(' ')}"))

        data = self.ser.read(13)
        if data:
            text = data.decode("ascii", errors="replace")
            if log:
                self.events.put(("log", f"RX: {text!r}    HEX: {data.hex(' ')}"))
            return text

        if log:
            self.events.put(("log", "RX: 超时无回复"))
        return None

    def write_frame(self, frame):
        if not (self.ser and self.ser.is_open):
            self.events.put(("error", "串口未连接"))
            return
        self._send_and_read(frame, log=True)

    def query_frame(self, frame, kind):
        if not (self.ser and self.ser.is_open):
            return
        text = self._send_and_read(frame, log=False)
        if text:
            self.events.put(("query_result", kind, text))


class PowerSupplyGUI:
    LINK_FRAME = "<09100000000>"
    UNLINK_FRAME = "<09200000000>"
    OUTPUT_ON_FRAME = "<07000000000>"
    OUTPUT_OFF_FRAME = "<08000000000>"
    VOLT_QUERY_FRAME = "<02012200000>"
    CURR_QUERY_FRAME = "<04003300000>"

    RAW_PRESETS = {
        "连接 Link": LINK_FRAME,
        "断开 Unlink": UNLINK_FRAME,
        "输出 ON": OUTPUT_ON_FRAME,
        "输出 OFF": OUTPUT_OFF_FRAME,
        "读电压": VOLT_QUERY_FRAME,
        "读电流": CURR_QUERY_FRAME,
        "设置 12.00V": "<01012000000>",
        "设置 2.000A": "<03002000000>",
    }

    def __init__(self, root):
        self.root = root
        self.root.title("KUAIQU / NICE-POWER SPPS-D305-232 电源控制 - Mangetic - 2026-8-31")
        self.base_geometry = "700x760"
        self.chart_geometry = "540x760"
        self.root.geometry(self.base_geometry)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.set_window_icon()

        self.config_path = writable_app_dir() / "power_config.json"
        self.chart_data_dir = writable_app_dir() / "current_curve_logs"
        self.volt_min = 0.00
        self.volt_max = 30.00
        self.amp_min = 0.00
        self.amp_max = 5.000
        self.volt_step = 0.01
        self.amp_step = 0.001
        self.default_volt = 12.00
        self.default_amp = 2.000
        self.saved_volt, self.saved_amp = self.load_config()

        self.connected = False
        self.is_output_on = False
        self.live_enabled = tk.BooleanVar(value=False)
        self.chart_panel_visible = False
        self.chart_enabled = tk.BooleanVar(value=False)
        self.chart_frozen = tk.BooleanVar(value=False)
        self.chart_range_value = tk.DoubleVar(value=5.0)
        self.chart_range_unit = tk.StringVar(value="分钟")
        self.chart_y_step = tk.DoubleVar(value=self.load_chart_y_step())
        chart_line_style, chart_line_color = self.load_chart_options()
        self.chart_line_style = tk.StringVar(value=chart_line_style)
        self.chart_line_color = chart_line_color
        self.live_poll_ms = 100
        self.next_live_query = "voltage"
        self.max_current_value = 0.0
        self.max_power_value = 0.0
        self.current_points = []
        self.chart_epoch_offset = time.time() - time.monotonic()
        self.current_chart_max_points = 108000
        self.chart_y_min = -0.2
        self.chart_y_max = 0.5
        self.chart_x_scroll_var = tk.DoubleVar(value=1000.0)
        self.chart_x_scroll_syncing = False
        self.chart_y_scroll_var = tk.DoubleVar(value=500.0)
        self.chart_y_scroll_syncing = False
        self.chart_y_manual = False
        self.chart_manual_anchor = None
        self.chart_window = None
        self.chart_panel = None
        self.current_chart = None
        self.chart_csv_file = None
        self.chart_csv_writer = None
        self.chart_csv_path = None
        self.chart_recording_start = None
        self.chart_sample_index = 0
        self.chart_static_anchor = None
        self.chart_freeze_anchor = None
        self.highlighted_y_values = set()
        self.chart_cursor_point = None
        self.chart_current_var = tk.StringVar(value="当前电流 0.000 A")
        self.chart_max_var = tk.StringVar(value="MAX 0.000 A")

        self.tasks = queue.Queue()
        self.events = queue.Queue()
        self.worker = SerialWorker(self.tasks, self.events)
        self.worker.start()

        self.build_ui()
        self.refresh_ports()
        self.drain_events()
        self.schedule_live_poll()

    def set_window_icon(self):
        ico_path = resource_path("kuaiqupower.ico")
        png_path = resource_path("kuaiqupower.png")
        try:
            if ico_path.exists():
                self.root.iconbitmap(str(ico_path))
            elif png_path.exists():
                self.icon_photo = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self.icon_photo)
        except Exception:
            pass

    def load_config(self):
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            volt = float(data.get("voltage", self.default_volt))
            amp = float(data.get("current", self.default_amp))
        except Exception:
            volt = self.default_volt
            amp = self.default_amp

        volt = max(self.volt_min, min(self.volt_max, volt))
        amp = max(self.amp_min, min(self.amp_max, amp))
        return volt, amp

    def save_config(self):
        try:
            voltage = float(self.volt_var.get())
        except (AttributeError, tk.TclError, ValueError):
            voltage = getattr(self, "saved_volt", self.default_volt)

        try:
            current = float(self.amp_var.get())
        except (AttributeError, tk.TclError, ValueError):
            current = getattr(self, "saved_amp", self.default_amp)

        voltage = max(self.volt_min, min(self.volt_max, voltage))
        current = max(self.amp_min, min(self.amp_max, current))
        data = {
            "voltage": round(voltage, 2),
            "current": round(current, 3),
        }
        if hasattr(self, "chart_y_step"):
            try:
                data["chart_y_step"] = round(float(self.chart_y_step.get()), 3)
            except (tk.TclError, ValueError):
                data["chart_y_step"] = 0.1
        if hasattr(self, "chart_line_style"):
            style = self.chart_line_style.get()
            data["chart_line_style"] = style if style in ("平滑", "折线") else "平滑"
        if hasattr(self, "chart_line_color"):
            data["chart_line_color"] = self.chart_line_color if self.is_valid_hex_color(self.chart_line_color) else "#198754"
        try:
            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.log(f"保存配置失败: {exc}")

    def load_chart_y_step(self):
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            step = float(data.get("chart_y_step", 0.1))
        except Exception:
            step = 0.1
        return max(0.001, min(5.0, step))

    def load_chart_options(self):
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            style = data.get("chart_line_style", "平滑")
            color = data.get("chart_line_color", "#198754")
        except Exception:
            style = "平滑"
            color = "#198754"

        if style not in ("平滑", "折线"):
            style = "平滑"
        if not self.is_valid_hex_color(color):
            color = "#198754"
        return style, color

    def is_valid_hex_color(self, color):
        if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
            return False
        try:
            int(color[1:], 16)
        except ValueError:
            return False
        return True

    def build_ui(self):
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        main = ttk.Frame(container)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        port_frame = ttk.LabelFrame(main, text="串口连接", padding=10)
        port_frame.pack(fill=tk.X, pady=(0, 8))
        port_frame.columnconfigure(1, weight=1)

        ttk.Label(port_frame, text="端口:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(port_frame, textvariable=self.port_var, width=16, state="readonly")
        self.port_cb.grid(row=0, column=1, padx=(8, 12), sticky="ew")
        ttk.Button(port_frame, text="刷新", command=self.refresh_ports).grid(row=0, column=2, padx=(0, 12))

        ttk.Label(port_frame, text="波特率:").grid(row=0, column=3, sticky="w")
        self.baud_var = tk.StringVar(value="9600")
        ttk.Combobox(port_frame, textvariable=self.baud_var, width=10, values=["9600"], state="readonly").grid(
            row=0, column=4, padx=(8, 0)
        )

        self.conn_btn = ttk.Button(port_frame, text="连接", command=self.toggle_connection)
        self.conn_btn.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0), padx=(0, 8))
        self.chart_panel_btn = ttk.Button(port_frame, text="打开曲线窗口", command=self.toggle_chart_panel)
        self.chart_panel_btn.grid(row=1, column=4, sticky="ew", pady=(8, 0))

        set_frame = ttk.LabelFrame(main, text="电压 / 电流", padding=10)
        set_frame.pack(fill=tk.X, pady=(0, 8))
        set_frame.columnconfigure(5, weight=1)

        ttk.Label(set_frame, text="电压 V:").grid(row=0, column=0, sticky="w")
        self.volt_var = tk.StringVar(value=f"{self.saved_volt:.2f}")
        ttk.Entry(set_frame, textvariable=self.volt_var, width=12, font=("Arial", 12)).grid(row=0, column=1, padx=(8, 12))
        ttk.Button(set_frame, text="-", width=3, command=self.volt_minus).grid(row=0, column=2)
        ttk.Button(set_frame, text="+", width=3, command=self.volt_plus).grid(row=0, column=3, padx=(6, 16))
        ttk.Button(set_frame, text="下发电压", command=self.apply_voltage).grid(row=0, column=4, sticky="ew")

        ttk.Label(set_frame, text="电流 A:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.amp_var = tk.StringVar(value=f"{self.saved_amp:.3f}")
        ttk.Entry(set_frame, textvariable=self.amp_var, width=12, font=("Arial", 12)).grid(row=1, column=1, padx=(8, 12), pady=(8, 0))
        ttk.Button(set_frame, text="-", width=3, command=self.amp_minus).grid(row=1, column=2, pady=(8, 0))
        ttk.Button(set_frame, text="+", width=3, command=self.amp_plus).grid(row=1, column=3, padx=(6, 16), pady=(8, 0))
        ttk.Button(set_frame, text="下发电流", command=self.apply_current).grid(row=1, column=4, sticky="ew", pady=(8, 0))

        ttk.Button(set_frame, text="下发设置", command=self.apply_setpoints).grid(
            row=2, column=0, columnspan=5, sticky="ew", pady=(10, 0)
        )

        live_frame = tk.Frame(
            set_frame,
            bg="white",
            bd=2,
            relief="solid",
            highlightthickness=2,
            highlightbackground="#d9534f",
        )
        live_frame.grid(row=0, column=5, rowspan=3, padx=(12, 0), sticky="nsew")
        live_frame.columnconfigure(1, weight=1)

        tk.Label(live_frame, text="实时数据", bg="white", fg="#d9534f", font=("Arial", 12, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(6, 2)
        )
        tk.Checkbutton(
            live_frame,
            text="开启",
            variable=self.live_enabled,
            command=self.reset_live_max,
            bg="white",
            activebackground="white",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10)

        self.read_volt_var = tk.StringVar(value="0.00")
        self.read_amp_var = tk.StringVar(value="0.000")
        self.read_power_var = tk.StringVar(value="0.000")
        self.max_amp_var = tk.StringVar(value="0.000 A")
        self.max_power_var = tk.StringVar(value="0.000 W")
        self.add_live_row(live_frame, 2, "电压 V:", self.read_volt_var, "#d00000", 18)
        self.add_live_row(live_frame, 3, "电流 A:", self.read_amp_var, "#198754", 18)
        self.add_live_row(live_frame, 4, "功率 W:", self.read_power_var, "#6f42c1", 18)
        self.add_live_row(live_frame, 5, "电流MAX:", self.max_amp_var, "#198754", 12)
        self.add_live_row(live_frame, 6, "功率MAX:", self.max_power_var, "#6f42c1", 12)

        output_frame = ttk.LabelFrame(main, text="输出控制", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 8))
        self.output_btn = tk.Button(
            output_frame,
            text="输出 OFF",
            bg="#cccccc",
            fg="black",
            font=("Arial", 18, "bold"),
            height=2,
            command=self.toggle_output,
        )
        self.output_btn.pack(fill=tk.X)

        raw_frame = ttk.LabelFrame(main, text="原始帧测试", padding=10)
        raw_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(raw_frame, text="常用帧:").pack(side=tk.LEFT)
        self.raw_preset_var = tk.StringVar(value="连接 Link")
        raw_preset_cb = ttk.Combobox(
            raw_frame,
            textvariable=self.raw_preset_var,
            values=list(self.RAW_PRESETS.keys()),
            width=14,
            state="readonly",
        )
        raw_preset_cb.pack(side=tk.LEFT, padx=(6, 8))
        raw_preset_cb.bind("<<ComboboxSelected>>", self.apply_raw_preset)

        ttk.Label(raw_frame, text="原始帧:").pack(side=tk.LEFT)
        self.raw_var = tk.StringVar(value=self.LINK_FRAME)
        ttk.Entry(raw_frame, textvariable=self.raw_var, font=("Consolas", 11)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))
        ttk.Button(raw_frame, text="发送原始帧", command=self.send_raw).pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(main, text="通信日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=8, state="disabled", wrap="none", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def build_chart_panel(self):
        self.chart_window = tk.Toplevel(self.root)
        self.chart_window.title("实时电流曲线")
        self.chart_window.geometry(self.chart_geometry)
        self.chart_window.minsize(420, 360)
        self.chart_window.resizable(True, True)
        self.chart_window.protocol("WM_DELETE_WINDOW", self.close_chart_panel)

        try:
            ico_path = resource_path("kuaiqupower.ico")
            if ico_path.exists():
                self.chart_window.iconbitmap(str(ico_path))
        except Exception:
            pass

        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() + 8
        y = self.root.winfo_y()
        self.chart_window.geometry(f"{self.chart_geometry}+{x}+{y}")

        self.chart_panel = ttk.LabelFrame(self.chart_window, text="实时电流曲线", padding=10)
        self.chart_panel.pack(fill=tk.BOTH, expand=True)
        self.chart_panel.columnconfigure(0, weight=1)
        self.chart_panel.columnconfigure(1, weight=0)
        self.chart_panel.rowconfigure(2, weight=1)

        top_bar = ttk.Frame(self.chart_panel)
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        top_bar.columnconfigure(7, weight=1)

        ttk.Checkbutton(
            top_bar,
            text="开启曲线采集",
            variable=self.chart_enabled,
            command=self.toggle_chart_recording,
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(top_bar, text="显示最近").grid(row=0, column=1, padx=(14, 4))
        range_spin = tk.Spinbox(
            top_bar,
            from_=0.1,
            to=365,
            increment=0.05,
            width=6,
            format="%.2f",
            textvariable=self.chart_range_value,
            command=self.draw_current_chart,
        )
        range_spin.grid(row=0, column=2, sticky="w")
        range_spin.bind("<KeyRelease>", lambda _event: self.draw_current_chart())
        range_spin.bind("<FocusOut>", lambda _event: self.draw_current_chart())
        unit_cb = ttk.Combobox(
            top_bar,
            textvariable=self.chart_range_unit,
            values=["分钟", "小时", "天"],
            width=6,
            state="readonly",
        )
        unit_cb.grid(row=0, column=3, padx=(4, 8), sticky="w")
        unit_cb.bind("<<ComboboxSelected>>", lambda _event: self.draw_current_chart())

        ttk.Label(top_bar, text="Y格距(A)").grid(row=0, column=4, padx=(8, 4), sticky="e")
        y_step_spin = tk.Spinbox(
            top_bar,
            from_=0.001,
            to=5.0,
            increment=0.001,
            width=7,
            format="%.3f",
            textvariable=self.chart_y_step,
            command=self.draw_current_chart,
        )
        y_step_spin.grid(row=0, column=5, sticky="w")
        y_step_spin.bind("<KeyRelease>", lambda _event: self.draw_current_chart())
        y_step_spin.bind("<FocusOut>", lambda _event: self.draw_current_chart())

        button_bar = ttk.Frame(self.chart_panel)
        button_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        button_bar.columnconfigure(5, weight=1)
        ttk.Button(button_bar, text="导入曲线", command=self.import_current_chart_file).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(button_bar, text="清空曲线", command=self.clear_current_chart).grid(row=0, column=1, padx=(0, 6))
        self.chart_freeze_btn = tk.Button(
            button_bar,
            text="冻结窗口",
            width=10,
            command=self.toggle_chart_freeze,
            relief=tk.RAISED,
            bg="#f8f9fa",
            fg="#212529",
            activebackground="#e9ecef",
            activeforeground="#212529",
        )
        self.chart_freeze_btn.grid(row=0, column=2, padx=(0, 6))
        ttk.Button(button_bar, text="清除标识", command=self.clear_chart_markers).grid(row=0, column=3, padx=(0, 6))
        ttk.Button(button_bar, text="关闭窗口", command=self.toggle_chart_panel).grid(row=0, column=4)

        ttk.Label(button_bar, text="曲线").grid(row=0, column=6, sticky="e", padx=(12, 4))
        style_cb = ttk.Combobox(
            button_bar,
            textvariable=self.chart_line_style,
            values=["平滑", "折线"],
            width=7,
            state="readonly",
        )
        style_cb.grid(row=0, column=7, sticky="e")
        style_cb.bind("<<ComboboxSelected>>", self.on_chart_style_change)
        ttk.Label(button_bar, text="颜色").grid(row=0, column=8, sticky="e", padx=(10, 4))
        self.chart_color_btn = tk.Button(
            button_bar,
            text="",
            width=3,
            height=1,
            command=self.choose_chart_line_color,
            bg=self.chart_line_color,
            activebackground=self.chart_line_color,
            relief=tk.RAISED,
            bd=1,
        )
        self.chart_color_btn.grid(row=0, column=9, sticky="e")

        self.chart_status_var = tk.StringVar(value="曲线区滚轮缩放时间，Y轴刻度区滚轮缩放电流轴，点击绘图区读电流")
        self.chart_summary_var = tk.StringVar(value="显示最近 5 分钟，可见 0 点 / 缓存 0 点 / 采集 0 点")

        self.current_chart = tk.Canvas(
            self.chart_panel,
            width=430,
            height=610,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#b8c2cc",
        )
        self.current_chart.grid(row=2, column=0, sticky="nsew", pady=(8, 8))
        self.current_chart.bind("<Configure>", lambda _event: self.draw_current_chart())
        self.current_chart.bind("<MouseWheel>", self.on_chart_mouse_wheel)
        self.current_chart.bind("<Button-4>", self.on_chart_mouse_wheel)
        self.current_chart.bind("<Button-5>", self.on_chart_mouse_wheel)
        self.current_chart.bind("<Button-1>", self.on_chart_click)

        y_scroll_bar = ttk.Frame(self.chart_panel)
        y_scroll_bar.grid(row=2, column=1, sticky="ns", padx=(8, 0), pady=(8, 8))
        ttk.Label(y_scroll_bar, text="Y轴").pack(anchor="center", pady=(0, 6))
        self.chart_y_scale = ttk.Scale(
            y_scroll_bar,
            from_=1000,
            to=0,
            orient=tk.VERTICAL,
            variable=self.chart_y_scroll_var,
            command=self.on_chart_y_scroll,
        )
        self.chart_y_scale.pack(fill=tk.Y, expand=True)

        x_scroll_bar = ttk.Frame(self.chart_panel)
        x_scroll_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        x_scroll_bar.columnconfigure(1, weight=1)
        ttk.Label(x_scroll_bar, text="X轴位置").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.chart_x_scale = ttk.Scale(
            x_scroll_bar,
            from_=0,
            to=1000,
            orient=tk.HORIZONTAL,
            variable=self.chart_x_scroll_var,
            command=self.on_chart_x_scroll,
        )
        self.chart_x_scale.grid(row=0, column=1, sticky="ew")
        ttk.Button(x_scroll_bar, text="最新", width=6, command=self.follow_latest_chart).grid(
            row=0, column=2, sticky="e", padx=(8, 0)
        )

        bottom_bar = ttk.Frame(self.chart_panel)
        bottom_bar.grid(row=4, column=0, columnspan=2, sticky="ew")
        bottom_bar.columnconfigure(0, weight=1)

        bottom_text = ttk.Frame(bottom_bar)
        bottom_text.grid(row=0, column=0, sticky="w")
        ttk.Label(bottom_text, textvariable=self.chart_status_var, foreground="#198754").pack(anchor="w")
        ttk.Label(bottom_text, textvariable=self.chart_summary_var, foreground="#4a5568").pack(anchor="w")

        readout_frame = ttk.Frame(bottom_bar)
        readout_frame.grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            readout_frame,
            textvariable=self.chart_current_var,
            foreground="#198754",
            font=("Consolas", 16, "bold"),
        ).pack(anchor="e")
        ttk.Label(
            readout_frame,
            textvariable=self.chart_max_var,
            foreground="#d00000",
            font=("Consolas", 16, "bold"),
        ).pack(anchor="e")
        self.update_chart_freeze_button()
        self.draw_current_chart()

    def add_live_row(self, parent, row, label, value_var, value_color, value_size):
        tk.Label(parent, text=label, bg="white", fg="#0b5ed7", font=("Arial", 10, "bold")).grid(
            row=row, column=0, sticky="w", padx=(10, 6), pady=2
        )
        tk.Label(
            parent,
            textvariable=value_var,
            bg="white",
            fg=value_color,
            font=("Consolas", value_size, "bold"),
        ).grid(row=row, column=1, sticky="e", padx=(0, 10), pady=2)

    def refresh_ports(self):
        current_port = self.port_var.get().strip()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports

        if current_port in ports:
            self.port_var.set(current_port)
        elif ports:
            self.port_var.set(ports[0])
        else:
            self.port_var.set("")

    def toggle_connection(self):
        if self.connected:
            self.write_frame(self.UNLINK_FRAME)
            self.tasks.put(("close",))
            return

        self.refresh_ports()
        port = self.port_var.get().strip()
        if not port:
            self.log("请先选择串口")
            return
        self.tasks.put(("open", port, int(self.baud_var.get())))

    def voltage_frame(self, value):
        value = max(self.volt_min, min(self.volt_max, value))
        units = int(round(value * 100))
        return f"<01{units:05d}0000>"

    def current_frame(self, value):
        value = max(self.amp_min, min(self.amp_max, value))
        units = int(round(value * 1000))
        return f"<03{units:06d}000>"

    def write_frame(self, frame):
        if not self.connected:
            self.log("请先连接串口")
            return
        self.tasks.put(("write", frame))

    def query_frame(self, frame, kind):
        if not self.connected:
            return
        self.tasks.put(("query", frame, kind))

    def clamp_voltage(self):
        try:
            value = float(self.volt_var.get())
        except ValueError:
            value = self.default_volt
        value = max(self.volt_min, min(self.volt_max, value))
        self.volt_var.set(f"{value:.2f}")
        return value

    def clamp_current(self):
        try:
            value = float(self.amp_var.get())
        except ValueError:
            value = self.default_amp
        value = max(self.amp_min, min(self.amp_max, value))
        self.amp_var.set(f"{value:.3f}")
        return value

    def apply_voltage(self):
        value = self.clamp_voltage()
        self.save_config()
        self.write_frame(self.voltage_frame(value))

    def apply_current(self):
        value = self.clamp_current()
        self.save_config()
        self.write_frame(self.current_frame(value))

    def apply_setpoints(self):
        self.apply_current()
        self.apply_voltage()

    def volt_plus(self):
        self.volt_var.set(f"{min(self.clamp_voltage() + self.volt_step, self.volt_max):.2f}")
        self.apply_voltage()

    def volt_minus(self):
        self.volt_var.set(f"{max(self.clamp_voltage() - self.volt_step, self.volt_min):.2f}")
        self.apply_voltage()

    def amp_plus(self):
        self.amp_var.set(f"{min(self.clamp_current() + self.amp_step, self.amp_max):.3f}")
        self.apply_current()

    def amp_minus(self):
        self.amp_var.set(f"{max(self.clamp_current() - self.amp_step, self.amp_min):.3f}")
        self.apply_current()

    def toggle_output(self):
        if not self.connected:
            self.log("请先连接串口")
            return

        target_on = not self.is_output_on
        if target_on:
            self.apply_setpoints()
            self.write_frame(self.OUTPUT_ON_FRAME)
        else:
            self.write_frame(self.OUTPUT_OFF_FRAME)
        self.is_output_on = target_on
        self.update_output_button()

    def update_output_button(self):
        if self.is_output_on:
            self.output_btn.config(text="输出 ON", bg="#28a745", fg="white")
        else:
            self.output_btn.config(text="输出 OFF", bg="#cccccc", fg="black")

    def send_raw(self):
        frame = self.raw_var.get().strip()
        if not (frame.startswith("<") and frame.endswith(">")):
            self.log("原始帧必须以 < 开头、以 > 结尾")
            return
        self.write_frame(frame)

    def apply_raw_preset(self, event=None):
        frame = self.RAW_PRESETS.get(self.raw_preset_var.get())
        if frame:
            self.raw_var.set(frame)

    def toggle_chart_panel(self):
        if self.chart_panel_visible:
            self.close_chart_panel()
        else:
            self.open_chart_panel()

    def open_chart_panel(self):
        if self.chart_window is None or not self.chart_window.winfo_exists():
            self.build_chart_panel()
        else:
            self.chart_window.deiconify()
            self.chart_window.lift()

        self.chart_panel_visible = True
        self.chart_panel_btn.config(text="关闭曲线窗口")
        self.draw_current_chart()

    def close_chart_panel(self):
        self.chart_panel_visible = False
        self.chart_panel_btn.config(text="打开曲线窗口")
        if self.chart_window is not None and self.chart_window.winfo_exists():
            self.chart_window.withdraw()

    def follow_latest_chart(self):
        self.chart_manual_anchor = None
        self.chart_freeze_anchor = None
        if self.chart_frozen.get():
            self.chart_frozen.set(False)
            self.update_chart_freeze_button()
        self.set_chart_x_scroll_value(1000.0)
        if hasattr(self, "chart_status_var"):
            self.chart_status_var.set("X轴已恢复跟随最新数据")
        self.draw_current_chart()

    def on_chart_style_change(self, _event=None):
        style = self.chart_line_style.get()
        if style not in ("平滑", "折线"):
            self.chart_line_style.set("平滑")
            style = "平滑"
        if hasattr(self, "chart_status_var"):
            self.chart_status_var.set(f"曲线样式已切换为: {style}")
        self.save_config()
        self.draw_current_chart()

    def choose_chart_line_color(self):
        parent = self.chart_window if self.chart_window is not None and self.chart_window.winfo_exists() else self.root
        parent.lift()
        _rgb, color = colorchooser.askcolor(color=self.chart_line_color, title="选择曲线颜色", parent=parent)
        parent.lift()
        if not color:
            return
        self.chart_line_color = color
        self.update_chart_color_button()
        if hasattr(self, "chart_status_var"):
            self.chart_status_var.set(f"曲线颜色已切换为: {color}")
        self.save_config()
        self.draw_current_chart()

    def update_chart_color_button(self):
        if not hasattr(self, "chart_color_btn"):
            return
        color = self.chart_line_color if self.is_valid_hex_color(self.chart_line_color) else "#198754"
        self.chart_color_btn.config(bg=color, activebackground=color)

    def toggle_chart_recording(self):
        if self.chart_enabled.get():
            if not self.open_current_log_file():
                self.chart_enabled.set(False)
                self.draw_current_chart()
                return
            if not self.live_enabled.get():
                self.live_enabled.set(True)
                self.reset_live_max()
            self.chart_static_anchor = None
            self.next_live_query = "current"
            self.chart_status_var.set(f"曲线采集已开启，文件: {self.chart_csv_path.name}")
        else:
            self.close_current_log_file()
            self.chart_status_var.set("曲线采集已关闭，已保存的数据保留")
        self.draw_current_chart()

    def toggle_chart_freeze(self):
        self.chart_frozen.set(not self.chart_frozen.get())
        if self.chart_frozen.get():
            _visible_points, _visible_count, _range_seconds, anchor_time = self.get_visible_current_points()
            self.chart_freeze_anchor = anchor_time
            self.chart_manual_anchor = None
            self.chart_status_var.set("窗口已冻结，采集和CSV保存继续；点击“解除冻结”恢复滚动")
        else:
            self.chart_freeze_anchor = None
            if self.chart_enabled.get() and self.chart_csv_path:
                self.chart_status_var.set(f"已解除冻结，曲线恢复滚动；文件: {self.chart_csv_path.name}")
            else:
                self.chart_status_var.set("已解除冻结，曲线恢复滚动")
        self.update_chart_freeze_button()
        self.draw_current_chart()

    def update_chart_freeze_button(self):
        if not hasattr(self, "chart_freeze_btn"):
            return
        if self.chart_frozen.get():
            self.chart_freeze_btn.config(
                text="解除冻结",
                bg="#0d6efd",
                fg="#ffffff",
                activebackground="#0b5ed7",
                activeforeground="#ffffff",
                relief=tk.SUNKEN,
            )
        else:
            self.chart_freeze_btn.config(
                text="冻结窗口",
                bg="#f8f9fa",
                fg="#212529",
                activebackground="#e9ecef",
                activeforeground="#212529",
                relief=tk.RAISED,
            )

    def open_current_log_file(self):
        self.close_current_log_file()
        try:
            self.chart_data_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.chart_csv_path = self.chart_data_dir / f"current_curve_{timestamp}.csv"
            self.chart_csv_file = self.chart_csv_path.open("w", newline="", encoding="utf-8-sig")
            self.chart_csv_writer = csv.writer(self.chart_csv_file)
            self.chart_csv_writer.writerow(["index", "local_time", "elapsed_seconds", "current_a"])
            self.chart_csv_file.flush()
            self.chart_recording_start = time.monotonic()
            self.chart_sample_index = 0
            self.current_points.clear()
            self.chart_static_anchor = None
            self.chart_manual_anchor = None
            self.highlighted_y_values.clear()
            self.chart_cursor_point = None
            self.log(f"电流曲线文件已创建: {self.chart_csv_path}")
            return True
        except Exception as exc:
            self.chart_csv_file = None
            self.chart_csv_writer = None
            self.chart_csv_path = None
            self.chart_recording_start = None
            self.log(f"创建电流曲线文件失败: {exc}")
            return False

    def close_current_log_file(self):
        if self.chart_csv_file:
            try:
                self.chart_csv_file.flush()
                self.chart_csv_file.close()
            except Exception as exc:
                self.log(f"关闭电流曲线文件失败: {exc}")
        self.chart_csv_file = None
        self.chart_csv_writer = None
        self.chart_recording_start = None

    def write_current_log_row(self, sample_time, value):
        if not self.chart_csv_writer or self.chart_recording_start is None:
            return
        try:
            self.chart_sample_index += 1
            local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            elapsed = sample_time - self.chart_recording_start
            self.chart_csv_writer.writerow([self.chart_sample_index, local_time, f"{elapsed:.3f}", f"{value:.3f}"])
            self.chart_csv_file.flush()
        except Exception as exc:
            self.log(f"写入电流曲线文件失败: {exc}")
            self.close_current_log_file()
            self.chart_enabled.set(False)

    def schedule_live_poll(self):
        need_poll = self.live_enabled.get() or self.chart_enabled.get()
        if self.connected and need_poll and self.tasks.qsize() < 2:
            if self.chart_enabled.get() and not self.live_enabled.get():
                self.query_frame(self.CURR_QUERY_FRAME, "current")
            elif self.next_live_query == "voltage":
                self.query_frame(self.VOLT_QUERY_FRAME, "voltage")
                self.next_live_query = "current"
            else:
                self.query_frame(self.CURR_QUERY_FRAME, "current")
                self.next_live_query = "voltage"
        self.root.after(self.live_poll_ms, self.schedule_live_poll)

    def reset_live_max(self):
        if self.live_enabled.get():
            self.max_current_value = 0.0
            self.max_power_value = 0.0
            self.next_live_query = "voltage"
            self.max_amp_var.set("0.000 A")
            self.max_power_var.set("0.000 W")

    def clear_current_chart(self):
        self.current_points.clear()
        self.chart_static_anchor = None
        self.chart_manual_anchor = None
        self.clear_chart_markers(redraw=False)
        self.set_chart_x_scroll_value(1000.0)
        self.chart_status_var.set("曲线已清空")
        self.draw_current_chart()

    def clear_chart_markers(self, redraw=True):
        self.highlighted_y_values.clear()
        self.chart_cursor_point = None
        if hasattr(self, "chart_status_var"):
            self.chart_status_var.set("标识线已清除")
        if redraw:
            self.draw_current_chart()

    def add_current_point(self, value):
        if not self.chart_enabled.get():
            return
        sample_time = time.monotonic()
        self.chart_static_anchor = None
        self.write_current_log_row(sample_time, value)
        self.current_points.append((sample_time, value, self.chart_sample_index))
        if len(self.current_points) > self.current_chart_max_points:
            del self.current_points[: len(self.current_points) - self.current_chart_max_points]
        self.draw_current_chart()

    def import_current_chart_file(self):
        self.chart_data_dir.mkdir(parents=True, exist_ok=True)
        file_path = filedialog.askopenfilename(
            title="导入电流曲线 CSV",
            initialdir=str(self.chart_data_dir),
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not file_path:
            return

        rows = []
        try:
            with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row_index, row in enumerate(reader, start=1):
                    current_text = row.get("current_a") or row.get("current") or row.get("电流")
                    if not current_text:
                        continue
                    elapsed_text = row.get("elapsed_seconds") or row.get("elapsed") or row.get("相对秒数")
                    elapsed = float(elapsed_text) if elapsed_text else (row_index - 1) * (self.live_poll_ms / 1000.0)
                    local_time = row.get("local_time") or row.get("本地时间") or row.get("time") or ""
                    rows.append((max(0.0, elapsed), float(current_text), local_time.strip()))
        except Exception as exc:
            self.log(f"导入电流曲线失败: {exc}")
            return

        if not rows:
            self.log("导入电流曲线失败: 文件中没有有效电流数据")
            return

        if self.chart_enabled.get():
            self.close_current_log_file()
            self.chart_enabled.set(False)

        rows.sort(key=lambda item: item[0])
        duration = max(rows[-1][0], 1.0)
        base_time = time.monotonic() - duration
        self.current_points = [
            (base_time + elapsed, current, index, local_time)
            for index, (elapsed, current, local_time) in enumerate(rows, start=1)
        ]
        self.chart_sample_index = len(rows)
        self.chart_static_anchor = base_time + duration
        self.chart_manual_anchor = None
        self.chart_cursor_point = None
        self.set_chart_x_scroll_value(1000.0)
        self.auto_set_chart_range(duration)
        self.chart_status_var.set(f"已导入静态曲线: {Path(file_path).name}，共 {len(rows)} 点")
        self.draw_current_chart()
        self.log(f"已导入电流曲线文件: {file_path}")

    def auto_set_chart_range(self, duration_seconds):
        if duration_seconds <= 3600:
            self.chart_range_unit.set("分钟")
            self.chart_range_value.set(max(0.1, round(duration_seconds / 60, 2)))
        elif duration_seconds <= 86400:
            self.chart_range_unit.set("小时")
            self.chart_range_value.set(max(0.1, round(duration_seconds / 3600, 2)))
        else:
            self.chart_range_unit.set("天")
            self.chart_range_value.set(max(0.1, round(duration_seconds / 86400, 2)))

    def get_chart_range_seconds(self):
        try:
            value = float(self.chart_range_value.get())
        except (tk.TclError, ValueError):
            value = 5.0
            self.chart_range_value.set(value)
        value = max(0.1, min(365.0, value))

        unit = self.chart_range_unit.get()
        if unit == "小时":
            return value * 3600
        if unit == "天":
            return value * 86400
        return value * 60

    def set_chart_range_seconds(self, seconds):
        seconds = max(6.0, min(365.0 * 86400, seconds))
        if seconds < 3600:
            self.chart_range_unit.set("分钟")
            self.chart_range_value.set(round(seconds / 60, 2))
        elif seconds < 86400:
            self.chart_range_unit.set("小时")
            self.chart_range_value.set(round(seconds / 3600, 2))
        else:
            self.chart_range_unit.set("天")
            self.chart_range_value.set(round(seconds / 86400, 2))

    def format_range_value(self):
        try:
            value = float(self.chart_range_value.get())
        except (tk.TclError, ValueError):
            value = 5.0
        return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")

    def set_chart_x_scroll_value(self, value):
        if not hasattr(self, "chart_x_scroll_var"):
            return
        self.chart_x_scroll_syncing = True
        try:
            self.chart_x_scroll_var.set(max(0.0, min(1000.0, float(value))))
        finally:
            self.chart_x_scroll_syncing = False

    def set_chart_y_scroll_value(self, value):
        if not hasattr(self, "chart_y_scroll_var"):
            return
        self.chart_y_scroll_syncing = True
        try:
            self.chart_y_scroll_var.set(max(0.0, min(1000.0, float(value))))
        finally:
            self.chart_y_scroll_syncing = False

    def get_chart_latest_anchor(self):
        if self.chart_static_anchor is not None:
            return self.chart_static_anchor
        if self.chart_frozen.get() and self.chart_freeze_anchor is not None:
            return self.chart_freeze_anchor
        return time.monotonic()

    def get_chart_scroll_bounds(self, range_seconds):
        latest_anchor = self.get_chart_latest_anchor()
        if not self.current_points:
            return latest_anchor, latest_anchor

        data_start = self.current_points[0][0]
        earliest_anchor = data_start + range_seconds
        if earliest_anchor > latest_anchor:
            earliest_anchor = latest_anchor
        return earliest_anchor, latest_anchor

    def clamp_chart_anchor(self, anchor_time, range_seconds):
        earliest_anchor, latest_anchor = self.get_chart_scroll_bounds(range_seconds)
        if latest_anchor <= earliest_anchor:
            return latest_anchor
        return max(earliest_anchor, min(latest_anchor, anchor_time))

    def update_chart_x_scroll(self, anchor_time, range_seconds):
        if not hasattr(self, "chart_x_scroll_var"):
            return
        if self.chart_manual_anchor is not None:
            # 手动拖动 X 轴后固定显示窗口；新数据继续采集和保存，但不再推着滑块/视窗滚动。
            return

        earliest_anchor, latest_anchor = self.get_chart_scroll_bounds(range_seconds)
        if latest_anchor <= earliest_anchor:
            self.set_chart_x_scroll_value(1000.0)
            return
        self.set_chart_x_scroll_value(1000.0)

    def on_chart_x_scroll(self, value):
        if self.chart_x_scroll_syncing or not self.current_points:
            return

        try:
            scroll_value = float(value)
        except ValueError:
            return

        range_seconds = self.get_chart_range_seconds()
        earliest_anchor, latest_anchor = self.get_chart_scroll_bounds(range_seconds)
        if latest_anchor <= earliest_anchor:
            self.chart_manual_anchor = None
        else:
            ratio = max(0.0, min(1.0, scroll_value / 1000.0))
            self.chart_manual_anchor = earliest_anchor + (latest_anchor - earliest_anchor) * ratio
            self.chart_status_var.set("X轴历史查看锁定，采集和CSV保存继续")
        self.draw_current_chart()

    def get_chart_y_scroll_bounds(self, visible_points, span):
        values = [point[1] for point in visible_points] if visible_points else []
        data_min = min(values, default=0.0)
        data_max = max(values, default=0.0)
        base_min = -0.2
        base_max = 0.5
        min_y_min = min(base_min, data_min - span * 0.5)
        max_y_min = max(base_min, base_max - span, data_max - span * 0.5)
        if max_y_min < min_y_min:
            max_y_min = min_y_min
        return min_y_min, max_y_min

    def update_chart_y_scroll(self, visible_points, y_min, y_max):
        if not hasattr(self, "chart_y_scroll_var"):
            return

        span = max(y_max - y_min, 0.001)
        min_y_min, max_y_min = self.get_chart_y_scroll_bounds(visible_points, span)
        if max_y_min <= min_y_min:
            self.set_chart_y_scroll_value(500.0)
            return

        value = (y_min - min_y_min) / (max_y_min - min_y_min) * 1000.0
        self.set_chart_y_scroll_value(value)

    def on_chart_y_scroll(self, value):
        if self.chart_y_scroll_syncing:
            return

        try:
            scroll_value = float(value)
        except ValueError:
            return

        visible_points, _visible_count, _range_seconds, _anchor_time = self.get_visible_current_points()
        span = max(self.chart_y_max - self.chart_y_min, 0.001)
        min_y_min, max_y_min = self.get_chart_y_scroll_bounds(visible_points, span)
        ratio = max(0.0, min(1.0, scroll_value / 1000.0))
        next_y_min = min_y_min + (max_y_min - min_y_min) * ratio
        self.chart_y_min = round(next_y_min, 4)
        self.chart_y_max = round(next_y_min + span, 4)
        self.chart_y_manual = True
        self.chart_status_var.set(f"Y轴位置 {self.chart_y_min:.3f} ~ {self.chart_y_max:.3f} A")
        self.draw_current_chart()

    def get_chart_plot_area(self):
        width = max(self.current_chart.winfo_width(), 430)
        height = max(self.current_chart.winfo_height(), 420)
        pad_left = 64
        pad_right = 16
        pad_top = 16
        pad_bottom = 34
        plot_left = pad_left
        plot_right = width - pad_right
        plot_top = pad_top
        plot_bottom = height - pad_bottom
        return width, height, plot_left, plot_right, plot_top, plot_bottom

    def chart_value_to_y(self, value, y_min, y_max, plot_top, plot_bottom):
        span = max(y_max - y_min, 0.001)
        plot_height = max(plot_bottom - plot_top, 1)
        return plot_bottom - ((value - y_min) / span) * plot_height

    def chart_y_to_value(self, y, y_min, y_max, plot_top, plot_bottom):
        span = max(y_max - y_min, 0.001)
        plot_height = max(plot_bottom - plot_top, 1)
        ratio = (plot_bottom - y) / plot_height
        return y_min + ratio * span

    def format_chart_y_label(self, value):
        y_step = self.get_chart_y_step()
        if y_step < 0.01:
            return f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def iter_chart_y_ticks(self, y_min, y_max, y_step):
        start = math.ceil((y_min - 1e-9) / y_step)
        end = math.floor((y_max + 1e-9) / y_step)
        for tick in range(start, end + 1):
            yield round(tick * y_step, 4)

    def get_chart_y_limits(self, visible_points):
        y_step = self.get_chart_y_step()
        y_min = self.chart_y_min
        y_max = self.chart_y_max
        if y_max <= y_min:
            y_min, y_max = -0.2, 0.5

        if visible_points and not self.chart_y_manual:
            min_value = min(point[1] for point in visible_points)
            max_value = max(point[1] for point in visible_points)
            y_min = min(y_min, min_value)
            y_max = max(y_max, max_value)

        y_min = math.floor(y_min / y_step) * y_step
        y_max = math.ceil(y_max / y_step) * y_step
        if y_max - y_min < y_step:
            y_max = y_min + y_step
        if not self.chart_y_manual:
            self.chart_y_min = round(y_min, 4)
            self.chart_y_max = round(y_max, 4)
        return round(y_min, 4), round(y_max, 4)

    def on_chart_mouse_wheel(self, event):
        zoom_factor = 1.25
        zoom_in = False
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            zoom_in = True
        elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            zoom_in = False

        _width, _height, plot_left, _plot_right, plot_top, plot_bottom = self.get_chart_plot_area()
        if getattr(event, "x", plot_left + 1) <= plot_left:
            self.zoom_chart_y_axis(event, zoom_in, plot_top, plot_bottom)
            self.draw_current_chart()
            return "break"

        _visible_points, _visible_count, current_seconds, anchor_time = self.get_visible_current_points()
        center_time = anchor_time - current_seconds / 2
        next_seconds = current_seconds / zoom_factor if zoom_in else current_seconds * zoom_factor
        self.set_chart_range_seconds(next_seconds)
        next_seconds = self.get_chart_range_seconds()
        if self.current_points:
            next_anchor = self.clamp_chart_anchor(center_time + next_seconds / 2, next_seconds)
            self.chart_manual_anchor = next_anchor
            self.chart_status_var.set("X轴历史查看锁定，采集和CSV保存继续")
        self.draw_current_chart()
        return "break"

    def zoom_chart_y_axis(self, event, zoom_in, plot_top, plot_bottom):
        visible_points, _visible_count, _range_seconds, _anchor_time = self.get_visible_current_points()
        y_min, y_max = self.get_chart_y_limits(visible_points)
        span = max(y_max - y_min, 0.001)
        factor = 1.25
        next_span = span / factor if zoom_in else span * factor
        min_span = max(self.get_chart_y_step() * 5, 0.005)
        next_span = max(min_span, min(6.0, next_span))

        anchor_value = self.chart_y_to_value(event.y, y_min, y_max, plot_top, plot_bottom)
        anchor_ratio = (anchor_value - y_min) / span
        anchor_ratio = max(0.05, min(0.95, anchor_ratio))
        self.chart_y_min = round(anchor_value - next_span * anchor_ratio, 4)
        self.chart_y_max = round(anchor_value + next_span * (1 - anchor_ratio), 4)
        self.chart_y_manual = True
        self.chart_status_var.set(f"Y轴范围 {self.chart_y_min:.3f} ~ {self.chart_y_max:.3f} A")

    def on_chart_click(self, event):
        if self.current_chart is None:
            return

        _width, _height, plot_left, plot_right, plot_top, plot_bottom = self.get_chart_plot_area()

        visible_points, _visible_count, range_seconds, anchor_time = self.get_visible_current_points()
        y_min, y_max = self.get_chart_y_limits(visible_points)
        y_step = self.get_chart_y_step()

        if plot_left <= event.x <= plot_right and plot_top <= event.y <= plot_bottom:
            self.select_current_chart_point(event.x, plot_left, plot_right, range_seconds, anchor_time, visible_points)
            return "break"

        if event.x > plot_left:
            return None

        for value in self.iter_chart_y_ticks(y_min, y_max, y_step):
            y = self.chart_value_to_y(value, y_min, y_max, plot_top, plot_bottom)
            if abs(event.y - y) <= 8:
                if value in self.highlighted_y_values:
                    self.highlighted_y_values.remove(value)
                else:
                    self.highlighted_y_values.add(value)
                self.draw_current_chart()
                return "break"

    def select_current_chart_point(self, click_x, plot_left, plot_right, range_seconds, anchor_time, visible_points):
        if not visible_points:
            return

        plot_width = max(plot_right - plot_left, 1)
        ratio = max(0.0, min(1.0, (click_x - plot_left) / plot_width))
        cutoff = anchor_time - range_seconds
        target_time = cutoff + range_seconds * ratio

        nearest = None
        nearest_distance = None
        for point in visible_points:
            point_time = point[0]
            if point_time < cutoff or point_time > anchor_time:
                continue
            distance = abs(point_time - target_time)
            if nearest_distance is None or distance < nearest_distance:
                nearest = point
                nearest_distance = distance

        if nearest is None:
            return

        self.chart_cursor_point = nearest
        point_index = nearest[2] if len(nearest) > 2 else 0
        seconds_from_right = anchor_time - nearest[0]
        local_time = self.format_chart_point_local_time(nearest)
        self.chart_status_var.set(
            f"选中点 #{point_index}: {nearest[1]:.3f} A，{local_time}，位置 {self.format_chart_time_label(seconds_from_right, range_seconds)}"
        )
        self.draw_current_chart()

    def get_visible_current_points(self):
        if not self.current_points:
            return [], 0, self.get_chart_range_seconds(), time.monotonic()

        range_seconds = self.get_chart_range_seconds()
        if self.chart_manual_anchor is not None:
            anchor_time = self.clamp_chart_anchor(self.chart_manual_anchor, range_seconds)
            self.chart_manual_anchor = anchor_time
        elif self.chart_static_anchor is not None:
            anchor_time = self.chart_static_anchor
        elif self.chart_frozen.get() and self.chart_freeze_anchor is not None:
            anchor_time = self.chart_freeze_anchor
        else:
            anchor_time = time.monotonic()
        cutoff = anchor_time - range_seconds
        start = 0
        for index in range(len(self.current_points) - 1, -1, -1):
            if self.current_points[index][0] < cutoff:
                start = index + 1
                break

        end = len(self.current_points)
        for index in range(start, len(self.current_points)):
            if self.current_points[index][0] > anchor_time:
                end = index
                break

        visible = self.current_points[start:end]
        visible_count = len(visible)
        max_draw_points = 1200
        if visible_count > max_draw_points:
            step = (visible_count + max_draw_points - 1) // max_draw_points
            visible = visible[::step]
        return visible, visible_count, range_seconds, anchor_time

    def format_chart_time_label(self, seconds_from_now, range_seconds):
        seconds_from_now = abs(int(seconds_from_now))
        unit = self.chart_range_unit.get()
        if unit == "天":
            days = seconds_from_now / 86400
            return f"-{days:.1f}天" if range_seconds <= 3 * 86400 else f"-{days:.0f}天"
        if unit == "小时":
            hours = seconds_from_now / 3600
            return f"-{hours:.1f}h" if range_seconds <= 3 * 3600 else f"-{hours:.0f}h"
        minutes = seconds_from_now / 60
        return f"-{minutes:.1f}min" if range_seconds <= 3 * 60 else f"-{minutes:.0f}min"

    def format_chart_point_local_time(self, point):
        if len(point) > 3 and point[3]:
            return point[3]
        timestamp = point[0] + self.chart_epoch_offset
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def get_chart_y_step(self):
        try:
            step = float(self.chart_y_step.get())
        except (tk.TclError, ValueError):
            step = 0.1
        step = max(0.001, min(5.0, step))
        self.chart_y_step.set(round(step, 3))
        return step

    def update_chart_readout(self, visible_points=None):
        if not hasattr(self, "chart_current_var"):
            return
        if self.chart_static_anchor is not None or self.chart_frozen.get():
            source_points = visible_points if visible_points else []
            current_value = source_points[-1][1] if source_points else 0.0
            max_value = max((point[1] for point in source_points), default=0.0)
        elif self.current_points:
            current_value = self.current_points[-1][1]
            source_points = visible_points if visible_points else self.current_points
            max_value = max(point[1] for point in source_points)
        else:
            current_value = 0.0
            max_value = 0.0
        self.chart_current_var.set(f"当前电流 {current_value:.3f} A")
        self.chart_max_var.set(f"MAX {max_value:.3f} A")

    def draw_chart_cursor_marker(self, canvas, cutoff, anchor_time, range_seconds, y_min, y_max, plot_left, plot_right, plot_top, plot_bottom):
        if self.chart_cursor_point is None:
            return

        point_time = self.chart_cursor_point[0]
        value = self.chart_cursor_point[1]
        point_index = self.chart_cursor_point[2] if len(self.chart_cursor_point) > 2 else 0
        if point_time < cutoff or point_time > anchor_time:
            return

        plot_width = max(plot_right - plot_left, 1)
        x = plot_left + ((point_time - cutoff) / range_seconds) * plot_width
        clamped = max(y_min, min(y_max, value))
        y = self.chart_value_to_y(clamped, y_min, y_max, plot_top, plot_bottom)

        canvas.create_line(x, plot_top, x, plot_bottom, fill="#0d6efd", width=1, dash=(4, 3))
        canvas.create_line(plot_left, y, plot_right, y, fill="#0d6efd", width=1, dash=(4, 3))
        canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#0d6efd", outline="#ffffff", width=2)

        local_time = self.format_chart_point_local_time(self.chart_cursor_point)
        label = f"#{point_index}  {value:.3f} A\n{local_time}"
        label_width = 178
        label_height = 34
        label_x = min(max(x + 8, plot_left + 4), plot_right - label_width - 4)
        label_y = max(plot_top + 6, y - 28)
        canvas.create_rectangle(
            label_x - 4,
            label_y - 3,
            label_x + label_width,
            label_y + label_height,
            fill="#ffffff",
            outline="#0d6efd",
        )
        canvas.create_text(label_x, label_y, text=label, anchor="nw", fill="#0d6efd", font=("Consolas", 9, "bold"))

    def draw_current_chart(self):
        if self.current_chart is None:
            return
        if not self.chart_panel_visible:
            return

        canvas = self.current_chart
        width, height, plot_left, plot_right, plot_top, plot_bottom = self.get_chart_plot_area()
        plot_width = max(plot_right - plot_left, 1)
        plot_height = max(plot_bottom - plot_top, 1)

        visible_points, visible_count, range_seconds, anchor_time = self.get_visible_current_points()
        self.update_chart_x_scroll(anchor_time, range_seconds)
        y_min, y_max = self.get_chart_y_limits(visible_points)
        self.update_chart_y_scroll(visible_points, y_min, y_max)
        self.update_chart_readout(visible_points)
        if hasattr(self, "chart_summary_var"):
            total_points = self.chart_sample_index if self.chart_sample_index else len(self.current_points)
            self.chart_summary_var.set(
                f"显示最近 {self.format_range_value()} {self.chart_range_unit.get()}，"
                f"可见 {visible_count} 点 / 缓存 {len(self.current_points)} 点 / 采集 {total_points} 点"
            )

        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#ffffff", outline="")
        canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom, outline="#b8c2cc")

        y_step = self.get_chart_y_step()
        y_ticks = list(self.iter_chart_y_ticks(y_min, y_max, y_step))
        grid_count = max(1, len(y_ticks) - 1)
        min_label_gap = 22
        label_every = max(1, math.ceil((grid_count + 1) * min_label_gap / plot_height))
        for idx, value in enumerate(y_ticks):
            value_key = round(value, 4)
            y = self.chart_value_to_y(value, y_min, y_max, plot_top, plot_bottom)
            highlighted = value_key in self.highlighted_y_values
            color = "#ff7a00" if highlighted else ("#b8c2cc" if abs(value) < 1e-9 else "#edf2f7")
            width_line = 3 if highlighted else 1
            canvas.create_line(plot_left, y, plot_right, y, fill=color, width=width_line)
            if idx % label_every == 0 or idx == grid_count:
                canvas.create_text(
                    plot_left - 8,
                    y,
                    text=self.format_chart_y_label(value),
                    anchor="e",
                    fill="#ff7a00" if highlighted else "#4a5568",
                    font=("Consolas", 9 if highlighted else 8, "bold" if highlighted else "normal"),
                )

        canvas.create_text(8, plot_top, text="A", anchor="nw", fill="#198754", font=("Arial", 9, "bold"))

        tick_count = 6
        for idx in range(tick_count):
            ratio = idx / (tick_count - 1)
            x = plot_left + plot_width * ratio
            seconds_from_now = range_seconds * (1 - ratio)
            label = self.format_chart_time_label(seconds_from_now, range_seconds)
            canvas.create_line(x, plot_top, x, plot_bottom, fill="#edf2f7")
            canvas.create_line(x, plot_bottom, x, plot_bottom + 5, fill="#718096")
            canvas.create_text(
                x,
                plot_bottom + 10,
                text="现在" if idx == tick_count - 1 else label,
                anchor="n",
                fill="#4a5568",
                font=("Consolas", 8),
            )

        if not self.current_points:
            empty_text = "正在等待电流数据" if self.chart_enabled.get() else "曲线采集未开启"
            canvas.create_text(
                width / 2,
                height / 2,
                text=empty_text,
                fill="#718096",
                font=("Arial", 12, "bold"),
            )
            return

        if not visible_points:
            canvas.create_text(
                width / 2,
                height / 2,
                text="暂无电流数据",
                fill="#718096",
                font=("Arial", 12, "bold"),
            )
            return

        if not self.chart_enabled.get():
            canvas.create_text(
                plot_left + 8,
                plot_top + 8,
                text="采集已暂停",
                anchor="nw",
                fill="#d97706",
                font=("Arial", 9, "bold"),
            )

        cutoff = anchor_time - range_seconds
        points = []
        line_color = self.chart_line_color if self.is_valid_hex_color(self.chart_line_color) else "#198754"
        smooth_curve = self.chart_line_style.get() == "平滑"
        for point_time, value, *_point_extra in visible_points:
            x = plot_left + ((point_time - cutoff) / range_seconds) * plot_width
            clamped = max(y_min, min(y_max, value))
            y = self.chart_value_to_y(clamped, y_min, y_max, plot_top, plot_bottom)
            points.extend([x, y])

        if len(points) >= 4:
            canvas.create_line(*points, fill=line_color, width=2, smooth=smooth_curve)
        else:
            canvas.create_oval(points[0] - 2, points[1] - 2, points[0] + 2, points[1] + 2, fill=line_color, outline="")
        self.draw_chart_cursor_marker(canvas, cutoff, anchor_time, range_seconds, y_min, y_max, plot_left, plot_right, plot_top, plot_bottom)

    def drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            event_type = event[0]
            message = event[1] if len(event) > 1 else ""
            if event_type == "connected":
                self.connected = True
                self.conn_btn.config(text="断开")
                self.log(message)
                self.write_frame(self.LINK_FRAME)
                self.write_frame(self.OUTPUT_OFF_FRAME)
                self.is_output_on = False
                self.update_output_button()
                self.apply_setpoints()
            elif event_type == "disconnected":
                self.connected = False
                self.conn_btn.config(text="连接")
                self.log(message)
            elif event_type == "error":
                self.log(f"错误: {message}")
            elif event_type == "log":
                self.log(message)
            elif event_type == "query_result":
                _, kind, text_value = event
                self.handle_query_result(kind, text_value)

        self.root.after(100, self.drain_events)

    def handle_query_result(self, kind, text_value):
        payload = text_value.strip().strip("<>")
        if len(payload) < 8:
            return

        try:
            if kind == "voltage":
                value = int(payload[2:7]) / 100.0
                self.read_volt_var.set(f"{value:.2f}")
            elif kind == "current":
                value = int(payload[2:8]) / 1000.0
                self.read_amp_var.set(f"{value:.3f}")
                self.add_current_point(value)
            else:
                return

            try:
                v = float(self.read_volt_var.get())
                a = float(self.read_amp_var.get())
                power = v * a
                self.read_power_var.set(f"{power:.3f}")
                if a > self.max_current_value:
                    self.max_current_value = a
                    self.max_amp_var.set(f"{a:.3f} A")
                if power > self.max_power_value:
                    self.max_power_value = power
                    self.max_power_var.set(f"{power:.3f} W")
            except ValueError:
                self.read_power_var.set("0.000")
        except ValueError:
            self.log(f"无法解析 {kind} 回复: {text_value}")

    def log(self, message):
        now = time.strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{now}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def on_close(self):
        self.save_config()
        self.close_current_log_file()
        self.tasks.put(("stop",))
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    app = PowerSupplyGUI(window)
    window.mainloop()


# ======================= SPPS-D305-232 协议说明 =======================
# 以下协议来自 Bus Hound 抓取官方 DC Power Supply V2.1.4 软件的通信数据。
# 串口参数：9600, 8N1, 无流控。
# 帧格式：ASCII 字符串，固定以 "<" 开头、以 ">" 结尾，不带 \r\n。
# 常见帧长度为 13 字节："<" + 11 个协议字符 + ">"。
#
# 连接 / 断开：
#   <09100000000> 连接 Link，正常回复类似 <19OK0000001>
#   <09200000000> 断开 Unlink，正常回复类似 <19OK0000000>
#
# 输出开关：
#   <07000000000> 打开输出
#   <08000000000> 关闭输出
#
# 电压设置：
#   格式：<01 + round(电压 * 100)补齐5位 + 0000>
#   12.00V -> <01012000000>
#   14.52V -> <01014520000>
#
# 电流设置：
#   格式：<03 + round(电流 * 1000)补齐6位 + 000>
#   2.000A -> <03002000000>
#   3.123A -> <03003123000>
#
# 实时读取：
#   <02012200000> 查询输出电压，回复中 payload[2:7] / 100
#   <04003300000> 查询输出电流，回复中 payload[2:8] / 1000
#   功率由软件计算：电压 * 电流
# =====================================================================
