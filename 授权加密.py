# -*- coding: utf-8 -*-
import base64
import json
import re
import tkinter as tk
from tkinter import messagebox, ttk

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


APP_NAME = "授权加密"
KEY_HEX = "A0B1C2D3E4F5A1B2C3D4E5F6A2B3C4D5E6F7A3B4C5D6E7F8A4B5C6D7E8F9AF09"
BEGIN_MARKER = "---RICHLINK BEGIN LICENSE KEY ---"
END_MARKER = "---RICHLINK END LICENSE KEY -----"
AES_BLOCK_SIZE = 16
TIME_PATTERN = re.compile(r"^\d{14}$")


def aes256_ecb_crypt(data, encrypt=True):
    cipher = Cipher(
        algorithms.AES(bytes.fromhex(KEY_HEX)),
        modes.ECB(),
        backend=default_backend(),
    )
    cryptor = cipher.encryptor() if encrypt else cipher.decryptor()
    return cryptor.update(data) + cryptor.finalize()


def pad_ff(data):
    padding_len = (-len(data)) % AES_BLOCK_SIZE
    if padding_len == 0:
        return data
    return data + (b"\xff" * padding_len)


def build_json_text(expire_time):
    expire_time = str(expire_time).strip()
    if not TIME_PATTERN.fullmatch(expire_time):
        raise ValueError("到期时间必须是 14 位数字，格式例如：20260814150141")
    return f'{{"time":{expire_time}}}'


def encrypt_license(expire_time):
    json_text = build_json_text(expire_time)
    json_bytes = json_text.encode("utf-8")
    if len(json_bytes) > 255:
        raise ValueError("JSON 数据长度超过 1 字节长度包头可表示的范围。")

    plain_data = bytes([len(json_bytes)]) + json_bytes
    padded_plain_data = pad_ff(plain_data)
    encrypted_data = aes256_ecb_crypt(padded_plain_data, encrypt=True)
    encoded_data = base64.b64encode(encrypted_data).decode("ascii")
    license_text = f"{BEGIN_MARKER}\n{encoded_data}\n{END_MARKER}"
    return {
        "json": json_text,
        "plain_hex": padded_plain_data.hex().upper(),
        "license": license_text,
    }


def strip_license_markers(license_text):
    value = str(license_text or "").strip()
    value = re.sub(r"-{3}RICHLINK BEGIN LICENSE KEY -{3}", "", value)
    value = re.sub(r"-{3}RICHLINK END LICENSE KEY -{5}", "", value)
    return re.sub(r"\s+", "", value)


def decrypt_license(license_text):
    encoded_data = strip_license_markers(license_text)
    if not encoded_data:
        raise ValueError("请输入需要解密的授权数据。")

    try:
        encrypted_data = base64.b64decode(encoded_data, validate=True)
    except Exception as exc:
        raise ValueError(f"Base64 解码失败：{exc}") from exc

    if len(encrypted_data) == 0 or len(encrypted_data) % AES_BLOCK_SIZE != 0:
        raise ValueError("AES 密文长度必须是 16 字节的整数倍。")

    plain_data = aes256_ecb_crypt(encrypted_data, encrypt=False)
    json_length = plain_data[0]
    json_end = 1 + json_length
    if json_length <= 0 or json_end > len(plain_data):
        raise ValueError("长度包头异常，无法提取 JSON 数据。")

    json_bytes = plain_data[1:json_end]
    padding = plain_data[json_end:]
    if any(byte != 0xFF for byte in padding):
        raise ValueError("FF 补位校验失败，解密结果可能不是有效授权数据。")

    try:
        json_text = json_bytes.decode("utf-8")
        parsed_json = json.loads(json_text)
    except Exception as exc:
        raise ValueError(f"JSON 解析失败：{exc}") from exc

    return {
        "json": json.dumps(parsed_json, ensure_ascii=False, indent=4),
        "time": parsed_json.get("time", ""),
        "plain_hex": plain_data.hex().upper(),
    }


class LicenseTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("860x620")
        self.minsize(780, 560)

        self.expire_time_var = tk.StringVar()
        self.encrypt_status_var = tk.StringVar(value="请输入到期时间后生成授权。")
        self.decrypt_status_var = tk.StringVar(value="请粘贴完整授权文本或纯 Base64 数据。")

        self.create_widgets()

    def create_widgets(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        self.encrypt_frame = ttk.Frame(notebook, padding=14)
        self.decrypt_frame = ttk.Frame(notebook, padding=14)
        notebook.add(self.encrypt_frame, text="加密")
        notebook.add(self.decrypt_frame, text="解密")

        self.create_encrypt_tab()
        self.create_decrypt_tab()

    def create_encrypt_tab(self):
        frame = self.encrypt_frame
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="到期时间").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.expire_time_var, width=28).grid(row=0, column=1, sticky=tk.W, pady=6)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=1, column=1, sticky=tk.W, pady=(8, 6))
        ttk.Button(button_frame, text="生成授权", command=self.encrypt_action).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="复制输出", command=lambda: self.copy_text(self.encrypt_output_text)).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(button_frame, text="清空", command=self.clear_encrypt).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frame, text="内部明文 HEX").grid(row=2, column=0, sticky=tk.NW, pady=(12, 4))
        self.encrypt_hex_text = tk.Text(frame, height=4, wrap=tk.WORD)
        self.encrypt_hex_text.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=(12, 4))

        ttk.Label(frame, text="授权输出").grid(row=3, column=0, sticky=tk.NW, pady=(12, 4))
        self.encrypt_output_text = tk.Text(frame, height=16, wrap=tk.WORD)
        self.encrypt_output_text.grid(row=4, column=0, columnspan=3, sticky=tk.NSEW)

        ttk.Label(frame, textvariable=self.encrypt_status_var).grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))

    def create_decrypt_tab(self):
        frame = self.decrypt_frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="授权数据").grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        self.decrypt_input_text = tk.Text(frame, height=10, wrap=tk.WORD)
        self.decrypt_input_text.grid(row=1, column=0, columnspan=3, sticky=tk.NSEW)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, sticky=tk.W, pady=(10, 8))
        ttk.Button(button_frame, text="解密授权", command=self.decrypt_action).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="复制 JSON", command=lambda: self.copy_text(self.decrypt_json_text)).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(button_frame, text="清空", command=self.clear_decrypt).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frame, text="到期时间").grid(row=3, column=0, sticky=tk.W, pady=(6, 4))
        self.decrypt_time_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.decrypt_time_var, state="readonly", width=28).grid(row=3, column=1, sticky=tk.W)

        ttk.Label(frame, text="JSON 输出").grid(row=4, column=0, sticky=tk.W, pady=(12, 4))
        self.decrypt_json_text = tk.Text(frame, height=10, wrap=tk.WORD)
        self.decrypt_json_text.grid(row=5, column=0, columnspan=3, sticky=tk.NSEW)

        ttk.Label(frame, textvariable=self.decrypt_status_var).grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))

    @staticmethod
    def text_value(text_widget):
        return text_widget.get("1.0", tk.END).strip()

    @staticmethod
    def set_text(text_widget, value):
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", value)

    def copy_text(self, text_widget):
        value = self.text_value(text_widget)
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update()

    def encrypt_action(self):
        try:
            result = encrypt_license(self.expire_time_var.get())
            self.set_text(self.encrypt_hex_text, result["plain_hex"])
            self.set_text(self.encrypt_output_text, result["license"])
            self.encrypt_status_var.set(f"生成成功：{result['json']}")
        except Exception as exc:
            messagebox.showerror("加密失败", str(exc))
            self.encrypt_status_var.set("生成失败。")

    def decrypt_action(self):
        try:
            result = decrypt_license(self.text_value(self.decrypt_input_text))
            self.decrypt_time_var.set(str(result["time"]))
            self.set_text(self.decrypt_json_text, result["json"])
            self.decrypt_status_var.set(f"解密成功，明文 HEX：{result['plain_hex']}")
        except Exception as exc:
            messagebox.showerror("解密失败", str(exc))
            self.decrypt_status_var.set("解密失败。")

    def clear_encrypt(self):
        self.expire_time_var.set("")
        self.set_text(self.encrypt_hex_text, "")
        self.set_text(self.encrypt_output_text, "")
        self.encrypt_status_var.set("请输入到期时间后生成授权。")

    def clear_decrypt(self):
        self.set_text(self.decrypt_input_text, "")
        self.decrypt_time_var.set("")
        self.set_text(self.decrypt_json_text, "")
        self.decrypt_status_var.set("请粘贴完整授权文本或纯 Base64 数据。")


if __name__ == "__main__":
    app = LicenseTool()
    app.mainloop()
