import os, sys
import re
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

# 编译命令
# pyinstaller -F -w --clean -n "GPS定位时间计算工具" -i gps_time_stats_icon.ico --add-data "gps_time_stats_icon.ico;." "GPS定位时间计算-冷启动单文件-界面-616优化代码.py"

# 预编译正则
RE_BRACKET_TIME = re.compile(r'\[(.*?)\]')
RE_LINE_HEAD_DATETIME = re.compile(r'(\d{4}[-/]\d{2}[-/]\d{2}[ -]\d{2}:\d{2}:\d{2}(?:[:.]\d+)?)')

# GGA 第 6 个字段（逗号分割后 parts[6]）为定位质量：
# 0=无效，1=单点，2=差分，3=PPS，4=RTK固定，5=RTK浮点，6=航位推算。
# 冷启动 TTFF 默认只统计卫星/RTK产生的有效定位，不把 6 航位推算计为定位成功。
VALID_GGA_FIX_QUALITY = {"1", "2", "3", "4", "5"}

def resource_path(relative_path):
    """获取资源文件的绝对路径（兼容打包后和开发模式）"""
    try:
        # PyInstaller 创建的临时文件夹
        base_path = sys._MEIPASS
    except Exception:
        # 开发模式下的路径
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def set_windows_app_id():
    """让 Windows 任务栏/Alt-Tab 使用本工具自己的应用身份和图标。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "GNSSColdStartAnalyzer.GPSLocateTimeTool"
        )
    except Exception:
        pass

def extract_timestamp(line):
    bracket_match = RE_BRACKET_TIME.search(line)
    if bracket_match:
        ts_str = bracket_match.group(1).strip()
        # 兼容 .毫秒 和 :毫秒 两种格式
        fmt_list = [
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S:%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d-%H:%M:%S.%f',
            '%Y/%m/%d-%H:%M:%S:%f',
            '%Y/%m/%d-%H:%M:%S',
            '%H:%M:%S.%f',
            '%H:%M:%S:%f',
            '%H:%M:%S'
        ]
        for fmt in fmt_list:
            try:
                dt = datetime.strptime(ts_str, fmt)
                if fmt.startswith("%H"):
                    now = datetime.now()
                    dt = dt.replace(year=now.year, month=now.month, day=now.day)
                return dt
            except ValueError:
                continue

    line_match = RE_LINE_HEAD_DATETIME.match(line.strip())
    if line_match:
        ts_str = line_match.group(1)
        fixed_ts = re.sub(r'(\d{2}:\d{2}:\d{2}):(\d{3,6})', r'\1.\2', ts_str)
        if "/" in ts_str and "-" in ts_str:
            fmt = '%Y/%m/%d-%H:%M:%S.%f' if "." in fixed_ts else '%Y/%m/%d-%H:%M:%S'
        else:
            fmt = '%Y-%m-%d %H:%M:%S.%f' if "." in fixed_ts else '%Y-%m-%d %H:%M:%S'
        try:
            return datetime.strptime(fixed_ts, fmt)
        except ValueError:
            pass
    return None

def is_valid_nmea(nmea_line, skip_loc_check=False):
    parts = nmea_line.split(",")
    if skip_loc_check:
        if len(parts) > 4 and parts[2].strip() and parts[4].strip():
            return True
        return False
    else:
        return len(parts) > 6 and parts[6].strip() in VALID_GGA_FIX_QUALITY

def process_file(file_path, boot_keyword, nmea_keyword, skip_loc_check, output_box):
    file_path = file_path.strip()
    boot_keyword = boot_keyword.strip()
    nmea_keyword = nmea_keyword.strip()

    if not file_path:
        messagebox.showwarning("提示", "请先选择日志文件！")
        return
    if not boot_keyword:
        messagebox.showwarning("提示", "启动关键字不能为空！")
        return
    if not nmea_keyword:
        messagebox.showwarning("提示", "定位NMEA语句不能为空！示例：$GNGGA、$GGA")
        return
    if not os.path.exists(file_path):
        messagebox.showerror("错误", f"文件不存在: {file_path}")
        return

    output_box.delete(1.0, tk.END)
    output_box.insert(tk.END, f"=== 开始分析日志：{os.path.basename(file_path)} ===\n")
    output_box.insert(tk.END, f"启动匹配关键字：{boot_keyword}\n")
    output_box.insert(tk.END, f"定位NMEA语句：{nmea_keyword}\n")
    rule_desc = "仅检查经纬度（不校验GGA状态码）" if skip_loc_check else "校验GGA状态码（1/2/3/4/5）"
    output_box.insert(tk.END, f"定位判定规则：{rule_desc}\n")
    output_box.insert(tk.END, "="*45 + "\n")
    output_box.update()

    cold_start_records = []  # 仅存储成功算出耗时的记录，用于统计
    boot_total_count = 0     # 所有启动总计数（成功+异常都占用序号）
    line_idx = 0
    lines = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
            output_box.insert(tk.END, "警告：文件非UTF-8，已切换GBK编码读取\n\n")
        except Exception as e:
            messagebox.showerror("读取失败", f"文件打开异常：{str(e)}")
            return

    total_lines = len(lines)

    while line_idx < total_lines:
        # 找到当前boot行
        while line_idx < total_lines and boot_keyword not in lines[line_idx]:
            line_idx += 1
        if line_idx >= total_lines:
            break

        boot_line = lines[line_idx]
        boot_dt = extract_timestamp(boot_line)
        boot_line_no = line_idx + 1
        line_idx += 1
        boot_total_count += 1  # 每匹配到一次启动，序号+1

        if not boot_dt:
            output_box.insert(
                tk.END,
                f"第 {boot_total_count} 次冷热启动 | 异常：该行无有效时间戳，无法计算耗时"
                f"  启动行：{boot_line_no}\n"
            )
            output_box.see(tk.END)
            output_box.update()
            continue

        found_valid_nmea = False
        # 检索区间遇到下一个boot直接停止，不跨启动抓取GNGGA
        while line_idx < total_lines:
            curr_line = lines[line_idx]
            if boot_keyword in curr_line:
                break
            if nmea_keyword in curr_line:
                if is_valid_nmea(curr_line, skip_loc_check):
                    nmea_dt = extract_timestamp(curr_line)
                    if nmea_dt:
                        delta = nmea_dt - boot_dt
                        cost_sec = delta.total_seconds()
                        cold_start_records.append(cost_sec)
                        output_box.insert(
                            tk.END,
                            f"第 {boot_total_count} 次冷热启动 | 耗时：{cost_sec:.3f} 秒"
                            f"  启动行：{boot_line_no} | 定位行：{line_idx+1}\n"
                        )
                        found_valid_nmea = True
                        break
            line_idx += 1

        if not found_valid_nmea:
            output_box.insert(
                tk.END,
                f"第 {boot_total_count} 次冷热启动 | 异常：本次启动至下一次启动前，未检测到有效定位NMEA数据"
                f"  启动行：{boot_line_no}\n"
            )
        output_box.see(tk.END)
        output_box.update()

    # 统计汇总输出
    output_box.insert(tk.END, "="*45 + "\n分析完成 · 统计汇总\n")
    output_box.insert(tk.END, f"总共检测到启动次数：{boot_total_count} 次\n")
    if not cold_start_records:
        output_box.insert(tk.END,
            f"无任何有效冷热启动耗时记录！排查方向：\n"
            f"1. 启动关键字「{boot_keyword}」是否和日志完全一致\n"
            f"2. 勾选【仅检查经纬度（不校验GGA状态码）】使用宽松匹配规则\n"
            f"3. 确认日志内存在{nmea_keyword}语句\n"
        )
    else:
        valid_cnt = len(cold_start_records)
        avg_sec = sum(cold_start_records) / valid_cnt
        min_sec = min(cold_start_records)
        max_sec = max(cold_start_records)
        output_box.insert(tk.END,
            f"有效定位成功次数：{valid_cnt} 次\n"
            f"单次最小耗时：{min_sec:.3f} s\n"
            f"单次最大耗时：{max_sec:.3f} s\n"
            f"平均启动耗时：{avg_sec:.3f} s\n"
        )
    output_box.see(tk.END)

def select_file(entry):
    path = filedialog.askopenfilename(
        title="选择GNSS日志文件",
        filetypes=[("日志文本", "*.txt;*.log"), ("所有文件", "*.*")]
    )
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)

def run_gui():
    set_windows_app_id()

    root = tk.Tk()
    root.title("GNSS 冷热启动时间分析工具-Mangetic-2026-7-15")
    root.geometry("760x580")
    root.resizable(True, True)

    # 图标设置：增加异常处理（文件不存在时不崩溃）
    try:
        ico_file = resource_path("gps_time_stats_icon.ico")
        if os.path.exists(ico_file):
            root.iconbitmap(ico_file)
            root.iconbitmap(default=ico_file)
    except Exception:
        pass

    # 自适应权重配置
    root.grid_rowconfigure(4, weight=1)
    root.grid_columnconfigure(1, weight=1)

    # 第0行 文件路径
    tk.Label(root, text="日志文件路径：").grid(row=0, column=0, sticky='e', padx=6, pady=4)
    file_entry = tk.Entry(root)
    file_entry.grid(row=0, column=1, sticky='ew', padx=4)
    tk.Button(root, text="浏览", width=6, command=lambda: select_file(file_entry)).grid(row=0, column=2, padx=4)

    # 第1行 启动关键字
    tk.Label(root, text="启动匹配关键字：").grid(row=1, column=0, sticky='e', padx=6, pady=4)
    boot_key_entry = tk.Entry(root)
    boot_key_entry.insert(0, "Welcome to boot rom")
    boot_key_entry.grid(row=1, column=1, sticky='ew', padx=4)

    # 第2行 NMEA语句
    tk.Label(root, text="定位NMEA语句：").grid(row=2, column=0, sticky='e', padx=6, pady=4)
    nmea_entry = tk.Entry(root)
    nmea_entry.insert(0, "$GNGGA")
    nmea_entry.grid(row=2, column=1, sticky='ew', padx=4)

    # 第3行 复选框
    skip_check_var = tk.BooleanVar()
    skip_check_var.set(False)
    tk.Checkbutton(
        root, text="仅检查经纬度（不校验GGA状态码）",
        variable=skip_check_var
    ).grid(row=3, column=1, sticky='w', padx=4, pady=2)

    # 输出文本框 自适应宽高
    output_box = scrolledtext.ScrolledText(root, font=("Consolas", 9))
    output_box.grid(row=4, column=0, columnspan=3, sticky='nsew', padx=10, pady=8)

    # 分析按钮
    def start_analyze():
        f_path = file_entry.get()
        boot_key = boot_key_entry.get()
        nmea_key = nmea_entry.get()
        skip_check = skip_check_var.get()
        process_file(f_path, boot_key, nmea_key, skip_check, output_box)

    tk.Button(
        root, text="开始分析", height=2, width=16, font=("微软雅黑", 10),
        command=start_analyze
    ).grid(row=5, column=1, pady=6)

    root.mainloop()

if __name__ == "__main__":
    run_gui()
