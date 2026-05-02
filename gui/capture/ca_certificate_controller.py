#!/usr/bin/env python3

import io

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QMessageBox

from .platform_state import CapturePlatformState


class CaptureCertificateController:
    def __init__(self, editor, qrcode_module=None):
        self.editor = editor
        self.qrcode = qrcode_module

    def refresh_capture_status(self):
        capture = self.editor.app_settings.get("capture", {})
        state = CapturePlatformState.from_value(self.editor._get_capture_platform())
        host, port = self.editor.capture_manager.get_proxy_address(capture)
        if host:
            self.editor.capture_proxy_summary_label.setText(f"代理地址: {host}:{port}")
            self.editor.capture_ca_url_label.setText(f"CA 下载地址: {self.editor.capture_manager.get_ca_install_url(capture)}")
        else:
            self.editor.capture_proxy_summary_label.setText("代理地址: 未识别本机局域网IP")
            self.editor.capture_ca_url_label.setText("CA 下载地址: 未识别本机局域网IP")

        ca_paths = self.editor.capture_manager.get_ca_paths()
        ca_path = ca_paths["pem"]
        if ca_path.exists():
            self.editor.capture_ca_path_label.setText(f"CA 路径: {ca_path}")
        else:
            self.editor.capture_ca_path_label.setText("CA 路径: 尚未生成，启动 mitmproxy 后会自动创建")

        capture_status = "运行中" if self.editor.capture_manager.is_running() else "未启动"
        ca_status = "运行中" if self.editor.capture_manager.asset_server and self.editor.capture_manager.asset_server.is_running() else "未启动"
        if hasattr(self.editor, "capture_status_label"):
            self.editor.capture_status_label.setText(f"抓取状态: {capture_status} / CA服务: {ca_status}")
        if hasattr(self.editor, "capture_service_step_status"):
            self.editor.capture_service_step_status.setText(capture_status)
        if hasattr(self.editor, "capture_ca_step_status"):
            self.editor.capture_ca_step_status.setText("已就绪" if ca_path.exists() else "未就绪")
        if hasattr(self.editor, "capture_overview_label"):
            if host:
                if state.is_ios:
                    self.editor.capture_overview_label.setText(
                        f"当前代理地址 {host}:{port}。iOS 手动模式：在 iPhone 手动配置 Wi‑Fi 代理，再安装并完全信任 CA。"
                    )
                elif state.is_both:
                    self.editor.capture_overview_label.setText(
                        f"当前代理地址 {host}:{port}。Android 可自动应用代理；iPhone 仍需手动配置 Wi‑Fi 代理并信任 CA。"
                    )
                else:
                    self.editor.capture_overview_label.setText(
                        f"当前代理地址 {host}:{port}。推荐顺序：启动抓取服务 -> 给手机应用代理 -> 安装并信任 CA。"
                    )
            else:
                if state.is_ios:
                    self.editor.capture_overview_label.setText("未识别本机局域网IP，当前不能给 iPhone 手动配置可用代理。请先确认电脑已连接到局域网。")
                else:
                    self.editor.capture_overview_label.setText("未识别本机局域网IP，当前不能直接给手机应用代理。请先确认电脑已连接到局域网。")

        self.editor._refresh_device_proxy_status()
        self.update_ca_qr()
        self.editor._refresh_capture_platform_ui()

    def update_ca_qr(self):
        if not hasattr(self.editor, "capture_qr_label"):
            return

        if self.qrcode is None:
            self.editor.capture_qr_label.setText("未安装 qrcode，无法显示二维码")
            self.editor.capture_qr_label.setPixmap(QPixmap())
            return

        host, _ = self.editor.capture_manager.get_proxy_address(self.editor.app_settings.get("capture", {}))
        if not host:
            self.editor.capture_qr_label.setText("未识别本机局域网IP，无法生成 CA 下载二维码")
            self.editor.capture_qr_label.setPixmap(QPixmap())
            return

        url = self.editor.capture_manager.get_ca_install_url(self.editor.app_settings.get("capture", {}))
        try:
            image = self.qrcode.make(url)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue(), "PNG")
            self.editor.capture_qr_label.setPixmap(pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.editor.capture_qr_label.setText("")
        except Exception:
            self.editor.capture_qr_label.setText(url)

    def start_ca_service(self):
        self.editor._save_settings_if_needed(silent=True)
        success, message = self.editor.capture_manager.start_asset_server(self.editor.app_settings.get("capture", {}))
        self.refresh_capture_status()
        if success:
            self.editor.statusBar().showMessage(message, 4000)
        else:
            QMessageBox.warning(self.editor, "CA 服务", message)

    def stop_ca_service(self):
        _, message = self.editor.capture_manager.stop_asset_server()
        self.refresh_capture_status()
        self.editor.statusBar().showMessage(message, 4000)

    def show_https_diagnosis(self):
        state = CapturePlatformState.from_value(self.editor._get_capture_platform())
        if state.is_ios:
            return self.editor.ios_capture_controller.show_capture_checklist()
        return self.editor.android_proxy_controller.show_android_https_diagnosis()
