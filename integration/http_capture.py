#!/usr/bin/env python3
"""
HTTP 接口抓取管理
"""

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

from config.settings import Settings
from data.capture_store import CaptureStore
from gui.capture.network_utils import list_local_ipv4_addresses
from integration.cert_asset_server import CACertAssetServer
from utils.logger import logger


class HttpCaptureManager:
    """mitmproxy 抓取进程管理"""

    DEFAULT_MITM_OPTIONS = {
        "http2": False,
        "http3": False,
        "connection_strategy": "lazy",
        "ssl_insecure": True,
    }

    def __init__(self):
        self.process = None
        self.asset_server = None
        self.store = CaptureStore()
        self.offset_path = Settings.CAPTURE_OFFSET_FILE
        self.inbox_path = Settings.CAPTURE_INBOX_FILE
        self.runtime_path = Settings.CAPTURE_RUNTIME_FILE
        self.addon_path = Settings.BASE_DIR / "integration" / "mitm_capture_addon.py"
        self.log_path = Settings.LOG_DIR / "capture_proxy.log"

    def is_available(self):
        return shutil.which("mitmdump") is not None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def start(self, capture_settings: dict):
        self._write_runtime(capture_settings)

        if self.is_running():
            self.start_asset_server(capture_settings)
            return True, "抓取服务已在运行，规则已刷新"

        mitmdump = shutil.which("mitmdump")
        if not mitmdump:
            return False, "未找到 mitmdump，请先安装 mitmproxy"

        cmd = self._build_mitmdump_command(mitmdump, capture_settings)

        log_file = open(self.log_path, "a", encoding="utf-8")
        self.process = subprocess.Popen(
            cmd,
            cwd=str(Settings.BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(0.8)
        if self.process.poll() is not None:
            error_message = "抓取服务启动失败"
            try:
                if self.log_path.exists():
                    log_tail = self.log_path.read_text(encoding="utf-8")[-1000:].strip()
                    if log_tail:
                        error_message = log_tail.splitlines()[-1]
            except Exception:
                pass
            self.process = None
            return False, f"抓取服务启动失败: {error_message}"
        self.start_asset_server(capture_settings)
        logger.info(f"HTTP 抓取服务已启动: PID={self.process.pid}")
        return True, "抓取服务已启动（兼容模式）"

    def _build_mitmdump_command(self, mitmdump: str, capture_settings: dict):
        """构造 mitmdump 启动命令，默认启用更保守的客户端兼容参数。"""
        listen_host = capture_settings.get("listen_host", "0.0.0.0")
        listen_port = str(int(capture_settings.get("listen_port", 8081) or 8081))
        options = {
            **self.DEFAULT_MITM_OPTIONS,
            **(capture_settings.get("mitm_options") or {}),
        }

        cmd = [
            mitmdump,
            "-q",
            "--listen-host",
            listen_host,
            "--listen-port",
            listen_port,
        ]

        for option_name, option_value in options.items():
            if isinstance(option_value, bool):
                serialized = "true" if option_value else "false"
            else:
                serialized = str(option_value)
            cmd.extend(["--set", f"{option_name}={serialized}"])

        cmd.extend([
            "-s",
            str(self.addon_path),
        ])
        return cmd

    def _write_runtime(self, capture_settings: dict):
        self.runtime_path.write_text(
            json.dumps(
                {
                    "patterns": self._parse_patterns(capture_settings.get("patterns_text", "")),
                    "inbox_path": str(self.inbox_path),
                    "platform": capture_settings.get("platform", "android"),
                    "max_body_kb": int(capture_settings.get("max_body_kb", 512) or 512),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def stop(self):
        if not self.process:
            return True, "抓取服务未运行"

        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        finally:
            self.process = None

        self.stop_asset_server()
        logger.info("HTTP 抓取服务已停止")
        return True, "抓取服务已停止"

    def start_asset_server(self, capture_settings: dict):
        host = capture_settings.get("listen_host", "0.0.0.0")
        public_host, _ = self.get_proxy_address(capture_settings)
        asset_port = int(capture_settings.get("asset_port", 8765) or 8765)

        if self.asset_server and self.asset_server.is_running():
            return True, "CA 下载服务已在运行"

        try:
            self.asset_server = CACertAssetServer(
                self.get_ca_paths(),
                host=host,
                port=asset_port,
                public_host=public_host,
            )
            self.asset_server.start()
            return True, "CA 下载服务已启动"
        except Exception as exc:
            self.asset_server = None
            logger.error(f"启动 CA 下载服务失败: {exc}")
            return False, f"启动 CA 下载服务失败: {exc}"

    def stop_asset_server(self):
        if self.asset_server:
            self.asset_server.stop()
            self.asset_server = None
        return True, "CA 下载服务已停止"

    def import_pending(self):
        if not self.inbox_path.exists():
            return 0

        start_offset = 0
        if self.offset_path.exists():
            try:
                start_offset = int(self.offset_path.read_text(encoding="utf-8") or "0")
            except Exception:
                start_offset = 0

        imported = 0
        with open(self.inbox_path, "r", encoding="utf-8") as file:
            file.seek(start_offset)
            for line in file:
                payload = line.strip()
                if not payload:
                    continue
                try:
                    self.store.insert_capture(json.loads(payload))
                    imported += 1
                except Exception as exc:
                    logger.error(f"导入抓取数据失败: {exc}")
            end_offset = file.tell()

        self.offset_path.write_text(str(end_offset), encoding="utf-8")
        return imported

    def clear_temporary_capture_data(self):
        self.store.clear_captures()
        self.inbox_path.write_text("", encoding="utf-8")
        self.offset_path.write_text("0", encoding="utf-8")
        return True, "临时抓包数据已清理"

    @staticmethod
    def _parse_patterns(patterns_text: str):
        lines = [line.strip() for line in patterns_text.splitlines() if line.strip()]
        if lines == ["*"]:
            return []
        return lines

    @staticmethod
    def get_local_ip():
        local_ips = list_local_ipv4_addresses()
        if local_ips:
            return local_ips[0]
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except Exception:
            return ""

    def get_proxy_address(self, capture_settings: dict):
        host = capture_settings.get("listen_host", "0.0.0.0")
        if host in {"0.0.0.0", "::"}:
            host = self.get_local_ip()
        port = int(capture_settings.get("listen_port", 8081) or 8081)
        return host, port

    @staticmethod
    def check_local_port(host: str, port: int, timeout: float = 1.5):
        """检测本机目标端口是否已监听"""
        candidates = []
        normalized_host = (host or "").strip()
        if normalized_host and normalized_host not in {"0.0.0.0", "::"}:
            candidates.append(normalized_host)
        candidates.extend(["127.0.0.1", "localhost"])

        tried = []
        for candidate in candidates:
            if candidate in tried:
                continue
            tried.append(candidate)
            try:
                with socket.create_connection((candidate, int(port)), timeout=timeout):
                    return True, f"{candidate}:{int(port)} 可连接"
            except Exception as exc:
                last_error = str(exc)

        return False, last_error if tried else "未提供可检测的主机地址"

    def get_ca_paths(self):
        mitm_dir = Path.home() / ".mitmproxy"
        return {
            "pem": mitm_dir / "mitmproxy-ca-cert.pem",
            "crt": mitm_dir / "mitmproxy-ca-cert.cer",
            "p12": mitm_dir / "mitmproxy-ca-cert.p12",
        }

    def get_ca_install_url(self, capture_settings: dict):
        public_host, _ = self.get_proxy_address(capture_settings)
        asset_port = int(capture_settings.get("asset_port", 8765) or 8765)
        return f"http://{public_host}:{asset_port}/"
