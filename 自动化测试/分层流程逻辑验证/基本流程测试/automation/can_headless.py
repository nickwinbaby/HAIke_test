import random
import threading
import time
from typing import Callable

from . import can_core


class HeadlessCanSimulator:
    def __init__(
        self,
        backend: str = "winusb",
        vid: int = 0x04D8,
        pid: int = 0x0053,
        channel_index: int = 0,
        bitrate: int = 500000,
        logger: Callable[[str], None] | None = None,
    ):
        self.can = can_core
        self.backend_name = backend
        self.config = {
            "vid": vid,
            "pid": pid,
            "channel_index": channel_index,
            "bitrate": bitrate,
        }
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
        self.responder = self.can.ObdIsoTpResponder(self.get_values, self.can.VIN)

    def open(self) -> None:
        if self.can_opened:
            return
        if self.backend_name.lower() == "mock":
            self.backend = self.can.MockBackend()
        else:
            self.backend = self.can.WinUsbBackend(**self.config)
        self.backend.open()
        self.can_opened = True
        self.recv_running = True
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()
        self.logger(
            "CAN opened: "
            f"backend={self.backend_name}, bitrate={self.config['bitrate']}, "
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
            self.cur_speed = float(self.can.DEFAULT_SPEED)
            self.cur_rpm = int(self.can.DEFAULT_RPM)
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
                self.cur_rpm = random.randint(self.can.RPM_MIN, self.can.RPM_MAX)
            time.sleep(self.can.DATA_UPDATE_INTERVAL)

    def _recv_loop(self) -> None:
        while self.recv_running and self.can_opened and self.backend:
            try:
                messages = self.backend.receive(timeout_ms=100, max_messages=5)
                for msg in messages:
                    for item in self.responder.handle(msg):
                        if item.delay_ms > 0:
                            time.sleep(item.delay_ms / 1000)
                        self.backend.send(item.message)
            except Exception as exc:
                self.logger(f"CAN receive/send error: {exc}")
                self.recv_running = False
                self.can_opened = False
                break


class DryRunCanSimulator:
    def __init__(self, logger: Callable[[str], None] | None = None):
        self.logger = logger or (lambda message: None)
        self.running = False

    def open(self) -> None:
        self.logger("DRY-RUN CAN opened.")

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
