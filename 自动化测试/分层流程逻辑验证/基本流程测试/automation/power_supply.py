from __future__ import annotations

import time
from dataclasses import dataclass

import serial
import serial.tools.list_ports


DEFAULT_KEYWORDS = (
    "SPPS",
    "D305",
    "NICE-POWER",
    "KUAIQU",
    "USB-SERIAL",
    "USB Serial",
    "CH340",
    "CP210",
)


@dataclass
class SerialPortCandidate:
    device: str
    description: str
    hwid: str


class PowerSupplyController:
    LINK_FRAME = "<09100000000>"
    UNLINK_FRAME = "<09200000000>"
    STATUS_FRAME = "<04003300000>"
    OUTPUT_ON_FRAME = "<07000000000>"
    OUTPUT_OFF_FRAME = "<08000000000>"

    def __init__(self, baudrate: int = 9600, current: float = 2.0, min_interval: float = 0.08):
        self.baudrate = baudrate
        self.current = current
        self.min_interval = min_interval
        self.ser: serial.Serial | None = None
        self.last_write_time = 0.0
        self.output_enabled = False

    def list_ports(self) -> list[SerialPortCandidate]:
        return [
            SerialPortCandidate(port.device, port.description or "", port.hwid or "")
            for port in serial.tools.list_ports.comports()
        ]

    def find_port(self, keyword: str | None = None) -> str:
        ports = self.list_ports()
        if not ports:
            raise RuntimeError("No serial ports found for the programmable power supply.")

        keywords = [keyword] if keyword else list(DEFAULT_KEYWORDS)
        keywords = [item.lower() for item in keywords if item]
        for port in ports:
            haystack = f"{port.device} {port.description} {port.hwid}".lower()
            if any(item in haystack for item in keywords):
                return port.device

        if len(ports) == 1:
            return ports[0].device

        details = "; ".join(f"{p.device} [{p.description}] {p.hwid}" for p in ports)
        raise RuntimeError(f"Multiple serial ports found, but none matched power keywords: {details}")

    def connect(self, port: str | None = None, keyword: str | None = None) -> str:
        target_port = port or self.find_port(keyword)
        self.close()
        self.ser = serial.Serial(
            port=target_port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.6,
            write_timeout=0.3,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        time.sleep(0.2)
        self.write_frame(self.LINK_FRAME)
        self.set_current(self.current)
        self.write_frame(self.STATUS_FRAME)
        return target_port

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.write_frame(self.UNLINK_FRAME)
            except Exception:
                pass
            self.ser.close()
        self.ser = None

    def write_frame(self, frame: str) -> bytes:
        if not (self.ser and self.ser.is_open):
            raise RuntimeError("Power supply serial port is not connected.")

        elapsed = time.monotonic() - self.last_write_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        payload = frame.encode("ascii")
        self.ser.write(payload)
        self.ser.flush()
        self.last_write_time = time.monotonic()
        return self.ser.read(13)

    @staticmethod
    def voltage_frame(voltage: float) -> str:
        voltage = max(0.0, min(30.0, voltage))
        units = int(round(voltage * 100))
        return f"<01{units:05d}0000>"

    @staticmethod
    def current_frame(current: float) -> str:
        current = max(0.0, min(5.0, current))
        units = int(round(current * 1000))
        return f"<03{units:06d}000>"

    def set_current(self, current: float) -> None:
        self.current = current
        self.write_frame(self.current_frame(current))

    def set_voltage(self, voltage: float) -> None:
        self.write_frame(self.voltage_frame(voltage))

    def output_on(self) -> None:
        self.set_current(self.current)
        self.write_frame(self.OUTPUT_ON_FRAME)
        self.output_enabled = True

    def output_off(self) -> None:
        self.write_frame(self.OUTPUT_OFF_FRAME)
        self.output_enabled = False

    def ramp_voltage(self, start: float, end: float, duration: float, steps: int | None = None) -> None:
        if duration < 0:
            raise ValueError("duration must be >= 0")

        if steps is None:
            steps = max(2, int(duration / self.min_interval))
        steps = max(1, steps)

        started_at = time.monotonic()
        for index in range(1, steps + 1):
            value = start + (end - start) * index / steps
            self.set_voltage(value)
            if index < steps and duration > 0:
                next_deadline = started_at + duration * index / steps
                remaining = next_deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)


class DryRunPowerSupplyController(PowerSupplyController):
    def __init__(self):
        super().__init__()
        self.connected_port = "DRY-RUN-COM"

    def find_port(self, keyword: str | None = None) -> str:
        return self.connected_port

    def connect(self, port: str | None = None, keyword: str | None = None) -> str:
        return port or self.connected_port

    def close(self) -> None:
        self.output_enabled = False

    def write_frame(self, frame: str) -> bytes:
        self.last_write_time = time.monotonic()
        return b""

