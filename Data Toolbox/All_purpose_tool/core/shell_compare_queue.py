"""收集Windows资源管理器多选静态菜单逐项启动时传入的路径。"""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
import tempfile
import time


QUEUE_FILE = Path(tempfile.gettempdir()) / "richlink_gnss_compare_selection.json"
MUTEX_NAME = "Local\\RichlinkGNSSCompareSelectionMutex"
COLLECT_SECONDS = 0.8
STALE_SECONDS = 5.0


class _NamedMutex:
    def __enter__(self):
        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not self.handle:
            raise OSError("无法创建右键对比同步锁")
        wait_result = kernel32.WaitForSingleObject(self.handle, 5000)
        if wait_result not in (0, 0x80):
            kernel32.CloseHandle(self.handle)
            raise TimeoutError("等待右键对比同步锁超时")
        return self

    def __exit__(self, _type, _value, _traceback):
        ctypes.windll.kernel32.ReleaseMutex(self.handle)
        ctypes.windll.kernel32.CloseHandle(self.handle)


def _read_state(now: float) -> dict:
    try:
        state = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"started": now, "paths": []}
    if now - float(state.get("started", 0)) > STALE_SECONDS:
        return {"started": now, "paths": []}
    return state


def enqueue_shell_item(path: str) -> None:
    normalized = str(Path(path).absolute())
    now = time.time()
    with _NamedMutex():
        state = _read_state(now)
        paths = list(state.get("paths") or [])
        if normalized.casefold() not in {item.casefold() for item in paths}:
            paths.append(normalized)
        state["paths"] = paths
        QUEUE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def claim_shell_selection() -> tuple[str, str] | None:
    """恰好收集到两个项目时返回；一个或超过两个项目均不启动对比。"""
    now = time.time()
    with _NamedMutex():
        state = _read_state(now)
        paths = list(state.get("paths") or [])
        try:
            QUEUE_FILE.unlink()
        except FileNotFoundError:
            pass
        if len(paths) == 2:
            return paths[0], paths[1]
        return None


def collect_shell_selection(path: str) -> tuple[str, str] | None:
    enqueue_shell_item(path)
    time.sleep(COLLECT_SECONDS)
    return claim_shell_selection()

