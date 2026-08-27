# import string
import ctypes
import json
import chardet
import requests
import openpyxl
from openpyxl import Workbook
from datetime import datetime, timedelta, timezone
from openpyxl.styles import PatternFill

# 定义枚举
class JsonLogLevel:
    JSON_LOG_LEVEL_DEBUG = 0
    JSON_LOG_LEVEL_INFO = 1
    JSON_LOG_LEVEL_WARN = 2
    JSON_LOG_LEVEL_ERROR = 3

def ascii_to_hex(ascii_str):
    return bytes.fromhex(ascii_str)

class JsonSdk:
    def __init__(self, dll_path):
        self.json_sdk = ctypes.CDLL(dll_path)
        self.json_sdk.json_protocol_get_library_version.restype = ctypes.c_char_p
        self.json_sdk.json_protocol_get_error_description.argtypes = [ctypes.c_int]
        self.json_sdk.json_protocol_get_error_description.restype = ctypes.c_char_p
        self.json_sdk.json_protocol_init_logger.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
        # self.json_sdk.json_protocol_set_protocol.argtypes = [ctypes.c_int]
        # self.json_sdk.json_protocol_set_protocol.restype = ctypes.c_int
        # self.json_sdk.json_protocol_init.restype = ctypes.c_int
        # self.json_sdk.json_protocol_set_vehicle_type.argtypes = [ctypes.c_int]
        # self.json_sdk.json_protocol_set_vehicle_type.restype = ctypes.c_int
        self.json_sdk.json_protocol_frame_package.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                                                             ctypes.POINTER(ctypes.c_int), ctypes.c_char_p,ctypes.c_int]
        self.json_sdk.json_protocol_frame_package.restype = ctypes.c_int
        self.json_sdk.json_protocol_frame_parse.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                                           ctypes.c_char_p,ctypes.c_int]
        self.json_sdk.json_protocol_frame_parse.restype = ctypes.c_int

    def get_library_version(self):
        version = self.json_sdk.json_protocol_get_library_version()
        return version.decode('utf-8')

    def get_error_description(self, errCode):
        description = self.json_sdk.json_protocol_get_error_description(errCode)
        return description.decode('utf-8')

    def init_logger(self, level, outputPath, fileName):
        self.json_sdk.json_protocol_init_logger(level, outputPath.encode('utf-8'), fileName.encode('utf-8'))

    # def set_protocol(self, protocolType):
    #     return self.json_sdk.json_protocol_set_protocol(protocolType)

    # def init_protocol(self):
    #     return self.json_sdk.json_protocol_init()

    def set_vehicle_type(self, vehicleType):
        return self.json_sdk.json_protocol_set_vehicle_type(vehicleType)

    def frame_package(self, pInBuff, usInLength, pOutBuff, usOutLength, mcukey):
        mcukey_hex = ascii_to_hex(mcukey)
        out_length = ctypes.c_int(usOutLength)
        result = self.json_sdk.json_protocol_frame_package(pInBuff.encode('utf-8'), usInLength, pOutBuff,
                                                          ctypes.byref(out_length), mcukey_hex, 1)
        return result, pOutBuff.raw[:out_length.value]

    def frame_parse(self, pInBuff, usInLength, pOutBuff, usOutLength, mcukey):
        mcukey_hex = ascii_to_hex(mcukey)
        out_length = ctypes.c_int(usOutLength)
        result = self.json_sdk.json_protocol_frame_parse(pInBuff, usInLength, pOutBuff, out_length, mcukey_hex, 1)
        parsed_data = pOutBuff.raw[:out_length.value].decode('utf-8').rstrip('\x00')
        return result, parsed_data

    def initialise(self, log_level, output_path, filename):
        self.init_logger(log_level, output_path, filename)
        print("Library Version:", self.get_library_version())
        print("Error Description (Code 0):", self.get_error_description(0))
        # print("Set Protocol (Type {}):".format(protocol_type), self.set_protocol(protocol_type))
        # print("Initialize Protocol:", self.init_protocol())
        # print("Set Vehicle Type (Type {}):".format(vehicle_type), self.set_vehicle_type(vehicle_type))


# # 使用示例
# if __name__ == '__main__':
dll_path = './dll/jsonrichlinksdk.dll'
json_sdk = JsonSdk(dll_path)
# 将协议版本号与其描述对应起来的字典
protocol_versions = {
    0: "Tracker 1.1.0",
    1: "Tracker 1.1.1",
    2: "OBD 2.5.1",
    3: "OBD 2.5.2",
    4: "OBD 2.6.13 - 不支持",
    5: "OBD 808 - 不支持",
    6: "G - 支持"
}

# 使用协议版本号初始化SDK
protocol_version = 3  # 示例：选择 Tracker 1.1.1
protocol_description = protocol_versions.get(protocol_version, "未知协议")

print(f"初始化SDK，协议版本号：{protocol_version} ({protocol_description})")

json_sdk.initialise(JsonLogLevel.JSON_LOG_LEVEL_DEBUG, '.\\logs', 'logfile.log')

# 加载 Excel 文件
workbook = openpyxl.load_workbook('1120-json.xlsx')
sheet = workbook.active

# 869595060730438 key ↓
# mcukey = "3F17FC9852ACC2856C57805589AE5A363B3522F48378398F80686D00EEA7ACB6"
# 869595060002739 key ↓
mcukey = "3F17FC9852ACC2856C57805589AE5A363B3522F48378398F80686D00EEA7ACB6"
mcukey_value = "MCUKEY：" + mcukey

protocol = "协议版本号：" + protocol_description

now_data = int((datetime.now(timezone.utc)).timestamp() * 1000)
bjtime = (datetime.utcfromtimestamp(now_data / 1000) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
test_time = "执行时间：" + bjtime

sheet.cell(row=1, column=10, value=mcukey_value)
sheet.cell(row=2, column=10, value=test_time)
sheet.cell(row=3, column=10, value=protocol)

# 遍历 A 列的每一行
for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_col=1, values_only=True), start=1):
    in_json_data = row[0]
    # 创建 ctypes 缓冲区
    out_buffer = ctypes.create_string_buffer(3072)
    out_length = 3072
    try:
        # 清除buffer占用地址
        ctypes.memset(out_buffer, 0, 3072)

        package_result, packaged_data = json_sdk.frame_package(in_json_data, len(in_json_data), out_buffer,
                                                               out_length, mcukey)
        # 将json转换后的数据写入 B 列
        formatted_hex = packaged_data.hex()
        sheet.cell(row=row_idx, column=2, value=formatted_hex)

        # # 清除buffer占用地址
        ctypes.memset(out_buffer, 0, 3072)

        in_buffer = ctypes.create_string_buffer(bytes.fromhex(formatted_hex))
        in_length = len(formatted_hex) // 2
        parse_result, parsed_data = json_sdk.frame_parse(in_buffer, in_length, out_buffer, out_length, mcukey)
        # 判断解析结果是否为空，如果为空，跳过本次循环
        if parse_result != 0:
            continue
        # 获取错误描述
        error_description = json_sdk.get_error_description(parse_result)
        print("Error Description:", error_description)
        try:
            parsed_json = json.loads(parsed_data)
            formatted_json = json.dumps(parsed_json, indent=4)
            print("Parsed Data:", formatted_json)

            # 将解析后的数据写入 C 列
            sheet.cell(row=row_idx, column=3, value=formatted_json)

            # 解析JSON数据，提取MsgIDDesc
            parsed_json = json.loads(formatted_json)
            msg_id_desc = parsed_json['body']['MsgIDDesc']
            sheet.cell(row=row_idx, column=8, value=msg_id_desc)

            ctypes.memset(out_buffer, 0, 3072)
        except json.JSONDecodeError as e:
            print("Failed to parse JSON:", e)
            # 将错误信息写入 C 列
            sheet.cell(row=row_idx, column=3, value="JSON Decode Error")
    except Exception as e:
        print(f"Failed to process row {row_idx}: {e}")
        # 将输入缓冲区创建错误信息写入 B 列
        sheet.cell(row=row_idx, column=2, value="data fail")
workbook.save('1120-json.xlsx')


for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_col=3, values_only=True), start=1):
    a_col_value = row[0]
    c_col_value = row[2]

    # 检查 C 列的值是否为 None 或 "Data Fail"
    if c_col_value is None or c_col_value == "Data Fail":
        result = "FAIL"
    else:
        # 比对 A 列和 C 列的值 (JSON)
        if a_col_value == c_col_value:
            result = "PASS"
        else:
            result = "FAIL"

    # 将结果写入 D 列
    result_cell_D = sheet.cell(row=row_idx, column=4, value=result)
    # 定义红色填充
    red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
    if result == "FAIL":
        result_cell_D.fill = red_fill

# 保存修改后的 Excel 文件
workbook.save('1120-json.xlsx')
#

# 遍历 C 列的每一行
for row_idx, row in enumerate(sheet.iter_rows(min_row=1, min_col=3, max_col=3,  values_only=True), start=1):
    in_json_data = row[0]
    # 创建 ctypes 缓冲区
    out_buffer = ctypes.create_string_buffer(3072)
    out_length = 3072
    try:
        # 清除buffer占用地址
        ctypes.memset(out_buffer, 0, 3072)

        package_result, packaged_data = json_sdk.frame_package(in_json_data, len(in_json_data), out_buffer,
                                                               out_length, mcukey)
        # 将json转换后的数据写入 F 列
        formatted_hex = packaged_data.hex()
        sheet.cell(row=row_idx, column=6, value=formatted_hex)

        # # 清除buffer占用地址
        ctypes.memset(out_buffer, 0, 3072)

    except Exception as e:
        print(f"Failed to process row {row_idx}: {e}")
        # 将输入缓冲区创建错误信息写入 F 列
        sheet.cell(row=row_idx, column=6, value="data fail")
workbook.save('1120-json.xlsx')


# 遍历第一列→第六列
for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_col=6, values_only=True), start=1):
    b_col_value = row[1]
    e_col_value = row[5]

    # 检查 C 列的值是否为 None 或 "Data Fail"
    if b_col_value is None or e_col_value == "Data Fail":
        result = "FAIL"
    else:
        # 比对 B 列和 E 列的值 （HEX）
        if b_col_value == e_col_value:
            result = "PASS"
        else:
            result = "FAIL"

    # 将结果写入 G 列
    result_cell_G = sheet.cell(row=row_idx, column=7, value=result)

    # 定义红色填充
    red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
    if result == "FAIL":
        result_cell_G.fill = red_fill

# 保存修改后的 Excel 文件
workbook.save('1120-json.xlsx')

# 测试思路
# 1：获取原始的JSON数据 A列
# 2：通过SDK解析JSON数据为HEX B列
# 3: 反向通过SDK解析HEX数据为JSON C列
# 4：对比原始的 A列（JSON）和 C列（JSON）的差异性 D列
# 5: 空出 E列
# 6：再次通过解析C列数据形成HEX F列
# 7：对比A列解析出的HEX（B列）与C列解析出的HEX（F列） G列
# 8：将JSON文件中的MsgIDDesc 提取出来放入 H列
#

# 如果不需要获取原始数据，从本地读取原始数据，屏蔽 server_get_data函数及上下代码，从本地读取数据（JSON转换HEX不涉及，代码已删除）
# limit = 1000
# 这里是取了七天内的数据，最大取1000条

# 需要修改对应测试的协议类型
# json_sdk.initialise(JsonLogLevel.JSON_LOG_LEVEL_DEBUG, '.\\logs', 'logfile.log', 1, 0)
# 需要修改最大的条数
# start = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)









