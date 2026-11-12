#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JT808 离线工具 —— 本地发送中转

为什么需要它：
    index.html 直接用浏览器 fetch 去 POST 平台接口时，如果平台没开 CORS，
    浏览器会拦掉响应（控制台报 "Failed to fetch"），即使平台其实已经收到了。

它做什么：
    在 127.0.0.1:8099 起一个极小的 HTTP 服务，页面把请求发给它，
    它再用 urllib 转发到真正的平台地址，并把平台的应答原样回给页面。

怎么用：
    1) 命令行：python send_relay.py
       默认目标 http://10.85.40.3:1813/client/sendRaw
       可改：  python send_relay.py --target http://10.85.40.3:1813/client/sendRaw --port 8099
    2) 页面「改地址」里把 URL 换成 http://127.0.0.1:8099/client/sendRaw
    3) 点「发送到设备」

只用标准库，Python 3.7+ 即可。
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_TARGET = "http://10.85.40.3:1813/client/sendRaw"

CFG = {"target": DEFAULT_TARGET, "timeout": 15}


class Handler(BaseHTTPRequestHandler):
    server_version = "JT808Relay/1.0"

    # ---- 统一 CORS，允许页面从 file:// 或任意本地端口访问 ----
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        """给浏览器直接打开时看的自检页"""
        if self.path.rstrip("/") in ("", "/health"):
            body = json.dumps(
                {"ok": True, "relay": "jt808", "target": CFG["target"]},
                ensure_ascii=False,
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b""

        # 校验一下页面发来的东西，顺手把格式问题挡在这里
        try:
            req_obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._reply(400, {
                "code": 400, "message": "中转收到的主体不是合法 JSON: %s" % e,
            })
            return

        imei = str(req_obj.get("imei", "")).strip()
        cmd = str(req_obj.get("cmd", "")).strip()
        if not imei or not cmd:
            self._reply(400, {
                "code": 400, "message": "缺少 imei 或 cmd",
            })
            return

        c = cmd.upper().replace(" ", "")
        warn = []
        if len(c) % 2:
            warn.append("cmd 十六进制位数为奇数")
        if not c.startswith("7E"):
            warn.append("cmd 未以 7E 开头，确认平台是否要求带帧头")
        if not c.endswith("7E"):
            warn.append("cmd 未以 7E 结尾")

        print("[中转] --> %s" % CFG["target"])
        print("[中转]     imei=%s  cmd=%s (%d 字节)" % (imei, c, len(c) // 2))
        if warn:
            print("[中转]     [!] %s" % "；".join(warn))

        payload = json.dumps({"imei": imei, "cmd": c}).encode("utf-8")
        req = urllib.request.Request(
            CFG["target"], data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=CFG["timeout"]) as r:
                body = r.read().decode("utf-8", "replace")
                print("[中转] <-- HTTP %d  %s" % (r.status, body[:300]))
                self._passthrough(r.status, body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            print("[中转] <-- HTTP %d  %s" % (e.code, body[:300]))
            self._passthrough(e.code, body)
        except Exception as e:
            msg = "%s: %s" % (type(e).__name__, e)
            print("[中转] <-- 失败  %s" % msg)
            self._reply(504, {
                "code": 504,
                "message": "中转连不上平台 %s（%s）" % (CFG["target"], msg),
            })

    # ---- 帮助函数 ----
    def _reply(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _passthrough(self, status, text):
        """平台回什么就原样给页面什么，让页面自己判断 code"""
        body = text.encode("utf-8", "replace")
        self.send_response(status if 200 <= status < 600 else 502)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # 关掉默认访问日志，输出更干净


def main(argv=None):
    ap = argparse.ArgumentParser(description="JT808 离线工具本地发送中转")
    ap.add_argument("--target", default=DEFAULT_TARGET, help="平台发送接口完整地址")
    ap.add_argument("--port", type=int, default=8099, help="本地监听端口，默认 8099")
    ap.add_argument("--timeout", type=float, default=15, help="转发超时秒数，默认 15")
    a = ap.parse_args(argv)

    CFG["target"] = a.target
    CFG["timeout"] = a.timeout

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError as e:
        print("[错误] 端口 %d 起不来：%s" % (a.port, e))
        print("       换个端口：python send_relay.py --port 8100")
        return 1

    print("=" * 62)
    print("  JT808 本地发送中转已启动")
    print("  监听   http://127.0.0.1:%d/client/sendRaw" % a.port)
    print("  转发至 %s" % a.target)
    print("  超时   %.0f 秒" % a.timeout)
    print("-" * 62)
    print("  页面「改地址」里填：http://127.0.0.1:%d/client/sendRaw" % a.port)
    print("  Ctrl+C 停止")
    print("=" * 62)

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[中转] 已停止")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
