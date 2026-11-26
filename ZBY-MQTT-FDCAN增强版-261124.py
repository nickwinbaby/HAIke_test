#!/usr/bin/env python3
# mqtt_aes_tool_pro_v2_final.py
# PyInstaller --noconfirm --clean --onefile --windowed --name "ZBY MQTT Data Tools-20261124" --icon "bulid_photos\MQTT_ZBY.ico" --add-data "bulid_photos\MQTT_ZBY.ico;bulid_photos" --add-data "bulid_photos\MQTT_ZBY.png;bulid_photos" --add-data "bulid_photos\Mangetic.png;bulid_photos" "ZBY-MQTT-FDCAN增强版-261124.py"
# 单文件：严格显示 FIFO（默认2000条），保存全部数据，GT115_ZBY/Raw Data 下拉，JSON 彩色渲染
# 新增：
# 1. GT115_ZBY 模式下，QoS 后显示：解密成功 / 解密失败
# 2. 解密失败时，显示并保存原始 HEX 数据；解密成功时不显示原始 HEX
#
# 依赖: paho-mqtt, pycryptodome, pillow
# pip install paho-mqtt pycryptodome pillow

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
import json
import os
import sys
import queue
import time
import logging
import uuid
import ctypes

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from PIL import Image, ImageTk

# ----------------------------
# CONFIG
# ----------------------------
FIXED_KEY_HEX = "d3f67a2e5b8c901f4a6d0e3c7b291f5d8e4c2a1b0f9e8d7c6b5a493827161514"
DEFAULT_MAX_MESSAGES = 2000
PAUSED_OUTPUT_LIMIT = 4000
TOPICS_SAVE_FILE = "topics.json"
RECONNECT_INTERVAL = 5  # seconds between reconnect attempts
CONNECT_TIMEOUT_MS = 10000
DISCONNECT_TIMEOUT_MS = 3000
APP_NAME = "ZBY MQTT Data Tools"
APP_RELEASE_DATE = "2026-11-24"
APP_NOTICE = "※瑞联内部工具，谢绝外发※"
APP_CONTACT = "guomengyao@gosuncn.com"
WATERMARK_RELATIVE_PATH = os.path.join("bulid_photos", "Mangetic.png")
WATERMARK_SIZE = (240, 80)
WATERMARK_OPACITY = 0.18
WATERMARK_MARGIN = 14
WINDOW_ICON_ICO = os.path.join("bulid_photos", "MQTT_ZBY.ico")
WINDOW_ICON_PNG = os.path.join("bulid_photos", "MQTT_ZBY.png")
WINDOWS_APP_ID = "RichLink.ZBY.MQTT.DataTools"

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

def hex_to_bytes(hex_str):
    return bytes.fromhex(hex_str)

KEY_BYTES = hex_to_bytes(FIXED_KEY_HEX)

# 固定 IV
IV_BYTES = bytes.fromhex("19e4f7a83d0b6c25a81234567890abcd")


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """返回开发环境或 PyInstaller 单文件环境中的资源路径。"""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)


def topic_file_path():
    return os.path.join(app_base_dir(), TOPICS_SAVE_FILE)

def decrypt_encrypted_string(encrypted_bytes: bytes) -> str:
    """
    AES256-CBC 解密，固定 KEY_BYTES 和 IV_BYTES。
    encrypted_bytes: 接收到的原始加密 bytes 数据
    返回解密后的 UTF-8 字符串
    """
    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, IV_BYTES)
    plain = cipher.decrypt(encrypted_bytes)

    try:
        plain = unpad(plain, AES.block_size)
    except ValueError:
        # 如果 padding 不正确，不中断，继续尝试 decode
        pass

    return plain.decode("utf-8", errors="ignore")


def encrypt_json_payload(json_text: str):
    """
    校验 JSON 格式，再将用户输入的原文按 AES-256-CBC + PKCS7 加密。

    JSON 中的空格、换行也是明文的一部分，不做压缩或重排，
    以便与在线 AES 工具按原文加密的结果保持一致。

    返回:
        encrypted_bytes -> 用于 MQTT 发布的密文字节
        source_json     -> 实际参与加密的 UTF-8 JSON 原文
    """
    source_json = json_text.strip()
    json.loads(source_json)
    plain_bytes = source_json.encode("utf-8")
    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, IV_BYTES)
    encrypted_bytes = cipher.encrypt(pad(plain_bytes, AES.block_size, style="pkcs7"))
    return encrypted_bytes, source_json

def parse_gt115_payload(payload_bytes: bytes):
    """
    GT115_ZBY 模式统一解析函数

    返回:
        obj             -> 用于显示/保存的数据对象
        decrypt_status  -> "解密成功" / "解密失败"
        failed_hex      -> 如果失败，返回原始HEX；成功则为 None

    判定标准：
    - 先 AES 解密
    - 再 json.loads()
    - 只有 JSON 解析成功才算“解密成功”
    """
    failed_hex = payload_bytes.hex().upper()

    try:
        decrypted = decrypt_encrypted_string(payload_bytes)
        obj = json.loads(decrypted)
        return obj, "解密成功", None
    except Exception as e:
        obj = {
            "decrypt_status": "解密失败",
            "error": str(e),
            "raw_hex": failed_hex
        }
        return obj, "解密失败", failed_hex

# ----------------------------
# 主应用
# ----------------------------
class MQTT_AES_Pro_v2(tk.Tk):
    def __init__(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
            except (AttributeError, OSError):
                pass
        super().__init__()
        self.title(f"{APP_NAME}    {APP_RELEASE_DATE}    {APP_NOTICE}    {APP_CONTACT}")
        self.geometry("1220x720")
        self.minsize(980, 620)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._native_icon_handles = []
        self._icon_refresh_after_id = None
        self._configure_window_icon()
        self.bind("<Map>", self._on_window_mapped, add="+")

        # MQTT
        self.client = None
        self.client_thread = None
        self.mqtt_connected = False
        self.connection_phase = "disconnected"
        self._connection_timeout_after_id = None
        self.auto_reconnect_enabled = True
        self._stop_event = threading.Event()
        self._connect_ready_event = threading.Event()
        self._manual_disconnect = False  # 手动断开标记，用于避免自动重连

        # Display FIFO
        self.max_messages = DEFAULT_MAX_MESSAGES
        self.message_blocks = deque()

        # Counters
        self.total_received = 0
        self.total_saved = 0

        # UI queue: mqtt -> ui
        # item: (timestamp, topic, qos, payload_obj, decrypt_status)
        self.ui_queue = queue.Queue(maxsize=20000)

        # Save file
        self.saving_enabled = False
        self.save_file = None
        self.save_lock = threading.Lock()

        # GT mode
        self.gt_mode_var = tk.StringVar(value="ZBY 解密")

        # FDCAN工具
        self.fdcan_visible = False

        # 订阅主题自动保存
        self._loading_topics = False
        self._topics_save_after_id = None
        self.notes_visible = False

        # Build UI
        self._configure_styles()
        self._build_ui()

        # Start ui queue processing
        self.after(60, self._process_ui_queue)

        # Load topics
        self._load_topics_from_disk()
        # 首次显示后固定左右面板比例，避免 Panedwindow 初始宽度为 1 的闪动。
        self.after(20, self._stabilize_initial_layout)

    # -------------------------
    # UI building
    # -------------------------
    def _configure_window_icon(self):
        """设置 Tk 窗口、Windows 标题栏和任务栏运行图标。"""
        ico_path = resource_path(WINDOW_ICON_ICO)
        png_path = resource_path(WINDOW_ICON_PNG)

        if os.path.isfile(png_path):
            try:
                with Image.open(png_path) as source:
                    source = source.convert("RGBA")
                    resampling = getattr(Image, "Resampling", Image).LANCZOS
                    source.thumbnail((256, 256), resampling)
                    self._window_icon_photo = ImageTk.PhotoImage(source)
                self.iconphoto(True, self._window_icon_photo)
            except (OSError, ValueError, tk.TclError) as e:
                logging.warning("PNG 窗口图标加载失败: %s", e)

        if not os.path.isfile(ico_path):
            logging.warning("ICO 窗口图标不存在: %s", ico_path)
            return

        try:
            self.iconbitmap(default=ico_path)
        except tk.TclError as e:
            logging.warning("Tk ICO 窗口图标设置失败: %s", e)

        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            load_image = user32.LoadImageW
            load_image.argtypes = [
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            load_image.restype = ctypes.c_void_p
            handles = [
                load_image(None, ico_path, 1, 16, 16, 0x10),
                load_image(None, ico_path, 1, 32, 32, 0x10),
            ]
            self._native_icon_handles = [handle for handle in handles if handle]
            self._schedule_window_icon_refresh()
        except (AttributeError, OSError, TypeError) as e:
            logging.warning("Windows 原生窗口图标设置失败: %s", e)

    def _on_window_mapped(self, event):
        if event.widget is self:
            self._schedule_window_icon_refresh()

    def _schedule_window_icon_refresh(self):
        """在 Windows 顶级窗口真正创建后补设图标，避免 Tk 映射时覆盖。"""
        if self._icon_refresh_after_id is not None:
            try:
                self.after_cancel(self._icon_refresh_after_id)
            except (tk.TclError, ValueError):
                pass
        self._icon_refresh_after_id = self.after_idle(self._refresh_window_icon_after_map)

    def _refresh_window_icon_after_map(self):
        self._icon_refresh_after_id = None
        ico_path = resource_path(WINDOW_ICON_ICO)
        try:
            if os.path.isfile(ico_path):
                self.iconbitmap(default=ico_path)
        except tk.TclError:
            pass
        try:
            if hasattr(self, "_window_icon_photo"):
                self.iconphoto(True, self._window_icon_photo)
        except tk.TclError:
            pass
        self._apply_native_window_icons()
        # Tk 的外层 HWND 可能比 <Map> 晚一个消息循环完成，再补设一次。
        self.after(120, self._apply_native_window_icons)

    def _apply_native_window_icons(self):
        if sys.platform != "win32" or len(self._native_icon_handles) < 2:
            return
        try:
            user32 = ctypes.windll.user32
            get_ancestor = user32.GetAncestor
            get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            get_ancestor.restype = ctypes.c_void_p
            send_message = user32.SendMessageW
            send_message.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            send_message.restype = ctypes.c_void_p
            child_hwnd = self.winfo_id()
            root_hwnd = get_ancestor(child_hwnd, 2)
            for target_hwnd in {child_hwnd, root_hwnd}:
                if not target_hwnd:
                    continue
                send_message(target_hwnd, 0x0080, 0, self._native_icon_handles[0])
                send_message(target_hwnd, 0x0080, 1, self._native_icon_handles[1])
        except (AttributeError, OSError, TypeError, tk.TclError):
            pass

    def _configure_styles(self):
        """配置统一的浅色卡片风格。"""
        self.configure(bg="#F3F6FA")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # 移除 clam 主题在按钮、下拉菜单和复选框获得焦点时的虚线框。
        style.layout("TButton", [
            ("Button.border", {
                "sticky": "nswe",
                "border": "1",
                "children": [
                    ("Button.padding", {
                        "sticky": "nswe",
                        "children": [("Button.label", {"sticky": "nswe"})],
                    }),
                ],
            }),
        ])
        style.layout("TMenubutton", [
            ("Menubutton.border", {
                "sticky": "nswe",
                "children": [
                    ("Menubutton.indicator", {"side": "right", "sticky": ""}),
                    ("Menubutton.padding", {
                        "sticky": "we",
                        "children": [("Menubutton.label", {"side": "left", "sticky": ""})],
                    }),
                ],
            }),
        ])
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {
                "sticky": "nswe",
                "children": [
                    ("Checkbutton.indicator", {"side": "left", "sticky": ""}),
                    ("Checkbutton.label", {"side": "left", "sticky": "w"}),
                ],
            }),
        ])

        normal_font = ("Microsoft YaHei UI", 9)
        bold_font = ("Microsoft YaHei UI", 9, "bold")
        style.configure(".", font=normal_font)
        style.configure("App.TFrame", background="#F3F6FA")
        style.configure("Header.TFrame", background="#17324D")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure(
            "Card.TLabelframe",
            background="#FFFFFF",
            bordercolor="#D9E2EC",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background="#FFFFFF",
            foreground="#183B56",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure("Card.TLabel", background="#FFFFFF", foreground="#334E68")
        style.configure("Muted.TLabel", background="#FFFFFF", foreground="#829AB1")
        style.configure("Footer.TLabel", background="#F3F6FA", foreground="#486581")
        style.configure("Card.TCheckbutton", background="#FFFFFF", foreground="#334E68")
        style.map("Card.TCheckbutton", background=[("active", "#FFFFFF")])
        style.configure("TEntry", padding=3, fieldbackground="#FFFFFF", foreground="#102A43")
        style.configure("TSpinbox", padding=3, fieldbackground="#FFFFFF")
        style.configure("TButton", padding=(8, 4), borderwidth=1)
        style.configure("Compact.TButton", padding=(6, 2), borderwidth=1, font=("Microsoft YaHei UI", 8))
        style.configure(
            "ToggleActive.TButton",
            padding=(6, 2),
            borderwidth=1,
            background="#DBEAFE",
            foreground="#1D4ED8",
            bordercolor="#60A5FA",
            font=("Microsoft YaHei UI", 8, "bold"),
        )
        style.map(
            "ToggleActive.TButton",
            background=[("active", "#BFDBFE"), ("pressed", "#93C5FD")],
            foreground=[("disabled", "#94A3B8")],
        )
        style.configure("RowDelete.TButton", padding=(4, 1), borderwidth=1, foreground="#B42318", font=("Microsoft YaHei UI", 8))
        style.configure("Enabled.TButton", padding=(4, 1), borderwidth=1, background="#DCFCE7", foreground="#166534", font=("Microsoft YaHei UI", 8))
        style.map("Enabled.TButton", background=[("active", "#BBF7D0")])
        style.configure("Disabled.TButton", padding=(4, 1), borderwidth=1, background="#F1F5F9", foreground="#64748B", font=("Microsoft YaHei UI", 8))
        style.map("Disabled.TButton", background=[("active", "#E2E8F0")])
        style.configure(
            "Primary.TButton",
            background="#2563EB",
            foreground="#FFFFFF",
            bordercolor="#2563EB",
            font=bold_font,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1D4ED8"), ("disabled", "#AFC5EC")],
            foreground=[("disabled", "#F8FAFC")],
        )
        style.configure(
            "Disconnect.TButton",
            background="#FEE2E2",
            foreground="#B91C1C",
            bordercolor="#FCA5A5",
            font=bold_font,
        )
        style.map(
            "Disconnect.TButton",
            background=[("active", "#FECACA"), ("pressed", "#FCA5A5")],
        )
        style.configure("Danger.TButton", foreground="#B42318")
        style.configure("Pane.TPanedwindow", background="#F3F6FA")

    def _make_text_box(self, parent, **kwargs):
        """创建统一样式的文本框。"""
        options = {
            "font": ("Consolas", 9),
            "background": "#F8FAFC",
            "foreground": "#102A43",
            "insertbackground": "#2563EB",
            "relief": "flat",
            "borderwidth": 0,
            "highlightthickness": 1,
            "highlightbackground": "#CBD5E1",
            "highlightcolor": "#2563EB",
            "padx": 5,
            "pady": 4,
        }
        options.update(kwargs)
        return tk.Text(parent, **options)

    def _setup_output_watermark(self, parent):
        """在输出区右下角放置固定的半透明水印。"""
        image_path = resource_path(WATERMARK_RELATIVE_PATH)
        if not os.path.exists(image_path):
            logging.warning("水印图片不存在: %s", image_path)
            return
        try:
            with Image.open(image_path) as source:
                source = source.convert("RGBA")
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                source.thumbnail(WATERMARK_SIZE, resampling)
                prepared = Image.new("RGBA", WATERMARK_SIZE, (0, 0, 0, 0))
                paste_x = (WATERMARK_SIZE[0] - source.width) // 2
                paste_y = (WATERMARK_SIZE[1] - source.height) // 2
                prepared.alpha_composite(source, (paste_x, paste_y))
                alpha = prepared.getchannel("A").point(
                    lambda value: int(value * WATERMARK_OPACITY)
                )
                prepared.putalpha(alpha)
                self.output_watermark_photo = ImageTk.PhotoImage(prepared)
        except Exception as e:
            logging.exception("水印图片加载失败: %s", e)
            return

        background = self.text_display.cget("background")
        self.output_watermark_label = tk.Label(
            parent,
            image=self.output_watermark_photo,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            takefocus=0,
        )
        horizontal_inset = (
            int(self.text_display.cget("padx"))
            + int(self.text_display.cget("highlightthickness"))
            + int(self.text_display.cget("borderwidth"))
        )
        vertical_inset = (
            int(self.text_display.cget("pady"))
            + int(self.text_display.cget("highlightthickness"))
            + int(self.text_display.cget("borderwidth"))
        )
        self.output_watermark_label.place(
            in_=self.text_display,
            relx=1.0,
            rely=1.0,
            x=-(WATERMARK_MARGIN - horizontal_inset),
            y=-(WATERMARK_MARGIN - vertical_inset),
            anchor="se",
            width=WATERMARK_SIZE[0],
            height=WATERMARK_SIZE[1],
        )
        self._watermark_raised = False
        self._watermark_refresh_pending = False
        self.output_watermark_label.lower(self.text_display)
        self.text_display.bind("<<Selection>>", self._queue_watermark_refresh, add="+")
        self.text_display.bind("<Configure>", self._queue_watermark_refresh, add="+")
        self.output_watermark_label.bind("<Configure>", self._queue_watermark_refresh, add="+")
        self._queue_watermark_refresh()

        for sequence in (
            "<ButtonPress-1>",
            "<B1-Motion>",
            "<ButtonRelease-1>",
            "<Double-Button-1>",
            "<Triple-Button-1>",
            "<ButtonPress-3>",
            "<ButtonRelease-3>",
            "<MouseWheel>",
        ):
            self.output_watermark_label.bind(
                sequence,
                lambda event, event_sequence=sequence: self._forward_watermark_event(
                    event_sequence, event
                ),
            )

    def _queue_watermark_refresh(self, event=None):
        if hasattr(self, "output_watermark_label") and not self._watermark_refresh_pending:
            self._watermark_refresh_pending = True
            self.after_idle(self._refresh_output_watermark)

    def _refresh_output_watermark(self):
        self._watermark_refresh_pending = False
        mark = self.output_watermark_label
        output = self.text_display
        left = mark.winfo_x() - output.winfo_x()
        top = mark.winfo_y() - output.winfo_y()
        bottom = top + mark.winfo_height()
        # Tk Text 的背景不透明，只在空白位置显示水印。文字和选区重叠时把水印降到文本框后面。
        show = mark.winfo_ismapped() and left >= 0 and top >= 0 and not output.tag_ranges("sel")
        y = top
        while show and y < bottom:
            bounds = output.dlineinfo(f"@0,{y}")
            if not bounds:
                break
            line_x, line_y, line_width, line_height, _ = bounds
            line_bottom = line_y + line_height
            if line_bottom <= y:
                break
            if line_y < bottom and line_x + line_width > left:
                show = False
            y = line_bottom
        if show != self._watermark_raised:
            if show:
                mark.lift(output)
            else:
                mark.lower(output)
            self._watermark_raised = show

    def _forward_watermark_event(self, sequence, event):
        """将水印上的鼠标操作透传给输出文本框。"""
        x = event.x_root - self.text_display.winfo_rootx()
        y = event.y_root - self.text_display.winfo_rooty()
        if sequence == "<ButtonPress-1>":
            self.text_display.focus_set()
        options = {"x": x, "y": y, "state": event.state}
        if sequence == "<MouseWheel>":
            options["delta"] = event.delta
        self.text_display.event_generate(sequence, **options)
        return "break"

    def _build_ui(self):
        app_frame = ttk.Frame(self, style="App.TFrame")
        app_frame.pack(fill=tk.BOTH, expand=True)

        # 页头
        header = ttk.Frame(app_frame, style="Header.TFrame", height=46)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="ZBY MQTT 数据工具",
            background="#17324D",
            foreground="#FFFFFF",
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side=tk.LEFT, padx=(12, 7), pady=7)
        tk.Label(
            header,
            text="AES 加解密 · JSON 发送 · FDCAN 解析",
            background="#17324D",
            foreground="#BCCCDC",
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT, pady=(12, 7))
        self.connection_status_label = tk.Label(
            header,
            text="●  未连接",
            background="#17324D",
            foreground="#FDA29B",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.connection_status_label.pack(side=tk.RIGHT, padx=13)

        # MQTT 连接设置
        connect_card = ttk.LabelFrame(app_frame, text=" MQTT 连接设置 ", style="Card.TLabelframe")
        connect_card.pack(fill=tk.X, padx=10, pady=(7, 5))
        connect_card.columnconfigure(1, weight=2)
        connect_card.columnconfigure(5, weight=1)
        connect_card.columnconfigure(7, weight=1)

        ttk.Label(connect_card, text="服务器", style="Card.TLabel").grid(row=0, column=0, padx=(8, 4), pady=4, sticky="w")
        self.entry_host = ttk.Entry(connect_card, width=22)
        self.entry_host.insert(0, "zte-cid.com")
        self.entry_host.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="ew")

        ttk.Label(connect_card, text="端口", style="Card.TLabel").grid(row=0, column=2, padx=(0, 4), pady=4)
        self.entry_port = ttk.Entry(connect_card, width=6)
        self.entry_port.insert(0, "1883")
        self.entry_port.grid(row=0, column=3, padx=(0, 8), pady=4)

        ttk.Label(connect_card, text="用户名", style="Card.TLabel").grid(row=0, column=4, padx=(0, 4), pady=4)
        self.entry_username = ttk.Entry(connect_card, width=11)
        self.entry_username.insert(0, "admin")
        self.entry_username.grid(row=0, column=5, padx=(0, 8), pady=4, sticky="ew")

        ttk.Label(connect_card, text="密码", style="Card.TLabel").grid(row=0, column=6, padx=(0, 4), pady=4)
        self.entry_password = ttk.Entry(connect_card, width=11, show="●")
        self.entry_password.insert(0, "Zbwd@010")
        self.entry_password.grid(row=0, column=7, padx=(0, 8), pady=4, sticky="ew")

        self.btn_connection = ttk.Button(
            connect_card,
            text="连接",
            style="Primary.TButton",
            command=self._toggle_connection,
            width=10,
        )
        self.btn_connection.grid(row=0, column=8, columnspan=2, padx=(0, 6), pady=4)

        self.auto_reconnect_var = tk.BooleanVar(value=self.auto_reconnect_enabled)
        auto_reconnect_frame = ttk.Frame(connect_card, style="Card.TFrame")
        auto_reconnect_frame.grid(row=0, column=10, padx=(0, 6), pady=4)
        self.auto_reconnect_button = tk.Canvas(
            auto_reconnect_frame,
            width=18,
            height=18,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.auto_reconnect_button.pack(side=tk.LEFT)
        self.auto_reconnect_button.bind("<Button-1>", lambda event: self._toggle_auto_reconnect())
        ttk.Label(auto_reconnect_frame, text="自动重连", style="Card.TLabel").pack(side=tk.LEFT, padx=(3, 0))
        self._refresh_auto_reconnect_button()
        ttk.Label(connect_card, text="显示行数", style="Card.TLabel").grid(row=0, column=11, padx=(0, 3), pady=4)
        self.spin_max = ttk.Spinbox(connect_card, from_=100, to=10000, width=6)
        self.spin_max.set(str(self.max_messages))
        self.spin_max.grid(row=0, column=12, padx=(0, 3), pady=4)
        ttk.Button(connect_card, text="应用", style="Compact.TButton", command=self._apply_max_messages).grid(row=0, column=13, padx=(0, 4), pady=4)
        self.btn_fdcan = ttk.Button(connect_card, text="FDCAN 解析", style="Compact.TButton", command=self.toggle_fdcan_panel)
        self.btn_fdcan.grid(row=0, column=14, padx=(0, 8), pady=4)

        self.main_pane = ttk.Panedwindow(app_frame, orient=tk.HORIZONTAL, style="Pane.TPanedwindow")
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)

        # 左侧：订阅和发送
        left_frame = ttk.Frame(self.main_pane, width=450, style="App.TFrame")
        self.main_pane.add(left_frame, weight=0)

        subscribe_card = ttk.LabelFrame(left_frame, text=" 订阅主题 ", style="Card.TLabelframe")
        subscribe_card.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        sub_header = ttk.Frame(subscribe_card, style="Card.TFrame", height=20)
        sub_header.pack(fill=tk.X, padx=(7, 20), pady=(4, 1))
        sub_header.pack_propagate(False)
        self.sub_header = sub_header
        self.sub_header_labels = {
            "enabled_button": ttk.Label(sub_header, text="状态", style="Muted.TLabel", anchor="center"),
            "topic_entry": ttk.Label(sub_header, text="MQTT 主题", style="Muted.TLabel", anchor="w"),
            "delete_button": ttk.Label(sub_header, text="删除", style="Muted.TLabel", anchor="center"),
            "note_entry": ttk.Label(sub_header, text="用途备注", style="Muted.TLabel", anchor="w"),
        }

        sub_list = ttk.Frame(subscribe_card, style="Card.TFrame")
        sub_list.pack(fill=tk.BOTH, expand=True, padx=7)
        self.sub_canvas = tk.Canvas(
            sub_list,
            height=135,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=27,
            confine=True,
        )
        sub_scroll = ttk.Scrollbar(sub_list, orient=tk.VERTICAL, command=self.sub_canvas.yview)
        self.sub_canvas.configure(yscrollcommand=sub_scroll.set)
        self.sub_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sub_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.sub_frame = ttk.Frame(self.sub_canvas, style="Card.TFrame")
        self.sub_canvas_window = self.sub_canvas.create_window((0, 0), window=self.sub_frame, anchor="nw")
        self.sub_frame.bind("<Configure>", self._refresh_subscription_scrollregion)
        self.sub_canvas.bind("<Configure>", self._resize_subscription_canvas)
        self.sub_canvas.bind("<MouseWheel>", self._scroll_subscriptions)

        self.sub_entries = []
        self._add_subscription_row("test/topic", "", True, schedule_save=False)

        btn_sub_controls = ttk.Frame(subscribe_card, style="Card.TFrame")
        btn_sub_controls.pack(fill=tk.X, padx=7, pady=(3, 6))
        ttk.Button(btn_sub_controls, text="＋ 添加主题", style="Compact.TButton", command=lambda: self._add_subscription_row("")).pack(side=tk.LEFT)
        self.notes_toggle_button = ttk.Button(
            btn_sub_controls,
            text="显示备注",
            style="Compact.TButton",
            command=self._toggle_notes_visibility,
        )
        self.notes_toggle_button.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_sub_controls, text="订阅勾选主题", style="Primary.TButton", command=self.subscribe_all).pack(side=tk.RIGHT)
        ttk.Button(btn_sub_controls, text="取消所有订阅", style="Compact.TButton", command=self.unsubscribe_all).pack(side=tk.RIGHT, padx=4)

        publish_frame = ttk.LabelFrame(left_frame, text=" AES 加密发送 ", style="Card.TLabelframe")
        publish_frame.pack(fill=tk.X)
        ttk.Label(publish_frame, text="发送主题", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(5, 2))
        self.publish_topic_entry = ttk.Entry(publish_frame)
        self.publish_topic_entry.pack(fill=tk.X, padx=7, pady=(0, 4))
        ttk.Label(publish_frame, text="JSON 数据", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(0, 2))
        self.publish_data_text = self._make_text_box(publish_frame, height=2, wrap="char")
        self.publish_data_text.pack(fill=tk.X, padx=7, pady=(0, 4))
        self.publish_data_text.bind("<Control-Return>", self._publish_shortcut)
        publish_controls = ttk.Frame(publish_frame, style="Card.TFrame")
        publish_controls.pack(fill=tk.X, padx=7, pady=(0, 6))
        self.btn_publish = ttk.Button(publish_controls, text="加密并发送", style="Primary.TButton", command=self.publish_encrypted_json)
        self.btn_publish.pack(side=tk.LEFT)
        self.publish_status_label = ttk.Label(publish_controls, text="Ctrl+Enter 快捷发送", style="Muted.TLabel")
        self.publish_status_label.pack(side=tk.LEFT, padx=6)

        # 中间可选：FDCAN 解析
        self.fdcan_frame = ttk.LabelFrame(self.main_pane, text=" FDCAN 数据解析 ", style="Card.TLabelframe", width=330)
        ttk.Label(self.fdcan_frame, text="输入 HEX 数据", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(5, 2))
        self.fdcan_input = self._make_text_box(self.fdcan_frame, height=7)
        self.fdcan_input.pack(fill=tk.X, padx=7, pady=(0, 4))
        ttk.Button(self.fdcan_frame, text="开始解析", style="Primary.TButton", command=self.parse_fdcan).pack(anchor=tk.W, padx=7, pady=(0, 5))
        ttk.Label(self.fdcan_frame, text="解析结果", style="Card.TLabel").pack(anchor=tk.W, padx=7, pady=(0, 2))
        self.fdcan_output = self._make_text_box(self.fdcan_frame, wrap="char")
        self.fdcan_output.pack(fill=tk.BOTH, expand=True, padx=7, pady=(0, 7))

        # 右侧：接收消息
        right_frame = ttk.LabelFrame(self.main_pane, text=" 接收消息 ", style="Card.TLabelframe")
        self.main_pane.add(right_frame, weight=1)
        ttk.Label(right_frame, text="实时显示 MQTT 数据和解密结果", style="Muted.TLabel").pack(anchor=tk.W, padx=7, pady=(4, 2))
        text_frame = ttk.Frame(right_frame, style="Card.TFrame")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=7, pady=(2, 7))
        self.text_display = self._make_text_box(
            text_frame,
            wrap="char",
            state=tk.DISABLED,
            highlightcolor="#CBD5E1",
        )
        self.text_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_display.yview)
        vsb.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0))
        self._wire_output_scrollbar(self.text_display, vsb)
        self._setup_output_watermark(text_frame)

        bold_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font.configure(weight="bold")
        self.text_display.tag_configure("timestamp", font=bold_font, foreground="#486581")
        self.text_display.tag_configure("topic", foreground="#2563EB")
        self.text_display.tag_configure("qos", foreground="#7C3AED")
        self.text_display.tag_configure("json_key", foreground="#C2410C")
        self.text_display.tag_configure("json_value", foreground="#047857")
        self.text_display.tag_configure("hex_error", foreground="#DC2626")
        self.text_display.tag_configure("sent_message", foreground="#2563EB")

        # 底部工具栏
        bottom_controls = ttk.Frame(app_frame, style="App.TFrame")
        bottom_controls.pack(fill=tk.X, padx=10, pady=(5, 7))
        ttk.Button(bottom_controls, text="清空显示", style="Compact.TButton", command=self.clear_display).pack(side=tk.LEFT)
        self.btn_save = ttk.Button(bottom_controls, text="开始保存日志", style="Compact.TButton", command=self.start_save)
        self.btn_save.pack(side=tk.LEFT, padx=(6, 3))
        self.btn_stop_save = ttk.Button(bottom_controls, text="停止保存", style="Compact.TButton", command=self.stop_save, state=tk.DISABLED)
        self.btn_stop_save.pack(side=tk.LEFT, padx=3)
        ttk.Label(bottom_controls, text="接收模式", style="Footer.TLabel").pack(side=tk.LEFT, padx=(12, 4))
        self.gt_mode_menu = ttk.OptionMenu(bottom_controls, self.gt_mode_var, self.gt_mode_var.get(), "ZBY 解密", "原始 HEX")
        self.gt_mode_menu.pack(side=tk.LEFT)
        self.msg_count_label = ttk.Label(bottom_controls, text=self._msg_count_text(), style="Footer.TLabel")
        self.msg_count_label.pack(side=tk.RIGHT)

    def _msg_count_text(self):
        return f"已接收：{self.total_received}    已保存：{self.total_saved}"

    def _update_msg_count_label(self):
        self.msg_count_label.config(text=self._msg_count_text())

    def _set_connection_status(self, text, color):
        self.connection_status_label.config(text=f"●  {text}", foreground=color)

    def _set_connection_phase(self, phase):
        self.connection_phase = phase
        settings = {
            "disconnected": ("连接", "Primary.TButton", tk.NORMAL),
            "connecting": ("连接", "Primary.TButton", tk.DISABLED),
            "connected": ("断开", "Disconnect.TButton", tk.NORMAL),
            "disconnecting": ("断开", "Disconnect.TButton", tk.DISABLED),
        }
        text, style, state = settings.get(phase, settings["disconnected"])
        self.btn_connection.config(text=text, style=style, state=state)

    def _toggle_connection(self):
        if self.connection_phase == "disconnected":
            self.connect_mqtt()
        elif self.connection_phase == "connected":
            self.disconnect_mqtt()

    def _clear_connection_timeout(self):
        if self._connection_timeout_after_id is None:
            return
        try:
            self.after_cancel(self._connection_timeout_after_id)
        except (tk.TclError, ValueError):
            pass
        self._connection_timeout_after_id = None

    def _start_connection_timeout(self, phase, timeout_ms):
        self._clear_connection_timeout()
        self._connection_timeout_after_id = self.after(
            timeout_ms,
            lambda expected=phase: self._handle_connection_timeout(expected),
        )

    def _handle_connection_timeout(self, expected_phase):
        self._connection_timeout_after_id = None
        if self.connection_phase != expected_phase:
            return
        self._manual_disconnect = True
        self.mqtt_connected = False
        self._connect_ready_event.set()
        try:
            if self.client:
                self.client.disconnect()
        except Exception:
            pass
        self._set_connection_phase("disconnected")
        if expected_phase == "connecting":
            self._set_connection_status("连接超时", "#FDA29B")
            self._append_plain("[错误] MQTT 连接超时，已停止本次连接。")
        else:
            self._set_connection_status("未连接", "#FDA29B")
            self._append_plain("[信息] MQTT 断开等待超时，已恢复为未连接状态。")

    def _draw_circle_toggle(self, canvas, enabled):
        canvas.delete("all")
        if enabled:
            canvas.create_oval(2, 2, 16, 16, fill="#22C55E", outline="#16A34A", width=1)
            canvas.create_text(9, 9, text="✓", fill="#FFFFFF", font=("Arial", 8, "bold"))
        else:
            canvas.create_oval(2, 2, 16, 16, fill="#FFFFFF", outline="#94A3B8", width=1)

    def _refresh_auto_reconnect_button(self):
        enabled = bool(self.auto_reconnect_var.get())
        self._draw_circle_toggle(self.auto_reconnect_button, enabled)

    def _toggle_auto_reconnect(self):
        self.auto_reconnect_var.set(not self.auto_reconnect_var.get())
        self.auto_reconnect_enabled = bool(self.auto_reconnect_var.get())
        self._refresh_auto_reconnect_button()

    # -------------------------
    # subscription rows
    # -------------------------
    def _stabilize_initial_layout(self, attempt=0):
        pane_width = self.main_pane.winfo_width()
        if pane_width < 600:
            if attempt < 12:
                self.after(50, lambda: self._stabilize_initial_layout(attempt + 1))
            return
        try:
            left_width = max(430, min(int(pane_width * 0.49), pane_width - 420))
            self.main_pane.sashpos(0, left_width)
        except Exception:
            pass
        self.update_idletasks()
        self._refresh_subscription_scrollregion()
        self._align_subscription_header()

    def _refresh_subscription_scrollregion(self, event=None):
        bbox = self.sub_canvas.bbox(self.sub_canvas_window)
        if not bbox:
            return
        visible_height = max(1, self.sub_canvas.winfo_height())
        content_height = max(bbox[3], visible_height)
        self.sub_canvas.configure(scrollregion=(0, 0, bbox[2], content_height))
        if bbox[3] <= visible_height:
            self.sub_canvas.yview_moveto(0.0)
        self.after_idle(self._align_subscription_header)

    def _resize_subscription_canvas(self, event):
        self.sub_canvas.itemconfigure(self.sub_canvas_window, width=event.width)
        self.after_idle(self._align_subscription_header)

    def _align_subscription_header(self):
        if not self.sub_entries:
            return
        first_item = self.sub_entries[0]
        for key, label in self.sub_header_labels.items():
            if key == "note_entry" and not self.notes_visible:
                label.place_forget()
                continue
            widget = first_item[key]
            x = widget.winfo_x()
            width = widget.winfo_width()
            if key == "enabled_button":
                # 状态表头使用整列宽度，不受圆形图标宽度限制。
                x = 0
                width = max(28, first_item["topic_entry"].winfo_x())
            elif key == "delete_button":
                # 删除表头使用垃圾桶图标所在的整列宽度。
                x = max(0, widget.winfo_x() - 4)
                if self.notes_visible:
                    width = max(28, first_item["note_entry"].winfo_x() - x)
                else:
                    width = max(28, first_item["row"].winfo_width() - x)
            label.place(
                x=x,
                y=0,
                width=max(1, width),
                height=18,
            )

    def _scroll_subscriptions(self, event):
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            first, last = self.sub_canvas.yview()
            if direction < 0 and first <= 0.0001:
                self.sub_canvas.yview_moveto(0.0)
            elif direction > 0 and last >= 0.9999:
                self.sub_canvas.yview_moveto(max(0.0, 1.0 - (last - first)))
            else:
                self.sub_canvas.yview_scroll(direction, "units")
        return "break"

    def _toggle_notes_visibility(self):
        self.notes_visible = not self.notes_visible
        self._apply_notes_visibility()

    def _apply_notes_visibility(self):
        for item in self.sub_entries:
            row = item["row"]
            note_entry = item["note_entry"]
            if self.notes_visible:
                row.columnconfigure(1, weight=3)
                row.columnconfigure(3, weight=2)
                note_entry.grid()
            else:
                note_entry.grid_remove()
                row.columnconfigure(1, weight=1)
                row.columnconfigure(3, weight=0, minsize=0)
        if hasattr(self, "notes_toggle_button"):
            self.notes_toggle_button.config(
                text="隐藏备注" if self.notes_visible else "显示备注",
                style="ToggleActive.TButton" if self.notes_visible else "Compact.TButton",
            )
        self.update_idletasks()
        self._refresh_subscription_scrollregion()
        self._align_subscription_header()

    def _schedule_topics_save(self, *args):
        if self._loading_topics:
            return
        if self._topics_save_after_id is not None:
            try:
                self.after_cancel(self._topics_save_after_id)
            except Exception:
                pass
        self._topics_save_after_id = self.after(450, self._auto_save_topics)

    def _auto_save_topics(self):
        self._topics_save_after_id = None
        self._save_topics_to_disk(silent=True)

    def _refresh_subscription_enabled_button(self, item):
        enabled = bool(item["enabled_var"].get())
        self._draw_circle_toggle(item["enabled_button"], enabled)

    def _toggle_subscription_enabled(self, item):
        item["enabled_var"].set(not item["enabled_var"].get())
        self._refresh_subscription_enabled_button(item)

    def _create_trash_icon(self, parent, command):
        canvas = tk.Canvas(
            parent,
            width=20,
            height=20,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        color = "#DC2626"
        canvas.create_line(5, 6, 15, 6, fill=color, width=1.5)
        canvas.create_line(8, 4, 12, 4, fill=color, width=1.5)
        canvas.create_rectangle(6, 7, 14, 16, outline=color, width=1.3)
        canvas.create_line(9, 9, 9, 14, fill=color, width=1)
        canvas.create_line(11, 9, 11, 14, fill=color, width=1)
        canvas.bind("<Button-1>", lambda event: command())
        return canvas

    def _add_subscription_row(self, default="", note="", enabled=True, schedule_save=True):
        row = ttk.Frame(self.sub_frame, style="Card.TFrame")
        row.columnconfigure(0, minsize=28)
        row.columnconfigure(1, weight=3)
        row.columnconfigure(2, minsize=28)
        row.columnconfigure(3, weight=2)

        enabled_var = tk.BooleanVar(value=bool(enabled))
        topic_var = tk.StringVar(value=default)
        note_var = tk.StringVar(value=note)
        item = {
            "row": row,
            "enabled_var": enabled_var,
            "topic_var": topic_var,
            "note_var": note_var,
        }

        enabled_button = tk.Canvas(
            row,
            width=20,
            height=20,
            background="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        enabled_button.grid(row=0, column=0, padx=(2, 6), pady=1)
        enabled_button.bind("<Button-1>", lambda event, current=item: self._toggle_subscription_enabled(current))
        topic_entry = ttk.Entry(row, textvariable=topic_var)
        topic_entry.grid(row=0, column=1, padx=2, pady=1, sticky="ew")
        delete_button = self._create_trash_icon(
            row,
            lambda current=item: self._remove_subscription_row(current),
        )
        delete_button.grid(row=0, column=2, padx=4, pady=1)
        note_entry = ttk.Entry(row, textvariable=note_var)
        note_entry.grid(row=0, column=3, padx=(2, 7), pady=1, sticky="ew")

        item.update({
            "enabled_button": enabled_button,
            "topic_entry": topic_entry,
            "note_entry": note_entry,
            "delete_button": delete_button,
        })
        self._refresh_subscription_enabled_button(item)
        row.pack(fill=tk.X)
        self.sub_entries.append(item)
        if not self.notes_visible:
            note_entry.grid_remove()
            row.columnconfigure(1, weight=1)
            row.columnconfigure(3, weight=0, minsize=0)

        for widget in (row, enabled_button, topic_entry, delete_button, note_entry):
            widget.bind("<MouseWheel>", self._scroll_subscriptions)
        enabled_var.trace_add("write", self._schedule_topics_save)
        topic_var.trace_add("write", self._schedule_topics_save)
        note_var.trace_add("write", self._schedule_topics_save)

        self.after_idle(self._refresh_subscription_scrollregion)
        self.after_idle(self._align_subscription_header)
        if schedule_save:
            self._schedule_topics_save()
            self.after_idle(self._scroll_subscription_to_bottom)
            topic_entry.focus_set()

    def _scroll_subscription_to_bottom(self):
        self._refresh_subscription_scrollregion()
        if self.sub_frame.winfo_reqheight() > self.sub_canvas.winfo_height():
            self.sub_canvas.yview_moveto(1.0)
        else:
            self.sub_canvas.yview_moveto(0.0)

    def _remove_subscription_row(self, item=None):
        if not self.sub_entries:
            return
        if item is None:
            item = self.sub_entries[-1]
        if item not in self.sub_entries:
            return
        topic = item["topic_var"].get().strip()
        if topic and self.client and self.mqtt_connected:
            try:
                self.client.unsubscribe(topic)
                self._append_plain(f"[信息] 已取消订阅：{topic}")
            except Exception as e:
                self._append_plain(f"[错误] 取消订阅失败：{topic}，{e}")
        self.sub_entries.remove(item)
        item["row"].destroy()
        self.after_idle(self._refresh_subscription_scrollregion)
        self.after_idle(self._align_subscription_header)
        self._schedule_topics_save()

    # -------------------------
    # append plain message
    # -------------------------
    def _append_plain(self, text, tag=None):
        def task():
            follow = self._output_at_bottom(self.text_display)
            self.text_display.configure(state=tk.NORMAL)
            self.text_display.insert(tk.END, text + "\n", tag or ())
            self.text_display.configure(state=tk.DISABLED)
            self._finish_output_append(self.text_display, follow)
        self.after(0, task)

    # -------------------------
    # UI queue processing
    # -------------------------
    def _process_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                # item: (timestamp, topic, qos, payload_obj, decrypt_status)
                self._insert_message_block(*item)
        except queue.Empty:
            pass
        self.after(60, self._process_ui_queue)

    # -------------------------
    # display trimming by lines
    # -------------------------
    @staticmethod
    def _output_at_bottom(output):
        return output.yview()[1] >= 1.0

    @staticmethod
    def _output_line_count(output):
        line, column = map(int, output.index("end-1c").split("."))
        return line if column else line - 1

    def _wire_output_scrollbar(self, output, scrollbar):
        refresh_pending = False

        def refresh():
            nonlocal refresh_pending
            refresh_pending = False
            if self._output_at_bottom(output):
                total_lines = self._output_line_count(output)
                if total_lines > self.max_messages:
                    self._trim_display_by_lines(output, total_lines)
                    output.see(tk.END)
            if output is self.text_display:
                self._queue_watermark_refresh()

        def update_scrollbar(first, last):
            nonlocal refresh_pending
            scrollbar.set(first, last)
            if not refresh_pending:
                refresh_pending = True
                self.after_idle(refresh)

        output.configure(yscrollcommand=update_scrollbar)

    def _finish_output_append(self, output, follow):
        total_lines = self._output_line_count(output)
        paused_limit = max(PAUSED_OUTPUT_LIMIT, self.max_messages)
        if follow or total_lines > paused_limit:
            self._trim_display_by_lines(output, total_lines)
            output.see(tk.END)
        if output is self.text_display:
            self._queue_watermark_refresh()

    def _trim_display_by_lines(self, output, total_lines):
        excess = total_lines - self.max_messages
        if excess <= 0:
            return

        previous_state = str(output.cget("state"))
        output.configure(state=tk.NORMAL)
        try:
            output.delete("1.0", f"{excess + 1}.0")
        finally:
            output.configure(state=previous_state)

        if output is self.text_display:
            while self.message_blocks:
                tag = self.message_blocks[0]["tag"]
                if output.tag_ranges(tag):
                    break
                output.tag_delete(tag)
                self.message_blocks.popleft()

    # -------------------------
    # insert a complete message block
    # -------------------------
    def _insert_message_block(self, timestamp, topic, qos, payload_obj, decrypt_status=""):
        """
        Insert full message and tag the entire region with unique tag.
        """
        block_tag = f"blk_{uuid.uuid4().hex}"
        start_mark = f"mstart_{uuid.uuid4().hex}"

        follow = self._output_at_bottom(self.text_display)
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.mark_set(start_mark, "end-1c")
        self.text_display.mark_gravity(start_mark, tk.LEFT)

        status_text = f" {decrypt_status}" if decrypt_status else ""
        header_text = f"{timestamp}  主题: {topic}  QoS: {qos}{status_text}\n"
        self.text_display.insert(tk.END, header_text)

        try:
            start_idx = self.text_display.index(start_mark)
            header_end = self.text_display.index("end-1c")
            header_line = self.text_display.get(start_idx, header_end)

            topic_label_pos = header_line.find("主题:")
            qos_label_pos = header_line.find("QoS:")

            if topic_label_pos != -1:
                ts_end_idx = f"{start_idx} + {topic_label_pos} chars"
                self.text_display.tag_add("timestamp", start_idx, ts_end_idx)

                topic_val_start = topic_label_pos + len("主题: ")
                topic_val_end = qos_label_pos if qos_label_pos != -1 else len(header_line)
                tstart = f"{start_idx} + {topic_val_start} chars"
                tend = f"{start_idx} + {topic_val_end} chars"
                self.text_display.tag_add("topic", tstart, tend)

            if qos_label_pos != -1:
                qos_value_text = f"{qos}{status_text}"
                qstart = f"{start_idx} + {qos_label_pos + len('QoS: ')} chars"
                qend = f"{qstart} + {len(qos_value_text)} chars"
                self.text_display.tag_add("qos", qstart, qend)
        except Exception:
            pass

        if isinstance(payload_obj, (dict, list)):
            self._insert_json_colorful(payload_obj, indent_level=0)
            self.text_display.insert(tk.END, "\n")
            if decrypt_status == "解密失败" and isinstance(payload_obj, dict) and "raw_hex" in payload_obj:
                self.text_display.insert(tk.END, "原始 HEX: ")
                start = self.text_display.index("end-1c")
                self.text_display.insert(tk.END, payload_obj["raw_hex"])
                end = self.text_display.index("end-1c")
                self.text_display.tag_add("hex_error", start, end)
                self.text_display.insert(tk.END, "\n")
            pretty = json.dumps(payload_obj, ensure_ascii=False, indent=2)
            raw = payload_obj
            json_flag = True
        else:
            self.text_display.insert(tk.END, str(payload_obj) + "\n")
            pretty = None
            raw = str(payload_obj)
            json_flag = False

        try:
            s_idx = self.text_display.index(start_mark)
            e_idx = self.text_display.index("end-1c")
            self.text_display.tag_add(block_tag, s_idx, e_idx)
        except Exception as e:
            logging.exception("Failed to tag block: %s", e)

        self.message_blocks.append({
            "tag": block_tag,
            "json_flag": json_flag,
            "raw": raw,
            "pretty": pretty
        })

        try:
            self.text_display.mark_unset(start_mark)
        except Exception:
            pass

        self.text_display.configure(state=tk.DISABLED)
        self._finish_output_append(self.text_display, follow)
        self._update_msg_count_label()

    # -------------------------
    # Recursive JSON colorful insertion
    # -------------------------
    def _insert_json_colorful(self, obj, indent_level=0):
        indent = "  " * indent_level
        if isinstance(obj, dict):
            self.text_display.insert(tk.END, "{\n")
            items = list(obj.items())
            for i, (k, v) in enumerate(items):
                self.text_display.insert(tk.END, indent + "  ")

                key_text = json.dumps(k, ensure_ascii=False)
                kstart = self.text_display.index("end-1c")
                self.text_display.insert(tk.END, key_text)
                kend = self.text_display.index("end-1c")
                self.text_display.tag_add("json_key", kstart, kend)

                self.text_display.insert(tk.END, ": ")

                if isinstance(v, (dict, list)):
                    self._insert_json_colorful(v, indent_level + 1)
                else:
                    val_text = json.dumps(v, ensure_ascii=False)
                    vstart = self.text_display.index("end-1c")
                    self.text_display.insert(tk.END, val_text)
                    vend = self.text_display.index("end-1c")
                    self.text_display.tag_add("json_value", vstart, vend)

                if i != len(items) - 1:
                    self.text_display.insert(tk.END, ",\n")
                else:
                    self.text_display.insert(tk.END, "\n")

            self.text_display.insert(tk.END, indent + "}")

        elif isinstance(obj, list):
            self.text_display.insert(tk.END, "[\n")
            for i, v in enumerate(obj):
                self.text_display.insert(tk.END, indent + "  ")
                if isinstance(v, (dict, list)):
                    self._insert_json_colorful(v, indent_level + 1)
                else:
                    val_text = json.dumps(v, ensure_ascii=False)
                    vstart = self.text_display.index("end-1c")
                    self.text_display.insert(tk.END, val_text)
                    vend = self.text_display.index("end-1c")
                    self.text_display.tag_add("json_value", vstart, vend)

                if i != len(obj) - 1:
                    self.text_display.insert(tk.END, ",\n")
                else:
                    self.text_display.insert(tk.END, "\n")

            self.text_display.insert(tk.END, indent + "]")

        else:
            val_text = json.dumps(obj, ensure_ascii=False)
            vstart = self.text_display.index("end-1c")
            self.text_display.insert(tk.END, val_text)
            vend = self.text_display.index("end-1c")
            self.text_display.tag_add("json_value", vstart, vend)

    # -------------------------
    # MQTT
    # -------------------------
    def connect_mqtt(self):
        host = self.entry_host.get().strip()
        try:
            port = int(self.entry_port.get().strip())
        except:
            messagebox.showerror("输入错误", "端口号必须是数字。")
            return

        if not host:
            messagebox.showerror("输入错误", "请输入 MQTT 服务器地址。")
            return

        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()

        self._set_connection_phase("connecting")
        self._set_connection_status("正在连接", "#FEC84B")
        self._start_connection_timeout("connecting", CONNECT_TIMEOUT_MS)
        self._connect_ready_event.clear()
        self.client = mqtt.Client()

        if username:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._manual_disconnect = False

        def client_loop():
            while not self._stop_event.is_set():
                try:
                    self.after(0, lambda: self._set_connection_phase("connecting"))
                    self.after(0, lambda: self._start_connection_timeout("connecting", CONNECT_TIMEOUT_MS))
                    self._connect_ready_event.clear()
                    self.mqtt_connected = False
                    self.client.connect(host, port, 60)
                    self.client.loop_start()

                    # 等待 on_connect / on_disconnect 回调给出真实连接结果，
                    # 避免 loop_start 后立即误判为断线而重连、重复订阅。
                    if not self._connect_ready_event.wait(timeout=10):
                        raise TimeoutError("MQTT 连接等待超时")

                    while not self._stop_event.is_set() and not self._manual_disconnect:
                        if not self.mqtt_connected:
                            break
                        time.sleep(0.2)

                    try:
                        self.client.loop_stop()
                    except Exception:
                        pass

                    if self._manual_disconnect:
                        try:
                            self.client.disconnect()
                        except Exception:
                            pass
                        break

                    if self._stop_event.is_set():
                        try:
                            self.client.disconnect()
                        except Exception:
                            pass
                        break

                    if self.auto_reconnect_enabled and not self._stop_event.is_set():
                        self._append_plain(f"[信息] {RECONNECT_INTERVAL} 秒后尝试自动重连。")
                        time.sleep(RECONNECT_INTERVAL)
                        continue
                    else:
                        break

                except Exception as e:
                    self.after(0, self._clear_connection_timeout)
                    logging.exception("MQTT connection error: %s", e)
                    self._append_plain(f"[错误] MQTT 连接失败：{e}")
                    self.mqtt_connected = False
                    try:
                        self.client.loop_stop()
                    except Exception:
                        pass
                    try:
                        self.client.disconnect()
                    except Exception:
                        pass
                    self.after(0, lambda: self._set_connection_status("连接失败", "#FDA29B"))

                    if self.auto_reconnect_enabled and not self._stop_event.is_set() and not self._manual_disconnect:
                        self.after(0, lambda: self._set_connection_phase("connecting"))
                        self._append_plain(f"[信息] {RECONNECT_INTERVAL} 秒后尝试自动重连。")
                        time.sleep(RECONNECT_INTERVAL)
                        continue
                    else:
                        break

            self.after(0, lambda: self._set_connection_phase("disconnected"))

        self.client_thread = threading.Thread(target=client_loop, daemon=True)
        self.client_thread.start()
        self._append_plain("[信息] 正在连接 MQTT 服务器……")

    def disconnect_mqtt(self):
        self._manual_disconnect = True
        self._connect_ready_event.set()
        self._set_connection_phase("disconnecting")
        self._start_connection_timeout("disconnecting", DISCONNECT_TIMEOUT_MS)
        try:
            if self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
        except Exception:
            pass

        self._set_connection_status("正在断开", "#FEC84B")
        self._append_plain("[信息] 正在断开 MQTT 连接。")

    def _on_connect(self, client, userdata, flags, rc):
        self.after(0, self._clear_connection_timeout)
        if rc == 0:
            self.mqtt_connected = True
            self._append_plain("[信息] MQTT 服务器连接成功。")
            self.after(0, lambda: self._set_connection_phase("connected"))
            self.after(0, lambda: self._set_connection_status("已连接", "#6CE9A6"))
            self.after(200, lambda: self.subscribe_all())
        else:
            self._append_plain(f"[错误] MQTT 连接失败，返回码={rc}（可能是用户名或密码错误）。")
            next_phase = "connecting" if self.auto_reconnect_enabled else "disconnected"
            self.after(0, lambda phase=next_phase: self._set_connection_phase(phase))
            self.after(0, lambda: self._set_connection_status("连接失败", "#FDA29B"))
        self._connect_ready_event.set()

    def _on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
        self._connect_ready_event.set()
        self.after(0, self._clear_connection_timeout)
        self._append_plain("[信息] MQTT 连接已断开。")
        if self._manual_disconnect or self._stop_event.is_set() or not self.auto_reconnect_enabled:
            self.after(0, lambda: self._set_connection_phase("disconnected"))
            self.after(0, lambda: self._set_connection_status("未连接", "#FDA29B"))
        else:
            self.after(0, lambda: self._set_connection_phase("connecting"))
            self.after(0, lambda: self._set_connection_status("等待重连", "#FEC84B"))

    def _on_message(self, client, userdata, msg):
        payload_bytes = msg.payload
        decrypt_status = ""
        failed_hex = None

        mode = self.gt_mode_var.get()

        if mode == "ZBY 解密":
            obj, decrypt_status, failed_hex = parse_gt115_payload(payload_bytes)
        else:
            # Raw Data mode 下直接显示原始 HEX
            obj = payload_bytes.hex().upper()
            decrypt_status = ""

        tz = timezone(timedelta(hours=8))
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        self.total_received += 1

        if self.saving_enabled and self.save_file:
            with self.save_lock:
                try:
                    status_text = f" {decrypt_status}" if decrypt_status else ""
                    header = f"{timestamp}  主题: {msg.topic}  QoS: {msg.qos}{status_text}\n"

                    if isinstance(obj, (dict, list)):
                        body = json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n"
                    else:
                        body = str(obj) + "\n\n"

                    self.save_file.write(header)
                    self.save_file.write(body)

                    # 只有解密失败才额外打印原始 HEX
                    if decrypt_status == "解密失败" and failed_hex:
                        self.save_file.write(f"原始 HEX: {failed_hex}\n\n")

                    try:
                        self.save_file.flush()
                        os.fsync(self.save_file.fileno())
                    except Exception:
                        pass

                    self.total_saved += 1
                except Exception:
                    logging.exception("Failed to write to save file")

        try:
            self.ui_queue.put_nowait((timestamp, msg.topic, msg.qos, obj, decrypt_status))
        except queue.Full:
            logging.warning("UI queue full; dropping message for display")

        self.after(0, self._update_msg_count_label)

    def _publish_shortcut(self, event=None):
        """Ctrl+Enter 快捷发送。"""
        self.publish_encrypted_json()
        return "break"

    def publish_encrypted_json(self):
        """JSON -> UTF-8 -> PKCS7 -> AES-256-CBC -> MQTT 密文字节。"""
        if not self.client or not self.mqtt_connected:
            self.publish_status_label.config(text="未连接 MQTT")
            messagebox.showwarning("发送失败", "请先连接 MQTT 服务器。")
            return

        topic = self.publish_topic_entry.get().strip()
        if not topic:
            self.publish_status_label.config(text="发送主题为空")
            messagebox.showwarning("发送失败", "请输入发送主题。")
            self.publish_topic_entry.focus_set()
            return

        json_text = self.publish_data_text.get("1.0", "end-1c").strip()
        if not json_text:
            self.publish_status_label.config(text="JSON 为空")
            messagebox.showwarning("发送失败", "请输入 JSON 数据。")
            self.publish_data_text.focus_set()
            return

        try:
            encrypted_bytes, source_json = encrypt_json_payload(json_text)
        except json.JSONDecodeError as e:
            detail = f"无法解析 JSON，请检查引号、逗号和括号。\n位置：第 {e.lineno} 行，第 {e.colno} 列。"
            self.publish_status_label.config(text="JSON 格式错误")
            messagebox.showerror("JSON 格式错误", detail)
            return
        except Exception as e:
            self.publish_status_label.config(text="加密失败")
            messagebox.showerror("加密失败", str(e))
            return

        encrypted_hex = encrypted_bytes.hex().upper()
        try:
            info = self.client.publish(topic, payload=encrypted_bytes, qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(mqtt.error_string(info.rc))
        except Exception as e:
            self.publish_status_label.config(text="发送失败")
            messagebox.showerror("MQTT 发送失败", str(e))
            return

        self.publish_status_label.config(text=f"已提交 {len(encrypted_bytes)} 字节")
        self._append_plain(
            f"[发送] 主题: {topic}  QoS: 1\n"
            f"JSON 原文: {source_json}\n"
            f"AES 密文 HEX: {encrypted_hex}",
            tag="sent_message",
        )

    # -------------------------
    # subscribe / unsubscribe
    # -------------------------
    def subscribe_all(self):
        if not self.client:
            messagebox.showwarning("无法订阅", "请先连接 MQTT 服务器。")
            return

        for item in self.sub_entries:
            t = item["topic_var"].get().strip()
            if t:
                try:
                    self.client.unsubscribe(t)
                except Exception:
                    pass

        applied_count = 0
        for item in self.sub_entries:
            topic = item["topic_var"].get().strip()
            if topic and item["enabled_var"].get():
                try:
                    self.client.subscribe(topic, 1)
                    self._append_plain(f"[信息] 已订阅：{topic}")
                    applied_count += 1
                except Exception as e:
                    self._append_plain(f"[错误] 订阅失败：{topic}，{e}")
        self._append_plain(f"[信息] 已应用 {applied_count} 个勾选主题。")

    def unsubscribe_all(self):
        if not self.client:
            messagebox.showwarning("无法取消订阅", "请先连接 MQTT 服务器。")
            return

        for item in self.sub_entries:
            topic = item["topic_var"].get().strip()
            if topic:
                try:
                    self.client.unsubscribe(topic)
                    self._append_plain(f"[信息] 已取消订阅：{topic}")
                except Exception as e:
                    self._append_plain(f"[错误] 取消订阅失败：{topic}，{e}")

    # -------------------------
    # clear / save log
    # -------------------------
    def clear_display(self):
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)
        self.text_display.configure(state=tk.DISABLED)
        for block in self.message_blocks:
            self.text_display.tag_delete(block["tag"])
        self.message_blocks.clear()
        self._update_msg_count_label()
        self._append_plain("[信息] 显示内容已清空。")

    def start_save(self):
        if self.saving_enabled:
            messagebox.showinfo("提示", "当前已在保存日志。")
            return

        path = filedialog.asksaveasfilename(
            title="选择日志保存位置",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not path:
            return

        try:
            self.save_file = open(path, "a", encoding="utf-8", buffering=1)
        except Exception as e:
            messagebox.showerror("保存失败", f"无法打开日志文件：{e}")
            return

        self.saving_enabled = True
        self.btn_save.config(state=tk.DISABLED)
        self.btn_stop_save.config(state=tk.NORMAL)
        self._append_plain(f"[信息] 已开始保存日志：{path}")
        self._update_msg_count_label()

    def stop_save(self):
        if not self.saving_enabled:
            return

        self.saving_enabled = False
        try:
            if self.save_file:
                with self.save_lock:
                    try:
                        self.save_file.flush()
                        try:
                            os.fsync(self.save_file.fileno())
                        except Exception:
                            pass
                        self.save_file.close()
                    except Exception:
                        pass
        except:
            pass

        self.save_file = None
        self.btn_save.config(state=tk.NORMAL)
        self.btn_stop_save.config(state=tk.DISABLED)
        self._append_plain("[信息] 已停止保存日志。")
        self._update_msg_count_label()

    # -------------------------
    # apply max messages
    # -------------------------
    def _apply_max_messages(self):
        try:
            val = int(self.spin_max.get())
            if val < 10:
                raise ValueError("不能小于 10")
            self.max_messages = val
            self._finish_output_append(self.text_display, self._output_at_bottom(self.text_display))
            self._append_plain(f"[信息] 最大显示行数已设为 {self.max_messages}。")
            self._update_msg_count_label()
        except Exception as e:
            messagebox.showerror("输入错误", f"最大显示行数无效：{e}")

    # -------------------------
    # topics save/load
    # -------------------------
    def _save_topics_to_disk(self, silent=True):
        arr = []
        for item in self.sub_entries:
            topic = item["topic_var"].get().strip()
            if not topic:
                continue
            arr.append({
                "enabled": bool(item["enabled_var"].get()),
                "topic": topic,
                "note": item["note_var"].get().strip(),
            })
        path = topic_file_path()
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=2)
            if not silent:
                self._append_plain(f"[信息] 已保存 {len(arr)} 个订阅主题：{path}")
        except Exception as e:
            logging.exception("订阅主题自动保存失败: %s", e)
            if not silent:
                messagebox.showerror("保存失败", f"订阅主题保存失败：{e}")

    def _load_topics_from_disk(self):
        path = topic_file_path()
        if not os.path.exists(path):
            return
        try:
            self._loading_topics = True
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)

            for item in self.sub_entries:
                item["row"].destroy()
            self.sub_entries.clear()

            for saved_item in arr:
                # 兼容旧版 ["topic/a", "topic/b"] 格式
                if isinstance(saved_item, str):
                    self._add_subscription_row(saved_item, "", True, schedule_save=False)
                elif isinstance(saved_item, dict):
                    self._add_subscription_row(
                        str(saved_item.get("topic", "")),
                        str(saved_item.get("note", "")),
                        bool(saved_item.get("enabled", True)),
                        schedule_save=False,
                    )

            if not self.sub_entries:
                self._add_subscription_row("", "", True, schedule_save=False)

            self._append_plain(f"[信息] 已加载 {len(arr)} 个订阅主题。")
        except Exception as e:
            logging.exception("Load topics failed: %s", e)
        finally:
            self._loading_topics = False
            self.after_idle(self._refresh_subscription_scrollregion)
            # 读取到旧格式后自动迁移到带备注和勾选状态的新格式
            self._schedule_topics_save()

    # -------------------------
    # shutdown
    # -------------------------
    def on_close(self):
        """
        安全非阻塞关闭
        """
        self._manual_disconnect = True
        self._stop_event.set()
        self._connect_ready_event.set()
        self._clear_connection_timeout()

        try:
            self.btn_connection.config(state=tk.DISABLED)
        except Exception:
            pass

        try:
            if self.saving_enabled and self.save_file:
                with self.save_lock:
                    try:
                        self.save_file.flush()
                        try:
                            os.fsync(self.save_file.fileno())
                        except Exception:
                            pass
                    except Exception:
                        pass
                    try:
                        self.save_file.close()
                    except Exception:
                        pass
                self.saving_enabled = False
                self.save_file = None
        except Exception:
            logging.exception("Error while closing save file")

        if not self.client:
            self._final_destroy()
            return

        def _shutdown_mqtt_bg():
            try:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                try:
                    self.client.loop_stop(force=True)
                except Exception:
                    pass
                try:
                    if self.client_thread and self.client_thread.is_alive():
                        self.client_thread.join(timeout=2)
                except Exception:
                    pass
            finally:
                try:
                    self.after(0, self._final_destroy)
                except Exception:
                    try:
                        self._final_destroy()
                    except Exception:
                        pass

        t = threading.Thread(target=_shutdown_mqtt_bg, daemon=True)
        t.start()

    def _final_destroy(self):
        try:
            try:
                self._save_topics_to_disk()
            except Exception:
                pass
        finally:
            try:
                self.destroy()
            except Exception:
                pass



    # -------------------------
    # FDCAN
    # -------------------------
    def toggle_fdcan_panel(self):
        if not hasattr(self, "fdcan_frame"):
            return
        if not self.fdcan_visible:
            self.main_pane.insert(1, self.fdcan_frame)
            self.fdcan_visible = True
            self.btn_fdcan.config(text="关闭 FDCAN")
        else:
            self.main_pane.forget(self.fdcan_frame)
            self.fdcan_visible = False
            self.btn_fdcan.config(text="FDCAN 解析")

    def parse_fdcan(self):
        raw = self.fdcan_input.get("1.0", tk.END).strip()
        raw = raw.replace(" ", "").replace("\r", "").replace("\n", "").upper()

        self.fdcan_output.delete("1.0", tk.END)

        try:
            data = bytes.fromhex(raw)
        except Exception:
            self.fdcan_output.insert(tk.END, "解析状态：失败\n\n失败原因：非法HEX字符串")
            return

        pos = 0
        idx = 1
        total = len(data)
        result = []

        while pos < total:
            length_pos = pos
            length = data[pos]
            pos += 1

            if length == 0:
                self.fdcan_output.insert(
                    tk.END,
                    f"解析状态：失败\n\n失败原因：长度字段为0\n数据序号：{idx}\n位置：字节[{length_pos}]"
                )
                return

            remain = total - pos
            if length > remain:
                self.fdcan_output.insert(
                    tk.END,
                    f"解析状态：失败\n\n失败原因：长度不足\n数据序号：{idx}\n长度字段位置：字节[{length_pos}]\n声明长度：{length}\n剩余长度：{remain}"
                )
                return

            payload = data[pos:pos + length]
            pos += length

            result.append(
                f"数据{idx}：\n长度：{length}\n数据内容：{payload.hex().upper()}\n"
            )
            idx += 1

        self.fdcan_output.insert(
            tk.END,
            f"解析状态：成功\n\n总长度：{total} 字节\n解析条数：{idx-1}\n\n" + "\n".join(result)
        )

# ----------------------------
# run
# ----------------------------
if __name__ == "__main__":
    app = MQTT_AES_Pro_v2()
    app.mainloop()
