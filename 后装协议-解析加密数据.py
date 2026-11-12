"""后装协议加密数据解析工具（GUI 版）。"""

import re
import tkinter as tk
import zlib
from tkinter import messagebox, ttk

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


DEFAULT_MCU_KEY = "ECFC69A548ADA26877661AF3AA89CBEBCFD8973CA572B7A1ED16E9F36C807DBD"
DEFAULT_DATA = (
    "5555002A400102001E383635383639303833393336343630"
    "BDC52015087AF8B694D18FE8CD03543BAAAA"
)


def normalize_hex(value: str, field_name: str) -> str:
    """去除常见分隔符，并验证十六进制输入。"""
    normalized = re.sub(r"[\s,:;\-_]", "", value).upper()
    if not normalized:
        raise ValueError(f"{field_name}不能为空")
    if not re.fullmatch(r"[0-9A-F]+", normalized):
        raise ValueError(f"{field_name}只能包含十六进制字符 0-9、A-F")
    if len(normalized) % 2:
        raise ValueError(f"{field_name}的十六进制字符数必须为偶数")
    return normalized


def decrypt_protocol_data(mcu_key: str, raw_data: str) -> dict[str, str | bool]:
    """按原脚本协议解密数据并返回格式化结果。"""
    hex_key = normalize_hex(mcu_key, "MCUKEY")
    hex_data = normalize_hex(raw_data, "data")

    if len(hex_key) != 64:
        raise ValueError("MCUKEY 必须是 64 个十六进制字符（32 字节 AES-256 密钥）")
    if len(hex_data) <= 52:
        raise ValueError("data 长度不足，至少需要 24 字节头、1 个密文块和 2 字节帧尾")

    ciphertext_hex = hex_data[48:-4]
    if not ciphertext_hex:
        raise ValueError("data 中没有可解密的密文")
    if len(ciphertext_hex) % 32:
        raise ValueError("data 的密文部分必须是 16 字节的整数倍")

    cipher = Cipher(
        algorithms.AES(bytes.fromhex(hex_key)),
        modes.ECB(),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    decrypted_bytes = decryptor.update(bytes.fromhex(ciphertext_hex)) + decryptor.finalize()
    decrypted_hex = decrypted_bytes.hex().upper()

    complete_hex = hex_data[:48] + decrypted_hex + hex_data[-4:]
    formatted_data = " ".join(
        complete_hex[index : index + 2] for index in range(0, len(complete_hex), 2)
    )

    # 保持原脚本的协议规则：填充字节 FF 不参与校验，末尾 4 字节为原始校验和。
    unpadded_hex = decrypted_hex.replace("FF", "")
    if len(unpadded_hex) < 8:
        raise ValueError("解密后的数据不足，无法提取 4 字节校验和")

    checksum_source = hex_data[4:48] + unpadded_hex[:-8]
    calculated_checksum = f"{zlib.adler32(bytes.fromhex(checksum_source)):08X}"
    original_checksum = unpadded_hex[-8:]

    return {
        "decrypted_data": formatted_data,
        "decrypted_payload": " ".join(
            decrypted_hex[index : index + 2]
            for index in range(0, len(decrypted_hex), 2)
        ),
        "calculated_checksum": calculated_checksum,
        "original_checksum": original_checksum,
        "checksum_ok": calculated_checksum == original_checksum,
    }


class DecryptApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("后装协议加密数据解析工具")
        self.root.geometry("860x650")
        self.root.minsize(720, 560)

        self.status_var = tk.StringVar(value="请输入 MCUKEY 和加密 data")
        self.checksum_var = tk.StringVar(value="尚未解密")

        self._configure_style()
        self._build_ui()
        self.root.bind("<Control-Return>", lambda _event: self.decrypt())

    def _configure_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Result.TLabel", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(6, weight=1)

        ttk.Label(container, text="后装协议加密数据解析", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            container,
            text="支持带空格、换行或常见分隔符的十六进制数据；Ctrl + Enter 可快速解密。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        ttk.Label(container, text="MCUKEY（AES-256，32 字节）").grid(
            row=2, column=0, sticky="w", pady=(0, 6)
        )
        self.key_entry = ttk.Entry(container, font=("Consolas", 11))
        self.key_entry.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        self.key_entry.insert(0, DEFAULT_MCU_KEY)

        ttk.Label(container, text="加密 data").grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.data_text = tk.Text(
            container,
            height=6,
            wrap="word",
            font=("Consolas", 11),
            relief="solid",
            borderwidth=1,
            undo=True,
        )
        self.data_text.grid(row=5, column=0, sticky="nsew", pady=(0, 14))
        self.data_text.insert("1.0", DEFAULT_DATA)

        result_frame = ttk.LabelFrame(container, text="解密结果", padding=12)
        result_frame.grid(row=6, column=0, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)

        ttk.Label(result_frame, textvariable=self.checksum_var, style="Result.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        output_holder = ttk.Frame(result_frame)
        output_holder.grid(row=1, column=0, sticky="nsew")
        output_holder.columnconfigure(0, weight=1)
        output_holder.rowconfigure(0, weight=1)

        self.output_text = tk.Text(
            output_holder,
            wrap="word",
            font=("Consolas", 11),
            relief="solid",
            borderwidth=1,
            state="disabled",
        )
        self.output_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(output_holder, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(container)
        button_frame.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(button_frame, text="解密", command=self.decrypt).pack(side="left")
        ttk.Button(button_frame, text="复制解密数据", command=self.copy_result).pack(
            side="left", padx=8
        )
        ttk.Button(button_frame, text="清空", command=self.clear).pack(side="left")
        ttk.Label(button_frame, textvariable=self.status_var, style="Hint.TLabel").pack(
            side="right"
        )

    def _set_output(self, value: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", value)
        self.output_text.configure(state="disabled")

    def decrypt(self) -> None:
        try:
            result = decrypt_protocol_data(
                self.key_entry.get(), self.data_text.get("1.0", "end-1c")
            )
        except (ValueError, TypeError) as exc:
            self._set_output("")
            self.checksum_var.set("解密失败")
            self.status_var.set("请检查输入")
            messagebox.showerror("输入或解密错误", str(exc), parent=self.root)
            return

        self._set_output(str(result["decrypted_data"]))
        check_mark = "通过" if result["checksum_ok"] else "不一致"
        self.checksum_var.set(
            f"校验{check_mark}  |  计算值：{result['calculated_checksum']}  "
            f"原始值：{result['original_checksum']}"
        )
        self.status_var.set("解密完成")

    def copy_result(self) -> None:
        result = self.output_text.get("1.0", "end-1c").strip()
        if not result:
            messagebox.showinfo("提示", "请先完成解密", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(result)
        self.root.update_idletasks()
        self.status_var.set("解密数据已复制到剪贴板")

    def clear(self) -> None:
        self.key_entry.delete(0, "end")
        self.data_text.delete("1.0", "end")
        self._set_output("")
        self.checksum_var.set("尚未解密")
        self.status_var.set("已清空")
        self.key_entry.focus_set()


def main() -> None:
    root = tk.Tk()
    DecryptApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
