from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any


VID = 0x16C0
PID = 0x05DF
PRODUCT_KEYWORD = "USBRelay"
CHANNEL_COUNT = 4

CMD_ALL_CLOSE = [0xFE, 0, 0, 0, 0, 0, 0, 0]
CMD_ALL_OPEN = [0xFC, 0, 0, 0, 0, 0, 0, 0]


def channel_close_command(channel: int) -> list[int]:
    return [0xFF, channel, 0, 0, 0, 0, 0, 0]


def channel_open_command(channel: int) -> list[int]:
    return [0xFD, channel, 0, 0, 0, 0, 0, 0]


@dataclass
class RelayDeviceInfo:
    backend: str
    path: Any
    product: str = ""
    manufacturer: str = ""

    def display_path(self) -> str:
        if isinstance(self.path, bytes):
            return self.path.decode("utf-8", errors="ignore")
        return str(self.path)


class HidApiRelayBackend:
    name = "hidapi"

    def __init__(self):
        self._hid = importlib.import_module("hid")

    def enumerate(self) -> list[RelayDeviceInfo]:
        devices = []
        for item in self._hid.enumerate(VID, PID):
            product = item.get("product_string") or ""
            manufacturer = item.get("manufacturer_string") or ""
            path = item.get("path")
            if PRODUCT_KEYWORD.lower() in product.lower() or path:
                devices.append(
                    RelayDeviceInfo(
                        backend=self.name,
                        path=path,
                        product=product,
                        manufacturer=manufacturer,
                    )
                )
        return devices

    def open(self, info: RelayDeviceInfo):
        handle = self._hid.device()
        handle.open_path(info.path)
        handle.set_nonblocking(True)
        return handle

    def send(self, handle, command: list[int]) -> None:
        payload = [0x00] + command
        try:
            handle.send_feature_report(payload)
        except Exception:
            handle.write(payload)

    def close(self, handle) -> None:
        handle.close()


class PyWinUsbRelayBackend:
    name = "pywinusb"

    def __init__(self):
        self._hid = importlib.import_module("pywinusb.hid")

    def enumerate(self) -> list[RelayDeviceInfo]:
        devices = []
        for item in self._hid.find_all_hid_devices():
            if item.vendor_id != VID or item.product_id != PID:
                continue
            devices.append(
                RelayDeviceInfo(
                    backend=self.name,
                    path=item.device_path,
                    product=item.product_name or "",
                    manufacturer=item.vendor_name or "",
                )
            )
        return devices

    def open(self, info: RelayDeviceInfo):
        for item in self._hid.find_all_hid_devices():
            if item.device_path == info.path:
                item.open()
                return item
        raise RuntimeError("Selected relay device was not found.")

    def send(self, handle, command: list[int]) -> None:
        reports = handle.find_feature_reports()
        if not reports:
            reports = handle.find_output_reports()
        if not reports:
            raise RuntimeError("Relay device has no feature/output report.")

        report = reports[0]
        report.set_raw_data([0x00] + command)
        report.send()

    def close(self, handle) -> None:
        handle.close()


def load_backend():
    errors = []
    for backend_cls in (HidApiRelayBackend, PyWinUsbRelayBackend):
        try:
            return backend_cls()
        except Exception as exc:
            errors.append(f"{backend_cls.name}: {exc}")
    joined = "; ".join(errors)
    raise RuntimeError(f"No HID relay backend is available. Install hidapi or pywinusb. Details: {joined}")


class RelayUsbController:
    def __init__(self):
        self.backend = None
        self.info: RelayDeviceInfo | None = None
        self.handle = None
        self.channel_closed = [False] * CHANNEL_COUNT

    def connect(self) -> RelayDeviceInfo:
        if self.handle and self.info:
            return self.info

        self.backend = load_backend()
        devices = self.backend.enumerate()
        if not devices:
            raise RuntimeError(f"USB relay not found: VID_{VID:04X}&PID_{PID:04X}.")

        self.info = devices[0]
        self.handle = self.backend.open(self.info)
        return self.info

    def close(self) -> None:
        if self.handle and self.backend:
            try:
                self.backend.close(self.handle)
            finally:
                self.handle = None
        self.info = None
        self.backend = None

    def set_channel(self, channel: int, closed: bool) -> None:
        self._check_channel(channel)
        if not self.handle:
            self.connect()

        command = channel_close_command(channel) if closed else channel_open_command(channel)
        self.backend.send(self.handle, command)
        self.channel_closed[channel - 1] = bool(closed)
        time.sleep(0.05)

    def set_all(self, closed: bool) -> None:
        if not self.handle:
            self.connect()

        command = CMD_ALL_CLOSE if closed else CMD_ALL_OPEN
        self.backend.send(self.handle, command)
        self.channel_closed = [bool(closed)] * CHANNEL_COUNT
        time.sleep(0.05)

    @staticmethod
    def _check_channel(channel: int) -> None:
        if not 1 <= int(channel) <= CHANNEL_COUNT:
            raise ValueError(f"Relay channel must be 1-{CHANNEL_COUNT}, got {channel}.")


class DryRunRelayUsbController(RelayUsbController):
    def connect(self) -> RelayDeviceInfo:
        self.info = RelayDeviceInfo(backend="dry-run", path="DRY-RUN-RELAY")
        return self.info

    def close(self) -> None:
        self.info = None
        self.handle = None

    def set_channel(self, channel: int, closed: bool) -> None:
        self._check_channel(channel)
        self.channel_closed[int(channel) - 1] = bool(closed)

    def set_all(self, closed: bool) -> None:
        self.channel_closed = [bool(closed)] * CHANNEL_COUNT
