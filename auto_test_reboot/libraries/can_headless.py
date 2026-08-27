import random
import threading
import time
from typing import Callable

try:
    from . import can_core
except ImportError:  # pragma: no cover - Robot imports as a file path.
    import can_core


class HeadlessCanSimulator:
    SUPPORTED_BITRATES = {250000, 500000}
    SUPPORTED_ID_FORMATS = {"11bit", "29bit"}
    WATCH_MODE01_PIDS = {0x0D, 0x9A, 0xA6, 0xB7}
    WATCH_UDS_DIDS = {
        0x0005,
        0x0008,
        0x0009,
        0x000A,
        0x0026,
        0x0028,
        0x0203,
        0x1FFC,
        0x2009,
        0x2708,
        0x2732,
        0x2733,
        0x2734,
        0x2735,
        0x2736,
        0x24A8,
        0xF190,
    }

    def __init__(
        self,
        backend: str = "winusb",
        vid: int = 0x04D8,
        pid: int = 0x0053,
        channel_index: int = 0,
        bitrate: int = 500000,
        id_format: str = "11bit",
        logger: Callable[[str], None] | None = None,
    ):
        self.can = can_core
        self.backend_name = backend
        self.id_format = self._normalize_id_format(id_format)
        self.config = {
            "vid": vid,
            "pid": pid,
            "channel_index": channel_index,
            "bitrate": self._normalize_bitrate(bitrate),
        }
        self.sim_profile = self._sim_profile(self.id_format, self.config["bitrate"])
        self.logger = logger or (lambda message: None)
        self.backend = None
        self.can_opened = False
        self.recv_running = False
        self.sim_running = False
        self.recv_thread: threading.Thread | None = None
        self.sim_thread: threading.Thread | None = None
        self.value_lock = threading.Lock()
        self.cur_speed = float(self.can.DEFAULT_SPEED)
        self.cur_rpm = int(self.can.DEFAULT_RPM)
        self.speed_mode = "rise"
        self.rpm_min = int(self.can.RPM_MIN)
        self.rpm_max = int(self.can.RPM_MAX)
        self.pid_values: dict[int, float | int] = {}
        self.pid_ranges: dict[int, tuple[float, float]] = {}
        self.signal_values: dict[str, float | int] = {}
        self.signal_ranges: dict[str, tuple[float, float]] = {}
        self.protocol_field_values: dict[str, float | int] = {}
        self.protocol_field_ranges: dict[str, tuple[float, float]] = {}
        self.raw_pid_payloads: dict[tuple[int, int], list[int]] = {}
        self.dtc_lists: dict[str, list[can_core.DtcEntry]] = {
            "current": [],
            "pending": [],
            "permanent": [],
        }
        self.responder = self._make_responder()

    def configure(
        self,
        bitrate: int | None = None,
        id_format: str | None = None,
        channel_index: int | None = None,
    ) -> None:
        if self.can_opened:
            raise RuntimeError("CAN is already opened. Configure CAN before starting simulation.")
        if bitrate is not None:
            self.config["bitrate"] = self._normalize_bitrate(bitrate)
        if id_format is not None:
            self.id_format = self._normalize_id_format(id_format)
        if channel_index is not None:
            self.config["channel_index"] = int(channel_index)
        self.sim_profile = self._sim_profile(self.id_format, self.config["bitrate"])
        self.responder = self._make_responder()
        self.logger(
            "CAN configured: "
            f"id_format={self.id_format}, bitrate={self.config['bitrate']}, "
            f"channel={self.config['channel_index']}"
        )

    def set_pid_value(self, pid: int, value: float | int) -> None:
        pid_int = int(pid)
        if not 0 <= pid_int <= 0xFF:
            raise ValueError(f"CAN PID must be 0x00-0xFF, got {pid}.")
        self.pid_ranges.pop(pid_int, None)
        self.pid_values[pid_int] = value
        self.responder.set_pid_value(pid_int, value)
        self.logger(f"CAN PID 0x{pid_int:02X} value override set to {value}.")

    def set_pid_range(self, pid: int, minimum: float, maximum: float) -> None:
        pid_int = int(pid)
        min_value = float(minimum)
        max_value = float(maximum)
        if not 0 <= pid_int <= 0xFF:
            raise ValueError(f"CAN PID must be 0x00-0xFF, got {pid}.")
        if min_value > max_value:
            raise ValueError("CAN PID range minimum must be <= maximum.")
        self.pid_values.pop(pid_int, None)
        self.responder.pid_values.pop(pid_int, None)
        self.pid_ranges[pid_int] = (min_value, max_value)
        self.logger(f"CAN PID 0x{pid_int:02X} dynamic range set to {min_value}-{max_value}.")

    def set_signal_value(self, signal: str, value: float | int) -> None:
        key = str(signal).strip()
        self.signal_ranges.pop(key, None)
        self.signal_values[key] = value
        self.responder.set_signal_value(key, value)
        self.logger(f"CAN signal {key} value override set to {value}.")

    def set_signal_range(self, signal: str, minimum: float, maximum: float) -> None:
        key = str(signal).strip()
        min_value = float(minimum)
        max_value = float(maximum)
        if min_value > max_value:
            raise ValueError("CAN signal range minimum must be <= maximum.")
        self.signal_values.pop(key, None)
        self.signal_ranges[key] = (min_value, max_value)
        self.logger(f"CAN signal {key} dynamic range set to {min_value}-{max_value}.")

    def set_protocol_field_value(self, field: str, value: float | int) -> None:
        key = str(field).strip()
        self.protocol_field_ranges.pop(key, None)
        self.protocol_field_values[key] = value
        self.logger(f"Protocol-only field {key} value stored as {value}; no CAN PID mapping is known yet.")

    def set_protocol_field_range(self, field: str, minimum: float, maximum: float) -> None:
        key = str(field).strip()
        min_value = float(minimum)
        max_value = float(maximum)
        if min_value > max_value:
            raise ValueError("Protocol-only field range minimum must be <= maximum.")
        self.protocol_field_values.pop(key, None)
        self.protocol_field_ranges[key] = (min_value, max_value)
        self.logger(f"Protocol-only field {key} range stored as {min_value}-{max_value}; no CAN PID mapping is known yet.")

    def set_rpm_range(self, minimum: int, maximum: int) -> None:
        min_rpm = int(minimum)
        max_rpm = int(maximum)
        if min_rpm < 0 or max_rpm < 0:
            raise ValueError("RPM range must be non-negative.")
        if min_rpm > max_rpm:
            raise ValueError("RPM minimum must be <= maximum.")
        self.rpm_min = min_rpm
        self.rpm_max = max_rpm
        self.pid_values.pop(0x0C, None)
        self.pid_ranges.pop(0x0C, None)
        self.responder.pid_values.pop(0x0C, None)
        self.logger(f"CAN RPM range set to {self.rpm_min}-{self.rpm_max}, PID 0x0C override cleared.")

    def set_raw_pid_payload(self, service: int, pid: int, payload: list[int]) -> None:
        service_int = int(service)
        pid_int = int(pid)
        payload_bytes = [int(item) for item in payload]
        self.raw_pid_payloads[(service_int, pid_int)] = payload_bytes
        self.responder.set_raw_pid_payload(service_int, pid_int, payload_bytes)
        self.logger(
            f"CAN raw PID response override set: service=0x{service_int:02X}, "
            f"pid=0x{pid_int:02X}, payload={' '.join(f'{item:02X}' for item in payload_bytes)}"
        )

    def set_dtc_list(self, kind: str, dtcs: list[can_core.DtcEntry]) -> None:
        target = can_core.ObdIsoTpResponder._dtc_target(kind)
        self.dtc_lists[target] = list(dtcs)
        self.responder.set_dtc_list(target, self.dtc_lists[target])
        formatted = self._format_dtcs(self.dtc_lists[target])
        self.logger(f"CAN WWH-OBD {target} DTC list set to [{formatted}].")

    def clear_dtc_list(self, kind: str) -> None:
        self.set_dtc_list(kind, [])

    def _make_responder(self):
        responder = self.can.ObdIsoTpResponder(
            self.get_values,
            self.can.VIN,
            id_format=self.id_format,
            pid_values=self.pid_values,
            signal_values=self.signal_values,
            raw_pid_payloads=self.raw_pid_payloads,
            respond_extended_29bit=self.id_format == "29bit",
        )
        for kind, dtcs in self.dtc_lists.items():
            responder.set_dtc_list(kind, dtcs)
        return responder

    def open(self) -> None:
        if self.can_opened:
            return
        if self.backend_name.lower() == "mock":
            self.backend = self.can.MockBackend(self.id_format)
        else:
            self.backend = self.can.WinUsbBackend(
                **self.config,
                tx_mid=self.sim_profile["tx_mid"],
                tx_trailer=self.sim_profile["tx_trailer"],
            )
        self.backend.open()
        self.can_opened = True
        self.recv_running = True
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()
        self.logger(
            "CAN opened: "
            f"backend={self.backend_name}, id_format={self.id_format}, bitrate={self.config['bitrate']}, "
            f"channel={self.config['channel_index']}"
        )

    def start(self) -> None:
        if self.sim_running:
            return
        if not self.can_opened:
            self.open()
        self.sim_running = True
        if self.backend and hasattr(self.backend, "last_rx_key"):
            self.backend.last_rx_key = None
        self.sim_thread = threading.Thread(target=self._sim_loop, daemon=True)
        self.sim_thread.start()
        self.logger("CAN dynamic OBD simulation started.")

    def stop(self) -> None:
        was_running = self.sim_running
        self.sim_running = False
        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=1.0)
        if was_running:
            self.logger("CAN dynamic OBD simulation stopped.")

    def close(self) -> None:
        self.stop()
        self.recv_running = False
        self.can_opened = False
        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join(timeout=1.0)
        if self.backend:
            self.backend.close()
        self.backend = None
        self.logger("CAN closed.")

    def get_values(self) -> tuple[float, int]:
        with self.value_lock:
            return self.cur_speed, self.cur_rpm

    def _sim_loop(self) -> None:
        with self.value_lock:
            self.cur_speed = float(self.sim_profile["speed_start"])
            self.cur_rpm = int(self.sim_profile["rpm_start"])
            self.speed_mode = "rise"

        while self.sim_running and self.can_opened:
            with self.value_lock:
                if self.speed_mode == "rise":
                    self.cur_speed += random.uniform(0.3, 1.1)
                    if self.cur_speed >= self.can.SPEED_RISE_MAX:
                        self.cur_speed = random.uniform(self.can.SPEED_STA_MIN, self.can.SPEED_STA_MAX)
                        self.speed_mode = "stable"
                else:
                    self.cur_speed = random.uniform(self.can.SPEED_STA_MIN, self.can.SPEED_STA_MAX)
                self.cur_rpm = random.randint(self.rpm_min, self.rpm_max)
                for pid, (min_value, max_value) in self.pid_ranges.items():
                    value = random.uniform(min_value, max_value)
                    self.responder.set_pid_value(pid, value)
                for signal, (min_value, max_value) in self.signal_ranges.items():
                    value = random.uniform(min_value, max_value)
                    self.responder.set_signal_value(signal, value)
            time.sleep(self.can.DATA_UPDATE_INTERVAL)

    def _recv_loop(self) -> None:
        while self.recv_running and self.can_opened and self.backend:
            try:
                messages = self.backend.receive(timeout_ms=100, max_messages=5)
                for msg in messages:
                    self._log_obd_request(msg)
                    items = self.responder.handle(msg)
                    self._log_obd_response_items(items)
                    for item in items:
                        if item.delay_ms > 0:
                            time.sleep(item.delay_ms / 1000)
                        self.backend.send(item.message)
            except Exception as exc:
                self.logger(f"CAN receive/send error: {exc}")
                self.recv_running = False
                self.can_opened = False
                break

    def _log_obd_request(self, msg) -> None:
        data = self.can.pad8(msg.data)
        if len(data) < 3:
            return
        payload_len = data[0] & 0x0F
        if payload_len >= 2 and data[1] == 0x01 and data[2] in self.WATCH_MODE01_PIDS:
            frame_type = "29bit" if msg.is_extended_id else "11bit"
            self.logger(
                f"CAN RX Mode01 PID 0x{data[2]:02X} request: "
                f"{frame_type} id=0x{msg.arbitration_id:X}, "
                f"data={' '.join(f'{item:02X}' for item in data)}"
            )
            return
        if payload_len >= 3 and data[1] == 0x22:
            did = (data[2] << 8) | data[3]
            if did in self.WATCH_UDS_DIDS:
                frame_type = "29bit" if msg.is_extended_id else "11bit"
                self.logger(
                    f"CAN RX UDS DID 0x{did:04X} request: "
                    f"{frame_type} id=0x{msg.arbitration_id:X}, "
                    f"data={' '.join(f'{item:02X}' for item in data)}"
                )

    def _log_obd_response_items(self, items) -> None:
        payload = self._isotp_payload_from_tx_items(items)
        if not payload or len(payload) < 2:
            return
        msg = items[0].message
        frame_type = "29bit" if msg.is_extended_id else "11bit"
        raw_data = " | ".join(" ".join(f"{byte:02X}" for byte in self.can.pad8(item.message.data)) for item in items)

        if payload[0] == 0x41 and payload[1] in self.WATCH_MODE01_PIDS:
            pid = payload[1]
            detail = self._describe_mode01_payload(pid, payload)
            self.logger(
                f"CAN TX Mode01 PID 0x{pid:02X} response: {detail}, "
                f"{frame_type} id=0x{msg.arbitration_id:X}, data={raw_data}"
            )
            return

        if payload[0] == 0x62 and len(payload) >= 3:
            did = (payload[1] << 8) | payload[2]
            if did in self.WATCH_UDS_DIDS:
                did_payload = " ".join(f"{byte:02X}" for byte in payload[3:])
                self.logger(
                    f"CAN TX UDS DID 0x{did:04X} response: payload={did_payload}, "
                    f"{frame_type} id=0x{msg.arbitration_id:X}, data={raw_data}"
                )

        if payload[0] in (0x43, 0x47, 0x4A):
            service_name = {0x43: "current", 0x47: "pending", 0x4A: "permanent"}[payload[0]]
            count = payload[1] if len(payload) >= 2 else 0
            dtc_payload = " ".join(f"{byte:02X}" for byte in payload[2:])
            self.logger(
                f"CAN TX WWH-OBD {service_name} DTC response: count={count}, payload={dtc_payload}, "
                f"{frame_type} id=0x{msg.arbitration_id:X}, data={raw_data}"
            )

    def _isotp_payload_from_tx_items(self, items) -> list[int] | None:
        if not items:
            return None
        first = self.can.pad8(items[0].message.data)
        pci_type = first[0] & 0xF0
        if pci_type == 0x00:
            payload_len = first[0] & 0x0F
            return first[1 : 1 + payload_len]
        if pci_type != 0x10:
            return None

        payload_len = ((first[0] & 0x0F) << 8) | first[1]
        payload = first[2:8]
        for item in items[1:]:
            data = self.can.pad8(item.message.data)
            if (data[0] & 0xF0) == 0x20:
                payload.extend(data[1:8])
        return payload[:payload_len]

    @staticmethod
    def _u16_from_payload(payload: list[int], index: int) -> int:
        return (payload[index] << 8) | payload[index + 1]

    @staticmethod
    def _u32_from_payload(payload: list[int], index: int) -> int:
        return (
            (payload[index] << 24)
            | (payload[index + 1] << 16)
            | (payload[index + 2] << 8)
            | payload[index + 3]
        )

    def _describe_mode01_payload(self, pid: int, payload: list[int]) -> str:
        if pid == 0x0D and len(payload) >= 3:
            return f"speed={payload[2]} km/h"
        if pid == 0xA6 and len(payload) >= 6:
            raw = self._u32_from_payload(payload, 2)
            return f"odometer_raw={raw}, decoded={raw / 10:.1f} km"
        if pid == 0x9A:
            if len(payload) >= 8:
                current_raw = self._u16_from_payload(payload, 2)
                voltage_raw = self._u16_from_payload(payload, 4)
                charging_state = payload[6]
                turn_signal_status = payload[7]
                return (
                    f"current_raw={current_raw}, decoded_current={current_raw * 0.1 - 1000:.1f} A, "
                    f"voltage_raw={voltage_raw}, decoded_voltage={voltage_raw * 0.1:.1f} V, "
                    f"charging_state={charging_state}, turn_signal_status={turn_signal_status}"
                )
            if len(payload) >= 6:
                ev_signal_keys = {"battery_pack_current", "battery_pack_voltage", "charging_state", "turn_signal_status"}
                if ev_signal_keys & (set(self.signal_values) | set(self.signal_ranges)):
                    current_raw = self._u16_from_payload(payload, 2)
                    voltage_raw = self._u16_from_payload(payload, 4)
                    return (
                        f"partial_ev_system current_raw={current_raw}, "
                        f"decoded_current={current_raw * 0.1 - 1000:.1f} A, "
                        f"voltage_raw={voltage_raw}, decoded_voltage={voltage_raw * 0.1:.1f} V, "
                        "charging_state/turn_signal_status will be sent after flow control"
                    )
                raw = self._u32_from_payload(payload, 2)
                return f"legacy_voltage_raw={raw}, decoded_voltage={raw / 100:.2f} V"
        if pid == 0xB7 and len(payload) >= 7:
            current_raw = self._u16_from_payload(payload, 2)
            voltage_raw = self._u16_from_payload(payload, 4)
            temp_raw = payload[6]
            return (
                f"current_raw={current_raw}, decoded_current={current_raw * 0.1 - 3276.8:.1f} A, "
                f"voltage_raw={voltage_raw}, decoded_voltage={voltage_raw * 0.1:.1f} V, "
                f"temp_raw={temp_raw}, decoded_temp={temp_raw - 40} C"
            )
        return "payload=" + " ".join(f"{byte:02X}" for byte in payload)

    @classmethod
    def _normalize_bitrate(cls, bitrate: int | str) -> int:
        text = str(bitrate).strip().lower().replace("k", "000")
        value = int(float(text))
        if value in (250, 500):
            value *= 1000
        if value not in cls.SUPPORTED_BITRATES:
            raise ValueError("CAN bitrate must be 250000 or 500000.")
        return value

    @classmethod
    def _normalize_id_format(cls, id_format: str) -> str:
        value = str(id_format).strip().lower().replace("-", "")
        if value in ("11", "standard", "std", "11bit"):
            return "11bit"
        if value in ("29", "extended", "ext", "29bit"):
            return "29bit"
        raise ValueError("CAN id format must be 11bit or 29bit.")

    @classmethod
    def _sim_profile(cls, id_format: str, bitrate: int) -> dict:
        normalized_id_format = cls._normalize_id_format(id_format)
        normalized_bitrate = cls._normalize_bitrate(bitrate)
        return can_core.SIM_PROFILES[(normalized_id_format, normalized_bitrate)]

    @staticmethod
    def _format_dtcs(dtcs: list[can_core.DtcEntry]) -> str:
        return ", ".join(f"{entry.high:02X}{entry.low:02X}" for entry in dtcs) or "none"


class DryRunCanSimulator:
    def __init__(self, logger: Callable[[str], None] | None = None):
        self.logger = logger or (lambda message: None)
        self.running = False
        self.config = {
            "id_format": "11bit",
            "bitrate": 500000,
            "channel_index": 0,
        }
        self.rpm_min = int(can_core.RPM_MIN)
        self.rpm_max = int(can_core.RPM_MAX)
        self.pid_values: dict[int, float | int] = {}
        self.pid_ranges: dict[int, tuple[float, float]] = {}
        self.signal_values: dict[str, float | int] = {}
        self.signal_ranges: dict[str, tuple[float, float]] = {}
        self.protocol_field_values: dict[str, float | int] = {}
        self.protocol_field_ranges: dict[str, tuple[float, float]] = {}
        self.raw_pid_payloads: dict[tuple[int, int], list[int]] = {}
        self.dtc_lists: dict[str, list[can_core.DtcEntry]] = {
            "current": [],
            "pending": [],
            "permanent": [],
        }

    def configure(
        self,
        bitrate: int | None = None,
        id_format: str | None = None,
        channel_index: int | None = None,
    ) -> None:
        if bitrate is not None:
            self.config["bitrate"] = HeadlessCanSimulator._normalize_bitrate(bitrate)
        if id_format is not None:
            self.config["id_format"] = HeadlessCanSimulator._normalize_id_format(id_format)
        if channel_index is not None:
            self.config["channel_index"] = int(channel_index)
        self.logger(
            "DRY-RUN CAN configured: "
            f"id_format={self.config['id_format']}, bitrate={self.config['bitrate']}, "
            f"channel={self.config['channel_index']}"
        )

    def set_pid_value(self, pid: int, value: float | int) -> None:
        pid_int = int(pid)
        self.pid_ranges.pop(pid_int, None)
        self.pid_values[pid_int] = value
        self.logger(f"DRY-RUN CAN PID 0x{pid_int:02X} value override set to {value}.")

    def set_pid_range(self, pid: int, minimum: float, maximum: float) -> None:
        pid_int = int(pid)
        min_value = float(minimum)
        max_value = float(maximum)
        if min_value > max_value:
            raise ValueError("CAN PID range minimum must be <= maximum.")
        self.pid_values.pop(pid_int, None)
        self.pid_ranges[pid_int] = (min_value, max_value)
        self.logger(f"DRY-RUN CAN PID 0x{pid_int:02X} dynamic range set to {min_value}-{max_value}.")

    def set_signal_value(self, signal: str, value: float | int) -> None:
        key = str(signal).strip()
        self.signal_ranges.pop(key, None)
        self.signal_values[key] = value
        self.logger(f"DRY-RUN CAN signal {key} value override set to {value}.")

    def set_signal_range(self, signal: str, minimum: float, maximum: float) -> None:
        key = str(signal).strip()
        min_value = float(minimum)
        max_value = float(maximum)
        if min_value > max_value:
            raise ValueError("CAN signal range minimum must be <= maximum.")
        self.signal_values.pop(key, None)
        self.signal_ranges[key] = (min_value, max_value)
        self.logger(f"DRY-RUN CAN signal {key} dynamic range set to {min_value}-{max_value}.")

    def set_protocol_field_value(self, field: str, value: float | int) -> None:
        key = str(field).strip()
        self.protocol_field_ranges.pop(key, None)
        self.protocol_field_values[key] = value
        self.logger(f"DRY-RUN protocol-only field {key} value stored as {value}; no CAN PID mapping is known yet.")

    def set_protocol_field_range(self, field: str, minimum: float, maximum: float) -> None:
        key = str(field).strip()
        min_value = float(minimum)
        max_value = float(maximum)
        if min_value > max_value:
            raise ValueError("Protocol-only field range minimum must be <= maximum.")
        self.protocol_field_values.pop(key, None)
        self.protocol_field_ranges[key] = (min_value, max_value)
        self.logger(f"DRY-RUN protocol-only field {key} range stored as {min_value}-{max_value}; no CAN PID mapping is known yet.")

    def set_rpm_range(self, minimum: int, maximum: int) -> None:
        self.rpm_min = int(minimum)
        self.rpm_max = int(maximum)
        self.pid_values.pop(0x0C, None)
        self.pid_ranges.pop(0x0C, None)
        self.logger(f"DRY-RUN CAN RPM range set to {self.rpm_min}-{self.rpm_max}, PID 0x0C override cleared.")

    def set_raw_pid_payload(self, service: int, pid: int, payload: list[int]) -> None:
        service_int = int(service)
        pid_int = int(pid)
        payload_bytes = [int(item) for item in payload]
        self.raw_pid_payloads[(service_int, pid_int)] = payload_bytes
        self.logger(
            f"DRY-RUN CAN raw PID response override set: service=0x{service_int:02X}, "
            f"pid=0x{pid_int:02X}, payload={' '.join(f'{item:02X}' for item in payload_bytes)}"
        )

    def set_dtc_list(self, kind: str, dtcs: list[can_core.DtcEntry]) -> None:
        target = can_core.ObdIsoTpResponder._dtc_target(kind)
        self.dtc_lists[target] = list(dtcs)
        formatted = HeadlessCanSimulator._format_dtcs(self.dtc_lists[target])
        self.logger(f"DRY-RUN CAN WWH-OBD {target} DTC list set to [{formatted}].")

    def clear_dtc_list(self, kind: str) -> None:
        self.set_dtc_list(kind, [])

    def open(self) -> None:
        self.logger(
            "DRY-RUN CAN opened: "
            f"id_format={self.config['id_format']}, bitrate={self.config['bitrate']}, "
            f"channel={self.config['channel_index']}"
        )

    def start(self) -> None:
        self.running = True
        self.logger("DRY-RUN CAN simulation started.")

    def stop(self) -> None:
        was_running = self.running
        self.running = False
        if was_running:
            self.logger("DRY-RUN CAN simulation stopped.")

    def close(self) -> None:
        self.running = False
        self.logger("DRY-RUN CAN closed.")
