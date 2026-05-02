#!/usr/bin/env python3

from PyQt5.QtWidgets import QMessageBox

from .platform_state import CapturePlatformState


class IOSCaptureController:
    def __init__(self, editor):
        self.editor = editor

    def platform_state(self) -> CapturePlatformState:
        return CapturePlatformState.from_value(self.editor._get_capture_platform())

    def apply_platform_ui(self):
        state = self.platform_state()

        if hasattr(self.editor, "capture_android_proxy_checkbox"):
            self.editor.capture_android_proxy_checkbox.setEnabled(not state.is_ios)

        if hasattr(self.editor, "capture_proxy_manual_hint_label"):
            self.editor.capture_proxy_manual_hint_label.setText(state.proxy_manual_hint_text)

        if hasattr(self.editor, "capture_overview_label"):
            capture = self.editor.app_settings.get("capture", {})
            host, port = self.editor.capture_manager.get_proxy_address(capture)
            if host:
                if state.is_ios:
                    text = f"当前代理地址 {host}:{port}。iOS 手动模式：在 iPhone 手动配置 Wi‑Fi 代理，再安装并完全信任 CA。"
                elif state.is_both:
                    text = f"当前代理地址 {host}:{port}。Android 可自动应用代理；iPhone 仍需手动配置 Wi‑Fi 代理并信任 CA。"
                else:
                    text = state.overview_text if "当前代理地址" not in state.overview_text else state.overview_text
            else:
                if state.is_ios:
                    text = "未识别本机局域网IP，当前不能给 iPhone 手动配置可用代理。请先确认电脑已连接到局域网。"
                else:
                    text = "未识别本机局域网IP，当前不能直接给手机应用代理。请先确认电脑已连接到局域网。"
            self.editor.capture_overview_label.setText(text)

        if hasattr(self.editor, "realtime_flow_hint_label"):
            self.editor.realtime_flow_hint_label.setText(state.realtime_hint_text)

        if hasattr(self.editor, "btn_https_diagnosis"):
            self.editor.btn_https_diagnosis.setText(state.https_button_text)

        if hasattr(self.editor, "btn_quick_android"):
            self.editor.btn_quick_android.setVisible(not state.is_ios)

        for attr in [
            "btn_apply_proxy_quick",
            "btn_clear_android_proxy",
            "btn_detect_android_proxy",
            "btn_test_proxy_connectivity",
        ]:
            if hasattr(self.editor, attr):
                getattr(self.editor, attr).setVisible(not state.is_ios)

    def show_ios_mode_apply_proxy_hint(self):
        QMessageBox.information(
            self.editor,
            "iOS 手动抓包",
            "当前为 iOS 手动抓包模式，不支持自动应用代理。\n\n请在 iPhone 的 Wi‑Fi 详情页手动填写当前代理地址。",
        )

    def show_ios_mode_clear_proxy_hint(self):
        QMessageBox.information(
            self.editor,
            "iOS 手动抓包",
            "当前为 iOS 手动抓包模式，没有可由系统自动清除的手机代理。\n\n请在 iPhone 的 Wi‑Fi 详情页手动关闭代理。",
        )

    def show_ios_mode_detect_proxy_hint(self):
        QMessageBox.information(
            self.editor,
            "iOS 手动抓包",
            "当前为 iOS 手动抓包模式，系统无法读取 iPhone 当前代理。\n\n请在 iPhone 的 Wi‑Fi 设置里手动核对代理地址是否与当前抓包地址一致。",
        )

    def show_capture_checklist(self):
        capture = self.editor.app_settings.get("capture", {})
        host, port = self.editor.capture_manager.get_proxy_address(capture)
        ca_url = self.editor.capture_manager.get_ca_install_url(capture) if host else "未识别本机局域网IP"
        ca_paths = self.editor.capture_manager.get_ca_paths()
        local_ca_ready = ca_paths["pem"].exists()
        local_proxy_ok = False
        local_ca_ok = False
        local_proxy_output = ""
        local_ca_output = ""
        asset_port = int(capture.get("asset_port", 8765) or 8765)
        if host:
            local_proxy_ok, local_proxy_output = self.editor.capture_manager.check_local_port(host, port)
            local_ca_ok, local_ca_output = self.editor.capture_manager.check_local_port(host, asset_port)

        lines = [
            "iOS 手动抓包检查清单:",
            "",
            f"1. 电脑代理地址: {host}:{port}" if host else "1. 电脑代理地址: 未识别本机局域网IP",
            f"2. 本机代理端口监听: {'成功' if local_proxy_ok else '失败'}",
            f"3. 本机 CA 端口监听: {'成功' if local_ca_ok else '失败'}",
            f"4. 本机 mitmproxy CA: {'已生成' if local_ca_ready else '未生成'}",
            f"5. CA 下载地址: {ca_url}",
            "",
            "iPhone 手动操作顺序:",
            "1. 确认 iPhone 与电脑在同一局域网",
            "2. 打开 Wi‑Fi 详情页，手动填写 HTTP 代理为当前电脑地址和端口",
            "3. 用 Safari 打开 CA 下载地址，安装证书描述文件",
            "4. 在 设置 -> 通用 -> 关于本机 -> 证书信任设置 中手动开启完全信任",
            "5. 先用 Safari 访问任意 HTTPS 页面验证联网正常",
            "6. 再打开目标页面/小程序，回到“抓取实时数据”页开始收集数据",
            "",
            "结果判断:",
        ]

        if not host:
            lines.append("电脑局域网IP未识别，当前无法为 iPhone 配置有效代理。")
        elif not local_proxy_ok:
            lines.append(f"本机 {port} 端口没有真正监听成功，先修复抓包服务。")
        elif not local_ca_ok:
            lines.append(f"本机 {asset_port} 端口没有真正监听成功，iPhone 无法直接下载安装证书。")
        elif not local_ca_ready:
            lines.append("本机 mitmproxy CA 尚未生成，先启动抓取服务。")
        else:
            lines.append("如果 Safari HTTPS 正常但目标页面仍无数据，优先检查目标 App/小程序自身的证书校验策略。")

        debug_lines = []
        if local_proxy_output:
            debug_lines.append(f"本机代理端口输出: {local_proxy_output}")
        if local_ca_output:
            debug_lines.append(f"本机CA端口输出: {local_ca_output}")
        if debug_lines:
            lines.extend(["", "调试信息:"])
            lines.extend(debug_lines)

        QMessageBox.information(self.editor, "iOS 抓包检查", "\n".join(lines))
        return local_proxy_ok and local_ca_ok
