#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JT808 平台接口分层诊断

解决的问题：
    页面上点「发送到设备」没反应时，到底是
      (a) 本机网络到不了平台？
      (b) 平台进程没起 / 被防火墙劫持？
      (c) 接口通了、但设备关机导致平台拒绝下发？
    这三种情况的处置完全不同，靠猜没有意义。本脚本从下往上逐层探，
    每层给出「通/不通」的硬证据，最后给一个明确结论。

分层：
    [1] DNS        域名能否解析成 IP（填 IP 时跳过）
    [2] TCP        三次握手能否完成，握手耗时多少
    [3] 裸 HTTP    握手成立后，发最小 HTTP 请求能否收到任何字节
    [4] POST 探测  空 body 打到 /client/send，看平台是否回 HTTP 状态码
    [5] 真实下发   仅在明确指定 --send 时执行

为什么 [3] 是关键：
    TCP 握手成功只说明「有东西回了 SYN-ACK」。如果这个 SYN-ACK 是防火墙
    或边界设备代答的，握手会瞬间成功（耗时异常接近 0），但之后发什么
    都不回字节 —— 这是劫持的典型特征，与设备是否开机毫无关系。

用法：
    python diagnose.py
    python diagnose.py --host 10.85.40.3 --port 1808 --path /client/send
    python diagnose.py --no-probe-post                 # 只探到第 3 层
    python diagnose.py --imei 869595066539 --cmd 7E... --send

只用标准库，Python 3.7+。
"""

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request

LINE = "-" * 68

# 平台应答里出现这些词，基本可以判定是「设备不在线」而不是「网络不通」
OFFLINE_WORDS = (
    "不在线", "离线", "未上线", "未连接", "无连接", "已离线",
    "offline", "not online", "not connected", "disconnected",
)

RES = {
    "host": "", "port": 0, "path": "/",
    "dns": None, "tcp": None, "raw": None, "probe": None, "send": None,
}


def section(n, title):
    print("\n[%d] %s" % (n, title))
    print(LINE)


def note(msg):
    print("    %s" % msg)


def fmt_ms(sec):
    return "%.3f s" % sec


# ---------------------------------------------------------------- [1] DNS
def do_dns(host, timeout=3.0):
    """host 已经是 IP 就直接通过"""
    if not host:
        return {"ok": False, "addrs": [], "err": "host 为空"}
    try:
        socket.inet_aton(host)
        return {"ok": True, "addrs": [host], "err": None, "literal": True}
    except OSError:
        pass
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        addrs = []
        for it in infos:
            a = it[4][0]
            if a not in addrs:
                addrs.append(a)
        return {"ok": bool(addrs), "addrs": addrs, "err": None,
                "elapsed": time.perf_counter() - t0}
    except Exception as e:
        return {"ok": False, "addrs": [], "err": "%s: %s" % (type(e).__name__, e),
                "elapsed": time.perf_counter() - t0}


# ---------------------------------------------------------------- [2] TCP
def do_tcp(host, port, timeout=3.0, tries=3):
    """多次握手，看耗时是否稳定；耗时异常接近 0 是劫持的可疑信号"""
    samples, err = [], None
    for _ in range(tries):
        t0 = time.perf_counter()
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            samples.append(time.perf_counter() - t0)
            s.close()
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
            break
    ok = len(samples) == tries
    return {
        "ok": ok,
        "samples": samples,
        "best": min(samples) if samples else None,
        "err": err,
    }


# ------------------------------------------------------- [3] 裸 HTTP 字节
def do_raw(host, port, path, timeout=4.0):
    """发最小 GET，看能不能收到任何字节。

    关键：必须区分「收到 0 字节」的两种成因 ——
      · closed_by_peer=True  → 对端主动 FIN/关闭连接。说明**那里真有服务在跑**，
                               只是它不认识 HTTP（比如 JT808 私有 TCP 端口），
                               或认为请求非法而断开。这不是劫持。
      · closed_by_peer=False → 连接一直被吊着、到期无任何字节。这才是
                               防火墙/边界设备吞包的特征。
    """
    s = None
    t0 = time.perf_counter()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        req = ("GET %s HTTP/1.0\r\nHost: %s:%d\r\nUser-Agent: jt808-diag\r\n"
               "Connection: close\r\n\r\n" % (path, host, port)).encode()
        s.sendall(req)
        buf = b""
        closed = False
        while len(buf) < 512:
            try:
                chunk = s.recv(512)
            except socket.timeout:
                break                      # 超时：连接还在，但对端不说话
            if not chunk:
                closed = True              # recv 返回 b"" = 对端发了 FIN
                break
            buf += chunk
        return {"bytes": len(buf), "peek": buf[:300], "err": None,
                "closed_by_peer": closed, "timed_out": (not closed and len(buf) == 0),
                "elapsed": time.perf_counter() - t0}
    except socket.timeout:
        return {"bytes": 0, "peek": b"", "err": "timeout（%.0f 秒内无任何字节）" % timeout,
                "closed_by_peer": False, "timed_out": True,
                "elapsed": time.perf_counter() - t0}
    except ConnectionResetError as e:
        return {"bytes": 0, "peek": b"", "err": "RST（对端重置连接）",
                "closed_by_peer": True, "timed_out": False, "rst": True,
                "elapsed": time.perf_counter() - t0}
    except Exception as e:
        return {"bytes": 0, "peek": b"", "err": "%s: %s" % (type(e).__name__, e),
                "closed_by_peer": False, "timed_out": False,
                "elapsed": time.perf_counter() - t0}
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def probe_tcp_payload(host, port, payload, timeout=4.0):
    """往端口灌一段自定义字节，观察对端如何反应。

    用来判断端口是不是「非 HTTP 的私有 TCP 协议」：
    灌垃圾数据后若对端立即 FIN/RST，说明有服务在做协议解析 —— 端口是活的。
    """
    s = None
    t0 = time.perf_counter()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(payload)
        try:
            d = s.recv(256)
            return {"closed_by_peer": d == b"", "timed_out": False,
                    "bytes": len(d), "peek": d[:120],
                    "elapsed": time.perf_counter() - t0}
        except socket.timeout:
            return {"closed_by_peer": False, "timed_out": True,
                    "bytes": 0, "peek": b"", "elapsed": time.perf_counter() - t0}
        except ConnectionResetError:
            return {"closed_by_peer": True, "timed_out": False,
                    "bytes": 0, "peek": b"", "rst": True,
                    "elapsed": time.perf_counter() - t0}
    except Exception as e:
        return {"closed_by_peer": False, "timed_out": False, "bytes": 0, "peek": b"",
                "err": "%s: %s" % (type(e).__name__, e),
                "elapsed": time.perf_counter() - t0}
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


# ------------------------------------------------------ [4][5] HTTP 请求
def http_post(url, payload, timeout=8.0):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "jt808-diag"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return {"status": r.status, "body": body,
                    "elapsed": time.perf_counter() - t0, "err": None}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return {"status": e.code, "body": body,
                "elapsed": time.perf_counter() - t0, "err": None}
    except Exception as e:
        return {"status": None, "body": "",
                "elapsed": time.perf_counter() - t0,
                "err": "%s: %s" % (type(e).__name__, e)}


def looks_offline(text):
    low = (text or "").lower()
    return any(w in low for w in OFFLINE_WORDS)


# ---------------------------------------------------------------- 结论
def is_loopback(host):
    """本机回环地址握手必然是 0 秒，不能据此判定劫持"""
    return host in ("127.0.0.1", "localhost", "::1") or host.startswith("127.")


def norm_path(p):
    """修正被 shell 改写的 --path。

    Git Bash / MSYS2 默认会把形如 / 或 /client/send 的单个参数当成 POSIX 路径，
    转换成 C:/Program Files/Git/client/send 之类。这里把这种畸形值还原回 /。
    """
    p = (p or "/").strip()
    if p.startswith("/") and not p.startswith("//"):
        return p
    # 命中 Windows 路径特征 → 说明被 shell 改写过
    if len(p) > 1 and p[1] == ":" or "\\" in p:
        return "/"
    return "/" + p.lstrip("/")


def verdict(r):
    """返回 (标签, 一句话结论, [依据...], [建议...])"""
    if not r["dns"]["ok"]:
        return ("A", "DNS 解析失败 —— 还没进入网络层",
                ["%s 无法解析：%s" % (r["host"], r["dns"]["err"])],
                ["检查主机名拼写，或直接在 --host 里填 IP。"])

    if not r["tcp"]["ok"]:
        return ("B", "TCP 握手失败 —— 网络层不通，与设备无关",
                ["%s:%d 连不上：%s" % (r["host"], r["port"], r["tcp"]["err"])],
                ["确认平台服务已启动、端口号正确。",
                 "确认本机与平台在同一网段 / VPN、路由可达。",
                 "请 IT 放通本机到 %s:%d 的出站规则。" % (r["host"], r["port"]),
                 "换一台在平台网段内的机器重跑本脚本对比。"])

    if r["raw"]["bytes"] == 0:
        best = r["tcp"]["best"]
        raw = r["raw"]

        # 情况一：对端主动 FIN/RST —— 那里真的有服务，只是它不讲 HTTP
        if raw.get("closed_by_peer"):
            how = "RST 重置" if raw.get("rst") else "主动 FIN 关闭"
            return ("G", "端口是活的，但不是 HTTP 服务 —— 别用 HTTP 打它",
                    ["TCP 握手成功（最快 %s）" % fmt_ms(best),
                     "发出 HTTP 请求后对端 %s（%s）" % (how, fmt_ms(raw["elapsed"])),
                     "对端主动断开说明有进程在做协议解析，不是防火墙吞包",
                     "该端口很可能跑的是 JT808 等私有 TCP 协议，不是 /client/send 这种 HTTP 接口"],
                    ["确认这个端口到底是「设备接入端口」还是「Web 接口端口」，两者用途不同：",
                     "· JT808 接入端口 → 设备自己连上来注册/上报，不能 POST JSON；",
                     "· Web 接口端口 → 才接受 imei/cmd 的 POST 下发。",
                     "若确实要下发指令，请向平台方索取 Web 接口地址（通常是 80/443 + /client/send）。",
                     "可用 --payload-hex 灌一段真实 JT808 帧，观察对端是否有应答。"])

        # 情况二：一直吊着、到期零字节 —— 这才是劫持/吞包
        ev = ["TCP 握手成功（最快 %s）" % fmt_ms(best),
              "但发出 HTTP 请求后 %s 内收到 0 个字节（连接被吊住，未关闭）"
              % fmt_ms(raw["elapsed"])]
        if best is not None and best < 0.005 and not is_loopback(r["host"]):
            ev.append("握手耗时 %s，异常接近 0 —— 典型 SYN-ACK 代答特征" % fmt_ms(best))
        return ("C", "TCP 能握手但应用层零响应 —— 被中间设备劫持，与设备无关",
                ev,
                ["这是防火墙 / 边界设备代答了三次握手，后面的 HTTP 根本没到平台。",
                 "请 IT 检查本机到 %s:%d 的访问策略。" % (r["host"], r["port"]),
                 "换一台平台网段内的机器，或在平台本机执行 curl 对比。",
                 "注意：设备关机不会造成这个现象 —— 设备离线时平台仍会正常回 HTTP 应答。"])

    # raw 有字节 → 应用层是活的。优先用「真实下发」的应答下结论，其次才用探测应答。
    offline_adv = ["平台侧链路已打通，问题在设备侧。逐条确认：",
                   "① 设备是否已开机 —— 关机时平台只能回「不在线」；",
                   "② SIM 是否已注网、有无欠费；",
                   "③ 设备配置的服务器地址/端口是否就是这个平台；",
                   "④ imei 是否与设备实际上报的终端手机号一致（取 IMSI 后 12 位）。"]

    src = None
    if r.get("send") and r["send"]["status"] is not None:
        src, label = r["send"], "真实下发"
    elif r["probe"] and r["probe"]["status"] is not None:
        src, label = r["probe"], "探测请求"

    if src is not None:
        body = src["body"]
        ev = ["%s HTTP %d" % (label, src["status"]),
              "应答片段：%s" % body[:160]]

        if looks_offline(body):
            return ("F", "平台接口正常，且明确回复「设备不在线」—— 设备侧问题",
                    ev, offline_adv)

        # 应答里有 code:200 才算真受理
        ok200 = False
        try:
            obj = json.loads(body)
            ok200 = isinstance(obj, dict) and obj.get("code") in (200, "200")
        except Exception:
            pass

        if ok200:
            return ("E", "平台接口正常，且已受理下发 —— 发送功能可用",
                    ev + ["应答 code=200，平台已接收并转发"],
                    ["链路整体通。若设备仍无动作，去看设备上行的 0x0001 / 0x0104 回包。"])

        if label == "真实下发":
            return ("E", "平台接口正常，但业务层拒绝了这次下发",
                    ev,
                    ["接口是通的，问题在参数或设备状态上：",
                     "核对 imei 是否为此设备的终端手机号；",
                     "核对 cmd 是否为完整 7E…7E 帧、校验码是否正确。"])

        return ("E", "平台接口活着，空 body 探测被业务层拒绝（正常现象）",
                ev + ["空 body 被拒恰恰说明 /client/send 已经在正常工作"],
                ["接口是通的。加 --send --imei … --cmd … 用真实报文再下发一次，看平台怎么回。"])

    return ("D", "应用层有响应，但 POST 探测未取得状态码",
            ["裸 GET 收到 %d 字节" % r["raw"]["bytes"],
             "POST 探测：%s" % (r["probe"]["err"] if r["probe"] else "未执行")],
            ["用真实报文下发一次确认业务链路。"])


def print_verdict(v):
    tag, title, ev, adv = v
    print("\n" + "=" * 68)
    print("  结论 [%s] %s" % (tag, title))
    print("=" * 68)
    print("  依据：")
    for e in ev:
        print("    · %s" % e)
    print("  建议：")
    for a in adv:
        print("    · %s" % a)
    print("=" * 68)


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="JT808 平台接口分层诊断：区分「网络不通」与「设备离线」")
    ap.add_argument("--host", default="10.85.40.3", help="平台地址，默认 10.85.40.3")
    ap.add_argument("--port", type=int, default=1808, help="平台端口，默认 1808")
    ap.add_argument("--path", default="/client/send", help="接口路径，默认 /client/send")
    ap.add_argument("--tcp-timeout", type=float, default=3.0, help="单次握手超时秒，默认 3")
    ap.add_argument("--timeout", type=float, default=8.0, help="HTTP 请求超时秒，默认 8")
    ap.add_argument("--no-probe-post", action="store_true",
                    help="跳过第 4 层空 body POST 探测")
    ap.add_argument("--imei", default="", help="真实下发用的 imei（IMSI 后 12 位）")
    ap.add_argument("--cmd", default="", help="真实下发用的报文十六进制")
    ap.add_argument("--send", action="store_true",
                    help="第 5 层：用 --imei/--cmd 真实下发一次（会真的下指令给设备）")
    ap.add_argument("--payload-hex", default="",
                    help="向该端口灌一段原始字节(hex)，用来判断是否为 JT808 等私有 TCP 端口")
    a = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    host, port, path = a.host.strip(), a.port, a.path
    path = norm_path(path)
    url = "http://%s:%d%s" % (host, port, path)
    RES["host"], RES["port"], RES["path"] = host, port, path

    print("=" * 68)
    print("  JT808 平台接口分层诊断")
    print("  目标  %s" % url)
    print("  时间  %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 68)

    # [1]
    section(1, "DNS / 地址解析")
    r1 = do_dns(host)
    RES["dns"] = r1
    if r1["ok"]:
        note("OK  -> %s%s" % (", ".join(r1["addrs"]),
                              "（直接是 IP，跳过解析）" if r1.get("literal")
                              else "（%.3f s）" % r1.get("elapsed", 0)))
    else:
        note("FAIL -> %s" % r1["err"])

    # [2]
    section(2, "TCP 三次握手  %s:%d" % (host, port))
    if not r1["ok"]:
        note("SKIP -> 上一层失败")
        RES["tcp"] = {"ok": False, "samples": [], "best": None, "err": "DNS 失败"}
    else:
        r2 = do_tcp(host, port, a.tcp_timeout)
        RES["tcp"] = r2
        if r2["ok"]:
            note("OK  -> 握手 3 次全部成功")
            for i, s in enumerate(r2["samples"], 1):
                note("       第 %d 次 %s" % (i, fmt_ms(s)))
            if r2["best"] < 0.005 and not is_loopback(host):
                note("     [!] 最快 %s，接近 0 —— 可能不是真机应答" % fmt_ms(r2["best"]))
        else:
            note("FAIL -> %s" % r2["err"])

    # [3]
    section(3, "应用层裸 HTTP 探测（发最小 GET，看有无字节）")
    if not RES["tcp"]["ok"]:
        note("SKIP -> 上一层失败")
        RES["raw"] = {"bytes": 0, "peek": b"", "err": "TCP 不通", "elapsed": 0}
    else:
        r3 = do_raw(host, port, path)
        RES["raw"] = r3
        if r3["bytes"] > 0:
            note("OK  -> 收到 %d 字节，耗时 %s" % (r3["bytes"], fmt_ms(r3["elapsed"])))
            head = r3["peek"].decode("utf-8", "replace").splitlines()
            for ln in head[:4]:
                note("       | %s" % ln)
        elif r3.get("closed_by_peer"):
            how = "RST 重置" if r3.get("rst") else "主动 FIN 关闭"
            note("[!]  0 字节，但对端%s（%s）" % (how, fmt_ms(r3["elapsed"])))
            note("     -> 端口上有服务在跑，它只是不认识 HTTP")
        else:
            note("FAIL -> 0 字节，连接被吊住直到超时  %s" % r3["err"])

    # [3.5] 可选：灌一段原始字节，判断是否为私有协议端口
    if a.payload_hex and RES["tcp"]["ok"]:
        section("3.5", "私有协议探测（灌入 --payload-hex）")
        try:
            pl = bytes.fromhex(a.payload_hex.replace(" ", ""))
        except ValueError as e:
            note("FAIL -> --payload-hex 不是合法十六进制：%s" % e)
            pl = None
        if pl:
            note("--> %d 字节：%s%s" % (len(pl), pl[:24].hex().upper(),
                                      "…" if len(pl) > 24 else ""))
            rp = probe_tcp_payload(host, port, pl, a.timeout)
            if rp.get("bytes"):
                note("<-- %d 字节，耗时 %s" % (rp["bytes"], fmt_ms(rp["elapsed"])))
                note("    %s" % rp["peek"].hex().upper())
                note("    => 有应答，该端口在讲这门协议")
            elif rp.get("closed_by_peer"):
                how = "RST" if rp.get("rst") else "FIN"
                note("<-- 对端%s 关闭（%s），无应答" % (how, fmt_ms(rp["elapsed"])))
                note("    => 服务在做协议解析但拒绝了这段报文（校验/字段/未注册等）")
            else:
                note("<-- %s 内无应答，连接保持" % fmt_ms(rp["elapsed"]))
                note("    => 服务沉默，可能仅在等完整帧或未开该消息")

    # [4]
    section(4, "POST 探测（空 body，只为确认接口是否活着）")
    if a.no_probe_post:
        note("SKIP -> --no-probe-post")
        RES["probe"] = None
    elif RES["raw"]["bytes"] == 0:
        note("SKIP -> 上一层应用层已不通，再打一次也没意义")
        RES["probe"] = None
    else:
        r4 = http_post(url, {}, a.timeout)
        RES["probe"] = r4
        if r4["status"] is not None:
            note("OK  -> HTTP %d  耗时 %s" % (r4["status"], fmt_ms(r4["elapsed"])))
            note("       | %s" % (r4["body"][:200].replace("\n", " ") or "（空）"))
        else:
            note("FAIL -> %s" % r4["err"])

    # [5]
    section(5, "真实下发")
    if not a.send:
        note("SKIP -> 未指定 --send（本层会真的把指令下发到设备，故默认关闭）")
    elif not a.imei or not a.cmd:
        note("FAIL -> --send 需要同时给 --imei 和 --cmd")
    elif RES["raw"]["bytes"] == 0:
        note("SKIP -> 应用层不通，下发必然失败")
    else:
        payload = {"imei": a.imei.strip(), "cmd": a.cmd.strip().upper().replace(" ", "")}
        note("--> imei=%s  cmd=%s (%d 字节)"
             % (payload["imei"], payload["cmd"][:40] + ("…" if len(payload["cmd"]) > 40 else ""),
                len(payload["cmd"]) // 2))
        r5 = http_post(url, payload, a.timeout)
        RES["send"] = r5
        if r5["status"] is not None:
            note("<-- HTTP %d  耗时 %s" % (r5["status"], fmt_ms(r5["elapsed"])))
            note("    | %s" % (r5["body"][:300].replace("\n", " ") or "（空）"))
            RES["probe"] = r5          # 有真实应答时，结论按真实应答给
        else:
            note("<-- FAIL %s" % r5["err"])

    print_verdict(verdict(RES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
