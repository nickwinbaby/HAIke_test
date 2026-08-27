from __future__ import annotations

import sys
import time
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import can_core
from can_headless import DryRunCanSimulator, HeadlessCanSimulator
from power_supply import DryRunPowerSupplyController, PowerSupplyController
from relay_usb import DryRunRelayUsbController, RelayUsbController


CAN_SIGNAL_PID_ALIASES = {
    "a": 0x05,
    "b": 0x11,
    "c": 0x04,
    "d": 0x10,
    "e": 0x0F,
    "f": 0x0B,
    "g": 0x42,
    "h": 0x2F,
    "i": 0x31,
    "j": 0x21,
    "m": 0xA6,
    "p": 0x5B,
    "q": 0xB2,
    "v": 0xB7,
    "x": 0x1F,
    "y": 0x51,
    "rpm": 0x0C,
    "engine_speed": 0x0C,
    "发动机转速": 0x0C,
    "speed": 0x0D,
    "vehicle_speed": 0x0D,
    "车速": 0x0D,
    "coolant_temp": 0x05,
    "engine_coolant_temperature": 0x05,
    "发动机冷却液温度": 0x05,
    "throttle": 0x11,
    "throttle_position": 0x11,
    "节气门位置": 0x11,
    "engine_load": 0x04,
    "calculated_engine_load": 0x04,
    "发动机负荷": 0x04,
    "air_flow": 0x10,
    "maf": 0x10,
    "进气流量": 0x10,
    "intake_temp": 0x0F,
    "intake_air_temperature": 0x0F,
    "进气温度": 0x0F,
    "intake_pressure": 0x0B,
    "intake_manifold_pressure": 0x0B,
    "进气压力": 0x0B,
    "battery_voltage": 0x42,
    "vehicle_battery_voltage": 0x42,
    "车辆电池电压": 0x42,
    "fuel_level": 0x2F,
    "fuel_tank_level": 0x2F,
    "油量": 0x2F,
    "distance_mil": 0x21,
    "mil_distance": 0x21,
    "distance_since_dtc": 0x21,
    "distance_with_mil_on": 0x21,
    "故障灯点亮后距离": 0x21,
    "distance_since_clear_dtc": 0x31,
    "distance_since_cleared_dtc": 0x31,
    "dtc清除后距离": 0x31,
    "fuel_rate": 0x5E,
    "hybrid_battery_life": 0x5B,
    "soc": 0x5B,
    "电池电量": 0x5B,
    "absolute_engine_load": 0x43,
    "ambient_air_temp": 0x46,
    "oil_temp": 0x5C,
    "engine_oil_temp": 0x5C,
    "oil_pressure": 0x0A,
    "engine_oil_pressure": 0x0A,
    "engine_percent_torque": 0x62,
    "odometer": 0xA6,
    "里程表": 0xA6,
    "obd_type": 0x1C,
    "air_flow_sensor": 0x66,
    "soh": 0xB2,
    "电池健康度": 0xB2,
    "battery_pack_temperature": 0xB7,
    "battery_temperature": 0xB7,
    "电池包温度": 0xB7,
    "ev_temp": 0xB7,
    "fuel_type": 0x51,
    "燃油类型": 0x51,
    "engine_run_time": 0x1F,
    "发动机运行时间": 0x1F,
}

CAN_SIGNAL_SPECIAL_ALIASES = {
    "r": "battery_pack_current",
    "s": "battery_pack_voltage",
    "t": "charging_state",
    "z": "turn_signal_status",
    "charging_state": "charging_state",
    "充电状态": "charging_state",
    "ev_current": "battery_pack_current",
    "battery_current": "battery_pack_current",
    "battery_pack_current": "battery_pack_current",
    "电池电流": "battery_pack_current",
    "ev_voltage": "battery_pack_voltage",
    "battery_pack_voltage": "battery_pack_voltage",
    "电池电压": "battery_pack_voltage",
    "turn_signal_status": "turn_signal_status",
    "turn_signals_status": "turn_signal_status",
    "转向灯状态": "turn_signal_status",
}

CAN_PROTOCOL_ONLY_FIELD_ALIASES = {
    "k1": "historical_total_mileage",
    "k2": "historical_total_fuel_consumption",
    "k3": "historical_total_driving_time",
    "l": "seatbelt_status",
    "n": "average_fuel_consumption",
    "o": "odometer_unit",
    "u": "remaining_range",
    "w": "next_service_distance",
    "historical_total_mileage": "historical_total_mileage",
    "历史总里程": "historical_total_mileage",
    "historical_total_fuel_consumption": "historical_total_fuel_consumption",
    "历史总油耗": "historical_total_fuel_consumption",
    "historical_total_driving_time": "historical_total_driving_time",
    "历史总行驶时间": "historical_total_driving_time",
    "seatbelt_status": "seatbelt_status",
    "安全带状态": "seatbelt_status",
    "average_fuel_consumption": "average_fuel_consumption",
    "平均油耗": "average_fuel_consumption",
    "odometer_unit": "odometer_unit",
    "里程单位": "odometer_unit",
    "remaining_range": "remaining_range",
    "剩余里程": "remaining_range",
    "next_service_distance": "next_service_distance",
    "下次保养里程": "next_service_distance",
    "def_tank_volume": "def_tank_volume",
    "尿素箱液位": "def_tank_volume",
    "transmission_gear": "transmission_gear",
    "档位": "transmission_gear",
    "accelerator_pedal": "accelerator_pedal",
    "加速踏板": "accelerator_pedal",
    "brake_pedal": "brake_pedal",
    "制动踏板": "brake_pedal",
    "clutch_slip": "clutch_slip",
    "离合器滑移": "clutch_slip",
}


class HardwareLibrary:
    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(
        self,
        dry_run: bool = True,
        time_scale: float = 1.0,
        power_baudrate: int = 9600,
        power_current: float = 2.0,
        can_backend: str = "winusb",
        can_vid: str = "0x04D8",
        can_pid: str = "0x0053",
        can_channel_index: int = 0,
        can_bitrate: int = 500000,
        can_id_format: str = "11bit",
    ):
        self.power_baudrate = int(power_baudrate)
        self.power_current = float(power_current)
        self.can_backend = str(can_backend)
        self.can_vid = int(str(can_vid), 0)
        self.can_pid = int(str(can_pid), 0)
        self.can_channel_index = int(can_channel_index)
        self.can_bitrate = int(can_bitrate)
        self.can_id_format = str(can_id_format)
        self.power_current = float(power_current)
        self.current_voltage = 0.0
        self.dry_run = True
        self.time_scale = float(time_scale)
        self.power = None
        self.can = None
        self.relay = None
        self._configure_runtime(dry_run=dry_run, time_scale=time_scale, log_status=False)

    def configure_runtime(self, dry_run: bool | None = None, time_scale: float | None = None) -> None:
        self._configure_runtime(dry_run=dry_run, time_scale=time_scale, log_status=True)

    def _configure_runtime(
        self,
        dry_run: bool | None = None,
        time_scale: float | None = None,
        log_status: bool = True,
    ) -> None:
        if dry_run is not None:
            new_dry_run = self._as_bool(dry_run)
        else:
            new_dry_run = self.dry_run
        if time_scale is not None:
            self.time_scale = float(time_scale)

        if self.power is not None and self.dry_run == new_dry_run:
            if log_status:
                self._log(f"Runtime configured: dry_run={self.dry_run}, time_scale={self.time_scale:.3f}")
            return

        if self.power is not None or self.can is not None or self.relay is not None:
            try:
                self.can.close()
            except Exception:
                pass
            try:
                self.power.close()
            except Exception:
                pass
            try:
                self.relay.close()
            except Exception:
                pass

        self.dry_run = new_dry_run
        if self.dry_run:
            self.power = DryRunPowerSupplyController()
            self.can = DryRunCanSimulator(self._log)
            self.relay = DryRunRelayUsbController()
        else:
            self.power = PowerSupplyController(baudrate=self.power_baudrate, current=self.power_current)
            self.can = HeadlessCanSimulator(
                backend=self.can_backend,
                vid=self.can_vid,
                pid=self.can_pid,
                channel_index=self.can_channel_index,
                bitrate=self.can_bitrate,
                id_format=self.can_id_format,
                logger=self._log,
            )
            self.relay = RelayUsbController()
        if log_status:
            self._log(f"Runtime configured: dry_run={self.dry_run}, time_scale={self.time_scale:.3f}")

    def configure_power_supply(self, current: float | None = None) -> None:
        if current is not None:
            self.power_current = float(current)
            self.power.current = self.power_current
            if getattr(self.power, "ser", None) and self.power.ser.is_open:
                self.power.set_current(self.power_current)
            self._log(f"Power current configured: {self.power_current:.3f} A")

    def connect_power_supply_usb(self) -> None:
        self._log("Connecting power supply USB...")
        port = self.power.connect()
        self._log(f"Power supply connected: {port}")

    def close_power_supply_usb(self) -> None:
        self._log("Closing power supply USB connection...")
        self.power.close()
        self._log("Power supply USB connection closed.")

    def set_power_current(self, current: float) -> None:
        self.power_current = float(current)
        self.power.set_current(self.power_current)
        self._log(f"Power current set to {self.power_current:.3f} A")

    def set_power_voltage(self, voltage: float, output: str = "off") -> None:
        target_voltage = float(voltage)
        self._log(f"Setting power voltage to {target_voltage:.2f} V, output={output}...")
        self.power.set_voltage(target_voltage)
        self.current_voltage = target_voltage
        if str(output).lower() == "on":
            self.power.set_current(self.power_current)
            self.power.output_on()
        self._log(f"Power voltage set to {target_voltage:.2f} V, output={output}")

    def ramp_power_voltage(self, start: float, end: float, duration: float, steps: int = 20) -> None:
        scaled_duration = self._scaled(float(duration))
        self._log(
            f"Ramping power voltage: {float(start):.2f} V -> {float(end):.2f} V "
            f"in {scaled_duration:.2f}s, steps={int(steps)}..."
        )
        self.power.ramp_voltage(float(start), float(end), scaled_duration, int(steps))
        self.current_voltage = float(end)
        self._log(f"Power ramp finished: {float(start):.2f} V -> {float(end):.2f} V in {scaled_duration:.2f}s")

    def start_can_simulation(self) -> None:
        self._log("Starting CAN simulation...")
        self.can.start()
        self._log("CAN simulation started.")

    def configure_can_simulation(
        self,
        id_format: str = "11bit",
        bitrate: int = 500000,
        channel_index: int = 0,
    ) -> None:
        self.can.configure(bitrate=int(bitrate), id_format=str(id_format), channel_index=int(channel_index))

    def set_can_pid_value(self, pid: str, value: float) -> None:
        pid_int = self._parse_int(pid)
        self.can.set_pid_value(pid_int, float(value))

    def set_can_pid_range(self, pid: str, minimum: float, maximum: float) -> None:
        pid_int = self._parse_int(pid)
        self.can.set_pid_range(pid_int, float(minimum), float(maximum))

    def set_can_signal_value(self, signal: str, value: float) -> None:
        kind, target = self._resolve_can_field(signal)
        if kind == "pid":
            self.can.set_pid_value(int(target), float(value))
        elif kind == "signal":
            self.can.set_signal_value(str(target), float(value))
        else:
            self.can.set_protocol_field_value(str(target), float(value))

    def set_can_signal_range(self, signal: str, minimum: float, maximum: float) -> None:
        kind, target = self._resolve_can_field(signal)
        if kind == "pid":
            self.can.set_pid_range(int(target), float(minimum), float(maximum))
        elif kind == "signal":
            self.can.set_signal_range(str(target), float(minimum), float(maximum))
        else:
            self.can.set_protocol_field_range(str(target), float(minimum), float(maximum))

    def set_can_field_value(self, field: str, value: float) -> None:
        self.set_can_signal_value(field, value)

    def set_can_field_range(self, field: str, minimum: float, maximum: float) -> None:
        self.set_can_signal_range(field, minimum, maximum)

    def set_can_rpm_range(self, minimum: float, maximum: float) -> None:
        self.can.set_rpm_range(int(minimum), int(maximum))

    def set_can_raw_pid_response(self, service: str, pid: str, payload: str) -> None:
        service_int = self._parse_int(service)
        pid_int = self._parse_int(pid)
        payload_bytes = self._parse_byte_list(payload)
        self.can.set_raw_pid_payload(service_int, pid_int, payload_bytes)

    def set_wwh_obd_current_dtc(self, function: str = "set", *dtcs) -> None:
        action = str(function).strip().lower()
        parsed_dtcs = [self._parse_wwh_dtc_entry(item) for item in dtcs]

        if action in ("set", "update", "override", "replace", "设置", "写入"):
            self.can.set_dtc_list("current", parsed_dtcs)
            self._log(
                "WWH-OBD current DTC set: "
                + (", ".join(f"{entry.high:02X}{entry.low:02X}" for entry in parsed_dtcs) or "none")
            )
            return

        if action in ("clear", "delete", "remove", "清除", "删除"):
            if parsed_dtcs:
                current = list(getattr(self.can, "dtc_lists", {}).get("current", []))
                remaining = [entry for entry in current if entry not in parsed_dtcs]
                self.can.set_dtc_list("current", remaining)
                self._log(
                    "WWH-OBD current DTC removed: "
                    + ", ".join(f"{entry.high:02X}{entry.low:02X}" for entry in parsed_dtcs)
                )
            else:
                self.can.clear_dtc_list("current")
                self._log("WWH-OBD current DTC cleared.")
            return

        raise ValueError("DTC function must be set/update/override/replace/clear/delete/remove.")

    def clear_wwh_obd_current_dtc(self) -> None:
        self.can.clear_dtc_list("current")
        self._log("WWH-OBD current DTC cleared.")

    def stop_can_simulation(self) -> None:
        self._log("Stopping CAN simulation...")
        self.can.stop()
        self.can.close()
        self._log("CAN simulation stopped and closed.")

    def close_can_connection(self) -> None:
        self._log("Closing CAN connection...")
        self.can.close()
        self._log("CAN connection closed.")

    def wait_seconds(self, seconds: float) -> None:
        scaled_seconds = self._scaled(float(seconds))
        self._log(f"Waiting {scaled_seconds:.2f}s")
        time.sleep(scaled_seconds)

    def power_off_to_zero(self) -> None:
        self._log("Powering off to 0.00 V...")
        self.power.set_voltage(0.0)
        self.current_voltage = 0.0
        self.power.output_off()
        self._log("Power output off, voltage command 0.00 V")

    def connect_relay_usb(self) -> None:
        self._log("Connecting USB relay...")
        info = self.relay.connect()
        self._log(
            "USB relay connected: "
            f"backend={info.backend}, product={info.product or 'N/A'}, path={info.display_path()}"
        )

    def close_relay_usb(self) -> None:
        self._log("Closing USB relay connection...")
        self.relay.close()
        self._log("USB relay connection closed.")

    def set_relay_channel(self, channel: int, state: str) -> None:
        closed = self._relay_state_to_closed(state)
        channel_int = int(channel)
        action = "closed/conducting" if closed else "open/disconnected"
        self._log(f"Setting relay channel {channel_int} to {action}...")
        self.relay.set_channel(channel_int, closed)
        self._log(f"Relay channel {channel_int} is {action}.")

    def close_relay_channel(self, channel: int) -> None:
        self.set_relay_channel(int(channel), "close")

    def open_relay_channel(self, channel: int) -> None:
        self.set_relay_channel(int(channel), "open")

    def set_all_relays(self, state: str) -> None:
        closed = self._relay_state_to_closed(state)
        action = "closed/conducting" if closed else "open/disconnected"
        self._log(f"Setting all relays to {action}...")
        self.relay.set_all(closed)
        self._log(f"All relays are {action}.")

    def close_all_relays(self) -> None:
        self.set_all_relays("close")

    def open_all_relays(self) -> None:
        self.set_all_relays("open")

    def cleanup_hardware(self) -> None:
        try:
            self.can.close()
        except Exception as exc:
            self._log(f"CAN cleanup failed: {exc}")
        try:
            self.power.close()
        except Exception as exc:
            self._log(f"Power cleanup failed: {exc}")
        try:
            self.relay.close()
        except Exception as exc:
            self._log(f"Relay cleanup failed: {exc}")

    def _scaled(self, seconds: float) -> float:
        return max(0.0, seconds * self.time_scale)

    @staticmethod
    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _parse_int(value) -> int:
        return int(str(value).strip(), 0)

    @classmethod
    def _normalize_key(cls, value: str) -> str:
        return str(value).strip().lower().replace("-", "_").replace(" ", "_")

    @classmethod
    def _resolve_can_field(cls, field: str) -> tuple[str, int | str]:
        key = cls._normalize_key(field)
        if key in CAN_SIGNAL_SPECIAL_ALIASES:
            return "signal", CAN_SIGNAL_SPECIAL_ALIASES[key]
        if key in CAN_SIGNAL_PID_ALIASES:
            return "pid", CAN_SIGNAL_PID_ALIASES[key]
        if key in CAN_PROTOCOL_ONLY_FIELD_ALIASES:
            return "protocol", CAN_PROTOCOL_ONLY_FIELD_ALIASES[key]
        return "pid", cls._parse_int(field)

    @classmethod
    def _signal_to_pid(cls, signal: str) -> int:
        kind, target = cls._resolve_can_field(signal)
        if kind != "pid":
            raise ValueError(f"CAN field {signal} is not a single OBD PID.")
        return int(target)

    @classmethod
    def _parse_byte_list(cls, value: str) -> list[int]:
        text = str(value).replace(",", " ").replace(";", " ")
        parts = [part for part in text.split() if part]
        return [cls._parse_int(part) for part in parts]

    @classmethod
    def _parse_wwh_dtc_entry(cls, value) -> can_core.DtcEntry:
        text = str(value).strip()
        if not text:
            raise ValueError("DTC entry cannot be empty.")

        text = text.replace(",", " ").replace(";", " ").replace("/", " ").replace("-", " ")
        parts = [part for part in text.split() if part]
        if len(parts) == 2:
            high = cls._parse_int(parts[0])
            low = cls._parse_int(parts[1])
            return can_core.DtcEntry(high=high, low=low)

        compact = "".join(parts).replace(" ", "")
        compact = compact[2:] if compact.lower().startswith("0x") else compact
        if len(compact) == 4:
            code = int(compact, 16)
            return can_core.DtcEntry(high=(code >> 8) & 0xFF, low=code & 0xFF)

        raise ValueError(
            f"DTC entry must be two bytes like '01 01' or a 4-digit hex code like '0101', got {value!r}."
        )

    @staticmethod
    def _relay_state_to_closed(state: str) -> bool:
        value = str(state).strip().lower()
        if value in ("close", "closed", "on", "conduct", "conducting", "通", "闭合", "合"):
            return True
        if value in ("open", "opened", "off", "disconnect", "disconnected", "断", "断开", "开"):
            return False
        raise ValueError("Relay state must be close/open, on/off, 通/断开, or 闭合/断开.")

    @staticmethod
    def _log(message: str) -> None:
        try:
            from robot.libraries.BuiltIn import BuiltIn

            BuiltIn().log(message)
            BuiltIn().log_to_console(message)
        except Exception:
            print(message, flush=True)
