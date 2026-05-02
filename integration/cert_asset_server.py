#!/usr/bin/env python3
"""
本地 CA 下载服务
"""

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from utils.logger import logger


class _AssetRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        asset_server = self.server.asset_server

        if self.path in {"/", "/index.html"}:
            self._send_html(asset_server.build_index_html())
            return

        if self.path.startswith("/download/"):
            filename = self.path.split("/download/", 1)[1]
            file_path = asset_server.resolve_asset_file(filename)
            if file_path and file_path.exists():
                self._send_file(file_path)
                return

        if self.path == "/health":
            self._send_text("ok")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _send_html(self, html: str):
        payload = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, text: str):
        payload = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, file_path: Path):
        payload = file_path.read_bytes()
        content_type = "application/octet-stream"
        if file_path.suffix in {".pem", ".cer", ".crt"}:
            content_type = "application/x-x509-ca-cert"
        elif file_path.suffix == ".p12":
            content_type = "application/x-pkcs12"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class CACertAssetServer:
    """证书下载静态服务"""

    def __init__(self, ca_paths: dict, host: str = "0.0.0.0", port: int = 8765, public_host: str = None):
        self.ca_paths = {key: Path(value) for key, value in (ca_paths or {}).items()}
        self.host = host
        self.port = int(port)
        self.public_host = public_host or host
        self.httpd = None
        self.thread = None

    def start(self):
        if self.is_running():
            return True

        self.httpd = ThreadingHTTPServer((self.host, self.port), _AssetRequestHandler)
        self.httpd.asset_server = self
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"CA 下载服务已启动: {self.host}:{self.port}")
        return True

    def stop(self):
        if not self.httpd:
            return True

        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        self.thread = None
        logger.info("CA 下载服务已停止")
        return True

    def is_running(self):
        return self.httpd is not None

    def get_public_url(self):
        return f"http://{self.public_host}:{self.port}/"

    def resolve_asset_file(self, filename: str):
        file_map = {
            "mitmproxy-ca-cert.pem": self.ca_paths.get("pem"),
            "mitmproxy-ca-cert.cer": self.ca_paths.get("crt"),
            "mitmproxy-ca-cert.p12": self.ca_paths.get("p12"),
        }
        return file_map.get(filename)

    def build_index_html(self):
        android_link = "/download/mitmproxy-ca-cert.cer"
        ios_link = "/download/mitmproxy-ca-cert.pem"
        return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CA 下载</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; color: #0f172a; }}
    .card {{ max-width: 760px; margin: 0 auto; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px; padding: 24px; }}
    h1 {{ margin-top: 0; }}
    a.button {{ display: inline-block; margin: 8px 12px 8px 0; padding: 12px 16px; background: #2563eb; color: white; text-decoration: none; border-radius: 10px; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }}
    li {{ margin: 8px 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>抓包 CA 下载</h1>
    <p>当前下载地址: <code>{self.get_public_url()}</code></p>
    <p>
      <a class="button" href="{android_link}">下载 Android 证书</a>
      <a class="button" href="{ios_link}">下载 iOS 证书</a>
    </p>
    <h2>Android</h2>
    <ol>
      <li>先在应用里设置 Wi-Fi/系统代理到 <code>{self.public_host}:{self.port}</code> 对应的抓包端口。</li>
      <li>下载 <code>.cer</code> 文件并在系统中安装。</li>
      <li>注意 Android 7+ 很多应用默认不信任用户 CA，如目标 App 做了证书校验，仍需进一步绕过。</li>
    </ol>
    <h2>iPhone / iPad</h2>
    <ol>
      <li>在 Wi-Fi 代理中配置抓包代理地址。</li>
      <li>下载证书后按提示安装描述文件。</li>
      <li>安装后前往 设置 → 通用 → 关于本机 → 证书信任设置，手动开启信任。</li>
    </ol>
  </div>
</body>
</html>
        """.strip()

