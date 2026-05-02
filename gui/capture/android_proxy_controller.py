#!/usr/bin/env python3

from PyQt5.QtWidgets import QMessageBox


class AndroidProxyController:
    def __init__(self, editor):
        self.editor = editor

    def get_expected_android_proxy(self):
        capture = self.editor.app_settings.get("capture", {})
        host, port = self.editor.capture_manager.get_proxy_address(capture)
        if not host or not port or host == "127.0.0.1":
            return ""
        return f"{host}:{port}"

    def apply_android_proxy_settings(self, silent: bool = False):
        if not self.editor._capture_platform_supports_android():
            if not silent:
                self.editor.ios_capture_controller.show_ios_mode_apply_proxy_hint()
            return False
        capture = self.editor.app_settings.get("capture", {})
        if not self.editor.adb_device or not self.editor.adb_device.connected:
            if not silent:
                QMessageBox.warning(self.editor, "ADB", "请先连接 Android 设备")
            return False

        host, port = self.editor.capture_manager.get_proxy_address(capture)
        if not host or host == "127.0.0.1":
            if not silent:
                QMessageBox.warning(self.editor, "ADB", "未识别可供手机访问的电脑局域网IP，暂不能应用代理")
            return False
        expected_proxy = f"{host}:{port}"
        current_proxy = self.editor.adb_device.get_http_proxy()
        if current_proxy is None:
            if not silent:
                QMessageBox.warning(self.editor, "ADB", "读取手机当前代理失败，暂不覆盖原代理")
            return False
        if current_proxy != expected_proxy:
            self.editor.android_adb_controller.save_proxy_backup(current_proxy, last_applied_proxy=expected_proxy)
        elif not self.editor.android_adb_controller.get_saved_proxy_backup():
            self.editor.android_adb_controller.save_proxy_backup("", last_applied_proxy=expected_proxy)

        if hasattr(self.editor.adb_device, "set_http_proxy") and self.editor.adb_device.set_http_proxy(host, port):
            self.refresh_device_proxy_status()
            self.editor.statusBar().showMessage(f"已应用 Android 代理: {host}:{port}", 4000)
            return True

        if not silent:
            QMessageBox.warning(self.editor, "ADB", "设置 Android 代理失败")
        return False

    def clear_android_proxy_settings(self):
        if not self.editor._capture_platform_supports_android():
            self.editor.ios_capture_controller.show_ios_mode_clear_proxy_hint()
            return False
        if not self.editor.adb_device or not self.editor.adb_device.connected:
            QMessageBox.warning(self.editor, "ADB", "请先连接 Android 设备")
            return False

        if hasattr(self.editor.adb_device, "clear_http_proxy") and self.editor.adb_device.clear_http_proxy():
            self.refresh_device_proxy_status()
            self.editor.statusBar().showMessage("已清除 Android 代理", 4000)
            return True

        QMessageBox.warning(self.editor, "ADB", "清除 Android 代理失败")
        return False

    def emergency_clear_android_proxy(self):
        if not self.editor.adb_device or not self.editor.adb_device.connected:
            QMessageBox.warning(
                self.editor,
                "紧急清除手机代理",
                "请先连接 Android 设备。\n\n如果无线 ADB 已断开，请改用 USB 连接后再执行清除。",
            )
            return False

        reply = QMessageBox.question(
            self.editor,
            "紧急清除手机代理",
            "这会立即清除手机当前的全局 HTTP 代理。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False

        return self.clear_android_proxy_settings()

    def restore_previous_android_proxy(self):
        if not self.editor.adb_device or not self.editor.adb_device.connected:
            QMessageBox.warning(
                self.editor,
                "恢复原代理",
                "请先连接 Android 设备。\n\n如果无线 ADB 已断开，请改用 USB 连接后再执行恢复。",
            )
            return False

        if not self.editor.android_adb_controller.has_saved_proxy_backup():
            QMessageBox.information(self.editor, "恢复原代理", "当前没有可恢复的旧代理备份")
            return False
        backup_proxy = self.editor.android_adb_controller.get_saved_proxy_backup()

        if backup_proxy:
            host, port_text = backup_proxy.split(":", 1)
            try:
                port = int(port_text)
            except ValueError:
                QMessageBox.warning(self.editor, "恢复原代理", f"备份代理格式无效: {backup_proxy}")
                return False
            success = self.editor.adb_device.set_http_proxy(host, port)
        else:
            success = self.editor.adb_device.clear_http_proxy()

        if not success:
            QMessageBox.warning(self.editor, "恢复原代理", "恢复手机原代理失败")
            return False

        restored_text = backup_proxy or "无代理"
        self.editor.android_adb_controller.clear_proxy_backup()
        self.refresh_device_proxy_status()
        self.editor.statusBar().showMessage(f"已恢复手机原代理: {restored_text}", 4000)
        QMessageBox.information(self.editor, "恢复原代理", f"已恢复手机原代理:\n{restored_text}")
        return True

    def refresh_device_proxy_status(self):
        if not hasattr(self.editor, "proxy_status_label"):
            return

        if not self.editor._capture_platform_supports_android():
            self.editor.proxy_status_label.setText("代理: iOS 手动配置")
            self.editor.proxy_status_label.setStyleSheet("color: #475569; font-weight: 600;")
            if hasattr(self.editor, "capture_proxy_step_status"):
                self.editor.capture_proxy_step_status.setText("手动配置")
            if hasattr(self.editor, "capture_device_proxy_summary_label"):
                self.editor.capture_device_proxy_summary_label.setText("手机代理: iOS 手动配置")
            if hasattr(self.editor, "proxy_fix_button"):
                self.editor.proxy_fix_button.setVisible(False)
            if hasattr(self.editor, "proxy_restore_button"):
                self.editor.proxy_restore_button.setVisible(False)
            if hasattr(self.editor, "proxy_emergency_clear_button"):
                self.editor.proxy_emergency_clear_button.setVisible(False)
            self.editor._refresh_adb_summary()
            return

        if hasattr(self.editor, "proxy_emergency_clear_button"):
            self.editor.proxy_emergency_clear_button.setVisible(True)

        if not self.editor.adb_device or not self.editor.adb_device.connected:
            self.editor.proxy_status_label.setText("代理: 未连接设备")
            self.editor.proxy_status_label.setStyleSheet("color: #475569; font-weight: 600;")
            if hasattr(self.editor, "capture_proxy_step_status"):
                self.editor.capture_proxy_step_status.setText("未连接设备")
            if hasattr(self.editor, "capture_device_proxy_summary_label"):
                self.editor.capture_device_proxy_summary_label.setText("手机代理: 未检测")
            if hasattr(self.editor, "proxy_fix_button"):
                self.editor.proxy_fix_button.setVisible(False)
            if hasattr(self.editor, "proxy_restore_button"):
                self.editor.proxy_restore_button.setVisible(False)
            self.editor._refresh_adb_summary()
            return

        proxy_value = self.editor.adb_device.get_http_proxy()
        if proxy_value is None:
            self.editor.proxy_status_label.setText("代理: 检测失败")
            self.editor.proxy_status_label.setStyleSheet("color: #B91C1C; font-weight: 600;")
            if hasattr(self.editor, "capture_proxy_step_status"):
                self.editor.capture_proxy_step_status.setText("检测失败")
            if hasattr(self.editor, "capture_device_proxy_summary_label"):
                self.editor.capture_device_proxy_summary_label.setText("手机代理: 检测失败")
            if hasattr(self.editor, "proxy_fix_button"):
                self.editor.proxy_fix_button.setVisible(False)
            if hasattr(self.editor, "proxy_restore_button"):
                self.editor.proxy_restore_button.setVisible(self.editor.android_adb_controller.has_saved_proxy_backup())
            self.editor._refresh_adb_summary()
            return

        expected_proxy = self.get_expected_android_proxy()
        show_fix_button = False
        if proxy_value:
            if expected_proxy and proxy_value == expected_proxy:
                self.editor.proxy_status_label.setText(f"代理: 已应用当前代理 {proxy_value}")
                self.editor.proxy_status_label.setStyleSheet("color: #15803D; font-weight: 600;")
                if hasattr(self.editor, "capture_proxy_step_status"):
                    self.editor.capture_proxy_step_status.setText("已应用")
                if hasattr(self.editor, "capture_device_proxy_summary_label"):
                    self.editor.capture_device_proxy_summary_label.setText(f"手机代理: {proxy_value}")
            elif expected_proxy:
                self.editor.proxy_status_label.setText(f"代理: 已应用但不匹配 {proxy_value}")
                self.editor.proxy_status_label.setStyleSheet("color: #D97706; font-weight: 600;")
                if hasattr(self.editor, "capture_proxy_step_status"):
                    self.editor.capture_proxy_step_status.setText("待修正")
                if hasattr(self.editor, "capture_device_proxy_summary_label"):
                    self.editor.capture_device_proxy_summary_label.setText(f"手机代理: {proxy_value}")
                show_fix_button = True
            else:
                self.editor.proxy_status_label.setText(f"代理: 已应用 {proxy_value}")
                self.editor.proxy_status_label.setStyleSheet("color: #15803D; font-weight: 600;")
                if hasattr(self.editor, "capture_proxy_step_status"):
                    self.editor.capture_proxy_step_status.setText("已应用")
                if hasattr(self.editor, "capture_device_proxy_summary_label"):
                    self.editor.capture_device_proxy_summary_label.setText(f"手机代理: {proxy_value}")
        else:
            if expected_proxy:
                self.editor.proxy_status_label.setText("代理: 未应用当前抓包代理")
                self.editor.proxy_status_label.setStyleSheet("color: #64748B; font-weight: 600;")
                if hasattr(self.editor, "capture_proxy_step_status"):
                    self.editor.capture_proxy_step_status.setText("未应用")
                if hasattr(self.editor, "capture_device_proxy_summary_label"):
                    self.editor.capture_device_proxy_summary_label.setText("手机代理: 未应用")
                show_fix_button = True
            else:
                self.editor.proxy_status_label.setText("代理: 未应用")
                self.editor.proxy_status_label.setStyleSheet("color: #475569; font-weight: 600;")
                if hasattr(self.editor, "capture_proxy_step_status"):
                    self.editor.capture_proxy_step_status.setText("未应用")
                if hasattr(self.editor, "capture_device_proxy_summary_label"):
                    self.editor.capture_device_proxy_summary_label.setText("手机代理: 未应用")

        if hasattr(self.editor, "proxy_fix_button"):
            self.editor.proxy_fix_button.setVisible(show_fix_button)
            self.editor.proxy_fix_button.setEnabled(show_fix_button)
        if hasattr(self.editor, "proxy_restore_button"):
            self.editor.proxy_restore_button.setVisible(self.editor.android_adb_controller.has_saved_proxy_backup())
            self.editor.proxy_restore_button.setEnabled(self.editor.android_adb_controller.has_saved_proxy_backup())
        self.editor._refresh_adb_summary()

    def detect_android_proxy_settings(self):
        if not self.editor._capture_platform_supports_android():
            self.editor.ios_capture_controller.show_ios_mode_detect_proxy_hint()
            return False
        if not self.editor.adb_device or not self.editor.adb_device.connected:
            QMessageBox.warning(self.editor, "ADB", "请先连接 Android 设备")
            return False

        proxy_value = self.editor.adb_device.get_http_proxy()
        self.refresh_device_proxy_status()
        if proxy_value is None:
            QMessageBox.warning(self.editor, "ADB", "读取手机代理配置失败")
            return False

        expected_proxy = self.get_expected_android_proxy()
        if proxy_value:
            lines = [f"当前手机代理配置为:\n{proxy_value}"]
            if expected_proxy:
                if proxy_value == expected_proxy:
                    lines.append(f"\n与当前抓包代理一致:\n{expected_proxy}")
                else:
                    lines.append(f"\n与当前抓包代理不一致:\n{expected_proxy}")
            QMessageBox.information(self.editor, "ADB 代理", "".join(lines))
        else:
            if expected_proxy:
                QMessageBox.information(
                    self.editor,
                    "ADB 代理",
                    f"当前手机未设置全局 HTTP 代理\n\n当前抓包代理目标为:\n{expected_proxy}",
                )
            else:
                QMessageBox.information(self.editor, "ADB 代理", "当前手机未设置全局 HTTP 代理")
        return True

    def test_android_proxy_connectivity(self):
        if not self.editor._capture_platform_supports_android():
            return self.editor.ios_capture_controller.show_capture_checklist()
        if not self.editor.adb_device or not self.editor.adb_device.connected:
            QMessageBox.warning(self.editor, "代理连通性", "请先连接 Android 设备")
            return False

        capture = self.editor.app_settings.get("capture", {})
        host, port = self.editor.capture_manager.get_proxy_address(capture)
        asset_port = int(capture.get("asset_port", 8765) or 8765)
        if not host:
            QMessageBox.warning(self.editor, "代理连通性", "未识别本机局域网IP，暂无法测试手机到电脑的代理链路")
            return False

        ping_ok, ping_output = self.editor.adb_device.ping_host(host)
        proxy_probe_status, proxy_output = self.editor.adb_device.probe_tcp_port(host, port)
        ca_probe_status, ca_output = self.editor.adb_device.probe_tcp_port(host, asset_port)
        proxy_ok = proxy_probe_status == "reachable"
        ca_ok = ca_probe_status == "reachable"
        local_proxy_ok, local_proxy_output = self.editor.capture_manager.check_local_port(host, port)
        local_ca_ok, local_ca_output = self.editor.capture_manager.check_local_port(host, asset_port)

        def _format_probe_status(status: str) -> str:
            if status == "reachable":
                return "成功"
            if status == "unsupported":
                return "设备不支持该检测"
            if status == "disconnected":
                return "设备未连接"
            return "失败"

        result_lines = [
            f"电脑地址: {host}",
            f"代理端口: {port}",
            f"CA 端口: {asset_port}",
            "",
            f"主机连通: {'成功' if ping_ok else '失败'}",
            f"本机代理端口监听: {'成功' if local_proxy_ok else '失败'}",
            f"本机CA端口监听: {'成功' if local_ca_ok else '失败'}",
            f"手机侧代理端口探测: {_format_probe_status(proxy_probe_status)}",
            f"手机侧CA端口探测: {_format_probe_status(ca_probe_status)}",
            "",
        ]

        if not ping_ok:
            result_lines.extend([
                "判断:",
                "手机当前无法到达电脑。请先确认手机和电脑在同一局域网，且没有访客网络/局域网隔离。",
            ])
        elif not local_proxy_ok:
            result_lines.extend([
                "判断:",
                f"本机 {port} 端口没有真正监听成功。优先检查抓取服务是否启动失败，或被其他进程占用了端口。",
            ])
        elif not local_ca_ok:
            result_lines.extend([
                "判断:",
                f"本机 {asset_port} 端口没有真正监听成功。抓包代理可能已启动，但 CA 下载服务未正常启动。",
            ])
        elif proxy_probe_status == "unsupported" or ca_probe_status == "unsupported":
            result_lines.extend([
                "判断:",
                "本机服务已监听，但当前 Android shell 不支持 TCP 端口探测，不能再把这类输出当成端口不通。",
                "如果手机仍然无网络，优先检查 macOS 防火墙/安全软件，并在手机浏览器直接访问 CA 下载地址验证连通性。",
            ])
        elif not proxy_ok:
            result_lines.extend([
                "判断:",
                f"手机可以到达电脑，但代理端口不通。优先检查抓取服务是否真的启动成功、macOS 防火墙是否拦截了 {port} 端口。",
            ])
        elif not ca_ok:
            result_lines.extend([
                "判断:",
                f"代理端口可达，但 CA 下载端口不通。抓包服务可用，但手机无法直接下载证书，请检查 {asset_port} 端口或单独启动 CA 服务。",
            ])
        else:
            result_lines.extend([
                "判断:",
                "手机到电脑代理链路正常。如果此时 App 仍表现为无网络，优先怀疑 CA 未安装/未信任，或目标 App 做了证书锁定。",
            ])

        debug_lines = []
        if ping_output:
            debug_lines.append(f"ping 输出: {ping_output}")
        if local_proxy_output:
            debug_lines.append(f"本机代理端口输出: {local_proxy_output}")
        if local_ca_output:
            debug_lines.append(f"本机CA端口输出: {local_ca_output}")
        if proxy_output:
            debug_lines.append(f"手机侧代理端口输出: {proxy_output}")
        if ca_output:
            debug_lines.append(f"手机侧CA端口输出: {ca_output}")
        if debug_lines:
            result_lines.extend(["", "调试信息:"])
            result_lines.extend(debug_lines)

        QMessageBox.information(self.editor, "代理连通性", "\n".join(result_lines))
        return ping_ok and local_proxy_ok

    def show_android_https_diagnosis(self):
        capture = self.editor.app_settings.get("capture", {})
        host, port = self.editor.capture_manager.get_proxy_address(capture)
        ca_url = self.editor.capture_manager.get_ca_install_url(capture) if host else "未识别本机局域网IP"
        ca_paths = self.editor.capture_manager.get_ca_paths()
        local_ca_ready = ca_paths["pem"].exists()
        proxy_value = self.editor.adb_device.get_http_proxy() if self.editor.adb_device and self.editor.adb_device.connected else None
        expected_proxy = self.get_expected_android_proxy()
        android_version = "-"
        if self.editor.adb_device and self.editor.adb_device.connected:
            device_info = self.editor.adb_device.get_device_info()
            android_version = device_info.get("android_version", "-")

        lines = [
            "Android HTTPS 抓包判断顺序:",
            "",
            f"1. 电脑代理地址: {host}:{port}" if host else "1. 电脑代理地址: 未识别本机局域网IP",
            f"2. Android 版本: {android_version}",
            f"3. 本机 mitmproxy CA: {'已生成' if local_ca_ready else '未生成'}",
            f"4. 手机当前代理: {proxy_value or '未设置/未检测'}",
            f"5. 期望手机代理: {expected_proxy or '当前不建议应用'}",
            f"6. CA 下载地址: {ca_url}",
            "",
        ]

        if not host:
            lines.extend([
                "当前结论:",
                "电脑局域网IP未识别，手机无法正确使用当前代理。先修复网络环境，再谈证书问题。",
            ])
        elif proxy_value != expected_proxy:
            lines.extend([
                "当前结论:",
                "手机代理还没有正确指向当前抓包地址。先修复代理，再验证 HTTPS。",
            ])
        elif not local_ca_ready:
            lines.extend([
                "当前结论:",
                "电脑上还没有生成 mitmproxy CA。先启动抓取服务，再下载安装证书。",
            ])
        else:
            lines.extend([
                "当前结论:",
                "如果浏览器访问 HTTPS 正常，但目标 App 仍然无网络，基本就是 App 不信任用户 CA 或做了证书锁定。",
                "",
                "建议验证:",
                "1. 手机浏览器打开 CA 下载地址并安装 mitmproxy 证书",
                "2. 安装后先不要测 App，先用手机浏览器访问任意 HTTPS 网站",
                "3. 浏览器 HTTPS 正常，说明代理链路和证书基础安装大体没问题",
                "4. 浏览器正常而 App 不正常时，优先判断为证书锁定或 App 不信任用户 CA",
            ])

        lines.extend([
            "",
            "Android 说明:",
            "Android 7+ 起，很多 App 默认不信任用户手动安装的 CA 证书。",
            "所以即使系统浏览器 HTTPS 正常，目标 App 仍可能表现为无网络。",
            "这不是代理链路问题，而是 App 自身的证书校验策略。",
        ])

        if self.editor.adb_device and self.editor.adb_device.connected:
            lines.extend([
                "",
                "应急处理:",
                "如果切网络后手机一直像断网，可直接点顶部“紧急清除手机代理”。",
            ])

        QMessageBox.information(self.editor, "HTTPS 诊断", "\n".join(lines))
