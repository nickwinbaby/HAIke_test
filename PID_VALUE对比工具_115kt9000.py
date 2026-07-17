import tkinter as tk
from tkinter import filedialog, messagebox
import openpyxl
import re
import json
import os
import shutil


# -----------------------------
# 提取 TXT 中所有 JSON 数据
# -----------------------------
def extract_json_from_txt(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    json_blocks = re.findall(r"\{[\s\S]*?\}", content)
    parsed_items = []

    for block in json_blocks:
        try:
            data = json.loads(block)
            for k, v in data.items():
                parsed_items.append(f"{str(k).upper()}")
        except:
            continue

    return parsed_items


# -----------------------------
# 将数据写入 Excel 并比对
# -----------------------------
def write_and_compare(excel_path, items):
    print(f"[DEBUG] 提取 JSON 条数: {len(items)}")

    # 先复制到临时文件避免占用问题
    temp_path = excel_path + ".tmp.xlsx"
    shutil.copy(excel_path, temp_path)

    wb = openpyxl.load_workbook(temp_path, data_only=False)
    ws = wb.active

    # 清空 B 列
    for cell in ws['B']:
        cell.value = None

    # 写入 B 列（从 B2 开始）
    row = 2
    for item in items:
        ws[f"B{row}"].value = item
        row += 1

    wb.save(temp_path)
    wb.close()

    # 覆盖原文件
    shutil.move(temp_path, excel_path)

    # 再次打开对比
    wb = openpyxl.load_workbook(excel_path)
    ws = wb.active

    # 处理 B 列内容为集合用于快速判断
    b_set = set()
    for cell in ws['B']:
        if cell.value:
            b_set.add(str(cell.value).strip().lower())

    # --------------------
    # A 列比对，加入你的新需求：
    # ❗ 空的 A 单元格不进行比对
    # --------------------
    for i in range(1, ws.max_row + 1):
        a_raw = ws[f"A{i}"].value

        # 跳过空单元格，不写入 C 列
        if a_raw is None or str(a_raw).strip() == "":
            ws[f"C{i}"].value = ""
            continue

        a_val = str(a_raw).strip().lower()

        if a_val in b_set:
            ws[f"C{i}"].value = "出现在B列"
        else:
            ws[f"C{i}"].value = "未出现"

    wb.save(excel_path)
    wb.close()

    print("[DEBUG] 比对结束，Excel 写入成功")


# -----------------------------
# GUI
# -----------------------------
def select_excel():
    excel_path_var.set(
        filedialog.askopenfilename(
            title="选择 Excel 文件",
            filetypes=[("Excel File", "*.xlsx")]
        )
    )


def select_txt():
    txt_path_var.set(
        filedialog.askopenfilename(
            title="选择 TXT 文件",
            filetypes=[("Text File", "*.txt")]
        )
    )


def start_process():
    excel_path = excel_path_var.get()
    txt_path = txt_path_var.get()

    if not excel_path:
        messagebox.showerror("错误", "请选择 Excel 文件！")
        return

    if not txt_path:
        messagebox.showerror("错误", "请选择 TXT 文件！")
        return

    items = extract_json_from_txt(txt_path)

    if not items:
        messagebox.showerror("错误", "TXT 内未找到 JSON 数据！")
        return

    write_and_compare(excel_path, items)
    messagebox.showinfo("成功", "处理完成，Excel 已成功写入！")


root = tk.Tk()
root.title("Excel/MQTT 数据比对工具")
root.geometry("600x250")

excel_path_var = tk.StringVar()
txt_path_var = tk.StringVar()

tk.Label(root, text="比对基准数据（Excel）:").pack()
tk.Entry(root, textvariable=excel_path_var, width=65).pack()
tk.Button(root, text="选择Excel文件", command=select_excel).pack()

tk.Label(root, text="MQTT 监听数据（TXT）:").pack()
tk.Entry(root, textvariable=txt_path_var, width=65).pack()
tk.Button(root, text="选择TXT文件", command=select_txt).pack()

tk.Button(root, text="开始处理", bg="lightgreen", command=start_process).pack(pady=20)

root.mainloop()
