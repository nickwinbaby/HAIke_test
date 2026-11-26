import re
from datetime import datetime, timezone, timedelta
from zlib import adler32


# ════════════════════════════════════════════════════════
# 1.self.dropdown1.addItems 定义一级目录
# 2.def fetch_data(self): if data_type not in 定义一级目录的显示
# 3.def update_dropdown2(self): 定义一级目录的二级目录显示
# 4.update_checkbox_visibility 定义二级目录的显示框内容
# 5.def fetch_data(self) 下面 定义二级目录的判断，进入具体函数
# 6.xxx复选框合集，定义页面可选择的展示内容，默认rawdata不展示
# 7.protocol_code_map 添加对应章节的协议码

# 7.需要在 第N章 添加按键
# 8.在数据流二级目录复选框处修改了整个复选框的布局的显示（单排显示几个）***********************************
# 9.尝试在device_info 使用for循环定义按键，简化代码
# 10.尝试在data_flow 使用字典的方式调用 build_checkbox 函数,简化代码
# ════════════════════════════════════════════════════════
# modify 260407
    # 修改下拉菜单大小和位置（全屏右对齐）
    # 修改下拉菜单标识，对应章节
    # 添加了第零章的connect和disconnect的专用复选框
# modify 260409
    # 完善可配置数据流50条 4-5 章
    # 添加急变道功能 2-7章
# modify 260415
    # 添加can数据支持状态 4-3章
    # 添加 raw_can_frame 4-4章
# modify 260416
    # 添加"4.6 - Vehicle Information KLV"
    # 添加"5.7 - Device tamper warning",
    # 添加"5.8 - Temperature warning",
    # 添加"5.13 - Device warning message"
    # 修改KLV 部分计算方式
# modify 260422
    # 添加 7.1 7.2 7.3 7.4 章节
    # 7.5 7.6 只打基础，不写具体解析，留给后续完善
# modify 260427
    # 修改LBS 适应新协议
    # 修改连接帧，兼容AP VERSION
# modify 260507
    # 增加电子围栏上报功能
# modify 260507
    # 增加电子围栏消息下发结果反馈
    # 增加电子围栏查询功能
# modify 260513
    # 增加协议码的匹配和显示
    # 增加协议一致性的frame num ,checks num ,补位 检查
    # 增加短信功能上报
    # 增加自学习功能上报
# modify 260514
    # 增加参数下发和查询
# modify 260521
    # 增加右侧ASCII转IMEI
# modify 260602
    # 修改部分功能
# modify 260617
    # 修改自动运行时间上限为1小时


# 将十六进制字符串转换为北京时间
def hex_to_beijing_time(hex_str):
    timestamp = int(hex_str, 16)
    utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    beijing_time = utc_time + timedelta(hours=8)
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')

# 将十六进制字符串转换为十进制
def ascii_to_decimal(ascii_hex):
    try:
        decoded = bytes.fromhex(ascii_hex).decode('utf-8', errors='strict')

        # 允许常见字符（数字 + 字母 + 常见符号）
        if all(32 <= ord(c) <= 126 for c in decoded):
            return decoded.strip()
        else:
            return f"{ascii_hex}(解析失败输出-HEX)"

    except Exception:
        return f"{ascii_hex}(解析失败输出-HEX)"


# GPS数据解析
def parse_gps_data(hex_string):
    # 将字符串转为字节列表
    bytes_data = bytes.fromhex(hex_string)

    if len(bytes_data) < 23:
        raise ValueError("输入数据不足23字节")

    result = {}

    # 00-03字节 # 这个是一个UNIX 时间戳的方法 转换为北京时间
    time_raw = int.from_bytes(bytes_data[0:4], byteorder='big')
    # gps_beijing_time = datetime.utcfromtimestamp(time_raw) + timedelta(hours=8)
    gps_beijing_time = datetime.fromtimestamp(time_raw, timezone.utc) + timedelta(hours=8)
    result['Time'] = gps_beijing_time.strftime("%Y-%m-%d %H:%M:%S")

    # 第04字节位拆解
    b4 = bytes_data[4]
    b4_bin = f"{b4:08b}"

    result['Positioning'] = 'GPS' if b4_bin[0] == '0' else 'GSM'
    result['Time Type'] = 'Real time' if b4_bin[1] == '0' else 'Last time'
    result['Longitude Direction'] = 'East' if b4_bin[2] == '0' else 'West'
    result['Latitude Direction'] = 'South' if b4_bin[3] == '0' else 'North'
    satellite_count = b4 & 0x0F
    result['Sate Num'] = satellite_count

    # 高度 = 第05字节 + 第06字节的07-01位
    b5 = bytes_data[5]
    b6 = bytes_data[6]
    b6_bin = f"{b6:08b}"
    height = (b5 << 7) + int(b6_bin[:7], 2)
    result['Height'] = height - 10000

    # 经度 = 第06字节的00位 + 07-09字节
    lon_prefix = b6 & 0x01
    longitude = (lon_prefix << 24) + (bytes_data[7] << 16) + (bytes_data[8] << 8) + bytes_data[9]
    result['Longitude'] = round(longitude * 0.00001, 6)

    # 纬度 = 10-12字节
    latitude = (bytes_data[10] << 16) + (bytes_data[11] << 8) + bytes_data[12]
    result['Latitude'] = round(latitude * 0.00001, 6)

    # GPS速度 = 第13字节 + 第14字节07-04位
    b13 = bytes_data[13]
    b14 = bytes_data[14]
    gps_speed = (b13 << 4) + (b14 >> 4)
    result['GPS Speed'] = round(gps_speed * 0.1, 1)

    # 保留位（不处理，但提取）
    reserved_bits = (b14 >> 2) & 0b11
    result['Reserved'] = reserved_bits

    # Heading = 第14字节01-00位 + 第15字节
    heading = ((b14 & 0b11) << 8) + bytes_data[15]
    result['Heading'] = heading

    # PDOP = 第16字节 + 第17字节07-04位
    pdop = (bytes_data[16] << 4) + (bytes_data[17] >> 4)
    result['PDOP'] = round(pdop * 0.1, 1)

    # HDOP = 第17字节03-00位 + 第18字节
    hdop = ((bytes_data[17] & 0x0F) << 8) + bytes_data[18]
    result['HDOP'] = round(hdop * 0.1, 1)

    # VDOP = 第19字节 + 第20字节07-04位
    vdop = (bytes_data[19] << 4) + (bytes_data[20] >> 4)
    result['VDOP'] = round(vdop * 0.1, 1)

    # HACC = 第21字节 + 第22字节
    hacc = (bytes_data[21] << 8) + bytes_data[22]
    result['HACC'] = round(hacc * 0.1, 1)

    return result

# config dataflow key 校验
# ===================== 工具函数：统一处理所有KEY =====================
def parse_value(v_hex, invalid, calc):
    # 无效值判断
    if isinstance(invalid, set):
        if v_hex.upper() in invalid:
            return v_hex
    else:
        if v_hex.upper() == invalid:
            return v_hex

    # 转换 + 计算
    try:
        val = int(v_hex, 16)
        return calc(val)
    except:
        return v_hex

#  KLV解析规则
def handle_value(k, v_hex):
    """
    根据不同K解析V
    """

    try:
        # ===== 5.1TLVs for Sensor Data 200-214 =======================================
        if k == 200:
            # Battery Voltage of Tag (mV -> V)
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.001:.3f} Volt")
        elif k == 201:
            # Anti-tamper Status of Tag
            if v_hex == "00":
                return "Not tamper"
            elif v_hex == "01":
                return "Tamper"
            elif v_hex == "FF":
                return "Not support"
            else:
                return f"Reserved ({v_hex})"
        elif k == 202:
            # Asensor Status of Tag
            if v_hex == "00":
                return "Stationary"
            elif v_hex == "01":
                return "Movement"
            elif v_hex == "FF":
                return "Not support"
            else:
                return f"Reserved ({v_hex})"
        elif k == 204:
            # Beacon Temperature
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 40:.1f} °C")
        elif k == 205:
            # Gsensor Data of Beacon (X/Y/Z mg)
            return f"Gsensor Data: {v_hex}"
        elif k == 206:
            # Angle of Beacon
            return f"Beacon Angle: {v_hex}"
        elif k == 207:
            # Tilt Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 208:
            # Motion Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 209:
            # Crash Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 210:
            # Falling Event Counter
            return parse_value(v_hex, "FFFF", lambda x: f"{x}")
        elif k == 211:
            # Door State of Beacon
            return "Closed" if v_hex == "01" else "Not closed"
        elif k == 212:
            # Asensor Data
            return f"Asensor Data: {v_hex}"
        elif k == 213:
            # Collected Temperature + Time
            return f"Collected Temperature Data: {v_hex}"
        elif k == 214:
            # Collected Air Pressure + Time
            return f"Collected Air Pressure Data: {v_hex}"
        # ===== 5.2TLVs for Location Data 400-411 =======================================
        elif k == 400:
            # One GPS Data
            return f"GPS Data: {v_hex}"
        elif k == 401:
            # Longitude 经度
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.00001:.5f} Degree")
        elif k == 402:
            # Latitude 纬度
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.00001:.5f} Degree")
        elif k == 403:
            # Radius 半径
            return parse_value(v_hex, "FFFF", lambda x: f"{x} meter")
        elif k == 404:
            # Circular Geo-fence
            return f"Circular Geo-fence: {v_hex}"
        elif k == 405:
            # Rectangular Geo-fence
            return f"Rectangular Geo-fence: {v_hex}"
        elif k == 406:
            # Polygon Geo-fence
            return f"Polygon Geo-fence: {v_hex}"
        elif k == 407:
            # Altitude 海拔
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 10000} meter")
        elif k == 408:
            # Location Data 1
            return f"Location Data: {v_hex}"
        elif k == 409:
            # Position Time UTC 时间戳
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Second")
        elif k == 410:
            # Heading 方向角
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Degree")
        elif k == 411:
            # LBS Data
            return f"LBS Data: {v_hex}"
        # ===== device warning message 500-505 ================================================
        elif k == 500:
            # Temperature Warning 温度告警
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 40:.1f} ℃")
        elif k == 501:
            # Air Pressure Warning 气压告警
            return parse_value(v_hex, "FFFF", lambda x: f"{x} mBar")
        elif k == 502:
            # Humidity Warning 湿度告警
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.1f} %")
        elif k == 503:
            # Warning Judged from Asensor Data 震动/冲击告警
            if v_hex == "00":
                return "Slight Vibration (轻微震动)"
            elif v_hex == "01":
                return "Medium Vibration (中等震动)"
            elif v_hex == "02":
                return "Severe Vibration (剧烈震动)"
            elif v_hex == "03":
                return "Shock (冲击)"
            else:
                return f"Reserved ({v_hex})"
        elif k == 504:
            # Device Tamper Warning 防拆告警
            return "Device tampered warning (设备被拆)" if v_hex == "01" else "Normal"
        elif k == 505:
            # Ambient Light Warning 环境光告警
            return "Ambient light warning (光线异常)" if v_hex == "01" else "Normal"
        # ===== 5.4TLVs for Fixed Vehicle Information 901-902 ==================================
        elif k == 901:
            # VIN Code 车辆识别码
            return f"VIN: {v_hex}"
        elif k == 902:
            # Engine Serial Number 发动机序列号
            return f"Engine SN: {v_hex}"
        # ===== config data flow KLV 1001 - 1055 ========================================
        elif k == 1001:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} RPM")
        elif k == 1002:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} km/h")
        elif k == 1003:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1004:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1005:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1006:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} g/s")
        elif k == 1007:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1008:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Kpa")
        elif k == 1009:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} V")
        elif k == 1010:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.01:.2f} %")
        elif k == 1011:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} KM")

        # 1012 特殊（多无效值）→ 照样支持
        elif k == 1012:
            return parse_value(v_hex, {"FFFF", "0000", "0001", "FFFE"}, lambda x: f"{x} KM")

        elif k == 1013:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} meter")
        elif k == 1014:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} ml")

        # 1016 复杂逻辑 → 单独写最清晰
        elif k == 1016:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                val = int(v_hex, 16)
                driver = val & 0b11
                passenger = (val >> 2) & 0b11

                def s(b):
                    if b == 0b00: return "Not Tied"
                    if b == 0b01: return "Tied"
                    if b == 0b11: return "Not supported"
                    return "Invalid"

                return f"Driver:{s(driver)}, Passenger:{s(passenger)}"
            except:
                return v_hex

        elif k == 1017:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} KM")

        # 1018 特殊枚举 → 单独写
        elif k == 1018:
            if v_hex.upper() == "FF": return v_hex
            if v_hex == "01": return "KM"
            if v_hex == "02": return "Mile"
            return v_hex

        elif k == 1019:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} ml/100KM")
        elif k == 1020:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1021:
            return parse_value(v_hex, "FF", lambda x: f"{x} %")
        elif k == 1022:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 1000:.2f} A")

        # ===================== 1022 ~ 1055 全部生成完毕 =====================
        # 懒得写了 AI 给写的
        elif k == 1022:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 1000:.2f} A")
        elif k == 1023:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} Volt")
        elif k == 1024:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                s = {0: "Not Charging", 1: "Level 1 Charging", 2: "Level 2 Charging", 3: "Level 3 Quick Charging"}
                return s.get(int(v_hex, 16), v_hex)
            except:
                return v_hex
        elif k == 1025:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} KM")
        elif k == 1026:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1027:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} KM")
        elif k == 1028:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} Second")
        elif k == 1029:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                m = {
                    0x00: "Not available", 0x01: "Gasoline", 0x02: "Methanol", 0x03: "Ethanol", 0x04: "Diesel",
                    0x05: "LPG", 0x06: "CNG", 0x07: "Propane", 0x08: "Electric", 0x09: "Bifuel running Gasoline",
                    0x0A: "Bifuel running Methanol", 0x0B: "Bifuel running Ethanol", 0x0C: "Bifuel running LPG",
                    0x0D: "Bifuel running CNG", 0x0E: "Bifuel running Propane", 0x17: "Natural Gas (NG)",
                    0x18: "Bi-fuel NG", 0x19: "Bi-fuel diesel", 0x1A: "Natural Gas", 0x1B: "Dual Fuel Diesel-CNG",
                    0x1C: "Dual Fuel Diesel-LNG", 0x1D: "Fuel cell hydrogen", 0x1E: "Hydrogen ICE", 0x1F: "Kerosene",
                    0x20: "Heavy Fuel Oil"
                }
                return m.get(int(v_hex, 16), v_hex)
            except:
                return v_hex
        elif k == 1030:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                v = int(v_hex, 16)
                left = "On" if (v & 1) else "Off"
                right = "On" if (v & 2) else "Off"
                return f"Left:{left}, Right:{right}"
            except:
                return v_hex
        elif k == 1031:
            return parse_value(v_hex, "FFFF", lambda x: f"{x - 40} ℃")
        elif k == 1032:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.01 - 100:.2f} %")
        elif k == 1033:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.01 - 100:.2f} %")
        elif k == 1034:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                g = {0: "Gear P", 2: "Gear R", 3: "Gear N", 4: "Gear D"}
                return g.get(int(v_hex, 16), v_hex)
            except:
                return v_hex
        elif k == 1035:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1036:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1 - 1000:.2f} Degree")
        elif k == 1037:
            if v_hex.upper() == "FF":
                return v_hex
            try:
                return "High beam On" if int(v_hex, 16) == 1 else "High beam Off"
            except:
                return v_hex
        elif k == 1038:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} kPa")
        elif k == 1039:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} mL/100KM")
        elif k == 1040:
            return parse_value(v_hex, "FFFFFFFF", lambda x: f"{x} mL")
        elif k == 1041:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1042:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} Minute")
        elif k == 1043:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1044:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1045:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1046:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1047:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1048:
            if v_hex.upper() == "FF": return v_hex
            try:
                return "Open" if int(v_hex, 16) == 1 else "Close"
            except:
                return v_hex
        elif k == 1050:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1051:
            if v_hex.upper() == "FF": return v_hex
            try:
                return f"{int(v_hex, 16) - 125} Gear value"
            except:
                return v_hex
        elif k == 1052:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} kPa")
        elif k == 1053:
            return parse_value(v_hex, "FFFF", lambda x: f"{x} kPa")
        elif k == 1054:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")
        elif k == 1055:
            return parse_value(v_hex, "FFFF", lambda x: f"{x * 0.1:.2f} %")



# 1001 - 1020 隐藏，用简单方式来继续处理
        # elif k == 1001:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16)} RPM"
        #     except:
        #         return v_hex
        # elif k == 1002:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16)} km/h"
        #     except:
        #         return v_hex
        # elif k == 1003:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16) * 0.1 - 40:.2f} ℃"
        #     except:
        #         return v_hex
        # elif k == 1004:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} %"
        # elif k == 1005:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} %"
        # elif k == 1006:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} g/s"
        # elif k == 1007:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1 - 40:.2f} ℃"
        # elif k == 1008:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} Kpa"
        # elif k == 1009:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} V"
        # elif k == 1010:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.01:.2f} %"
        # elif k == 1011:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} KM"
        # elif k == 1012:
        #     if v_hex.upper() in {"FFFF", "0000", "0001", "FFFE"}:
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16)} KM"
        #     except:
        #         return v_hex
        # elif k == 1013:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) } meter"
        # elif k == 1014:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} ml"
        # elif k == 1016:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #
        #     try:
        #         val = int(v_hex, 16)
        #         # 解析主驾（bit0-1）
        #         driver = val & 0b11
        #         # 解析副驾（bit2-3）
        #         passenger = (val >> 2) & 0b11
        #
        #         # 转成文字
        #         def get_status(bits):
        #             if bits == 0b00:
        #                 return "Not Tied"
        #             elif bits == 0b01:
        #                 return "Tied"
        #             elif bits == 0b11:
        #                 return "Not supported"
        #             else:
        #                 return "Invalid"
        #
        #         d_stat = get_status(driver)
        #         p_stat = get_status(passenger)
        #         return f"Driver:{d_stat}, Passenger:{p_stat}"
        #
        #     except:
        #         return v_hex
        # elif k == 1017:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} KM"
        # elif k == 1018:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #     elif v_hex == "01":
        #         return "KM"
        #     elif v_hex == "02":
        #         return "Mile"
        #     else:
        #         return v_hex
        # elif k == 1019:
        #     if v_hex.upper() == "FFFFFFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} ml/100KM"
        # elif k == 1020:
        #     if v_hex.upper() == "FFFF":
        #         return v_hex
        #     return f"{int(v_hex, 16) * 0.1:.2f} %"
        # elif k == 1021:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #     return f"{int(v_hex, 16)} %"
        # elif k == 1021:
        #     if v_hex.upper() == "FF":
        #         return v_hex
        #     try:
        #         return f"{int(v_hex, 16) * 0.1 - 1000:.2f } A"
        #     except:
        #         return v_hex


        else:
            return v_hex  # 默认直接返回
    except:
        return v_hex

def parse_klv(data):
    i = 0
    result = []

    while i + 6 <= len(data):  # 至少 K(4) + L(2)
        try:
            # 1️⃣ K
            k_hex = data[i:i + 4]
            k = int(k_hex, 16)
            i += 4

            # 2️⃣ L
            l_hex = data[i:i + 2]
            l = int(l_hex, 16)
            i += 2

            # 3️⃣ V长度
            v_len = l * 2
            if i + v_len > len(data):
                break

            v_hex = data[i:i + v_len]
            i += v_len

            # 4️⃣ 解析V
            v_value = handle_value(k, v_hex)

            result.append(f"{k} - {v_value}")

        except:
            break

    return " , ".join(result)

# can 支持参数状态 -函数框

gasoline_map = {
    1: ["VIN", "ODO", "FLI(%)", "FLI(Liter)", "Seatbelt_Driver", "Seatbelt_Passenger", "TPMS_P", "TPMS_T"],
    2: ["DTC", "MILStatus", "DistanceTraveledWhileMILActivated", "DistanceTraveledSinceDTCsCleared",
        "RemainingDistance", "DistanceTillNextServicing", "OilTemp", "OBDType"],
    3: ["EngineRPM", "VehicleSpeed", "MassAirFlow", "IntakeAirTemp",
        "IntakeManifoldAbsolutePressure", "TimeSinceEngineStart", "CalculatedLoad", "EngineCoolantTemp"],
    4: ["ThrottlePosition", "EngineRunTime", "AmbientTemperature", "LongTermFuelTrim",
        "ExtendedMassAirFlowInformation", "EngineOilPressure", "EngineInstantaneousFuelEconomy", "DieselExhaustFluidTankVolume"],
    5: ["PercentClutchSlip", "TotalFuelUsed", "BrakePrimaryPressure", "BrakeSecondaryPressure",
        "EngineCoolantLevel", "FuelLevel2", "Reserved", "Reserved"]
}

ev_map = {
    1: ["VIN", "Ready", "SOC", "SOH", "ChargingState", "ChargeMinutesRemaining", "ODO", "VehicleSpeed"],
    2: ["BatteryPackCurrent", "BatteryPackVoltage", "BatteryPackTemperature", "RemainingDistance",
        "DistanceTillNextServicing", "Seatbelt_Driver", "Seatbelt_Passenger", "TPMS_P"],
    3: ["ODOUnit", "DoorsStatus", "TrunkStatus", "GearPosition",
        "ParkStatus", "MotorRPM", "BrakePedal", "WheelSpeed"],
    4: ["SteeringAngle", "HighBeamStatus", "LeftTurnSignal", "RightTurnSignal",
        "TPMS_T", "ACCPedal", "ACCPedaPercent", "BrakePedalPercent"]
}


def parse_can_list(line, start, mapping):
    result = []

    if start + 2 > len(line):
        return result, start

    length = int(line[start:start+2], 16)

    # 长度为0
    if length == 0:
        return result, start + 2

    # ✅ 正确：包含 byte0 + 数据
    total_bytes = 1 + length

    for i in range(1, length + 1):   # ✅ 关键修复
        byte_hex = line[start + i*2 : start + i*2 + 2]
        byte_val = int(byte_hex, 16)

        if i not in mapping:
            continue

        fields = mapping[i]

        for bit in range(8):
            if byte_val & (1 << (7 - bit)):
                result.append(f"byte{i}-bit{7-bit}:{fields[bit]}")

    # ✅ 正确 offset
    new_start = start + total_bytes * 2

    return result, new_start


# 构建按键函数
# def build_checkbox(fields, context):
#     row = []
#     for checkbox, value, fmt in fields:
#         if getattr(context, checkbox).isChecked():
#             row.append(fmt.format(value))
#     return row


# 创建按键
def build_checkbox(fields, context):
    row = []
    for checkbox, label, width in fields:
        if getattr(context, checkbox).isChecked():
            row.append(f"{label:<{width}}")
    return row


# 8.2 章参数下发
def f1_02_parse_tlv_status_fields(line):
    result_mapping = {
        "00": "failure",
        "01": "successful",
        "02": "work m2 invalid",
        "03": "work m3 invalid",
        "04": "work m4 invalid",
        "05": "main power dis"
    }

    offset = 0
    results = []

    effective_data_length = int(line[54:58], 16)
    parameters_effective_data = line[62:62 + (effective_data_length - 2) * 2]

    while offset + 6 <= len(parameters_effective_data):  # 确保剩下至少6个字符可读
        param = parameters_effective_data[offset:offset + 4]
        status_code = parameters_effective_data[offset + 4:offset + 6]

        status_text = result_mapping.get(status_code, "unknown")

        # results.append((param, status_code, status_text))
        results.append(f"{param.upper()}:{status_text}")
        offset += 6  # 每次向后推进6位

    return results


# 8.3 章处理 可变长度字段
def handle_variable_length_field(data, calc_func):
    length_byte = int(data[:2], 16)  # 取长度字段
    data_length = length_byte * 2  # 转换为十六进制字符长度
    data_value = data[2:2 + data_length]  # 提取有效数据部分
    value = calc_func(data_value)  # 调用传入函数处理（如 ASCII 解码）
    return value, data_length

def parse_024A(value_hex):
    try:
        pos = 0

        # A：APN长度
        if pos + 2 > len(value_hex):
            return f"{value_hex}(HEX,缺少APN长度)"

        apn_len = int(value_hex[pos:pos + 2], 16)
        pos += 2

        if apn_len >= 32:
            return f"{value_hex}(HEX,APN长度异常:{apn_len})"

        apn_hex = value_hex[pos:pos + apn_len * 2]
        if len(apn_hex) < apn_len * 2:
            return f"{value_hex}(HEX,APN内容长度不足)"

        pos += apn_len * 2
        apn = ascii_to_decimal(apn_hex)

        # B：用户名长度
        if pos + 2 > len(value_hex):
            return f"APN:{apn}, User:, Password:"

        username_len = int(value_hex[pos:pos + 2], 16)
        pos += 2

        if username_len >= 32:
            return f"{value_hex}(HEX,用户名长度异常:{username_len})"

        username_hex = value_hex[pos:pos + username_len * 2]
        if len(username_hex) < username_len * 2:
            return f"{value_hex}(HEX,用户名内容长度不足)"

        pos += username_len * 2
        username = ascii_to_decimal(username_hex)

        # C：密码长度
        if pos + 2 > len(value_hex):
            return f"APN:{apn}, User:{username}, Password:"

        password_len = int(value_hex[pos:pos + 2], 16)
        pos += 2

        if password_len >= 32:
            return f"{value_hex}(HEX,密码长度异常:{password_len})"

        password_hex = value_hex[pos:pos + password_len * 2]
        if len(password_hex) < password_len * 2:
            return f"{value_hex}(HEX,密码内容长度不足)"

        password = ascii_to_decimal(password_hex)

        return f"APN:{apn}, User:{username}, Password:{password}"

    except Exception as e:
        return f"{value_hex}(HEX,024A解析失败:{e})"

# 8.3 章参数查询
def f1_03_parse_custom_fields(line):
    results = []

    field_defs = {
        "0001": (1, lambda v: int(v, 16) * 10),
        "0002": (1, lambda v: int(v, 16) * 10),
        "0003": (1, lambda v: int(v, 16) * 10),
        "0004": (2, lambda v: int(v, 16)),
        "0005": (1, lambda v: int(v, 16)),
        "0006": (1, lambda v: int(v, 16) * 0.1),
        "0007": (1, lambda v: {"01": "0.0625g", "02": "0.125g", "03": "0.250g", "04": "0.375g", "05": "0.625g",
                               "06": "0.9375g", "07": "1.25g"}.get(v.upper(), "unknown")),
        "0008": (1, lambda v: int(v, 16) * 100),
        "0009": (2, lambda v: int(v, 16)),
        "000B": (2, lambda v: int(v, 16)),
        "000C": (2, lambda v: int(v, 16)),
        "000D": (2, lambda v: int(v, 16)),
        "000E": (2, lambda v: int(v, 16)),
        "000F": (2, lambda v: int(v, 16) * 0.1),
        "0010": (2, lambda v: {"0000": "Enable OBD", "0001": "Disable OBD"}.get(v.upper(), "Unknown")),
        "0012": (1, lambda v: {"01": "ASS OFF", "02": "ASS ON"}.get(v.upper(), "Unknown")),
        "0016": (1, lambda v: {"01": "factory reset"}.get(v.upper(), "Unknown")),
        "0017": (1, lambda v: {"01": "reboot device"}.get(v.upper(), "Unknown")),
        "0018": (1, lambda v: int(v, 16)),
        "0207": (
        1, lambda v: {"00": "Not controlled", "01": "HOTSPOT on", "02": "HOTSPOT off"}.get(v.upper(), "Unknown")),
        "020F": (1, lambda v: {"00": "Tracker", "01": "ACC", "02": "OBD", "03": "Mixed", "04": "Standalone "}.get(
            v.upper(), "Unknown")),
        "0220": (1, lambda v: int(v, 16) * 0.1),
        "0225": (2, lambda v: int(v, 16) * 3),
        "0226": (2, lambda v: int(v, 16)),
        "0227": (1, lambda v: {"00": "recover", "01": "cut off"}.get(v.upper(), "Unknown")),
        "0228": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0229": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "022A": (2, lambda v: int(v, 16)),
        "022B": (2, lambda v: int(v, 16)),
        "0230": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0231": (1, lambda v: {"01": "mode1 ", "02": "mode2", "03": "mode3", "04": "mode4"}.get(v.upper(), "Unknown")),
        "0232": (1, lambda v: int(v, 16)),
        "0233": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0235": (1, lambda v: int(v, 16)),
        "0236": (4, lambda v: int(v, 16) * 0.1 - 40),
        "0237": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0238": (1, lambda v: int(v, 16)),
        "0239": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "023A": (2, lambda v: int(v, 16)),
        "023C": (2, lambda v: int(v, 16)),
        "023D": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0247": (1, lambda v: int(v, 16) * 0.1),
        "0250": (1, lambda v: {"01": "factory reset"}.get(v.upper(), "Unknown")),
        "0251": (1, lambda v: {"01": "reboot device"}.get(v.upper(), "Unknown")),
        "0252": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0253": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0255": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0256": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0257": (1, lambda v: int(v, 16)),
        "0271": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0272": (1, lambda v: int(v, 16)),
        "0273": (1, lambda v: {"01": " Hard reset the device"}.get(v.upper(), "Unknown")),
        "0274": (1, lambda v: int(v, 16)),
        "0275": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0276": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0277": (1, lambda v: int(v, 16)),
        "0278": (1, lambda v: int(v, 16)),
        "0279": (1, lambda v: {"00": "INFO ", "01": "DEBUG"}.get(v.upper(), "Unknown")),
        "040D": (1, lambda v: {"01": "Terminate current MCU FOTA task"}.get(v.upper(), "Unknown")),
        "0414": (1, lambda v: {"00": "Not controlled by the server", "01": "5GHz HOTSPOT on",
                               "02": "5GHz HOTSPOT off"}.get(v.upper(), "Unknown")),
        "0415": (2, lambda v: int(v, 16)),
        "0416": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0417": (
        1, lambda v: {"00": "Deep Sleep", "01": "Light Sleep", "02": "GPS Online Sleep"}.get(v.upper(), "Unknown")),
        "0418": (1, lambda v: {"00": "Disable", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0419": (4, lambda v: int(v, 16) * 0.1),
        "041A": (1, lambda v: {"01": "force to re-learning"}.get(v.upper(), "Unknown")),
        "041B": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "041C": (1, lambda v: {"00": "00 ", "01": "01", "02": "02"}.get(v.upper(), "Unknown")),
        "041D": (2, lambda v: int(v, 16)),
        "041F": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0420": (4, lambda v: int(v, 16)),
        "0421": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0422": (1, lambda v: {"00": "Disable iButton and RFID",
                               "01": "Only report iButton ID",
                               "02": "report iButton ID, and wire relay",
                               "03": "Only report RFID card",
                               "04": "report RFID card, and wire relay",
                               "05": "report iButton ID, and ble relay",
                               "06": "report RFID card, and wire relay",
                               }.get(v.upper(), "Unknown")),
        "0423": (1, lambda v: {"00": "Disable RFID function ", "01": "Only report RFID",
                               "02": "Report RFID, and control relay"}.get(v.upper(), "Unknown")),
        "0425": (2, lambda v: int(v, 16)),
        "0426": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "0428": (1, lambda v: {"00": "Disable ", "01": "Enable"}.get(v.upper(), "Unknown")),
        "042A": (2, lambda v: int(v, 16)),
        "0434": (7, lambda v: f"{int(v[0:2], 16)} - {v[2:].upper()}"),

        # 动态字段处理
        "0200": (99, ascii_to_decimal),
        "0202": (99, ascii_to_decimal),
        "0203": (99, ascii_to_decimal),
        "0204": (99, ascii_to_decimal),
        "0206": (99, ascii_to_decimal),
        "0221": (99, ascii_to_decimal),
        "023B": (99, ascii_to_decimal),
        "0240": (99, ascii_to_decimal),
        "0241": (99, ascii_to_decimal),
        "024A": (99, parse_024A),
        "0254": (99, ascii_to_decimal),
        "0407": (99, ascii_to_decimal),
        "041E": (99, ascii_to_decimal),
        "0424": (99, ascii_to_decimal),
    }

    effective_data_length = int(line[54:58], 16)
    payload = line[62:62 + (effective_data_length - 2) * 2]

    offset = 0
    while offset + 4 <= len(payload):
        param = payload[offset:offset + 4].upper()

        if param in field_defs:
            num, func = field_defs[param]

            if num == 99:
                length_hex = payload[offset + 4:offset + 6]

                if len(length_hex) < 2:
                    results.append(f"{param}:数据错误，缺少长度字段")
                    break

                data_len = int(length_hex, 16)
                end_pos = offset + 6 + data_len * 2

                if end_pos > len(payload):
                    results.append(f"{param}:数据错误，返回值长度不足，无法解析")
                    break

                value_hex = payload[offset + 6:end_pos]

                try:
                    value = func(value_hex)
                    results.append(f"{param}:{value}")
                except Exception:
                    results.append(f"{param}:数据错误，无法被ASCII解析")
                    break

                offset += 4 + 2 + data_len * 2

            else:
                length = num * 2
                end_pos = offset + 4 + length

                if end_pos > len(payload):
                    results.append(f"{param}:数据错误，返回值长度不足，无法解析")
                    break

                value_hex = payload[offset + 4:end_pos]

                try:
                    value = func(value_hex)
                    results.append(f"{param}:{value}")
                except Exception:
                    results.append(f"{param}:数据错误，无法解析")
                    break

                offset += 4 + length

        else:
            results.append(f"{param}:未识别字段")
            break

    return results


# sensor_normal_event 事件取正负值
def parse_signed_16bit(hex_str):
    value = int(hex_str, 16)
    if value & 0x8000:  # 判断最高位是否为1
        return value - 0x10000  # 65536
    return value
