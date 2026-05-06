#!/usr/bin/env python3
"""
HTTP 接口抓取管理
"""

import json
import os
import shutil
import socket
import subprocess
import sys
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
        self.addon_path = Settings.get_bundled_capture_addon_path()
        self.log_path = Settings.LOG_DIR / "capture_proxy.log"

    def is_available(self):
        return self._resolve_mitmdump_command() is not None

    def is_running(self):
        if self.process is None:
            return False
        if self.process.poll() is None:
            return True
        logger.warning("抓取服务进程已退出: returncode={}", self.process.returncode)
        self.process = None
        return False

    def start(self, capture_settings: dict):
        self._write_runtime(capture_settings)

        if self.is_running():
            self.start_asset_server(capture_settings)
            return True, "抓取服务已在运行，规则已刷新"

        mitmdump_cmd = self._resolve_mitmdump_command()
        if not mitmdump_cmd:
            helper_candidates = "\n".join(str(path) for path in Settings.get_bundled_mitmdump_candidates())
            return False, (
                "未找到 mitmdump。正式打包版应优先使用包内 mitmdump-helper。\n"
                f"已检查路径:\n{helper_candidates}\n"
                f"日志: {self.log_path}"
            )

        if not self.addon_path.exists():
            return False, f"抓取插件缺失: {self.addon_path}"

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")

        cmd = self._build_mitmdump_command(mitmdump_cmd, capture_settings)
        env = self._build_capture_env()
        self._write_launch_debug_header(cmd, env)

        with open(self.log_path, "a", encoding="utf-8") as log_file:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(Settings.RESOURCE_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

        first_check_delay = 0.8
        second_check_delay = 2.5
        time.sleep(first_check_delay)
        if self._handle_early_exit():
            return False, self._build_failure_message("抓取服务启动失败")

        logger.info("HTTP 抓取服务首次启动检查通过: PID={}", self.process.pid)
        time.sleep(max(0.0, second_check_delay - first_check_delay))
        if self._handle_early_exit():
            return False, self._build_failure_message("抓取服务启动后很快退出")

        proxy_host, proxy_port = self.get_proxy_address(capture_settings)
        proxy_ready, proxy_output = self.check_local_port(proxy_host, proxy_port, timeout=1.5)
        if not proxy_ready:
            self.stop()
            return False, f"抓取服务进程已启动，但 {proxy_port} 端口未监听成功: {proxy_output}\n日志: {self.log_path}"

        asset_ok, asset_message = self.start_asset_server(capture_settings)
        logger.info("HTTP 抓取服务已启动: PID={}", self.process.pid)
        if asset_ok:
            return True, "抓取服务已启动"
        return True, f"抓取服务已启动，但 CA 服务启动失败: {asset_message}"

    def _build_mitmdump_command(self, mitmdump_cmd: list[str], capture_settings: dict):
        """构造 mitmdump 启动命令，默认启用更保守的客户端兼容参数。"""
        listen_host = capture_settings.get("listen_host", "0.0.0.0")
        listen_port = str(int(capture_settings.get("listen_port", 8081) or 8081))
        options = {
            **self.DEFAULT_MITM_OPTIONS,
            **(capture_settings.get("mitm_options") or {}),
        }

        cmd = [
            *mitmdump_cmd,
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

    @staticmethod
    def _resolve_mitmdump_command() -> list[str] | None:
        bundled_helper = Settings.get_bundled_mitmdump_path()
        if bundled_helper.exists():
            return [str(bundled_helper)]

        system_mitmdump = shutil.which("mitmdump")
        if system_mitmdump:
            return [system_mitmdump]

        if getattr(sys, "frozen", False):
            return None

        try:
            result = subprocess.run(
                [sys.executable, "-m", "mitmdump", "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return [sys.executable, "-m", "mitmdump"]
        except Exception:
            return None

        return None

    def _build_capture_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["DP_CAPTURE_RUNTIME_PATH"] = str(self.runtime_path)
        env["DP_CAPTURE_INBOX_PATH"] = str(self.inbox_path)

        if getattr(sys, "frozen", False):
            existing_path = env.get("PYTHONPATH", "")
            resource_root = str(Settings.RESOURCE_DIR)
            env["PYTHONPATH"] = f"{resource_root}{os.pathsep}{existing_path}" if existing_path else resource_root

        return env

    def _write_launch_debug_header(self, cmd: list[str], env: dict[str, str]):
        debug_lines = [
            "",
            "=" * 72,
            f"[capture-launch] frozen={getattr(sys, 'frozen', False)} pid={os.getpid()}",
            f"[capture-launch] resource_dir={Settings.RESOURCE_DIR}",
            f"[capture-launch] base_dir={Settings.BASE_DIR}",
            f"[capture-launch] runtime_path={self.runtime_path}",
            f"[capture-launch] inbox_path={self.inbox_path}",
            f"[capture-launch] addon_path={self.addon_path} exists={self.addon_path.exists()}",
            f"[capture-launch] mitmdump_helper={Settings.get_bundled_mitmdump_path()} exists={Settings.get_bundled_mitmdump_path().exists()}",
            "[capture-launch] helper_candidates=" + " | ".join(str(path) for path in Settings.get_bundled_mitmdump_candidates()),
            "[capture-launch] addon_candidates=" + " | ".join(str(path) for path in Settings.get_bundled_capture_addon_candidates()),
            f"[capture-launch] command={' '.join(cmd)}",
            f"[capture-launch] cwd={Settings.RESOURCE_DIR}",
            f"[capture-launch] env.DP_CAPTURE_RUNTIME_PATH={env.get('DP_CAPTURE_RUNTIME_PATH')}",
            f"[capture-launch] env.PYTHONPATH={env.get('PYTHONPATH', '')}",
            "=" * 72,
        ]
        with open(self.log_path, "a", encoding="utf-8") as log_file:
            log_file.write("\n".join(debug_lines) + "\n")

    def _handle_early_exit(self) -> bool:
        if self.process is None:
            return True
        return_code = self.process.poll()
        if return_code is None:
            return False
        logger.error("抓取服务进程异常退出: returncode={}", return_code)
        self.process = None
        return True

    def _build_failure_message(self, prefix: str) -> str:
        log_tail = self._read_log_tail()
        last_line = log_tail.splitlines()[-1] if log_tail else prefix
        return f"{prefix}: {last_line}\n日志: {self.log_path}"

    def _read_log_tail(self, max_chars: int = 2000) -> str:
        try:
            if self.log_path.exists():
                return self.log_path.read_text(encoding="utf-8")[-max_chars:].strip()
        except Exception as exc:
            logger.warning("读取抓取日志失败: {}", exc)
        return ""

    def _write_runtime(self, capture_settings: dict):
        self.runtime_path.write_text(
            json.dumps(
                {
                    "patterns": self._parse_patterns(capture_settings.get("patterns_text", "")),
                    "inbox_path": str(self.inbox_path),
                    "platform": capture_settings.get("platform", "ios"),
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
            self.ensure_ca_assets_ready()
            self.asset_server = CACertAssetServer(
                self.get_ca_paths(),
                host=host,
                port=asset_port,
                public_host=public_host,
            )
            self.asset_server.start()
            ca_ok, ca_output = self.check_local_port(public_host, asset_port, timeout=1.5)
            if not ca_ok:
                self.stop_asset_server()
                return False, f"CA 下载服务进程已启动，但 {asset_port} 端口未监听成功: {ca_output}"
            return True, "CA 下载服务已启动"
        except Exception as exc:
            self.asset_server = None
            logger.error("启动 CA 下载服务失败: {}", exc)
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
                    logger.error("导入抓取数据失败: {}", exc)
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
            return None

    def get_proxy_address(self, capture_settings: dict):
        host = self.get_local_ip()
        port = int(capture_settings.get("listen_port", 8081) or 8081)
        return host, port

    @staticmethod
    def check_local_port(host: str | None, port: int, timeout: float = 1.5):
        """检测本机目标端口是否已监听。"""
        candidates = []
        normalized_host = (host or "").strip()
        if normalized_host and normalized_host not in {"0.0.0.0", "::"}:
            candidates.append(normalized_host)
        candidates.extend(["127.0.0.1", "localhost"])

        tried = []
        last_error = ""
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
        return {
            "pem": Settings.CAPTURE_ASSET_DIR / "mitmproxy-ca-cert.pem",
            "cer": Settings.CAPTURE_ASSET_DIR / "mitmproxy-ca-cert.cer",
            "p12": Settings.CAPTURE_ASSET_DIR / "mitmproxy-ca-cert.p12",
        }

    def ensure_ca_assets_ready(self):
        target_paths = self.get_ca_paths()
        if target_paths["pem"].exists() and target_paths["cer"].exists():
            return target_paths

        for source_dir in self._candidate_mitmproxy_ca_dirs():
            copied_any = False
            for name, target_path in target_paths.items():
                source_path = source_dir / f"mitmproxy-ca-cert.{name}"
                if source_path.exists():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target_path)
                    copied_any = True
            if copied_any and target_paths["pem"].exists() and target_paths["cer"].exists():
                logger.info("已同步 mitmproxy CA 文件到 {}", Settings.CAPTURE_ASSET_DIR)
                return target_paths

        logger.warning("未找到可同步的 mitmproxy CA 文件，已检查目录: {}", ", ".join(str(path) for path in self._candidate_mitmproxy_ca_dirs()))
        return target_paths

    @staticmethod
    def _candidate_mitmproxy_ca_dirs() -> list[Path]:
        home = Path.home()
        candidates = [
            home / ".mitmproxy",
            home / "Library" / "Application Support" / "mitmproxy",
            Settings.BASE_DIR / ".mitmproxy",
            Settings.RESOURCE_DIR / ".mitmproxy",
        ]
        result: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    def get_ca_install_url(self, capture_settings: dict):
        host, _ = self.get_proxy_address(capture_settings)
        asset_port = int(capture_settings.get("asset_port", 8765) or 8765)
        if not host:
            return ""
        return f"http://{host}:{asset_port}/"
