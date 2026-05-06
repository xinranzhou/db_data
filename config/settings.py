#!/usr/bin/env python3
"""
全局配置管理
"""

import os
import sys
from pathlib import Path


APP_NAME = "DP采集器"
SOURCE_DIR = Path(__file__).resolve().parent.parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", str(SOURCE_DIR))).resolve()


def _resolve_runtime_dir() -> Path:
    if not getattr(sys, "frozen", False):
        return SOURCE_DIR

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


RUNTIME_DIR = _resolve_runtime_dir()

class Settings:
    """全局配置类"""

    APP_NAME = APP_NAME

    # 资源路径
    SOURCE_DIR = SOURCE_DIR
    RESOURCE_DIR = RESOURCE_DIR
    BASE_DIR = RUNTIME_DIR
    TEMPLATE_DIR = RESOURCE_DIR / "templates"
    IMAGE_DIR = RESOURCE_DIR / "images"
    CONFIG_DIR = RESOURCE_DIR / "config"
    MEITUAN_CONFIG_DIR = CONFIG_DIR / "meituan"
    DATA_DIR = BASE_DIR / "data"
    TOOLS_DIR = BASE_DIR / "tools"
    BUNDLED_TOOLS_DIR = RESOURCE_DIR / "tools"
    PLATFORM_TOOLS_DIR = TOOLS_DIR / "platform-tools"
    LOG_DIR = BASE_DIR / "logs"

    # 确保目录存在
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_ASSET_DIR = DATA_DIR / "capture_assets"
    CAPTURE_ASSET_DIR.mkdir(parents=True, exist_ok=True)

    # 配置文件路径
    NODES_CONFIG = CONFIG_DIR / "nodes.json"
    REGIONS_CONFIG = CONFIG_DIR / "regions.json"
    CACHE_FILE = CONFIG_DIR / "cache.json"
    APP_SETTINGS_FILE = CONFIG_DIR / "app_settings.json"
    CAPTURE_DB_FILE = DATA_DIR / "captures.db"
    CAPTURE_INBOX_FILE = DATA_DIR / "capture_inbox.jsonl"
    CAPTURE_OFFSET_FILE = DATA_DIR / "capture_inbox.offset"
    CAPTURE_RUNTIME_FILE = DATA_DIR / "capture_runtime.json"
    PLAYRIGHT_DIR = DATA_DIR / "playright"
    PLAYRIGHT_RUNS_DIR = PLAYRIGHT_DIR / "runs"
    PLAYRIGHT_BROWSER_PROFILE_DIR = PLAYRIGHT_DIR / "browser_profile"
    PLAYWRIGHT_BROWSERS_DIR = BUNDLED_TOOLS_DIR / "playwright-browsers"
    AUTH_API_BASE_URL_DEV = os.getenv("AUTH_API_BASE_URL_DEV", "http://admin.aowu100.com/member/api")
    AUTH_API_BASE_URL_PROD = os.getenv("AUTH_API_BASE_URL_PROD", "http://admin.aowu100.com/member/api")
    AUTH_TOKEN_TTL_MS = int(os.getenv("AUTH_TOKEN_TTL_MS", str(7 * 24 * 60 * 60 * 1000)))

    PLAYRIGHT_DIR.mkdir(parents=True, exist_ok=True)
    PLAYRIGHT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    PLAYRIGHT_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLED_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    PLAYWRIGHT_BROWSERS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_local_adb_path(cls) -> Path:
        """获取项目内置 ADB 路径"""
        executable = "adb.exe" if __import__("os").name == "nt" else "adb"
        bundled_path = cls.BUNDLED_TOOLS_DIR / "platform-tools" / executable
        if bundled_path.exists():
            return bundled_path
        return cls.PLATFORM_TOOLS_DIR / executable

    @classmethod
    def get_bundled_mitmdump_path(cls) -> Path:
        executable = "mitmdump-helper.exe" if os.name == "nt" else "mitmdump-helper"
        candidates = cls.get_bundled_mitmdump_candidates(executable)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    @classmethod
    def get_bundled_capture_addon_path(cls) -> Path:
        candidates = cls.get_bundled_capture_addon_candidates()
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    @classmethod
    def get_bundled_mitmdump_candidates(cls, executable: str | None = None) -> list[Path]:
        filename = executable or ("mitmdump-helper.exe" if os.name == "nt" else "mitmdump-helper")
        return [
            cls.RESOURCE_DIR / "tools" / "bin" / filename,
            cls.RESOURCE_DIR.parent / "Resources" / "tools" / "bin" / filename,
            cls.RESOURCE_DIR.parent / "Frameworks" / "tools" / "bin" / filename,
        ]

    @classmethod
    def get_bundled_capture_addon_candidates(cls) -> list[Path]:
        return [
            cls.RESOURCE_DIR / "integration" / "mitm_capture_addon.py",
            cls.RESOURCE_DIR.parent / "Resources" / "integration" / "mitm_capture_addon.py",
            cls.RESOURCE_DIR.parent / "Frameworks" / "integration" / "mitm_capture_addon.py",
        ]


    # 匹配阈值
    THRESHOLDS = {
        'default': 0.7,
        'strict': 0.85,
        'loose': 0.6,
    }

    # 延迟配置（秒）
    DELAYS = {
        'click_min': 0.1,
        'click_max': 0.3,
        'page_load': 1.0,
        'filter_apply': 0.8,
        'scroll_interval': 0.5,
    }

    # 重试配置
    RETRY = {
        'max_attempts': 3,
        'backoff_factor': 1.5,
        'initial_wait': 1.0,
    }

    # 随机化配置
    RANDOMIZATION = {
        'click_offset_range': 5,  # 像素
        'delay_variance': 0.2,     # 20%变化
    }

    # 屏幕配置（iPhone 12 Pro）
    SCREEN = {
        'width': 1170,
        'height': 2532,
        'device_scale': 2.0,  # Retina屏幕缩放
    }

    # 滚动配置
    SCROLL = {
        'distance': 500,  # 滚动距离（像素）
        'duration': 0.5,  # 滚动时长（秒）
        'max_scrolls': 100,  # 最大滚动次数
    }

    # Rust集成配置
    RUST = {
        'command': './rust_collector',
        'data_dir': './data',
        'timeout': 300,  # 5分钟超时
    }

    @classmethod
    def get_template_path(cls, template_name: str) -> Path:
        """获取模板文件路径"""
        return cls.TEMPLATE_DIR / template_name

    @classmethod
    def get_image_path(cls, image_name: str) -> Path:
        """获取图片文件路径"""
        return cls.IMAGE_DIR / image_name
