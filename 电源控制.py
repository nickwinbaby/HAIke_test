import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import serial
import serial.tools.list_ports


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
            timeout=0.6,
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

    def write_frame(self, frame):
        if not (self.ser and self.ser.is_open):
            self.events.put(("error", "串口未连接"))
            return

        elapsed = time.monotonic() - self.last_write_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        payload = frame.encode("ascii")
        self.ser.write(payload)
        self.ser.flush()
        self.last_write_time = time.monotonic()
        self.events.put(("log", f"TX: {frame}    HEX: {payload.hex(' ')}"))

        data = self.ser.read(13)
        if data:
            text = data.decode("ascii", errors="replace")
            self.events.put(("log", f"RX: {text!r}    HEX: {data.hex(' ')}"))
        else:
            self.events.put(("log", "RX: 超时无回复"))


class PowerSupplyGUI:
    LINK_FRAME = "<09100000000>"
    UNLINK_FRAME = "<09200000000>"
    STATUS_FRAME = "<04003300000>"
    OUTPUT_ON_FRAME = "<07000000000>"
    OUTPUT_OFF_FRAME = "<08000000000>"

    def __init__(self, root):
        self.root = root
        self.root.title("KUAIQU / NICE-POWER SPPS-D305-232 电源控制")
        self.root.geometry("620x560")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.volt_min = 0.00
        self.volt_max = 30.00
        self.amp_min = 0.00
        self.amp_max = 5.00
        self.volt_step = 0.01
        self.amp_step = 0.001
        self.default_volt = 12.00
        self.default_amp = 2.00
        self.connected = False
        self.is_output_on = False

        self.tasks = queue.Queue()
        self.events = queue.Queue()
        self.worker = SerialWorker(self.tasks, self.events)
        self.worker.start()

        self.build_ui()
        self.refresh_ports()
        self.drain_events()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill=tk.BOTH, expand=True)

        port_frame = ttk.LabelFrame(main, text="串口连接", padding=10)
        port_frame.pack(fill=tk.X, pady=(0, 12))
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
        set_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(set_frame, text="电压 V:").grid(row=0, column=0, sticky="w")
        self.volt_var = tk.StringVar(value=f"{self.default_volt:.2f}")
        ttk.Entry(set_frame, textvariable=self.volt_var, width=12, font=("Arial", 12)).grid(row=0, column=1, padx=(8, 12))
        ttk.Button(set_frame, text="-", width=3, command=self.volt_minus).grid(row=0, column=2)
        ttk.Button(set_frame, text="+", width=3, command=self.volt_plus).grid(row=0, column=3, padx=(6, 16))
        ttk.Button(set_frame, text="下发电压", command=self.apply_voltage).grid(row=0, column=4, sticky="ew")

        ttk.Label(set_frame, text="电流 A:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.amp_var = tk.StringVar(value=f"{self.default_amp:.3f}")
        ttk.Entry(set_frame, textvariable=self.amp_var, width=12, font=("Arial", 12)).grid(row=1, column=1, padx=(8, 12), pady=(8, 0))
        ttk.Button(set_frame, text="-", width=3, command=self.amp_minus).grid(row=1, column=2, pady=(8, 0))
        ttk.Button(set_frame, text="+", width=3, command=self.amp_plus).grid(row=1, column=3, padx=(6, 16), pady=(8, 0))
        ttk.Button(set_frame, text="下发电流", command=self.apply_current).grid(row=1, column=4, sticky="ew", pady=(8, 0))

        ttk.Button(set_frame, text="下发设置", command=self.apply_setpoints).grid(
            row=2, column=0, columnspan=5, sticky="ew", pady=(10, 0)
        )

        output_frame = ttk.LabelFrame(main, text="输出控制", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 12))
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
        raw_frame.pack(fill=tk.X, pady=(0, 12))
        self.raw_var = tk.StringVar(value=self.LINK_FRAME)
        ttk.Entry(raw_frame, textvariable=self.raw_var, font=("Consolas", 11)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(raw_frame, text="发送", command=self.send_raw).pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.LabelFrame(main, text="通信日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=12, state="disabled", wrap="none", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def toggle_connection(self):
        if self.connected:
            self.write_frame(self.UNLINK_FRAME)
            self.tasks.put(("close",))
            return

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
        self.write_frame(self.voltage_frame(self.clamp_voltage()))

    def apply_current(self):
        self.write_frame(self.current_frame(self.clamp_current()))

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
                self.is_output_on = False
                self.update_output_button()
                self.apply_setpoints()
                self.write_frame(self.STATUS_FRAME)
            elif event_type == "disconnected":
                self.connected = False
                self.conn_btn.config(text="连接")
                self.log(message)
            elif event_type == "error":
                self.log(f"错误: {message}")
            elif event_type == "log":
                self.log(message)

        self.root.after(100, self.drain_events)

    def log(self, message):
        now = time.strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{now}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def on_close(self):
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
#   LINK_FRAME   = "<09100000000>"
#       官方软件点击 Link 后发送，设备正常回复类似 "<19OK0000001>"。
#   UNLINK_FRAME = "<09200000000>"
#       官方软件断开连接前发送，设备正常回复类似 "<19OK0000000>"。
#
# 输出开关：
#   OUTPUT_ON_FRAME  = "<07000000000>"
#       打开电源输出端子。
#   OUTPUT_OFF_FRAME = "<08000000000>"
#       关闭电源输出端子。
#
# 状态查询：
#   STATUS_FRAME = "<04003300000>"
#       官方软件周期性发送的状态/采集帧之一，设备回复可能类似
#       "<14000000001>" 或 "<C4000620000>"。当前程序只记录回复，不解析显示。
#
# 电压设置：
#   格式："<01" + 电压值 + "0000>"
#   电压值 = round(电压 * 100)，补齐 5 位。
#   例：
#       12.00V -> 1200 -> "01200" -> "<01012000000>"
#       14.52V -> 1452 -> "01452" -> "<01014520000>"
#
# 电流设置：
#   格式："<03" + 电流值 + "000>"
#   电流值 = round(电流 * 1000)，补齐 6 位。
#   例：
#       2.000A -> 2000 -> "002000" -> "<03002000000>"
#       3.123A -> 3123 -> "003123" -> "<03003123000>"
#
# 读回说明：
#   Bus Hound 里的 OUT 是电脑发给电源，IN 是电源回复电脑。
#   程序每发送一帧后会读取 13 字节回复，正常应看到类似 "<13OK0000001>"。
# =====================================================================
