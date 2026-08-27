from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .can_headless import DryRunCanSimulator, HeadlessCanSimulator
from .power_supply import DryRunPowerSupplyController, PowerSupplyController


class CaseRunner:
    def __init__(self, case: dict[str, Any], dry_run: bool = False, time_scale: float = 1.0, logger=print):
        self.case = case
        self.dry_run = dry_run
        self.time_scale = time_scale
        self.logger = logger
        self.steps_result: list[dict[str, Any]] = []
        self.current_voltage = float(case.get("power", {}).get("initial_voltage", 0.0))

        self.power = DryRunPowerSupplyController() if dry_run else PowerSupplyController(
            baudrate=case.get("power", {}).get("baudrate", 9600),
            current=case.get("power", {}).get("current", 2.0),
        )
        if dry_run:
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

    def log(self, message: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.logger(f"[{now}] {message}")

    def run(self) -> dict[str, Any]:
        started_at = datetime.now()
        self.log(f"Case start: {self.case.get('name', 'unnamed')}")
        status = "PASS"
        error_text = ""
        try:
            for index, step in enumerate(self.case["steps"], start=1):
                step_name = step.get("name") or step["action"]
                step_started = datetime.now()
                self.log(f"Step {index}: {step_name}")
                try:
                    self._run_step(step)
                    step_status = "PASS"
                except Exception as exc:
                    step_status = "FAIL"
                    error_text = str(exc)
                    status = "FAIL"
                    self.log(f"Step {index} failed: {exc}")
                    self.steps_result.append(
                        {
                            "index": index,
                            "name": step_name,
                            "action": step["action"],
                            "status": step_status,
                            "error": str(exc),
                            "started_at": step_started.isoformat(timespec="seconds"),
                            "finished_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    )
                    raise
                else:
                    self.steps_result.append(
                        {
                            "index": index,
                            "name": step_name,
                            "action": step["action"],
                            "status": step_status,
                            "error": "",
                            "started_at": step_started.isoformat(timespec="seconds"),
                            "finished_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    )
                    self.log(f"Step {index} done.")
        finally:
            self._cleanup()
            finished_at = datetime.now()

        return {
            "name": self.case.get("name", "unnamed"),
            "status": status,
            "error": error_text,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
            "steps": self.steps_result,
        }

    def _scaled_duration(self, seconds: float) -> float:
        return max(0.0, seconds * self.time_scale)

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
    import json

    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)

