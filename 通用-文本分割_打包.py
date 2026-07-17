import os
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

def split_file_by_size(file_path, chunk_size, save_directory):
    try:
        with open(file_path, 'rb') as file:
            chunk_index = 0
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break

                file_name = os.path.splitext(os.path.basename(file_path))[0]

                chunk_file_path = f"{save_directory}/{file_name}_{chunk_index}.txt"
                with open(chunk_file_path, 'wb') as chunk_file:
                    chunk_file.write(chunk)

                chunk_index += 1

        messagebox.showinfo("完成", f"文件已成功按大小分割为 {chunk_index} 个部分。")
    except Exception as e:
        messagebox.showerror("错误", f"分割文件时出错: {e}")

def split_file_by_count(file_path, parts, save_directory):
    try:
        with open(file_path, 'rb') as file:
            file_size = os.path.getsize(file_path)
            chunk_size = file_size // parts
            chunk_index = 0

            while chunk_index < parts:
                if chunk_index == parts - 1:
                    chunk = file.read()  # 最后一部分读取剩余的所有数据
                else:
                    chunk = file.read(chunk_size)
                chunk_file_path = f"{save_directory}/{os.path.basename(file_path)}.part{chunk_index}"

                with open(chunk_file_path, 'wb') as chunk_file:
                    chunk_file.write(chunk)

                chunk_index += 1

        messagebox.showinfo("完成", f"文件已成功按数量分割为 {parts} 个部分。")
    except Exception as e:
        messagebox.showerror("错误", f"分割文件时出错: {e}")

def browse_file():
    file_path = filedialog.askopenfilename(title="选择文件")
    entry_file_path.delete(0, tk.END)
    entry_file_path.insert(0, file_path)

def browse_save_directory():
    save_directory = filedialog.askdirectory(title="选择保存目录")
    entry_save_directory.delete(0, tk.END)
    entry_save_directory.insert(0, save_directory)

def start_splitting():
    file_path = entry_file_path.get()
    save_directory = entry_save_directory.get()
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)
    if split_mode.get() == "size":
        try:
            chunk_size = int(entry_chunk_size.get()) * 1024 * 1024
            if os.path.isfile(file_path):
                split_file_by_size(file_path, chunk_size, save_directory)
            else:
                messagebox.showerror("错误", "无效的文件路径。")
        except ValueError:
            messagebox.showerror("错误", "请提供一个有效的分割大小（MB）。")
    elif split_mode.get() == "count":
        try:
            parts = int(entry_chunk_size.get())
            if os.path.isfile(file_path):
                split_file_by_count(file_path, parts, save_directory)
            else:
                messagebox.showerror("错误", "无效的文件路径。")
        except ValueError:
            messagebox.showerror("错误", "请提供一个有效的分割数量。")

# 创建主窗口
root = tk.Tk()
root.title("文件分割工具-木林夕")

# 文件路径输入框和按钮
tk.Label(root, text="选择文件:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
entry_file_path = tk.Entry(root, width=50)
entry_file_path.grid(row=0, column=1, padx=10, pady=10)
tk.Button(root, text="浏览", command=browse_file).grid(row=0, column=2, padx=10, pady=10)

# 保存目录输入框和按钮
tk.Label(root, text="选择保存目录:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
entry_save_directory = tk.Entry(root, width=50)
entry_save_directory.grid(row=1, column=1, padx=10, pady=10)
tk.Button(root, text="浏览", command=browse_save_directory).grid(row=1, column=2, padx=10, pady=10)

# 分割方式选择
tk.Label(root, text="分割方式:").grid(row=2, column=0, padx=10, pady=10, sticky="e")
frame_options = tk.Frame(root)
frame_options.grid(row=2, column=1, columnspan=2, padx=10, pady=10, sticky="w")

split_mode = tk.StringVar(value="size")
tk.Radiobutton(frame_options, text="按大小分割 (MB)", variable=split_mode, value="size").grid(row=0, column=0, padx=10, pady=5, sticky="w")
tk.Radiobutton(frame_options, text="按数量分割", variable=split_mode, value="count").grid(row=1, column=0, padx=10, pady=5, sticky="w")

# 分割大小或数量输入框
entry_chunk_size = tk.Entry(frame_options, width=10)
entry_chunk_size.grid(row=0, column=1, rowspan=2, padx=10, pady=5, sticky="w")

# 开始按钮
tk.Button(root, text="开始分割", command=start_splitting).grid(row=3, column=1, pady=20, sticky="w")

# 运行主循环
root.mainloop()