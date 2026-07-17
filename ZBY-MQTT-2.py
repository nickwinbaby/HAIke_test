import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
import base64
import json
import tkinter.font as tkfont

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ----------------- 配置 AES 固定 KEY/IV -----------------
FIXED_KEY_HEX = "d3f67a2e5b8c901f4a6d0e3c7b291f5d8e4c2a1b0f9e8d7c6b5a493827161514"
FIXED_IV_HEX  = "19e4f7a83d0b6c25a81234567890abcd"

def hex_to_bytes(hex_str):
    return bytes.fromhex(hex_str)

KEY_BYTES = hex_to_bytes(FIXED_KEY_HEX)
IV_BYTES_FIXED = hex_to_bytes(FIXED_IV_HEX)

def fix_base64_padding(s: str) -> str:
    return s + "=" * (-len(s) % 4)

def decrypt_encrypted_string(encrypted_text: str) -> str:
    if ":" not in encrypted_text:
        raise ValueError("Encrypted text format invalid (no colon).")
    iv_b64, cipher_b64 = encrypted_text.split(":", 1)
    iv_b64 = fix_base64_padding(iv_b64.strip())
    cipher_b64 = fix_base64_padding(cipher_b64.strip())

    iv = base64.b64decode(iv_b64)
    ciphertext = base64.b64decode(cipher_b64)

    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, iv)
    plain_padded = cipher.decrypt(ciphertext)
    plain = unpad(plain_padded, AES.block_size)
    return plain.decode("utf-8")

class MQTT_AES_Tool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MQTT AES256-CBC Viewer -- mangetic 1117")
        self.geometry("1000x600")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.mqtt_client = None
        self.mqtt_thread = None
        self.mqtt_connected = False

        self.max_lines = 5000
        self.max_entries = max(1, self.max_lines // 2)
        self.line_buffer = deque(maxlen=self.max_entries)

        self._build_ui()

    def _build_ui(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        ttk.Label(top_frame, text="MQTT Server:").pack(side=tk.LEFT)
        self.entry_host = ttk.Entry(top_frame, width=25)
        self.entry_host.insert(0, "zbwd.12321.run")
        self.entry_host.pack(side=tk.LEFT, padx=4)

        ttk.Label(top_frame, text="Port:").pack(side=tk.LEFT)
        self.entry_port = ttk.Entry(top_frame, width=6)
        self.entry_port.insert(0, "10096")
        self.entry_port.pack(side=tk.LEFT, padx=4)

        self.btn_connect = ttk.Button(top_frame, text="Connect", command=self.connect_mqtt)
        self.btn_connect.pack(side=tk.LEFT, padx=6)
        self.btn_disconnect = ttk.Button(top_frame, text="Disconnect", command=self.disconnect_mqtt, state=tk.DISABLED)
        self.btn_disconnect.pack(side=tk.LEFT, padx=2)

        main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

        left_frame = ttk.Frame(main_pane, width=300)
        main_pane.add(left_frame, weight=0)

        ttk.Label(left_frame, text="Subscriptions (one topic per box):").pack(anchor=tk.W, pady=(4,2), padx=4)

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

        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=1)

        self.text_display = tk.Text(right_frame, wrap="char")
        self.text_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.text_display.yview)
        vsb.pack(side=tk.LEFT, fill=tk.Y)
        self.text_display.configure(yscrollcommand=vsb.set)

        base_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font.configure(weight="bold")
        self.text_display.tag_configure("timestamp", font=bold_font)
        self.text_display.tag_configure("topic", foreground="blue")
        self.text_display.tag_configure("qos", foreground="red")
        # JSON tags: key = 橙色, value = 绿色
        self.text_display.tag_configure("json_key", foreground="#FF8C00")
        self.text_display.tag_configure("json_value", foreground="#008800")

        bottom_controls = ttk.Frame(self)
        bottom_controls.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(bottom_controls, text="Clear", command=self.clear_display).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom_controls, text="Save", command=self.save_display).pack(side=tk.LEFT, padx=4)

    def _add_subscription_row(self, topic_default=""):
        row = ttk.Frame(self.sub_frame)
        entry = ttk.Entry(row, width=30)
        entry.insert(0, topic_default)
        entry.pack(side=tk.LEFT, padx=2, pady=2)
        row.pack(fill=tk.X)
        self.sub_entries.append((row, entry))

    def _remove_subscription_row(self):
        if not self.sub_entries:
            return
        row, entry = self.sub_entries.pop()
        topic = entry.get().strip()
        if topic and self.mqtt_client and self.mqtt_connected:
            try:
                self.mqtt_client.unsubscribe(topic)
                self._append_plain(f"[INFO] Unsubscribed (removed row): {topic}")
            except Exception as e:
                self._append_plain(f"[ERROR] Unsubscribe failed for {topic}: {e}")
        row.destroy()

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

        self.btn_connect.config(state=tk.DISABLED)
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect

        def run_client():
            try:
                self.mqtt_client.connect(host, port, keepalive=60)
                self.mqtt_client.loop_forever()
            except Exception as e:
                self._append_plain(f"[ERROR] MQTT connect failed: {e}")
                self.btn_connect.config(state=tk.NORMAL)

        self.mqtt_thread = threading.Thread(target=run_client, daemon=True)
        self.mqtt_thread.start()
        self._append_plain("[INFO] Connecting to MQTT...")

    def disconnect_mqtt(self):
        if self.mqtt_client:
            try:
                self.mqtt_client.disconnect()
            except:
                pass
        self.btn_disconnect.config(state=tk.DISABLED)
        self.btn_connect.config(state=tk.NORMAL)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
            self._append_plain("[INFO] Connected to MQTT broker")
            self.after(0, lambda: self.btn_disconnect.config(state=tk.NORMAL))
            self.after(0, lambda: self.btn_connect.config(state=tk.DISABLED))
        else:
            self._append_plain(f"[ERROR] Failed to connect, rc={rc}")
            self.after(0, lambda: self.btn_connect.config(state=tk.NORMAL))

    def _on_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
        self._append_plain("[INFO] Disconnected from MQTT")
        self.after(0, lambda: self.btn_connect.config(state=tk.NORMAL))
        self.after(0, lambda: self.btn_disconnect.config(state=tk.DISABLED))

    def unsubscribe_entry(self, entry):
        topic = entry.get().strip()
        if topic and self.mqtt_client and self.mqtt_connected:
            try:
                self.mqtt_client.unsubscribe(topic)
                self._append_plain(f"[INFO] Unsubscribed: {topic}")
            except Exception as e:
                self._append_plain(f"[ERROR] Unsubscribe failed: {topic} {e}")

    def subscribe_all(self):
        if not self.mqtt_client or not self.mqtt_connected:
            messagebox.showwarning("Warning", "MQTT not connected")
            return

        for _, entry in self.sub_entries:
            self.unsubscribe_entry(entry)

        for _, entry in self.sub_entries:
            topic = entry.get().strip()
            if topic:
                try:
                    self.mqtt_client.subscribe(topic, qos=1)
                    self._append_plain(f"[INFO] Subscribed: {topic}")
                except Exception as e:
                    self._append_plain(f"[ERROR] Subscribe {topic} failed: {e}")

    def unsubscribe_all(self):
        if not self.mqtt_client or not self.mqtt_connected:
            messagebox.showwarning("Warning", "MQTT not connected")
            return
        for _, entry in self.sub_entries:
            self.unsubscribe_entry(entry)

    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8', errors='ignore')
        except:
            payload = str(msg.payload)
        try:
            decrypted = decrypt_encrypted_string(payload)
            # 尝试解析 JSON；若成功则保存为对象，便于高亮渲染
            try:
                parsed = json.loads(decrypted)
                decrypted_obj = parsed
            except json.JSONDecodeError:
                decrypted_obj = decrypted
        except Exception as e:
            decrypted_obj = f"[DECRYPT ERROR] {e}  RAW: {payload}"

        tz = timezone(timedelta(hours=8))
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        self.after(0, lambda: self._append_msg(timestamp, msg.topic, msg.qos, decrypted_obj))

    def _append_msg(self, timestamp, topic, qos, decrypted):
        self.line_buffer.append(("msg", timestamp, topic, str(qos), decrypted))
        self._refresh_display()

    def _append_plain(self, text):
        self.line_buffer.append(("plain", text))
        self._refresh_display()

    def _insert_json(self, obj, indent_level=0):
        indent = "  " * indent_level
        if isinstance(obj, dict):
            self.text_display.insert(tk.END, "{\n")
            first = True
            for k, v in obj.items():
                if not first:
                    self.text_display.insert(tk.END, ",\n")
                first = False
                self.text_display.insert(tk.END, indent + "  ")
                # key (橙色)
                self.text_display.insert(tk.END, json.dumps(k, ensure_ascii=False), ("json_key",))
                self.text_display.insert(tk.END, ": ")
                if isinstance(v, (dict, list)):
                    self._insert_json(v, indent_level + 1)
                else:
                    # value (绿色)，使用 json.dumps 保持字符串引号与转义
                    self.text_display.insert(tk.END, json.dumps(v, ensure_ascii=False), ("json_value",))
            self.text_display.insert(tk.END, "\n" + indent + "}")
        elif isinstance(obj, list):
            self.text_display.insert(tk.END, "[\n")
            for i, v in enumerate(obj):
                if i:
                    self.text_display.insert(tk.END, ",\n")
                self.text_display.insert(tk.END, indent + "  ")
                if isinstance(v, (dict, list)):
                    self._insert_json(v, indent_level + 1)
                else:
                    self.text_display.insert(tk.END, json.dumps(v, ensure_ascii=False), ("json_value",))
            self.text_display.insert(tk.END, "\n" + indent + "]")
        else:
            self.text_display.insert(tk.END, json.dumps(obj, ensure_ascii=False), ("json_value",))

    def _refresh_display(self):
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)
        for item in self.line_buffer:
            if item[0] == "plain":
                self.text_display.insert(tk.END, item[1] + "\n")
            elif item[0] == "msg":
                _, timestamp, topic, qos, decrypted = item
                self.text_display.insert(tk.END, timestamp, ("timestamp",))
                self.text_display.insert(tk.END, "  Topic: ")
                self.text_display.insert(tk.END, topic, ("topic",))
                self.text_display.insert(tk.END, "  QoS: ")
                self.text_display.insert(tk.END, qos, ("qos",))
                self.text_display.insert(tk.END, "\n")
                # JSON 对象则高亮渲染 key/value，否则作为普通文本插入
                if isinstance(decrypted, (dict, list)):
                    self._insert_json(decrypted, indent_level=0)
                    self.text_display.insert(tk.END, "\n")
                else:
                    self.text_display.insert(tk.END, str(decrypted) + "\n")
        self.text_display.see(tk.END)
        self.text_display.configure(state=tk.DISABLED)

    def clear_display(self):
        self.line_buffer.clear()
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)
        self.text_display.configure(state=tk.DISABLED)

    def save_display(self):
        if not self.line_buffer:
            messagebox.showinfo("Info", "No content to save")
            return
        fpath = filedialog.asksaveasfilename(title="Save as", defaultextension=".txt",
                                             filetypes=[("Text files", "*.txt")])
        if not fpath:
            return
        try:
            lines = []
            for item in self.line_buffer:
                if item[0] == "plain":
                    lines.append(item[1])
                elif item[0] == "msg":
                    _, timestamp, topic, qos, decrypted = item
                    lines.append(f"{timestamp}  Topic: {topic}  QoS: {qos}")
                    if isinstance(decrypted, (dict, list)):
                        lines.append(json.dumps(decrypted, ensure_ascii=False, indent=2))
                    else:
                        lines.append(str(decrypted))
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("Saved", f"Saved to: {fpath}")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")

    def on_close(self):
        try:
            if self.mqtt_client:
                self.mqtt_client.disconnect()
        except:
            pass
        self.destroy()

if __name__ == "__main__":
    app = MQTT_AES_Tool()
    app.mainloop()
