# -*- coding: utf-8 -*-
"""
JT808 离线报文工具 —— 桌面版外壳（单文件 exe 入口）

做三件事：
  1. 在本机 127.0.0.1 起一个极简 HTTP 服务，把内置的 index.html 交给窗口；
  2. 页面里的 POST 走同源 /__proxy，由本进程转发到真实平台
     —— 浏览器同源策略 / OPTIONS 预检 / CORS 头这一整套问题从根上不存在；
  3. 用系统 Edge/Chrome 的 --app 模式拉起无地址栏、无标签页的独立窗口，
     对使用者就是一个双击即开的桌面程序。

只依赖 Python 标准库，不用装任何第三方包。

命令行（一般用不到，调试用）：
    jt808_desktop.exe --no-window --port 18100     # 只起服务不开窗
    jt808_desktop.exe --platform http://1.2.3.4:1813
"""
import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

APP_ID = "jt808-offline-tool"
APP_TITLE = "JT808 离线报文工具"
APP_VERSION = "1.2"

# 设备平台默认地址；被 exe 同目录 config.json 或命令行 --platform 覆盖
DEFAULT_PLATFORM = "http://10.85.40.3:1813"
PREFERRED_PORT = 18099

# 端口被占时的顺延区间。页面 index.html 里的 SHELL_PORTS 必须与此保持一致，
# 否则网页版探不到本机服务、不会自动跳转。
SHELL_PORTS = list(range(PREFERRED_PORT, PREFERRED_PORT + 7))

# 关掉窗口后多久退进程（页面每 3s 心跳一次）
IDLE_EXIT_SEC = 600  # 兜底模式下收不到页面心跳多久后自动退出。
# 生命周期主判据是"窗口进程是否还在"（见 watchdog），最小化、系统休眠都不会退出；
# 心跳只在拿不到窗口进程时兜底（用默认浏览器打开、窗口被已有浏览器进程接管）。
# 兜底模式下系统休眠期间的时间不计入空闲（watchdog 检测时钟跳变后重新计时）。

_state = {"seen": False, "last": time.time()}
_log_path = os.path.join(tempfile.gettempdir(), "jt808_desktop.log")

# 转发是否走代理。默认空 = 直连。
# 必须默认直连：Windows 上 urllib 会自动继承 IE/系统代理，
# 而设备平台在内网，一过代理就 502，这是很容易踩的坑。
_PROXY = ""
_opener = None


def log(msg):
    line = time.strftime("%H:%M:%S") + "  " + str(msg)
    try:
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:
            pass


def fatal(msg):
    """无控制台运行时的兜底提示，否则用户双击后毫无反应。"""
    log("FATAL " + msg)
    try:
        ctypes.windll.user32.MessageBoxW(0, str(msg), APP_TITLE, 0x10)
    except Exception:
        pass


# ------------------------------------------------------------------ 资源定位

def _base_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _app_dir():
    """exe（或脚本）所在目录，用来放用户自己的 config.json。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_index_html():
    """外部 index.html 优先，包内副本兜底。

    以前是先读包内的，导致「改了同目录的 index.html 却不生效、必须重打包」，
    白白浪费很多排查时间。现在 exe 同目录有 index.html 就用它，
    只在只拿到一个 exe（没有外部页面）时才回落到包内那份。
    """
    cands = [
        os.path.join(_app_dir(), "index.html"),    # exe 同目录：改了立即生效
        os.path.join(_base_dir(), "index.html"),   # 包内（frozen 时是 _MEIPASS）
        os.path.join(_base_dir(), "..", "index.html"),
    ]
    for p in cands:
        if os.path.isfile(p):
            return os.path.abspath(p)
    return None


# 编解码脚本（../shared/*.js）与页面分开存放，两个工具共用一份源码。
# 页面用相对路径 ../shared/xxx.js 引用，所以这里要把这个前缀映射到磁盘目录。
SHARED_PREFIX = "/shared/"
# V1.2 地图：页面用 ./vendor/leaflet.* 和 ./assets/marker-*.png 引用，
# 由本地服务映射出去（Leaflet 是本地文件，不走 CDN）。
STATIC_PREFIXES = ("/vendor/", "/assets/")
STATIC_EXTS = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg",
    ".svg": "image/svg+xml", ".ico": "image/x-icon"
}
SHARED_EXTS = {".js": "application/javascript; charset=utf-8",
               ".css": "text/css; charset=utf-8",
               ".json": "application/json; charset=utf-8"}


def find_shared_dir():
    """shared/ 的相对位置：随 index.html 走，或包内平铺。"""
    cands = []
    page = find_index_html()
    if page:
        cands.append(os.path.join(os.path.dirname(page), "..", "shared"))
    cands.append(os.path.join(_app_dir(), "shared"))
    cands.append(os.path.join(_base_dir(), "shared"))
    for p in cands:
        if os.path.isdir(p):
            return os.path.abspath(p)
    return None


def find_static_dir(name):
    """vendor/ 或 assets/：随 index.html 走，或 exe 同目录 / 包内平铺。"""
    cands = []
    page = find_index_html()
    if page:
        cands.append(os.path.join(os.path.dirname(page), name))
    cands.append(os.path.join(_app_dir(), name))
    cands.append(os.path.join(_base_dir(), name))
    for p in cands:
        if os.path.isdir(p):
            return os.path.abspath(p)
    return None


def load_config():
    """exe 同目录 config.json：
    {
      "platform": "http://10.85.40.3:1813",   // 设备平台地址
      "proxy": ""                              // 留空=直连；填 http://ip:port 才走代理
    }
    """
    cfg = {"platform": DEFAULT_PLATFORM, "proxy": ""}
    path = os.path.join(_app_dir(), "config.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                o = json.load(f)
            if isinstance(o, dict):
                if o.get("platform"):
                    cfg["platform"] = str(o["platform"])
                if o.get("proxy"):
                    cfg["proxy"] = str(o["proxy"])
        except Exception as e:
            log("config.json 读取失败，用默认值：" + str(e))
    return cfg


# ------------------------------------------------------------------ 页面组装

_JS_HEAD = (
    '<script>window.__JT808_DESKTOP__={enabled:true,version:%s,platform:%s};</script>\n'
)
_JS_BODY = (
    '<script>(function(){function p(){try{fetch("/__ping",{cache:"no-store"});}'
    'catch(e){}}p();setInterval(p,3000);})();</script>\n'
)


def build_page(platform):
    path = find_index_html()
    if not path:
        fatal("找不到 index.html，程序包不完整。\n请重新下载完整的 exe。")
        sys.exit(2)
    with open(path, "r", encoding="utf-8", newline="") as f:
        html = f.read()

    head_js = _JS_HEAD % (json.dumps(APP_VERSION), json.dumps(platform))
    if "</head>" in html:
        html = html.replace("</head>", head_js + "</head>", 1)
    else:
        html = head_js + html

    if "</body>" in html:
        html = html.replace("</body>", _JS_BODY + "</body>", 1)
    else:
        html += _JS_BODY
    return html


# ------------------------------------------------------------------ 页面热重载

# 外壳以前只在启动时读一次 index.html，之后死死抱着那份 bytes 不放：
# 改完页面不重启 exe 就永远看到旧版，而且双击 exe 时 already_running() 会直接
# 复用老实例，连"重启"的机会都不给。这里按源文件 mtime+size 判断是否需要重建。
_page_lock = threading.Lock()
_page_cache = {"key": None, "data": b""}


def current_page(platform):
    """当前该交给窗口的页面字节（源文件变了自动重建）。"""
    path = find_index_html()
    try:
        st = os.stat(path) if path else None
        key = (path, st.st_mtime_ns, st.st_size) if st else (None, 0, 0)
    except OSError:
        key = (path, 0, 0)
    with _page_lock:
        if _page_cache["key"] != key or not _page_cache["data"]:
            try:
                data = build_page(platform).encode("utf-8")
                _page_cache["data"] = data
                _page_cache["key"] = key
                log("页面已加载：%s（%d 字节）" % (path, len(data)))
            except Exception as e:
                log("页面重建失败，沿用上一版：" + str(e))
        return _page_cache["data"]


# ------------------------------------------------------------------ 转发

def _get_opener():
    global _opener
    if _opener is None:
        if _PROXY:
            h = urllib.request.ProxyHandler({"http": _PROXY, "https": _PROXY})
            log("转发走代理：" + _PROXY)
        else:
            h = urllib.request.ProxyHandler({})     # 空 dict = 不用任何代理
        _opener = urllib.request.build_opener(h)
    return _opener


def forward(target, body, ctype, timeout=60):
    """把请求原样打到上游，返回 (status, content_type, bytes)。不抛异常。"""
    req = urllib.request.Request(target, data=body, method="POST")
    req.add_header("Content-Type", ctype or "application/json")
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("User-Agent", "JT808-Desktop/" + APP_VERSION)
    try:
        with _get_opener().open(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", "application/json"), r.read()
    except urllib.error.HTTPError as e:
        try:
            data = e.read()
        except Exception:
            data = b""
        return e.code, e.headers.get("Content-Type", "text/plain"), data
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return 502, "application/json", json.dumps({
            "__proxy": "error",
            "message": "连不上上游 %s\n%s\n\n检查：平台是否启动、本机能否 ping 通、端口是否放通。"
                       % (target, reason)
        }, ensure_ascii=False).encode("utf-8")
    except socket.timeout:
        return 504, "application/json", json.dumps({
            "__proxy": "error",
            "message": "上游 %s 超过 %d 秒没有响应。" % (target, timeout)
        }, ensure_ascii=False).encode("utf-8")
    except Exception as e:
        return 502, "application/json", json.dumps({
            "__proxy": "error",
            "message": "转发异常：%s: %s" % (type(e).__name__, e)
        }, ensure_ascii=False).encode("utf-8")


# ------------------------------------------------------------------ HTTP 服务

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JT808Desktop/" + APP_VERSION
    sys_version = ""
    platform = DEFAULT_PLATFORM

    def log_message(self, fmt, *args):
        log("HTTP " + (fmt % args))

    # ---- 基础响应 ----
    def _send(self, code, ctype, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD" and data:
            try:
                self.wfile.write(data)
            except Exception:
                pass

    def _json(self, code, obj):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False))

    # ---- GET ----
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8",
                       current_page(self.platform))
        elif path == "/health":
            self._json(200, {
                "ok": True, "app": APP_ID, "version": APP_VERSION,
                "mode": "desktop", "target": self.platform,
            })
        elif path == "/__ping":
            _state["seen"] = True
            _state["last"] = time.time()
            self._json(200, {"ok": True})
        elif path == "/favicon.ico":
            self._send(200, "image/x-icon", b"")
        elif path.startswith(SHARED_PREFIX):
            self.serve_shared(path)
        elif path.startswith(STATIC_PREFIXES):
            self.serve_static(path)
        else:
            self._json(404, {"ok": False, "message": "not found"})

    def serve_shared(self, path):
        """把 /shared/xxx.js 落到磁盘上的 shared 目录。只允许单层文件名。"""
        name = os.path.basename(urllib.parse.unquote(path))
        root = find_shared_dir()
        if not root:
            self._json(404, {"ok": False, "message": "shared 目录缺失"})
            return
        full = os.path.abspath(os.path.join(root, name))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            self._json(404, {"ok": False, "message": "not found"})
            return
        ext = os.path.splitext(full)[1].lower()
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError as e:
            self._json(404, {"ok": False, "message": str(e)})
            return
        self._send(200, SHARED_EXTS.get(ext, "application/octet-stream"), data)

    def serve_static(self, path):
        """把 /vendor/xxx、/assets/xxx 落到磁盘同名目录。只允许单层文件名。"""
        p = urllib.parse.unquote(path)
        parts = [x for x in p.split("/") if x and x not in (".", "..")]
        if len(parts) != 2:
            self._json(404, {"ok": False, "message": "not found"})
            return
        root = find_static_dir(parts[0])
        if not root:
            self._json(404, {"ok": False, "message": parts[0] + " 目录缺失"})
            return
        full = os.path.abspath(os.path.join(root, parts[1]))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            self._json(404, {"ok": False, "message": "not found"})
            return
        ext = os.path.splitext(full)[1].lower()
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError as e:
            self._json(404, {"ok": False, "message": str(e)})
            return
        self._send(200, STATIC_EXTS.get(ext, "application/octet-stream"), data)

    # ---- POST ----
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        body = self.rfile.read(n) if n > 0 else b""
        ctype = self.headers.get("Content-Type") or "application/json"

        if u.path == "/__proxy":
            qs = urllib.parse.parse_qs(u.query)
            target = urllib.parse.unquote((qs.get("u") or [""])[0])
            if not target:
                self._json(400, {"__proxy": "error", "message": "缺少参数 u"})
                return
        elif u.path.startswith("/client/"):
            # 页面里地址写成相对路径时，落到这里，用默认平台拼
            target = self.platform.rstrip("/") + u.path
        else:
            self._json(404, {"ok": False, "message": "not found"})
            return

        scheme = urllib.parse.urlparse(target).scheme.lower()
        if scheme not in ("http", "https"):
            self._json(400, {"__proxy": "error",
                             "message": "只允许 http/https：" + target})
            return

        t0 = time.time()
        status, rct, data = forward(target, body, ctype)
        log("POST %s -> %s  %dB  %.0fms" % (target, status, len(data),
                                            (time.time() - t0) * 1000))
        self._send(status, rct, data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """Keep-Alive 连接被页面关掉是常态，别往日志里刷异常。"""
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError,
                            BrokenPipeError, socket.timeout)):
            return
        log("SERVER ERROR " + repr(exc))


# ------------------------------------------------------------------ 窗口

_BROWSERS = (
    r"Microsoft\Edge\Application\msedge.exe",
    r"Google\Chrome\Application\chrome.exe",
)


def find_browser():
    roots = [os.environ.get("ProgramFiles(x86)"),
             os.environ.get("ProgramFiles"),
             os.environ.get("LOCALAPPDATA")]
    for rel in _BROWSERS:
        for root in roots:
            if not root:
                continue
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                return p
    return None


def open_window(url):
    exe = find_browser()
    if not exe:
        log("没找到 Edge/Chrome，改用默认浏览器打开")
        webbrowser.open(url)
        return None

    prof = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                        "JT808Tool", "profile")
    try:
        os.makedirs(prof, exist_ok=True)
    except Exception:
        prof = os.path.join(tempfile.gettempdir(), "JT808ToolProfile")
        os.makedirs(prof, exist_ok=True)

    args = [
        exe,
        "--app=" + url,
        "--user-data-dir=" + prof,
        "--window-size=1500,960",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-service-autorun",
        "--disable-background-mode",
        # 最小化/被遮挡时不节流页面定时器，心跳与状态检测保持正常节奏
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-sync",
        "--disable-features=Translate,msEdgeSidebarV2,msEdgeCollections",
    ]
    log("启动窗口：" + exe)
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(args, close_fds=True, creationflags=flags)


# ------------------------------------------------------------------ 守护

# 窗口进程启动后这么久内就退出，说明窗口被已在运行的同 profile 浏览器进程接管了，
# 手里的进程句柄不代表窗口，改走心跳兜底。
HANDOFF_SEC = 15


def watchdog(proc=None):
    """决定服务何时退出。

    主判据：窗口进程（专用 profile 的 Edge/Chrome 主进程）退出 = 用户关了窗口。
    最小化、系统休眠只会让进程挂起，不会退出，所以服务一直在。
    兜底：没有窗口进程时按心跳判断，且系统休眠期间不计入空闲时间。
    """
    born = time.time()
    tick = born
    while True:
        time.sleep(2)
        now = time.time()
        if now - tick > 30:
            # 2s 的睡眠实际过去了 30s 以上 = 系统刚从休眠/挂起中恢复，空闲重新计时
            log("检测到系统休眠恢复（挂起约 %ds），重新计时" % int(now - tick))
            _state["last"] = now
            born = now
        tick = now

        if proc is not None:
            if proc.poll() is None:
                continue
            if now - born > HANDOFF_SEC:
                log("窗口已关闭（窗口进程退出），退出")
                break
            log("窗口进程启动即退出（被已有浏览器进程接管），改用心跳判断")
            proc = None

        if _state["seen"]:
            if now - _state["last"] > IDLE_EXIT_SEC:
                log("窗口已关闭（%ds 无心跳），退出" % IDLE_EXIT_SEC)
                break
        elif now - born > 180:
            log("启动 3 分钟无页面连接，退出")
            break
    os._exit(0)


def port_in_use(port):
    """本机这个端口上是不是已经有东西在监听。

    Windows 的 SO_REUSEADDR 语义比 Linux 宽松：进程 A 绑 0.0.0.0:18099、
    进程 B 再绑 127.0.0.1:18099 居然也能成功，然后连接落到谁身上看运气。
    所以不能只靠 bind 失败来判断占用，必须先 connect 探一次。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return True
    finally:
        try:
            s.close()
        except Exception:
            pass


def already_running(port=None):
    """扫描本机是否已有实例在跑，返回它在用的端口，没有则 None。

    探测必须绕开系统代理，否则会被系统代理转走。
    扫描多个端口是为了配合端口被占时的顺延策略——
    否则第一个实例起在 18100，第二次双击找不到 18099 又会起一个新实例。
    """
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    ports = [port] if port else SHELL_PORTS
    for p in ports:
        try:
            with op.open("http://127.0.0.1:%d/health" % p, timeout=0.6) as r:
                if json.loads(r.read().decode("utf-8", "replace")).get("app") == APP_ID:
                    return p
        except Exception:
            continue
    return None


def main():
    global _PROXY
    argv = sys.argv[1:]
    cfg = load_config()
    platform = cfg["platform"]
    _PROXY = cfg["proxy"]
    no_window = False
    port_pref = PREFERRED_PORT

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--platform" and i + 1 < len(argv):
            platform = argv[i + 1]
            i += 2
            continue
        if a == "--proxy" and i + 1 < len(argv):
            _PROXY = argv[i + 1]
            i += 2
            continue
        if a == "--port" and i + 1 < len(argv):
            try:
                port_pref = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if a in ("--no-window", "--headless"):
            no_window = True
        i += 1

    log("=" * 50)
    log("%s v%s 启动，平台 %s（转发%s）"
        % (APP_TITLE, APP_VERSION, platform,
           ("经代理 " + _PROXY) if _PROXY else "直连，不吃系统代理"))

    # 已经有一个实例在跑 —— 直接把它的页面再开一个窗口，然后本进程退出
    running = already_running()
    if running:
        url = "http://127.0.0.1:%d/" % running
        log("已有实例在跑，复用 " + url)
        if not no_window:
            open_window(url)
        return

    Handler.platform = platform
    current_page(platform)          # 预热一次，顺带把页面加载情况写进日志

    # 端口顺延：18099 被占就试 18100…18105，保证页面那套固定端口探测能命中
    httpd = None
    tried = []
    for p in [port_pref] + [x for x in SHELL_PORTS if x != port_pref]:
        if port_in_use(p):
            tried.append("%d(已被占用)" % p)
            continue
        try:
            httpd = Server(("127.0.0.1", p), Handler)
            break
        except OSError as e:
            tried.append("%d(%s)" % (p, e.strerror or e))
            continue
    if httpd is None:
        fatal("本地端口都起不来：" + "、".join(tried)
              + "\n请关掉占用 18099~18105 的程序后重试。")
        sys.exit(3)
    port = httpd.server_address[1]
    url = "http://127.0.0.1:%d/" % port
    log("本地服务 " + url)

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    proc = None
    if not no_window:
        proc = open_window(url)
    threading.Thread(target=watchdog, args=(proc,), daemon=True).start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
