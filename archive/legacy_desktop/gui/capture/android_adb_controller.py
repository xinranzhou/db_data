#!/usr/bin/env python3

from pathlib import Path

from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

from config.app_settings import AppSettings
from core.adb_device import ADBDevice
from utils.logger import logger


class AndroidAdbController:
    def __init__(self, editor):
        self.editor = editor

    def collect_adb_settings_from_form(self):
        current_adb = self.editor.app_settings.get("adb", {})
        resolved = ADBDevice.resolve_adb_path(current_adb.get("adb_path"))
        return {
            "adb_path": resolved or current_adb.get("adb_path", ""),
            "remote_address": self.editor.remote_address_entry.text().strip(),
            "pair_address": self.editor.pair_address_entry.text().strip(),
            "proxy_backup": current_adb.get("proxy_backup", ""),
            "last_applied_proxy": current_adb.get("last_applied_proxy", ""),
        }

    def get_configured_adb_path(self):
        return self.editor.app_settings.get("adb", {}).get("adb_path", "")

    def get_saved_proxy_backup(self) -> str:
        return self.editor.app_settings.get("adb", {}).get("proxy_backup", "")

    def has_saved_proxy_backup(self) -> bool:
        adb_settings = self.editor.app_settings.get("adb", {})
        return bool(adb_settings.get("last_applied_proxy", ""))

    def save_proxy_backup(self, proxy_value: str, last_applied_proxy: str = None):
        self.editor.app_settings.setdefault("adb", {})
        self.editor.app_settings["adb"]["proxy_backup"] = proxy_value or ""
        if last_applied_proxy is not None:
            self.editor.app_settings["adb"]["last_applied_proxy"] = last_applied_proxy or ""
        AppSettings.save(self.editor.app_settings)

    def clear_proxy_backup(self):
        self.editor.app_settings.setdefault("adb", {})
        self.editor.app_settings["adb"]["proxy_backup"] = ""
        self.editor.app_settings["adb"]["last_applied_proxy"] = ""
        AppSettings.save(self.editor.app_settings)

    def refresh_adb_tool_status(self):
        ok, resolved = ADBDevice.is_adb_available(self.get_configured_adb_path())
        if ok:
            display_path = Path(resolved)
            self.editor.adb_tool_label.setText(f"ADB: {display_path.name}")
            self.editor.adb_tool_label.setToolTip(resolved)
            self.editor.adb_tool_label.setStyleSheet("color: #15803D; font-weight: 600;")
            self.editor.app_settings.setdefault("adb", {})
            self.editor.app_settings["adb"]["adb_path"] = resolved
        else:
            self.editor.adb_tool_label.setText("ADB: 未安装")
            self.editor.adb_tool_label.setToolTip("未检测到 adb，可点击“安装ADB”自动下载")
            self.editor.adb_tool_label.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.refresh_local_network_hint()
        self.refresh_adb_summary()

    def refresh_local_network_hint(self):
        local_ips = ADBDevice.list_local_ipv4_addresses()
        if local_ips:
            summary = " / ".join(local_ips[:3])
            self.editor.adb_network_label.setText(f"电脑局域网IP: {summary}，请确保手机与电脑处于同一网段")
        else:
            self.editor.adb_network_label.setText("电脑局域网IP: 未识别，请确认已连接局域网")

    def refresh_adb_summary(self):
        if not hasattr(self.editor, "adb_summary_label"):
            return

        if not self.editor._capture_platform_supports_android():
            self.editor.adb_summary_label.setText("当前为 iOS 手动抓包模式。这里的 ADB 连接和代理按钮不会参与 iPhone 抓包。")
            return

        adb_ok, _ = ADBDevice.is_adb_available(self.get_configured_adb_path())
        if not adb_ok:
            self.editor.adb_summary_label.setText("当前未检测到 ADB。先点击“安装ADB”，再连接 Android 设备。")
            return

        if self.editor.adb_device and self.editor.adb_device.connected:
            self.editor.adb_summary_label.setText("设备已连接。若要抓包，下一步去“抓包配置”完成代理与证书步骤。")
            return

        self.editor.adb_summary_label.setText("先连接 Android 设备，再到“抓包配置”按 3 步完成代理与证书设置。")

    def ensure_adb_available(self, prompt_download: bool = True):
        ok, resolved = ADBDevice.is_adb_available(self.get_configured_adb_path())
        if ok:
            self.editor.app_settings.setdefault("adb", {})
            self.editor.app_settings["adb"]["adb_path"] = resolved
            self.refresh_adb_tool_status()
            return True

        self.refresh_adb_tool_status()
        if not prompt_download:
            return False

        reply = QMessageBox.question(
            self.editor,
            "未检测到ADB",
            "系统未检测到 adb，是否现在自动下载 Android platform-tools？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False
        return self.download_adb_tools(silent=False)

    def download_adb_tools(self, silent: bool = False):
        self.editor.statusBar().showMessage("正在下载 ADB 工具，请稍候...", 0)
        QApplication.processEvents()
        success, message, adb_path = ADBDevice.download_platform_tools()
        self.editor.statusBar().clearMessage()

        if success:
            self.editor.app_settings.setdefault("adb", {})
            self.editor.app_settings["adb"]["adb_path"] = adb_path or ""
            AppSettings.save(self.editor.app_settings)
            self.refresh_adb_tool_status()
            if not silent:
                QMessageBox.information(self.editor, "ADB", message)
            return True

        self.refresh_adb_tool_status()
        if not silent:
            QMessageBox.warning(self.editor, "ADB", message)
        return False

    def connect_remote_device(self):
        address = self.editor.remote_address_entry.text().strip()
        if not address:
            QMessageBox.warning(self.editor, "ADB", "请输入设备地址，例如 192.168.1.2:5555")
            return
        if not self.ensure_adb_available(prompt_download=True):
            return

        self.editor.app_settings.setdefault("adb", {})
        self.editor.app_settings["adb"]["remote_address"] = address
        AppSettings.save(self.editor.app_settings)

        success, output = ADBDevice.connect_remote(address, adb_path=self.get_configured_adb_path())
        if not success:
            QMessageBox.warning(self.editor, "ADB", output or "无线连接失败")
            return

        self.refresh_devices(select_device_id=address)
        QMessageBox.information(self.editor, "ADB", output or f"已连接设备: {address}")

    def pair_remote_device(self):
        pair_address = self.editor.pair_address_entry.text().strip()
        pairing_code = self.editor.pair_code_entry.text().strip()
        if not self.ensure_adb_available(prompt_download=True):
            return

        self.editor.app_settings.setdefault("adb", {})
        self.editor.app_settings["adb"]["pair_address"] = pair_address
        AppSettings.save(self.editor.app_settings)

        success, output = ADBDevice.pair_remote(
            pair_address,
            pairing_code,
            adb_path=self.get_configured_adb_path(),
        )
        if not success:
            QMessageBox.warning(self.editor, "ADB 配对", output or "无线配对失败")
            return

        host = pair_address.split(":", 1)[0] if ":" in pair_address else pair_address
        if host and not self.editor.remote_address_entry.text().strip():
            self.editor.remote_address_entry.setText(f"{host}:5555")
        self.editor.pair_code_entry.clear()
        QMessageBox.information(
            self.editor,
            "ADB 配对",
            (output or "无线配对成功") + "\n\n下一步请在手机无线调试页面查看“IP地址和端口”，填到上方调试地址后点“无线连接”。",
        )

    def disconnect_remote_device(self):
        if not self.ensure_adb_available(prompt_download=False):
            QMessageBox.warning(self.editor, "ADB", "未检测到 adb，请先安装")
            return

        address = self.editor.remote_address_entry.text().strip()
        if not address:
            address, ok = QInputDialog.getText(self.editor, "断开无线ADB", "设备地址（留空则全部断开）:")
            if not ok:
                return
            address = address.strip()

        success, output = ADBDevice.disconnect_remote(address or None, adb_path=self.get_configured_adb_path())
        self.refresh_devices()
        if success:
            QMessageBox.information(self.editor, "ADB", output or "已断开无线 ADB")
        else:
            QMessageBox.warning(self.editor, "ADB", output or "断开无线 ADB 失败")

    def refresh_devices(self, select_device_id: str = None):
        if not self.ensure_adb_available(prompt_download=True):
            return

        self.editor.device_combo.clear()
        devices = ADBDevice.list_devices(self.get_configured_adb_path())
        if not devices:
            QMessageBox.warning(self.editor, "警告", "未找到设备\n\n请确保:\n1. 手机已通过USB连接，或先执行无线连接\n2. 已开启USB调试\n3. 设备已授权此电脑")
            return

        selected_index = 0
        for device in devices:
            status = "✓" if device["status"] == "device" else "✗"
            self.editor.device_combo.addItem(f"{status} {device['id']}", device["id"])
            if select_device_id and device["id"] == select_device_id:
                selected_index = self.editor.device_combo.count() - 1

        self.editor.device_combo.setCurrentIndex(selected_index)
        logger.info(f"找到 {len(devices)} 个设备")

    def connect_device(self):
        if not self.ensure_adb_available(prompt_download=True):
            return
        if self.editor.device_combo.count() == 0:
            QMessageBox.warning(self.editor, "警告", "请先刷新设备列表")
            return

        device_id = self.editor.device_combo.currentData()
        try:
            self.editor.adb_device = ADBDevice(device_id, adb_path=self.get_configured_adb_path())
            if self.editor.adb_device.connect():
                info = self.editor.adb_device.get_device_info()
                status_text = (
                    f"已连接手机: {info.get('model', 'Unknown')} "
                    f"({info.get('screen_width', 0)}x{info.get('screen_height', 0)})"
                )
                self.editor.status_label.setText(status_text)
                self.editor.status_label.setStyleSheet("color: #15803D; font-weight: 700;")
                self.editor.btn_start.setEnabled(True)
                self.editor._refresh_device_proxy_status()
                QMessageBox.information(
                    self.editor,
                    "连接成功",
                    f"设备信息:\n"
                    f"型号: {info.get('model', 'Unknown')}\n"
                    f"Android版本: {info.get('android_version', 'Unknown')}\n"
                    f"屏幕尺寸: {info.get('screen_width', 0)}x{info.get('screen_height', 0)}",
                )
                if self.editor._should_prompt_apply_proxy():
                    reply = QMessageBox.question(
                        self.editor,
                        "应用 Android 代理",
                        "检测到抓取服务已配置，是否现在一键将当前代理应用到已连接手机？",
                        QMessageBox.Yes | QMessageBox.No,
                    )
                    if reply == QMessageBox.Yes:
                        self.editor._apply_android_proxy_settings()
                self.editor._refresh_capture_status()
            else:
                self.editor.status_label.setText("连接手机失败")
                self.editor.status_label.setStyleSheet("color: #B91C1C;")
                self.editor._refresh_device_proxy_status()
                QMessageBox.critical(self.editor, "错误", "连接设备失败")
        except Exception as exc:
            logger.error(f"连接设备异常: {exc}")
            self.editor.status_label.setText("连接手机异常")
            self.editor.status_label.setStyleSheet("color: #B91C1C;")
            self.editor._refresh_device_proxy_status()
            QMessageBox.critical(self.editor, "错误", f"连接设备异常: {exc}")
