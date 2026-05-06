#!/usr/bin/env python3
"""
mitmproxy 抓取插件
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path


def _resolve_runtime_path() -> Path:
    configured = os.getenv("DP_CAPTURE_RUNTIME_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "data" / "capture_runtime.json"


RUNTIME_PATH = _resolve_runtime_path()


def _default_runtime():
    inbox_default = RUNTIME_PATH.parent / "capture_inbox.jsonl"
    return {
        "patterns": [],
        "inbox_path": str(inbox_default),
        "platform": "ios",
        "max_body_kb": 512,
    }


def _load_runtime():
    if not RUNTIME_PATH.exists():
        return _default_runtime()

    with open(RUNTIME_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


class MatchRecorder:
    def __init__(self):
        self._runtime_mtime = None
        self._startup_logged = False
        self.reload_runtime()

    def reload_runtime(self):
        if RUNTIME_PATH.exists():
            try:
                self._runtime_mtime = RUNTIME_PATH.stat().st_mtime
            except Exception:
                self._runtime_mtime = None
        runtime = _load_runtime()
        self.patterns = []
        for pattern in runtime.get("patterns", []):
            try:
                self.patterns.append(re.compile(pattern))
            except re.error:
                continue
        self.inbox_path = Path(runtime.get("inbox_path") or (_default_runtime()["inbox_path"]))
        self.inbox_path.parent.mkdir(parents=True, exist_ok=True)
        self.platform = runtime.get("platform", "ios")
        self.max_body_bytes = int(runtime.get("max_body_kb", 512) or 512) * 1024
        if not self._startup_logged:
            print(
                "[capture-addon] runtime_path=%s inbox_path=%s platform=%s patterns=%s"
                % (RUNTIME_PATH, self.inbox_path, self.platform, len(self.patterns)),
                flush=True,
            )
            self._startup_logged = True

    def refresh_runtime_if_needed(self):
        try:
            current_mtime = RUNTIME_PATH.stat().st_mtime if RUNTIME_PATH.exists() else None
        except Exception:
            current_mtime = None

        if current_mtime != self._runtime_mtime:
            self.reload_runtime()

    def response(self, flow):
        self.refresh_runtime_if_needed()
        url = flow.request.pretty_url
        matched_pattern = "ALL"
        if self.patterns:
            matched_pattern = None
            for pattern in self.patterns:
                if pattern.search(url):
                    matched_pattern = pattern.pattern
                    break

            if not matched_pattern:
                return

        body = flow.response.get_text(strict=False) or ""
        if len(body.encode("utf-8")) > self.max_body_bytes:
            body = body[: self.max_body_bytes]

        payload = {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pattern": matched_pattern,
            "platform": self.platform,
            "method": flow.request.method,
            "status_code": flow.response.status_code,
            "host": flow.request.host,
            "path": flow.request.path,
            "url": url,
            "response_size": len((flow.response.content or b"")),
            "response_text": body,
            "headers": dict(flow.response.headers),
            "meta": {
                "request_headers": dict(flow.request.headers),
            },
        }

        with open(self.inbox_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


addons = [MatchRecorder()]
