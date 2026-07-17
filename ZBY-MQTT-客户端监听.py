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

def hex_to_bytes(hex_str): return bytes.fromhex(hex_str)

KEY_BYTES = hex_to_bytes(FIXED_KEY_HEX)
IV_BYTES_FIXED = hex_to_bytes(FIXED_IV_HEX)

def fix_base64_padding(s: str) -> str:
    return s + "=" * (-len(s) % 4)

def decrypt_encrypted_string(encrypted_text: str) -> str:
    if ":" not in encrypted_text:
        raise ValueError("Encrypted text format invalid (no colon).")
    iv_b64, cipher_b64 = encrypted_text.split(":", 1)
    iv = base64.b64decode(fix_base64_padding(iv_b64.strip()))
    ciphertext = base64.b64decode(fix_base64_padding(cipher_b64.strip()))
    cipher = AES.new(KEY_BYTES, AES.MODE_CBC, iv)
    plain = unpad(cipher.decrypt(ciphertext), AES.block_size)
    return plain.decode("utf-8")


class MQTT_AES_Tool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MQTT AES256-CBC Viewer - mangetic - 1120")
        self.geometry("1000x600")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.mqtt_client = None
        self.mqtt_thread = None
        self.mqtt_connected = False

        # buffer
        self.max_lines = 2000
        self.max_entries = max(1, self.max_lines // 2)
        self.line_buffer = deque(maxlen=self.max_entries)

        ### >>> 新增：保存日志相关变量 >>> ###
        self.saving_enabled = False
        self.save_file = None
        self.save_path = None
        self.save_lock = threading.Lock()
        ### <<< END 新增 >>> ###

        self._build_ui()

    # --------------------------- UI ---------------------------
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
        main_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        left_frame = ttk.Frame(main_pane, width=300)
        main_pane.add(left_frame, weight=0)

        ttk.Label(left_frame, text="Subscriptions (one topic per box):").pack(anchor=tk.W, pady=(4, 2), padx=4)

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

        # text styles
        base_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font = tkfont.Font(self.text_display, self.text_display.cget("font"))
        bold_font.configure(weight="bold")

        self.text_display.tag_configure("timestamp", font=bold_font)
        self.text_display.tag_configure("topic", foreground="blue")
        self.text_display.tag_configure("qos", foreground="red")
        self.text_display.tag_configure("json_key", foreground="#FF8C00")
        self.text_display.tag_configure("json_value", foreground="#008800")

        bottom_controls = ttk.Frame(self)
        bottom_controls.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(bottom_controls, text="Clear", command=self.clear_display).pack(side=tk.LEFT, padx=4)

        ### >>> 修改：原来的 SAVE 按钮换成持续保存模式 >>> ###
        self.btn_save = ttk.Button(bottom_controls, text="Start Save", command=self.start_save)
        self.btn_save.pack(side=tk.LEFT, padx=4)

        self.btn_stop_save = ttk.Button(bottom_controls, text="Stop Save", command=self.stop_save, state=tk.DISABLED)
        self.btn_stop_save.pack(side=tk.LEFT, padx=4)
        ### <<< END 修改 >>> ###

    def _add_subscription_row(self, topic_default=""):
        row = ttk.Frame(self.sub_frame)
        entry = ttk.Entry(row, width=30)
        entry.insert(0, topic_default)
        entry.pack(side=tk.LEFT, padx=2, pady=2)
        row.pack(fill=tk.X)
        self.sub_entries.append((row, entry))

    def _remove_subscription_row(self):
        if not self.sub_entries: return
        row, entry = self.sub_entries.pop()
        topic = entry.get().strip()
        if topic and self.mqtt_client and self.mqtt_connected:
            try:
                self.mqtt_client.unsubscribe(topic)
                self._append_plain(f"[INFO] Unsubscribed (removed row): {topic}")
            except Exception as e:
                self._append_plain(f"[ERROR] Unsubscribe failed for {topic}: {e}")
        row.destroy()

    # --------------------------- MQTT ---------------------------
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

        def run():
            try:
                self.mqtt_client.connect(host, port, 60)
                self.mqtt_client.loop_forever()
            except Exception as e:
                self._append_plain(f"[ERROR] MQTT connect failed: {e}")
                self.btn_connect.config(state=tk.NORMAL)

        self.mqtt_thread = threading.Thread(target=run, daemon=True)
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
        if topic and self.mqtt_connected:
            try:
                self.mqtt_client.unsubscribe(topic)
                self._append_plain(f"[INFO] Unsubscribed: {topic}")
            except Exception as e:
                self._append_plain(f"[ERROR] Unsubscribe failed for {topic}: {e}")

    def subscribe_all(self):
        if not self.mqtt_connected:
            messagebox.showwarning("Warning", "MQTT not connected")
            return
        for _, entry in self.sub_entries:
            self.unsubscribe_entry(entry)
        for _, entry in self.sub_entries:
            topic = entry.get().strip()
            if topic:
                try:
                    self.mqtt_client.subscribe(topic, 1)
                    self._append_plain(f"[INFO] Subscribed: {topic}")
                except Exception as e:
                    self._append_plain(f"[ERROR] Subscribe failed: {e}")

    def unsubscribe_all(self):
        if not self.mqtt_connected:
            messagebox.showwarning("Warning", "MQTT not connected")
            return
        for _, entry in self.sub_entries:
            self.unsubscribe_entry(entry)

    # ----------------------------------------------------------
    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8', errors='ignore')
        except:
            payload = str(msg.payload)
        try:
            decrypted = decrypt_encrypted_string(payload)
            try:
                obj = json.loads(decrypted)
            except json.JSONDecodeError:
                obj = decrypted
        except Exception as e:
            obj = f"[DECRYPT ERROR] {e} RAW: {payload}"

        tz = timezone(timedelta(hours=8))
        timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        self.after(0, lambda: self._append_msg(timestamp, msg.topic, msg.qos, obj))

        ### >>> 日志实时保存 >>> ###
        if self.saving_enabled and self.save_file:
            with self.save_lock:
                try:
                    self.save_file.write(f"{timestamp}  Topic: {msg.topic}  QoS: {msg.qos}\n")
                    if isinstance(obj, (dict, list)):
                        self.save_file.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n\n")
                    else:
                        self.save_file.write(str(obj) + "\n\n")
                except Exception as e:
                    print("LOG SAVE ERROR:", e)
        ### <<< END >>> ###

    # --------------------------- Display ---------------------------
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
                self.text_display.insert(tk.END, json.dumps(k, ensure_ascii=False), "json_key")
                self.text_display.insert(tk.END, ": ")
                if isinstance(v, (dict, list)):
                    self._insert_json(v, indent_level + 1)
                else:
                    self.text_display.insert(tk.END, json.dumps(v, ensure_ascii=False), "json_value")
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
                    self.text_display.insert(tk.END, json.dumps(v, ensure_ascii=False), "json_value")
            self.text_display.insert(tk.END, "\n" + indent + "]")
        else:
            self.text_display.insert(tk.END, json.dumps(obj, ensure_ascii=False), "json_value")

    def _refresh_display(self):
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)

        for item in self.line_buffer:
            if item[0] == "plain":
                self.text_display.insert(tk.END, item[1] + "\n")
            else:
                _, timestamp, topic, qos, decrypted = item

                self.text_display.insert(tk.END, timestamp, "timestamp")
                self.text_display.insert(tk.END, "  Topic: ")
                self.text_display.insert(tk.END, topic, "topic")
                self.text_display.insert(tk.END, "  QoS: ")
                self.text_display.insert(tk.END, qos, "qos")
                self.text_display.insert(tk.END, "\n")

                if isinstance(decrypted, (dict, list)):
                    self._insert_json(decrypted)
                    self.text_display.insert(tk.END, "\n")
                else:
                    self.text_display.insert(tk.END, str(decrypted) + "\n")

        # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
        # ----------- 新增：严格限制 2000 行 -----------
        total_lines = int(self.text_display.index('end-1c').split('.')[0])
        if total_lines > self.max_lines:
            remove_count = total_lines - self.max_lines
            self.text_display.delete("1.0", f"{remove_count}.0")
        # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑

        self.text_display.see(tk.END)
        self.text_display.configure(state=tk.DISABLED)

    def clear_display(self):
        self.line_buffer.clear()
        self.text_display.configure(state=tk.NORMAL)
        self.text_display.delete("1.0", tk.END)
        self.text_display.configure(state=tk.DISABLED)

    # ------------------- 新增持续 SAVE 功能 -------------------
    def start_save(self):
        if self.saving_enabled:
            messagebox.showinfo("Hint", "Already saving logs.")
            return

        path = filedialog.asksaveasfilename(
            title="Save log as...",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            # 非锁定方式打开
            self.save_file = open(path, "a", encoding="utf-8", buffering=1)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")
            return

        self.save_path = path
        self.saving_enabled = True
        self.btn_save.config(state=tk.DISABLED)
        self.btn_stop_save.config(state=tk.NORMAL)

        self._append_plain(f"[INFO] Log saving started: {path}")

    def stop_save(self):
        if not self.saving_enabled:
            return
        self.saving_enabled = False

        if self.save_file:
            try:
                self.save_file.close()
            except:
                pass

        self.save_file = None
        self.btn_save.config(state=tk.NORMAL)
        self.btn_stop_save.config(state=tk.DISABLED)

        self._append_plain("[INFO] Log saving stopped.")

    # ------------------- CLOSE -------------------
    def on_close(self):
        self.stop_save()
        try:
            if self.mqtt_client:
                self.mqtt_client.disconnect()
        except:
            pass
        self.destroy()


if __name__ == "__main__":
    app = MQTT_AES_Tool()
    app.mainloop()
