from parsers_common import *


def display_raw_data(self, data):
    self.result_label.setText(f"Total raw lines: {len(data)}")
    self.raw_data_display.setText("\n".join(data[:1000]))

def display_protocol_consistency(self, raw_data_string):
    """
    协议一致性检测：
    1. 解析基础字段
    2. 校验消息长度
    3. 使用 Adler32 校验 checksum
    4. 比对原始 FF 补位和计算补位是否一致
    """
    headers = [
        f"{'消息长度':<8}",
        f"{'协议版本':<10}",
        f"{'加密方式':<14}",
        f"{'电池电量':<8}",
        f"{'帧类型':<7}",
        f"{'帧序号':<7}",
        f"{'有效长度':<6}",
        f"{'数据类型':<26}",
        f"{'长度校验':<6}",
        f"{'checksum校验':<12}",
        f"{'FF补位校验':<8}",
    ]

    result_lines = ["".join(headers)]

    # 帧类型映射
    frame_type_map = {
        "01": "CONNECT",
        "02": "CONNACK",
        "03": "PUBLISH",
        "04": "PUBACK",
        "05": "PUBLISH_NOACK",
        "0C": "PINGREQ",
        "0D": "PINGRESP",
        "0E": "DISCONNECT"
    }

    # 协议码映射：key为协议码，value为显示名称
    protocol_code_map = {
        "0000": "trip summary",
        "0001": "Ignition on",
        "0002": "Ignition off",
        "0003": "trip start",
        "0004": "trip end",

        "0100": "Sudden acc",
        "0101": "Sudden dec",
        "0102": "Sharp turn",
        "0103": "Exceed idle",
        "0104": "Driving tired",
        "0105": "Over speed",
        "0107": "Sudden Lane Change",

        "0200": "GPS data",
        "0201": "LBS data",

        "0300": "VIN Cold",
        "0301": "Data flow",
        "0304": "CAN parameter support status",
        "0305": "Raw can frame",
        "0306": "Config data flow",
        "0307": "Vehicle Information KLV",

        "0500": "DTC code",
        "0501": "Battery low",
        "0502": "Vibration event",
        "0505": "Suspected collision",
        "0507": "Unplug warning",
        "050B": "Jamming detection",
        "050C": "Device tamper warning",
        "050D": "Temperature warning",
        "050E": "Air pressure warning",
        "050F": "Shock warning",
        "0511": "Humidity warning",
        "0512": "Device warning message",
        "0513": "Fence warning",

        "0402": "Sleep state",
        "0403": "Wakeup state",
        "0404": "GPS not fix",
        "0405": "Reboot event",
        "0406": "Mcu upgrade state",
        "040B": "SMS",
        "040C": "Device info",
        "040D": "Sensor normal",
        "040E": "Sensor event",
        "0414": "Relay control status",
        "0407": "Self learning status",

        "F001": "Request MCU update package",
        "F002": "Request AGPS data",
        "F003": "MCU Update package verification",
        "F004": "MCU Log Report",
        "F005": "Check new update package",
        "F006": "Response to the New Update Package",

        "F102": "Set parameters",
        "F103": "Inquiry parameters",
        "F10C": "whitelist management",
        "F10D": "whitelist query",
        "F10F": "Management fence device response",
        "F110": "Query fence device response",

        "0601": "Ibutton id",
        "0602": "Ble sensor data",
        "0603": "Rs485 temperature humidity",
        "0604": "Ble sensor warning",
        "0605": "Rfid data",
        "0607": "Ble tag",
    }

    for line in raw_data_string:
        try:
            line = line.replace(" ", "").upper()

            if len(line) < 62:
                result_lines.append(f"{'数据过短':<12}{line}")
                continue

            # 消息总长度
            msg_length = int(line[4:8], 16)
            actual_length = len(line) // 2
            length_check_result = "PASS" if msg_length == actual_length else f"FAILFAIL({actual_length})"

            # 协议版本
            protocol_version_hex = line[8:12]
            byte1 = int(protocol_version_hex[0:2], 16)
            byte2 = int(protocol_version_hex[2:4], 16)

            major_version = (byte1 >> 4) & 0x0F
            minor_version = byte1 & 0x0F
            revision_version = byte2 & 0x3F
            protocol_version = f"V{major_version}.{minor_version}.{revision_version}"

            # 加密方式
            encryption_type = line[12:14].upper()
            encryption_map = {
                "00": "DES-3 ECB",
                "01": "AES-128 ECB",
                "02": "AES-256 ECB",
                "03": "AES-256 CBC",
                "FF": "Without Encryption"
            }
            encryption_algorithm = encryption_map.get(encryption_type, f"Unknown({encryption_type})")

            # 电池电量
            battery_level_hex = line[16:18].upper()
            if battery_level_hex == "FF":
                battery_level = "Not support"
            else:
                battery_level = f"{int(battery_level_hex, 16)}%"

            # 帧类型
            frame_type = line[48:50].upper()
            frame_type_name = frame_type_map.get(frame_type, f"Unknown({frame_type})")

            # 帧序号
            frame_num = line[50:54].upper()

            # 有效数据长度
            effective_data_length = int(line[54:58], 16)

            # 数据类型显示
            data_type_display = frame_type_name

            if frame_type in ["03", "04"]:
                data_type = line[58:62].upper()
                data_type_name = protocol_code_map.get(data_type, f"Unknown({data_type})")
                data_type_display = data_type_name

            # 参与 Adler32 校验的数据
            encrypted_data = line[4:58 + effective_data_length * 2]

            checksum_start = len(encrypted_data) + 4
            checksum = line[checksum_start:checksum_start + 8].upper()

            # 原始FF补位
            raw_data_ff = line[checksum_start + 8:-4].upper()

            # 计算 Adler32
            calc_checksum = adler32(bytes.fromhex(encrypted_data)) & 0xFFFFFFFF
            calc_checksum_hex = f"{calc_checksum:08X}"

            checksum_result = "PASS" if checksum == calc_checksum_hex else f"FAILFAIL({calc_checksum_hex})"

            # 计算 FF 补位
            need_encrypt_data = line[48:58 + effective_data_length * 2 + 8]
            need_encrypt_data_len = len(need_encrypt_data)

            padding_hex = ""
            remainder = need_encrypt_data_len % 32

            if remainder != 0:
                padding_len = 32 - remainder
                padding_hex = "FF" * (padding_len // 2)

            ff_result = "PASS" if raw_data_ff == padding_hex else f"FAILFAIL({padding_hex})"

            row = [
                f"{msg_length:<12}",
                f"{protocol_version:<14}",
                f"{encryption_algorithm:<18}",
                f"{battery_level:<12}",
                f"{frame_type:<10}",
                f"{frame_num:<10}",
                f"{effective_data_length:<10}",
                f"{data_type_display:<30}",
                f"{length_check_result:<10}",
                f"{checksum_result:<14}",
                f"{ff_result:<12}",
            ]

            result_lines.append("".join(row))

        except Exception as e:
            result_lines.append(f"{'解析异常':<12}{str(e):<30}{line}")

    self.result_label.setText(f"共检测 {len(raw_data_string)} 条协议数据")
    self.raw_data_display.setText("\n".join(result_lines[:1000]))

# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第零章：万始花香总盛开，一切虚无零落尽 —— 开天
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════
# connect 帧
def process_connect_data(self, raw_data_string):
    headers = []
    if self.connect_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.connect_time_checkbox.isChecked():
        headers.append(f"{'时间':<20}")
    if self.connect_hardware_version_checkbox.isChecked():
        headers.append(f"{'硬件版本':<16}")
    if self.connect_mcu_ap_version_checkbox.isChecked():
        headers.append(f"{'MCU/AP版本':<30}")
    if self.connect_mdm_version_checkbox.isChecked():
        headers.append(f"{'MDM版本':<30}")
    if self.connect_cfg_version_checkbox.isChecked():
        headers.append(f"{'配置版本':<10}")
    if self.connect_support_status_fota_checkbox.isChecked():
        headers.append(f"{'支持FOTA':<20}")
    if self.connect_ap_version_checkbox.isChecked():
        headers.append(f"{'AP版本':<30}")
    if self.connect_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    connect_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50].upper() == "01":
            imei = ascii_to_decimal(line[18:48])
            hardware_version = line[58:62]

            offset = 62

            # === 1. MCU AP Version ===
            mcu_ap_version_num = int(line[offset:offset + 2], 16)
            offset += 2  # 偏移后移 2 位

            if mcu_ap_version_num != 0:
                mcu_ap_version = ascii_to_decimal(line[offset:offset + mcu_ap_version_num * 2])
                offset += mcu_ap_version_num * 2  # 继续后移
            else:
                mcu_ap_version = "N/A"

            # === 2. MDM Version ===
            mdm_version_num = int(line[offset:offset + 2], 16)
            offset += 2

            if mdm_version_num != 0:
                mdm_version = ascii_to_decimal(line[offset:offset + mdm_version_num * 2])
                offset += mdm_version_num * 2
            else:
                mdm_version = "N/A"

            # === 3. Time (固定取 16 位 / 8字节) ===
            time_str = hex_to_beijing_time(line[offset:offset + 8])
            offset += 8

            # === 4. cfg version ===
            cfg_version_num = int(line[offset:offset + 2], 16)
            offset += 2

            if cfg_version_num != 0:
                cfg_version = ascii_to_decimal(line[offset:offset + cfg_version_num * 2])
                offset += cfg_version_num * 2
            else:
                cfg_version = "N/A"

            # === 5. support FOTA ===
            fota_support = int(line[offset:offset + 2], 16)
            offset += 2

            mcu_tcp_support = (fota_support >> 0) & 1
            mcu_http_support = (fota_support >> 1) & 1

            # 输出成你能看懂的文字
            support_status_fota = ""
            if mcu_tcp_support and mcu_http_support:
                support_status_fota = "TCP + HTTP"
            elif mcu_tcp_support:
                support_status_fota = "TCP"
            elif mcu_http_support:
                support_status_fota = "HTTP"
            else:
                support_status_fota = "NOT FOTA"

            ap_version_len = int(line[offset:offset + 2], 16)
            offset += 2
            ap_version = ascii_to_decimal(line[offset:offset + ap_version_len * 2]) if ap_version_len > 0 else "N/A"
            offset += ap_version_len * 2

            row = []
            if self.connect_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.connect_time_checkbox.isChecked():
                row.append(f"{time_str:<22}")
            if self.connect_hardware_version_checkbox.isChecked():
                row.append(f"{hardware_version:<20}")
            if self.connect_mcu_ap_version_checkbox.isChecked():
                row.append(f"{mcu_ap_version:<32}")
            if self.connect_mdm_version_checkbox.isChecked():
                row.append(f"{mdm_version:<32}")
            if self.connect_cfg_version_checkbox.isChecked():
                row.append(f"{cfg_version:<14}")
            if self.connect_support_status_fota_checkbox.isChecked():
                row.append(f"{support_status_fota:<22}")
            if self.connect_ap_version_checkbox.isChecked():
                row.append(f"{ap_version:<32}")
            if self.connect_raw_data_checkbox.isChecked():
                row.append(line)

            connect_times_1.append("".join(row))

    if connect_times_1:
        self.result_label.setText(f"共找到 {len(connect_times_1) - 1} 个连接事件")
        self.raw_data_display.setText("\n".join(connect_times_1))
    else:
        self.result_label.setText("未找到连接事件")
        self.raw_data_display.setText("")

# disconnect 帧
def process_disconnect_data(self, raw_data_string):
    headers = []
    if self.disconnect_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.disconnect_time_checkbox.isChecked():
        headers.append(f"{'时间':<20}")
    if self.disconnect_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    disconnect_times_1 = ["".join(headers)]

    for line in raw_data_string:
        # print(line)
        # print(line[48:50])
        if line[48:50].upper()  == "0E":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[58:66])
            # print(line, imei, time_str)

            row = []
            if self.disconnect_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.disconnect_time_checkbox.isChecked():
                row.append(f"{time_str:<20}")
            if self.disconnect_raw_data_checkbox.isChecked():
                row.append(line)

            disconnect_times_1.append("".join(row))
    if disconnect_times_1:
        self.result_label.setText(f"共找到 {len(disconnect_times_1) - 1} 个断开连接事件")
        self.raw_data_display.setText("\n".join(disconnect_times_1))
    else:
        self.result_label.setText("未找到断开连接事件")
        self.raw_data_display.setText("")






# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第一章：长相思兮长相忆，短相思兮无穷极 —— 相思
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# 行程总结
def process_trip_summary(self, raw_data_string):
    headers = []
    if self.trip_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.trip_start_time_checkbox.isChecked():
        headers.append(f"{'点火时间':<19}")
    if self.trip_end_time_checkbox.isChecked():
        headers.append(f"{'熄火时间':<19}")
    if self.trip_source_checkbox.isChecked():
        headers.append(f"{'统计来源':<6}")
    if self.trip_mileage_checkbox.isChecked():
        headers.append(f"{'行驶里程':<6}")
    if self.trip_fuel_consumption_checkbox.isChecked():
        headers.append(f"{'行程油耗':<6}")
    if self.trip_max_speed_checkbox.isChecked():
        headers.append(f"{'最高车速':<6}")
    if self.trip_idle_time_checkbox.isChecked():
        headers.append(f"{'怠速时间':<6}")
    if self.trip_idle_fuel_consumption_checkbox.isChecked():
        headers.append(f"{'怠速油耗':<6}")
    if self.trip_num_of_acceleration_checkbox.isChecked():
        headers.append(f"{'急加速次数':<7}")
    if self.trip_num_of_deceleration_checkbox.isChecked():
        headers.append(f"{'急减速次数':<7}")
    if self.trip_num_of_sharp_turn_checkbox.isChecked():
        headers.append(f"{'急转弯次数':<7}")
    if self.trip_histor_total_mil_checkbox.isChecked():
        headers.append(f"{'历史总里程':<7}")
    if self.trip_histor_total_fuel_checkbox.isChecked():
        headers.append(f"{'历史总油耗':<7}")
    if self.trip_histor_total_driving_time_checkbox.isChecked():
        headers.append(f"{'历史总行驶时间':<7}")
    if self.trip_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    trip_summary_event_times_1 = ["".join(headers)]
    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0000":
            imei = ascii_to_decimal(line[18:48])
            ignition_on_time_str = hex_to_beijing_time(line[62:70])
            # gps_location_when_ignition_on = line[70:118]  # GPS位置内容暂时忽略
            ignition_off_time_str = hex_to_beijing_time(line[118:126])
            # gps_location_when_ignition_off = line[126:174] # GPS位置内容暂时忽略

            # 取值先切片，输出16进制，然后转换为10进制，再转换为二进制
            # driving_distance_bin = bin(int(line[174:180], 16))[2:]
            driving_distance_bin = format(int(line[174:180], 16), '024b')

            source = driving_distance_bin[0]
            mileage = int(driving_distance_bin[-23:], 2)

            statistics_source = "OBD" if source == "0" else "GPS"
            trip_distance = mileage

            # trip_fuel_consumption = int(line[180:186], 16)
            trip_fuel_consumption = line[180:186] if line[180:186].upper() == "FFFFFF" else int(line[180:186], 16)
            max_speed = int(line[186:190], 16)
            idle_time = int(line[190:194], 16)
            # idle_fuel_consumption = int(line[194:198], 16)
            idle_fuel_consumption = line[194:198] if line[194:198].upper() == "FFFF" else int(line[194:198], 16)
            num_of_acceleration = int(line[198:200], 16)
            num_of_deceleration = int(line[200:202], 16)
            num_of_sharp_turn = int(line[202:204], 16)
            histor_total_mil = int(line[204:212], 16)
            # histor_total_fuel = int(line[212:220], 16)
            histor_total_fuel = line[212:220] if line[212:220].upper() == "FFFFFFFF" else int(line[212:220], 16)
            histor_total_driving_time = int(line[220:228], 16)

            row = []
            if self.trip_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.trip_start_time_checkbox.isChecked():
                row.append(f"{ignition_on_time_str:<23}")
            if self.trip_end_time_checkbox.isChecked():
                row.append(f"{ignition_off_time_str:<23}")
            if self.trip_source_checkbox.isChecked():
                row.append(f"{statistics_source:<10}")
            if self.trip_mileage_checkbox.isChecked():
                row.append(f"{trip_distance:<10}")
            if self.trip_fuel_consumption_checkbox.isChecked():
                row.append(f"{trip_fuel_consumption:<10}")
            if self.trip_max_speed_checkbox.isChecked():
                row.append(f"{max_speed:<10}")
            if self.trip_idle_time_checkbox.isChecked():
                row.append(f"{idle_time:<10}")
            if self.trip_idle_fuel_consumption_checkbox.isChecked():
                row.append(f"{idle_fuel_consumption:<10}")
            if self.trip_num_of_acceleration_checkbox.isChecked():
                row.append(f"{num_of_acceleration:<12}")
            if self.trip_num_of_deceleration_checkbox.isChecked():
                row.append(f"{num_of_deceleration:<12}")
            if self.trip_num_of_sharp_turn_checkbox.isChecked():
                row.append(f"{num_of_sharp_turn:<12}")
            if self.trip_histor_total_mil_checkbox.isChecked():
                row.append(f"{histor_total_mil:<12}")
            if self.trip_histor_total_fuel_checkbox.isChecked():
                row.append(f"{histor_total_fuel:<12}")
            if self.trip_histor_total_driving_time_checkbox.isChecked():
                row.append(f"{histor_total_driving_time:<12}")
            if self.trip_raw_data_checkbox.isChecked():
                row.append(line)

            trip_summary_event_times_1.append("".join(row))

    if trip_summary_event_times_1:
        self.result_label.setText(f"共找到 {len(trip_summary_event_times_1) - 1} 个行程事件")
        self.raw_data_display.setText("\n".join(trip_summary_event_times_1))
    else:
        self.result_label.setText("未找到行程事件")
        self.raw_data_display.setText("")

# 点火事件
def process_ignition_on(self, raw_data_string):
    headers = []
    if self.eng_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.eng_type_checkbox.isChecked():
        headers.append(f"{'类型':<10}")
    if self.eng_time_checkbox.isChecked():
        headers.append(f"{'北京时间':<23}")
    if self.eng_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    ignition_on_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0001":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[64:72])

            type_code = line[62:64]
            ignition_type = {
                "00": "RPM",
                "04": "GPS",
                "05": "SENSOR",
                "06": "ACC ON",
                "07": "Ready ON"
            }.get(type_code, type_code)

            row = []
            if self.eng_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.eng_type_checkbox.isChecked():
                row.append(f"{ignition_type:<12}")
            if self.eng_time_checkbox.isChecked():
                row.append(f"{time_str:<27}")
            if self.eng_raw_data_checkbox.isChecked():
                row.append(line)

            ignition_on_event_times_1.append("".join(row))

    if ignition_on_event_times_1:
        self.result_label.setText(f"共找到 {len(ignition_on_event_times_1) - 1} 个点火事件")
        self.raw_data_display.setText("\n".join(ignition_on_event_times_1))
    else:
        self.result_label.setText("未找到点火事件")
        self.raw_data_display.setText("")

# 熄火事件
def process_ignition_off(self, raw_data_string):
    headers = []
    if self.eng_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.eng_type_checkbox.isChecked():
        headers.append(f"{'类型':<10}")
    if self.eng_time_checkbox.isChecked():
        headers.append(f"{'北京时间':<23}")
    if self.eng_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    ignition_off_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0002":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[64:72])

            type_code = line[62:64]
            ignition_type = {
                "00": "RPM=0",
                "02": "RPM不变",
                "08": "GPS",
                "09": "SENSOR",
                "0a": "ACC OFF",
                "0b": "主电断开",
                "0c": "低电压",
                "0d": "Ready OFF"
            }.get(type_code, type_code)

            row = []
            if self.eng_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.eng_type_checkbox.isChecked():
                row.append(f"{ignition_type:<12}")
            if self.eng_time_checkbox.isChecked():
                row.append(f"{time_str:<27}")
            if self.eng_raw_data_checkbox.isChecked():
                row.append(line)

            ignition_off_event_times_1.append("".join(row))

    if ignition_off_event_times_1:
        self.result_label.setText(f"共找到 {len(ignition_off_event_times_1) - 1} 个熄火事件")
        self.raw_data_display.setText("\n".join(ignition_off_event_times_1))
    else:
        self.result_label.setText("未找到熄火事件")
        self.raw_data_display.setText("")

# 拖车开始
def process_trip_start(self, raw_data_string):
    headers = []
    if self.passive_trip_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.passive_trip_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<23}")
    if self.passive_trip_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    trip_start_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0003":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            row = []
            if self.passive_trip_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.passive_trip_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.passive_trip_raw_data_checkbox.isChecked():
                row.append(line)

            trip_start_event_times_1.append("".join(row))

    if trip_start_event_times_1:
        self.result_label.setText(f"共找到 {len(trip_start_event_times_1) - 1} 个拖车开始事件")
        self.raw_data_display.setText("\n".join(trip_start_event_times_1))
    else:
        self.result_label.setText("未找到拖车开始事件")
        self.raw_data_display.setText("")

# 拖车结束
def process_trip_end(self, raw_data_string):
    headers = []
    if self.passive_trip_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.passive_trip_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<23}")
    if self.passive_trip_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    trip_end_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0004":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            row = []
            if self.passive_trip_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.passive_trip_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.passive_trip_raw_data_checkbox.isChecked():
                row.append(line)

            trip_end_event_times_1.append("".join(row))

    if trip_end_event_times_1:
        self.result_label.setText(f"共找到 {len(trip_end_event_times_1) - 1} 个拖车结束事件")
        self.raw_data_display.setText("\n".join(trip_end_event_times_1))
    else:
        self.result_label.setText("未找到拖车结束事件")
        self.raw_data_display.setText("")

# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第二章：相思一夜情多少，地角天涯未是长 —— 断肠
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# 急加速事件
def process_sudden_acc(self, raw_data_string):
    headers = []
    if self.sudden_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.sudden_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.sudden_before_speed_checkbox.isChecked():
        headers.append(f"{'触发前车速':<7}")
    if self.sudden_after_speed_checkbox.isChecked():
        headers.append(f"{'触发后车速':<7}")
    if self.sudden_value_checkbox.isChecked():
        headers.append(f"{'触发值':<5}")
    if self.sudden_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    sudden_acc_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0100":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            before_speed = int(line[118:120], 16)
            after_speed = int(line[120:122], 16)
            value = int(line[122:124], 16) * 10  # 精度乘以10

            row = []
            if self.sudden_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.sudden_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.sudden_before_speed_checkbox.isChecked():
                row.append(f"{before_speed:<12}")
            if self.sudden_after_speed_checkbox.isChecked():
                row.append(f"{after_speed:<12}")
            if self.sudden_value_checkbox.isChecked():
                row.append(f"{value:<8}")
            if self.sudden_raw_data_checkbox.isChecked():
                row.append(line)

            sudden_acc_event_times_1.append("".join(row))

    if sudden_acc_event_times_1:
        self.result_label.setText(f"共找到 {len(sudden_acc_event_times_1) - 1} 个急加速事件")
        self.raw_data_display.setText("\n".join(sudden_acc_event_times_1))
    else:
        self.result_label.setText("未找到急加速事件")
        self.raw_data_display.setText("")

# 急减速事件
def process_sudden_dec(self, raw_data_string):
    headers = []
    if self.sudden_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.sudden_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.sudden_before_speed_checkbox.isChecked():
        headers.append(f"{'触发前车速':<7}")
    if self.sudden_after_speed_checkbox.isChecked():
        headers.append(f"{'触发后车速':<7}")
    if self.sudden_value_checkbox.isChecked():
        headers.append(f"{'触发值':<5}")
    if self.sudden_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    sudden_dec_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0101":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            before_speed = int(line[118:120], 16)
            after_speed = int(line[120:122], 16)
            value = int(line[122:124], 16) * 10  # 精度乘以10

            row = []
            if self.sudden_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.sudden_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.sudden_before_speed_checkbox.isChecked():
                row.append(f"{before_speed:<12}")
            if self.sudden_after_speed_checkbox.isChecked():
                row.append(f"{after_speed:<12}")
            if self.sudden_value_checkbox.isChecked():
                row.append(f"{value:<8}")
            if self.sudden_raw_data_checkbox.isChecked():
                row.append(line)

            sudden_dec_event_times_1.append("".join(row))

    if sudden_dec_event_times_1:
        self.result_label.setText(f"共找到 {len(sudden_dec_event_times_1) - 1} 个急减速事件")
        self.raw_data_display.setText("\n".join(sudden_dec_event_times_1))
    else:
        self.result_label.setText("未找到急减速事件")
        self.raw_data_display.setText("")

# 急转弯事件
def process_sharp_turn(self, raw_data_string):
    headers = []
    if self.sharp_turn_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.sharp_turn_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.sharp_turn_Turn_checkbox.isChecked():
        headers.append(f"{'触发值':<5}")
    if self.sharp_turn_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    sharp_turn_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0102":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            value = int(line[118:120], 16) * 10

            row = []
            if self.sharp_turn_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.sharp_turn_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.sharp_turn_Turn_checkbox.isChecked():
                row.append(f"{value:<8}")
            if self.sharp_turn_raw_data_checkbox.isChecked():
                row.append(line)

            sharp_turn_event_times_1.append("".join(row))

    if sharp_turn_event_times_1:
        self.result_label.setText(f"共找到 {len(sharp_turn_event_times_1) - 1} 个急转弯事件")
        self.raw_data_display.setText("\n".join(sharp_turn_event_times_1))
    else:
        self.result_label.setText("未找到急转弯事件")
        self.raw_data_display.setText("")

# 怠速事件
def process_exceed_idle(self, raw_data_string):
    headers = []
    if self.exceed_idle_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.exceed_idle_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.exceed_idle_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    exceed_idle_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0103":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            row = []
            if self.exceed_idle_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.exceed_idle_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.exceed_idle_raw_data_checkbox.isChecked():
                row.append(line)

            exceed_idle_event_times_1.append("".join(row))

    if exceed_idle_event_times_1:
        self.result_label.setText(f"共找到 {len(exceed_idle_event_times_1) - 1} 个怠速事件")
        self.raw_data_display.setText("\n".join(exceed_idle_event_times_1))
    else:
        self.result_label.setText("未找到怠速事件")
        self.raw_data_display.setText("")

# 疲劳驾驶事件
def process_driving_tired(self, raw_data_string):
    headers = []
    if self.driving_tired_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.driving_tired_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.driving_tired_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    driving_tired_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0104":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            row = []
            if self.driving_tired_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.driving_tired_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.driving_tired_raw_data_checkbox.isChecked():
                row.append(line)

            driving_tired_event_times_1.append("".join(row))

    if driving_tired_event_times_1:
        self.result_label.setText(f"共找到 {len(driving_tired_event_times_1) - 1} 个疲劳驾驶事件")
        self.raw_data_display.setText("\n".join(driving_tired_event_times_1))
    else:
        self.result_label.setText("未找到疲劳驾驶事件")
        self.raw_data_display.setText("")

# 超速事件
def process_over_speed(self, raw_data_string):
    headers = []
    if self.over_speed_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.over_speed_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.over_speed_value_checkbox.isChecked():
        headers.append(f"{'触发值':<5}")
    if self.over_speed_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    over_speed_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0105":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            value = int(line[70:72], 16)

            row = []
            if self.over_speed_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.over_speed_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.over_speed_value_checkbox.isChecked():
                row.append(f"{value:<8}")
            if self.over_speed_raw_data_checkbox.isChecked():
                row.append(line)

            over_speed_event_times_1.append("".join(row))

    if over_speed_event_times_1:
        self.result_label.setText(f"共找到 {len(over_speed_event_times_1) - 1} 个超速事件")
        self.raw_data_display.setText("\n".join(over_speed_event_times_1))
    else:
        self.result_label.setText("未找到超速事件")
        self.raw_data_display.setText("")

# 急变道事件
def process_sudden_lane_change(self, raw_data_string):
    headers = []
    if self.sudden_lane_change_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.sudden_lane_change_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.sudden_lane_change_value_checkbox.isChecked():
        headers.append(f"{'触发值':<5}")
    if self.sudden_lane_change_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    sudden_lane_change_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0107":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            value = int(line[118:120], 16) * 10

            row = []
            if self.sudden_lane_change_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.sudden_lane_change_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.sudden_lane_change_value_checkbox.isChecked():
                row.append(f"{value:<8}")
            if self.sudden_lane_change_raw_data_checkbox.isChecked():
                row.append(line)

            sudden_lane_change_times_1.append("".join(row))

    if sudden_lane_change_times_1:
        self.result_label.setText(f"共找到 {len(sudden_lane_change_times_1) - 1} 个急变道事件")
        self.raw_data_display.setText("\n".join(sudden_lane_change_times_1))
    else:
        self.result_label.setText("未找到急变道事件")
        self.raw_data_display.setText("")

# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第三章：眼见为虚，心听则实 —— 盲龙
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

def process_gps_data_3(self, raw_data_string):

    headers = []
    keys = []  # 用于记录字段 key，跟 headers 一一对应

    if self.gps_location_data_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.gps_location_data_num_checkbox.isChecked():
        headers.append(f"{'GPS数量':<7}")
    if self.gps_location_data_time_checkbox.isChecked():
        headers.append(f"{'GPS时间':<19}")
    if self.gps_location_data_source_checkbox.isChecked():
        headers.append(f"{'位置源':<5}")
    if self.gps_location_data_validity_checkbox.isChecked():
        headers.append(f"{'有效性':<9}")
    if self.gps_location_data_longitude_checkbox.isChecked():
        headers.append(f"{'经度':<5}")
    if self.gps_location_data_latitude_checkbox.isChecked():
        headers.append(f"{'纬度':<5}")
    if self.gps_location_data_sate_num_checkbox.isChecked():
        headers.append(f"{'卫星数':<5}")
    if self.gps_location_data_height_checkbox.isChecked():
        headers.append(f"{'高度':<4}")
    if self.gps_location_data_longitude_value_checkbox.isChecked():
        headers.append(f"{'经度值':<10}")
    if self.gps_location_data_latitude_value_checkbox.isChecked():
        headers.append(f"{'纬度值':<10}")
    if self.gps_location_data_gps_speed_checkbox.isChecked():
        headers.append(f"{'GPS速度':<7}")
    if self.gps_location_data_heading_checkbox.isChecked():
        headers.append(f"{'航向角':<6}")
    if self.gps_location_data_pdop_checkbox.isChecked():
        headers.append(f"{'PDOP':<6}")
    if self.gps_location_data_hdop_checkbox.isChecked():
        headers.append(f"{'HDOP':<6}")
    if self.gps_location_data_vdop_checkbox.isChecked():
        headers.append(f"{'VDOP':<6}")
    if self.gps_location_data_hacc_checkbox.isChecked():
        headers.append(f"{'HACC':<6}")
    if self.gps_location_data_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    gps_location_data_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0200":
            imei = ascii_to_decimal(line[18:48])
            gps_count = int(line[62:64], 16)
            if gps_count == 0:
                gps_location_data_event_times_1.append("没有 GPS 数据")
            else:
                for i in range(gps_count):
                    start = 64 + i * 48
                    end = start + 48
                    gps_data = line[start:end]
                    # print(gps_data)
                    if not isinstance(gps_data, str):
                        gps_data = str(gps_data)
                    try:
                        parsed = parse_gps_data(gps_data)
                        row = []

                        if self.gps_location_data_imei_checkbox.isChecked():
                            row.append(f"{imei:<20}")
                        if self.gps_location_data_num_checkbox.isChecked():
                            row.append(f"{gps_count:<9}")
                        if self.gps_location_data_time_checkbox.isChecked():
                            row.append(f"{parsed.get('Time', ''):<21}")
                        if self.gps_location_data_source_checkbox.isChecked():
                            row.append(f"{parsed.get('Positioning', ''):<8}")
                        if self.gps_location_data_validity_checkbox.isChecked():
                            row.append(f"{parsed.get('Time Type', ''):<12}")
                        if self.gps_location_data_longitude_checkbox.isChecked():
                            row.append(f"{parsed.get('Longitude Direction', ''):<7}")
                        if self.gps_location_data_latitude_checkbox.isChecked():
                            row.append(f"{parsed.get('Latitude Direction', ''):<7}")
                        if self.gps_location_data_sate_num_checkbox.isChecked():
                            row.append(f"{parsed.get('Sate Num', ''):<8}")
                        if self.gps_location_data_height_checkbox.isChecked():
                            row.append(f"{parsed.get('Height', ''):<6}")
                        if self.gps_location_data_longitude_value_checkbox.isChecked():
                            row.append(f"{parsed.get('Longitude', ''):<13}")
                        if self.gps_location_data_latitude_value_checkbox.isChecked():
                            row.append(f"{parsed.get('Latitude', ''):<13}")
                        if self.gps_location_data_gps_speed_checkbox.isChecked():
                            row.append(f"{parsed.get('GPS Speed', ''):<9}")
                        if self.gps_location_data_heading_checkbox.isChecked():
                            row.append(f"{parsed.get('Heading', ''):<9}")
                        if self.gps_location_data_pdop_checkbox.isChecked():
                            row.append(f"{parsed.get('PDOP', ''):<6}")
                        if self.gps_location_data_hdop_checkbox.isChecked():
                            row.append(f"{parsed.get('HDOP', ''):<6}")
                        if self.gps_location_data_vdop_checkbox.isChecked():
                            row.append(f"{parsed.get('VDOP', ''):<6}")
                        if self.gps_location_data_hacc_checkbox.isChecked():
                            row.append(f"{parsed.get('HACC', ''):<6}")
                        if self.gps_location_data_raw_data_checkbox.isChecked():
                            row.append(line)

                        gps_location_data_event_times_1.append("".join(row))

                    except Exception as e:
                        gps_location_data_event_times_1.append(f"GPS {i + 1} 解析失败: {str(e)}")

    if gps_location_data_event_times_1:
        self.result_label.setText(f"共找到 {len(gps_location_data_event_times_1) - 1} 个GPS数据包")
        self.raw_data_display.setText("\n".join(gps_location_data_event_times_1))
    else:
        self.result_label.setText("未找到GPS数据事件")
        self.raw_data_display.setText("")

# lbs事件
def process_lbs_data(self, raw_data_string):
    headers = []
    if self.lbs_location_data_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.lbs_location_data_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<18}")
    if self.lbs_location_data_mcc_mnc_checkbox.isChecked():
        headers.append(f"{'PLMN':<8}")
    if self.lbs_location_data_radio_type_checkbox.isChecked():
        headers.append(f"{'类型':<4}")
    if self.lbs_location_data_carrier_name_checkbox.isChecked():
        headers.append(f"{'运营商':<11}")
    if self.lbs_location_data_consider_ip_checkbox.isChecked():
        headers.append(f"{'参考地址':<6}")
    # if self.lbs_location_data_cell_num_checkbox.isChecked():
    #     headers.append(f"{'小区数量':<6}")
    if self.lbs_location_data_cell_list_checkbox.isChecked():
        headers.append(f"{'小区列表(Cell id-PLMN-Location Code-RSSI)':<50}")
    # if self.lbs_location_data_wifi_num_checkbox.isChecked():
    #     headers.append(f"{'WiFi数量':<8}")
    if self.lbs_location_data_wifi_list_checkbox.isChecked():
        headers.append(f"{'WiFi列表':<40}")
    if self.lbs_location_data_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    lbs_location_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0201":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            # --------------------- 以下全部是我补全 ---------------------
            ptr = 62  # 时间结束位置：32-35字节 → 字符串62-70
            ptr += 8

            # 3. Home MCC 36-38 → 6位字符串
            home_mcc_hex = line[ptr:ptr + 6]
            home_mcc = bytes.fromhex(home_mcc_hex).decode("ascii").strip()
            ptr += 6

            # 4. Length of Home MNC
            home_mnc_len = int(line[ptr:ptr + 2], 16)
            ptr += 2

            # 5. Home MNC
            home_mnc_hex = line[ptr:ptr + home_mnc_len * 2]
            home_mnc = bytes.fromhex(home_mnc_hex).decode("ascii").strip()
            ptr += home_mnc_len * 2

            mcc_mnc = f"{home_mcc}{home_mnc}"

            # 6. Radio Type 02=GSM 03=WCDMA 04=LTE 05=5G
            radio_type_hex = line[ptr:ptr + 2]
            radio_map = {"02": "GSM", "03": "WCDMA", "04": "LTE", "05": "5G NR"}
            radio_type = radio_map.get(radio_type_hex, "未知")
            ptr += 2

            # 7. Carrier Name 长度 + 内容
            carrier_len = int(line[ptr:ptr + 2], 16)
            ptr += 2
            carrier_hex = line[ptr:ptr + carrier_len * 2]
            carrier_name = bytes.fromhex(carrier_hex).decode("ascii").strip()
            ptr += carrier_len * 2

            # 8. Consider Ip
            consider_ip = line[ptr:ptr + 2]
            ptr += 2

            # ===================== 解析 基站列表（循环） =====================
            cell_num = int(line[ptr:ptr + 2], 16)
            ptr += 2
            cell_list = []
            for i in range(cell_num):
                cell_id = line[ptr:ptr + 16]
                ptr += 16
                cell_mcc_hex = line[ptr:ptr + 6]
                cell_mcc = bytes.fromhex(cell_mcc_hex).decode("ascii").strip()
                ptr += 6
                cell_mnc_len = int(line[ptr:ptr + 2], 16)
                ptr += 2
                cell_mnc_hex = line[ptr:ptr + cell_mnc_len * 2]
                cell_mnc = bytes.fromhex(cell_mnc_hex).decode("ascii").strip()
                ptr += cell_mnc_len * 2
                lac = line[ptr:ptr + 8]
                ptr += 8
                rssi = line[ptr:ptr + 2]
                ptr += 2
                cell_info = f"CELL{i + 1}：{cell_id}-{cell_mcc}{cell_mnc}-{lac}-{rssi} "
                cell_list.append(cell_info)
            cell_list_str = "；".join(cell_list).upper()

            # ===================== 解析 WIFI列表（循环） =====================
            wifi_num = int(line[ptr:ptr + 2], 16)
            ptr += 2
            wifi_list = []
            for i in range(wifi_num):
                mac = line[ptr:ptr + 12]
                ptr += 12
                wifi_rssi = line[ptr:ptr + 2]
                ptr += 2
                wifi_channel = line[ptr:ptr + 2]
                ptr += 2
                ssid_len = int(line[ptr:ptr + 2], 16)
                ptr += 2
                ssid_hex = line[ptr:ptr + ssid_len * 2]
                ssid = bytes.fromhex(ssid_hex).decode("ascii", errors="ignore").strip()
                ptr += ssid_len * 2
                wifi_info = f"wifi{i + 1}：{mac}-{wifi_rssi}-{wifi_channel}-{ssid}"
                wifi_list.append(wifi_info)
            wifi_list_str = "；".join(wifi_list).upper()

            row = []
            if self.lbs_location_data_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.lbs_location_data_time_checkbox.isChecked():
                row.append(f"{time_str:<22}")
            if self.lbs_location_data_mcc_mnc_checkbox.isChecked():
                row.append(f"{mcc_mnc:<8}")
            if self.lbs_location_data_radio_type_checkbox.isChecked():
                row.append(f"{radio_type:<6}")
            if self.lbs_location_data_carrier_name_checkbox.isChecked():
                row.append(f"{carrier_name:<14}")
            if self.lbs_location_data_consider_ip_checkbox.isChecked():
                row.append(f"{consider_ip:<10}")
            # if self.lbs_location_data_cell_num_checkbox.isChecked():
            #     row.append(f"{cell_num:<10}")
            if self.lbs_location_data_cell_list_checkbox.isChecked():
                row.append(f"CN-{cell_num}>> {cell_list_str}  ")
            # if self.lbs_location_data_wifi_num_checkbox.isChecked():
            #     row.append(f"{wifi_num:<10}")
            if self.lbs_location_data_wifi_list_checkbox.isChecked():
                row.append(f"WN-{wifi_num}>> {wifi_list_str}  ")
            if self.lbs_location_data_raw_data_checkbox.isChecked():
                row.append(line)

            lbs_location_event_times_1.append("".join(row))

    if lbs_location_event_times_1:
        self.result_label.setText(f"共找到 {len(lbs_location_event_times_1) - 1} 个LBS数据包")
        self.raw_data_display.setText("\n".join(lbs_location_event_times_1))
    else:
        self.result_label.setText("未找到LBS数据事件")
        self.raw_data_display.setText("")

# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第四章：乾坤一簌天下游，月如钩，难别求 —— 风流
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# VIN码事件
def process_vin_code(self, raw_data_string):
    headers = []
    if self.vin_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.vin_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.vin_type_checkbox.isChecked():
        headers.append(f"{'协议类型':<12}")
    if self.vin_length_checkbox.isChecked():
        headers.append(f"{'VIN长度':<8}")
    if self.vin_vin_value_checkbox.isChecked():
        headers.append(f"{'VIN码':<20}")
    if self.vin_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    vin_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0300":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            type_code_hex = line[70:72]
            if type_code_hex == "00":
                type_code = "PT_NORMAL"
            elif type_code_hex == "01":
                type_code = "PT_KWP"
            elif type_code_hex == "02":
                type_code = "PT_ISO"
            elif type_code_hex == "03":
                type_code = "PT_VPW"
            elif type_code_hex == "04":
                type_code = "PT_PWM"
            elif type_code_hex == "19":
                type_code = "PT_KWP_QUICK"
            elif type_code_hex == "99":
                type_code = "PT_OBD_CAN"
            elif type_code_hex == "20":
                type_code = "PT_J1939"
            else:
                type_code = "UNKNOWN"
            vin_length = int(line[72:74], 16)
            vin_value = ascii_to_decimal(line[74: 74 + (vin_length * 2)])

            row = []

            if self.vin_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.vin_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.vin_type_checkbox.isChecked():
                row.append(f"{type_code:<16}")
            if self.vin_length_checkbox.isChecked():
                row.append(f"{vin_length:<10}")
            if self.vin_vin_value_checkbox.isChecked():
                row.append(f"{vin_value:<21}")
            if self.vin_raw_data_checkbox.isChecked():
                row.append(line)

            vin_event_times_1.append("".join(row))

    if vin_event_times_1:
        self.result_label.setText(f"共找到 {len(vin_event_times_1) - 1} 个VIN码事件")
        self.raw_data_display.setText("\n".join(vin_event_times_1))
    else:
        self.result_label.setText("未找到VIN码事件")
        self.raw_data_display.setText("")

# 数据流事件
def process_data_flow(self, raw_data_string):
    dataflow_header_fields = [
        ("dataflow_imei_checkbox", "IMEI", 20),
        ("dataflow_time_checkbox", "触发时间", 19),
        ("dataflow_rpm_checkbox", "转速", 5),
        ("dataflow_speed_checkbox", "车速", 5),
        ("dataflow_engine_coolant_temperature_checkbox", "A", 7),
        ("dataflow_throttle_position_checkbox", "B", 7),
        ("dataflow_engine_duty_checkbox", "C", 7),
        ("dataflow_intake_air_flow_checkbox", "D", 7),
        ("dataflow_intake_air_temperature_checkbox", "E", 7),
        ("dataflow_intake_air_pressure_checkbox", "F", 7),
        ("dataflow_battery_voltage_checkbox", "G", 7),
        ("dataflow_fuel_level_checkbox", "H", 7),
        ("dataflow_distance_dtcs_cleared_checkbox", "I", 7),
        ("dataflow_distance_mil_checkbox", "J", 7),
        ("dataflow_historical_total_mileage_checkbox", "K1", 13),
        ("dataflow_historical_total_fuel_consumption_checkbox", "K2", 13),
        ("dataflow_historical_total_driving_time_checkbox", "K3", 13),
        ("dataflow_seatbelt_status_checkbox", "L", 7),
        ("dataflow_odometer_checkbox", "M", 13),
        ("dataflow_average_fuel_consumption_checkbox", "N", 13),
        ("dataflow_odometer_unit_checkbox", "O", 7),
        ("dataflow_soc_checkbox", "P", 7),
        ("dataflow_soh_checkbox", "Q", 7),
        ("dataflow_battery_pack_current_checkbox", "R", 7),
        ("dataflow_battery_pack_voltage_checkbox", "S", 7),
        ("dataflow_battery_pack_charging_checkbox", "T", 5),
        ("dataflow_remaining_distance_checkbox", "U", 7),
        ("dataflow_battery_pack_temperature_checkbox", "V", 7),
        ("dataflow_distance_till_next_servicing_checkbox", "W", 7),
        ("dataflow_engine_run_time_checkbox", "X", 13),
        ("dataflow_fuel_type_checkbox", "Y", 5),
        ("dataflow_turn_signals_status_checkbox", "Z", 5),
        ("dataflow_raw_data_checkbox", "原始数据", 100)
    ]
    headers = build_checkbox(dataflow_header_fields, self)

    # headers = []
    # if self.dataflow_imei_checkbox.isChecked():
    #     headers.append(f"{'IMEI':<20}")
    # if self.dataflow_time_checkbox.isChecked():
    #     headers.append(f"{'触发时间':<19}")
    # if self.dataflow_rpm_checkbox.isChecked():
    #     headers.append(f"{'转速':<5}")
    # if self.dataflow_speed_checkbox.isChecked():
    #     headers.append(f"{'车速':<5}")
    # if self.dataflow_engine_coolant_temperature_checkbox.isChecked():
    #     headers.append(f"{'A':<7}")
    # if self.dataflow_throttle_position_checkbox.isChecked():
    #     headers.append(f"{'B':<7}")
    # if self.dataflow_engine_duty_checkbox.isChecked():
    #     headers.append(f"{'C':<7}")
    # if self.dataflow_intake_air_flow_checkbox.isChecked():
    #     headers.append(f"{'D':<7}")
    # if self.dataflow_intake_air_temperature_checkbox.isChecked():
    #     headers.append(f"{'E':<7}")
    # if self.dataflow_intake_air_pressure_checkbox.isChecked():
    #     headers.append(f"{'F':<7}")
    # if self.dataflow_battery_voltage_checkbox.isChecked():
    #     headers.append(f"{'G':<7}")
    # if self.dataflow_fuel_level_checkbox.isChecked():
    #     headers.append(f"{'H':<7}")
    # if self.dataflow_distance_dtcs_cleared_checkbox.isChecked():
    #     headers.append(f"{'I':<7}")
    # if self.dataflow_distance_mil_checkbox.isChecked():
    #     headers.append(f"{'J':<7}")
    # if self.dataflow_historical_total_mileage_checkbox.isChecked():
    #     headers.append(f"{'K1':<13}")
    # if self.dataflow_historical_total_fuel_consumption_checkbox.isChecked():
    #     headers.append(f"{'K2':<13}")
    # if self.dataflow_historical_total_driving_time_checkbox.isChecked():
    #     headers.append(f"{'K3':<13}")
    # if self.dataflow_seatbelt_status_checkbox.isChecked():
    #     headers.append(f"{'L':<7}")
    # if self.dataflow_odometer_checkbox.isChecked():
    #     headers.append(f"{'M':<13}")
    # if self.dataflow_average_fuel_consumption_checkbox.isChecked():
    #     headers.append(f"{'N':<13}")
    # if self.dataflow_odometer_unit_checkbox.isChecked():
    #     headers.append(f"{'O':<7}")
    # if self.dataflow_soc_checkbox.isChecked():
    #     headers.append(f"{'P':<7}")
    # if self.dataflow_soh_checkbox.isChecked():
    #     headers.append(f"{'Q':<7}")
    # if self.dataflow_battery_pack_current_checkbox.isChecked():
    #     headers.append(f"{'R':<7}")
    # if self.dataflow_battery_pack_voltage_checkbox.isChecked():
    #     headers.append(f"{'S':<7}")
    # if self.dataflow_battery_pack_charging_checkbox.isChecked():
    #     headers.append(f"{'T':<5}")
    # if self.dataflow_remaining_distance_checkbox.isChecked():
    #     headers.append(f"{'U':<7}")
    # if self.dataflow_battery_pack_temperature_checkbox.isChecked():
    #     headers.append(f"{'V':<7}")
    # if self.dataflow_distance_till_next_servicing_checkbox.isChecked():
    #     headers.append(f"{'W':<7}")
    # if self.dataflow_engine_run_time_checkbox.isChecked():
    #     headers.append(f"{'X':<13}")
    # if self.dataflow_fuel_type_checkbox.isChecked():
    #     headers.append(f"{'Y':<5}")
    # if self.dataflow_turn_signals_status_checkbox.isChecked():
    #     headers.append(f"{'Z':<5}")
    # if self.dataflow_raw_data_checkbox.isChecked():
    #     headers.append(f"{'原始数据'}")

    dataflow_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0301":
            imei = ascii_to_decimal(line[18:48])  # imei号
            time_str = hex_to_beijing_time(line[62:70])  # 触发时间
            rpm = "FFFF" if line[120:124].upper() == "FFFF" else int(line[120:124], 16)  # 转速
            speed = "FFFF" if line[124:128].upper() == "FFFF" else int(line[124:128], 16)  # 车速
            engine_coolant_temperature = "FFFF" if line[128:132].upper() == "FFFF" else int(line[128:132],
                                                                                            16) - 40  # 发动机冷却液温度 偏移-40

            throttle_position = "FFFF" if line[132:136].upper() == "FFFF" else round(int(line[132:136], 16) * 0.1,
                                                                                     1)  # 节气门位置
            engine_duty = "FFFF" if line[136:140].upper() == "FFFF" else round(int(line[136:140], 16) * 0.1,
                                                                               1)  # 发动机负荷
            intake_air_flow = "FFFF" if line[140:144].upper() == "FFFF" else round(int(line[140:144], 16) * 0.1,
                                                                                   1)  # 进气流量
            intake_air_temperature = "FFFF" if line[144:148].upper() == "FFFF" else int(line[144:148],
                                                                                        16) - 40  # 进气温度 偏移-40
            intake_air_pressure = "FFFF" if line[148:152].upper() == "FFFF" else int(line[148:152], 16)  # 进气压力

            battery_voltage = "FFFF" if line[152:156].upper() == "FFFF" else round(int(line[152:156], 16) * 0.1,
                                                                                   1)  # 电池电压
            fuel_level = "FFFF" if line[156:160].upper() == "FFFF" else round(int(line[156:160], 16) * 0.01, 2)
            distance_dtcs_cleared = "FFFF" if line[160:164].upper() == "FFFF" else int(line[160:164], 16)  # 故障码清除里程

            distance_mil_hex = line[164:168]  # 故障灯点亮里程
            if distance_mil_hex.upper() == "FFFF":
                distance_mil = "FFFF"
            elif distance_mil_hex.upper() == "FFFE":
                distance_mil = "FFFE"
            elif distance_mil_hex == "0000":
                distance_mil = "0000"
            else:
                distance_mil = int(line[164:168], 16)

            historical_total_mileage = int(line[168:176], 16)  # 历史总里程

            historical_total_fuel_consumption = int(line[176:184], 16)  # 历史总油耗
            historical_total_driving_time = int(line[184:192], 16)  # 历史总驾驶时间

            seatbelt_int = int(line[192:194], 16)  # 安全带状态
            seatbelt_bin = format(seatbelt_int, '08b')
            seatbelt_bits_0_to_3 = seatbelt_bin[-4:]
            seatbelt_status = str(seatbelt_bits_0_to_3)

            odometer = "FFFFFFFF" if line[194:202].upper() == "FFFFFFFF" else int(line[194:202], 16)  # 里程表读数
            average_fuel_consumption = "FFFFFFFF" if line[202:210].upper() == "FFFFFFFF" else int(line[202:210],
                                                                                                  16)  # 平均油耗
            odometer_unit_hex = line[210:212]
            if odometer_unit_hex == "01":
                odometer_unit = "KM"
            elif odometer_unit_hex == "02":
                odometer_unit = "Mile"
            elif odometer_unit_hex.lower() == "ff":
                odometer_unit = "Unkn"
            else:
                odometer_unit = odometer_unit_hex

            soc = "FFFF" if line[212:216].upper() == "FFFF" else round(int(line[212:216], 16) * 0.1, 1)  # SOC

            soh = "FF" if line[216:218].upper() == "FF" else int(line[216:218], 16)  # SOH

            battery_pack_current = "FFFF" if line[218:222].upper() == "FFFF" else round(
                (int(line[218:222], 16)  - 10000) * 0.1, 1)  # 电池组电流
            battery_pack_voltage = "FFFF" if line[222:226].upper() == "FFFF" else round(
                int(line[222:226], 16) * 0.1, 1)  # 电池组电压

            battery_pack_charging_hex = line[226:228]  # 电池组充电状态
            if battery_pack_charging_hex == "00":
                battery_pack_charging = "NA"
            elif battery_pack_charging_hex == "01":
                battery_pack_charging = "L1"
            elif battery_pack_charging_hex == "02":
                battery_pack_charging = "L2"
            elif battery_pack_charging_hex == "03":
                battery_pack_charging = "L3"
            elif battery_pack_charging_hex.lower() == "ff":
                battery_pack_charging = "FF"
            else:
                battery_pack_charging = battery_pack_charging_hex

            remaining_distance = "FFFF" if line[228:232].upper() == "FFFF" else int(line[228:232], 16)  # 剩余里程
            battery_pack_temperature = "FFFF" if line[232:236].upper() == "FFFF" else int(line[232:236],
                                                                                          16) - 40  # 电池组温度 偏移-40
            distance_till_next_servicing = "FFFF" if line[236:240].upper() == "FFFF" else int(line[236:240],
                                                                                              16)  # 下次保养里程
            engine_run_time = "FFFFFFFF" if line[240:248].upper() == "FFFFFFFF" else int(line[240:248],
                                                                                         16)  # 发动机运行时间
            fuel_type = "FF" if line[248:250].upper() == "FF" else line[248:250]  # 燃油类型
            turn_signals_status_int = int(line[250:252], 16)  # 转向灯状态
            turn_signals_status_bin = format(turn_signals_status_int, '08b')
            turn_signals_status_bits_0_to_1 = turn_signals_status_bin[-2:]
            turn_signals_status = str(turn_signals_status_bits_0_to_1)

            dataflow_tail_fields = [
                ("dataflow_imei_checkbox", imei, 20),
                ("dataflow_time_checkbox", time_str, 23),
                ("dataflow_rpm_checkbox", rpm, 7),
                ("dataflow_speed_checkbox", speed, 7),
                ("dataflow_engine_coolant_temperature_checkbox", engine_coolant_temperature, 7),
                ("dataflow_throttle_position_checkbox", throttle_position, 7),
                ("dataflow_engine_duty_checkbox", engine_duty, 7),
                ("dataflow_intake_air_flow_checkbox", intake_air_flow, 7),
                ("dataflow_intake_air_temperature_checkbox", intake_air_temperature, 7),
                ("dataflow_intake_air_pressure_checkbox", intake_air_pressure, 7),
                ("dataflow_battery_voltage_checkbox", battery_voltage, 7),
                ("dataflow_fuel_level_checkbox", fuel_level, 7),
                ("dataflow_distance_dtcs_cleared_checkbox", distance_dtcs_cleared, 7),
                ("dataflow_distance_mil_checkbox", distance_mil, 7),
                ("dataflow_historical_total_mileage_checkbox", historical_total_mileage, 13),
                ("dataflow_historical_total_fuel_consumption_checkbox", historical_total_fuel_consumption, 13),
                ("dataflow_historical_total_driving_time_checkbox", historical_total_driving_time, 13),
                ("dataflow_seatbelt_status_checkbox", seatbelt_status, 7),
                ("dataflow_odometer_checkbox", odometer, 13),
                ("dataflow_average_fuel_consumption_checkbox", average_fuel_consumption, 13),
                ("dataflow_odometer_unit_checkbox", odometer_unit, 7),
                ("dataflow_soc_checkbox", soc, 7),
                ("dataflow_soh_checkbox", soh, 7),
                ("dataflow_battery_pack_current_checkbox", battery_pack_current, 7),
                ("dataflow_battery_pack_voltage_checkbox", battery_pack_voltage, 7),
                ("dataflow_battery_pack_charging_checkbox", battery_pack_charging, 5),
                ("dataflow_remaining_distance_checkbox", remaining_distance, 7),
                ("dataflow_battery_pack_temperature_checkbox", battery_pack_temperature, 7),
                ("dataflow_distance_till_next_servicing_checkbox", distance_till_next_servicing, 7),
                ("dataflow_engine_run_time_checkbox", engine_run_time, 13),
                ("dataflow_fuel_type_checkbox", fuel_type, 5),
                ("dataflow_turn_signals_status_checkbox", turn_signals_status, 5),
                ("dataflow_raw_data_checkbox", line, 100)
            ]

            row = build_checkbox(dataflow_tail_fields, self)

            # row = []
            # if self.dataflow_imei_checkbox.isChecked():
            #     row.append(f"{imei:<20}")
            # if self.dataflow_time_checkbox.isChecked():
            #     row.append(f"{time_str:<23}")
            # if self.dataflow_rpm_checkbox.isChecked():
            #     row.append(f"{rpm:<7}")
            # if self.dataflow_speed_checkbox.isChecked():
            #     row.append(f"{speed:<7}")
            # if self.dataflow_engine_coolant_temperature_checkbox.isChecked():
            #     row.append(f"{engine_coolant_temperature:<7}")
            # if self.dataflow_throttle_position_checkbox.isChecked():
            #     row.append(f"{throttle_position:<7}")
            # if self.dataflow_engine_duty_checkbox.isChecked():
            #     row.append(f"{engine_duty:<7}")
            # if self.dataflow_intake_air_flow_checkbox.isChecked():
            #     row.append(f"{intake_air_flow:<7}")
            # if self.dataflow_intake_air_temperature_checkbox.isChecked():
            #     row.append(f"{intake_air_temperature:<7}")
            # if self.dataflow_intake_air_pressure_checkbox.isChecked():
            #     row.append(f"{intake_air_pressure:<7}")
            # if self.dataflow_battery_voltage_checkbox.isChecked():
            #     row.append(f"{battery_voltage:<7}")
            # if self.dataflow_fuel_level_checkbox.isChecked():
            #     row.append(f"{fuel_level:<7}")
            # if self.dataflow_distance_dtcs_cleared_checkbox.isChecked():
            #     row.append(f"{distance_dtcs_cleared:<7}")
            # if self.dataflow_distance_mil_checkbox.isChecked():
            #     row.append(f"{distance_mil:<7}")
            # if self.dataflow_historical_total_mileage_checkbox.isChecked():
            #     row.append(f"{historical_total_mileage:<13}")
            # if self.dataflow_historical_total_fuel_consumption_checkbox.isChecked():
            #     row.append(f"{historical_total_fuel_consumption:<13}")
            # if self.dataflow_historical_total_driving_time_checkbox.isChecked():
            #     row.append(f"{historical_total_driving_time:<13}")
            # if self.dataflow_seatbelt_status_checkbox.isChecked():
            #     row.append(f"{seatbelt_status:<7}")
            # if self.dataflow_odometer_checkbox.isChecked():
            #     row.append(f"{odometer:<13}")
            # if self.dataflow_average_fuel_consumption_checkbox.isChecked():
            #     row.append(f"{average_fuel_consumption:<13}")
            # if self.dataflow_odometer_unit_checkbox.isChecked():
            #     row.append(f"{odometer_unit:<7}")
            # if self.dataflow_soc_checkbox.isChecked():
            #     row.append(f"{soc:<7}")
            # if self.dataflow_soh_checkbox.isChecked():
            #     row.append(f"{soh:<7}")
            # if self.dataflow_battery_pack_current_checkbox.isChecked():
            #     row.append(f"{battery_pack_current:<7}")
            # if self.dataflow_battery_pack_voltage_checkbox.isChecked():
            #     row.append(f"{battery_pack_voltage:<7}")
            # if self.dataflow_battery_pack_charging_checkbox.isChecked():
            #     row.append(f"{battery_pack_charging:<5}")
            # if self.dataflow_remaining_distance_checkbox.isChecked():
            #     row.append(f"{remaining_distance:<7}")
            # if self.dataflow_battery_pack_temperature_checkbox.isChecked():
            #     row.append(f"{battery_pack_temperature:<7}")
            # if self.dataflow_distance_till_next_servicing_checkbox.isChecked():
            #     row.append(f"{distance_till_next_servicing:<7}")
            # if self.dataflow_engine_run_time_checkbox.isChecked():
            #     row.append(f"{engine_run_time:<13}")
            # if self.dataflow_fuel_type_checkbox.isChecked():
            #     row.append(f"{fuel_type:<5}")
            # if self.dataflow_turn_signals_status_checkbox.isChecked():
            #     row.append(f"{turn_signals_status:<5}")
            # if self.dataflow_raw_data_checkbox.isChecked():
            #     row.append(line)

            dataflow_event_times_1.append("".join(row))

    if dataflow_event_times_1:
        self.result_label.setText(f"共找到 {len(dataflow_event_times_1) - 1} 个数据流事件")
        self.raw_data_display.setText("\n".join(dataflow_event_times_1))
    else:
        self.result_label.setText("未找到数据流事件")
        self.raw_data_display.setText("")

# CAN 支持参数列表
def process_can_parameter_support_status(self,raw_data_string):
    headers = []
    if self.can_parameter_support_status_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.can_parameter_support_status_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<20}")
    if self.can_parameter_support_status_vin_checkbox.isChecked():
        headers.append(f"{'VIN':<20}")
    if self.can_parameter_support_status_gasoline_ev_checkbox.isChecked():
        headers.append(f"{'GASOLINE_EV'}")
    if self.can_parameter_support_status_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    can_parameter_support_status_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0304":
            imei = ascii_to_decimal(line[18:48])  # imei号
            time_str = hex_to_beijing_time(line[62:70])  # 触发时间
            vin_length = int(line[70:72], 16)
            vin_value = ascii_to_decimal(line[72: 72 + (vin_length * 2)])

            # ✅ CAN 起始位置
            start = 72 + (vin_length * 2)

            # ===== 解析 Gasoline =====
            gasoline_list, next_start = parse_can_list(
                line, start, gasoline_map
            )

            # ===== 解析 EV =====
            ev_list, final_start = parse_can_list(
                line, next_start, ev_map
            )

            # ===== 拼接字符串 =====
            gasoline_str = "，".join(gasoline_list) if gasoline_list else "无支持项"
            ev_str = "，".join(ev_list) if ev_list else "无支持项"

            Gasoline_EV_value_list = (
                f"CAN parameter list for Gasoline Vehicle（{gasoline_str}）"
                f" CAN parameter list for EV Vehicle（{ev_str}）"
            )

            row = []
            if self.can_parameter_support_status_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.can_parameter_support_status_time_checkbox.isChecked():
                row.append(f"{time_str:<20}")
            if self.can_parameter_support_status_vin_checkbox.isChecked():
                row.append(f"{vin_value:<20}")
            if self.can_parameter_support_status_gasoline_ev_checkbox.isChecked():
                row.append(Gasoline_EV_value_list)
            if self.can_parameter_support_status_raw_data_checkbox.isChecked():
                row.append(line)

            can_parameter_support_status_times_1.append("".join(row))

    if can_parameter_support_status_times_1:
        self.result_label.setText(f"共找到 {len(can_parameter_support_status_times_1) - 1} 个CAN参数支持状态事件")
        self.raw_data_display.setText("\n".join(can_parameter_support_status_times_1))
    else:
        self.result_label.setText("未找到CAN参数支持状态")
        self.raw_data_display.setText("")

# raw can frame
def process_raw_can_frame(self,raw_data_string):
    headers = []
    if self.raw_can_frame_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.raw_can_frame_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<20}")
    if self.raw_can_frame_canbuspins_checkbox.isChecked():
        headers.append(f"{'pin':<10}")
    if self.raw_can_frame_num_canframe_checkbox.isChecked():
        headers.append(f"{'num':<10}")
    if self.raw_can_frame_canframeid_raw_checkbox.isChecked():
        headers.append(f"{'CANID_RAW'}")
    if self.raw_can_frame_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    raw_can_frame_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0305":
            imei = ascii_to_decimal(line[18:48])  # imei号
            time_str = hex_to_beijing_time(line[62:70])  # 触发时间
            canbuspins = int(line[70:72], 16)
            num_canframe = int(line[72:74],16)

            start = 74
            canframeid_raw_list = []

            for i in range(num_canframe):
                offset = start + i * 24
                # 防止越界（非常重要）
                if offset + 24 > len(line):
                    break
                # CAN ID（8个hex字符）
                can_id = line[offset: offset + 8]
                # RAW CAN FRAME（16个hex字符）
                raw_frame = line[offset + 8: offset + 24]
                # 拼接
                canframeid_raw_list.append(can_id + "-" + raw_frame + " ")

            canframeid_raw = "".join(canframeid_raw_list).upper()

            row = []
            if self.raw_can_frame_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.raw_can_frame_time_checkbox.isChecked():
                row.append(f"{time_str:<24}")
            if self.raw_can_frame_canbuspins_checkbox.isChecked():
                row.append(f"{canbuspins:<10}")
            if self.raw_can_frame_num_canframe_checkbox.isChecked():
                row.append(f"{num_canframe:<10}")
            if self.raw_can_frame_canframeid_raw_checkbox.isChecked():
                row.append(canframeid_raw)
            if self.raw_can_frame_raw_data_checkbox.isChecked():
                row.append(line)

            raw_can_frame_times_1.append("".join(row))

    if raw_can_frame_times_1:
        self.result_label.setText(f"共找到 {len(raw_can_frame_times_1) - 1} 个raw can frame状态事件")
        self.raw_data_display.setText("\n".join(raw_can_frame_times_1))
    else:
        self.result_label.setText("未找到raw can frame状态事件")
        self.raw_data_display.setText("")

# config 数据流
def process_config_data_flow(self, raw_data_string):
    headers = []
    if self.config_dataflow_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.config_dataflow_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.config_dataflow_klv_checkbox.isChecked():
        headers.append(f"{'KLV数据'}")
    if self.config_dataflow_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    config_dataflow_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0306":
            imei = ascii_to_decimal(line[18:48])  # imei号
            time_str = hex_to_beijing_time(line[62:70])  # 触发时间

            # ✅ 解析KLV（从第70位开始）
            valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
            klv_data = line[70:58+valid_data_length]
            klv = parse_klv(klv_data)

            row = []
            if self.config_dataflow_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.config_dataflow_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.config_dataflow_klv_checkbox.isChecked():
                row.append(f"{klv:<100} "  "")  # 已解析KLV
            if self.config_dataflow_raw_data_checkbox.isChecked():
                row.append(line)

            config_dataflow_times_1.append("".join(row))

    if config_dataflow_times_1:
        self.result_label.setText(f"共找到 {len(config_dataflow_times_1) - 1} 个配置数据流事件")
        self.raw_data_display.setText("\n".join(config_dataflow_times_1))
    else:
        self.result_label.setText("未找到配置数据流事件")
        self.raw_data_display.setText("")

def process_vehicle_Information_klv(self, raw_data_string):
    headers = []
    if self.vehicle_Information_klv_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    # if self.vehicle_Information_klv_time_checkbox.isChecked():
    #     headers.append(f"{'触发时间':<19}")
    if self.vehicle_Information_klv_klv_data_checkbox.isChecked():
        headers.append(f"{'消息内容'}")
    if self.vehicle_Information_klv_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    vehicle_Information_klv_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0307":
            imei = ascii_to_decimal(line[18:48])  # imei号

            # ✅ 解析KLV（从第70位开始）
            valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
            klv_source_data = line[62:58+valid_data_length]
            klv_data = parse_klv(klv_source_data)

            row = []
            if self.vehicle_Information_klv_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            # if self.vehicle_Information_klv_time_checkbox.isChecked():
            #     row.append(f"{time_str:<23}")
            if self.vehicle_Information_klv_klv_data_checkbox.isChecked():
                row.append(f"{klv_data:<10}")
            if self.vehicle_Information_klv_raw_data_checkbox.isChecked():
                row.append(line)

            vehicle_Information_klv_times_1.append("".join(row))

    if vehicle_Information_klv_times_1:
        self.result_label.setText(f"共找到 {len(vehicle_Information_klv_times_1) - 1} 个消息发送事件")
        self.raw_data_display.setText("\n".join(vehicle_Information_klv_times_1))
    else:
        self.result_label.setText("未找到消息发送事件")
        self.raw_data_display.setText("")


# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第五章：书香百味有多少，天下何人配白衣 —— 无双
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# dtc事件
def process_dtc_code(self, raw_data_string):
    headers = []
    if self.dtc_code_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.dtc_code_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.dtc_code_obd_dtc_num_checkbox.isChecked():
        headers.append(f"{'故障码数量':<6}")
    if self.dtc_code_obd_dtc_data_checkbox.isChecked():
        headers.append(f"{'故障码数据':<25}")
    if self.dtc_code_private_code_num_checkbox.isChecked():
        headers.append(f"{'私有码数量':<6}")
    if self.dtc_code_private_code_data_checkbox.isChecked():
        headers.append(f"{'私有码数据':<25}")
    if self.dtc_code_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    dtc_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0500":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            obd_dtc_num = int(line[70:72], 16)
            obd_dtc_data = line[72:72 + (obd_dtc_num * 6)]
            private_code_num = int(line[72 + (obd_dtc_num * 6):74 + (obd_dtc_num * 6)], 16)
            private_code_data = line[74 + (obd_dtc_num * 6):74 + (obd_dtc_num * 6) + (private_code_num * 8)]

            row = []
            if self.dtc_code_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.dtc_code_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.dtc_code_obd_dtc_num_checkbox.isChecked():
                row.append(f"{obd_dtc_num:<11}")
            if self.dtc_code_obd_dtc_data_checkbox.isChecked():
                row.append(f"{obd_dtc_data:<30}")
            if self.dtc_code_private_code_num_checkbox.isChecked():
                row.append(f"{private_code_num:<11}")
            if self.dtc_code_private_code_data_checkbox.isChecked():
                row.append(f"{private_code_data:<30}")
            if self.dtc_code_raw_data_checkbox.isChecked():
                row.append(line)

            dtc_event_times_1.append("".join(row))

    if dtc_event_times_1:
        self.result_label.setText(f"共找到 {len(dtc_event_times_1) - 1} 个故障码事件")
        self.raw_data_display.setText("\n".join(dtc_event_times_1))
    else:
        self.result_label.setText("未找到故障码事件")
        self.raw_data_display.setText("")

# 低电压事件
def process_battery_low(self, raw_data_string):
    headers = []
    if self.battery_low_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.battery_low_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.battery_low_battery_voltage_checkbox.isChecked():
        headers.append(f"{'电源电压':<6}")
    if self.battery_low_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    low_voltage_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0501":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            voltage = round(int(line[118:122], 16) * 0.1, 1)  # 电压

            row = []
            if self.battery_low_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.battery_low_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.battery_low_battery_voltage_checkbox.isChecked():
                row.append(f"{voltage:<10}")
            if self.battery_low_raw_data_checkbox.isChecked():
                row.append(line)

            low_voltage_event_times_1.append("".join(row))

    if low_voltage_event_times_1:
        self.result_label.setText(f"共找到 {len(low_voltage_event_times_1) - 1} 个低电压事件")
        self.raw_data_display.setText("\n".join(low_voltage_event_times_1))
    else:
        self.result_label.setText("未找到低电压事件")
        self.raw_data_display.setText("")

# 震动事件
def process_vibration_event(self, raw_data_string):
    headers = []
    if self.vibration_event_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.vibration_event_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.vibration_event_vibration_value_checkbox.isChecked():
        headers.append(f"{'震动值':<8}")
    if self.vibration_event_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    vibration_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0502":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            vibration_value = int(line[118:122], 16)

            row = []
            if self.vibration_event_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.vibration_event_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.vibration_event_vibration_value_checkbox.isChecked():
                row.append(f"{vibration_value:<11}")
            if self.vibration_event_raw_data_checkbox.isChecked():
                row.append(line)

            vibration_event_times_1.append("".join(row))

    if vibration_event_times_1:
        self.result_label.setText(f"共找到 {len(vibration_event_times_1) - 1} 个震动事件")
        self.raw_data_display.setText("\n".join(vibration_event_times_1))
    else:
        self.result_label.setText("未找到震动事件")
        self.raw_data_display.setText("")

# 疑似碰撞
def process_suspected_collision(self, raw_data_string):
    headers = []
    if self.suspected_collision_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.suspected_collision_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.suspected_collision_collision_value_checkbox.isChecked():
        headers.append(f"{'碰撞值':<8}")
    if self.suspected_collision_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    suspected_collision_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0505":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            collision_value = round(int(line[118:120], 16) * 0.1, 1)

            row = []
            if self.suspected_collision_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.suspected_collision_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.suspected_collision_collision_value_checkbox.isChecked():
                row.append(f"{collision_value:<11}")
            if self.suspected_collision_raw_data_checkbox.isChecked():
                row.append(line)

            suspected_collision_event_times_1.append("".join(row))

    if suspected_collision_event_times_1:
        self.result_label.setText(f"共找到 {len(suspected_collision_event_times_1) - 1} 个疑似碰撞事件")
        self.raw_data_display.setText("\n".join(suspected_collision_event_times_1))
    else:
        self.result_label.setText("未找到疑似碰撞事件")
        self.raw_data_display.setText("")

# 拔出告警
def process_unplug_warning(self, raw_data_string):
    headers = []
    if self.unplug_warning_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.unplug_warning_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.unplug_warning_unplug_state_checkbox.isChecked():
        headers.append(f"{'拔出状态':<8}")
    if self.unplug_warning_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    unplug_warning_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62] == "0507":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            unplug_state_hex = line[118:120]
            if unplug_state_hex == "00":
                unplug_state = "正常拔出"
            elif unplug_state_hex == "01":
                unplug_state = "点火中拔出"
            else:
                unplug_state = "N/A"

            row = []
            if self.unplug_warning_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.unplug_warning_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.unplug_warning_unplug_state_checkbox.isChecked():
                row.append(f"{unplug_state:<12}")
            if self.unplug_warning_raw_data_checkbox.isChecked():
                row.append(line)

            unplug_warning_event_times_1.append("".join(row))

    if unplug_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(unplug_warning_event_times_1) - 1} 个拔出告警事件")
        self.raw_data_display.setText("\n".join(unplug_warning_event_times_1))
    else:
        self.result_label.setText("未找到拔出告警事件")
        self.raw_data_display.setText("")

# 干扰状态
def process_jamming_detection(self, raw_data_string):
    headers = []
    if self.jamming_detection_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.jamming_detection_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.jamming_detection_jamming_status_checkbox.isChecked():
        headers.append(f"{'干扰状态':<8}")
    if self.jamming_detection_jamming_type_checkbox.isChecked():
        headers.append(f"{'干扰类型':<8}")
    if self.jamming_detection_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    jamming_detection_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "050B":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            jamming_state_hex = line[118:120]
            if jamming_state_hex == "00":
                jamming_state = "start"
            elif jamming_state_hex == "01":
                jamming_state = "end"
            else:
                jamming_state = "N/A"

            jamming_type_hex = line[120:122]
            if jamming_type_hex == "00":
                jamming_type = "CELL"
            elif jamming_type_hex == "01":
                jamming_type = "GNSS"
            else:
                jamming_type = "N/A"

            row = []
            if self.jamming_detection_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.jamming_detection_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.jamming_detection_jamming_status_checkbox.isChecked():
                row.append(f"{jamming_state:<12}")
            if self.jamming_detection_jamming_status_checkbox.isChecked():
                row.append(f"{jamming_type:<12}")
            if self.jamming_detection_raw_data_checkbox.isChecked():
                row.append(line)

            jamming_detection_event_times_1.append("".join(row))

    if jamming_detection_event_times_1:
        self.result_label.setText(f"共找到 {len(jamming_detection_event_times_1) - 1} 个干扰状态事件")
        self.raw_data_display.setText("\n".join(jamming_detection_event_times_1))
    else:
        self.result_label.setText("未找到干扰状态事件")
        self.raw_data_display.setText("")

# 设备防拆告警
def process_device_tamper_warning(self, raw_data_string):
    header = []
    if self.device_tamper_warning_imei_checkbox.isChecked():
        header.append(f"{'IMEI':<20}")
    if self.device_tamper_warning_time_checkbox.isChecked():
        header.append(f"{'触发时间':<19}")
    if self.device_tamper_warning_raw_data_checkbox.isChecked():
        header.append(f"{'原始数据'}")

    device_tamper_warning_event_times_1 = ["".join(header)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "050C":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            row = []
            if self.device_tamper_warning_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.device_tamper_warning_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.device_tamper_warning_raw_data_checkbox.isChecked():
                row.append(line)

            device_tamper_warning_event_times_1.append("".join(row))

    if device_tamper_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(device_tamper_warning_event_times_1) - 1} 个设备防拆告警事件")
        self.raw_data_display.setText("\n".join(device_tamper_warning_event_times_1))
    else:
        self.result_label.setText("未找到设备防拆告警事件")
        self.raw_data_display.setText("")

def process_temperature_warning(self, raw_data_string):
    headers = []
    if self.temperature_warning_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.temperature_warning_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.temperature_warning_temperature_value_checkbox.isChecked():
        headers.append(f"{'温度值':<8}")
    if self.temperature_warning_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    temperature_warning_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "050D":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            temperature_value = round(int(line[118:122], 16) * 0.1 - 40, 1)   # 温度值，单位为摄氏度

            row = []
            if self.temperature_warning_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.temperature_warning_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.temperature_warning_temperature_value_checkbox.isChecked():
                row.append(f"{temperature_value:<11}")
            if self.temperature_warning_raw_data_checkbox.isChecked():
                row.append(line)

            temperature_warning_event_times_1.append("".join(row))

    if temperature_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(temperature_warning_event_times_1) - 1} 个温度告警事件")
        self.raw_data_display.setText("\n".join(temperature_warning_event_times_1))
    else:
        self.result_label.setText("未找到温度告警事件")
        self.raw_data_display.setText("")

# 气压告警信息
def process_air_pressure_warning(self, raw_data_string):
    headers = []
    if self.air_pressure_warning_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.air_pressure_warning_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.air_pressure_warning_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    air_pressure_warning_event_times_1 = ["".join(headers)]

    # for line in raw_data_string:
    #     if line[48:50] == "03" and line[58:62].upper() == "050E":
    #         imei = ascii_to_decimal(line[18:48])
    #         time_str = hex_to_beijing_time(line[62:70])
    #
    #         row = []
    #         if self.air_pressure_warning_imei_checkbox.isChecked():
    #             row.append(f"{imei:<20}")
    #         if self.air_pressure_warning_time_checkbox.isChecked():
    #             row.append(f"{time_str:<23}")
    #         if self.air_pressure_warning_raw_data_checkbox.isChecked():
    #             row.append(line)
    #
    #         air_pressure_warning_event_times_1.append("".join(row))

    if air_pressure_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(air_pressure_warning_event_times_1) - 1} 个气压告警事件")
        self.raw_data_display.setText("\n".join(air_pressure_warning_event_times_1))
    else:
        self.result_label.setText("未找到气压告警事件")
        self.raw_data_display.setText("")

# 冲击告警
def process_shock_warning(self, raw_data_string):
    headers = []
    if self.shock_warning_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.shock_warning_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.shock_warning_num_checkbox.isChecked():
        headers.append(f"{'NUM':<8}")
    if self.shock_warning_sensor_data_checkbox.isChecked():
        headers.append(f"{'冲击值':<10}")
    if self.shock_warning_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    shock_warning_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "050F":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            num = int(line[70:72], 16)
            sensor_data_list = []
            for i in range(num):
                # 每组传感器数据 6 字节 = 12 个字符
                start = 72 + i * 12
                end = start + 12
                data_hex = line[start:end]

                # X Y Z 三轴解析（2 字节/轴，有符号数）
                x = int(data_hex[0:4], 16)
                y = int(data_hex[4:8], 16)
                z = int(data_hex[8:12], 16)

                x = x - 65536 if x > 32767 else x
                y = y - 65536 if y > 32767 else y
                z = z - 65536 if z > 32767 else z

                # 把每组拼成小段字符串
                group_str = f"X:{x}mg,Y:{y}mg,Z:{z}mg"
                sensor_data_list.append(group_str)

            # 把所有组拼成 **一个完整字符串**
            sensor_data_str = "，".join(sensor_data_list)

            row = []
            if self.shock_warning_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.shock_warning_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.shock_warning_num_checkbox.isChecked():
                row.append(f"{num:<8}")
            if self.shock_warning_sensor_data_checkbox.isChecked():
                row.append(sensor_data_str)
            if self.shock_warning_raw_data_checkbox.isChecked():
                row.append(line)

            shock_warning_event_times_1.append("".join(row))

    if shock_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(shock_warning_event_times_1) - 1} 个冲击告警事件")
        self.raw_data_display.setText("\n".join(shock_warning_event_times_1))
    else:
        self.result_label.setText("未找到冲击告警事件")
        self.raw_data_display.setText("")

# 5.12 Humidity warning
def process_humidity_warning(self, raw_data_string):
    headers = []
    if self.humidity_warning_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.humidity_warning_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.humidity_warning_humidity_value_checkbox.isChecked():
        headers.append(f"{'湿度':<12}")
    if self.humidity_warning_raw_data_checkbox.isChecked():
        headers.append(f"{'Raw Data'}")

    humidity_warning_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0511":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            humidity_hex = line[118:122].upper()
            humidity_value = "FFFF" if humidity_hex == "FFFF" else round(int(humidity_hex, 16) * 0.1, 1)

            row = []
            if self.humidity_warning_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.humidity_warning_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.humidity_warning_humidity_value_checkbox.isChecked():
                row.append(f"{humidity_value:<14}")
            if self.humidity_warning_raw_data_checkbox.isChecked():
                row.append(line)

            humidity_warning_event_times_1.append("".join(row))

    if humidity_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(humidity_warning_event_times_1) - 1} 个湿度告警事件")
        self.raw_data_display.setText("\n".join(humidity_warning_event_times_1))
    else:
        self.result_label.setText("未找到湿度告警事件")
        self.raw_data_display.setText("")

def process_device_warning_message(self, raw_data_string):
    headers = []
    if self.device_warning_message_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.device_warning_message_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.device_warning_message_klv_data_checkbox.isChecked():
        headers.append(f"{'告警类型':<20}")
    if self.device_warning_message_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    device_warning_message_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0512":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            # ✅ 解析KLV（从第70位开始）
            valid_data_length = int(line[54:58], 16) * 2  # KLV数据的有效长度（单位是字节，所以乘以2）
            klv_source_data = line[118:58+valid_data_length]
            klv_data = parse_klv(klv_source_data)


            row = []
            if self.device_warning_message_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.device_warning_message_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.device_warning_message_klv_data_checkbox.isChecked():
                row.append(f"{klv_data:<20}")
            if self.device_warning_message_raw_data_checkbox.isChecked():
                row.append(line)

            device_warning_message_event_times_1.append("".join(row))

    if device_warning_message_event_times_1:
        self.result_label.setText(f"共找到 {len(device_warning_message_event_times_1) - 1} 个设备告警信息事件")
        self.raw_data_display.setText("\n".join(device_warning_message_event_times_1))
    else:
        self.result_label.setText("未找到设备告警信息")
        self.raw_data_display.setText("")

# 5.15 电子围栏告警
def process_fence_warning(self, raw_data_string):
    headers = []
    if self.fence_warning_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.fence_warning_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.fence_warning_id_checkbox.isChecked():
        headers.append(f"{'ID':<6}")
    if self.fence_warning_type_checkbox.isChecked():
        headers.append(f"{'Type':<8}")
    if self.fence_warning_location_checkbox.isChecked():
        headers.append(f"{'Location':<20}")
    if self.fence_warning_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    fence_warning_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0513":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            geo_id = str(line[70:72])

            warning_type_code = line[72:74]
            if warning_type_code == "00":
                warning_type = "进入"
            elif warning_type_code == "01":
                warning_type = "离开"
            else:
                warning_type = warning_type_code  # 其他值保持原始

            location_str = line[74:126]
            # 解析定位字符串
            location_str = line[74:126]
            gps_data = parse_gps_data(location_str)

            # 组合成友好格式
            location_show = (
                f"{gps_data['Time']} "
                f"[{gps_data['Longitude']:.6f}, {gps_data['Latitude']:.6f}] "
                f"Speed:{gps_data['GPS Speed']:.1f}"
            )


            row = []
            if self.fence_warning_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.fence_warning_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.fence_warning_id_checkbox.isChecked():
                row.append(f"{geo_id:<6}")
            if self.fence_warning_type_checkbox.isChecked():
                row.append(f"{warning_type:<6}")
            if self.fence_warning_location_checkbox.isChecked():
                row.append(f"{location_show:<20}")
            if self.fence_warning_raw_data_checkbox.isChecked():
                row.append(line)

            fence_warning_event_times_1.append("".join(row))

    if fence_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(fence_warning_event_times_1) - 1} 个电子围栏事件")
        self.raw_data_display.setText("\n".join(fence_warning_event_times_1))
    else:
        self.result_label.setText("未找到电子围栏事件")
        self.raw_data_display.setText("")


# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第六章：枪似游龙万兵手，命若黄泉不回头 —— 白龙
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# 休眠事件
def process_sleep_state(self, raw_data_string):
    headers = []
    if self.sleep_state_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.sleep_state_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.sleep_state_sleep_voltage_checkbox.isChecked():
        headers.append(f"{'休眠电压':<8}")
    if self.sleep_state_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    sleep_state_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0402":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            sleep_voltage = round(int(line[70:74], 16) * 0.1, 1)  # 电压

            row = []
            if self.sleep_state_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.sleep_state_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.sleep_state_sleep_voltage_checkbox.isChecked():
                row.append(f"{sleep_voltage:<12}")
            if self.sleep_state_raw_data_checkbox.isChecked():
                row.append(line)

            sleep_state_event_times_1.append("".join(row))

    if sleep_state_event_times_1:
        self.result_label.setText(f"共找到 {len(sleep_state_event_times_1) - 1} 个休眠状态事件")
        self.raw_data_display.setText("\n".join(sleep_state_event_times_1))
    else:
        self.result_label.setText("未找到休眠状态事件")
        self.raw_data_display.setText("")

# 唤醒状态
def process_wakeup_state(self, raw_data_string):
    headers = []
    if self.wakeup_state_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.wakeup_state_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.wakeup_state_wakeup_voltage_checkbox.isChecked():
        headers.append(f"{'唤醒电压':<8}")
    if self.wakeup_state_wakeup_type_checkbox.isChecked():
        headers.append(f"{'唤醒类型':<31}")
    if self.wakeup_state_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    wakeup_state_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0403":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            wakeup_voltage = round(int(line[70:74], 16) * 0.1, 1)
            wakeup_state_hex = line[74:76]
            if wakeup_state_hex == "01":
                wakeup_state = "Time wakeup"
            elif wakeup_state_hex == "03":
                wakeup_state = "main battery voltage"
            elif wakeup_state_hex == "04":
                wakeup_state = "busline"
            elif wakeup_state_hex == "05":
                wakeup_state = "vibration"
            elif wakeup_state_hex == "06":
                wakeup_state = " low voltage"
            elif wakeup_state_hex == "11":
                wakeup_state = "backup battery"
            elif wakeup_state_hex == "12":
                wakeup_state = "ACC"
            elif wakeup_state_hex == "13":
                wakeup_state = "optical sensor - device tamper"
            elif wakeup_state_hex == "14":
                wakeup_state = "butten"
            elif wakeup_state_hex == "15":
                wakeup_state = "optical sensor - ambient light"
            elif wakeup_state_hex == "16":
                wakeup_state = "MDM - RING"
            else:
                wakeup_state = "unknown"

            row = []
            if self.wakeup_state_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.wakeup_state_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.wakeup_state_wakeup_voltage_checkbox.isChecked():
                row.append(f"{wakeup_voltage:<12}")
            if self.wakeup_state_wakeup_type_checkbox.isChecked():
                row.append(f"{wakeup_state:<35}")
            if self.wakeup_state_raw_data_checkbox.isChecked():
                row.append(line)

            wakeup_state_event_times_1.append("".join(row))

    if wakeup_state_event_times_1:
        self.result_label.setText(f"共找到 {len(wakeup_state_event_times_1) - 1} 个唤醒状态事件")
        self.raw_data_display.setText("\n".join(wakeup_state_event_times_1))
    else:
        self.result_label.setText("未找到唤醒状态事件")
        self.raw_data_display.setText("")

# 长时间无法定位
def process_gps_not_fix(self, raw_data_string):
    headers = []
    if self.gps_not_fix_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.gps_not_fix_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.gps_not_fix_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    gps_not_fix_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0404":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            row = []
            if self.gps_not_fix_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.gps_not_fix_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.gps_not_fix_raw_data_checkbox.isChecked():
                row.append(line)

            gps_not_fix_event_times_1.append("".join(row))

    if gps_not_fix_event_times_1:
        self.result_label.setText(f"共找到 {len(gps_not_fix_event_times_1) - 1} 个长时间无法定位事件")
        self.raw_data_display.setText("\n".join(gps_not_fix_event_times_1))
    else:
        self.result_label.setText("未找到长时间无法定位事件")
        self.raw_data_display.setText("")

# 重启事件
def process_reboot_event(self, raw_data_string):
    headers = []
    if self.reboot_event_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.reboot_event_power_on_time_checkbox.isChecked():
        headers.append(f"{'上电时间':<19}")
    if self.reboot_event_power_off_time_checkbox.isChecked():
        headers.append(f"{'断电时间':<19}")
    if self.reboot_event_reboot_reason_checkbox.isChecked():
        headers.append(f"{'重启原因':<31}")
    if self.reboot_event_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    reboot_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0405":
            imei = ascii_to_decimal(line[18:48])
            power_on_time = hex_to_beijing_time(line[62:70])
            power_off_time = hex_to_beijing_time(line[70:78])
            reboot_reason_hex = line[78:80].upper()
            reboot_reason_map = {
                "00": "正常重启",
                "01": "software dog",
                "02": "upgrade",
                "03": "plugged",
                "04": "reboot key",
                "06": "SMS",
                "07": "SMS rsest",
                "08": "flash reboot",
                "09": "flash reset",
                "0A": "5th sleep",
                "0B": "Platform reboot",
                "0C": "Platform reset",
                "0D": "7 days",
                "0F": "AT CMD FAIL",
                "10": "长时间与服务器失联",
                "11": "长时间无法锁定任务",
                "40": "GPS线程异常",
                "41": "OBD线程异常",
                "42": "通信线程异常",
                "43": "休眠唤醒线程异常",
                "44": "其他线程异常",
                "45": "optical sensor - device tamper",
                "46": "by butten",
                "47": "optical sensor - ambient light",
                "48": "定时重启",
                "49": "workmode switch",
                "4A": "vibration"
            }

            reboot_reason = reboot_reason_map.get(reboot_reason_hex.upper(), "N/A")

            row = []
            if self.reboot_event_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.reboot_event_power_on_time_checkbox.isChecked():
                row.append(f"{power_on_time:<23}")
            if self.reboot_event_power_off_time_checkbox.isChecked():
                row.append(f"{power_off_time:<23}")
            if self.reboot_event_reboot_reason_checkbox.isChecked():
                row.append(f"{reboot_reason:<35}")
            if self.reboot_event_raw_data_checkbox.isChecked():
                row.append(line)

            reboot_event_times_1.append("".join(row))

    if reboot_event_times_1:
        self.result_label.setText(f"共找到 {len(reboot_event_times_1) - 1} 个重启事件")
        self.raw_data_display.setText("\n".join(reboot_event_times_1))
    else:
        self.result_label.setText("未找到重启事件")
        self.raw_data_display.setText("")

# MCU升级状态
def process_mcu_upgrade_state(self, raw_data_string):
    headers = []
    if self.mcu_upgrade_state_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.mcu_upgrade_state_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.mcu_upgrade_state_upgrade_state_checkbox.isChecked():
        headers.append(f"{'升级状态':<31}")
    if self.mcu_upgrade_state_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    mcu_upgrade_state_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0406":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            upgrade_status_hex = line[70:72].upper()
            upgrade_status_map = {
                "00": "success",
                "01": "已下载，等待更新",
                "11": "failure，帧的CRC校验错误",
                "12": "failure，文件的CRC校验错误",
                "21": "failure，文件名验证错误",
                "22": "failure，长度错误",
                "31": "failure，与硬件不匹配",
                "32": "failure，超过2分钟未更新数据",
                "33": "failure，请求错误，3小时后终止任务",
                "34": "failure，服务器终止任务",
                "35": "failure，电压过低",
            }
            upgrade_status = upgrade_status_map.get(upgrade_status_hex, "N/A")

            row = []
            if self.mcu_upgrade_state_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.mcu_upgrade_state_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.mcu_upgrade_state_upgrade_state_checkbox.isChecked():
                row.append(f"{upgrade_status:<35}")
            if self.mcu_upgrade_state_raw_data_checkbox.isChecked():
                row.append(line)

            mcu_upgrade_state_event_times_1.append("".join(row))

    if mcu_upgrade_state_event_times_1:
        self.result_label.setText(f"共找到 {len(mcu_upgrade_state_event_times_1) - 1} 个MCU升级状态事件")
        self.raw_data_display.setText("\n".join(mcu_upgrade_state_event_times_1))
    else:
        self.result_label.setText("未找到MCU升级状态事件")
        self.raw_data_display.setText("")

# 短信消息
def process_sms(self, raw_data_string):
    headers = []
    if self.sms_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.sms_utc_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.sms_sms_time_checkbox.isChecked():
        headers.append(f"{'短信时间':<19}")
    if self.sms_phone_num_checkbox.isChecked():
        headers.append(f"{'电话号码':<19}")
    if self.sms_encoding_checkbox.isChecked():
        headers.append(f"{'编码格式':<10}")
    if self.sms_message_checkbox.isChecked():
        headers.append(f"{'消息':<19}")
    if self.sms_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    sms_event_time_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "040B":
            imei = ascii_to_decimal(line[18:48])
            utc_time = hex_to_beijing_time(line[62:70])
            sms_time = hex_to_beijing_time(line[70:78])

            ptr = 78

            # 1. 手机号长度 N (1字节 HEX)
            phone_len_hex = line[ptr:ptr + 2]
            phone_len = int(phone_len_hex, 16)
            ptr += 2  # 长度字段固定占1字节

            # 2. 手机号（长度 N 字节）
            phone_number = ""
            if phone_len > 0:
                phone_hex = line[ptr:ptr + phone_len * 2]
                phone_number = bytes.fromhex(phone_hex).decode("utf-8")
                ptr += phone_len * 2

            # 3. SMS编码长度 N1 (1字节 HEX)
            sms_enc_len_hex = line[ptr:ptr + 2]
            sms_enc_len = int(sms_enc_len_hex, 16)
            ptr += 2

            # 4. SMS编码（长度 N1 字节）
            sms_encoding = ""
            if sms_enc_len > 0:
                enc_hex = line[ptr:ptr + sms_enc_len * 2]
                sms_encoding = bytes.fromhex(enc_hex).decode("utf-8")
                ptr += sms_enc_len * 2

            # 5. SMS内容长度 N2 (2字节 HEX，协议写的是两个字节)
            sms_msg_len_hex = line[ptr:ptr + 4]
            sms_msg_len = int(sms_msg_len_hex, 16)
            ptr += 4

            # 6. SMS内容（长度 N2 字节）
            sms_message = ""
            if sms_msg_len > 0:
                msg_hex = line[ptr:ptr + sms_msg_len * 2]
                sms_message = bytes.fromhex(msg_hex).decode("utf-8")
                ptr += sms_msg_len * 2

            # 7. SMS是否结束标记 (1字节 HEX)
            sms_end_hex = line[ptr:ptr + 2]
            end_status = "end" if sms_end_hex == "00" else "not end" if sms_end_hex == "01" else "unknown"

            row = []
            if self.sms_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.sms_utc_time_checkbox.isChecked():
                row.append(f"{utc_time:<23}")
            if self.sms_sms_time_checkbox.isChecked():
                row.append(f"{sms_time:<23}")
            if self.sms_phone_num_checkbox.isChecked():
                row.append(f"{phone_number:<23}")
            if self.sms_encoding_checkbox.isChecked():
                row.append(f"{sms_encoding:<14}")
            if self.sms_message_checkbox.isChecked():
                row.append(f"{sms_message:<23}")
            if self.sms_raw_data_checkbox.isChecked():
                row.append(line)

            sms_event_time_1.append("".join(row))

    if sms_event_time_1:
        self.result_label.setText(f"共找到 {len(sms_event_time_1) - 1} 个SMS事件")
        self.raw_data_display.setText("\n".join(sms_event_time_1))
    else:
        self.result_label.setText("未找到SMS事件")
        self.raw_data_display.setText("")


# 设备信息
def process_device_info(self, raw_data_string):
    device_info_header_fields = [
        ("device_info_imei_checkbox", "IMEI", 20),
        ("device_info_time_checkbox", "触发时间", 19),
        ("device_info_phone_number_checkbox", "号码", 14),
        ("device_info_iccid_checkbox", "ICCID", 22),
        ("device_info_imsi_checkbox", "IMSI", 17),
        ("device_info_wifi_mac_checkbox", "WIFI MAC", 19),
        ("device_info_bt_mac_checkbox", "BT MAC", 19),
        ("device_info_wifi_mac_5g_checkbox", "WIFI MAC 5G", 19),
        ("device_info_softerware_ble_version_checkbox", "BLE VER", 25),
        ("device_info_softerware_gnss_version_checkbox", "GNSS VER", 25),
        ("device_info_softerware_boot_version_checkbox", "BOOT VER", 25),
        ("device_info_softerware_ap_version_checkbox", "AP VER", 25),
        ("device_info_mcc_checkbox", "MCC", 6),
        ("device_info_mnc_checkbox", "MNC", 6),
        ("device_info_cfg_file_version_checkbox", "CFG VER", 10),
        ("device_info_gl103_workmode_checkbox", "103 MODE", 20),
        ("device_info_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]
    headers = []
    for attr, label, width in device_info_header_fields:
        checkbox = getattr(self, attr)
        if checkbox.isChecked():
            if width:
                headers.append(f"{label:<{width}}")
            else:
                headers.append(label)

    device_info_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "040C":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])

            phone_number_len = int(line[70:72], 16)
            phone_number_str = line[72:72 + phone_number_len * 2]
            phone_number = ascii_to_decimal(phone_number_str) if phone_number_len != 0 else "N/A"
            # phone_number = ascii_to_decimal(phone_number_str)

            end_phone_number = 72 + phone_number_len * 2

            iccid_len_str = line[end_phone_number:end_phone_number + 2]
            iccid_len = int(iccid_len_str, 16)
            iccid_str = line[end_phone_number + 2:end_phone_number + 2 + iccid_len * 2]
            iccid = ascii_to_decimal(iccid_str) if iccid_len != 0 else "N/A"
            # iccid = ascii_to_decimal(iccid_str)

            end_iccid = end_phone_number + 2 + iccid_len * 2

            imsi_len_str = line[end_iccid:end_iccid + 2]
            imsi_len = int(imsi_len_str, 16)
            imsi_str = line[end_iccid + 2:end_iccid + 2 + imsi_len * 2]
            imsi = ascii_to_decimal(imsi_str) if imsi_len != 0 else "N/A"
            # imsi = ascii_to_decimal(imsi_str)

            end_imsi = end_iccid + 2 + imsi_len * 2

            wifi_mac_len_hex = line[end_imsi:end_imsi + 2]
            wifi_mac_len = int(wifi_mac_len_hex, 16)
            wifi_mac_str = line[end_imsi + 2:end_imsi + 2 + wifi_mac_len * 2]
            wifi_mac = ascii_to_decimal(wifi_mac_str) if wifi_mac_len != 0 else "N/A"
            # wifi_mac = ascii_to_decimal(wifi_mac_str)

            end_wifi_mac = end_imsi + 2 + wifi_mac_len * 2

            bt_mac_len_hex = line[end_wifi_mac:end_wifi_mac + 2]
            bt_mac_len = int(bt_mac_len_hex, 16)
            bt_mac_str = line[end_wifi_mac + 2:end_wifi_mac + 2 + bt_mac_len * 2]
            bt_mac = ascii_to_decimal(bt_mac_str) if bt_mac_len != 0 else "N/A"
            # bt_mac = ascii_to_decimal(bt_mac_str)

            end_bt_mac = end_wifi_mac + 2 + bt_mac_len * 2

            wifi_mac_5g_len_hex = line[end_bt_mac:end_bt_mac + 2]
            wifi_mac_5g_len = int(wifi_mac_5g_len_hex, 16)
            wifi_mac_5g_str = line[end_bt_mac + 2:end_bt_mac + 2 + wifi_mac_5g_len * 2]
            wifi_mac_5g = ascii_to_decimal(wifi_mac_5g_str) if wifi_mac_5g_len != 0 else "N/A"
            # wifi_mac_5g = ascii_to_decimal(wifi_mac_5g_str)

            end_wifi_mac_5g = end_bt_mac + 2 + wifi_mac_5g_len * 2

            software_ble_version_len_hex = line[end_wifi_mac_5g:end_wifi_mac_5g + 2]
            software_ble_version_len_bit = format(int(software_ble_version_len_hex, 16), '08b')
            low_6_bits_ble = software_ble_version_len_bit[-6:]  # 取第5到第0位（低6位）
            software_ble_version_len_result = int(low_6_bits_ble, 2)
            software_ble_version_str = line[
                                       end_wifi_mac_5g + 2:end_wifi_mac_5g + 2 + software_ble_version_len_result * 2]
            software_ble_version = ascii_to_decimal(
                software_ble_version_str) if software_ble_version_len_result != 0 else "N/A"
            # software_ble_version = ascii_to_decimal(software_ble_version_str)

            end_ble_version = end_wifi_mac_5g + 2 + software_ble_version_len_result * 2

            software_gnss_version_len_hex = line[end_ble_version:end_ble_version + 2]
            software_gnss_version_len_bit = format(int(software_gnss_version_len_hex, 16), '08b')
            low_6_bits_gnss = software_gnss_version_len_bit[-6:]
            software_gnss_version_len_result = int(low_6_bits_gnss, 2)
            software_gnss_version_str = line[
                                        end_ble_version + 2:end_ble_version + 2 + software_gnss_version_len_result * 2]
            software_gnss_version = ascii_to_decimal(
                software_gnss_version_str) if software_gnss_version_len_result != 0 else "N/A"
            # software_gnss_version = ascii_to_decimal(software_gnss_version_str)

            end_gnss_version = end_ble_version + 2 + software_gnss_version_len_result * 2

            software_boot_version_len_hex = line[end_gnss_version:end_gnss_version + 2]
            software_boot_version_len_bit = format(int(software_boot_version_len_hex, 16), '08b')
            low_6_bits_boot = software_boot_version_len_bit[-6:]
            software_boot_version_len_result = int(low_6_bits_boot, 2)
            software_boot_version_str = line[
                                        end_gnss_version + 2:end_gnss_version + 2 + software_boot_version_len_result * 2]
            software_boot_version = ascii_to_decimal(
                software_boot_version_str) if software_boot_version_len_result != 0 else "N/A"
            # software_boot_version = ascii_to_decimal(software_boot_version_str)

            end_boot_version = end_gnss_version + 2 + software_boot_version_len_result * 2
            software_ap_version_len_hex = line[end_boot_version:end_boot_version + 2]
            software_ap_version_len_bit = format(int(software_ap_version_len_hex, 16), '08b')
            low_6_bits_ap = software_ap_version_len_bit[-6:]
            software_ap_version_len_result = int(low_6_bits_ap, 2)
            software_ap_version_str = line[
                                      end_boot_version + 2:end_boot_version + 2 + software_ap_version_len_result * 2]
            software_ap_version = ascii_to_decimal(
                software_ap_version_str) if software_ap_version_len_result != 0 else "N/A"
            # software_ap_version = ascii_to_decimal(software_ap_version_str)

            end_ap_version = end_boot_version + 2 + software_ap_version_len_result * 2

            mcc_str = line[end_ap_version:end_ap_version + 6]
            if mcc_str:
                try:
                    mcc = ascii_to_decimal(mcc_str)
                except (ValueError, UnicodeDecodeError):
                    mcc = mcc_str
            else:
                mcc = mcc_str
            # mcc = ascii_to_decimal(mcc_str)

            mnc_len = line[end_ap_version + 6:end_ap_version + 6 + 2]
            mnc_str = line[end_ap_version + 6 + 2:end_ap_version + 6 + 2 + int(mnc_len, 16) * 2]
            if mnc_str:
                try:
                    mnc = ascii_to_decimal(mnc_str)
                except (ValueError, UnicodeDecodeError):
                    mnc = mnc_str
            else:
                mnc = mnc_str
            # mnc = ascii_to_decimal(mnc_str)

            end_mnc = end_ap_version + 6 + 2 + int(mnc_len, 16) * 2

            cfg_file_version_len = line[end_mnc:end_mnc + 2]
            cfg_file_version_len_bit = format(int(cfg_file_version_len, 16), '08b')
            low_6_bits_cfg = cfg_file_version_len_bit[-6:]
            cfg_file_version_len_result = int(low_6_bits_cfg, 2)
            cfg_file_version_str = line[end_mnc + 2:end_mnc + 2 + cfg_file_version_len_result * 2]
            cfg_file_version = ascii_to_decimal(cfg_file_version_str) if cfg_file_version_len_result != 0 else "N/A"
            # cfg_file_version = ascii_to_decimal(cfg_file_version_str)

            gl103_workmode_str = line[
                                 end_mnc + 2 + cfg_file_version_len_result * 2:end_mnc + 2 + cfg_file_version_len_result * 2 + 2]
            if gl103_workmode_str == "01":
                gl103_workmode = "mode 1"
            elif gl103_workmode_str == "02":
                gl103_workmode = "mode 2"
            elif gl103_workmode_str == "03":
                gl103_workmode = "mode 3"
            elif gl103_workmode_str == "04":
                gl103_workmode = "mode 4"
            elif gl103_workmode_str.upper() == "FF":
                gl103_workmode = "Not Applicable"
            else:
                gl103_workmode = gl103_workmode_str

            device_info_tail_fields = [
                (self.device_info_imei_checkbox, imei, 20),
                (self.device_info_time_checkbox, time_str, 23),
                (self.device_info_phone_number_checkbox, phone_number, 16),
                (self.device_info_iccid_checkbox, iccid, 22),
                (self.device_info_imsi_checkbox, imsi, 17),
                (self.device_info_wifi_mac_checkbox, wifi_mac, 19),
                (self.device_info_bt_mac_checkbox, bt_mac, 19),
                (self.device_info_wifi_mac_5g_checkbox, wifi_mac_5g, 19),
                (self.device_info_softerware_ble_version_checkbox, software_ble_version, 25),
                (self.device_info_softerware_gnss_version_checkbox, software_gnss_version, 25),
                (self.device_info_softerware_boot_version_checkbox, software_boot_version, 25),
                (self.device_info_softerware_ap_version_checkbox, software_ap_version, 25),
                (self.device_info_mcc_checkbox, mcc, 6),
                (self.device_info_mnc_checkbox, mnc, 6),
                (self.device_info_cfg_file_version_checkbox, cfg_file_version, 10),
                (self.device_info_gl103_workmode_checkbox, gl103_workmode, 20),
                (self.device_info_raw_data_checkbox, line, 100),
            ]

            row = []
            for checkbox, value, width in device_info_tail_fields:
                if checkbox.isChecked():
                    row.append(f"{value:<{width}}")

            if self.device_info_raw_data_checkbox.isChecked():
                row.append(line)

            device_info_event_times_1.append("".join(row))

    if device_info_event_times_1:
        self.result_label.setText(f"共找到 {len(device_info_event_times_1) - 1} 个设备信息事件")
        self.raw_data_display.setText("\n".join(device_info_event_times_1))
    else:
        self.result_label.setText("未找到设备信息事件")
        self.raw_data_display.setText("")

# sensor_normal 事件
def process_sensor_normal(self, raw_data_string):
    sensor_normal_header_fields = [
        ("sensor_normal_imei_checkbox", "IMEI", 20),
        ("sensor_normal_time_checkbox", "触发时间", 19),
        ("sensor_normal_time_interval_checkbox", "时间间隔", 6),
        ("sensor_normal_sensor_status_checkbox", "状态", 12),
        ("sensor_normal_number_checkbox", "sensor数量", 12),
        ("sensor_normal_x_axis_checkbox", "X轴", 8),
        ("sensor_normal_y_axis_checkbox", "Y轴", 8),
        ("sensor_normal_z_axis_checkbox", "Z轴", 8),
        ("sensor_normal_rpm_checkbox", "转速", 8),
        ("sensor_normal_speed_checkbox", "车速", 8),
        ("sensor_normal_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]

    headers = build_checkbox(sensor_normal_header_fields, self)

    sensor_normal_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "040D":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            time_interval = int(line[70:74], 16)
            sensor_status_hex = line[74:76]
            sensor_status_map = {
                "00": "Not Cal",
                "01": "learning",
                "02": "success"
            }
            sensor_status = sensor_status_map.get(sensor_status_hex, "N/A")

            sensor_number = int(line[76:78], 16)
            if sensor_number == 0:
                sensor_normal_event_times_1.append("未找到sensor_normal事件")
                continue

            for i in range(sensor_number):
                start = 78 + i * 28 * 2
                end = start + 56
                sensor_data = line[start:end]
                x_axis = parse_signed_16bit(sensor_data[0:4])
                y_axis = parse_signed_16bit(sensor_data[4:8])
                z_axis = parse_signed_16bit(sensor_data[8:12])
                rpm = int(sensor_data[12:16], 16)
                speed = int(sensor_data[16:20], 16)

                sensor_normal_tail_fields = [
                    ("sensor_normal_imei_checkbox", imei, 20),
                    ("sensor_normal_time_checkbox", time_str, 23),
                    ("sensor_normal_time_interval_checkbox", time_interval, 10),
                    ("sensor_normal_sensor_status_checkbox", sensor_status, 14),
                    ("sensor_normal_number_checkbox", sensor_number, 14),
                    ("sensor_normal_x_axis_checkbox", x_axis, 9),
                    ("sensor_normal_y_axis_checkbox", y_axis, 9),
                    ("sensor_normal_z_axis_checkbox", z_axis, 9),
                    ("sensor_normal_rpm_checkbox", rpm, 10),
                    ("sensor_normal_speed_checkbox", speed, 10),
                    ("sensor_normal_raw_data_checkbox", line, 100),
                ]

                row = build_checkbox(sensor_normal_tail_fields, self)

                sensor_normal_event_times_1.append("".join(row))

    if sensor_normal_event_times_1:
        self.result_label.setText(f"共找到 {len(sensor_normal_event_times_1) - 1} 个sensor_normal事件")
        self.raw_data_display.setText("\n".join(sensor_normal_event_times_1))
    else:
        self.result_label.setText("未找到sensor_normal事件")
        self.raw_data_display.setText("")

# sensor_event 事件
def process_sensor_event(self, raw_data_string):
    sensor_event_header_fields = [
        ("sensor_event_imei_checkbox", "IMEI", 20),
        ("sensor_event_time_checkbox", "上报时间", 19),
        ("sensor_event_happen_time_checkbox", "发生时间", 19),
        ("sensor_event_event_time_checkbox", "事件时间(ms)", 10),
        ("sensor_event_collection_time_checkbox", "采集时间", 19),
        ("sensor_event_collection_time_ms_checkbox", "采集时间(ms)", 10),
        ("sensor_event_time_interval_checkbox", "时间间隔", 6),
        ("sensor_event_event_type_checkbox", "事件类型", 6),
        ("sensor_event_sensor_state_checkbox", "状态", 12),
        ("sensor_event_sensor_num_checkbox", "sensor数量", 12),
        ("sensor_event_x_axis_checkbox", "X轴", 8),
        ("sensor_event_y_axis_checkbox", "Y轴", 8),
        ("sensor_event_z_axis_checkbox", "Z轴", 8),
        ("sensor_event_rpm_checkbox", "转速", 8),
        ("sensor_event_speed_checkbox", "车速", 8),
        ("sensor_event_raw_data_checkbox", "原始数据", 100),
    ]

    headers = build_checkbox(sensor_event_header_fields, self)

    sensor_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "040E":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            happen_time = hex_to_beijing_time(line[70:78])
            event_time = int(line[78:82], 16)
            collection_time = hex_to_beijing_time(line[82:90])
            collection_time_ms = int(line[90:94], 16)
            time_interval = int(line[94:98], 16)
            event_type_hex = line[98:100]
            event_type_map = {
                "00": "Acc",
                "01": "Dec",
                "02": "Turn",
                "03": "Crash",
            }
            event_type = event_type_map.get(event_type_hex, "N/A")
            sensor_status_hex = line[100:102]
            sensor_status_map = {
                "00": "Not",
                "01": "learning",
                "02": "success"
            }
            sensor_status = sensor_status_map.get(sensor_status_hex, "N/A")
            sensor_number = int(line[102:104], 16)
            if sensor_number == 0:
                sensor_event_times_1.append("未找到sensor_event事件")
                continue
            for i in range(sensor_number):
                start = 104 + i * 10 * 2
                end = start + 20
                sensor_data = line[start:end]

                x_axis = parse_signed_16bit(sensor_data[0:4])
                y_axis = parse_signed_16bit(sensor_data[4:8])
                z_axis = parse_signed_16bit(sensor_data[8:12])
                rpm = int(sensor_data[12:16], 16)
                speed = int(sensor_data[16:20], 16)

                sensor_event_tail_fields = [
                    ("sensor_event_imei_checkbox", imei, 20),
                    ("sensor_event_time_checkbox", time_str, 23),
                    ("sensor_event_happen_time_checkbox", happen_time, 23),
                    ("sensor_event_event_time_checkbox", event_time, 14),
                    ("sensor_event_collection_time_checkbox", collection_time, 23),
                    ("sensor_event_collection_time_ms_checkbox", collection_time_ms, 14),
                    ("sensor_event_time_interval_checkbox", time_interval, 10),
                    ("sensor_event_event_type_checkbox", event_type, 10),
                    ("sensor_event_sensor_state_checkbox", sensor_status, 14),
                    ("sensor_event_sensor_num_checkbox", sensor_number, 14),
                    ("sensor_event_x_axis_checkbox", x_axis, 9),
                    ("sensor_event_y_axis_checkbox", y_axis, 9),
                    ("sensor_event_z_axis_checkbox", z_axis, 9),
                    ("sensor_event_rpm_checkbox", rpm, 10),
                    ("sensor_event_speed_checkbox", speed, 10),
                    ("sensor_event_raw_data_checkbox", line, 100),
                ]

                row = build_checkbox(sensor_event_tail_fields, self)

                sensor_event_times_1.append("".join(row))
    if sensor_event_times_1:
        self.result_label.setText(f"共找到 {len(sensor_event_times_1) - 1} 个sensor_event事件")
        self.raw_data_display.setText("\n".join(sensor_event_times_1))
    else:
        self.result_label.setText("未找到sensor_event事件")
        self.raw_data_display.setText("")

# 继电器控制状态
def process_relay_control_status(self, raw_data_string):
    relay_control_status_header_fields = [
        ("relay_control_status_imei_checkbox", "IMEI", 20),
        ("relay_control_status_time_checkbox", "上报时间", 19),
        ("relay_control_status_relay_control_status_checkbox", "控制状态", 12),
        ("relay_control_status_event_trigger_reason_checkbox", "原因", 20),
        ("relay_control_status_ibutton_id_checkbox", "iButton ID", 20),
        ("relay_control_status_rfid_id_checkbox", "RFID ID", 14),
        ("relay_control_status_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]
    headers = build_checkbox(relay_control_status_header_fields, self)
    relay_control_status_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0414":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            relay_control_status_hex = line[70:72]
            relay_control_status_map = {
                "00": "恢复",
                "01": "切断",
            }
            relay_control_status = relay_control_status_map.get(relay_control_status_hex, "N/A")

            event_trigger_reason_hex = line[120:122]
            event_trigger_reason_map = {
                "00": "属iButton白名单",
                "01": "平台命令",
                "02": "属RFID白名单",
                "03": "熄火断开",
                "04": "工具断开",
            }
            event_trigger_reason = event_trigger_reason_map.get(event_trigger_reason_hex, "N/A")

            ibutton_id = line[122:138].upper()
            rfid_id = line[138:146].upper()

            relay_control_status_tail_fields = [
                ("relay_control_status_imei_checkbox", imei, 20),
                ("relay_control_status_time_checkbox", time_str, 23),
                ("relay_control_status_relay_control_status_checkbox", relay_control_status, 14),
                ("relay_control_status_event_trigger_reason_checkbox", event_trigger_reason, 18),
                ("relay_control_status_ibutton_id_checkbox", ibutton_id, 20),
                ("relay_control_status_rfid_id_checkbox", rfid_id, 14),
                ("relay_control_status_raw_data_checkbox", line, 100),
            ]
            row = build_checkbox(relay_control_status_tail_fields, self)
            relay_control_status_event_times_1.append("".join(row))

    if relay_control_status_event_times_1:
        self.result_label.setText(f"共找到 {len(relay_control_status_event_times_1) - 1} 个继电器控制状态事件")
        self.raw_data_display.setText("\n".join(relay_control_status_event_times_1))
    else:
        self.result_label.setText("未找到继电器控制状态事件")
        self.raw_data_display.setText("")

# 自学习状态监测
def process_self_learning_status(self,raw_data_string):
    headers = []
    if self.self_learning_status_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.self_learning_status_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.self_learning_status_calibration_status_checkbox.isChecked():
        headers.append(f"{'学习状态':<19}")
    if self.self_learning_status_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据':<20}")

    self_learning_status_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0407":
            imei = ascii_to_decimal(line[18:48])
            report_time = hex_to_beijing_time(line[62:70])
            calibration_status_hex = line[70:72]
            calibration_status = "learning success" if calibration_status_hex == "01" else "unknown"

            row = []

            if self.self_learning_status_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.self_learning_status_time_checkbox.isChecked():
                row.append(f"{report_time:<23}")
            if self.self_learning_status_calibration_status_checkbox.isChecked():
                row.append(f"{calibration_status:<23}")
            if self.self_learning_status_raw_data_checkbox.isChecked():
                row.append(line)

            self_learning_status_event_times_1.append("".join(row))

    if self_learning_status_event_times_1:
        self.result_label.setText(f"共找到 {len(self_learning_status_event_times_1) - 1} 个自学习事件")
        self.raw_data_display.setText("\n".join(self_learning_status_event_times_1))
    else:
        self.result_label.setText("未找到自学习事件")
        self.raw_data_display.setText("")

# 博世碰撞事件
def process_bosch_crash_data(self, raw_data_string):
    bosch_crash_header_fields = [
        ("bosch_crash_imei_checkbox", "IMEI", 20),
        ("bosch_crash_report_time_checkbox", "触发时间", 19),
        ("bosch_crash_event_time_checkbox", "事件时间", 19),
        ("bosch_crash_crash_index_checkbox", "碰撞指数", 12),
        ("bosch_crash_crash_status_checkbox", "碰撞状态", 12),
        ("bosch_crash_crash_event_counter_checkbox", "事件计数器", 18),
        ("bosch_crash_crash_frame_counter_checkbox", "事件结构", 18),
        ("bosch_crash_error_status_checkbox", "错误状态", 12),
        ("bosch_crash_raw_data_checkbox", "原始数据", 100),
    ]
    headers = build_checkbox(bosch_crash_header_fields, self)
    bosch_crash_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0410":
            imei = ascii_to_decimal(line[18:48])
            report_time = hex_to_beijing_time(line[62:70])
            event_time = hex_to_beijing_time(line[70:78])
            crash_index = int(line[78:80], 16)
            crash_status = line[80:82]
            crash_event_counter = line[82:84]
            crash_frame_counter = line[84:86]
            error_status_hex = line[86:88]
            error_status_map = {
                "00": "SUCCESS",
                "01": "SIGNAL",
                "02": "ERROR",
            }
            print(error_status_hex,"error_status_hex")
            error_status = error_status_map.get(error_status_hex, "N/A")


            bosch_crash_tail_fields = [
                ("bosch_crash_imei_checkbox", imei, 20),
                ("bosch_crash_report_time_checkbox", report_time, 23),
                ("bosch_crash_event_time_checkbox", event_time, 23),
                ("bosch_crash_crash_index_checkbox", crash_index, 16),
                ("bosch_crash_crash_status_checkbox", crash_status, 16),
                ("bosch_crash_crash_event_counter_checkbox", crash_event_counter, 23),
                ("bosch_crash_crash_frame_counter_checkbox", crash_frame_counter, 22),
                ("bosch_crash_error_status_checkbox", error_status, 16),
                ("bosch_crash_raw_data_checkbox", line, 100),
            ]
            row = build_checkbox(bosch_crash_tail_fields, self)
            bosch_crash_event_times_1.append("".join(row))

    if bosch_crash_event_times_1:
        self.result_label.setText(f"共找到 {len(bosch_crash_event_times_1) - 1} 个博世碰撞事件")
        self.raw_data_display.setText("\n".join(bosch_crash_event_times_1))
    else:
        self.result_label.setText("未找到博世碰撞事件")
        self.raw_data_display.setText("")


# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第七章：有过痛苦方知众生痛苦，有过牵挂，了无牵挂，若是修佛先修心，一枪风雪一枪冰 —— 望穿
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# 7.1
def process_request_mcu_update_package_tcp(self, raw_data_string):
    headers = []
    if self.request_mcu_update_package_tcp_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.request_mcu_update_package_tcp_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.request_mcu_update_package_tcp_file_name_length_checkbox.isChecked():
        headers.append(f"{'长度':<6}")
    if self.request_mcu_update_package_tcp_file_name_checkbox.isChecked():
        headers.append(f"{'文件名':<6}")
    if self.request_mcu_update_package_tcp_staring_position_checkbox.isChecked():
        headers.append(f"{'起始位置':<8}")
    if self.request_mcu_update_package_tcp_request_length_bytes_checkbox.isChecked():
        headers.append(f"{'数据长度':<8}")
    if self.request_mcu_update_package_tcp_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    mcu_update_package_tcp_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "F001":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            file_name_len = int(line[70:72], 16)
            file_name = ascii_to_decimal(line[72:72 + file_name_len * 2]) if file_name_len != 0 else "N/A"
            offset = 72 + file_name_len * 2
            starting_position = (line[offset:offset + 8]).upper()
            offset += 8
            request_length_bytes = int(line[offset:offset + 4], 16)

            row = []
            if self.request_mcu_update_package_tcp_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.request_mcu_update_package_tcp_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.request_mcu_update_package_tcp_file_name_length_checkbox.isChecked():
                row.append(f"{file_name_len:<8}")
            if self.request_mcu_update_package_tcp_file_name_checkbox.isChecked():
                row.append(f"{file_name:<9}")
            if self.request_mcu_update_package_tcp_staring_position_checkbox.isChecked():
                row.append(f"{starting_position:<12}")
            if self.request_mcu_update_package_tcp_request_length_bytes_checkbox.isChecked():
                row.append(f"{request_length_bytes:<12}")
            if self.request_mcu_update_package_tcp_raw_data_checkbox.isChecked():
                row.append(line)

            mcu_update_package_tcp_event_times_1.append("".join(row))

    if mcu_update_package_tcp_event_times_1:
        self.result_label.setText(f"共找到 {len(mcu_update_package_tcp_event_times_1) - 1} 个MCU升级包TCP事件")
        self.raw_data_display.setText("\n".join(mcu_update_package_tcp_event_times_1))
    else:
        self.result_label.setText("未找到MCU升级包TCP事件")
        self.raw_data_display.setText("")

# 7.2
def process_request_agps_data(self, raw_data_string):
        headers = []
        if self.request_agps_data_imei_checkbox.isChecked():
            headers.append(f"{'IMEI':<20}")
        if self.request_agps_data_time_checkbox.isChecked():
            headers.append(f"{'触发时间':<19}")
        if self.request_agps_data_longitude_checkbox.isChecked():
            headers.append(f"{'经度':<4}")
        if self.request_agps_data_longitude_value_checkbox.isChecked():
            headers.append(f"{'经度值':<11}")
        if self.request_agps_data_latitude_checkbox.isChecked():
            headers.append(f"{'纬度':<4}")
        if self.request_agps_data_latitude_value_checkbox.isChecked():
            headers.append(f"{'纬度值':<11}")
        if self.request_agps_data_ages_service_type_checkbox.isChecked():
            headers.append(f"{'服务器类型':<10}")
        if self.request_agps_data_raw_data_checkbox.isChecked():
            headers.append(f"{'原始数据'}")

        request_agps_data_event_times_1 = ["".join(headers)]

        for line in raw_data_string:
            if line[48:50] == "03" and line[58:62].upper() == "F002":
                imei = ascii_to_decimal(line[18:48])
                time_str = hex_to_beijing_time(line[62:70])

                # 3. 解析经度（36-39字节）
                long_hex = line[70:78]  # 1. 从报文里截取经度的8位十六进制字符串
                long_val = int(long_hex, 16)  # 2. 转成32位整数（方便位运算）
                long_dir_bit = (long_val >> 31) & 1  # 3. 取出最高位 → 代表东经/西经
                long_num = long_val & 0x7FFFFFFF  # 4. 取出后面31位 → 真正的经度数值
                actual_long = long_num / 100000  # 5. 除以10万 → 得到真实经度度数
                long_dir = "东经" if long_dir_bit == 0 else "西经"  # 6. 判断方向

                # 4. 解析纬度（40-43字节）
                lat_hex = line[78:86]
                lat_val = int(lat_hex, 16)
                lat_dir_bit = (lat_val >> 31) & 1
                lat_num = lat_val & 0x7FFFFFFF
                actual_lat = lat_num / 100000
                lat_dir = "南纬" if lat_dir_bit == 0 else "北纬"

                # 5. 解析 AGPS 服务类型
                agps_type = line[86:88]
                agps_name = "U-Blox" if agps_type == "00" else "ZKE" if agps_type == "01" else "未知"

                row = []
                if self.request_agps_data_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.request_agps_data_time_checkbox.isChecked():
                    row.append(f"{time_str:<23}")
                if self.request_agps_data_longitude_checkbox.isChecked():
                    row.append(f"{long_dir:<6}")
                if self.request_agps_data_longitude_value_checkbox.isChecked():
                    row.append(f"{actual_long:<14}")
                if self.request_agps_data_latitude_checkbox.isChecked():
                    row.append(f"{lat_dir:<6}")
                if self.request_agps_data_latitude_value_checkbox.isChecked():
                    row.append(f"{actual_lat:<14}")
                if self.request_agps_data_ages_service_type_checkbox.isChecked():
                    row.append(f"{agps_name:<15}")
                if self.request_agps_data_raw_data_checkbox.isChecked():
                    row.append(line)

                request_agps_data_event_times_1.append("".join(row))

        if request_agps_data_event_times_1:
            self.result_label.setText(f"共找到 {len(request_agps_data_event_times_1) - 1} 个AGPS请求事件")
            self.raw_data_display.setText("\n".join(request_agps_data_event_times_1))
        else:
            self.result_label.setText("未找到AGPS请求事件")
            self.raw_data_display.setText("")

# 7.3
def process_mcu_update_package_verification_tcp(self, raw_data_string):
    headers = []
    if self.mcu_update_package_verification_tcp_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.mcu_update_package_verification_tcp_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.mcu_update_package_verification_tcp_file_name_length_checkbox.isChecked():
        headers.append(f"{'长度':<6}")
    if self.mcu_update_package_verification_tcp_file_name_checkbox.isChecked():
        headers.append(f"{'文件名':<6}")
    if self.mcu_update_package_verification_tcp_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    mcu_update_package_verification_tcp_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "F003":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            file_name_len = int(line[70:72], 16)
            file_name = ascii_to_decimal(line[72:72 + file_name_len * 2]) if file_name_len != 0 else "N/A"

            row = []
            if self.mcu_update_package_verification_tcp_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.mcu_update_package_verification_tcp_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.mcu_update_package_verification_tcp_file_name_length_checkbox.isChecked():
                row.append(f"{file_name_len:<8}")
            if self.mcu_update_package_verification_tcp_file_name_checkbox.isChecked():
                row.append(f"{file_name:<9}")
            if self.mcu_update_package_verification_tcp_raw_data_checkbox.isChecked():
                row.append(line)

            mcu_update_package_verification_tcp_event_times_1.append("".join(row))

    if mcu_update_package_verification_tcp_event_times_1:
        self.result_label.setText(f"共找到 {len(mcu_update_package_verification_tcp_event_times_1) - 1} 个MCU升级包校验TCP事件")
        self.raw_data_display.setText("\n".join(mcu_update_package_verification_tcp_event_times_1))
    else:
        self.result_label.setText("未找到MCU升级包校验TCP事件")
        self.raw_data_display.setText("")

# 7.4
def process_mcu_log_report(self, raw_data_string):
    headers = []
    if self.mcu_log_report_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.mcu_log_report_log_type_checkbox.isChecked():
        headers.append(f"{'日志类型':<10}")
    if self.mcu_log_report_log_id_checkbox.isChecked():
        headers.append(f"{'日志ID':<10}")
    if self.mcu_log_report_offset_checkbox.isChecked():
        headers.append(f"{'日志偏移':<10}")
    if self.mcu_log_report_logdata_checkbox.isChecked():
        headers.append(f"{'日志数据'}")
    if self.mcu_log_report_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    mcu_log_report_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "F004":
            imei = ascii_to_decimal(line[18:48])
            log_type_hex = line[62:64].upper()
            log_type_map = {
                "00": "CAN Log",
                "01": "KEY Msg",
            }
            log_type = log_type_map.get(log_type_hex, "N/A")

            effective_data_length = int(line[54:58], 16)
            effective_data = line[58:58 + effective_data_length * 2]  # 按有效数据长度截取日志内容
            # print(effective_data,"有效数据长度")
            effective_data_len = len(effective_data)

            # 按协议表的字节位置截取（每个字节对应2个Hex字符）
            log_id_hex = line[64:72].upper()  # Log ID: 33-36字节 → 66~74
            offset_hex = line[72:80].upper()  # Offset: 37-40字节 → 74~82
            log_data_hex = line[80:58+effective_data_len].upper()  # Log data: 41-N字节 → 82~结束

            # ===================== 核心逻辑：log_type=00 直接无效 =====================
            if log_id_hex == "00":
                log_id = "00"
                offset = "日志无效"
                log_data_parsed = "日志无效"

            else:
                # 非00类型：正常解析Log ID和Offset
                log_id = log_id_hex
                offset = offset_hex

                # ===================== 按类型解析Log Data =====================
                if log_type_hex == "00":
                    # CAN Log 格式：CANID(4字节) + LENGTH(1字节) + DATA(8字节)
                    can_frames = []
                    frame_len = 26  # 4+1+8字节 = 13字节 → 26个Hex字符
                    for i in range(0, len(log_data_hex), frame_len):
                        frame = log_data_hex[i:i + frame_len]
                        if len(frame) < frame_len:
                            continue  # 不完整帧跳过

                        can_id_hex = frame[0:8]  # 4字节 → 8Hex
                        length_hex = frame[8:10]  # 1字节 → 2Hex
                        data_hex = frame[10:26]  # 8字节 → 16Hex

                        can_id = int(can_id_hex, 16)
                        length = int(length_hex, 16)
                        actual_data = data_hex[:length * 2]  # 按实际长度截取

                        can_frames.append(f"ID:{can_id:08X},LEN:{length},DATA:{actual_data}")

                    log_data_parsed = ", ".join(can_frames) if can_frames else "无有效CAN数据"

                elif log_type_hex == "01":
                    # KEY Message 格式：长度+内容；offset=0时前4字节是文件大小
                    if offset == "00000000":
                        # 首包：前4字节是文件大小
                        if len(log_data_hex) >= 8:
                            file_size_hex = log_data_hex[0:8]
                            file_size = int(file_size_hex, 16)
                            content_hex = log_data_hex[8:]
                            content_len = len(content_hex) // 2
                            try:
                                content_str = bytes.fromhex(content_hex).decode("utf-8", errors="replace")
                            except:
                                content_str = content_hex
                            log_data_parsed = f"文件大小:{file_size}字节, 内容长度:{content_len}字节, 内容:\n{content_str}\n{log_data_hex}\n"
                        else:
                            log_data_parsed = "KEY日志数据不完整"
                    else:
                        # 非首包：直接长度+内容
                        data_len = len(log_data_hex) // 2
                        try:
                            content_str = bytes.fromhex(log_data_hex).decode("utf-8", errors="replace")
                        except:
                            content_str = log_data_hex
                        log_data_parsed = f"内容长度:{data_len}字节, 内容:\n{content_str}\n{log_data_hex}\n"

                else:
                    log_data_parsed = "未知日志类型"

            row = []
            if self.mcu_log_report_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.mcu_log_report_log_type_checkbox.isChecked():
                row.append(f"{log_type:<14}")
            if self.mcu_log_report_log_id_checkbox.isChecked():
                row.append(f"{log_id:<12}")
            if self.mcu_log_report_offset_checkbox.isChecked():
                row.append(f"{offset:<14}")
            if self.mcu_log_report_logdata_checkbox.isChecked():
                row.append(log_data_parsed)
            if self.mcu_log_report_raw_data_checkbox.isChecked():
                row.append(line)

            mcu_log_report_event_times_1.append("".join(row))

    if mcu_log_report_event_times_1:
        self.result_label.setText(f"共找到 {len(mcu_log_report_event_times_1) - 1} 个MCU日志上报事件")
        self.raw_data_display.setText("\n".join(mcu_log_report_event_times_1))
    else:
        self.result_label.setText("未找到MCU日志上报事件")
        self.raw_data_display.setText("")

# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第八章：翻云起雾藏杀意，横扫千军几万里 —— 鲲鹏
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# 8.2章参数下发
def process_set_parameters(self, raw_data_string):
    headers = []
    if self.set_parameters_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.set_parameters_set_result_checkbox.isChecked():
        headers.append(f"{'设置结果':<50}")
    if self.set_parameters_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    set_parameters_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "04" and line[58:62].upper() == "F102":
            imei = ascii_to_decimal(line[18:48])

            result_strings = f1_02_parse_tlv_status_fields(line)

            row = []
            if self.set_parameters_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.set_parameters_set_result_checkbox.isChecked():
                # 将多个结果拼接成用逗号分隔的字符串
                row.append(f"{'; '.join(result_strings):<54}")
            if self.set_parameters_raw_data_checkbox.isChecked():
                row.append(line)

            set_parameters_event_times_1.append("".join(row))

    if set_parameters_event_times_1:
        self.result_label.setText(f"共找到 {len(set_parameters_event_times_1) - 1} 个参数下发事件")
        self.raw_data_display.setText("\n".join(set_parameters_event_times_1))
    else:
        self.result_label.setText("未找到参数下发事件")
        self.raw_data_display.setText("")

# 8.3章参数查询
def process_inquiry_parameters(self, raw_data_string):
    headers = []
    if self.inquiry_parameters_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.inquiry_parameters_inquiry_result_checkbox.isChecked():
        headers.append(f"{'查询结果':<50}")
    if self.inquiry_parameters_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    get_parameters_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        # print(line)
        if line[48:50] == "04" and line[58:62].upper() == "F103":
            imei = ascii_to_decimal(line[18:48])

            result_strings = f1_03_parse_custom_fields(line)

            row = []
            if self.inquiry_parameters_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.inquiry_parameters_inquiry_result_checkbox.isChecked():
                # 将多个结果拼接成用逗号分隔的字符串
                row.append(f"{'; '.join(result_strings):<54}")
            if self.inquiry_parameters_raw_data_checkbox.isChecked():
                row.append(line)

            get_parameters_event_times_1.append("".join(row))

    if get_parameters_event_times_1:
        self.result_label.setText(f"共找到 {len(get_parameters_event_times_1) - 1} 个参数查询事件")
        self.raw_data_display.setText("\n".join(get_parameters_event_times_1))
    else:
        self.result_label.setText("未找到参数查询事件")
        self.raw_data_display.setText("")

# 白名单响应
def process_whitelist_management(self, raw_data_string):
    whilelist_management_header_fields = [
        ("whitelist_management_imei_checkbox", "IMEI", 20),
        ("whitelist_management_operation_result_checkbox", "操作结果", 30),
        ("whitelist_management_type_checkbox", "类型", 10),
        ("whitelist_management_num_of_ids_checkbox", "已有ID数量", 10),
        ("whitelist_management_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]
    headers = build_checkbox(whilelist_management_header_fields, self)
    whitelist_management_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "04" and line[58:62].upper() == "F10C":
            imei = ascii_to_decimal(line[18:48])

            operation_result_hex = line[62:64].upper()
            operation_result_map = {
                "00": "操作失败，原因未知",
                "01": "操作成功",
                "02": "操作失败。要写的ID太多",
            }
            id_type_hex = line[64:66].upper()
            id_type_map = {
                "00": "RFID",
                "01": "IBUTTON",
            }
            id_type = id_type_map.get(id_type_hex, "N/A")

            num_of_ids = int(line[66:70], 16)

            operation_result = operation_result_map.get(operation_result_hex, "N/A")

            whitelist_management_tail_fields = [
                ("whitelist_management_imei_checkbox", imei, 20),
                ("whitelist_management_operation_result_checkbox", operation_result, 30),
                ("whitelist_management_type_checkbox", id_type, 12),
                ("whitelist_management_num_of_ids_checkbox", num_of_ids, 14),
                ("whitelist_management_raw_data_checkbox", line, 100),
            ]
            row = build_checkbox(whitelist_management_tail_fields, self)
            whitelist_management_event_times_1.append("".join(row))

    if whitelist_management_event_times_1:
        self.result_label.setText(f"共找到 {len(whitelist_management_event_times_1) - 1} 个白名单响应事件")
        self.raw_data_display.setText("\n".join(whitelist_management_event_times_1))
    else:
        self.result_label.setText("未找到白名单响应事件")
        self.raw_data_display.setText("")

# 白名单查询 IBUTON RFID
def process_whitelist_query(self, raw_data_string):
    whitelist_query_header_fields = [
        ("whitelist_query_imei_checkbox", "IMEI", 20),
        ("whitelist_query_type_checkbox", "类型", 10),
        ("whitelist_query_length_id_checkbox", "长度ID", 10),
        ("whitelist_query_multi_frame_flag_checkbox", "消息帧数", 10),
        ("whitelist_query_current_response_message_checkbox", "消息索引", 8),
        ("whitelist_query_number_of_ids_checkbox", "ID数量", 10),
        ("whitelist_query_ids_checkbox", "ID列表", 50),
        ("whitelist_query_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]
    headers = build_checkbox(whitelist_query_header_fields, self)
    whitelist_query_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "04" and line[58:62].upper() == "F10D":
            imei = ascii_to_decimal(line[18:48])

            type_hex = line[62:64].upper()
            type_map = {
                "00": "RFID",
                "01": "IBUTTON",
            }
            query_type = type_map.get(type_hex, "N/A")

            length_id = int(line[64:66], 16)

            multi_frame_flag = int(line[66:68], 16)

            current_response_message = int(line[68:70], 16)

            number_of_ids = int(line[70:74], 16)

            if number_of_ids == 0:
                ids_info = "NO DATA"
            elif number_of_ids > 0:
                # ids_info = line[74:74 + number_of_ids * length_id * 2]
                start = 74
                group_len = length_id * 2
                ids_info = '-'.join(
                    [line[start + i * group_len: start + (i + 1) * group_len] for i in range(number_of_ids)]
                )
            else:
                ids_info = "N/A"

            whitelist_query_tail_fields = [
                ("whitelist_query_imei_checkbox", imei, 20),
                ("whitelist_query_type_checkbox", query_type, 12),
                ("whitelist_query_length_id_checkbox", length_id, 12),
                ("whitelist_query_multi_frame_flag_checkbox", multi_frame_flag, 14),
                ("whitelist_query_current_response_message_checkbox", current_response_message, 12),
                ("whitelist_query_number_of_ids_checkbox", number_of_ids, 12),
                ("whitelist_query_ids_checkbox", ids_info, 52),
                ("whitelist_query_raw_data_checkbox", line, 100),
            ]
            row = build_checkbox(whitelist_query_tail_fields, self)
            whitelist_query_event_times_1.append("".join(row))

    if whitelist_query_event_times_1:
        self.result_label.setText(f"共找到 {len(whitelist_query_event_times_1) - 1} 个白名单查询事件")
        self.raw_data_display.setText("\n".join(whitelist_query_event_times_1))
    else:
        self.result_label.setText("未找到白名单查询事件")
        self.raw_data_display.setText("")

# 电子围栏响应 消息
def process_message_fence_response(self, raw_data_string):
    headers = []
    if self.message_fence_device_response_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.message_fence_device_response_operation_result_checkbox.isChecked():
        headers.append(f"{'操作结果':<6}")
    if self.message_fence_device_response_num_checkbox.isChecked():
        headers.append(f"{'围栏个数':<6}")
    if self.message_fence_device_response_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据':<20}")

    process_message_fence_response_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "04" and line[58:62].upper() == "F10F":
            imei = ascii_to_decimal(line[18:48])
            operation_result = line[62:64]
            operation_status = {"00": "失败", "01": "成功"}.get(operation_result, "未知")
            fence_num = int(line[64:66], 16)

            row = []
            if self.message_fence_device_response_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.message_fence_device_response_operation_result_checkbox.isChecked():
                row.append(f"{operation_status:<8}")
            if self.message_fence_device_response_num_checkbox.isChecked():
                row.append(f"{fence_num:<10}")
            if self.message_fence_device_response_raw_data_checkbox.isChecked():
                row.append(line)

            process_message_fence_response_event_times_1.append("".join(row))

    if process_message_fence_response_event_times_1:
        self.result_label.setText(f"共找到 {len(process_message_fence_response_event_times_1) - 1} 个电子围栏响应事件")
        self.raw_data_display.setText("\n".join(process_message_fence_response_event_times_1))
    else:
        self.result_label.setText("未找到电子围栏响应事件")
        self.raw_data_display.setText("")

# 电子围栏查询 消息
def process_query_fence_to_device(self, raw_data_string):
    headers = []
    if self.query_fence_to_device_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.query_fence_to_device_total_num_checkbox.isChecked():
        headers.append(f"{'围栏总数':<6}")
    if self.query_fence_to_device_start_id_checkbox.isChecked():
        headers.append(f"{'开始ID':<6}")
    if self.query_fence_to_device_message_num_checkbox.isChecked():
        headers.append(f"{'消息数':<5}")
    if self.query_fence_to_device_fence_data_checkbox.isChecked():
        headers.append(f"{'围栏消息':<120}")
    if self.query_fence_to_device_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据':<20}")

    process_query_fence_to_device_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "04" and line[58:62].upper() == "F110":
            imei = ascii_to_decimal(line[18:48])
            operate_num = int(line[62:64], 16)
            start_id = int(line[64:66], 16)
            message_num = int(line[66:68], 16)

            effective_data_length = int(line[54:58], 16)
            effective_data = line[58:58 + effective_data_length * 2]  # 按有效数据长度截取日志内容
            effective_data_len = len(effective_data)
            log_data_hex = line[68:58 + effective_data_len].upper()  # Log data: 41-N字节 → 82~结束
            print(log_data_hex)

            klv_data = log_data_hex
            offset = 0

            while offset + 4 <= len(klv_data):
                geo_id_hex = klv_data[offset:offset + 2]
                offset += 2

                data_len_hex = klv_data[offset:offset + 2]
                data_len = int(data_len_hex, 16)
                offset += 2

                data_end = offset + data_len * 2
                if data_end > len(klv_data):
                    break

                data = klv_data[offset:data_end]
                offset = data_end

                if len(data) < 10:
                    continue

                geo_mode_hex = data[0:2]
                point_num_hex = data[2:4]
                key_hex = data[4:8]
                value_len_hex = data[8:10]
                value_hex = data[10:]

                geo_id = int(geo_id_hex, 16)
                geo_mode = {
                    "00": "禁用",
                    "01": "进入",
                    "02": "退出",
                    "03": "进出"
                }.get(geo_mode_hex.upper(), "未知")

                point_num = int(point_num_hex, 16)
                key_dec = int(key_hex, 16)
                value_len = int(value_len_hex, 16)

                if point_num == 1:
                    fence_type = "圆形"
                elif point_num == 2:
                    fence_type = "矩形"
                elif 3 <= point_num <= 10:
                    fence_type = "多边形"
                else:
                    fence_type = "未知"

                gps_info_list = []
                gps_offset = 0

                if point_num == 1:
                    # 圆形：经度4字节 + 纬度4字节 + 半径3字节
                    if len(value_hex) >= 22:
                        lon_hex = value_hex[gps_offset:gps_offset + 8]
                        gps_offset += 8

                        lat_hex = value_hex[gps_offset:gps_offset + 8]
                        gps_offset += 8

                        radius_hex = value_hex[gps_offset:gps_offset + 6]

                        lon_raw = int(lon_hex, 16)
                        lat_raw = int(lat_hex, 16)

                        lon_dir_bit = (lon_raw >> 31) & 1
                        lat_dir_bit = (lat_raw >> 31) & 1

                        lon_value = (lon_raw & 0x7FFFFFFF) / 100000
                        lat_value = (lat_raw & 0x7FFFFFFF) / 100000

                        lon_dir = "西经" if lon_dir_bit == 1 else "东经"
                        lat_dir = "北纬" if lat_dir_bit == 1 else "南纬"

                        radius = int(radius_hex, 16)

                        gps_info_list.append(
                            f"经度:{lon_dir}{lon_value:.5f},"
                            f"纬度:{lat_dir}{lat_value:.5f},"
                            f"半径:{radius}"
                        )

                elif 2 <= point_num <= 10:
                    # 矩形/多边形：每组 经度4字节 + 纬度4字节
                    for i in range(point_num):
                        if gps_offset + 16 > len(value_hex):
                            break

                        lon_hex = value_hex[gps_offset:gps_offset + 8]
                        gps_offset += 8

                        lat_hex = value_hex[gps_offset:gps_offset + 8]
                        gps_offset += 8

                        lon_raw = int(lon_hex, 16)
                        lat_raw = int(lat_hex, 16)

                        lon_dir_bit = (lon_raw >> 31) & 1
                        lat_dir_bit = (lat_raw >> 31) & 1

                        lon_value = (lon_raw & 0x7FFFFFFF) / 100000
                        lat_value = (lat_raw & 0x7FFFFFFF) / 100000

                        lon_dir = "西经" if lon_dir_bit == 1 else "东经"
                        lat_dir = "北纬" if lat_dir_bit == 1 else "南纬"

                        gps_info_list.append(
                            f"点{i + 1}:经度:{lon_dir}{lon_value:.5f},"
                            f"纬度:{lat_dir}{lat_value:.5f}"
                        )

                fence_data = (
                    f"围栏ID:{geo_id},"
                    f"长度:{data_len},"
                    f"上报方式:{geo_mode},"
                    f"类型:{fence_type},"
                    f"KEY:{key_dec},"
                    f"经纬度数据长度:{value_len},"
                    f"{'；'.join(gps_info_list)}  "
                )

                row = []

                if self.query_fence_to_device_imei_checkbox.isChecked():
                    row.append(f"{imei:<20}")
                if self.query_fence_to_device_total_num_checkbox.isChecked():
                    row.append(f"{operate_num:<10}")
                if self.query_fence_to_device_start_id_checkbox.isChecked():
                    row.append(f"{start_id:<8}")
                if self.query_fence_to_device_message_num_checkbox.isChecked():
                    row.append(f"{message_num:<8}")
                if self.query_fence_to_device_fence_data_checkbox.isChecked():
                    row.append(f"{fence_data:<120}")
                if self.query_fence_to_device_raw_data_checkbox.isChecked():
                    row.append(line)

                process_query_fence_to_device_event_times_1.append("".join(row))

    if len(process_query_fence_to_device_event_times_1) > 1:
        self.result_label.setText(
            f"共找到 {len(process_query_fence_to_device_event_times_1) - 1} 个电子围栏查询事件"
        )
        self.raw_data_display.setText("\n".join(process_query_fence_to_device_event_times_1))
    else:
        self.result_label.setText("未找到电子围栏查询事件")
        self.raw_data_display.setText("")



# ════════════════════════════════════════════════════════
# ┏━━━━━━━━━━━━━━━━━━┓
# ┃  ∝╬══════→ ┃ 第九章：纵使韩信断了枪，也徒留我一人伤 —— 百鬼夜行
# ┗━━━━━━━━━━━━━━━━━━┛
# ════════════════════════════════════════════════════════

# ibutton id
def process_ibutton_id(self, raw_data_string):
    headers = []
    if self.ibutton_id_imei_checkbox.isChecked():
        headers.append(f"{'IMEI':<20}")
    if self.ibutton_id_time_checkbox.isChecked():
        headers.append(f"{'触发时间':<19}")
    if self.ibutton_id_ibutton_id_checkbox.isChecked():
        headers.append(f"{'iButton ID':<18}")
    if self.ibutton_id_authentication_status_checkbox.isChecked():
        headers.append(f"{'认证状态':<30}")
    if self.ibutton_id_gps_data_checkbox.isChecked():
        headers.append(f"{'GPS经纬度':<25}")
    if self.ibutton_id_raw_data_checkbox.isChecked():
        headers.append(f"{'原始数据'}")

    ibutton_id_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0601":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            ibutton_id = (line[118:134]).upper()
            authentication_status_hex = line[134:136].upper()
            authentication_status_map = {
                "00": "00-无需验证",
                "01": "01-ibutton ID在白名单",
                "02": "02-ibutton ID不在白名单",
            }
            authentication_status = authentication_status_map.get(authentication_status_hex, "N/A")

            # GPS信息
            ibutton_id_gps_data = parse_gps_data(line[70:118])
            longitude = ibutton_id_gps_data.get('Longitude', '')
            latitude = ibutton_id_gps_data.get('Latitude', '')
            gps_data = f"{longitude},{latitude}"

            row = []
            if self.ibutton_id_imei_checkbox.isChecked():
                row.append(f"{imei:<20}")
            if self.ibutton_id_time_checkbox.isChecked():
                row.append(f"{time_str:<23}")
            if self.ibutton_id_ibutton_id_checkbox.isChecked():
                row.append(f"{ibutton_id:<18}")
            if self.ibutton_id_authentication_status_checkbox.isChecked():
                row.append(f"{authentication_status:<28}")
            if self.ibutton_id_gps_data_checkbox.isChecked():
                row.append(f"{gps_data:<25}")
            if self.ibutton_id_raw_data_checkbox.isChecked():
                row.append(line)

            ibutton_id_event_times_1.append("".join(row))

    if ibutton_id_event_times_1:
        self.result_label.setText(f"共找到 {len(ibutton_id_event_times_1) - 1} 个iButton ID事件")
        self.raw_data_display.setText("\n".join(ibutton_id_event_times_1))
    else:
        self.result_label.setText("未找到iButton ID事件")
        self.raw_data_display.setText("")

# 胎压上报
def process_ble_sensor_data(self, raw_data_string):
    ble_sensor_data_header_fields = [
        ("ble_sensor_data_imei_checkbox", "IMEI", 20),
        ("ble_sensor_data_time_checkbox", "触发时间", 19),
        ("ble_sensor_data_front_left_pressure_checkbox", "左前胎压", 10),
        ("ble_sensor_data_front_right_pressure_checkbox", "右前胎压", 10),
        ("ble_sensor_data_rear_left_pressure_checkbox", "左后胎压", 10),
        ("ble_sensor_data_rear_right_pressure_checkbox", "右后胎压", 10),
        ("ble_sensor_data_front_left_temperature_checkbox", "左前温度", 10),
        ("ble_sensor_data_front_right_temperature_checkbox", "右前温度", 10),
        ("ble_sensor_data_rear_left_temperature_checkbox", "左后温度", 10),
        ("ble_sensor_data_rear_right_temperature_checkbox", "右后温度", 10),
        ("ble_sensor_data_front_left_battery_checkbox", "左前电量", 10),
        ("ble_sensor_data_front_right_battery_checkbox", "右前电量", 10),
        ("ble_sensor_data_rear_left_battery_checkbox", "左后电量", 10),
        ("ble_sensor_data_rear_right_battery_checkbox", "右后电量", 10),
        ("ble_sensor_data_tire_status_of_tire_checkbox", "胎压状态值", 55),
        ("ble_sensor_data_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]

    hearders = build_checkbox(ble_sensor_data_header_fields, self)

    ble_sensor_data_event_times_1 = ["".join(hearders)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0602":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            # 胎压
            front_left_pressure = (
                line[70:78].upper() if line[70:78].upper() == "FFFFFFFF" else int(line[70:78], 16))
            front_right_pressure = (
                line[78:86].upper() if line[78:86].upper() == "FFFFFFFF" else int(line[78:86], 16))
            rear_left_pressure = (
                line[86:94].upper() if line[86:94].upper() == "FFFFFFFF" else int(line[86:94], 16))
            rear_right_pressure = (
                line[94:102].upper() if line[94:102].upper() == "FFFFFFFF" else int(line[94:102], 16))
            # 温度
            front_left_temperature = line[102:106].upper() if line[102:106].upper() == "FFFF" else round(
                int(line[102:106], 16) * 0.01 - 60, 2)
            front_right_temperature = line[106:110].upper() if line[106:110].upper() == "FFFF" else round(
                int(line[106:110], 16) * 0.01 - 60, 2)
            rear_left_temperature = line[110:114].upper() if line[110:114].upper() == "FFFF" else round(
                int(line[110:114], 16) * 0.01 - 60, 2)
            rear_right_temperature = line[114:118].upper() if line[114:118].upper() == "FFFF" else round(
                int(line[114:118], 16) * 0.01 - 60, 2)
            # 电量
            front_left_battery = (
                line[118:120].upper() if line[118:120].upper() == "FF" else int(line[118:120], 16))
            front_right_battery = (
                line[120:122].upper() if line[120:122].upper() == "FF" else int(line[120:122], 16))
            rear_left_battery = (line[122:124].upper() if line[122:124].upper() == "FF" else int(line[122:124], 16))
            rear_right_battery = (
                line[124:126].upper() if line[124:126].upper() == "FF" else int(line[124:126], 16))
            # 漏气状态
            tire_status_of_tire_hex = line[126:128]
            tire_status_bin = format(int(tire_status_of_tire_hex, 16), '08b')

            tire_leak_map = {
                0: "左前轮",
                1: "右前轮",
                2: "左后轮",
                3: "右后轮"
            }
            # 构建漏气信息列表（只显示异常）
            leak_status = [
                f"{tire_leak_map[bit_index]}: 漏气"
                for bit_index in range(4)
                if tire_status_bin[7 - bit_index] == "1"
            ]
            leak_status_str = " | ".join(leak_status) if leak_status else "全部轮胎正常"

            ble_sensor_data_tail_fields = [
                ("ble_sensor_data_imei_checkbox", imei, 20),
                ("ble_sensor_data_time_checkbox", time_str, 23),
                ("ble_sensor_data_front_left_pressure_checkbox", front_left_pressure, 14),
                ("ble_sensor_data_front_right_pressure_checkbox", front_right_pressure, 14),
                ("ble_sensor_data_rear_left_pressure_checkbox", rear_left_pressure, 14),
                ("ble_sensor_data_rear_right_pressure_checkbox", rear_right_pressure, 14),
                ("ble_sensor_data_front_left_temperature_checkbox", front_left_temperature, 14),
                ("ble_sensor_data_front_right_temperature_checkbox", front_right_temperature, 14),
                ("ble_sensor_data_rear_left_temperature_checkbox", rear_left_temperature, 14),
                ("ble_sensor_data_rear_right_temperature_checkbox", rear_right_temperature, 14),
                ("ble_sensor_data_front_left_battery_checkbox", front_left_battery, 14),
                ("ble_sensor_data_front_right_battery_checkbox", front_right_battery, 14),
                ("ble_sensor_data_rear_left_battery_checkbox", rear_left_battery, 14),
                ("ble_sensor_data_rear_right_battery_checkbox", rear_right_battery, 14),
                ("ble_sensor_data_tire_status_of_tire_checkbox", leak_status_str, 60),
                ("ble_sensor_data_raw_data_checkbox", line, 100)
            ]

            row = build_checkbox(ble_sensor_data_tail_fields, self)

            ble_sensor_data_event_times_1.append("".join(row))

    if ble_sensor_data_event_times_1:
        self.result_label.setText(f"共找到 {len(ble_sensor_data_event_times_1) - 1} 个胎压上报事件")
        self.raw_data_display.setText("\n".join(ble_sensor_data_event_times_1))
    else:
        self.result_label.setText("未找到胎压上报事件")
        self.raw_data_display.setText("")

# 胎压告警
def process_ble_sensor_warning(self, raw_data_string):
    ble_sensor_warning_header_fields = [
        ("ble_sensor_warning_imei_checkbox", "IMEI", 20),
        ("ble_sensor_warning_time_checkbox", "触发时间", 19),
        ("ble_sensor_warning_warning_type_checkbox", "告警类型", 14),
        ("ble_sensor_warning_warning_position_checkbox", "告警位置", 29),
        ("ble_sensor_warning_warning_pressure_checkbox", "告警胎压", 14),
        ("ble_sensor_warning_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]

    headers = build_checkbox(ble_sensor_warning_header_fields, self)

    ble_sensor_warning_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0604":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            warning_type_hex = line[70:72]
            if warning_type_hex == "00":
                warning_type = "低压"
            elif warning_type_hex == "01":
                warning_type = "丢失"
            else:
                warning_type = "N/A"

            warning_position_hex = line[72:74]
            warning_position_bin = format(int(warning_position_hex, 16), '08b')
            warning_position_map = {
                0: "左前轮",
                1: "右前轮",
                2: "左后轮",
                3: "右后轮"
            }

            # 收集所有报警位置（bit位为1的）
            warning_positions = [
                warning_position_map[bit_index]
                for bit_index in range(4)
                if warning_position_bin[7 - bit_index] == "1"
            ]
            warning_position_str = " | ".join(warning_positions) if warning_positions else "全部轮胎正常"

            warning_pressure = line[74:82].upper() if line[74:82].upper() == "FFFFFFFF" else int(line[74:82], 16)
            # print(line[74:78])
            # print(warning_pressure)

            ble_sensor_warning_tail_fields = [
                ("ble_sensor_warning_imei_checkbox", imei, 20),
                ("ble_sensor_warning_time_checkbox", time_str, 23),
                ("ble_sensor_warning_warning_type_checkbox", warning_type, 18),
                ("ble_sensor_warning_warning_position_checkbox", warning_position_str, 32),
                ("ble_sensor_warning_warning_pressure_checkbox", warning_pressure, 18),
                ("ble_sensor_warning_raw_data_checkbox", line, 100)
            ]

            row = build_checkbox(ble_sensor_warning_tail_fields, self)

            ble_sensor_warning_event_times_1.append("".join(row))

    if ble_sensor_warning_event_times_1:
        self.result_label.setText(f"共找到 {len(ble_sensor_warning_event_times_1) - 1} 个胎压告警事件")
        self.raw_data_display.setText("\n".join(ble_sensor_warning_event_times_1))
    else:
        self.result_label.setText("未找到胎压告警事件")
        self.raw_data_display.setText("")

# 温湿度传感器
def process_rs485_temperature_humidity(self, raw_data_string):
    rs485_temperature_humidity_header_fields = [
        ("rs485_temperature_humidity_imei_checkbox", "IMEI", 20),
        ("rs485_temperature_humidity_num_checkbox", "个数", 6),
        ("rs485_temperature_humidity_time_checkbox", "触发时间", 19),
        ("rs485_temperature_humidity_temperature_checkbox", "温度(℃)", 10),
        ("rs485_temperature_humidity_humidity_checkbox", "湿度(%)", 10),
        ("rs485_temperature_humidity_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]

    headers = build_checkbox(rs485_temperature_humidity_header_fields, self)
    rs485_temperature_humidity_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0603":
            imei = ascii_to_decimal(line[18:48])
            num = int(line[62:64], 16)

            if num == 0:
                rs485_temperature_humidity_tail_fields = [
                    ("rs485_temperature_humidity_imei_checkbox", imei, 20),
                    ("rs485_temperature_humidity_num_checkbox", num, 8),
                    ("rs485_temperature_humidity_time_checkbox", "N/A", 23),
                    ("rs485_temperature_humidity_temperature_checkbox", "N/A", 13),
                    ("rs485_temperature_humidity_humidity_checkbox", "N/A", 12),
                    ("rs485_temperature_humidity_raw_data_checkbox", "N/A", 100)
                ]
                row = build_checkbox(rs485_temperature_humidity_tail_fields, self)
                rs485_temperature_humidity_event_times_1.append("".join(row))
            else:
                for i in range(num):
                    start = 64 + i * 8 * 2
                    end = start + 16
                    data_segment = line[start:end]
                    time = hex_to_beijing_time(data_segment[0:8])

                    temperature_hex = data_segment[8:12].upper()
                    temperature = "FFFF" if temperature_hex.upper() == "FFFF" else round(
                        (int(temperature_hex, 16) * 0.1 - 40), 1)

                    humidity_hex = data_segment[12:16].upper()
                    humidity = "FFFF" if humidity_hex.upper() == "FFFF" else round(
                        int(humidity_hex, 16) * 0.1, 1)

                    rs485_temperature_humidity_tail_fields = [
                        ("rs485_temperature_humidity_imei_checkbox", imei, 20),
                        ("rs485_temperature_humidity_num_checkbox", num, 8),
                        ("rs485_temperature_humidity_time_checkbox", time, 23),
                        ("rs485_temperature_humidity_temperature_checkbox", temperature, 13),
                        ("rs485_temperature_humidity_humidity_checkbox", humidity, 12),
                        ("rs485_temperature_humidity_raw_data_checkbox", line, 100)
                    ]

                    row = build_checkbox(rs485_temperature_humidity_tail_fields, self)
                    rs485_temperature_humidity_event_times_1.append("".join(row))

    if rs485_temperature_humidity_event_times_1:
        self.result_label.setText(f"共找到 {len(rs485_temperature_humidity_event_times_1) - 1} 个温湿度传感器事件")
        self.raw_data_display.setText("\n".join(rs485_temperature_humidity_event_times_1))
    else:
        self.result_label.setText("未找到温湿度传感器事件")
        self.raw_data_display.setText("")

# RFID 事件
def process_rfid_data(self, raw_data_string):
    rfid_header_fields = [
        ("rfid_data_imei_checkbox", "IMEI", 20),
        ("rfid_data_time_checkbox", "触发时间", 19),
        ("rfid_data_rfid_id_checkbox", "RFID_ID", 10),
        ("rfid_data_authentication_status_checkbox", "认证状态", 30),
        ("rfid_data_raw_data_checkbox", "原始数据", 100),  # 无需对齐
    ]

    headers = build_checkbox(rfid_header_fields, self)

    rfid_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        if line[48:50] == "03" and line[58:62].upper() == "0605":
            imei = ascii_to_decimal(line[18:48])
            time_str = hex_to_beijing_time(line[62:70])
            rfid_id = line[118:126].upper()
            authentication_status_hex = line[126:128].upper()
            authentication_status_map = {
                "00": "00-无需验证",
                "01": "01-ibutton ID在白名单",
                "02": "02-ibutton ID不在白名单",
            }
            authentication_status = authentication_status_map.get(authentication_status_hex, "N/A")

            rfid_tail_fields = [
                ("rfid_data_imei_checkbox", imei, 20),
                ("rfid_data_time_checkbox", time_str, 23),
                ("rfid_data_rfid_id_checkbox", rfid_id, 10),
                ("rfid_data_authentication_status_checkbox", authentication_status, 28),
                ("rfid_data_raw_data_checkbox", line, 100)
            ]

            row = build_checkbox(rfid_tail_fields, self)

            rfid_event_times_1.append("".join(row))

    if rfid_event_times_1:
        self.result_label.setText(f"共找到 {len(rfid_event_times_1) - 1} 个RFID事件")
        self.raw_data_display.setText("\n".join(rfid_event_times_1))
    else:
        self.result_label.setText("未找到RFID事件")
        self.raw_data_display.setText("")

# ble tag 事件
def process_ble_tag_data(self, raw_data_string):
    ble_tag_header_fields = [
        ("ble_tag_data_imei_checkbox", "IMEI", 20),
        ("ble_tag_data_tag_num_checkbox", "标签数量", 6),
        ("ble_tag_data_UUID_checkbox", "UUID", 34),
        ("ble_tag_data_major_checkbox", "Major", 8),
        ("ble_tag_data_minor_checkbox", "Minor", 8),
        ("ble_tag_data_RSSI_checkbox", "RSSI", 10),
        ("ble_tag_data_battery_checkbox", "电池电量", 10),
        ("ble_tag_data_anti_tamper_status_checkbox", "防拆状态", 8),
        ("ble_tag_data_asensor_status_checkbox", "传感器状态", 8),
        ("ble_tag_data_raw_data_checkbox", "原始数据", 100),  # 无需对齐

    ]

    headers = build_checkbox(ble_tag_header_fields, self)

    ble_tag_event_times_1 = ["".join(headers)]

    for line in raw_data_string:
        print(line,"ble tag 打印")
        if line[48:50] == "03" and line[58:62].upper() == "0607":
            imei = ascii_to_decimal(line[18:48])
            tag_num = int(line[62:64], 16)

            for i in range(tag_num):
                start = 64 + i * 27 * 2
                end = start + 54
                tag_data = line[start:end]
                uuid = tag_data[0:32].upper()
                major = int(tag_data[32:36], 16)
                minor = int(tag_data[36:40], 16)
                rssi = int(tag_data[40:48], 16)
                print(tag_data[48:50], "电池打印")
                battery = round(int(tag_data[48:50], 16) * 0.1, 1)
                anti_tamper_status_hex = tag_data[50:52].upper()
                anti_tamper_status_map = {
                    "00": "not tamper",
                    "01": "tamper",
                    "FF": "not support",
                }
                anti_tamper_status = anti_tamper_status_map.get(anti_tamper_status_hex, "N/A")
                asensor_status_hex = tag_data[52:54].upper()
                asensor_status_map = {
                    "00": "Stationary",
                    "01": "Movement",
                    "FF": "not support"
                }
                asensor_status = asensor_status_map.get(asensor_status_hex, "N/A")

                ble_tag_tail_fields = [
                    ("ble_tag_data_imei_checkbox", imei, 20),
                    ("ble_tag_data_tag_num_checkbox", tag_num, 10),
                    ("ble_tag_data_UUID_checkbox", uuid, 34),
                    ("ble_tag_data_major_checkbox", major, 8),
                    ("ble_tag_data_minor_checkbox", minor, 8),
                    ("ble_tag_data_RSSI_checkbox", rssi, 10),
                    ("ble_tag_data_battery_checkbox", battery, 10),
                    ("ble_tag_data_anti_tamper_status_checkbox", anti_tamper_status, 55),
                    ("ble_tag_data_asensor_status_checkbox", asensor_status, 55),
                    ("ble_tag_data_raw_data_checkbox", line, 100)

                ]

                row = build_checkbox(ble_tag_tail_fields, self)

                ble_tag_event_times_1.append("".join(row))

    if ble_tag_event_times_1:
        self.result_label.setText(f"共找到 {len(ble_tag_event_times_1) - 1} 个BLE Tag事件")
        self.raw_data_display.setText("\n".join(ble_tag_event_times_1))
    else:
        self.result_label.setText("未找到BLE Tag事件")
        self.raw_data_display.setText("")


_PARSER_METHOD_NAMES = [
    name for name, value in globals().items()
    if callable(value) and (name.startswith("display_") or name.startswith("process_"))
]


def bind_parser_methods(cls):
    for name in _PARSER_METHOD_NAMES:
        setattr(cls, name, globals()[name])
