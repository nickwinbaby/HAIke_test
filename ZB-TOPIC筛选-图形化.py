# -*- coding: utf-8 -*-
import os
import tkinter as tk
from tkinter import filedialog, messagebox

def select_input_file():
    file_path = filedialog.askopenfilename(
        title="选择输入文件",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)

def select_output_dir():
    dir_path = filedialog.askdirectory(title="选择输出目录")
    if dir_path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, dir_path)

def clear_placeholder(event):
    if topic_entry.get() == "loc/imei":
        topic_entry.delete(0, tk.END)
        topic_entry.config(fg="black")

def add_placeholder(event):
    if topic_entry.get() == "":
        topic_entry.insert(0, "loc/imei")
        topic_entry.config(fg="gray")

def run_filter():
    input_file = input_entry.get()
    output_dir = output_entry.get()
    target_topic = topic_entry.get()

    if not input_file or not os.path.isfile(input_file):
        messagebox.showerror("错误", "请选择有效的输入文件")
        return

    if not output_dir or not os.path.isdir(output_dir):
        messagebox.showerror("错误", "请选择有效的输出目录")
        return

    if not target_topic or target_topic == "loc/imei":
        messagebox.showerror("错误", "请输入有效的 topic")
        return

    # 自动生成输出文件名
    base_name = os.path.basename(input_file)
    name, ext = os.path.splitext(base_name)
    output_file = os.path.join(output_dir, f"{name}-筛选.txt")

    try:
        with open(input_file, "r", encoding="utf-8") as infile, \
             open(output_file, "w", encoding="utf-8") as outfile:

            record = []
            write_record = False

            for line in infile:
                line_strip = line.strip()

                if line_strip.startswith("202") and "Topic:" in line_strip:
                    if write_record and record:
                        outfile.writelines(record)
                        outfile.write("\n")

                    record = [line]
                    write_record = target_topic in line_strip
                else:
                    if record:
                        record.append(line)

            if write_record and record:
                outfile.writelines(record)

        messagebox.showinfo("完成", f"筛选完成！\n输出文件：\n{output_file}")

    except Exception as e:
        messagebox.showerror("错误", str(e))


# ================= GUI =================
root = tk.Tk()
root.title("GT115_ZB_TOPIC_筛选工具-Mangetic")
root.geometry("500x250")

# 输入文件
tk.Label(root, text="输入文件:").pack(anchor="w", padx=10, pady=5)
frame1 = tk.Frame(root)
frame1.pack(fill="x", padx=10)
input_entry = tk.Entry(frame1)
input_entry.pack(side="left", fill="x", expand=True)
tk.Button(frame1, text="选择文件", command=select_input_file).pack(side="left", padx=5)

# 输出目录
tk.Label(root, text="输出目录:").pack(anchor="w", padx=10, pady=5)
frame2 = tk.Frame(root)
frame2.pack(fill="x", padx=10)
output_entry = tk.Entry(frame2)
output_entry.pack(side="left", fill="x", expand=True)
tk.Button(frame2, text="选择目录", command=select_output_dir).pack(side="left", padx=5)

# Topic 输入
tk.Label(root, text="Topic:").pack(anchor="w", padx=10, pady=5)
topic_entry = tk.Entry(root, fg="gray")
topic_entry.pack(fill="x", padx=10)
topic_entry.insert(0, "topic/imei")

topic_entry.bind("<FocusIn>", clear_placeholder)
topic_entry.bind("<FocusOut>", add_placeholder)

# 运行按钮
tk.Button(root, text="开始筛选", command=run_filter, bg="#4CAF50", fg="white").pack(pady=20)

root.mainloop()