# -*- coding: utf-8 -*-
"""
TCP Server 测试工具。

默认作为普通 TCP 服务接收并显示数据；切换到 JT/T 808 模式后，会对终端注册
0x0100 下发 0x8100 注册应答，并对终端鉴权 0x0102 下发 0x8001 通用应答。
"""

import queue
import socket
import struct
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk


JT808_NAMES = {
    0x0001: "终端通用应答",
    0x0002: "终端心跳",
    0x0003: "终端注销",
    0x0100: "终端注册",
    0x0102: "终端鉴权",
    0x0200: "位置信息汇报",
    0x8001: "平台通用应答",
    0x8100: "终端注册应答",
}


def bytes_to_hex(data: bytes) -> str:
    return data.hex(" ").upper()


def safe_decode(data: bytes) -> str:
    if not data:
        return ""
    text = data.decode("utf-8", errors="replace")
    return "".join(ch if ch.isprintable() or ch in "\r\n\t" else "." for ch in text)


def xor_checksum(data: bytes) -> int:
    value = 0
    for item in data:
        value ^= item
    return value


def jt808_unescape(data: bytes) -> bytes:
    result = bytearray()
    index = 0
    while index < len(data):
        current = data[index]
        if current == 0x7D and index + 1 < len(data):
            nxt = data[index + 1]
            if nxt == 0x01:
                result.append(0x7D)
                index += 2
                continue
            if nxt == 0x02:
                result.append(0x7E)
                index += 2
                continue
        result.append(current)
        index += 1
    return bytes(result)


def jt808_escape(data: bytes) -> bytes:
    result = bytearray()
    for item in data:
        if item == 0x7E:
            result.extend(b"\x7D\x02")
        elif item == 0x7D:
            result.extend(b"\x7D\x01")
        else:
            result.append(item)
    return bytes(result)


class JT808Packet:
    def __init__(
        self,
        raw_frame: bytes,
        payload: bytes,
        msg_id: int,
        props: int,
        version_flag: bool,
        version: int | None,
        terminal_id: bytes,
        msg_seq: int,
        body: bytes,
        checksum_ok: bool,
    ):
        self.raw_frame = raw_frame
        self.payload = payload
        self.msg_id = msg_id
        self.props = props
        self.version_flag = version_flag
        self.version = version
        self.terminal_id = terminal_id
        self.msg_seq = msg_seq
        self.body = body
        self.checksum_ok = checksum_ok


def parse_jt808_frame(frame: bytes) -> JT808Packet:
    if len(frame) < 2 or frame[0] != 0x7E or frame[-1] != 0x7E:
        raise ValueError("不是标准 7E 开始/结束的 JT/T 808 帧")

    payload = jt808_unescape(frame[1:-1])
    if len(payload) < 13:
        raise ValueError(f"帧长度过短，解转义后仅 {len(payload)} 字节")

    checksum_ok = xor_checksum(payload[:-1]) == payload[-1]
    msg_id, props = struct.unpack(">HH", payload[:4])
    version_flag = bool(props & 0x4000)
    body_len = props & 0x03FF

    if version_flag:
        if len(payload) < 18:
            raise ValueError("2019 版本头长度不足")
        version = payload[4]
        terminal_id = payload[5:15]
        msg_seq = struct.unpack(">H", payload[15:17])[0]
        header_len = 17
    else:
        version = None
        terminal_id = payload[4:10]
        msg_seq = struct.unpack(">H", payload[10:12])[0]
        header_len = 12

    if props & 0x2000:
        header_len += 4

    body_end = header_len + body_len
    if len(payload) < body_end + 1:
        raise ValueError(f"消息体长度不足，声明 {body_len} 字节，实际剩余不足")

    body = payload[header_len:body_end]
    return JT808Packet(
        raw_frame=frame,
        payload=payload,
        msg_id=msg_id,
        props=props,
        version_flag=version_flag,
        version=version,
        terminal_id=terminal_id,
        msg_seq=msg_seq,
        body=body,
        checksum_ok=checksum_ok,
    )


def build_jt808_frame(
    msg_id: int,
    terminal_id: bytes,
    msg_seq: int,
    body: bytes,
    version_flag: bool = False,
    version: int | None = None,
) -> bytes:
    props = len(body) & 0x03FF
    if version_flag:
        props |= 0x4000
        if len(terminal_id) != 10:
            terminal_id = terminal_id.rjust(10, b"\x00")[-10:]
        header = struct.pack(">HHB", msg_id, props, version if version is not None else 1)
        header += terminal_id
        header += struct.pack(">H", msg_seq & 0xFFFF)
    else:
        if len(terminal_id) != 6:
            terminal_id = terminal_id.rjust(6, b"\x00")[-6:]
        header = struct.pack(">HH", msg_id, props)
        header += terminal_id
        header += struct.pack(">H", msg_seq & 0xFFFF)

    payload = header + body
    checksum = xor_checksum(payload)
    return b"\x7E" + jt808_escape(payload + bytes([checksum])) + b"\x7E"


def build_register_response(packet: JT808Packet, platform_seq: int, auth_code: str) -> bytes:
    auth_bytes = auth_code.encode("ascii", errors="ignore") or b"123456"
    body = struct.pack(">HB", packet.msg_seq, 0x00) + auth_bytes
    return build_jt808_frame(
        0x8100,
        packet.terminal_id,
        platform_seq,
        body,
        packet.version_flag,
        packet.version,
    )


def build_general_response(packet: JT808Packet, platform_seq: int, result: int = 0x00) -> bytes:
    body = struct.pack(">HHB", packet.msg_seq, packet.msg_id, result)
    return build_jt808_frame(
        0x8001,
        packet.terminal_id,
        platform_seq,
        body,
        packet.version_flag,
        packet.version,
    )


class TcpServerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TCP Server 测试工具 - 普通TCP / JT808鉴权")
        self.root.geometry("980x680")
        self.root.minsize(820, 540)

        self.server_socket: socket.socket | None = None
        self.running = False
        self.clients: dict[str, socket.socket] = {}
        self.clients_lock = threading.Lock()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.platform_seq = 1

        self.host_var = tk.StringVar(value="0.0.0.0")
        self.port_var = tk.StringVar(value="9000")
        self.mode_var = tk.StringVar(value="普通TCP")
        self.auth_code_var = tk.StringVar(value="123456")
        self.status_var = tk.StringVar(value="未启动")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.drain_log_queue)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        config = ttk.LabelFrame(main, text="服务器配置", padding=10)
        config.grid(row=0, column=0, sticky="ew")
        for col in (1, 3, 5):
            config.columnconfigure(col, weight=1)

        ttk.Label(config, text="服务器地址").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(config, textvariable=self.host_var, width=18).grid(row=0, column=1, sticky="ew", padx=(0, 12))

        ttk.Label(config, text="端口").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(config, textvariable=self.port_var, width=10).grid(row=0, column=3, sticky="ew", padx=(0, 12))

        ttk.Label(config, text="模式").grid(row=0, column=4, sticky="w", padx=(0, 6))
        mode_box = ttk.Combobox(
            config,
            textvariable=self.mode_var,
            values=("普通TCP", "JT/T 808鉴权"),
            state="readonly",
            width=16,
        )
        mode_box.grid(row=0, column=5, sticky="ew", padx=(0, 12))
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self.update_mode_state())

        self.start_button = ttk.Button(config, text="启动服务", command=self.start_server)
        self.start_button.grid(row=0, column=6, padx=(0, 8))
        self.stop_button = ttk.Button(config, text="停止服务", command=self.stop_server, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=7)

        ttk.Label(config, text="808鉴权码").grid(row=1, column=0, sticky="w", pady=(10, 0), padx=(0, 6))
        self.auth_entry = ttk.Entry(config, textvariable=self.auth_code_var, width=18)
        self.auth_entry.grid(row=1, column=1, sticky="ew", pady=(10, 0), padx=(0, 12))
        ttk.Label(config, textvariable=self.status_var).grid(row=1, column=2, columnspan=6, sticky="w", pady=(10, 0))

        action = ttk.Frame(main)
        action.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        ttk.Button(action, text="清空接收内容", command=self.clear_log).pack(side=tk.LEFT)

        self.log_text = scrolledtext.ScrolledText(main, wrap=tk.WORD, height=24)
        self.log_text.grid(row=2, column=0, sticky="nsew")
        self.log_text.configure(state=tk.DISABLED, font=("Consolas", 10))

        self.update_mode_state()

    def update_mode_state(self):
        if self.mode_var.get() == "JT/T 808鉴权":
            self.auth_entry.configure(state=tk.NORMAL)
        else:
            self.auth_entry.configure(state=tk.DISABLED)

    def start_server(self):
        if self.running:
            return

        host = self.host_var.get().strip() or "0.0.0.0"
        try:
            port = int(self.port_var.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning("端口错误", "端口必须是 1-65535 的整数。")
            return

        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(20)
            server.settimeout(1.0)
        except OSError as exc:
            messagebox.showerror("启动失败", f"无法监听 {host}:{port}\n{exc}")
            return

        self.server_socket = server
        self.running = True
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.status_var.set(f"运行中：{host}:{port} / {self.mode_var.get()}")
        self.log(f"服务已启动：{host}:{port}，模式：{self.mode_var.get()}")
        threading.Thread(target=self.accept_loop, daemon=True).start()

    def stop_server(self):
        if not self.running and self.server_socket is None:
            return

        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None

        with self.clients_lock:
            clients = list(self.clients.items())
            self.clients.clear()

        for _client_id, client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass

        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("已停止")
        self.log("服务已停止")

    def accept_loop(self):
        while self.running and self.server_socket:
            try:
                client, address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_id = f"{address[0]}:{address[1]}"
            client.settimeout(1.0)
            with self.clients_lock:
                self.clients[client_id] = client
            self.log(f"客户端已连接：{client_id}")
            threading.Thread(target=self.client_loop, args=(client_id, client), daemon=True).start()

    def client_loop(self, client_id: str, client: socket.socket):
        jt808_buffer = bytearray()
        try:
            while self.running:
                try:
                    data = client.recv(4096)
                except socket.timeout:
                    continue
                except OSError as exc:
                    self.log(f"客户端接收异常：{client_id}，{exc}")
                    break

                if not data:
                    break

                if self.mode_var.get() == "JT/T 808鉴权":
                    self.handle_jt808_data(client_id, client, data, jt808_buffer)
                else:
                    self.log_normal_data(client_id, data)
        finally:
            with self.clients_lock:
                self.clients.pop(client_id, None)
            try:
                client.close()
            except OSError:
                pass
            self.log(f"客户端已断开：{client_id}")

    def log_normal_data(self, client_id: str, data: bytes):
        self.log(f"[{client_id}] RX {len(data)} bytes")
        self.log(f"HEX: {bytes_to_hex(data)}")
        text = safe_decode(data)
        if text:
            self.log(f"TEXT: {text}")

    def handle_jt808_data(self, client_id: str, client: socket.socket, data: bytes, buffer: bytearray):
        self.log(f"[{client_id}] RX原始 {len(data)} bytes: {bytes_to_hex(data)}")
        buffer.extend(data)

        while True:
            try:
                start = buffer.index(0x7E)
            except ValueError:
                if len(buffer) > 4096:
                    buffer.clear()
                return

            if start > 0:
                del buffer[:start]

            try:
                end = buffer.index(0x7E, 1)
            except ValueError:
                return

            frame = bytes(buffer[: end + 1])
            del buffer[: end + 1]
            self.process_jt808_frame(client_id, client, frame)

    def process_jt808_frame(self, client_id: str, client: socket.socket, frame: bytes):
        try:
            packet = parse_jt808_frame(frame)
        except ValueError as exc:
            self.log(f"[{client_id}] 808解析失败：{exc}")
            self.log(f"FRAME: {bytes_to_hex(frame)}")
            return

        name = JT808_NAMES.get(packet.msg_id, "未知消息")
        version_text = "2019" if packet.version_flag else "2013"
        checksum_text = "OK" if packet.checksum_ok else "FAIL"
        terminal_text = packet.terminal_id.hex().upper()

        self.log(
            f"[{client_id}] 808消息：0x{packet.msg_id:04X} {name}，"
            f"流水号={packet.msg_seq}，终端={terminal_text}，版本={version_text}，校验={checksum_text}"
        )
        if packet.body:
            self.log(f"BODY: {bytes_to_hex(packet.body)}")
            body_text = safe_decode(packet.body)
            if body_text:
                self.log(f"BODY_TEXT: {body_text}")

        if not packet.checksum_ok:
            self.log("校验失败，已记录但不自动应答。")
            return

        response = None
        response_name = ""
        if packet.msg_id == 0x0100:
            response = build_register_response(packet, self.next_platform_seq(), self.auth_code_var.get().strip())
            response_name = "0x8100 终端注册应答"
        elif packet.msg_id in (0x0102, 0x0002):
            response = build_general_response(packet, self.next_platform_seq(), 0x00)
            response_name = "0x8001 平台通用应答"

        if response:
            try:
                client.sendall(response)
                self.log(f"[{client_id}] TX {response_name}: {bytes_to_hex(response)}")
            except OSError as exc:
                self.log(f"[{client_id}] 应答发送失败：{exc}")

    def next_platform_seq(self) -> int:
        value = self.platform_seq
        self.platform_seq = (self.platform_seq + 1) & 0xFFFF
        if self.platform_seq == 0:
            self.platform_seq = 1
        return value

    def clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def log(self, text: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {text}\n")

    def drain_log_queue(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                self.log_text.configure(state=tk.NORMAL)
                self.log_text.insert(tk.END, item)
                self.log_text.see(tk.END)
                self.log_text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self.drain_log_queue)

    def on_close(self):
        self.stop_server()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = TcpServerApp(root)
    root.mainloop()
