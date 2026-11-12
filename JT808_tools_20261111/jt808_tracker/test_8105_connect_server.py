# -*- coding: utf-8 -*-
"""
0x8105 命令字 2「控制终端连接指定服务器」协议测试用例。

协议格式（表19，命令字 2）：
    连接控制;平台鉴权码;拨号点名称;拨号用户名;拨号密码;地址;TCP端口;UDP端口;连接到指定服务器时限
    · 半角分号分隔，共 9 个字段；无值的字段放空，但占位分号不能省
    · 连接控制 = 1 时无后继参数，整串只填 "1"
    · 连接控制 = 0 时按序填写；UDP 端口协议固定留空

用法：
    python test_8105_connect_server.py --list              # 只打印用例与完整帧 hex
    python test_8105_connect_server.py                    # 下发全部用例并核对 0x0001 应答
    python test_8105_connect_server.py --case TC1         # 只跑一条
    python test_8105_connect_server.py --addr 10.85.20.124 --port 7613

前提：平台服务已启动、设备已接入（设备列表里能选中这台）。
注意：--addr/--port 必须填平台真实的设备接入地址与端口，否则 TC1 把设备
      指到别的服务器后，后续用例收不到应答。命令字 2 会触发设备重连，
      脚本在每条之间等设备重新上线。

结果码：0=成功/确认  1=失败  2=消息有误  3=不支持
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

FLAG, ESC, ESC_FLAG, ESC_ESC = 0x7E, 0x7D, 0x02, 0x01
PHONE = "138001380001"

# (编号, 参数串模板, 期望结果码, 说明)
# 期望码 0 = 接受并执行；2 = 回「消息有误」，不执行
CASES = [
    ("TC1",  "0;AUTHCODE;cmnet;user;pwd;{addr};{port};;30", 0,
     "9 字段齐全，UDP 端口留空但占位分号保留"),
    ("TC2",  "0;;cmnet;;;{addr};{port};;30", 0,
     "鉴权码/用户名/密码/UDP 全空，仅靠分号占位"),
    ("TC3",  "1", 0,
     "连接控制=1，整串只有 1，无后继参数 → 撤销临时覆盖，回主服务器"),
    ("TC4",  "1;AUTHCODE;cmnet;;;{addr};{port};;30", 0,
     "连接控制=1 却带后继参数（协议不允许，固件应忽略并按默认服务器处理）"),
    ("TC5",  "0;AUTHCODE;cmnet;;;;{port};;30", 2,
     "地址为空 → 核心参数缺失，拒绝"),
    ("TC6",  "0;AUTHCODE;cmnet;;;{addr};;;30", 2,
     "TCP 端口为空 → 拒绝"),
    ("TC7",  "0;AUTHCODE;cmnet;;;{addr};{port};;0", 2,
     "连接时限为 0 → 拒绝"),
    ("TC8",  "2;AUTHCODE;cmnet;;;{addr};{port};;30", 2,
     "连接控制=2，超出 0/1 取值 → 拒绝"),
    ("TC9",  "x;AUTHCODE;cmnet;;;{addr};{port};;30", 2,
     "连接控制非数字 → 解析失败，回消息有误"),
    ("TC10", "257;AUTHCODE;cmnet;;;{addr};{port};;30", 2,
     "连接控制超过 u8，防截断成 1 被误判为回默认服务器"),
    ("TC11", "", 2,
     "命令字 2 但无参数（消息体仅 1 字节 0x02）→ 拒绝"),
    ("TC12", "0;AUTHCODE;cmnet", 2,
     "字段数不足 9 → 核心参数缺失，拒绝"),
    ("TC13", "0;AUTHCODE;cmnet;;;{addr};{port};5000;30", 0,
     "UDP 端口填了值，固件解析但不使用，仍应成功"),
    ("TC14", "0;AUTHCODE;cmnet;;;{addr};{port};;30;", 0,
     "多一个尾部分号 = 10 字段，核心参数仍合法；当前实现只校验命令字 1 的字段数，"
     "命令字 2 未校验，故仍成功（协议 8.13.1 第4条严格解释应回 2）"),
]


# ---------------------------------------------------------------- 独立组帧
def bcd_phone(s, n=12):
    s = "".join(c for c in str(s) if c.isdigit()).ljust(n, "0")[:n]
    return bytes(int(s[i:i + 2], 16) for i in range(0, n, 2))


def escape(raw):
    out = bytearray()
    for b in raw:
        if b == FLAG:
            out += bytes([ESC, ESC_FLAG])
        elif b == ESC:
            out += bytes([ESC, ESC_ESC])
        else:
            out.append(b)
    return bytes(out)


def frame(msg_id, phone, seq, body):
    prop = len(body) & 0x3FF
    raw = msg_id.to_bytes(2, "big") + prop.to_bytes(2, "big") \
        + bcd_phone(phone) + seq.to_bytes(2, "big") + body
    cs = 0
    for b in raw:
        cs ^= b
    return bytes([FLAG]) + escape(raw + bytes([cs])) + bytes([FLAG])


def make_hex(param, phone, seq):
    body = bytes([0x02]) + param.encode("ascii")
    return frame(0x8105, phone, seq, body).hex().upper()


# ---------------------------------------------------------------- HTTP
def req(base, path, data=None, timeout=6):
    if data is None:
        r = urllib.request.Request(base + path)
    else:
        r = urllib.request.Request(
            base + path,
            data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status, json.loads(f.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return 0, {"ok": False, "message": str(e)}


def events(base):
    code, obj = req(base, "/api/state")
    return obj.get("events", []) if code == 200 else []


def online(base, phone):
    code, obj = req(base, "/api/state")
    if code != 200:
        return False
    return any(d.get("phone") == phone and d.get("online")
               for d in obj.get("devices", []))


RESULT_TEXT = {"成功/确认": 0, "失败": 1, "消息有误": 2, "不支持": 3}


def wait_ack(base, seq, timeout=10):
    """从运行日志里找设备回的 0x0001，返回 (结果码, 日志原文)。"""
    end = time.time() + timeout
    while time.time() < end:
        for e in events(base):
            msg = e.get("msg", "")
            if "应答 8105" in msg and ("流水号 %d：" % seq) in msg:
                for text, code in RESULT_TEXT.items():
                    if text in msg:
                        return code, msg
                return None, msg
        time.sleep(0.35)
    return None, ""


def wait_online(base, phone, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        if online(base, phone):
            return True
        time.sleep(0.6)
    return False


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", type=int, default=8099)
    ap.add_argument("--phone", default=PHONE)
    ap.add_argument("--addr", default="10.85.20.124", help="下发到设备的临时服务器地址")
    ap.add_argument("--port", type=int, default=7611, help="下发到设备的临时服务器 TCP 端口")
    ap.add_argument("--seq", type=int, default=100, help="起始平台流水号")
    ap.add_argument("--case", default="", help="只跑指定编号，如 TC3")
    ap.add_argument("--list", action="store_true", help="只打印用例与完整帧 hex，不下发")
    args = ap.parse_args()
    base = "http://127.0.0.1:%d" % args.web

    picked = [c for c in CASES if not args.case or c[0].upper() == args.case.upper()]
    if not picked:
        sys.exit("没有匹配的用例编号：%s" % args.case)

    if args.list:
        print("手机号 %s，平台流水号 1，地址 %s:%d\n" %
              (args.phone, args.addr, args.port))
        for no, tpl, want, note in picked:
            param = tpl.format(addr=args.addr, port=args.port)
            body = bytes([0x02]) + param.encode("ascii")
            print("%s  期望 0x0001 结果码 = %d  ·  %s" % (no, want, note))
            print("  参数串：%s" % (param if param else "(空，消息体仅 0x02)"))
            print("  消息体：%d Byte" % len(body))
            print("  完整帧：%s\n" % make_hex(param, args.phone, 1))
        return 0

    code, obj = req(base, "/api/state")
    if code != 200:
        sys.exit("平台没起来：%s → %s" % (base, obj.get("message")))
    if not online(base, args.phone):
        sys.exit("设备 %s 不在线，先把设备接进来再跑" % args.phone)

    print("平台 %s，设备 %s，共 %d 条用例\n" % (base, args.phone, len(picked)))
    rows = []
    seq = args.seq
    for no, tpl, want, note in picked:
        param = tpl.format(addr=args.addr, port=args.port)
        hexs = make_hex(param, args.phone, seq)
        code, res = req(base, "/api/send", {
            "phone": args.phone, "hex": hexs,
            "msg_id": "0x8105", "msg_name": "终端控制"})
        if code != 200 or not res.get("ok"):
            rows.append((no, False, "下发失败 http=%d %s" % (code, res.get("message"))))
            print("  [FAIL] %-5s %s" % (no, rows[-1][2]))
            seq += 1
            continue

        got, log = wait_ack(base, seq)
        ok = (got == want)
        detail = "期望 %d / 实得 %s" % (want, "未收到应答" if got is None else got)
        if log:
            detail += "  |  " + log
        rows.append((no, ok, detail))
        print("  [%s] %-5s %s" % ("PASS" if ok else "FAIL", no, detail))
        seq += 1
        wait_online(base, args.phone)

    bad = [r for r in rows if not r[1]]
    print("\n" + "=" * 68)
    print("共 %d 条，通过 %d，失败 %d" % (len(rows), len(rows) - len(bad), len(bad)))
    print("=" * 68)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
