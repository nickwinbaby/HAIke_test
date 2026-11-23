"""电子围栏地图的本地服务和浏览器窗口入口。"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import urllib.parse
import webbrowser


class MapPickerServer:
    """仅绑定 127.0.0.1，为本工程的地图页面提供资源与回填通道。"""

    def __init__(self, map_dir=None):
        self.map_dir = Path(map_dir or Path(__file__).resolve().parent.parent / "map").resolve()
        self.token = secrets.token_urlsafe(24)
        self._lock = threading.Lock()
        self._results = []
        self._tracks = []
        self._server = None
        self._thread = None

    @property
    def url(self):
        return self.url_for("all")

    def url_for(self, mode, **options):
        self.start()
        port = self._server.server_address[1]
        query = urllib.parse.urlencode({"token": self.token, "mode": mode, **options})
        return f"http://127.0.0.1:{port}/?{query}"

    def start(self):
        if self._server is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return

            def _send(self, status, content_type, data):
                if isinstance(data, str):
                    data = data.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/api/tracks":
                    query = urllib.parse.parse_qs(parsed.query)
                    if (query.get("token") or [""])[0] != owner.token:
                        self._send(403, "application/json; charset=utf-8", '{"ok":false}')
                        return
                    with owner._lock:
                        payload = json.dumps(owner._tracks, ensure_ascii=False)
                    self._send(200, "application/json; charset=utf-8", payload)
                    return
                request_path = urllib.parse.unquote(parsed.path)
                relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
                target = (owner.map_dir / relative).resolve()
                try:
                    target.relative_to(owner.map_dir)
                except ValueError:
                    self._send(403, "text/plain; charset=utf-8", "forbidden")
                    return
                if not target.is_file():
                    self._send(404, "text/plain; charset=utf-8", "not found")
                    return
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if content_type.startswith("text/") or target.suffix in {".js", ".json"}:
                    content_type += "; charset=utf-8"
                self._send(200, content_type, target.read_bytes())

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path not in {"/api/apply", "/api/tracks"}:
                    self._send(404, "application/json", b'{"ok":false}')
                    return
                query = urllib.parse.parse_qs(parsed.query)
                if (query.get("token") or [""])[0] != owner.token:
                    self._send(403, "application/json", b'{"ok":false}')
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if parsed.path == "/api/apply" and not isinstance(payload, dict):
                        raise ValueError("invalid payload")
                    if parsed.path == "/api/tracks" and not isinstance(payload, list):
                        raise ValueError("invalid payload")
                except Exception:
                    self._send(400, "application/json", b'{"ok":false}')
                    return
                with owner._lock:
                    if parsed.path == "/api/tracks":
                        owner._tracks = payload
                    else:
                        owner._results.append(payload)
                self._send(200, "application/json; charset=utf-8", '{"ok":true}')

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def pop_results(self):
        with self._lock:
            results = self._results[:]
            self._results.clear()
        return results

    def open_window(self, mode="all", **options):
        """使用系统默认浏览器打开地图，返回可手动访问的本地地址。"""
        url = self.url_for(mode, **options)
        opened = False
        if os.name == "nt" and hasattr(os, "startfile"):
            try:
                os.startfile(url)
                opened = True
            except OSError:
                pass
        if not opened:
            opened = bool(webbrowser.open_new_tab(url))
        if not opened:
            raise RuntimeError(f"无法自动打开浏览器，请手动访问：{url}")
        return url

