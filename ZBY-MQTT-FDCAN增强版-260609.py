#!/usr/bin/env python3
# mqtt_aes_tool_pro_v2_final.py
# 单文件：严格显示 FIFO（默认2000条），保存全部数据，GT115_ZBY/Raw Data 下拉，JSON 彩色渲染
# 新增：
# 1. GT115_ZBY 模式下，QoS 后显示：解密成功 / 解密失败
# 2. 解密失败时，显示并保存原始 HEX 数据；解密成功时不显示原始 HEX
#
# 依赖: paho-mqtt, pycryptodome
# pip install paho-mqtt pycryptodome

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

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ----------------------------
# CONFIG
# ----------------------------
FIXED_KEY_HEX = "d3f67a2e5b8c901f4a6d0e3c7b291f5d8e4c2a1b0f9e8d7c6b5a493827161514"
DEFAULT_MAX_MESSAGES = 2000
TOPICS_SAVE_FILE = "topics.json"
RECONNECT_INTERVAL = 5  # seconds between reconnect attempts

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
        super().__init__()
        self.title("MQTT-ZB功德箱增强版 ★★★★★ 广告位招租 ★★★★★ - Mangetic")
        self.geometry("1240x760")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # MQTT
        self.client = None
        self.client_thread = None
        self.mqtt_connected = False
        self._stop_event = threading.Event()
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
        self.gt_mode_var = tk.StringVar(value="ZBY")

        # FDCAN工具
        self.fdcan_visible = False

        # Build UI
        self._build_ui()

        # Start ui queue processing
        self.after(60, self._process_ui_queue)

        # Load topics
        self._load_topics_from_disk()

    # -------------------------
    # UI building
    # -------------------------
    def _build_ui(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        ttk.Label(top_frame, text="MQTT Server:").pack(side=tk.LEFT)
        self.entry_host = ttk.Entry(top_frame, width=28)
        self.entry_host.insert(0, "zte-cid.com")
        self.entry_host.pack(side=tk.LEFT, padx=4)

        ttk.Label(top_frame, text="Port:").pack(side=tk.LEFT)
        self.entry_port = ttk.Entry(top_frame, width=6)
        self.entry_port.insert(0, "1883")
        self.entry_port.pack(side=tk.LEFT, padx=4)

        ttk.Label(top_frame, text="Username:").pack(side=tk.LEFT, padx=(10, 0))
        self.entry_username = ttk.Entry(top_frame, width=12)
        self.entry_username.insert(0, "admin")
        self.entry_username.pack(side=tk.LEFT, padx=4)

        ttk.Label(top_frame, text="Password:").pack(side=tk.LEFT)
        self.entry_password = ttk.Entry(top_frame, width=12, show="*")
        self.entry_password.insert(0, "Zbwd@010")
        self.entry_password.pack(side=tk.LEFT, padx=4)

        self.btn_connect = ttk.Button(top_frame, text="Connect", command=self.connect_mqtt)
        self.btn_connect.pack(side=tk.LEFT, padx=6)

        self.btn_disconnect = ttk.Button(top_frame, text="Disconnect", command=self.disconnect_mqtt, state=tk.DISABLED)
        self.btn_disconnect.pack(side=tk.LEFT, padx=2)

        self.btn_fdcan = ttk.Button(top_frame, text="FDCAN解析", command=self.toggle_fdcan_panel)
        self.btn_fdcan.pack(side=tk.LEFT, padx=4)

        ttk.Label(top_frame, text="Max Messages:").pack(side=tk.LEFT, padx=(10, 0))
        self.spin_max = ttk.Spinbox(top_frame, from_=100, to=10000, width=6)
        self.spin_max.set(str(self.max_messages))
        self.spin_max.pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="Apply", command=self._apply_max_messages).pack(side=tk.LEFT, padx=4)

        self.auto_reconnect_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top_frame, text="AutoReconnect", variable=self.auto_reconnect_var).pack(side=tk.LEFT, padx=6)

        self.main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        # left
        left_frame = ttk.Frame(self.main_pane, width=320)
        self.main_pane.add(left_frame, weight=0)

        ttk.Label(left_frame, text="Subscriptions:").pack(anchor=tk.W, pady=(4, 2), padx=4)
        self.sub_frame = ttk.Frame(left_frame)
        self.sub_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        self.sub_entries = []
        self._add_subscription_row("test/topic")

        btn_sub_controls = ttk.Frame(left_frame)
        btn_sub_controls.pack(fill=tk.X, pady=4, padx=4)
        ttk.Button(btn_sub_controls, text="Add", command=lambda: self._add_subscription_row("")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_sub_controls, text="Remove", command=self._remove_subscription_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_sub_controls, text="Subscribe All", command=self.subscribe_all).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_sub_controls, text="Unsubscribe All", command=self.unsubscribe_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_sub_controls, text="Save Topics", command=self._save_topics_to_disk).pack(side=tk.LEFT, padx=4)


        # FDCAN工具区
        self.fdcan_frame = ttk.Frame(self.main_pane, width=350)

        ttk.Label(self.fdcan_frame, text="FDCAN解析工具").pack(anchor=tk.W, padx=5, pady=5)

        self.fdcan_input = tk.Text(self.fdcan_frame, height=10)
        self.fdcan_input.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(self.fdcan_frame, text="解析", command=self.parse_fdcan).pack(pady=5)

        self.fdcan_output = tk.Text(self.fdcan_frame)
        self.fdcan_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # right
        right_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(right_frame, weight=1)

        text_frame = ttk.Frame(right_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.text_display = tk.Text(text_frame, wrap="char", state=tk.DISABLED)
        self.text_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_display.yview)
        vsb.pack(side=tk.LEFT, fill=tk.Y)
        self.text_display.configure(yscrollcommand=vsb.set)

        # tags
        base_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font.configure(weight="bold")

        self.text_display.tag_configure("timestamp", font=bold_font)
        self.text_display.tag_configure("topic", foreground="blue")
        self.text_display.tag_configure("qos", foreground="red")
        self.text_display.tag_configure("json_key", foreground="#FF8C00")
        self.text_display.tag_configure("json_value", foreground="#008800")
        self.text_display.tag_configure("hex_error", foreground="red")

        bottom_controls = ttk.Frame(self)
        bottom_controls.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(bottom_controls, text="Clear", command=self.clear_display).pack(side=tk.LEFT, padx=4)

        self.btn_save = ttk.Button(bottom_controls, text="Start Save", command=self.start_save)
        self.btn_save.pack(side=tk.LEFT, padx=4)

        self.btn_stop_save = ttk.Button(bottom_controls, text="Stop Save", command=self.stop_save, state=tk.DISABLED)
        self.btn_stop_save.pack(side=tk.LEFT, padx=4)

        ttk.Label(bottom_controls, text="Mode:").pack(side=tk.LEFT, padx=(8, 2))
        self.gt_mode_menu = ttk.OptionMenu(bottom_controls, self.gt_mode_var, self.gt_mode_var.get(), "ZBY", "Raw Data")
        self.gt_mode_menu.pack(side=tk.LEFT, padx=2)

        self.msg_count_label = ttk.Label(bottom_controls, text=self._msg_count_text())
        self.msg_count_label.pack(side=tk.RIGHT, padx=8)

    def _msg_count_text(self):
        return f" Received: {self.total_received}  Saved: {self.total_saved}"

    def _update_msg_count_label(self):
        self.msg_count_label.config(text=self._msg_count_text())

    # -------------------------
    # subscription rows
    # -------------------------
    def _add_subscription_row(self, default=""):
        row = ttk.Frame(self.sub_frame)
        entry = ttk.Entry(row, width=30)
        entry.insert(0, default)
        entry.pack(side=tk.LEFT, padx=2, pady=2)
        row.pack(fill=tk.X)
        self.sub_entries.append((row, entry))

    def _remove_subscription_row(self):
        if not self.sub_entries:
            return
        row, entry = self.sub_entries.pop()
        topic = entry.get().strip()
        if topic and self.client and self.mqtt_connected:
            try:
                self.client.unsubscribe(topic)
                self._append_plain(f"[INFO] Unsubscribed: {topic}")
            except Exception as e:
                self._append_plain(f"[ERROR] Unsubscribe failed for {topic}: {e}")
        row.destroy()

    # -------------------------
    # append plain message
    # -------------------------
    def _append_plain(self, text):
        def task():
            self.text_display.configure(state=tk.NORMAL)
            self.text_display.insert(tk.END, text + "\n")
            self.text_display.see(tk.END)
            self.text_display.configure(state=tk.DISABLED)
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
    def _trim_display_by_lines(self):
        """
        根据 self.max_messages（行数上限）裁剪 Text 顶部多余行，
        并同步清理 self.message_blocks 中已被删除的条目。
        """
        try:
            total_lines = int(self.text_display.index("end-1c").split(".")[0])
        except Exception:
            return

        if total_lines <= self.max_messages:
            return

        lines_to_remove = total_lines - self.max_messages
        self.text_display.configure(state=tk.NORMAL)
        try:
            self.text_display.delete("1.0", f"{lines_to_remove + 1}.0")
        except Exception as e:
            logging.exception("Trim delete failed: %s", e)

        try:
            while self.message_blocks:
                first = self.message_blocks[0]
                if not self.text_display.tag_ranges(first.get("tag", "")):
                    self.message_blocks.popleft()
                else:
                    break
        except Exception:
            logging.exception("Failed to sync message_blocks after trim")

        self._update_msg_count_label()
        self.text_display.configure(state=tk.DISABLED)

    # -------------------------
    # insert a complete message block
    # -------------------------
    def _insert_message_block(self, timestamp, topic, qos, payload_obj, decrypt_status=""):
        """
        Insert full message and tag the entire region with unique tag.
        """
        block_tag = f"blk_{uuid.uuid4().hex}"
        start_mark = f"mstart_{uuid.uuid4().hex}"

        self.text_display.configure(state=tk.NORMAL)
        self.text_display.mark_set(start_mark, "end-1c")

        status_text = f" {decrypt_status}" if decrypt_status else ""
        header_text = f"{timestamp}  Topic: {topic}  QoS: {qos}{status_text}\n"
        self.text_display.insert(tk.END, header_text)

        try:
            start_idx = self.text_display.index(start_mark)
            header_end = self.text_display.index("end-1c")
            header_line = self.text_display.get(start_idx, header_end)

            topic_label_pos = header_line.find("Topic:")
            qos_label_pos = header_line.find("QoS:")

            if topic_label_pos != -1:
                ts_end_idx = f"{start_idx} + {topic_label_pos} chars"
                self.text_display.tag_add("timestamp", start_idx, ts_end_idx)

                topic_val_start = topic_label_pos + len("Topic: ")
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
                self.text_display.insert(tk.END, "RAW HEX: ")
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

        self._trim_display_by_lines()
        self.text_display.see(tk.END)
        self.text_display.configure(state=tk.DISABLED)
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
            messagebox.showerror("Error", "Invalid port")
            return

        if not host:
            messagebox.showerror("Error", "Host empty")
            return

        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()

        self.btn_connect.config(state=tk.DISABLED)
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
                    self.client.connect(host, port, 60)
                    self.client.loop_start()

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

                    if self.auto_reconnect_var.get() and not self._stop_event.is_set():
                        self._append_plain(f"[INFO] AutoReconnect enabled — retrying in {RECONNECT_INTERVAL}s")
                        time.sleep(RECONNECT_INTERVAL)
                        continue
                    else:
                        break

                except Exception as e:
                    logging.exception("MQTT connection error: %s", e)
                    self._append_plain(f"[ERROR] MQTT connect failed: {e}")
                    self.mqtt_connected = False
                    self.after(0, lambda: self.btn_connect.config(state=tk.NORMAL))
                    self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))

                    if self.auto_reconnect_var.get() and not self._stop_event.is_set() and not self._manual_disconnect:
                        self._append_plain(f"[INFO] AutoReconnect enabled — retrying in {RECONNECT_INTERVAL}s")
                        time.sleep(RECONNECT_INTERVAL)
                        continue
                    else:
                        break

            self.after(0, lambda: self.btn_connect.config(state=tk.NORMAL))
            self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))

        self.client_thread = threading.Thread(target=client_loop, daemon=True)
        self.client_thread.start()
        self._append_plain("[INFO] Connecting to MQTT...")

    def disconnect_mqtt(self):
        self._manual_disconnect = True
        try:
            if self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
        except Exception:
            pass

        self.btn_disconnect.config(state=tk.DISABLED)
        self.btn_connect.config(state=tk.NORMAL)
        self._append_plain("[INFO] Disconnect requested by user.")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
            self._append_plain("[INFO] Connected to MQTT broker")
            self.after(0, lambda: self.btn_disconnect.config(state=tk.NORMAL))
            self.after(0, lambda: self.btn_connect.config(state=tk.DISABLED))
            self.after(200, lambda: self.subscribe_all())
        else:
            self._append_plain(f"[ERROR] Failed to connect, rc={rc}  (可能用户名密码错误)")
            self.after(0, lambda: self.btn_connect.config(state=tk.NORMAL))

    def _on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
        self._append_plain("[INFO] Disconnected from MQTT")
        self.after(0, lambda: self.btn_connect.config(state=tk.NORMAL))
        self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))

    def _on_message(self, client, userdata, msg):
        payload_bytes = msg.payload
        decrypt_status = ""
        failed_hex = None

        mode = self.gt_mode_var.get()

        if mode == "ZBY":
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
                    header = f"{timestamp}  Topic: {msg.topic}  QoS: {msg.qos}{status_text}\n"

                    if isinstance(obj, (dict, list)):
                        body = json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n"
                    else:
                        body = str(obj) + "\n\n"

                    self.save_file.write(header)
                    self.save_file.write(body)

                    # 只有解密失败才额外打印原始 HEX
                    if decrypt_status == "解密失败" and failed_hex:
                        self.save_file.write(f"RAW HEX: {failed_hex}\n\n")

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

    # -------------------------
    # subscribe / unsubscribe
    # -------------------------
    def subscribe_all(self):
        if not self.client:
            messagebox.showwarning("Warning", "MQTT client not initialized")
            return

        for _, entry in self.sub_entries:
            t = entry.get().strip()
            if t:
                try:
                    self.client.unsubscribe(t)
                except Exception:
                    pass

        for _, entry in self.sub_entries:
            topic = entry.get().strip()
            if topic:
                try:
                    self.client.subscribe(topic, 1)
                    self._append_plain(f"[INFO] Subscribed: {topic}")
                except Exception as e:
                    self._append_plain(f"[ERROR] Subscribe failed: {e}")

    def unsubscribe_all(self):
        if not self.client:
            messagebox.showwarning("Warning", "MQTT client not initialized")
            return

        for _, entry in self.sub_entries:
            topic = entry.get().strip()
            if topic:
                try:
                    self.client.unsubscribe(topic)
                    self._append_plain(f"[INFO] Unsubscribed: {topic}")
                except Exception as e:
                    self._append_plain(f"[ERROR] Unsubscribe failed: {e}")

    # -------------------------
    # clear / save log
    # -------------------------
    def clear_display(self):
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)
        self.text_display.configure(state=tk.DISABLED)
        self.message_blocks.clear()
        self._update_msg_count_label()
        self._append_plain("[INFO] Display cleared.")

    def start_save(self):
        if self.saving_enabled:
            messagebox.showinfo("Info", "Already saving logs.")
            return

        path = filedialog.asksaveasfilename(
            title="Save log as...",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            self.save_file = open(path, "a", encoding="utf-8", buffering=1)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")
            return

        self.saving_enabled = True
        self.btn_save.config(state=tk.DISABLED)
        self.btn_stop_save.config(state=tk.NORMAL)
        self._append_plain(f"[INFO] Log saving started: {path}")
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
        self._append_plain("[INFO] Log saving stopped.")
        self._update_msg_count_label()

    # -------------------------
    # apply max messages
    # -------------------------
    def _apply_max_messages(self):
        try:
            val = int(self.spin_max.get())
            if val < 10:
                raise ValueError("Too small")
            self.max_messages = val
            self._trim_display_by_lines()
            self._append_plain(f"[INFO] max_messages set to {self.max_messages}")
            self._update_msg_count_label()
        except Exception as e:
            messagebox.showerror("Error", f"Invalid value: {e}")

    # -------------------------
    # topics save/load
    # -------------------------
    def _save_topics_to_disk(self):
        arr = [entry.get().strip() for _, entry in self.sub_entries if entry.get().strip()]
        path = topic_file_path()
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=2)
            self._append_plain(f"[INFO] Saved {len(arr)} topics to {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Save topics failed: {e}")

    def _load_topics_from_disk(self):
        path = topic_file_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f)

            for row, _ in self.sub_entries:
                row.destroy()
            self.sub_entries.clear()

            for t in arr:
                self._add_subscription_row(t)

            self._append_plain(f"[INFO] Loaded {len(arr)} topics from {path}")
        except Exception as e:
            logging.exception("Load topics failed: %s", e)

    # -------------------------
    # shutdown
    # -------------------------
    def on_close(self):
        """
        安全非阻塞关闭
        """
        self._manual_disconnect = True
        self._stop_event.set()

        try:
            self.btn_disconnect.config(state=tk.DISABLED)
            self.btn_connect.config(state=tk.DISABLED)
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
        else:
            self.main_pane.forget(self.fdcan_frame)
            self.fdcan_visible = False

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
                    f"解析状态：失败\n\n失败原因：长度字段为0\n数据序号：{idx}\n位置：Byte[{length_pos}]"
                )
                return

            remain = total - pos
            if length > remain:
                self.fdcan_output.insert(
                    tk.END,
                    f"解析状态：失败\n\n失败原因：长度不足\n数据序号：{idx}\n长度字段位置：Byte[{length_pos}]\n声明长度：{length}\n剩余长度：{remain}"
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
            f"解析状态：成功\n\n总长度：{total} Bytes\n解析条数：{idx-1}\n\n" + "\n".join(result)
        )

# ----------------------------
# run
# ----------------------------
if __name__ == "__main__":
    app = MQTT_AES_Pro_v2()
    app.mainloop()
