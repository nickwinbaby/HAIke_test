import ctypes
import os
import queue
import random
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

# ====================== OBD仿真配置 ======================
VIN = "LSIM2026071300001"  # 必须17位，VIN查询会用ISO-TP多帧返回
ECU_RESPONSE_ID = 0x7E8
FUNCTIONAL_REQUEST_ID = 0x7DF
PHYSICAL_REQUEST_BASE = 0x7E0
PHYSICAL_REQUEST_END = 0x7E7
RESPOND_EXTENDED_29BIT = False

SPEED_RISE_MAX = 120
SPEED_STA_MIN = 100
SPEED_STA_MAX = 120
DEFAULT_SPEED = 75.0
DEFAULT_RPM = 431
RPM_MIN = 1000
RPM_MAX = 3000
DATA_UPDATE_INTERVAL = 0.1

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

SUPPORTED_MODE01_PIDS = {
    0x01, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
    0x0B, 0x0C, 0x0D, 0x0F, 0x10, 0x11,
    0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B,
    0x1C, 0x1F, 0x20, 0x21, 0x2F, 0x31, 0x40,
    0x43, 0x51, 0x5B, 0x5C, 0x5E,
}


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
    INIT_PACKET_CH1_A = bytes.fromhex(
        "01 00 00 00 00 00 00 00 ff ff ff ff 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 1c 00 00 00"
    )
    INIT_PACKET_CH1_B = bytes.fromhex(
        "02 00 00 00 03 02 00 00 9e 4d c8 28 03 02 00 00 "
        "f0 94 c0 4a 03 02 00 00 30 03 aa 4a 03 02 00 00"
    )
    INIT_PACKET_CH2_A = INIT_PACKET_CH1_A
    INIT_PACKET_CH2_B = bytes.fromhex(
        "02 00 00 00 00 00 00 00 00 00 00 00 1c 00 00 00 "
        "00 00 00 00 01 00 00 00 30 03 aa 4a 03 02 00 00"
    )

    def __init__(self, vid: int, pid: int, channel_index: int = 0, bitrate: int = 500000):
        self.vid = vid
        self.pid = pid
        self.channel_index = channel_index
        self.bitrate = bitrate
        self.device_handle = None
        self.winusb_handle = ctypes.c_void_p()
        self.pipes: dict[int, WINUSB_PIPE_INFORMATION] = {}
        self.is_open = False
        self.last_rx_key = None

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
        self._initialize_can_box()
        self.is_open = True

    def close(self):
        if self.winusb_handle:
            self.winusb.WinUsb_Free(self.winusb_handle)
            self.winusb_handle = ctypes.c_void_p()
        if self.device_handle:
            self.kernel32.CloseHandle(self.device_handle)
            self.device_handle = None
        self.is_open = False

    def send(self, msg: CanMessage):
        pipe_id = self._data_out_pipe()
        self._write_pipe(pipe_id, self._encode_can_packet(msg))

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

    def _initialize_can_box(self):
        handshake = bytes([0x13, 0x00, 0x00, 0x00]) + os.urandom(28)
        self._write_pipe(0x02, handshake)
        if 0x82 in self.pipes:
            self._read_pipe(0x82, 32, ignore_errors=True)

        self._write_pipe(0x02, self.INIT_PACKET_CH1_A)
        self._write_pipe(0x02, self.INIT_PACKET_CH1_B)
        if 0x04 in self.pipes:
            self._write_pipe(0x04, self.INIT_PACKET_CH2_A)
            self._write_pipe(0x04, self.INIT_PACKET_CH2_B)

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
    def _encode_can_packet(msg: CanMessage) -> bytes:
        packet = bytearray(32)
        packet[0] = 0x01
        packet[1:5] = int(msg.arbitration_id).to_bytes(4, "little")
        packet[9] = 0x01
        packet[12] = 0x01 if msg.is_extended_id else 0x00
        packet[13] = min(len(msg.data), 8)
        packet[14 : 14 + packet[13]] = bytes(pad8(msg.data)[: packet[13]])
        return bytes(packet)

    @staticmethod
    def _decode_can_packet(packet: bytes) -> CanMessage | None:
        if len(packet) < 22 or all(byte == 0 for byte in packet):
            return None
        can_id = int.from_bytes(packet[1:5], "little")
        if can_id == 0:
            return None
        dlc = max(0, min(8, packet[13]))
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
    def __init__(self):
        self.is_open = False
        self.rx_queue = queue.Queue()
        self.thread = None

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
        index = 0
        while self.is_open:
            self.rx_queue.put(CanMessage(FUNCTIONAL_REQUEST_ID, requests[index]))
            index = (index + 1) % len(requests)
            time.sleep(1.0)


class ObdIsoTpResponder:
    def __init__(self, value_provider, vin: str):
        self.value_provider = value_provider
        self.vin = vin[:17].ljust(17, "0")
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
        if payload_len < 2 or payload_len > 7:
            return []

        payload = data[1 : 1 + payload_len]
        service = payload[0]
        pid = payload[1]

        response_payload = self._build_obd_payload(service, pid)
        if response_payload is None:
            response_payload = [0x7F, service, 0x12]  # sub-function not supported

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
        if not msg.is_extended_id:
            if can_id == FUNCTIONAL_REQUEST_ID:
                return ECU_RESPONSE_ID, PHYSICAL_REQUEST_BASE
            if PHYSICAL_REQUEST_BASE <= can_id <= PHYSICAL_REQUEST_END:
                return ECU_RESPONSE_ID + (can_id - PHYSICAL_REQUEST_BASE), can_id
            return None, None

        # 默认只模拟 J1979 11bit。需要29bit时再打开 RESPOND_EXTENDED_29BIT。
        if RESPOND_EXTENDED_29BIT and can_id in (0x18DB33F1, 0x18DA10F1):
            return 0x18DAF110, 0x18DA10F1
        return None, None

    def _build_obd_payload(self, service: int, pid: int) -> list[int] | None:
        speed, rpm = self.value_provider()

        if service == 0x01:
            if pid in (0x00, 0x20, 0x40):
                return [0x41, pid] + self._supported_pid_mask(pid)
            if pid == 0x01:
                return [0x41, 0x01, 0x00, 0x00, 0x00, 0x00]
            if pid == 0x04:
                return [0x41, 0x04, self._percent_byte(CALCULATED_LOAD_PERCENT)]
            if pid == 0x05:
                return [0x41, 0x05, self._temperature_byte(COOLANT_TEMP_C)]
            if pid == 0x06:
                return [0x41, 0x06, self._fuel_trim_byte(SHORT_FUEL_TRIM_BANK1_PERCENT)]
            if pid == 0x07:
                return [0x41, 0x07, self._fuel_trim_byte(LONG_FUEL_TRIM_BANK1_PERCENT)]
            if pid == 0x08:
                return [0x41, 0x08, self._fuel_trim_byte(SHORT_FUEL_TRIM_BANK2_PERCENT)]
            if pid == 0x09:
                return [0x41, 0x09, self._fuel_trim_byte(LONG_FUEL_TRIM_BANK2_PERCENT)]
            if pid == 0x0B:
                return [0x41, 0x0B, self._u8(INTAKE_PRESSURE_KPA)]
            if pid == 0x0C:
                rpm_raw = max(0, min(0xFFFF, int(rpm * 4)))
                return [0x41, 0x0C, (rpm_raw >> 8) & 0xFF, rpm_raw & 0xFF]
            if pid == 0x0D:
                return [0x41, 0x0D, max(0, min(255, int(round(speed))))]
            if pid == 0x0F:
                return [0x41, 0x0F, self._temperature_byte(INTAKE_AIR_TEMP_C)]
            if pid == 0x10:
                maf_raw = self._u16(round(MAF_GPS * 100))
                return [0x41, 0x10, (maf_raw >> 8) & 0xFF, maf_raw & 0xFF]
            if pid == 0x11:
                return [0x41, 0x11, self._percent_byte(THROTTLE_PERCENT)]
            if 0x14 <= pid <= 0x1B:
                voltage = self._u8(O2_SENSOR_VOLTAGE_V * 200)
                trim = self._fuel_trim_byte(0)
                return [0x41, pid, voltage, trim]
            if pid == 0x1C:
                return [0x41, 0x1C, 0x06]
            if pid == 0x1F:
                value = self._u16(RUN_TIME_SEC)
                return [0x41, 0x1F, (value >> 8) & 0xFF, value & 0xFF]
            if pid == 0x21:
                value = self._u16(MIL_DISTANCE_KM)
                return [0x41, 0x21, (value >> 8) & 0xFF, value & 0xFF]
            if pid == 0x2F:
                return [0x41, 0x2F, self._percent_byte(FUEL_LEVEL_PERCENT)]
            if pid == 0x31:
                value = self._u16(CLEAR_DISTANCE_KM)
                return [0x41, 0x31, (value >> 8) & 0xFF, value & 0xFF]
            if pid == 0x43:
                value = self._u16(round(ABSOLUTE_LOAD_PERCENT * 255 / 100))
                return [0x41, 0x43, (value >> 8) & 0xFF, value & 0xFF]
            if pid == 0x51:
                return [0x41, 0x51, self._u8(FUEL_TYPE)]
            if pid == 0x5B:
                return [0x41, 0x5B, self._percent_byte(HYBRID_SOC_PERCENT)]
            if pid == 0x5C:
                return [0x41, 0x5C, self._temperature_byte(OIL_TEMP_C)]
            if pid == 0x5E:
                value = self._u16(round(FUEL_RATE_LPH / 0.05))
                return [0x41, 0x5E, (value >> 8) & 0xFF, value & 0xFF]

        if service == 0x09:
            if pid == 0x00:
                # 支持 09 02 VIN
                return [0x49, 0x00, 0x40, 0x00, 0x00, 0x00]
            if pid == 0x02:
                return [0x49, 0x02, 0x01] + list(self.vin.encode("ascii", errors="replace"))

        return None

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

        self.cur_speed = DEFAULT_SPEED
        self.cur_rpm = DEFAULT_RPM
        self.speed_mode = "rise"
        self.value_lock = threading.Lock()
        self.last_rx_log_key = None
        self.last_rx_log_time = 0.0
        self.suppressed_rx_count = 0

        self.backend_var = tk.StringVar(value=CAN_BACKEND)
        self.vid_var = tk.StringVar(value=f"0x{WINUSB_VID:04X}")
        self.pid_var = tk.StringVar(value=f"0x{WINUSB_PID:04X}")
        self.channel_index_var = tk.StringVar(value=str(CAN_CHANNEL_INDEX))
        self.bitrate_var = tk.StringVar(value=str(CAN_BITRATE))

        self.responder = ObdIsoTpResponder(self.get_values, VIN)
        self.build_ui()

    def build_ui(self):
        frame_top = ttk.Frame(self.root, padding=6)
        frame_top.pack(fill="x")
        self.btn_open = ttk.Button(frame_top, text="打开CAN盒", command=self.open_can)
        self.btn_open.grid(row=0, column=0, padx=4)
        self.btn_close = ttk.Button(frame_top, text="关闭CAN盒", command=self.close_can, state="disabled")
        self.btn_close.grid(row=0, column=1, padx=4)
        self.btn_start = ttk.Button(frame_top, text="启动动态数据", command=self.start_sim, state="disabled")
        self.btn_start.grid(row=0, column=2, padx=4)
        self.btn_stop = ttk.Button(frame_top, text="停止数据仿真", command=self.stop_sim, state="disabled")
        self.btn_stop.grid(row=0, column=3, padx=4)

        frame_cfg = ttk.LabelFrame(self.root, text="CAN盒配置", padding=6)
        frame_cfg.pack(fill="x", padx=6, pady=4)
        ttk.Label(frame_cfg, text="后端:").grid(row=0, column=0, sticky="w")
        backend_box = ttk.Combobox(
            frame_cfg,
            textvariable=self.backend_var,
            values=("winusb", "mock"),
            width=12,
            state="readonly",
        )
        backend_box.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(frame_cfg, text="VID:").grid(row=0, column=2, sticky="w")
        ttk.Entry(frame_cfg, textvariable=self.vid_var, width=10).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(frame_cfg, text="PID:").grid(row=0, column=4, sticky="w", padx=(8, 0))
        ttk.Entry(frame_cfg, textvariable=self.pid_var, width=10).grid(row=0, column=5, sticky="w", padx=4)

        ttk.Label(frame_cfg, text="channelIndex:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frame_cfg, textvariable=self.channel_index_var, width=8).grid(row=1, column=1, sticky="w", padx=(4, 12), pady=(6, 0))
        ttk.Label(frame_cfg, text="bitrate:").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(frame_cfg, textvariable=self.bitrate_var, width=9).grid(row=1, column=3, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(frame_cfg, text=f"应答模式：OBD设备请求 -> CAN盒应答，VIN={VIN}").grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        frame_cfg.columnconfigure(3, weight=1)

        frame_data = ttk.LabelFrame(self.root, text="实时仿真值", padding=6)
        frame_data.pack(fill="x", padx=6, pady=4)
        ttk.Label(frame_data, text="车速(km/h):").grid(row=0, column=0, sticky="w")
        self.label_spd = ttk.Label(frame_data, text=f"{DEFAULT_SPEED:.1f}", font=("", 12, "bold"), foreground="#0055cc")
        self.label_spd.grid(row=0, column=1, padx=10)
        ttk.Label(frame_data, text="转速(rpm):").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.label_rpm = ttk.Label(frame_data, text=str(DEFAULT_RPM), font=("", 12, "bold"), foreground="#cc2200")
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

    def get_values(self):
        with self.value_lock:
            return self.cur_speed, self.cur_rpm

    @staticmethod
    def _read_int(value: str, field_name: str) -> int:
        try:
            return int(value.strip(), 0)
        except ValueError as exc:
            raise ValueError(f"{field_name}必须是数字，当前值={value!r}") from exc

    def _read_can_config(self):
        return {
            "vid": self._read_int(self.vid_var.get(), "VID"),
            "pid": self._read_int(self.pid_var.get(), "PID"),
            "channel_index": self._read_int(self.channel_index_var.get(), "channelIndex"),
            "bitrate": self._read_int(self.bitrate_var.get(), "bitrate"),
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
                f"channelIndex={config['channel_index']}, bitrate={config['bitrate']}"
            )
            self.backend = MockBackend() if backend_name == "mock" else WinUsbBackend(**config)
            self.backend.open()
            self.can_opened = True
            self.recv_running = True
            self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
            self.recv_thread.start()

            self.log_print(f"✅ CAN盒已打开：{config['bitrate']}bps，channelIndex={config['channel_index']}")
            self.btn_open.config(state="disabled")
            self.btn_close.config(state="normal")
            self.btn_start.config(state="normal")
        except Exception as exc:
            self.can_opened = False
            self.recv_running = False
            if self.backend:
                self.backend.close()
            self.backend = None
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
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.log_print("✅ CAN盒已关闭")

    def start_sim(self):
        if not self.can_opened or self.sim_running:
            return
        self.sim_running = True
        if self.backend and hasattr(self.backend, "last_rx_key"):
            self.backend.last_rx_key = None
        self.sim_thread = threading.Thread(target=self.sim_main_loop, daemon=True)
        self.sim_thread.start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.log_print("🚗 动态数据已启动：车速/RPM开始变化，OBD请求会实时应答")

    def stop_sim(self):
        was_running = self.sim_running
        self.sim_running = False
        if was_running:
            self.log_print("🛑 数据仿真已停止")
        if self.can_opened:
            self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def sim_main_loop(self):
        with self.value_lock:
            self.cur_speed = DEFAULT_SPEED
            self.cur_rpm = DEFAULT_RPM
            self.speed_mode = "rise"

        while self.sim_running and self.can_opened:
            with self.value_lock:
                if self.speed_mode == "rise":
                    self.cur_speed += random.uniform(0.3, 1.1)
                    if self.cur_speed >= SPEED_RISE_MAX:
                        self.cur_speed = random.uniform(SPEED_STA_MIN, SPEED_STA_MAX)
                        self.speed_mode = "stable"
                else:
                    self.cur_speed = random.uniform(SPEED_STA_MIN, SPEED_STA_MAX)
                self.cur_rpm = random.randint(RPM_MIN, RPM_MAX)
                speed_text = f"{self.cur_speed:.1f}"
                rpm_text = str(self.cur_rpm)

            self.root.after(0, self.label_spd.config, {"text": speed_text})
            self.root.after(0, self.label_rpm.config, {"text": rpm_text})
            time.sleep(DATA_UPDATE_INTERVAL)

    def recv_loop(self):
        while self.recv_running and self.can_opened and self.backend:
            try:
                messages = self.backend.receive(timeout_ms=100, max_messages=5)
                for msg in messages:
                    if self.should_log_rx(msg):
                        self.log_print(f"[RX] {fmt_frame(msg)}")
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
        if not self.backend or not self.can_opened:
            return
        for item in self.responder.handle(msg):
            if item.delay_ms > 0:
                time.sleep(item.delay_ms / 1000)
            self.backend.send(item.message)
            self.log_print(f"[TX] {fmt_frame(item.message)}")

    def _set_closed_buttons(self):
        self.btn_open.config(state="normal")
        self.btn_close.config(state="disabled")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")

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
# 注意：ISO 15765-4/J1979 的常见请求 ID 是 0x7DF，常见 ECU 响应 ID 是
# 0x7E8。当前代码主要按 11 位标准帧来模拟，默认不主动处理 29 位扩展帧。
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
#    - 设置 CAN 波特率，例如 500000 bps。
#    - 设置工作模式。
#    - 让 CAN 盒进入可以收发 CAN 帧的状态。
#
#    这里要特别注意：
#    初始化包必须尽量贴近正常工具的行为。之前异常日志里出现过 USB 传输错误
#    和设备重新枚举，说明错误初始化可能让 CAN 盒进入异常状态，甚至导致对端
#    OBD 设备无响应。因此本代码使用的是正常日志里匹配过的一组初始化序列。
#
# 7. 启动接收线程
#    CAN 盒打开成功后，CanSimGUI 会启动 recv_loop() 线程。
#    这个线程循环调用：
#    backend.receive(timeout_ms=100, max_messages=5)
#    它不会等你点击“启动动态数据”才应答；只要 CAN 盒已打开，收到 OBD 请求
#    就会尝试响应。
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
#    - byte 22-31 ：保留或填充。
#
#    例如收到：
#    ID = 0x7DF
#    DATA = 02 01 0D 00 00 00 00 00
#    解析后就会得到一个 CanMessage，交给协议层处理。
#
# 10. OBD 请求解析
#     ObdIsoTpResponder.handle(msg) 会检查：
#     - CAN ID 是否是功能寻址 0x7DF，或物理寻址 0x7E0-0x7E7。
#     - 是否是 11 位标准帧。
#     - 是否是 ISO-TP 单帧请求。
#     - 服务号是否为当前支持的服务，例如 01 或 09。
#
#     常见请求含义：
#     - 01 00：查询支持的 Mode 01 PID 范围。
#     - 01 0C：请求发动机转速。
#     - 01 0D：请求车速。
#     - 09 00：查询支持的 Mode 09 PID。
#     - 09 02：请求 VIN。
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
# 12. 编码并发送响应
#     生成 CanMessage 后，WinUsbBackend.send() 会把它重新编码成 CAN 盒需要的
#     32 字节 USB 数据对象，然后调用 WinUsb_WritePipe 写到 0x01 端点。
#     CAN 盒收到这个 USB 包后，再把里面的 CAN ID 和 8 字节数据真正发到 CANH/
#     CANL 总线上。
#
#
# 四、“打开 CAN”和“启动动态数据”的区别
# -----------------------------------------------------------------------------
# 当前代码里，“打开 CAN”以后就已经开始接收 OBD 请求并自动应答。
#
# “启动动态数据”不是应答开关，它只控制模拟值是否变化：
# - 未启动动态数据时，车速/RPM 使用默认值。
# - 启动动态数据后，车速/RPM 会按代码里的随机逻辑变化。
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
