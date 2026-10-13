"""Windows / Linux 无线网卡热点管理器。

Windows 优先兼容 Hosted Network + ICS，并在旧接口不可用时回退到现代移动热点 API；
Linux 使用 NetworkManager/nmcli。
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from ctypes import wintypes
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape as xml_escape

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError as exc:
    if exc.name != "tkinter":
        raise
    raise SystemExit(
        "缺少 Python 图形界面组件 tkinter。\n\n"
        "Ubuntu / Debian / Linux Mint：sudo apt install python3-tk\n"
        "Fedora / RHEL：sudo dnf install python3-tkinter\n"
        "Arch Linux：sudo pacman -S tk\n\n"
        "安装完成后重新运行本程序。"
    ) from None


APP_TITLE = "WIFI热点-连接管理器-Mangetic-2026-9-20"
APP_VERSION = "2026.09.19-CLIENT-NETWORK-SAFE-R19"
DEFAULT_SSID_PREFIX = "AAA"
DEFAULT_CLIENT_SSID = "Richlink-Guest-2.4G"
DEFAULT_CLIENT_PASSWORD = "richlink_0401"
APP_DIR = Path(__file__).resolve().parent
CURRENT_PLATFORM = "Windows" if os.name == "nt" else "Linux" if sys.platform.startswith("linux") else "Unsupported"
if os.name == "nt":
    STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "GMYHotspotManager"
else:
    STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "gmy_hotspot_manager"
STATE_FILE = STATE_DIR / "runtime_state.json"
DEFAULT_STATE_FILE = STATE_FILE
PENDING_STATE_FILE = STATE_DIR / "pending_recovery.json"
DEFAULT_PENDING_STATE_FILE = PENDING_STATE_FILE
if os.name == "nt":
    legacy_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else APP_DIR
    LEGACY_STATE_FILE = legacy_dir / "runtime_state.json"
else:
    LEGACY_STATE_FILE = Path.home() / ".gmy_hotspot_manager" / "runtime_state.json"
CREATE_NO_WINDOW = 0x08000000
_INSTANCE_HANDLE: Any = None
_ACTIVE_PROCESSES: dict[int, subprocess.Popen[Any]] = {}
_ACTIVE_PROCESSES_LOCK = threading.RLock()
_TERMINATE_REQUESTED = threading.Event()


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    """只终止本程序登记的外部命令及其子进程。"""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            # PowerShell 经常再启动 netsh/CIM 子进程；仅调用 Popen.kill()
            # 只会结束父进程，留下后台命令继续改网卡状态。taskkill /T
            # 以登记到的 PID 为根，限制在本次命令进程树内。
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=5,
                check=False,
            )
        elif hasattr(os, "killpg"):
            os.killpg(process.pid, 9)
        else:
            process.kill()
    except (OSError, ProcessLookupError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass


# Win32 WLAN API 结构定义。只在 Windows 后端调用 wlanapi.dll；
# Linux 下这些 ctypes 类型仅作为静态定义，不会加载 Windows DLL。
class _WlanGuid(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class _WlanInterfaceInfo(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", _WlanGuid),
        ("strInterfaceDescription", wintypes.WCHAR * 256),
        ("isState", wintypes.DWORD),
    ]


class _WlanInterfaceInfoListHead(ctypes.Structure):
    _fields_ = [
        ("dwNumberOfItems", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("InterfaceInfo", _WlanInterfaceInfo * 1),
    ]


class _Dot11Ssid(ctypes.Structure):
    _fields_ = [
        ("uSSIDLength", wintypes.ULONG),
        ("ucSSID", wintypes.BYTE * 32),
    ]


class _WlanAssociationAttributes(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", _Dot11Ssid),
        ("dot11BssType", wintypes.ULONG),
        ("dot11Bssid", wintypes.BYTE * 6),
        ("dot11PhyType", wintypes.ULONG),
        ("uDot11PhyIndex", wintypes.ULONG),
        ("wlanSignalQuality", wintypes.ULONG),
        ("ulRxRate", wintypes.ULONG),
        ("ulTxRate", wintypes.ULONG),
    ]


class _WlanSecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("dot11AuthAlgorithm", wintypes.ULONG),
        ("dot11CipherAlgorithm", wintypes.ULONG),
        ("bSecurityEnabled", wintypes.BOOL),
        ("bOneXEnabled", wintypes.BOOL),
    ]


class _WlanConnectionAttributes(ctypes.Structure):
    _fields_ = [
        ("isState", wintypes.ULONG),
        ("wlanConnectionMode", wintypes.ULONG),
        ("strProfileName", wintypes.WCHAR * 256),
        ("wlanAssociationAttributes", _WlanAssociationAttributes),
        ("wlanSecurityAttributes", _WlanSecurityAttributes),
    ]


WLAN_INTF_OPCODE_CURRENT_CONNECTION = 7
WLAN_INTERFACE_STATE_CONNECTED = 1
WLAN_INTERFACE_STATE_ADHOC_NETWORK_FORMED = 2
ERROR_WLAN_NOT_FOUND = 1168
ERROR_ACCESS_DENIED = 5

# 本工具不主动指定热点信道；由操作系统、驱动和网卡自行协商。
# 下方信道表仅用于把系统回报的信道号转换成频段，以及保留后端兼容入口。
REGULATORY_COUNTRY = "CN"
DEFAULT_CHANNELS_BY_BAND: dict[str, tuple[int, ...]] = {
    "2.4G": tuple(range(1, 14)),
    "5G": (
        36, 40, 44, 48,
        52, 56, 60, 64, 68,
        96,
        100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144,
        149, 153, 157, 161, 165,
        169, 173, 177,
    ),
}
RANDOM_CHANNELS_BY_BAND: dict[str, tuple[int, ...]] = {
    "2.4G": DEFAULT_CHANNELS_BY_BAND["2.4G"],
    "5G": DEFAULT_CHANNELS_BY_BAND["5G"],
}
PREFERRED_5G_CHANNELS: tuple[int, ...] = (36, 40, 44, 48)
DFS_CHANNELS_BY_COUNTRY: dict[str, tuple[int, ...]] = {
    "CN": (52, 56, 60, 64),
}
DFS_ACTIVATION_TIMEOUT = 180
DFS_VERIFY_TIMEOUT = 90.0
NORMAL_ACTIVATION_TIMEOUT = 60
NORMAL_VERIFY_TIMEOUT = 12.0


def make_ssid(prefix: str, index: int, band: str) -> str:
    """根据统一前缀生成每块网卡的 SSID。"""
    return f"{prefix.strip()}{index}-{band}"


def band_for_channel(channel: int) -> str:
    """根据标准信道号判断频段；无法判断时返回空字符串。"""
    if channel in DEFAULT_CHANNELS_BY_BAND["2.4G"]:
        return "2.4G"
    if channel in DEFAULT_CHANNELS_BY_BAND["5G"]:
        return "5G"
    return ""


def ssid_prefix_from_preview(ssid: str, index: int, band: str) -> str:
    """从预览 SSID 移除精确的“当前网卡序号-频段”后缀。"""
    suffix = f"{index}-{band}"
    return ssid[:-len(suffix)] if ssid.endswith(suffix) else ssid


class HotspotError(RuntimeError):
    pass


class PendingRecoveryError(HotspotError):
    """热点已经停止，但仍有系统设置需要稍后恢复。"""


def _serialized_backend_operation(func: Callable[..., Any]) -> Callable[..., Any]:
    """串行化会改变 NetworkManager/Windows WLAN 状态的后端操作。

    GUI 通常通过 ``busy`` 防止重复点击，但后台状态查询、关闭窗口和
    快速连续操作仍可能在命令边界重叠。NetworkManager 对同一块无线网卡
    的 down/up/managed 切换不是可重入的；串行化只保护本程序发起的写操作，
    不会阻塞只读状态查询。
    """
    @wraps(func)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        lock = getattr(self, "_operation_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._operation_lock = lock
        with lock:
            return func(self, *args, **kwargs)
    return wrapped


@dataclass
class WifiAdapter:
    index: int
    name: str
    description: str
    status: str
    if_index: int
    guid: str
    hosted_supported: bool | None = None
    bands: tuple[str, ...] = ()
    channels_by_band: dict[str, tuple[int, ...]] = field(default_factory=dict)
    channel_info_available: bool = False

    @property
    def default_ssid(self) -> str:
        return make_ssid(DEFAULT_SSID_PREFIX, self.index, "2.4G")


def adapter_channel_options(adapter: WifiAdapter, band: str) -> tuple[int, ...]:
    """返回内置常见信道表；启动热点时不再指定具体信道。"""
    return DEFAULT_CHANNELS_BY_BAND.get(band, ())


def random_adapter_channel_options(adapter: WifiAdapter, band: str) -> tuple[int, ...]:
    """保留给兼容测试的随机候选；界面启动路径不再使用。"""
    china_channels = RANDOM_CHANNELS_BY_BAND.get(band, DEFAULT_CHANNELS_BY_BAND.get(band, ()))
    reported = tuple(
        channel for channel in adapter.channels_by_band.get(band, ())
        if channel in china_channels
    )
    # iw 没有信息时保留内置表；实际启动不指定信道，由系统/驱动最终决定。
    return reported if adapter.channel_info_available and reported else china_channels


def random_unique_channel_assignment(
    adapters: list[WifiAdapter], band: str, excluded: set[int] | None = None,
    rng: random.Random | random.SystemRandom | None = None,
) -> dict[str, int]:
    """从代码内置信道表随机生成互不重复的信道；仅保留兼容入口。"""
    randomizer = rng or random.SystemRandom()
    blocked = set(excluded or ())
    options_by_name: dict[str, list[int]] = {}
    for adapter in adapters:
        choices = [
            channel for channel in random_adapter_channel_options(adapter, band)
            if channel not in blocked
        ]
        randomizer.shuffle(choices)
        options_by_name[adapter.name] = choices

    adapter_names = list(options_by_name)
    randomizer.shuffle(adapter_names)
    adapter_names.sort(key=lambda name: len(options_by_name[name]))
    channel_owner: dict[int, str] = {}

    def claim(adapter_name: str, visited: set[int]) -> bool:
        for channel in options_by_name[adapter_name]:
            if channel in visited:
                continue
            visited.add(channel)
            previous_owner = channel_owner.get(channel)
            if previous_owner is None or claim(previous_owner, visited):
                channel_owner[channel] = adapter_name
                return True
        return False

    for adapter_name in adapter_names:
        claim(adapter_name, set())
    return {adapter_name: channel for channel, adapter_name in channel_owner.items()}


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _decode_output(data: bytes, prefer_legacy: bool = False) -> str:
    encodings = ("gb18030", "utf-8-sig", "utf-16") if prefer_legacy else ("utf-8-sig", "gb18030", "utf-16")
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode(errors="replace")


def run_process(
    args: list[str], timeout: int = 30, prefer_legacy: bool = False,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if _TERMINATE_REQUESTED.is_set():
        raise HotspotError("用户已请求终止本程序正在执行的命令。")
    if os.name == "nt":
        # 新进程组便于“强制终止”只结束本程序启动的命令，不碰 NetworkManager/
        # WLAN 服务本身；CREATE_NO_WINDOW 保持原有无黑框行为。
        kwargs["creationflags"] = CREATE_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    elif hasattr(os, "setsid"):
        kwargs["start_new_session"] = True
    process = subprocess.Popen(args, **kwargs)
    with _ACTIVE_PROCESSES_LOCK:
        _ACTIVE_PROCESSES[process.pid] = process
    try:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(process)
            output, _ = process.communicate()
            timeout_exc = subprocess.TimeoutExpired(args, timeout, output=output)
            raise timeout_exc from exc
        if _TERMINATE_REQUESTED.is_set():
            raise HotspotError("用户已请求终止本程序正在执行的命令。")
        return process.returncode, _decode_output(output or b"", prefer_legacy=prefer_legacy).strip()
    finally:
        with _ACTIVE_PROCESSES_LOCK:
            _ACTIVE_PROCESSES.pop(process.pid, None)


def request_terminate_active_processes() -> int:
    """终止本程序当前登记的外部命令进程，不操作系统级网络服务。"""
    _TERMINATE_REQUESTED.set()
    with _ACTIVE_PROCESSES_LOCK:
        processes = list(_ACTIVE_PROCESSES.values())
    terminated = 0
    for process in processes:
        try:
            if process.poll() is None:
                _terminate_process_tree(process)
                terminated += 1
        except (OSError, ProcessLookupError, subprocess.SubprocessError):
            pass
    return terminated


def clear_terminate_request() -> None:
    """开始新的用户操作前清除上一次的终止请求。"""
    _TERMINATE_REQUESTED.clear()


def load_runtime_state() -> dict[str, Any]:
    candidates = [STATE_FILE]
    if STATE_FILE == DEFAULT_STATE_FILE and LEGACY_STATE_FILE != STATE_FILE:
        candidates.append(LEGACY_STATE_FILE)
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def save_runtime_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(STATE_FILE)
    if STATE_FILE == DEFAULT_STATE_FILE and LEGACY_STATE_FILE != STATE_FILE:
        try:
            LEGACY_STATE_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def delete_runtime_state() -> None:
    candidates = {STATE_FILE}
    if STATE_FILE == DEFAULT_STATE_FILE:
        candidates.add(LEGACY_STATE_FILE)
    for candidate in candidates:
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def load_pending_recovery() -> dict[str, Any]:
    if not PENDING_STATE_FILE.exists():
        return {}
    try:
        value = json.loads(PENDING_STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_pending_recovery(state: dict[str, Any]) -> None:
    PENDING_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = PENDING_STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(PENDING_STATE_FILE)


def delete_pending_recovery() -> None:
    try:
        PENDING_STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def acquire_single_instance() -> bool:
    """防止两个 GUI 同时操作系统级热点和同一份运行状态。"""
    global _INSTANCE_HANDLE
    if os.name == "nt":
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\GMYHotspotManager")
        if not handle:
            return False
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        _INSTANCE_HANDLE = handle
        return True
    try:
        import socket

        instance_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        instance_socket.bind("\0gmy_hotspot_manager")
        instance_socket.listen(1)
        _INSTANCE_HANDLE = instance_socket
        return True
    except (ImportError, OSError):
        return False


def run_netsh(args: list[str], timeout: int = 30) -> tuple[int, str]:
    """读取 netsh 输出；现代 Windows 控制台通常返回 UTF-8，失败时自动回退 GB18030。"""
    return run_process(args, timeout=timeout, prefer_legacy=False)


def run_powershell(script: str, timeout: int = 30) -> str:
    prefix = (
        "$ErrorActionPreference='Stop';"
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        "$OutputEncoding=[System.Text.UTF8Encoding]::new();"
    )
    code, output = run_process(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", prefix + script],
        timeout,
    )
    if code != 0:
        raise HotspotError(output or f"PowerShell 执行失败，退出码 {code}")
    return output


def parse_driver_capabilities(text: str) -> tuple[bool | None, tuple[str, ...]]:
    """解析 Windows 驱动能力；频段优先取明确的 GHz 行，再用无线制式兜底。"""
    lowered = text.lower()
    hosted: bool | None = None
    chinese_yes = re.search(r"(?:支持的承载网络|承载网络支持)\s*[:：]\s*是", text)
    chinese_no = re.search(r"(?:支持的承载网络|承载网络支持)\s*[:：]\s*否", text)
    if re.search(r"hosted network supported\s*:\s*yes", lowered) or chinese_yes:
        hosted = True
    elif re.search(r"hosted network supported\s*:\s*no", lowered) or chinese_no:
        hosted = False

    bands: list[str] = []
    if re.search(r"2[.,]4\s*ghz", lowered) or "2.4 ghz" in lowered:
        bands.append("2.4G")
    if re.search(r"(?:^|\s)5\s*ghz", lowered):
        bands.append("5G")
    # 某些驱动不会输出标准的“2.4 GHz/5 GHz”行，只输出 Radio types supported。
    # 仅在上面的明确频段为空时兜底，避免 802.11n/ax 被错误解释成某一个频段。
    if not bands:
        radio_line = re.search(r"radio\s+types?\s+supported\s*:\s*([^\r\n]+)", lowered)
        if radio_line:
            radio = radio_line.group(1)
            if re.search(r"802\.11(?:a|ac)", radio):
                bands.append("5G")
            if re.search(r"802\.11(?:b|g)", radio):
                bands.append("2.4G")
    return hosted, tuple(bands)


def localized_adapter_status(value: str) -> str:
    """将网卡驱动状态转换为用户容易理解的中文。"""
    normalized = str(value or "").strip().lower()
    code_match = re.match(r"(\d+)", normalized)
    if code_match:
        code = int(code_match.group(1))
        numeric_mapping = {
            10: "已禁用（未由网络服务管理）",
            20: "已启用（暂不可用）",
            30: "已启用（未连接）",
            40: "正在连接",
            50: "正在配置",
            60: "正在等待认证",
            70: "正在配置网络地址",
            80: "正在检查网络",
            90: "正在启动连接",
            100: "已启用",
            110: "正在断开",
            120: "连接失败",
        }
        if code in numeric_mapping:
            return numeric_mapping[code]
    if normalized in {"up", "connected"}:
        return "已启用"
    if normalized in {"disconnected", "disconnected/unknown"}:
        return "已启用（未连接）"
    if normalized.startswith("connecting"):
        return "正在连接"
    if normalized.startswith("disconnecting"):
        return "正在断开"
    if normalized == "unavailable":
        return "已启用（暂不可用）"
    if normalized == "unmanaged":
        return "已禁用（未由网络服务管理）"
    if normalized == "disabled":
        return "已禁用"
    if normalized == "not present":
        return "设备未插入"
    if normalized in {"unknown", ""}:
        return "未知"
    return str(value)


def adapter_status_is_disabled(value: str) -> bool:
    """判断网卡是否被操作系统禁用或不再由 NetworkManager 管理。"""
    normalized = str(value or "").strip().lower()
    code_match = re.match(r"(\d+)", normalized)
    if code_match and int(code_match.group(1)) == 10:
        return True
    return normalized in {"disabled", "unmanaged"}


def localized_nm_device_state(value: str) -> str:
    """把 NetworkManager 设备状态码转换成便于排查的中文。"""
    text = str(value or "").strip()
    match = re.match(r"(\d+)", text)
    state_code = int(match.group(1)) if match else None
    mapping = {
        0: "未知",
        10: "未由 NetworkManager 管理",
        20: "设备暂不可用",
        30: "已断开",
        40: "正在准备连接",
        50: "正在配置",
        60: "等待认证信息",
        70: "正在配置 IP 地址",
        80: "正在检查 IP 连接",
        90: "正在启动附属连接",
        100: "已连接并激活",
        110: "正在断开",
        120: "连接失败",
    }
    if state_code in mapping:
        return f"{mapping[state_code]}（代码 {state_code}）"
    return text or "未知"


def localized_nm_device_reason(value: str) -> str:
    """翻译常见 NetworkManager 掉线原因；保留代码以便继续定位驱动问题。"""
    text = str(value or "").strip()
    match = re.match(r"(\d+)", text)
    reason_code = int(match.group(1)) if match else None
    mapping = {
        0: "没有提供明确原因",
        3: "设备被改为不受 NetworkManager 管理",
        4: "热点配置失败",
        5: "无法获得 IP 配置",
        7: "缺少密码或认证信息",
        8: "无线驱动/认证组件主动断开",
        9: "无线认证配置失败",
        10: "无线认证组件运行失败",
        11: "无线认证超时",
        15: "DHCP 启动失败",
        16: "DHCP 发生错误",
        17: "DHCP 获取地址失败",
        18: "共享网络服务启动失败",
        19: "共享网络服务运行失败",
        35: "缺少网卡固件",
        36: "网卡被拔出或被系统移除",
        37: "系统进入睡眠/节能状态",
        38: "热点连接配置被删除",
        39: "用户或程序请求断开",
        40: "网卡检测到链路状态变化",
        50: "依赖的网络连接失败",
        53: "找不到目标无线网络",
        54: "附属连接启动失败",
        60: "另一个连接取代了当前连接",
        64: "检测到 IP 地址冲突",
        65: "驱动或系统不支持所需的 IP 配置方式",
        67: "找不到对端设备",
    }
    if reason_code in mapping:
        return f"{mapping[reason_code]}（代码 {reason_code}）"
    return text or "未知原因"


def localized_tethering_status(value: str) -> str:
    """将 Windows WinRT 移动热点枚举值转换为中文。"""
    mapping = {
        "success": "成功",
        "alreadyoff": "本来就是关闭的",
        "on": "已启动",
        "off": "未启动",
        "intransition": "正在切换",
        "unknown": "未知",
        "wifideviceoff": "无线设备已关闭",
        "operationinprogress": "已有操作正在进行",
        "networklimitedconnectivity": "网络连接受限",
        "entitlementcheckfailure": "系统热点权限检查失败",
        "entitlementchecktimeout": "系统热点权限检查超时",
        "unavailable": "不可用",
        "enabled": "可用",
        "disabled": "不可用",
    }
    text = str(value or "未知").strip()
    translated = mapping.get(text.replace(" ", "").lower())
    if translated:
        return translated
    # 兼容旧运行状态里保存的 “On (Windows 现代移动热点)” 一类混合文本，
    # 避免界面再次出现 On/Off/InTransition 等英文枚举值。
    match = re.fullmatch(r"(On|Off|InTransition|Unavailable|Enabled|Disabled)\s*(\(.*\))?", text, re.I)
    if match:
        base = mapping.get(match.group(1).replace(" ", "").lower(), match.group(1))
        return f"{base}{' ' + match.group(2) if match.group(2) else ''}"
    return text


def localized_band(value: str) -> str:
    mapping = {
        "twopointfourgigahertz": "2.4G",
        "fivegigahertz": "5G",
        "sixgigahertz": "6G",
        "auto": "自动选择",
        "2.4g": "2.4G",
        "5g": "5G",
        "6g": "6G",
    }
    normalized = str(value or "").replace(" ", "").lower()
    return mapping.get(normalized, str(value or "未读取"))


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
        working_dir = str(Path(sys.executable).resolve().parent)
    else:
        executable = sys.executable
        params = subprocess.list2cmdline([str(Path(__file__).resolve()), *sys.argv[1:]])
        working_dir = str(APP_DIR)
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, params, working_dir, 1
    )
    return result > 32


class WindowsHotspotBackend:
    @staticmethod
    def _wlan_query_requires_location(output: str) -> bool:
        text = str(output or "").lower()
        return (
            "wlanqueryinterface" in text
            or "位置服务" in text
            or "location" in text and "privacy" in text
            or "access is denied" in text
            or "拒绝访问" in text
        )

    @staticmethod
    def _guid_from_text(value: str) -> _WlanGuid | None:
        """把 PowerShell 返回的网卡 GUID 转成 WLAN API 所需的 GUID 结构。"""
        text = str(value or "").strip().strip("{}")
        if not text:
            return None
        try:
            return _WlanGuid.from_buffer_copy(uuid.UUID(text).bytes_le)
        except (ValueError, TypeError):
            return None

    def _get_windows_wlan_api_status(
        self, adapters: list[WifiAdapter],
    ) -> tuple[dict[str, dict[str, Any]], str]:
        """用 wlanapi.dll 读取每块网卡当前真实关联 SSID。

        这里故意不使用 Get-NetConnectionProfile.Name：那个字段是 Windows
        网络配置文件名，可能被用户修改，也可能保留旧名字，不能代表当前
        无线链路的 SSID。
        """
        if os.name != "nt":
            return {}, "当前系统不是 Windows"
        try:
            wlanapi = ctypes.WinDLL("wlanapi.dll")
        except (AttributeError, OSError) as exc:
            return {}, f"无法加载 wlanapi.dll：{exc}"

        try:
            wlanapi.WlanOpenHandle.argtypes = [
                wintypes.DWORD, wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.HANDLE),
            ]
            wlanapi.WlanOpenHandle.restype = wintypes.DWORD
            wlanapi.WlanEnumInterfaces.argtypes = [
                wintypes.HANDLE, wintypes.LPVOID, ctypes.POINTER(ctypes.c_void_p),
            ]
            wlanapi.WlanEnumInterfaces.restype = wintypes.DWORD
            wlanapi.WlanQueryInterface.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(_WlanGuid), wintypes.DWORD,
                wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(wintypes.DWORD),
            ]
            wlanapi.WlanQueryInterface.restype = wintypes.DWORD
            wlanapi.WlanFreeMemory.argtypes = [ctypes.c_void_p]
            wlanapi.WlanFreeMemory.restype = None
        except AttributeError as exc:
            return {}, f"Windows WLAN API 函数不可用：{exc}"

        negotiated_version = wintypes.DWORD()
        client_handle = wintypes.HANDLE()
        code = int(wlanapi.WlanOpenHandle(
            2, None, ctypes.byref(negotiated_version), ctypes.byref(client_handle),
        ))
        if code != 0:
            return {}, f"WlanOpenHandle 失败（错误码 {code}）"

        rows: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        interface_list = ctypes.c_void_p()
        try:
            code = int(wlanapi.WlanEnumInterfaces(
                client_handle, None, ctypes.byref(interface_list),
            ))
            if code != 0 or not interface_list.value:
                return {}, f"WlanEnumInterfaces 失败（错误码 {code}）"

            list_head = ctypes.cast(
                interface_list,
                ctypes.POINTER(_WlanInterfaceInfoListHead),
            ).contents
            count = int(list_head.dwNumberOfItems)
            base_address = (
                ctypes.addressof(list_head)
                + _WlanInterfaceInfoListHead.InterfaceInfo.offset
            )
            interface_size = ctypes.sizeof(_WlanInterfaceInfo)
            adapter_guids = {
                adapter.name: self._guid_from_text(adapter.guid)
                for adapter in adapters
            }
            for index in range(count):
                info = ctypes.cast(
                    base_address + index * interface_size,
                    ctypes.POINTER(_WlanInterfaceInfo),
                ).contents
                matched_name = ""
                for adapter in adapters:
                    wanted = adapter_guids.get(adapter.name)
                    if wanted is not None and bytes(info.InterfaceGuid) == bytes(wanted):
                        matched_name = adapter.name
                        break
                if not matched_name:
                    continue

                data_size = wintypes.DWORD()
                data_ptr = ctypes.c_void_p()
                opcode_type = wintypes.DWORD()
                query_code = int(wlanapi.WlanQueryInterface(
                    client_handle,
                    ctypes.byref(info.InterfaceGuid),
                    WLAN_INTF_OPCODE_CURRENT_CONNECTION,
                    None,
                    ctypes.byref(data_size),
                    ctypes.byref(data_ptr),
                    ctypes.byref(opcode_type),
                ))
                try:
                    if query_code == ERROR_WLAN_NOT_FOUND:
                        rows[matched_name] = {
                            "connected": False,
                            "ssid": "",
                            "signal": "",
                            "state": "未连接（Win32 WLAN API）",
                            "api_source": "Win32 WLAN API",
                        }
                    elif query_code == ERROR_ACCESS_DENIED:
                        errors.append(
                            f"{matched_name}：WlanQueryInterface 被拒绝访问（错误码 5）"
                        )
                    elif query_code != 0 or not data_ptr.value:
                        errors.append(
                            f"{matched_name}：WlanQueryInterface 失败（错误码 {query_code}）"
                        )
                    else:
                        attrs = ctypes.cast(
                            data_ptr,
                            ctypes.POINTER(_WlanConnectionAttributes),
                        ).contents
                        ssid_length = min(
                            int(attrs.wlanAssociationAttributes.dot11Ssid.uSSIDLength),
                            32,
                        )
                        raw_ssid = bytes(
                            attrs.wlanAssociationAttributes.dot11Ssid.ucSSID[:ssid_length]
                        )
                        ssid = raw_ssid.decode("utf-8", errors="replace")
                        state_code = int(attrs.isState)
                        connected = state_code in {
                            WLAN_INTERFACE_STATE_CONNECTED,
                            WLAN_INTERFACE_STATE_ADHOC_NETWORK_FORMED,
                        }
                        signal_quality = int(
                            attrs.wlanAssociationAttributes.wlanSignalQuality
                        )
                        rows[matched_name] = {
                            "connected": connected,
                            "ssid": ssid if connected else "",
                            "signal": f"{signal_quality}%" if connected else "",
                            "state": (
                                "已连接（Win32 WLAN API）"
                                if connected
                                else "未连接（Win32 WLAN API）"
                            ),
                            "api_source": "Win32 WLAN API",
                        }
                finally:
                    if data_ptr.value:
                        wlanapi.WlanFreeMemory(data_ptr)
        finally:
            if interface_list.value:
                wlanapi.WlanFreeMemory(interface_list)
            close_handle = getattr(wlanapi, "WlanCloseHandle", None)
            if close_handle is not None:
                close_handle.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
                close_handle.restype = wintypes.DWORD
                close_handle(client_handle, None)

        return rows, "；".join(errors)

    def _get_windows_connection_profiles(self) -> tuple[dict[str, dict[str, str]], str]:
        """只读取接口是否有活动网络，不读取 Name/网络配置文件名。"""
        script = r'''
$profiles=@(Get-NetConnectionProfile -ErrorAction Stop | Select-Object InterfaceAlias,IPv4Connectivity,IPv6Connectivity)
$profiles | ConvertTo-Json -Depth 3 -Compress
'''
        try:
            raw = run_powershell(script, timeout=20)
            if not raw.strip():
                return {}, ""
            value: Any = json.loads(raw)
            rows = value if isinstance(value, list) else [value]
            result: dict[str, dict[str, str]] = {}
            for item in rows:
                if not isinstance(item, dict):
                    continue
                alias = str(item.get("InterfaceAlias", "") or "").strip()
                if alias:
                    result[alias] = {
                        "ipv4": str(item.get("IPv4Connectivity", "") or "").strip(),
                        "ipv6": str(item.get("IPv6Connectivity", "") or "").strip(),
                    }
            return result, ""
        except Exception as exc:
            return {}, str(exc)

    def _get_windows_ipv4_addresses(
        self, adapters: list[WifiAdapter],
    ) -> dict[str, str]:
        """读取各无线接口的 IPv4；这里只补充地址，不参与 SSID 判断。"""
        if not adapters:
            return {}
        aliases = ",".join(_ps_quote(adapter.name) for adapter in adapters)
        script = fr'''
$wanted=@({aliases})
$rows=@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {{ $wanted -contains $_.InterfaceAlias -and $_.IPAddress -notlike '169.254.*' }} |
    Select-Object InterfaceAlias,IPAddress,PrefixLength)
$rows | ConvertTo-Json -Depth 3 -Compress
'''
        try:
            raw = run_powershell(script, timeout=20)
            if not raw.strip():
                return {}
            value: Any = json.loads(raw)
            rows = value if isinstance(value, list) else [value]
            result: dict[str, str] = {}
            for item in rows:
                if not isinstance(item, dict):
                    continue
                alias = str(item.get("InterfaceAlias", "") or "").strip()
                address = str(item.get("IPAddress", "") or "").strip()
                prefix = str(item.get("PrefixLength", "") or "").strip()
                if alias and address:
                    result[alias] = f"{address}/{prefix}" if prefix else address
            return result
        except Exception:
            # IP 只是补充信息，读取失败不能影响连接状态显示。
            return {}

    def list_wifi_adapters(self) -> list[WifiAdapter]:
        script = r"""
$items = Get-NetAdapter -IncludeHidden | Where-Object {
    $_.HardwareInterface -eq $true -and (
        $_.PhysicalMediaType -eq 'Native 802.11' -or
        $_.InterfaceDescription -match '(?i)wireless|wi-?fi|wlan|802\.11'
    )
} | Sort-Object ifIndex
$rows=@()
foreach($item in $items) {
    $bands=@()
    try {
        $props=@(Get-NetAdapterAdvancedProperty -Name $item.Name -ErrorAction SilentlyContinue)
        $validText=(@($props | ForEach-Object {@($_.ValidDisplayValues)}) -join ' ')
        if($validText -match '(?i)2[\.,]4|802\.11b|802\.11g') {$bands += '2.4G'}
        if($validText -match '(?i)(^|[^0-9])5\s*G|802\.11a|802\.11ac') {$bands += '5G'}
    } catch {}
    $rows += [pscustomobject]@{
        Name=$item.Name
        InterfaceDescription=$item.InterfaceDescription
        Status=$item.Status
        ifIndex=$item.ifIndex
        InterfaceGuid=$item.InterfaceGuid
        ConfigurableBands=@($bands | Select-Object -Unique)
    }
}
$rows | ConvertTo-Json -Depth 4 -Compress
"""
        raw = run_powershell(script)
        if not raw:
            return []
        parsed: Any = json.loads(raw)
        rows = parsed if isinstance(parsed, list) else [parsed]
        adapters: list[WifiAdapter] = []
        for position, row in enumerate(rows, 1):
            adapter = WifiAdapter(
                index=position,
                name=str(row.get("Name", "")),
                description=str(row.get("InterfaceDescription", "")),
                status=str(row.get("Status", "Unknown")),
                if_index=int(row.get("ifIndex", 0)),
                guid=str(row.get("InterfaceGuid", "")),
            )
            _, driver_text = run_netsh(
                ["netsh", "wlan", "show", "drivers", f'interface={adapter.name}'], timeout=15
            )
            adapter.hosted_supported, reported_bands = parse_driver_capabilities(driver_text)
            configurable = row.get("ConfigurableBands", [])
            if isinstance(configurable, str):
                configurable = [configurable]
            adapter.bands = tuple(
                band for band in ("2.4G", "5G", "6G")
                if band in reported_bands or band in configurable
            )
            adapters.append(adapter)
        return adapters

    def list_share_sources(self) -> list[str]:
        script = r"""
Get-NetAdapter -IncludeHidden | Where-Object {
    $_.Status -eq 'Up' -and
    $_.HardwareInterface -eq $true -and
    $_.PhysicalMediaType -ne 'Native 802.11' -and
    $_.InterfaceDescription -notmatch '(?i)virtual|vpn|loopback'
} | Sort-Object ifIndex | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress
"""
        raw = run_powershell(script)
        if not raw:
            return []
        value = json.loads(raw)
        return [str(x) for x in value] if isinstance(value, list) else [str(value)]

    @_serialized_backend_operation
    def set_adapter_enabled(self, name: str, enabled: bool) -> str:
        action_text = "启用" if enabled else "禁用"
        if os.name == "nt" and not is_admin():
            raise HotspotError(
                f"Windows 当前不是管理员权限，无法{action_text}网卡“{name}”。\n"
                "请右键 Python 或启动脚本，选择“以管理员身份运行”后重试。"
            )
        verb = "Enable" if enabled else "Disable"
        script = fr"""
$name={_ps_quote(name)}
$wantEnabled={'$true' if enabled else '$false'}
$actionError=$null
try {{
    {verb}-NetAdapter -Name $name -Confirm:$false -ErrorAction Stop
}} catch {{
    $actionError=$_.Exception.Message
}}
$lastStatus=$null
for($attempt=0;$attempt -lt 6;$attempt++) {{
    try {{
        $lastStatus=(Get-NetAdapter -Name $name -ErrorAction Stop).Status.ToString()
        if($wantEnabled -and $lastStatus -ne 'Disabled') {{$lastStatus; exit}}
        if(-not $wantEnabled -and $lastStatus -eq 'Disabled') {{$lastStatus; exit}}
    }} catch {{}}
    Start-Sleep -Milliseconds 700
}}
try {{
    $cim=Get-CimInstance Win32_NetworkAdapter -ErrorAction Stop |
        Where-Object {{$_.NetConnectionID -eq $name}} | Select-Object -First 1
    if($cim) {{
        if($wantEnabled -and $cim.NetEnabled -eq $true) {{'Enabled（WMI）'; exit}}
        if(-not $wantEnabled -and $cim.NetEnabled -eq $false) {{'Disabled（WMI）'; exit}}
    }}
}} catch {{}}
if($actionError) {{throw $actionError}}
if($lastStatus) {{$lastStatus; exit}}
'命令已提交，驱动状态仍在刷新'
"""
        try:
            return run_powershell(script, timeout=45)
        except HotspotError as exc:
            detail = str(exc)
            if re.search(r"access\s+is\s+denied|拒绝访问", detail, re.I):
                raise HotspotError(
                    f"Windows 无法{action_text}网卡“{name}”：权限不足。\n"
                    "请右键 Python 或启动脚本，选择“以管理员身份运行”后重试。"
                ) from None
            raise

    @_serialized_backend_operation
    def connect_wifi_adapters(
        self, adapters: list[WifiAdapter], ssid: str, password: str,
        log: Callable[[str], None], retry_failed: bool = True,
    ) -> dict[str, str]:
        if not adapters:
            raise HotspotError("请选择至少一块无线网卡。")
        if not 1 <= len(ssid.encode("utf-8")) <= 32:
            raise HotspotError("Wi-Fi 名称不能为空，且 UTF-8 长度不能超过 32 字节。")
        # 不在客户端连接入口强制套用热点创建时的 WPA2 密码规则：
        # 空密码表示开放网络，具体认证方式交给 Windows/驱动判断。
        if len(password) > 63:
            raise HotspotError("Wi-Fi 密码长度不能超过 63 个字符。")

        if password:
            security_xml = f"""
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{xml_escape(password)}</keyMaterial>
            </sharedKey>
        </security>"""
        else:
            security_xml = """
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>"""

        profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{xml_escape(ssid)}</name>
    <SSIDConfig>
        <SSID>
            <name>{xml_escape(ssid)}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
{security_xml}
    </MSM>
</WLANProfile>
"""
        results: dict[str, str] = {}
        failures: list[str] = []
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as profile_file:
            profile_file.write(profile_xml)
            profile_path = profile_file.name
        try:
            for adapter in adapters:
                try:
                    if adapter_status_is_disabled(adapter.status):
                        if os.name == "nt" and not is_admin():
                            raise HotspotError(
                                f"{adapter.name} 当前已禁用，启用网卡需要管理员权限。\n"
                                "请右键 Python 或启动脚本，选择“以管理员身份运行”后重试。"
                            )
                        log(f"Windows：{adapter.name} 当前已禁用，正在尝试启用后连接。")
                        self.set_adapter_enabled(adapter.name, True)
                        if not self._wait_windows_adapter_ready(adapter.name, timeout=18.0):
                            raise HotspotError(
                                f"{adapter.name} 已发出启用命令，但无线接口仍未准备好。"
                                "请等待几秒后刷新，或重新插拔该无线网卡。"
                            )
                        log(f"Windows：{adapter.name} 已启用，正在等待 WLAN 驱动完成恢复。")
                    radio_state, radio_detail = self._windows_radio_state(adapter.name)
                    if radio_state == "software_off":
                        raise HotspotError(
                            f"{adapter.name} 的无线射频被 Windows 软件关闭（Software Off）。"
                            "请打开 Windows WiFi、关闭飞行模式后再连接。"
                        )
                    if radio_state == "hardware_off":
                        raise HotspotError(
                            f"{adapter.name} 的无线射频被硬件开关关闭（Hardware Off）。"
                            "请检查实体开关、键盘无线按键或 USB 网卡状态。"
                        )
                    if radio_state == "missing":
                        raise HotspotError(
                            f"{adapter.name} 当前没有被 WLAN 服务识别；请刷新网卡或重新插拔设备。"
                        )
                    log(f"Windows：正在让 {adapter.name} 连接 WiFi：{ssid}")
                    add_code, add_output = run_netsh(
                        ["netsh", "wlan", "add", "profile", f"filename={profile_path}", f"interface={adapter.name}"],
                        timeout=30,
                    )
                    if add_code != 0:
                        raise HotspotError(f"添加 WiFi 配置失败：{add_output}")
                    connect_code, connect_output = run_netsh(
                        ["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}", f"interface={adapter.name}"],
                        timeout=45,
                    )
                    if connect_code != 0 and re.search(r"80342002|0x80342002", connect_output, re.I):
                        raise HotspotError(
                            f"{adapter.name} 返回无线电源状态错误 0x80342002；"
                            "本轮连接失败，第一轮全部网卡完成后将只重试一次。"
                        )
                    if connect_code != 0:
                        raise HotspotError(f"连接 WiFi 失败：{connect_output}")
                    log(f"Windows：{adapter.name} 连接命令已提交，正在等待系统确认目标 SSID。")
                    self._wlan_api_adapter_context = adapter
                    try:
                        confirmed, state = self._wait_windows_client_connected(
                            adapter.name, ssid, timeout=12,
                        )
                    finally:
                        self._wlan_api_adapter_context = None
                    if not confirmed:
                        detail = state or "未读取到最终状态"
                        # netsh 返回成功已经代表请求交给 Windows WLAN 服务。
                        # WLAN API/位置权限或驱动切换较慢时，不撤销这次请求，
                        # 后续 10 秒状态刷新会继续确认真实连接结果。
                        log(
                            f"Windows：{adapter.name} 连接请求已提交，暂未读取到最终状态："
                            f"{detail}；保留系统连接请求并继续后台检查。"
                        )
                    results[adapter.name] = (
                        state or connect_output or "已确认连接"
                        if confirmed
                        else "连接请求已提交，等待系统确认"
                    )
                    if confirmed:
                        log(f"Windows：{adapter.name} 已确认连接到 {ssid}（{state or '已连接'}）。")
                except HotspotError as exc:
                    failures.append(f"{adapter.name}: {exc}")
                    log(f"Windows：{adapter.name} 连接失败：{exc}；继续尝试其它选中网卡。")
        finally:
            try:
                Path(profile_path).unlink(missing_ok=True)
            except OSError:
                pass
        if failures and retry_failed:
            failed_names = {
                item.split(":", 1)[0].strip()
                for item in failures
                if ":" in item
            }
            retry_adapters = [adapter for adapter in adapters if adapter.name in failed_names]
            if retry_adapters:
                log(
                    "Windows：第一轮连接已完成；将只对未连接网卡再重试一轮："
                    + "、".join(adapter.name for adapter in retry_adapters)
                )
                try:
                    retry_results = self.connect_wifi_adapters(
                        retry_adapters, ssid, password, log, retry_failed=False,
                    )
                except HotspotError as retry_exc:
                    prefix = "部分无线网卡连接失败" if results else "无线网卡连接失败"
                    raise HotspotError(
                        prefix + "（已完成一次重试）：\n" + str(retry_exc)
                    ) from None
                results.update(retry_results)
                failures = []
        if failures and not results:
            raise HotspotError("无线网卡连接失败：\n" + "\n\n".join(failures))
        if failures:
            log("Windows：部分网卡连接失败，但已保留成功或已提交的连接请求：\n" + "\n".join(failures))
        return results

    def _wait_windows_client_connected(
        self, adapter_name: str, target_ssid: str, timeout: float = 30.0,
    ) -> tuple[bool, str]:
        """等待 Windows 真正连接到目标 SSID，避免把 netsh 命令提交成功当成已连接。

        netsh wlan connect 通常只表示连接请求已进入系统队列。这里优先读取
        Win32 WLAN API 的实时关联 SSID；如果系统策略拦截 API，再回退到
        netsh。Get-NetConnectionProfile 只能判断接口是否有活动网络，绝不用于
        比较目标 SSID。
        """
        deadline = time.monotonic() + timeout
        last_state = ""
        can_read_any_state = False
        while time.monotonic() < deadline:
            api_adapter = getattr(self, "_wlan_api_adapter_context", None)
            if isinstance(api_adapter, WifiAdapter) and api_adapter.name == adapter_name:
                api_rows, api_error = self._get_windows_wlan_api_status([api_adapter])
                api_row = api_rows.get(adapter_name)
                if api_row:
                    can_read_any_state = True
                    current_ssid = str(api_row.get("ssid", "") or "").strip()
                    state = str(api_row.get("state", "") or "未读取")
                    signal = str(api_row.get("signal", "") or "")
                    last_state = (
                        f"{state}｜SSID：{current_ssid or '未连接'}"
                        f"{f'｜信号：{signal}' if signal else ''}"
                    )
                    if bool(api_row.get("connected")) and current_ssid == target_ssid:
                        return True, last_state
                elif api_error:
                    last_state = f"Win32 WLAN API 暂时不可用：{api_error}"

            code, output = run_netsh(
                ["netsh", "wlan", "show", "interfaces", f"interface={adapter_name}"],
                timeout=12,
            )
            if code == 0 and output.strip():
                can_read_any_state = True
                parsed = self._parse_windows_interface_status(output, adapter_name)
                state = parsed.get("state", "")
                current_ssid = parsed.get("ssid", "")
                last_state = (
                    f"{state or '未读取'}｜SSID：{current_ssid or '未读取'}"
                )
                if (
                    current_ssid.strip() == target_ssid
                    and state
                    and not re.search(r"disconnected|not connected|未连接|已断开", state, re.I)
                ):
                    return True, last_state
            else:
                profiles, _ = self._get_windows_connection_profiles()
                item = profiles.get(adapter_name, {})
                if item:
                    can_read_any_state = True
                    ipv4 = str(item.get("ipv4", "") or "").strip()
                    last_state = (
                        "系统检测到接口有活动网络"
                        "｜真实 SSID：受 Windows 权限限制，未核对"
                    )
                    # 不能用活动网络名称冒充 SSID，但可告诉上层“接口有连接”。
                    # 连接目标仍必须由 Win32 API/netsh 的真实 SSID确认。
                    last_state = f"{last_state}｜IPv4：{ipv4 or '未读取'}"
            time.sleep(1.0)

        if not can_read_any_state:
            # 位置权限、企业策略或旧版 Windows 可能同时阻止两种读取方式。
            # 这里绝不能把“命令已提交”伪装成“已连接”；交给上层显示
            # “未确认”，并引导用户检查位置权限。
            return False, "命令已提交，但 Windows 暂时禁止读取 WLAN 最终状态"
        return False, last_state or "未读取到最终状态"

    @staticmethod
    def _parse_windows_interface_status(
        output: str, adapter_name: str = "",
    ) -> dict[str, str]:
        """解析 netsh wlan show interfaces 的单个接口结果。"""
        parsed: dict[str, str] = {}
        key_map = {
            "name": {"name", "名称", "名字"},
            "state": {"state", "状态"},
            "ssid": {"ssid"},
            "signal": {"signal", "信号"},
        }
        current_name = ""
        for raw_line in output.splitlines():
            if ":" not in raw_line:
                continue
            label, value = raw_line.split(":", 1)
            label = label.strip().lower()
            value = value.strip()
            if label in key_map["name"]:
                current_name = value
                continue
            if label in key_map["state"]:
                parsed["state"] = value
            elif label in key_map["ssid"]:
                parsed["ssid"] = value
            elif label in key_map["signal"]:
                parsed["signal"] = value
        if adapter_name and current_name and current_name != adapter_name:
            return {}
        return parsed

    @staticmethod
    def _parse_windows_scan_target(output: str, target_ssid: str) -> tuple[bool, str]:
        """解析 netsh wlan show networks mode=bssid 的目标 SSID 和最佳信号。"""
        if not target_ssid:
            return False, ""
        current_ssid = ""
        in_target = False
        best_signal = -1
        for raw_line in output.splitlines():
            line = raw_line.strip()
            ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line, re.I)
            if not ssid_match:
                ssid_match = re.match(r"^SSID\s+\d+\s*：\s*(.*)$", line, re.I)
            if ssid_match:
                current_ssid = ssid_match.group(1).strip()
                in_target = current_ssid == target_ssid
                continue
            if not in_target:
                continue
            signal_match = re.search(r"(?:Signal|信号)\s*[:：]\s*(\d+)\s*%", line, re.I)
            if signal_match:
                try:
                    best_signal = max(best_signal, int(signal_match.group(1)))
                except ValueError:
                    pass
        return best_signal >= 0, f"{best_signal}%" if best_signal >= 0 else ""

    def _get_windows_target_scan(
        self, adapter_name: str, target_ssid: str,
    ) -> tuple[bool, str, str]:
        """读取指定 Windows 无线网卡扫描缓存中的目标 SSID 信号。"""
        if not target_ssid:
            return False, "", ""
        code, output = run_netsh(
            [
                "netsh", "wlan", "show", "networks",
                "mode=bssid", f"interface={adapter_name}",
            ],
            timeout=25,
        )
        if code != 0:
            return False, "", output.strip()
        visible, signal = self._parse_windows_scan_target(output, target_ssid)
        return visible, signal, ""

    @_serialized_backend_operation
    def disconnect_wifi_adapters(
        self, adapters: list[WifiAdapter], log: Callable[[str], None],
    ) -> dict[str, str]:
        if not adapters:
            raise HotspotError("请选择至少一块无线网卡。")
        results: dict[str, str] = {}
        for adapter in adapters:
            log(f"Windows：正在断开 {adapter.name} 的 WiFi 连接。")
            code, output = run_netsh(["netsh", "wlan", "disconnect", f"interface={adapter.name}"], timeout=30)
            if code != 0:
                raise HotspotError(f"{adapter.name} 断开 WiFi 失败：{output}")
            results[adapter.name] = output or "断开命令已提交"
            log(f"Windows：{adapter.name} 断开命令已提交。")
        return results

    def get_wifi_client_status(
        self, adapters: list[WifiAdapter], target_ssid: str = "",
    ) -> list[dict[str, Any]]:
        api_rows, api_error = self._get_windows_wlan_api_status(adapters)
        if adapters and len(api_rows) == len(adapters):
            ipv4_by_adapter = self._get_windows_ipv4_addresses(adapters)
            rows: list[dict[str, Any]] = []
            for adapter in adapters:
                item = dict(api_rows.get(adapter.name, {}))
                connected = bool(item.get("connected"))
                ssid = str(item.get("ssid", "") or "")
                target_match = (
                    bool(connected and target_ssid and ssid == target_ssid)
                    if target_ssid
                    else None
                )
                warning = ""
                if api_error:
                    warning = api_error
                rows.append({
                    "adapter": adapter.name,
                    "connected": connected,
                    "ssid": ssid,
                    "target_match": target_match,
                    "state": str(item.get("state", "") or "未读取"),
                    "profile": "",
                    "ip": ipv4_by_adapter.get(adapter.name, ""),
                    "signal": str(item.get("signal", "") or ""),
                    "target_visible": False,
                    "target_signal": "",
                    "warning": warning,
                })
            return rows

        code, output = run_netsh(["netsh", "wlan", "show", "interfaces"], timeout=25)
        if code != 0:
            if self._wlan_query_requires_location(output):
                profiles, profile_error = self._get_windows_connection_profiles()
                ipv4_by_adapter = self._get_windows_ipv4_addresses(adapters)
                warning = (
                    "Windows WLAN API/netsh 读取真实 SSID 受权限限制；"
                    "Get-NetConnectionProfile 仅用于判断接口是否有活动连接，"
                    "不会把网络配置名当作 SSID。可在‘设置→隐私和安全性→位置’开启。"
                )
                if api_error:
                    warning = f"{warning} Win32 WLAN API：{api_error}。"
                if profile_error:
                    warning += f" 兜底读取也失败：{profile_error}"
                rows: list[dict[str, Any]] = []
                for adapter in adapters:
                    item = profiles.get(adapter.name, {})
                    connected = bool(item)
                    state = "已连接，但真实 SSID 未读取" if connected else "未连接（真实 SSID 未读取）"
                    if connected:
                        warning_text = (
                            "说明：只能确认接口存在活动网络，不能确认它是不是目标 SSID。"
                        )
                    else:
                        warning_text = warning
                    rows.append({
                        "adapter": adapter.name,
                        "connected": connected,
                        "ssid": "",
                        "target_match": None if connected and target_ssid else False,
                        "state": state,
                        "profile": "",
                        "ip": ipv4_by_adapter.get(adapter.name, ""),
                        "signal": "",
                        "target_visible": False,
                        "target_signal": "",
                        "warning": warning_text,
                    })
                return rows
            raise HotspotError(output or "读取 Windows WiFi 连接状态失败。")
        parsed: dict[str, dict[str, str]] = {}
        current_name = ""
        current_item: dict[str, str] = {}
        key_map = {
            "name": {"name", "名称", "名字"},
            "state": {"state", "状态"},
            "ssid": {"ssid"},
            "signal": {"signal", "信号"},
        }
        for raw_line in output.splitlines():
            if ":" not in raw_line:
                continue
            label, value = raw_line.split(":", 1)
            label = label.strip().lower()
            value = value.strip()
            if label in key_map["name"]:
                if current_name:
                    parsed[current_name] = current_item
                current_name = value
                current_item = {}
                continue
            if not current_name:
                continue
            if label in key_map["state"]:
                current_item["state"] = value
            elif label in key_map["ssid"]:
                current_item["ssid"] = value
            elif label in key_map["signal"]:
                current_item["signal"] = value
        if current_name:
            parsed[current_name] = current_item
        rows: list[dict[str, Any]] = []
        for adapter in adapters:
            item = parsed.get(adapter.name, {})
            state = item.get("state", "未读取")
            ssid = item.get("ssid", "")
            connected = bool(
                ssid and not re.search(r"disconnected|not connected|未连接|已断开|未連線", state, re.I)
            )
            target_match = (
                bool(connected and target_ssid and ssid == target_ssid)
                if target_ssid
                else None
            )
            target_visible = False
            target_signal = ""
            scan_warning = ""
            if target_ssid and not connected:
                target_visible, target_signal, scan_error = self._get_windows_target_scan(
                    adapter.name, target_ssid,
                )
                if scan_error and self._wlan_query_requires_location(scan_error):
                    scan_warning = (
                        "Windows 位置权限未开启，暂时无法读取扫描到的热点和信号；"
                        "可在“设置→隐私和安全性→位置”开启。"
                    )
            # Win32 API 可能只对部分网卡返回错误，而 netsh 仍能返回其余
            # 接口的基本状态。对没有读到 SSID 的网卡保留这个权限提示，
            # 避免把“无法查询/无法扫描”误显示成“目标热点不存在”。
            if not ssid and api_error and not scan_warning:
                scan_warning = (
                    "Windows WLAN API 未能读取此网卡的实时 SSID；"
                    "扫描结果可能不完整。可在“设置→隐私和安全性→位置”开启。"
                )
            rows.append({
                "adapter": adapter.name,
                "connected": connected,
                "ssid": ssid,
                "target_match": target_match,
                "state": state,
                "profile": "",
                "ip": "",
                "signal": item.get("signal", ""),
                "target_visible": target_visible,
                "target_signal": target_signal,
                "warning": scan_warning,
            })
        return rows

    def _adapter_is_enabled(self, name: str) -> bool:
        script = fr"""
$name={_ps_quote(name)}
for($attempt=0;$attempt -lt 4;$attempt++) {{
    try {{
        $status=(Get-NetAdapter -Name $name -ErrorAction Stop).Status.ToString()
        [pscustomobject]@{{Known=$true;Enabled=($status -ne 'Disabled');Status=$status}} |
            ConvertTo-Json -Compress
        exit
    }} catch {{Start-Sleep -Milliseconds 500}}
}}
try {{
    $cim=Get-CimInstance Win32_NetworkAdapter -ErrorAction Stop |
        Where-Object {{$_.NetConnectionID -eq $name}} | Select-Object -First 1
    if($cim -and $null -ne $cim.NetEnabled) {{
        [pscustomobject]@{{Known=$true;Enabled=[bool]$cim.NetEnabled;Status='WMI'}} |
            ConvertTo-Json -Compress
        exit
    }}
}} catch {{}}
[pscustomobject]@{{Known=$false;Enabled=$true;Status='Unknown'}} | ConvertTo-Json -Compress
"""
        result = json.loads(run_powershell(script, timeout=25))
        if not result.get("Known"):
            raise HotspotError(f"暂时无法读取网卡 {name} 的启用状态，请刷新后重试。")
        return bool(result.get("Enabled"))

    def _windows_radio_state(self, name: str) -> tuple[str, str]:
        """读取指定无线接口的硬件/软件射频状态。

        ``Get-NetAdapter`` 的 ``Up`` 只代表网卡接口已启用，不能代表 WLAN
        射频已经打开。Windows 仍可能报告 Hardware On / Software Off，
        此时 ``netsh wlan connect`` 会返回 0x80342002。
        """
        code, output = run_netsh(
            ["netsh", "wlan", "show", "interfaces", f"interface={name}"],
            timeout=15,
        )
        text = output or ""
        lowered = text.lower()
        if re.search(r"software\s+off|software\s+disabled|软件\s*(?:关闭|关|禁用)", lowered, re.I):
            return "software_off", text
        if re.search(r"hardware\s+off|hardware\s+disabled|硬件\s*(?:关闭|关|禁用)", lowered, re.I):
            return "hardware_off", text
        if code != 0 and re.search(
            r"no wireless interface|没有无线接口|系统上没有此类无线接口|interface.*not found",
            text,
            re.I,
        ):
            return "missing", text
        return "unknown", text

    def _wait_windows_adapter_ready(self, name: str, timeout: float = 18.0) -> bool:
        """等待刚启用的无线网卡完成驱动/射频恢复。

        ``Enable-NetAdapter`` 返回并不代表 WLAN AutoConfig 已经可以接受
        ``netsh wlan connect``。某些 USB 网卡会先报告已启用，随后还需要数秒
        才能从掉电状态恢复；过早连接会返回 0x80342002。
        """
        deadline = time.monotonic() + timeout
        script = fr"""
$name={_ps_quote(name)}
try {{
    $item=Get-NetAdapter -Name $name -ErrorAction Stop
    $status=$item.Status.ToString()
    [pscustomobject]@{{Known=$true;Enabled=($status -notin @('Disabled','Not Present'));Status=$status}} |
        ConvertTo-Json -Compress
}} catch {{
    [pscustomobject]@{{Known=$false;Enabled=$false;Status=$_.Exception.Message}} |
        ConvertTo-Json -Compress
}}
"""
        while time.monotonic() < deadline:
            try:
                raw = run_powershell(script, timeout=10)
                result = json.loads(raw) if raw.strip() else {}
                if result.get("Known") and result.get("Enabled"):
                    # 给 WLAN AutoConfig/驱动一个短暂的 settle 时间，避免
                    # Get-NetAdapter 已恢复但射频仍处于掉电状态。
                    time.sleep(1.0)
                    return True
            except (HotspotError, json.JSONDecodeError, TypeError, ValueError):
                pass
            time.sleep(0.7)
        return False

    def _set_band(self, name: str, band: str) -> dict[str, Any]:
        # 驱动属性没有统一命名，按“首选频带”优先，其次使用 Wireless Mode。
        script = fr"""
$name={_ps_quote(name)}
$band={_ps_quote(band)}
$props=@(Get-NetAdapterAdvancedProperty -Name $name -ErrorAction SilentlyContinue)
$chosen=$null
$preferred=$props | Where-Object {{
    $_.DisplayName -match '(?i)preferred.*band|band.*preference|首选.*频|频带.*首选' -or
    $_.RegistryKeyword -match '(?i)preferredband|bandpreference'
}} | Select-Object -First 1
if ($preferred) {{
    $values=@($preferred.ValidDisplayValues)
    if ($band -eq '2.4G') {{
        $chosen=$values | Where-Object {{ $_ -match '2[\.,]4|2\.4' }} | Select-Object -First 1
    }} else {{
        $chosen=$values | Where-Object {{ $_ -match '(^|[^0-9])5([^0-9]|$)|5G' }} | Select-Object -First 1
    }}
    if ($chosen) {{
        Set-NetAdapterAdvancedProperty -Name $name -RegistryKeyword $preferred.RegistryKeyword -DisplayValue $chosen -NoRestart
        [pscustomobject]@{{Applied=$true; Property=$preferred.DisplayName; RegistryKeyword=$preferred.RegistryKeyword; Value=$chosen; Previous=@($preferred.RegistryValue)}} | ConvertTo-Json -Compress
        exit
    }}
}}
$mode=$props | Where-Object {{
    $_.DisplayName -match '(?i)^wireless mode$|无线模式' -or $_.RegistryKeyword -match '(?i)^wirelessmode$'
}} | Select-Object -First 1
if ($mode) {{
    $pairs=@()
    for($i=0;$i -lt @($mode.ValidDisplayValues).Count;$i++) {{
        $pairs += [pscustomobject]@{{D=@($mode.ValidDisplayValues)[$i];R=@($mode.ValidRegistryValues)[$i]}}
    }}
    if ($band -eq '2.4G') {{
        $pick=$pairs | Where-Object {{ $_.D -match '(?i)b|g' -and $_.D -notmatch '(?i)ac' }} | Select-Object -Last 1
    }} else {{
        $pick=$pairs | Where-Object {{ $_.D -match '(?i)802\.11a|ac' }} | Select-Object -Last 1
    }}
    if ($pick) {{
        Set-NetAdapterAdvancedProperty -Name $name -RegistryKeyword $mode.RegistryKeyword -RegistryValue $pick.R -NoRestart
        [pscustomobject]@{{Applied=$true; Property=$mode.DisplayName; RegistryKeyword=$mode.RegistryKeyword; Value=$pick.D; Previous=@($mode.RegistryValue)}} | ConvertTo-Json -Compress
        exit
    }}
}}
[pscustomobject]@{{Applied=$false; Property=''; RegistryKeyword=''; Value=''; Previous=@()}} | ConvertTo-Json -Compress
"""
        raw = run_powershell(script, timeout=40)
        return json.loads(raw)

    def _set_channel(self, name: str, band: str, channel: int) -> dict[str, Any]:
        """保守尝试 Windows 厂商驱动提供的热点/IBSS 信道属性。"""
        if channel not in DEFAULT_CHANNELS_BY_BAND.get(band, ()):
            raise HotspotError(f"信道 {channel} 不属于 {band} 的内置常见信道范围。")
        script = fr"""
$name={_ps_quote(name)}
$wanted={channel}
$props=@(Get-NetAdapterAdvancedProperty -Name $name -ErrorAction SilentlyContinue)
$candidates=@($props | Where-Object {{
    $label=(([string]$_.DisplayName) + ' ' + ([string]$_.RegistryKeyword))
    $label -match '(?i)(ad.?hoc|ibss|soft.?ap|hosted).*(channel|信道|频道)|(channel|信道|频道).*(ad.?hoc|ibss|soft.?ap|hosted)' -or
    $_.DisplayName -match '(?i)^\s*(channel|信道|频道)(\s*(number|编号))?\s*$' -or
    $_.RegistryKeyword -match '(?i)^channel(number)?$'
}})
foreach($property in $candidates) {{
    $displayValues=@($property.ValidDisplayValues)
    $registryValues=@($property.ValidRegistryValues)
    for($i=0;$i -lt $displayValues.Count;$i++) {{
        $displayText=[string]$displayValues[$i]
        $numbers=@([regex]::Matches($displayText,'(?<!\d)\d{{1,3}}(?!\d)') | ForEach-Object {{[int]$_.Value}})
        if($numbers -notcontains $wanted) {{continue}}
        if($i -lt $registryValues.Count -and $null -ne $registryValues[$i]) {{
            Set-NetAdapterAdvancedProperty -Name $name -RegistryKeyword $property.RegistryKeyword -RegistryValue @($registryValues[$i]) -NoRestart -ErrorAction Stop
        }} else {{
            Set-NetAdapterAdvancedProperty -Name $name -RegistryKeyword $property.RegistryKeyword -DisplayValue $displayText -NoRestart -ErrorAction Stop
        }}
        [pscustomobject]@{{
            Applied=$true; Property=$property.DisplayName; RegistryKeyword=$property.RegistryKeyword;
            Value=$displayText; Previous=@($property.RegistryValue)
        }} | ConvertTo-Json -Compress
        exit
    }}
}}
[pscustomobject]@{{
    Applied=$false; Property=''; RegistryKeyword=''; Value=''; Previous=@();
    Reason='Windows 系统热点没有标准信道指定接口，且驱动未提供可识别的热点信道属性。'
}} | ConvertTo-Json -Compress
"""
        raw = run_powershell(script, timeout=40)
        return json.loads(raw)

    def _restore_band(self, name: str, setting: dict[str, Any]) -> None:
        """恢复热点启动前的驱动属性，也兼容没有 RegistryKeyword 的旧状态文件。"""
        if not setting.get("Applied"):
            return
        previous = setting.get("Previous", [])
        if not isinstance(previous, list):
            previous = [previous]
        if not previous:
            return
        values = "@(" + ",".join(_ps_quote(str(value)) for value in previous) + ")"
        script = f"""
$name={_ps_quote(name)}
$keyword={_ps_quote(str(setting.get('RegistryKeyword', '')))}
$displayName={_ps_quote(str(setting.get('Property', '')))}
$property=Get-NetAdapterAdvancedProperty -Name $name -ErrorAction Stop | Where-Object {{
    ($keyword -and $_.RegistryKeyword -eq $keyword) -or
    ((-not $keyword) -and $displayName -and $_.DisplayName -eq $displayName)
}} | Select-Object -First 1
if(-not $property) {{throw "找不到需要恢复的网卡高级属性：$displayName / $keyword"}}
Set-NetAdapterAdvancedProperty -Name $name -RegistryKeyword $property.RegistryKeyword -RegistryValue {values} -NoRestart -ErrorAction Stop
"""
        run_powershell(script, timeout=40)
        self._restart_adapter(name)

    def _restore_channel(self, name: str, setting: dict[str, Any]) -> None:
        """信道和频段都是同一种 Windows 高级属性记录，恢复格式相同。"""
        self._restore_band(name, setting)

    def _restart_adapter(self, name: str) -> None:
        script = (
            f"Restart-NetAdapter -Name {_ps_quote(name)} -Confirm:$false;"
            "Start-Sleep -Seconds 2"
        )
        run_powershell(script, timeout=45)

    def _list_other_wifi(self, selected_name: str) -> list[str]:
        script = fr"""
$selected={_ps_quote(selected_name)}
$names=@(Get-NetAdapter -IncludeHidden | Where-Object {{
    $_.HardwareInterface -eq $true -and $_.Status -notin @('Disabled','Not Present') -and $_.Name -ne $selected -and (
        $_.PhysicalMediaType -eq 'Native 802.11' -or $_.InterfaceDescription -match '(?i)wireless|wi-?fi|wlan|802\.11'
    )
}} | Select-Object -ExpandProperty Name)
$names | ConvertTo-Json -Compress
"""
        raw = run_powershell(script, timeout=30)
        if not raw:
            return []
        value = json.loads(raw)
        return [str(x) for x in value] if isinstance(value, list) else [str(value)]

    def _disable_wifi_adapters(self, names: list[str]) -> None:
        if not names:
            return
        array = "@(" + ",".join(_ps_quote(x) for x in names) + ")"
        run_powershell(
            f"foreach($n in {array}) {{ Disable-NetAdapter -Name $n -Confirm:$false -ErrorAction Stop }}",
            timeout=50,
        )

    def _enable_adapters(self, names: list[str]) -> None:
        if not names:
            return
        array = "@(" + ",".join(_ps_quote(x) for x in names) + ")"
        run_powershell(
            f"foreach($n in {array}) {{ Enable-NetAdapter -Name $n -Confirm:$false -ErrorAction Stop }}",
            timeout=50,
        )

    def _hosted_is_started(self) -> bool:
        _, output = run_netsh(["netsh", "wlan", "show", "hostednetwork"], timeout=15)
        return bool(
            re.search(r"status\s*:\s*started", output, re.I)
            or re.search(r"状态\s*:\s*已启动", output)
        )

    @staticmethod
    def _modern_powershell_preamble() -> str:
        """加载 WinRT 移动热点类型，并提供 PowerShell 5 可用的异步等待函数。"""
        return r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.Connectivity.ConnectionProfile,Windows.Networking.Connectivity,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.NetworkOperatorTetheringAccessPointConfiguration,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.TetheringWiFiBand,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
[Windows.Networking.NetworkOperators.TetheringWiFiAuthenticationKind,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime] | Out-Null
function Wait-GmyWinRtAction($operation) {
    $method=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
    } | Select-Object -First 1
    if(-not $method) {throw '当前 PowerShell 无法等待 Windows 异步操作。'}
    $task=$method.Invoke($null,@($operation))
    $task.Wait()
}
function Wait-GmyWinRtOperation($operation, [Type]$resultType) {
    $method=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and
        $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1
    } | Select-Object -First 1
    if(-not $method) {throw '当前 PowerShell 无法等待 Windows 异步操作。'}
    $task=$method.MakeGenericMethod($resultType).Invoke($null,@($operation))
    $task.Wait()
    return $task.Result
}
function Get-GmySourceProfile([string]$sourceName) {
    $adapter=$null
    for($attempt=0;$attempt -lt 3 -and -not $adapter;$attempt++) {
        try {
            $adapter=Get-NetAdapter -IncludeHidden -ErrorAction Stop |
                Where-Object {$_.Name -eq $sourceName} | Select-Object -First 1
        } catch {}
        if(-not $adapter) {Start-Sleep -Milliseconds 500}
    }
    if(-not $adapter) {throw "找不到共享源网卡：$sourceName"}
    $adapterId=[guid]$adapter.InterfaceGuid
    $profile=[Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles() |
        Where-Object {$_.NetworkAdapter -and $_.NetworkAdapter.NetworkAdapterId -eq $adapterId} |
        Select-Object -First 1
    if(-not $profile) {throw "找不到共享源 $sourceName 对应的活动 Windows 网络配置。"}
    return $profile
}
"""

    def _get_modern_hotspot_status(self) -> dict[str, Any]:
        """查询现代 Windows 移动热点；旧系统不支持时返回 available=False。"""
        script = self._modern_powershell_preamble() + r"""
$rows=@()
foreach($profile in @([Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles())) {
    if(-not $profile.NetworkAdapter) {continue}
    try {
        $cap=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::GetTetheringCapabilityFromConnectionProfile($profile)
        $manager=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        $config=$manager.GetCurrentAccessPointConfiguration()
        $profileAdapterId=$profile.NetworkAdapter.NetworkAdapterId
        $adapter=$null
        try {
            $adapter=Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue |
                Where-Object {try {[guid]$_.InterfaceGuid -eq $profileAdapterId} catch {$false}} |
                Select-Object -First 1
        } catch {}
        $rows += [pscustomobject]@{
            Source=if($adapter){$adapter.Name}else{$profile.ProfileName}
            Profile=$profile.ProfileName
            Capability=$cap.ToString()
            State=$manager.TetheringOperationalState.ToString()
            Ssid=$config.Ssid
            Band=$config.Band.ToString()
            Authentication=if($config.PSObject.Properties.Name -contains 'AuthenticationKind'){$config.AuthenticationKind.ToString()}else{'Unknown'}
        }
    } catch {}
}
[pscustomobject]@{Rows=@($rows)} | ConvertTo-Json -Depth 4 -Compress
"""
        try:
            raw = run_powershell(script, timeout=30)
            value: Any = json.loads(raw) if raw else {}
        except (HotspotError, json.JSONDecodeError):
            return {"available": False, "started": False, "state": "Unavailable", "rows": []}
        rows_value = value.get("Rows", []) if isinstance(value, dict) else []
        rows = rows_value if isinstance(rows_value, list) else ([rows_value] if rows_value else [])
        active = next(
            (row for row in rows if str(row.get("State", "")).lower() in ("on", "intransition")),
            None,
        )
        enabled = next(
            (row for row in rows if str(row.get("Capability", "")).lower() == "enabled"),
            None,
        )
        selected = active or enabled or (rows[0] if rows else {})
        return {
            "available": bool(rows),
            "started": bool(active and str(active.get("State", "")).lower() == "on"),
            "transitioning": bool(active and str(active.get("State", "")).lower() == "intransition"),
            "state": str(selected.get("State", "Off" if rows else "Unavailable")),
            "ssid": str(selected.get("Ssid", "")),
            "source": str(selected.get("Source", "")),
            "band": str(selected.get("Band", "")),
            "authentication": str(selected.get("Authentication", "")),
            "capability": str(selected.get("Capability", "")),
            "rows": rows,
        }

    def _start_modern_hotspot(
        self, source_name: str, ssid: str, password: str, band: str
    ) -> dict[str, Any]:
        band_value = "TwoPointFourGigahertz" if band == "2.4G" else "FiveGigahertz"
        script = self._modern_powershell_preamble() + f"""
$sourceName={_ps_quote(source_name)}
$ssid={_ps_quote(ssid)}
$passphrase={_ps_quote(password)}
$profile=Get-GmySourceProfile $sourceName
$capability=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::GetTetheringCapabilityFromConnectionProfile($profile)
if($capability.ToString() -ne 'Enabled') {{throw "Windows 移动热点能力不可用：$capability"}}
$manager=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$config=$manager.GetCurrentAccessPointConfiguration()
$config.Ssid=$ssid
$config.Passphrase=$passphrase
$config.Band=[Windows.Networking.NetworkOperators.TetheringWiFiBand]::{band_value}
if($config.PSObject.Properties.Name -contains 'AuthenticationKind') {{
    $config.AuthenticationKind=[Windows.Networking.NetworkOperators.TetheringWiFiAuthenticationKind]::Wpa2
}}
Wait-GmyWinRtAction ($manager.ConfigureAccessPointAsync($config))
$result=Wait-GmyWinRtOperation ($manager.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
$state=$manager.TetheringOperationalState.ToString()
[pscustomobject]@{{
    Success=($result.Status.ToString() -eq 'Success' -and $state -eq 'On')
    Result=$result.Status.ToString()
    Message=$result.AdditionalErrorMessage
    State=$state
    Ssid=$manager.GetCurrentAccessPointConfiguration().Ssid
}} | ConvertTo-Json -Compress
"""
        raw = run_powershell(script, timeout=75)
        result: Any = json.loads(raw) if raw else {}
        if not isinstance(result, dict) or not result.get("Success"):
            status = str(result.get("Result", "Unknown")) if isinstance(result, dict) else "Unknown"
            detail = str(result.get("Message", "")) if isinstance(result, dict) else ""
            state = str(result.get("State", "Unknown")) if isinstance(result, dict) else "Unknown"
            raise HotspotError(
                f"Windows 现代移动热点启动失败：{localized_tethering_status(status)}（系统状态：{localized_tethering_status(state)}）"
                + (f"\n\n{detail}" if detail else "")
            )
        return result

    def _stop_modern_hotspot(self, source_name: str = "") -> None:
        script = self._modern_powershell_preamble() + f"""
$sourceName={_ps_quote(source_name)}
$profiles=@([Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles())
if($sourceName) {{
    try {{
        $preferred=Get-GmySourceProfile $sourceName
        $profiles=@($preferred) + @($profiles | Where-Object {{$_.NetworkAdapter.NetworkAdapterId -ne $preferred.NetworkAdapter.NetworkAdapterId}})
    }} catch {{}}
}}
$stopped=$false
$resultStatus='AlreadyOff'
$message=''
foreach($profile in $profiles) {{
    if(-not $profile.NetworkAdapter) {{continue}}
    try {{
        $manager=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
        if($manager.TetheringOperationalState.ToString() -in @('On','InTransition')) {{
            $result=Wait-GmyWinRtOperation ($manager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
            $resultStatus=$result.Status.ToString()
            $message=$result.AdditionalErrorMessage
            $stopped=($resultStatus -eq 'Success' -and $manager.TetheringOperationalState.ToString() -eq 'Off')
            break
        }}
    }} catch {{}}
}}
[pscustomobject]@{{Success=($stopped -or $resultStatus -eq 'AlreadyOff');Result=$resultStatus;Message=$message}} |
    ConvertTo-Json -Compress
"""
        raw = run_powershell(script, timeout=60)
        result: Any = json.loads(raw) if raw else {}
        if not isinstance(result, dict) or not result.get("Success"):
            status = str(result.get("Result", "Unknown")) if isinstance(result, dict) else "Unknown"
            detail = str(result.get("Message", "")) if isinstance(result, dict) else ""
            raise HotspotError(
                f"停止 Windows 现代移动热点失败：{localized_tethering_status(status)}"
                + (f"\n\n{detail}" if detail else "")
            )

    def get_hotspot_status(self) -> dict[str, Any]:
        """同时读取旧 Hosted Network 与现代 Windows 移动热点真实状态。"""
        code, output = run_netsh(["netsh", "wlan", "show", "hostednetwork"], timeout=15)
        legacy_started = bool(
            re.search(r"status\s*:\s*started", output, re.I)
            or re.search(r"状态\s*:\s*已启动", output)
        )
        ssid_match = re.search(r"SSID\s+name\s*:\s*([^\r\n]+)", output, re.I)
        if not ssid_match:
            ssid_match = re.search(r"SSID\s*(?:名称|名)\s*:\s*([^\r\n]+)", output, re.I)
        channel_match = re.search(
            r"^\s*(?:Channel|信道|频道)\s*:\s*(\d+)\s*$", output, re.I | re.M,
        )
        legacy_channel = int(channel_match.group(1)) if legacy_started and channel_match else 0
        modern = self._get_modern_hotspot_status()
        modern_started = bool(modern.get("started"))
        started = legacy_started or modern_started
        backend_kind = "legacy" if legacy_started else "modern" if modern_started else ""
        saved = load_runtime_state()
        app_adapter = str(saved.get("adapter", "")) if saved.get("platform") in (None, "windows") else ""
        saved_channel = (
            int(saved.get("channel", 0))
            if saved.get("platform") in (None, "windows")
            and str(saved.get("channel", "0")).isdigit()
            else 0
        )
        pending = load_pending_recovery()
        pending_count = len(pending.get("recoveries", [])) if isinstance(pending.get("recoveries"), list) else int(bool(pending))
        if modern_started:
            status_text = "已启动"
        elif legacy_started:
            status_text = "已启动"
        elif modern.get("transitioning"):
            status_text = "正在切换"
        elif modern.get("available"):
            status_text = "未启动（现代热点接口可用）"
        else:
            status_text = "未启动"
        return {
            "started": started,
            "status": status_text,
            "ssid": str(modern.get("ssid", "")) if modern_started else (
                ssid_match.group(1).strip().strip('"“”') if ssid_match else ""
            ),
            "adapter": app_adapter,
            "adapter_confirmed": bool(started and backend_kind == "legacy"),
            "backend": backend_kind,
            "backend_label": (
                "Windows 现代移动热点" if backend_kind == "modern"
                else "Windows 旧式系统热点" if backend_kind == "legacy"
                else "Windows 系统热点"
            ),
            "source": str(modern.get("source", "")) if modern_started else str(saved.get("source_name", "")),
            "band": str(modern.get("band", "")) if modern_started else str(saved.get("band", "")),
            "band_confirmed": bool(modern_started and modern.get("band")),
            "requested_band": str(saved.get("band", "")),
            "channel": legacy_channel or (saved_channel if started else 0),
            "channels": (
                [legacy_channel] if legacy_channel
                else [saved_channel] if started and saved_channel else []
            ),
            "channel_confirmed": bool(legacy_channel),
            "channels_confirmed": bool(legacy_channel),
            "channels_requested": bool(started and saved_channel),
            "authentication": str(modern.get("authentication", "")) if modern_started else "",
            "pending_recovery": bool(pending),
            "pending_recovery_count": pending_count,
            "returncode": 0 if code == 0 or modern.get("available") else code,
            "raw": output,
        }

    def _verify_running_channel(self, requested_channel: int, log: Callable[[str], None]) -> None:
        """读取 Windows 热点实际信道；不再因无法确认或不一致而阻止测试。"""
        if not requested_channel:
            return
        status = self.get_hotspot_status()
        actual_channel = int(status.get("channel", 0) or 0)
        if not status.get("started"):
            raise HotspotError("Windows 启动命令已完成，但系统复核时热点没有保持运行。")
        if not status.get("channel_confirmed") or not actual_channel:
            backend_label = str(status.get("backend_label", "Windows 系统热点"))
            log(
                f"Windows：{backend_label} 已启动；系统无法读取实际发射信道。"
                f"程序已按设定信道 {requested_channel} 请求启动，不再因此自动停止。"
            )
            return
        if actual_channel != requested_channel:
            log(f"Windows：设定信道 {requested_channel}，系统实际回报信道 {actual_channel}；热点继续保留用于测试。")
            return
        log(f"Windows：已确认实际发射信道为 {actual_channel}，与设定值一致。")

    def _find_virtual_adapter(self) -> str:
        script = r"""
$v=Get-NetAdapter -IncludeHidden | Where-Object {
    $_.Status -eq 'Up' -and $_.InterfaceDescription -match '(?i)hosted network|wi-?fi direct|virtual.*wi-?fi'
} | Sort-Object ifIndex -Descending | Select-Object -First 1 -ExpandProperty Name
if($v){$v}
"""
        return run_powershell(script).strip()

    def _get_ics_snapshot(self) -> list[dict[str, Any]]:
        script = r"""
$share=New-Object -ComObject HNetCfg.HNetShare
$rows=@()
foreach($connection in @($share.EnumEveryConnection())) {
    $props=$share.NetConnectionProps.Invoke($connection)
    $cfg=$share.INetSharingConfigurationForINetConnection.Invoke($connection)
    if($cfg.SharingEnabled) {
        $rows += [pscustomobject]@{Name=$props.Name; Type=[int]$cfg.SharingConnectionType}
    }
}
$rows | ConvertTo-Json -Compress
"""
        raw = run_powershell(script, timeout=30)
        if not raw:
            return []
        value: Any = json.loads(raw)
        rows = value if isinstance(value, list) else [value]
        return [
            {"Name": str(row.get("Name", "")), "Type": int(row.get("Type", 0))}
            for row in rows if row.get("Name")
        ]

    def _configure_ics(self, public_name: str, private_name: str) -> None:
        script = f"""
$publicName={_ps_quote(public_name)}
$privateName={_ps_quote(private_name)}
$share=New-Object -ComObject HNetCfg.HNetShare
$public=$null; $private=$null
foreach($connection in @($share.EnumEveryConnection())) {{
    $props=$share.NetConnectionProps.Invoke($connection)
    if($props.Name -eq $publicName) {{$public=$connection}}
    if($props.Name -eq $privateName) {{$private=$connection}}
}}
if(-not $public) {{throw "找不到共享源网卡：$publicName"}}
if(-not $private) {{throw "找不到热点虚拟网卡：$privateName"}}
$publicCfg=$share.INetSharingConfigurationForINetConnection.Invoke($public)
$privateCfg=$share.INetSharingConfigurationForINetConnection.Invoke($private)
foreach($connection in @($share.EnumEveryConnection())) {{
    $cfg=$share.INetSharingConfigurationForINetConnection.Invoke($connection)
    if($cfg.SharingEnabled) {{$cfg.DisableSharing()}}
}}
$publicCfg.EnableSharing(0)
$privateCfg.EnableSharing(1)
"""
        run_powershell(script, timeout=40)

    def _disable_ics(self, names: list[str]) -> None:
        if not names:
            return
        array = "@(" + ",".join(_ps_quote(x) for x in names) + ")"
        script = f"""
$targets={array}
$share=New-Object -ComObject HNetCfg.HNetShare
foreach($connection in @($share.EnumEveryConnection())) {{
    $props=$share.NetConnectionProps.Invoke($connection)
    if($targets -contains $props.Name) {{
        $cfg=$share.INetSharingConfigurationForINetConnection.Invoke($connection)
        if($cfg.SharingEnabled) {{$cfg.DisableSharing()}}
    }}
}}
"""
        run_powershell(script, timeout=30)

    def _restore_ics(self, snapshot: list[dict[str, Any]]) -> None:
        entries = []
        for row in snapshot:
            name = str(row.get("Name", ""))
            if not name:
                continue
            sharing_type = 1 if int(row.get("Type", 0)) == 1 else 0
            entries.append(f"[pscustomobject]@{{Name={_ps_quote(name)};Type={sharing_type}}}")
        saved = "@(" + ",".join(entries) + ")"
        script = f"""
$saved={saved}
$share=New-Object -ComObject HNetCfg.HNetShare
$connections=@($share.EnumEveryConnection())
$targets=@{{}}
foreach($entry in @($saved)) {{
    $target=$null
    foreach($connection in $connections) {{
        $props=$share.NetConnectionProps.Invoke($connection)
        if($props.Name -eq $entry.Name) {{$target=$connection; break}}
    }}
    if(-not $target) {{throw "无法恢复 ICS，找不到接口：$($entry.Name)"}}
    $targets[$entry.Name]=$target
}}
foreach($connection in $connections) {{
    $cfg=$share.INetSharingConfigurationForINetConnection.Invoke($connection)
    if($cfg.SharingEnabled) {{$cfg.DisableSharing()}}
}}
foreach($entry in @($saved | Sort-Object Type)) {{
    $target=$targets[$entry.Name]
    $cfg=$share.INetSharingConfigurationForINetConnection.Invoke($target)
    $cfg.EnableSharing([int]$entry.Type)
}}
"""
        run_powershell(script, timeout=40)

    @staticmethod
    def _pending_states() -> list[dict[str, Any]]:
        pending = load_pending_recovery()
        recoveries = pending.get("recoveries") if isinstance(pending, dict) else None
        if isinstance(recoveries, list):
            return [dict(item) for item in recoveries if isinstance(item, dict)]
        return [dict(pending)] if pending else []

    @staticmethod
    def _save_pending_states(states: list[dict[str, Any]]) -> None:
        states = [state for state in states if state]
        if not states:
            delete_pending_recovery()
        elif len(states) == 1:
            save_pending_recovery(states[0])
        else:
            save_pending_recovery({"platform": "windows", "recoveries": states})

    def _append_pending_recovery(self, state: dict[str, Any]) -> None:
        states = self._pending_states()
        states.append(dict(state))
        self._save_pending_states(states)

    def _restore_saved_settings(self, state: dict[str, Any], log: Callable[[str], None]) -> list[str]:
        """尽可能恢复一份 Windows 状态；成功的项目会立即从该状态中清除。"""
        failures: list[str] = []
        if "ics_snapshot" in state and state.get("ics_snapshot") is not None:
            try:
                self._restore_ics(list(state.get("ics_snapshot", [])))
                log("已恢复热点启动前的 ICS 网络共享配置。")
                state["ics_names"] = []
                state["ics_snapshot"] = None
            except Exception as exc:
                log(f"恢复原 ICS 配置时出现警告：{exc}")
                failures.append(f"ICS：{exc}")
        elif state.get("ics_names"):
            try:
                self._disable_ics(list(state["ics_names"]))
                log("已关闭本程序配置的 ICS 网络共享。")
                state["ics_names"] = []
            except Exception as exc:
                log(f"关闭 ICS 时出现警告：{exc}")
                failures.append(f"ICS：{exc}")

        if state.get("band_setting") and state.get("adapter"):
            try:
                self._restore_band(str(state["adapter"]), dict(state["band_setting"]))
                if state["band_setting"].get("Applied"):
                    log("已恢复热点启动前的网卡频段/无线模式设置。")
                state["band_setting"] = None
            except Exception as exc:
                log(f"恢复网卡频段设置时出现警告：{exc}")
                failures.append(f"频段设置：{exc}")

        if state.get("channel_setting") and state.get("adapter"):
            try:
                self._restore_channel(str(state["adapter"]), dict(state["channel_setting"]))
                if state["channel_setting"].get("Applied"):
                    log("已恢复热点启动前的网卡信道设置。")
                state["channel_setting"] = None
            except Exception as exc:
                log(f"恢复网卡信道设置时出现警告：{exc}")
                failures.append(f"信道设置：{exc}")

        remaining_adapters: list[str] = []
        for name in list(state.get("disabled_adapters", [])):
            try:
                self._enable_adapters([str(name)])
                log(f"已恢复启动热点时临时禁用的无线网卡：{name}")
            except Exception as exc:
                remaining_adapters.append(str(name))
                log(f"恢复临时禁用网卡 {name} 时出现警告：{exc}")
                failures.append(f"无线网卡 {name}：{exc}")
        state["disabled_adapters"] = remaining_adapters

        if "target_was_enabled" in state:
            if state.get("target_was_enabled") is not False:
                state.pop("target_was_enabled", None)
            elif state.get("band_setting") or state.get("channel_setting"):
                message = "等待频段/信道设置恢复后再禁用目标网卡"
                log(message)
                failures.append(f"目标网卡状态：{message}")
            elif state.get("adapter"):
                try:
                    self.set_adapter_enabled(str(state["adapter"]), False)
                    log("已将目标网卡恢复为热点启动前的禁用状态。")
                    state.pop("target_was_enabled", None)
                except Exception as exc:
                    log(f"恢复目标网卡启用状态时出现警告：{exc}")
                    failures.append(f"目标网卡状态：{exc}")
        return failures

    def retry_pending_recovery(self, log: Callable[[str], None]) -> None:
        states = self._pending_states()
        if not states:
            log("没有待恢复的旧网卡设置。")
            return
        status = self.get_hotspot_status()
        if int(status.get("returncode", 1)) != 0:
            raise PendingRecoveryError("无法确认 Windows 热点是否已停止，暂不执行残留恢复。")
        if status.get("started"):
            raise PendingRecoveryError("当前热点仍在运行，请先停止热点，再重试残留恢复。")

        remaining: list[dict[str, Any]] = []
        all_failures: list[str] = []
        for state in states:
            failures = self._restore_saved_settings(state, log)
            if failures:
                remaining.append(state)
                all_failures.extend(failures)
        self._save_pending_states(remaining)
        if all_failures:
            raise PendingRecoveryError(
                "仍有旧网卡设置未恢复；缺失的 USB 网卡重新插入后可再次重试：\n" + "\n".join(all_failures)
            )
        log("残留的旧网卡设置已全部恢复。")

    @_serialized_backend_operation
    def start_hotspot(
        self,
        adapter: WifiAdapter,
        source_name: str,
        ssid: str,
        password: str,
        band: str,
        isolate_adapter: bool,
        log: Callable[[str], None],
        channel: int = 0,
    ) -> None:
        if adapter.status.lower() == "not present":
            raise HotspotError(f"网卡 {adapter.name} 当前为 Not Present，请重新插入或恢复设备后再启动热点。")
        if not source_name:
            raise HotspotError("请选择要共享的 LAN/以太网接口。")
        if not 1 <= len(ssid.encode("utf-8")) <= 32:
            raise HotspotError("Wi-Fi 名称不能为空，且 UTF-8 长度不能超过 32 字节。")
        if not 8 <= len(password) <= 63 or not password.isascii():
            raise HotspotError("密码必须为 8~63 位 ASCII 字符。")
        if channel and channel not in DEFAULT_CHANNELS_BY_BAND.get(band, ()):
            raise HotspotError(f"信道 {channel} 不属于 {band} 的内置常见信道范围。")
        if adapter.hosted_supported is False:
            log(
                "Windows 提示：驱动报告旧式 Hosted Network 不受支持；程序仍会实际尝试，"
                "失败后自动切换到现代移动热点接口。"
            )

        state: dict[str, Any] = {
            "platform": "windows",
            "adapter": adapter.name,
            "source_name": source_name,
            "ssid": ssid,
            "band": band,
            "channel": channel,
            "hotspot_backend": "preparing",
            "target_was_enabled": None,
            "disabled_adapters": [],
            "ics_names": [],
            "ics_snapshot": None,
            "band_setting": None,
            "channel_setting": None,
        }
        # 若上一次运行异常退出，先清理本程序留下的 Hosted Network/ICS 状态。
        try:
            self.stop_hotspot(restore=True, log=log)
        except PendingRecoveryError as exc:
            # 旧 USB 网卡暂时缺失时，把恢复任务留在独立文件中，不阻塞其他网卡测试。
            log(f"Windows：旧设置暂未完全恢复，但不阻塞本次启动：{exc}")
        try:
            # 清理旧状态可能启用了这块网卡，因此此处重新读取，不能依赖界面扫描时的旧值。
            state["target_was_enabled"] = self._adapter_is_enabled(adapter.name)
            # 先记录目标网卡原状态，避免启用网卡后进程异常退出而无法还原。
            save_runtime_state(state)
            log(f"启用目标网卡：{adapter.name}")
            self.set_adapter_enabled(adapter.name, True)

            if isolate_adapter:
                disabled = self._list_other_wifi(adapter.name)
                # 必须在实际禁用前写盘，避免进程恰好中断后不知道需要恢复哪些网卡。
                state["disabled_adapters"] = disabled
                save_runtime_state(state)
                self._disable_wifi_adapters(disabled)
                if disabled:
                    log("已临时禁用其他无线网卡：" + "、".join(disabled))

            adapter_restart_needed = False
            try:
                band_result = self._set_band(adapter.name, band)
                state["band_setting"] = band_result
                save_runtime_state(state)
                if band_result.get("Applied"):
                    log(f"已设置 {band_result.get('Property')} = {band_result.get('Value')}")
                    adapter_restart_needed = True
                else:
                    log("驱动没有可识别的频段属性；热点名称后缀已设置，但实际频段由驱动决定。")
            except Exception as exc:
                # 频段属性是厂商自定义的，设置失败不应阻止基本热点测试。
                state["band_setting"] = {"Applied": False, "Error": str(exc)}
                save_runtime_state(state)
                log(f"设置 {band} 频段时出现警告，将让驱动自行选择：{exc}")

            if channel:
                try:
                    channel_result = self._set_channel(adapter.name, band, channel)
                    state["channel_setting"] = channel_result
                    save_runtime_state(state)
                    if channel_result.get("Applied"):
                        adapter_restart_needed = True
                        log(
                            f"Windows：已向驱动尝试设置目标信道 {channel}（{channel_result.get('Property')} = "
                            f"{channel_result.get('Value')}）；如系统最终改用其他信道，程序不再阻止测试。"
                        )
                    else:
                        log(
                            f"Windows：驱动没有可识别的热点信道属性；仍会尝试启动，"
                            "实际信道由 Windows 和网卡决定。"
                        )
                except Exception as exc:
                    state["channel_setting"] = {"Applied": False, "Error": str(exc)}
                    save_runtime_state(state)
                    log(f"Windows：设置目标信道 {channel} 时出现警告；将改由系统自动协商：{exc}")

            if adapter_restart_needed:
                try:
                    self._restart_adapter(adapter.name)
                except Exception as exc:
                    log(f"重启网卡使频段/信道设置生效时出现警告：{exc}")

            log(f"配置旧式 Windows 热点：{ssid}")
            code, set_output = run_netsh(
                [
                    "netsh", "wlan", "set", "hostednetwork", "mode=allow",
                    f"ssid={ssid}", f"key={password}", "keyUsage=persistent",
                ],
                timeout=20,
            )
            legacy_detail = set_output if code != 0 else ""
            legacy_started = False
            if code == 0:
                code, start_output = run_netsh(["netsh", "wlan", "start", "hostednetwork"], timeout=30)
                legacy_started = code == 0 and self._hosted_is_started()
                if not legacy_started:
                    legacy_detail = start_output or "系统未进入 Started 状态"

            if legacy_started:
                state["hotspot_backend"] = "legacy"
                save_runtime_state(state)
                private_name = self._find_virtual_adapter()
                if not private_name:
                    raise HotspotError("旧式热点已启动，但没有找到它的虚拟网卡，无法配置 LAN 网络共享。")

                log(f"配置 ICS：{source_name} → {private_name}")
                # 先记录待清理对象，即使 ICS 配置到一半失败也能在回滚时尝试恢复。
                state["ics_names"] = [source_name, private_name]
                state["ics_snapshot"] = self._get_ics_snapshot()
                save_runtime_state(state)
                self._configure_ics(source_name, private_name)
                save_runtime_state(state)
                self._verify_running_channel(channel, log)
                channel_text = f"，信道 {channel}" if channel else ""
                log(f"热点已启动：{ssid}（{band}{channel_text}，旧式 Windows 热点）")
            else:
                compact_detail = " ".join(legacy_detail.replace("\r", " ").splitlines()).strip()
                log(
                    "旧式 Windows 热点未能启动，正在自动切换到 Windows 现代移动热点接口。"
                    + (f" 原因：{compact_detail}" if compact_detail else "")
                )
                if isolate_adapter:
                    log(
                        f"现代接口无法直接回报物理发射网卡；当前仅保留目标网卡 {adapter.name} 启用，"
                        "Windows 通常会选择它，但程序会把该绑定标记为‘未确认’。"
                    )
                else:
                    log(
                        "现代接口由 Windows 自动选择无线射频；未启用‘只使用所选网卡’时，"
                        f"不能保证实际使用 {adapter.name}。"
                    )
                # 先写入现代后端标记；若进程在 StartTetheringAsync 后异常退出，下次仍能正确停止。
                state["hotspot_backend"] = "modern"
                state["ics_names"] = []
                state["ics_snapshot"] = None
                save_runtime_state(state)
                result = self._start_modern_hotspot(source_name, ssid, password, band)
                save_runtime_state(state)
                self._verify_running_channel(channel, log)
                log(
                    f"热点已启动：{result.get('Ssid', ssid)}（{band}"
                    f"{f'，信道 {channel}' if channel else ''}，Windows 现代移动热点；"
                    "实际物理网卡由系统选择）"
                )
        except Exception:
            log("Windows：启动失败，正在恢复 ICS、频段设置和临时禁用的网卡。")
            try:
                self.stop_hotspot(restore=True, log=log)
            except Exception as cleanup_exc:
                log(f"Windows：启动失败后的自动恢复未完全成功：{cleanup_exc}")
            raise

    @_serialized_backend_operation
    def stop_hotspot(self, restore: bool, log: Callable[[str], None]) -> None:
        state = load_runtime_state()
        owns_state = state.get("platform") in (None, "windows")
        if not owns_state:
            # 不要让 Windows 后端误删 Linux NetworkManager 的运行状态。
            state = {}
        # 只停止本程序留下记录的热点。若系统里已有用户手工启动的移动
        # 热点/Hosted Network，而本程序没有运行状态记录，不能为了刷新或
        # 启动另一块网卡把它误关掉。
        app_owned = bool(
            owns_state
            and (
                state.get("adapter")
                or state.get("hotspot_backend") in {"legacy", "modern", "preparing"}
            )
        )
        modern_before = self._get_modern_hotspot_status()
        legacy_before = self._hosted_is_started()
        if (modern_before.get("started") or modern_before.get("transitioning") or legacy_before) and not app_owned:
            raise HotspotError(
                "检测到系统中已有热点，但没有本程序的运行记录；为避免误关闭其他程序/手工热点，"
                "本次操作未停止它。请先在系统网络设置中关闭该热点，再重试。"
            )
        if not app_owned and not (
            modern_before.get("started")
            or modern_before.get("transitioning")
            or legacy_before
        ):
            # 首次启动或普通刷新时，系统没有本程序热点，也没有外部热点。
            # 不再执行“停止 Hosted Network”命令；某些 Windows 版本会把
            # “本来就没启动”返回成错误码，从而阻断后续热点启动。
            if restore and load_pending_recovery():
                self.retry_pending_recovery(log)
            return
        modern_error: Exception | None = None
        if modern_before.get("started") or modern_before.get("transitioning"):
            try:
                self._stop_modern_hotspot(str(state.get("source_name", "")))
                log("已停止 Windows 现代移动热点。")
            except Exception as exc:
                modern_error = exc

        stop_code, output = run_netsh(["netsh", "wlan", "stop", "hostednetwork"], timeout=20)
        if output:
            log(output.replace("\r", " ").replace("\n", " "))
        status = self.get_hotspot_status()
        if status.get("started"):
            raise HotspotError("Windows 报告热点仍在运行；为避免丢失恢复信息，已保留运行状态记录。")
        if modern_error:
            log(f"停止现代热点命令返回警告，但系统已确认热点关闭：{modern_error}")
        if stop_code != 0 and int(status.get("returncode", 1)) != 0 and not modern_before.get("available"):
            raise HotspotError(output or "无法确认 Windows 热点已经停止；已保留运行状态记录。")
        if not restore:
            return

        failures = self._restore_saved_settings(state, log) if owns_state and state else []
        if owns_state:
            if failures:
                self._append_pending_recovery(state)
            delete_runtime_state()
        if failures:
            raise PendingRecoveryError(
                "热点已停止，但部分系统设置暂未恢复；不影响改用其他网卡启动：\n" + "\n".join(failures)
            )

        # 停止热点后顺便重试以前因 USB 网卡缺失而留下的恢复任务。
        if load_pending_recovery():
            self.retry_pending_recovery(log)

    @_serialized_backend_operation
    def stop_hotspots(self, adapters: list[WifiAdapter], restore: bool, log: Callable[[str], None]) -> None:
        self.stop_hotspot(restore=restore, log=log)

    def start_hotspots(self, adapters: list[WifiAdapter], *args: Any, **kwargs: Any) -> None:
        if len(adapters) != 1:
            raise HotspotError("Windows 系统热点只能同时运行一个实例，请每次只选择一块网卡。")
        self.start_hotspot(adapters[0], *args, **kwargs)


class LinuxHotspotBackend:
    """Linux NetworkManager 后端。

    使用 nmcli 的 hotspot profile 创建 AP；NetworkManager 的 ipv4.method=shared
    提供 DHCP/NAT。多块网卡是否能同时 AP 取决于驱动是否报告 AP mode。
    """

    def __init__(self) -> None:
        self._operation_lock = threading.RLock()
        # 旧版本曾记录监管域处理状态；保留字段名用于兼容测试和运行对象。
        self._regulatory_elevation_attempted = False
        self._regulatory_cn_seen = False

    def _run(self, args: list[str], timeout: int = 30) -> tuple[int, str]:
        env = os.environ.copy()
        env.update({"LC_ALL": "C", "LANG": "C"})
        try:
            return run_process(args, timeout=timeout, env=env)
        except subprocess.TimeoutExpired as exc:
            raw_output = exc.stdout or exc.output or b""
            if isinstance(raw_output, bytes):
                detail = _decode_output(raw_output).strip()
            else:
                detail = str(raw_output).strip()
            suffix = f"\n命令最后输出：{detail}" if detail else ""
            raise HotspotError(
                f"Linux 命令等待超过 {timeout} 秒：{args[0]} {args[1] if len(args) > 1 else ''}。"
                f"{suffix}"
            ) from None

    def _cmd(self, args: list[str], timeout: int = 30) -> str:
        code, output = self._run(args, timeout=timeout)
        if code != 0:
            command_label = " ".join(args[:4])
            raise HotspotError(output or f"命令执行失败：{command_label}")
        return output

    def _require_nmcli(self) -> None:
        if not shutil.which("nmcli"):
            raise HotspotError("Linux 后端需要 NetworkManager/nmcli，请先安装并启动 NetworkManager。")

    @staticmethod
    def _regulatory_domain_is_cn(output: str) -> bool:
        """兼容全局和 self-managed wiphy 输出，只要明确出现 CN 即视为已设置。"""
        return bool(re.search(rf"^\s*country\s+{REGULATORY_COUNTRY}:", output, re.I | re.M))

    def _ensure_cn_regulatory_domain(
        self, log: Callable[[str], None] | None = None, allow_elevation: bool = False,
    ) -> bool:
        """保留兼容入口；当前版本不主动设置或校验 Linux 国家码。"""
        if log:
            log("Linux：已跳过国家码设置/校验；5G 会优先请求 36/40/44/48，失败后再自动协商。")
        return True

    def _prepare_ap_device(self, adapter_name: str, log: Callable[[str], None]) -> None:
        """清理目标网卡残留连接状态，降低热点停止后立刻重启的 supplicant 超时概率。"""
        self._run(["nmcli", "device", "set", adapter_name, "managed", "yes"], timeout=20)
        code, output = self._run(["nmcli", "device", "disconnect", adapter_name], timeout=25)
        if code == 0:
            log(f"Linux：已清理 {adapter_name} 的旧连接状态，准备重新进入 AP 模式。")
        elif output and not re.search(r"not active|not connected|disconnected", output, re.I):
            log(f"Linux：清理 {adapter_name} 连接状态时收到提示：{output.strip()}")
        state_text = self._wait_device_leaves_transition(adapter_name, timeout=8.0)
        if any(token in state_text for token in ("prepare", "config", "ip-config", "deactivating")):
            log(
                f"Linux：{adapter_name} 仍处于过渡状态（{state_text or '未知'}），"
                "正在软释放网卡后再启动热点。"
            )
            self._soft_release_device(adapter_name)
            self._wait_device_leaves_transition(adapter_name, timeout=15.0)

    def _wait_device_leaves_transition(self, adapter_name: str, timeout: float = 8.0) -> str:
        """等待 NetworkManager/wpa_supplicant 释放接口，返回最后读取到的状态文本。"""
        last_state = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state_code, state_output = self._run(
                ["nmcli", "-g", "GENERAL.STATE", "device", "show", adapter_name], timeout=10,
            )
            state_text = state_output.strip().lower()
            last_state = state_text
            if state_code != 0 or not any(
                token in state_text for token in ("prepare", "config", "ip-config", "deactivating")
            ):
                break
            time.sleep(0.4)
        return last_state

    def _soft_release_device(self, adapter_name: str) -> None:
        """只释放目标网卡，不碰其他 AP；用于停止/重启后清理 MANAGED/configuring 残留。"""
        self._run(["nmcli", "device", "disconnect", adapter_name], timeout=25)
        self._run(["nmcli", "device", "set", adapter_name, "managed", "no"], timeout=20)
        time.sleep(0.8)
        self._run(["nmcli", "device", "set", adapter_name, "managed", "yes"], timeout=20)

    def _reset_ap_device_for_retry(
        self, adapter_name: str, profile: str, log: Callable[[str], None],
    ) -> None:
        """仅软复位目标无线接口，处理刚停热点后 supplicant/NM 还没释放干净的情况。"""
        log(
            f"Linux：{adapter_name} 进入 AP 模式超时；正在只对这块网卡做一次软复位，"
            "不会主动停止其他网卡热点。"
        )
        self._run(["nmcli", "connection", "down", "id", profile], timeout=20)
        self._run(["nmcli", "device", "disconnect", adapter_name], timeout=25)
        self._run(["nmcli", "device", "set", adapter_name, "managed", "no"], timeout=20)
        time.sleep(1.0)
        self._run(["nmcli", "device", "set", adapter_name, "managed", "yes"], timeout=20)

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            state_code, state_output = self._run(
                ["nmcli", "-g", "GENERAL.STATE", "device", "show", adapter_name], timeout=10,
            )
            state_text = state_output.strip().lower()
            if state_code != 0:
                break
            # 10=unmanaged，20=unavailable。等它回到 disconnected/available 后再重试 AP。
            if not re.match(r"^(10|20)\b", state_text):
                break
            time.sleep(0.5)
        self._prepare_ap_device(adapter_name, log)

    def _activation_failure_message(
        self, adapter: WifiAdapter, band: str, channel: int, detail: str,
    ) -> str:
        """把 NetworkManager 的通用 802.1X 超时翻译为热点/AP 场景的明确诊断。"""
        if "802.1X supplicant took too long" not in detail:
            return detail
        usable = tuple(adapter.channels_by_band.get(band, ()))
        channel_text = f"{band} 信道 {channel}" if channel else f"{band} 自动信道"
        lines = [
            f"{adapter.name} 无法在 {channel_text} 进入 AP 发射模式。",
            "这一步是 NetworkManager 启动 AP 本身失败，热点还没有真正创建成功；"
            "自动信道模式只能保留已经启动成功的热点，不能把启动失败的接口强行变成 AP。",
            "NetworkManager 显示的 ‘802.1X supplicant’ 是底层通用超时名称；"
            "本热点仍配置为 WPA2-个人版（AES），不是企业 802.1X 认证。",
            "程序没有强制校验或设置国家码，也没有指定具体信道；信道由系统和网卡自动协商。",
        ]
        if channel and adapter.channel_info_available and channel not in usable:
            lines.append(
                f"驱动当前没有把信道 {channel} 报告为可主动发射；常见原因是"
                "当前驱动/固件不支持该信道的 AP 模式，或网卡复位后仍未恢复。"
            )
        else:
            lines.append(
                "程序已清理该网卡的旧连接状态并自动重试，仍失败；"
                "常见原因是驱动/固件不能在该信道建立 AP，或网卡复位尚未恢复。"
            )
        hint = re.search(r"Hint:\s*(.+)", detail, re.I | re.S)
        if hint:
            lines.append("系统建议的详细日志命令：" + " ".join(hint.group(1).split()))
        return "\n\n".join(lines)

    def list_wifi_adapters(self) -> list[WifiAdapter]:
        self._require_nmcli()
        raw = self._cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
        rows: list[WifiAdapter] = []
        for line in raw.splitlines():
            parts = line.split(":")
            if len(parts) < 3 or parts[1] != "wifi":
                continue
            name, state = parts[0], parts[2]
            if not name:
                continue
            hosted, bands, channels_by_band, channel_info_available = self._probe_iw(name)
            rows.append(WifiAdapter(
                len(rows) + 1, name, name, state, len(rows) + 1, "", hosted, bands,
                channels_by_band, channel_info_available,
            ))
        return rows

    def _probe_iw(
        self, name: str,
    ) -> tuple[bool | None, tuple[str, ...], dict[str, tuple[int, ...]], bool]:
        if not shutil.which("iw"):
            return None, (), {}, False
        code, output = self._run(["iw", "dev", name, "info"], timeout=10)
        if code != 0:
            return None, (), {}, False
        wiphy_match = re.search(r"\bwiphy\s+(\d+)", output)
        phy_args = ["iw", "phy", f"phy{wiphy_match.group(1)}", "info"] if wiphy_match else ["iw", "list"]
        phy_code, phy = self._run(phy_args, timeout=15)
        if phy_code != 0:
            return None, (), {}, False
        hosted = bool(re.search(r"Supported interface modes:.*?\* AP", phy, re.S)) if phy else None
        bands: list[str] = []
        frequencies: list[int] = []
        usable_channels: dict[str, list[int]] = {"2.4G": [], "5G": []}
        hardware_channels: dict[str, list[int]] = {"2.4G": [], "5G": []}
        for line in phy.splitlines():
            match = re.search(r"\b(\d{4})\s+MHz\s+\[(\d+)\]", line)
            if match:
                frequency = int(match.group(1))
                channel = int(match.group(2))
                frequencies.append(frequency)
                band = "2.4G" if 2400 <= frequency <= 2500 else "5G" if 4900 <= frequency <= 5900 else ""
                if not band or channel not in DEFAULT_CHANNELS_BY_BAND[band]:
                    continue
                # 这里保留驱动报告供诊断；界面分配不使用此结果做启动前拦截。
                if "disabled" in line.lower():
                    continue
                hardware_channels[band].append(channel)
                if not re.search(r"\bno[ -]?IR\b", line, re.I):
                    usable_channels[band].append(channel)
        if any(2400 <= frequency <= 2500 for frequency in frequencies):
            bands.append("2.4G")
        if any(4900 <= frequency <= 5900 for frequency in frequencies):
            bands.append("5G")
        channels_by_band: dict[str, tuple[int, ...]] = {}
        for band in ("2.4G", "5G"):
            # 这里只保存驱动当前报告可主动发射的信道，供诊断/兼容测试参考；
            # 图形界面启动热点时不再指定具体信道，也不设置或复核国家码。
            channels_by_band[band] = tuple(sorted(set(usable_channels[band])))
        return hosted, tuple(bands), channels_by_band, True

    def list_share_sources(self) -> list[str]:
        self._require_nmcli()
        raw = self._cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
        result: list[str] = []
        for line in raw.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] in {"ethernet", "bridge"} and parts[2] in {"connected", "connected (externally)"}:
                result.append(parts[0])
        return result

    @_serialized_backend_operation
    def set_adapter_enabled(self, name: str, enabled: bool) -> str:
        self._require_nmcli()
        managed = "yes" if enabled else "no"
        self._cmd(["nmcli", "device", "set", name, "managed", managed], timeout=40)
        status = self._cmd(["nmcli", "-g", "GENERAL.STATE", "device", "show", name], timeout=20)
        return status or ("managed" if enabled else "unmanaged")

    def _client_profile_name(self, adapter: WifiAdapter) -> str:
        return f"GMY-CLIENT-{adapter.name}"

    def _connection_interface_name(self, profile: str) -> str:
        """读取连接配置绑定的接口名；空值表示未绑定或配置不存在。"""
        if not profile:
            return ""
        code, output = self._run(
            [
                "nmcli", "-g", "connection.interface-name",
                "connection", "show", "id", profile,
            ],
            timeout=12,
        )
        return output.strip() if code == 0 else ""

    def _safe_client_profile_for_adapter(
        self, adapter: WifiAdapter, log: Callable[[str], None],
    ) -> str:
        """避免历史同名 profile 绑定到另一块网卡时误伤其它连接。

        旧版本固定使用 ``GMY-CLIENT-<接口>``。如果用户曾手工复制/修改
        该 profile，使它实际绑定到 ens33 或另一块 WLAN，直接 down/delete
        会产生“连接一块网卡，另一块也掉线”的假象。此时保留旧配置，
        为当前接口使用独立 profile。
        """
        preferred = self._client_profile_name(adapter)
        candidates = [preferred, f"{preferred}-{adapter.index}", f"{preferred}-safe"]
        for candidate in candidates:
            bound_to = self._connection_interface_name(candidate)
            if not bound_to or bound_to == adapter.name:
                if candidate != preferred:
                    log(
                        f"Linux：发现旧客户端配置 {preferred} 绑定到其它接口；"
                        f"本次使用独立配置 {candidate} 连接 {adapter.name}。"
                    )
                return candidate
        # 极端情况下多个历史配置都绑定到其它接口；使用一个不会覆盖旧配置的
        # 新名称，随后由当前接口专用的 profile 管理这次连接。
        alternate = f"{preferred}-{adapter.index}-new"
        log(
            f"Linux：多个旧客户端配置均绑定到其它接口；"
            f"本次使用新配置 {alternate}，不会断开已有连接。"
        )
        return alternate

    def _restore_protected_client_connections(
        self, protected: dict[str, str], log: Callable[[str], None],
    ) -> None:
        """连接目标网卡后，只恢复被驱动/NM 连带断开的其它无线网卡。"""
        if not protected:
            return
        try:
            active_after = self._linux_active_wifi_connection_map()
        except HotspotError as exc:
            log(f"Linux：连接目标网卡后无法复核其它网卡状态：{exc}")
            return
        for adapter_name, profile in protected.items():
            if active_after.get(adapter_name) == profile:
                continue
            log(
                f"Linux 警告：连接其它网卡时检测到 {adapter_name} 的连接"
                f"“{profile}”不再活动，正在仅恢复该网卡。"
            )
            code, output = self._run(
                ["nmcli", "connection", "up", "id", profile, "ifname", adapter_name],
                timeout=60,
            )
            if code == 0:
                log(f"Linux：已恢复 {adapter_name} 的原 WiFi 连接：{profile}")
            else:
                log(
                    f"Linux：恢复 {adapter_name} 的 WiFi 连接失败："
                    f"{output.strip() or '未提供原因'}"
                )

    def _scan_wifi_ssid(self, adapter_name: str, ssid: str, log: Callable[[str], None]) -> bool:
        """只读取现有扫描缓存，避免主动扫描打断正在运行的无线连接。"""
        code, output = self._run(
            [
                "nmcli", "-t", "--escape", "no", "-f", "SSID",
                "device", "wifi", "list", "ifname", adapter_name, "--rescan", "no",
            ],
            timeout=12,
        )
        if code == 0 and ssid in {line.strip() for line in output.splitlines() if line.strip()}:
            return True
        log(
            f"Linux：{adapter_name} 当前扫描缓存未看到 SSID：{ssid}；"
            "为避免扫描打断其它连接，不主动 rescan，仍直接提交连接请求。"
        )
        return False

    def _scan_wifi_bssid(self, adapter_name: str, ssid: str) -> str:
        """从最近一次扫描中选择目标 SSID 信号最强的 BSSID。

        同一个 SSID 可能由多个 AP/BSSID 广播；只把 SSID 交给 NetworkManager
        时，它可能自动选到一个认证失败或信号较弱的节点。连接测试场景下，
        绑定当前网卡扫描到的最佳 BSSID 更稳定；读取失败则返回空字符串，
        仍保留 NetworkManager 的自动选择能力。
        """
        code, output = self._run(
            [
                "nmcli", "-t", "--escape", "no", "-f", "BSSID,SSID,SIGNAL",
                "device", "wifi", "list", "ifname", adapter_name, "--rescan", "no",
            ],
            timeout=15,
        )
        if code != 0:
            return ""
        best_bssid = ""
        best_signal = -1
        mac_pattern = r"^((?:[0-9a-f]{2}:){5}[0-9a-f]{2}):(.*):(\d+)\s*$"
        for line in output.splitlines():
            match = re.match(mac_pattern, line.strip(), re.I)
            if not match:
                continue
            bssid, row_ssid, signal_text = match.groups()
            if row_ssid.strip() != ssid:
                continue
            try:
                signal = int(signal_text)
            except ValueError:
                signal = 0
            if signal > best_signal:
                best_bssid = bssid.upper()
                best_signal = signal
        return best_bssid

    def _client_needs_ap_cleanup(self, adapter_name: str) -> bool:
        """只有接口仍处于 AP/本程序热点 profile 时才做清理，避免正常客户端连接被复位。"""
        try:
            mode = self._interface_mode(adapter_name).strip().lower()
        except HotspotError:
            mode = ""
        if mode == "ap":
            return True
        code, output = self._run(
            ["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", adapter_name],
            timeout=8,
        )
        return code == 0 and "GMY-AP-" in output

    def _wait_client_connected(
        self, adapter_name: str, ssid: str, timeout: float = 25.0,
    ) -> tuple[bool, str]:
        """等待 NetworkManager 真正进入 connected/activated，而不是只看命令退出码。"""
        deadline = time.monotonic() + timeout
        last_state = ""
        while time.monotonic() < deadline:
            code, output = self._run(
                [
                    "nmcli", "-g", "GENERAL.STATE,GENERAL.CONNECTION",
                    "device", "show", adapter_name,
                ],
                timeout=8,
            )
            if code == 0:
                lines = [line.strip() for line in output.splitlines()]
                state = lines[0] if lines else ""
                connection = lines[1] if len(lines) > 1 else ""
                last_state = state or last_state
                active = (
                    re.match(r"^100\b", state)
                    or state.lower() in {"connected", "connected (externally)"}
                )
                if active and connection not in {"", "--"}:
                    profile_ssid = self._wifi_profile_ssid(connection)
                    if not profile_ssid or profile_ssid == ssid:
                        return True, f"{state}｜{connection}"
            time.sleep(1.0)
        return False, last_state or "未读取"

    def _wait_client_device_ready(
        self, adapter_name: str, timeout: float = 15.0,
    ) -> tuple[bool, str]:
        """等待网卡回到可被 NetworkManager 使用的状态；20=暂不可用时不能立即下连接命令。"""
        deadline = time.monotonic() + timeout
        last_state = ""
        while time.monotonic() < deadline:
            code, output = self._run(
                ["nmcli", "-g", "GENERAL.STATE", "device", "show", adapter_name],
                timeout=8,
            )
            if code != 0:
                last_state = output.strip() or last_state
                time.sleep(1.0)
                continue
            state = output.strip()
            last_state = state or last_state
            if not re.match(r"^(10|20)\b", state.lower()):
                return True, state
            time.sleep(1.0)
        return False, last_state or "未读取"

    def _activate_wifi_client_profile(
        self, adapter: WifiAdapter, profile: str, ssid: str, password: str, hidden: bool,
        bssid: str = "",
    ) -> None:
        """优先用 nmcli device wifi connect；失败时回退到手动 profile。"""
        connect_args = [
            "nmcli", "device", "wifi", "connect", ssid,
            "ifname", adapter.name,
            "name", profile,
        ]
        if password:
            connect_args[5:5] = ["password", password]
        if hidden:
            connect_args.extend(["hidden", "yes"])
        if bssid:
            connect_args.extend(["bssid", bssid])
        try:
            self._cmd(connect_args, timeout=70)
            self._cmd([
                "nmcli", "connection", "modify", profile,
                "connection.interface-name", adapter.name,
                "connection.autoconnect", "no",
                "ipv4.method", "auto",
                "ipv6.method", "ignore",
            ], timeout=30)
            return
        except HotspotError as first_exc:
            # 只删除确认属于当前目标网卡的 profile。即使旧 profile 在
            # 连接过程中被 NetworkManager 错误地绑定到其它接口，也不能
            # 因为一次重试把其它网卡的连接配置删掉。
            profile_interface = self._connection_interface_name(profile)
            if not profile_interface or profile_interface == adapter.name:
                self._run(["nmcli", "connection", "delete", "id", profile], timeout=20)
            # 第一次激活失败时，NetworkManager 可能仍把接口停在
            # configuring/deactivating。只释放当前网卡，避免影响其它客户端/AP。
            detail = str(first_exc)
            self._run(["nmcli", "device", "disconnect", adapter.name], timeout=25)
            self._wait_device_leaves_transition(adapter.name, timeout=8.0)
            if re.search(
                r"802\.1X|supplicant|activation failed|timeout|not available|"
                r"认证|激活失败|超时",
                detail,
                re.I,
            ):
                self._soft_release_device(adapter.name)
                self._wait_client_device_ready(adapter.name, timeout=15.0)

        self._cmd([
            "nmcli", "connection", "add", "type", "wifi", "ifname", adapter.name,
            "con-name", profile, "autoconnect", "no", "ssid", ssid,
        ], timeout=30)
        modify_args = [
            "nmcli", "connection", "modify", profile,
            "802-11-wireless.mode", "infrastructure",
            "ipv4.method", "auto", "ipv6.method", "ignore",
            "connection.interface-name", adapter.name,
            "connection.autoconnect", "no",
        ]
        if password:
            modify_args.extend([
                "802-11-wireless-security.key-mgmt", "wpa-psk",
                "802-11-wireless-security.psk", password,
            ])
        if hidden:
            modify_args.extend(["802-11-wireless.hidden", "yes"])
        if bssid:
            modify_args.extend(["802-11-wireless.bssid", bssid])
        self._cmd(modify_args, timeout=30)
        self._cmd(["nmcli", "connection", "up", "id", profile, "ifname", adapter.name], timeout=60)

    @_serialized_backend_operation
    def connect_wifi_adapters(
        self, adapters: list[WifiAdapter], ssid: str, password: str,
        log: Callable[[str], None], retry_failed: bool = True,
    ) -> dict[str, str]:
        self._require_nmcli()
        if not adapters:
            raise HotspotError("请选择至少一块无线网卡。")
        if not 1 <= len(ssid.encode("utf-8")) <= 32:
            raise HotspotError("Wi-Fi 名称不能为空，且 UTF-8 长度不能超过 32 字节。")
        if len(password) > 63:
            raise HotspotError("Wi-Fi 密码长度不能超过 63 个字符。")
        results: dict[str, str] = {}
        failures: list[str] = []
        target_names = {adapter.name for adapter in adapters}
        # 在任何目标网卡切换前记录其它无线网卡的活动连接。某些 USB
        # 驱动/NetworkManager 组合在扫描或切换模式时会短暂连带断开它们，
        # 结束后只恢复确实受影响的接口，不碰有线 ens33/docker0。
        try:
            active_before = self._linux_active_wifi_connection_map()
        except HotspotError:
            active_before = {}
        protected_connections = {
            adapter_name: profile
            for adapter_name, profile in active_before.items()
            if adapter_name not in target_names and profile not in {"", "--"}
        }
        for adapter in adapters:
            profile = self._safe_client_profile_for_adapter(adapter, log)
            log(f"Linux：正在让 {adapter.name} 连接 WiFi：{ssid}")
            try:
                # 只有配置明确属于目标接口，或尚未绑定任何接口时才清理；
                # 不再按名称直接删除可能属于其它网卡/有线接口的 profile。
                profile_interface = self._connection_interface_name(profile)
                if not profile_interface or profile_interface == adapter.name:
                    self._run(
                        ["nmcli", "connection", "down", "id", profile, "ifname", adapter.name],
                        timeout=20,
                    )
                    self._run(["nmcli", "connection", "delete", "id", profile], timeout=20)
                else:
                    log(
                        f"Linux：跳过清理 {profile}（它绑定到 {profile_interface}，"
                        f"不是目标网卡 {adapter.name}）。"
                    )
                self._cmd(["nmcli", "device", "set", adapter.name, "managed", "yes"], timeout=20)
                if self._client_needs_ap_cleanup(adapter.name):
                    log(f"Linux：{adapter.name} 仍处于 AP/热点残留状态，先清理残留再连接客户端。")
                    self._run(["nmcli", "device", "disconnect", adapter.name], timeout=25)
                    self._wait_device_leaves_transition(adapter.name, timeout=8.0)
                ready, ready_state = self._wait_client_device_ready(adapter.name, timeout=15.0)
                if not ready:
                    log(
                        f"Linux：{adapter.name} 当前状态为 {ready_state or '未知'}，"
                        "仍继续把连接请求交给 NetworkManager。"
                    )
                visible = self._scan_wifi_ssid(adapter.name, ssid, log)
                # 扫描缓存可能滞后或被位置/驱动策略限制；即使未看到 SSID，
                # 也继续交给 NetworkManager 尝试，不把扫描结果当成硬门槛。
                # 不把某个扫描到的 BSSID 写死，避免同名 AP 漫游、缓存过期或
                # 某个节点拒绝认证时阻塞连接；由 NetworkManager 自行选择可用节点。
                bssid = ""
                try:
                    self._activate_wifi_client_profile(
                        # 目标 SSID 是用户明确输入的普通广播名称。扫描缓存
                        # 暂时没有它时仍按普通网络连接；把它错误标成 hidden
                        # 会让 NetworkManager 走另一套扫描/认证路径，反而
                        # 比手动点击连接更容易失败。
                        adapter, profile, ssid, password, hidden=False, bssid=bssid,
                    )
                except HotspotError as exc:
                    detail = str(exc)
                    if "Wi-Fi network could not be found" in detail:
                        raise HotspotError(
                            f"{adapter.name} 连接请求已提交，但 NetworkManager 当前找不到 WiFi：{ssid}。\n"
                            "请确认热点仍在广播、网卡频段兼容、距离和信号正常；"
                            "程序不会因为扫描缓存缺失提前阻止连接。"
                        ) from None
                    if (
                        "No suitable device found" in detail
                        or "mismatching interface name" in detail
                        or re.search(r"device .+ not available", detail, re.I)
                    ):
                        raise HotspotError(
                            f"{adapter.name} 没有被 NetworkManager 绑定到本次 WiFi 连接。\n"
                            "通常是旧连接配置绑定了错误的网卡（例如误匹配到有线网卡），"
                            "程序已清理本程序自己的连接配置；请再次点击连接，或先断开该网卡的旧连接。"
                        ) from None
                    if re.search(
                        r"802\.1X supplicant|supplicant|authentication|authenticate|"
                        r"Connection activation failed",
                        detail,
                        re.I,
                    ):
                        raise HotspotError(
                            f"{adapter.name} WiFi 密码认证或连接激活超时。\n"
                            "这不是企业 802.1X 配置；NetworkManager 使用了通用的 supplicant 错误文案。"
                            f"\n目标热点：{ssid}"
                            f"{f'（已尝试 BSSID：{bssid}）' if bssid else ''}\n"
                            "请确认密码正确、热点允许新设备接入，并先关闭该网卡上残留的其它 WiFi/AP 连接。"
                        ) from None
                    raise
                connected, state = self._wait_client_connected(adapter.name, ssid, timeout=25.0)
                if not connected:
                    log(
                        f"Linux：{adapter.name} 连接命令已提交，但暂未读取到最终状态："
                        f"{state or '未读取'}；保留连接请求并继续后台检查。"
                    )
                results[adapter.name] = (
                    state or "已确认连接"
                    if connected
                    else "连接请求已提交，等待系统确认"
                )
                if connected:
                    log(f"Linux：{adapter.name} 已确认连接到 {ssid}（{state}）。")
            except HotspotError as exc:
                failures.append(f"{adapter.name}: {exc}")
                log(f"Linux：{adapter.name} 连接失败：{exc}")
                continue
        self._restore_protected_client_connections(protected_connections, log)
        if failures and retry_failed:
            failed_names = {
                item.split(":", 1)[0].strip()
                for item in failures
                if ":" in item
            }
            retry_adapters = [adapter for adapter in adapters if adapter.name in failed_names]
            if retry_adapters:
                log(
                    "Linux：第一轮连接已完成；将只对未连接网卡再重试一轮："
                    + "、".join(adapter.name for adapter in retry_adapters)
                )
                try:
                    retry_results = self.connect_wifi_adapters(
                        retry_adapters, ssid, password, log, retry_failed=False,
                    )
                except HotspotError as retry_exc:
                    prefix = "部分无线网卡连接失败" if results else "无线网卡连接失败"
                    raise HotspotError(
                        prefix + "（已完成一次重试）：\n" + str(retry_exc)
                    ) from None
                results.update(retry_results)
                failures = []
        if failures:
            prefix = "部分无线网卡连接失败" if results else "无线网卡连接失败"
            raise HotspotError(prefix + "：\n" + "\n\n".join(failures))
        return results

    @_serialized_backend_operation
    def disconnect_wifi_adapters(
        self, adapters: list[WifiAdapter], log: Callable[[str], None],
    ) -> dict[str, str]:
        self._require_nmcli()
        if not adapters:
            raise HotspotError("请选择至少一块无线网卡。")
        target_names = {adapter.name for adapter in adapters}
        # 断开前记录其它网卡正在使用的连接。正常情况下这些连接完全不应
        # 被本次操作碰到；如果某些驱动/NM 状态切换造成连带掉线，下面会
        # 只按原网卡和原 profile 尝试恢复，避免用户误以为“停一块全掉”。
        try:
            active_before = self._linux_active_wifi_connection_map()
        except HotspotError:
            active_before = {}
        protected_connections = {
            adapter_name: profile
            for adapter_name, profile in active_before.items()
            if adapter_name not in target_names and profile not in {"", "--"}
        }
        results: dict[str, str] = {}
        for adapter in adapters:
            # 连接时如果发现同名旧 profile 绑定到了别的接口，程序会为当前
            # 网卡生成带后缀的安全 profile（例如 GMY-CLIENT-wlan0-1）。
            # 断开时不能只查固定名称，否则虽然网卡断开了，旧 profile 会残留，
            # 下次连接又可能被 NetworkManager 误选中。
            canonical_profile = self._client_profile_name(adapter)
            profile = canonical_profile
            log(f"Linux：正在断开 {adapter.name} 的 WiFi 客户端连接。")
            active_profile = active_before.get(adapter.name, "")
            if active_profile.startswith(canonical_profile) and active_profile != canonical_profile:
                profile = active_profile
            profile_interface = ""
            profile_code, profile_output = self._run(
                ["nmcli", "-g", "connection.interface-name", "connection", "show", "id", profile],
                timeout=15,
            )
            if profile_code == 0:
                profile_interface = profile_output.strip()
            # 查询不到绑定接口时不把它当作匹配；宁可留下旧 profile，
            # 也不能在名称冲突/状态异常时误删其它网卡的连接配置。
            profile_matches_adapter = profile_interface == adapter.name

            down_code = 0
            down_output = ""
            # 只有 profile 确实属于目标网卡时才执行 down/delete，避免名称
            # 冲突或历史残留 profile 被误操作到其它设备。
            if profile_matches_adapter and active_profile == profile:
                down_code, down_output = self._run(
                    ["nmcli", "connection", "down", "id", profile, "ifname", adapter.name],
                    timeout=25,
                )
            elif active_profile and active_profile != profile:
                log(
                    f"Linux：{adapter.name} 当前使用的是“{active_profile}”，"
                    "不会删除其它 profile，只断开这块目标网卡。"
                )

            # 目标网卡仍有活动连接、profile 状态尚未同步，或 down 失败时，
            # 才执行按接口限定的 device disconnect；绝不使用全局 radio off。
            if active_profile != profile or down_code != 0:
                self._run(
                    ["nmcli", "device", "disconnect", "ifname", adapter.name],
                    timeout=25,
                )

            if profile_matches_adapter:
                self._run(["nmcli", "connection", "delete", "id", profile], timeout=25)
            result_text = "已断开（仅目标网卡）"
            if down_output and down_code != 0:
                result_text += f"｜提示：{down_output.strip()}"
            results[adapter.name] = result_text
            log(f"Linux：{adapter.name} 已断开；未主动操作其它无线网卡。")

        # 复核并恢复被连带影响的其它客户端连接。恢复使用 NetworkManager
        # 已保存的 profile，不需要重新索要密码。
        if protected_connections:
            try:
                active_after = self._linux_active_wifi_connection_map()
            except HotspotError:
                active_after = {}
            for adapter_name, profile in protected_connections.items():
                if active_after.get(adapter_name) == profile:
                    continue
                log(
                    f"Linux 警告：断开目标网卡时检测到 {adapter_name} 的连接"
                    f"“{profile}”也不再活动，正在仅恢复该网卡。"
                )
                restore_code, restore_output = self._run(
                    ["nmcli", "connection", "up", "id", profile, "ifname", adapter_name],
                    timeout=60,
                )
                if restore_code == 0:
                    log(f"Linux：已恢复 {adapter_name} 的原 WiFi 连接：{profile}")
                else:
                    log(
                        f"Linux：恢复 {adapter_name} 的 WiFi 连接失败："
                        f"{restore_output.strip() or '未提供原因'}"
                    )
        return results

    def _linux_device_status_map(self) -> dict[str, dict[str, str]]:
        """读取 NetworkManager 的设备状态总表，作为 device show 短暂不同步时的兜底。"""
        code, output = self._run(
            ["nmcli", "-t", "--escape", "no", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
            timeout=15,
        )
        result: dict[str, dict[str, str]] = {}
        if code != 0:
            return result
        for line in output.splitlines():
            parts = line.split(":", 3)
            if len(parts) < 4 or parts[1] != "wifi":
                continue
            result[parts[0]] = {"state": parts[2], "connection": parts[3]}
        return result

    def _linux_active_wifi_connection_map(self) -> dict[str, str]:
        """按设备名读取当前 active WiFi profile，避免只看单个字段时误判未连接。"""
        code, output = self._run(
            ["nmcli", "-t", "--escape", "no", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
            timeout=15,
        )
        result: dict[str, str] = {}
        if code != 0:
            return result
        for line in output.splitlines():
            parts = line.rsplit(":", 2)
            if len(parts) != 3:
                continue
            name, connection_type, device = parts
            if connection_type in {"wifi", "802-11-wireless"} and device:
                result[device] = name
        return result

    def _wifi_profile_ssid(self, profile: str) -> str:
        if not profile or profile == "--":
            return ""
        code, output = self._run(
            ["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", "id", profile],
            timeout=12,
        )
        return output.strip() if code == 0 else ""

    def _visible_wifi_signal(self, adapter_name: str, target_ssid: str) -> str:
        """不强制重新扫描，只读取 NetworkManager 最近一次扫描缓存里目标 SSID 的最好信号。"""
        if not target_ssid:
            return ""
        code, output = self._run(
            [
                "nmcli", "-t", "--escape", "no", "-f", "SSID,SIGNAL",
                "device", "wifi", "list", "ifname", adapter_name, "--rescan", "no",
            ],
            timeout=15,
        )
        if code != 0:
            return ""
        best_signal = -1
        for line in output.splitlines():
            ssid, separator, signal = line.rpartition(":")
            if not separator or ssid != target_ssid:
                continue
            try:
                best_signal = max(best_signal, int(signal.strip()))
            except ValueError:
                best_signal = max(best_signal, 0)
        return str(best_signal) if best_signal >= 0 else ""

    def get_wifi_client_status(
        self, adapters: list[WifiAdapter], target_ssid: str = "",
    ) -> list[dict[str, Any]]:
        self._require_nmcli()
        rows: list[dict[str, Any]] = []
        warnings_by_adapter: dict[str, list[str]] = {}
        try:
            status_map = self._linux_device_status_map()
        except HotspotError as exc:
            status_map = {}
            warning = f"NetworkManager 设备总表读取失败：{exc}"
            for adapter in adapters:
                warnings_by_adapter.setdefault(adapter.name, []).append(warning)
        try:
            active_map = self._linux_active_wifi_connection_map()
        except HotspotError as exc:
            active_map = {}
            warning = f"NetworkManager 活动连接读取失败：{exc}"
            for adapter in adapters:
                warnings_by_adapter.setdefault(adapter.name, []).append(warning)
        for adapter in adapters:
            state_text = ""
            connection = ""
            ip_text = ""
            try:
                code, output = self._run(
                    ["nmcli", "-g", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "device", "show", adapter.name],
                    timeout=12,
                )
                if code == 0:
                    lines = [line.strip() for line in output.splitlines()]
                    state_text = lines[0] if len(lines) > 0 else ""
                    connection = lines[1] if len(lines) > 1 else ""
                    ip_text = lines[2] if len(lines) > 2 else ""
                elif output.strip():
                    warnings_by_adapter.setdefault(adapter.name, []).append(
                        f"设备状态读取失败：{output.strip()}"
                    )
            except HotspotError as exc:
                warnings_by_adapter.setdefault(adapter.name, []).append(
                    f"设备状态暂时无法读取：{exc}"
                )
            status_row = status_map.get(adapter.name, {})
            status_state = status_row.get("state", "")
            status_connection = status_row.get("connection", "")
            active_connection = active_map.get(adapter.name, "")
            if (not state_text or state_text.startswith("30")) and status_state:
                # device show 有时短暂仍停在 30；device status 的连接态更贴近 GNOME 面板。
                if status_state not in {"disconnected", "unavailable", "unmanaged"}:
                    state_text = status_state
            if connection in {"", "--"}:
                connection = active_connection or status_connection
            ssid = ""
            signal = ""
            iw_connected = False
            if shutil.which("iw"):
                try:
                    link_code, link_output = self._run(["iw", "dev", adapter.name, "link"], timeout=4)
                    if link_code == 0:
                        ssid_match = re.search(r"^\s*SSID:\s*(.+)$", link_output, re.M)
                        signal_match = re.search(r"^\s*signal:\s*(.+)$", link_output, re.M)
                        iw_connected = bool(ssid_match) and not re.search(r"\bnot connected\b", link_output, re.I)
                        if ssid_match:
                            ssid = ssid_match.group(1).strip()
                        if signal_match:
                            signal = signal_match.group(1).strip()
                except HotspotError as exc:
                    warnings_by_adapter.setdefault(adapter.name, []).append(
                        f"iw 无线链路读取超时/失败：{exc}"
                    )
            if not ssid and connection not in {"", "--"}:
                try:
                    ssid = self._wifi_profile_ssid(connection)
                except HotspotError as exc:
                    warnings_by_adapter.setdefault(adapter.name, []).append(
                        f"连接配置读取失败：{exc}"
                    )
            try:
                target_signal = self._visible_wifi_signal(adapter.name, target_ssid)
            except HotspotError as exc:
                target_signal = ""
                warnings_by_adapter.setdefault(adapter.name, []).append(
                    f"扫描缓存读取失败：{exc}"
                )
            if not signal and target_ssid and ssid == target_ssid and target_signal:
                signal = target_signal
            state_for_connected = state_text.strip().lower()
            nm_connected = (
                state_for_connected.startswith("100")
                or state_for_connected == "connected"
                or state_for_connected == "connected (externally)"
                or status_state in {"connected", "connected (externally)"}
                or bool(active_connection)
            )
            connected = bool(iw_connected or (connection not in {"", "--"} and nm_connected))
            rows.append({
                "adapter": adapter.name,
                "connected": connected,
                "ssid": ssid,
                "state": localized_nm_device_state(state_text) if state_text else "未读取",
                "profile": "" if connection == "--" else connection,
                "ip": ip_text,
                "signal": signal,
                "target_visible": bool(target_signal),
                "target_signal": target_signal,
                "warning": "；".join(dict.fromkeys(warnings_by_adapter.get(adapter.name, []))),
            })
        return rows

    def _profile_name(self, adapter: WifiAdapter) -> str:
        return f"GMY-AP-{adapter.name}-{adapter.index}"

    def _preferred_start_channel(self, adapter: WifiAdapter, band: str) -> int:
        """为提高手机可见率，5G 优先请求低信道；失败时会回退自动协商。"""
        if band != "5G" or not PREFERRED_5G_CHANNELS:
            return 0
        return PREFERRED_5G_CHANNELS[(max(adapter.index, 1) - 1) % len(PREFERRED_5G_CHANNELS)]

    def _default_route_devices(self) -> list[str]:
        if not shutil.which("ip"):
            return []
        code, output = self._run(["ip", "-4", "route", "show", "default"], timeout=10)
        if code != 0:
            return []
        return list(dict.fromkeys(re.findall(r"\bdev\s+(\S+)", output)))

    def _discover_profiles(self, active_only: bool = False) -> list[dict[str, str]]:
        args = ["nmcli", "-t", "--escape", "no", "-f", "NAME,TYPE", "connection", "show"]
        if active_only:
            args.append("--active")
        raw = self._cmd(args, timeout=20)
        profiles: list[dict[str, str]] = []
        for line in raw.splitlines():
            name, separator, connection_type = line.rpartition(":")
            if not separator or not name.startswith("GMY-AP-"):
                continue
            if connection_type not in {"wifi", "802-11-wireless"}:
                continue
            adapter_code, adapter = self._run(
                ["nmcli", "-g", "connection.interface-name", "connection", "show", "id", name],
                timeout=15,
            )
            ssid_code, ssid = self._run(
                ["nmcli", "-g", "802-11-wireless.ssid", "connection", "show", "id", name],
                timeout=15,
            )
            profiles.append({
                "profile": name,
                "adapter": adapter.strip() if adapter_code == 0 else "",
                "ssid": ssid.strip() if ssid_code == 0 else "",
            })
        return profiles

    def _wiphy_id(self, adapter_name: str) -> str:
        if not shutil.which("iw"):
            return ""
        code, output = self._run(["iw", "dev", adapter_name, "info"], timeout=10)
        if code != 0:
            return ""
        match = re.search(r"\bwiphy\s+(\d+)", output)
        return match.group(1) if match else ""

    def _interface_mode(self, adapter_name: str) -> str:
        if not shutil.which("iw"):
            return ""
        code, output = self._run(["iw", "dev", adapter_name, "info"], timeout=10)
        if code != 0:
            return ""
        match = re.search(r"\btype\s+(\S+)", output)
        mode = match.group(1).upper() if match else ""
        if mode == "AP" and not re.search(r"\bchannel\s+\d+\b", output, re.I):
            return "AP（未分配工作信道）"
        return mode

    def _interface_channel(self, adapter_name: str) -> int:
        if not shutil.which("iw"):
            return 0
        code, output = self._run(["iw", "dev", adapter_name, "info"], timeout=10)
        if code != 0:
            return 0
        match = re.search(r"\bchannel\s+(\d+)\b", output, re.I)
        return int(match.group(1)) if match else 0

    def _device_health(self, adapter_name: str) -> str:
        try:
            code, output = self._run(
                ["nmcli", "-g", "GENERAL.STATE,GENERAL.REASON,GENERAL.CONNECTION",
                 "device", "show", adapter_name],
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return "无法读取设备状态"
        if code != 0:
            return output.strip() or "无法读取设备状态"
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return "设备没有返回状态"
        state = localized_nm_device_state(lines[0])
        reason = localized_nm_device_reason(lines[1]) if len(lines) > 1 else "未知原因"
        connection = lines[2] if len(lines) > 2 and lines[2] not in {"--", ""} else "无"
        return f"设备状态：{state}｜掉线原因：{reason}｜当前连接：{connection}"

    def _wait_for_hotspots_active(
        self, expected: dict[str, str], timeout: float = 12.0
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        """复核 profile 仍处于活动状态，并在 iw 可用时确认接口确实是 AP。"""
        deadline = time.monotonic() + timeout
        last_rows: list[dict[str, str]] = []
        last_modes: dict[str, str] = {}
        while True:
            try:
                last_rows = self._discover_profiles(active_only=True)
            except HotspotError:
                last_rows = []
            active_names = {row["profile"] for row in last_rows}
            profiles_ready = set(expected).issubset(active_names)
            last_modes = {adapter: self._interface_mode(adapter) for adapter in expected.values()}
            modes_ready = all(not mode or mode == "AP" for mode in last_modes.values())
            if profiles_ready and modes_ready:
                return last_rows, last_modes
            if time.monotonic() >= deadline:
                return last_rows, last_modes
            time.sleep(0.75)

    @_serialized_backend_operation
    def start_hotspot(
        self, adapter: WifiAdapter, source_name: str, ssid: str, password: str,
        band: str, isolate_adapter: bool, log: Callable[[str], None], channel: int = 0,
    ) -> None:
        self.start_hotspots(
            [adapter], source_name, ssid, password, band, isolate_adapter, log,
            channels={adapter.name: channel} if channel else None,
        )

    def start_hotspots(
        self, adapters: list[WifiAdapter], source_name: str, ssid: str, password: str,
        band: str, isolate_adapter: bool, log: Callable[[str], None],
        channels: dict[str, int] | None = None,
    ) -> None:
        self._require_nmcli()
        if not adapters:
            raise HotspotError("至少选择一块无线网卡。")
        if not source_name:
            raise HotspotError("请选择要共享的 LAN/以太网接口。")
        if not 1 <= len(ssid.encode("utf-8")) <= 32:
            raise HotspotError("Wi-Fi 名称不能为空，且 UTF-8 长度不能超过 32 字节。")
        if not 8 <= len(password) <= 63 or not password.isascii():
            raise HotspotError("密码必须为 8~63 位 ASCII 字符。")
        for adapter in adapters:
            if adapter.hosted_supported is False:
                # iw 的能力报告并非所有 USB 驱动都完整；这里仅提示，不在
                # 启动前硬拦截。最终是否能发射由 NetworkManager/驱动复核，
                # 这样用户仍可测试“能力报告不完整但实际支持 AP”的网卡。
                log(
                    f"Linux 警告：{adapter.name} 的驱动未报告 AP mode；"
                    "仍会实际尝试创建热点，最终以 AP 状态复核为准。"
                )
        if len(adapters) > 1:
            phy_to_adapters: dict[str, list[str]] = {}
            for adapter in adapters:
                phy = self._wiphy_id(adapter.name)
                if phy:
                    phy_to_adapters.setdefault(phy, []).append(adapter.name)
            shared_phys = [names for names in phy_to_adapters.values() if len(names) > 1]
            if shared_phys:
                groups = "；".join("、".join(names) for names in shared_phys)
                log(
                    f"Linux 警告：以下接口属于同一个物理无线射频：{groups}。"
                    "即使显示成多块接口，驱动也可能只允许其中一个热点运行。"
                )
        default_devices = self._default_route_devices()
        if default_devices and source_name not in default_devices:
            log(
                f"Linux 警告：所选共享接口是 {source_name}，但当前 IPv4 默认路由经过 "
                f"{'、'.join(default_devices)}。NetworkManager shared 模式会使用系统默认路由，"
                "本次热点流量不一定从所选接口上网。"
            )
        elif default_devices:
            log(f"Linux：已确认所选共享接口 {source_name} 位于当前 IPv4 默认路由。")
        # 只重启本次操作的网卡；其他正在运行的本程序热点继续保留。
        self.stop_hotspots(adapters, restore=True, log=lambda _: None)
        base_state = load_runtime_state()
        if base_state.get("platform") != "linux":
            base_state = {}
        # 运行记录可能因驱动掉线而过期；以 NetworkManager 当前仍活动的 profile 为准。
        base_active = [
            row for row in self._discover_profiles(active_only=True)
            if row.get("profile") and row.get("adapter") and row.get("ssid")
        ]
        base_profiles = [row["profile"] for row in base_active]
        base_adapters = [row["adapter"] for row in base_active]
        base_ssids = [row["ssid"] for row in base_active]
        base_count = min(len(base_profiles), len(base_adapters), len(base_ssids))
        profiles = base_profiles[:base_count]
        adapter_names = base_adapters[:base_count]
        ssids = base_ssids[:base_count]
        saved_profiles = list(base_state.get("profiles", []))
        saved_channels = list(base_state.get("channels", []))
        saved_bands = list(base_state.get("bands", []))
        saved_profile_channels = {
            profile: int(saved_channels[index])
            for index, profile in enumerate(saved_profiles)
            if index < len(saved_channels) and str(saved_channels[index]).isdigit()
        }
        saved_profile_bands = {
            profile: str(saved_bands[index])
            for index, profile in enumerate(saved_profiles)
            if index < len(saved_bands) and str(saved_bands[index]) in DEFAULT_CHANNELS_BY_BAND
        }
        legacy_saved_band = str(base_state.get("band", ""))
        active_channels = [saved_profile_channels.get(profile, 0) for profile in base_profiles[:base_count]]
        active_bands = [
            saved_profile_bands.get(profile, legacy_saved_band)
            for profile in base_profiles[:base_count]
        ]
        created_profiles: list[str] = []
        ssid_prefix = ssid_prefix_from_preview(ssid, adapters[0].index, band)
        try:
            for adapter in adapters:
                profile = self._profile_name(adapter)
                current_ssid = ssid if len(adapters) == 1 else make_ssid(ssid_prefix, adapter.index, band)
                # 5G 自动协商经常落到 157/161 等高信道，部分手机扫描不到；
                # 因此先请求 36/40/44/48 低信道。若驱动拒绝，下面会退回完全自动协商。
                current_channel = self._preferred_start_channel(adapter, band)
                if not 1 <= len(current_ssid.encode("utf-8")) <= 32:
                    raise HotspotError(f"{adapter.name} 生成的 SSID 超过 32 字节：{current_ssid}")
                if current_channel:
                    log(
                        f"Linux：在 {adapter.name} 创建 AP：{current_ssid}"
                        f"（{band}，优先请求低信道 {current_channel}；失败则自动协商）"
                    )
                else:
                    log(f"Linux：在 {adapter.name} 创建 AP：{current_ssid}（{band}，信道自动协商）")
                self._prepare_ap_device(adapter.name, log)
                # 删除同名旧 profile，显式创建 WPA2-PSK/AES AP connection。
                self._run(["nmcli", "connection", "delete", "id", profile], timeout=20)
                self._cmd([
                    "nmcli", "connection", "add", "type", "wifi", "ifname", adapter.name,
                    "con-name", profile, "autoconnect", "no", "ssid", current_ssid,
                ], timeout=30)
                created_profiles.append(profile)
                band_value = "bg" if band == "2.4G" else "a"
                modify_args = ["nmcli", "connection", "modify", profile,
                               # 创建阶段先禁止自动连接，避免它与下方显式 connection up 竞争。
                               "connection.autoconnect", "no",
                               "connection.autoconnect-retries", "0",
                               "802-11-wireless.mode", "ap",
                               "802-11-wireless.band", band_value,
                               "802-11-wireless.hidden", "no",
                               "802-11-wireless.powersave", "2"]
                if current_channel:
                    modify_args.extend(["802-11-wireless.channel", str(current_channel)])
                modify_args.extend([
                    "802-11-wireless-security.key-mgmt", "wpa-psk",
                    "802-11-wireless-security.proto", "rsn",
                    "802-11-wireless-security.pairwise", "ccmp",
                    "802-11-wireless-security.group", "ccmp",
                    "802-11-wireless-security.psk", password,
                    "ipv4.method", "shared", "ipv6.method", "ignore",
                ])
                self._cmd(modify_args, timeout=30)
                activation_detail = ""
                activated = False
                channel_attempts = [current_channel] if current_channel else [0]
                if current_channel:
                    channel_attempts.append(0)
                for requested_channel in channel_attempts:
                    if requested_channel == 0 and current_channel:
                        log(
                            f"Linux：{adapter.name} 无法按低信道 {current_channel} 启动，"
                            "正在退回由系统和网卡自动协商信道。"
                        )
                        self._cmd(
                            ["nmcli", "connection", "modify", profile, "802-11-wireless.channel", "0"],
                            timeout=20,
                        )
                    current_channel = requested_channel
                    for activation_attempt in range(2):
                        try:
                            self._cmd(["nmcli", "connection", "up", "id", profile], timeout=NORMAL_ACTIVATION_TIMEOUT)
                            activated = True
                            break
                        except HotspotError as exc:
                            activation_detail = str(exc)
                            is_supplicant_timeout = "802.1X supplicant took too long" in activation_detail
                            if is_supplicant_timeout and activation_attempt == 0:
                                self._reset_ap_device_for_retry(adapter.name, profile, log)
                                continue
                            break
                    if activated:
                        break
                if not activated:
                    detail = self._activation_failure_message(
                        adapter, band, current_channel, activation_detail,
                    )
                    raise HotspotError(detail) from None
                # 激活成功后再打开自动重连，避免首次启动发生双重激活竞争。
                self._cmd(
                    ["nmcli", "connection", "modify", profile,
                     "connection.autoconnect", "yes", "connection.autoconnect-retries", "0"],
                    timeout=20,
                )
                profiles.append(profile)
                adapter_names.append(adapter.name)
                ssids.append(current_ssid)
                active_channels.append(current_channel)
                active_bands.append(band)
                # 每成功一块就落盘，异常退出时仍可由“停止热点”清理。
                save_runtime_state({
                    "platform": "linux", "profiles": profiles,
                    "adapters": adapter_names, "adapter": adapter_names[0],
                    "ssids": ssids, "ssid": ssids[0], "source": source_name, "band": band,
                    "channels": active_channels, "bands": active_bands,
                })
                log(f"Linux：{adapter.name} 启动命令成功，等待最终状态复核。")

            expected = dict(zip(profiles, adapter_names))
            verify_timeout = NORMAL_VERIFY_TIMEOUT
            active_rows, interface_modes = self._wait_for_hotspots_active(
                expected, timeout=verify_timeout,
            )
            active_profiles = {row["profile"] for row in active_rows}
            missing_profiles = [profile for profile in profiles if profile not in active_profiles]
            wrong_modes = {
                adapter: mode for adapter, mode in interface_modes.items() if mode and mode != "AP"
            }
            if missing_profiles or wrong_modes:
                missing_adapters = [
                    adapter_names[profiles.index(profile)]
                    for profile in missing_profiles if profile in profiles
                ]
                details: list[str] = []
                if missing_adapters:
                    details.append("未保持运行的网卡：" + "、".join(missing_adapters))
                if wrong_modes:
                    details.append(
                        "无线接口未完全进入发射状态："
                        + "、".join(f"{adapter}={mode}" for adapter, mode in wrong_modes.items())
                    )
                raise HotspotError(
                    f"Linux 最终只确认 {len(active_profiles & set(profiles))}/{len(profiles)} 个热点仍在运行。\n"
                    + "\n".join(details)
                    + "\n\n常见原因：两块接口属于同一个物理射频、驱动不支持并发 AP、"
                    "第二个热点启动时替换了第一个，或 USB 网卡/驱动发生了重置。"
                )
            actual_channels = {
                adapter_name: self._interface_channel(adapter_name) for adapter_name in adapter_names
            }
            confirmed_channels = [
                f"{adapter_name}=信道 {actual_channel}"
                for adapter_name, actual_channel in actual_channels.items() if actual_channel
            ]
            if confirmed_channels:
                log("Linux：已从 iw 确认实际发射信道：" + "、".join(confirmed_channels))
            else:
                log("Linux：信道由系统和网卡自动协商；当前未能从 iw 读取实际信道。")
            active_channels = [actual_channels.get(adapter_name, 0) for adapter_name in adapter_names]
            save_runtime_state({
                "platform": "linux", "profiles": profiles,
                "adapters": adapter_names, "adapter": adapter_names[0],
                "ssids": ssids, "ssid": ssids[0], "source": source_name, "band": band,
                "channels": active_channels, "bands": active_bands,
            })
            log(
                f"Linux：已复核 {len(profiles)}/{len(profiles)} 个热点均保持运行；"
                f"NetworkManager 将通过系统默认路由共享网络（所选参考接口：{source_name}）。"
            )
        except Exception:
            log("Linux：启动命令没有成功完成，正在清理本次创建但未成功运行的热点配置。")
            for profile in reversed(created_profiles):
                down_code, down_output = self._run(["nmcli", "connection", "down", "id", profile], timeout=20)
                delete_code, delete_output = self._run(["nmcli", "connection", "delete", "id", profile], timeout=20)
                if (
                    down_code != 0 and down_output
                    and not re.search(r"not an active connection|no active connection", down_output, re.I)
                ):
                    log(f"Linux：回滚 {profile} 的 down 警告：{down_output}")
                if delete_code != 0 and delete_output:
                    log(f"Linux：回滚 {profile} 的 delete 警告：{delete_output}")
            if base_count:
                restored = dict(base_state)
                restored.update({
                    "platform": "linux", "profiles": base_profiles[:base_count],
                    "adapters": base_adapters[:base_count], "adapter": base_adapters[0],
                    "ssids": base_ssids[:base_count], "ssid": base_ssids[0],
                    "channels": active_channels[:base_count], "bands": active_bands[:base_count],
                })
                save_runtime_state(restored)
                for index, profile in enumerate(base_profiles[:base_count]):
                    restore_timeout = (
                        DFS_ACTIVATION_TIMEOUT
                        if index < len(active_channels)
                        and active_channels[index] in DFS_CHANNELS_BY_COUNTRY[REGULATORY_COUNTRY]
                        else NORMAL_ACTIVATION_TIMEOUT
                    )
                    self._run(["nmcli", "connection", "up", "id", profile], timeout=restore_timeout)
            else:
                delete_runtime_state()
            raise

    def get_hotspot_status(self) -> dict[str, Any]:
        self._require_nmcli()
        reported_active_profiles = self._discover_profiles(active_only=True)
        # NetworkManager 偶尔仍把 profile 标成 active，但驱动已经没有工作信道。
        # iw 可用时把这种“逻辑在线、射频未发射”的接口按掉线处理。
        radio_faults: dict[str, str] = {}
        active_profiles: list[dict[str, str]] = []
        for row in reported_active_profiles:
            adapter_name = row.get("adapter", "")
            mode = self._interface_mode(adapter_name) if adapter_name else ""
            if mode and mode != "AP":
                radio_faults[row.get("profile", "")] = mode
            else:
                active_profiles.append(row)
        state = load_runtime_state()
        expected_profiles = list(state.get("profiles", [])) if state.get("platform") == "linux" else []
        expected_adapters = list(state.get("adapters", [])) if state.get("platform") == "linux" else []
        expected_channels = list(state.get("channels", [])) if state.get("platform") == "linux" else []
        expected_bands = list(state.get("bands", [])) if state.get("platform") == "linux" else []
        profile_to_channel = {
            profile: int(expected_channels[index])
            for index, profile in enumerate(expected_profiles)
            if index < len(expected_channels) and str(expected_channels[index]).isdigit()
        }
        profile_to_band = {
            profile: str(expected_bands[index])
            for index, profile in enumerate(expected_profiles)
            if index < len(expected_bands) and str(expected_bands[index]) in DEFAULT_CHANNELS_BY_BAND
        }
        active_profile_names = {row["profile"] for row in active_profiles}
        active_adapters: list[str] = []
        active_ssids: list[str] = []
        active_channels: list[int] = []
        active_bands: list[str] = []
        channel_confirmed: list[bool] = []
        confirmed_channel_count = 0
        legacy_band = str(state.get("band", ""))
        for row in active_profiles:
            adapter_name = row.get("adapter", "")
            if not adapter_name:
                continue
            profile_name = row.get("profile", "")
            actual_channel = self._interface_channel(adapter_name)
            configured_channel = profile_to_channel.get(profile_name, 0)
            display_channel = actual_channel or configured_channel
            if actual_channel:
                confirmed_channel_count += 1
            active_adapters.append(adapter_name)
            # 保留空值以确保 SSID、信道和频段始终与网卡列表按下标对应。
            active_ssids.append(row.get("ssid", ""))
            active_channels.append(display_channel)
            channel_confirmed.append(bool(actual_channel))
            active_bands.append(
                band_for_channel(actual_channel)
                or profile_to_band.get(profile_name, "")
                or band_for_channel(configured_channel)
                or legacy_band
            )
        started = bool(active_profiles)
        if expected_profiles:
            missing_profiles = [profile for profile in expected_profiles if profile not in active_profile_names]
        else:
            missing_profiles = [profile for profile in radio_faults if profile]
        profile_to_adapter = dict(zip(expected_profiles, expected_adapters))
        profile_to_adapter.update({row["profile"]: row["adapter"] for row in reported_active_profiles})
        missing_adapters = [profile_to_adapter.get(profile, profile) for profile in missing_profiles]
        dropout_details: dict[str, str] = {}
        for profile, adapter in zip(missing_profiles, missing_adapters):
            if not adapter:
                continue
            detail = self._device_health(adapter)
            if profile in radio_faults:
                detail += f"｜无线接口：{radio_faults[profile]}"
            dropout_details[adapter] = detail
        expected_count = len(expected_profiles) if expected_profiles else len(reported_active_profiles)
        active_expected_count = len(set(expected_profiles) & active_profile_names) if expected_profiles else len(active_profiles)
        degraded = bool(missing_profiles)
        if degraded and started:
            status_text = f"部分热点已掉线（{active_expected_count}/{expected_count}）"
        elif degraded:
            status_text = f"热点已掉线（0/{expected_count}）"
        else:
            status_text = "已启动" if started else "未启动"
        unique_bands = list(dict.fromkeys(item for item in active_bands if item))
        reported_band = "、".join(unique_bands)
        channels_confirmed = bool(active_adapters) and confirmed_channel_count == len(active_adapters)
        return {
            "started": started, "status": status_text,
            "ssid": active_ssids[0] if active_ssids else "", "ssids": active_ssids,
            "adapter": active_adapters[0] if active_adapters else "", "adapters": active_adapters,
            "channels": active_channels, "channel_confirmed": channel_confirmed,
            "channels_confirmed": channels_confirmed,
            "bands": active_bands,
            "backend_label": "Linux NetworkManager 热点",
            "band": reported_band if started else "",
            "band_confirmed": bool(reported_band and channels_confirmed),
            "requested_band": str(state.get("band", "")),
            "degraded": degraded,
            "active_count": active_expected_count,
            "expected_count": expected_count,
            "missing_profiles": missing_profiles,
            "missing_adapters": missing_adapters,
            "dropout_details": dropout_details,
        }

    @_serialized_backend_operation
    def stop_hotspot(self, restore: bool, log: Callable[[str], None]) -> None:
        self.stop_hotspots([], restore=restore, log=log)

    @_serialized_backend_operation
    def stop_hotspots(self, adapters: list[WifiAdapter], restore: bool, log: Callable[[str], None]) -> None:
        self._require_nmcli()
        state = load_runtime_state()
        profiles = list(state.get("profiles", [])) if state.get("platform") == "linux" else []
        adapter_names = list(state.get("adapters", [])) if state.get("platform") == "linux" else []
        ssids = list(state.get("ssids", [])) if state.get("platform") == "linux" else []
        channels = list(state.get("channels", [])) if state.get("platform") == "linux" else []
        bands = list(state.get("bands", [])) if state.get("platform") == "linux" else []
        record_count = min(len(profiles), len(adapter_names), len(ssids))
        profiles, adapter_names, ssids = profiles[:record_count], adapter_names[:record_count], ssids[:record_count]
        channels = [
            int(channels[index]) if index < len(channels) and str(channels[index]).isdigit() else 0
            for index in range(record_count)
        ]
        legacy_band = str(state.get("band", ""))
        bands = [
            str(bands[index]) if index < len(bands) and str(bands[index]) in DEFAULT_CHANNELS_BY_BAND
            else band_for_channel(channels[index]) or legacy_band
            for index in range(record_count)
        ]
        active_before = self._discover_profiles(active_only=True)
        known_profiles = set(profiles)
        for row in self._discover_profiles(active_only=False):
            if row["profile"] in known_profiles:
                continue
            profiles.append(row["profile"])
            adapter_names.append(row["adapter"])
            ssids.append(row["ssid"])
            channels.append(0)
            bands.append("")
            known_profiles.add(row["profile"])
        if not profiles:
            return
        selected_names = {item.name for item in adapters}
        # 单网卡停止时，先记住其他当前活动的热点；驱动重置把它们连带停掉时可立即恢复。
        protected_profiles = {
            row["profile"]: row.get("adapter", "")
            for row in active_before
            if selected_names
            and row.get("profile")
            and row.get("adapter", "") not in selected_names
        }
        targets = [
            index for index, name in enumerate(adapter_names)
            if not selected_names or name in selected_names
        ]
        stopped: set[int] = set()
        failures: list[str] = []
        for index in targets:
            profile = profiles[index] if index < len(profiles) else ""
            if not profile:
                continue
            down_code, down_output = self._run(["nmcli", "connection", "down", "id", str(profile)], timeout=30)
            delete_code, delete_output = self._run(["nmcli", "connection", "delete", "id", str(profile)], timeout=30)
            exists_code, _ = self._run(["nmcli", "-g", "NAME", "connection", "show", "id", str(profile)], timeout=15)
            if delete_code == 0 or exists_code != 0:
                stopped.add(index)
                log(f"Linux：已停止并删除 AP profile：{profile}")
                adapter_name = adapter_names[index] if index < len(adapter_names) else ""
                if adapter_name:
                    self._soft_release_device(adapter_name)
                    self._wait_device_leaves_transition(adapter_name, timeout=10.0)
                    log(f"Linux：已释放 {adapter_name} 的热点残留状态，便于下次重新启动。")
            else:
                details = delete_output or down_output or "未知错误"
                failures.append(f"{profile}: {details}")
                log(f"Linux：停止 {profile} 失败，保留运行状态记录：{details}")

        recovery_failures: list[str] = []
        if protected_profiles:
            try:
                active_after = self._discover_profiles(active_only=True)
            except HotspotError as exc:
                active_after = []
                log(f"Linux：停止目标后暂时无法读取其他热点状态，将尝试逐一恢复：{exc}")
            active_after_names = {row.get("profile", "") for row in active_after}
            affected_profiles: list[str] = []
            for profile, adapter_name in protected_profiles.items():
                mode = self._interface_mode(adapter_name) if adapter_name else ""
                if profile not in active_after_names or (mode and mode != "AP"):
                    affected_profiles.append(profile)

            if affected_profiles:
                log(
                    "Linux 警告：停止目标热点时以下其他热点被驱动或 NetworkManager 连带影响："
                    + "、".join(affected_profiles)
                    + "。正在自动恢复。"
                )
                profile_channels = dict(zip(profiles, channels))
                for profile in affected_profiles:
                    recovery_timeout = (
                        DFS_ACTIVATION_TIMEOUT
                        if profile_channels.get(profile, 0)
                        in DFS_CHANNELS_BY_COUNTRY[REGULATORY_COUNTRY]
                        else NORMAL_ACTIVATION_TIMEOUT
                    )
                    try:
                        self._cmd(
                            ["nmcli", "connection", "up", "id", profile],
                            timeout=recovery_timeout,
                        )
                        log(f"Linux：已重新激活受保护热点：{profile}")
                    except HotspotError as exc:
                        recovery_failures.append(f"{profile}: {exc}")

                protected_has_dfs = any(
                    profile_channels.get(profile, 0)
                    in DFS_CHANNELS_BY_COUNTRY[REGULATORY_COUNTRY]
                    for profile in protected_profiles
                )
                verified_rows, verified_modes = self._wait_for_hotspots_active(
                    protected_profiles,
                    timeout=DFS_VERIFY_TIMEOUT if protected_has_dfs else NORMAL_VERIFY_TIMEOUT,
                )
                verified_names = {row.get("profile", "") for row in verified_rows}
                for profile, adapter_name in protected_profiles.items():
                    mode = verified_modes.get(adapter_name, "")
                    if profile not in verified_names or (mode and mode != "AP"):
                        detail = "profile 未恢复活动"
                        if mode and mode != "AP":
                            detail += f"，接口状态为 {mode}"
                        item = f"{profile}: {detail}"
                        if item not in recovery_failures:
                            recovery_failures.append(item)
                if not recovery_failures:
                    log("Linux：已确认其他热点仍在运行，单热点停止未留下连带影响。")
        remaining = [i for i in range(len(adapter_names)) if i not in stopped]
        if remaining:
            state["profiles"] = [profiles[i] for i in remaining if i < len(profiles)]
            state["adapters"] = [adapter_names[i] for i in remaining]
            state["ssids"] = [ssids[i] for i in remaining if i < len(ssids)]
            state["channels"] = [channels[i] for i in remaining if i < len(channels)]
            state["bands"] = [bands[i] for i in remaining if i < len(bands)]
            state["adapter"] = state["adapters"][0]
            state["ssid"] = state["ssids"][0] if state["ssids"] else ""
            remaining_bands = [item for item in state["bands"] if item]
            state["band"] = remaining_bands[-1] if remaining_bands else ""
            state["platform"] = "linux"
            save_runtime_state(state)
        else:
            delete_runtime_state()
        if failures:
            raise HotspotError("部分 Linux 热点停止失败：\n" + "\n".join(failures))
        if recovery_failures:
            raise HotspotError(
                "目标热点已经停止，但其他热点被驱动或 NetworkManager 连带影响，自动恢复未完全成功：\n"
                + "\n".join(recovery_failures)
            )


class HotspotApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        window_width = min(1120, max(920, self.winfo_screenwidth() - 80))
        # Windows 默认窗口给日志区预留更多高度，避免启动后只剩几行日志。
        window_height = min(980, max(820, self.winfo_screenheight() - 70))
        self.geometry(f"{window_width}x{window_height}")
        self.minsize(920, 820)
        self.backends = {"Windows": WindowsHotspotBackend(), "Linux": LinuxHotspotBackend()}
        self.platform_var = tk.StringVar(value=CURRENT_PLATFORM if CURRENT_PLATFORM in self.backends else "Windows")
        self.adapters: list[WifiAdapter] = []
        self.hotspot_status: dict[str, Any] = {"started": False, "adapter": "", "ssid": ""}
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.status_polling = False
        self.client_status_polling = False
        self.last_background_status_error = ""
        self.last_client_status_error = ""
        self.last_client_status_signature: tuple[Any, ...] | None = None
        self.last_health_signature: tuple[Any, ...] | None = None
        self.prefix_update_after_id: str | None = None
        self.adapter_order: dict[str, int] = {}
        self.next_adapter_index = 1
        self.selected_adapter_index: int | None = None
        self.closing = False

        self.band_var = tk.StringVar(value="2.4G")
        self.ssid_prefix_var = tk.StringVar(value=DEFAULT_SSID_PREFIX)
        self.ssid_var = tk.StringVar(value=make_ssid(DEFAULT_SSID_PREFIX, 1, "2.4G"))
        self.password_var = tk.StringVar(value="12345678")
        self.client_ssid_var = tk.StringVar(value=DEFAULT_CLIENT_SSID)
        self.client_password_var = tk.StringVar(value=DEFAULT_CLIENT_PASSWORD)
        self.client_password_visible_var = tk.BooleanVar(value=False)
        self.source_var = tk.StringVar()
        self.isolate_var = tk.BooleanVar(value=True)
        self.password_visible_var = tk.BooleanVar(value=False)
        self.encryption_var = tk.StringVar(value="WPA2-个人版（AES）")
        self.status_var = tk.StringVar(value="准备就绪")
        self.hotspot_state_var = tk.StringVar(value="● 正在读取全部热点状态…")
        self.hotspot_adapter_var = tk.StringVar(value="运行网卡：正在读取")
        self.hotspot_ssid_var = tk.StringVar(value="热点名称：正在读取")
        self.hotspot_band_var = tk.StringVar(value="实际发射频段：正在读取")
        self.hotspot_backend_var = tk.StringVar(value="启动方式：正在读取")
        self.hotspot_detail_var = tk.StringVar(
            value="此处汇总所有网卡的热点状态；单块网卡请查看表格并使用最后一列操作。"
        )
        self.selected_adapter_var = tk.StringVar(value="当前未选择网卡")
        self.client_window: tk.Toplevel | None = None
        self.client_adapter_listbox: tk.Listbox | None = None
        self.client_password_entry: ttk.Entry | None = None
        self.client_status_text: tk.Text | None = None
        self.client_progress: ttk.Progressbar | None = None
        self.client_status_by_adapter: dict[str, dict[str, Any]] = {}
        self.client_row_colors: dict[int, str] = {}
        self.client_operation_var = tk.StringVar(value="准备就绪｜Windows/Linux 每 10 秒自动刷新连接状态")
        self.client_operation_label: ttk.Label | None = None
        # 连接操作期间保留“阶段提示”，直到下一次实际状态读取完成。
        # 这样用户不会把“命令已提交”误认为“已经连上 WiFi”。
        self.client_operation_pending = False
        # 首次打开页面时只是读取状态，并没有发起过连接操作；
        # 此时不能把“当前未连接”显示成“连接失败”。
        self.client_action_started = False
        self.client_pending_adapter_names: set[str] = set()
        self.client_pending_action: str | None = None

        self._configure_style()
        self._build_ui()
        self.backend = self.backends[self.platform_var.get()]
        self._update_platform_controls()
        self.ssid_prefix_var.trace_add("write", lambda *_: self._schedule_prefix_changed())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_events)
        self.after(250, lambda: self.refresh(refresh_status=True))
        self.after(10000, self._poll_hotspot_status)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Hint.TLabel", foreground="#52606d", font=("Microsoft YaHei UI", 9))
        style.configure("Main.TNotebook", background="#dbeafe", borderwidth=1)
        style.configure(
            "Main.TNotebook.Tab",
            padding=(16, 7),
            font=("Microsoft YaHei UI", 10, "bold"),
            foreground="#1f2937",
            background="#e5e7eb",
        )
        style.map(
            "Main.TNotebook.Tab",
            background=[("selected", "#bfdbfe"), ("active", "#dbeafe")],
            foreground=[("selected", "#111827"), ("active", "#111827")],
        )
        style.configure("HotspotPage.TFrame", background="#f8fafc")
        style.configure("ClientPage.TFrame", background="#eff6ff")
        style.configure("Hotspot.Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))
        style.configure("Hotspot.Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        # 不使用系统 Treeview 选中态着色；部分 Linux 主题会强行把文字改浅导致看不清。
        style.map("Hotspot.Treeview", background=[], foreground=[])
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Running.TLabel", foreground="#14804a", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Stopped.TLabel", foreground="#2563eb", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Unknown.TLabel", foreground="#64748b", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Degraded.TLabel", foreground="#dc2626", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Busy.TLabel", foreground="#155eef", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("ClientReady.TLabel", foreground="#475569", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("ClientBusy.TLabel", foreground="#1d4ed8", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("ClientGood.TLabel", foreground="#047857", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("ClientBad.TLabel", foreground="#b91c1c", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("StatusField.TLabel", foreground="#1f2937", font=("Microsoft YaHei UI", 9))
        style.configure("StatusNote.TLabel", foreground="#52606d", font=("Microsoft YaHei UI", 9))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 7))
        title_area = ttk.Frame(header)
        title_area.pack(side="left", fill="x", expand=True)
        # 主界面大标题暂时隐藏；APP_TITLE 仍保留给窗口标题和提示框使用。
        # ttk.Label(title_area, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_area,
            text=f"跨平台无线热点测试工具｜默认热点名称：{DEFAULT_SSID_PREFIX}序号-2.4G",
            style="Hint.TLabel",
        ).pack(anchor="w")

        platform_bar = ttk.Frame(header)
        platform_bar.pack(side="right", anchor="ne", padx=(12, 0), pady=(3, 0))
        ttk.Label(platform_bar, text="运行平台：").pack(side="left")
        self.platform_combo = ttk.Combobox(
            platform_bar, textvariable=self.platform_var,
            values=("Windows", "Linux"), state="readonly", width=12,
        )
        self.platform_combo.pack(side="left")
        self.platform_combo.bind("<<ComboboxSelected>>", self._platform_changed)

        self.main_notebook = ttk.Notebook(outer, style="Main.TNotebook")
        self.main_notebook.pack(fill="both", expand=True)
        hotspot_page = ttk.Frame(self.main_notebook, padding=(8, 8, 8, 6), style="HotspotPage.TFrame")
        client_page = ttk.Frame(self.main_notebook, padding=(8, 8, 8, 6), style="ClientPage.TFrame")
        self.main_notebook.add(hotspot_page, text="📡 WIFI热点")
        self.main_notebook.add(client_page, text="🔗 WIFI连接")

        state_box = ttk.LabelFrame(
            hotspot_page, text="全部热点运行概览（单块网卡请在表格最后一列操作）", padding=8,
        )
        state_box.pack(fill="x", pady=(0, 7))
        self.hotspot_state_label = ttk.Label(state_box, textvariable=self.hotspot_state_var, style="Unknown.TLabel")
        self.hotspot_state_label.grid(row=0, column=0, sticky="nw", padx=(0, 18), pady=(2, 0))

        status_fields = ttk.Frame(state_box)
        status_fields.grid(row=0, column=1, sticky="ew")
        status_fields.columnconfigure(0, weight=1)
        status_fields.columnconfigure(1, weight=1)
        ttk.Label(
            status_fields, textvariable=self.hotspot_adapter_var, style="StatusField.TLabel",
            wraplength=330, justify="left",
        ).grid(row=0, column=0, sticky="w", padx=(0, 14))
        ttk.Label(
            status_fields, textvariable=self.hotspot_ssid_var, style="StatusField.TLabel",
            wraplength=300, justify="left",
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(
            status_fields, textvariable=self.hotspot_band_var, style="StatusField.TLabel",
            wraplength=330, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=(0, 14), pady=(4, 0))
        ttk.Label(
            status_fields, textvariable=self.hotspot_backend_var, style="StatusField.TLabel",
            wraplength=300, justify="left",
        ).grid(row=1, column=1, sticky="w", pady=(4, 0))

        self.hotspot_detail_label = ttk.Label(
            status_fields, textvariable=self.hotspot_detail_var, style="StatusNote.TLabel",
            wraplength=650, justify="left",
        )
        self.hotspot_detail_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        status_actions = ttk.Frame(state_box)
        status_actions.grid(row=0, column=2, sticky="ne", padx=(14, 0))
        ttk.Button(status_actions, text="刷新热点状态", command=self.refresh_hotspot_status).pack(side="right")
        self.retry_recovery_button = ttk.Button(
            status_actions, text="重试残留恢复", command=self.retry_pending_recovery,
        )
        self.retry_recovery_button.pack(side="right", padx=(0, 8))
        state_box.columnconfigure(1, weight=1)

        table_box = ttk.LabelFrame(
            hotspot_page, text="无线网卡（选择一行修改配置；点击最后一列可单独启动或停止该网卡热点）", padding=8,
        )
        # 网卡列表是热点页的主要工作区，允许它吸收页面剩余高度。
        # 之前只按横向填充，Treeview 固定两行，窗口下方的大量空间没有被利用。
        table_box.pack(fill="both", expand=True, pady=(0, 2))
        columns = ("seq", "name", "desc", "status", "channel", "hotspot", "ssid", "action")
        self.tree = ttk.Treeview(
            table_box, columns=columns, show="headings", height=8, style="Hotspot.Treeview",
        )
        self.tree.tag_configure("hotspot_running", foreground="#14804a")
        self.tree.tag_configure("hotspot_stopped", foreground="#2563eb")
        self.tree.tag_configure("hotspot_degraded", foreground="#dc2626")
        self.tree.tag_configure("hotspot_unknown", foreground="#64748b")
        self.tree.tag_configure("selected_hotspot_running", foreground="#14804a", background="#edf6ff")
        self.tree.tag_configure("selected_hotspot_stopped", foreground="#2563eb", background="#edf6ff")
        self.tree.tag_configure("selected_hotspot_degraded", foreground="#dc2626", background="#fff1f2")
        self.tree.tag_configure("selected_hotspot_unknown", foreground="#64748b", background="#edf6ff")
        headings = {
            "seq": "序号", "name": "接口名", "desc": "网卡型号", "status": "网卡状态",
            "channel": "实际信道", "hotspot": "热点状态", "ssid": "热点名称（运行/预览）",
            "action": "热点开关（点击）",
        }
        # 使用较紧凑的基础列宽并允许 Treeview 自动拉伸；小屏不会把右侧状态/SSID 整列裁掉。
        widths = {
            "seq": 42, "name": 100, "desc": 150, "status": 135,
            "channel": 80, "hotspot": 110, "ssid": 125, "action": 105,
        }
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], anchor="center" if key != "desc" else "w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._tree_action_click)
        self.tree.bind("<Motion>", self._tree_motion)

        action_bar = ttk.Frame(hotspot_page)
        action_bar.pack(fill="x", pady=5)
        ttk.Button(action_bar, text="刷新网卡", command=self.refresh).pack(side="left")
        ttk.Button(
            action_bar, text="启用当前网卡", command=lambda: self._toggle_adapter(True),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            action_bar, text="禁用当前网卡", command=lambda: self._toggle_adapter(False),
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            action_bar, text="先选择表格中的网卡，再执行启用/禁用", style="Hint.TLabel",
        ).pack(side="left", padx=(14, 0))
        ttk.Label(action_bar, textvariable=self.selected_adapter_var, style="Hint.TLabel").pack(side="right")

        settings = ttk.LabelFrame(hotspot_page, text="热点配置", padding=8)
        settings.pack(fill="x")
        ttk.Label(settings, text="共享上网来源").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        self.source_combo = ttk.Combobox(settings, textvariable=self.source_var, state="readonly", width=16)
        self.source_combo.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=3)

        ttk.Label(settings, text="热点名称前缀（SSID）").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.ssid_prefix_var, width=16).grid(row=0, column=3, sticky="ew", padx=(0, 14), pady=3)

        ttk.Label(settings, text="密码（8~63位）").grid(row=0, column=4, sticky="w", padx=(0, 6), pady=3)
        password_frame = ttk.Frame(settings)
        password_frame.grid(row=0, column=5, sticky="ew", pady=3)
        self.password_entry = ttk.Entry(password_frame, textvariable=self.password_var, width=14, show="●")
        self.password_entry.pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(
            password_frame, text="显示", variable=self.password_visible_var,
            command=self._toggle_password_visibility,
        ).pack(side="left", padx=(6, 0))

        ttk.Label(settings, text="设置发射频段").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        band_frame = ttk.Frame(settings)
        band_frame.grid(row=1, column=1, sticky="w", padx=(0, 14), pady=3)
        ttk.Radiobutton(band_frame, text="2.4G（默认）", value="2.4G", variable=self.band_var, command=self._band_changed).pack(side="left")
        ttk.Radiobutton(band_frame, text="5G", value="5G", variable=self.band_var, command=self._band_changed).pack(side="left", padx=(12, 0))

        ttk.Label(settings, text="加密方式").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=3)
        encryption_frame = ttk.Frame(settings)
        encryption_frame.grid(row=1, column=3, sticky="ew", padx=(0, 14), pady=3)
        self.encryption_combo = ttk.Combobox(
            encryption_frame, textvariable=self.encryption_var,
            values=("WPA2-个人版（AES）",), state="disabled", width=17,
        )
        self.encryption_combo.pack(side="left")
        ttk.Label(encryption_frame, text="固定 WPA2", style="Hint.TLabel").pack(side="left", padx=(6, 0))

        ttk.Label(settings, text="热点名称预览").grid(row=1, column=4, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.ssid_var, state="readonly", width=16).grid(row=1, column=5, sticky="ew", pady=3)

        ttk.Label(
            settings, text="信道不再手动指定，由系统、驱动和网卡自动协商；运行后能读取就显示实际值。",
            style="Hint.TLabel",
            wraplength=470, justify="left",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=3)

        self.isolate_check = ttk.Checkbutton(
            settings,
            text="只使用所选网卡：启动前临时禁用其他无线网卡，停止后自动恢复",
            variable=self.isolate_var,
        )
        self.isolate_check.grid(row=3, column=0, columnspan=6, sticky="w", pady=(5, 0))
        for col in (1, 3, 5):
            settings.columnconfigure(col, weight=1)

        controls = ttk.Frame(hotspot_page)
        controls.pack(fill="x", pady=6)
        ttk.Label(
            controls,
            text="热点启停请点击表格最后一列；进度条只表示当前命令正在执行（后台检查不显示）",
            style="Hint.TLabel",
        ).pack(side="left")
        ttk.Label(controls, textvariable=self.status_var).pack(side="right")

        self._build_wifi_client_tab(client_page)

        operation_bar = ttk.Frame(outer)
        operation_bar.pack(fill="x", pady=(6, 0))
        self.operation_bar = operation_bar
        ttk.Label(
            operation_bar, textvariable=self.status_var, style="Busy.TLabel", anchor="w",
        ).pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(operation_bar, mode="indeterminate", length=130)
        self.force_stop_button = ttk.Button(
            operation_bar, text="强制终止本程序命令", command=self.force_terminate_operations,
        )
        self.force_stop_button.pack(side="right", padx=(10, 0))

        log_box = ttk.LabelFrame(outer, text="运行日志（两个页面共用，WIFI热点/WIFI连接操作都会显示在这里）", padding=8)
        # 日志是排查多网卡连接/断开问题的主要依据，给它更充足的固定高度；
        # 这样切换页面或同时操作多块网卡时，不会只看到最后两三行。
        log_box.pack(fill="both", expand=False, pady=(8, 0))
        log_frame = ttk.Frame(log_box)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_frame, height=40, wrap="word", state="disabled", font=("Consolas", 9),
            background="#111827", foreground="#d1fae5", insertbackground="white",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self._log(f"程序版本：{APP_VERSION}")
        self._log("提示：修改‘热点名称前缀（SSID）’后，会自动生成 序号-频段 后缀。")
        self._log(f"提示：默认热点名称前缀为 {DEFAULT_SSID_PREFIX}，例如 {make_ssid(DEFAULT_SSID_PREFIX, 1, '2.4G')}。")
        self._log("提示：热点名称里的 2.4G/5G 只是名称后缀；真实运行频段看顶部“实际发射频段”。")
        self._log("提示：点击网卡表格最后一列，只会启动或停止该行对应的热点。")
        self._log("提示：点击“连接外部 WiFi”可让多块无线网卡同时连接同一个 SSID。")
        self._log("提示：Windows 只能运行一个系统热点；切换目标网卡前程序会先提示。")
        self._log("提示：Linux 后端使用 NetworkManager，可尝试让多块支持 AP 模式的网卡同时建立热点。")
        self._log(
            "提示：Linux 5G 会优先请求 36/40/44/48 低信道，失败后再退回系统自动协商；"
            "2.4G 由系统和网卡自动协商。"
        )
        self._log("提示：程序不做严格信道校验；实际信道能读取就显示，读不到以扫描工具为准。")
        self._log("提示：Linux 不主动设置或校验国家码；如果驱动拒绝低信道，会自动退回协商。")
        self._log("提示：Windows 客户端优先用 Win32 WLAN API 读取实时关联 SSID；不使用 WLAN Profile 名称判定连接。")
        self._log("提示：Windows/Linux 每 10 秒静默检查一次热点和 WiFi 连接状态；后台检查不会显示进度条，也不会打断 SSID 输入。")
        self._log("提示：WiFi 连接会先让所有选中网卡各尝试一轮；第一轮结束后，只对未连接网卡再重试一轮。")
        self._log(
            "提示：连接/断开/启停网卡操作会串行执行；Linux 会核对客户端配置绑定网卡，"
            "避免误操作其它无线网卡或有线接口。"
        )

    def _run_async(self, label: str, worker: Callable[[], Any], done: Callable[[Any], None] | None = None) -> None:
        if self.busy:
            self._log("提示：正在执行上一项操作；如需停止，请点击底部“强制终止本程序命令”。")
            self.status_var.set("上一项操作仍在执行，请查看底部进度条或点击强制终止")
            return
        clear_terminate_request()
        self.busy = True
        self.status_var.set(label)
        self.retry_recovery_button.configure(state="disabled")
        self.platform_combo.configure(state="disabled")
        if not self.progress.winfo_manager():
            # Progressbar 的父容器已经是 operation_bar。
            # Linux Tk 对 pack(in_=...) 的跨父容器挂载校验更严格，
            # 这里直接在自身父容器中 pack，避免启动首个操作时 TclError。
            self.progress.pack(side="left", padx=(12, 0))
        self.progress.start(10)
        if hasattr(self, "force_stop_button"):
            self.force_stop_button.configure(state="normal", text="强制终止本程序命令")

        def target() -> None:
            try:
                result = worker()
                self.events.put(("done", (result, done)))
            except Exception as exc:
                self.events.put(("error", (exc, traceback.format_exc())))

        threading.Thread(target=target, daemon=True).start()

    def force_terminate_operations(self) -> None:
        """只终止本程序启动的外部命令，不关闭 NetworkManager/WLAN 服务。"""
        if not self.busy:
            self._log("提示：当前没有正在执行的前台操作。")
            self.status_var.set("当前没有正在执行的前台操作")
            return
        count = request_terminate_active_processes()
        self.status_var.set("正在终止本程序命令；等待操作线程收尾…")
        self._log(
            f"用户请求强制终止本程序命令：已发出终止请求"
            f"{f'（已结束 {count} 个外部进程）' if count else ''}。"
        )
        if hasattr(self, "force_stop_button"):
            self.force_stop_button.configure(state="disabled", text="正在终止…")

    def _reset_force_stop_button(self) -> None:
        if hasattr(self, "force_stop_button"):
            try:
                self.force_stop_button.configure(state="normal", text="强制终止本程序命令")
            except tk.TclError:
                pass

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    result, callback = payload
                    clear_terminate_request()
                    self.busy = False
                    self.status_var.set("操作完成")
                    self.retry_recovery_button.configure(
                        state="normal" if self.platform_var.get() == "Windows" else "disabled"
                    )
                    self.platform_combo.configure(state="readonly")
                    self.progress.stop()
                    self.progress.pack_forget()
                    self._reset_force_stop_button()
                    self._set_client_progress(False)
                    if callback:
                        callback(result)
                elif kind == "status_done":
                    result, callback = payload
                    self.status_polling = False
                    self.last_background_status_error = ""
                    if not self.busy:
                        callback(result)
                elif kind == "status_error":
                    exc = payload
                    self.status_polling = False
                    message = str(exc)
                    if not self.busy and message != self.last_background_status_error:
                        self.last_background_status_error = message
                        self._log(f"后台状态查询失败：{message}")
                elif kind == "client_status_done":
                    result = payload
                    self.client_status_polling = False
                    self.last_client_status_error = ""
                    self._render_client_status(result)
                elif kind == "client_status_error":
                    exc = payload
                    self.client_status_polling = False
                    message = str(exc)
                    if message != self.last_client_status_error:
                        self.last_client_status_error = message
                        self._log(f"WiFi 客户端状态查询失败：{message}")
                    self._render_client_status_error(message)
                elif kind == "close_done":
                    clear_terminate_request()
                    self._log("关闭程序：已执行全部热点停止命令。")
                    self.destroy()
                    return
                elif kind == "close_error":
                    exc, trace = payload
                    self.busy = False
                    self.closing = False
                    self.retry_recovery_button.configure(
                        state="normal" if self.platform_var.get() == "Windows" else "disabled"
                    )
                    self.platform_combo.configure(state="readonly")
                    self.progress.stop()
                    self.progress.pack_forget()
                    self._reset_force_stop_button()
                    self._set_client_progress(False)
                    self.status_var.set("关闭前停止热点失败")
                    user_message = self._close_error_message(exc)
                    self._log(f"关闭清理失败：{user_message}")
                    self._log(trace)
                    force_exit = messagebox.askyesno(
                        APP_TITLE,
                        "关闭窗口前停止热点失败。\n\n"
                        f"原因：{user_message}\n\n"
                        "选择“是”将直接退出，热点可能仍在运行；选择“否”返回界面重试。",
                    )
                    if force_exit:
                        self.destroy()
                        return
                    self.refresh_hotspot_status(silent=True)
                elif kind == "error":
                    exc, trace = payload
                    clear_terminate_request()
                    self.busy = False
                    self.retry_recovery_button.configure(
                        state="normal" if self.platform_var.get() == "Windows" else "disabled"
                    )
                    self.platform_combo.configure(state="readonly")
                    self.progress.stop()
                    self.progress.pack_forget()
                    self._reset_force_stop_button()
                    self._set_client_progress(False)
                    if isinstance(exc, PendingRecoveryError):
                        self.status_var.set("仍有旧网卡设置待恢复")
                        self._log(f"恢复提示：{exc}")
                        messagebox.showwarning(APP_TITLE, str(exc))
                        self.after(200, self.refresh_hotspot_status)
                    elif isinstance(exc, HotspotError):
                        # 驱动不兼容、命令失败等属于可预期的操作结果，不向用户倾倒内部调用栈。
                        on_client_tab = (
                            self.client_status_text is not None
                            and hasattr(self, "main_notebook")
                            and self.main_notebook.index("current") == 1
                        )
                        self.status_var.set("WiFi连接操作失败" if on_client_tab else "热点操作失败")
                        self._log(f"错误：{exc}")
                        if on_client_tab:
                            self.client_operation_pending = False
                            self.client_pending_adapter_names.clear()
                            self.client_pending_action = None
                            self._set_client_operation(
                                "❌ 连接操作失败｜未确认目标 WiFi 已连接，请查看运行日志",
                                "ClientBad.TLabel",
                            )
                            self._render_client_status_message(
                                f"WiFi 连接/断开操作失败：\n\n{exc}\n\n"
                                "底部运行日志里有每块网卡的具体过程；程序会继续每 10 秒刷新实际连接状态。"
                            )
                        messagebox.showerror(APP_TITLE, str(exc))
                        self.after(300, lambda: self.refresh(refresh_status=True))
                        self.after(1200, lambda: self.refresh_wifi_client_status(silent=True))
                    else:
                        self.status_var.set("操作失败")
                        self._log(f"错误：{exc}")
                        self._log(trace)
                        messagebox.showerror(APP_TITLE, str(exc))
        except queue.Empty:
            pass
        except Exception as exc:
            try:
                self.busy = False
                self.retry_recovery_button.configure(
                    state="normal" if self.platform_var.get() == "Windows" else "disabled"
                )
                self.platform_combo.configure(state="readonly")
                self.progress.stop()
                self.progress.pack_forget()
                self._reset_force_stop_button()
                self._set_client_progress(False)
                self.status_var.set("界面回调失败")
                self._log(f"界面回调错误：{exc}")
                self._log(traceback.format_exc())
                messagebox.showerror(APP_TITLE, f"界面回调失败：{exc}")
            except tk.TclError:
                return
        try:
            self.after(100, self._drain_events)
        except tk.TclError:
            pass

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def thread_log(self, message: str) -> None:
        self.events.put(("log", message))

    @staticmethod
    def _pending_recovery_allows_close(exc: PendingRecoveryError) -> bool:
        """关闭窗口时，热点已停但旧设置待恢复属于可延后处理；热点状态不明则不能放行。"""
        message = str(exc)
        blocking_markers = (
            "当前热点仍在运行",
            "热点仍在运行",
            "无法确认 Windows 热点是否已停止",
            "无法确认 Windows 热点已经停止",
        )
        return not any(marker in message for marker in blocking_markers)

    @staticmethod
    def _close_error_message(exc: Exception) -> str:
        """把关闭清理时的底层命令错误压缩成用户能判断的中文提示。"""
        message = str(exc).strip()
        if not message:
            return "未知错误"
        if (
            "Get-NetAdapterAdvancedProperty" in message
            and ("找不到任何" in message or "No matching" in message or "not found" in message.lower())
        ):
            return (
                "热点停止命令已执行，但恢复旧网卡高级属性时找不到之前记录的网卡或属性。"
                "通常是 USB 无线网卡已拔出、网卡名称变化，或驱动重装导致。"
                "请重新插入对应网卡后，在程序里点击“重试残留恢复”。"
            )
        if len(message) > 700:
            return message[:700].rstrip() + "……"
        return message

    def _on_close(self) -> None:
        """正常关闭窗口时先停止本程序管理的热点，避免界面退出后 AP 残留。"""
        if self.closing:
            return
        if self.busy:
            messagebox.showinfo(APP_TITLE, "当前正在执行操作，请完成后再关闭程序。")
            return
        self.closing = True
        self.busy = True
        self.status_var.set("正在关闭全部热点…")
        self._set_hotspot_state(None, "正在关闭窗口：先停止本程序创建的全部热点")
        self.retry_recovery_button.configure(state="disabled")
        self.platform_combo.configure(state="disabled")
        if not self.progress.winfo_manager():
            self.progress.pack(side="left", padx=(14, 0))
        self.progress.start(10)
        self._log("关闭程序：正在停止本程序管理的全部热点。")

        def target() -> None:
            try:
                self.backend.stop_hotspots([], restore=True, log=self.thread_log)
                self.events.put(("close_done", None))
            except PendingRecoveryError as exc:
                if self._pending_recovery_allows_close(exc):
                    self.thread_log(f"关闭程序：热点停止流程已执行，旧网卡设置留待稍后恢复：{exc}")
                    self.thread_log("关闭程序：下次插回对应无线网卡后，可点击“重试残留恢复”。")
                    self.events.put(("close_done", None))
                else:
                    self.events.put(("close_error", (exc, traceback.format_exc())))
            except Exception as exc:
                self.events.put(("close_error", (exc, traceback.format_exc())))

        threading.Thread(target=target, daemon=True).start()

    def _platform_changed(self, _event: Any = None) -> None:
        if self.busy:
            current = next((name for name, backend in self.backends.items() if backend is self.backend), CURRENT_PLATFORM)
            self.platform_var.set(current)
            messagebox.showinfo(APP_TITLE, "当前正在执行操作，请完成后再切换平台。")
            return
        selected = self.platform_var.get()
        actual = CURRENT_PLATFORM
        if actual == "Unsupported":
            messagebox.showerror(APP_TITLE, "当前操作系统不是受支持的 Windows 或 Linux。")
            return
        if selected != actual:
            messagebox.showwarning(
                APP_TITLE,
                f"当前电脑运行的是 {actual}，不能用 {selected} 后端控制本机网卡。\n\n"
                f"同一份 Python 源码复制到 {selected} 系统运行时，会自动选择 {selected} 后端。",
            )
            self.platform_var.set(actual)
            return
        if self.backend is self.backends.get(selected):
            return
        self.backend = self.backends[selected]
        # 切换后端后只是重新读取状态；不能把之前平台的失败结果
        # 继续显示成当前平台刚刚发起的连接失败。
        self.client_action_started = False
        self.client_operation_pending = False
        self.client_pending_adapter_names.clear()
        self.client_pending_action = None
        self._set_client_operation(
            "○ 尚未发起连接｜当前仅显示网卡状态",
            "ClientReady.TLabel",
        )
        self._update_platform_controls()
        self.hotspot_status = {"started": False, "adapter": "", "ssid": ""}
        self._set_hotspot_fields("—", "—", "—", f"{selected} 后端")
        self._set_hotspot_state(None, f"当前后端：{selected}")
        self._log(f"已切换到 {selected} 后端，正在重新扫描网卡。")
        self.refresh()

    def _update_platform_controls(self) -> None:
        if self.platform_var.get() == "Linux":
            self.isolate_var.set(False)
            self.isolate_check.configure(state="disabled")
            self.retry_recovery_button.configure(state="disabled")
        else:
            self.isolate_check.configure(state="normal")
            self.retry_recovery_button.configure(state="normal")

    def _set_hotspot_state(
        self, started: bool | None, detail: str = "", degraded: bool = False,
        active_count: int = 0,
    ) -> None:
        if degraded and started is True:
            self.hotspot_state_var.set(f"● 运行异常：当前仍有 {max(active_count, 1)} 个热点")
            self.hotspot_state_label.configure(style="Degraded.TLabel")
        elif degraded:
            self.hotspot_state_var.set("● 热点已掉线")
            self.hotspot_state_label.configure(style="Degraded.TLabel")
        elif started is True:
            self.hotspot_state_var.set(f"● 当前运行 {max(active_count, 1)} 个热点")
            self.hotspot_state_label.configure(style="Running.TLabel")
        elif started is False:
            self.hotspot_state_var.set("● 当前没有热点运行")
            self.hotspot_state_label.configure(style="Stopped.TLabel")
        else:
            self.hotspot_state_var.set("● 正在读取全部热点状态")
            self.hotspot_state_label.configure(style="Unknown.TLabel")
        self.hotspot_detail_var.set(detail)
        if hasattr(self, "hotspot_detail_label"):
            if detail.strip():
                self.hotspot_detail_label.grid()
            else:
                self.hotspot_detail_label.grid_remove()

    def _set_hotspot_fields(
        self, adapter: str = "—", ssid: str = "—", band: str = "—", backend: str = "—"
    ) -> None:
        """用固定中文字段显示运行信息，避免把所有状态挤成一行。"""
        self.hotspot_adapter_var.set(f"运行网卡：{adapter}")
        self.hotspot_ssid_var.set(f"热点名称：{ssid}")
        self.hotspot_band_var.set(f"实际发射频段：{band}")
        self.hotspot_backend_var.set(f"启动方式：{backend}")

    def refresh_hotspot_status(self, silent: bool = False) -> None:
        # 用户可以手动查询；周期查询由 _poll_hotspot_status 单独调度，避免重复定时器。
        if self.busy or (silent and self.status_polling):
            return

        def worker() -> dict[str, Any]:
            return self.backend.get_hotspot_status()

        def done(result: dict[str, Any]) -> None:
            self.hotspot_status = result
            degraded = bool(result.get("degraded"))
            health_signature = (
                degraded,
                int(result.get("active_count", 0)),
                int(result.get("expected_count", 0)),
                tuple(result.get("missing_adapters", [])),
            )
            if degraded and health_signature != self.last_health_signature:
                self._log(f"Linux 热点状态异常：{result.get('status', '部分热点已经掉线')}")
                missing = "、".join(str(x) for x in result.get("missing_adapters", []))
                if missing:
                    self._log(f"未保持运行的网卡：{missing}")
                for adapter_name, device_detail in dict(result.get("dropout_details", {})).items():
                    self._log(f"{adapter_name} 掉线时的 NetworkManager 状态：{device_detail}")
            self.last_health_signature = health_signature
            pending_detail = ""
            if result.get("pending_recovery"):
                count = int(result.get("pending_recovery_count", 1))
                pending_detail = f"｜有 {count} 份旧网卡设置待恢复，可点击‘重试残留恢复’"
            if result.get("started"):
                ssids = result.get("ssids") or ([result.get("ssid")] if result.get("ssid") else [])
                ssid = "、".join(str(x) for x in ssids) or "名称未读取"
                adapters = result.get("adapters") or ([result.get("adapter")] if result.get("adapter") else [])
                adapter_text = "、".join(str(x) for x in adapters) or "网卡未记录"
                active_count = int(result.get("active_count", 0)) or len(adapters) or 1
                assignment_confirmed = result.get("adapter_confirmed", True)
                if not assignment_confirmed:
                    adapter_text += "（系统未确认是否由它实际发射）"
                backend_text = result.get("backend_label", "系统热点")
                reported_band = str(result.get("band", ""))
                requested_band = str(result.get("requested_band", ""))
                configured_channels = [
                    int(value) for value in result.get("channels", []) if str(value).isdigit() and int(value) > 0
                ]
                if configured_channels and result.get("channels_confirmed"):
                    channel_suffix = "；信道 " + "、".join(str(value) for value in configured_channels)
                elif configured_channels:
                    channel_suffix = "；信道 " + "、".join(str(value) for value in configured_channels) + "（未复核）"
                else:
                    channel_suffix = "；信道系统未提供"
                if reported_band and result.get("band_confirmed", False):
                    actual_band = localized_band(reported_band) + channel_suffix
                elif reported_band or requested_band:
                    configured = localized_band(reported_band or requested_band)
                    actual_band = f"系统未确认（启动时设置为 {configured}{channel_suffix}）"
                else:
                    actual_band = "系统未提供（请用扫描设备确认）"
                self._set_hotspot_fields(adapter_text, ssid, actual_band, backend_text)
                notes: list[str] = []
                if degraded:
                    notes.append(str(result.get("status", "部分热点已经掉线")))
                if pending_detail:
                    notes.append(pending_detail.lstrip("｜"))
                self._set_hotspot_state(
                    True,
                    "；".join(notes),
                    degraded=degraded,
                    active_count=active_count,
                )
            else:
                backend_text = result.get("backend_label", "系统热点")
                self._set_hotspot_fields("—", "—", "—", backend_text)
                system_status = localized_tethering_status(str(result.get("status", "未启动")))
                detail = pending_detail.lstrip("｜") if pending_detail else ""
                if system_status not in {"未启动", "未启动（现代热点接口可用）"}:
                    detail = f"系统状态：{system_status}" + (f"；{detail}" if detail else "")
                self._set_hotspot_state(False, detail, degraded=degraded)
            self._update_tree_hotspot_state()

        if silent:
            self.status_polling = True

            def target() -> None:
                try:
                    self.events.put(("status_done", (worker(), done)))
                except Exception as exc:
                    self.events.put(("status_error", exc))

            threading.Thread(target=target, daemon=True).start()
        else:
            self._run_async("正在读取热点状态…", worker, done)

    def retry_pending_recovery(self) -> None:
        if self.platform_var.get() != "Windows":
            messagebox.showinfo(APP_TITLE, "残留恢复按钮仅用于 Windows 后端。")
            return

        def worker() -> None:
            self.backend.retry_pending_recovery(self.thread_log)

        def done(_: Any) -> None:
            self.status_var.set("残留设置恢复完成")
            self._log("Windows：残留设置恢复检查已完成。")
            self.refresh_hotspot_status(silent=True)

        self._run_async("正在重试残留恢复…", worker, done)

    def _poll_hotspot_status(self) -> None:
        if self.closing:
            return
        self.refresh_hotspot_status(silent=True)
        self.refresh_wifi_client_status(silent=True)
        try:
            self.after(10000, self._poll_hotspot_status)
        except tk.TclError:
            pass

    def _toggle_password_visibility(self) -> None:
        self.password_entry.configure(show="" if self.password_visible_var.get() else "●")

    def _toggle_client_password_visibility(self) -> None:
        if self.client_password_entry is not None:
            self.client_password_entry.configure(show="" if self.client_password_visible_var.get() else "●")

    @staticmethod
    def _bind_entry_edit_shortcuts(entry: ttk.Entry | tk.Entry) -> None:
        """统一 Linux/Windows 的 Ctrl+A 全选行为，便于直接覆盖粘贴。"""
        def select_all(event: Any) -> str:
            try:
                event.widget.selection_range(0, "end")
                event.widget.icursor("end")
            except tk.TclError:
                pass
            return "break"

        entry.bind("<Control-KeyPress-a>", select_all)
        entry.bind("<Control-KeyPress-A>", select_all)

    def _build_wifi_client_tab(self, parent: ttk.Frame) -> None:
        """构建常驻的 WiFi 客户端连接页面。"""
        ttk.Label(
            parent,
            text="多网卡连接同一个外部 WiFi 热点",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text="说明：这里是让无线网卡作为客户端连接外部热点；多块网卡都连上后，系统默认上网出口通常只会选择其中一块。",
            style="Hint.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        form = ttk.LabelFrame(parent, text="目标 WiFi", padding=8)
        form.pack(fill="x")
        ttk.Label(form, text="SSID").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        client_ssid_entry = ttk.Entry(form, textvariable=self.client_ssid_var, width=30)
        client_ssid_entry.grid(
            row=0, column=1, sticky="ew", padx=(0, 14), pady=4,
        )
        self._bind_entry_edit_shortcuts(client_ssid_entry)
        ttk.Label(form, text="密码").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        password_frame = ttk.Frame(form)
        password_frame.grid(row=0, column=3, sticky="ew", pady=4)
        self.client_password_entry = ttk.Entry(
            password_frame, textvariable=self.client_password_var, width=26, show="●",
        )
        self.client_password_entry.pack(side="left", fill="x", expand=True)
        self._bind_entry_edit_shortcuts(self.client_password_entry)
        ttk.Checkbutton(
            password_frame, text="显示", variable=self.client_password_visible_var,
            command=self._toggle_client_password_visibility,
        ).pack(side="left", padx=(6, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        middle = ttk.Frame(parent)
        middle.pack(fill="both", expand=True, pady=(8, 0))
        list_box = ttk.LabelFrame(middle, text="选择要连接的无线网卡（默认全选；状态同步更新，详细结果见底部运行日志）", padding=8)
        list_box.pack(fill="both", expand=True)
        operation_bar = ttk.Frame(list_box)
        operation_bar.pack(fill="x", pady=(0, 6))
        self.client_operation_label = ttk.Label(
            operation_bar,
            textvariable=self.client_operation_var,
            style="ClientReady.TLabel",
            anchor="w",
        )
        self.client_operation_label.pack(side="left", fill="x", expand=True)
        list_frame = ttk.Frame(list_box)
        list_frame.pack(fill="both", expand=True)
        self.client_adapter_listbox = tk.Listbox(
            list_frame, selectmode="extended", height=14, exportselection=False,
            font=("Microsoft YaHei UI", 10),
            background="#f8fafc", foreground="#1f2937",
            selectbackground="#c7dbf5", selectforeground="#1f2937",
            activestyle="none",
        )
        self.client_adapter_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.client_adapter_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.client_adapter_listbox.configure(yscrollcommand=scroll.set)
        self.client_adapter_listbox.bind(
            "<<ListboxSelect>>", self._preserve_client_selection_colors,
        )
        self._populate_client_adapter_listbox(select_all=True)

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="全选网卡", command=self._select_all_client_adapters).pack(side="left")
        ttk.Button(buttons, text="清空选择", command=self._clear_client_adapter_selection).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="刷新网卡列表", command=lambda: self.refresh(refresh_status=False)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="刷新并写入日志", command=self.refresh_wifi_client_status).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="连接选中网卡", command=self.connect_selected_wifi_clients).pack(side="right")
        ttk.Button(buttons, text="断开选中网卡", command=self.disconnect_selected_wifi_clients).pack(side="right", padx=(0, 8))
        # 进度条紧挨着连接/断开按钮，操作时能直观看到命令仍在运行。
        self.client_progress = ttk.Progressbar(
            buttons, mode="indeterminate", length=150,
        )

    def _set_client_progress(self, active: bool) -> None:
        """显示或隐藏 WIFI 客户端连接/断开操作的动态进度条。"""
        if self.client_progress is None:
            return
        try:
            if active:
                if not self.client_progress.winfo_manager():
                    self.client_progress.pack(side="right", padx=(10, 0))
                self.client_progress.start(10)
            else:
                self.client_progress.stop()
                self.client_progress.pack_forget()
        except tk.TclError:
            # 窗口正在关闭时，控件可能已经销毁。
            pass

    def open_wifi_client_window(self) -> None:
        """打开多网卡连接同一个外部 WiFi 的客户端窗口。"""
        if hasattr(self, "main_notebook"):
            self.main_notebook.select(1)
            self.refresh_wifi_client_status(silent=True)
            return
        if self.client_window is not None and self.client_window.winfo_exists():
            self.client_window.lift()
            self.client_window.focus_force()
            return
        window = tk.Toplevel(self)
        window.title("多网卡连接外部 WiFi")
        window.geometry("760x620")
        window.minsize(680, 520)
        window.transient(self)
        self.client_window = window

        outer = ttk.Frame(window, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="把多块无线网卡作为客户端，连接到同一个外部 WiFi 热点",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="说明：这会让网卡去连接别人的热点，不是让网卡发射热点；多网卡都连上后，系统默认上网出口通常只会选其中一块。",
            style="Hint.TLabel",
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        form = ttk.LabelFrame(outer, text="目标 WiFi", padding=8)
        form.pack(fill="x")
        ttk.Label(form, text="SSID").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        client_ssid_entry = ttk.Entry(form, textvariable=self.client_ssid_var, width=28)
        client_ssid_entry.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=4)
        self._bind_entry_edit_shortcuts(client_ssid_entry)
        ttk.Label(form, text="密码").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        password_frame = ttk.Frame(form)
        password_frame.grid(row=0, column=3, sticky="ew", pady=4)
        self.client_password_entry = ttk.Entry(
            password_frame, textvariable=self.client_password_var, width=24, show="●",
        )
        self.client_password_entry.pack(side="left", fill="x", expand=True)
        self._bind_entry_edit_shortcuts(self.client_password_entry)
        ttk.Checkbutton(
            password_frame, text="显示", variable=self.client_password_visible_var,
            command=self._toggle_client_password_visibility,
        ).pack(side="left", padx=(6, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        list_box = ttk.LabelFrame(outer, text="选择要连接的无线网卡（默认全选）", padding=8)
        list_box.pack(fill="both", expand=True, pady=(8, 0))
        list_frame = ttk.Frame(list_box)
        list_frame.pack(fill="both", expand=True)
        self.client_adapter_listbox = tk.Listbox(
            list_frame, selectmode="extended", height=10, exportselection=False,
            font=("Microsoft YaHei UI", 9),
            background="#f8fafc", foreground="#1f2937",
            selectbackground="#c7dbf5", selectforeground="#1f2937",
            activestyle="none",
        )
        self.client_adapter_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.client_adapter_listbox.yview)
        scroll.pack(side="right", fill="y")
        self.client_adapter_listbox.configure(yscrollcommand=scroll.set)
        self.client_adapter_listbox.bind(
            "<<ListboxSelect>>", self._preserve_client_selection_colors,
        )
        self._populate_client_adapter_listbox(select_all=True)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="全选网卡", command=self._select_all_client_adapters).pack(side="left")
        ttk.Button(buttons, text="清空选择", command=self._clear_client_adapter_selection).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="刷新列表", command=lambda: self._populate_client_adapter_listbox(select_all=True)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="刷新并写入日志", command=self.refresh_wifi_client_status).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="连接选中网卡", command=self.connect_selected_wifi_clients).pack(side="right")
        ttk.Button(buttons, text="断开选中网卡", command=self.disconnect_selected_wifi_clients).pack(side="right", padx=(0, 8))

        status_box = ttk.LabelFrame(outer, text="连接状态（每 10 秒自动刷新）", padding=8)
        status_box.pack(fill="both", expand=True, pady=(8, 0))
        self.client_status_text = tk.Text(
            status_box, height=7, wrap="word", state="disabled", font=("Consolas", 9),
            background="#0f172a", foreground="#dbeafe", insertbackground="white",
        )
        self.client_status_text.pack(side="left", fill="both", expand=True)
        status_scroll = ttk.Scrollbar(status_box, orient="vertical", command=self.client_status_text.yview)
        status_scroll.pack(side="right", fill="y")
        self.client_status_text.configure(yscrollcommand=status_scroll.set)
        self.refresh_wifi_client_status(silent=True)

        def on_close() -> None:
            self.client_window = None
            self.client_adapter_listbox = None
            self.client_password_entry = None
            self.client_status_text = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

    def _populate_client_adapter_listbox(self, select_all: bool = False) -> None:
        if self.client_adapter_listbox is None:
            return
        previous_selection = set(int(index) for index in self.client_adapter_listbox.curselection())
        self.client_adapter_listbox.delete(0, "end")
        self.client_row_colors = {}
        for row_index, adapter in enumerate(self.adapters):
            row = self.client_status_by_adapter.get(adapter.name, {})
            if row.get("connected") and row.get("target_match") is None:
                # 系统已经确认接口处于连接状态；SSID 读取受权限限制只影响
                # “连的是哪个热点”的核对，不应把已连接状态显示成黄色。
                status_icon = "●"
                status_text = "已连接（SSID未核对）"
                status_color = "#047857"
                extra = "｜系统已确认连接，SSID读取受限"
            elif row.get("connected"):
                status_icon = "●"
                status_text = "已连接"
                status_color = "#047857"
                ssid_text = str(row.get("ssid", "") or "SSID未读取")
                signal_text = str(row.get("signal", "") or "")
                extra = f"｜连接：{ssid_text}{f'｜信号：{signal_text}' if signal_text else ''}"
            elif row.get("target_visible"):
                signal = str(row.get("target_signal", "") or "")
                status_icon = "◉"
                status_text = "未连接"
                status_color = "#1d4ed8"
                extra = f"｜已扫描到目标热点{f'，信号 {signal}' if signal else ''}"
            elif row.get("warning"):
                warning = str(row.get("warning", ""))
                status_icon = "⚠"
                status_text = (
                    "扫描受权限限制"
                    if (
                        "位置" in warning
                        or "WlanQueryInterface" in warning
                        or "WLAN API" in warning
                        or "权限" in warning
                        or "拒绝访问" in warning
                    )
                    else "状态暂不可读"
                )
                status_color = "#b45309"
                extra = ""
            else:
                status_icon = "○"
                status_text = "未连接"
                status_color = "#64748b"
                extra = ""
            self.client_adapter_listbox.insert(
                "end",
                f"{status_icon} {adapter.index}. {adapter.name}｜{status_text}｜{adapter.description}{extra}",
            )
            self.client_row_colors[row_index] = status_color
            # Listbox 的全局 selectforeground 会覆盖普通 foreground。
            # 为每一行单独设置 selectforeground，选中时只改变底色，
            # 仍保留“已连接=绿色、扫描到=蓝色、异常=黄色”等状态字体颜色。
            # 这样用户可以同时看出“当前选择”和“网卡状态”。
            try:
                self.client_adapter_listbox.itemconfigure(
                    row_index,
                    foreground=status_color,
                    selectforeground=status_color,
                    # 选中只用浅底色标记所在行；字体颜色始终保留
                    # 当前网卡的连接/扫描/异常状态颜色。
                    selectbackground="#c7dbf5",
                    selectborderwidth=0,
                )
            except tk.TclError:
                # 兼容少数旧版 Tk：至少保留正常状态颜色。
                self.client_adapter_listbox.itemconfigure(
                    row_index,
                    foreground=status_color,
                )
        if select_all and self.adapters:
            self.client_adapter_listbox.selection_set(0, "end")
        elif previous_selection:
            for index in previous_selection:
                if 0 <= index < len(self.adapters):
                    self.client_adapter_listbox.selection_set(index)
        self._preserve_client_selection_colors()

    def _preserve_client_selection_colors(self, _event: Any = None) -> None:
        """选中只改变底色，保留每行原本的状态字体颜色。"""
        if self.client_adapter_listbox is None:
            return
        try:
            for row_index, status_color in self.client_row_colors.items():
                self.client_adapter_listbox.itemconfigure(
                    row_index,
                    selectforeground=status_color,
                    selectbackground="#c7dbf5",
                )
        except tk.TclError:
            pass

    def _set_client_operation(self, message: str, style: str = "ClientReady.TLabel") -> None:
        self.client_operation_var.set(message)
        if self.client_operation_label is not None:
            self.client_operation_label.configure(style=style)

    def _select_all_client_adapters(self) -> None:
        if self.client_adapter_listbox is not None and self.adapters:
            self.client_adapter_listbox.selection_set(0, "end")

    def _clear_client_adapter_selection(self) -> None:
        if self.client_adapter_listbox is not None:
            self.client_adapter_listbox.selection_clear(0, "end")

    def _selected_client_adapters(self) -> list[WifiAdapter]:
        if self.client_adapter_listbox is None:
            return []
        selected = [int(index) for index in self.client_adapter_listbox.curselection()]
        return [self.adapters[index] for index in selected if 0 <= index < len(self.adapters)]

    def refresh_wifi_client_status(self, silent: bool = False) -> None:
        if (
            self.client_status_polling
            or (silent and self.busy)
        ):
            return
        adapters = list(self.adapters)
        target_ssid = self.client_ssid_var.get().strip()
        self.client_status_polling = True
        if not silent:
            self._log("WiFi 客户端：正在读取各网卡实际连接状态…")

        def target() -> None:
            try:
                rows = self.backend.get_wifi_client_status(adapters, target_ssid=target_ssid)
                self.events.put((
                    "client_status_done",
                    {"rows": rows, "target_ssid": target_ssid, "silent": silent},
                ))
            except Exception as exc:
                self.events.put(("client_status_error", exc))

        threading.Thread(target=target, daemon=True).start()

    def _render_client_status_message(self, message: str) -> None:
        if self.client_status_text is None:
            if hasattr(self, "log_text"):
                self._log(message)
            return
        self.client_status_text.configure(state="normal")
        self.client_status_text.delete("1.0", "end")
        self.client_status_text.insert("end", message)
        self.client_status_text.configure(state="disabled")

    def _render_client_status_error(self, message: str) -> None:
        self._log(f"WiFi 客户端状态读取失败：{message}")
        # Windows 读取 WLAN 信息可能因为“位置服务”权限被拒绝。
        # 这是读取受限，不等于网卡已经断开，因此用黄色提示而不是红色失败。
        if "位置" in message or "WlanQueryInterface" in message or "拒绝访问" in message:
            self._set_client_operation(
                "⚠ 状态读取受限｜不代表已断开，请检查 Windows 位置权限",
                "ClientBusy.TLabel",
            )
        else:
            self._set_client_operation(
                "⚠ 状态读取失败｜请查看运行日志，10 秒后会自动重试",
                "ClientBad.TLabel",
            )
        if self.client_status_text is not None:
            self._render_client_status_message(f"状态读取失败：{message}")

    def _render_client_status(self, payload: dict[str, Any]) -> None:
        rows = list(payload.get("rows", []))
        target_ssid = str(payload.get("target_ssid", "")).strip()
        silent = bool(payload.get("silent"))
        lines: list[str] = []
        if target_ssid:
            lines.append(f"目标 SSID：{target_ssid}")
        else:
            lines.append("目标 SSID：未填写（仅显示当前连接状态）")
        lines.append(f"刷新时间：{time.strftime('%H:%M:%S')}")
        lines.append("")
        if not rows:
            lines.append("当前没有无线网卡。")
        warnings: list[str] = []
        for row in rows:
            adapter = str(row.get("adapter", ""))
            ssid = str(row.get("ssid", "") or "")
            state = str(row.get("state", "") or "未知")
            profile = str(row.get("profile", "") or "无")
            ip = str(row.get("ip", "") or "无")
            signal = str(row.get("signal", "") or "")
            connected = bool(row.get("connected"))
            target_match = row.get("target_match")
            target_visible = bool(row.get("target_visible"))
            target_signal = str(row.get("target_signal", "") or "")
            warning = str(row.get("warning", "") or "").strip()
            if warning and warning not in warnings:
                warnings.append(warning)
            if target_ssid:
                ok = target_match is True or (target_match is None and connected and ssid == target_ssid)
                if ok:
                    icon = "✅"
                    status = "已连接目标热点"
                elif (
                    not self.client_action_started
                    and not connected
                    and not target_visible
                ):
                    # 程序刚启动时只是自动读取状态，用户还没有点击“连接”；
                    # “当前未连接”不是一次失败操作，不使用红色失败提示。
                    icon = "○"
                    status = "尚未连接（尚未发起连接）"
                elif connected and target_match is None:
                    icon = "✅"
                    status = "已连接（真实 SSID 受权限限制，未核对）"
                elif connected:
                    icon = "⚠️"
                    status = "已连接其他热点"
                elif warning and (
                    "位置" in warning
                    or "WlanQueryInterface" in warning
                    or "WLAN API" in warning
                    or "权限" in warning
                    or "拒绝访问" in warning
                ):
                    # Windows 位置权限关闭时，扫描结果不可用；不能把
                    # “扫描不到”误报成“目标热点不存在”。
                    icon = "⚠️"
                    status = "未连接，扫描信息受 Windows 权限限制"
                elif target_visible:
                    icon = "🔎"
                    status = "未连接，但已扫描到目标热点"
                else:
                    icon = "❌"
                    status = "未连接，且当前扫描缓存未看到目标热点"
            else:
                icon = "✅" if connected else "❌"
                status = "已连接" if connected else "未连接"
            ssid_text = ssid or "未读取"
            if signal:
                signal_text = f"｜信号：{signal}"
            elif target_visible and target_signal:
                signal_text = f"｜目标热点信号：{target_signal}"
            else:
                signal_text = ""
            lines.append(
                f"{icon} {adapter}：{status}｜SSID：{ssid_text}"
                f"｜状态：{state}｜Profile：{profile}｜IP：{ip}{signal_text}"
            )
        self.client_status_by_adapter = {
            str(row.get("adapter", "")): dict(row)
            for row in rows
            if row.get("adapter")
        }
        self._populate_client_adapter_listbox(select_all=False)
        if warnings:
            lines.insert(2, "提示：" + " ".join(warnings))
        rendered = "\n".join(lines)
        connected_count = sum(
            1 for row in rows
            if bool(row.get("connected"))
            and (
                not target_ssid
                or row.get("target_match") is True
            )
        )
        unknown_target_count = sum(
            1 for row in rows
            if target_ssid
            and bool(row.get("connected"))
            and row.get("target_match") is None
        )
        if self.client_operation_pending:
            # 一次连接/断开操作结束后的第一次真实状态读取，给出明确结论。
            self.client_operation_pending = False
            pending_names = set(self.client_pending_adapter_names)
            pending_rows = [
                row for row in rows
                if not pending_names or str(row.get("adapter", "")) in pending_names
            ]
            pending_action = self.client_pending_action or "connect"
            self.client_pending_adapter_names.clear()
            self.client_pending_action = None
            if not pending_rows:
                self._set_client_operation(
                    "⚠ 已读取，但当前没有可用无线网卡",
                    "ClientBad.TLabel",
                )
            else:
                pending_total = len(pending_rows)
                pending_connected = sum(1 for row in pending_rows if bool(row.get("connected")))
                pending_target_connected = sum(
                    1 for row in pending_rows
                    if bool(row.get("connected"))
                    and (not target_ssid or row.get("target_match") is True)
                )
                pending_unknown = sum(
                    1 for row in pending_rows
                    if bool(row.get("connected"))
                    and target_ssid
                    and row.get("target_match") is None
                )
                if pending_action == "disconnect":
                    if pending_connected == 0:
                        self._set_client_operation(
                            f"✅ 已确认：{pending_total} 块选中网卡均已断开",
                            "ClientGood.TLabel",
                        )
                    elif pending_connected < pending_total:
                        self._set_client_operation(
                            f"⚠ 部分断开：仍有 {pending_connected}/{pending_total} 块选中网卡保持连接",
                            "ClientBusy.TLabel",
                        )
                    else:
                        self._set_client_operation(
                            f"❌ 仍未断开：{pending_connected}/{pending_total} 块选中网卡保持连接",
                            "ClientBad.TLabel",
                        )
                elif target_ssid and pending_target_connected == pending_total:
                    self._set_client_operation(
                        f"✅ 已确认：{pending_target_connected}/{pending_total} 块选中网卡已连接目标热点",
                        "ClientGood.TLabel",
                    )
                elif target_ssid and pending_target_connected:
                    self._set_client_operation(
                        f"⚠ 部分成功：{pending_target_connected}/{pending_total} 块选中网卡已连接目标热点",
                        "ClientBusy.TLabel",
                    )
                elif target_ssid and pending_unknown == pending_total:
                    self._set_client_operation(
                        f"⚠ {pending_unknown}/{pending_total} 块选中网卡已连接，但 Windows 未允许核对真实 SSID",
                        "ClientBusy.TLabel",
                    )
                elif target_ssid:
                    self._set_client_operation(
                        "❌ 未确认选中的网卡连接成功｜请查看列表状态和运行日志",
                        "ClientBad.TLabel",
                    )
                else:
                    self._set_client_operation(
                        f"已刷新实际状态｜选中网卡已连接 {pending_connected}/{pending_total}",
                        "ClientReady.TLabel",
                    )
        elif not silent:
            if target_ssid and rows and connected_count == len(rows):
                self._set_client_operation(
                    f"✅ 当前状态：{connected_count}/{len(rows)} 块网卡已连接目标热点",
                    "ClientGood.TLabel",
                )
            elif target_ssid and connected_count:
                self._set_client_operation(
                    f"⚠ 当前状态：{connected_count}/{len(rows)} 块网卡已连接目标热点",
                    "ClientBusy.TLabel",
                )
            elif target_ssid and unknown_target_count:
                self._set_client_operation(
                    f"✅ 当前已连接 {unknown_target_count}/{len(rows)} 块网卡（SSID受权限限制，暂未核对）",
                    "ClientGood.TLabel",
                )
            elif target_ssid and rows and not self.client_action_started:
                self._set_client_operation(
                    "○ 尚未发起连接｜当前仅显示网卡状态",
                    "ClientReady.TLabel",
                )
            elif target_ssid and rows:
                self._set_client_operation(
                    "❌ 当前没有网卡确认连接目标热点",
                    "ClientBad.TLabel",
                )
        elif rows and not self.busy:
            # 定时刷新只更新一行简短的“最近读取”提示，避免每 10 秒刷屏。
            self._set_client_operation(
                f"最近刷新 {time.strftime('%H:%M:%S')}｜Windows/Linux 每 10 秒自动检查",
                "ClientReady.TLabel",
            )
        signature = tuple(
            (
                row.get("adapter"), row.get("connected"), row.get("ssid"),
                row.get("target_match"),
                row.get("state"), row.get("profile"), row.get("ip"),
                row.get("target_visible"), row.get("target_signal"), row.get("warning"),
            )
            for row in rows
        )
        if not silent or signature != getattr(self, "last_client_status_signature", None):
            self._log("WiFi 客户端状态：\n" + rendered)
        self.last_client_status_signature = signature
        if self.client_status_text is not None:
            self.client_status_text.configure(state="normal")
            self.client_status_text.delete("1.0", "end")
            self.client_status_text.insert("end", rendered)
            self.client_status_text.configure(state="disabled")

    def connect_selected_wifi_clients(self) -> None:
        if self.busy:
            self._log("提示：正在执行上一项操作；底部进度条正在运行，可点击强制终止。")
            self.status_var.set("上一项操作仍在执行，请查看底部进度条")
            return
        adapters = self._selected_client_adapters()
        if not adapters:
            messagebox.showwarning(APP_TITLE, "请先选择至少一块无线网卡。")
            return
        ssid = self.client_ssid_var.get().strip()
        password = self.client_password_var.get()
        if not ssid:
            messagebox.showwarning(APP_TITLE, "请输入要连接的 WiFi SSID。")
            return
        self.client_action_started = True
        self.client_pending_adapter_names = {adapter.name for adapter in adapters}
        self.client_pending_action = "connect"
        names = "、".join(adapter.name for adapter in adapters)
        self.client_operation_pending = True
        self._set_client_operation(
            f"阶段 1/4：准备连接｜已选 {len(adapters)} 块网卡",
            "ClientBusy.TLabel",
        )
        self._render_client_status_message(
            f"阶段 1/4：准备连接\n\n目标 SSID：{ssid}\n网卡：{names}\n\n"
            "下一步将扫描并提交连接命令；命令完成后还会等待系统确认实际连接状态。"
        )
        self.status_var.set(f"正在连接 {len(adapters)} 块网卡到 WiFi…")
        self._log(f"WiFi 客户端：准备连接 {names} 到 {ssid}")
        self._set_client_operation("阶段 2/4：扫描目标 SSID并检查网卡状态", "ClientBusy.TLabel")
        self._render_client_status_message(
            f"阶段 2/4：扫描目标 SSID并检查网卡状态\n\n目标 SSID：{ssid}\n网卡：{names}\n\n"
            "正在执行连接，请等待底部运行日志出现每块网卡的结果。"
        )
        self._set_client_operation("阶段 3/4：提交连接命令并等待网卡响应", "ClientBusy.TLabel")
        self._render_client_status_message(
            f"阶段 3/4：提交连接命令并等待网卡响应\n\n目标 SSID：{ssid}\n网卡：{names}\n\n"
            "命令返回成功后，程序还会核对实际 SSID，避免把“命令已提交”误认为“已连接”。"
        )

        def worker() -> dict[str, str]:
            return self.backend.connect_wifi_adapters(adapters, ssid, password, self.thread_log)

        def done(result: dict[str, str]) -> None:
            self._set_client_progress(False)
            names = "、".join(result) or "无"
            self._log(f"WiFi 客户端连接请求已提交：{names}")
            self.status_var.set(f"连接请求已提交，正在确认 {len(result)} 块网卡的实际状态")
            self._set_client_operation(
                "阶段 4/4：等待系统确认实际连接状态（命令完成不等于已连接）",
                "ClientBusy.TLabel",
            )
            self._render_client_status_message(
                f"阶段 4/4：等待系统确认实际连接状态\n\n目标 SSID：{ssid}\n网卡：{names}\n\n"
                "连接请求已提交，程序正在读取实际连接状态；请以列表中的图标和状态为准。"
            )
            self.after(800, self.refresh)
            self.after(1000, lambda: self.refresh_wifi_client_status(silent=True))

        self._set_client_progress(True)
        self._run_async(f"正在连接 {len(adapters)} 块网卡到 WiFi…", worker, done)

    def disconnect_selected_wifi_clients(self) -> None:
        if self.busy:
            self._log("提示：正在执行上一项操作；底部进度条正在运行，可点击强制终止。")
            self.status_var.set("上一项操作仍在执行，请查看底部进度条")
            return
        adapters = self._selected_client_adapters()
        if not adapters:
            messagebox.showwarning(APP_TITLE, "请先选择至少一块无线网卡。")
            return
        self.client_action_started = True
        self.client_pending_adapter_names = {adapter.name for adapter in adapters}
        self.client_pending_action = "disconnect"
        names = "、".join(adapter.name for adapter in adapters)
        self.client_operation_pending = True
        self._set_client_operation(
            f"阶段 1/2：准备断开｜已选 {len(adapters)} 块网卡",
            "ClientBusy.TLabel",
        )
        self._render_client_status_message(
            f"阶段 1/2：准备断开\n\n网卡：{names}\n\n"
            "正在提交断开命令，完成后还会读取系统实际状态。"
        )
        self.status_var.set(f"正在断开 {len(adapters)} 块网卡的 WiFi…")
        self._log(f"WiFi 客户端：准备断开 {names}")

        def worker() -> dict[str, str]:
            return self.backend.disconnect_wifi_adapters(adapters, self.thread_log)

        def done(result: dict[str, str]) -> None:
            self._set_client_progress(False)
            names = "、".join(result) or "无"
            self._log(f"WiFi 客户端断开完成：{names}")
            self.status_var.set(f"断开命令已完成，正在确认 {len(result)} 块网卡的实际状态")
            self._set_client_operation(
                "阶段 2/2：等待系统确认已经断开",
                "ClientBusy.TLabel",
            )
            self._render_client_status_message(
                f"阶段 2/2：等待系统确认已经断开\n\n网卡：{names}\n\n"
                "断开命令已完成，程序正在读取实际状态；请以列表中的图标和状态为准。"
            )
            self.after(800, self.refresh)
            self.after(1000, lambda: self.refresh_wifi_client_status(silent=True))

        self._set_client_progress(True)
        self._run_async(f"正在断开 {len(adapters)} 块网卡的 WiFi…", worker, done)

    def _tree_action_click(self, event: Any) -> str | None:
        """点击最后一列时，只启动或停止这一行对应的热点。"""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None
        adapter = next((item for item in self.adapters if str(item.index) == item_id), None)
        if not adapter:
            return None
        self._select_adapter(adapter)
        self.tree.focus(item_id)
        if self.tree.identify_column(event.x) == "#8":
            self.after_idle(lambda: self._toggle_hotspot_for_adapter(adapter))
            return "break"
        return None

    def _tree_motion(self, event: Any) -> None:
        is_action = (
            self.tree.identify_region(event.x, event.y) == "cell"
            and self.tree.identify_column(event.x) == "#8"
            and bool(self.tree.identify_row(event.y))
        )
        self.tree.configure(cursor="hand2" if is_action else "")

    def _adapter_hotspot_running(self, adapter: WifiAdapter) -> bool:
        if not self.hotspot_status.get("started"):
            return False
        active_adapters = set(self.hotspot_status.get("adapters", []))
        active_adapter = str(self.hotspot_status.get("adapter", ""))
        return adapter.name in active_adapters or adapter.name == active_adapter

    def _hotspot_assignment_unknown(self) -> bool:
        return bool(
            self.hotspot_status.get("started")
            and not self.hotspot_status.get("adapter")
            and not self.hotspot_status.get("adapters")
        )

    def _toggle_hotspot_for_adapter(self, adapter: WifiAdapter) -> None:
        if self.busy:
            self._log("提示：正在执行上一项操作；底部进度条正在运行，可点击强制终止。")
            self.status_var.set("上一项操作仍在执行，请查看底部进度条")
            return
        if self._hotspot_assignment_unknown():
            if self.platform_var.get() == "Linux":
                messagebox.showwarning(
                    APP_TITLE,
                    "NetworkManager 当前报告热点正在运行，但暂时无法确认它属于哪块网卡。\n\n"
                    "为避免误停其他热点，本次没有执行停止操作。程序将重新读取状态，请稍后再点击目标行。",
                )
                self.refresh_hotspot_status(silent=True)
                return
            # Windows 系统热点是单实例，归属不明时只能调用系统级停止。
            self.stop_all_hotspots()
        elif self._adapter_hotspot_running(adapter):
            self.stop_hotspot(adapter)
        else:
            self.start_hotspot(adapter)

    def _channel_display(self, adapter: WifiAdapter) -> str:
        running_channel = self._active_status_value_for_adapter(adapter, "channels", "channel")
        if self._adapter_hotspot_running(adapter):
            confirmed = bool(
                self._active_status_value_for_adapter(adapter, "channel_confirmed", "channel_confirmed")
            )
            if confirmed and str(running_channel or "").isdigit() and int(running_channel) > 0:
                return str(int(running_channel))
            if str(running_channel or "").isdigit() and int(running_channel) > 0:
                return f"{int(running_channel)}（未复核）"
            return "系统未提供"
        return "自动"

    def _active_status_value_for_adapter(
        self, adapter: WifiAdapter, plural_key: str, singular_key: str,
    ) -> Any:
        """读取与运行网卡下标对应的状态字段，避免多热点数据错位。"""
        active_adapters = list(self.hotspot_status.get("adapters") or [])
        if adapter.name in active_adapters:
            index = active_adapters.index(adapter.name)
            values = list(self.hotspot_status.get(plural_key) or [])
            if index < len(values):
                return values[index]
        if adapter.name == str(self.hotspot_status.get("adapter", "")):
            return self.hotspot_status.get(singular_key)
        return None

    def _ssid_display_for_adapter(self, adapter: WifiAdapter) -> str:
        active_ssid = self._active_status_value_for_adapter(adapter, "ssids", "ssid")
        if active_ssid:
            return str(active_ssid)
        return make_ssid(self.ssid_prefix_var.get(), adapter.index, self.band_var.get())

    def _render_adapter_row(self, item: WifiAdapter) -> None:
        if not self.tree.exists(str(item.index)):
            return
        hotspot_text = "● 已关闭"
        hotspot_tag = "hotspot_stopped"
        action_text = "▶ 启动此热点"
        adapter_status = localized_adapter_status(item.status)
        active_adapter = str(self.hotspot_status.get("adapter", ""))
        active_adapters = set(self.hotspot_status.get("adapters", []))
        missing_adapters = set(self.hotspot_status.get("missing_adapters", []))
        if self.hotspot_status.get("degraded") and item.name in missing_adapters:
            hotspot_text = "● 已掉线"
            hotspot_tag = "hotspot_degraded"
            action_text = "▶ 重新启动"
            if not adapter_status_is_disabled(item.status):
                adapter_status = "已启用（热点已掉线）"
        elif self.hotspot_status.get("started"):
            assignment_confirmed = self.hotspot_status.get("adapter_confirmed", True)
            if not assignment_confirmed and active_adapter == item.name:
                hotspot_text = "● 运行中（网卡待确认）"
                hotspot_tag = "hotspot_unknown"
                action_text = "■ 停止此热点"
                adapter_status = "已启用（系统热点运行中）"
            elif item.name in active_adapters or active_adapter == item.name:
                hotspot_text = "● 运行中"
                hotspot_tag = "hotspot_running"
                action_text = "■ 停止此热点"
                adapter_status = "已启用（热点运行中）"
            elif not active_adapter and not active_adapters:
                hotspot_text = "● 系统热点运行中（网卡未知）"
                hotspot_tag = "hotspot_unknown"
                action_text = "■ 停止系统热点"
        if (
            adapter_status_is_disabled(item.status)
            and not self._adapter_hotspot_running(item)
            and not self._hotspot_assignment_unknown()
        ):
            hotspot_text = "— 网卡已禁用"
            hotspot_tag = "hotspot_unknown"
            action_text = "请先启用网卡"
        is_selected = item.index == self.selected_adapter_index
        sequence_text = f"▶ {item.index}" if is_selected else str(item.index)
        row_tag = f"selected_{hotspot_tag}" if is_selected else hotspot_tag
        self.tree.item(
            str(item.index),
            values=(
                sequence_text, item.name, item.description, adapter_status,
                self._channel_display(item), hotspot_text,
                self._ssid_display_for_adapter(item), action_text,
            ),
            tags=(row_tag,),
        )

    def _update_tree_hotspot_state(self) -> None:
        for item in self.adapters:
            self._render_adapter_row(item)

    def selected_adapter(self) -> WifiAdapter | None:
        if self.selected_adapter_index is None:
            return None
        return next((item for item in self.adapters if item.index == self.selected_adapter_index), None)

    def _adapter_identity(self, adapter: WifiAdapter) -> str:
        """生成会话内稳定身份；刷新时用它保持同一块网卡的序号不变。"""
        platform_name = self.platform_var.get() if hasattr(self, "platform_var") else CURRENT_PLATFORM
        if platform_name == "Windows" and adapter.guid:
            key = adapter.guid.strip().lower()
        else:
            key = adapter.name.strip().lower() or adapter.guid.strip().lower()
        return f"{platform_name}:{key}"

    def _stabilize_adapter_order(self, adapters: list[WifiAdapter]) -> list[WifiAdapter]:
        for adapter in adapters:
            identity = self._adapter_identity(adapter)
            if identity not in self.adapter_order:
                self.adapter_order[identity] = self.next_adapter_index
                self.next_adapter_index += 1
            adapter.index = self.adapter_order[identity]
        return sorted(adapters, key=lambda item: item.index)

    def refresh(self, refresh_status: bool = False) -> None:
        old_selected = self.selected_adapter().name if hasattr(self, "tree") and self.selected_adapter() else ""

        def worker() -> tuple[list[WifiAdapter], list[str]]:
            return self.backend.list_wifi_adapters(), self.backend.list_share_sources()

        def done(result: tuple[list[WifiAdapter], list[str]]) -> None:
            adapters, sources = result
            adapters = self._stabilize_adapter_order(adapters)
            self.adapters = adapters
            self.tree.delete(*self.tree.get_children())
            for item in adapters:
                self.tree.insert(
                    "", "end", iid=str(item.index),
                    values=(
                        item.index, item.name, item.description, localized_adapter_status(item.status),
                        self._channel_display(item), "", item.default_ssid, "",
                    ),
                )
                self._render_adapter_row(item)
            self.source_combo["values"] = sources
            if sources and self.source_var.get() not in sources:
                self.source_var.set(sources[0])
            elif not sources:
                self.source_var.set("")
            if adapters:
                selected = next((item for item in adapters if item.name == old_selected), adapters[0])
                self._select_adapter(selected)
                self.tree.focus(str(selected.index))
            else:
                self.selected_adapter_index = None
                self.selected_adapter_var.set("当前没有可用无线网卡")
                self.ssid_var.set("")
            self._populate_client_adapter_listbox(select_all=True)
            self._log(f"刷新完成：发现 {len(adapters)} 块无线网卡；可共享 LAN：{', '.join(sources) or '无'}")
            if refresh_status:
                self.after(0, lambda: self.refresh_hotspot_status(silent=True))
            self.after(200, lambda: self.refresh_wifi_client_status(silent=True))

        self._run_async("正在扫描网卡…", worker, done)

    def _select_adapter(self, adapter: WifiAdapter | None) -> None:
        old_index = self.selected_adapter_index
        self.selected_adapter_index = adapter.index if adapter else None
        if hasattr(self, "tree"):
            try:
                self.tree.selection_remove(self.tree.selection())
            except tk.TclError:
                pass
        for index in {old_index, self.selected_adapter_index}:
            if index is None:
                continue
            item = next((candidate for candidate in self.adapters if candidate.index == index), None)
            if item:
                self._render_adapter_row(item)
        if adapter:
            self.selected_adapter_var.set(
                f"当前选择：{adapter.name}（第 {adapter.index} 块）"
            )
            self.ssid_var.set(make_ssid(self.ssid_prefix_var.get(), adapter.index, self.band_var.get()))
            self._update_tree_ssid_preview()

    def _on_select(self, _event: Any = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        try:
            index = int(selected[0])
        except (TypeError, ValueError):
            return
        adapter = next((item for item in self.adapters if item.index == index), None)
        if adapter:
            self._select_adapter(adapter)

    def _band_changed(self) -> None:
        adapter = self.selected_adapter()
        if adapter:
            self.ssid_var.set(make_ssid(self.ssid_prefix_var.get(), adapter.index, self.band_var.get()))
        self._update_tree_hotspot_state()

    def _schedule_prefix_changed(self) -> None:
        """合并连续键盘输入，避免每个字符都同步重绘整张网卡表。"""
        if self.prefix_update_after_id is not None:
            try:
                self.after_cancel(self.prefix_update_after_id)
            except tk.TclError:
                pass
        self.prefix_update_after_id = self.after(180, self._prefix_changed)

    def _prefix_changed(self) -> None:
        self.prefix_update_after_id = None
        adapter = self.selected_adapter() if hasattr(self, "tree") else None
        if adapter:
            self.ssid_var.set(make_ssid(self.ssid_prefix_var.get(), adapter.index, self.band_var.get()))
        if hasattr(self, "tree"):
            self._update_tree_ssid_preview()

    def _update_tree_ssid_preview(self) -> None:
        if not hasattr(self, "tree"):
            return
        for item in self.adapters:
            self._render_adapter_row(item)

    def _toggle_adapter(self, enabled: bool) -> None:
        adapter = self.selected_adapter()
        if not adapter:
            messagebox.showwarning(APP_TITLE, "请先选择一块无线网卡。")
            return
        assignment_uncertain = bool(
            self.hotspot_status.get("started")
            and (
                self._hotspot_assignment_unknown()
                or not self.hotspot_status.get("adapter_confirmed", True)
            )
        )
        if not enabled and assignment_uncertain:
            messagebox.showwarning(
                APP_TITLE,
                "系统热点正在运行，但系统无法可靠确认实际发射网卡。\n\n"
                "为避免误关正在发射的网卡，请先在表格最后一列停止系统热点，再禁用网卡。",
            )
            return
        if not enabled and self._adapter_hotspot_running(adapter):
            messagebox.showwarning(
                APP_TITLE,
                f"{adapter.name} 的热点仍在运行。请先点击该行最后一列的“停止热点”，再禁用网卡。",
            )
            return

        def worker() -> str:
            return self.backend.set_adapter_enabled(adapter.name, enabled)

        def done(status: str) -> None:
            self._log(
                f"{adapter.name} 已{'启用' if enabled else '禁用'}，"
                f"系统状态：{localized_adapter_status(status)}"
            )
            self.after(500, self.refresh)

        self._run_async(f"正在{'启用' if enabled else '禁用'} {adapter.name}…", worker, done)

    def start_hotspot(self, adapter: WifiAdapter | None = None) -> None:
        adapter = adapter or self.selected_adapter()
        if not adapter:
            messagebox.showwarning(APP_TITLE, "请先选择一块无线网卡。")
            return
        if adapter_status_is_disabled(adapter.status):
            messagebox.showwarning(APP_TITLE, f"{adapter.name} 当前已禁用，请先点击“启用当前网卡”。")
            return
        if adapter.status.lower() == "not present":
            messagebox.showwarning(APP_TITLE, f"{adapter.name} 当前未插入，无法启动热点。")
            return
        if self._adapter_hotspot_running(adapter):
            messagebox.showinfo(APP_TITLE, f"{adapter.name} 的热点已经在运行。")
            return
        if self.platform_var.get() == "Windows" and self.hotspot_status.get("started"):
            active_adapter = str(self.hotspot_status.get("adapter", "")) or "当前系统热点"
            if not messagebox.askyesno(
                APP_TITLE,
                "Windows 同一时间只能运行一个系统热点。\n\n"
                f"继续操作会先停止 {active_adapter}，再尝试使用 {adapter.name} 启动。是否继续？",
            ):
                return
        prefix = self.ssid_prefix_var.get().strip()
        if not prefix:
            messagebox.showwarning(APP_TITLE, "热点名称前缀不能为空。")
            return
        requested_band = self.band_var.get()
        values = (
            self.source_var.get().strip(), make_ssid(prefix, adapter.index, requested_band), self.password_var.get(),
            requested_band, self.isolate_var.get(),
        )

        def worker() -> dict[str, Any]:
            self.backend.start_hotspot(
                adapter, *values, log=self.thread_log, channel=0,
            )
            result = self.backend.get_hotspot_status()
            if not result.get("started"):
                raise HotspotError("启动命令已执行，但系统复核时没有发现仍在运行的热点。")
            if self.platform_var.get() == "Linux" and adapter.name not in set(result.get("adapters", [])):
                raise HotspotError(f"系统中有其他热点运行，但没有确认 {adapter.name} 的热点启动成功。")
            return result

        def done(result: dict[str, Any]) -> None:
            self.status_var.set(f"已启动 {adapter.name}：{values[1]}")
            self.hotspot_status = result
            self._update_tree_hotspot_state()
            self.refresh_hotspot_status(silent=True)
            active_adapters = result.get("adapters") or ([result.get("adapter")] if result.get("adapter") else [])
            actual_count = len(active_adapters) or 1
            confirmation = ""
            if self.platform_var.get() == "Windows" and not result.get("adapter_confirmed", True):
                confirmation = "\n注意：Windows 已启动系统热点，但不能可靠确认实际物理发射网卡。"
            actual_channel = self._active_status_value_for_adapter(adapter, "channels", "channel")
            channel_confirmed = bool(self._active_status_value_for_adapter(adapter, "channel_confirmed", "channel_confirmed"))
            if channel_confirmed and str(actual_channel or "").isdigit() and int(actual_channel) > 0:
                confirmation += f"\n系统读取到实际发射信道：{int(actual_channel)}。"
            else:
                confirmation += "\n信道由系统和网卡自动协商；实际信道请以系统读取或扫描工具为准。"
            messagebox.showinfo(
                APP_TITLE,
                f"已完成当前网卡的热点启动\n\n网卡：{adapter.name}\n热点名称：{values[1]}\n"
                f"请求频段：{values[3]}\n共享网络：{values[0]}\n"
                f"当前总运行数量：{actual_count}{confirmation}",
            )

        self._run_async(f"正在启动 {adapter.name} 的热点…", worker, done)

    def stop_hotspot(self, adapter: WifiAdapter | None = None) -> None:
        adapter = adapter or self.selected_adapter()
        if not adapter:
            messagebox.showwarning(APP_TITLE, "请先选择一块无线网卡。")
            return
        if not self._adapter_hotspot_running(adapter):
            messagebox.showinfo(APP_TITLE, f"{adapter.name} 当前没有运行热点。")
            self.refresh_hotspot_status(silent=True)
            return

        def worker() -> None:
            self.backend.stop_hotspots([adapter], restore=True, log=self.thread_log)

        def done(_: Any) -> None:
            self.status_var.set(f"已停止 {adapter.name} 的热点")
            self._set_hotspot_state(None, f"已停止 {adapter.name}，正在重新读取全部热点状态")
            self.after(300, lambda: self.refresh(refresh_status=True))

        self._run_async(f"正在停止 {adapter.name} 的热点…", worker, done)

    def stop_all_hotspots(self) -> None:
        if not self.hotspot_status.get("started"):
            messagebox.showinfo(APP_TITLE, "当前没有正在运行的热点。")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "系统正在运行热点，但无法确认对应的物理网卡。\n\n是否停止本程序能够识别到的全部热点？",
        ):
            return

        def worker() -> None:
            self.backend.stop_hotspots([], restore=True, log=self.thread_log)

        def done(_: Any) -> None:
            self.status_var.set("已停止系统热点")
            self._set_hotspot_state(None, "已执行停止命令，正在重新读取全部热点状态")
            self.after(300, lambda: self.refresh(refresh_status=True))

        self._run_async("正在停止系统热点…", worker, done)


def main() -> None:
    if CURRENT_PLATFORM == "Unsupported":
        raise SystemExit("当前操作系统不受支持，仅支持 Windows 和 Linux。")
    non_admin_windows = os.name == "nt" and not is_admin()
    if not acquire_single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, "程序已经在运行。请先使用现有窗口，避免两个实例同时修改热点和网络共享。")
        root.destroy()
        raise SystemExit("检测到另一个正在运行的实例。")
    app = HotspotApp()
    if non_admin_windows:
        # 不再在启动入口静默 ShellExecuteW("runas") 后让 IDE 只看到
        # “退出代码 0”。普通用户权限足够读取网卡、连接外部 WiFi；
        # 需要管理员权限的热点/网卡启停操作会由具体命令返回明确提示。
        app._log(
            "提示：当前 Windows 不是管理员权限运行。"
            "WiFi 连接和状态读取可以继续；若热点启停/网卡启禁用提示权限不足，"
            "请右键 Python 或启动脚本选择“以管理员身份运行”。"
        )
    app.mainloop()


if __name__ == "__main__":
    main()
