"""Native service manager; the editor and its database stay unchanged."""
import argparse
import ctypes
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from limits import MAX_MESSAGE


FROZEN = bool(getattr(sys, "frozen", False))
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON = BUNDLE / "static/XMind_web.ico"
TITLE = "GNN · 服务管理"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def port_number(value):
    try:
        port = int(value)
    except (ValueError, TypeError):
        raise ValueError("端口需要是 1–65535 之间的整数。") from None
    if not 1 <= port <= 65535:
        raise ValueError("端口需要是 1–65535 之间的整数。")
    return port


def python_command(root=BASE):
    if FROZEN:
        return str(root / "server" / "GNN-Server.exe")
    return str(root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


def storage_at(port):
    # Ignore machine proxy settings for the loopback health check.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/storage", timeout=0.8) as response:
            return json.loads(response.read(8192))
    except (OSError, ValueError, urllib.error.URLError):
        return None


def same_workspace(storage, root=BASE):
    if not isinstance(storage, dict) or not isinstance(storage.get("database"), str):
        return False
    expected = Path(os.environ.get("MINDCOLLAB_DB", root / "data/mindcollab.sqlite3"))
    return os.path.normcase(os.path.abspath(storage["database"])) == os.path.normcase(str(expected.resolve()))


def port_available(port, lan=False):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("0.0.0.0" if lan else "127.0.0.1", port))
        return True
    except OSError:
        return False


def server_command(port, lan, root=BASE):
    if FROZEN:
        return [python_command(root), "--serve", "--port", str(port)] + (["--lan"] if lan else [])
    return [python_command(root), "-u", str(root / "launcher.py"), "--serve", "--port", str(port),
            *(["--lan"] if lan else [])]


def lan_addresses(port):
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                            if not item[4][0].startswith(("127.", "169.254."))})
    except OSError:
        addresses = []
    return [f"http://{address}:{port}" for address in addresses]


def serve(port, lan):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(
        "app:app", host="0.0.0.0" if lan else "127.0.0.1", port=port,
        workers=1, ws_max_size=MAX_MESSAGE, timeout_graceful_shutdown=5, log_config=None,
    ))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    def control():
        # EOF also shuts down the child if the manager crashes or is terminated.
        for line in sys.stdin:
            if line.strip() == "stop":
                break
        server.should_exit = True

    threading.Thread(target=control, daemon=True).start()
    server.run()
    if not server.started:
        raise SystemExit(1)


class Cancelled(Exception):
    pass


class Service:
    """All child I/O and setup run off the Tk event loop."""

    def __init__(self, events, root=BASE):
        self.events, self.root = events, root
        self.process = None
        self.worker = None
        self.shutdown_worker = None
        self.cancel = threading.Event()
        self.stage = "idle"
        self.lock = threading.Lock()

    def emit(self, kind, value):
        self.events.put((kind, value))

    def start(self, port, lan):
        port = port_number(port)
        with self.lock:
            if (self.worker and self.worker.is_alive()) or (self.process and self.process.poll() is None):
                return False
            self.cancel.clear()
            self.worker = threading.Thread(target=self._run, args=(port, lan), daemon=True)
            self.worker.start()
        return True

    def _spawn(self, command, stage):
        if self.cancel.is_set():
            raise Cancelled()
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        if FROZEN:
            environment.setdefault("MINDCOLLAB_DB", str((self.root / "data" / "mindcollab.sqlite3").resolve()))
        with self.lock:
            if self.cancel.is_set():
                raise Cancelled()
            process = subprocess.Popen(
                command, cwd=self.root, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
            )
            self.process, self.stage = process, stage

        def read_logs():
            try:
                for line in process.stdout:
                    self.emit("log", line.rstrip())
            except (OSError, ValueError):
                pass
            finally:
                process.stdout.close()

        threading.Thread(target=read_logs, daemon=True).start()
        return process

    def _step(self, command, label):
        self.emit("state", ("starting", label))
        self.emit("log", label)
        process = self._spawn(command, "setup")
        code = process.wait()
        if process.stdin:
            process.stdin.close()
        if self.cancel.is_set():
            raise Cancelled()
        if code:
            raise RuntimeError(f"{label}失败（退出码 {code}），请查看日志。")

    def _prepare(self):
        if FROZEN:
            if not Path(python_command(self.root)).is_file():
                raise RuntimeError("便携版服务组件缺失，请重新解压完整的 GNN 便携版文件夹。")
            return
        python = python_command(self.root)
        if not Path(python).is_file():
            bootstrap = Path(sys.executable)
            if bootstrap.name.lower() == "pythonw.exe":
                bootstrap = bootstrap.with_name("python.exe")
            self._step([str(bootstrap), "-m", "venv", str(self.root / ".venv")], "创建 Python 环境")
        check = subprocess.run(
            [python, "-c", "import fastapi, uvicorn, python_multipart, ijson"],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW, timeout=20,
        )
        if check.returncode:
            self._step([python, "-m", "pip", "install", "-r", "requirements.txt",
                        "--disable-pip-version-check", "--no-input"], "安装服务依赖（首次运行需要联网）")
        if not (self.root / "static/app.js").is_file():
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if not npm:
                raise RuntimeError("缺少前端文件，请安装 Node.js 18+ 后重试。")
            command = [npm]
            if os.name == "nt":
                command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", npm]
            self._step([*command, "ci"], "安装前端依赖")
            self._step([*command, "run", "build"], "构建前端")

    def _run(self, port, lan):
        final_state = None
        try:
            self.emit("state", ("starting", "检查运行环境…"))
            if not port_available(port, lan):
                if same_workspace(storage_at(port), self.root):
                    final_state = ("external", "服务已运行（外部启动），请点击“接管旧服务”管理启停")
                    return
                raise RuntimeError(f"端口 {port} 已被其他程序占用，请更换端口。")
            self._prepare()
            self.emit("state", ("starting", "正在启动服务…"))
            process = self._spawn(server_command(port, lan, self.root), "server")
            ready, deadline = False, time.monotonic() + 30
            while process.poll() is None:
                if self.cancel.is_set():
                    time.sleep(0.1)
                    continue
                if not ready and same_workspace(storage_at(port), self.root):
                    ready = True
                    self.emit("state", ("running", f"服务运行中 · PID {process.pid}"))
                    if lan:
                        self.emit("network", lan_addresses(port))
                    self.emit("ready", None)
                if not ready and time.monotonic() > deadline:
                    raise RuntimeError("服务启动超时，请查看日志，或检查防火墙及端口。")
                time.sleep(0.35)
            if self.cancel.is_set():
                final_state = ("idle", "服务已停止，已保存的导图仍保留")
            else:
                raise RuntimeError(f"服务意外退出（退出码 {process.returncode}），请查看日志。")
        except Cancelled:
            final_state = ("idle", "已取消启动")
        except Exception as error:
            self.emit("log", str(error))
            final_state = ("error", str(error))
        finally:
            with self.lock:
                process = self.process
            if process and process.poll() is None:
                self.stop()
                # Keep ownership and monitoring after a failed stop; the GUI can retry.
                while process.poll() is None:
                    time.sleep(0.1)
            with self.lock:
                shutdown_worker = self.shutdown_worker
            if shutdown_worker:
                shutdown_worker.join()
            if process and process.stdin and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError as error:
                    self.emit("log", f"关闭控制管道失败：{error}")
            with self.lock:
                self.process, self.stage = None, "idle"
            if final_state:
                self.emit("state", final_state)
            self.emit("finished", None)

    @staticmethod
    def _kill_owned(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            result = subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    creationflags=NO_WINDOW, timeout=10)
            if result.returncode and process.poll() is None:
                raise RuntimeError(f"结束子进程失败（退出码 {result.returncode}，PID {process.pid}）")
        else:
            process.kill()

    def stop(self):
        def shutdown():
            failure = None
            try:
                if not process or process.poll() is not None:
                    return
                if stage == "server":
                    try:
                        process.stdin.write("stop\n")
                        process.stdin.flush()
                        process.wait(timeout=9)
                        return
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        pass
                self._kill_owned(process)
                process.wait(timeout=10)
            except Exception as error:
                if process.poll() is None:
                    failure = str(error)
            finally:
                with self.lock:
                    if failure:
                        self.emit("log", f"停止 PID {process.pid} 失败：{failure}")
                        self.emit("state", ("stop_failed", f"进程 {process.pid} 尚未退出，仍由本窗口管理；请点击“重试停止”"))
                    self.shutdown_worker = None

        with self.lock:
            if self.shutdown_worker and self.shutdown_worker.is_alive():
                return False
            process, stage = self.process, self.stage
            if not ((process and process.poll() is None) or (self.worker and self.worker.is_alive())):
                return False
            self.cancel.set()
            self.emit("state", ("stopping", "正在停止，请稍候…"))
            self.shutdown_worker = threading.Thread(target=shutdown, daemon=True)
            self.shutdown_worker.start()
        return True


def external_listener(port, root=BASE):
    """Never infer ownership from a port number or process name alone."""
    if os.name != "nt" or not same_workspace(storage_at(port), root):
        raise RuntimeError("无法确认此服务属于当前工作空间；不会停止该进程。")
    script = (
        f"$ids = @(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction Stop | "
        "Select-Object -ExpandProperty OwningProcess -Unique); "
        "if ($ids.Count -ne 1) { throw 'Ambiguous listener' }; "
        "$p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $ids[0]); "
        "@{pid=$p.ProcessId; command=$p.CommandLine; "
        "created=$p.CreationDate.ToFileTimeUtc().ToString()} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, encoding="utf-8", creationflags=NO_WINDOW, timeout=15)
    if result.returncode:
        raise RuntimeError("无法核实已有服务的进程信息；请先从原启动入口关闭服务。")
    info = json.loads(result.stdout)
    command = info.get("command") or ""
    if not re.search(r"(?:^|\s)-m\s+uvicorn\s+app:app(?:\s|$)", command) or not re.search(
            rf"(?:^|\s)--port\s+{port}(?:\s|$)", command):
        raise RuntimeError("已有服务不是旧版启动脚本启动的进程；为安全起见不自动接管。")
    return info


def stop_external(port, root=BASE):
    info = external_listener(port, root)
    # Compare creation time again to guard against PID reuse before Stop-Process.
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(info['pid'])}'; "
        f"if ($null -eq $p -or $p.CreationDate.ToFileTimeUtc().ToString() -ne '{int(info['created'])}') "
        "{ throw 'Process identity changed' }; "
        "Stop-Process -Id $p.ProcessId -ErrorAction Stop"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, creationflags=NO_WINDOW, timeout=15)
    if result.returncode:
        raise RuntimeError("无法停止旧服务，请从原启动入口关闭，再点击启动。")
    deadline = time.monotonic() + 8
    while not port_available(port) and time.monotonic() < deadline:
        time.sleep(0.2)
    if not port_available(port):
        raise RuntimeError("端口仍未释放，请稍候再启动。")


class Manager:
    def __init__(self, window, port, lan):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText

        self.tk, self.ttk, self.window = tk, ttk, window
        self.events = queue.Queue()
        self.service = Service(self.events)
        self.state, self.closing, self.busy = "idle", False, False
        self.external_port = None
        self.probe_pending = False
        self.next_probe = 0
        self.port = tk.StringVar(value=str(port))
        self.lan = tk.BooleanVar(value=lan)
        self.auto_open = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="尚未启动")
        self.address = tk.StringVar(value=f"http://127.0.0.1:{port}")
        self.access = tk.StringVar(value="仅本机访问")
        self.storage = BASE / "data"
        self.storage.mkdir(exist_ok=True)
        self.logger = logging.getLogger("mindcollab.launcher")
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(self.storage / "launcher.log", maxBytes=1024 * 1024,
                                      backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)
        self.log_handler = handler

        window.title(TITLE)
        window.geometry("860x660")
        window.minsize(730, 560)
        window.configure(background="#F3F5F7")
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.report_callback_exception = self.callback_error
        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure("TFrame", background="#F3F5F7")
        style.configure("TLabel", background="#F3F5F7", foreground="#252A32", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Muted.TLabel", foreground="#606975", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(14, 8))
        style.configure("Accent.TButton", background="#247553", foreground="white", borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#1B6043"), ("disabled", "#D7E0DA")],
                  foreground=[("disabled", "#737C76")])
        style.configure("Toggle.TButton", background="#F3F5F7", foreground="#252A32",
                        font=("Microsoft YaHei UI", 10), padding=(4, 4), borderwidth=0)
        style.map("Toggle.TButton", background=[("active", "#E8ECEA"), ("disabled", "#F3F5F7")],
                  foreground=[("disabled", "#9AA2AA")])
        style.configure("TEntry", padding=6, font=("Microsoft YaHei UI", 10))
        outer = ttk.Frame(window, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="GNN", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="本地协作思维导图 · 服务控制台", style="Muted.TLabel").pack(anchor="w", pady=(2, 18))
        status_row = ttk.Frame(outer)
        status_row.pack(fill="x")
        self.dot = ttk.Label(status_row, text="●", foreground="#939DA7", font=("Segoe UI", 16))
        self.dot.pack(side="left", padx=(0, 8))
        ttk.Label(status_row, textvariable=self.status, wraplength=620).pack(side="left")
        settings = ttk.Frame(outer)
        settings.pack(fill="x", pady=(15, 6))
        ttk.Label(settings, text="服务端口").pack(side="left")
        self.port_input = ttk.Entry(settings, textvariable=self.port, width=8)
        self.port_input.pack(side="left", padx=(10, 20))
        self.lan_input = ttk.Button(settings, text="", style="Toggle.TButton", command=self.toggle_lan)
        self.lan_input.pack(side="left")
        self.auto_open_input = ttk.Button(settings, text="", style="Toggle.TButton", command=self.toggle_auto_open)
        self.auto_open_input.pack(side="right")
        self.lan.trace_add("write", lambda *_: self.refresh_toggle_labels())
        self.auto_open.trace_add("write", lambda *_: self.refresh_toggle_labels())
        self.refresh_toggle_labels()
        self.port.trace_add("write", lambda *_: self.update_address())
        link = ttk.Entry(outer, textvariable=self.address, state="readonly")
        link.pack(fill="x", pady=(5, 4))
        ttk.Label(outer, textvariable=self.access, style="Muted.TLabel", wraplength=680).pack(anchor="w")
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(18, 16))
        self.start_button = ttk.Button(buttons, text="启动服务", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="停止服务", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=10)
        self.browser_button = ttk.Button(buttons, text="打开导图", command=self.open_browser, state="disabled")
        self.browser_button.pack(side="left")
        self.adopt_button = ttk.Button(buttons, text="接管旧服务", command=self.adopt, state="disabled")
        self.adopt_button.pack(side="right")
        log_heading = ttk.Frame(outer)
        log_heading.pack(fill="x", pady=(0, 5))
        ttk.Label(log_heading, text="运行日志").pack(side="left")
        ttk.Button(log_heading, text="打开日志", command=lambda: os.startfile(self.storage / "launcher.log")).pack(side="right")
        self.logs = ScrolledText(outer, height=10, wrap="word", state="disabled", relief="flat",
                                 background="#FFFFFF", foreground="#38414B", font=("Consolas", 10),
                                 padx=12, pady=10, highlightthickness=1, highlightbackground="#DCE1E5")
        self.logs.pack(fill="both", expand=True)
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, text="自动保存：data\\mindcollab.sqlite3\n停止服务不会删除导图，也不会覆盖原 XMind 文件。",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="打开数据目录", command=lambda: os.startfile(self.storage)).pack(side="right")
        self.append_log(f"工作目录：{BASE}")
        self.append_log("点击启动后在后台运行，无需保留命令行窗口。")
        self.update_address()
        self.timer = self.window.after(100, self.poll)
        self.check_existing()

    def refresh_toggle_labels(self):
        """Render unambiguous on/off indicators independent of the Windows theme."""
        if hasattr(self, "lan_input"):
            self.lan_input.configure(text=f"{'●' if self.lan.get() else '○'} 允许局域网访问")
        if hasattr(self, "auto_open_input"):
            self.auto_open_input.configure(text=f"{'●' if self.auto_open.get() else '○'} 启动后打开浏览器")

    def toggle_lan(self):
        self.lan.set(not self.lan.get())
        self.update_address()

    def toggle_auto_open(self):
        self.auto_open.set(not self.auto_open.get())

    def append_log(self, text):
        self.logger.info(text)
        self.logs.configure(state="normal")
        self.logs.insert("end", time.strftime("%H:%M:%S  ") + text + "\n")
        if int(self.logs.index("end-1c").split(".")[0]) > 1200:
            self.logs.delete("1.0", "201.0")
        self.logs.see("end")
        self.logs.configure(state="disabled")

    def callback_error(self, error_type, error, trace):
        import traceback
        from tkinter import messagebox
        self.append_log("".join(traceback.format_exception(error_type, error, trace)))
        messagebox.showerror("操作失败", str(error) + "\n详细信息已写入运行日志。", parent=self.window)

    def update_address(self):
        port = self.selected_port()
        self.address.set(f"http://127.0.0.1:{port if port is not None else self.port.get()}")
        if self.state in {"external", "conflict"} and self.external_port != port:
            self.set_state("idle", "设置已更改，点击启动检查所选端口")
        if self.lan.get():
            self.access.set("局域网模式：无账号验证，仅用于可信网络；不要映射到公网。")
        else:
            self.access.set("仅本机访问")

    def selected_port(self):
        try:
            return port_number(self.port.get())
        except ValueError:
            return None

    def check_existing(self):
        # Capture Tk values only on the UI thread.
        if self.probe_pending or self.busy or self.closing:
            return
        try:
            port = port_number(self.port.get())
        except ValueError:
            return
        lan = self.lan.get()
        self.probe_pending = True
        self.next_probe = time.monotonic() + 3
        if self.state == "idle":
            self.set_state("checking", "正在检测已有服务…")
        def run():
            try:
                if same_workspace(storage_at(port)):
                    result = "external"
                elif port_available(port, lan):
                    result = "idle"
                else:
                    result = "conflict"
                self.events.put(("probe_result", (port, lan, result)))
            except Exception as error:
                self.events.put(("probe_result", (port, lan, "error")))
                self.events.put(("log", f"检测已有服务失败：{error}"))
        threading.Thread(target=run, daemon=True).start()

    def set_state(self, kind, label):
        self.state = kind
        self.status.set(label)
        if kind in {"external", "conflict"}:
            self.external_port = self.selected_port()
        active = kind in {"checking", "starting", "running", "stopping", "stop_failed"}
        self.dot.configure(foreground={"running": "#247553", "external": "#B3781C", "error": "#B73535",
                                       "stop_failed": "#B73535"}.get(kind, "#939DA7"))
        self.port_input.configure(state="disabled" if active else "normal")
        self.lan_input.configure(state="disabled" if active else "normal")
        can_start = kind in {"idle", "error"} and not self.busy and not self.closing
        self.start_button.configure(state="normal" if can_start else "disabled")
        self.stop_button.configure(text="重试停止" if kind == "stop_failed" else "停止服务",
                                   state="normal" if kind in {"starting", "running", "stop_failed"} else "disabled")
        self.browser_button.configure(state="normal" if kind in {"running", "external"} else "disabled")
        self.adopt_button.configure(state="normal" if kind == "external" and not self.busy and os.name == "nt" else "disabled")

    def start(self):
        from tkinter import messagebox
        if self.busy or self.closing or self.state not in {"idle", "error"}:
            return
        try:
            port = port_number(self.port.get())
        except ValueError as error:
            messagebox.showerror("端口无效", str(error), parent=self.window)
            return
        lan = self.lan.get()
        if lan and not messagebox.askokcancel(
                "局域网访问", "局域网用户可以访问并修改全部导图，当前没有登录验证。\n只在可信网络使用，确认开启？", parent=self.window):
            return
        if (self.busy or self.closing or self.state not in {"idle", "error"}
                or port != self.selected_port() or lan != self.lan.get()):
            return
        self.busy = True
        self.set_state("starting", "正在启动…")
        if not self.service.start(port, lan):
            self.busy = False
            self.set_state("error", "上一次任务正在收尾，请稍候再试")

    def stop(self):
        from tkinter import messagebox
        if not self.busy or self.closing or self.state not in {"starting", "running", "stop_failed"}:
            return
        if self.state == "running" and not messagebox.askokcancel(
                "停止服务", "停止后其他协作者也会断开连接，已保存的导图不会删除。\n确定停止？", parent=self.window):
            return
        if not self.busy or self.closing or self.state not in {"starting", "running", "stop_failed"}:
            return
        self.set_state("stopping", "正在停止，请稍候…")
        self.service.stop()

    def adopt(self):
        from tkinter import messagebox
        if self.busy or self.closing or self.state != "external":
            return
        try:
            port = port_number(self.port.get())
        except ValueError as error:
            messagebox.showerror("端口无效", str(error), parent=self.window)
            return
        lan = self.lan.get()
        if not messagebox.askokcancel(
                "接管旧版服务", "将结束旧命令行启动的服务，再由本窗口重新启动。\n协作者会短暂断线，已保存的导图保留。\n\n旧服务不支持平滑停止；仅在确认无需继续当前连接时接管。\n确定继续？", parent=self.window):
            return
        if (self.busy or self.closing or self.state != "external"
                or port != self.selected_port() or lan != self.lan.get()):
            return
        self.busy = True
        self.set_state("starting", "核实并停止旧服务…")
        self.stop_button.configure(state="disabled")
        def takeover():
            try:
                stop_external(port)
                self.events.put(("adopted", (port, lan)))
            except Exception as error:
                self.events.put(("log", str(error)))
                self.events.put(("state", ("error", str(error))))
                self.events.put(("finished", None))
        threading.Thread(target=takeover, daemon=True).start()

    def open_browser(self):
        try:
            webbrowser.open(f"http://127.0.0.1:{port_number(self.port.get())}")
        except ValueError:
            pass

    def poll(self):
        for _ in range(150):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append_log(value)
            elif kind == "state":
                if value[0] == "stop_failed":
                    self.closing = False
                changed = self.state != value[0] or self.status.get() != value[1]
                self.set_state(*value)
                if changed:
                    self.append_log(value[1])
            elif kind == "ready" and self.auto_open.get():
                self.open_browser()
            elif kind == "network" and value:
                links = "  ".join(value)
                self.access.set("局域网访问：" + links + "（仅限可信网络）")
                self.append_log("局域网访问地址：" + links)
            elif kind == "adopted":
                if self.closing:
                    self.destroy()
                    return
                if not self.service.start(*value):
                    self.events.put(("state", ("error", "旧服务已停止，但管理任务尚未结束，请稍候再试")))
                    self.events.put(("finished", None))
            elif kind == "probe_result":
                self.probe_pending = False
                port, lan, result = value
                if self.busy or self.closing or port != self.selected_port() or lan != self.lan.get():
                    if self.state == "checking" and not self.busy:
                        self.set_state("idle", "设置已更改，点击启动检查所选端口")
                    continue
                labels = {
                    "external": "服务已运行（外部启动），请点击“接管旧服务”管理启停",
                    "idle": "服务未运行，可点击“启动服务”",
                    "conflict": f"端口 {port} 被其他程序占用，请更换端口或等待释放",
                    "error": "服务状态检测失败，请查看日志后重试",
                }
                changed = self.state != result
                self.set_state(result, labels[result])
                if changed and result != "idle":
                    self.append_log(labels[result])
            elif kind == "finished":
                self.busy = False
                self.set_state(self.state, self.status.get())
                if self.closing:
                    self.destroy()
                    return
        if self.state in {"external", "conflict"} and time.monotonic() >= self.next_probe:
            self.check_existing()
        self.timer = self.window.after(100, self.poll)

    def destroy(self):
        if self.timer:
            self.window.after_cancel(self.timer)
            self.timer = None
        self.log_handler.close()
        self.logger.removeHandler(self.log_handler)
        self.window.destroy()

    def close(self):
        from tkinter import messagebox
        if self.busy:
            if self.closing:
                return
            if not messagebox.askokcancel("退出服务管理", "退出将停止本窗口启动的服务或安装任务。\n已保存的导图保留，协作者会断开连接。\n确定退出？", parent=self.window):
                return
            if self.closing:
                return
            if not self.busy:
                self.destroy()
                return
            self.closing = True
            self.set_state("stopping", "正在停止，请稍候…")
            self.service.stop()
        else:
            self.destroy()


def acquire_instance(root=BASE):
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    key = hashlib.sha256(str(root.resolve()).lower().encode()).hexdigest()[:20]
    handle = kernel.CreateMutexW(None, False, "Local\\MindCollabLauncher_" + key)
    if not handle:
        raise OSError(ctypes.get_last_error(), "Cannot create launcher mutex")
    if ctypes.get_last_error() == 183:
        user = ctypes.WinDLL("user32")
        user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user.FindWindowW.restype = ctypes.c_void_p
        user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        window = user.FindWindowW(None, TITLE)
        if window:
            user.ShowWindow(window, 9)
            user.SetForegroundWindow(window)
        else:
            user.MessageBoxW(None, "服务管理窗口已经打开，请查看任务栏。", TITLE, 0)
        raise SystemExit(0)
    return handle


def main():
    parser = argparse.ArgumentParser(description="GNN service manager")
    parser.add_argument("--port", type=port_number, default=8765)
    parser.add_argument("--lan", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        serve(args.port, args.lan)
        return
    os.chdir(BASE)
    if os.name == "nt":
        ctypes.WinDLL("user32").SetProcessDPIAware()
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GNN.CollaborativeMindMap")
    handle = acquire_instance()
    import tkinter as tk
    window = tk.Tk()
    if ICON.is_file():
        window.iconbitmap(default=str(ICON))
    Manager(window, args.port, args.lan)
    try:
        window.mainloop()
    finally:
        if handle:
            kernel = ctypes.WinDLL("kernel32")
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(handle)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        details = traceback.format_exc()
        try:
            (BASE / "data").mkdir(exist_ok=True)
            (BASE / "data/launcher-error.log").write_text(details, encoding="utf-8")
        except OSError:
            pass
        if os.name == "nt" and "--serve" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, "启动失败，详细信息：\n" + details[-1800:], TITLE, 0x10)
        else:
            sys.stderr.write(details)
        raise SystemExit(1)
