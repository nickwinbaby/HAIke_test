import requests
import time
import datetime
import threading
import tkinter as tk
import tkinter.font as tkfont
import os,sys
import ctypes
from ctypes import wintypes
from tkinter import ttk, filedialog, scrolledtext

# ===================== 全局变量 =====================
stop_event = threading.Event()
is_running = False
POLL_CHECKPOINTS_SEC = (60, 90, 120, 150, 180, 210, 240)

# 下拉框映射关系
FOTA_TYPE_MAP = {
    "00-MCU": 0,
    # "01-MDM": 1,
    "02-BLE": 2,
    # "03-GNSS": 3,
    # "04-BOOT": 4,
    "05-AP": 5,
    # "06-CFG": 6,
    # "FF-HARDWARE": 255
}
DOWNLOAD_TYPE_MAP = {
    # "01-TCP": 1,
    "02-HTTP": 2
}

# ========== 【新增1】FOTA类型对应默认升级等待时长 ==========
FOTA_WAIT_CFG = {
    "00-MCU": 420,
    # "01-MDM": 420,
    "02-BLE": 180,
    # "03-GNSS": 420,
    # "04-BOOT": 420,
    "05-AP": 300,
    # "06-CFG": 420,
    # "FF-HARDWARE": 420
}

# ===================== 占位提示框工具函数 =====================
def set_placeholder(entry, placeholder):
    """设置输入框灰色占位提示"""
    entry.insert(0, placeholder)
    entry.config(foreground="#888888")

    def on_focus_in(event):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(foreground="black")

    def on_focus_out(event):
        if not entry.get().strip():
            entry.delete(0, tk.END)
            entry.insert(0, placeholder)
            entry.config(foreground="#888888")

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)

# ========== 【新增2】FOTA下拉切换自动更新等待时间 ==========
def on_fota_combo_change(event):
    selected_key = combo_fota.get()
    if selected_key in FOTA_WAIT_CFG:
        entry_wait.delete(0, tk.END)
        entry_wait.insert(0, str(FOTA_WAIT_CFG[selected_key]))


def setup_ui_style(root):
    """初始化界面样式"""
    root.option_add("*Font", ("Microsoft YaHei UI", 10))
    try:
        root.tk.call("tk", "scaling", 1.1)
    except Exception:
        pass

    style = ttk.Style(root)
    for theme in ("vista", "xpnative", "clam"):
        try:
            style.theme_use(theme)
            break
        except tk.TclError:
            continue
    style.configure("TLabel", font=("Microsoft YaHei UI", 10))
    style.configure("TEntry", font=("Microsoft YaHei UI", 10), padding=5)
    style.configure("TCombobox", font=("Microsoft YaHei UI", 10), padding=5)
    style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))

# ===================== 原有工具函数（解析逻辑不变） =====================
def log(msg, log_widget=None):
    """打印带时间戳的日志"""
    content = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    if log_widget:
        try:
            log_widget.configure(state="normal")
            log_widget.insert(tk.END, content)
            log_widget.see(tk.END)
        finally:
            log_widget.configure(state="disabled")
    else:
        print(content.strip())


def get_unix_ms(offset_sec=0):
    """获取当前 Unix 毫秒时间戳"""
    return str(int(time.time() * 1000 + offset_sec * 1000))


def format_beijing_time(utc_ts):
    """把 Unix UTC 秒时间戳转换为北京时间"""
    bj_tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.fromtimestamp(utc_ts, tz=datetime.timezone.utc).astimezone(bj_tz).strftime('%Y-%m-%d %H:%M:%S')


def hex_to_ascii(hex_list):
    """HEX byte 列表转换成 ASCII 字符串"""
    return ''.join(chr(int(h, 16)) for h in hex_list)


def get_check_version_name(fotaType):
    """根据 fotaType 决定当前需要校验哪个版本字段"""
    if fotaType == 5:
        return "AP"
    elif fotaType == 0:
        return "MCU"
    elif fotaType == 2:
        return "BLE"
    else:
        return "UNKNOWN"


def parse_ascii_length_field(hex_list, offset, field_name):
    """解析【长度 + ASCII内容】格式的字段"""
    if offset >= len(hex_list):
        raise ValueError(f"{field_name} 长度位置越界，offset={offset}")

    data_len = int(hex_list[offset], 16)
    if data_len == 0:
        return "", offset + 1

    start = offset + 1
    end = start + data_len
    if end > len(hex_list):
        raise ValueError(
            f"{field_name} 长度超过实际数据长度，"
            f"offset={offset}, length={data_len}, end={end}, total={len(hex_list)}"
        )
    value = hex_to_ascii(hex_list[start:end])
    return value, end


def parse_version_report_frame(hex_list, fotaType):
    """动态解析版本上报帧，根据fotaType决定是否解析到AP"""
    try:
        if len(hex_list) <= 24:
            return None
        if hex_list[24] != "01":
            return None

        offset = 29
        if offset + 2 > len(hex_list):
            return None

        hardware_version = ''.join(hex_list[offset:offset + 2])
        offset += 2

        # MCU版本
        mcu_version, offset = parse_ascii_length_field(
            hex_list, offset, "MCU version number"
        )

        modem_version, offset = parse_ascii_length_field(
            hex_list, offset, "Modem version number"
        )

        if offset + 4 > len(hex_list):
            raise ValueError("Report UTC time 长度不足")
        utc_hex = ''.join(hex_list[offset:offset + 4])
        utc_ts = int(utc_hex, 16)
        offset += 4

        # MCU模式只需要解析到 UTC 即可，后续字段对当前版本判定不是必须项
        if fotaType == 0:
            return {
                "hardware_version": hardware_version,
                "mcu_version": mcu_version,
                "modem_version": modem_version,
                "utc": utc_ts,
                "cfg_version": "",
                "fota_status": "",
                "ap_version": "",
                "mcu_is_t99": mcu_version.endswith("T99"),
                "ap_is_t99": False
            }

        cfg_version, offset = parse_ascii_length_field(
            hex_list, offset, "CFG file version"
        )

        if offset >= len(hex_list):
            raise ValueError("Support status of FOTA 位置越界")
        fota_status = hex_list[offset]
        offset += 1

        ap_version, offset = parse_ascii_length_field(
            hex_list, offset, "AP version number"
        )

        return {
            "hardware_version": hardware_version,
            "mcu_version": mcu_version,
            "modem_version": modem_version,
            "utc": utc_ts,
            "cfg_version": cfg_version,
            "fota_status": fota_status,
            "ap_version": ap_version,
            "mcu_is_t99": mcu_version.endswith("T99"),
            "ap_is_t99": ap_version.endswith("T99")
        }
    except ValueError as e:
        log(f"版本帧解析失败：{e}")
        return None


def parse_deviceinfo_ble_frame(hex_list):
    """解析 DeviceInfo(040C) 帧中的 BLE 版本及上报 UTC。"""
    if len(hex_list) <= 30 or hex_list[29:31] != ["04", "0C"]:
        return None

    try:
        offset = 31
        if offset + 4 > len(hex_list):
            raise ValueError("UTC字段数据不足")
        utc_ts = int("".join(hex_list[offset:offset + 4]), 16)
        offset += 4

        # DeviceInfo 中 BLE 版本前依次为手机号、ICCID、IMSI、Wi-Fi MAC、
        # BT MAC 和 5G Wi-Fi MAC，均采用单字节长度前缀。
        for field_name in ("手机号", "ICCID", "IMSI", "Wi-Fi MAC", "BT MAC", "5G Wi-Fi MAC"):
            if offset >= len(hex_list):
                raise ValueError(f"{field_name}长度字节缺失")
            field_len = int(hex_list[offset], 16)
            offset += 1
            if offset + field_len > len(hex_list):
                raise ValueError(f"{field_name}数据不足")
            offset += field_len

        if offset >= len(hex_list):
            raise ValueError("BLE版本长度字节缺失")
        ble_version_len = int(hex_list[offset], 16) & 0x3F
        offset += 1
        if offset + ble_version_len > len(hex_list):
            raise ValueError("BLE版本字符串数据不足")
        ble_version = bytes.fromhex("".join(hex_list[offset:offset + ble_version_len])).decode("ascii")

        return {
            "utc": utc_ts,
            "ble_version": ble_version,
            "ble_is_t99": ble_version.endswith("T99")
        }
    except (ValueError, UnicodeDecodeError) as e:
        log(f"DeviceInfo BLE版本帧解析失败：{e}")
        return None


def parse_target_version(rawdata_list, fotaType):
    """根据 fotaType 解析当前需要校验的版本"""
    candidates = []
    check_name = get_check_version_name(fotaType)

    if check_name == "UNKNOWN":
        log(f"当前 fotaType={fotaType} 暂不支持版本解析")
        return None

    for idx, hex_list in enumerate(rawdata_list):
        if fotaType == 2:
            result = parse_deviceinfo_ble_frame(hex_list)
        else:
            result = parse_version_report_frame(hex_list, fotaType)
        if not result:
            continue
        result["idx"] = idx
        candidates.append(result)

        if fotaType == 2:
            log(
                f"第 {idx + 1} 条 DeviceInfo 帧解析成功 | "
                f"UTC={result['utc']} | "
                f"北京时间={format_beijing_time(result['utc'])} | "
                f"BLE={result['ble_version']} | "
                f"BLE后三位是否T99={result['ble_is_t99']}"
            )
        else:
            log(
                f"第 {idx + 1} 条版本帧解析成功 | "
                f"UTC={result['utc']} | "
                f"北京时间={format_beijing_time(result['utc'])} | "
                f"MCU={result['mcu_version']} | "
                f"MCU后三位是否T99={result['mcu_is_t99']} | "
                f"AP={result['ap_version']} | "
                f"AP后三位是否T99={result['ap_is_t99']}"
            )

    if not candidates:
        log("未检测到有效版本上报帧")
        return None

    latest = max(candidates, key=lambda x: (x["utc"], x["idx"]))
    if fotaType == 2:
        version = latest["ble_version"]
        is_t99 = latest["ble_is_t99"]
    elif fotaType == 5:
        version = latest["ap_version"]
        is_t99 = latest["ap_is_t99"]
    else:
        version = latest["mcu_version"]
        is_t99 = latest["mcu_is_t99"]

    log(
        f"选取第 {latest['idx'] + 1} 条最新版本帧 | "
        f"校验字段={check_name} | "
        f"UTC={latest['utc']} | "
        f"北京时间={format_beijing_time(latest['utc'])} | "
        f"VERSION={version} | "
        f"后三位是否T99={is_t99}"
    )
    return version


def wait_version_progressive(imei, fotaType, window_start_time):
    """按60秒起步、每次增加30秒的节奏等待版本上报，最长240秒。"""
    log("渐进式等待版本上报：60/90/120/150/180/210/240秒检查")
    for checkpoint in POLL_CHECKPOINTS_SEC:
        deadline = window_start_time + checkpoint
        interruptible_sleep(max(0, deadline - time.time()))
        if stop_event.is_set():
            return None

        rawdata = fetch_raw_data(
            imei,
            start_ms=int(window_start_time * 1000),
            stop_ms=int(time.time() * 1000)
        )
        version = parse_target_version(rawdata, fotaType)
        if version is not None:
            log(f"累计{checkpoint}秒检查已获取版本，提前结束等待")
            return version

    log("累计60/90/120/150/180/210/240秒均未获取到版本，获取失败")
    return None


def wait_f108_progressive(imei, window_start_time):
    """按60秒起步、每次增加30秒的节奏等待F108上报，最长240秒。"""
    log("渐进式等待F108上报：60/90/120/150/180/210/240秒检查")
    for checkpoint in POLL_CHECKPOINTS_SEC:
        deadline = window_start_time + checkpoint
        interruptible_sleep(max(0, deadline - time.time()))
        if stop_event.is_set():
            return False

        rawdata = fetch_raw_data(
            imei,
            start_ms=int(window_start_time * 1000),
            stop_ms=int(time.time() * 1000)
        )
        if check_f108(rawdata):
            log(f"累计{checkpoint}秒检查检测到F108，提前结束等待")
            return True

    log("累计60/90/120/150/180/210/240秒均未检测到F108，上报失败")
    return False


def fetch_fota_detail(imei, fotaType, downloadType, TARGET_A, TARGET_B):
    """查询服务器上的 FOTA 任务详情"""
    url = f"http://10.85.40.3:8082/testAPI/fota/getDetail?imei={imei}"
    log(f"GET {url}")
    try:
        resp = requests.get(url, timeout=10).json()
    except Exception as e:
        log(f"请求FOTA详情接口失败: {e}")
        return None, None

    id_a = id_b = None
    for item in resp.get("data", []):
        log(item)
        if (
            item["fotaType"] == fotaType and
            item["downloadType"] == downloadType
        ):
            if item["targetVersion"] == TARGET_A:
                id_a = item["id"]
            elif item["targetVersion"] == TARGET_B:
                id_b = item["id"]
    log(f"FOTA detail: A_id={id_a}, B_id={id_b}")
    return id_a, id_b


def send_cmd(imei, cmd):
    """给设备下发命令"""
    url = "http://10.85.40.3:8088/client/send"
    data = {"imei": imei, "cmd": cmd}
    log(f"POST {url} -> {data}")
    try:
        r = requests.post(url, json=data, timeout=10)
        log(f"返回: {r.status_code} {r.text}")
        try:
            resp_json = r.json()
        except Exception:
            resp_json = {}
        if resp_json.get("message") == "成功":
            log("设备重启")
    except Exception as e:
        log(f"下发指令接口异常: {e}")


def fetch_raw_data(
    imei,
    start_offset_sec=None,
    stop_offset_sec=0,
    start_ms=None,
    stop_ms=None
):
    """从服务器获取设备 rawData"""
    url = "http://10.85.40.3:8082/testAPI/rawData"
    if start_ms is None:
        start_ms = get_unix_ms(start_offset_sec or 0)
    else:
        start_ms = str(int(start_ms))

    if stop_ms is None:
        stop_ms = get_unix_ms(stop_offset_sec)
    else:
        stop_ms = str(int(stop_ms))

    data = {
        "imei": imei,
        "start": start_ms,
        "stop": stop_ms,
        "offset": "0",
        "limit": "100"
    }
    log(f"POST {url} -> {data}")
    try:
        resp = requests.post(url, json=data, timeout=10).json()
    except Exception as e:
        log(f"请求rawData接口失败: {e}")
        return []

    if isinstance(resp, dict):
        items = resp.get("data", [])
    elif isinstance(resp, list):
        items = resp
    else:
        return []

    result = []
    for item in items:
        raw = item.get("rawDataString", "")
        hex_list = [raw[i:i + 2].upper() for i in range(0, len(raw), 2)]
        result.append(hex_list)
    log(f"获取 rawData 条数: {len(result)}")
    return result


def check_f108(rawdata_list):
    """检测 rawData 中是否存在 F108"""
    for idx, hex_list in enumerate(rawdata_list):
        if (
            len(hex_list) >= 31 and
            hex_list[24] == "04" and
            hex_list[29] + hex_list[30] == "F108"
        ):
            log(f"第 {idx + 1} 条 rawData 检测到 F108")
            return True
    log("未检测到 F108")
    return False


def check_upgrade_result_frame(hex_list):
    """检测当前 rawData 是否是升级成功结果帧"""
    if len(hex_list) < 37:
        return False, None
    if hex_list[24] != "03":
        return False, None
    key_id = hex_list[29] + hex_list[30]
    if key_id in ("0406", "0415") and hex_list[35] == "00":
        return True, key_id
    return False, key_id


def check_upgrade_success(rawdata_list, target_version, fotaType, wait_sec):
    """校验升级是否成功"""
    check_name = get_check_version_name(fotaType)
    for idx, hex_list in enumerate(rawdata_list):
        matched, key_id = check_upgrade_result_frame(hex_list)
        if matched:
            log(f"第 {idx + 1} 条 rawData 检测到升级成功结果帧：{key_id}")
            if fotaType == 2:
                log("BLE升级收到回执帧，跳过现场版本校验，后续重启设备后再校验新版本")
                return 2

            version = parse_target_version(rawdata_list, fotaType)
            log(
                f"升级结果上报成功 | "
                f"校验字段={check_name} | "
                f"当前 VERSION={version} | "
                f"目标 VERSION={target_version}"
            )
            return version == target_version
    log("未检测到 0406 / 0415 升级成功结果帧")
    return False


def check_upgrade_success_with_retry(
    imei,
    target_version,
    fotaType,
    wait_sec,
    window_start_time=None
):
    """带重试机制的升级成功校验，时间窗口使用配置值"""
    log("开始第一次升级完成校验")
    window_sec = wait_sec + 30 if fotaType == 2 else wait_sec
    if window_start_time is None:
        window_start_time = time.time() - window_sec

    rawdata = fetch_raw_data(
        imei,
        start_ms=int(window_start_time * 1000),
        stop_ms=int(time.time() * 1000)
    )
    result = check_upgrade_success(rawdata, target_version, fotaType, wait_sec)
    if result is not False:
        return result
    if stop_event.is_set():
        return False

    log("第一次失败，3 分钟后重试")
    interruptible_sleep(180)
    if stop_event.is_set():
        return False

    log("开始第二次升级完成校验")
    rawdata = fetch_raw_data(
        imei,
        start_ms=int(window_start_time * 1000),
        stop_ms=int(time.time() * 1000)
    )
    return check_upgrade_success(rawdata, target_version, fotaType, wait_sec)


def reset_fota_task(task_id):
    """重置指定 FOTA 任务"""
    url = "http://10.85.40.3:8082/testAPI/fota/resetFotaTaskDetail"
    log(f"POST {url} -> [{task_id}]")
    try:
        r = requests.post(url, json=[task_id], timeout=10)
        log(f"返回: {r.status_code} {r.text}")
    except Exception as e:
        log(f"重置FOTA任务异常: {e}")


# ===================== 可中断睡眠 =====================
def interruptible_sleep(seconds):
    """可被停止事件中断的睡眠"""
    start = time.time()
    while time.time() - start < seconds:
        if stop_event.is_set():
            return
        time.sleep(0.1)


# ===================== 主FOTA循环 =====================
def run_fota_loop(imei, target_a, target_b, fotaType, downloadType, upgrade_wait_sec):
    global is_running
    CMD_F102_0251 = "F1020251000001"
    CMD_F102_0018 = "F102001800000F"

    check_name = get_check_version_name(fotaType)
    if check_name == "UNKNOWN":
        log(f"当前 fotaType={fotaType} 暂不支持，只支持 fotaType=0/2/5")
        is_running = False
        return

    # 设置休眠时间
    send_cmd(imei, CMD_F102_0018)
    log("设置休眠时间为15分钟，等待 3 秒")
    interruptible_sleep(3)
    if stop_event.is_set():
        is_running = False
        return

    id_a, id_b = fetch_fota_detail(imei, fotaType, downloadType, target_a, target_b)
    if not id_a or not id_b:
        log("FOTA 包信息不完整，退出")
        is_running = False
        return

    count = 1
    current_version = None

    while not stop_event.is_set():
        log(f"========== 第 {count} 次 FOTA 循环 ==========")

        if count == 1:
            version_window_start = time.time()
            send_cmd(imei, CMD_F102_0251)
            log(f"首次启动，渐进式等待获取 {check_name}_VERSION")
            current_version = wait_version_progressive(
                imei, fotaType, version_window_start
            )

            if not current_version:
                log(f"首次未获取 {check_name}_VERSION，退出")
                break

        # 判断升级目标
        if current_version == target_a:
            next_id = id_b
            target_version = target_b
        elif current_version == target_b:
            next_id = id_a
            target_version = target_a
        else:
            log(f"未知 {check_name}_VERSION={current_version}，退出")
            break

        # 重置任务
        reset_fota_task(next_id)
        if stop_event.is_set():
            break

        # 从本轮触发时刻开始查询，避免把之前循环的F108带入本轮
        fota_window_start = time.time()
        send_cmd(imei, CMD_F102_0251)
        log("下发重启，渐进式等待触发升级F108上报")
        f108_found = wait_f108_progressive(imei, fota_window_start)

        if not f108_found:
            log("未检测到 F108，退出")
            break

        # 动态读取配置的升级等待时间
        log(f"开始等待升级过程，共计{upgrade_wait_sec}秒，目标版本{target_version}")
        start = time.time()
        while time.time() - start < upgrade_wait_sec and not stop_event.is_set():
            elapsed = int(time.time() - start)
            log(f"FOTA进行中，目标版本 {target_version}，已 {elapsed} 秒")
            interruptible_sleep(60)

        if stop_event.is_set():
            break

        # 校验升级结果：时间窗口同步使用配置值
        result = check_upgrade_success_with_retry(
            imei,
            target_version,
            fotaType,
            upgrade_wait_sec,
            fota_window_start
        )
        if result is True:
            log(f"升级 {target_version} 成功（第 {count} 次）")
            current_version = target_version
        elif result == 2 and fotaType == 2:
            log("========== BLE专属后置版本校验流程启动 ==========")
            verify_window_start = time.time()
            send_cmd(imei, CMD_F102_0251)
            log("BLE升级回执收到，下发重启，渐进式等待新版本上报校验")
            new_version = wait_version_progressive(
                imei, fotaType, verify_window_start
            )
            if stop_event.is_set():
                break

            log(f"设备重启后校验版本：获取版本={new_version}，目标版本={target_version}")
            if new_version == target_version:
                log(f"BLE升级校验完成：版本匹配 {target_version}，本轮升级成功（第 {count} 次）")
                current_version = target_version
            else:
                log(f"BLE升级失败：重启后版本不匹配，当前:{new_version} 目标:{target_version}")
                break
        else:
            log("升级失败，终止")
            break

        count += 1

    log("===== 升级流程已停止 =====")
    is_running = False


# ===================== GUI 界面逻辑 =====================
def start_task():
    """开始升级"""
    global is_running, stop_event
    if is_running:
        log("任务正在运行中，请勿重复点击")
        return

    # 获取界面参数
    imei = entry_imei.get().strip()
    ta = entry_a.get().strip()
    tb = entry_b.get().strip()
    fota_text = combo_fota.get()
    down_text = combo_download.get()

    # ========== 【新增3】适配自动时长 + 手动优先逻辑 ==========
    fota_key = combo_fota.get()
    default_wait = FOTA_WAIT_CFG.get(fota_key, 420)
    try:
        user_input = entry_wait.get().strip()
        upgrade_wait_sec = int(user_input)
        if upgrade_wait_sec <= 0:
            upgrade_wait_sec = default_wait
    except ValueError:
        upgrade_wait_sec = default_wait

    log(f"当前FOTA类型：{fota_key}，最终升级等待时长：{upgrade_wait_sec} 秒")

    # 非空校验
    if not all([imei, ta, tb]):
        log("IMEI / TARGET_A / TARGET_B 不能为空！")
        return

    fota_type = FOTA_TYPE_MAP.get(fota_text, 0)
    download_type = DOWNLOAD_TYPE_MAP.get(down_text, 2)

    # 重置停止信号
    stop_event.clear()
    is_running = True

    # 子线程运行升级逻辑
    t = threading.Thread(
        target=run_fota_loop,
        args=(imei, ta, tb, fota_type, download_type, upgrade_wait_sec),
        daemon=True
    )
    t.start()


def stop_task():
    """停止升级"""
    global stop_event
    stop_event.set()
    log("已发送停止指令，等待流程退出...")


def clear_log():
    """清空日志"""
    log_text.configure(state="normal")
    log_text.delete(1.0, tk.END)
    log_text.configure(state="disabled")


def save_log():
    """保存日志到本地文件"""
    log_content = log_text.get(1.0, tk.END)
    if not log_content.strip():
        log("日志为空，无需保存")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        title="保存日志"
    )
    if file_path:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_content)
            log(f"日志已保存到：{file_path}")
        except Exception as e:
            log(f"保存日志失败：{e}")


# ===================== 主窗口创建 =====================
def set_native_windows_icons(window, ico_file):
    """将多尺寸 ICO 设置到真正的 Windows 顶层窗口。"""
    if sys.platform != "win32":
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.LoadImageW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int

    image_icon = 1
    load_from_file = 0x00000010
    ga_root = 2
    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    small_width = max(16, user32.GetSystemMetrics(49))
    small_height = max(16, user32.GetSystemMetrics(50))
    big_width = max(32, user32.GetSystemMetrics(11))
    big_height = max(32, user32.GetSystemMetrics(12))

    # Tk 的 winfo_id() 可能指向内部窗口，必须先取得真正的顶层窗口。
    hwnd = user32.GetAncestor(window.winfo_id(), ga_root)
    if not hwnd:
        return

    small_icon = user32.LoadImageW(
        None, ico_file, image_icon, small_width, small_height, load_from_file
    )
    big_icon = user32.LoadImageW(
        None, ico_file, image_icon, big_width, big_height, load_from_file
    )
    if not small_icon or not big_icon:
        return

    user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
    user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon)

    window._fota_icon_handles = (small_icon, big_icon)


def set_windows_app_user_model_id():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Mangetic.FOTA.LoopUpgrade"
        )
    except (AttributeError, OSError):
        pass


set_windows_app_user_model_id()
root = tk.Tk()
root.title("FOTA 循环升级工具 - Mangetic-2026-09-24")
root.geometry("960x820")
root.minsize(900, 720)
setup_ui_style(root)

icon_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
icon_path = os.path.join(icon_dir, "FOTA_tool_20260924_v3.ico")
try:
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)
        root.iconbitmap(default=icon_path)
        root.after(500, lambda: set_native_windows_icons(root, icon_path))
except (tk.TclError, OSError):
    pass

root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)

main_frame = ttk.Frame(root, padding=16)
main_frame.grid(row=0, column=0, sticky="nsew")
main_frame.grid_columnconfigure(0, weight=1)
main_frame.grid_rowconfigure(2, weight=1)

form_frame = ttk.LabelFrame(main_frame, text="基本参数", padding=12)
form_frame.grid(row=0, column=0, sticky="ew")
form_frame.grid_columnconfigure(1, weight=1)

def add_field(parent, row, label_text, widget):
    ttk.Label(parent, text=label_text, width=16).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
    widget.grid(row=row, column=1, sticky="ew", pady=5)

entry_imei = ttk.Entry(form_frame)
add_field(form_frame, 0, "IMEI", entry_imei)
set_placeholder(entry_imei, "请输入设备IMEI")

entry_a = ttk.Entry(form_frame)
add_field(form_frame, 1, "TARGET_A", entry_a)
set_placeholder(entry_a, "请输入目标版本A")

entry_b = ttk.Entry(form_frame)
add_field(form_frame, 2, "TARGET_B", entry_b)
set_placeholder(entry_b, "请输入目标版本B")

combo_fota = ttk.Combobox(form_frame, state="readonly")
combo_fota["values"] = list(FOTA_TYPE_MAP.keys())
add_field(form_frame, 3, "FOTA Type", combo_fota)
combo_fota.set("00-MCU")
combo_fota.bind("<<ComboboxSelected>>", on_fota_combo_change)

combo_download = ttk.Combobox(form_frame, state="readonly")
combo_download["values"] = list(DOWNLOAD_TYPE_MAP.keys())
add_field(form_frame, 4, "Download Type", combo_download)
combo_download.set("02-HTTP")

entry_wait = ttk.Entry(form_frame)
add_field(form_frame, 5, "升级等待(秒)", entry_wait)
entry_wait.insert(0, "420")  # 默认420秒

action_frame = ttk.LabelFrame(main_frame, text="操作", padding=8)
action_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))

btn_start = tk.Button(action_frame, text="开始循环升级", command=start_task, font=("Microsoft YaHei UI", 10), padx=12, pady=4, relief="raised", bd=1, fg="#111111", bg="#f2f2f2", activebackground="#e0e0e0")
btn_stop = tk.Button(action_frame, text="停止升级", command=stop_task, font=("Microsoft YaHei UI", 10), padx=12, pady=4, relief="raised", bd=1, fg="#111111", bg="#f2f2f2", activebackground="#e0e0e0")
btn_clear = tk.Button(action_frame, text="清空日志", command=clear_log, font=("Microsoft YaHei UI", 10), padx=12, pady=4, relief="raised", bd=1, fg="#111111", bg="#f2f2f2", activebackground="#e0e0e0")
btn_save = tk.Button(action_frame, text="保存日志", command=save_log, font=("Microsoft YaHei UI", 10), padx=12, pady=4, relief="raised", bd=1, fg="#111111", bg="#f2f2f2", activebackground="#e0e0e0")
btn_start.pack(side=tk.LEFT, padx=(0, 6))
btn_stop.pack(side=tk.LEFT, padx=(0, 6))
btn_clear.pack(side=tk.LEFT, padx=(0, 6))
btn_save.pack(side=tk.LEFT)

log_frame = ttk.LabelFrame(main_frame, text="日志输出", padding=12)
log_frame.grid(row=2, column=0, sticky="nsew")
main_frame.grid_rowconfigure(2, weight=1)
log_frame.grid_rowconfigure(0, weight=1)
log_frame.grid_columnconfigure(0, weight=1)

log_text = scrolledtext.ScrolledText(
    log_frame,
    height=28,
    wrap="word",
    font=("Consolas", 11),
    relief="solid",
    borderwidth=1
)
log_text.grid(row=0, column=0, sticky="nsew")
log_text.configure(state="disabled")

# 重定向日志输出
original_log = log
def gui_log(msg):
    original_log(msg, log_text)
globals()["log"] = gui_log

# 窗口主循环
root.mainloop()
