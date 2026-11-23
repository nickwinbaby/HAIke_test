"""向设备平台发送组包结果。

两个围栏协议页面都使用相同的 JSON 结构：
    {"imei": "...", "cmd": "..."}
本模块只负责 HTTP 通信，不依赖旧工具或外部 EXE。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.parse
import urllib.request


@dataclass(frozen=True)
class CommandSendResult:
    url: str
    imei: str
    cmd: str
    status: int | None
    response_text: str
    error: str = ""

    @property
    def http_ok(self):
        return self.status is not None and 200 <= self.status < 300


def normalize_command_payload(url, imei, cmd):
    """校验并规范化接口地址、IMEI和十六进制命令。"""
    endpoint = str(url or "").strip()
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("发送接口必须是完整的 http:// 或 https:// 地址")

    device_id = re.sub(r"\s+", "", str(imei or ""))
    if not device_id:
        raise ValueError("IMEI不能为空")
    if not device_id.isdigit():
        raise ValueError("IMEI只能包含数字")

    command = re.sub(r"\s+", "", str(cmd or "")).upper()
    if not command:
        raise ValueError("CMD不能为空，请先生成组包数据")
    if len(command) % 2 or not re.fullmatch(r"[0-9A-F]+", command):
        raise ValueError("CMD必须是偶数位的十六进制数据")
    return endpoint, device_id, command


def send_command_json(url, imei, cmd, timeout=15):
    """以 application/json POST imei/cmd，保留平台的原始响应正文。"""
    endpoint, device_id, command = normalize_command_payload(url, imei, cmd)
    payload = json.dumps(
        {"imei": device_id, "cmd": command}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/plain, */*"},
        method="POST",
    )
    # 内网设备平台默认直连，避免继承Windows系统代理导致请求被错误转发。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        timeout_seconds = float(timeout)
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("发送超时时间应为1～120秒")
        with opener.open(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            text = response.read().decode("utf-8", "replace")
            return CommandSendResult(endpoint, device_id, command, status, text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return CommandSendResult(endpoint, device_id, command, exc.code, text, str(exc))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return CommandSendResult(endpoint, device_id, command, None, "", str(reason))
    except Exception as exc:
        return CommandSendResult(endpoint, device_id, command, None, "", f"{type(exc).__name__}: {exc}")
