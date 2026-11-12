# -*- coding: utf-8 -*-
"""模拟平台 /client/send，用于本地验证"""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CASE = {"mode": "ok"}   # ok / fail / badjson / http500 / slow

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        print("[平台] 收到 %s  body=%s" % (self.path, raw.decode("utf-8", "replace")), flush=True)
        try:
            o = json.loads(raw)
            print("[平台]    imei=%s cmd=%s" % (o.get("imei"), o.get("cmd")), flush=True)
        except Exception:
            pass
        m = CASE["mode"]
        if m == "ok":
            return self._j(200, {"code": 200, "data": {"flowId": "119"}, "message": "成功"})
        if m == "fail":
            return self._j(200, {"code": 500, "data": {}, "message": "设备不在线"})
        if m == "badjson":
            return self._raw(200, b"OK, delivered")
        if m == "http500":
            return self._raw(500, b'{"code":500,"message":"internal"}')
        if m == "slow":
            import time; time.sleep(30)
            return self._j(200, {"code": 200, "data": {"flowId": "1"}, "message": "慢"})
    def _j(self, s, o):
        self._raw(s, json.dumps(o, ensure_ascii=False).encode())
    def _raw(self, s, b):
        self.send_response(s)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    mode = sys.argv[2] if len(sys.argv) > 2 else "ok"
    CASE["mode"] = mode
    print("[平台] 监听 127.0.0.1:%d  mode=%s" % (port, mode), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
