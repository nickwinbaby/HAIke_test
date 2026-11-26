import os
import re
import pandas as pd
import requests
from PyQt5.QtWidgets import QFileDialog


def export_to_excel(self):
    text = self.raw_data_display.toPlainText()
    if not text.strip():
        self.result_label.setText("没有数据可导出")
        return

    # 按行分割文本
    lines = text.strip().split('\n')
    if not lines or len(lines) < 2:
        self.result_label.setText("数据不足，无法导出")
        return

    # 解析表头
    headers = re.split(r'\s{2,}', lines[0].strip())
    data_rows = []
    skipped_lines = []

    # 解析每一行数据
    for i, line in enumerate(lines[1:], start=2):
        row = re.split(r'\s{2,}', line.strip())
        if len(row) != len(headers):
            skipped_lines.append(i)
            print(f"⚠️ 第{i}行列数不匹配（{len(row)}列，应为{len(headers)}列）: {row}")
            continue
        data_rows.append(row)

    if not data_rows:
        self.result_label.setText("所有数据行格式异常，导出失败")
        return

    # 创建 DataFrame
    df = pd.DataFrame(data_rows, columns=headers)

    # 选择保存路径
    file_path, _ = QFileDialog.getSaveFileName(self, "保存 Excel 文件", "", "Excel 文件 (*.xlsx)")
    if file_path:
        try:
            df.to_excel(file_path, index=False)
            if skipped_lines:
                self.result_label.setText(f"导出成功: {file_path}（跳过 {len(skipped_lines)} 行格式错误）")
            else:
                self.result_label.setText(f"导出成功: {file_path}")

            # 打开文件所在的文件夹
            file_path_start = os.path.dirname(file_path)  # 获取文件夹路径
            os.startfile(file_path_start)

        except Exception as e:
            self.result_label.setText(f"导出失败: {str(e)}")


def server_get_data(self, imei_num_list, start_timestamp, stop_timestamp):
    all_raw_data_string = []
    self.result_label.setText("Fetching data... Please wait.")
    self.raw_data_display.clear()

    for imei_num in imei_num_list:
        url = "http://10.85.40.3:8082/testAPI/rawData"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer YOUR_ACCESS_TOKEN'  # Replace this with actual token
        }

        offset = 0
        limit = 1000
        while True:
            payload = {
                'imei': imei_num,
                'start': start_timestamp,
                'stop': stop_timestamp,
                'offset': offset,
                'limit': limit
            }

            try:
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    batch = response.json()
                    lines = [entry["rawDataString"] for entry in batch]
                    all_raw_data_string.extend(lines)
                    if len(lines) < limit:
                        break
                    offset += limit
                else:
                    print("Request failed:", response.status_code, response.text)
                    break
            except requests.exceptions.RequestException as e:
                print("Request error:", e)
                break

    return all_raw_data_string

# ══════════════════════ RAW DATA ════════════════════════
