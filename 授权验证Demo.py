# -*- coding: utf-8 -*-
import base64
import json
import re
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


APP_NAME = "授权验证Demo"
LICENSE_FILE_NAME = "richlink_license"
BUILTIN_EXPIRE_TIME = "20260814154510"
KEY_HEX = "A0B1C2D3E4F5A1B2C3D4E5F6A2B3C4D5E6F7A3B4C5D6E7F8A4B5C6D7E8F9AF09"
AES_BLOCK_SIZE = 16
BEGIN_MARKER = "---RICHLINK BEGIN LICENSE KEY ---"
END_MARKER = "---RICHLINK END LICENSE KEY -----"
TIME_PATTERN = re.compile(r"^\d{14}$")


class LicenseError(Exception):
    pass


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def license_file_path():
    return app_dir() / LICENSE_FILE_NAME


def ensure_license_file():
    path = license_file_path()
    if not path.exists():
        path.touch()
    return path


def strip_license_markers(license_text):
    value = str(license_text or "").strip()
    value = value.replace(BEGIN_MARKER, "")
    value = value.replace(END_MARKER, "")
    return re.sub(r"\s+", "", value)


def aes256_ecb_decrypt(data):
    cipher = Cipher(
        algorithms.AES(bytes.fromhex(KEY_HEX)),
        modes.ECB(),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


def decrypt_license_time(license_text):
    encoded_data = strip_license_markers(license_text)
    if not encoded_data:
        raise LicenseError("授权文件内容为空。")

    try:
        encrypted_data = base64.b64decode(encoded_data, validate=True)
    except Exception as exc:
        raise LicenseError(f"授权文件 Base64 解码失败：{exc}") from exc

    if len(encrypted_data) == 0 or len(encrypted_data) % AES_BLOCK_SIZE != 0:
        raise LicenseError("授权文件密文长度不是 16 字节整数倍。")

    plain_data = aes256_ecb_decrypt(encrypted_data)
    json_length = plain_data[0]
    json_end = 1 + json_length
    if json_length <= 0 or json_end > len(plain_data):
        raise LicenseError("授权文件长度包头异常。")

    json_bytes = plain_data[1:json_end]
    padding = plain_data[json_end:]
    if any(byte != 0xFF for byte in padding):
        raise LicenseError("授权文件 FF 补位校验失败。")

    try:
        parsed_json = json.loads(json_bytes.decode("utf-8"))
    except Exception as exc:
        raise LicenseError(f"授权文件 JSON 解析失败：{exc}") from exc

    expire_time = str(parsed_json.get("time", "")).strip()
    if not TIME_PATTERN.fullmatch(expire_time):
        raise LicenseError("授权文件 JSON 中的 time 必须是 14 位数字。")
    return expire_time


def parse_expire_time(expire_time):
    expire_time = str(expire_time).strip()
    if not TIME_PATTERN.fullmatch(expire_time):
        raise LicenseError("授权时间必须是 14 位数字，格式例如：20260814154510")
    return datetime.strptime(expire_time, "%Y%m%d%H%M%S")


def load_authorization():
    path = ensure_license_file()
    license_text = path.read_text(encoding="utf-8").strip()
    if license_text:
        return {
            "source": "richlink_license",
            "expire_time": decrypt_license_time(license_text),
            "path": path,
        }
    return {
        "source": "代码内置时间",
        "expire_time": BUILTIN_EXPIRE_TIME,
        "path": path,
    }


def check_authorization(now=None):
    auth_info = load_authorization()
    expire_dt = parse_expire_time(auth_info["expire_time"])
    now_dt = (now or datetime.now()).replace(microsecond=0)
    if expire_dt < now_dt:
        raise LicenseError(
            "license过期了，无法使用。\n\n"
            f"授权来源：{auth_info['source']}\n"
            f"授权时间：{expire_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"当前时间：{now_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    auth_info["expire_dt"] = expire_dt
    auth_info["now_dt"] = now_dt
    return auth_info


class DemoApp(tk.Tk):
    def __init__(self, auth_info):
        super().__init__()
        self.auth_info = auth_info
        self.title(APP_NAME)
        self.geometry("420x220")
        self.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        container = ttk.Frame(self, padding=18)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="授权验证通过", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor=tk.W, pady=(0, 12))
        ttk.Label(container, text=f"授权来源：{self.auth_info['source']}").pack(anchor=tk.W, pady=3)
        ttk.Label(container, text=f"到期时间：{self.auth_info['expire_dt'].strftime('%Y-%m-%d %H:%M:%S')}").pack(anchor=tk.W, pady=3)
        ttk.Label(container, text=f"授权文件：{self.auth_info['path']}").pack(anchor=tk.W, pady=3)

        button_frame = ttk.Frame(container)
        button_frame.pack(anchor=tk.W, pady=(18, 0))
        ttk.Button(button_frame, text="确定", command=self.destroy).pack(side=tk.LEFT)


def show_error_and_exit(message):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("授权失败", message)
    root.destroy()


if __name__ == "__main__":
    try:
        authorization = check_authorization()
    except Exception as exc:
        show_error_and_exit(str(exc))
        sys.exit(1)

    app = DemoApp(authorization)
    app.mainloop()
