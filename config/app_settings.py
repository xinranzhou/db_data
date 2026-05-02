#!/usr/bin/env python3
"""
应用级设置读写
"""

import json
import time
from copy import deepcopy

from config.settings import Settings


DEFAULT_APP_SETTINGS = {
    "account": {
        "display_name": "未登录",
        "account_id": "",
        "workspace": "默认工作区",
    },
    "auth": {
        "token": "",
        "expires_at": 0,
        "timestamp": "",
        "admin": {},
        "device_id": "",
    },
    "capture": {
        "enabled": False,
        "tool": "mitmproxy",
        "listen_host": "0.0.0.0",
        "listen_port": 8081,
        "asset_port": 8765,
        "patterns_text": "",
        "platform": "android",
        "android_proxy_auto_apply": False,
        "ios_proxy_manual": True,
        "max_body_kb": 512,
        "export_default_name": "captures.xlsx",
    },
    "data_capture": {
        "selected_platform": "meituan",
        "selected_interface_key": "all",
        "structured_export_name": "dianping_shop.xlsx",
    },
    "adb": {
        "adb_path": "",
        "remote_address": "",
        "pair_address": "",
        "proxy_backup": "",
        "last_applied_proxy": "",
    },
}


class AppSettings:
    """应用设置管理"""

    @classmethod
    def load(cls):
        settings = deepcopy(DEFAULT_APP_SETTINGS)
        path = Settings.APP_SETTINGS_FILE

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as file:
                    raw = json.load(file)
                cls._deep_merge(settings, raw)
            except Exception:
                # 配置损坏时回落到默认值
                pass

        return settings

    @classmethod
    def save(cls, settings: dict):
        path = Settings.APP_SETTINGS_FILE
        with open(path, "w", encoding="utf-8") as file:
            json.dump(settings, file, indent=2, ensure_ascii=False)

    @classmethod
    def update_section(cls, section: str, data: dict):
        settings = cls.load()
        settings.setdefault(section, {})
        settings[section].update(data)
        cls.save(settings)
        return settings

    @classmethod
    def save_auth_response(cls, response: dict):
        settings = cls.load()
        data = response.get("data", {}) if isinstance(response, dict) else {}
        admin = data.get("admin", {}) if isinstance(data, dict) else {}
        auth = settings.get("auth", {})
        existing_device_id = auth.get("device_id", "") if isinstance(auth, dict) else ""
        expires_at = (
            data.get("expires_at")
            or data.get("token_expires_at")
            or data.get("expiresAt")
            or 0
        )
        try:
            expires_at = int(expires_at or 0)
        except (TypeError, ValueError):
            expires_at = 0

        settings["auth"] = {
            "token": data.get("token", ""),
            "expires_at": expires_at,
            "timestamp": response.get("timestamp", ""),
            "admin": admin,
            "device_id": data.get("device_id", "") or existing_device_id,
        }
        settings["account"] = {
            "display_name": admin.get("nickname") or admin.get("username") or "未登录",
            "account_id": admin.get("id", ""),
            "workspace": settings.get("account", {}).get("workspace", "默认工作区"),
        }
        cls.save(settings)
        return settings

    @classmethod
    def clear_auth(cls):
        settings = cls.load()
        existing_device_id = settings.get("auth", {}).get("device_id", "")
        settings["auth"] = deepcopy(DEFAULT_APP_SETTINGS["auth"])
        settings["auth"]["device_id"] = existing_device_id
        settings["account"] = deepcopy(DEFAULT_APP_SETTINGS["account"])
        cls.save(settings)
        return settings

    @staticmethod
    def is_auth_valid(settings: dict = None) -> bool:
        current = settings or AppSettings.load()
        auth = current.get("auth", {})
        token = auth.get("token")
        expires_at = auth.get("expires_at") or 0
        try:
            expires_at = int(expires_at)
        except (TypeError, ValueError):
            expires_at = 0
        return bool(token) and expires_at > int(time.time() * 1000)

    @staticmethod
    def _deep_merge(target: dict, source: dict):
        for key, value in (source or {}).items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                AppSettings._deep_merge(target[key], value)
            else:
                target[key] = value
