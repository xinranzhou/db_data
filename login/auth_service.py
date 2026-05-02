#!/usr/bin/env python3
"""
认证服务。
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import uuid
from typing import Any
from urllib import error, request

from config.app_settings import AppSettings
from config.settings import Settings
from utils.logger import logger

AUTH_TIMEOUT_SECONDS = 10


def _is_packaged_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def is_mock_auth_enabled() -> bool:
    return _bool_from_env("AUTH_ENABLE_MOCK_LOGIN", not _is_packaged_runtime())


def get_auth_api_base_url() -> str:
    explicit = os.getenv("AUTH_API_BASE_URL")
    if explicit:
        return explicit.rstrip("/")

    if _is_packaged_runtime():
        base = os.getenv("AUTH_API_BASE_URL_PROD", Settings.AUTH_API_BASE_URL_PROD)
    else:
        base = os.getenv("AUTH_API_BASE_URL_DEV", Settings.AUTH_API_BASE_URL_DEV)
    return str(base or Settings.AUTH_API_BASE_URL_DEV).rstrip("/")


def _is_plain_record(value: Any) -> bool:
    return isinstance(value, dict)


def _read_response_body(exc_or_response) -> Any:
    try:
        raw_bytes = exc_or_response.read()
    except Exception:
        return None
    if not raw_bytes:
        return None
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return None


def _request_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, Any]:
    payload = None
    request_headers = dict(headers or {})
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = request.Request(url, data=payload, headers=request_headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=AUTH_TIMEOUT_SECONDS) as response:
            return int(getattr(response, "status", 200) or 200), _read_response_body(response)
    except error.HTTPError as exc:
        return int(getattr(exc, "code", 500) or 500), _read_response_body(exc)


def read_local_token() -> dict:
    settings = AppSettings.load()
    auth = settings.get("auth", {})
    return {
        "token": auth.get("token"),
        "token_expires_at": auth.get("expires_at"),
    }


def is_token_valid(params: dict) -> bool:
    token = params.get("token")
    if not token:
        return False

    raw_exp = params.get("token_expires_at")
    try:
        expires_at = int(raw_exp or 0)
    except (TypeError, ValueError):
        expires_at = 0
    return expires_at > 0 and expires_at > int(__import__("time").time() * 1000)


def get_or_create_device_id() -> str:
    settings = AppSettings.load()
    auth = settings.get("auth", {})
    existing = str(auth.get("device_id", "") or "").strip()
    if existing:
        return existing

    device_id = str(uuid.uuid4())
    auth["device_id"] = device_id
    settings["auth"] = auth
    AppSettings.save(settings)
    return device_id


def _pick_admin_from_auth_payload(payload: Any, fallback_username: str = "") -> dict:
    if not _is_plain_record(payload):
        return {"username": fallback_username} if fallback_username else {}

    raw_data = payload.get("data")
    if _is_plain_record(raw_data):
        if _is_plain_record(raw_data.get("admin")):
            return dict(raw_data.get("admin"))
        if _is_plain_record(raw_data.get("user")):
            user = dict(raw_data.get("user"))
            return {
                "id": user.get("id", ""),
                "username": user.get("username") or fallback_username,
                "nickname": user.get("nickname") or user.get("username") or fallback_username,
            }
        if isinstance(raw_data.get("username"), str):
            username = raw_data.get("username") or fallback_username
            return {
                "id": raw_data.get("id", ""),
                "username": username,
                "nickname": raw_data.get("nickname") or username,
            }

    top_user = payload.get("user")
    if _is_plain_record(top_user):
        user = dict(top_user)
        username = user.get("username") or fallback_username
        return {
            "id": user.get("id", ""),
            "username": username,
            "nickname": user.get("nickname") or username,
        }
    if fallback_username:
        return {"username": fallback_username, "nickname": fallback_username}
    return {}


def pick_token_from_auth_payload(payload: Any) -> dict:
    if not _is_plain_record(payload):
        return {"token": "", "ok": False, "message": "登录响应解析失败"}

    success = payload.get("success")
    if isinstance(success, bool):
        success_value = success
    elif isinstance(payload.get("code"), int):
        success_value = int(payload.get("code")) == 0
    else:
        success_value = True

    message = ""
    if isinstance(payload.get("message"), str):
        message = payload.get("message")
    elif isinstance(payload.get("msg"), str):
        message = payload.get("msg")

    raw_data = payload.get("data") if _is_plain_record(payload.get("data")) else None
    raw_data_record = raw_data or {}
    token = (
        (raw_data_record.get("token") if isinstance(raw_data_record.get("token"), str) else "")
        or (raw_data_record.get("accessToken") if isinstance(raw_data_record.get("accessToken"), str) else "")
        or (raw_data_record.get("access_token") if isinstance(raw_data_record.get("access_token"), str) else "")
        or (payload.get("token") if isinstance(payload.get("token"), str) else "")
        or (payload.get("accessToken") if isinstance(payload.get("accessToken"), str) else "")
        or (payload.get("access_token") if isinstance(payload.get("access_token"), str) else "")
    )

    expires_at_from_data = None
    if raw_data and isinstance(raw_data_record.get("token_expires_at"), (int, float)):
        expires_at_from_data = int(raw_data_record.get("token_expires_at"))
    elif raw_data and isinstance(raw_data_record.get("expires_at"), (int, float)):
        expires_at_from_data = int(raw_data_record.get("expires_at"))
    elif raw_data and isinstance(raw_data_record.get("expiresAt"), (int, float)):
        expires_at_from_data = int(raw_data_record.get("expiresAt"))
    elif isinstance(payload.get("expires_at"), (int, float)):
        expires_at_from_data = int(payload.get("expires_at"))

    expires_in_ms = None
    if raw_data and isinstance(raw_data_record.get("expires_in"), (int, float)):
        expires_in_ms = int(raw_data_record.get("expires_in")) * 1000
    elif raw_data and isinstance(raw_data_record.get("expiresIn"), (int, float)):
        expires_in_ms = int(raw_data_record.get("expiresIn")) * 1000

    token_expires_at = expires_at_from_data
    if token_expires_at is None and expires_in_ms:
        token_expires_at = int(__import__("time").time() * 1000) + expires_in_ms

    username = None
    raw_user = raw_data_record.get("user") if raw_data else None
    if raw_data and _is_plain_record(raw_user) and isinstance(raw_user.get("username"), str):
        username = raw_user.get("username")
    elif raw_data and isinstance(raw_data_record.get("username"), str):
        username = raw_data_record.get("username")
    elif _is_plain_record(payload.get("user")) and isinstance(payload.get("user").get("username"), str):
        username = payload.get("user").get("username")

    ok = bool(success_value and token)
    return {
        "token": token,
        "token_expires_at": token_expires_at,
        "username": username,
        "message": message,
        "ok": ok,
    }


def is_verify_invalid(params: dict) -> bool:
    status = int(params.get("status", 0) or 0)
    payload = params.get("payload")
    if status in {401, 403}:
        return True
    if not _is_plain_record(payload):
        return False
    if isinstance(payload.get("success"), bool):
        return payload.get("success") is False
    if isinstance(payload.get("code"), int):
        return int(payload.get("code")) != 0
    return False


def _save_login_response(payload: Any, fallback_username: str = "") -> dict:
    parsed = pick_token_from_auth_payload(payload)
    if not parsed.get("ok"):
        return parsed

    token_expires_at = parsed.get("token_expires_at")
    if not isinstance(token_expires_at, int):
        token_expires_at = int(__import__("time").time() * 1000) + Settings.AUTH_TOKEN_TTL_MS

    admin = _pick_admin_from_auth_payload(payload, fallback_username=fallback_username)
    if fallback_username and not admin.get("username"):
        admin["username"] = fallback_username
    if fallback_username and not admin.get("nickname"):
        admin["nickname"] = fallback_username

    normalized_response = {
        "success": True,
        "timestamp": payload.get("timestamp", "") if _is_plain_record(payload) else "",
        "data": {
            "token": parsed.get("token", ""),
            "expires_at": token_expires_at,
            "admin": admin,
        },
    }
    AppSettings.save_auth_response(normalized_response)
    return parsed


def mock_login(credentials: dict) -> dict:
    username = str(credentials.get("username", "") or "").strip()
    password = str(credentials.get("password", "") or "").strip()
    if username != "admin" or password != "admin":
        return {"success": False, "message": "账号或密码错误"}

    now_ms = int(__import__("time").time() * 1000)
    payload = {
        "success": True,
        "timestamp": "",
        "data": {
            "token": f"mock-token-{uuid.uuid4().hex}",
            "expires_at": now_ms + Settings.AUTH_TOKEN_TTL_MS,
            "admin": {
                "id": "930e3161-de3f-4cae-b815-9e7dc238995d",
                "username": username,
                "nickname": "Super Administrator",
            },
        },
    }
    _save_login_response(payload, fallback_username=username)
    return {"success": True, "data": {"token": payload["data"]["token"]}}


def login(credentials: dict) -> dict:
    username = str(credentials.get("username", "") or "").strip()
    password = str(credentials.get("password", "") or "").strip()

    if is_mock_auth_enabled() and username == "admin" and password == "admin":
        return mock_login(credentials)

    base_url = get_auth_api_base_url()
    device_id = get_or_create_device_id()
    device_name = f"{socket.gethostname()}-{platform.system().lower()}"
    post_data = {
        "name": username,
        "password": password,
        "deviceId": device_id,
        "deviceName": device_name,
    }

    try:
        status, raw = _request_json("POST", f"{base_url}/auth/login", body=post_data)
        parsed = pick_token_from_auth_payload(raw)
        if status >= 400 and not parsed.get("ok"):
            return {
                "success": False,
                "message": parsed.get("message") or f"登录失败（HTTP {status}）",
            }
        if not parsed.get("ok"):
            return {"success": False, "message": parsed.get("message") or "登录失败"}

        _save_login_response(raw, fallback_username=username)
        return {"success": True, "data": {"token": parsed.get("token", "")}}
    except Exception as exc:
        logger.exception("登录请求失败")
        return {"success": False, "message": str(exc) or "登录失败"}


def clear_session() -> dict:
    AppSettings.clear_auth()
    return {"success": True, "data": True}


def verify_auth() -> dict:
    local = read_local_token()
    if not is_token_valid(local):
        clear_session()
        return {"success": True, "data": {"valid": False}}

    token = str(local.get("token", "") or "").strip()
    if token.startswith("mock-token-") or token.startswith("mock_"):
        return {"success": True, "data": {"valid": True}}

    try:
        base_url = get_auth_api_base_url()
        status, raw = _request_json(
            "GET",
            f"{base_url}/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        if is_verify_invalid({"status": status, "payload": raw}):
            clear_session()
            return {"success": True, "data": {"valid": False}, "message": "登录已失效"}
        return {"success": True, "data": {"valid": True}}
    except Exception:
        logger.exception("登录态校验失败，按有效处理")
        return {"success": True, "data": {"valid": True}}


def get_stored_token() -> dict:
    try:
        result = verify_auth()
        if not result.get("success"):
            return {"success": True, "data": {"token": None}}
        if not result.get("data", {}).get("valid"):
            return {"success": True, "data": {"token": None}, "message": result.get("message")}
        local = read_local_token()
        return {
            "success": True,
            "data": {"token": local.get("token") if is_token_valid(local) else None},
        }
    except Exception:
        return {"success": True, "data": {"token": None}}
