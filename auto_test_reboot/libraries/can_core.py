from __future__ import annotations

import ctypes
import os
import queue
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass


WINUSB_VID = 0x04D8
WINUSB_PID = 0x0053
CAN_CHANNEL_INDEX = 0
CAN_BITRATE = 500000

VIN = "LSIM2026071300001"
ECU_RESPONSE_ID = 0x7E8
FUNCTIONAL_REQUEST_ID = 0x7DF
PHYSICAL_REQUEST_BASE = 0x7E0
PHYSICAL_REQUEST_END = 0x7E7
RESPOND_EXTENDED_29BIT = True
EXT_FUNCTIONAL_REQUEST_BASE = 0x18DB3300
EXT_PHYSICAL_REQUEST_BASE = 0x18DA0000
EXT_OBD_ECU_ADDR = 0x10
CAN_BOX_STATUS_IDS = {0x01020800, 0x01020801}
USB_CAN_TX_MID = bytes.fromhex("A8 A8 3F DA")
USB_CAN_TX_TRAILER = bytes.fromhex("8B 02 00 00")
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

SPEED_RISE_MAX = 120
SPEED_STA_MIN = 100
SPEED_STA_MAX = 120
DEFAULT_SPEED = 75.0
DEFAULT_RPM = 431
RPM_MIN = 1000
RPM_MAX = 3000
DATA_UPDATE_INTERVAL = 0.1


@dataclass(frozen=True)
class DtcEntry:
    high: int
    low: int

    def as_bytes(self) -> list[int]:
        return [self.high & 0xFF, self.low & 0xFF]

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

CATALYST_TEMP_C = 350
FUEL_PRESSURE_KPA = 300
FUEL_RAIL_PRESSURE_KPA = 3000
EVAP_PRESSURE_PA = 0
BAROMETRIC_PRESSURE_KPA = 101
CONTROL_MODULE_VOLTAGE_V = 13.8
COMMANDED_EQUIV_RATIO = 1.0
AMBIENT_AIR_TEMP_C = 25
MAX_AIR_FLOW_GPS = 655
ETHANOL_PERCENT = 0
ABSOLUTE_EVAP_PRESSURE_KPA = 100
ODOMETER_KM = 12345
SOH_PERCENT = 93
EV_BATTERY_TEMP_C = 25
BATTERY_PACK_CURRENT_A = 0.0
BATTERY_PACK_VOLTAGE_V = 360.0
BATTERY_PACK_CHARGING_STATE = 0
TURN_SIGNAL_STATUS = 0

SUPPORTED_MODE01_PIDS = set(range(0x01, 0x24))
SUPPORTED_MODE01_PIDS.update(range(0x24, 0x2C))
SUPPORTED_MODE01_PIDS.update(range(0x2C, 0x34))
SUPPORTED_MODE01_PIDS.update(range(0x34, 0x40))
SUPPORTED_MODE01_PIDS.update(range(0x40, 0x50))
SUPPORTED_MODE01_PIDS.update(range(0x50, 0x60))
SUPPORTED_MODE01_PIDS.update({0x60, 0x62, 0x66, 0x80, 0x9A, 0xA0, 0xA6, 0xB2, 0xB7})
SUPPORTED_MODE01_MASK_PIDS = {0x00, 0x20, 0x40, 0x60, 0x80, 0xA0}
SUPPORTED_MODE09_INFOTYPES = set(range(0x01, 0x0C))
SUPPORTED_MODE09_MASK_INFOTYPES = {0x00}

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
    0xA6: ODOMETER_KM,
    0xB2: SOH_PERCENT,
    0xB7: EV_BATTERY_TEMP_C,
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
        500000: (INIT_PACKET_500K_CH1_A, INIT_PACKET_500K_CH1_B, None, None),
        250000: (INIT_PACKET_250K_CH1_A, INIT_PACKET_250K_CH1_B, None, None),
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

    def open(self) -> None:
        if self.is_open:
            return
        device_path = self._find_device_path()
        self.device_handle = self._open_device_handle(device_path)
        if not self.winusb.WinUsb_Initialize(self.device_handle, ctypes.byref(self.winusb_handle)):
            self._raise_last_error("WinUsb_Initialize failed")
        self._query_pipes()
        self._set_pipe_timeouts(100)
        self._flush_usb_pipes()
        self._initialize_can_box()
        self.startup_discarded_packets = self._drain_data_in_pipe()
        self.last_rx_key = None
        self.is_open = True

    def close(self) -> None:
        if self.winusb_handle:
            self._flush_usb_pipes()
        if self.winusb_handle:
            self.winusb.WinUsb_Free(self.winusb_handle)
            self.winusb_handle = ctypes.c_void_p()
        if self.device_handle:
            self.kernel32.CloseHandle(self.device_handle)
            self.device_handle = None
        self.is_open = False

    def send(self, msg: CanMessage) -> None:
        self._write_pipe(self._data_out_pipe(), self._encode_can_packet(msg, self.tx_mid, self.tx_trailer))

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

    def _bind_apis(self) -> None:
        self.setupapi.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD
        ]
        self.setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        self.setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)
        ]
        self.setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
        self.setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W), wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
        ]
        self.setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
        self.setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        self.setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        self.kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
        ]
        self.kernel32.CreateFileW.restype = ctypes.c_void_p
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        self.winusb.WinUsb_Initialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.winusb.WinUsb_Initialize.restype = wintypes.BOOL
        self.winusb.WinUsb_Free.argtypes = [ctypes.c_void_p]
        self.winusb.WinUsb_Free.restype = wintypes.BOOL
        self.winusb.WinUsb_QueryInterfaceSettings.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(USB_INTERFACE_DESCRIPTOR)
        ]
        self.winusb.WinUsb_QueryInterfaceSettings.restype = wintypes.BOOL
        self.winusb.WinUsb_QueryPipe.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.POINTER(WINUSB_PIPE_INFORMATION)
        ]
        self.winusb.WinUsb_QueryPipe.restype = wintypes.BOOL
        self.winusb.WinUsb_ReadPipe.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte), wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p
        ]
        self.winusb.WinUsb_ReadPipe.restype = wintypes.BOOL
        self.winusb.WinUsb_WritePipe.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte), wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p
        ]
        self.winusb.WinUsb_WritePipe.restype = wintypes.BOOL
        self.winusb.WinUsb_SetPipePolicy.argtypes = [
            ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_uint, wintypes.ULONG, ctypes.c_void_p
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
            ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE), None, None,
            digcf_present | digcf_deviceinterface
        )
        if info_set == ctypes.c_void_p(-1).value:
            self._raise_last_error("SetupDiGetClassDevsW failed")

        target = f"vid_{self.vid:04x}&pid_{self.pid:04x}"
        try:
            index = 0
            while True:
                interface_data = SP_DEVICE_INTERFACE_DATA()
                interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
                ok = self.setupapi.SetupDiEnumDeviceInterfaces(
                    info_set, None, ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE),
                    index, ctypes.byref(interface_data)
                )
                if not ok:
                    if ctypes.get_last_error() == 259:
                        break
                    self._raise_last_error("SetupDiEnumDeviceInterfaces failed")

                detail = SP_DEVICE_INTERFACE_DETAIL_DATA_W()
                detail.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                required = wintypes.DWORD()
                ok = self.setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info_set, ctypes.byref(interface_data), ctypes.byref(detail),
                    ctypes.sizeof(detail), ctypes.byref(required), None
                )
                if ok and target in detail.DevicePath.lower():
                    return detail.DevicePath
                index += 1
        finally:
            self.setupapi.SetupDiDestroyDeviceInfoList(info_set)

        raise RuntimeError(f"WinUSB CAN device not found: VID_{self.vid:04X}&PID_{self.pid:04X}")

    def _open_device_handle(self, device_path: str):
        generic_read = 0x80000000
        generic_write = 0x40000000
        file_share_read = 0x00000001
        file_share_write = 0x00000002
        open_existing = 3
        file_attribute_normal = 0x00000080
        file_flag_overlapped = 0x40000000
        handle = self.kernel32.CreateFileW(
            device_path, generic_read | generic_write, file_share_read | file_share_write,
            None, open_existing, file_attribute_normal | file_flag_overlapped, None
        )
        if handle == ctypes.c_void_p(-1).value:
            self._raise_last_error(f"CreateFileW failed: {device_path}")
        return handle

    def _query_pipes(self) -> None:
        descriptor = USB_INTERFACE_DESCRIPTOR()
        if not self.winusb.WinUsb_QueryInterfaceSettings(self.winusb_handle, 0, ctypes.byref(descriptor)):
            self._raise_last_error("WinUsb_QueryInterfaceSettings failed")

        for pipe_index in range(descriptor.bNumEndpoints):
            pipe = WINUSB_PIPE_INFORMATION()
            if self.winusb.WinUsb_QueryPipe(self.winusb_handle, 0, pipe_index, ctypes.byref(pipe)):
                self.pipes[int(pipe.PipeId)] = pipe

        required = [0x01, 0x02, 0x81]
        missing = [pipe for pipe in required if pipe not in self.pipes]
        if missing:
            found = ", ".join(f"0x{pipe:02X}" for pipe in sorted(self.pipes))
            raise RuntimeError(f"WinUSB endpoints incomplete, missing={missing}, found={found}")

    def _set_pipe_timeouts(self, timeout_ms: int) -> None:
        for pipe_id in self.pipes:
            self._set_pipe_timeout(pipe_id, timeout_ms)

    def _set_pipe_timeout(self, pipe_id: int, timeout_ms: int) -> None:
        pipe_transfer_timeout = 0x03
        value = wintypes.ULONG(timeout_ms)
        self.winusb.WinUsb_SetPipePolicy(
            self.winusb_handle, pipe_id, pipe_transfer_timeout,
            ctypes.sizeof(value), ctypes.byref(value)
        )

    def _flush_usb_pipes(self) -> None:
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

    def _initialize_can_box(self) -> None:
        ch1_a, ch1_b, ch2_a, ch2_b = self._init_packets_for_bitrate()
        if self.channel_index != 0:
            raise RuntimeError("Only CAN1/channelIndex=0 has been verified for this WinUSB CAN box.")
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
            raise RuntimeError(f"No verified CAN box init packet for bitrate={self.bitrate}.")
        return profile

    def _data_in_pipe(self) -> int:
        return 0x81 if self.channel_index == 0 else 0x83

    def _data_out_pipe(self) -> int:
        return 0x01 if self.channel_index == 0 else 0x03

    def _read_pipe(self, pipe_id: int, size: int, ignore_errors: bool = False) -> bytes:
        buffer = (ctypes.c_ubyte * size)()
        transferred = wintypes.ULONG()
        ok = self.winusb.WinUsb_ReadPipe(
            self.winusb_handle, pipe_id, buffer, size, ctypes.byref(transferred), None
        )
        if not ok:
            err = ctypes.get_last_error()
            if ignore_errors or err in (121, 995):
                return b""
            self._raise_last_error(f"WinUsb_ReadPipe failed pipe=0x{pipe_id:02X}")
        return bytes(buffer[: transferred.value])

    def _write_pipe(self, pipe_id: int, data: bytes) -> None:
        self._set_pipe_timeout(pipe_id, 2000)
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        transferred = wintypes.ULONG()
        ok = self.winusb.WinUsb_WritePipe(
            self.winusb_handle, pipe_id, buffer, len(data), ctypes.byref(transferred), None
        )
        if not ok or transferred.value != len(data):
            self._raise_last_error(f"WinUsb_WritePipe failed pipe=0x{pipe_id:02X}")

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

    def open(self) -> None:
        self.is_open = True
        self.thread = threading.Thread(target=self._mock_request_loop, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.is_open = False

    def send(self, msg: CanMessage) -> None:
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

    def _mock_request_loop(self) -> None:
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
        pid_values: dict[int, float | int] | None = None,
        signal_values: dict[str, float | int] | None = None,
        raw_pid_payloads: dict[tuple[int, int], list[int]] | None = None,
        respond_extended_29bit: bool | None = None,
    ):
        self.value_provider = value_provider
        self.vin = vin[:17].ljust(17, "0")
        self.id_format = self._normalize_id_format(id_format)
        self.pid_values = pid_values if pid_values is not None else {}
        self.signal_values = signal_values if signal_values is not None else {}
        self.raw_pid_payloads = raw_pid_payloads if raw_pid_payloads is not None else {}
        self.respond_extended_29bit = RESPOND_EXTENDED_29BIT if respond_extended_29bit is None else bool(respond_extended_29bit)
        self.pending_by_fc_id: dict[tuple[int, bool], PendingIsoTp] = {}
        self.current_dtcs: list[DtcEntry] = []
        self.pending_dtcs: list[DtcEntry] = []
        self.permanent_dtcs: list[DtcEntry] = []

    def set_pid_value(self, pid: int, value: float | int) -> None:
        self.pid_values[int(pid)] = value

    def set_signal_value(self, signal: str, value: float | int) -> None:
        self.signal_values[str(signal)] = value

    def set_raw_pid_payload(self, service: int, pid: int, payload: list[int]) -> None:
        self.raw_pid_payloads[(int(service), int(pid))] = [self._u8(item) for item in payload]

    def set_dtc_list(self, kind: str, dtcs: list[DtcEntry]) -> None:
        target = self._dtc_target(kind)
        copied = [DtcEntry(int(entry.high) & 0xFF, int(entry.low) & 0xFF) for entry in dtcs]
        if target == "current":
            self.current_dtcs = copied
        elif target == "pending":
            self.pending_dtcs = copied
        else:
            self.permanent_dtcs = copied

    def clear_dtc_list(self, kind: str) -> None:
        self.set_dtc_list(kind, [])

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
            response_payload = [0x7F, service, 0x12]
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
            items.append(TxItem(CanMessage(pending.response_id, pad8(frame), pending.is_extended_id), st_min_ms))
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
            if target_addr == EXT_OBD_ECU_ADDR:
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
        raise ValueError("CAN id format must be 11bit or 29bit.")

    def _build_obd_payload(
        self,
        service: int,
        pid: int | None,
        params: list[int] | None = None,
    ) -> list[int] | None:
        speed, rpm = self.value_provider()
        params = params or []
        if pid is not None:
            raw_payload = self.raw_pid_payloads.get((service, pid))
            if raw_payload is not None:
                return raw_payload

        if service == 0x01:
            if pid is None:
                return None
            if pid in SUPPORTED_MODE01_MASK_PIDS:
                return [0x41, pid] + self._supported_pid_mask(pid)
            return self._mode01_payload(pid, speed, rpm)

        if service == 0x09:
            if pid is None:
                return None
            if pid in SUPPORTED_MODE09_MASK_INFOTYPES:
                return [0x49, pid] + self._supported_infotype_mask(pid)
            return self._mode09_payload(pid)

        if service == 0x03:
            return self._build_dtc_payload(0x03, self.current_dtcs)

        if service == 0x07:
            return self._build_dtc_payload(0x07, self.pending_dtcs)

        if service == 0x0A:
            return self._build_dtc_payload(0x0A, self.permanent_dtcs)

        if service == 0x10 and params:
            return [0x50, params[0], 0x00, 0x32, 0x01, 0xF4]

        if service == 0x22 and len(params) >= 2:
            did = (params[0] << 8) | params[1]
            did_data = self._build_uds_did_payload(did)
            if did_data is not None:
                return [0x62, params[0], params[1]] + did_data

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
            return [
                0x41,
                pid,
                0x03,
                (maf_raw >> 8) & 0xFF,
                maf_raw & 0xFF,
                (maf_raw >> 8) & 0xFF,
                maf_raw & 0xFF,
            ]
        if pid == 0x9A:
            if pid in self.pid_values:
                value = self._u16(self._pid_value(pid, 0))
                return [0x41, pid, (value >> 8) & 0xFF, value & 0xFF]
            ev_signals = {"battery_pack_current", "battery_pack_voltage", "charging_state", "turn_signal_status"}
            if ev_signals & set(self.signal_values):
                return [0x41, pid] + self._ev_system_bytes()
            value = self._u32(round(float(self._signal_value("battery_pack_voltage", BATTERY_PACK_VOLTAGE_V)) * 100))
            return [0x41, pid] + self._u32_bytes(value)
        if pid == 0xA6:
            value = self._u32(round(float(self._pid_value(pid, ODOMETER_KM)) * 10))
            return [0x41, pid] + self._u32_bytes(value)
        if pid == 0xB2:
            return [0x41, pid, self._percent_byte(self._pid_value(pid, SOH_PERCENT))]
        if pid == 0xB7:
            current_raw = self._u16(
                (float(self._signal_value("battery_pack_current", BATTERY_PACK_CURRENT_A)) + 3276.8) * 10
            )
            voltage_raw = self._u16(float(self._signal_value("battery_pack_voltage", BATTERY_PACK_VOLTAGE_V)) * 10)
            temp_raw = self._temperature_byte(self._signal_value("battery_pack_temperature", self._pid_value(pid, EV_BATTERY_TEMP_C)))
            return [
                0x41,
                pid,
                (current_raw >> 8) & 0xFF,
                current_raw & 0xFF,
                (voltage_raw >> 8) & 0xFF,
                voltage_raw & 0xFF,
                temp_raw,
            ]

        return [0x41, pid, 0x00]

    def _mode09_payload(self, infotype: int) -> list[int] | None:
        if infotype not in SUPPORTED_MODE09_INFOTYPES:
            return None
        if infotype == 0x01:
            return [0x49, infotype, 0x01]
        if infotype == 0x02:
            return [0x49, infotype, 0x01] + list(self.vin.encode("ascii", errors="replace"))
        if infotype == 0x03:
            return [0x49, infotype, 0x01]
        if infotype == 0x04:
            return [0x49, infotype, 0x01] + self._ascii_bytes("CALID2026", 16)
        if infotype == 0x05:
            return [0x49, infotype, 0x01]
        if infotype == 0x06:
            return [0x49, infotype, 0x01, 0x12, 0x34, 0x56, 0x78]
        if infotype == 0x07:
            return [0x49, infotype, 0x01]
        if infotype == 0x08:
            return [0x49, infotype, 0x01] + [0x00] * 16
        if infotype == 0x09:
            return [0x49, infotype, 0x01]
        if infotype == 0x0A:
            return [0x49, infotype, 0x01] + self._ascii_bytes("ECM_AUTO_TEST", 20)
        if infotype == 0x0B:
            return [0x49, infotype, 0x01] + [0x00] * 16
        return None

    def _supported_pid_mask(self, start_pid: int) -> list[int]:
        mask = 0
        supported_pids = set(SUPPORTED_MODE01_PIDS)
        supported_pids.update(pid for service, pid in self.raw_pid_payloads if service == 0x01)
        supported_pids.update(self.pid_values)
        for supported_pid in supported_pids:
            if start_pid < supported_pid <= start_pid + 0x20:
                mask |= 1 << (32 - (supported_pid - start_pid))
        return [(mask >> 24) & 0xFF, (mask >> 16) & 0xFF, (mask >> 8) & 0xFF, mask & 0xFF]

    def _supported_infotype_mask(self, start_infotype: int) -> list[int]:
        mask = 0
        supported_infotypes = set(SUPPORTED_MODE09_INFOTYPES)
        supported_infotypes.update(pid for service, pid in self.raw_pid_payloads if service == 0x09)
        for supported_infotype in supported_infotypes:
            if start_infotype < supported_infotype <= start_infotype + 0x20:
                mask |= 1 << (32 - (supported_infotype - start_infotype))
        return [(mask >> 24) & 0xFF, (mask >> 16) & 0xFF, (mask >> 8) & 0xFF, mask & 0xFF]

    def _pid_value(self, pid: int, default: float | int) -> float | int:
        return self.pid_values.get(pid, default)

    def _signal_value(self, signal: str, default: float | int) -> float | int:
        return self.signal_values.get(signal, default)

    def _build_uds_did_payload(self, did: int) -> list[int] | None:
        if did == 0xF190:
            return list(self.vin.encode("ascii", errors="replace"))
        if did == 0x2708:
            return [0x01]
        if did == 0x0026:
            return [self._u8(self._pid_value(0x10, MAF_GPS) * 100)]
        if did == 0x0028:
            speed, _ = self.value_provider()
            return [self._u8(self._pid_value(0x0D, speed))]
        if did in (0x0005, 0x0008, 0x0009, 0x000A, 0x0203, 0x1FFC, 0x2009, 0x24A8):
            return [0x00]
        if 0x2732 <= did <= 0x2736:
            return [0x00]
        return None

    @staticmethod
    def _build_dtc_payload(service: int, dtcs: list[DtcEntry]) -> list[int]:
        response_service = service + 0x40
        if not dtcs:
            return [response_service, 0x00]
        payload = [response_service, len(dtcs)]
        for entry in dtcs:
            payload.extend(entry.as_bytes())
        return payload

    @staticmethod
    def _dtc_target(kind: str) -> str:
        key = str(kind).strip().lower().replace("-", "_").replace(" ", "_")
        if key in ("current", "curr", "curr_dtc", "current_dtc", "wwh_obd_currdtc"):
            return "current"
        if key in ("pending", "pend", "pending_dtc"):
            return "pending"
        if key in ("permanent", "perman", "permanent_dtc"):
            return "permanent"
        raise ValueError(f"Unsupported DTC kind: {kind}")

    def _ev_system_bytes(self) -> list[int]:
        current_raw = self._u16((float(self._signal_value("battery_pack_current", BATTERY_PACK_CURRENT_A)) + 1000) * 10)
        voltage_raw = self._u16(float(self._signal_value("battery_pack_voltage", BATTERY_PACK_VOLTAGE_V)) * 10)
        charging_state = self._u8(self._signal_value("charging_state", BATTERY_PACK_CHARGING_STATE))
        turn_signal_status = self._u8(self._signal_value("turn_signal_status", TURN_SIGNAL_STATUS))
        return [
            (current_raw >> 8) & 0xFF,
            current_raw & 0xFF,
            (voltage_raw >> 8) & 0xFF,
            voltage_raw & 0xFF,
            charging_state,
            turn_signal_status,
        ]

    @staticmethod
    def _u8(value: float | int) -> int:
        return max(0, min(255, int(round(value))))

    @staticmethod
    def _u16(value: float | int) -> int:
        return max(0, min(0xFFFF, int(round(value))))

    @staticmethod
    def _u32(value: float | int) -> int:
        return max(0, min(0xFFFFFFFF, int(round(value))))

    @classmethod
    def _u16_bytes(cls, value: float | int) -> list[int]:
        raw = cls._u16(value)
        return [(raw >> 8) & 0xFF, raw & 0xFF]

    @classmethod
    def _u32_bytes(cls, value: float | int) -> list[int]:
        raw = cls._u32(value)
        return [(raw >> 24) & 0xFF, (raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF]

    @classmethod
    def _i16_bytes(cls, value: float | int) -> list[int]:
        raw = int(round(value))
        raw = max(-32768, min(32767, raw))
        if raw < 0:
            raw = (1 << 16) + raw
        return [(raw >> 8) & 0xFF, raw & 0xFF]

    @classmethod
    def _lambda_voltage_bytes(cls, lambda_value: float | int, voltage: float | int) -> list[int]:
        lambda_raw = cls._u16(float(lambda_value) * 65536 / 2)
        voltage_raw = cls._u16(float(voltage) * 65536 / 8)
        return [
            (lambda_raw >> 8) & 0xFF,
            lambda_raw & 0xFF,
            (voltage_raw >> 8) & 0xFF,
            voltage_raw & 0xFF,
        ]

    @classmethod
    def _lambda_current_bytes(cls, lambda_value: float | int, current_ma: float | int) -> list[int]:
        lambda_raw = cls._u16(float(lambda_value) * 65536 / 2)
        current_raw = cls._u16((float(current_ma) + 128) * 256)
        return [
            (lambda_raw >> 8) & 0xFF,
            lambda_raw & 0xFF,
            (current_raw >> 8) & 0xFF,
            current_raw & 0xFF,
        ]

    @staticmethod
    def _ascii_bytes(text: str, length: int) -> list[int]:
        return list(str(text)[:length].ljust(length, " ").encode("ascii", errors="replace"))

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
