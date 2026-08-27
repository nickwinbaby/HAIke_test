import json
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import serial
import serial.tools.list_ports


def resource_path(filename):
    """Return a path that works both in source mode and PyInstaller one-file mode."""
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / filename


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
        self.root.title("KUAIQU / NICE-POWER SPPS-D305-232 电源控制 - Mangetic - 2026-7-27")
        self.root.geometry("700x720")
        self.root.resizable(False, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.set_window_icon()

        self.config_path = Path(__file__).resolve().with_name("power_config.json")
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
        self.live_poll_ms = 100
        self.next_live_query = "voltage"
        self.max_current_value = 0.0
        self.max_power_value = 0.0

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
        data = {
            "voltage": round(float(self.volt_var.get()), 2),
            "current": round(float(self.amp_var.get()), 3),
        }
        try:
            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.log(f"保存配置失败: {exc}")

    def build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

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
        self.conn_btn.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(8, 0))

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
        self.save_config()
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

    def schedule_live_poll(self):
        if self.connected and self.live_enabled.get() and self.tasks.qsize() < 2:
            if self.next_live_query == "voltage":
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
