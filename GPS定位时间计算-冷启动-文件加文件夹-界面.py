import os
import re
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

def extract_timestamp(line):
    """提取行中的时分秒时间戳，兼容无日期格式"""
    match = re.search(r'\[(.*?)\]', line)
    if match:
        timestamp_str = match.group(1)
        try:
            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f').time()
        except ValueError:
            try:
                return datetime.strptime(timestamp_str, '%H:%M:%S.%f').time()
            except ValueError:
                pass
    return None

def process_single_file(file_path, keyword, output_box):
    """处理单个文件，计算每次冷启动时间"""
    if not os.path.exists(file_path):
        output_box.insert(tk.END, f"⚠️ 文件未找到: {file_path}\n")
        return

    with open(file_path, 'r', encoding='gbk', errors='ignore') as file:
        lines = file.readlines()

    cold_start_count = 0
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        # 找到BOOTING行
        while i < total_lines and keyword not in lines[i]:
            i += 1
        if i >= total_lines:
            break

        booting_line = lines[i]
        booting_timestamp = extract_timestamp(booting_line)
        i += 1

        # 寻找GNGGA行
        while i < total_lines:
            line = lines[i]
            if "$GNGGA" in line:
                gngga_parts = line.split(",")
                if len(gngga_parts) > 5 and gngga_parts[2] and gngga_parts[4]:
                    gngga_line = line
                    gngga_timestamp = extract_timestamp(gngga_line)
                    if booting_timestamp and gngga_timestamp:
                        booting_seconds = timedelta(
                            hours=booting_timestamp.hour,
                            minutes=booting_timestamp.minute,
                            seconds=booting_timestamp.second)
                        gngga_seconds = timedelta(
                            hours=gngga_timestamp.hour,
                            minutes=gngga_timestamp.minute,
                            seconds=gngga_timestamp.second)
                        time_diff = gngga_seconds - booting_seconds

                        if time_diff.total_seconds() >= 0:
                            cold_start_count += 1
                            # output_box.insert(tk.END, f"📄 文件：{os.path.basename(file_path)}\n")
                            output_box.insert(tk.END, f"⏱ 第 {cold_start_count} 次冷启动时间: {time_diff.total_seconds()} 秒\n")
                            output_box.insert(tk.END, "-" * 50 + "\n")
                        else:
                            output_box.insert(tk.END, f"⚠️ 文件：{os.path.basename(file_path)} 时间异常，跳过\n")
                    break
            i += 1

def process_directory(directory, keyword, output_box):
    """处理文件夹中的所有文件"""
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            file_path = os.path.join(directory, filename)
            cold_start_count = 0
            with open(file_path, 'r', encoding='gbk', errors='ignore') as file:
                lines = file.readlines()

            i = 0
            total_lines = len(lines)

            while i < total_lines:
                # 找到BOOTING行
                while i < total_lines and keyword not in lines[i]:
                    i += 1
                if i >= total_lines:
                    break

                booting_line = lines[i]
                booting_timestamp = extract_timestamp(booting_line)
                i += 1

                # 寻找GNGGA行
                while i < total_lines:
                    line = lines[i]
                    if "$GNGGA" in line:
                        gngga_parts = line.split(",")
                        if len(gngga_parts) > 5 and gngga_parts[2] and gngga_parts[4]:
                            gngga_line = line
                            gngga_timestamp = extract_timestamp(gngga_line)
                            if booting_timestamp and gngga_timestamp:
                                booting_seconds = timedelta(
                                    hours=booting_timestamp.hour,
                                    minutes=booting_timestamp.minute,
                                    seconds=booting_timestamp.second)
                                gngga_seconds = timedelta(
                                    hours=gngga_timestamp.hour,
                                    minutes=gngga_timestamp.minute,
                                    seconds=gngga_timestamp.second)
                                time_diff = gngga_seconds - booting_seconds

                                if time_diff.total_seconds() >= 0:
                                    cold_start_count += 1
                                    output_box.insert(tk.END, f"文件：{os.path.basename(file_path)}, ⏱冷启动时间: {time_diff.total_seconds()} 秒\n")
                                    output_box.insert(tk.END, "-" * 50 + "\n")

                                else:
                                    output_box.insert(tk.END, f"⚠️ 文件：{os.path.basename(file_path)} 时间异常，跳过\n")
                            break
                    i += 1

def process_entry_path(path, keyword, output_box):
    """根据路径判断处理单个文件还是整个文件夹"""
    output_box.delete(1.0, tk.END)
    if os.path.isdir(path):
        process_directory(path, keyword, output_box)
    elif os.path.isfile(path) and path.endswith(".txt"):
        process_single_file(path, keyword, output_box)
    else:
        messagebox.showerror("错误", "请选择有效的 .txt 文件或文件夹")

def select_folder(entry):
    """选择文件夹"""
    folder_path = filedialog.askdirectory()
    if folder_path:
        entry.delete(0, tk.END)
        entry.insert(0, folder_path)

def select_file(entry):
    """选择单个文件"""
    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)

def run_gui():
    """启动 GUI 界面"""
    root = tk.Tk()
    root.title("冷启动分析工具-木林夕")
    root.geometry("850x620")

    # 输入路径
    tk.Label(root, text="日志文件 / 文件夹路径：").grid(row=0, column=0, sticky='e', padx=5, pady=5)
    path_entry = tk.Entry(root, width=60)
    path_entry.grid(row=0, column=1, padx=5)

    # 浏览按钮
    tk.Button(root, text="选择文件", command=lambda: select_file(path_entry)).grid(row=0, column=2, padx=2)
    tk.Button(root, text="选择文件夹", command=lambda: select_folder(path_entry)).grid(row=0, column=3, padx=2)

    # 启动关键字输入
    tk.Label(root, text="启动关键字：").grid(row=1, column=0, sticky='e', padx=5, pady=5)
    keyword_entry = tk.Entry(root)
    keyword_entry.insert(0, "BOOTING")  # 默认关键字为 "BOOTING"
    keyword_entry.grid(row=1, column=1, sticky='w', padx=5)

    # 输出区域
    output_box = scrolledtext.ScrolledText(root, width=100, height=30)
    output_box.grid(row=2, column=0, columnspan=4, padx=10, pady=10)

    # 分析按钮
    tk.Button(root, text="开始分析", height=2, width=20,
              command=lambda: process_entry_path(path_entry.get(), keyword_entry.get(), output_box)
              ).grid(row=3, column=1, pady=10)

    root.mainloop()

if __name__ == "__main__":
    run_gui()
