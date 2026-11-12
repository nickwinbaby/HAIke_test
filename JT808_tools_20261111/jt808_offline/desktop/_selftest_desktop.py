# -*- coding: utf-8 -*-
"""桌面壳回归测试：把 exe 当黑盒跑一遍关键链路。

用法（在 desktop 目录下）：
    E:/python/python.exe _selftest_desktop.py

优先测打好的 exe；没有 exe 时退回测 jt808_desktop.py 源码。
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "..", "JT808离线工具.exe")
SRC = os.path.join(HERE, "jt808_desktop.py")
PORT = 18130

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS  " + name)
    else:
        failed += 1
        print("  FAIL  " + name + ("   " + extra if extra else ""))


class Upstream(BaseHTTPRequestHandler):
    """假平台：原样回显收到的 imei/cmd"""
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            body = {}
        out = json.dumps({"code": 200, "data": {"flowId": "119"}, "echo": body,
                          "ct": self.headers.get("Content-Type")},
                         ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def post(path, obj, timeout=10):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data=data,
                                method="POST",
                                headers={"Content-Type": "application/json"})
    # 测试自己也要绕代理，否则会被系统代理带走
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def get(path, timeout=10):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open("http://127.0.0.1:%d%s" % (PORT, path), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    up = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    if os.path.isfile(EXE):
        cmd = [EXE, "--no-window", "--port", str(PORT)]
        target = "exe"
    else:
        cmd = [sys.executable, SRC, "--no-window", "--port", str(PORT)]
        target = "源码"
    print("测试对象：%s → %s\n" % (target, os.path.basename(cmd[0])))

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        # 等端口起来（onefile 解压要一两秒）
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                if get("/health", 1)[0] == 200:
                    ok = True
                    break
            except Exception:
                pass
        check("服务启动", ok)
        if not ok:
            return

        st, txt = get("/health")
        o = json.loads(txt)
        check("/health 标识正确", o.get("app") == "jt808-offline-tool" and o.get("ok"))
        check("/health 报 desktop 模式", o.get("mode") == "desktop")

        st, page = get("/")
        check("首页返回 200", st == 200)
        check("页面注入了 __JT808_DESKTOP__", "__JT808_DESKTOP__={enabled:true" in page)
        check("页面注入了心跳", 'fetch("/__ping"' in page)
        check("页面含桌面转发函数", "function viaDesktop" in page)
        check("页面含 desktopSendUrl", "function desktopSendUrl" in page)

        # 转发成功
        u = "http://127.0.0.1:%d/client/sendRaw" % up
        st, txt = post("/__proxy?u=" + urllib.parse.quote(u, safe=""),
                       {"imei": "115436621651", "cmd": "7E8001000500000000"})
        check("代理转发 200", st == 200, txt[:120])
        check("代理透传 body", "115436621651" in txt, txt[:120])
        check("代理保持 json 头", "application/json" in txt)

        # 上游不可达
        st, txt = post("/__proxy?u=" + urllib.parse.quote(
            "http://127.0.0.1:1/client/sendRaw", safe=""), {"a": 1})
        check("上游不可达回 502", st == 502, txt[:100])
        check("502 带 __proxy 结构", '"__proxy"' in txt)

        # 相对路径落到默认平台（沙箱内可能 200/500/502/504，只要不 404）
        st, txt = post("/client/sendRaw", {"a": 1})
        check("相对 /client/* 会转发而非 404", st != 404, str(st))

        # 非法 scheme
        st, txt = post("/__proxy?u=" + urllib.parse.quote("file:///c:/x", safe=""), {})
        check("file:// 被拒", st == 400)

        # 未知路径
        st, txt = get("/nope")
        check("未知路径 404", st == 404)

        # 心跳后健康仍正常（验证 Keep-Alive 不被搞坏）
        for _ in range(3):
            get("/__ping")
        check("连续心跳后服务存活", get("/health")[0] == 200)
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    print("\n" + "=" * 46)
    print("  通过 %d 项，失败 %d 项" % (passed, failed))
    print("=" * 46)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
