#!/usr/bin/env python3

from dataclasses import dataclass


@dataclass(frozen=True)
class CapturePlatformState:
    value: str

    @classmethod
    def from_value(cls, value: str):
        normalized = (value or "android").strip().lower()
        if normalized not in {"android", "ios", "both"}:
            normalized = "android"
        return cls(value=normalized)

    @property
    def is_android(self) -> bool:
        return self.value == "android"

    @property
    def is_ios(self) -> bool:
        return self.value == "ios"

    @property
    def is_both(self) -> bool:
        return self.value == "both"

    @property
    def supports_android_proxy_actions(self) -> bool:
        return self.value in {"android", "both"}

    @property
    def supports_ios_manual_flow(self) -> bool:
        return self.value in {"ios", "both"}

    @property
    def overview_text(self) -> str:
        if self.is_ios:
            return "当前为 iOS 手动抓包模式：启动抓取服务 -> 在 iPhone 手动配置 Wi‑Fi 代理 -> 安装并信任 CA。"
        if self.is_both:
            return "当前为双平台模式：Android 可自动应用代理，iPhone 需手动配置 Wi‑Fi 代理并信任 CA。"
        return "推荐顺序：启动抓取服务 -> 给手机应用代理 -> 安装并信任 CA。"

    @property
    def realtime_hint_text(self) -> str:
        if self.is_ios:
            return "iOS 模式推荐流程：在 iPhone 手动打开目标页面/小程序 -> 回到这里开始收集数据 -> 录入抓取数据 -> 去“数据管理”维护结果。"
        if self.is_both:
            return "双平台模式推荐流程：在目标设备触发请求 -> 开始收集数据 -> 录入抓取数据 -> 去“数据管理”维护结果。"
        return "推荐流程：开始收集数据 -> 录入抓取数据 -> 去“数据管理”筛选和维护最终结果。"

    @property
    def proxy_manual_hint_text(self) -> str:
        if self.is_ios:
            return "iPhone / iPad 仅支持手动配置：请在 Wi‑Fi 详情页手动填写 HTTP 代理，再安装并在系统里完全信任证书。系统不会自动改写 iOS 代理。"
        if self.is_both:
            return "Android 可直接下发代理；iPhone / iPad 仍需手动配置 Wi‑Fi 代理和证书。"
        return "Android 设备连接成功后，可直接应用、检测和清除当前抓包代理。"

    @property
    def https_button_text(self) -> str:
        return "iOS 抓包检查" if self.is_ios else "HTTPS 诊断"
