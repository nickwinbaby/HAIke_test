"""AES加解密核心逻辑，与界面完全解耦。"""

from __future__ import annotations

import base64
import re

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


BLOCK_SIZE = AES.block_size


def _hex_bytes(value: str, field_name: str) -> bytes:
    compact = re.sub(r"(?i)0x", "", value.strip())
    compact = re.sub(r"[\s,;:_-]+", "", compact)
    if not compact:
        raise ValueError(f"请输入{field_name}")
    if re.search(r"[^0-9a-fA-F]", compact) or len(compact) % 2:
        raise ValueError(f"{field_name}必须是偶数长度的HEX数据")
    return bytes.fromhex(compact)


def _formatted_bytes(value: str, value_format: str, field_name: str) -> bytes:
    if value_format == "Text":
        if value == "":
            raise ValueError(f"请输入{field_name}")
        return value.encode("utf-8")
    if value_format == "Hex":
        return _hex_bytes(value, field_name)
    raise ValueError(f"未知的{field_name}格式")


def _key_bytes(value: str, value_format: str, key_bits: int) -> bytes:
    key = _formatted_bytes(value, value_format, "密钥")
    expected = key_bits // 8
    if len(key) != expected:
        raise ValueError(f"{key_bits}位AES密钥必须正好为{expected}字节，当前为{len(key)}字节")
    return key


def _cipher(mode: str, key: bytes, iv_value: str, iv_format: str):
    if mode == "ECB":
        return AES.new(key, AES.MODE_ECB)
    if mode == "CBC":
        iv = _formatted_bytes(iv_value, iv_format, "偏移IV")
        if len(iv) != BLOCK_SIZE:
            raise ValueError(f"CBC偏移IV必须正好为{BLOCK_SIZE}字节，当前为{len(iv)}字节")
        return AES.new(key, AES.MODE_CBC, iv=iv)
    raise ValueError("当前版本支持CBC和ECB运算模式")


def _pad_data(data: bytes, padding: str) -> bytes:
    if padding == "PKCS7":
        return pad(data, BLOCK_SIZE, style="pkcs7")
    if padding == "Zeros":
        missing = (-len(data)) % BLOCK_SIZE
        return data + (b"\x00" * missing)
    if padding == "None":
        if len(data) % BLOCK_SIZE:
            raise ValueError("不填充时，输入数据长度必须是16字节的整数倍")
        return data
    raise ValueError("未知的填充模式")


def _unpad_data(data: bytes, padding: str) -> bytes:
    if padding == "PKCS7":
        try:
            return unpad(data, BLOCK_SIZE, style="pkcs7")
        except ValueError as exc:
            raise ValueError("PKCS7填充校验失败，请检查密钥、偏移或密文") from exc
    if padding == "Zeros":
        return data.rstrip(b"\x00")
    if padding == "None":
        return data
    raise ValueError("未知的填充模式")


def _plain_bytes(value: str, encoding: str) -> bytes:
    if encoding == "UTF-8":
        return value.encode("utf-8")
    if encoding == "Hex":
        return _hex_bytes(value, "输入数据")
    raise ValueError("未知的字符编码")


def _cipher_bytes(value: str, output_format: str) -> bytes:
    if output_format == "Hex":
        return _hex_bytes(value, "密文")
    if output_format == "Base64":
        try:
            return base64.b64decode(value.strip(), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("密文不是有效的Base64数据") from exc
    raise ValueError("未知的密文格式")


def aes_encrypt(
    value: str,
    key: str,
    *,
    mode: str = "CBC",
    padding: str = "PKCS7",
    key_bits: int = 128,
    key_format: str = "Text",
    iv: str = "",
    iv_format: str = "Text",
    encoding: str = "UTF-8",
    output_format: str = "Base64",
) -> str:
    """AES加密；字符编码控制明文输入，输出格式控制密文展示。"""
    key_data = _key_bytes(key, key_format, key_bits)
    cipher = _cipher(mode, key_data, iv, iv_format)
    encrypted = cipher.encrypt(_pad_data(_plain_bytes(value, encoding), padding))
    if output_format == "Base64":
        return base64.b64encode(encrypted).decode("ascii")
    if output_format == "Hex":
        return encrypted.hex().upper()
    raise ValueError("未知的密文格式")


def aes_decrypt(
    value: str,
    key: str,
    *,
    mode: str = "CBC",
    padding: str = "PKCS7",
    key_bits: int = 128,
    key_format: str = "Text",
    iv: str = "",
    iv_format: str = "Text",
    encoding: str = "UTF-8",
    input_format: str = "Base64",
) -> str:
    """AES解密；输入格式控制密文解析，字符编码控制明文输出。"""
    key_data = _key_bytes(key, key_format, key_bits)
    encrypted = _cipher_bytes(value, input_format)
    if not encrypted or len(encrypted) % BLOCK_SIZE:
        raise ValueError("AES密文长度必须是16字节的整数倍")
    cipher = _cipher(mode, key_data, iv, iv_format)
    plain = _unpad_data(cipher.decrypt(encrypted), padding)
    if encoding == "Hex":
        return plain.hex().upper()
    if encoding == "UTF-8":
        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("解密结果不是有效的UTF-8文本，可将字符编码改为Hex查看") from exc
    raise ValueError("未知的字符编码")
