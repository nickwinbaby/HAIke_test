import codecs
import hashlib
import io
import os
import queue
import re
import tempfile
import threading
import time
import uuid

from PyQt5.QtCore import QSize, QSignalBlocker, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QKeySequence, QPainter, QTextCursor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from lz4.frame import LZ4FrameDecompressor
except ImportError:
    LZ4FrameDecompressor = None

PREVIEW_PAGE_BYTES = 4096
EDIT_MAX_BYTES = 1024 * 1024
LZ4_IO_BYTES = 64 * 1024
LZ4_CACHE_MEMORY_BYTES = 1024 * 1024
LZ4_PREVIEW_MAX_BYTES = 128 * 1024 * 1024


def decode_lz4_preview(chunks, check_cancel):
    decoder = LZ4FrameDecompressor()
    cache = tempfile.SpooledTemporaryFile(max_size=LZ4_CACHE_MEMORY_BYTES, mode="w+b")
    size = 0
    try:
        for compressed in chunks:
            while compressed or (not decoder.eof and not decoder.needs_input):
                check_cancel()
                if decoder.eof:
                    decoder.reset()
                try:
                    data = decoder.decompress(compressed, max_length=LZ4_IO_BYTES)
                except RuntimeError as error:
                    raise GP03DeviceError("LZ4 解压失败：文件损坏或不是标准 LZ4 帧。") from error
                size += len(data)
                if size > LZ4_PREVIEW_MAX_BYTES:
                    raise GP03DeviceError("LZ4 解压后超过 128 MiB。请下载原文件后在本地解压。")
                cache.write(data)
                compressed = decoder.unused_data or b""
        check_cancel()
        if not decoder.eof:
            raise GP03DeviceError("LZ4 文件不完整，未能读到帧结束。")
        cache.seek(0)
        return cache, size
    except BaseException:
        cache.close()
        raise


class GP03Error(IOError):
    pass


class GP03DeviceError(Exception):
    pass


class GP03Cancelled(Exception):
    pass


class GP03ByteStream:
    """Adapts SerialReader's exclusive RX queue to a blocking byte stream."""

    def __init__(self, rx_queue, write_bytes, cancel_event, timestamp_factory=None):
        self.rx_queue = rx_queue
        self.write_bytes = write_bytes
        self.cancel_event = cancel_event
        self.timestamp_factory = timestamp_factory or (lambda: time.strftime("[%Y-%m-%d %H:%M:%S.000]"))
        self.buffer = bytearray()
        self.allow_cancelled = False
        self.log_callback = None

    def log_received_line(self, line):
        if self.log_callback:
            self.log_callback("received", line, self.timestamp_factory())

    def write(self, data):
        if self.cancel_event.is_set() and not self.allow_cancelled:
            raise GP03Cancelled()
        written = self.write_bytes(data)
        if written == len(data) and self.log_callback:
            command = data.decode("utf-8", errors="replace").rstrip("\r\n")
            self.log_callback("sent", command, self.timestamp_factory())
        return written

    def read(self, count):
        while not self.buffer:
            if self.cancel_event.is_set() and not self.allow_cancelled:
                raise GP03Cancelled()
            try:
                data = self.rx_queue.get(timeout=0.1)
            except queue.Empty:
                return b""
            if data is None:
                raise GP03Error("串口连接已关闭。")
            self.buffer.extend(data)
        size = min(count, len(self.buffer))
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def take_unread(self):
        remaining = bytearray(self.buffer)
        self.buffer.clear()
        while True:
            try:
                data = self.rx_queue.get_nowait()
            except queue.Empty:
                break
            if data is not None:
                remaining.extend(data)
        return bytes(remaining)


class GP03DeviceFiles:
    DEFAULT_READ_CHUNK = 256
    PATH_LIMIT = 63
    ITEM = re.compile(r'^\+FILELIST:"(.*)",([0-9]+),([FD])$')

    def __init__(self, stream, cancel_event, mtu=0):
        self.stream = stream
        self.cancel_event = cancel_event
        self.rx_buffer = bytearray()
        self.timeout_ms = 10000
        self.deadline = 0
        self.read_chunk_limit = min(self.DEFAULT_READ_CHUNK, mtu) if mtu > 0 else self.DEFAULT_READ_CHUNK
        self.cleanup_mode = False

    @staticmethod
    def parent(path):
        index = path.rfind("/")
        return "/" if index <= 0 else path[:index]

    @classmethod
    def path_arg(cls, path):
        if path == "/":
            return path
        if (not path or not path.startswith("/") or path.endswith("/") or "//" in path
                or ".." in path or "." in path.split("/") or '"' in path
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or len(path.encode("utf-8")) > cls.PATH_LIMIT):
            raise ValueError("设备路径须以 / 开头，且不超过 63 个 UTF-8 字节。")
        return path

    @classmethod
    def child(cls, directory, name):
        if not name or "/" in name:
            raise ValueError("请输入单个文件名或目录名。")
        return cls.path_arg(directory.rstrip("/") + "/" + name)

    @classmethod
    def quote(cls, path):
        return '"' + cls.path_arg(path) + '"'

    def _check_cancel(self):
        if self.cancel_event.is_set() and not self.cleanup_mode:
            raise GP03Cancelled()

    def _send(self, command):
        self._check_cancel()
        try:
            payload = (command + "\r\n").encode("utf-8")
            written = self.stream.write(payload)
            if written != len(payload):
                raise IOError("串口未能写入完整命令。")
        except GP03Cancelled:
            raise
        except Exception as error:
            raise GP03Error("串口发送失败：" + str(error)) from error
        self.timeout_ms = 90000 if command.startswith("AT+FILESIZE=") else 10000
        self.deadline = time.monotonic() + self.timeout_ms / 1000.0

    def _byte(self):
        while True:
            self._check_cancel()
            if time.monotonic() >= self.deadline:
                raise GP03Error("等待设备 AT 应答超时，请检查设备和串口。")
            if self.rx_buffer:
                value = self.rx_buffer[0]
                del self.rx_buffer[0]
                return value
            try:
                data = self.stream.read(4096)
            except GP03Cancelled:
                raise
            except Exception as error:
                raise GP03Error("串口读取失败：" + str(error)) from error
            if data:
                self.rx_buffer.extend(data)

    def _record(self, binary_header=None):
        content = bytearray()
        while True:
            value = self._byte()
            if value == 10:
                break
            content.append(value)
            if binary_header and bytes(content) == binary_header:
                return bytes(content).decode("utf-8", errors="replace"), True
            if len(content) > 8192:
                raise GP03Error("收到超长串口行，文件响应格式异常。")
        if content.endswith(b"\r"):
            content.pop()
        try:
            encoding = "utf-8" if content.startswith(b"+") else "ascii"
            return content.decode(encoding, errors="replace"), False
        except UnicodeDecodeError as error:
            raise GP03Error("设备响应包含无效字符。") from error

    @staticmethod
    def _is_error(line):
        return line == "ERROR" or line.startswith("+CME ERROR:")

    def _text(self, command, prefix):
        self._send(command)
        rows = []
        while True:
            line, _ = self._record()
            if line:
                self.stream.log_received_line(line)
            if line == "OK":
                return rows
            if self._is_error(line):
                raise GP03DeviceError((rows[-1] if rows else command) + " " + line)
            if line.startswith(prefix):
                rows.append(line)
                self.deadline = time.monotonic() + self.timeout_ms / 1000.0

    def command_ok(self, command):
        self._send(command)
        while True:
            line, _ = self._record()
            if line:
                self.stream.log_received_line(line)
            if line == "OK":
                return
            if self._is_error(line):
                raise GP03DeviceError(command + " " + line)

    def negotiate_mtu(self):
        rows = self._text("AT+DEVICEINFO=GetCapacity,MTU", "+DEVICEINFO:")
        values = []
        for row in rows:
            match = re.search(r"\+DEVICEINFO:GetCapacity,MTU,(\d+)", row, re.IGNORECASE)
            if match:
                values.append(int(match.group(1)))
        if len(values) != 1 or values[0] <= 0:
            raise GP03Error("MTU 查询应答格式异常。")
        self.read_chunk_limit = min(self.DEFAULT_READ_CHUNK, values[0])
        return values[0]

    def prepare(self):
        self.command_ok("AT+LOGCHANNEL=Null")
        return self.negotiate_mtu()

    @staticmethod
    def _one(rows):
        if len(rows) != 1:
            raise GP03Error("设备应答数量异常。")
        return rows[0]

    def list(self, directory):
        directory = self.path_arg(directory)
        rows = self._text("AT+FILELIST=" + self.quote(directory), "+FILELIST:")
        entries = []
        for row in rows[:-1]:
            match = self.ITEM.match(row)
            if not match or self.parent(match.group(1)) != directory:
                raise GP03Error("目录条目格式异常。")
            entries.append({
                "path": match.group(1), "name": match.group(1).rsplit("/", 1)[-1],
                "size": int(match.group(2)), "folder": match.group(3) == "D",
            })
        if not rows or rows[-1] != "+FILELIST:COUNT," + str(len(entries)):
            raise GP03Error("目录返回数量不符，请重新读取。")
        return sorted(entries, key=lambda entry: (not entry["folder"], entry["name"].casefold()))

    def capacity(self):
        line = self._one(self._text("AT+FSDF", "+FSDF:"))
        match = re.match(r"^\+FSDF:(\d+)%,size:(\d+)MB$", line)
        return ("已用 {}%   /   总容量 {} MB".format(match.group(1), match.group(2))
                if match else line)

    def _fsop(self, arguments, expected):
        response = self._one(self._text("AT+FSOP=" + arguments, "+FSOP:"))
        if response != "+FSOP:" + str(expected):
            raise GP03Error("FSOP 确认值异常：" + response)

    def mkdir(self, path):
        self._fsop("MKDIR," + self.quote(path), 0)

    def create(self, path):
        self._fsop("CREATE," + self.quote(path), 0)

    def move(self, source, target):
        self._fsop("MOVE," + self.quote(source) + "," + self.quote(target), 0)

    def delete(self, path):
        arg = self.quote(path)
        if self._one(self._text("AT+FILEDEL=" + arg, "+FILEDEL:")) != "+FILEDEL:" + arg + ",0":
            raise GP03Error("删除应答与请求路径不符。")

    def digest(self, path, size):
        arg = self.quote(path)
        response = self._one(self._text("AT+FILESIZE=" + arg, "+FILESIZE:"))
        prefix = "+FILESIZE:{},{},".format(arg, size)
        if not response.startswith(prefix) or not re.fullmatch(r"[a-fA-F0-9]{32}", response[len(prefix):]):
            raise GP03Error("文件大小或 MD5 应答不符，文件可能已变化。")
        return response[len(prefix):].lower()

    def _read_block(self, path_arg, offset, count):
        self._send("AT+FILEREAD={},{},{}".format(path_arg, offset, count))
        header = ("+FILEREAD:" + path_arg + ",").encode("utf-8")
        block = None
        detail = "FILEREAD"
        while True:
            line, matched = self._record(header)
            if matched:
                if block is not None:
                    raise GP03Error("收到重复的 FILEREAD 数据块。")
                digits = bytearray()
                while True:
                    value = self._byte()
                    if value == 44:
                        break
                    if len(digits) >= 5 or value < 48 or value > 57:
                        raise GP03Error("FILEREAD 二进制长度无效。")
                    digits.append(value)
                length = int(digits.decode("ascii"))
                self.stream.log_received_line(line + str(length))
                if length != count + 4:
                    raise GP03Error("FILEREAD 数据块长度不符。")
                data = bytearray(self._byte() for _ in range(count))
                checksum = 0
                for _ in range(4):
                    checksum = (checksum << 8) | self._byte()
                if self._byte() != 13 or self._byte() != 10:
                    raise GP03Error("FILEREAD 数据结束标志不正确。")
                a, b = 1, 0
                for value in data:
                    a = (a + value) % 65521
                    b = (b + a) % 65521
                if checksum != ((b << 16) | a):
                    raise GP03Error("FILEREAD 分片校验失败。")
                block = bytes(data)
            elif line == "OK":
                self.stream.log_received_line(line)
                if block is None:
                    raise GP03Error("FILEREAD 缺少数据。")
                return block
            elif self._is_error(line):
                self.stream.log_received_line(line)
                if block is None and count > 1 and detail == "+FILEREAD:-4":
                    return None
                raise GP03DeviceError(detail + " " + line)
            else:
                if line:
                    self.stream.log_received_line(line)
                if line.startswith("+FILEREAD:"):
                    detail = line

    def read_part(self, path, offset, count, progress=None):
        arg = self.quote(path)
        if count == 0:
            return b""
        result = bytearray()
        limit = min(count, self.read_chunk_limit)
        while len(result) < count:
            self._check_cancel()
            size = min(limit, count - len(result))
            block = self._read_block(arg, offset + len(result), size)
            if block is None:
                limit = size // 2
                continue
            result.extend(block)
            if progress:
                progress(len(result), count)
        self.read_chunk_limit = limit
        return bytes(result)

    @staticmethod
    def _hex(data):
        return data.hex().upper()

    def upload(self, local_path, target, replace, progress):
        with open(local_path, "rb") as source:
            self._upload(source, os.fstat(source.fileno()).st_size, target, replace, progress)

    def _upload(self, source, total, target, replace, progress, check_before_replace=None):
        target = self.path_arg(target)
        directory = self.parent(target)
        suffix = ".u" + uuid.uuid4().hex[:10]
        temporary = directory.rstrip("/") + "/" + suffix
        if len(temporary.encode("utf-8")) > self.PATH_LIMIT:
            temporary = "/" + suffix
        created = False
        try:
            if total > 0x7FFFFFFF:
                raise IOError("文件超过设备偏移范围。")
            self._check_cancel()
            self.create(temporary)
            created = True
            digest = hashlib.md5()
            offset = 0
            while True:
                self._check_cancel()
                chunk = source.read(128)
                if not chunk:
                    break
                self._fsop("WRITE,{},{},{}".format(self.quote(temporary), offset, self._hex(chunk)), offset + len(chunk))
                digest.update(chunk)
                offset += len(chunk)
                progress(offset, total)
            if offset != total or (total and self.digest(temporary, total) != digest.hexdigest()):
                raise IOError("上传文件校验失败。")
            self._check_cancel()
            if replace:
                if check_before_replace is not None:
                    if not total and self.file_entry(temporary)["size"] != 0:
                        raise IOError("临时文件大小校验失败。")
                    check_before_replace()
                    self._check_cancel()
                self._fsop("REPLACE,{},{}".format(self.quote(temporary), self.quote(target)), 0)
            else:
                self.move(temporary, target)
        except GP03Error as error:
            raise GP03Error(str(error) + "；请重连后检查临时文件 " + temporary) from error
        except Exception:
            if created:
                try:
                    self.cleanup_mode = True
                    if hasattr(self.stream, "allow_cancelled"):
                        self.stream.allow_cancelled = True
                    self.delete(temporary)
                except Exception as cleanup_error:
                    raise GP03Error("上传失败，临时文件待检查：{}；清理失败：{}".format(temporary, cleanup_error))
                finally:
                    self.cleanup_mode = False
                    if hasattr(self.stream, "allow_cancelled"):
                        self.stream.allow_cancelled = False
            raise

    def file_entry(self, path):
        current = next((item for item in self.list(self.parent(path))
                        if item["path"] == path and not item["folder"]), None)
        if current is None:
            raise IOError("所选文件已移走，请刷新目录。")
        return current

    def save_edited_file(self, path, data, original_size, original_digest, progress):
        def check_original():
            current = self.file_entry(path)
            if current["size"] != original_size or (original_size and self.digest(path, original_size) != original_digest):
                raise GP03DeviceError("设备上的原文件已变化，未覆盖。请重新打开文件再编辑。")

        check_original()
        with io.BytesIO(data) as source:
            self._upload(source, len(data), path, True, progress, check_original)

    def download(self, entry, local_path, progress):
        current = self.file_entry(entry["path"])
        size = current["size"]
        expected = self.digest(entry["path"], size) if size else None
        temp = os.path.join(os.path.dirname(local_path) or ".", ".gp03-" + uuid.uuid4().hex + ".part")
        digest = hashlib.md5()
        try:
            with open(temp, "xb") as output:
                offset = 0
                while offset < size:
                    self._check_cancel()
                    chunk = self.read_part(entry["path"], offset, min(self.DEFAULT_READ_CHUNK, size - offset))
                    output.write(chunk)
                    digest.update(chunk)
                    offset += len(chunk)
                    progress(offset, size)
                output.flush()
                os.fsync(output.fileno())
            if expected and digest.hexdigest() != expected:
                raise IOError("下载文件 MD5 不符，设备文件可能已变化。")
            self._check_cancel()
            if os.path.exists(local_path):
                os.replace(temp, local_path)
            else:
                os.rename(temp, local_path)
        finally:
            if os.path.exists(temp):
                os.remove(temp)


class GP03Worker(QThread):
    progress = pyqtSignal(int, int)
    completed = pyqtSignal(object, str, bool)
    serial_log = pyqtSignal(str, str, str)

    def __init__(self, stream, cancel_event, operation, mtu=0, parent=None):
        super().__init__(parent)
        self.stream = stream
        self.cancel_event = cancel_event
        self.operation = operation
        self.mtu = mtu

    def run(self):
        self.stream.log_callback = self.serial_log.emit
        device = GP03DeviceFiles(self.stream, self.cancel_event, self.mtu)
        last_update = 0.0

        def report_progress(done, total):
            nonlocal last_update
            now = time.monotonic()
            if done == total or now - last_update >= 0.05:
                last_update = now
                self.progress.emit(done, total)

        try:
            result = self.operation(device, report_progress)
            self.completed.emit(result, "", False)
        except GP03Cancelled:
            self.completed.emit(None, "", True)
        except Exception as error:
            self.completed.emit(None, str(error), False)


class GP03LineNumbers(QWidget):
    def paintEvent(self, event):
        editor = self.parentWidget()
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#eef2f6"))
        painter.setPen(QColor("#c9d3dd"))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.setFont(editor.font())
        painter.setPen(QColor("#485c70"))
        block = editor.firstVisibleBlock()
        while block.isValid():
            top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
            if top > event.rect().bottom():
                break
            if block.isVisible() and top + editor.blockBoundingRect(block).height() >= event.rect().top():
                painter.drawText(0, top, self.width() - 8, editor.fontMetrics().height(),
                                 Qt.AlignRight | Qt.AlignVCenter, str(block.blockNumber() + 1))
            block = block.next()


class GP03TextPreview(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.gutter = GP03LineNumbers(self)
        self.gutter.hide()
        self.show_line_numbers = False
        self.blockCountChanged.connect(self._layout_gutter)
        self.updateRequest.connect(self.gutter.update)

    def set_line_numbers(self, enabled):
        self.show_line_numbers = enabled
        self._layout_gutter()

    def _layout_gutter(self):
        width = 0
        if self.show_line_numbers:
            width = self.fontMetrics().horizontalAdvance("0" * max(2, len(str(self.blockCount())))) + 18
        if self.viewportMargins().left() != width:
            self.setViewportMargins(width, 0, 0, 0)
        rect = self.viewport().geometry()
        self.gutter.setGeometry(rect.left() - width, rect.top(), width, rect.height())
        self.gutter.setVisible(self.show_line_numbers)
        self.gutter.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_gutter()


class GP03HexBlockEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    @staticmethod
    def _group_digits(digits):
        lines = []
        for start in range(0, len(digits), 32):
            line = digits[start:start + 32]
            lines.append(" ".join(line[i:i + 2] for i in range(0, len(line), 2)))
        if not digits or len(digits) % 2:
            separator = ""
        else:
            separator = "\n" if len(digits) % 32 == 0 else " "
        return "\n".join(lines) + separator

    def set_bytes(self, data):
        self.setPlainText(self._group_digits(data.hex().upper()))

    def _reflow(self):
        text = self.toPlainText()
        digits = "".join(text.split())
        if len(digits) > 2 * EDIT_MAX_BYTES or not re.fullmatch(r"[0-9A-Fa-f]*", digits):
            return
        formatted = self._group_digits(digits.upper())
        if formatted == text:
            return
        cursor = self.textCursor()

        def formatted_position(position):
            count = len("".join(text[:position].split()))
            return count + count // 2

        anchor = formatted_position(cursor.anchor())
        position = formatted_position(cursor.position())
        edit = QTextCursor(self.document())
        edit.select(QTextCursor.Document)
        edit.insertText(formatted)
        cursor.setPosition(anchor)
        cursor.setPosition(position, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _edit_and_reflow(self, apply_edit):
        # Automatic separators and the user's input should undo together.
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            apply_edit()
            self._reflow()
        finally:
            cursor.endEditBlock()

    def insertFromMimeData(self, source):
        paste = super().insertFromMimeData
        self._edit_and_reflow(lambda: paste(source))

    def inputMethodEvent(self, event):
        edit = super().inputMethodEvent
        if event.commitString() or event.replacementLength():
            self._edit_and_reflow(lambda: edit(event))
        else:
            edit(event)

    def keyPressEvent(self, event):
        key = event.key()
        edit = super().keyPressEvent
        if any(event.matches(action) for action in (QKeySequence.Undo, QKeySequence.Redo, QKeySequence.Paste)):
            edit(event)
            return
        if key not in (Qt.Key_Backspace, Qt.Key_Delete) and not event.text() and not event.matches(QKeySequence.Cut):
            edit(event)
            return
        cursor = self.textCursor()
        if key in (Qt.Key_Backspace, Qt.Key_Delete) and event.modifiers() == Qt.NoModifier and not cursor.hasSelection():
            text = self.toPlainText()
            pos = cursor.position()
            if key == Qt.Key_Backspace and pos > 0 and text[pos - 1:pos].isspace():
                cursor.setPosition(pos - 1)
                self.setTextCursor(cursor)
            elif key == Qt.Key_Delete and text[pos:pos + 1].isspace():
                cursor.setPosition(pos + 1)
                self.setTextCursor(cursor)
        self._edit_and_reflow(lambda: edit(event))


class GP03FileSystemDialog(QDialog):
    def __init__(self, owner, begin_io, end_io, tr, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.begin_io = begin_io
        self.end_io = end_io
        self.tr = tr
        self.current = "/"
        self.entries = []
        self.loaded = False
        self.prepared = False
        self.mtu = 0
        self.worker = None
        self.stream = None
        self.cancel_event = None
        self.closing = False
        self.editing = False
        self.saving_preview = False
        self.preview_entry = None
        self.preview_data = b""
        self.preview_cache = None
        self.preview_cache_size = 0
        self.preview_text = None
        self.preview_format = None
        self.preview_connection = None
        self.hex_draft = None
        self.hex_block_range = None
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
                            Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.resize(1010, 620)
        self.setMinimumSize(810, 470)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        action_row = QHBoxLayout()
        action_row.setSpacing(5)
        self.new_button = QToolButton()
        self.new_button.setAutoRaise(True)
        self.new_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.new_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.new_button.setPopupMode(QToolButton.InstantPopup)
        new_menu = QMenu(self.new_button)
        self.mkdir_action = new_menu.addAction("新建目录", self.make_directory)
        self.create_action = new_menu.addAction("新建空文件", self.make_file)
        self.new_button.setMenu(new_menu)
        action_row.addWidget(self.new_button)
        self.upload_button = QToolButton()
        self.upload_button.setAutoRaise(True)
        self.upload_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.upload_button.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.upload_button.clicked.connect(self.upload)
        action_row.addWidget(self.upload_button)
        self.download_button = QToolButton()
        self.download_button.setAutoRaise(True)
        self.download_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.download_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.download_button.clicked.connect(self.download)
        action_row.addWidget(self.download_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        address_row = QHBoxLayout()
        address_row.setSpacing(5)
        self.up_button = QToolButton()
        self.up_button.setAutoRaise(True)
        self.up_button.clicked.connect(self.go_up)
        address_row.addWidget(self.up_button)
        self.address = QLineEdit("/")
        self.address.returnPressed.connect(self._navigate_address)
        address_row.addWidget(self.address, 1)
        self.go_button = QToolButton()
        self.go_button.setAutoRaise(True)
        self.go_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.go_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.go_button.clicked.connect(self._navigate_address)
        address_row.addWidget(self.go_button)
        self.refresh_button = QToolButton()
        self.refresh_button.setAutoRaise(True)
        self.refresh_button.clicked.connect(self.refresh)
        address_row.addWidget(self.refresh_button)
        self.capacity_label = QLabel("")
        self.count_label = QLabel("")
        address_row.addWidget(self.capacity_label)
        address_row.addWidget(self.count_label)
        root.addLayout(address_row)

        self.splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.folder_icon = QIcon()
        sizes = folder_icon.availableSizes() or [QSize(16, 16), QSize(32, 32)]
        # Supply the original artwork for every mode to prevent Qt tinting it.
        for size in sizes:
            pixmap = folder_icon.pixmap(size, QIcon.Normal, QIcon.Off)
            for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected, QIcon.Disabled):
                for state in (QIcon.Off, QIcon.On):
                    self.folder_icon.addPixmap(pixmap, mode, state)
        self.file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        self.list = QTreeWidget()
        self.list.setObjectName("gp03FileList")
        for view in (self.tree, self.list):
            view.setMouseTracking(True)
            view.setStyleSheet("""
            QTreeWidget {
                background-color: #ffffff;
                alternate-background-color: #e6edf4;
                border: 1px solid #b8c2cc;
                show-decoration-selected: 1;
            }
            QHeaderView::section {
                background-color: #f5f7f9;
                color: #304050;
                border: none;
                border-bottom: 1px solid #c6d0da;
                padding: 3px 8px;
            }
            QTreeWidget::item {
                border: 1px solid transparent;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #e6f2fc;
                color: #182635;
            }
            QTreeWidget::item:selected {
                background-color: #c6e2fb;
                border: 1px solid #75a7d4;
                color: #182635;
            }
            QTreeWidget#gp03FileList {
                outline: 0;
            }
            QTreeWidget#gp03FileList::item:selected {
                border-color: transparent;
            }
            """)
        self.list.setColumnCount(2)
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.header().setStretchLastSection(False)
        self.list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.list.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_menu = QMenu(self.list)
        self.preview_action = self.file_menu.addAction("")
        self.download_file_action = self.file_menu.addAction("")
        self.new_subfolder_action = self.file_menu.addAction("")
        self.item_menu_separator = self.file_menu.addSeparator()
        self.move_action = self.file_menu.addAction("")
        self.rename_action = self.file_menu.addAction("")
        self.delete_action = self.file_menu.addAction("")
        self.empty_list_menu = QMenu(self.list)
        self.new_blank_file_action = self.empty_list_menu.addAction("")

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(5)
        preview_toolbar = QHBoxLayout()
        self.preview_name = QLabel()
        self.preview_name.setStyleSheet("font-weight: 600; color: #253646;")
        self.preview_name.setTextFormat(Qt.PlainText)
        self.preview_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview_size = QLabel()
        self.preview_size.setStyleSheet("color: #506478;")
        self.preview_mode = QComboBox()
        self.preview_mode.addItems(["", "HEX"])
        self.preview_mode.setEnabled(False)
        preview_toolbar.addWidget(self.preview_name, 1)
        preview_toolbar.addWidget(self.preview_size)
        preview_toolbar.addWidget(self.preview_mode)
        preview_layout.addLayout(preview_toolbar)

        edit_toolbar = QHBoxLayout()
        self.preview_edit = QToolButton()
        self.preview_edit.setObjectName("gp03PreviewEdit")
        self.preview_edit.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.preview_edit.setStyleSheet("""
            QToolButton#gp03PreviewEdit {
                background: #edf5fd;
                color: #174978;
                border: 1px solid #92b4d4;
                border-radius: 4px;
                padding: 3px 8px;
            }
            QToolButton#gp03PreviewEdit:hover { background: #dcecfb; }
            QToolButton#gp03PreviewEdit[editing="true"] {
                background: #fff0ef;
                color: #9e2525;
                border-color: #d3918d;
            }
            QToolButton#gp03PreviewEdit[editing="true"]:hover { background: #fbe0de; }
            QToolButton#gp03PreviewEdit:disabled {
                background: #f2f4f6;
                color: #626e7b;
                border-color: #c8d0d8;
            }
        """)
        self.preview_edit.clicked.connect(self._toggle_preview_edit)
        self.preview_save = QToolButton()
        self.preview_save.setAutoRaise(True)
        self.preview_save.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.preview_save.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.preview_save.clicked.connect(self._save_preview)
        edit_toolbar.addWidget(self.preview_edit)
        self.hex_block_button = QToolButton()
        self.hex_block_button.setAutoRaise(True)
        self.hex_block_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.hex_block_button.clicked.connect(lambda: self._open_hex_block())
        edit_toolbar.addWidget(self.hex_block_button)
        edit_toolbar.addWidget(self.preview_save)
        self.preview_edit_status = QLabel()
        self.preview_edit_status.setStyleSheet("color: #a52222; font-weight: 600;")
        self.preview_edit_status.hide()
        edit_toolbar.addWidget(self.preview_edit_status)
        edit_toolbar.addStretch(1)
        preview_layout.addLayout(edit_toolbar)

        self.preview_views = QStackedWidget()
        self.preview_output = GP03TextPreview()
        self.preview_output.setObjectName("gp03TextPreview")
        self.preview_output.setStyleSheet("""
            QPlainTextEdit#gp03TextPreview {
                font-family: "Consolas", "Courier New";
                font-size: 11pt;
                background-color: #ffffff;
                color: #1d2d3d;
                border: 1px solid #b8c2cc;
                border-radius: 3px;
                padding: 0;
                selection-background-color: #d5e7fa;
                selection-color: #142b44;
            }
        """)
        self.preview_output.setReadOnly(True)
        font = (QFont("Consolas") if "Consolas" in QFontDatabase().families()
                else QFontDatabase.systemFont(QFontDatabase.FixedFont))
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        self.preview_output.setFont(font)
        self.preview_output.document().setDocumentMargin(9)
        self.preview_views.addWidget(self.preview_output)
        self.preview_output.document().modificationChanged.connect(self._update_preview_buttons)

        self.preview_hex = QTableWidget(0, 3)
        self.preview_hex.setObjectName("gp03HexPreview")
        self.preview_hex.setFont(font)
        self.preview_hex.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_hex.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.preview_hex.setWordWrap(False)
        self.preview_hex.cellDoubleClicked.connect(self._open_hex_row)
        copy_hex = QShortcut(QKeySequence.Copy, self.preview_hex)
        copy_hex.setContext(Qt.WidgetShortcut)
        copy_hex.activated.connect(self._copy_hex_selection)
        self.preview_hex.setGridStyle(Qt.SolidLine)
        self.preview_hex.verticalHeader().hide()
        self.preview_hex.setStyleSheet("""
            QTableWidget#gp03HexPreview {
                font-family: "Consolas", "Courier New";
                font-size: 10pt;
                border: 1px solid #aeb9c4;
                background-color: #ffffff;
                gridline-color: #d8e0e7;
            }
            QTableWidget#gp03HexPreview QHeaderView::section {
                background-color: #f5f7f9;
                color: #28394a;
                border: none;
                border-right: 1px solid #c4cfd9;
                border-bottom: 1px solid #aeb9c4;
                padding: 4px 6px;
                text-align: left;
            }
            QTableWidget#gp03HexPreview::item { padding: 0 6px; }
        """)
        header = self.preview_hex.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Fixed)
        rows = self.preview_hex.verticalHeader()
        rows.setSectionResizeMode(QHeaderView.Fixed)
        rows.setMinimumSectionSize(0)
        self.preview_views.addWidget(self.preview_hex)

        self.hex_block_panel = QWidget()
        block_layout = QVBoxLayout(self.hex_block_panel)
        block_layout.setContentsMargins(0, 0, 0, 0)
        self.hex_block_label = QLabel()
        block_layout.addWidget(self.hex_block_label)
        self.hex_block_input = GP03HexBlockEditor()
        self.hex_block_input.setFont(font)
        self.hex_block_input.setStyleSheet('font-family: "Consolas", "Courier New";')
        self.hex_block_input.document().modificationChanged.connect(self._update_preview_buttons)
        block_layout.addWidget(self.hex_block_input, 1)
        self.hex_block_error = QLabel()
        self.hex_block_error.setStyleSheet("color: #a52222;")
        self.hex_block_error.setWordWrap(True)
        self.hex_block_error.hide()
        self.hex_block_input.textChanged.connect(self.hex_block_error.hide)
        block_layout.addWidget(self.hex_block_error)
        block_actions = QHBoxLayout()
        block_actions.addStretch(1)
        self.hex_block_cancel = QPushButton()
        self.hex_block_cancel.setAutoDefault(False)
        self.hex_block_cancel.clicked.connect(self._cancel_hex_block)
        block_actions.addWidget(self.hex_block_cancel)
        self.hex_block_apply = QPushButton()
        self.hex_block_apply.setAutoDefault(False)
        self.hex_block_apply.clicked.connect(self._apply_hex_block)
        block_actions.addWidget(self.hex_block_apply)
        block_layout.addLayout(block_actions)
        self.preview_views.addWidget(self.hex_block_panel)
        preview_layout.addWidget(self.preview_views, 1)

        self.preview_pages = QWidget()
        page_layout = QHBoxLayout(self.preview_pages)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addStretch(1)
        self.preview_page = QSpinBox()
        self.preview_page.setRange(1, 1)
        self.preview_total_pages = QLabel()
        page_layout.addWidget(self.preview_page)
        page_layout.addWidget(self.preview_total_pages)
        preview_layout.addWidget(self.preview_pages)
        self.preview_pages.hide()
        self.preview_page.valueChanged.connect(self._render_preview)
        self.preview_mode.currentIndexChanged.connect(self._reset_preview_page)

        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.list)
        self.splitter.addWidget(preview_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([190, 240, 560])
        root.addWidget(self.splitter, 1)

        self.state = QLabel("")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setVisible(False)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        footer = QHBoxLayout()
        footer.addWidget(self.state, 1)
        footer.addWidget(self.progress, 1)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)

        self.tree.itemClicked.connect(self._tree_selected)
        self.tree.itemExpanded.connect(self._tree_expanded)
        self.list.itemDoubleClicked.connect(self._list_activated)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.preview_hex.itemSelectionChanged.connect(self._update_preview_buttons)
        self.list.customContextMenuRequested.connect(self._show_file_menu)
        self.tree.customContextMenuRequested.connect(self._show_folder_menu)
        self.update_language()
        self._update_buttons()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.prepared and self.worker is None:
            self.prepare_on_open()

    def update_language(self):
        english = getattr(self.owner, "language", "zh") == "en"
        self.setWindowTitle("GP03 File System" if english else "GP03 文件管理")
        texts = {
            "new": "New" if english else "新建",
            "mkdir": "New folder" if english else "新建目录",
            "create": "New empty file" if english else "新建空文件",
            "upload": "Upload" if english else "上传",
            "download": "Download" if english else "下载",
            "move": "Move" if english else "移动",
            "rename": "Rename" if english else "重命名",
            "delete": "Delete" if english else "删除",
            "preview": "Preview" if english else "预览",
            "up": "Up one level" if english else "上一级",
            "refresh": "Refresh" if english else "刷新",
        }
        self.new_button.setText(texts["new"])
        self.mkdir_action.setText(texts["mkdir"])
        self.create_action.setText(texts["create"])
        self.upload_button.setText(texts["upload"])
        self.download_button.setText(texts["download"])
        self.move_action.setText(texts["move"])
        self.rename_action.setText(texts["rename"])
        self.delete_action.setText(texts["delete"])
        self.preview_action.setText(texts["preview"])
        self.download_file_action.setText(texts["download"])
        self.new_subfolder_action.setText(texts["mkdir"])
        self.new_blank_file_action.setText(texts["create"])
        self.preview_mode.setItemText(0, "Text" if english else "文本")
        if self.preview_cache is not None:
            self._update_preview_size(self.preview_cache_size)
        self.preview_hex.setHorizontalHeaderLabels(
            ["Offset", "Hex bytes", "ASCII"] if english else ["Offset", "HEX 字节", "ASCII"]
        )
        self.preview_hex.ensurePolished()
        metrics = QFontMetrics(self.preview_hex.font())
        self.preview_hex.verticalHeader().setDefaultSectionSize(metrics.height() + 4)
        header_metrics = QFontMetrics(self.preview_hex.horizontalHeader().font())
        for col, chars in enumerate(("0" * 8, "FF " * 15 + "FF ", "W" * 16)):
            title = self.preview_hex.horizontalHeaderItem(col).text()
            width = max(metrics.horizontalAdvance(chars), header_metrics.horizontalAdvance(title)) + 18
            self.preview_hex.setColumnWidth(col, width)
        self.hex_block_button.setText("Edit block" if english else "多行编辑")
        self.hex_block_button.setToolTip("Edit the selected consecutive rows" if english else "编辑选中的连续行")
        self.hex_block_cancel.setText("Cancel" if english else "取消")
        self.hex_block_apply.setText("Apply" if english else "应用")
        self._update_hex_block_label()
        self.preview_output.setPlaceholderText("No file open" if english else "未打开文件")
        self.preview_save.setText("Save" if english else "保存")
        self.preview_page.setAccessibleName("Page" if english else "页码")
        if self.preview_entry is None:
            self.preview_name.setText(texts["preview"])
        self._update_preview_buttons()
        self.list.setHeaderLabels(["File", "Size"] if english else ["文件", "大小"])
        self.tree.setHeaderHidden(False)
        self.tree.setHeaderLabel("Folders" if english else "目录")
        self.up_button.setText("")
        self.up_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.up_button.setToolTip(texts["up"])
        self.go_button.setText("Go" if english else "前往")
        self.go_button.setToolTip("Open directory (Enter)" if english else "打开目录（回车）")
        self.refresh_button.setText("")
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_button.setToolTip(texts["refresh"])
        if english:
            self.cancel_button.setText("Cancel")
        else:
            self.cancel_button.setText("取消")
        if self.prepared:
            self.count_label.setText(
                "{} items  ·  MTU {}".format(len(self.entries), self.mtu)
                if english else "{} 项  ·  MTU {}".format(len(self.entries), self.mtu)
            )

    def _selected(self):
        item = self.list.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def _show_file_menu(self, position):
        if self.worker is not None:
            return
        item = self.list.itemAt(position)
        global_position = self.list.viewport().mapToGlobal(position)
        if item is None:
            directory = self.current
            action = self.empty_list_menu.exec_(global_position)
            if action == self.new_blank_file_action and self.worker is None and self.isVisible():
                self._create_entry(directory, folder=False)
            return
        self.list.setCurrentItem(item)
        self._show_item_menu(item.data(0, Qt.UserRole), global_position)

    def _show_folder_menu(self, position):
        item = self.tree.itemAt(position)
        if self.worker is not None or item is None:
            return
        path = item.data(0, Qt.UserRole)
        if path:
            entry = {"path": path, "name": item.text(0), "folder": True}
            self._show_item_menu(entry, self.tree.viewport().mapToGlobal(position))

    def _show_item_menu(self, entry, position):
        folder = entry["folder"]
        is_root = entry["path"] == "/"
        self.preview_action.setVisible(not folder)
        self.download_file_action.setVisible(not folder)
        self.new_subfolder_action.setVisible(folder)
        self.item_menu_separator.setVisible(not is_root)
        for action in (self.move_action, self.rename_action, self.delete_action):
            action.setVisible(not is_root)
        action = self.file_menu.exec_(position)
        handlers = {
            self.preview_action: self.preview,
            self.download_file_action: self._download_entry,
            self.new_subfolder_action: lambda item: self._create_entry(item["path"], folder=True),
            self.move_action: self.move_item,
            self.rename_action: self.rename_item,
            self.delete_action: self.delete_item,
        }
        if action in handlers and self.worker is None and self.isVisible():
            handlers[action](entry)

    def _set_enabled(self, enabled):
        self.cancel_button.setVisible(not enabled and not self.saving_preview)
        self.progress.setVisible(not enabled)
        self._update_buttons()

    def _update_buttons(self):
        idle = self.worker is None and not self.editing
        entry = self._selected()
        self.up_button.setEnabled(idle and self.current != "/")
        self.go_button.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.new_button.setEnabled(idle)
        self.upload_button.setEnabled(idle)
        self.download_button.setEnabled(idle and entry is not None and not entry["folder"])
        self.address.setEnabled(idle)
        self.tree.setEnabled(idle)
        self.list.setEnabled(idle)
        self._update_preview_buttons()

    def _run(self, title, operation, *, saving=False):
        if self.worker is not None or (self.editing and not saving):
            return
        stream = self.begin_io()
        if stream is None:
            return
        self.stream = stream
        self.cancel_event = stream.cancel_event
        self.state.setText(title)
        self.progress.setValue(0)
        self.saving_preview = saving
        self.worker = GP03Worker(stream, self.cancel_event, operation, self.mtu, self)
        self._set_enabled(False)
        self.worker.progress.connect(self._progress)
        self.worker.serial_log.connect(self._display_serial_event)
        self.worker.completed.connect(self._finished)
        self.worker.start()

    def _display_serial_event(self, direction, text, timestamp):
        if direction == "sent":
            self.owner.append_sent_log(text, "Serial", timestamp)
        else:
            raw = text.encode("utf-8")
            hex_text = " ".join("{:02X}".format(value) for value in raw)
            self.owner.update_log(timestamp, text, hex_text)

    def _finished(self, result, error, cancelled):
        worker = self.worker
        was_saving = self.saving_preview
        self.saving_preview = False
        self.worker = None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self.end_io(self.stream)
        self.stream = None
        self.cancel_event = None
        self._set_enabled(True)
        if self.closing:
            if isinstance(result, dict) and result.get("cache") is not None:
                result["cache"].close()
            self.close()
            if getattr(self.owner, "gp03_close_pending", False):
                self.owner.close()
            return
        if error and not cancelled:
            self.state.setText(error.replace("\n", " "))
            QMessageBox.warning(self, "GP03 文件管理", error)
        elif cancelled:
            self.state.setText("传输已取消。")
        else:
            self.state.setText("完成：" + str(result) if isinstance(result, str) and result else "操作完成")
            if isinstance(result, dict) and "entries" in result:
                if "mtu" in result:
                    self.mtu = result["mtu"]
                self._populate(result["entries"], result.get("capacity"), result["path"])
            elif isinstance(result, dict) and result.get("cache") is not None:
                self._show_preview(result["entry"], b"", cache=result["cache"], cache_size=result["cache_size"])
                self.state.setText("Decompressed LZ4 preview (read-only)" if self.owner.language == "en"
                                   else "LZ4 解压预览（只读）")
            elif isinstance(result, dict) and result.get("preview") is not None:
                if result.get("saved"):
                    self._update_saved_size(result["entry"])
                self._show_preview(result["entry"], result["preview"], result.get("hex_page"))
                self.preview_connection = result["connection"]
                if result.get("saved"):
                    self.state.setText("Saved" if self.owner.language == "en" else "已保存到设备")
            elif result == "refresh":
                self.refresh()
            elif result == "reload":
                self.refresh()
        self._update_buttons()
        if error and not cancelled and not was_saving:
            self.prepared = False

    def _progress(self, done, total):
        self.progress.setValue(0 if total == 0 else min(1000, int(1000 * done / total)))
        self.progress.setFormat("{} / {} B".format(done, total))

    def _reload_operation(self, device, _progress=None):
        entries = device.list(self.current)
        try:
            capacity = device.capacity()
        except GP03DeviceError:
            capacity = ""
        return {"entries": entries, "capacity": capacity, "path": self.current}

    def refresh(self):
        if not self.prepared:
            self.prepare_on_open()
            return
        self._run("读取目录...", self._reload_operation)

    def prepare_on_open(self):
        if self.worker is not None or self.prepared:
            return

        def operation(device, _progress):
            mtu = device.prepare()
            entries = device.list("/")
            try:
                capacity = device.capacity()
            except GP03DeviceError:
                capacity = ""
            return {"entries": entries, "capacity": capacity, "path": "/", "mtu": mtu}

        title = (
            "Preparing GP03 file system..."
            if getattr(self.owner, "language", "zh") == "en"
            else "设置日志通道并协商 MTU..."
        )
        self._run(title, operation)

    def _populate(self, entries, capacity, path):
        self._clear_preview()
        self.entries = entries
        self.loaded = True
        self.prepared = True
        self.current = path
        self.address.setText(path)
        self.capacity_label.setText(capacity or "")
        if getattr(self.owner, "language", "zh") == "en":
            self.count_label.setText("{} items  ·  MTU {}".format(len(entries), self.mtu))
        else:
            self.count_label.setText("{} 项  ·  MTU {}".format(len(entries), self.mtu))
        self.list.clear()
        for entry in entries:
            if entry["folder"]:
                continue
            item = QTreeWidgetItem([entry["name"], "{:,} B".format(entry["size"])])
            item.setData(0, Qt.UserRole, entry)
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setIcon(0, self.file_icon)
            self.list.addTopLevelItem(item)
        self._sync_tree(path, entries)
        self.state.setText("目录读取完成")

    def _folder_node(self, parent, path):
        item = QTreeWidgetItem([path.rsplit("/", 1)[-1] or "/"])
        item.setData(0, Qt.UserRole, path)
        item.setIcon(0, self.folder_icon)
        item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        parent.addChild(item)
        return item

    def _sync_tree(self, path, entries):
        # Only the listed directory is authoritative; keep other loaded branches.
        with QSignalBlocker(self.tree):
            root = self.tree.topLevelItem(0)
            if root is None:
                root = self._folder_node(self.tree.invisibleRootItem(), "/")
            parent = root
            prefix = ""
            for name in filter(None, path.split("/")):
                prefix += "/" + name
                child = next((parent.child(i) for i in range(parent.childCount())
                              if parent.child(i).data(0, Qt.UserRole) == prefix), None)
                parent.setExpanded(True)
                parent = child if child is not None else self._folder_node(parent, prefix)

            folders = {entry["path"] for entry in entries if entry["folder"]}
            for index in range(parent.childCount() - 1, -1, -1):
                if parent.child(index).data(0, Qt.UserRole) not in folders:
                    parent.takeChild(index)
            existing = {parent.child(i).data(0, Qt.UserRole) for i in range(parent.childCount())}
            for folder in sorted(folders - existing, key=str.casefold):
                self._folder_node(parent, folder)
            parent.sortChildren(0, Qt.AscendingOrder)
            parent.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)
            parent.setExpanded(True)
            self.tree.setCurrentItem(parent)
            self.tree.scrollToItem(parent)

    def _tree_selected(self, item, _column):
        path = item.data(0, Qt.UserRole)
        if path and path != self.current:
            self._navigate(path)

    def _tree_expanded(self, item):
        if item.childIndicatorPolicy() == QTreeWidgetItem.ShowIndicator:
            path = item.data(0, Qt.UserRole)
            if path:
                self._navigate(path)

    def _navigate(self, path):
        self._run("读取目录...", lambda device, progress: self._navigate_operation(device, path, progress))

    def _navigate_address(self):
        if self.worker is not None or self.editing:
            return
        path = self.address.text().strip() or "/"
        if path != "/" and path.endswith("/") and not path.endswith("//"):
            path = path[:-1]
        try:
            path = GP03DeviceFiles.path_arg(path)
        except ValueError as error:
            self.state.setText(str(error))
            self.address.setFocus()
            return
        self._navigate(path)

    def _navigate_operation(self, device, path, _progress=None):
        entries = device.list(path)
        try:
            capacity = device.capacity()
        except GP03DeviceError:
            capacity = ""
        return {"entries": entries, "capacity": capacity, "path": path}

    def _list_activated(self, item, _column):
        self.preview(item.data(0, Qt.UserRole))

    def go_up(self):
        if self.current != "/":
            self._navigate(GP03DeviceFiles.parent(self.current))

    def make_directory(self):
        self._create_entry(self.current, folder=True)

    def make_file(self):
        self._create_entry(self.current, folder=False)

    def _create_entry(self, directory, *, folder):
        action = self.mkdir_action if folder else self.create_action
        english = self.owner.language == "en"
        prompt = ("Folder name" if folder else "File name") if english else ("目录名称" if folder else "文件名称")
        location = "In: " if english else "位置："
        name, accepted = QInputDialog.getText(self, action.text(), "{}\n{}{}".format(prompt, location, directory))
        if not accepted or not name.strip():
            return
        try:
            target = GP03DeviceFiles.child(directory, name)
        except ValueError as error:
            QMessageBox.warning(self, action.text(), str(error))
            return
        def create(device, _progress):
            operation = device.mkdir if folder else device.create
            operation(target)

        self._mutate(action.text(), create, directory)

    def _mutate(self, title, mutation, refresh_path=None):
        path = self.current if refresh_path is None else refresh_path

        def operation(device, progress):
            mutation(device, progress)
            return self._navigate_operation(device, path)
        self._run(title + "...", operation)

    def upload(self):
        local, _ = QFileDialog.getOpenFileName(self, "选择上传文件")
        if not local:
            return
        name = os.path.basename(local)
        existing = next((item for item in self.entries if item["name"] == name), None)
        if existing and existing["folder"]:
            QMessageBox.warning(self, "上传", "目标目录已有同名文件夹。")
            return
        replace = bool(existing)
        english = self.owner.language == "en"
        if replace and not self._confirm_action(
            "Confirm overwrite" if english else "确认覆盖",
            (f"Overwrite {name} after verifying the upload?" if english else f"校验上传内容后覆盖 {name}？"),
        ):
            return
        target = GP03DeviceFiles.child(self.current, name)
        self._mutate("上传 " + name, lambda device, progress: device.upload(local, target, replace, progress))

    def download(self):
        self._download_entry(self._selected())

    def _download_entry(self, entry):
        if not entry or entry["folder"]:
            return
        english = self.owner.language == "en"
        local, _ = QFileDialog.getSaveFileName(
            self, "Save to computer" if english else "保存到电脑", entry["name"],
            options=QFileDialog.DontConfirmOverwrite,
        )
        if not local:
            return
        if os.path.exists(local) and not self._confirm_action(
            "Confirm overwrite" if english else "确认覆盖",
            (f"The local file already exists. Overwrite {local}?" if english else f"本地文件已存在，是否覆盖 {local}？"),
        ):
            return
        self._run("下载 " + entry["name"], lambda device, progress: device.download(entry, local, progress))

    def move_item(self, entry):
        parent = GP03DeviceFiles.parent(entry["path"])
        english = self.owner.language == "en"
        title = "Move" if english else "移动"
        prompt = "Destination folder (absolute path)" if english else "输入目标目录的绝对路径（保留原文件名）"
        directory, accepted = QInputDialog.getText(self, title, prompt, text=parent)
        if not accepted:
            return
        try:
            directory = GP03DeviceFiles.path_arg(directory.strip())
            target = GP03DeviceFiles.child(directory, entry["name"])
            if entry["folder"] and (directory == entry["path"] or directory.startswith(entry["path"] + "/")):
                raise ValueError("A folder cannot be moved into itself." if english else "不能把目录移动到自身或其子目录。")
        except ValueError as error:
            QMessageBox.warning(self, title, str(error))
            return
        self._relocate(title, entry, target)

    def rename_item(self, entry):
        english = self.owner.language == "en"
        title = "Rename" if english else "重命名"
        prompt = "New name" if english else "输入新名称（不改变所在目录）"
        name, accepted = QInputDialog.getText(self, title, prompt, text=entry["name"])
        if not accepted:
            return
        try:
            target = GP03DeviceFiles.child(GP03DeviceFiles.parent(entry["path"]), name)
        except ValueError as error:
            QMessageBox.warning(self, title, str(error))
            return
        self._relocate(title, entry, target)

    def _relocate(self, title, entry, target):
        source = entry["path"]
        if target != source:
            self._mutate(title, lambda device, _progress: device.move(source, target),
                         GP03DeviceFiles.parent(source))

    def delete_item(self, entry):
        english = self.owner.language == "en"
        path = entry["path"]
        if self._confirm_action(
            "Confirm deletion" if english else "确认删除",
            f"Delete {path} from the device?" if english else f"删除设备上的 {path}？",
        ):
            self._mutate("删除", lambda device, _progress: device.delete(entry["path"]),
                         GP03DeviceFiles.parent(entry["path"]))

    def preview(self, entry):
        if not entry or entry["folder"]:
            return
        lz4_preview = entry["name"].lower().endswith(".lz4")
        if lz4_preview and LZ4FrameDecompressor is None:
            message = ("LZ4 support is unavailable. Install the lz4 package or use a build that includes it."
                       if self.owner.language == "en" else "缺少 lz4 依赖，请安装 lz4 或使用包含该依赖的发行版。")
            QMessageBox.warning(self, self.windowTitle(), message)
            return
        connection = getattr(self.owner, "serial_thread", None)

        def read_file(device, progress):
            current = device.file_entry(entry["path"])
            if lz4_preview:
                path, total = current["path"], current["size"]

                def chunks():
                    for offset in range(0, total, LZ4_IO_BYTES):
                        data = device.read_part(path, offset, min(LZ4_IO_BYTES, total - offset))
                        progress(offset + len(data), total)
                        yield data

                cache, size = decode_lz4_preview(chunks(), device._check_cancel)
                return {"entry": current, "cache": cache, "cache_size": size}
            data = device.read_part(current["path"], 0, current["size"], progress)
            return {"entry": current, "preview": data, "connection": connection}

        self._run("预览 " + entry["name"], read_file)

    def _show_preview(self, entry, data, hex_page=None, *, cache=None, cache_size=0):
        self._close_preview_cache()
        self.editing = False
        self.hex_draft = None
        self.hex_block_range = None
        self.preview_entry = entry
        self.preview_data = data
        self.preview_cache = cache
        self.preview_cache_size = cache_size
        self.preview_connection = None
        self.preview_text = None
        self.preview_format = None
        size = self._preview_size_bytes()
        complete = size <= EDIT_MAX_BYTES
        sample = self._preview_slice(0, size if complete else PREVIEW_PAGE_BYTES)
        encoding = "utf-8-sig" if sample.startswith(codecs.BOM_UTF8) else "utf-8"
        try:
            text = codecs.getincrementaldecoder(encoding)().decode(sample, final=complete)
            is_text = all(char.isprintable() or char in "\r\n\t" for char in text)
        except UnicodeDecodeError:
            is_text = False
        if complete and is_text:
            endings = set(re.findall(r"\r\n|\r|\n", text))
            self.preview_text = text.replace("\r\n", "\n").replace("\r", "\n")
            if cache is None and len(endings) <= 1:
                self.preview_format = (encoding, next(iter(endings), "\n"))

        self.preview_name.setText(entry["name"])
        self.preview_name.setToolTip(entry["path"])
        self._update_preview_size(size)
        with QSignalBlocker(self.preview_mode):
            self.preview_mode.setCurrentIndex(1 if hex_page is not None or not is_text else 0)
        self._reset_preview_page(page=hex_page or 1)

    def _reset_preview_page(self, *, page=1):
        hex_mode = self.preview_mode.currentIndex() == 1
        paged = hex_mode or self.preview_text is None
        size = self._preview_size_bytes()
        total = max(1, (size + PREVIEW_PAGE_BYTES - 1) // PREVIEW_PAGE_BYTES) if paged else 1
        with QSignalBlocker(self.preview_page):
            self.preview_page.setRange(1, total)
            self.preview_page.setValue(page)
        self.preview_total_pages.setText("/ {:,}".format(total))
        self.preview_pages.setVisible(total > 1 and self.hex_block_range is None
                                      and (not self.editing or self._hex_editing()))
        self._render_preview()
        self._update_preview_buttons()

    @staticmethod
    def _hex_ascii(data):
        return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in data)

    def _hex_editing(self):
        return self.editing and self.preview_mode.currentIndex() == 1

    def _hex_data(self):
        return self.preview_data if self.hex_draft is None else self.hex_draft

    def _preview_size_bytes(self):
        return self.preview_cache_size if self.preview_cache is not None else len(self._hex_data())

    def _preview_slice(self, start, stop):
        if self.preview_cache is None:
            return self._hex_data()[start:stop]
        self.preview_cache.seek(start)
        return self.preview_cache.read(stop - start)

    def _update_preview_size(self, size):
        if self.preview_cache is None:
            self.preview_size.setText(f"{size:,} B")
            self.preview_size.setToolTip("")
        else:
            english = self.owner.language == "en"
            self.preview_size.setText(f"{size:,} B · " + ("Read-only" if english else "只读"))
            original_size = self.preview_entry["size"]
            self.preview_size.setToolTip(f"LZ4 compressed: {original_size:,} B" if english
                                         else f"LZ4 压缩文件：{original_size:,} B")

    def _close_preview_cache(self):
        if self.preview_cache is not None:
            self.preview_cache.close()
            self.preview_cache = None
        self.preview_cache_size = 0

    def _has_unsaved_edit(self):
        if self._hex_editing():
            return self._hex_data() != self.preview_data or self._hex_block_modified()
        return self.preview_output.document().isModified()

    def _render_hex_page(self, start, stop):
        table = self.preview_hex
        editable = self._hex_editing()
        data = self._preview_slice(start, stop)
        with QSignalBlocker(table):
            table.clearContents()
            table.setRowCount((len(data) + 15) // 16)
            for row, position in enumerate(range(0, len(data), 16)):
                offset = start + position
                chunk = data[position:position + 16]
                values = (f"{offset:08X}", chunk.hex(" ").upper(), self._hex_ascii(chunk))
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if col == 0:
                        item.setForeground(QColor("#42566a"))
                        item.setBackground(QColor("#e9eff6"))
                    elif col == 2:
                        item.setForeground(QColor("#30574c"))
                        item.setBackground(QColor("#e7f0ec"))
                    else:
                        if editable and chunk != self.preview_data[offset:offset + 16]:
                            color = "#cfe5ff"
                        elif editable:
                            color = "#f0f7ff" if row % 2 == 0 else "#eaf3fd"
                        else:
                            color = "#ffffff" if row % 2 == 0 else "#f7f9fc"
                        item.setBackground(QColor(color))
                        item.setForeground(QColor("#182635"))
                    table.setItem(row, col, item)
        self._update_preview_size(self._preview_size_bytes())
        table.scrollToTop()

    def _update_hex_block_label(self):
        if self.hex_block_range is None:
            return
        start, stop = self.hex_block_range
        english = self.owner.language == "en"
        self.hex_block_label.setText(f"Offset {start:08X}  ·  {stop - start:,} B"
                                    if english else f"起始偏移 {start:08X}  ·  原区块 {stop - start:,} B")

    def _open_hex_row(self, row, column):
        if column == 1:
            self._open_hex_block(row=row)

    def _selected_hex_rows(self):
        return sorted({item.row() for item in self.preview_hex.selectedItems()})

    def _open_hex_block(self, *, row=None):
        if not self._hex_editing() or self.worker is not None or self.hex_block_range is not None:
            return
        english = self.owner.language == "en"
        rows = [row] if row is not None else self._selected_hex_rows()
        if not rows:
            rows = [max(0, self.preview_hex.currentRow())]
        if rows[-1] - rows[0] + 1 != len(rows):
            self.state.setText("Select consecutive rows." if english else "请选择连续的行。")
            return
        data = self._hex_data()
        page_start = (self.preview_page.value() - 1) * PREVIEW_PAGE_BYTES
        start = min(len(data), page_start + rows[0] * 16)
        stop = min(len(data), page_start + (rows[-1] + 1) * 16)
        self.hex_block_range = (start, stop)
        self._update_hex_block_label()
        self.hex_block_input.set_bytes(data[start:stop])
        self.hex_block_input.document().setModified(False)
        self.hex_block_error.hide()
        self.preview_pages.hide()
        self.preview_views.setCurrentWidget(self.hex_block_panel)
        self.hex_block_input.setFocus()
        self.hex_block_input.selectAll()
        self._update_preview_buttons()

    def _hex_block_modified(self):
        return self.hex_block_range is not None and self.hex_block_input.document().isModified()

    def _cancel_hex_block(self):
        english = self.owner.language == "en"
        if self._hex_block_modified() and not self._confirm_action(
            "Unsaved changes" if english else "尚未应用",
            "Discard changes to this block?" if english else "是否放弃本次字节块修改？",
        ):
            return
        self._close_hex_block()

    def _close_hex_block(self):
        self.hex_block_range = None
        self.hex_block_input.clear()
        self.hex_block_error.hide()
        self._reset_preview_page(page=self.preview_page.value())
        self.preview_hex.setFocus()

    def _apply_hex_block(self):
        if self.hex_block_range is None:
            return
        start, stop = self.hex_block_range
        digits = "".join(self.hex_block_input.toPlainText().split())
        english = self.owner.language == "en"
        data = self._hex_data()
        if len(digits) % 2 or not re.fullmatch(r"[0-9A-Fa-f]*", digits):
            error = ("Invalid HEX: enter two digits (0-9, A-F) per byte."
                     if english else "字节格式有误：每个字节须为两位十六进制数字（0-9、A-F）。")
        elif len(data) - (stop - start) + len(digits) // 2 > EDIT_MAX_BYTES:
            error = "File exceeds 1 MiB." if english else "修改后文件超过 1 MiB。"
        else:
            self.hex_draft = data[:start] + bytes.fromhex(digits) + data[stop:]
            self._close_hex_block()
            return
        self.hex_block_error.setText(error)
        self.hex_block_error.show()

    def _copy_hex_selection(self):
        table = self.preview_hex
        groups = []
        for selection in table.selectedRanges():
            groups.append("\n".join(
                "\t".join(table.item(row, col).text() for col in range(selection.leftColumn(), selection.rightColumn() + 1))
                for row in range(selection.topRow(), selection.bottomRow() + 1)
            ))
        if groups:
            QApplication.clipboard().setText("\n".join(groups))

    def _text_page(self, start, stop):
        # Both pages use the same UTF-8 character boundary.
        data = self._preview_slice(start, stop + 3)

        def boundary(offset):
            for _ in range(3):
                if offset >= len(data) or data[offset] & 0xC0 != 0x80:
                    break
                offset += 1
            return offset

        encoding = "utf-8-sig" if start == 0 else "utf-8"
        text = data[boundary(0):boundary(stop - start)].decode(encoding, errors="replace")
        return "".join(char if char.isprintable() or char in "\r\n\t" else "\ufffd" for char in text)

    def _render_preview(self):
        if self.preview_entry is None or self.hex_block_range is not None:
            return
        start = (self.preview_page.value() - 1) * PREVIEW_PAGE_BYTES
        stop = start + PREVIEW_PAGE_BYTES
        if self.preview_mode.currentIndex() == 1:
            self.preview_views.setCurrentWidget(self.preview_hex)
            self._render_hex_page(start, stop)
        elif not self.editing:
            self.preview_views.setCurrentWidget(self.preview_output)
            text = self.preview_text if self.preview_text is not None else self._text_page(start, stop)
            self.preview_output.setPlainText(text)
            self.preview_output.set_line_numbers(self.preview_text is not None)
            self.preview_output.document().setModified(False)

    def _update_preview_buttons(self):
        idle = self.worker is None
        has_file = self.preview_entry is not None
        english = self.owner.language == "en"
        hex_mode = self.preview_mode.currentIndex() == 1
        cached = self.preview_cache is not None
        can_edit = not cached and (
            has_file and len(self.preview_data) <= EDIT_MAX_BYTES if hex_mode else self.preview_format is not None
        )
        self.preview_edit.setText(
            ("Cancel edit" if english else "取消编辑") if self.editing else ("Edit" if english else "编辑")
        )
        if self.preview_edit.property("editing") != self.editing:
            self.preview_edit.setProperty("editing", self.editing)
            self.preview_edit.style().unpolish(self.preview_edit)
            self.preview_edit.style().polish(self.preview_edit)
            self.preview_edit.update()
        self.preview_edit.setEnabled(idle and can_edit)
        hint = ""
        if has_file:
            if cached:
                hint = "Decompressed LZ4 preview is read-only." if english else "LZ4 解压预览仅供查看。"
            elif len(self.preview_data) > EDIT_MAX_BYTES:
                hint = "Editing is limited to 1 MiB." if english else "仅可编辑不超过 1 MiB 的文件。"
            elif hex_mode:
                hint = ("Double-click a row or select consecutive rows and click Edit block."
                        if english else "双击字节列编辑单行，或选中连续行后点「多行编辑」。")
            elif not can_edit:
                hint = ("Text editing requires UTF-8 with consistent line endings. Switch to HEX to edit bytes."
                        if english else "文本编辑要求 UTF-8 且换行一致，可切换到 HEX 编辑字节。")
        self.preview_edit.setToolTip(hint)
        self.preview_hex.setToolTip(hint if hex_mode else "")
        hex_editing = self._hex_editing()
        block_open = self.hex_block_range is not None
        dirty = self.editing and self._has_unsaved_edit()
        empty_hex = hex_editing and not self._hex_data()
        show_block = hex_editing and not block_open and (empty_hex or len(self._selected_hex_rows()) > 1)
        if empty_hex:
            self.hex_block_button.setText("Enter bytes" if english else "输入字节")
        else:
            self.hex_block_button.setText("Edit block" if english else "多行编辑")
        self.hex_block_button.setVisible(show_block)
        self.hex_block_button.setEnabled(idle and show_block)
        if not self.editing:
            edit_status = ""
        elif self.saving_preview:
            edit_status = "Saving..." if english else "保存中…"
        elif dirty:
            edit_status = "Unsaved" if english else "未保存"
        else:
            edit_status = "Editing" if english else "编辑中"
        self.preview_edit_status.setText(edit_status)
        self.preview_edit_status.setVisible(bool(edit_status))
        self.preview_save.setEnabled(idle and dirty and not block_open)
        self.preview_save.setToolTip(("Apply the block first." if english else "请先应用字节块。") if block_open else "")
        self.preview_mode.setEnabled(idle and has_file and not self.editing)
        self.preview_page.setEnabled(idle and not block_open and (not self.editing or hex_mode))
        self.preview_output.setReadOnly(not idle or not self.editing or hex_mode)

    def _confirm_action(self, title, message):
        english = self.owner.language == "en"
        dialog = QMessageBox(QMessageBox.Question, title, message, QMessageBox.Yes | QMessageBox.Cancel, self)
        dialog.setTextFormat(Qt.PlainText)
        dialog.button(QMessageBox.Yes).setText("Yes" if english else "确定")
        dialog.button(QMessageBox.Cancel).setText("Cancel" if english else "取消")
        dialog.setDefaultButton(QMessageBox.Cancel)
        dialog.setEscapeButton(QMessageBox.Cancel)
        try:
            return dialog.exec_() == QMessageBox.Yes
        finally:
            dialog.deleteLater()

    def _confirm_discard_edit(self):
        if not self.editing or not self._has_unsaved_edit():
            return True
        english = self.owner.language == "en"
        return self._confirm_action(
            "Unsaved changes" if english else "尚未保存",
            "Discard changes to the file?" if english else "是否放弃对文件的修改？",
        )

    def _toggle_preview_edit(self):
        if self.worker is not None or not self.preview_edit.isEnabled() or not self._confirm_discard_edit():
            return
        hex_mode = self.preview_mode.currentIndex() == 1
        if self.editing:
            self.editing = False
            self.hex_draft = None
            if hex_mode:
                self._close_hex_block()
            else:
                self._render_preview()
        else:
            self.editing = True
            if hex_mode:
                self.hex_draft = self.preview_data
                self._render_preview()
                self.preview_hex.setFocus()
            else:
                self.preview_output.setFocus()
        self._update_buttons()

    def _save_preview(self):
        if not self.editing or self.worker is not None or self.hex_block_range is not None:
            return
        hex_mode = self._hex_editing()
        hex_page = self.preview_page.value() if hex_mode else None
        if not self._has_unsaved_edit():
            return
        english = self.owner.language == "en"
        if getattr(self.owner, "serial_thread", None) is not self.preview_connection:
            QMessageBox.warning(self, self.preview_save.text(),
                                "The serial connection changed. Reopen the file before editing." if english
                                else "串口连接已变化，请重新打开文件后再编辑。")
            return
        if hex_mode:
            data = self._hex_data()
        else:
            encoding, newline = self.preview_format
            text = self.preview_output.document().toRawText().replace("\u2029", "\n")
            if not all(char.isprintable() or char in "\n\t" for char in text):
                QMessageBox.warning(self, self.preview_save.text(),
                                    "The text contains unsupported control characters." if english else "文本包含不支持的控制字符。")
                return
            data = text.replace("\n", newline).encode(encoding)
        if len(data) > EDIT_MAX_BYTES:
            QMessageBox.warning(self, self.preview_save.text(), "File exceeds 1 MiB." if english else "文件超过 1 MiB。")
            return
        if data == self.preview_data:
            self.editing = False
            self.hex_draft = None
            self._render_preview()
            self._update_buttons()
            return
        entry = self.preview_entry
        connection = self.preview_connection
        original_size = len(self.preview_data)
        digest = hashlib.md5(self.preview_data).hexdigest()

        def save_file(device, progress):
            device.save_edited_file(entry["path"], data, original_size, digest, progress)
            return {"entry": dict(entry, size=len(data)), "preview": data, "connection": connection,
                    "saved": True, "hex_page": hex_page}

        self._run(("Saving " if english else "正在保存 ") + entry["name"], save_file, saving=True)

    def _update_saved_size(self, entry):
        for original in self.entries:
            if original["path"] == entry["path"]:
                original["size"] = entry["size"]
                break
        for index in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(index)
            if item.data(0, Qt.UserRole)["path"] == entry["path"]:
                item.setData(0, Qt.UserRole, entry)
                item.setText(1, "{:,} B".format(entry["size"]))
                break

    def _clear_preview(self):
        self._close_preview_cache()
        self.editing = False
        self.hex_draft = None
        self.hex_block_range = None
        self.hex_block_input.clear()
        self.hex_block_error.hide()
        self.preview_entry = None
        self.preview_data = b""
        self.preview_text = None
        self.preview_format = None
        self.preview_connection = None
        self.preview_name.setText(self.preview_action.text())
        self.preview_name.setToolTip("")
        self.preview_size.clear()
        self.preview_size.setToolTip("")
        self.preview_pages.hide()
        self.preview_output.set_line_numbers(False)
        self.preview_output.clear()
        self.preview_hex.setRowCount(0)
        self.preview_views.setCurrentWidget(self.preview_output)
        self._update_preview_buttons()

    def cancel_operation(self):
        if self.cancel_event:
            self.cancel_event.set()

    def reject(self):
        if self.saving_preview:
            return
        if self.worker is not None:
            self.closing = True
            self.cancel_operation()
            return
        if not self._confirm_discard_edit():
            return
        self.closing = False
        self.prepared = False
        self._clear_preview()
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
