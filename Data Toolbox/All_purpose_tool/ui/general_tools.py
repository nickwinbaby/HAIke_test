"""GNSS 之外的通用工具页面。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # 打包环境缺少拖放组件时，普通文件选择仍可使用。
    DND_FILES = None
    TkinterDnD = None

from core.file_checksum import (
    Md5Result,
    calculate_bytes_checksums,
    calculate_checksums,
    collect_files,
    format_file_size,
)
from core.aes_crypto import aes_decrypt, aes_encrypt
from core.data_conversion import (
    BEIJING_TIMEZONE,
    ascii_to_hex,
    beijing_to_unix,
    format_beijing_time,
    hex_to_ascii,
    hex_to_beijing,
    hex_timestamp_to_int,
    unix_to_beijing,
)
from core.file_compare import (
    FileCompareResult,
    FolderCompareResult,
    compare_files,
    compare_folders,
)
from core.registry_integration import (
    register_shell_integration,
    remove_shell_integration,
    shell_integration_exists,
)
from ui.panels import ToolPanel


class DataFormatConversionPanel(ToolPanel):
    """每次只展示一种数据转换功能。"""

    HEX_TO_ASCII = "HEX → ASCII"
    ASCII_TO_HEX = "ASCII → HEX"
    UNIX_TO_BEIJING = "Unix → 北京时间"
    BEIJING_TO_UNIX = "北京时间 → Unix"
    HEX_TO_BEIJING = "HEX → 北京时间"
    PAGE_HEX = "HEX / ASCII"
    PAGE_TIME = "时间转换"

    def __init__(self, master):
        super().__init__(master, "数据转换", "HEX与ASCII双向转换，Unix秒/毫秒时间戳转换为北京时间。", show_heading=False)
        self.feature_var = tk.StringVar(value=self.PAGE_HEX)
        self.direction_var = tk.StringVar(value=self.HEX_TO_ASCII)
        self.hex_ascii_input_var = tk.StringVar()
        self.hex_ascii_output_var = tk.StringVar()
        self.time_direction_var = tk.StringVar(value=self.UNIX_TO_BEIJING)
        self.time_input_var = tk.StringVar()
        self.time_unit_var = tk.StringVar(value="自动识别")
        self.time_result_var = tk.StringVar()
        self.time_result_hint_var = tk.StringVar()
        self.current_beijing_var = tk.StringVar()
        self.current_unix_seconds_var = tk.StringVar()
        self._clock_job = None

        selector = self.section("选择转换功能", 0)
        ttk.Label(selector, text="转换功能").grid(row=0, column=0, sticky="w", padx=(0, 10))
        feature_combo = ttk.Combobox(
            selector,
            textvariable=self.feature_var,
            values=(self.PAGE_HEX, self.PAGE_TIME),
            state="readonly",
            width=22,
        )
        feature_combo.grid(row=0, column=1, sticky="w")
        feature_combo.bind("<<ComboboxSelected>>", self._show_selected_feature)

        page_host = ttk.Frame(self.body, style="Page.TFrame")
        page_host.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        page_host.rowconfigure(0, weight=1)
        page_host.columnconfigure(0, weight=1)
        self.body.rowconfigure(1, weight=1)

        convert_frame = ttk.LabelFrame(
            page_host, text="HEX / ASCII 双向转换", padding=14, style="Section.TLabelframe"
        )
        convert_frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(convert_frame, text="转换方向").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        direction = ttk.Combobox(
            convert_frame,
            textvariable=self.direction_var,
            values=(self.HEX_TO_ASCII, self.ASCII_TO_HEX),
            state="readonly",
            width=18,
        )
        direction.grid(row=0, column=1, sticky="w", pady=5)
        direction.bind("<<ComboboxSelected>>", self._direction_changed)
        ttk.Button(convert_frame, text="交换方向", command=self.swap_hex_ascii).grid(
            row=0, column=2, sticky="w", padx=(10, 0), pady=5
        )
        self.hex_ascii_input_label = ttk.Label(convert_frame, text="HEX输入")
        self.hex_ascii_input_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.hex_ascii_input_text = scrolledtext.ScrolledText(
            convert_frame,
            # 4行为最小高度；所在行带权重，窗口放大时会自动扩展。
            height=4,
            wrap="word",
            font=("Consolas", 10),
            undo=True,
        )
        self.hex_ascii_input_text.grid(row=1, column=1, columnspan=3, sticky="nsew", pady=5)
        self.hex_ascii_output_label = ttk.Label(convert_frame, text="ASCII结果")
        self.hex_ascii_output_label.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        self.hex_ascii_output_text = scrolledtext.ScrolledText(
            convert_frame,
            height=4,
            wrap="word",
            font=("Consolas", 10),
            undo=True,
        )
        self.hex_ascii_output_text.grid(row=2, column=1, columnspan=3, sticky="nsew", pady=5)
        ttk.Button(
            convert_frame, text="开始转换", command=self.convert_hex_ascii, style="Primary.TButton"
        ).grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Button(convert_frame, text="清空", command=self.clear_hex_ascii).grid(
            row=3, column=2, sticky="w", padx=(10, 0), pady=(8, 0)
        )
        convert_frame.columnconfigure(1, weight=1)
        convert_frame.rowconfigure(1, weight=1)
        convert_frame.rowconfigure(2, weight=1)
        self.hex_ascii_input_var.trace_add(
            "write",
            lambda *_args: self._write_text(self.hex_ascii_input_text, self.hex_ascii_input_var.get()),
        )
        self.hex_ascii_output_var.trace_add(
            "write",
            lambda *_args: self._write_text(self.hex_ascii_output_text, self.hex_ascii_output_var.get()),
        )

        time_page = ttk.Frame(page_host, style="Page.TFrame")
        time_page.grid(row=0, column=0, sticky="nsew")
        time_page.columnconfigure(0, weight=1)

        time_frame = ttk.LabelFrame(
            time_page,
            text="Unix / 北京时间双向转换",
            padding=(14, 7),
            style="Section.TLabelframe",
        )
        time_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(time_frame, text="转换方向").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        time_direction = ttk.Combobox(
            time_frame,
            textvariable=self.time_direction_var,
            values=(self.UNIX_TO_BEIJING, self.BEIJING_TO_UNIX, self.HEX_TO_BEIJING),
            state="readonly",
            width=20,
        )
        time_direction.grid(row=0, column=1, sticky="w", pady=5)
        time_direction.bind("<<ComboboxSelected>>", self._time_direction_changed)
        self.time_unit_combo = ttk.Combobox(
            time_frame, textvariable=self.time_unit_var, state="readonly", width=12
        )
        self.time_unit_combo.grid(row=0, column=2, sticky="w", padx=(10, 0), pady=5)
        ttk.Button(time_frame, text="交换方向", command=self.swap_time_direction).grid(
            row=0, column=3, sticky="w", padx=(10, 0), pady=5
        )
        self.time_input_label = ttk.Label(time_frame, text="Unix时间戳")
        self.time_input_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        time_entry = ttk.Entry(time_frame, textvariable=self.time_input_var)
        time_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)
        self.time_result_label = ttk.Label(time_frame, text="北京时间")
        self.time_result_label.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(time_frame, textvariable=self.time_result_var).grid(
            row=2, column=1, columnspan=3, sticky="ew", pady=5
        )
        ttk.Label(time_frame, textvariable=self.time_result_hint_var, style="Hint.TLabel").grid(
            row=3, column=1, columnspan=3, sticky="w", pady=(0, 5)
        )
        ttk.Button(
            time_frame, text="开始转换", command=self.convert_time, style="Primary.TButton"
        ).grid(row=4, column=1, sticky="w", pady=(8, 0))
        ttk.Button(time_frame, text="复制结果", command=lambda: self.copy_value(self.time_result_var)).grid(
            row=4, column=2, sticky="w", padx=(10, 0), pady=(8, 0)
        )
        time_entry.bind("<Return>", lambda _event: self.convert_time())
        time_frame.columnconfigure(1, weight=1)

        clock_frame = ttk.LabelFrame(
            time_page,
            text="当前北京时间与Unix时间戳",
            padding=(14, 7),
            style="Section.TLabelframe",
        )
        clock_frame.grid(row=1, column=0, sticky="ew")
        self._clock_row(clock_frame, 0, "当前北京时间", self.current_beijing_var)
        self._clock_row(clock_frame, 1, "Unix时间戳（秒）", self.current_unix_seconds_var)

        self.feature_pages = {
            self.PAGE_HEX: convert_frame,
            self.PAGE_TIME: time_page,
        }
        self._time_direction_changed()
        self._show_selected_feature()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._update_clock()

    def _clock_row(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=5)
        ttk.Label(
            parent, textvariable=variable, font=("Consolas", 11, "bold"), foreground="#0f4c6e"
        ).grid(row=row, column=1, sticky="w", pady=5)
        ttk.Button(parent, text="复制", command=lambda current=variable: self.copy_value(current)).grid(
            row=row, column=2, sticky="w", padx=(14, 0), pady=5
        )

    def _show_selected_feature(self, _event=None):
        selected = self.feature_pages[self.feature_var.get()]
        for page in self.feature_pages.values():
            if page is selected:
                page.grid()
            else:
                page.grid_remove()
        selected.tkraise()
        self._sync_scroll_region()

    @staticmethod
    def _read_text(widget):
        return widget.get("1.0", "end-1c")

    @staticmethod
    def _write_text(widget, value):
        current = widget.get("1.0", "end-1c")
        if current == value:
            return
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _direction_changed(self, _event=None):
        if self.direction_var.get() == self.HEX_TO_ASCII:
            self.hex_ascii_input_label.configure(text="HEX输入")
            self.hex_ascii_output_label.configure(text="ASCII结果")
        else:
            self.hex_ascii_input_label.configure(text="ASCII输入")
            self.hex_ascii_output_label.configure(text="HEX结果")

    def convert_hex_ascii(self):
        source = self._read_text(self.hex_ascii_input_text)
        if self.hex_ascii_input_var.get() != source:
            self.hex_ascii_input_var.set(source)
        try:
            if self.direction_var.get() == self.HEX_TO_ASCII:
                result = hex_to_ascii(source)
            else:
                result = ascii_to_hex(source)
        except ValueError as exc:
            messagebox.showerror("转换失败", str(exc), parent=self)
            return
        self.hex_ascii_output_var.set(result)

    def swap_hex_ascii(self):
        old_input = self._read_text(self.hex_ascii_input_text)
        old_output = self._read_text(self.hex_ascii_output_text)
        self.direction_var.set(
            self.ASCII_TO_HEX if self.direction_var.get() == self.HEX_TO_ASCII else self.HEX_TO_ASCII
        )
        self.hex_ascii_input_var.set(old_output)
        self.hex_ascii_output_var.set(old_input)
        self._direction_changed()

    def clear_hex_ascii(self):
        self.hex_ascii_input_var.set("")
        self.hex_ascii_output_var.set("")

    def _time_direction_changed(self, _event=None):
        direction = self.time_direction_var.get()
        if direction == self.UNIX_TO_BEIJING:
            self.time_input_label.configure(text="Unix时间戳")
            self.time_result_label.configure(text="北京时间")
            self.time_unit_combo.configure(values=("自动识别", "秒", "毫秒"))
            self.time_unit_combo.configure(state="readonly")
            if self.time_unit_var.get() not in ("自动识别", "秒", "毫秒"):
                self.time_unit_var.set("自动识别")
        elif direction == self.BEIJING_TO_UNIX:
            self.time_input_label.configure(text="北京时间")
            self.time_result_label.configure(text="Unix时间戳")
            self.time_unit_combo.configure(values=("秒", "毫秒"))
            self.time_unit_combo.configure(state="readonly")
            if self.time_unit_var.get() not in ("秒", "毫秒"):
                self.time_unit_var.set("秒")
        else:
            self.time_input_label.configure(text="HEX时间戳")
            self.time_result_label.configure(text="北京时间")
            self.time_unit_var.set("自动识别")
            self.time_unit_combo.configure(values=("自动识别",), state="disabled")
        self.time_result_hint_var.set("")

    def swap_time_direction(self):
        old_input = self.time_input_var.get()
        old_result = self.time_result_var.get()
        direction = self.time_direction_var.get()
        self.time_direction_var.set(
            self.BEIJING_TO_UNIX if direction == self.UNIX_TO_BEIJING else self.UNIX_TO_BEIJING
        )
        self._time_direction_changed()
        self.time_input_var.set(old_result)
        self.time_result_var.set(old_input)

    def convert_time(self):
        try:
            direction = self.time_direction_var.get()
            if direction == self.UNIX_TO_BEIJING:
                converted, detected = unix_to_beijing(
                    self.time_input_var.get(), self.time_unit_var.get()
                )
                result = format_beijing_time(
                    converted, include_milliseconds=(detected == "毫秒")
                )
                hint = f"按{detected}解析"
            elif direction == self.BEIJING_TO_UNIX:
                result = str(beijing_to_unix(self.time_input_var.get(), self.time_unit_var.get()))
                hint = f"输出单位：{self.time_unit_var.get()}"
            else:
                timestamp = hex_timestamp_to_int(self.time_input_var.get())
                converted, detected = unix_to_beijing(timestamp, "自动识别")
                result = format_beijing_time(
                    converted, include_milliseconds=(detected == "毫秒")
                )
                hint = f"HEX转十进制后按{detected}自动解析"
        except ValueError as exc:
            messagebox.showerror("转换失败", str(exc), parent=self)
            return
        self.time_result_var.set(result)
        self.time_result_hint_var.set(hint)

    def copy_value(self, variable):
        value = variable.get()
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)

    def _update_clock(self):
        now_timestamp = datetime.now().timestamp()
        now_beijing = datetime.fromtimestamp(now_timestamp, tz=BEIJING_TIMEZONE)
        self.current_beijing_var.set(format_beijing_time(now_beijing, include_milliseconds=False))
        self.current_unix_seconds_var.set(str(int(now_timestamp)))
        self._clock_job = self.after(500, self._update_clock)

    def _on_destroy(self, event):
        if event.widget is not self or self._clock_job is None:
            return
        try:
            self.after_cancel(self._clock_job)
        except tk.TclError:
            pass
        self._clock_job = None


class DataEncryptionPanel(ToolPanel):
    """本地AES加解密工具。"""

    def __init__(self, master):
        super().__init__(master, "数据加解密", "AES加密与解密。", show_heading=False)
        self.mode_var = tk.StringVar(value="CBC")
        self.padding_var = tk.StringVar(value="PKCS7")
        self.key_bits_var = tk.StringVar(value="256")
        self.key_format_var = tk.StringVar(value="Hex")
        self.key_var = tk.StringVar()
        self.iv_format_var = tk.StringVar(value="Hex")
        self.iv_var = tk.StringVar()
        self.encoding_var = tk.StringVar(value="UTF-8")
        self.cipher_format_var = tk.StringVar(value="Hex")

        options = self.section("AES参数", 0)
        ttk.Label(options, text="运算模式").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        mode_combo = ttk.Combobox(
            options, textvariable=self.mode_var, values=("CBC", "ECB"), state="readonly", width=10
        )
        mode_combo.grid(row=0, column=1, sticky="w", pady=4)
        mode_combo.bind("<<ComboboxSelected>>", self._mode_changed)
        ttk.Label(options, text="填充模式").grid(row=0, column=2, sticky="w", padx=(20, 8), pady=4)
        ttk.Combobox(
            options,
            textvariable=self.padding_var,
            values=("PKCS7", "Zeros", "None"),
            state="readonly",
            width=12,
        ).grid(row=0, column=3, sticky="w", pady=4)
        ttk.Label(options, text="密钥长度").grid(row=0, column=4, sticky="w", padx=(20, 8), pady=4)
        ttk.Combobox(
            options,
            textvariable=self.key_bits_var,
            values=("128", "192", "256"),
            state="readonly",
            width=9,
        ).grid(row=0, column=5, sticky="w", pady=4)

        ttk.Label(options, text="密钥").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            options,
            textvariable=self.key_format_var,
            values=("Text", "Hex"),
            state="readonly",
            width=10,
        ).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Entry(options, textvariable=self.key_var).grid(
            row=1, column=2, columnspan=4, sticky="ew", padx=(8, 0), pady=4
        )

        self.iv_label = ttk.Label(options, text="偏移IV")
        self.iv_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.iv_format_combo = ttk.Combobox(
            options,
            textvariable=self.iv_format_var,
            values=("Text", "Hex"),
            state="readonly",
            width=10,
        )
        self.iv_format_combo.grid(row=2, column=1, sticky="w", pady=4)
        self.iv_entry = ttk.Entry(options, textvariable=self.iv_var)
        self.iv_entry.grid(row=2, column=2, columnspan=4, sticky="ew", padx=(8, 0), pady=4)
        options.columnconfigure(3, weight=1)
        options.columnconfigure(5, weight=1)
        options.grid_configure(pady=(0, 6))

        data_frame = self.section("AES数据", 1)
        settings = ttk.Frame(data_frame, style="Section.TFrame")
        settings.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        ttk.Label(settings, text="字符编码").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(
            settings,
            textvariable=self.encoding_var,
            values=("UTF-8", "Hex"),
            state="readonly",
            width=11,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(settings, text="密文格式").grid(row=0, column=2, sticky="w", padx=(20, 8))
        ttk.Combobox(
            settings,
            textvariable=self.cipher_format_var,
            values=("Base64", "Hex"),
            state="readonly",
            width=11,
        ).grid(row=0, column=3, sticky="w")
        ttk.Label(
            settings,
            text="字符编码用于明文；密文格式用于加密输出和解密输入。",
            style="Hint.TLabel",
        ).grid(row=0, column=4, sticky="w", padx=(20, 0))

        ttk.Label(data_frame, text="输入").grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=5)
        self.input_text = scrolledtext.ScrolledText(
            data_frame, height=4, wrap="word", font=("Consolas", 10), undo=True
        )
        self.input_text.grid(row=1, column=1, columnspan=2, sticky="nsew", pady=5)
        ttk.Label(data_frame, text="结果").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=5)
        self.output_text = scrolledtext.ScrolledText(
            data_frame, height=4, wrap="word", font=("Consolas", 10), undo=True
        )
        self.output_text.grid(row=2, column=1, columnspan=2, sticky="nsew", pady=5)
        actions = ttk.Frame(data_frame, style="Section.TFrame")
        actions.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="加密", command=self.encrypt, style="Primary.TButton").pack(
            side="left"
        )
        ttk.Button(actions, text="解密", command=self.decrypt).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="交换", command=self.swap).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="清空", command=self.clear).pack(side="right")
        ttk.Button(actions, text="复制结果", command=self.copy_result).pack(
            side="right", padx=(0, 8)
        )
        data_frame.columnconfigure(1, weight=1)
        data_frame.columnconfigure(2, weight=1)
        data_frame.rowconfigure(1, weight=1)
        data_frame.rowconfigure(2, weight=1)
        data_frame.grid_configure(sticky="nsew", pady=(0, 0))
        self.body.rowconfigure(1, weight=1)
        self._mode_changed()

    def _mode_changed(self, _event=None):
        state = "disabled" if self.mode_var.get() == "ECB" else "readonly"
        self.iv_format_combo.configure(state=state)
        self.iv_entry.configure(state="disabled" if state == "disabled" else "normal")
        self.iv_label.configure(text="偏移IV（ECB不使用）" if state == "disabled" else "偏移IV")

    def _values(self):
        return {
            "mode": self.mode_var.get(),
            "padding": self.padding_var.get(),
            "key_bits": int(self.key_bits_var.get()),
            "key_format": self.key_format_var.get(),
            "iv": self.iv_var.get(),
            "iv_format": self.iv_format_var.get(),
            "encoding": self.encoding_var.get(),
        }

    def _source(self):
        return self.input_text.get("1.0", "end-1c")

    def _show_result(self, value):
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", value)

    def encrypt(self):
        try:
            result = aes_encrypt(
                self._source(),
                self.key_var.get(),
                output_format=self.cipher_format_var.get(),
                **self._values(),
            )
        except ValueError as exc:
            messagebox.showerror("AES加密失败", str(exc), parent=self)
            return
        self._show_result(result)

    def decrypt(self):
        try:
            result = aes_decrypt(
                self._source(),
                self.key_var.get(),
                input_format=self.cipher_format_var.get(),
                **self._values(),
            )
        except ValueError as exc:
            messagebox.showerror("AES解密失败", str(exc), parent=self)
            return
        self._show_result(result)

    def swap(self):
        source = self._source()
        result = self.output_text.get("1.0", "end-1c")
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", result)
        self._show_result(source)

    def copy_result(self):
        result = self.output_text.get("1.0", "end-1c")
        if result:
            self.clipboard_clear()
            self.clipboard_append(result)

    def clear(self):
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")


class DataConversionPanel(ttk.Frame):
    """数据转换一级菜单，承载转换和加解密两个二级功能。"""

    def __init__(self, master):
        super().__init__(master, style="Page.TFrame")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # 这里是一级“数据转换”下面的二级功能，使用和GNSS内部一致的
        # Tools页签；各功能内部再使用轻量的三级选择控件。
        self.notebook = ttk.Notebook(self, style="Tools.TNotebook", takefocus=False)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.pages = {
            "convert": DataFormatConversionPanel(self.notebook),
            "crypto": DataEncryptionPanel(self.notebook),
        }
        self.notebook.add(self.pages["convert"], text="数据转换")
        self.notebook.add(self.pages["crypto"], text="数据加解密")
        self.show_page("convert")

    def show_page(self, key):
        self.notebook.select(self.pages[key])


class FileComparisonPanel(ToolPanel):
    TYPE_FILE = "文件对比"
    TYPE_FOLDER = "文件夹对比"
    STATUS_TEXT = {
        "same": "文件相同",
        "different": "文件不同",
        "only_left": "仅左侧存在",
        "only_right": "仅右侧存在",
    }

    FILTER_DIFFERENT = "different"
    FILTER_ALL = "all"
    FILTER_SAME = "same"
    AUTO_REFRESH_INTERVAL_MS = 5_000
    AUTO_REFRESH_MAX_MS = 30 * 60 * 1_000

    def _resize_scroll_body(self, event):
        """独立结果窗口铺满可用高度；普通页面仍沿用可滚动布局。"""
        if getattr(self, "compact_view", False):
            self.scroll_canvas.itemconfigure(
                self.body_window,
                width=event.width,
                height=event.height,
            )
            self.scroll_canvas.coords(self.body_window, 0, 0)
            self.scroll_canvas.configure(
                scrollregion=(0, 0, event.width, event.height)
            )
            return
        super()._resize_scroll_body(event)

    def _apply_scroll_region(self):
        """避免基类把独立窗口的内容高度重新压回请求高度。"""
        if getattr(self, "compact_view", False):
            self._scroll_refresh_job = None
            if not self.winfo_exists():
                return
            width = max(1, self.scroll_canvas.winfo_width())
            height = max(1, self.scroll_canvas.winfo_height())
            self.scroll_canvas.itemconfigure(
                self.body_window,
                width=width,
                height=height,
            )
            self.scroll_canvas.configure(scrollregion=(0, 0, width, height))
            return
        super()._apply_scroll_region()

    def __init__(self, master, allow_detach=True, compact_view=False):
        super().__init__(
            master,
            "文件对比",
            "文件模式支持纯文本、DOCX内容和二进制HEX对比；文件夹模式只比较目录和文件属性。",
            show_heading=not compact_view,
        )
        self.allow_detach = allow_detach
        self.compact_view = compact_view
        self._detached_window = None
        self._detached_panel = None
        self.mode_var = tk.StringVar(value=self.TYPE_FILE)
        self.left_var = tk.StringVar()
        self.right_var = tk.StringVar()
        self.hide_same_var = tk.BooleanVar(value=False)
        self.show_line_numbers_var = tk.BooleanVar(value=True)
        self.display_filter_var = tk.StringVar(value=self.FILTER_ALL)
        self.auto_refresh_var = tk.BooleanVar(value=False)
        self.refresh_status_var = tk.StringVar(value="")
        self._refresh_in_progress = False
        self._auto_refresh_job = None
        self._auto_refresh_stop_job = None
        self._auto_refresh_deadline = None
        self._source_panel = None
        # 文件选择对话框的锚点。第一次选中文件后，另一侧始终从同一个父目录开始，
        # 避免 Windows 文件对话框沿用上一次浏览到的深层目录。
        self._dialog_anchor_dir: Path | None = None
        self._stop_event = Event()
        self.current_result: FileCompareResult | FolderCompareResult | None = None

        if not self.compact_view:
            settings = self.section("对比设置", 0)
            ttk.Label(settings, text="对比类型").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
            mode = ttk.Combobox(
                settings,
                textvariable=self.mode_var,
                values=(self.TYPE_FILE, self.TYPE_FOLDER),
                state="readonly",
                width=18,
            )
            mode.grid(row=0, column=1, sticky="w", pady=4)
            mode.bind("<<ComboboxSelected>>", self._mode_changed)
            ttk.Checkbutton(
                settings,
                text="隐藏相同内容",
                variable=self.hide_same_var,
                command=self._hide_same_changed,
                style="Clean.TCheckbutton",
                takefocus=False,
            ).grid(row=0, column=2, sticky="w", padx=(18, 0), pady=4)
            ttk.Checkbutton(
                settings,
                text="显示行号",
                variable=self.show_line_numbers_var,
                command=self._display_option_changed,
                style="Clean.TCheckbutton",
                takefocus=False,
            ).grid(row=0, column=3, sticky="w", padx=(18, 0), pady=4)

            ttk.Label(settings, text="左侧路径").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
            ttk.Entry(settings, textvariable=self.left_var).grid(row=1, column=1, sticky="ew", pady=4, padx=(0, 10))
            ttk.Button(settings, text="选择", command=lambda: self._browse_path(self.left_var)).grid(
                row=1, column=2, sticky="w", pady=4
            )
            ttk.Label(settings, text="右侧路径").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
            ttk.Entry(settings, textvariable=self.right_var).grid(row=2, column=1, sticky="ew", pady=4, padx=(0, 10))
            ttk.Button(settings, text="选择", command=lambda: self._browse_path(self.right_var)).grid(
                row=2, column=2, sticky="w", pady=4
            )
            ttk.Button(settings, text="交换路径", command=self.swap_paths).grid(
                row=2, column=3, sticky="w", padx=(10, 0), pady=4
            )
            settings.columnconfigure(1, weight=1)

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=0 if self.compact_view else 1, column=0, sticky="ew", pady=(0, 12))
        if self.compact_view:
            ttk.Label(actions, text="显示范围").pack(side="left", padx=(0, 10))
            for value, label in (
                (self.FILTER_DIFFERENT, "仅显示差异内容"),
                (self.FILTER_ALL, "显示所有内容"),
                (self.FILTER_SAME, "仅显示相同内容"),
            ):
                ttk.Radiobutton(
                    actions,
                    text=label,
                    value=value,
                    variable=self.display_filter_var,
                    command=self._apply_display_filter,
                    style="Clean.TRadiobutton",
                    takefocus=False,
                ).pack(side="left", padx=(0, 14))
            self.refresh_action_host = ttk.Frame(actions, style="Page.TFrame")
            self.refresh_action_host.pack(side="right")
            self.refresh_button = ttk.Button(
                self.refresh_action_host,
                text="立即刷新",
                command=self.refresh_comparison,
            )
            self.refresh_button.pack(side="left", padx=(0, 8))
            ttk.Checkbutton(
                self.refresh_action_host,
                text="自动刷新（5秒，最长30分钟）",
                variable=self.auto_refresh_var,
                command=self._toggle_auto_refresh,
                style="Clean.TCheckbutton",
                takefocus=False,
            ).pack(side="left", padx=(0, 8))
            ttk.Label(
                self.refresh_action_host,
                textvariable=self.refresh_status_var,
                style="Hint.TLabel",
            ).pack(side="left")
            self.compact_line_numbers = ttk.Checkbutton(
                actions,
                text="显示行号",
                variable=self.show_line_numbers_var,
                command=self._display_option_changed,
                style="Clean.TCheckbutton",
                takefocus=False,
            )
            self.compact_line_numbers.pack(side="right", padx=(0, 16))
            self.folder_action_host = ttk.Frame(actions, style="Page.TFrame")
            ttk.Button(
                self.folder_action_host, text="全部展开", command=self.expand_all_folders
            ).pack(side="left", padx=(0, 8))
            ttk.Button(
                self.folder_action_host, text="全部折叠", command=self.collapse_all_folders
            ).pack(side="left")
        else:
            self.compare_button = ttk.Button(
                actions, text="开始对比", command=self.start_comparison, style="Primary.TButton"
            )
            self.compare_button.pack(side="left")
            self.stop_button = ttk.Button(actions, text="停止", command=self.stop_comparison, state="disabled")
            self.stop_button.pack(side="left", padx=(10, 0))
            ttk.Button(actions, text="清空", command=self.clear).pack(side="left", padx=(10, 0))
            if self.allow_detach:
                ttk.Button(
                    actions, text="独立窗口", command=self.open_detached_window
                ).pack(side="right")
                ttk.Button(
                    actions, text="写入注册表", command=self.register_context_menu
                ).pack(side="right", padx=(0, 10))
                ttk.Button(
                    actions, text="清除工具注册表", command=self.remove_context_menu
                ).pack(side="right", padx=(0, 10))

        self.progress = ttk.Progressbar(
            self.body,
            mode="determinate",
            maximum=100,
            style="Hash.Horizontal.TProgressbar",
        )
        if not self.compact_view:
            self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 12))
            self.progress.grid_remove()

        result_frame = ttk.LabelFrame(
            self.body, text="对比结果", padding=10, style="Section.TLabelframe"
        )
        result_row = 1 if self.compact_view else 3
        result_frame.grid(row=result_row, column=0, sticky="nsew", pady=(0, 12))
        self.body.rowconfigure(result_row, weight=1)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)

        self.file_summary_var = tk.StringVar(value="尚未执行文件对比")
        self.file_summary_label = ttk.Label(
            result_frame, textvariable=self.file_summary_var, style="Hint.TLabel"
        )
        self.file_summary_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.file_result_host = ttk.Frame(result_frame, style="Page.TFrame")
        self.file_result_host.grid(row=1, column=0, sticky="nsew")
        self.file_result_host.columnconfigure(0, weight=1)
        self.file_result_host.columnconfigure(1, weight=1)
        self.file_result_host.rowconfigure(0, weight=1)
        self.left_name_var = tk.StringVar(value="左侧文件")
        self.right_name_var = tk.StringVar(value="右侧文件")
        self._syncing_file_scroll = False

        self.left_text, self.left_scroll = self._build_compare_text(
            self.file_result_host, 0, self.left_name_var, "left"
        )
        self.right_text, self.right_scroll = self._build_compare_text(
            self.file_result_host, 1, self.right_name_var, "right"
        )

        self.folder_result_host = ttk.Frame(result_frame, style="Page.TFrame")
        self.folder_result_host.columnconfigure(0, weight=1)
        self.folder_result_host.columnconfigure(1, weight=1)
        self.folder_result_host.rowconfigure(1, weight=1)
        self.left_folder_var = tk.StringVar(value="左侧文件夹")
        self.right_folder_var = tk.StringVar(value="右侧文件夹")
        ttk.Label(
            self.folder_result_host, textvariable=self.left_folder_var,
            font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=(0, 5))
        ttk.Label(
            self.folder_result_host, textvariable=self.right_folder_var,
            font=("Microsoft YaHei UI", 9, "bold"), anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=(0, 5))
        self._syncing_folder_trees = False
        self._folder_entries_by_path = {}
        self._folder_children_by_parent = {}
        self._folder_expanded_paths = set()
        self._folder_visible_rows = []
        self._folder_virtual_offset = 0
        self._folder_virtual_render_job = None
        self._folder_rendered_iids = {}
        self._folder_selected_path = None
        self._folder_summary_text = ""
        self.left_folder_tree, self.left_folder_scroll = self._build_folder_tree(
            self.folder_result_host, 0, "left"
        )
        self.right_folder_tree, self.right_folder_scroll = self._build_folder_tree(
            self.folder_result_host, 1, "right"
        )

        if not self.compact_view:
            self.add_status(4)
        self._mode_changed()

    def _mode_changed(self, _event=None):
        # 模式切换后重新选择路径，避免把文件模式的目录状态带到文件夹模式。
        self._dialog_anchor_dir = None
        self.current_result = None
        self.progress.configure(value=0)
        if not self.compact_view:
            self.progress.grid_remove()
        self._clear_result_widgets()
        if self.mode_var.get() == self.TYPE_FOLDER:
            self.file_summary_label.grid_remove()
            self.file_result_host.grid_remove()
            # folder_result_host 本身包含表头和树控件，始终放在结果框的内容行，
            # 不与独立窗口的筛选工具栏重叠。
            self.folder_result_host.grid(row=1, column=0, sticky="nsew")
        else:
            self.folder_result_host.grid_remove()
            self.file_summary_label.grid()
            self.file_result_host.grid()
        self._update_compact_controls()

    def _update_compact_controls(self):
        """更新独立窗口的一次性控件，不使用定时器或持续监测。"""
        if not self.compact_view:
            return
        is_folder = self.mode_var.get() == self.TYPE_FOLDER
        if is_folder:
            self.compact_line_numbers.pack_forget()
            self.folder_action_host.pack(side="left", padx=(18, 0))
        else:
            self.folder_action_host.pack_forget()
            self.compact_line_numbers.pack(side="right", padx=(0, 16))

    def _apply_display_filter(self):
        """单击筛选项后只重绘一次当前结果。"""
        if isinstance(self.current_result, FolderCompareResult):
            self._render_folder_result(self.current_result, reset_view=False)
        elif isinstance(self.current_result, FileCompareResult):
            self._render_file_result(self.current_result)

    def expand_all_folders(self):
        """一次性展开当前结果中的所有有子项目录。"""
        if not isinstance(self.current_result, FolderCompareResult):
            return
        self._folder_expanded_paths = {
            path for path, children in self._folder_children_by_parent.items()
            if path and children
        }
        self._folder_virtual_offset = 0
        self._rebuild_folder_visible_rows()

    def collapse_all_folders(self):
        """一次性折叠当前结果中的所有目录。"""
        if not isinstance(self.current_result, FolderCompareResult):
            return
        self._folder_expanded_paths.clear()
        self._folder_virtual_offset = 0
        self._rebuild_folder_visible_rows()

    def register_context_menu(self):
        try:
            register_shell_integration()
        except (OSError, PermissionError) as exc:
            messagebox.showerror("写入失败", str(exc), parent=self)
            return
        self.status_var.set("已写入资源管理器右键菜单；请选择两个文件或文件夹后使用")
        messagebox.showinfo(
            "写入成功",
            "已添加“GNN文件对比”。\n\n"
            "在资源管理器中同时选中两个文件或两个文件夹，右键即可直接打开独立对比窗口。",
            parent=self,
        )

    def remove_context_menu(self):
        if not shell_integration_exists():
            self.status_var.set("未发现本工具的右键菜单")
            return
        try:
            remove_shell_integration()
        except (OSError, PermissionError) as exc:
            messagebox.showerror("清除失败", str(exc), parent=self)
            return
        self.status_var.set("已清除资源管理器右键菜单")
        messagebox.showinfo("清除成功", "已清除本工具写入的资源管理器右键菜单。", parent=self)

    def refresh_comparison(self, automatic=False):
        """重新读取当前左右路径并执行一次完整对比。"""
        if not self.compact_view or self._refresh_in_progress:
            return False
        left = self.left_var.get().strip()
        right = self.right_var.get().strip()
        if not left or not right:
            self.refresh_status_var.set("缺少左右路径")
            if not automatic:
                messagebox.showwarning("无法刷新", "当前没有可重新对比的左右路径", parent=self)
            return False

        is_folder = self.mode_var.get() == self.TYPE_FOLDER
        self._refresh_in_progress = True
        self._stop_event.clear()
        self.refresh_button.configure(state="disabled")
        self.refresh_status_var.set("正在自动刷新..." if automatic else "正在刷新...")

        def worker():
            def dispatch(callback):
                try:
                    self.after(0, callback)
                except (RuntimeError, tk.TclError):
                    # 独立窗口可能在后台对比结束前已被关闭。
                    pass

            try:
                if is_folder:
                    result = compare_folders(left, right, stop_event=self._stop_event)
                else:
                    # 显示范围只影响渲染；刷新始终保留完整对比结果。
                    result = compare_files(left, right, hide_same=False, stop_event=self._stop_event)
            except Exception as exc:
                dispatch(lambda error=exc: self._compact_refresh_failed(error, automatic))
            else:
                dispatch(lambda value=result: self._compact_refresh_finished(value))

        Thread(target=worker, daemon=True).start()
        return True

    def _compact_refresh_finished(self, result):
        self._refresh_in_progress = False
        self.refresh_button.configure(state="normal")
        if result is None:
            self.refresh_status_var.set("刷新已停止")
            return
        self.current_result = result
        if isinstance(result, FolderCompareResult):
            self._render_folder_result(result, reset_view=False)
        else:
            self._render_file_result(result)
        if self._source_panel is not None:
            self._source_panel.current_result = result
        self.refresh_status_var.set(datetime.now().strftime("已刷新 %H:%M:%S"))

    def _compact_refresh_failed(self, error, automatic):
        self._refresh_in_progress = False
        self.refresh_button.configure(state="normal")
        self.refresh_status_var.set(f"刷新失败：{error}")
        if not automatic:
            messagebox.showerror("刷新失败", str(error), parent=self)

    def _toggle_auto_refresh(self):
        if not self.auto_refresh_var.get():
            self._cancel_auto_refresh_jobs()
            self.refresh_status_var.set("自动刷新已关闭")
            return
        if not self.left_var.get().strip() or not self.right_var.get().strip():
            self.auto_refresh_var.set(False)
            self.refresh_status_var.set("缺少左右路径")
            messagebox.showwarning("无法自动刷新", "当前没有可重新对比的左右路径", parent=self)
            return
        self._cancel_auto_refresh_jobs()
        self._auto_refresh_deadline = monotonic() + self.AUTO_REFRESH_MAX_MS / 1000
        self.refresh_status_var.set("自动刷新已开启")
        self._auto_refresh_job = self.after(
            self.AUTO_REFRESH_INTERVAL_MS, self._auto_refresh_tick
        )
        self._auto_refresh_stop_job = self.after(
            self.AUTO_REFRESH_MAX_MS, self._auto_refresh_limit_reached
        )

    def _auto_refresh_tick(self):
        self._auto_refresh_job = None
        if not self.auto_refresh_var.get():
            return
        if self._auto_refresh_deadline is None or monotonic() >= self._auto_refresh_deadline:
            self._auto_refresh_limit_reached()
            return
        self.refresh_comparison(automatic=True)
        remaining_ms = max(1, int((self._auto_refresh_deadline - monotonic()) * 1000))
        self._auto_refresh_job = self.after(
            min(self.AUTO_REFRESH_INTERVAL_MS, remaining_ms), self._auto_refresh_tick
        )

    def _auto_refresh_limit_reached(self):
        self._auto_refresh_stop_job = None
        self.auto_refresh_var.set(False)
        self._cancel_auto_refresh_jobs()
        self.refresh_status_var.set("自动刷新已停止（达到30分钟）")

    def _cancel_auto_refresh_jobs(self):
        for attribute in ("_auto_refresh_job", "_auto_refresh_stop_job"):
            job = getattr(self, attribute, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        self._auto_refresh_deadline = None

    def open_detached_window(self):
        """在更大的独立窗口中打开文件对比，并带入当前参数和结果。"""
        if self._detached_window is not None:
            try:
                if self._detached_window.winfo_exists():
                    self._detached_window.deiconify()
                    self._detached_window.lift()
                    self._detached_window.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        window.title("文件对比 - 独立窗口")
        window.configure(background="#eef3f8")
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        width = max(760, min(1400, screen_width - 100))
        height = max(560, min(900, screen_height - 140))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(760, 520)

        # 独立窗口只保留结果区和一次性显示操作，不重复显示路径选择及执行按钮。
        panel = FileComparisonPanel(window, allow_detach=False, compact_view=True)
        panel._source_panel = self
        panel.pack(fill="both", expand=True)
        panel.mode_var.set(self.mode_var.get())
        panel.left_var.set(self.left_var.get())
        panel.right_var.set(self.right_var.get())
        panel.hide_same_var.set(self.hide_same_var.get())
        panel.show_line_numbers_var.set(self.show_line_numbers_var.get())
        panel.display_filter_var.set(
            self.display_filter_var.get()
            if self.compact_view
            else (self.FILTER_DIFFERENT if self.hide_same_var.get() else self.FILTER_ALL)
        )
        panel._dialog_anchor_dir = self._dialog_anchor_dir
        panel._mode_changed()
        panel.current_result = self.current_result
        if isinstance(self.current_result, FolderCompareResult):
            panel.progress.configure(value=100)
            panel._render_folder_result(self.current_result)
        elif isinstance(self.current_result, FileCompareResult):
            panel.progress.configure(value=100)
            panel._render_file_result(self.current_result)

        self._detached_window = window
        self._detached_panel = panel

        def close_window():
            panel.auto_refresh_var.set(False)
            panel._cancel_auto_refresh_jobs()
            panel._stop_event.set()
            self._detached_window = None
            self._detached_panel = None
            window.destroy()
            if getattr(self, "_external_compare_mode", False):
                # 右键菜单模式下主窗口处于隐藏状态；关闭独立窗口时退出整个进程。
                self.winfo_toplevel().destroy()

        window.protocol("WM_DELETE_WINDOW", close_window)
        # 独立窗口用于正式查看差异，Windows下打开后直接最大化；保留标题栏，
        # 用户仍可还原、最小化和关闭，不使用无边框全屏。
        try:
            window.state("zoomed")
        except tk.TclError:
            try:
                window.attributes("-zoomed", True)
            except tk.TclError:
                pass
        window.focus_force()

    def _build_folder_tree(self, parent, column, side):
        host = ttk.Frame(parent, style="Page.TFrame")
        host.grid(row=1, column=column, sticky="nsew", padx=(0, 5) if column == 0 else (5, 0))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            host, columns=("name", "size", "modified"), show="headings", height=20,
        )
        tree.heading("name", text="名称", anchor="w")
        tree.heading("size", text="大小", anchor="e")
        tree.heading("modified", text="修改时间", anchor="w")
        tree.column("name", width=280, minwidth=140, stretch=True)
        tree.column("size", width=90, minwidth=70, stretch=False, anchor="e")
        tree.column("modified", width=145, minwidth=120, stretch=False)
        y_scroll = ttk.Scrollbar(
            host, orient="vertical", command=lambda *args: self._virtual_folder_scroll(*args)
        )
        x_scroll = ttk.Scrollbar(host, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.tag_configure("same", foreground="#334155")
        tree.tag_configure("different", foreground="#b42318", background="#fff4f2")
        tree.tag_configure("only_left", foreground="#b54708", background="#fff8eb")
        tree.tag_configure("only_right", foreground="#175cd3", background="#eff8ff")
        tree.tag_configure("placeholder", foreground="#cbd5e1")
        tree.bind("<Button-1>", self._virtual_folder_click, add="+")
        # 不使用<<TreeviewSelect>>做左右同步：selection_set会再次产生该事件，
        # 容易形成左右树互相触发的无限循环。鼠标释放时只同步一次。
        tree.bind("<ButtonRelease-1>", self._sync_folder_selection_click, add="+")
        tree.bind("<MouseWheel>", self._virtual_folder_mousewheel, add="+")
        tree.bind("<Configure>", lambda _event: self._schedule_virtual_folder_render(), add="+")
        return tree, y_scroll

    def _virtual_folder_mousewheel(self, event):
        direction = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
        self._set_virtual_folder_offset(self._folder_virtual_offset + direction * 3)
        return "break"

    def _virtual_folder_scroll(self, *args):
        if not args:
            return
        if args[0] == "moveto":
            maximum = max(0, len(self._folder_visible_rows) - self._folder_page_rows())
            self._set_virtual_folder_offset(round(float(args[1]) * maximum))
        elif args[0] == "scroll":
            amount = int(args[1])
            step = self._folder_page_rows() if args[2] == "pages" else 3
            self._set_virtual_folder_offset(self._folder_virtual_offset + amount * step)

    def _folder_page_rows(self):
        height = max(
            self.left_folder_tree.winfo_height(), self.right_folder_tree.winfo_height(), 440
        )
        return max(12, height // 22)

    def _set_virtual_folder_offset(self, value):
        maximum = max(0, len(self._folder_visible_rows) - self._folder_page_rows())
        offset = max(0, min(int(value), maximum))
        if offset == self._folder_virtual_offset and self._folder_virtual_render_job is None:
            return
        self._folder_virtual_offset = offset
        self._schedule_virtual_folder_render()

    def _schedule_virtual_folder_render(self):
        if self._folder_virtual_render_job is not None:
            return
        self._folder_virtual_render_job = self.after_idle(self._render_virtual_folder_window)

    def _virtual_folder_click(self, event):
        tree = event.widget
        item_id = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        if not item_id or column != "#1":
            return
        relative_path = self._folder_rendered_iids.get(item_id)
        if relative_path is None or not self._folder_children_by_parent.get(relative_path):
            return
        depth = relative_path.count("/")
        bbox = tree.bbox(item_id, "name")
        triangle_limit = (bbox[0] if bbox else 0) + depth * 16 + 28
        if event.x > triangle_limit:
            return
        if relative_path in self._folder_expanded_paths:
            self._folder_expanded_paths.remove(relative_path)
        else:
            self._folder_expanded_paths.add(relative_path)
        self._rebuild_folder_visible_rows(relative_path)
        return "break"

    def _sync_folder_selection_click(self, event):
        item_id = event.widget.identify_row(event.y)
        if not item_id:
            return
        selected_path = self._folder_rendered_iids.get(item_id)
        if selected_path is None:
            return
        self._folder_selected_path = selected_path
        # 两边一次性设置同一行；没有TreeviewSelect回调，因此不会反向触发。
        for tree in (self.left_folder_tree, self.right_folder_tree):
            if tree.exists(item_id):
                tree.selection_set(item_id)
                tree.focus(item_id)

    def _rebuild_folder_visible_rows(self, anchor_path=None):
        rows = []

        def append_children(parent_path, depth):
            for entry in self._folder_children_by_parent.get(parent_path, ()):
                rows.append((entry, depth))
                if entry.relative_path in self._folder_expanded_paths:
                    append_children(entry.relative_path, depth + 1)

        append_children("", 0)
        self._folder_visible_rows = rows
        if anchor_path:
            for index, (entry, _depth) in enumerate(rows):
                if entry.relative_path == anchor_path:
                    self._folder_virtual_offset = min(self._folder_virtual_offset, index)
                    break
        self._set_virtual_folder_offset(self._folder_virtual_offset)
        self._schedule_virtual_folder_render()

    def _render_virtual_folder_window(self):
        self._folder_virtual_render_job = None
        page_rows = self._folder_page_rows()
        total = len(self._folder_visible_rows)
        maximum = max(0, total - page_rows)
        self._folder_virtual_offset = min(self._folder_virtual_offset, maximum)
        start = self._folder_virtual_offset
        window_rows = self._folder_visible_rows[start:start + page_rows + 4]
        selected_path = self._folder_selected_path
        for tree in (self.left_folder_tree, self.right_folder_tree):
            for item in tree.get_children(""):
                tree.delete(item)
        self._folder_rendered_iids = {}
        for row_index, (entry, depth) in enumerate(window_rows):
            iid = f"row:{start + row_index}"
            self._folder_rendered_iids[iid] = entry.relative_path
            name = entry.relative_path.rsplit("/", 1)[-1]
            has_children = bool(self._folder_children_by_parent.get(entry.relative_path))
            arrow = "▼" if entry.relative_path in self._folder_expanded_paths else "▶" if has_children else " "
            indent = "    " * depth
            left_present = entry.status != "only_right"
            right_present = entry.status != "only_left"
            left_folder = left_present and entry.left_size is None
            right_folder = right_present and entry.right_size is None
            left_name = f"{indent}{arrow} {'📁' if left_folder else '📄'} {name}" if left_present else ""
            right_name = f"{indent}{arrow} {'📁' if right_folder else '📄'} {name}" if right_present else ""
            left_values = (
                left_name,
                "" if entry.left_size is None else format_file_size(entry.left_size),
                "" if entry.left_mtime is None else datetime.fromtimestamp(entry.left_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )
            right_values = (
                right_name,
                "" if entry.right_size is None else format_file_size(entry.right_size),
                "" if entry.right_mtime is None else datetime.fromtimestamp(entry.right_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )
            self.left_folder_tree.insert("", tk.END, iid=iid, values=left_values if left_present else ("", "", ""), tags=(entry.status if left_present else "placeholder",))
            self.right_folder_tree.insert("", tk.END, iid=iid, values=right_values if right_present else ("", "", ""), tags=(entry.status if right_present else "placeholder",))
            if entry.relative_path == selected_path:
                self.left_folder_tree.selection_set(iid)
                self.right_folder_tree.selection_set(iid)
        if total:
            first = start / total
            last = min(1.0, (start + page_rows) / total)
        else:
            first, last = 0.0, 1.0
        self.left_folder_scroll.set(first, last)
        self.right_folder_scroll.set(first, last)

    def _build_compare_text(self, parent, column, name_var, side):
        host = ttk.Frame(parent, style="Page.TFrame")
        host.grid(row=0, column=column, sticky="nsew", padx=(0, 4) if column == 0 else (4, 0))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(1, weight=1)
        ttk.Label(
            host, textvariable=name_var, anchor="center",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        text = tk.Text(host, height=20, wrap="none", font=("Consolas", 9), borderwidth=1)
        y_scroll = ttk.Scrollbar(host, orient="vertical")
        x_scroll = ttk.Scrollbar(host, orient="horizontal", command=text.xview)
        text.configure(
            xscrollcommand=x_scroll.set,
            yscrollcommand=lambda first, last, current=side: self._text_scrolled(
                current, first, last
            ),
        )
        y_scroll.configure(command=self._scroll_compare_texts)
        text.grid(row=1, column=0, sticky="nsew")
        y_scroll.grid(row=1, column=1, sticky="ns")
        x_scroll.grid(row=2, column=0, sticky="ew")
        text.tag_configure("same", foreground="#334155")
        if side == "left":
            text.tag_configure("different", foreground="#b42318", background="#fff1f0")
        else:
            text.tag_configure("different", foreground="#067647", background="#ecfdf3")
        text.tag_configure("gap", foreground="#94a3b8", background="#f1f5f9")
        text.configure(state="disabled")
        return text, y_scroll

    def _scroll_compare_texts(self, *args):
        self.left_text.yview(*args)
        self.right_text.yview(*args)

    def _text_scrolled(self, side, first, last):
        scrollbar = self.left_scroll if side == "left" else self.right_scroll
        other = self.right_text if side == "left" else self.left_text
        scrollbar.set(first, last)
        if self._syncing_file_scroll:
            return
        self._syncing_file_scroll = True
        try:
            if abs(other.yview()[0] - float(first)) > 0.000001:
                other.yview_moveto(first)
        finally:
            self._syncing_file_scroll = False

    def _browse_path(self, variable):
        initial_directory = self._browse_initial_directory(variable)
        if self.mode_var.get() == self.TYPE_FOLDER:
            path = filedialog.askdirectory(
                title="选择要对比的文件夹",
                initialdir=initial_directory,
                parent=self,
            )
        else:
            path = filedialog.askopenfilename(
                title="选择要对比的文件",
                initialdir=initial_directory,
                parent=self,
            )
        if path:
            # 对话框返回后只做字符串/Path对象回填，不再调用resolve、stat或扫描目录；
            # 这些磁盘访问会挡住Tk完成对话框关闭后的第一帧刷新。
            variable.set(path)
            self._dialog_anchor_dir = Path(path).parent

    def _browse_initial_directory(self, variable):
        """让左右路径选择始终从同级父目录开始，而不是进入上次选择的目录。"""
        current_value = variable.get().strip()
        if current_value:
            current_path = Path(current_value)
            return str(current_path.parent)

        other_variable = self.right_var if variable is self.left_var else self.left_var
        other_value = other_variable.get().strip()
        if other_value:
            other_path = Path(other_value)
            # 文件夹和文件都从另一侧已选路径的父目录开始。
            return str(other_path.parent)
        if self._dialog_anchor_dir is not None:
            return str(self._dialog_anchor_dir)
        return None

    def swap_paths(self):
        left, right = self.left_var.get(), self.right_var.get()
        self.left_var.set(right)
        self.right_var.set(left)

    def clear(self):
        if self.compare_button.instate(["disabled"]):
            return
        self.left_var.set("")
        self.right_var.set("")
        self.current_result = None
        self.progress.configure(value=0)
        self.progress.grid_remove()
        self.status_var.set("")
        self._clear_result_widgets()

    def _clear_result_widgets(self):
        if self._folder_virtual_render_job is not None:
            try:
                self.after_cancel(self._folder_virtual_render_job)
            except tk.TclError:
                pass
            self._folder_virtual_render_job = None
        self._folder_visible_rows = []
        self._folder_virtual_offset = 0
        self._folder_expanded_paths = set()
        self._folder_selected_path = None
        self._folder_entries_by_path = {}
        self._folder_children_by_parent = {}
        self._folder_rendered_iids = {}
        for text in (self.left_text, self.right_text):
            text.configure(state="normal")
            text.delete("1.0", tk.END)
            text.configure(state="disabled")
        self.file_summary_var.set("尚未执行文件对比")
        self.left_name_var.set("左侧文件")
        self.right_name_var.set("右侧文件")
        for tree in (self.left_folder_tree, self.right_folder_tree):
            for item in tree.get_children(""):
                tree.delete(item)

    def start_comparison(self):
        left = self.left_var.get().strip()
        right = self.right_var.get().strip()
        if not left or not right:
            messagebox.showwarning("缺少路径", "请先选择左右两个对比路径", parent=self)
            return
        is_folder = self.mode_var.get() == self.TYPE_FOLDER
        if is_folder and (not Path(left).is_dir() or not Path(right).is_dir()):
            messagebox.showerror("路径无效", "文件夹对比需要选择两个有效文件夹", parent=self)
            return
        if not is_folder and (not Path(left).is_file() or not Path(right).is_file()):
            messagebox.showerror("路径无效", "文件对比需要选择两个有效文件", parent=self)
            return
        hide_same = self.hide_same_var.get()
        self._stop_event.clear()
        self.current_result = None
        self._clear_result_widgets()
        self.progress.configure(value=0)
        if not self.compact_view:
            self.progress.grid()
        self.compare_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("正在比较...")

        def update_progress(done, total):
            value = 100 if total == 0 else done * 100 / total
            self.after(0, lambda: self.progress.configure(value=value))

        def update_status(text):
            self.after(0, lambda value=text: self.status_var.set(value))

        def worker():
            try:
                if is_folder:
                    result = compare_folders(
                        left, right, update_progress, update_status, self._stop_event
                    )
                else:
                    result = compare_files(left, right, hide_same, self._stop_event)
            except Exception as exc:
                self.after(0, lambda error=exc: self._comparison_failed(error))
            else:
                self.after(0, lambda: self._comparison_finished(result))

        Thread(target=worker, daemon=True).start()

    def stop_comparison(self):
        self._stop_event.set()
        self.status_var.set("正在停止...")

    def _comparison_failed(self, exc):
        self.compare_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.progress.grid_remove()
        self.status_var.set("对比失败")
        messagebox.showerror("对比失败", str(exc), parent=self)

    def _comparison_finished(self, result):
        self.compare_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if result is None:
            self.progress.grid_remove()
            self.status_var.set("对比已停止")
            return
        self.progress.configure(value=100)
        self.current_result = result
        if isinstance(result, FolderCompareResult):
            self._render_folder_result(result)
        else:
            self._render_file_result(result)
        self._refresh_detached_result()
        self.after(350, self.progress.grid_remove)

    def _refresh_detached_result(self):
        """若独立窗口已打开，将本次结果一次性同步过去。"""
        panel = self._detached_panel
        if panel is None:
            return
        try:
            if not panel.winfo_exists():
                return
        except tk.TclError:
            return
        panel.mode_var.set(self.mode_var.get())
        panel.left_var.set(self.left_var.get())
        panel.right_var.set(self.right_var.get())
        panel._mode_changed()
        panel.current_result = self.current_result
        if isinstance(self.current_result, FolderCompareResult):
            panel._render_folder_result(self.current_result)
        elif isinstance(self.current_result, FileCompareResult):
            panel._render_file_result(self.current_result)

    def _render_file_result(self, result: FileCompareResult):
        state = "完全相同" if result.identical else "存在差异"
        self.left_name_var.set(result.left_path.name)
        self.right_name_var.set(result.right_path.name)
        if result.text_comparison:
            self.file_summary_var.set(
                f"对比结果：{state}    相同行：{result.same_lines}    "
                f"左侧差异行：{result.deleted_lines}    右侧差异行：{result.added_lines}"
            )
        elif result.hex_comparison:
            self.file_summary_var.set(
                f"二进制HEX对比：{state}    相同块：{result.same_lines}    "
                f"左侧差异块：{result.deleted_lines}    右侧差异块：{result.added_lines}    "
                f"（每块16字节）"
            )
        else:
            self.file_summary_var.set(
                f"对比结果：{state}；二进制文件不展开内容 "
                f"（左侧 {format_file_size(result.left_size)}，右侧 {format_file_size(result.right_size)}）"
            )
        if self.compact_view:
            self.compact_line_numbers.configure(
                text="显示偏移" if result.hex_comparison else "显示行号"
            )
        for text in (self.left_text, self.right_text):
            text.configure(state="normal")
            text.delete("1.0", tk.END)
        if not result.text_comparison and not result.hex_comparison:
            # 二进制内容不解码、不渲染；只在上方摘要显示一致性和大小。
            pass
        else:
            show_numbers = self.show_line_numbers_var.get()
            left_chunks = []
            right_chunks = []

            def append_chunk(chunks, tag, value):
                if chunks and chunks[-1][0] == tag:
                    chunks[-1][1].append(value)
                else:
                    chunks.append((tag, [value]))

            for row in result.rows:
                filter_value = self.display_filter_var.get()
                if filter_value == self.FILTER_DIFFERENT and row.status == "same":
                    continue
                if filter_value == self.FILTER_SAME and row.status != "same":
                    continue
                if result.hex_comparison:
                    left_prefix = f"{row.left_number:08X}  " if show_numbers and row.left_number is not None else "          " if show_numbers else ""
                    right_prefix = f"{row.right_number:08X}  " if show_numbers and row.right_number is not None else "          " if show_numbers else ""
                else:
                    left_prefix = f"{row.left_number:6d}  " if show_numbers and row.left_number is not None else "        " if show_numbers else ""
                    right_prefix = f"{row.right_number:6d}  " if show_numbers and row.right_number is not None else "        " if show_numbers else ""
                left_content = row.left_text.rstrip("\r\n")
                right_content = row.right_text.rstrip("\r\n")
                append_chunk(
                    left_chunks,
                    row.status if row.left_number is not None else "gap",
                    left_prefix + left_content + "\n",
                )
                append_chunk(
                    right_chunks,
                    row.status if row.right_number is not None else "gap",
                    right_prefix + right_content + "\n",
                )
            # 按连续样式批量插入，避免大文件逐行调用Tk导致界面长时间无响应。
            for tag, values in left_chunks:
                self.left_text.insert(tk.END, "".join(values), tag)
            for tag, values in right_chunks:
                self.right_text.insert(tk.END, "".join(values), tag)
        for text in (self.left_text, self.right_text):
            text.configure(state="disabled")
        self.status_var.set(f"文件对比完成：{state}")

    def _render_folder_result(self, result: FolderCompareResult, reset_view=True):
        if self._folder_virtual_render_job is not None:
            try:
                self.after_cancel(self._folder_virtual_render_job)
            except tk.TclError:
                pass
            self._folder_virtual_render_job = None
        for tree in (self.left_folder_tree, self.right_folder_tree):
            for item in tree.get_children(""):
                tree.delete(item)
        if self.compact_view:
            self.left_folder_var.set(result.left_path.name)
            self.right_folder_var.set(result.right_path.name)
        else:
            self.left_folder_var.set(str(result.left_path))
            self.right_folder_var.set(str(result.right_path))
        filter_value = self.display_filter_var.get()
        if filter_value == self.FILTER_ALL:
            visible_entries = list(result.entries)
        elif filter_value == self.FILTER_SAME:
            visible_entries = [entry for entry in result.entries if entry.status == "same"]
            # 仅显示相同时仍保留必要的父目录作为导航容器；这些容器不代表
            # 目录内所有项目都相同，只是为了让子项有可展开的路径。
            by_path = {entry.relative_path: entry for entry in result.entries}
            paths = {entry.relative_path for entry in visible_entries}
            for entry in tuple(visible_entries):
                parent = entry.relative_path.rsplit("/", 1)[0] if "/" in entry.relative_path else ""
                while parent:
                    if parent not in paths and parent in by_path:
                        parent_entry = by_path[parent]
                        if parent_entry.item_type == "文件夹":
                            visible_entries.append(parent_entry)
                            paths.add(parent)
                    parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        else:
            visible_entries = [entry for entry in result.entries if entry.status != "same"]
        visible_entries.sort(
            key=lambda entry: (entry.relative_path.count("/"), entry.relative_path.casefold())
        )
        self._folder_entries_by_path = {
            entry.relative_path: entry for entry in visible_entries
        }
        children_by_parent = {}
        for entry in visible_entries:
            relative_path = entry.relative_path
            parent_path = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
            children_by_parent.setdefault(parent_path, []).append(entry)
        for entries in children_by_parent.values():
            entries.sort(
                key=lambda entry: (
                    entry.item_type not in ("文件夹", "类型冲突"),
                    entry.relative_path.rsplit("/", 1)[-1].casefold(),
                )
            )
        self._folder_children_by_parent = children_by_parent
        if reset_view:
            self._folder_expanded_paths = set()
            self._folder_virtual_offset = 0
            self._folder_selected_path = None
        self._folder_visible_rows = []
        self._folder_rendered_iids = {}
        total = len(result.entries)
        self._folder_summary_text = (
            f"文件夹对比完成：总项目 {total}，相同 {result.count('same')}，"
            f"有差异 {result.count('different')}，仅左侧 {result.count('only_left')}，"
            f"仅右侧 {result.count('only_right')}；目录使用虚拟列表显示"
        )
        self.status_var.set(self._folder_summary_text)
        self._rebuild_folder_visible_rows()

    def _hide_same_changed(self):
        self.display_filter_var.set(self.FILTER_DIFFERENT if self.hide_same_var.get() else self.FILTER_ALL)
        if isinstance(self.current_result, FolderCompareResult):
            self._render_folder_result(self.current_result)
        elif isinstance(self.current_result, FileCompareResult):
            self._render_file_result(self.current_result)

    def _display_option_changed(self):
        if isinstance(self.current_result, FileCompareResult):
            self._render_file_result(self.current_result)

class Md5Panel(ToolPanel):
    ALGORITHMS = (
        ("md5", "MD5"),
        ("sha1", "SHA-1"),
        ("sha256", "SHA-256"),
        ("crc32", "CRC-32"),
        ("crc32_rl", "CRC-32-RL"),
    )

    def __init__(self, master):
        super().__init__(master, "哈希算法", "支持批量计算 MD5、SHA-1、SHA-256、CRC-32 和 CRC-32-RL。")
        self.files: list[Path] = []
        self.results: list[Md5Result] = []
        self.errors: list[str] = []
        self._stop_event = Event()
        self.input_mode_var = tk.StringVar(value="文件/文件夹")
        self.text_input_encoding_var = tk.StringVar(value="UTF-8")
        self.text_results: dict[str, str] = {}
        self.algorithm_vars = {
            key: tk.BooleanVar(value=key == "md5") for key, _label in self.ALGORITHMS
        }

        file_frame = self.section("输入数据", 0)
        ttk.Label(file_frame, text="输入类型").grid(row=0, column=0, sticky="w", padx=(0, 14), pady=(0, 8))
        input_mode = ttk.Combobox(
            file_frame,
            textvariable=self.input_mode_var,
            values=("文件/文件夹", "文本输入"),
            state="readonly",
            width=15,
        )
        input_mode.grid(row=0, column=1, sticky="w", pady=(0, 8))
        input_mode.bind("<<ComboboxSelected>>", self._input_mode_changed)
        algorithm_row = ttk.Frame(file_frame, style="Page.TFrame")
        algorithm_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Label(algorithm_row, text="哈希算法").pack(side="left", padx=(0, 14))
        for key, label in self.ALGORITHMS:
            ttk.Checkbutton(
                algorithm_row,
                text=label,
                variable=self.algorithm_vars[key],
                style="Clean.TCheckbutton",
                takefocus=False,
            ).pack(side="left", padx=(0, 16))
        self.file_buttons = ttk.Frame(file_frame, style="Page.TFrame")
        self.file_buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Button(self.file_buttons, text="添加文件", command=self.add_files).pack(side="left")
        ttk.Button(self.file_buttons, text="添加文件夹", command=self.add_folder).pack(side="left", padx=(8, 0))
        ttk.Button(self.file_buttons, text="移除选中", command=self.remove_selected).pack(side="left", padx=(8, 0))
        self.list_host = ttk.Frame(file_frame, style="Page.TFrame")
        self.list_host.grid(row=3, column=0, columnspan=3, sticky="nsew")
        self.list_host.columnconfigure(0, weight=1)
        self.list_host.rowconfigure(0, weight=1)
        self.file_list = tk.Listbox(
            self.list_host, height=4, selectmode=tk.EXTENDED, font=("Microsoft YaHei UI", 9)
        )
        list_scroll = ttk.Scrollbar(self.list_host, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=list_scroll.set)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.drop_hint_var = tk.StringVar(value="可将文件或文件夹拖入此区域，松开后自动计算")
        self.drop_hint_label = ttk.Label(
            file_frame,
            textvariable=self.drop_hint_var,
            style="Hint.TLabel",
        )
        self.drop_hint_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(7, 0))
        self.text_input_label = ttk.Label(file_frame, text="文本内容")
        self.text_input_label.grid(row=2, column=0, sticky="nw", padx=(0, 14), pady=5)
        self.text_input = scrolledtext.ScrolledText(
            file_frame, height=4, wrap="word", font=("Consolas", 10), undo=True
        )
        self.text_input.grid(row=2, column=1, columnspan=2, sticky="nsew", pady=5)
        self.text_encoding_label = ttk.Label(file_frame, text="文本编码")
        self.text_encoding_label.grid(row=3, column=0, sticky="w", padx=(0, 14), pady=(4, 0))
        self.text_encoding_combo = ttk.Combobox(
            file_frame,
            textvariable=self.text_input_encoding_var,
            values=("UTF-8", "GBK", "GB18030", "UTF-16LE", "UTF-16BE"),
            state="readonly",
            width=12,
        )
        self.text_encoding_combo.grid(row=3, column=1, sticky="w", pady=(4, 0))
        self.text_encoding_combo.bind("<<ComboboxSelected>>", self._text_encoding_changed)
        file_frame.rowconfigure(3, weight=1)
        self._enable_file_drop()
        self._text_encoding_changed()
        self._input_mode_changed()

        actions = ttk.Frame(self.body, style="Page.TFrame")
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.calculate_button = ttk.Button(
            actions, text="开始计算", command=self.start_calculation, style="Primary.TButton"
        )
        self.calculate_button.pack(side="left")
        self.clear_button = ttk.Button(actions, text="清空", command=self.clear_current)
        self.clear_button.pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="复制结果", command=self.copy_results).pack(side="right")
        ttk.Button(actions, text="保存结果", command=self.save_results).pack(side="right", padx=(0, 10))

        self.progress = ttk.Progressbar(
            self.body, mode="determinate", maximum=100, style="Hash.Horizontal.TProgressbar"
        )
        self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.progress.grid_remove()

        result_frame = ttk.LabelFrame(
            self.body, text="哈希计算结果", padding=10, style="Section.TLabelframe"
        )
        result_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 12))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        self.result_text = scrolledtext.ScrolledText(
            result_frame, height=5, wrap="none", font=("Consolas", 9), state="disabled"
        )
        self.result_text.grid(row=0, column=0, sticky="nsew")
        self.result_text.tag_configure("filename", foreground="#0f4c6e", font=("Consolas", 9, "bold"))
        self.result_text.tag_configure("md5", foreground="#b42318")
        self.result_text.tag_configure("sha1", foreground="#087f5b")
        self.result_text.tag_configure("sha256", foreground="#6941c6")
        self.result_text.tag_configure("crc32", foreground="#b54708")
        self.result_text.tag_configure("crc32_rl", foreground="#b54708")
        self.result_text.tag_configure("error", foreground="#b42318")
        self.body.rowconfigure(3, weight=1)
        self.add_status(4)

    def _add_paths(self, paths):
        known = {str(path).casefold() for path in self.files}
        for path in collect_files(paths):
            key = str(path).casefold()
            if key not in known:
                known.add(key)
                self.files.append(path)
        self._render_file_list()

    def _enable_file_drop(self):
        if TkinterDnD is None or DND_FILES is None:
            self.drop_hint_var.set("当前环境未加载拖放组件，可使用“添加文件/添加文件夹”")
            return
        try:
            TkinterDnD._require(self.winfo_toplevel())
            self.file_list.drop_target_register(DND_FILES)
            self.file_list.dnd_bind("<<Drop>>", self._on_files_dropped)
        except (RuntimeError, tk.TclError):
            self.drop_hint_var.set("当前环境未加载拖放组件，可使用“添加文件/添加文件夹”")

    def _on_files_dropped(self, event):
        if self.calculate_button.instate(["disabled"]):
            self.status_var.set("正在计算，请完成或停止当前任务后再拖入文件")
            return "break"
        try:
            paths = self.tk.splitlist(event.data)
        except (tk.TclError, AttributeError):
            paths = ()
        before = len(self.files)
        self._add_paths(paths)
        added = len(self.files) - before
        if added:
            self.status_var.set(f"已拖入 {added} 个文件，准备自动计算")
            self.after_idle(self.start_calculation)
        else:
            self.status_var.set("拖入内容中没有可添加的新文件")
        return "break"

    def add_files(self):
        paths = filedialog.askopenfilenames(title="选择要计算哈希值的文件", parent=self)
        if paths:
            self._add_paths(paths)
            self.status_var.set(f"当前已添加 {len(self.files)} 个文件")

    def add_folder(self):
        path = filedialog.askdirectory(title="选择要计算哈希值的文件夹", parent=self)
        if path:
            self._add_paths((path,))
            self.status_var.set(f"当前已添加 {len(self.files)} 个文件")

    def _render_file_list(self):
        self.file_list.delete(0, tk.END)
        for path in self.files:
            self.file_list.insert(tk.END, f"{path.name}  ({format_file_size(path.stat().st_size)})")

    def _input_mode_changed(self, _event=None):
        text_mode = self.input_mode_var.get() == "文本输入"
        if text_mode:
            self.file_list.master.master.rowconfigure(2, weight=1)
            self.file_list.master.master.rowconfigure(3, weight=0)
            self.file_buttons.grid_remove()
            self.list_host.grid_remove()
            self.drop_hint_label.grid_remove()
            self.text_input.grid()
            self.text_input_label.grid()
            self.text_encoding_combo.grid()
            self.text_encoding_label.grid()
            self.progress.grid_remove()
        else:
            self.file_list.master.master.rowconfigure(2, weight=0)
            self.file_list.master.master.rowconfigure(3, weight=1)
            self.file_buttons.grid()
            self.list_host.grid()
            self.drop_hint_label.grid()
            self.text_input.grid_remove()
            self.text_input_label.grid_remove()
            self.text_encoding_combo.grid_remove()
            self.text_encoding_label.grid_remove()
            self.drop_hint_var.set("可将文件或文件夹拖入此区域，松开后自动计算")
        self._sync_scroll_region()

    def _text_encoding_changed(self, _event=None):
        self.text_input_label.configure(text=f"文本内容（{self.text_input_encoding_var.get()}）")

    def remove_selected(self):
        if self.calculate_button.instate(["disabled"]):
            return
        selected = set(self.file_list.curselection())
        self.files = [path for index, path in enumerate(self.files) if index not in selected]
        self._render_file_list()

    def clear_files(self):
        if self.calculate_button.instate(["disabled"]):
            return
        self.files.clear()
        self.results.clear()
        self.errors.clear()
        self.text_results = {}
        self.file_list.delete(0, tk.END)
        self._set_result_text("")
        self.progress.configure(value=0)
        self.progress.grid_remove()
        self.status_var.set("")

    def clear_current(self):
        """清空当前输入模式的数据和计算结果。"""
        if self.calculate_button.instate(["disabled"]):
            return
        if self.input_mode_var.get() == "文本输入":
            self.text_input.delete("1.0", tk.END)
            self.text_results = {}
            self.results = []
            self.errors = []
            self._set_result_text("")
            self.progress.configure(value=0)
            self.progress.grid_remove()
            self.status_var.set("")
        else:
            self.clear_files()

    def start_calculation(self):
        if self.input_mode_var.get() == "文本输入":
            self._start_text_calculation()
            return
        if not self.files:
            messagebox.showwarning("缺少文件", "请先添加要计算哈希值的文件", parent=self)
            return
        algorithms = tuple(
            key for key, _label in self.ALGORITHMS if self.algorithm_vars[key].get()
        )
        if not algorithms:
            messagebox.showwarning("缺少算法", "请至少选择一种校验算法", parent=self)
            return
        files = tuple(self.files)
        self._stop_event.clear()
        self.results = []
        self.errors = []
        self.text_results = {}
        self.progress.configure(value=0)
        self.progress.grid()
        self.calculate_button.configure(state="disabled")
        self.clear_button.configure(state="disabled")
        self._set_result_text("")

        def worker():
            total = len(files)
            results: list[Md5Result] = []
            errors: list[str] = []
            for index, path in enumerate(files):
                if self._stop_event.is_set():
                    break
                self.after(0, lambda name=path.name, current=index + 1: self.status_var.set(
                    f"正在计算：{name}（{current}/{total}）"
                ))

                def file_progress(done, size, item=index):
                    fraction = 1 if size == 0 else done / size
                    value = (item + fraction) * 100 / total
                    self.after(0, lambda percent=value: self.progress.configure(value=percent))

                try:
                    result = calculate_checksums(
                        path, algorithms, file_progress, self._stop_event
                    )
                    if result is not None:
                        results.append(result)
                except Exception as exc:
                    errors.append(f"{path}: {exc}")
            self.after(0, lambda: self._calculation_finished(results, errors))

        Thread(target=worker, daemon=True).start()

    def _start_text_calculation(self):
        algorithms = tuple(key for key, _label in self.ALGORITHMS if self.algorithm_vars[key].get())
        if not algorithms:
            messagebox.showwarning("缺少算法", "请至少选择一种校验算法", parent=self)
            return
        value = self.text_input.get("1.0", "end-1c")
        if value == "":
            messagebox.showwarning("缺少文本", "请先粘贴或输入要计算的文本", parent=self)
            return
        try:
            encoding = self.text_input_encoding_var.get()
            data = value.encode(encoding)
            self.text_results = calculate_bytes_checksums(data, algorithms, text_encoding=encoding)
        except (LookupError, UnicodeEncodeError, ValueError) as exc:
            messagebox.showerror("计算失败", str(exc), parent=self)
            return
        self.results = []
        self.errors = []
        self.progress.grid_remove()
        self._render_results()
        self.status_var.set(f"文本哈希计算完成（{len(data)} 字节）")

    def stop_calculation(self):
        self._stop_event.set()
        self.status_var.set("正在停止计算...")

    def _calculation_finished(self, results, errors):
        self.results = results
        self.errors = errors
        self.calculate_button.configure(state="normal")
        self.clear_button.configure(state="normal")
        if not self._stop_event.is_set():
            self.progress.configure(value=100)
        self._render_results()
        if self._stop_event.is_set():
            self.status_var.set(f"计算已停止，已完成 {len(results)} 个文件")
        else:
            self.status_var.set(f"文件校验完成：成功 {len(results)}，失败 {len(errors)}")
        self.after(350, self.progress.grid_remove)

    def _set_result_text(self, text):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        if text:
            self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def _render_results(self):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        if self.input_mode_var.get() == "文本输入":
            self.result_text.insert(tk.END, f"文本（{self.text_input_encoding_var.get()}）\n", "filename")
            byte_count = len(self.text_input.get("1.0", "end-1c").encode(self.text_input_encoding_var.get()))
            self.result_text.insert(tk.END, f"字节数：{byte_count}\n")
            for key, value in self.text_results.items():
                label = dict(self.ALGORITHMS)[key]
                self.result_text.insert(tk.END, f"{label}：{value}\n", key)
            self.result_text.configure(state="disabled")
            return
        for result in self.results:
            self.result_text.insert(tk.END, f"文件：{result.path.name}\n", "filename")
            for key, value in result.checksums.items():
                label = dict(self.ALGORITHMS)[key]
                self.result_text.insert(tk.END, f"{label}：{value}\n", key)
            self.result_text.insert(tk.END, f"大小：{format_file_size(result.size)}\n{'-' * 88}\n")
        for error in self.errors:
            self.result_text.insert(tk.END, f"失败：{error}\n", "error")
        self.result_text.configure(state="disabled")

    def _plain_results(self) -> str:
        return self.result_text.get("1.0", tk.END).rstrip()

    def copy_results(self):
        text = self._plain_results()
        if not text:
            messagebox.showinfo("提示", "当前没有可复制的文件校验结果", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("文件校验结果已复制")

    def save_results(self):
        text = self._plain_results()
        if not text:
            messagebox.showinfo("提示", "当前没有可保存的文件校验结果", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="保存文件校验结果", defaultextension=".txt",
            filetypes=(("文本文件", "*.txt"), ("所有文件", "*.*")), parent=self,
        )
        if path:
            header = f"文件校验结果\n计算时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n{'=' * 88}\n"
            Path(path).write_text(header + text, encoding="utf-8")
            self.status_var.set(f"文件校验结果已保存：{path}")
