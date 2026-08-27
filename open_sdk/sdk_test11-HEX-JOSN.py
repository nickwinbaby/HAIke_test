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
    #    return self.json_sdk.json_protocol_set_protocol(protocolType)

    # def init_protocol(self):
    #     return self.json_sdk.json_protocol_init()

    def set_vehicle_type(self, vehicleType):
        return self.json_sdk.json_protocol_set_vehicle_type(vehicleType)

    def frame_package(self, pInBuff, usInLength, pOutBuff, usOutLength, mcukey):
        mcukey_hex = ascii_to_hex(mcukey)
        out_length = ctypes.c_int(usOutLength)
        result = self.json_sdk.json_protocol_frame_package(pInBuff.encode('utf-8'), usInLength, pOutBuff,
                                                          ctypes.byref(out_length), mcukey_hex, protocol_version)
        return result, pOutBuff.raw[:out_length.value]

    def frame_parse(self, pInBuff, usInLength, pOutBuff, usOutLength, mcukey):
        mcukey_hex = ascii_to_hex(mcukey)
        out_length = ctypes.c_int(usOutLength)
        result = self.json_sdk.json_protocol_frame_parse(pInBuff, usInLength, pOutBuff, out_length, mcukey_hex, protocol_version)
        parsed_data = pOutBuff.raw[:out_length.value].decode('utf-8').rstrip('\x00')
        return result, parsed_data
    #
    # # 针对python执行错误原始数据进行过滤优化
    # def frame_parse(self, pInBuff, usInLength, pOutBuff, usOutLength, mcukey):
    #     mcukey_hex = ascii_to_hex(mcukey)
    #     out_length = ctypes.c_int(usOutLength)
    #     result = self.json_sdk.json_protocol_frame_parse(pInBuff, usInLength, pOutBuff, out_length, mcukey_hex)
    #     # parsed_data = pOutBuff.raw[:out_length.value].decode('utf-8').rstrip('\x00')
    #     raw_data = pOutBuff.raw[:out_length.value]
    #     # 检测编码
    #     ret = chardet.detect(raw_data)
    #     encoding = ret['encoding']
    #     print(f"检测到的编码: {encoding}")
    #     # 用检测到的编码解码
    #     try:
    #         parsed_data = raw_data.decode(encoding).rstrip('\x00')
    #     except UnicodeDecodeError as e:
    #         print(f"UnicodeDecodeError: {e}")
    #         # 根据需要处理或记录错误
    #         parsed_data = raw_data.decode('utf-8', errors='ignore').rstrip('\x00')
    #     return result, parsed_data

    def initialise(self, log_level, output_path, filename):
        self.init_logger(log_level, output_path, filename)
        print("Library Version:", self.get_library_version())
        print("Error Description (Code 0):", self.get_error_description(0))
        # print("Set Protocol (Type {}):".format(protocol_type), self.set_protocol(protocol_type))
        # print("Initialize Protocol:", self.init_protocol())
        # print("Set Vehicle Type (Type {}):".format(vehicle_type), self.set_vehicle_type(vehicle_type))



# # 从这里开始注释 ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
# # 创建一个新的Excel工作簿
# wb = Workbook()
# ws = wb.active
# ws.title = "Raw Data"
#
# # 从服务器获取原始数据
# def server_get_data(imei_num):
#     # 请求数据 F103/03地址（内网地址）
#     url_set_dat = "http://10.85.40.3:8082/testAPI/rawData"
#
#     headers = {
#         'Content-Type': 'application/json',
#         'Authorization': 'Bearer YOUR_ACCESS_TOKEN'  # 如果需要认证
#     }
#
#     # 获取当前 UTC 时间，取前七天到当前时间的数据
#     start = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)
#     stop = int((datetime.now(timezone.utc)).timestamp() * 1000)
#     offset = 0
#     limit = 1000
#
#     # UTC 时间戳转北京时间
#     start_bjtime = (datetime.utcfromtimestamp(start / 1000) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
#     stop_bjtime = (datetime.utcfromtimestamp(stop / 1000) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
#
#     print("北京时间戳", start_bjtime, stop_bjtime, "UNIX时间戳:", start, stop)
#
#     # 请求数据的格式
#     body_data = {
#         'imei': imei_num,
#         'start': start,
#         'stop': stop,
#         'offset': offset,
#         'limit': limit
#     }
#
#     try:
#         # 发送 POST 请求
#         response_raw_data = requests.post(url_set_dat, headers=headers, json=body_data)
#
#         # 检查响应状态码和内容
#         if response_raw_data.status_code == 200:
#             print('请求成功:', response_raw_data.json())
#             raw_data = response_raw_data.json()
#             file_path = r"\raw_data.json"
#
#             with open(file_path, "w") as file:
#                 json.dump(raw_data, file)
#             # print(os.getcwd(), "查看代码执行路径")
#             return raw_data
#         else:
#             print('请求失败:', response_raw_data.status_code, response_raw_data.text)
#             return None
#     except requests.exceptions.RequestException as e:
#         print('请求过程中出现错误:', e)
#         return None
#
#
# encryptDataString = server_get_data("869595060730438")
#
# # 将每行的 encryptDataString 写入 Excel 中
# for index, item in enumerate(encryptDataString):
#     if 'encryptDataString' in item:
#         ws.cell(row=index + 1, column=1, value=item['encryptDataString'])
#
# # 从服务器获取数据
#
# file_path = r"gmy.xlsx"
# wb.save(file_path)
# print(f"数据已保存至 {file_path}")
# # 从这里开始注释 ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑


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
    4: "G - 不支持",
    5: "4.0.0",
    6: "4.0.1",
    7: "4.0.2"
}

# 使用协议版本号初始化SDK
protocol_version = 7  # 示例：选择 Tracker 1.1.1
protocol_description = protocol_versions.get(protocol_version, "未知协议")

print(f"初始化SDK，协议版本号：{protocol_version} ({protocol_description})")

json_sdk.initialise(JsonLogLevel.JSON_LOG_LEVEL_DEBUG, '.\\logs', 'logfile.log')

# 加载 Excel 文件
workbook = openpyxl.load_workbook('gmy.xlsx')
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
    in_buffer_hex = row[0]
    if in_buffer_hex is None:
        continue
    try:
        # 将 in_buffer_hex 转换为字节
        in_buffer = ctypes.create_string_buffer(bytes.fromhex(in_buffer_hex))
        print(in_buffer, "in_buffer")
        in_length = len(in_buffer_hex) // 2
        # 创建 ctypes 缓冲区
        out_buffer = ctypes.create_string_buffer(3072)
        print(out_buffer, "out_buffer")
        out_length = 3072
    # 调用 frame_parse 函数
        try:
            ctypes.memset(out_buffer, 0, 3072)
            parse_result, parsed_data = json_sdk.frame_parse(in_buffer, in_length, out_buffer, out_length, mcukey)
            print(parse_result, "parse_result ")
            print(parsed_data, " parsed_data")
            # 判断解析结果是否为空，如果为空，跳过本次循环
            if parse_result != 0:
                continue
            # 获取错误描述
            error_description = json_sdk.get_error_description(parse_result)
            print("Error Description:", error_description)

            # 假设输出缓冲区包含一个以 null 终止的字符串
            # parsed_data = out_buffer.value.decode('utf-8').rstrip('\x00')

            try:
                parsed_json = json.loads(parsed_data)
                formatted_json = json.dumps(parsed_json, indent=4)
                print("Parsed Data:", formatted_json)

                # 将解析后的数据写入 B 列
                sheet.cell(row=row_idx, column=2, value=formatted_json)
                ctypes.memset(out_buffer, 0, 3072)

                # 将解析后的JSON数据转化为HEX
                package_result, packaged_data = json_sdk.frame_package(parsed_data, len(parsed_data), out_buffer,
                                                                       out_length, mcukey)
                # 将json转换后的数据写入 C 列
                formatted_hex = packaged_data.hex()
                sheet.cell(row=row_idx, column=3, value=formatted_hex)


            except json.JSONDecodeError as e:
                print("Failed to parse JSON:", e)
                # 将错误信息写入 B 列
                sheet.cell(row=row_idx, column=2, value="JSON Decode Error")
        except Exception as e:
            print("Failed to execute frame_parse:", e)
        # 将错误信息写入 B 列
            sheet.cell(row=row_idx, column=2, value="data fail")
    except Exception as e:
        print(f"Failed to process row {row_idx}: {e}")
    # 将输入缓冲区创建错误信息写入 B 列
        sheet.cell(row=row_idx, column=2, value="data fail")
    # finally:
    #     # 清空输出缓冲区
    #     try:
    #         if 'out_buffer' in locals() and 'out_length' in locals():
    #             ctypes.memset(out_buffer, 0, out_length)
    #     except Exception as e:
    #         print(f"Failed to clear output buffer for row {row_idx}: {e}")
workbook.save('gmy.xlsx')

for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_col=3, values_only=True), start=1):
    a_col_value = row[0]
    c_col_value = row[2]

    # 检查 C 列的值是否为 None 或 "Data Fail"
    if c_col_value is None or c_col_value == "Data Fail":
        result = "FAIL"
    else:
        # 比对 A 列和 C 列的值
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
workbook.save('gmy.xlsx')


# 遍历 C 列的每一行
for row_idx, row in enumerate(sheet.iter_rows(min_row=1, min_col=3, max_col=3, values_only=True), start=1):
    in_buffer_hex = row[0]
    if in_buffer_hex is None:
        continue
    try:
        # 将 in_buffer_hex 转换为字节
        in_buffer = ctypes.create_string_buffer(bytes.fromhex(in_buffer_hex))
        in_length = len(in_buffer_hex) // 2
        # 创建 ctypes 缓冲区
        out_buffer = ctypes.create_string_buffer(3072)
        out_length = 3072
    # 调用 frame_parse 函数
        try:
            # 清除buffer占用地址
            ctypes.memset(out_buffer, 0, 3072)
            parse_result, parsed_data = json_sdk.frame_parse(in_buffer, in_length, out_buffer, out_length, mcukey)
            if parse_result != 0:
                continue
            # 获取错误描述
            error_description = json_sdk.get_error_description(parse_result)
            print("Error Description:", error_description)

            # 假设输出缓冲区包含一个以 null 终止的字符串
            # parsed_data = out_buffer.value.decode('utf-8').rstrip('\x00')

            try:
                parsed_json = json.loads(parsed_data)
                formatted_json = json.dumps(parsed_json, indent=4)
                print("Parsed Data:", formatted_json)

                # 将解析后的数据写入 F 列
                sheet.cell(row=row_idx, column=6, value=formatted_json)

                # 解析JSON数据，提取MsgIDDesc
                parsed_json = json.loads(formatted_json)
                msg_id_desc = parsed_json['body']['MsgIDDesc']
                sheet.cell(row=row_idx, column=8, value=msg_id_desc)

                # 清除buffer占用地址
                ctypes.memset(out_buffer, 0, 3072)


            except json.JSONDecodeError as e:
                print("Failed to parse JSON:", e)
                # 将错误信息写入 F 列
                sheet.cell(row=row_idx, column=6, value="JSON Decode Error")
        except Exception as e:
            print("Failed to execute frame_parse:", e)
        # 将错误信息写入 F 列
            sheet.cell(row=row_idx, column=6, value="data fail")
    except Exception as e:
        print(f"Failed to process row {row_idx}: {e}")
    # 将输入缓冲区创建错误信息写入 F 列
        sheet.cell(row=row_idx, column=6, value="data fail")
    # finally:
    #     # 清空输出缓冲区
    #     try:
    #         if 'out_buffer' in locals() and 'out_length' in locals():
    #             ctypes.memset(out_buffer, 0, out_length)
    #     except Exception as e:
    #         print(f"Failed to clear output buffer for row {row_idx}: {e}")
workbook.save('gmy.xlsx')


# 遍历第一列→第六列
for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_col=6, values_only=True), start=1):
    b_col_value = row[1]
    e_col_value = row[5]

    # 检查 C 列的值是否为 None 或 "Data Fail"
    if b_col_value is None or e_col_value == "Data Fail":
        result = "FAIL"
    else:
        # 比对 B 列和 E 列的值
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
workbook.save('gmy.xlsx')

# 测试思路
# 1：从服务器取云端原始加密数据 A 列
# 2：通过SDK解析加密数据，并形成JSON 格式 B列
# 3：反向通过SDK解析JSON数据为HEX  C列
# 4：比对原始的A列（HEX）和 C列（HEX）的差异性  D列
# 5：空出 F列
# 6：再次通过解析C列数据形成JSON格式 F列
# 7：比对A列解析出的JSON（B列）与C列解析出的JSON(F列) G列
# 8：将JSON文件中的MsgIDDesc 提取出来放入 H列

# 如果不需要获取原始数据，从本地读取原始数据，屏蔽 server_get_data函数及上下代码，从本地读取数据
# 需要修改对应测试的协议类型
# json_sdk.initialise(JsonLogLevel.JSON_LOG_LEVEL_DEBUG, '.\\logs', 'logfile.log', 1, 0)
# 需要修改最大的条数
# limit = 1000
# 这里是取了七天内的数据，最大取1000条
# start = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp() * 1000)









