import tkinter as tk
from tkinter import messagebox, scrolledtext
import requests
import time
import os
import json
from datetime import datetime, timedelta, timezone
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Alignment
from openpyxl.styles import GradientFill
# from openpyxl.utils import get_column_letter
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties
from openpyxl.styles import Font


# 你的主函数，接受一个 IMEI 列表
def main(imei_num_list: list[str], start_time: str, stop_time: str):
    # 替换为你原来的逻辑
    #
    #
    # run_start_time = time.time()
    # imei_num_list = [869595060730669, 869595060743324, 869595060743357, 869595060742987, 869595060728317,
    #                  869595060730602,
    #                  869595060728358, 869595060747911, 869595060743795, 869595060743977]
    # start_time = "2025-05-19 01:00:00"  # unix时间 对应北京 +8小时 8:00
    # stop_time = "2025-05-20 01:00:00"  # unix时间 对应北京 +8小时 9:00

    file_path = 'C:/SENSOR-专项测试/数据检查/'
    os.makedirs(file_path, exist_ok=True)
    current_time = datetime.now().strftime('%Y%m%d_%H%M%S')

    start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    stop_dt = datetime.strptime(stop_time, "%Y-%m-%d %H:%M:%S")

    start_timestamp = int(start_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    stop_timestamp = int(stop_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

    def convert_to_beijing_time(timestamp):
        dt_utc = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        dt_beijing = dt_utc + timedelta(hours=8)
        return dt_beijing.strftime('%Y-%m-%d %H:%M:%S')

    print(start_timestamp, stop_timestamp)

    start_time_beijing = convert_to_beijing_time(start_timestamp)
    stop_time_beijing = convert_to_beijing_time(stop_timestamp)

    data_request_time = f"数据开始时间:{start_time_beijing}", f"数据结束时间: {stop_time_beijing}"

    wb = Workbook()
    ws = wb.active

    blue_fill = PatternFill(start_color="6d9eeb", end_color="6d9eeb", fill_type="solid")

    light_yellow_fill = PatternFill(start_color="f9ca9c", end_color="f9ca9c", fill_type="solid")

    headers = ['基本信息', '最后一包数据', '急加速', '急减速', '急转弯', '疑似碰撞', '休眠时间', '唤醒时间',
               '点火时间', '熄火时间', 'SENSOR自学习状态', '备注', '行程统计', '自学习次数', '学习成功率', '行驶里程',
               '重启事件']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = blue_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    def hex_to_beijing_time(hex_str):
        timestamp = int(hex_str, 16)
        utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        beijing_time = utc_time + timedelta(hours=8)
        return beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    def server_get_data(imei_num_list, start_timestamp, stop_timestamp):
        global output_file
        row_num = 2
        imei_data = {}
        total_valid_event_count = 0
        total_self_learning_event_count = 0
        abnormal_mileage_count = 0
        for imei_num in imei_num_list:
            url_set_dat = "http://10.85.40.3:8082/testAPI/rawData"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer YOUR_ACCESS_TOKEN'
            }
            print("IMEI号:", imei_num)
            raw_data_string = []
            offset = 0
            limit = 1000

            while True:
                body_data = {
                    'imei': imei_num,
                    'start': start_timestamp,
                    'stop': stop_timestamp,
                    'offset': offset,
                    'limit': limit
                }
                try:
                    response_raw_data = requests.post(url_set_dat, headers=headers, json=body_data)
                    if response_raw_data.status_code == 200:
                        raw_data = response_raw_data.json()
                        raw_data_string_2 = [entry["rawDataString"] for entry in raw_data]
                        raw_data_count = len(raw_data_string_2)
                        raw_data_string.extend(raw_data_string_2)
                        print(f"单次请求数据数: {raw_data_count}", "offset", offset)
                        if raw_data_count < limit:
                            break
                        else:
                            offset += 1000
                    else:
                        print('请求失败:', response_raw_data.status_code, response_raw_data.text)
                        break
                except requests.exceptions.RequestException as e:
                    print('请求过程中出现错误:', e)
                    break

            raw_data_count_all = len(raw_data_string)
            print(f"总数据的个数: {len(raw_data_string)}")

            software_version_printed = False

            software_version_ascii_report = "未获取到版本号"

            for line in raw_data_string:
                if line[48:50] == "01" and not software_version_printed:
                    software_version_len = line[62:64]
                    software_version_len_int = int(software_version_len, 16)
                    software_version_len_bin = bin(software_version_len_int)[2:].zfill(8)
                    software_version_len_dec = int(software_version_len_bin[-6:], 2)
                    software_version = line[64:(64 + software_version_len_dec * 2)]
                    software_version_bytes = bytes.fromhex(software_version)
                    software_version_ascii = software_version_bytes.decode('ascii')
                    software_version_ascii_report = software_version_ascii

            if raw_data_string:
                last_event_data = raw_data_string[-1]
                if last_event_data[48:50] == "0e":
                    last_event_time = hex_to_beijing_time(last_event_data[58:66])
                    last_event_data_report = f"最后一包数据-disconnect帧，时间:\n{last_event_time}"
                elif last_event_data[48:50] == "03" and last_event_data[58:62] == "04f0":
                    last_event_time = hex_to_beijing_time(last_event_data[62:70])
                    last_event_data_report = f"最后一包数据-SENSOR帧，时间:\n{last_event_time}"
                elif last_event_data[48:50] == "03" and last_event_data[58:62] == "0200":
                    last_event_time = hex_to_beijing_time(last_event_data[64:72])
                    last_event_data_report = f"最后一包数据-GPS帧，时间:\n{last_event_time}"
                elif last_event_data[48:50] == "03" and last_event_data[58:62] == "0402":
                    last_event_time = hex_to_beijing_time(last_event_data[62:70])
                    last_event_data_report = f"最后一包数据-休眠帧，时间:\n{last_event_time}"
                else:
                    last_event_data_report = f"最后一包数据原始数据:\n{last_event_data}"
            else:
                last_event_data_report = "未获取到原始数据"

            ignition_event_times = []
            ignition_event_times_1 = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0001":
                    ignition_event_times.append(hex_to_beijing_time(line[64:72]))
                    if line[62:64] == "04":
                        ignition_type = "GPS"
                    elif line[62:64] == "05":
                        ignition_type = "SENSOR"
                    else:
                        ignition_type = line[62:64]
                    ignition_event_times_1.append(hex_to_beijing_time(line[64:72]) + " - 类型：" + ignition_type)

            if ignition_event_times_1:
                ignon_event_time_report = "点火时间:\n" + "\n".join(ignition_event_times_1)
            else:
                ignon_event_time_report = "无点火事件"

            # 熄火事件
            extinguish_event_times = []
            extinguish_event_times_1 = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0002":
                    extinguish_event_times.append(hex_to_beijing_time(line[64:72]))
                    if line[62:64] == "08":
                        extinguish_type = "GPS"
                    elif line[62:64] == "09":
                        extinguish_type = "SENSOR"
                    elif line[62:64] == "0d":
                        extinguish_type = "Ready"
                    elif line[62:64] == "0b":
                        extinguish_type = "拔出"
                    else:
                        extinguish_type = line[62:64]
                    extinguish_event_times_1.append(hex_to_beijing_time(line[64:72]) + " - 类型：" + extinguish_type)

            if extinguish_event_times_1:
                ignoff_event_time_report = "熄火时间:\n" + "\n".join(extinguish_event_times_1)
            else:
                ignoff_event_time_report = "无熄火事件"

            sleep_event_times = []
            sleep_event_times_1 = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0402":
                    sleep_voltage = int(line[70:74], 16) / 10

                    sleep_event_times.append(hex_to_beijing_time(line[62:70]))
                    sleep_event_times_1.append(hex_to_beijing_time(line[62:70]) + ' - 电压：' + str(sleep_voltage) + "V")

            if sleep_event_times_1:
                sleep_event_time_report = "休眠时间:\n" + "\n".join(sleep_event_times_1)
            else:
                sleep_event_time_report = "无休眠事件"

            wakeup_event_times = []
            wakeup_event_times_1 = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0403":
                    wakeup_event_times.append(hex_to_beijing_time(line[62:70]))
                    wakeup_voltage = int(line[70:74], 16) / 10
                    if line[74:76] == "00":
                        wakeup_type = "定时唤醒"
                    elif line[74:76] == "03":
                        wakeup_type = "电压唤醒"
                    elif line[74:76] == "05":
                        wakeup_type = "震动唤醒"
                    elif line[74:76] == "06":
                        wakeup_type = "低电唤醒"
                    else:
                        wakeup_type = line[74:76]
                    wakeup_event_times_1.append(hex_to_beijing_time(line[62:70]) + "--" + wakeup_type
                                                + "-" + str(wakeup_voltage) + "V")
            if wakeup_event_times_1:
                wakeup_event_time_report = "唤醒时间:\n" + "\n".join(wakeup_event_times_1)
            else:
                wakeup_event_time_report = "无唤醒事件"

            # 重启记录
            reboot_event_times = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0405":
                    if line[78:80] == "00":
                        type_power_on = "normal"
                    elif line[78:80] == "01":
                        type_power_on = "software dog"
                    elif line[78:80] == "02":
                        type_power_on = "upgrade"
                    elif line[78:80] == "02":
                        type_power_on = "key"
                    elif line[78:80] == "0a":
                        type_power_on = "5th sleep"
                    elif line[78:80] == "0d":
                        type_power_on = "7 day"
                    elif line[78:80] == "0f":
                        type_power_on = "AT ERROR"
                    else:
                        type_power_on = line[78:80]

                    reboot_event_times.append(hex_to_beijing_time(line[62:70]) + " - " + type_power_on)

            if reboot_event_times:
                reboot_event_times_report = "重启时间:\n" + "\n".join(reboot_event_times)
            else:
                reboot_event_times_report = "无重启事件"

            sensor_acc_event_times = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0100":
                    sensor_acc_event_times.append(hex_to_beijing_time(line[62:70]))
            if sensor_acc_event_times:
                sensor_acc_event_time_report = "急加速时间:\n" + "\n".join(sensor_acc_event_times)
            else:
                sensor_acc_event_time_report = "无急加速事件"

            sensor_dec_event_times = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0101":
                    sensor_dec_event_times.append(hex_to_beijing_time(line[62:70]))
            if sensor_dec_event_times:
                sensor_dec_event_time_report = "急减速时间:\n" + "\n".join(sensor_dec_event_times)
            else:
                sensor_dec_event_time_report = "无急减速事件"

            sensor_turn_event_times = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0102":
                    sensor_turn_event_times.append(hex_to_beijing_time(line[62:70]))
            if sensor_turn_event_times:
                sensor_turn_event_time_report = "急转弯时间:\n" + "\n".join(sensor_turn_event_times)
            else:
                sensor_turn_event_time_report = "无急转弯事件"

            sensor_collision_event_times = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0505":
                    sensor_collision_event_times.append(hex_to_beijing_time(line[62:70]))
            if sensor_collision_event_times:
                sensor_collision_event_time_report = "疑似碰撞时间:\n" + "\n".join(sensor_collision_event_times)
            else:
                sensor_collision_event_time_report = "无疑似碰撞事件"

            last_gps_event_time = None
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0200":
                    last_gps_event_time = hex_to_beijing_time(line[64:72])
            if last_gps_event_time:
                last_gps_event_time_report = last_gps_event_time
            else:
                last_gps_event_time_report = f"无GPS事件"

            self_learning_event_count = 0
            self_learning_event_times = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0407":
                    self_learning_event_times.append(hex_to_beijing_time(line[62:70]))
                    self_learning_event_count += 1
            if self_learning_event_times:
                self_learning_event_time_report = "自学习事件:\n" + "\n".join(self_learning_event_times)
            else:
                self_learning_event_time_report = "无自学习事件上报"

            driving_distance_list = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0000":
                    driving_distance_bin = bin(int(line[174:180], 16))[2:]
                    source = driving_distance_bin[0]
                    mileage = int(driving_distance_bin[-23:], 2)

                    source_type = "OBD--" if source == "0" else "GPS--"
                    driving_distance = f"{source_type}{mileage}m"
                    driving_distance_list.append(driving_distance)

                    if mileage == 8388607:
                        abnormal_mileage_count += 1
            if driving_distance_list:
                driving_distance_report = "\n".join(driving_distance_list)
            else:
                driving_distance_report = "无行程里程"

            valid_count = 0
            invalid_count = 0
            trip_summary_event_num_reprot = []
            for line in raw_data_string:
                if line[48:50] == "03" and line[58:62] == "0000":
                    lgnition_time = hex_to_beijing_time(line[62:70])
                    lgnitioff_time = hex_to_beijing_time(line[118:126])
                    lgnition_dt = datetime.strptime(lgnition_time, "%Y-%m-%d %H:%M:%S")
                    lgnitioff_dt = datetime.strptime(lgnitioff_time, "%Y-%m-%d %H:%M:%S")
                    time_difference = lgnitioff_dt - lgnition_dt
                    if time_difference > timedelta(minutes=5):
                        valid_count += 1
                    else:
                        invalid_count += 1
            if valid_count > 0 or invalid_count > 0:
                trip_summary_event_num_reprot = (
                    f"有效行程:{valid_count}次\n无效行程:{invalid_count}次\n\n备注：只判断Trip summary"
                    f"，大于5分钟算有效行程")
            else:
                trip_summary_event_num_reprot = "无有效行程"

            # 计算单体设备自学习成功率
            if valid_count > 0:
                self_learning_success_rate = (self_learning_event_count / valid_count) * 100
            else:
                self_learning_success_rate = 0

            total_valid_event_count += valid_count
            total_self_learning_event_count += self_learning_event_count

            if total_valid_event_count > 0:
                total_self_learning_success_rate = (total_self_learning_event_count / total_valid_event_count) * 100
            else:
                total_self_learning_success_rate = 0
            ws['L3'] = (
                f"总体自学习成功率: {total_self_learning_success_rate:.2f}%, "
                "\n计算方法:数据采集时间段内自学习成功次数除以大于5分钟行程的Trip summary次数"
            )

            end_color = "ffffff"  # White
            start_color = "00ff00"  # Green

            gradient_fill = GradientFill(stop=(start_color, end_color))
            ws['L3'].fill = gradient_fill

            base_information = [(str(imei_num), f"软件版本:\n{software_version_ascii_report}",
                                 f"获取数据:\"{raw_data_count_all}\"条")]
            base_information_str = "\n".join([f"{info[0]} \n{info[1]} \n{info[2]}" for info in base_information])

            last_gps_and_last_event = [(f"最后一包GPS时间:\n{last_gps_event_time_report}", last_event_data_report)]
            last_gps_and_last_event_str = "\n".join([f"{info[0]} \n{info[1]}" for info in last_gps_and_last_event])

            ws.cell(row=row_num, column=1, value=base_information_str)
            ws.cell(row=row_num, column=2, value=last_gps_and_last_event_str)
            ws.cell(row=row_num, column=3, value=sensor_acc_event_time_report)
            ws.cell(row=row_num, column=4, value=sensor_dec_event_time_report)
            ws.cell(row=row_num, column=5, value=sensor_turn_event_time_report)
            ws.cell(row=row_num, column=6, value=sensor_collision_event_time_report)
            ws.cell(row=row_num, column=7, value=sleep_event_time_report)
            ws.cell(row=row_num, column=8, value=wakeup_event_time_report)
            ws.cell(row=row_num, column=9, value=ignon_event_time_report)
            ws.cell(row=row_num, column=10, value=ignoff_event_time_report)
            ws.cell(row=row_num, column=11, value=self_learning_event_time_report)
            # 11列K2被采集数据时间统计占用
            ws.cell(row=row_num, column=13, value=trip_summary_event_num_reprot)
            ws.cell(row=row_num, column=14, value=self_learning_event_count)
            ws.cell(row=row_num, column=15, value=f"{self_learning_success_rate:.2f}%")
            ws.cell(row=row_num, column=16, value=driving_distance_report)
            ws.cell(row=row_num, column=17, value=reboot_event_times_report)

            row_num += 1

            # ↓↓↓生成图片↓↓↓
            imei_data[imei_num] = {
                'ignition_event_times': ignition_event_times,
                'extinguish_event_times': extinguish_event_times,
                'sleep_event_times': sleep_event_times,
                'wakeup_event_times': wakeup_event_times,
                'self_learning_event_times': self_learning_event_times
            }

            def add_hours_to_events(events, hours):
                return [datetime.strptime(event, '%Y-%m-%d %H:%M:%S') + timedelta(hours=hours) for event in events]

            # def plot_imei_events(imei_data, start_time_beijing, stop_time_beijing, output_file):
            #     fig, ax = plt.subplots(figsize=(20, 6))
            #
            #     time_format = mdates.DateFormatter('%H:%M')
            #     ax.xaxis.set_major_formatter(time_format)
            #     ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
            #
            #     start_dt = datetime.strptime(start_time_beijing, '%Y-%m-%d %H:%M:%S')
            #     stop_dt = datetime.strptime(stop_time_beijing, '%Y-%m-%d %H:%M:%S')
            #
            #     for i, (imei, events) in enumerate(imei_data.items()):
            #         y_pos = i * 2
            #         ax.text(mdates.date2num(start_dt), y_pos, imei, verticalalignment='center')
            #
            #         # 加0小时
            #         ignition_event_times_1 = add_hours_to_events(events['ignition_event_times'], 0)
            #         extinguish_event_times_1 = add_hours_to_events(events['extinguish_event_times'], 0)
            #         sleep_event_times_1 = add_hours_to_events(events['sleep_event_times'], 0)
            #         wakeup_event_times_1 = add_hours_to_events(events['wakeup_event_times'], 0)
            #         self_learning_event_times_1 = add_hours_to_events(events['self_learning_event_times'], 0)
            #
            #         colors = ['red', 'blue', 'green', 'orange']
            #
            #         color = colors[(i // 1) % len(colors)]
            #         ax.hlines(y_pos + 0.5, mdates.date2num(start_dt), mdates.date2num(stop_dt), colors=color,
            #                   linestyles='dotted')
            #         ax.hlines(y_pos - 0.5, mdates.date2num(start_dt), mdates.date2num(stop_dt), colors=color,
            #                   linestyles='dotted')
            #
            #     font = FontProperties(fname='C:/Windows/Fonts/simhei.ttf')
            #
            #     ax.set_yticks([])
            #     ax.set_title('事件发生时间轴', fontproperties=font)
            #
            #     ax.set_xlabel('时间轴-北京时间', fontproperties=font)
            #
            #     fig.text(0.045, 0.02, "数据采集时间:", color='grey', fontproperties=font, ha='center')
            #     fig.text(0.1, 0.02, start_time_beijing, color='grey', fontproperties=font, ha='center')
            #     fig.text(0.14, 0.02, "→", color='grey', fontproperties=font, ha='center')
            #     fig.text(0.18, 0.02, stop_time_beijing, color='grey', fontproperties=font, ha='center')
            #
            #     fig.text(0.75, 0.02, '●点火事件  ', color='green', fontproperties=font, ha='center')
            #     fig.text(0.8, 0.02, '●熄火事件  ', color='red', fontproperties=font, ha='center')
            #     fig.text(0.85, 0.02, '★自学习事件', color='orange', fontproperties=font, ha='center')
            #     fig.text(0.91, 0.02, '●休眠事件  ', color='black', fontproperties=font, ha='center')
            #     fig.text(0.96, 0.02, '●唤醒事件', color='blue', fontproperties=font, ha='center')
            #
            #     plt.tight_layout()
            #     plt.savefig(output_file)
            #     plt.close()
            #
            # output_file = f'{file_path}sensor_photo_{current_time}.png'
            # plot_imei_events(imei_data, start_time_beijing, stop_time_beijing, output_file)

        ws['L4'] = f"行程异常次数 {abnormal_mileage_count} 次 \n\n统计行程8388607米出现的次数"
        if abnormal_mileage_count != 0:
            ws['L4'].font = Font(color="FF0000")  # Red color in hex

        json_file_path = f'{file_path}imei_data_{current_time}.json'
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(imei_data, json_file, ensure_ascii=False, indent=4)
        print("JSON 文件保存路径:", json_file_path)

    print("↓↓↓生成EXCEL文件↓↓↓")
    server_get_data(imei_num_list, start_timestamp, stop_timestamp)

    # 数据请求时间填写到L2列
    ws['L2'] = f"{data_request_time[0]}\n{data_request_time[1]}"
    ws['L2'].fill = light_yellow_fill
    # 调整列宽,定义要调整的列
    columns_to_adjust_5cm = ['A', 'B', 'C', 'D', 'E', 'F', 'K', 'L']
    columns_to_adjust_10cm = ['G', 'H', 'I', 'J']
    columns_to_adjust_3cm = ['M', 'N', 'O', 'P', 'Q']
    # 将每个指定列的宽度设置为5厘米
    for column in columns_to_adjust_5cm:
        ws.column_dimensions[column].width = 5 * 10 / 2.54
    for column in columns_to_adjust_10cm:
        ws.column_dimensions[column].width = 9.5 * 10 / 2.54
    for column in columns_to_adjust_3cm:
        ws.column_dimensions[column].width = 3 * 10 / 2.54

    red_font = Font(color="FF0000")
    blue_font = Font(color="4450FC")

    reboot_event_tag = 0

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True)
            cell.alignment = Alignment(wrap_text=True, vertical='center', horizontal='left')
            if (cell.value and isinstance(cell.value, str) and
                    ("未获取到原始数据" in cell.value
                     or "未获取到版本号" in cell.value
                     or "无GPS事件" in cell.value
                     or "8388607m" in cell.value)):
                cell.font = red_font
            elif (cell.value and isinstance(cell.value, str) and
                  ("无急加速事件" in cell.value
                   or "无急减速事件" in cell.value
                   or "无急转弯事件" in cell.value
                   or "无疑似碰撞事件" in cell.value)):
                cell.font = blue_font
            elif (cell.value and isinstance(cell.value, str) and
                  "重启时间" in cell.value):
                reboot_event_tag += 1
                cell.font = red_font

    ws['L5'] = f"重启设备个数: {reboot_event_tag}次"
    if reboot_event_tag != 0:
        ws['L5'].font = Font(color="FF0000")  # Red color in hex

    # 保存工作簿
    filename = f'{file_path}sensor_{current_time}.xlsx'
    print("文件保存路径:", filename)
    wb.save(filename)

    run_end_time = time.time()
    # elapsed_time = run_end_time - run_start_time
    # print(f"程序运行耗时: {elapsed_time:.2f} 秒")

    # 打开本地文件夹
    os.startfile(file_path)



    # print(f"处理 {len(imei_list)} 个 IMEI")
    # print(f"开始时间: {start_time}")
    # print(f"结束时间: {end_time}")
    # print("IMEI 列表:", imei_list)

# 包装 GUI 界面
def create_gui():
    window = tk.Tk()
    window.title("SENSOR专项-服务器获取数据-木林夕")
    window.geometry("500x400")

    # IMEI 列表输入框
    tk.Label(window, text="IMEI 列表（每行一个）:").pack(pady=(10, 0))
    imei_text = scrolledtext.ScrolledText(window, width=60, height=10)
    imei_text.pack(pady=5)

    # 开始时间
    tk.Label(window, text="开始时间-输入无时区时间 (YYYY-MM-DD):").pack()
    start_entry = tk.Entry(window, width=30)
    start_entry.insert(0, "2025-05-19 01:00:00")  # 设置默认值
    start_entry.pack(pady=2)

    # 结束时间
    tk.Label(window, text="结束时间-输入无时区时间 (YYYY-MM-DD):").pack()
    end_entry = tk.Entry(window, width=30)
    end_entry.insert(0, "2025-05-20 01:00:00")  # 设置默认值
    end_entry.pack(pady=2)

    # 点击按钮逻辑
    def on_submit():
        imei_list_raw = imei_text.get("1.0", tk.END).strip()
        imeis = [line.strip() for line in imei_list_raw.splitlines() if line.strip()]
        start_time = start_entry.get().strip()
        end_time = end_entry.get().strip()

        if not imeis or not start_time or not end_time:
            messagebox.showerror("错误", "请填写所有字段！")
            return

        try:
            main(imeis, start_time, end_time)
            messagebox.showinfo("完成", f"已成功处理 {len(imeis)} 个 IMEI。")
        except Exception as e:
            messagebox.showerror("执行出错", str(e))

    # 提交按钮
    tk.Button(window, text="运行程序", command=on_submit, bg="green", fg="white").pack(pady=20)

    window.mainloop()

if __name__ == "__main__":
    create_gui()
