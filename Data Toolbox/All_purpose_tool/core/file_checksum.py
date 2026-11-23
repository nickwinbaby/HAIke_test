"""文件哈希值及CRC校验值计算逻辑。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from threading import Event
from typing import Callable, Iterable
import zlib


ProgressCallback = Callable[[int, int], None]
CRC_RL_LINE_END = re.compile(r"\\?(?:\r\n?|\n)")
SUPPORTED_ALGORITHMS = {"md5", "sha1", "sha256", "crc32", "crc32_rl"}


class _Crc32Rl:
    """对规范化的配置行增量计算 CRC-32/IEEE。"""

    def __init__(self, encoding: str):
        self._encoding = encoding
        self._crc = 0
        self._pending = ""
        self._needs_final_lf = False

    def update(self, text: str) -> None:
        text = self._pending + text
        # 文件分块可能在反斜杠、CR 或 CRLF 中间截断。
        suffix_size = 0
        if text.endswith("\\\r"):
            suffix_size = 2
        elif text.endswith(("\\", "\r")):
            suffix_size = 1
        self._pending = text[-suffix_size:] if suffix_size else ""
        if suffix_size:
            text = text[:-suffix_size]
        if text:
            normalized = CRC_RL_LINE_END.sub("\n", text)
            self._crc = zlib.crc32(normalized.encode(self._encoding), self._crc)
            self._needs_final_lf = not normalized.endswith("\n")

    def hexdigest(self) -> str:
        crc = self._crc
        if self._pending or self._needs_final_lf:
            crc = zlib.crc32("\n".encode(self._encoding), crc)
        return f"{crc:08X}"


def _select_algorithms(algorithms: Iterable[str]) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(str(name).strip().lower() for name in algorithms))
    invalid = [name for name in selected if name not in SUPPORTED_ALGORITHMS]
    if invalid:
        raise ValueError(f"不支持的校验算法：{', '.join(invalid)}")
    if not selected:
        raise ValueError("请至少选择一种校验算法")
    return selected


@dataclass(frozen=True)
class Md5Result:
    path: Path
    size: int
    checksums: dict[str, str]

    @property
    def md5(self) -> str:
        return self.checksums.get("md5", "")

    @property
    def sha1(self) -> str:
        return self.checksums.get("sha1", "")

    @property
    def sha256(self) -> str:
        return self.checksums.get("sha256", "")

    @property
    def crc32(self) -> str:
        return self.checksums.get("crc32", "")


def collect_files(paths: Iterable[str | Path]) -> list[Path]:
    """展开文件和文件夹，返回去重后的文件列表。"""
    files: list[Path] = []
    seen: set[str] = set()
    for source in paths:
        path = Path(source).expanduser()
        candidates = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for candidate in candidates:
            resolved = candidate.resolve()
            key = str(resolved).casefold()
            if key not in seen:
                seen.add(key)
                files.append(resolved)
    return files


def calculate_checksums(
    file_path: str | Path,
    algorithms: Iterable[str] = ("md5",),
    progress_callback: ProgressCallback | None = None,
    stop_event: Event | None = None,
    chunk_size: int = 1024 * 1024,
) -> Md5Result | None:
    """一次分块读取计算一个或多个校验值；取消时返回 ``None``。"""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在：{path}")
    selected = _select_algorithms(algorithms)
    size = path.stat().st_size
    bytes_read = 0
    hashers = {
        name: hashlib.new(name)
        for name in selected
        if name not in {"crc32", "crc32_rl"}
    }
    crc_value = 0
    # Latin-1 在这里仅作字节的无损映射，以保留配置文件中的原始字节。
    crc_rl = _Crc32Rl("latin-1") if "crc32_rl" in selected else None
    with path.open("rb") as file_obj:
        while True:
            if stop_event is not None and stop_event.is_set():
                return None
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            for hasher in hashers.values():
                hasher.update(chunk)
            if "crc32" in selected:
                crc_value = zlib.crc32(chunk, crc_value)
            if crc_rl is not None:
                crc_rl.update(chunk.decode("latin-1"))
            bytes_read += len(chunk)
            if progress_callback is not None:
                progress_callback(bytes_read, size)
    if progress_callback is not None and size == 0:
        progress_callback(0, 0)
    checksums = {name: hasher.hexdigest() for name, hasher in hashers.items()}
    if "crc32" in selected:
        checksums["crc32"] = f"{crc_value & 0xFFFFFFFF:08x}"
    if crc_rl is not None:
        checksums["crc32_rl"] = crc_rl.hexdigest()
    # 保持用户勾选顺序，便于UI按相同顺序展示。
    ordered = {name: checksums[name] for name in selected}
    return Md5Result(path=path.resolve(), size=size, checksums=ordered)


def calculate_bytes_checksums(
    data: bytes,
    algorithms: Iterable[str] = ("md5",),
    *,
    text_encoding: str = "latin-1",
) -> dict[str, str]:
    """计算内存中文本数据的哈希/CRC值，供文本输入模式使用。"""
    selected = _select_algorithms(algorithms)
    checksums = {
        name: hashlib.new(name, data).hexdigest()
        for name in selected
        if name not in {"crc32", "crc32_rl"}
    }
    if "crc32" in selected:
        checksums["crc32"] = f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"
    if "crc32_rl" in selected:
        crc_rl = _Crc32Rl(text_encoding)
        crc_rl.update(data.decode(text_encoding))
        checksums["crc32_rl"] = crc_rl.hexdigest()
    return {name: checksums[name] for name in selected}


def calculate_md5(
    file_path: str | Path,
    progress_callback: ProgressCallback | None = None,
    stop_event: Event | None = None,
    chunk_size: int = 1024 * 1024,
) -> Md5Result | None:
    """兼容调用：仅计算 MD5。"""
    return calculate_checksums(
        file_path,
        ("md5",),
        progress_callback,
        stop_event,
        chunk_size,
    )


def format_file_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"
