import datetime
import re
import sys
import struct
from typing import List, Union, Dict, Any, Optional

def _to_hex_list(segment: Union[str, List[str]]) -> List[str]:
    if isinstance(segment, list):
        return [b.upper() for b in segment]
    s = ''.join(segment.split()).upper()
    return [s[i:i+2] for i in range(0, len(s), 2)]

def _utc_to_beijing(hex_bytes: List[str]) -> str:
    try:
        ts = int(''.join(hex_bytes), 16)
        dt = datetime.datetime.utcfromtimestamp(ts) + datetime.timedelta(hours=8)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''.join(hex_bytes)

def _parse_ieee754_one(hex_bytes: List[str]) -> Optional[float]:
    if len(hex_bytes) < 4:
        return None
    chunk = ''.join(hex_bytes[0:4])
    try:
        return struct.unpack('>f', bytes.fromhex(chunk))[0]
    except Exception:
        return None

def parse_segment(segment: Union[str, List[str]]) -> Dict[str, Any]:
    """
    解析单段数据（段头包含2字节长度）:
      1-2: 数据长度 (16->10)
      3-6: 时间 (UTC->北京时间)
      7-12: BT MAC 原始
      13-14: major 原始
      15-16: minor 原始
      17-20: RSSI（4字节）按 IEEE754 单精度大端解析
      从第21位（索引20）开始解析 K(2字节)-L(1字节)-V(L字节)
    返回的 KLV 列表仅包含 title 和 value
    """
    hex_list = _to_hex_list(segment)
    out: Dict[str, Any] = {}
    n = len(hex_list)

    # 1-2 位 数据长度
    if n >= 1:
        length_hex = ''.join(hex_list[0:1])
        out['数据长度_raw'] = length_hex
        try:
            out['数据长度'] = int(length_hex, 16)
        except Exception:
            out['数据长度'] = None
    else:
        out['数据长度_raw'] = ''
        out['数据长度'] = None

    # 3-6 位 时间
    if n >= 6:
        out['时间_raw'] = ''.join(hex_list[1:5])
        out['时间'] = _utc_to_beijing(hex_list[1:5])
    else:
        out['时间_raw'] = ''
        out['时间'] = None

    # 7-12 位 BT MAC 原始
    out['BT_MAC_raw'] = ''.join(hex_list[5:11]) if n >= 12 else ''.join(hex_list[5:n]) if n > 6 else ''

    # 13-14 major 原始
    out['major'] = ''.join(hex_list[11:13]) if n >= 14 else ''

    # 15-16 minor 原始
    out['minor'] = ''.join(hex_list[13:15]) if n >= 16 else ''

    # 17-20 RSSI（四字节 IEEE754 单精度，大端）
    rssi_bytes = hex_list[15:19] if n >= 20 else hex_list[15:n] if n > 16 else []
    out['RSSI_raw'] = ''.join(rssi_bytes)
    rssi_val = _parse_ieee754_one(rssi_bytes)
    out['RSSI'] = rssi_val if rssi_val is not None else out['RSSI_raw']

    # KLV 从第21位（索引20）开始
    klv_list: List[Dict[str, Any]] = []
    ptr = 19
    while ptr + 3 <= n:
        K = ''.join(hex_list[ptr:ptr+2]).upper()
        L_hex = hex_list[ptr+2]
        try:
            L = int(L_hex, 16)
        except Exception:
            break
        ptr += 3
        if ptr + L > n:
            V_bytes = hex_list[ptr:n]
            ptr = n
        else:
            V_bytes = hex_list[ptr:ptr+L]
            ptr += L

        V_raw = ''.join(V_bytes)
        # 仅保留 title 和 value，去掉 K/L/V 原始展示
        entry: Dict[str, Any] = {}

        if K == '00C8':
            try:
                val = int(V_raw, 16) * 0.001
                entry['title'] = 'tag电压'
                entry['value'] = f"{val:.3f} V --[00C8]"
            except Exception:
                entry['title'] = 'tag电压'
                entry['value'] = V_raw + " --[00C8]"
        elif K == '00C9':
            entry['title'] = '防篡改标志'
            entry['value'] = V_raw + " --[00C9]"
        elif K == '00CA':
            entry['title'] = '传感器状态'
            entry['value'] = V_raw + " --[00CA]"
        elif K == '00CC':
            try:
                val = int(V_raw, 16) * 0.1 - 40
                entry['title'] = '信标温度'
                entry['value'] = f"{val:.1f} ℃ --[00CC]"
            except Exception:
                entry['title'] = '信标温度'
                entry['value'] = V_raw + " --[00CC]"
        elif K == '00CD':
            entry['title'] = 'G-SENSOR数据'
            entry['value'] = V_raw + " --[00CD]"
        elif K == '00CE':
            entry['title'] = '信标角度'
            entry['value'] = V_raw + " --[00CE]"
        elif K == '00CF':
            entry['title'] = '信标倾斜角度'
            entry['value'] = V_raw + " --[00CF]"
        elif K == '00D0':
            entry['title'] = '信标运动事件计数'
            entry['value'] = V_raw + " --[00D0]"
        elif K == '00D1':
            entry['title'] = '信标碰撞事件计数'
            entry['value'] = V_raw + " --[00D1]"
        elif K == '00D2':
            entry['title'] = '信标坠落事件计数'
            entry['value'] = V_raw + " --[00D2]"
        else:
            entry['title'] = f'未知标签_{K}'
            entry['value'] = V_raw

        klv_list.append(entry)

    out['KLV'] = klv_list
    out['剩余字节'] = n - ptr
    return out

def parse_hex_string(hex_str: str) -> Dict[str, Any]:
    hex_str = re.sub(r'\s+', '', hex_str)
    hex_list = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
    # print(hex_str)
    # print(hex_list)
    if len(hex_list) < 70:
        raise ValueError(f"数据长度不足，当前字节数：{len(hex_list)}，需要至少113字节")
    result: Dict[str, Any] = {}

    major = hex_list[29]
    minor = hex_list[30]
    key = major + minor

    if key == '0301':
        result['major'] = major
        result['minor'] = minor
        utc_hex = ''.join(hex_list[31:35])
        try:
            utc_int = int(utc_hex, 16)
            utc_time = datetime.datetime.utcfromtimestamp(utc_int)
            beijing_time = utc_time + datetime.timedelta(hours=8)
            result['UTC时间'] = beijing_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            result['UTC时间'] = utc_hex
        # 其余 0301 字段解析保留用户原逻辑（这里按原代码实现）
        # ... （略） ...
        return result

    elif key == '0607':
        result['major'] = major
        result['minor'] = minor

        utc_hex = ''.join(hex_list[31:35])
        try:
            utc_int = int(utc_hex, 16)
            utc_time = datetime.datetime.utcfromtimestamp(utc_int)
            beijing_time = utc_time + datetime.timedelta(hours=8)
            result['UTC时间'] = beijing_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            result['UTC时间'] = utc_hex

        result['GPS'] = ' '.join(hex_list[35:59])
        result['消息总数'] = int(hex_list[59], 16) if len(hex_list) >= 60 else None
        result['消息索引'] = int(hex_list[60], 16) if len(hex_list) >= 61 else None
        result['BLE数据编号'] = int(hex_list[61], 16) if len(hex_list) >= 62 else None

        # 从第63位（索引62）开始，按两字节长度(包含自身)解析段
        ptr = 62
        seg_no = 1
        while True:
            remaining = len(hex_list) - ptr
            # 若剩余字节小于20，不再分割，把剩余原始数据输出并结束
            if remaining < 25:
                result['尾部原始'] = ''.join(hex_list[ptr:]) if remaining > 0 else ''
                break
            if ptr + 2 > len(hex_list):
                result['尾部原始'] = ''.join(hex_list[ptr:]) if len(hex_list) > ptr else ''
                break

            length_hex = ''.join(hex_list[ptr:ptr+1])
            try:
                seg_len = int(length_hex, 16)
            except Exception:
                result['尾部原始'] = ''.join(hex_list[ptr:])
                break

            # 若段长度小于20，将该部分视为尾部原始并停止分割
            if seg_len < 20:
                end = ptr + seg_len
                if end > len(hex_list):
                    end = len(hex_list)
                result['尾部原始'] = ''.join(hex_list[ptr:end])
                break

            if seg_len <= 0:
                result['尾部原始'] = ''.join(hex_list[ptr:])
                break

            start = ptr
            end = start + seg_len
            if end > len(hex_list):
                end = len(hex_list)

            seg_bytes = hex_list[start:end]  # 含长度字段
            result[f'消息长度{seg_no}'] = seg_len
            result[f'第{seg_no}段数据原始'] = ''.join(seg_bytes)
            try:
                result[f'第{seg_no}段解析'] = parse_segment(seg_bytes)
            except Exception as e:
                result[f'第{seg_no}段解析错误'] = str(e)

            ptr = end
            seg_no += 1

        result['剩余字节'] = len(hex_list) - ptr
        return result

    elif key == '0606':
        result['major'] = major
        result['minor'] = minor
        result['消息总数'] = int(hex_list[31], 16) if len(hex_list) > 31 else None
        result['当前消息索引'] = int(hex_list[32], 16) if len(hex_list) > 32 else None
        result['温湿度编号'] = int(hex_list[33], 16) if len(hex_list) > 33 else None

        groups: List[Dict[str, Any]] = []
        ptr = 34  # 从第35位开始（索引34）
        total_len = len(hex_list)
        group_no = 1

        while ptr < total_len:
            remaining = total_len - ptr
            # 按需求：若剩余小于20字节则停止（每次完整循环后也会判断）
            if remaining < 20:
                result['尾部原始'] = ''.join(hex_list[ptr:]) if remaining > 0 else ''
                break

            # 先至少读到第10字节用于判断 THS_ID（组内索引9）
            if remaining < 10:
                result['尾部原始'] = ''.join(hex_list[ptr:])
                break
            try:
                ths_id = int(hex_list[ptr + 9], 16)
            except Exception:
                result['尾部原始'] = ''.join(hex_list[ptr:])
                break

            # 决定基础长度与是否需要扩展到包含门禁开关
            if ths_id != 0:
                # 非0：基础需包含到 MAC，共24字节
                if remaining < 24:
                    result['尾部原始'] = ''.join(hex_list[ptr:])
                    break
                # 检查是否存在 00D3（位于全局 ptr+24:ptr+26）
                tag = ''.join(hex_list[ptr + 24: ptr + 26]).upper() if remaining >= 26 else ''
                if tag == '00D3':
                    # 需完整 28 字节才能取门禁开关
                    if remaining < 28:
                        result['尾部原始'] = ''.join(hex_list[ptr:])
                        break
                    advance = 28
                else:
                    advance = 24
            else:
                # ths_id == 0：基础到 MAC 为16字节
                if remaining < 16:
                    result['尾部原始'] = ''.join(hex_list[ptr:])
                    break
                tag = ''.join(hex_list[ptr + 16: ptr + 18]).upper() if remaining >= 18 else ''
                if tag == '00D3':
                    if remaining < 20:
                        result['尾部原始'] = ''.join(hex_list[ptr:])
                        break
                    advance = 20
                else:
                    advance = 16

            group_bytes = hex_list[ptr: ptr + advance]
            g: Dict[str, Any] = {}

            # 1-4 北京时间（组内索引0:4）
            try:
                g['北京时间'] = _utc_to_beijing(group_bytes[0:4])
            except Exception:
                g['北京时间'] = ''.join(group_bytes[0:4])

            # 5-6 温度（组内索引4:6）
            temp_hex = ''.join(group_bytes[4:6]).upper() if len(group_bytes) >= 6 else ''
            if temp_hex == 'FFFF':
                g['温度'] = 'FFFF'
            else:
                try:
                    g['温度'] = f"{int(temp_hex, 16) * 0.1 - 40:.1f} ℃"
                except Exception:
                    g['温度'] = temp_hex

            # 7-8 湿度（组内索引6:8）
            hum_hex = ''.join(group_bytes[6:8]).upper() if len(group_bytes) >= 8 else ''
            if hum_hex == 'FFFF':
                g['湿度'] = 'FFFF'
            else:
                try:
                    g['湿度'] = f"{int(hum_hex, 16) * 0.1:.1f} %"
                except Exception:
                    g['湿度'] = hum_hex

            # 9 电量（组内索引8）
            batt_hex = group_bytes[8].upper() if len(group_bytes) > 8 else ''
            if batt_hex == 'FF':
                g['电量'] = 'FF'
            else:
                try:
                    g['电量'] = f"{int(batt_hex, 16)} %"
                except Exception:
                    g['电量'] = batt_hex

            # 10 蓝牙THS ID（组内索引9）
            try:
                g['蓝牙THS_ID'] = int(group_bytes[9], 16)
            except Exception:
                g['蓝牙THS_ID'] = group_bytes[9]

            # 根据 THS_ID 解析后续字段
            if g['蓝牙THS_ID'] != 0:
                # 11-18 蓝牙ID（组内索引10:18）
                bt_id_hex = ''.join(group_bytes[10:18]) if len(group_bytes) >= 18 else ''
                try:
                    bt_id_str = bytes.fromhex(bt_id_hex).decode('ascii', errors='ignore')
                    g['蓝牙ID'] = int(bt_id_str) if bt_id_str.isdigit() else bt_id_str
                except Exception:
                    g['蓝牙ID'] = bt_id_hex

                # 19-24 蓝牙MAC（组内索引18:24）
                g['蓝牙MAC'] = ''.join(group_bytes[18:24]) if len(group_bytes) >= 24 else ''.join(group_bytes[18:])

                # 仅当 advance 包含门禁开关时才输出门禁开关（组内索引24:28）
                if advance >= 28:
                    g['门禁开关'] = ''.join(group_bytes[24:28]) + " -----最后一位 00/01 判断有无锁 01开00合"
            else:
                # ths_id == 0：11-16 蓝牙MAC（组内索引10:16）
                g['蓝牙MAC'] = ''.join(group_bytes[10:16]) if len(group_bytes) >= 16 else ''.join(group_bytes[10:])
                # 仅当 advance 包含门禁开关时才输出门禁开关（组内索引16:20）
                if advance >= 20:
                    g['门禁开关'] = ''.join(group_bytes[16:20]) + " -----最后一位 00/01 判断有无锁"

            g['组序号'] = group_no
            groups.append(g)

            # 移动指针到本组末尾（注意：若没有 00D3 则 advance 为基础长度，不会消耗后续潜在门禁字段）
            ptr += advance
            group_no += 1

            # 每次解析完一组后判断剩余是否小于20，若小于则将剩余记录并退出
            if total_len - ptr < 20:
                if ptr < total_len:
                    result['尾部原始'] = ''.join(hex_list[ptr:])
                break

        result['温湿度组'] = groups
        result['剩余字节'] = total_len - ptr
        return result


    elif key == '0000':
        result['major'] = major
        result['minor'] = minor
        ignition_hex = ''.join(hex_list[31:35])
        try:
            ignition_int = int(ignition_hex, 16)
            ignition_time = datetime.datetime.utcfromtimestamp(ignition_int) + datetime.timedelta(hours=8)
            result['点火时间'] = ignition_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            result['点火时间'] = ignition_hex
        # 其余 0000 字段解析保留用户原逻辑（这里按原代码实现）
        # ... （略） ...
        return result

    else:
        result['错误'] = f"未识别的major+minor: {key}"
        return result

# def print_result(obj: Any, indent: int = 0) -> None:
#     pad = ' ' * indent
#     if isinstance(obj, dict):
#         for k, v in obj.items():
#             if isinstance(v, (dict, list)):
#                 print(f"{pad}{k}:")
#                 print_result(v, indent + 4)
#             else:
#                 # 键与值换行显示
#                 print(f"{pad}{k}:")
#                 print(f"{pad}    {v}")
#     elif isinstance(obj, list):
#         for i, item in enumerate(obj, 1):
#             if isinstance(item, (dict, list)):
#                 print(f"{pad}- [{i}]")
#                 print_result(item, indent + 4)
#             else:
#                 print(f"{pad}- {item}")
#     else:
#         print(f"{pad}{obj}")


def print_result(obj: Any, indent: int = 0) -> None:
    pad = ' ' * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            # KLV 专用格式：KLV: \n- [i]\n    title: value
            if k == 'KLV' and isinstance(v, list):
                print(f"{pad}{k}:")
                for i, item in enumerate(v, 1):
                    print(f"{pad}- [{i}]")
                    if isinstance(item, dict):
                        title = item.get('title')
                        value = item.get('value')
                        if title is not None and value is not None:
                            print(f"{pad}    {title}: {value}")
                        else:
                            # 回退：打印字典中所有键值（每行一对）
                            for kk, vv in item.items():
                                print(f"{pad}    {kk}: {vv}")
                    else:
                        print(f"{pad}    {item}")
            # 普通列表：键行单独，列表项用 - [i] 行，项内容缩进在一行
            elif isinstance(v, list):
                print(f"{pad}{k}:")
                for i, item in enumerate(v, 1):
                    print(f"{pad}- [{i}]")
                    if isinstance(item, dict):
                        for kk, vv in item.items():
                            print(f"{pad}    {kk}: {vv}")
                    else:
                        print(f"{pad}    {item}")
            # 嵌套字典：键行单独，然后递归（子项保持一行格式）
            elif isinstance(v, dict):
                print(f"{pad}{k}:")
                print_result(v, indent + 4)
            # 普通键值对：同一行显示
            else:
                print(f"{pad}{k}: {v}")
    elif isinstance(obj, list):
        # 顶层为列表时也遵循 - [i] 单独一行规则
        for i, item in enumerate(obj, 1):
            print(f"{pad}- [{i}]")
            if isinstance(item, dict):
                for kk, vv in item.items():
                    print(f"{pad}    {kk}: {vv}")
            else:
                print(f"{pad}    {item}")
    else:
        print(f"{pad}{obj}")




if __name__ == "__main__":
    print("请输入HEX字符串（可多行，Ctrl+D结束输入）：")
    hex_str = sys.stdin.read().upper()
    try:
        result = parse_hex_string(hex_str)
        print_result(result)
    except ValueError as e:
        print(e)