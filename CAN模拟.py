import ctypes
import os
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from ctypes import wintypes
from tkinter import scrolledtext, ttk


# ====================== CAN盒配置 ======================
# winusb: 直接通过 WinUSB 访问珠海创芯 USB-CAN/CANalyst-II
# mock: 不连硬件，软件自动生成OBD请求，方便验证界面和协议逻辑
CAN_BACKEND = "winusb"

WINUSB_VID = 0x04D8
WINUSB_PID = 0x0053
CAN_CHANNEL_INDEX = 0
CAN_BITRATE = 500000
CAN_ID_FORMAT = "11bit"

# ====================== OBD仿真配置 ======================
VIN = "LSIM2026071300001"  # 必须17位，VIN查询会用ISO-TP多帧返回
ECU_RESPONSE_ID = 0x7E8
FUNCTIONAL_REQUEST_ID = 0x7DF
PHYSICAL_REQUEST_BASE = 0x7E0
PHYSICAL_REQUEST_END = 0x7E7
RESPOND_EXTENDED_29BIT = True
SUPPORTED_BITRATES = {250000, 500000}
SUPPORTED_ID_FORMATS = {"11bit", "29bit"}
EXT_FUNCTIONAL_REQUEST_BASE = 0x18DB3300
EXT_PHYSICAL_REQUEST_BASE = 0x18DA0000
EXT_OBD_ECU_ADDR = 0x10
CAN_BOX_STATUS_IDS = {0x01020800, 0x01020801}
DUPLICATE_REQUEST_TX_GAP_SEC = 0.12
USB_CAN_TX_MID = bytes.fromhex("A8 A8 3F DA")
USB_CAN_TX_TRAILER = bytes.fromhex("8B 02 00 00")

SPEED_RISE_MAX = 255
SPEED_STA_MIN = 0
SPEED_STA_MAX = 255
SPEED_STEP_KMH = 1.0
DEFAULT_SPEED = 179.0
DEFAULT_RPM = 4500
RPM_MIN = 4500
RPM_MAX = 6000
RPM_STEP = 1
DATA_UPDATE_INTERVAL = 0.28

SIM_PROFILES = {
    ("11bit", 500000): {
        "tx_mid": bytes.fromhex("A8 A8 3F DA"),
        "tx_trailer": bytes.fromhex("8B 02 00 00"),
        "speed_start": 179.0,
        "rpm_start": 4500,
    },
    ("11bit", 250000): {
        "tx_mid": bytes.fromhex("E8 F7 B7 0A"),
        "tx_trailer": bytes.fromhex("22 01 00 00"),
        "speed_start": 31.0,
        "rpm_start": 134,
    },
    ("29bit", 500000): {
        "tx_mid": bytes.fromhex("A8 D1 14 A7"),
        "tx_trailer": bytes.fromhex("52 01 00 00"),
        "speed_start": 44.0,
        "rpm_start": 146,
    },
    ("29bit", 250000): {
        "tx_mid": bytes.fromhex("A8 D1 14 A7"),
        "tx_trailer": bytes.fromhex("52 01 00 00"),
        "speed_start": 151.0,
        "rpm_start": 351,
    },
}

COOLANT_TEMP_C = 17
FUEL_LEVEL_PERCENT = 93
THROTTLE_PERCENT = 93
CALCULATED_LOAD_PERCENT = 6
MAF_GPS = 0.18
INTAKE_AIR_TEMP_C = -23
INTAKE_PRESSURE_KPA = 17
RUN_TIME_SEC = 17
MIL_DISTANCE_KM = 17
CLEAR_DISTANCE_KM = 17
FUEL_RATE_LPH = 0.85
FUEL_TYPE = 17
ABSOLUTE_LOAD_PERCENT = 17
HYBRID_SOC_PERCENT = 93.3
OIL_TEMP_C = -23
SHORT_FUEL_TRIM_BANK1_PERCENT = 0
LONG_FUEL_TRIM_BANK1_PERCENT = 0
SHORT_FUEL_TRIM_BANK2_PERCENT = 0
LONG_FUEL_TRIM_BANK2_PERCENT = 0
O2_SENSOR_VOLTAGE_V = 0.45
FUEL_PRESSURE_KPA = 51
AMBIENT_AIR_TEMP_C = -23
ODO_KM = 50
BATTERY_SOH_PERCENT = 98
BATTERY_CURRENT_A = 0.0
BATTERY_VOLTAGE_V = 12.6
BATTERY_TEMP_C = 25
CATALYST_TEMP_C = 350
FUEL_RAIL_PRESSURE_KPA = 3000
EVAP_PRESSURE_PA = 0
BAROMETRIC_PRESSURE_KPA = 101
CONTROL_MODULE_VOLTAGE_V = 13.8
COMMANDED_EQUIV_RATIO = 1.0
MAX_AIR_FLOW_GPS = 655
ETHANOL_PERCENT = 0
ABSOLUTE_EVAP_PRESSURE_KPA = 100
BATTERY_PACK_CHARGING_STATE = 0
TURN_SIGNAL_STATUS = 0

# Mode 01 is the standard J1979/ISO15765 PID space, so keep it broad.
# Grey UI items are filtered by not answering private UDS DID / private CAN IDs,
# not by shrinking Mode 01 compatibility.
SUPPORTED_MODE01_PIDS = set(range(0x01, 0x24))
SUPPORTED_MODE01_PIDS.update(range(0x24, 0x2C))
SUPPORTED_MODE01_PIDS.update(range(0x2C, 0x34))
SUPPORTED_MODE01_PIDS.update(range(0x34, 0x40))
SUPPORTED_MODE01_PIDS.update(range(0x40, 0x50))
SUPPORTED_MODE01_PIDS.update(range(0x50, 0x60))
SUPPORTED_MODE01_PIDS.update({0x60, 0x62, 0x66, 0x80, 0x9A, 0xA0, 0xA6, 0xB2, 0xB7})
SUPPORTED_MODE01_MASK_PIDS = {0x00, 0x20, 0x40, 0x60, 0x80, 0xA0}

DEFAULT_MODE01_PID_VALUES = {
    0x02: 0,
    0x03: 2,
    0x04: CALCULATED_LOAD_PERCENT,
    0x05: COOLANT_TEMP_C,
    0x06: SHORT_FUEL_TRIM_BANK1_PERCENT,
    0x07: LONG_FUEL_TRIM_BANK1_PERCENT,
    0x08: SHORT_FUEL_TRIM_BANK2_PERCENT,
    0x09: LONG_FUEL_TRIM_BANK2_PERCENT,
    0x0A: FUEL_PRESSURE_KPA,
    0x0B: INTAKE_PRESSURE_KPA,
    0x0C: DEFAULT_RPM,
    0x0D: DEFAULT_SPEED,
    0x0E: 0,
    0x0F: INTAKE_AIR_TEMP_C,
    0x10: MAF_GPS,
    0x11: THROTTLE_PERCENT,
    0x12: 1,
    0x13: 0x03,
    0x14: O2_SENSOR_VOLTAGE_V,
    0x15: O2_SENSOR_VOLTAGE_V,
    0x16: O2_SENSOR_VOLTAGE_V,
    0x17: O2_SENSOR_VOLTAGE_V,
    0x18: O2_SENSOR_VOLTAGE_V,
    0x19: O2_SENSOR_VOLTAGE_V,
    0x1A: O2_SENSOR_VOLTAGE_V,
    0x1B: O2_SENSOR_VOLTAGE_V,
    0x1C: 6,
    0x1D: 0x03,
    0x1E: 0,
    0x1F: RUN_TIME_SEC,
    0x21: MIL_DISTANCE_KM,
    0x22: FUEL_RAIL_PRESSURE_KPA,
    0x23: FUEL_RAIL_PRESSURE_KPA,
    0x2F: FUEL_LEVEL_PERCENT,
    0x30: 1,
    0x31: CLEAR_DISTANCE_KM,
    0x32: EVAP_PRESSURE_PA,
    0x33: BAROMETRIC_PRESSURE_KPA,
    0x43: ABSOLUTE_LOAD_PERCENT,
    0x44: COMMANDED_EQUIV_RATIO,
    0x45: THROTTLE_PERCENT,
    0x46: AMBIENT_AIR_TEMP_C,
    0x47: THROTTLE_PERCENT,
    0x48: THROTTLE_PERCENT,
    0x49: THROTTLE_PERCENT,
    0x4A: THROTTLE_PERCENT,
    0x4B: THROTTLE_PERCENT,
    0x4C: THROTTLE_PERCENT,
    0x4D: RUN_TIME_SEC,
    0x4E: CLEAR_DISTANCE_KM,
    0x50: MAX_AIR_FLOW_GPS,
    0x51: FUEL_TYPE,
    0x52: ETHANOL_PERCENT,
    0x53: ABSOLUTE_EVAP_PRESSURE_KPA,
    0x54: EVAP_PRESSURE_PA,
    0x5B: HYBRID_SOC_PERCENT,
    0x5C: OIL_TEMP_C,
    0x5D: 0,
    0x5E: FUEL_RATE_LPH,
    0x5F: 0,
    0x62: 0,
    0x9A: 0,
    0xA6: ODO_KM,
    0xB2: BATTERY_SOH_PERCENT,
    0xB7: BATTERY_TEMP_C,
}
for _pid in range(0x24, 0x2C):
    DEFAULT_MODE01_PID_VALUES.setdefault(_pid, COMMANDED_EQUIV_RATIO)
for _pid in range(0x2C, 0x2F):
    DEFAULT_MODE01_PID_VALUES.setdefault(_pid, 0)
for _pid in range(0x34, 0x3C):
    DEFAULT_MODE01_PID_VALUES.setdefault(_pid, COMMANDED_EQUIV_RATIO)
for _pid in range(0x3C, 0x40):
    DEFAULT_MODE01_PID_VALUES.setdefault(_pid, CATALYST_TEMP_C)
for _pid in range(0x55, 0x59):
    DEFAULT_MODE01_PID_VALUES.setdefault(_pid, 0)
for _pid in (0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x5A):
    DEFAULT_MODE01_PID_VALUES.setdefault(_pid, THROTTLE_PERCENT)


@dataclass
class CanMessage:
    arbitration_id: int
    data: list[int]
    is_extended_id: bool = False
    timestamp: int = 0


@dataclass
class TxItem:
    message: CanMessage
    delay_ms: int = 0


@dataclass
class PendingIsoTp:
    response_id: int
    is_extended_id: bool
    remaining: list[int]
    next_sn: int = 1


def fmt_frame(msg: CanMessage) -> str:
    data = " ".join(f"{byte:02X}" for byte in msg.data)
    frame_type = "EXT" if msg.is_extended_id else "STD"
    width = 8 if msg.is_extended_id else 3
    return f"{frame_type} ID:{msg.arbitration_id:0{width}X} DATA:{data}"


def pad8(data: list[int]) -> list[int]:
    return (data[:8] + [0x00] * 8)[:8]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1024),
    ]


class USB_INTERFACE_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_ubyte),
        ("bDescriptorType", ctypes.c_ubyte),
        ("bInterfaceNumber", ctypes.c_ubyte),
        ("bAlternateSetting", ctypes.c_ubyte),
        ("bNumEndpoints", ctypes.c_ubyte),
        ("bInterfaceClass", ctypes.c_ubyte),
        ("bInterfaceSubClass", ctypes.c_ubyte),
        ("bInterfaceProtocol", ctypes.c_ubyte),
        ("iInterface", ctypes.c_ubyte),
    ]


class WINUSB_PIPE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PipeType", ctypes.c_int),
        ("PipeId", ctypes.c_ubyte),
        ("MaximumPacketSize", ctypes.c_ushort),
        ("Interval", ctypes.c_ubyte),
    ]


GUID_DEVINTERFACE_USB_DEVICE = GUID(
    0xA5DCBF10,
    0x6530,
    0x11D2,
    (ctypes.c_ubyte * 8)(0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED),
)


class WinUsbBackend:
    INIT_PACKET_500K_CH1_A = bytes.fromhex(
        "01 00 00 00 00 00 00 00 ff ff ff ff 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 1c 00 00 00"
    )
    INIT_PACKET_500K_CH1_B = bytes.fromhex(
        "02 00 00 00 2a 02 00 00 9e 4d 35 6d 2a 02 00 00 "
        "d0 b1 aa 11 2a 02 00 00 30 cf 1f 0f 2a 02 00 00"
    )
    INIT_PACKET_250K_CH1_A = bytes.fromhex(
        "01 00 00 00 00 00 00 00 ff ff ff ff 00 00 00 00 "
        "00 00 00 00 00 00 00 00 01 00 00 00 1c 00 00 00"
    )
    INIT_PACKET_250K_CH1_B = bytes.fromhex(
        "02 00 00 00 2a 02 00 00 9e 4d 35 6d 2a 02 00 00 "
        "a0 b7 f3 1a 2a 02 00 00 30 cf 1f 0f 2a 02 00 00"
    )
    BITRATE_INIT_PROFILES = {
        500000: (
            INIT_PACKET_500K_CH1_A,
            INIT_PACKET_500K_CH1_B,
            None,
            None,
        ),
        250000: (
            INIT_PACKET_250K_CH1_A,
            INIT_PACKET_250K_CH1_B,
            None,
            None,
        ),
    }

    def __init__(
        self,
        vid: int,
        pid: int,
        channel_index: int = 0,
        bitrate: int = 500000,
        tx_mid: bytes = USB_CAN_TX_MID,
        tx_trailer: bytes = USB_CAN_TX_TRAILER,
    ):
        self.vid = vid
        self.pid = pid
        self.channel_index = channel_index
        self.bitrate = bitrate
        self.tx_mid = tx_mid
        self.tx_trailer = tx_trailer
        self.device_handle = None
        self.winusb_handle = ctypes.c_void_p()
        self.pipes: dict[int, WINUSB_PIPE_INFORMATION] = {}
        self.is_open = False
        self.last_rx_key = None
        self.startup_discarded_packets = 0

        self.setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.winusb = ctypes.WinDLL("winusb", use_last_error=True)
        self._bind_apis()

    def open(self):
        if self.is_open:
            return
        device_path = self._find_device_path()
        self.device_handle = self._open_device_handle(device_path)
        if not self.winusb.WinUsb_Initialize(self.device_handle, ctypes.byref(self.winusb_handle)):
            self._raise_last_error("WinUsb_Initialize失败")
        self._query_pipes()
        self._set_pipe_timeouts(100)
        self._flush_usb_pipes()
        self._initialize_can_box()
        self.startup_discarded_packets = self._drain_data_in_pipe()
        self.last_rx_key = None
        self.is_open = True

    def close(self):
        if self.winusb_handle:
            self._flush_usb_pipes()
        if self.winusb_handle:
            self.winusb.WinUsb_Free(self.winusb_handle)
            self.winusb_handle = ctypes.c_void_p()
        if self.device_handle:
            self.kernel32.CloseHandle(self.device_handle)
            self.device_handle = None
        self.is_open = False

    def send(self, msg: CanMessage):
        pipe_id = self._data_out_pipe()
        self._write_pipe(pipe_id, self._encode_can_packet(msg, self.tx_mid, self.tx_trailer))

    def receive(self, timeout_ms: int = 100, max_messages: int = 50) -> list[CanMessage]:
        self._set_pipe_timeout(self._data_in_pipe(), timeout_ms)
        messages = []
        for _ in range(max_messages):
            packet = self._read_pipe(self._data_in_pipe(), 32)
            if not packet:
                break
            msg = self._decode_can_packet(packet)
            if msg:
                key = (msg.arbitration_id, msg.timestamp, tuple(msg.data), msg.is_extended_id)
                if key == self.last_rx_key:
                    continue
                self.last_rx_key = key
                messages.append(msg)
        return messages

    def _bind_apis(self):
        self.setupapi.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(GUID),
            wintypes.LPCWSTR,
            wintypes.HWND,
            wintypes.DWORD,
        ]
        self.setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        self.setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
        ]
        self.setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
        self.setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        self.setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
        self.setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        self.setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        self.kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.kernel32.CreateFileW.restype = ctypes.c_void_p
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        self.winusb.WinUsb_Initialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.winusb.WinUsb_Initialize.restype = wintypes.BOOL
        self.winusb.WinUsb_Free.argtypes = [ctypes.c_void_p]
        self.winusb.WinUsb_Free.restype = wintypes.BOOL
        self.winusb.WinUsb_QueryInterfaceSettings.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ubyte,
            ctypes.POINTER(USB_INTERFACE_DESCRIPTOR),
        ]
        self.winusb.WinUsb_QueryInterfaceSettings.restype = wintypes.BOOL
        self.winusb.WinUsb_QueryPipe.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ubyte,
            ctypes.c_ubyte,
            ctypes.POINTER(WINUSB_PIPE_INFORMATION),
        ]
        self.winusb.WinUsb_QueryPipe.restype = wintypes.BOOL
        self.winusb.WinUsb_ReadPipe.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ubyte,
            ctypes.POINTER(ctypes.c_ubyte),
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
            ctypes.c_void_p,
        ]
        self.winusb.WinUsb_ReadPipe.restype = wintypes.BOOL
        self.winusb.WinUsb_WritePipe.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ubyte,
            ctypes.POINTER(ctypes.c_ubyte),
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
            ctypes.c_void_p,
        ]
        self.winusb.WinUsb_WritePipe.restype = wintypes.BOOL
        self.winusb.WinUsb_SetPipePolicy.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ubyte,
            ctypes.c_uint,
            wintypes.ULONG,
            ctypes.c_void_p,
        ]
        self.winusb.WinUsb_SetPipePolicy.restype = wintypes.BOOL
        self.winusb.WinUsb_AbortPipe.argtypes = [ctypes.c_void_p, ctypes.c_ubyte]
        self.winusb.WinUsb_AbortPipe.restype = wintypes.BOOL
        self.winusb.WinUsb_FlushPipe.argtypes = [ctypes.c_void_p, ctypes.c_ubyte]
        self.winusb.WinUsb_FlushPipe.restype = wintypes.BOOL

    def _find_device_path(self) -> str:
        digcf_present = 0x00000002
        digcf_deviceinterface = 0x00000010
        info_set = self.setupapi.SetupDiGetClassDevsW(
            ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE),
            None,
            None,
            digcf_present | digcf_deviceinterface,
        )
        if info_set == ctypes.c_void_p(-1).value:
            self._raise_last_error("SetupDiGetClassDevsW失败")

        target = f"vid_{self.vid:04x}&pid_{self.pid:04x}"
        try:
            index = 0
            while True:
                interface_data = SP_DEVICE_INTERFACE_DATA()
                interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
                ok = self.setupapi.SetupDiEnumDeviceInterfaces(
                    info_set,
                    None,
                    ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE),
                    index,
                    ctypes.byref(interface_data),
                )
                if not ok:
                    if ctypes.get_last_error() == 259:
                        break
                    self._raise_last_error("SetupDiEnumDeviceInterfaces失败")

                detail = SP_DEVICE_INTERFACE_DETAIL_DATA_W()
                detail.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                required = wintypes.DWORD()
                ok = self.setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info_set,
                    ctypes.byref(interface_data),
                    ctypes.byref(detail),
                    ctypes.sizeof(detail),
                    ctypes.byref(required),
                    None,
                )
                if ok and target in detail.DevicePath.lower():
                    return detail.DevicePath
                index += 1
        finally:
            self.setupapi.SetupDiDestroyDeviceInfoList(info_set)

        raise RuntimeError(f"未找到WinUSB设备 VID_{self.vid:04X}&PID_{self.pid:04X}")

    def _open_device_handle(self, device_path: str):
        generic_read = 0x80000000
        generic_write = 0x40000000
        file_share_read = 0x00000001
        file_share_write = 0x00000002
        open_existing = 3
        file_attribute_normal = 0x00000080
        file_flag_overlapped = 0x40000000
        handle = self.kernel32.CreateFileW(
            device_path,
            generic_read | generic_write,
            file_share_read | file_share_write,
            None,
            open_existing,
            file_attribute_normal | file_flag_overlapped,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            self._raise_last_error(f"CreateFileW失败：{device_path}")
        return handle

    def _query_pipes(self):
        descriptor = USB_INTERFACE_DESCRIPTOR()
        if not self.winusb.WinUsb_QueryInterfaceSettings(self.winusb_handle, 0, ctypes.byref(descriptor)):
            self._raise_last_error("WinUsb_QueryInterfaceSettings失败")

        for pipe_index in range(descriptor.bNumEndpoints):
            pipe = WINUSB_PIPE_INFORMATION()
            if self.winusb.WinUsb_QueryPipe(self.winusb_handle, 0, pipe_index, ctypes.byref(pipe)):
                self.pipes[int(pipe.PipeId)] = pipe

        required = [0x01, 0x02, 0x81]
        missing = [pipe for pipe in required if pipe not in self.pipes]
        if missing:
            found = ", ".join(f"0x{pipe:02X}" for pipe in sorted(self.pipes))
            raise RuntimeError(f"WinUSB端点不完整，缺少 {missing}，当前端点：{found}")

    def _set_pipe_timeouts(self, timeout_ms: int):
        for pipe_id in self.pipes:
            self._set_pipe_timeout(pipe_id, timeout_ms)

    def _set_pipe_timeout(self, pipe_id: int, timeout_ms: int):
        pipe_transfer_timeout = 0x03
        value = wintypes.ULONG(timeout_ms)
        self.winusb.WinUsb_SetPipePolicy(
            self.winusb_handle,
            pipe_id,
            pipe_transfer_timeout,
            ctypes.sizeof(value),
            ctypes.byref(value),
        )

    def _flush_usb_pipes(self):
        for pipe_id in list(self.pipes):
            self.winusb.WinUsb_AbortPipe(self.winusb_handle, pipe_id)
            self.winusb.WinUsb_FlushPipe(self.winusb_handle, pipe_id)

    def _drain_data_in_pipe(self, duration_ms: int = 250, max_packets: int = 200) -> int:
        pipe_id = self._data_in_pipe()
        old_timeout_ms = 100
        deadline = time.time() + duration_ms / 1000
        discarded = 0
        self._set_pipe_timeout(pipe_id, 5)
        try:
            while discarded < max_packets and time.time() < deadline:
                packet = self._read_pipe(pipe_id, 32, ignore_errors=True)
                if not packet:
                    break
                discarded += 1
        finally:
            self._set_pipe_timeout(pipe_id, old_timeout_ms)
        return discarded

    def _initialize_can_box(self):
        ch1_a, ch1_b, ch2_a, ch2_b = self._init_packets_for_bitrate()
        if self.channel_index != 0:
            raise RuntimeError("当前只验证了 CAN1/channelIndex=0 的WinUSB初始化流程")
        handshake = bytes([0x13, 0x00, 0x00, 0x00]) + os.urandom(28)
        self._write_pipe(0x02, handshake)
        if 0x82 in self.pipes:
            self._read_pipe(0x82, 32, ignore_errors=True)

        self._write_pipe(0x02, ch1_a)
        self._write_pipe(0x02, ch1_b)
        if 0x04 in self.pipes and ch2_a and ch2_b:
            self._write_pipe(0x04, ch2_a)
            self._write_pipe(0x04, ch2_b)

    def _init_packets_for_bitrate(self) -> tuple[bytes, bytes, bytes | None, bytes | None]:
        profile = self.BITRATE_INIT_PROFILES.get(self.bitrate)
        if profile is None:
            raise RuntimeError(
                f"当前还没有 {self.bitrate}bps 的已验证CAN盒初始化包。"
                "请用正常工具选择该波特率打开CAN，并提供Bus Hound打开阶段日志。"
            )
        return profile

    def _data_in_pipe(self) -> int:
        return 0x81 if self.channel_index == 0 else 0x83

    def _data_out_pipe(self) -> int:
        return 0x01 if self.channel_index == 0 else 0x03

    def _read_pipe(self, pipe_id: int, size: int, ignore_errors: bool = False) -> bytes:
        buffer = (ctypes.c_ubyte * size)()
        transferred = wintypes.ULONG()
        ok = self.winusb.WinUsb_ReadPipe(
            self.winusb_handle,
            pipe_id,
            buffer,
            size,
            ctypes.byref(transferred),
            None,
        )
        if not ok:
            err = ctypes.get_last_error()
            if ignore_errors or err in (121, 995):
                return b""
            self._raise_last_error(f"WinUsb_ReadPipe失败 pipe=0x{pipe_id:02X}")
        return bytes(buffer[: transferred.value])

    def _write_pipe(self, pipe_id: int, data: bytes):
        self._set_pipe_timeout(pipe_id, 2000)
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        transferred = wintypes.ULONG()
        ok = self.winusb.WinUsb_WritePipe(
            self.winusb_handle,
            pipe_id,
            buffer,
            len(data),
            ctypes.byref(transferred),
            None,
        )
        if not ok or transferred.value != len(data):
            self._raise_last_error(f"WinUsb_WritePipe失败 pipe=0x{pipe_id:02X}")

    @staticmethod
    def _encode_can_packet(
        msg: CanMessage,
        tx_mid: bytes = USB_CAN_TX_MID,
        tx_trailer: bytes = USB_CAN_TX_TRAILER,
    ) -> bytes:
        packet = bytearray(32)
        packet[0] = 0x01
        packet[1:5] = int(msg.arbitration_id).to_bytes(4, "little")
        packet[9] = 0x01
        packet[12] = 0x01 if msg.is_extended_id else 0x00
        packet[13] = min(len(msg.data), 8)
        packet[14 : 14 + packet[13]] = bytes(pad8(msg.data)[: packet[13]])
        packet[24:28] = tx_mid
        packet[28:32] = tx_trailer
        return bytes(packet)

    @staticmethod
    def _decode_can_packet(packet: bytes) -> CanMessage | None:
        if len(packet) < 22 or all(byte == 0 for byte in packet):
            return None
        can_id = int.from_bytes(packet[1:5], "little")
        if can_id == 0 or can_id in CAN_BOX_STATUS_IDS:
            return None
        dlc = max(0, min(8, packet[13]))
        if dlc == 0:
            return None
        return CanMessage(
            arbitration_id=can_id,
            data=list(packet[14 : 14 + dlc]),
            is_extended_id=bool(packet[12]),
            timestamp=int.from_bytes(packet[5:9], "little"),
        )

    @staticmethod
    def _raise_last_error(message: str):
        raise ctypes.WinError(ctypes.get_last_error(), message)


class MockBackend:
    def __init__(self, id_format: str = "11bit"):
        self.is_open = False
        self.rx_queue = queue.Queue()
        self.thread = None
        self.id_format = id_format

    def open(self):
        self.is_open = True
        self.thread = threading.Thread(target=self._mock_request_loop, daemon=True)
        self.thread.start()

    def close(self):
        self.is_open = False

    def send(self, msg: CanMessage):
        return

    def receive(self, timeout_ms: int = 100, max_messages: int = 50) -> list[CanMessage]:
        messages = []
        deadline = time.time() + timeout_ms / 1000
        while len(messages) < max_messages and time.time() < deadline:
            try:
                msg = self.rx_queue.get(timeout=max(0.01, deadline - time.time()))
                messages.append(msg)
            except queue.Empty:
                break
        return messages

    def _mock_request_loop(self):
        requests = [
            [0x02, 0x01, 0x00, 0, 0, 0, 0, 0],
            [0x02, 0x01, 0x0C, 0, 0, 0, 0, 0],
            [0x02, 0x01, 0x0D, 0, 0, 0, 0, 0],
            [0x02, 0x09, 0x00, 0, 0, 0, 0, 0],
            [0x02, 0x09, 0x02, 0, 0, 0, 0, 0],
            [0x30, 0x00, 0x00, 0, 0, 0, 0, 0],
        ]
        request_id = 0x18DB33F1 if self.id_format == "29bit" else FUNCTIONAL_REQUEST_ID
        index = 0
        while self.is_open:
            self.rx_queue.put(CanMessage(request_id, requests[index], is_extended_id=(self.id_format == "29bit")))
            index = (index + 1) % len(requests)
            time.sleep(1.0)


class ObdIsoTpResponder:
    def __init__(
        self,
        value_provider,
        vin: str,
        id_format: str = "11bit",
        respond_extended_29bit: bool | None = None,
    ):
        self.value_provider = value_provider
        self.vin = vin[:17].ljust(17, "0")
        self.id_format = self._normalize_id_format(id_format)
        self.respond_extended_29bit = (
            RESPOND_EXTENDED_29BIT if respond_extended_29bit is None else bool(respond_extended_29bit)
        )
        self.pending_by_fc_id: dict[tuple[int, bool], PendingIsoTp] = {}

    def handle(self, msg: CanMessage) -> list[TxItem]:
        data = pad8(msg.data)
        pci_type = data[0] & 0xF0

        if pci_type == 0x00:
            return self._handle_single_frame_request(msg, data)
        if pci_type == 0x30:
            return self._handle_flow_control(msg, data)
        return []

    def _handle_single_frame_request(self, msg: CanMessage, data: list[int]) -> list[TxItem]:
        response_id, flow_control_id = self._response_address(msg)
        if response_id is None:
            return []

        payload_len = data[0] & 0x0F
        if payload_len < 1 or payload_len > 7:
            return []

        payload = data[1 : 1 + payload_len]
        service = payload[0]
        pid = payload[1] if len(payload) >= 2 else None

        response_payload = self._build_obd_payload(service, pid, payload[1:])
        if response_payload is None:
            return []

        return self._make_isotp_response(response_id, flow_control_id, msg.is_extended_id, response_payload)

    def _handle_flow_control(self, msg: CanMessage, data: list[int]) -> list[TxItem]:
        pending = self.pending_by_fc_id.pop((msg.arbitration_id, msg.is_extended_id), None)
        if pending is None:
            return []

        flow_status = data[0] & 0x0F
        if flow_status != 0x00:
            return []

        st_min_ms = self._parse_st_min(data[2])
        items = []
        while pending.remaining:
            chunk = pending.remaining[:7]
            pending.remaining = pending.remaining[7:]
            frame = [0x20 | (pending.next_sn & 0x0F)] + chunk
            pending.next_sn = (pending.next_sn + 1) & 0x0F
            if pending.next_sn == 0:
                pending.next_sn = 1
            items.append(
                TxItem(
                    CanMessage(pending.response_id, pad8(frame), pending.is_extended_id),
                    delay_ms=st_min_ms,
                )
            )
        return items

    def _response_address(self, msg: CanMessage):
        can_id = msg.arbitration_id
        if self.id_format == "11bit":
            if msg.is_extended_id:
                return None, None
            if can_id == FUNCTIONAL_REQUEST_ID:
                return ECU_RESPONSE_ID, PHYSICAL_REQUEST_BASE
            if PHYSICAL_REQUEST_BASE <= can_id <= PHYSICAL_REQUEST_END:
                return ECU_RESPONSE_ID + (can_id - PHYSICAL_REQUEST_BASE), can_id
            return None, None

        if not msg.is_extended_id or not self.respond_extended_29bit:
            return None, None

        if (can_id & 0x1FFFFF00) == EXT_FUNCTIONAL_REQUEST_BASE:
            tester_addr = can_id & 0xFF
            response_id = EXT_PHYSICAL_REQUEST_BASE | (tester_addr << 8) | EXT_OBD_ECU_ADDR
            flow_control_id = EXT_PHYSICAL_REQUEST_BASE | (EXT_OBD_ECU_ADDR << 8) | tester_addr
            return response_id, flow_control_id

        if (can_id & 0x1FFF0000) == EXT_PHYSICAL_REQUEST_BASE:
            target_addr = (can_id >> 8) & 0xFF
            source_addr = can_id & 0xFF
            response_id = EXT_PHYSICAL_REQUEST_BASE | (source_addr << 8) | target_addr
            return response_id, can_id
        return None, None

    @staticmethod
    def _normalize_id_format(value: str) -> str:
        text = str(value).strip().lower().replace("-", "")
        if text in ("11", "11bit", "standard", "std"):
            return "11bit"
        if text in ("29", "29bit", "extended", "ext"):
            return "29bit"
        raise ValueError("ID格式必须是 11bit 或 29bit")

    def _build_obd_payload(self, service: int, pid: int | None, params: list[int] | None = None) -> list[int] | None:
        speed, rpm = self.value_provider()
        params = params or []

        if service == 0x01:
            if pid is None:
                return None
            if pid in SUPPORTED_MODE01_MASK_PIDS:
                return [0x41, pid] + self._supported_pid_mask(pid)
            return self._mode01_payload(pid, speed, rpm)

        if service == 0x03:
            return [0x43, 0x00]

        if service == 0x07:
            return [0x47, 0x00]

        if service == 0x0A:
            return [0x4A, 0x00]

        if service == 0x10 and params:
            return [0x50, params[0], 0x00, 0x32, 0x01, 0xF4]

        if service == 0x09:
            if pid is None:
                return None
            if pid == 0x00:
                # 支持 09 02 VIN
                return [0x49, 0x00, 0x40, 0x00, 0x00, 0x00]
            if pid == 0x02:
                return [0x49, 0x02, 0x01] + list(self.vin.encode("ascii", errors="replace"))

        return None

    def _mode01_payload(self, pid: int, speed: float, rpm: int) -> list[int] | None:
        if pid not in SUPPORTED_MODE01_PIDS:
            return None

        if pid == 0x01:
            return [0x41, 0x01, 0x00, 0x00, 0x00, 0x00]
        if pid == 0x02:
            return [0x41, 0x02, 0x00, self._u8(self._pid_value(0x02, 0))]
        if pid == 0x03:
            return [0x41, 0x03, self._u8(self._pid_value(0x03, 2)), 0x00]
        if pid == 0x04:
            return [0x41, pid, self._percent_byte(self._pid_value(pid, CALCULATED_LOAD_PERCENT))]
        if pid == 0x05:
            return [0x41, pid, self._temperature_byte(self._pid_value(pid, COOLANT_TEMP_C))]
        if 0x06 <= pid <= 0x09:
            return [0x41, pid, self._fuel_trim_byte(self._pid_value(pid, DEFAULT_MODE01_PID_VALUES[pid]))]
        if pid == 0x0A:
            return [0x41, pid, self._u8(self._pid_value(pid, FUEL_PRESSURE_KPA) / 3)]
        if pid == 0x0B:
            return [0x41, pid, self._u8(self._pid_value(pid, INTAKE_PRESSURE_KPA))]
        if pid == 0x0C:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, rpm) * 4)
        if pid == 0x0D:
            return [0x41, pid, self._u8(self._pid_value(pid, speed))]
        if pid == 0x0E:
            return [0x41, pid, self._u8((self._pid_value(pid, 0) + 64) * 2)]
        if pid == 0x0F:
            return [0x41, pid, self._temperature_byte(self._pid_value(pid, INTAKE_AIR_TEMP_C))]
        if pid == 0x10:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, MAF_GPS) * 100)
        if pid == 0x11:
            return [0x41, pid, self._percent_byte(self._pid_value(pid, THROTTLE_PERCENT))]
        if pid == 0x12:
            return [0x41, pid, self._u8(self._pid_value(pid, 1))]
        if pid == 0x13:
            return [0x41, pid, self._u8(self._pid_value(pid, 0x03))]
        if 0x14 <= pid <= 0x1B:
            return [0x41, pid, self._u8(self._pid_value(pid, O2_SENSOR_VOLTAGE_V) * 200), self._fuel_trim_byte(0)]
        if pid == 0x1C:
            return [0x41, pid, self._u8(self._pid_value(pid, 6))]
        if pid == 0x1D:
            return [0x41, pid, self._u8(self._pid_value(pid, 0x03))]
        if pid == 0x1E:
            return [0x41, pid, self._u8(self._pid_value(pid, 0))]
        if pid in (0x1F, 0x21, 0x31, 0x4D, 0x4E):
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, DEFAULT_MODE01_PID_VALUES.get(pid, 0)))
        if pid == 0x22:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, FUEL_RAIL_PRESSURE_KPA) / 0.079)
        if pid in (0x23, 0x59):
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, FUEL_RAIL_PRESSURE_KPA) / 10)
        if 0x24 <= pid <= 0x2B:
            return [0x41, pid] + self._lambda_voltage_bytes(self._pid_value(pid, COMMANDED_EQUIV_RATIO), O2_SENSOR_VOLTAGE_V)
        if pid in (0x2C, 0x2E, 0x2F, 0x45, 0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x52, 0x5A, 0x5B):
            return [0x41, pid, self._percent_byte(self._pid_value(pid, DEFAULT_MODE01_PID_VALUES.get(pid, 0)))]
        if pid in (0x2D, 0x55, 0x56, 0x57, 0x58):
            return [0x41, pid, self._fuel_trim_byte(self._pid_value(pid, 0))]
        if pid == 0x30:
            return [0x41, pid, self._u8(self._pid_value(pid, 1))]
        if pid == 0x32:
            return [0x41, pid] + self._i16_bytes(self._pid_value(pid, EVAP_PRESSURE_PA) * 4)
        if pid == 0x33:
            return [0x41, pid, self._u8(self._pid_value(pid, BAROMETRIC_PRESSURE_KPA))]
        if 0x34 <= pid <= 0x3B:
            return [0x41, pid] + self._lambda_current_bytes(self._pid_value(pid, COMMANDED_EQUIV_RATIO), 0)
        if 0x3C <= pid <= 0x3F:
            return [0x41, pid] + self._u16_bytes((self._pid_value(pid, CATALYST_TEMP_C) + 40) * 10)
        if pid == 0x41:
            return [0x41, pid, 0x00, 0x00, 0x00, 0x00]
        if pid == 0x42:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, CONTROL_MODULE_VOLTAGE_V) * 1000)
        if pid == 0x43:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, ABSOLUTE_LOAD_PERCENT) * 255 / 100)
        if pid == 0x44:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, COMMANDED_EQUIV_RATIO) * 65536 / 2)
        if pid in (0x46, 0x5C):
            return [0x41, pid, self._temperature_byte(self._pid_value(pid, DEFAULT_MODE01_PID_VALUES.get(pid, 0)))]
        if pid == 0x4F:
            return [0x41, pid, 0xFF, 0xFF, 0xFF, 0xFF]
        if pid == 0x50:
            return [0x41, pid, self._u8(self._pid_value(pid, MAX_AIR_FLOW_GPS) / 10)]
        if pid == 0x51:
            return [0x41, pid, self._u8(self._pid_value(pid, FUEL_TYPE))]
        if pid == 0x53:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, ABSOLUTE_EVAP_PRESSURE_KPA) * 200)
        if pid == 0x54:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, EVAP_PRESSURE_PA) + 32767)
        if pid == 0x5D:
            return [0x41, pid] + self._u16_bytes((self._pid_value(pid, 0) + 210) * 128)
        if pid == 0x5E:
            return [0x41, pid] + self._u16_bytes(self._pid_value(pid, FUEL_RATE_LPH) / 0.05)
        if pid == 0x5F:
            return [0x41, pid, self._u8(self._pid_value(pid, 0))]
        if pid == 0x62:
            return [0x41, pid, self._u8(self._pid_value(pid, 0) + 125)]
        if pid == 0x66:
            maf_raw = self._u16(self._pid_value(0x10, MAF_GPS) * 32)
            return [0x41, pid, 0x03, (maf_raw >> 8) & 0xFF, maf_raw & 0xFF, (maf_raw >> 8) & 0xFF, maf_raw & 0xFF]
        if pid == 0x9A:
            value = self._u32(round(float(self._signal_value("battery_pack_voltage", BATTERY_VOLTAGE_V)) * 100))
            return [0x41, pid] + self._u32_bytes(value)
        if pid == 0xA6:
            value = self._u32(round(float(self._pid_value(pid, ODO_KM)) * 10))
            return [0x41, pid] + self._u32_bytes(value)
        if pid == 0xB2:
            return [0x41, pid, self._percent_byte(self._pid_value(pid, BATTERY_SOH_PERCENT))]
        if pid == 0xB7:
            current_raw = self._u16((float(self._signal_value("battery_pack_current", BATTERY_CURRENT_A)) + 3276.8) * 10)
            voltage_raw = self._u16(float(self._signal_value("battery_pack_voltage", BATTERY_VOLTAGE_V)) * 10)
            temp_raw = self._temperature_byte(self._signal_value("battery_pack_temperature", self._pid_value(pid, BATTERY_TEMP_C)))
            return [0x41, pid, (current_raw >> 8) & 0xFF, current_raw & 0xFF, (voltage_raw >> 8) & 0xFF, voltage_raw & 0xFF, temp_raw]

        return [0x41, pid, 0x00]

    @staticmethod
    def _supported_pid_mask(start_pid: int) -> list[int]:
        mask = 0
        for supported_pid in SUPPORTED_MODE01_PIDS:
            if start_pid < supported_pid <= start_pid + 0x20:
                mask |= 1 << (32 - (supported_pid - start_pid))
        return [(mask >> 24) & 0xFF, (mask >> 16) & 0xFF, (mask >> 8) & 0xFF, mask & 0xFF]

    @staticmethod
    def _u8(value: float | int) -> int:
        return max(0, min(255, int(round(value))))

    @staticmethod
    def _u16(value: float | int) -> int:
        return max(0, min(0xFFFF, int(round(value))))

    @staticmethod
    def _u32(value: float | int) -> int:
        return max(0, min(0xFFFFFFFF, int(round(value))))

    @staticmethod
    def _u32_bytes(value: int) -> list[int]:
        return [(value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF]

    @classmethod
    def _u16_bytes(cls, value: float | int) -> list[int]:
        raw = cls._u16(value)
        return [(raw >> 8) & 0xFF, raw & 0xFF]

    @classmethod
    def _i16_bytes(cls, value: float | int) -> list[int]:
        raw = int(round(value))
        raw = max(-32768, min(32767, raw)) & 0xFFFF
        return [(raw >> 8) & 0xFF, raw & 0xFF]

    @classmethod
    def _lambda_voltage_bytes(cls, ratio: float | int, voltage: float | int) -> list[int]:
        ratio_raw = cls._u16(float(ratio) * 32768)
        voltage_raw = cls._u16(float(voltage) * 8192)
        return [(ratio_raw >> 8) & 0xFF, ratio_raw & 0xFF, (voltage_raw >> 8) & 0xFF, voltage_raw & 0xFF]

    @classmethod
    def _lambda_current_bytes(cls, ratio: float | int, current_ma: float | int) -> list[int]:
        ratio_raw = cls._u16(float(ratio) * 32768)
        current_raw = cls._u16((float(current_ma) + 128) * 256)
        return [(ratio_raw >> 8) & 0xFF, ratio_raw & 0xFF, (current_raw >> 8) & 0xFF, current_raw & 0xFF]

    @staticmethod
    def _pid_value(pid: int, default: float | int) -> float | int:
        return default

    @staticmethod
    def _signal_value(signal: str, default: float | int) -> float | int:
        return default

    @classmethod
    def _temperature_byte(cls, celsius: float | int) -> int:
        return cls._u8(celsius + 40)

    @classmethod
    def _percent_byte(cls, percent: float | int) -> int:
        return cls._u8(percent * 255 / 100)

    @classmethod
    def _fuel_trim_byte(cls, percent: float | int) -> int:
        return cls._u8((percent + 100) * 1.28)

    def _make_isotp_response(
        self,
        response_id: int,
        flow_control_id: int,
        is_extended_id: bool,
        payload: list[int],
    ) -> list[TxItem]:
        if len(payload) <= 7:
            frame = [len(payload)] + payload
            return [TxItem(CanMessage(response_id, pad8(frame), is_extended_id))]

        total_len = len(payload)
        first_frame = [0x10 | ((total_len >> 8) & 0x0F), total_len & 0xFF] + payload[:6]
        self.pending_by_fc_id[(flow_control_id, is_extended_id)] = PendingIsoTp(
            response_id=response_id,
            is_extended_id=is_extended_id,
            remaining=payload[6:],
        )
        return [TxItem(CanMessage(response_id, pad8(first_frame), is_extended_id))]

    @staticmethod
    def _parse_st_min(value: int) -> int:
        if value <= 0x7F:
            return value
        return 1


class CanSimGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ISO15765 OBD应答仿真工具")
        self.root.geometry("860x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.can_opened = False
        self.sim_running = False
        self.recv_running = False
        self.sim_thread = None
        self.recv_thread = None
        self.backend = None
        self.active_id_format = CAN_ID_FORMAT
        self.active_bitrate = CAN_BITRATE
        self.sim_profile = self._sim_profile(CAN_ID_FORMAT, CAN_BITRATE)

        self.cur_speed = self.sim_profile["speed_start"]
        self.cur_rpm = self.sim_profile["rpm_start"]
        self.speed_mode = "rise"
        self.value_lock = threading.Lock()
        self.last_rx_log_key = None
        self.last_rx_log_time = 0.0
        self.suppressed_rx_count = 0
        self.last_answer_time_by_request: dict[tuple[int, bool, tuple[int, ...]], float] = {}
        self.suppressed_tx_count = 0

        self.backend_var = tk.StringVar(value=CAN_BACKEND)
        self.vid_var = tk.StringVar(value=f"0x{WINUSB_VID:04X}")
        self.pid_var = tk.StringVar(value=f"0x{WINUSB_PID:04X}")
        self.channel_index_var = tk.StringVar(value=str(CAN_CHANNEL_INDEX))
        self.bitrate_var = tk.StringVar(value=str(CAN_BITRATE))
        self.id_format_var = tk.StringVar(value=CAN_ID_FORMAT)
        self.sim_status_var = tk.StringVar(value="状态：未打开 CAN")

        self.responder = ObdIsoTpResponder(
            self.get_values,
            VIN,
            id_format=self.id_format_var.get(),
            respond_extended_29bit=(self.id_format_var.get() == "29bit"),
        )
        self.build_ui()

    @staticmethod
    def _sim_profile(id_format: str, bitrate: int) -> dict:
        return SIM_PROFILES.get((id_format, bitrate), SIM_PROFILES[(CAN_ID_FORMAT, CAN_BITRATE)])

    def build_ui(self):
        frame_top = ttk.Frame(self.root, padding=6)
        frame_top.pack(fill="x")
        self.btn_open = ttk.Button(frame_top, text="打开CAN盒", command=self.open_can)
        self.btn_open.grid(row=0, column=0, padx=4)
        self.btn_close = ttk.Button(frame_top, text="关闭CAN盒", command=self.close_can, state="disabled")
        self.btn_close.grid(row=0, column=1, padx=4)
        self.btn_start = ttk.Button(frame_top, text="启动仿真应答", command=self.start_sim, state="disabled")
        self.btn_start.grid(row=0, column=2, padx=4)
        self.btn_stop = ttk.Button(frame_top, text="停止数据仿真", command=self.stop_sim, state="disabled")
        self.btn_stop.grid(row=0, column=3, padx=4)
        self.label_sim_status = ttk.Label(frame_top, textvariable=self.sim_status_var, foreground="#666666")
        self.label_sim_status.grid(row=0, column=4, sticky="w", padx=(12, 4))
        frame_top.columnconfigure(4, weight=1)

        frame_cfg = ttk.LabelFrame(self.root, text="CAN盒配置", padding=6)
        frame_cfg.pack(fill="x", padx=6, pady=4)
        ttk.Label(frame_cfg, text="后端:").grid(row=0, column=0, sticky="w")
        self.backend_box = ttk.Combobox(
            frame_cfg,
            textvariable=self.backend_var,
            values=("winusb", "mock"),
            width=12,
            state="readonly",
        )
        self.backend_box.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(frame_cfg, text="VID:").grid(row=0, column=2, sticky="w")
        ttk.Entry(frame_cfg, textvariable=self.vid_var, width=10).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(frame_cfg, text="PID:").grid(row=0, column=4, sticky="w", padx=(8, 0))
        ttk.Entry(frame_cfg, textvariable=self.pid_var, width=10).grid(row=0, column=5, sticky="w", padx=4)

        ttk.Label(frame_cfg, text="channelIndex:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frame_cfg, textvariable=self.channel_index_var, width=8).grid(row=1, column=1, sticky="w", padx=(4, 12), pady=(6, 0))
        ttk.Label(frame_cfg, text="bitrate:").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.bitrate_box = ttk.Combobox(
            frame_cfg,
            textvariable=self.bitrate_var,
            values=("250000", "500000"),
            width=9,
            state="readonly",
        )
        self.bitrate_box.grid(row=1, column=3, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(frame_cfg, text="ID格式:").grid(row=1, column=4, sticky="w", padx=(8, 0), pady=(6, 0))
        self.id_format_box = ttk.Combobox(
            frame_cfg,
            textvariable=self.id_format_var,
            values=("11bit", "29bit"),
            width=8,
            state="readonly",
        )
        self.id_format_box.grid(row=1, column=5, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(
            frame_cfg,
            text=(
                f"打开后先监听；点击“启动仿真应答”后才应答OBD请求；"
                f"11bit/29bit 已分开；250K/500K 初始化已按Bus Hound日志分开；VIN={VIN}"
            ),
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        frame_cfg.columnconfigure(3, weight=1)

        frame_data = ttk.LabelFrame(self.root, text="实时仿真值", padding=6)
        frame_data.pack(fill="x", padx=6, pady=4)
        ttk.Label(frame_data, text="车速(km/h):").grid(row=0, column=0, sticky="w")
        self.label_spd = ttk.Label(frame_data, text=f"{self.cur_speed:.1f}", font=("", 12, "bold"), foreground="#0055cc")
        self.label_spd.grid(row=0, column=1, padx=10)
        ttk.Label(frame_data, text="转速(rpm):").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.label_rpm = ttk.Label(frame_data, text=str(self.cur_rpm), font=("", 12, "bold"), foreground="#cc2200")
        self.label_rpm.grid(row=0, column=3, padx=10)

        frame_log = ttk.LabelFrame(self.root, text="总线日志", padding=6)
        frame_log.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_box = scrolledtext.ScrolledText(frame_log)
        self.log_box.pack(fill="both", expand=True)

    def log_print(self, msg: str):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_box.see(tk.END)

    def set_config_widgets_state(self, state: str):
        for widget_name in ("backend_box", "bitrate_box", "id_format_box"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.config(state=state)

    def should_log_rx(self, msg: CanMessage) -> bool:
        key = (msg.arbitration_id, tuple(msg.data), msg.is_extended_id)
        now = time.time()
        if key == self.last_rx_log_key and now - self.last_rx_log_time < 1.0:
            self.suppressed_rx_count += 1
            return False
        if self.suppressed_rx_count:
            self.log_print(f"[RX] 重复报文已省略 {self.suppressed_rx_count} 条")
            self.suppressed_rx_count = 0
        self.last_rx_log_key = key
        self.last_rx_log_time = now
        return True

    def should_answer_request(self, msg: CanMessage) -> bool:
        data = pad8(msg.data)
        pci_type = data[0] & 0xF0
        if pci_type == 0x30:
            return True
        if pci_type != 0x00:
            return True

        payload_len = data[0] & 0x0F
        key = (msg.arbitration_id, msg.is_extended_id, tuple(data[: 1 + payload_len]))
        now = time.time()
        last_time = self.last_answer_time_by_request.get(key)
        if last_time is not None and now - last_time < DUPLICATE_REQUEST_TX_GAP_SEC:
            self.suppressed_tx_count += 1
            return False

        if self.suppressed_tx_count:
            self.log_print(f"[TX] 重复请求应答已限速 {self.suppressed_tx_count} 次")
            self.suppressed_tx_count = 0
        self.last_answer_time_by_request[key] = now
        return True

    def is_speed_request(self, msg: CanMessage) -> bool:
        data = pad8(msg.data)
        payload_len = data[0] & 0x0F
        return (data[0] & 0xF0) == 0x00 and payload_len >= 2 and data[1] == 0x01 and data[2] == 0x0D

    def is_obd_value_request(self, msg: CanMessage) -> bool:
        data = pad8(msg.data)
        payload_len = data[0] & 0x0F
        return (
            (data[0] & 0xF0) == 0x00
            and payload_len >= 2
            and data[1] == 0x01
            and data[2] in (0x0C, 0x0D)
        )

    def is_speed_response(self, msg: CanMessage) -> bool:
        data = pad8(msg.data)
        payload_len = data[0] & 0x0F
        return (data[0] & 0xF0) == 0x00 and payload_len == 3 and data[1] == 0x41 and data[2] == 0x0D

    def matches_selected_id_format(self, msg: CanMessage) -> bool:
        return msg.is_extended_id if self.active_id_format == "29bit" else not msg.is_extended_id

    @staticmethod
    def actual_id_format(msg: CanMessage) -> str:
        return "29bit" if msg.is_extended_id else "11bit"

    def get_values(self):
        with self.value_lock:
            return self.cur_speed, self.cur_rpm

    def reset_values_for_profile(self):
        with self.value_lock:
            self.cur_speed = float(self.sim_profile["speed_start"])
            self.cur_rpm = int(self.sim_profile["rpm_start"])
            speed_text = f"{self.cur_speed:.1f}"
            rpm_text = str(self.cur_rpm)
        self.root.after(0, self.label_spd.config, {"text": speed_text})
        self.root.after(0, self.label_rpm.config, {"text": rpm_text})

    def advance_value_after_response(self, msg: CanMessage):
        data = pad8(msg.data)
        payload_len = data[0] & 0x0F
        if (data[0] & 0xF0) != 0x00 or payload_len < 3 or data[1] != 0x41:
            return

        with self.value_lock:
            if data[2] == 0x0D:
                self.cur_speed += SPEED_STEP_KMH
                if self.cur_speed > SPEED_RISE_MAX:
                    self.cur_speed = SPEED_STA_MIN
            elif data[2] == 0x0C:
                self.cur_rpm += RPM_STEP
                if self.cur_rpm > RPM_MAX:
                    self.cur_rpm = RPM_MIN
            else:
                return
            speed_text = f"{self.cur_speed:.1f}"
            rpm_text = str(self.cur_rpm)
        self.root.after(0, self.label_spd.config, {"text": speed_text})
        self.root.after(0, self.label_rpm.config, {"text": rpm_text})

    @staticmethod
    def _read_int(value: str, field_name: str) -> int:
        try:
            return int(value.strip(), 0)
        except ValueError as exc:
            raise ValueError(f"{field_name}必须是数字，当前值={value!r}") from exc

    @staticmethod
    def _normalize_id_format(value: str) -> str:
        text = str(value).strip().lower().replace("-", "")
        if text in ("11", "11bit", "standard", "std"):
            return "11bit"
        if text in ("29", "29bit", "extended", "ext"):
            return "29bit"
        raise ValueError("ID格式必须是 11bit 或 29bit")

    @classmethod
    def _normalize_bitrate(cls, value: str | int) -> int:
        text = str(value).strip().lower().replace("k", "000")
        bitrate = int(float(text))
        if bitrate in (250, 500):
            bitrate *= 1000
        if bitrate not in SUPPORTED_BITRATES:
            raise ValueError("bitrate必须是 250000 或 500000")
        return bitrate

    def _read_can_config(self):
        return {
            "vid": self._read_int(self.vid_var.get(), "VID"),
            "pid": self._read_int(self.pid_var.get(), "PID"),
            "channel_index": self._read_int(self.channel_index_var.get(), "channelIndex"),
            "bitrate": self._normalize_bitrate(self.bitrate_var.get()),
            "id_format": self._normalize_id_format(self.id_format_var.get()),
        }

    def open_can(self):
        if self.can_opened:
            return
        try:
            backend_name = self.backend_var.get().strip().lower()
            config = self._read_can_config()
            python_bits = ctypes.sizeof(ctypes.c_void_p) * 8
            self.log_print(
                f"准备打开CAN：backend={backend_name}, Python={python_bits}bit, "
                f"VID=0x{config['vid']:04X}, PID=0x{config['pid']:04X}, "
                f"channelIndex={config['channel_index']}, id_format={config['id_format']}, "
                f"bitrate={config['bitrate']}"
            )
            self.active_id_format = config["id_format"]
            self.active_bitrate = config["bitrate"]
            self.sim_profile = self._sim_profile(self.active_id_format, self.active_bitrate)
            self.responder = ObdIsoTpResponder(
                self.get_values,
                VIN,
                id_format=self.active_id_format,
                respond_extended_29bit=(self.active_id_format == "29bit"),
            )
            hardware_config = {
                "vid": config["vid"],
                "pid": config["pid"],
                "channel_index": config["channel_index"],
                "bitrate": config["bitrate"],
            }
            hardware_config["tx_mid"] = self.sim_profile["tx_mid"]
            hardware_config["tx_trailer"] = self.sim_profile["tx_trailer"]
            self.backend = (
                MockBackend(self.active_id_format)
                if backend_name == "mock"
                else WinUsbBackend(**hardware_config)
            )
            self.backend.open()
            self.can_opened = True
            self.recv_running = True
            self.reset_values_for_profile()
            self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
            self.recv_thread.start()

            discarded_packets = getattr(self.backend, "startup_discarded_packets", 0)
            self.log_print(
                f"✅ CAN盒已打开：{config['id_format']} / {config['bitrate']}bps，"
                f"channelIndex={config['channel_index']}；当前仅监听，不应答；"
                f"启动清理={discarded_packets}包；"
                f"USB尾部={self.sim_profile['tx_mid'].hex(' ').upper()} "
                f"{self.sim_profile['tx_trailer'].hex(' ').upper()}"
            )
            self.btn_open.config(state="disabled")
            self.btn_close.config(state="normal")
            self.btn_start.config(text="启动仿真应答", state="normal")
            self.btn_stop.config(state="disabled")
            self.set_config_widgets_state("disabled")
            self.sim_status_var.set("状态：仅监听，未启动应答")
            self.label_sim_status.config(foreground="#996600")
        except Exception as exc:
            self.can_opened = False
            self.recv_running = False
            if self.backend:
                self.backend.close()
            self.backend = None
            self.set_config_widgets_state("readonly")
            self.sim_status_var.set("状态：打开失败")
            self.label_sim_status.config(foreground="#cc2200")
            self.log_print(f"❌ CAN盒打开失败：{exc}")

    def close_can(self):
        self.stop_sim()
        self.recv_running = False
        self.can_opened = False
        if self.backend:
            try:
                self.backend.close()
            except Exception as exc:
                self.log_print(f"⚠️ 关闭CAN盒异常：{exc}")
        self.backend = None

        self.btn_open.config(state="normal")
        self.btn_close.config(state="disabled")
        self.btn_start.config(text="启动仿真应答", state="disabled")
        self.btn_stop.config(state="disabled")
        self.set_config_widgets_state("readonly")
        self.sim_status_var.set("状态：已关闭")
        self.label_sim_status.config(foreground="#666666")
        self.log_print("✅ CAN盒已关闭")

    def start_sim(self):
        if not self.can_opened or self.sim_running:
            return
        self.sim_running = True
        if self.backend and hasattr(self.backend, "last_rx_key"):
            self.backend.last_rx_key = None
        self.last_answer_time_by_request.clear()
        self.suppressed_tx_count = 0
        self.reset_values_for_profile()
        self.sim_thread = threading.Thread(target=self.sim_main_loop, daemon=True)
        self.sim_thread.start()
        self.btn_start.config(text="仿真应答运行中", state="disabled")
        self.btn_stop.config(text="停止仿真应答", state="normal")
        self.sim_status_var.set("状态：仿真应答运行中")
        self.label_sim_status.config(foreground="#008000")
        self.log_print("🚗 仿真应答已启动：收到 01 0D/01 0C 请求并应答后，车速/RPM按正常日志递增")

    def stop_sim(self):
        was_running = self.sim_running
        self.sim_running = False
        if was_running:
            self.log_print("🛑 仿真应答已停止：CAN盒保持监听，不再发送OBD响应")
        if self.can_opened:
            self.btn_start.config(text="启动仿真应答", state="normal")
            self.sim_status_var.set("状态：仅监听，未启动应答")
            self.label_sim_status.config(foreground="#996600")
        self.btn_stop.config(state="disabled")

    def sim_main_loop(self):
        while self.sim_running and self.can_opened:
            with self.value_lock:
                speed_text = f"{self.cur_speed:.1f}"
                rpm_text = str(self.cur_rpm)

            self.root.after(0, self.label_spd.config, {"text": speed_text})
            self.root.after(0, self.label_rpm.config, {"text": rpm_text})
            time.sleep(DATA_UPDATE_INTERVAL)

    def recv_loop(self):
        while self.recv_running and self.can_opened and self.backend:
            try:
                messages = self.backend.receive(timeout_ms=100, max_messages=50)
                for msg in messages:
                    logged_rx = self.should_log_rx(msg)
                    if logged_rx:
                        self.log_print(f"[RX] {fmt_frame(msg)}")

                    is_speed_request = self.is_speed_request(msg)
                    is_value_request = self.is_obd_value_request(msg)
                    id_format_ok = self.matches_selected_id_format(msg)

                    if is_speed_request and logged_rx and not self.sim_running:
                        actual = self.actual_id_format(msg)
                        self.log_print(
                            f"⚠️ 收到车速请求 PID 0x0D，但仿真应答未启动，所以不会发送 41 0D；"
                            f"实际总线帧格式={actual}"
                        )
                    elif is_value_request and logged_rx and not id_format_ok:
                        data = pad8(msg.data)
                        selected = self.active_id_format
                        actual = self.actual_id_format(msg)
                        self.log_print(
                            f"⚠️ 收到 PID 0x{data[2]:02X} 请求，但当前会话固定为 {selected}，"
                            f"实际收到 {actual}，已忽略；如要模拟该格式，请先关闭CAN盒后重新选择"
                        )

                    if self.sim_running and id_format_ok and self.should_answer_request(msg):
                        if is_speed_request:
                            frame_type = "29bit" if msg.is_extended_id else "11bit"
                            self.log_print(
                                f"🔎 收到车速请求 PID 0x0D：{frame_type} id=0x{msg.arbitration_id:X}"
                            )
                        self.send_obd_response(msg)
            except Exception as exc:
                self.log_print(f"❌ CAN收发异常：{exc}")
                if self.backend:
                    try:
                        self.backend.close()
                    except Exception as close_exc:
                        self.log_print(f"⚠️ 异常后关闭CAN盒失败：{close_exc}")
                    self.backend = None
                self.recv_running = False
                self.can_opened = False
                self.root.after(0, self._set_closed_buttons)
                break

    def send_obd_response(self, msg: CanMessage):
        if not self.backend or not self.can_opened or not self.sim_running:
            return
        for item in self.responder.handle(msg):
            if item.delay_ms > 0:
                time.sleep(item.delay_ms / 1000)
            self.backend.send(item.message)
            self.log_print(f"[TX] {fmt_frame(item.message)}")
            if self.is_speed_response(item.message):
                data = pad8(item.message.data)
                frame_type = "29bit" if item.message.is_extended_id else "11bit"
                self.log_print(
                    f"✅ 已发送车速响应 PID 0x0D：value={data[3]} km/h，"
                    f"{frame_type} id=0x{item.message.arbitration_id:X}"
                )
            self.advance_value_after_response(item.message)

    def _set_closed_buttons(self):
        self.btn_open.config(state="normal")
        self.btn_close.config(state="disabled")
        self.btn_start.config(text="启动仿真应答", state="disabled")
        self.btn_stop.config(state="disabled")
        self.set_config_widgets_state("readonly")
        self.sim_status_var.set("状态：异常关闭")
        self.label_sim_status.config(foreground="#cc2200")

    def on_close(self):
        self.close_can()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = CanSimGUI(root)
    root.mainloop()


# =============================================================================
# 代码结构和运行逻辑说明
# =============================================================================
#
# 一、这个脚本整体在做什么
# -----------------------------------------------------------------------------
# 本脚本的目标是：让电脑通过创芯科技/同类 USB-CAN 盒子，在 CAN 总线上模拟
# 一个 OBD ECU。真实 OBD 设备作为请求方，会向 CAN 总线发送 OBD/UDS/J1979
# 请求；本脚本收到请求后，按照 ISO 15765-4 的 CAN 报文格式回发响应。
#
# 当前代码的工作方式是“请求-应答式”：
# 1. OBD 设备发送请求，例如：
#    7DF  02 01 0D 00 00 00 00 00      请求车速
#    7DF  02 01 0C 00 00 00 00 00      请求发动机转速
#    7DF  02 09 02 00 00 00 00 00      请求 VIN
# 2. 脚本从 CAN 盒 USB 口读到这帧请求。
# 3. 脚本解析请求内容，判断服务号和 PID。
# 4. 脚本生成对应响应，例如：
#    7E8  03 41 0D xx 00 00 00 00      响应车速
#    7E8  04 41 0C xx xx 00 00 00      响应转速
#    7E8  10 ... / 21 ... / 22 ...     多帧响应 VIN
# 5. 脚本通过 USB-CAN 盒把响应帧发回 CAN 总线。
#
# 注意：ISO 15765-4/J1979 的 11 位常见请求 ID 是 0x7DF，常见 ECU 响应 ID 是
# 0x7E8；29 位常见功能请求 ID 形如 0x18DB33F1，常见 ECU 响应 ID 形如
# 0x18DAF110。当前代码会根据 UI 选择只应答 11bit 或 29bit，避免混用。
#
#
# 二、主要类和职责
# -----------------------------------------------------------------------------
# 1. CanMessage
#    表示一帧 CAN 报文，是脚本内部统一使用的数据结构。
#    主要字段：
#    - arbitration_id：CAN ID，例如 0x7DF 或 0x7E8。
#    - data：最多 8 字节 CAN 数据。
#    - is_extended_id：是否为 29 位扩展帧。
#    - timestamp：从 USB-CAN 盒收到的时间戳，主要用于过滤重复缓存帧。
#
# 2. WinUsbBackend
#    负责直接通过 Windows WinUSB 接口访问 CAN 盒。
#    这里没有调用 ControlCAN.dll，也没有调用厂商 32 位 DLL。
#    它主要做四件事：
#    - 枚举 VID/PID 对应的 USB 设备。
#    - 用 CreateFileW 打开 USB 设备路径。
#    - 用 WinUsb_Initialize 初始化 WinUSB 句柄并查询端点。
#    - 用 WinUsb_ReadPipe/WinUsb_WritePipe 收发 USB 数据包。
#
# 3. ObdIsoTpResponder
#    负责 OBD 协议层逻辑。
#    它不关心 USB 怎么打开，也不关心 CAN 盒型号，只负责：
#    - 判断收到的 CAN 帧是不是 OBD 请求。
#    - 解析单帧请求里的服务号和 PID。
#    - 根据请求生成对应的 CAN 响应帧。
#    - 对 VIN 这种超过 7 字节的数据，生成 ISO-TP 多帧响应。
#
# 4. CanSimGUI
#    Tkinter 图形界面和运行调度层。
#    它负责：
#    - 读取界面参数。
#    - 打开/关闭 CAN 盒。
#    - 启动接收线程。
#    - 将收到的请求交给 ObdIsoTpResponder。
#    - 将响应交给 WinUsbBackend 发送。
#    - 在界面日志里显示 RX/TX 报文。
#
#
# 三、CAN 盒调用的完整步骤
# -----------------------------------------------------------------------------
# 从点击“打开 CAN”开始，代码大致按下面顺序执行：
#
# 1. GUI 创建 WinUsbBackend
#    CanSimGUI.open_can() 会根据界面配置创建后端对象。
#    当前默认后端是 winusb，VID/PID 默认对应你抓到的设备：
#    VID = 0x04D8
#    PID = 0x0053
#
# 2. 枚举 USB 设备
#    WinUsbBackend.open() 会调用 Windows SetupAPI。
#    典型流程是：
#    - SetupDiGetClassDevsW
#    - SetupDiEnumDeviceInterfaces
#    - SetupDiGetDeviceInterfaceDetailW
#    这样可以找到类似下面的设备路径：
#    \\?\usb#vid_04d8&pid_0053#...#{a5dcbf10-6530-11d2-901f-00c04fb951ed}
#
# 3. 打开 USB 设备文件
#    找到设备路径后，代码用 CreateFileW 打开它。
#    如果这里失败，常见原因是：
#    - 设备被别的软件占用。
#    - 驱动不是 WinUSB/libusbK/libusb-win32 兼容驱动。
#    - 权限或设备状态异常。
#    - CAN 盒刚刚异常复位，还没有重新枚举完成。
#
# 4. 初始化 WinUSB
#    CreateFileW 成功以后，代码调用 WinUsb_Initialize。
#    这一步会拿到 WinUSB 接口句柄，后续读写都通过这个句柄完成。
#
# 5. 查询 USB 端点
#    代码会查询接口端点，并使用抓包中确认过的端点。
#    当前逻辑里最关键的是：
#    - 0x81：IN 端点，电脑从 CAN 盒读取数据。
#    - 0x01：OUT 端点，电脑向 CAN 盒发送 CAN 报文。
#    - 0x02：OUT 端点，发送 CAN1 初始化配置。
#    - 0x04：OUT 端点，可能用于 CAN2 初始化配置。
#
# 6. 发送 CAN 盒初始化包
#    打开 USB 后，代码会发送从正常工具 Bus Hound 日志中整理出的初始化数据。
#    这些初始化包的作用大致包括：
#    - 选择 CAN 通道。
#    - 设置 CAN 工作参数。当前 500000 bps 初始化包来自 15765-11b-500k.txt；
#      250000 bps 初始化包来自 15765-11b-250k-3.txt。11bit/29bit 不改变
#      这组打开包，实际发送帧时通过 CAN 帧的扩展帧标志区分。
#    - 设置工作模式。
#    - 让 CAN 盒进入可以收发 CAN 帧的状态。
#
#    这里要特别注意：
#    初始化包必须尽量贴近正常工具的行为。之前异常日志里出现过 USB 传输错误
#    和设备重新枚举，说明错误初始化可能让 CAN 盒进入异常状态，甚至导致对端
#    OBD 设备无响应。因此本代码按 250K/500K 分别使用正常日志里匹配过的
#    初始化序列。
#
# 7. 启动接收线程
#    CAN 盒打开成功后，CanSimGUI 会启动 recv_loop() 线程。
#    这个线程循环调用：
#    backend.receive(timeout_ms=100, max_messages=50)
#    打开 CAN 盒后先进入监听模式，只打印收到的 OBD 请求，不主动应答。
#    点击“启动仿真应答”后，收到 OBD 请求才会尝试响应。
#
# 8. 从 USB 端点读取 CAN 报文
#    WinUsbBackend.receive() 内部调用 WinUsb_ReadPipe，从 0x81 端点读数据。
#    CAN 盒返回的不是直接的 8 字节 CAN 数据，而是 CAN 盒自己的 32 字节 USB
#    数据对象。代码需要先把这个 32 字节对象解析成 CanMessage。
#
# 9. 解析 32 字节 USB-CAN 对象
#    根据你提供的正常工具日志，当前代码按下面格式理解 USB 数据：
#    - byte 0     ：方向/类型标记，发送时常见为 0x01。
#    - byte 1-4   ：CAN ID，小端格式。
#    - byte 5-8   ：接收时间戳或设备内部计数，主要用于去重。
#    - byte 9     ：正常日志中常见为 0x01。
#    - byte 12    ：扩展帧标记，0 表示标准帧，非 0 表示扩展帧。
#    - byte 13    ：DLC，也就是 CAN 数据长度。
#    - byte 14-21 ：CAN 数据区，最多 8 字节。
#    - byte 22-23 ：正常工具里像是保留/未使用字段。
#    - byte 24-31 ：不同 bit/bitrate 的 rpm+speed 正常工具日志不同，当前通过
#                   SIM_PROFILES 按 UI 选择自动填充。
#
#    另外，0x01020800/0x01020801 这类对象更像 CAN 盒自己的状态/缓存对象，
#    不是 OBD 请求。当前代码会在解析阶段过滤掉，避免干扰 OBD 判断。
#
#    例如收到：
#    ID = 0x7DF
#    DATA = 02 01 0D 00 00 00 00 00
#    解析后就会得到一个 CanMessage，交给协议层处理。
#
# 10. OBD 请求解析
#     ObdIsoTpResponder.handle(msg) 会检查：
#     - CAN ID 是否是当前 UI 选择的 OBD 请求格式。
#       11bit 模式只处理 0x7DF 或 0x7E0-0x7E7。
#       29bit 模式只处理 0x18DB33xx 或 0x18DA10xx 这类扩展 OBD 地址。
#     - 是否是 ISO-TP 单帧请求。
#     - 服务号是否为当前支持的服务，例如 01、03、07、09、0A、10、22。
#
#     常见请求含义：
#     - 01 00：查询支持的 Mode 01 PID 范围。
#     - 01 20 / 01 40 / 01 60 / 01 80 / 01 A0：继续查询后续 PID 范围。
#     - 01 0C：请求发动机转速。
#     - 01 0D：请求车速。
#     - 01 A6：请求 ODO/累计里程。该 PID 在很多工具里按扩展 PID 使用。
#     - 03 / 07 / 0A：请求故障码，当前默认返回无故障码。
#     - 09 00：查询支持的 Mode 09 PID。
#     - 09 02：请求 VIN。
#     - 22 xxxx：UDS ReadDataByIdentifier，当前只对日志里出现的少量 DID 做模拟。
#
# 11. 生成 OBD 响应
#     如果请求可以识别，代码会生成对应响应。
#     单帧响应格式示例：
#     - 请求 01 0D，响应 41 0D。
#       7E8  03 41 0D speed 00 00 00 00
#     - 请求 01 0C，响应 41 0C。
#       RPM 计算公式是 SAE J1979 标准格式：raw = rpm * 4。
#       7E8  04 41 0C A B 00 00 00
#
#     VIN 响应较长，超过单帧长度，因此使用 ISO-TP 多帧：
#     - 首帧 First Frame：PCI 以 0x10 开头，表示总长度。
#     - 连续帧 Consecutive Frame：PCI 以 0x21、0x22、0x23... 递增。
#     当前代码为了模拟工具行为，会按设定的短延时依次发出多帧。
#
#     当前 Mode 01 已按你提供的日志和界面清单补充了这些关键项：
#     - 0x0A：燃油压力。
#     - 0x46：环境温度。
#     - 0x66：空气流量/MAF 相关扩展项。
#     - 0x9A：电池电压类扩展项。
#     - 0xA6：ODO/累计里程。
#     - 0xB2：SOH。
#     - 0xB7：电池电流、电压、温度类扩展项。
#
# 12. 编码并发送响应
#     生成 CanMessage 后，WinUsbBackend.send() 会把它重新编码成 CAN 盒需要的
#     32 字节 USB 数据对象，并按 SIM_PROFILES 补上该模式从 rpm+speed 正常
#     日志里提取出的 byte24-31，然后调用 WinUsb_WritePipe 写到 0x01 端点。
#     CAN 盒收到这个 USB 包后，再把里面的 CAN ID 和 8 字节数据真正发到 CANH/
#     CANL 总线上。
#
#
# 四、“打开 CAN”和“启动仿真应答”的区别
# -----------------------------------------------------------------------------
# 当前代码里，“打开 CAN”以后只开始接收 OBD 请求和显示 RX 日志，不会发送 TX 响应。
#
# “启动仿真应答”才是应答开关：
# - 未启动仿真应答时，只监听，不发送 OBD 响应。
# - 启动仿真应答后，车速/RPM 会从当前 11bit/29bit、250K/500K 对应的
#   rpm+speed 正常日志起始值开始；每次成功应答 01 0D 后车速 +1，每次成功
#   应答 01 0C 后 RPM +1。
#
# 这样设计的原因是：OBD/ISO15765 本身是请求-应答协议。对端 OBD 设备问什么，
# CAN 盒就应该尽快按协议回答什么，而不是卡在某个固定 PID 或等待某个按钮后
# 才开始应答。
#
#
# 五、去重和限速逻辑
# -----------------------------------------------------------------------------
# 一些 USB-CAN 盒或驱动可能会重复返回缓存帧。为了避免同一个 OBD 请求被重复
# 处理太多次，代码里有两层保护：
#
# 1. WinUsbBackend.receive()
#    根据 CAN ID、时间戳、数据内容、扩展帧标记过滤重复帧。
#
# 2. CanSimGUI.should_log_rx()
#    对界面 RX 日志做节流，避免同一帧在界面里刷屏太快。
#
# 3. CanSimGUI.should_answer_request()
#    对同一个单帧 OBD 请求做很短的 TX 限速，避免 USB-CAN 盒重复吐缓存帧时
#    脚本在几十毫秒内重复应答同一个 PID，导致对端 OBD 设备被刷屏。
#
# 注意：去重只应该减少重复处理，不应该影响真实的新请求。如果对端设备持续按
# 周期发送请求，只要时间戳或数据对象不同，代码仍然会继续处理。
#
#
# 六、排查问题时优先看的位置
# -----------------------------------------------------------------------------
# 如果后续发现“打开失败”：
# - 先看 WinUsbBackend.open()。
# - 重点看设备 VID/PID、CreateFileW、WinUsb_Initialize、端点查询。
#
# 如果发现“Bus Hound 看不到发送”：
# - 先看 WinUsbBackend.send()。
# - 确认是否写到了 0x01 OUT 端点。
# - 确认编码出来的 32 字节对象里 CAN ID、DLC、DATA 是否正确。
#
# 如果发现“收到请求但没有应答”：
# - 先看 recv_loop() 是否打印了 [RX]。
# - 再看 send_obd_response() 是否调用 responder.handle()。
# - 最后看 ObdIsoTpResponder 是否支持该服务号/PID。
#
# 如果发现“OBD 设备死机或无响应”：
# - 不要提高发送频率。
# - 优先对比正常工具的 Bus Hound 时间戳和初始化包。
# - 确认脚本没有在没有请求的情况下主动高速刷 CAN 帧。
# - 确认只对真实 OBD 请求应答，且响应 ID、帧格式、DLC、填充字节正确。
#
#
# 七、最核心的一句话
# -----------------------------------------------------------------------------
# 本脚本不是直接把“OBD 数据”写到 OBD 设备里，而是：
# Python GUI -> WinUSB -> USB-CAN 盒 -> CANH/CANL -> OBD 设备
# Python 从 USB-CAN 盒读取请求帧，协议层生成响应帧，再通过 USB-CAN 盒把响应
# 发送到 CAN 总线。真正和 OBD 设备通信的是 CANH/CANL，USB 只是电脑控制 CAN
# 盒的通道。
