# pylint: disable=broad-exception-caught,no-self-use,import-error
# cSpell:ignore hidapi pywinusb
import importlib
import random
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Callable


VID = 0x16C0
PID = 0x05DF
DEVICE_NAME = "HW341"
PRODUCT_KEYWORD = "USBRelay"
CHANNEL_COUNT = 4
CHANNEL_DISPLAY_ORDER = [4, 3, 2, 1]
LOG_FILE_NAME = "mangetic_relay_test.txt"

CMD_ALL_CLOSE = [0xFE, 0, 0, 0, 0, 0, 0, 0]
CMD_ALL_OPEN = [0xFC, 0, 0, 0, 0, 0, 0, 0]


def channel_close_command(channel):
    return [0xFF, channel, 0, 0, 0, 0, 0, 0]


def channel_open_command(channel):
    return [0xFD, channel, 0, 0, 0, 0, 0, 0]


@dataclass
class RelayDeviceInfo:
    backend: str
    path: object
    name: str = DEVICE_NAME
    product: str = ""
    manufacturer: str = ""

    def log_path(self):
        text = str(self.path)
        if isinstance(self.path, bytes):
            text = self.path.decode("utf-8", errors="ignore")
        return text


class HidApiRelayBackend:
    name = "hidapi"

    def __init__(self):
        self._hid = None
        self.hid_module()

    def hid_module(self):
        if self._hid is None:
            self._hid = importlib.import_module("hid")
        return self._hid

    def enumerate(self):
        hid = self.hid_module()
        devices = []
        for item in hid.enumerate(VID, PID):
            product = item.get("product_string") or ""
            manufacturer = item.get("manufacturer_string") or ""
            path = item.get("path")
            if PRODUCT_KEYWORD.lower() in product.lower() or path:
                devices.append(
                    RelayDeviceInfo(
                        backend=self.name,
                        path=path,
                        product=product,
                        manufacturer=manufacturer,
                    )
                )
        return devices

    def open(self, info):
        hid = self.hid_module()
        handle = hid.device()
        handle.open_path(info.path)
        handle.set_nonblocking(True)
        return handle

    def send(self, handle, command):
        payload = [0x00] + command
        try:
            handle.send_feature_report(payload)
        except Exception:
            handle.write(payload)

    def close(self, handle):
        handle.close()


class PyWinUsbRelayBackend:
    name = "pywinusb"

    def __init__(self):
        import pywinusb.hid as hid

        self.hid = hid

    def enumerate(self):
        devices = []
        for item in self.hid.find_all_hid_devices():
            if item.vendor_id != VID or item.product_id != PID:
                continue
            devices.append(
                RelayDeviceInfo(
                    backend=self.name,
                    path=item.device_path,
                    product=item.product_name or "",
                    manufacturer=item.vendor_name or "",
                )
            )
        return devices

    def open(self, info):
        for item in self.hid.find_all_hid_devices():
            if item.device_path == info.path:
                item.open()
                return item
        raise RuntimeError("未找到已选择的继电器设备")

    def send(self, handle, command):
        reports = handle.find_feature_reports()
        if not reports:
            reports = handle.find_output_reports()
        if not reports:
            raise RuntimeError("设备没有可用的 feature/output report")

        report = reports[0]
        report.set_raw_data([0x00] + command)
        report.send()

    def close(self, handle):
        handle.close()


def load_backend():
    errors = []
    for backend_cls in (HidApiRelayBackend, PyWinUsbRelayBackend):
        try:
            return backend_cls(), None
        except Exception as exc:
            errors.append(f"{backend_cls.name}: {exc}")
    return None, "未安装 HID 控制库，可安装 hidapi 或 pywinusb。\n" + "\n".join(errors)


class RelayUsbApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("USB_DELAY_APP")
        self.geometry("820x570")
        self.minsize(820, 570)
        self.resizable(False, False)

        self.backend, backend_error = load_backend()
        self.devices = []
        self.selected_info = None
        self.handle = None
        self.command_lock = threading.Lock()
        self.loop_running = False
        self.loop_thread = None
        self.loop_count = 0
        self.loop_count_var = tk.StringVar(value="循环次数：0")
        self.log_file_path = Path(__file__).resolve().with_name(LOG_FILE_NAME)
        self.log_file_error_reported = False
        self.relay_closed = [False] * CHANNEL_COUNT
        self.action_widgets = []

        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if backend_error:
            self.log(backend_error)
        self.log("程序已启动，点击“查找设备”扫描 USB HID 继电器。")

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#f4f5f7")
        style.configure("Panel.TLabelframe", background="#f4f5f7", padding=8)
        style.configure("Panel.TLabelframe.Label", background="#f4f5f7", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TLabel", background="#f4f5f7", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 9))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Danger.TButton", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TCheckbutton", background="#f4f5f7", font=("Microsoft YaHei UI", 9))

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        device_frame = ttk.LabelFrame(root, text="设备", style="Panel.TLabelframe")
        device_frame.place(x=10, y=8, width=790, height=76)

        ttk.Button(device_frame, text="查找设备", command=self.find_devices).place(x=12, y=14, width=86, height=30)
        ttk.Button(device_frame, text="启动设备", command=self.open_device).place(x=108, y=14, width=86, height=30)
        ttk.Button(device_frame, text="释放设备", command=self.close_device).place(x=204, y=14, width=86, height=30)

        self.device_status_var = tk.StringVar(value="未连接")
        ttk.Label(device_frame, text="状态：").place(x=315, y=20)
        self.device_status_label = tk.Label(
            device_frame,
            textvariable=self.device_status_var,
            width=14,
            bg="#cfd6df",
            fg="#1f2933",
            relief="groove",
            font=("Microsoft YaHei UI", 9),
        )
        self.device_status_label.place(x=360, y=16, height=28)

        self.device_count_var = tk.StringVar(value="设备数量：0")
        ttk.Label(device_frame, textvariable=self.device_count_var).place(x=500, y=20)

        relay_frame = ttk.LabelFrame(root, text="四路继电器独立控制", style="Panel.TLabelframe")
        relay_frame.place(x=10, y=94, width=500, height=220)

        headers = ("通道", "当前状态", "单独控制", "参与循环")
        for col, text in enumerate(headers):
            ttk.Label(relay_frame, text=text).place(x=(18, 100, 210, 360)[col], y=10)

        self.channel_status_vars: dict[int, tk.StringVar] = {}
        self.channel_status_labels: dict[int, tk.Label] = {}
        self.channel_loop_vars: dict[int, tk.BooleanVar] = {}
        self.channel_loop_buttons: dict[int, tk.Button] = {}

        for row_index, channel in enumerate(CHANNEL_DISPLAY_ORDER):
            y = 42 + row_index * 38
            ttk.Label(relay_frame, text=f"{channel}").place(x=28, y=y + 5)

            status_var = tk.StringVar(value="断开")
            status_label = tk.Label(
                relay_frame,
                textvariable=status_var,
                width=8,
                bg="#dbe3ea",
                fg="#263238",
                relief="groove",
                font=("Microsoft YaHei UI", 9),
            )
            status_label.place(x=92, y=y, height=28)
            self.channel_status_vars[channel] = status_var
            self.channel_status_labels[channel] = status_label

            close_button = ttk.Button(relay_frame, text="闭合", command=lambda ch=channel: self.set_channel(ch, True))
            close_button.place(x=190, y=y, width=70, height=28)
            self.action_widgets.append(close_button)

            open_button = ttk.Button(relay_frame, text="断开", command=lambda ch=channel: self.set_channel(ch, False))
            open_button.place(x=270, y=y, width=70, height=28)
            self.action_widgets.append(open_button)

            loop_var = tk.BooleanVar(value=True)
            self.channel_loop_vars[channel] = loop_var
            loop_button = tk.Button(
                relay_frame,
                text="●",
                width=2,
                bd=0,
                cursor="hand2",
                font=("Microsoft YaHei UI", 12, "bold"),
                fg="#1b7f5a",
                bg="#f4f5f7",
                activebackground="#f4f5f7",
                command=lambda ch=channel: self.toggle_loop_channel(ch),
            )
            loop_button.place(x=374, y=y, width=34, height=28)
            self.channel_loop_buttons[channel] = loop_button

        all_frame = ttk.LabelFrame(root, text="全部控制", style="Panel.TLabelframe")
        all_frame.place(x=520, y=94, width=280, height=94)

        all_close_button = ttk.Button(all_frame, text="全部闭合", style="Accent.TButton", command=lambda: self.set_all(True))
        all_close_button.place(x=18, y=18, width=110, height=34)
        self.action_widgets.append(all_close_button)

        all_open_button = ttk.Button(all_frame, text="全部断开", style="Danger.TButton", command=lambda: self.set_all(False))
        all_open_button.place(x=148, y=18, width=110, height=34)
        self.action_widgets.append(all_open_button)

        loop_frame = ttk.LabelFrame(root, text="随机循环测试", style="Panel.TLabelframe")
        loop_frame.place(x=520, y=198, width=280, height=140)

        self.min_close_var = tk.StringVar(value="10")
        self.max_close_var = tk.StringVar(value="20")
        self.open_wait_var = tk.StringVar(value="5")

        ttk.Label(loop_frame, text="闭合最小").place(x=16, y=12)
        ttk.Entry(loop_frame, textvariable=self.min_close_var, width=6).place(x=76, y=9, height=24)
        ttk.Label(loop_frame, text="s").place(x=122, y=12)

        ttk.Label(loop_frame, text="闭合最大").place(x=150, y=12)
        ttk.Entry(loop_frame, textvariable=self.max_close_var, width=6).place(x=210, y=9, height=24)
        ttk.Label(loop_frame, text="s").place(x=256, y=12)

        ttk.Label(loop_frame, text="断开时间").place(x=16, y=50)
        ttk.Entry(loop_frame, textvariable=self.open_wait_var, width=6).place(x=76, y=47, height=24)
        ttk.Label(loop_frame, text="s").place(x=122, y=50)

        self.loop_button = ttk.Button(loop_frame, text="启动循环", command=self.toggle_loop)
        self.loop_button.place(x=172, y=44, width=86, height=30)
        self.action_widgets.append(self.loop_button)

        loop_count_label = tk.Label(
            loop_frame,
            textvariable=self.loop_count_var,
            bg="#e8eef5",
            fg="#1f2933",
            relief="groove",
            anchor="center",
            font=("Microsoft YaHei UI", 9),
        )
        loop_count_label.place(x=16, y=86, width=242, height=28)

        log_frame = ttk.LabelFrame(root, text="STATE", style="Panel.TLabelframe")
        log_frame.place(x=10, y=348, width=790, height=194)

        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            wrap="word",
            relief="flat",
            bg="#fbfbfb",
        )
        self.log_box.pack(fill="both", expand=True, padx=2, pady=2)
        self.set_action_controls_enabled(False)

    def log(self, text):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {text}\n"
        self.log_box.insert(tk.END, line)
        self.log_box.see(tk.END)
        self.write_log_file(line)

    def write_log_file(self, line):
        try:
            with self.log_file_path.open("a", encoding="utf-8") as file:
                file.write(line)
        except Exception as exc:
            if not self.log_file_error_reported:
                self.log_file_error_reported = True
                self.log_box.insert(tk.END, f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 日志文件写入失败：{exc}\n")
                self.log_box.see(tk.END)

    def ui_call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self.after(0, lambda: func(*args, **kwargs))

    def set_action_controls_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        ttk_state = ["!disabled"] if enabled else ["disabled"]

        for widget in self.action_widgets:
            try:
                widget.state(ttk_state)
            except Exception:
                widget.configure(state=state)

    def toggle_loop_channel(self, channel):
        current = self.channel_loop_vars[channel].get()
        self.channel_loop_vars[channel].set(not current)
        self.update_loop_channel_button(channel)

    def update_loop_channel_button(self, channel):
        selected = self.channel_loop_vars[channel].get()
        button = self.channel_loop_buttons[channel]
        button.configure(
            text="●" if selected else "○",
            fg="#1b7f5a" if selected else "#7b8794",
        )

    def find_devices(self):
        self.devices = []
        self.selected_info = None

        if not self.backend:
            self.log("查找失败：未安装 HID 控制库。请执行 pip install hidapi 或 pip install pywinusb")
            return

        try:
            self.devices = self.backend.enumerate()
        except Exception as exc:
            self.log(f"查找设备失败：{exc}")
            return

        for item in self.devices:
            self.log(f"NUM={item.name},BACKEND={item.backend},PATH={item.log_path()}")

        if self.devices:
            self.selected_info = self.devices[0]
            self.log(f"共找到{len(self.devices)}个设备，默认选择第1个。")
        else:
            self.log("共找到0个设备。")

        self.device_count_var.set(f"设备数量：{len(self.devices)}")

    def open_device(self):
        if self.handle:
            self.log(f"设备 [{DEVICE_NAME}] 已启动。")
            return True

        if not self.selected_info:
            self.find_devices()

        if not self.selected_info:
            self.log("启动设备失败：未找到继电器设备。")
            return False

        try:
            self.handle = self.backend.open(self.selected_info)
            self.device_status_var.set("已连接")
            self.device_status_label.configure(bg="#c9ead1", fg="#14532d")
            self.set_action_controls_enabled(True)
            self.log(f"设备 [{DEVICE_NAME}] 打开成功。")
            return True
        except Exception as exc:
            self.handle = None
            self.device_status_var.set("连接失败")
            self.device_status_label.configure(bg="#f8d7da", fg="#842029")
            self.set_action_controls_enabled(False)
            self.log(f"设备 [{DEVICE_NAME}] 打开失败：{exc}")
            return False

    def close_device(self):
        self.loop_running = False
        self.loop_button.configure(text="启动循环")

        if self.handle and self.backend:
            try:
                self.backend.close(self.handle)
            except Exception as exc:
                self.log(f"释放设备异常：{exc}")

        self.handle = None
        self.device_status_var.set("未连接")
        self.device_status_label.configure(bg="#cfd6df", fg="#1f2933")
        self.set_action_controls_enabled(False)
        self.log("设备已释放。")

    def send_command(self, command, success_text):
        if not self.handle:
            self.log("设备未连接，请先点击“启动设备”。")
            return False

        try:
            with self.command_lock:
                self.backend.send(self.handle, command)
            self.log(success_text)
            return True
        except Exception as exc:
            self.log(f"发送命令失败：{exc}")
            self.close_device()
            return False

    def set_channel(self, channel, closed):
        if closed:
            ok = self.send_command(channel_close_command(channel), f"第{channel}路继电器闭合成功。")
        else:
            ok = self.send_command(channel_open_command(channel), f"第{channel}路继电器断开成功。")

        if ok:
            self.relay_closed[channel - 1] = closed
            self.update_channel_status(channel)
        return ok

    def set_all(self, closed):
        if closed:
            ok = self.send_command(CMD_ALL_CLOSE, "全部继电器闭合成功。")
        else:
            ok = self.send_command(CMD_ALL_OPEN, "全部继电器断开成功。")

        if ok:
            self.relay_closed = [closed] * CHANNEL_COUNT
            self.update_all_status()
        return ok

    def update_channel_status(self, channel):
        index = channel - 1
        closed = self.relay_closed[index]
        self.channel_status_vars[channel].set("闭合" if closed else "断开")
        if closed:
            self.channel_status_labels[channel].configure(bg="#c9ead1", fg="#14532d")
        else:
            self.channel_status_labels[channel].configure(bg="#dbe3ea", fg="#263238")

    def update_all_status(self):
        for channel in range(1, CHANNEL_COUNT + 1):
            self.update_channel_status(channel)

    def read_loop_config(self):
        try:
            min_close = float(self.min_close_var.get())
            max_close = float(self.max_close_var.get())
            open_wait = float(self.open_wait_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "闭合最小、闭合最大、断开时间必须是数字。")
            return None

        if min_close < 0 or max_close < 0 or open_wait < 0:
            messagebox.showerror("参数错误", "时间不能小于 0。")
            return None

        if min_close > max_close:
            messagebox.showerror("参数错误", "闭合最小不能大于闭合最大。")
            return None

        channels = [channel for channel in range(1, CHANNEL_COUNT + 1) if self.channel_loop_vars[channel].get()]
        if not channels:
            messagebox.showerror("参数错误", "请至少勾选一个参与循环的继电器。")
            return None

        return min_close, max_close, open_wait, channels

    def toggle_loop(self):
        if self.loop_running:
            self.stop_loop()
            return

        config = self.read_loop_config()
        if config is None:
            return

        if not self.handle:
            self.log("设备未连接，请先点击“启动设备”。")
            return

        self.reset_loop_count()
        self.loop_running = True
        self.loop_button.configure(text="停止循环")
        self.loop_thread = threading.Thread(target=self.loop_worker, args=config, daemon=True)
        self.loop_thread.start()
        self.log("随机循环测试启动。")

    def stop_loop(self):
        self.loop_running = False
        self.loop_button.configure(text="启动循环")
        self.log("随机循环测试停止。")

    def reset_loop_count(self):
        self.loop_count = 0
        self.loop_count_var.set("循环次数：0")

    def increment_loop_count(self):
        self.loop_count += 1
        self.loop_count_var.set(f"循环次数：{self.loop_count}")

    def loop_worker(self, min_close, max_close, open_wait, channels):
        while self.loop_running:
            close_seconds = random.uniform(min_close, max_close)
            channel_text = ",".join(str(item) for item in channels)

            if not self.thread_set_channels(channels, True):
                break
            self.ui_call(self.log, f"循环：第{channel_text}路闭合，持续 {close_seconds:.1f} 秒。")
            if not self.sleep_interruptible(close_seconds):
                break

            if not self.thread_set_channels(channels, False):
                break
            self.ui_call(self.log, f"循环：第{channel_text}路断开，持续 {open_wait:.1f} 秒。")
            if not self.sleep_interruptible(open_wait):
                break

            self.ui_call(self.increment_loop_count)

        self.loop_running = False
        self.ui_call(self.loop_button.configure, text="启动循环")

    def thread_set_channels(self, channels, closed):
        try:
            with self.command_lock:
                if len(channels) == CHANNEL_COUNT:
                    command = CMD_ALL_CLOSE if closed else CMD_ALL_OPEN
                    self.backend.send(self.handle, command)
                else:
                    for channel in channels:
                        command = channel_close_command(channel) if closed else channel_open_command(channel)
                        self.backend.send(self.handle, command)
                        time.sleep(0.05)

            for channel in channels:
                self.relay_closed[channel - 1] = closed
                self.ui_call(self.update_channel_status, channel)
            return True
        except Exception as exc:
            self.ui_call(self.log, f"循环发送命令失败：{exc}")
            self.ui_call(self.close_device)
            return False

    def sleep_interruptible(self, seconds):
        end_at = time.time() + seconds
        while self.loop_running and time.time() < end_at:
            time.sleep(min(0.2, max(0, end_at - time.time())))
        return self.loop_running

    def on_close(self):
        self.loop_running = False
        if self.handle and self.backend:
            try:
                self.backend.close(self.handle)
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = RelayUsbApp()
    app.mainloop()


# ============================== 程序说明 ==============================
# 1. 设备是怎么找到的，依据是什么？
#    你给的 Bus Hound 日志里显示继电器设备为 USB HID 设备，不是普通 COM 串口设备：
#      - VID = 16C0
#      - PID = 05DF
#      - 产品字符串里出现 USBRelay4
#      - 设备返回 HW341
#    所以本程序查找设备时，不去扫描“端口 COM 和 LPT”，而是通过 hidapi/pywinusb
#    枚举 USB HID 设备，并筛选 VID_16C0、PID_05DF 的设备。
#
# 2. 为什么设备可能不在端口里显示？
#    这个继电器是 HID 类设备，Windows 通常会把它显示在“人体学输入设备”、
#    “USB 输入设备”或“通用串行总线设备”相关分类里。只有 USB 转串口芯片，
#    例如 CH340、CP210x、FTDI，才会显示成 COM 端口。
#
# 3. 四路继电器怎么控制？
#    日志里的 8 字节 HID 命令规律如下：
#      - FE 00 00 00 00 00 00 00  -> 全部闭合
#      - FC 00 00 00 00 00 00 00  -> 全部断开
#      - FF NN 00 00 00 00 00 00  -> 第 NN 路闭合，NN 为 1~4
#      - FD NN 00 00 00 00 00 00  -> 第 NN 路断开，NN 为 1~4
#    hidapi/pywinusb 发送时前面还会补一个 Report ID：00。
#    实际发送数组形如：00 FE 00 00 00 00 00 00 00。
#
# 4. 当前软件是否支持自定义闭合最小、闭合最大、断开时间？
#    支持。界面“随机循环测试”里有三个输入框：
#      - 闭合最小：例如 10 秒
#      - 闭合最大：例如 20 秒
#      - 断开时间：例如 5 秒
#    每次循环开始闭合时，会用 random.uniform(闭合最小, 闭合最大)
#    生成一个随机闭合时间，所以闭合时间是范围随机数。
#    断开时间不是随机数，按输入框里的固定秒数等待，也可以自定义。
#
# 5. 随机循环的运行逻辑是什么？
#    点击“启动循环”后：
#      1) 读取闭合最小、闭合最大、断开时间。
#      2) 读取勾选的“参与循环”继电器通道。
#      3) 检查设备是否已启动；未连接时不允许启动循环。
#      4) 随机生成本轮闭合时间。
#      5) 对勾选通道发送闭合命令。
#      6) 等待随机闭合时间。
#      7) 对勾选通道发送断开命令。
#      8) 等待固定断开时间。
#      9) 重复 4~8，直到点击“停止循环”或发送失败。
#
# 6. 单独控制和一起控制的区别是什么？
#    单独控制：
#      - 第1路闭合 -> 发送 FF 01 00 00 00 00 00 00
#      - 第1路断开 -> 发送 FD 01 00 00 00 00 00 00
#      - 第2/3/4路同理，只改变第二个字节。
#    一起控制：
#      - 全部闭合 -> 发送 FE 00 00 00 00 00 00 00
#      - 全部断开 -> 发送 FC 00 00 00 00 00 00 00
#    界面显示顺序按当前物理接线排列为 4、3、2、1。
#    显示第4路时，实际发送的也是第4路命令，不会映射成第1路。
#
# 7. 发送数据的流程是什么？
#    按钮或循环线程调用 set_channel/set_all/thread_set_channels。
#    程序先检查设备是否已打开，未连接时直接拒绝发送；已连接时进入 command_lock，
#    避免多个命令同时写 HID。
#    最后通过当前可用的后端发送：
#      - hidapi：优先 send_feature_report，失败后尝试 write
#      - pywinusb：优先 feature report，没有则尝试 output report
#
# 8. 注意事项
#    如果程序能打开界面但查找失败，多数是 HID 控制库未安装，执行：
#      pip install hidapi
#    或：
#      pip install pywinusb
#    如果仍找不到设备，请在设备管理器里查看是否存在 VID_16C0&PID_05DF。
