import tkinter as tk
import re
import os
from tkinter import filedialog

from openpyxl import Workbook
from datetime import datetime
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# 编译命令 pyinstaller --onefile --windowed V16协议解析.py
# 应用时手动选择文件路径
# 创建一个Tkinter根窗口并隐藏它
root = tk.Tk()
root.withdraw()

# 打开文件对话框选择文件路径
file_path = filedialog.askopenfilename(title="选择文件", filetypes=[("Text files", "*.TXT"), ("All files", "*.*")])

# # 文件路径
# file_path = r'C:\Users\G1006871\Desktop\V16测试.TXT'

# 获取当前时间并格式化为字符串
file_name = os.path.splitext(os.path.basename(file_path))[0]
current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
directory = 'D:/python脚本生成文件集/GAL100协议解析'
excel_filename = f'{directory}/{file_name}-{current_time}_V16.xlsx'

# 如果目录不存在，自动创建目录
if not os.path.exists(directory):
    os.makedirs(directory)

# 创建一个新的Excel工作簿
wb = Workbook()
light_grey_fill = PatternFill(start_color="c8c7c7", end_color="c8c7c7", fill_type="solid")
# 定义淡蓝色填充
ws = wb.active

# 定义浅灰色填充
light_blue_fill = PatternFill(start_color="6d9eeb", end_color="6d9eeb", fill_type="solid")
# 定义浅黄色填充
light_yellow_fill = PatternFill(start_color="f9ca9c", end_color="f9ca9c", fill_type="solid")
# 定义浅绿色填充
light_green_fill = PatternFill(start_color="b6d7a8", end_color="b6d7a8", fill_type="solid")
# 定义浅红色填充
light_red_fill = PatternFill(start_color="e99998", end_color="e99998", fill_type="solid")

# 合并单元格
ws.merge_cells('B1:E1')
ws.merge_cells('F1:I1')
ws.merge_cells('J1:R1')
ws.merge_cells('S1:AA1')
# 设置合并单元格的值

ws['B1'] = 'MESSAGE'  # 消息
ws['F1'] = 'DEVICE'   # 设备
ws['J1'] = 'QUALITY'  # 质量
ws['S1'] = 'LOCATION'  # 位置

# 设置固定值
ws['A2'] = 'RAW DATA'  # 原始数据
ws['B2'] = 'PACKET LENGTH'  # 数据包长度
ws['C2'] = 'PACKET VERSION'  # 数据包版本
ws['D2'] = "PACKET TYPE"  # 数据包类型
ws['E2'] = "SEQUENCE"  # 序列

ws['F2'] = "MANUFACTURER ID"  # 制造商ID
ws['G2'] = "SOFTWARE VERSION"  # 软件版本
ws['H2'] = "HARDWARE VERSION"  # 硬件版本
ws['I2'] = "DEVICE ID"  # 设备ID

ws['J2'] = "BATTERY %"  # 电池百分比
ws['K2'] = "ACTIVE TIME"  # 活动时间
ws['L2'] = "IMEI"  # IMEI
ws['M2'] = "CELL INFO (ECL)"  # 小区信息
ws['N2'] = "RSSI"  # RSSI
ws['O2'] = "RSRP"  # RSRP
ws['P2'] = "RSRQ"  # RSRQ
ws['Q2'] = "PLMN"  # PLMN
ws['R2'] = "AUX"  # 辅助

ws['S2'] = "GPS N/S"  # GPS N/S
ws['T2'] = "GPS LATITUDE"  # GPS 纬度
ws['U2'] = "GPS E/W"  # GPS E/W
ws['V2'] = "GPS LONGITUDE"  # GPS 经度
ws['W2'] = "GPS TIMESTAMP (YYYYMMDDHHMISS)"  # GPS 时间戳
ws['X2'] = "GPS ALTITUDE"  # GPS 高度
ws['Y2'] = "GPS HORIZ EPEL"  # GPS 水平精度
ws['Z2'] = "GPS SATELLITE COUNT"  # GPS 卫星数量
ws['AA2'] = "GPS HDOP"  # GPS HDOP


# 批量填充颜色的函数
def fill_cells(ws_state, cell_range, fill_color, font=None, alignment=None):
    for cell in cell_range:
        ws_state[cell].fill = fill_color
        if font:
            ws_state[cell].font = font
        if alignment:
            ws_state[cell].alignment = alignment


# 定义加粗字体
bold_font = Font(bold=True)
# 定义居中对齐
center_alignment = Alignment(horizontal="center", vertical="center")
# 批量填充颜色、
fill_cells(ws, ['A1', 'A2'], light_grey_fill, bold_font, center_alignment)
fill_cells(ws, ['B2', 'C2', 'D2', 'E2', 'B1'], light_blue_fill, bold_font, center_alignment)
fill_cells(ws, ['F2', 'G2', 'H2', 'I2', 'F1'], light_yellow_fill, bold_font, center_alignment)
fill_cells(ws, ['J2', 'K2', 'L2', 'M2', 'N2', 'O2', 'P2', 'Q2', 'R2', 'J1'], light_green_fill, bold_font, center_alignment)
fill_cells(ws, ['S2', 'T2', 'U2', 'V2', 'W2', 'X2', 'Y2', 'Z2', 'AA2', 'S1'], light_red_fill, bold_font, center_alignment)


# 调整列宽函数
def auto_adjust_column_width(ws_state, row_num):
    for col in range(1, ws_state.max_column + 1):
        cell = ws_state.cell(row=row_num, column=col)
        max_length = len(str(cell.value)) if cell.value else 0
        adjusted_width = (max_length + 2)
        ws_state.column_dimensions[get_column_letter(col)].width = adjusted_width

def remove_bracket_content(text):
    text = re.sub(r'\[.*?\]', '', text)
    return text.replace(' ', '')


# 调整第二行的列宽
auto_adjust_column_width(ws, 2)

# 打开文件并处理
with open(file_path, 'r', encoding='utf-8',  errors='ignore') as file:
    # errors='ignore' 会跳过错误字符
    # errors='replace' 会用 � 替换错误字符
    # 如果utf-8校验不过，可以换编码方式，如ISO-8859-1
    # 从第三行开始写入
    row = 3
    for line in file:
        # print(line)
        if "[TGAT]><-- UDP socket0 pack_len" in line or "udp_buff" in line:
            # 提取引号内的内容
            if "[TGAT]><-- UDP socket0 pack_len" in line:
                start_index = line.find('"') + 1
                end_index = line.find('"', start_index)
            else:
                udp_buff_index = line.find("udp_buff")
                start_index = line.find('[', udp_buff_index) + 1
                end_index = line.find(']', start_index)
            # 确保引号匹配
            if 0 < start_index < end_index:
                content = line[start_index:end_index]
                # print(content)
                content = remove_bracket_content(content)
                print(content)
                # 将内容写入Excel的A列
                ws.cell(row=row, column=1, value=content).fill = light_grey_fill
                # message
                ws.cell(row=row, column=2, value=content[0:3]).fill = light_blue_fill
                ws.cell(row=row, column=3, value=content[3:6]).fill = light_blue_fill
                ws.cell(row=row, column=4, value=content[6:7]).fill = light_blue_fill
                ws.cell(row=row, column=5, value=content[7:10]).fill = light_blue_fill
                # device
                ws.cell(row=row, column=6, value=content[10:14]).fill = light_yellow_fill
                ws.cell(row=row, column=7, value=content[14:16]).fill = light_yellow_fill
                ws.cell(row=row, column=8, value=content[16:18]).fill = light_yellow_fill
                ws.cell(row=row, column=9, value=content[18:26]).fill = light_yellow_fill
                # quality
                ws.cell(row=row, column=10, value=content[26:28]).fill = light_green_fill
                ws.cell(row=row, column=11, value=content[28:31]).fill = light_green_fill
                ws.cell(row=row, column=12, value=content[31:46]).fill = light_green_fill
                ws.cell(row=row, column=13, value=content[46:54]).fill = light_green_fill
                ws.cell(row=row, column=14, value=content[54:58]).fill = light_green_fill
                ws.cell(row=row, column=15, value=content[58:62]).fill = light_green_fill
                ws.cell(row=row, column=16, value=content[62:66]).fill = light_green_fill
                ws.cell(row=row, column=17, value=content[66:72]).fill = light_green_fill
                ws.cell(row=row, column=18, value=content[72:77]).fill = light_green_fill
                # location
                value = content[77:78]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=19, value=value).fill = light_red_fill
                value = content[78:87]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=20, value=value).fill = light_red_fill
                value = content[87:88]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=21, value=value).fill = light_red_fill
                value = content[88:98]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=22, value=value).fill = light_red_fill
                value = content[98:112]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=23, value=value).fill = light_red_fill
                value = content[112:116]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=24, value=value).fill = light_red_fill
                value = content[116:118]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=25, value=value).fill = light_red_fill
                value = content[118:120]
                if not value:
                    value = "NULL"
# 打开本地文件夹
                ws.cell(row=row, column=26, value=value).fill = light_red_fill
                value = content[120:125]
                if not value:
                    value = "NULL"
                ws.cell(row=row, column=27, value=value).fill = light_red_fill
                row += 1
print("处理成功")
wb.save(excel_filename)

os.startfile(directory)
