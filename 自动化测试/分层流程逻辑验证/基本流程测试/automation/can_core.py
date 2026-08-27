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

    def open(self) -> None:
        if self.is_open:
            return
        device_path = self._find_device_path()
        self.device_handle = self._open_device_handle(device_path)
        if not self.winusb.WinUsb_Initialize(self.device_handle, ctypes.byref(self.winusb_handle)):
            self._raise_last_error("WinUsb_Initialize failed")
        self._query_pipes()
        self._set_pipe_timeouts(100)
        self._initialize_can_box()
        self.is_open = True

    def close(self) -> None:
        if self.winusb_handle:
            self.winusb.WinUsb_Free(self.winusb_handle)
            self.winusb_handle = ctypes.c_void_p()
        if self.device_handle:
            self.kernel32.CloseHandle(self.device_handle)
            self.device_handle = None
        self.is_open = False

    def send(self, msg: CanMessage) -> None:
        self._write_pipe(self._data_out_pipe(), self._encode_can_packet(msg))

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

    def _initialize_can_box(self) -> None:
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
        if not msg.is_extended_id:
            if can_id == FUNCTIONAL_REQUEST_ID:
                return ECU_RESPONSE_ID, PHYSICAL_REQUEST_BASE
            if PHYSICAL_REQUEST_BASE <= can_id <= PHYSICAL_REQUEST_END:
                return ECU_RESPONSE_ID + (can_id - PHYSICAL_REQUEST_BASE), can_id
            return None, None

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
                return [0x41, pid, self._u8(O2_SENSOR_VOLTAGE_V * 200), self._fuel_trim_byte(0)]
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

