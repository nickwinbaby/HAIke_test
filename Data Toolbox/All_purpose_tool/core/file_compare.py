"""文件及文件夹对比逻辑。"""

from __future__ import annotations

from dataclasses import dataclass, replace
import difflib
import os
from pathlib import Path
from threading import Event
from typing import Callable
import xml.etree.ElementTree as ET
import zipfile

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WORD_TAG = f"{{{WORD_NS}}}"
BINARY_EXTENSIONS = {
    ".bin", ".elf", ".exe", ".dll", ".so", ".img", ".rom", ".fw",
    ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".pdf", ".png", ".jpg",
    ".jpeg", ".gif", ".bmp", ".ico", ".mp3", ".wav", ".mp4", ".avi",
}


@dataclass(frozen=True)
class FileDiffRow:
    left_number: int | None
    right_number: int | None
    left_text: str
    right_text: str
    status: str


@dataclass(frozen=True)
class FileCompareResult:
    left_path: Path
    right_path: Path
    left_size: int
    right_size: int
    identical: bool
    text_comparison: bool
    rows: tuple[FileDiffRow, ...]
    same_lines: int
    deleted_lines: int
    added_lines: int
    hex_comparison: bool = False


@dataclass(frozen=True)
class FolderCompareEntry:
    relative_path: str
    status: str
    item_type: str = "文件"
    left_size: int | None = None
    right_size: int | None = None
    left_mtime: float | None = None
    right_mtime: float | None = None


@dataclass(frozen=True)
class FolderCompareResult:
    left_path: Path
    right_path: Path
    entries: tuple[FolderCompareEntry, ...]

    @property
    def identical(self) -> bool:
        return all(entry.status == "same" for entry in self.entries)

    def count(self, status: str) -> int:
        return sum(entry.status == status for entry in self.entries)


def _word_paragraph_text(paragraph: ET.Element) -> str:
    """提取一个Word段落的可见文字、制表符和换行。"""
    parts: list[str] = []
    for element in paragraph.iter():
        if element.tag == f"{WORD_TAG}t":
            parts.append(element.text or "")
        elif element.tag == f"{WORD_TAG}tab":
            parts.append("\t")
        elif element.tag in (f"{WORD_TAG}br", f"{WORD_TAG}cr"):
            parts.append("\n")
    return "".join(parts)


def _read_docx_lines(path: Path) -> list[str]:
    """按正文顺序提取DOCX段落与表格行，不依赖Word或python-docx。"""
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"无法读取DOCX文件：{path.name}") from exc
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise ValueError(f"DOCX正文XML损坏：{path.name}") from exc
    body = root.find(f"{WORD_TAG}body")
    if body is None:
        return []
    lines: list[str] = []
    for block in body:
        if block.tag == f"{WORD_TAG}p":
            paragraph_text = _word_paragraph_text(block)
            paragraph_lines = paragraph_text.splitlines() or [""]
            lines.extend(f"{line}\n" for line in paragraph_lines)
        elif block.tag == f"{WORD_TAG}tbl":
            for row in block.findall(f"{WORD_TAG}tr"):
                cells: list[str] = []
                for cell in row.findall(f"{WORD_TAG}tc"):
                    paragraphs = [
                        _word_paragraph_text(paragraph)
                        for paragraph in cell.findall(f"{WORD_TAG}p")
                    ]
                    cells.append(" / ".join(paragraphs))
                lines.append("\t".join(cells) + "\n")
    return lines


def _read_text_lines(path: Path) -> list[str] | None:
    if path.suffix.lower() == ".docx":
        return _read_docx_lines(path)
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return None
    with path.open("rb") as source:
        sample = source.read(8192)
        control_count = sum(byte < 32 and byte not in (9, 10, 12, 13) for byte in sample)
        if b"\x00" in sample or (sample and control_count / len(sample) > 0.08):
            return None
        raw = sample + source.read()
    for encoding in ("utf-8-sig", "gb18030", "cp1252"):
        try:
            return raw.decode(encoding).splitlines(keepends=True)
        except UnicodeDecodeError:
            continue
    return None


def _files_equal(left: Path, right: Path, stop_event: Event | None = None) -> bool | None:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            if stop_event is not None and stop_event.is_set():
                return None
            left_chunk = left_file.read(1024 * 1024)
            right_chunk = right_file.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def _aligned_rows(
    left_lines: list[str],
    right_lines: list[str],
    stop_event: Event | None = None,
) -> tuple[FileDiffRow, ...] | None:
    rows: list[FileDiffRow] = []
    # 小文件关闭autojunk以获得更稳定的逐行结果；大文件启用它，避免大量
    # 重复行令SequenceMatcher出现极端CPU占用。
    autojunk = len(left_lines) + len(right_lines) > 4000
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=autojunk)
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if stop_event is not None and stop_event.is_set():
            return None
        left_block = left_lines[left_start:left_end]
        right_block = right_lines[right_start:right_end]
        block_size = max(len(left_block), len(right_block))
        status = "same" if tag == "equal" else "different"
        for offset in range(block_size):
            left_exists = offset < len(left_block)
            right_exists = offset < len(right_block)
            rows.append(FileDiffRow(
                left_start + offset + 1 if left_exists else None,
                right_start + offset + 1 if right_exists else None,
                left_block[offset] if left_exists else "",
                right_block[offset] if right_exists else "",
                status,
            ))
    return tuple(rows)


def _binary_hex_rows(
    left: Path,
    right: Path,
    stop_event: Event | None = None,
    bytes_per_row: int = 16,
) -> tuple[FileDiffRow, ...] | None:
    """按相同文件偏移生成左右HEX行，不尝试把二进制内容解码成文字。"""
    def format_hex_line(chunk: bytes) -> str:
        hex_part = " ".join(f"{byte:02X}" for byte in chunk)
        # Beyond/十六进制查看器常见的尾列：可打印ASCII原样显示，
        # 控制字符和其他不可打印字节用点代替。
        ascii_part = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in chunk)
        return f"{hex_part:<47}  |{ascii_part}|"

    rows: list[FileDiffRow] = []
    offset = 0
    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            if stop_event is not None and stop_event.is_set():
                return None
            left_chunk = left_file.read(bytes_per_row)
            right_chunk = right_file.read(bytes_per_row)
            if not left_chunk and not right_chunk:
                break
            rows.append(FileDiffRow(
                offset if left_chunk else None,
                offset if right_chunk else None,
                format_hex_line(left_chunk),
                format_hex_line(right_chunk),
                "same" if left_chunk == right_chunk else "different",
            ))
            offset += bytes_per_row
    return tuple(rows)


def compare_files(
    left_path: str | Path,
    right_path: str | Path,
    hide_same: bool = True,
    stop_event: Event | None = None,
) -> FileCompareResult | None:
    """比较两个文件；文本文件生成左右对齐的逐行差异。"""
    left = Path(left_path)
    right = Path(right_path)
    if not left.is_file() or not right.is_file():
        raise ValueError("请选择两个有效文件")
    identical = _files_equal(left, right, stop_event)
    if identical is None:
        return None
    left_lines = _read_text_lines(left)
    right_lines = _read_text_lines(right)
    if left_lines is None or right_lines is None:
        rows = _binary_hex_rows(left, right, stop_event)
        if rows is None:
            return None
        same = sum(row.status == "same" for row in rows)
        deleted = sum(row.status != "same" and row.left_number is not None for row in rows)
        added = sum(row.status != "same" and row.right_number is not None for row in rows)
        return FileCompareResult(
            left.resolve(), right.resolve(), left.stat().st_size, right.stat().st_size,
            identical, False, rows, same, deleted, added, True,
        )
    if stop_event is not None and stop_event.is_set():
        return None
    rows = _aligned_rows(left_lines, right_lines, stop_event)
    if rows is None:
        return None
    same = sum(row.status == "same" for row in rows)
    deleted = sum(row.status != "same" and row.left_number is not None for row in rows)
    added = sum(row.status != "same" and row.right_number is not None for row in rows)
    return FileCompareResult(
        left.resolve(), right.resolve(), left.stat().st_size, right.stat().st_size,
        identical, True, rows, same, deleted, added,
    )


def _folder_items(folder: Path) -> dict[str, tuple[Path, bool]]:
    """扫描文件与子文件夹；保留空文件夹，跳过无权限访问的分支。"""
    items: dict[str, tuple[Path, bool]] = {}

    def ignore_error(_error):
        return None

    for root, directories, files in os.walk(folder, onerror=ignore_error):
        root_path = Path(root)
        for name in directories:
            path = root_path / name
            items[path.relative_to(folder).as_posix()] = (path, True)
        for name in files:
            path = root_path / name
            items[path.relative_to(folder).as_posix()] = (path, False)
    return items


def compare_folders(
    left_path: str | Path,
    right_path: str | Path,
    progress_callback: ProgressCallback | None = None,
    status_callback: StatusCallback | None = None,
    stop_event: Event | None = None,
) -> FolderCompareResult | None:
    """只比较目录清单和文件属性，不读取文件内容。"""
    left = Path(left_path)
    right = Path(right_path)
    if not left.is_dir() or not right.is_dir():
        raise ValueError("请选择两个有效文件夹")
    left_items = _folder_items(left)
    right_items = _folder_items(right)
    relative_paths = sorted(set(left_items) | set(right_items), key=str.casefold)
    entries: list[FolderCompareEntry] = []
    total = len(relative_paths)
    for index, relative_path in enumerate(relative_paths, 1):
        if stop_event is not None and stop_event.is_set():
            return None
        if status_callback is not None:
            status_callback(f"正在比较：{relative_path}（{index}/{total}）")
        left_item = left_items.get(relative_path)
        right_item = right_items.get(relative_path)
        if left_item is None:
            right_path_item, right_is_dir = right_item
            right_stat = right_path_item.stat()
            entries.append(FolderCompareEntry(
                relative_path, "only_right",
                "文件夹" if right_is_dir else "文件",
                right_size=None if right_is_dir else right_stat.st_size,
                right_mtime=right_stat.st_mtime,
            ))
        elif right_item is None:
            left_path_item, left_is_dir = left_item
            left_stat = left_path_item.stat()
            entries.append(FolderCompareEntry(
                relative_path, "only_left",
                "文件夹" if left_is_dir else "文件",
                left_size=None if left_is_dir else left_stat.st_size,
                left_mtime=left_stat.st_mtime,
            ))
        else:
            left_path_item, left_is_dir = left_item
            right_path_item, right_is_dir = right_item
            left_stat = left_path_item.stat()
            right_stat = right_path_item.stat()
            if stop_event is not None and stop_event.is_set():
                return None
            if left_is_dir != right_is_dir:
                status = "different"
                item_type = "类型冲突"
            elif left_is_dir:
                status = "same"
                item_type = "文件夹"
            else:
                # 文件夹模式只比较系统文件属性，不打开文件读取内容。
                # 修改时间按界面显示的秒级精度比较。
                same_attributes = (
                    left_stat.st_size == right_stat.st_size
                    and int(left_stat.st_mtime) == int(right_stat.st_mtime)
                )
                status = "same" if same_attributes else "different"
                item_type = "文件"
            entries.append(FolderCompareEntry(
                relative_path,
                status,
                item_type,
                None if left_is_dir else left_stat.st_size,
                None if right_is_dir else right_stat.st_size,
                left_stat.st_mtime,
                right_stat.st_mtime,
            ))
        if progress_callback is not None:
            progress_callback(index, total)
    # 像目录对比工具一样，将子项差异向父文件夹汇总；这样折叠时也能看出目录有差异。
    entry_map = {entry.relative_path: entry for entry in entries}
    for relative_path in sorted(entry_map, key=lambda value: value.count("/"), reverse=True):
        entry = entry_map[relative_path]
        if entry.status == "same" or "/" not in relative_path:
            continue
        parent_path = relative_path.rsplit("/", 1)[0]
        parent = entry_map.get(parent_path)
        if parent is not None and parent.item_type == "文件夹" and parent.status == "same":
            entry_map[parent_path] = replace(parent, status="different")
    entries = [entry_map[path] for path in relative_paths]
    return FolderCompareResult(left.resolve(), right.resolve(), tuple(entries))
