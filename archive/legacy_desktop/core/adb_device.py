#!/usr/bin/env python3
"""
ADB操作模块
通过ADB与Android设备通信
"""

import os
import platform
import re
import shlex
import socket
import subprocess
import time
import shutil
import zipfile
import urllib.request
from pathlib import Path
from typing import List, Tuple, Optional

from utils.logger import logger
from config.settings import Settings


class ADBDevice:
    """ADB设备操作类"""

    def __init__(self, device_id: str = None, adb_path: str = None):
        """
        Args:
            device_id: 设备ID，如果为None则使用第一个连接的设备
        """
        self.device_id = device_id
        self.connected = False
        self.adb_path = None
        self._configured_adb_path = adb_path
        self._check_adb()

        if device_id:
            self.connected = self._test_connection()
            if self.connected:
                logger.info(f"ADB设备已连接: {device_id}")

    def _check_adb(self):
        """检查ADB是否可用"""
        try:
            resolved = self.resolve_adb_path(self._configured_adb_path)
            if not resolved:
                logger.error("未找到ADB工具，请安装Android SDK Platform Tools")
                return False

            self.adb_path = resolved
            result = subprocess.run(
                [self.adb_path, 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"ADB工具可用: {self.adb_path}")
                return True
            else:
                logger.error("ADB工具不可用")
                return False
        except FileNotFoundError:
            logger.error("未找到ADB工具，请安装Android SDK Platform Tools")
            return False
        except Exception as e:
            logger.error(f"检查ADB失败: {e}")
            return False

    def _run_adb_command(self, args: List[str], timeout: int = 30) -> Tuple[bool, str]:
        """
        执行ADB命令

        Args:
            args: ADB命令参数列表
            timeout: 超时时间（秒）

        Returns:
            (是否成功, 输出内容)
        """
        try:
            if not self.adb_path:
                self.adb_path = self.resolve_adb_path(self._configured_adb_path)
            if not self.adb_path:
                return False, "未找到ADB工具"

            cmd = [self.adb_path]
            if self.device_id:
                cmd.extend(['-s', self.device_id])
            cmd.extend(args)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                logger.error(f"ADB命令失败: {' '.join(cmd)}\n错误: {result.stderr}")
                return False, result.stderr.strip()

        except subprocess.TimeoutExpired:
            logger.error(f"ADB命令超时: {' '.join(args)}")
            return False, "命令超时"
        except Exception as e:
            logger.error(f"执行ADB命令异常: {e}")
            return False, str(e)

    def _test_connection(self) -> bool:
        """测试设备连接"""
        success, output = self._run_adb_command(['shell', 'echo', 'test'])
        return success and output == 'test'

    @staticmethod
    def resolve_adb_path(adb_path: str = None) -> Optional[str]:
        """解析可用的 ADB 可执行文件路径"""
        candidates = []
        if adb_path:
            candidates.append(Path(adb_path))

        env_path = os.environ.get("ADB_PATH")
        if env_path:
            candidates.append(Path(env_path))

        local_adb = Settings.get_local_adb_path()
        candidates.append(local_adb)

        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)

        adb_in_path = shutil.which("adb")
        if adb_in_path:
            return adb_in_path

        return None

    @classmethod
    def is_adb_available(cls, adb_path: str = None) -> Tuple[bool, str]:
        """检查 ADB 是否存在"""
        resolved = cls.resolve_adb_path(adb_path)
        return bool(resolved), resolved or ""

    @staticmethod
    def _run_raw_adb_command(args: List[str], adb_path: str = None, timeout: int = 30) -> Tuple[bool, str]:
        """执行不绑定设备的 adb 命令"""
        resolved = ADBDevice.resolve_adb_path(adb_path)
        if not resolved:
            return False, "未找到ADB工具"

        try:
            result = subprocess.run(
                [resolved, *args],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            error_text = result.stderr.strip() or result.stdout.strip()
            logger.error(f"ADB命令失败: {[resolved, *args]}\n错误: {error_text}")
            return False, error_text
        except Exception as e:
            logger.error(f"执行ADB命令异常: {e}")
            return False, str(e)

    @staticmethod
    def list_devices(adb_path: str = None) -> List[dict]:
        """
        列出所有连接的设备

        Returns:
            设备列表 [{'id': 'xxx', 'status': 'device'}, ...]
        """
        try:
            resolved = ADBDevice.resolve_adb_path(adb_path)
            if not resolved:
                logger.error("未找到ADB工具，请安装Android SDK Platform Tools")
                return []

            result = subprocess.run(
                [resolved, 'devices'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.error("获取设备列表失败")
                return []

            devices = []
            lines = result.stdout.strip().split('\n')[1:]  # 跳过第一行标题

            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        devices.append({
                            'id': parts[0],
                            'status': parts[1]
                        })

            logger.info(f"找到 {len(devices)} 个设备")
            return devices

        except Exception as e:
            logger.error(f"列出设备失败: {e}")
            return []

    @staticmethod
    def connect_remote(address: str, adb_path: str = None, timeout: int = 15) -> Tuple[bool, str]:
        """连接无线 ADB 设备"""
        address = (address or "").strip()
        if not address:
            return False, "请输入设备地址，例如 192.168.1.2:5555"
        return ADBDevice._run_raw_adb_command(['connect', address], adb_path=adb_path, timeout=timeout)

    @staticmethod
    def disconnect_remote(address: str = None, adb_path: str = None, timeout: int = 15) -> Tuple[bool, str]:
        """断开无线 ADB 设备"""
        args = ['disconnect']
        if address:
            args.append(address.strip())
        return ADBDevice._run_raw_adb_command(args, adb_path=adb_path, timeout=timeout)

    @staticmethod
    def list_mdns_services(adb_path: str = None) -> List[dict]:
        """读取 adb mDNS 服务列表"""
        success, output = ADBDevice._run_raw_adb_command(['mdns', 'services'], adb_path=adb_path, timeout=10)
        if not success:
            return []

        services = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("List of discovered mdns services"):
                continue
            match = re.match(r"^(?P<name>\S+)\s+(?P<type>_[^\s]+)\s+(?P<address>\S+)$", line)
            if not match:
                continue
            services.append(match.groupdict())
        return services

    @staticmethod
    def pair_remote(address: str, pairing_code: str, adb_path: str = None, timeout: int = 20) -> Tuple[bool, str]:
        """Android 11+ 无线调试配对"""
        address = (address or "").strip()
        pairing_code = (pairing_code or "").strip()
        if not address:
            return False, "请输入配对地址，例如 192.168.1.8:37143"
        if not pairing_code:
            return False, "请输入 6 位配对码"
        return ADBDevice._run_raw_adb_command(
            ['pair', address, pairing_code],
            adb_path=adb_path,
            timeout=timeout,
        )

    @staticmethod
    def list_local_ipv4_addresses() -> List[str]:
        """获取当前电脑可用的局域网 IPv4 地址"""
        addresses = []
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if ip and not ip.startswith("127."):
                    addresses.append(ip)
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
                ip = info[4][0]
                if ip.startswith("127."):
                    continue
                addresses.append(ip)
        except Exception:
            pass

        try:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.connect(("8.8.8.8", 80))
            ip = udp.getsockname()[0]
            if ip and not ip.startswith("127."):
                addresses.append(ip)
            udp.close()
        except Exception:
            pass

        normalized = []
        for ip in addresses:
            if ip not in normalized:
                normalized.append(ip)
        return normalized

    @staticmethod
    def get_platform_tools_download_url() -> Optional[str]:
        """返回当前平台对应的官方 platform-tools 下载地址"""
        system = platform.system().lower()
        if system == 'darwin':
            return "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
        if system == 'linux':
            return "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
        if system == 'windows':
            return "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
        return None

    @staticmethod
    def download_platform_tools(target_dir: Path = None) -> Tuple[bool, str, Optional[str]]:
        """下载并解压官方 platform-tools"""
        url = ADBDevice.get_platform_tools_download_url()
        if not url:
            return False, "当前系统暂不支持自动下载 ADB", None

        target_dir = Path(target_dir or Settings.TOOLS_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        archive_path = target_dir / "platform-tools-latest.zip"
        extract_dir = target_dir

        try:
            logger.info(f"开始下载 platform-tools: {url}")
            with urllib.request.urlopen(url, timeout=120) as response, open(archive_path, 'wb') as file:
                shutil.copyfileobj(response, file)

            if Settings.PLATFORM_TOOLS_DIR.exists():
                shutil.rmtree(Settings.PLATFORM_TOOLS_DIR)

            with zipfile.ZipFile(archive_path, 'r') as zip_file:
                zip_file.extractall(extract_dir)

            adb_path = Settings.get_local_adb_path()
            if adb_path.exists() and os.name != 'nt':
                adb_path.chmod(adb_path.stat().st_mode | 0o111)

            logger.info(f"platform-tools 安装完成: {adb_path}")
            return True, f"ADB 下载完成: {adb_path}", str(adb_path)
        except Exception as e:
            logger.error(f"下载 platform-tools 失败: {e}")
            return False, f"下载ADB失败: {e}", None
        finally:
            try:
                if archive_path.exists():
                    archive_path.unlink()
            except Exception:
                pass

    def connect(self, device_id: str = None) -> bool:
        """
        连接设备

        Args:
            device_id: 设备ID，如果为None则使用第一个设备

        Returns:
            是否成功
        """
        if device_id:
            self.device_id = device_id

        if not self.adb_path:
            self.adb_path = self.resolve_adb_path(self._configured_adb_path)
        if not self.adb_path:
            logger.error("未找到可用的ADB工具")
            return False

        if not self.device_id:
            devices = self.list_devices(self.adb_path)
            if devices:
                self.device_id = devices[0]['id']
            else:
                logger.error("未找到可用设备")
                return False

        self.connected = self._test_connection()
        if self.connected:
            logger.info(f"成功连接设备: {self.device_id}")
        else:
            logger.error(f"连接设备失败: {self.device_id}")

        return self.connected

    def tap(self, x: int, y: int) -> bool:
        """
        点击屏幕

        Args:
            x, y: 点击坐标

        Returns:
            是否成功
        """
        if not self.connected:
            logger.error("设备未连接")
            return False

        success, _ = self._run_adb_command(['shell', 'input', 'tap', str(x), str(y)])
        if success:
            logger.info(f"点击坐标: ({x}, {y})")
        return success

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 500) -> bool:
        """
        滑动屏幕

        Args:
            x1, y1: 起点坐标
            x2, y2: 终点坐标
            duration: 滑动时长（毫秒）

        Returns:
            是否成功
        """
        if not self.connected:
            logger.error("设备未连接")
            return False

        success, _ = self._run_adb_command([
            'shell', 'input', 'swipe',
            str(x1), str(y1), str(x2), str(y2), str(duration)
        ])

        if success:
            logger.info(f"滑动: ({x1}, {y1}) -> ({x2}, {y2})")
        return success

    def screenshot(self, save_path: str = '/tmp/screenshot.png') -> Optional[str]:
        """
        截取屏幕

        Args:
            save_path: 保存路径

        Returns:
            截图文件路径，失败返回None
        """
        if not self.connected:
            logger.error("设备未连接")
            return None

        # 在设备上截图
        device_path = '/sdcard/screenshot.png'
        success, _ = self._run_adb_command(['shell', 'screencap', '-p', device_path])

        if not success:
            logger.error("设备截图失败")
            return None

        # 拉取到本地
        success, _ = self._run_adb_command(['pull', device_path, save_path])

        if success:
            logger.info(f"截图已保存: {save_path}")
            return save_path
        else:
            logger.error("拉取截图失败")
            return None

    def get_screen_size(self) -> Optional[Tuple[int, int]]:
        """
        获取屏幕尺寸

        Returns:
            (width, height) 或 None
        """
        if not self.connected:
            logger.error("设备未连接")
            return None

        success, output = self._run_adb_command(['shell', 'wm', 'size'])

        if success:
            # 输出格式: Physical size: 1080x2340
            try:
                size_str = output.split(':')[1].strip()
                width, height = map(int, size_str.split('x'))
                logger.info(f"屏幕尺寸: {width}x{height}")
                return width, height
            except Exception as e:
                logger.error(f"解析屏幕尺寸失败: {e}")
                return None
        else:
            return None

    def get_device_info(self) -> dict:
        """
        获取设备信息

        Returns:
            设备信息字典
        """
        if not self.connected:
            return {'connected': False}

        info = {'connected': True, 'id': self.device_id}

        # 获取设备型号
        success, output = self._run_adb_command(['shell', 'getprop', 'ro.product.model'])
        if success:
            info['model'] = output

        # 获取Android版本
        success, output = self._run_adb_command(['shell', 'getprop', 'ro.build.version.release'])
        if success:
            info['android_version'] = output

        # 获取屏幕尺寸
        screen_size = self.get_screen_size()
        if screen_size:
            info['screen_width'] = screen_size[0]
            info['screen_height'] = screen_size[1]

        return info

    def disconnect(self):
        """断开连接"""
        self.connected = False
        self.device_id = None
        logger.info("设备已断开")

    def set_http_proxy(self, host: str, port: int) -> bool:
        """设置 Android 全局 HTTP 代理"""
        if not self.connected:
            logger.error("设备未连接")
            return False

        success, _ = self._run_adb_command(
            ['shell', 'settings', 'put', 'global', 'http_proxy', f'{host}:{int(port)}']
        )
        if success:
            logger.info(f"Android HTTP 代理已设置: {host}:{port}")
        return success

    def get_http_proxy(self) -> Optional[str]:
        """读取 Android 全局 HTTP 代理"""
        if not self.connected:
            logger.error("设备未连接")
            return None

        success, output = self._run_adb_command(['shell', 'settings', 'get', 'global', 'http_proxy'])
        if not success:
            return None

        proxy_value = (output or "").strip()
        if proxy_value in {"", "null", ":0"}:
            return ""
        return proxy_value

    def ping_host(self, host: str) -> Tuple[bool, str]:
        """检测设备是否能连通指定主机"""
        if not self.connected:
            return False, "设备未连接"

        commands = [
            ['shell', 'ping', '-c', '1', '-W', '2', host],
            ['shell', 'ping', '-c', '1', host],
        ]
        for command in commands:
            success, output = self._run_adb_command(command, timeout=6)
            if success:
                return True, output
        return False, output

    def check_tcp_port(self, host: str, port: int) -> Tuple[bool, str]:
        """检测设备到指定主机端口的 TCP 连通性"""
        status, output = self.probe_tcp_port(host, port)
        return status == "reachable", output

    def probe_tcp_port(self, host: str, port: int) -> Tuple[str, str]:
        """检测设备到指定主机端口的 TCP 连通性，返回 reachable/unreachable/unsupported"""
        if not self.connected:
            return "disconnected", "设备未连接"

        safe_host = shlex.quote(host)
        raw_host = host.strip()
        safe_port = str(int(port))
        shell_commands = [
            f"toybox nc -z -w 2 {safe_host} {safe_port}",
            f"nc -z -w 2 {safe_host} {safe_port}",
            f"busybox nc -z -w 2 {safe_host} {safe_port}",
            f"exec 3<>/dev/tcp/{raw_host}/{safe_port}",
        ]
        last_output = ""
        saw_unsupported = False
        for shell_command in shell_commands:
            success, output = self._run_adb_command(['shell', 'sh', '-c', shell_command], timeout=6)
            last_output = output
            normalized_output = (output or "").strip().lower()
            if success and not self._looks_like_shell_help(normalized_output):
                return "reachable", output
            if self._looks_like_shell_help(normalized_output) or self._looks_like_unsupported_tcp_probe(normalized_output):
                saw_unsupported = True
                continue

        if saw_unsupported:
            fallback = last_output or "当前 Android shell 不支持可用的 TCP 端口探测命令"
            return "unsupported", fallback
        return "unreachable", last_output

    @staticmethod
    def _looks_like_shell_help(output: str) -> bool:
        """过滤 Android shell 中把帮助信息误当成功的情况"""
        if not output:
            return False
        help_markers = [
            "acpi base64 basename blkid",
            "toybox",
            "usage:",
            "applet not found",
            "inaccessible or not found",
        ]
        return any(marker in output for marker in help_markers)

    @staticmethod
    def _looks_like_unsupported_tcp_probe(output: str) -> bool:
        """识别 Android shell 不支持当前 TCP 探测命令的输出"""
        if not output:
            return False
        unsupported_markers = [
            "can't create /dev/tcp/",
            "no such file or directory",
            "not found",
            "not executable",
            "permission denied",
        ]
        if "/dev/tcp/" in output and "connection refused" not in output and "timed out" not in output:
            return True
        return any(marker in output for marker in unsupported_markers)

    def clear_http_proxy(self) -> bool:
        """清除 Android 全局 HTTP 代理"""
        if not self.connected:
            logger.error("设备未连接")
            return False

        success_a, _ = self._run_adb_command(['shell', 'settings', 'put', 'global', 'http_proxy', ':0'])
        success_b, _ = self._run_adb_command(['shell', 'settings', 'delete', 'global', 'http_proxy'])
        success = success_a or success_b
        if success:
            logger.info("Android HTTP 代理已清除")
        return success
