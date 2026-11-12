from __future__ import annotations

import csv
import re
import threading
import tkinter as tk
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "107MCU注册时间统计工具"
DEFAULT_START_MARKER = "Read_MCU_Info---Enter"
DEFAULT_REGISTER_MARKER = '"1A2D001",8'
AUTO_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")

# 支持示例中的 [2026-10-26 15:35:43.307]，也支持时间戳不在行首的日志格式。
TIMESTAMP_RE = re.compile(
    r"(?<!\d)(?P<timestamp>\d{4}[-/]\d{2}[-/]\d{2}"
    r"[ T]\d{2}:\d{2}:\d{2}(?:[.,:]\d{1,6})?)(?![\d.,])"
)


@dataclass(frozen=True)
class RegistrationRecord:
    """一轮 Read_MCU_Info 查询的统计结果。"""

    sequence: int
    start_line_number: int
    start_timestamp: datetime | None
    target_line_number: int | None
    target_timestamp: datetime | None
    delta_seconds: float | None
    status: str
    start_line: str
    target_line: str | None
    source_file: str = "日志"
    source_path: str = "日志"


@dataclass(frozen=True)
class AnalysisResult:
    source_path: Path
    encoding: str
    records: list[RegistrationRecord]
    source_files: tuple[Path, ...] = ()

    @property
    def registered_records(self) -> list[RegistrationRecord]:
        return [record for record in self.records if record.delta_seconds is not None]

    @property
    def unregistered_records(self) -> list[RegistrationRecord]:
        return [record for record in self.records if record.status == "未注册"]


def parse_timestamp(line: str) -> datetime | None:
    """从一行中提取第一个完整时间戳。"""
    match = TIMESTAMP_RE.search(line)
    if not match:
        return None

    value = match.group("timestamp").replace("/", "-").replace(",", ".")
    # 某些串口日志使用 HH:MM:SS:毫秒，统一成 datetime 可识别的格式。
    value = re.sub(r"(\d{2}:\d{2}:\d{2}):(\d+)$", r"\1.\2", value)
    if "." in value:
        base, fraction = value.rsplit(".", 1)
        value = f"{base}.{fraction[:6].ljust(6, '0')}"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _read_lines(path: Path, encoding_choice: str = "自动识别") -> tuple[list[str], str]:
    encodings = AUTO_ENCODINGS if encoding_choice == "自动识别" else (encoding_choice,)
    errors: list[str] = []
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, errors="strict", newline=None) as file:
                return file.readlines(), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise UnicodeError("无法识别 TXT 文件编码，请手动选择编码。\n" + "\n".join(errors))


def analyze_lines(
    lines: list[str],
    start_marker: str = DEFAULT_START_MARKER,
    register_marker: str = DEFAULT_REGISTER_MARKER,
    source_path: str | Path = "日志",
    encoding: str = "未知",
) -> AnalysisResult:
    """按启动行切分查询区间，并取每区间第一条注册行。"""
    start_marker = start_marker.strip()
    register_marker = register_marker.strip()
    if not start_marker:
        raise ValueError("启动关键字不能为空。")
    if not register_marker:
        raise ValueError("注册关键字不能为空。")

    start_indexes = [index for index, line in enumerate(lines) if start_marker in line]
    records: list[RegistrationRecord] = []

    for sequence, start_index in enumerate(start_indexes, start=1):
        next_start_index = (
            start_indexes[sequence] if sequence < len(start_indexes) else len(lines)
        )
        start_line = lines[start_index].rstrip("\r\n")
        start_timestamp = parse_timestamp(start_line)

        target_index: int | None = None
        for index in range(start_index + 1, next_start_index):
            if register_marker in lines[index]:
                target_index = index
                break

        if target_index is None:
            records.append(
                RegistrationRecord(
                    sequence=sequence,
                    start_line_number=start_index + 1,
                    start_timestamp=start_timestamp,
                    target_line_number=None,
                    target_timestamp=None,
                    delta_seconds=None,
                    status="未注册",
                    start_line=start_line,
                    target_line=None,
                    source_file=Path(source_path).name,
                    source_path=str(Path(source_path)),
                )
            )
            continue

        target_line = lines[target_index].rstrip("\r\n")
        target_timestamp = parse_timestamp(target_line)
        if start_timestamp is None or target_timestamp is None:
            status = "时间戳无效"
            delta_seconds = None
        else:
            delta_seconds = (target_timestamp - start_timestamp).total_seconds()
            status = "成功" if delta_seconds >= 0 else "时间顺序异常"
            if delta_seconds < 0:
                delta_seconds = None

        records.append(
            RegistrationRecord(
                sequence=sequence,
                start_line_number=start_index + 1,
                start_timestamp=start_timestamp,
                target_line_number=target_index + 1,
                target_timestamp=target_timestamp,
                delta_seconds=delta_seconds,
                status=status,
                start_line=start_line,
                target_line=target_line,
                source_file=Path(source_path).name,
                source_path=str(Path(source_path)),
            )
        )

    source = Path(source_path)
    return AnalysisResult(source, encoding, records, (source,))


def analyze_file(
    file_path: str | Path,
    start_marker: str = DEFAULT_START_MARKER,
    register_marker: str = DEFAULT_REGISTER_MARKER,
    encoding_choice: str = "自动识别",
) -> AnalysisResult:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"TXT 文件不存在：{path}")
    lines, encoding = _read_lines(path, encoding_choice)
    return analyze_lines(lines, start_marker, register_marker, path, encoding)


def analyze_files(
    file_paths: list[str] | tuple[str, ...],
    start_marker: str = DEFAULT_START_MARKER,
    register_marker: str = DEFAULT_REGISTER_MARKER,
    encoding_choice: str = "自动识别",
) -> AnalysisResult:
    """逐个独立分析文件，再按选择顺序合并结果。"""
    paths = tuple(Path(path) for path in file_paths)
    if not paths:
        raise ValueError("请至少选择一个 TXT 日志文件。")

    merged_records: list[RegistrationRecord] = []
    encodings: list[str] = []
    sequence = 1
    for path in paths:
        result = analyze_file(path, start_marker, register_marker, encoding_choice)
        encodings.append(result.encoding)
        for record in result.records:
            merged_records.append(replace(record, sequence=sequence))
            sequence += 1

    encoding_text = encodings[0] if len(set(encodings)) == 1 else "、".join(dict.fromkeys(encodings))
    return AnalysisResult(paths[0], encoding_text, merged_records, paths)


def format_timestamp(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if value else "-"


def export_csv(result: AnalysisResult, output_path: str | Path) -> Path:
    destination = Path(output_path)
    if destination.suffix.lower() != ".csv":
        destination = destination.with_suffix(".csv")
    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "文件名",
                "序号",
                "启动行号",
                "启动时间",
                "注册行号",
                "注册时间",
                "耗时（秒）",
                "状态",
                "启动原始行",
                "注册原始行",
            ]
        )
        for record in result.records:
            writer.writerow(
                [
                    record.source_file,
                    record.sequence,
                    record.start_line_number,
                    format_timestamp(record.start_timestamp),
                    record.target_line_number or "-",
                    format_timestamp(record.target_timestamp),
                    f"{record.delta_seconds:.3f}" if record.delta_seconds is not None else "-",
                    record.status,
                    record.start_line,
                    record.target_line or "-",
                ]
            )
    return destination


class RegistrationAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x680")
        self.root.minsize(900, 540)
        self.result: AnalysisResult | None = None
        self.elapsed_window: tk.Toplevel | None = None
        self.selected_files: tuple[str, ...] = ()
        self.selected_files_display = ""
        self._build_widgets()

    def _build_widgets(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(5, weight=1)

        ttk.Label(self.root, text="TXT 日志文件：").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        self.file_var = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.file_var).grid(row=0, column=1, padx=4, pady=8, sticky="ew")
        ttk.Button(self.root, text="选择文件…", command=self.choose_file).grid(row=0, column=2, padx=8, pady=8)

        ttk.Label(self.root, text="启动关键字：").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        self.start_var = tk.StringVar(value=DEFAULT_START_MARKER)
        ttk.Entry(self.root, textvariable=self.start_var).grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        ttk.Label(self.root, text="注册关键字：").grid(row=2, column=0, padx=8, pady=4, sticky="e")
        self.register_var = tk.StringVar(value=DEFAULT_REGISTER_MARKER)
        ttk.Entry(self.root, textvariable=self.register_var).grid(row=2, column=1, padx=4, pady=4, sticky="ew")

        ttk.Label(self.root, text="编码：").grid(row=3, column=0, padx=8, pady=4, sticky="e")
        self.encoding_var = tk.StringVar(value="自动识别")
        ttk.Combobox(
            self.root,
            textvariable=self.encoding_var,
            values=("自动识别", "utf-8-sig", "utf-8", "gb18030", "gbk"),
            state="readonly",
            width=14,
        ).grid(row=3, column=1, padx=4, pady=4, sticky="w")

        action_frame = ttk.Frame(self.root)
        action_frame.grid(row=4, column=0, columnspan=3, padx=8, pady=8, sticky="ew")
        self.analyze_button = ttk.Button(action_frame, text="开始分析", command=self.start_analysis)
        self.analyze_button.pack(side="left")
        self.export_button = ttk.Button(action_frame, text="导出 CSV", command=self.export_result, state="disabled")
        self.export_button.pack(side="left", padx=8)
        self.horizontal_button = ttk.Button(
            action_frame,
            text="耗时横向窗口",
            command=self.open_elapsed_window,
            state="disabled",
        )
        self.horizontal_button.pack(side="left")
        self.status_var = tk.StringVar(value="请选择 TXT 文件。")
        ttk.Label(action_frame, textvariable=self.status_var).pack(side="left", padx=12)

        table_frame = ttk.Frame(self.root)
        table_frame.grid(row=5, column=0, columnspan=3, padx=8, pady=(0, 4), sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = ("file", "sequence", "start", "target", "elapsed", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        headings = {
            "file": "文件名",
            "sequence": "序号",
            "start": "启动时间",
            "target": "注册时间",
            "elapsed": "耗时（秒）",
            "status": "状态",
        }
        widths = {
            "file": 180,
            "sequence": 60,
            "start": 180,
            "target": 180,
            "elapsed": 100,
            "status": 120,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="center")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self.show_record_detail)

        self.summary_text = tk.Text(self.root, height=5, state="disabled", wrap="word")
        self.summary_text.grid(row=6, column=0, columnspan=3, padx=8, pady=(4, 8), sticky="ew")

    def choose_file(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择一个或多个 TXT 日志",
            filetypes=(("文本日志", "*.txt;*.log"), ("所有文件", "*.*")),
        )
        if paths:
            self.selected_files = tuple(paths)
            self.selected_files_display = " | ".join(paths)
            self.file_var.set(self.selected_files_display)
            self.status_var.set(f"已选择 {len(paths)} 个文件，点击“开始分析”。")

    def start_analysis(self) -> None:
        file_text = self.file_var.get().strip()
        if not file_text:
            messagebox.showwarning("提示", "请先选择 TXT 日志文件。")
            return
        if self.selected_files and file_text == self.selected_files_display:
            file_paths = self.selected_files
        else:
            file_paths = (file_text,)
        start_marker = self.start_var.get()
        register_marker = self.register_var.get()
        encoding_choice = self.encoding_var.get()
        if self.elapsed_window is not None and self.elapsed_window.winfo_exists():
            self.elapsed_window.destroy()
        self.horizontal_button.configure(state="disabled")
        self.analyze_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.status_var.set("正在读取并分析，请稍候…")
        threading.Thread(
            target=self._analyze_worker,
            args=(file_paths, start_marker, register_marker, encoding_choice),
            daemon=True,
        ).start()

    def _analyze_worker(
        self,
        file_paths: tuple[str, ...],
        start_marker: str,
        register_marker: str,
        encoding_choice: str,
    ) -> None:
        try:
            result = analyze_files(
                file_paths,
                start_marker,
                register_marker,
                encoding_choice,
            )
        except Exception as exc:  # 将后台异常安全地交给主线程显示。
            self.root.after(0, self._analysis_failed, str(exc))
            return
        self.root.after(0, self._display_result, result)

    def _analysis_failed(self, message: str) -> None:
        self.analyze_button.configure(state="normal")
        self.status_var.set("分析失败。")
        messagebox.showerror("分析失败", message)

    def _display_result(self, result: AnalysisResult) -> None:
        self.result = result
        self.horizontal_button.configure(state="normal" if result.records else "disabled")
        for item in self.tree.get_children():
            self.tree.delete(item)
        for record in result.records:
            elapsed = f"{record.delta_seconds:.3f}" if record.delta_seconds is not None else "-"
            self.tree.insert(
                "",
                "end",
                iid=str(record.sequence),
                values=(
                    record.source_file,
                    record.sequence,
                    format_timestamp(record.start_timestamp),
                    format_timestamp(record.target_timestamp),
                    elapsed,
                    record.status,
                ),
            )

        registered = result.registered_records
        unregistered = result.unregistered_records
        invalid = sum(record.status == "时间戳无效" for record in result.records)
        average = sum(record.delta_seconds for record in registered) / len(registered) if registered else None
        average_text = f"平均 {average:.3f} 秒" if average is not None else "无有效数据"
        file_count = len(result.source_files) or 1
        summary = (
            f"文件数量：{file_count}    编码：{result.encoding}\n"
            f"启动次数：{len(result.records)}    成功注册：{len(registered)}    "
            f"未注册：{len(unregistered)}    时间戳异常：{invalid}\n"
            f"耗时统计（仅成功记录）：{average_text}"
        )
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", summary)
        self.summary_text.configure(state="disabled")
        self.status_var.set("分析完成。双击表格行可查看原始日志。")
        self.analyze_button.configure(state="normal")
        self.export_button.configure(state="normal" if result.records else "disabled")

    def open_elapsed_window(self) -> None:
        """打开便于横向查看和复制耗时的独立窗口。"""
        if not self.result or not self.result.records:
            return

        if self.elapsed_window is not None and self.elapsed_window.winfo_exists():
            self.elapsed_window.destroy()

        window = tk.Toplevel(self.root)
        self.elapsed_window = window
        window.title("耗时横向列表")
        window.geometry("1000x230")
        window.minsize(620, 180)
        window.transient(self.root)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        ttk.Label(
            window,
            text="每个文件占一行，文件名在第一列，后面是该文件各次耗时（秒）。",
        ).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

        text_frame = ttk.Frame(window)
        text_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        elapsed_text = tk.Text(text_frame, height=4, wrap="none", undo=False)
        elapsed_text.grid(row=0, column=0, sticky="nsew")
        horizontal_scrollbar = ttk.Scrollbar(
            text_frame, orient="horizontal", command=elapsed_text.xview
        )
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        vertical_scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=elapsed_text.yview
        )
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        elapsed_text.configure(
            xscrollcommand=horizontal_scrollbar.set,
            yscrollcommand=vertical_scrollbar.set,
        )

        file_rows: list[str] = []
        header_width = 0
        for source_path in self.result.source_files:
            file_records = [
                record
                for record in self.result.records
                if Path(record.source_path) == source_path
            ]
            values = [
                f"{record.delta_seconds:.3f}" if record.delta_seconds is not None else "-"
                for record in file_records
            ]
            header_width = max(header_width, len(values))
            file_rows.append("\t".join([source_path.name, *values]))

        elapsed_rows = "\n".join(file_rows)
        header_row = "\t".join(["文件名", *(f"第{i}次" for i in range(1, header_width + 1))])
        elapsed_text.insert("1.0", elapsed_rows)
        elapsed_text.configure(state="disabled")

        button_frame = ttk.Frame(window)
        button_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="e")

        def copy_elapsed() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(elapsed_rows)
            self.root.update()  # 保证窗口关闭后剪贴板内容仍然保留。
            messagebox.showinfo(
                "复制完成",
                "已按每个文件一行复制，可直接粘贴到 Excel。",
                parent=window,
            )

        def copy_with_sequence() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(f"{header_row}\n{elapsed_rows}")
            self.root.update()
            messagebox.showinfo("复制完成", "表头、文件名和耗时已复制。", parent=window)

        ttk.Button(button_frame, text="复制文件名+耗时", command=copy_elapsed).pack(side="left", padx=4)
        ttk.Button(button_frame, text="复制表头+全部数据", command=copy_with_sequence).pack(side="left", padx=4)
        ttk.Button(button_frame, text="关闭", command=window.destroy).pack(side="left", padx=4)
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.after_idle(lambda: (window.lift(), window.focus_force(), elapsed_text.focus_set()))

    def show_record_detail(self, _event: tk.Event) -> None:
        if not self.result:
            return
        selected = self.tree.selection()
        if not selected:
            return
        record = self.result.records[int(selected[0]) - 1]
        detail = (
            f"文件：{record.source_file}\n"
            f"第 {record.sequence} 轮：{record.status}\n"
            f"启动行 {record.start_line_number}：{record.start_line}\n"
        )
        if record.target_line is None:
            detail += "注册行：未找到（截至下一轮启动或文件结束）"
        else:
            detail += f"注册行 {record.target_line_number}：{record.target_line}"
        messagebox.showinfo("日志详情", detail)

    def export_result(self) -> None:
        if not self.result:
            return
        if len(self.result.source_files) > 1:
            default_name = "多文件_MCU注册时间统计.csv"
        else:
            default_name = self.result.source_path.stem + "_MCU注册时间统计.csv"
        output = filedialog.asksaveasfilename(
            title="导出统计结果",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=(("CSV 文件", "*.csv"), ("所有文件", "*.*")),
        )
        if not output:
            return
        try:
            destination = export_csv(self.result, output)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        messagebox.showinfo("导出完成", f"结果已保存到：\n{destination}")


def main() -> None:
    root = tk.Tk()
    RegistrationAnalyzerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
