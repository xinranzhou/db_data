#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.app_settings import AppSettings
from config.settings import Settings
from login import auth_service


class AuthServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.tmpdir.name) / "app_settings.json"
        self.settings_patcher = patch.object(Settings, "APP_SETTINGS_FILE", self.settings_path)
        self.settings_patcher.start()
        AppSettings.save(AppSettings.load())

    def tearDown(self):
        self.settings_patcher.stop()
        self.tmpdir.cleanup()

    def test_pick_token_from_auth_payload_supports_access_token_and_expires_in(self):
        payload = {
            "success": True,
            "data": {
                "access_token": "token-123",
                "expires_in": 60,
                "user": {"username": "alice"},
            },
        }

        parsed = auth_service.pick_token_from_auth_payload(payload)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["token"], "token-123")
        self.assertEqual(parsed["username"], "alice")
        self.assertIsInstance(parsed["token_expires_at"], int)

    def test_pick_token_from_auth_payload_handles_missing_data_without_crashing(self):
        payload = {
            "success": False,
            "message": "账号或密码错误",
            "data": None,
        }

        parsed = auth_service.pick_token_from_auth_payload(payload)

        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["token"], "")
        self.assertEqual(parsed["message"], "账号或密码错误")

    def test_login_persists_real_auth_response(self):
        payload = {
            "success": True,
            "timestamp": "2026-04-29T10:00:00.000Z",
            "data": {
                "token": "real-token",
                "expires_at": 1890000000000,
                "admin": {
                    "id": "admin-1",
                    "username": "alice",
                    "nickname": "Alice",
                },
            },
        }

        with patch.object(auth_service, "is_mock_auth_enabled", return_value=False), patch.object(
            auth_service, "_request_json", return_value=(200, payload)
        ):
            result = auth_service.login({"username": "alice", "password": "secret"})

        self.assertTrue(result["success"])
        settings = AppSettings.load()
        self.assertEqual(settings["auth"]["token"], "real-token")
        self.assertEqual(settings["auth"]["expires_at"], 1890000000000)
        self.assertEqual(settings["auth"]["admin"]["username"], "alice")
        self.assertTrue(settings["auth"]["device_id"])
        self.assertEqual(settings["account"]["display_name"], "Alice")

    def test_verify_auth_clears_invalid_session_and_preserves_device_id(self):
        settings = AppSettings.load()
        settings["auth"] = {
            "token": "real-token",
            "expires_at": 1890000000000,
            "timestamp": "",
            "admin": {"username": "alice"},
            "device_id": "device-123",
        }
        AppSettings.save(settings)

        with patch.object(auth_service, "_request_json", return_value=(401, {"success": False})):
            result = auth_service.verify_auth()

        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["valid"])
        cleared = AppSettings.load()
        self.assertEqual(cleared["auth"]["token"], "")
        self.assertEqual(cleared["auth"]["device_id"], "device-123")

    def test_get_stored_token_returns_none_after_expired_local_token(self):
        settings = AppSettings.load()
        settings["auth"] = {
            "token": "expired-token",
            "expires_at": 1,
            "timestamp": "",
            "admin": {"username": "alice"},
            "device_id": "device-123",
        }
        AppSettings.save(settings)

        result = auth_service.get_stored_token()

        self.assertTrue(result["success"])
        self.assertIsNone(result["data"]["token"])
        cleared = AppSettings.load()
        self.assertEqual(cleared["auth"]["token"], "")
        self.assertEqual(cleared["auth"]["device_id"], "device-123")


if __name__ == "__main__":
    unittest.main()
