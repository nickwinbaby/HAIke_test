from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .can_headless import DryRunCanSimulator, HeadlessCanSimulator
from .power_supply import DryRunPowerSupplyController, PowerSupplyController


@dataclass
class RuntimeOptions:
    dry_run: bool = False
    manual: bool = False
    time_scale: float = 1.0


class StepRunner:
    def __init__(self, case: dict[str, Any], options: RuntimeOptions):
        self.case = case
        self.options = options
        self.power = DryRunPowerSupplyController() if options.dry_run else PowerSupplyController(
            baudrate=case.get("power", {}).get("baudrate", 9600),
            current=case.get("power", {}).get("current", 2.0),
        )
        if options.dry_run:
            self.can = DryRunCanSimulator(self.log)
        else:
            can_config = case.get("can", {})
            self.can = HeadlessCanSimulator(
                backend=can_config.get("backend", "winusb"),
                vid=int(str(can_config.get("vid", "0x04D8")), 0),
                pid=int(str(can_config.get("pid", "0x0053")), 0),
                channel_index=int(can_config.get("channel_index", 0)),
                bitrate=int(can_config.get("bitrate", 500000)),
                logger=self.log,
            )
        self.current_voltage = float(case.get("power", {}).get("initial_voltage", 0.0))

    def log(self, message: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] {message}", flush=True)

    def run(self) -> None:
        self.log(f"Case start: {self.case.get('name', 'unnamed')}")
        try:
            for index, step in enumerate(self.case["steps"], start=1):
                name = step.get("name") or step["action"]
                self.log(f"Step {index}: {name}")
                self._run_step(step)
                self.log(f"Step {index} done.")
                if self.options.manual and index < len(self.case["steps"]):
                    input("Press Enter to run next step...")
        finally:
            self._cleanup()
        self.log("Case finished.")

    def _run_step(self, step: dict[str, Any]) -> None:
        action = step["action"]
        if action == "power.connect":
            port = self.power.connect(
                port=step.get("port") or self.case.get("power", {}).get("port"),
                keyword=step.get("keyword") or self.case.get("power", {}).get("keyword"),
            )
            self.log(f"Power connected on {port}.")
            return

        if action == "power.set_voltage":
            voltage = float(step["voltage"])
            self.power.set_voltage(voltage)
            self.current_voltage = voltage
            if step.get("output", "").lower() == "on":
                self.power.output_on()
            self.log(f"Power voltage set to {voltage:.2f} V.")
            return

        if action == "power.ramp_voltage":
            start = float(step.get("from", self.current_voltage))
            end = float(step["to"])
            duration = self._scaled_duration(float(step["duration"]))
            steps = step.get("steps")
            self.power.ramp_voltage(start, end, duration, int(steps) if steps else None)
            self.current_voltage = end
            self.log(f"Power ramp finished: {start:.2f} V -> {end:.2f} V in {duration:.2f}s.")
            return

        if action == "power.output_off":
            target_voltage = float(step.get("voltage", 0.0))
            self.power.set_voltage(target_voltage)
            self.current_voltage = target_voltage
            self.power.output_off()
            self.log(f"Power output off, voltage command {target_voltage:.2f} V.")
            return

        if action == "wait":
            seconds = self._scaled_duration(float(step["seconds"]))
            self.log(f"Waiting {seconds:.2f}s.")
            time.sleep(seconds)
            return

        if action == "can.start":
            self.can.start()
            return

        if action == "can.stop":
            self.can.stop()
            self.can.close()
            return

        raise ValueError(f"Unsupported action: {action}")

    def _scaled_duration(self, seconds: float) -> float:
        return max(0.0, seconds * self.options.time_scale)

    def _cleanup(self) -> None:
        try:
            self.can.close()
        except Exception as exc:
            self.log(f"CAN cleanup failed: {exc}")
        try:
            self.power.close()
        except Exception as exc:
            self.log(f"Power cleanup failed: {exc}")


def load_case(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)

