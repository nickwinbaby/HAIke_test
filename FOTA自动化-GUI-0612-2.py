import requests
import time
import datetime
import threading
import tkinter as tk
import os,sys
from tkinter import ttk, scrolledtext, filedialog

# ===================== 全局变量 =====================
stop_event = threading.Event()
is_running = False

# 下拉框映射关系
FOTA_TYPE_MAP = {
    "00-MCU": 0,
    "01-MDM": 1,
    "02-BLE": 2,
    "03-GNSS": 3,
    "04-BOOT": 4,
    "05-AP": 5,
    "06-CFG": 6,
    "FF-HARDWARE": 255
}
DOWNLOAD_TYPE_MAP = {
    "01-TCP": 1,
    "02-HTTP": 2
}

# ========== 【新增1】FOTA类型对应默认升级等待时长 ==========
FOTA_WAIT_CFG = {
    "00-MCU": 420,
    "01-MDM": 420,
    "02-BLE": 420,
    "03-GNSS": 420,
    "04-BOOT": 420,
    "05-AP": 300,
    "06-CFG": 420,
    "FF-HARDWARE": 420
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

# ===================== 原有工具函数（解析逻辑不变） =====================
def log(msg, log_widget=None):
    """打印带时间戳的日志"""
    content = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    if log_widget:
        log_widget.insert(tk.END, content)
        log_widget.see(tk.END)
    else:
        print(content.strip())


def get_unix_ms(offset_sec=0):
    """获取当前 Unix 毫秒时间戳"""
    return str(int(time.time() * 1000 + offset_sec * 1000))


def hex_to_ascii(hex_list):
    """HEX byte 列表转换成 ASCII 字符串"""
    return ''.join(chr(int(h, 16)) for h in hex_list)


def get_check_version_name(fotaType):
    """根据 fotaType 决定当前需要校验哪个版本字段"""
    if fotaType == 5:
        return "AP"
    elif fotaType == 0:
        return "MCU"
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

        # MCU模式解析完成直接返回，不再解析后续字段
        if fotaType == 0:
            return {
                "hardware_version": hardware_version,
                "mcu_version": mcu_version,
                "modem_version": "",
                "utc": 0,
                "cfg_version": "",
                "fota_status": "",
                "ap_version": "",
                "mcu_is_t99": mcu_version.endswith("T99"),
                "ap_is_t99": False
            }

        # AP模式继续解析后续字段
        modem_version, offset = parse_ascii_length_field(
            hex_list, offset, "Modem version number"
        )

        if offset + 4 > len(hex_list):
            raise ValueError("Report UTC time 长度不足")
        utc_hex = ''.join(hex_list[offset:offset + 4])
        utc_ts = int(utc_hex, 16)
        offset += 4

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


def parse_target_version(rawdata_list, fotaType):
    """根据 fotaType 解析当前需要校验的版本"""
    candidates = []
    check_name = get_check_version_name(fotaType)

    if check_name == "UNKNOWN":
        log(f"当前 fotaType={fotaType} 暂不支持版本解析")
        return None

    for idx, hex_list in enumerate(rawdata_list):
        result = parse_version_report_frame(hex_list, fotaType)
        if not result:
            continue
        result["idx"] = idx
        candidates.append(result)

        log(
            f"第 {idx + 1} 条版本帧解析成功 | "
            f"UTC={result['utc']} | "
            f"MCU={result['mcu_version']} | "
            f"MCU后三位是否T99={result['mcu_is_t99']} | "
            f"AP={result['ap_version']} | "
            f"AP后三位是否T99={result['ap_is_t99']}"
        )

    if not candidates:
        log("未检测到有效版本上报帧")
        return None

    latest = max(candidates, key=lambda x: x["utc"])
    if fotaType == 5:
        version = latest["ap_version"]
        is_t99 = latest["ap_is_t99"]
    else:
        version = latest["mcu_version"]
        is_t99 = latest["mcu_is_t99"]

    log(
        f"选取第 {latest['idx'] + 1} 条最新版本帧 | "
        f"校验字段={check_name} | "
        f"UTC={latest['utc']} | "
        f"VERSION={version} | "
        f"后三位是否T99={is_t99}"
    )
    return version


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
    except Exception as e:
        log(f"下发指令接口异常: {e}")


def fetch_raw_data(imei, start_offset_sec, stop_offset_sec=0):
    """从服务器获取设备 rawData"""
    url = "http://10.85.40.3:8082/testAPI/rawData"
    data = {
        "imei": imei,
        "start": get_unix_ms(start_offset_sec),
        "stop": get_unix_ms(stop_offset_sec),
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


def get_current_version_with_retry(imei, fotaType, retries=2, interval_sec=15):
    """带重试机制获取当前版本"""
    check_name = get_check_version_name(fotaType)
    for attempt in range(1, retries + 1):
        log(f"尝试第 {attempt} 次获取 {check_name}_VERSION")
        rawdata = fetch_raw_data(imei, -120)
        version = parse_target_version(rawdata, fotaType)
        if version:
            return version
        if attempt < retries:
            log(f"{interval_sec} 秒后重试")
            interruptible_sleep(interval_sec)
    return None


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


def check_f108_with_retry(imei, first_window_sec=120, retry_delay_sec=120):
    """带重试机制检测 F108"""
    log("开始第一次 F108 检测")
    rawdata = fetch_raw_data(imei, -first_window_sec)
    if check_f108(rawdata):
        return True

    log(f"第一次未检测到 F108，等待 {retry_delay_sec} 秒后重试")
    interruptible_sleep(retry_delay_sec)
    if stop_event.is_set():
        return False

    log("开始第二次 F108 检测")
    rawdata = fetch_raw_data(imei, -first_window_sec)
    if check_f108(rawdata):
        return True
    log("第二次仍未检测到 F108")
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


def check_upgrade_success_with_retry(imei, target_version, fotaType, wait_sec):
    """带重试机制的升级成功校验，时间窗口使用配置值"""
    log("开始第一次升级完成校验")
    rawdata = fetch_raw_data(imei, -wait_sec)
    if check_upgrade_success(rawdata, target_version, fotaType, wait_sec):
        return True
    if stop_event.is_set():
        return False

    log("第一次失败，3 分钟后重试")
    interruptible_sleep(180)
    if stop_event.is_set():
        return False

    log("开始第二次升级完成校验")
    rawdata = fetch_raw_data(imei, -wait_sec)
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
        log(f"当前 fotaType={fotaType} 暂不支持，只支持 fotaType=0 或 fotaType=5")
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
            send_cmd(imei, CMD_F102_0251)
            log(f"首次启动，等待 120 秒获取 {check_name}_VERSION")
            interruptible_sleep(120)
            if stop_event.is_set():
                break

            current_version = get_current_version_with_retry(imei, fotaType)
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

        # 下发重启指令
        send_cmd(imei, CMD_F102_0251)
        log("等待 120 秒触发升级")
        interruptible_sleep(120)
        if stop_event.is_set():
            break

        # 检测 F108
        if not check_f108_with_retry(imei):
            log("两次检测均未发现 F108，退出")
            break

        # 动态读取配置的升级等待时间
        log(f"开始等待升级过程，共计{upgrade_wait_sec}秒")
        start = time.time()
        while time.time() - start < upgrade_wait_sec and not stop_event.is_set():
            elapsed = int(time.time() - start)
            log(f"FOTA进行中，目标版本 {target_version}，已 {elapsed} 秒")
            interruptible_sleep(60)

        if stop_event.is_set():
            break

        # 校验升级结果：时间窗口同步使用配置值
        if check_upgrade_success_with_retry(imei, target_version, fotaType, upgrade_wait_sec):
            log(f"升级 {target_version} 成功（第 {count} 次）")
            current_version = target_version
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
    log_text.delete(1.0, tk.END)


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
root = tk.Tk()
root.title("FOTA 循环升级工具 - Mangetic - 2026-6-12 ★★★★★ 广告位招租 ★★★★★")
root.geometry("700x600")

# 配置自适应权重
root.grid_rowconfigure(8, weight=1)
root.grid_columnconfigure(1, weight=1)

# 1. IMEI
tk.Label(root, text="IMEI", anchor="w").grid(row=0, column=0, sticky="w", padx=10, pady=5)
entry_imei = ttk.Entry(root)
entry_imei.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
set_placeholder(entry_imei, "请输入设备IMEI")

# 2. TARGET_A
tk.Label(root, text="TARGET_A", anchor="w").grid(row=1, column=0, sticky="w", padx=10, pady=5)
entry_a = ttk.Entry(root)
entry_a.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
set_placeholder(entry_a, "请输入目标版本A")

# 3. TARGET_B
tk.Label(root, text="TARGET_B", anchor="w").grid(row=2, column=0, sticky="w", padx=10, pady=5)
entry_b = ttk.Entry(root)
entry_b.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
set_placeholder(entry_b, "请输入目标版本B")

# 4. FOTA Type
tk.Label(root, text="FOTA Type", anchor="w").grid(row=3, column=0, sticky="w", padx=10, pady=5)
combo_fota = ttk.Combobox(root, state="readonly")
combo_fota["values"] = list(FOTA_TYPE_MAP.keys())
combo_fota.grid(row=3, column=1, padx=10, pady=5, sticky="ew")
combo_fota.set("00-MCU")
# ========== 【新增4】绑定下拉切换事件 ==========
combo_fota.bind("<<ComboboxSelected>>", on_fota_combo_change)

# 5. Download Type
tk.Label(root, text="Download Type", anchor="w").grid(row=4, column=0, sticky="w", padx=10, pady=5)
combo_download = ttk.Combobox(root, state="readonly")
combo_download["values"] = list(DOWNLOAD_TYPE_MAP.keys())
combo_download.grid(row=4, column=1, padx=10, pady=5, sticky="ew")
combo_download.set("02-HTTP")

# 6. 新增：升级等待时间
tk.Label(root, text="升级等待时间(秒)", anchor="w").grid(row=5, column=0, sticky="w", padx=10, pady=5)
entry_wait = ttk.Entry(root)
entry_wait.grid(row=5, column=1, padx=10, pady=5, sticky="ew")
entry_wait.insert(0, "420")  # 默认420秒

# 按钮区
btn_frame = tk.Frame(root)
btn_frame.grid(row=6, column=0, columnspan=2, pady=10)

btn_start = ttk.Button(btn_frame, text="开始循环升级", command=start_task)
btn_start.pack(side=tk.LEFT, padx=10)

btn_stop = ttk.Button(btn_frame, text="停止升级", command=stop_task)
btn_stop.pack(side=tk.LEFT, padx=10)

btn_clear = ttk.Button(btn_frame, text="清空日志", command=clear_log)
btn_clear.pack(side=tk.LEFT, padx=10)

btn_save = ttk.Button(btn_frame, text="保存日志", command=save_log)
btn_save.pack(side=tk.LEFT, padx=10)

# 日志区域
tk.Label(root, text="日志输出", anchor="w").grid(row=7, column=0, columnspan=2, sticky="w", padx=10)
log_text = scrolledtext.ScrolledText(root)
log_text.grid(row=8, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")

# 重定向日志输出
original_log = log
def gui_log(msg):
    original_log(msg, log_text)
globals()["log"] = gui_log

# 窗口主循环
root.mainloop()
