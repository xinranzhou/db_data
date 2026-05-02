#!/usr/bin/env python3
"""
点评网页版详情补全。

支持两种模式：
1. mock：使用本地 HTML 假数据跑通补全链路
2. playwright：预留真实浏览器访问能力，后续安装 playwright 后可直接切换
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import random
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Protocol

from config.settings import Settings
from data.capture_store import CaptureStore
from utils.logger import logger

DATASET_CODE = "dianping_shop"
DEFAULT_EXPORT_COLUMNS = [
    "shop_id",
    "shop_uuid",
    "name",
    "region_name",
    "shop_type",
    "starScore",
    "district",
    "rating",
    "avg_price",
    "price_text",
    "category_name",
    "category",
    "phone",
    "address",
    "open_time",
    "shop_notice",
    "merchant_tags",
    "photo_count",
    "has_phone",
    "shop_url",
    "detail_fetch_status",
    "detail_fetch_time",
    "detail_error_message",
    "new_phone_flag",
    "contacted",
]
DONE_STATUSES = {"success", "no_phone", "not_found", "blocked"}
DEFAULT_MOCK_DATA_FILE = Path(__file__).parent / "mock_data" / "shops.json"
DEFAULT_MOCK_FIXTURES_DIR = Path(__file__).parent / "mock_pages"
PHONE_STATUS_HAS = "有"
PHONE_STATUS_NONE = "无"


@dataclass
class PageSnapshot:
    shop_uuid: str
    shop_url: str
    html: str = ""
    final_url: str = ""
    status_hint: str = ""
    error_message: str = ""


class DetailPageClient(Protocol):
    def fetch(self, record: dict) -> PageSnapshot:
        """拉取单个商家详情页。"""


class MockDetailPageClient:
    """从本地 HTML 夹具读取详情页。"""

    def __init__(self, fixtures_dir: Path):
        self.fixtures_dir = Path(fixtures_dir)

    def fetch(self, record: dict) -> PageSnapshot:
        shop_uuid = str(record.get("shop_uuid", "") or "").strip()
        shop_url = build_shop_url(shop_uuid)
        html_path = self.fixtures_dir / f"{shop_uuid}.html"

        if not shop_uuid:
            return PageSnapshot(
                shop_uuid="",
                shop_url="",
                status_hint="not_found",
                error_message="记录缺少 shop_uuid",
            )

        if not html_path.exists():
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=shop_url,
                status_hint="not_found",
                error_message=f"未找到 mock 页面: {html_path.name}",
            )

        return PageSnapshot(
            shop_uuid=shop_uuid,
            shop_url=shop_url,
            final_url=shop_url,
            html=html_path.read_text(encoding="utf-8"),
        )


class PlaywrightDetailPageClient:
    """真实浏览器访问器。当前 turn 主要用于后续接真实站点。"""

    LOGIN_SELECTOR = "a[href*='account.dianping.com/login']"
    LOGIN_FORM_SELECTORS = [
        "input[name='mobile']",
        "input[name='username']",
        "input[type='password']",
        ".login-form",
    ]
    LOGGED_IN_SELECTORS = [
        ".user-info",
        ".user-name",
        ".avatar",
        ".top-nav-user",
        "[data-click-name='user']",
    ]
    VERIFICATION_SELECTORS = [
        "iframe[src*='captcha']",
        "iframe[src*='verify']",
        ".yodaSlider",
        ".verify-slider",
        ".geetest_panel",
    ]
    APP_MODAL_CLOSE_SELECTOR = "#oapWide .oap-close, .oap-wide .oap-close"
    READY_SELECTORS = [
        ".desc-phone",
        "[data-test='phone']",
        "[data-test='address']",
        "[data-launch-name='telephone']",
        "h1",
    ]
    DETAIL_PAGE_MARKERS = [
        'data-launch-name="telephone"',
        'class="desc-phone',
        'data-test="phone"',
        'data-test="address"',
        'data-test="shop-name"',
        "地址",
        "电话",
        "营业时间",
    ]

    def __init__(
        self,
        user_data_dir: Path,
        headless: bool = False,
        timeout_ms: int = 15000,
        login_wait_ms: int = 180000,
        browser_path: Path | str | None = None,
        browser_channel: str = "auto",
    ):
        self.user_data_dir = Path(user_data_dir)
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.login_wait_ms = login_wait_ms
        self.browser_path = Path(browser_path).expanduser() if browser_path else None
        self.browser_channel = browser_channel
        self._playwright = None
        self._context = None
        self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def start(self):
        if self._context is not None:
            return

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "未安装 playwright，真实模式请先执行 `pip install playwright` "
                "并运行 `playwright install chromium`。"
            ) from exc

        self._playwright_timeout_error = PlaywrightTimeoutError
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        launch_options = {
            "user_data_dir": str(self.user_data_dir),
            "headless": self.headless,
        }
        launch_options.update(resolve_browser_launch_options(self.browser_path, self.browser_channel))
        self._context = self._playwright.chromium.launch_persistent_context(**launch_options)
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)

    def close(self):
        if self._page is not None:
            self._page.close()
            self._page = None
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def fetch(self, record: dict) -> PageSnapshot:
        self.start()
        shop_uuid = str(record.get("shop_uuid", "") or "").strip()
        shop_url = build_shop_url(shop_uuid)

        if not shop_uuid:
            return PageSnapshot(
                shop_uuid="",
                shop_url="",
                status_hint="not_found",
                error_message="记录缺少 shop_uuid",
            )

        try:
            self._page.goto(shop_url, wait_until="domcontentloaded")
            self._ensure_access_ready(shop_url)
            self._close_open_app_modal()
            self._wait_until_ready(shop_url)
            html = self._wait_for_detail_html(shop_url)
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=shop_url,
                final_url=self._page.url,
                html=html,
            )
        except self._playwright_timeout_error:
            html = self._safe_page_content()
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=shop_url,
                final_url=self._page.url if self._page else shop_url,
                html=html,
                status_hint="timeout",
                error_message="页面关键节点等待超时",
            )
        except Exception as exc:  # pragma: no cover - depends on browser runtime
            html = self._safe_page_content()
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=shop_url,
                final_url=self._page.url if self._page else shop_url,
                html=html,
                status_hint="blocked",
                error_message=str(exc),
            )

    def _ensure_access_ready(self, target_url: str):
        if not self._page:
            return

        deadline = time.time() + (self.login_wait_ms / 1000.0)
        verification_logged = False
        login_logged = False

        while time.time() < deadline:
            current_url = (self._page.url or "").lower()

            if self._is_verification_in_progress():
                if not verification_logged:
                    logger.info("检测到页面校验/拖动验证，等待人工处理完成后继续")
                    verification_logged = True
                self._page.wait_for_timeout(1000)
                continue

            if self._is_login_entry_visible():
                if not login_logged:
                    logger.warning("检测到点评网页版未登录，请在浏览器中手动登录")
                    try:
                        self._page.locator(self.LOGIN_SELECTOR).first.click()
                    except Exception:
                        pass
                    login_logged = True
                self._page.wait_for_timeout(1000)
                continue

            if self._is_login_pending():
                if not login_logged:
                    logger.info("等待登录流程完成并返回点评页面")
                    login_logged = True
                self._page.wait_for_timeout(1000)
                continue

            if self._is_logged_in() and self._is_dianping_page():
                if not self._is_target_shop_page(target_url):
                    logger.info("登录/校验完成，重新进入目标详情页")
                    self._page.goto(target_url, wait_until="domcontentloaded")
                return

            self._page.wait_for_timeout(1000)

        raise self._playwright_timeout_error("等待登录/校验完成并返回点评页面超时")

    def _is_login_entry_visible(self) -> bool:
        if not self._page:
            return False

        locator = self._page.locator(self.LOGIN_SELECTOR)
        try:
            return locator.count() > 0 and locator.first.is_visible()
        except Exception:
            return False

    def _is_verification_in_progress(self) -> bool:
        if not self._page:
            return False

        url = self._page.url.lower()
        if any(keyword in url for keyword in ["verify", "captcha", "challenge", "yoda"]):
            return True

        return self._has_visible_selector(self.VERIFICATION_SELECTORS)

    def _is_login_pending(self) -> bool:
        if not self._page:
            return False

        url = self._page.url.lower()
        if "account.dianping.com/login" in url or "login" in url:
            return True

        if self._has_visible_selector(self.LOGIN_FORM_SELECTORS):
            return True

        login_locator = self._page.locator(self.LOGIN_SELECTOR)
        try:
            return login_locator.count() > 0 and login_locator.first.is_visible()
        except Exception:
            return False

    def _is_logged_in(self) -> bool:
        if not self._page:
            return False

        if self._has_visible_selector(self.LOGGED_IN_SELECTORS):
            return True

        current_url = self._page.url.lower()
        if "account.dianping.com/login" in current_url:
            return False

        login_locator = self._page.locator(self.LOGIN_SELECTOR)
        try:
            if login_locator.count() > 0 and login_locator.first.is_visible():
                return False
        except Exception:
            pass

        return True

    def _is_dianping_page(self) -> bool:
        if not self._page:
            return False
        url = (self._page.url or "").lower()
        return "dianping.com" in url

    def _is_target_shop_page(self, target_url: str) -> bool:
        if not self._page:
            return False
        current_url = (self._page.url or "").lower()
        target = (target_url or "").lower()
        return current_url.startswith(target)

    def _has_visible_selector(self, selectors: list[str]) -> bool:
        if not self._page:
            return False

        for selector in selectors:
            try:
                locator = self._page.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    return True
            except Exception:
                continue
        return False

    def _close_open_app_modal(self):
        if not self._page:
            return

        modal_close = self._page.locator(self.APP_MODAL_CLOSE_SELECTOR)
        if modal_close.count() == 0:
            return

        try:
            if modal_close.first.is_visible():
                modal_close.first.click()
                self._page.wait_for_timeout(300)
        except Exception:
            logger.warning("打开 App 弹层关闭失败，继续检查页面状态")

    def _wait_until_ready(self, target_url: str):
        if not self._page:
            return

        self._wait_for_document_complete()

        for selector in self.READY_SELECTORS:
            try:
                self._page.locator(selector).first.wait_for(state="visible", timeout=3000)
                break
            except Exception:
                continue

        self._wait_for_document_complete()

        if not self._is_target_shop_page(target_url):
            raise self._playwright_timeout_error("页面未回到目标详情页")

    def _wait_for_document_complete(self):
        if not self._page:
            return

        try:
            self._page.wait_for_function("document.readyState === 'complete'", timeout=5000)
        except Exception:
            pass

        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    def _wait_for_detail_html(self, target_url: str) -> str:
        if not self._page:
            return ""

        deadline = time.time() + 15
        last_html = ""
        while time.time() < deadline:
            if self._is_verification_in_progress() or self._is_login_pending():
                self._ensure_access_ready(target_url)
                self._close_open_app_modal()
                self._wait_for_document_complete()

            if not self._is_target_shop_page(target_url):
                self._page.goto(target_url, wait_until="domcontentloaded")
                self._wait_for_document_complete()

            html = self._safe_page_content()
            if html:
                last_html = html

            if self._looks_like_detail_html(html):
                return html

            self._page.wait_for_timeout(1200)
            self._wait_for_document_complete()

        return last_html

    def _looks_like_detail_html(self, html: str) -> bool:
        if not html:
            return False

        lower_html = html.lower()
        if any(keyword in lower_html for keyword in ["pclogin", "verify.meituan.com", "captcha", "yoda"]):
            return False

        text_only = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text_only = re.sub(r"<style[\s\S]*?</style>", " ", text_only, flags=re.IGNORECASE)
        if any(marker.lower() in text_only.lower() for marker in self.DETAIL_PAGE_MARKERS):
            return True

        return False

    def _safe_page_content(self) -> str:
        if not self._page:
            return ""
        try:
            return self._page.content()
        except Exception:
            return ""

class DianpingDetailParser:
    """把 HTML 快照解析成结构化详情字段。"""

    BLOCKED_PATTERNS = [
        "验证中心",
        "滑动验证",
        "请完成人机验证",
        "访问异常",
        "captcha",
        "data-page-status=\"blocked\"",
    ]
    NOT_FOUND_PATTERNS = [
        "页面不存在",
        "商户不存在",
        "抱歉，页面无法访问",
        "data-page-status=\"not_found\"",
    ]
    APP_MODAL_PATTERNS = ["id=\"oapWide\"", "class=\"oap-wide\""]

    def parse(self, snapshot: PageSnapshot) -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html = snapshot.html or ""
        result = {
            "shop_uuid": snapshot.shop_uuid,
            "shop_url": snapshot.final_url or snapshot.shop_url,
            "detail_fetch_time": now,
            "raw_html_excerpt": self._excerpt(html),
        }

        status = snapshot.status_hint or self._detect_status(html)
        if status in {"blocked", "not_found", "timeout"}:
            result["detail_fetch_status"] = status
            result["detail_error_message"] = snapshot.error_message or self._default_error_message(status)
            result["has_phone"] = ""
            return result

        fields = self._extract_fields(html)
        result.update(fields)
        result["has_phone"] = PHONE_STATUS_HAS if bool(fields.get("phone")) or self._has_phone_entry(html) else PHONE_STATUS_NONE
        result["detail_fetch_status"] = "success" if result["has_phone"] == PHONE_STATUS_HAS else "no_phone"
        result["detail_error_message"] = snapshot.error_message or ""
        return result

    def _detect_status(self, html: str) -> str:
        text = html or ""
        if any(pattern in text for pattern in self.BLOCKED_PATTERNS):
            return "blocked"
        if any(pattern in text for pattern in self.NOT_FOUND_PATTERNS):
            return "not_found"
        return "success"

    @staticmethod
    def _has_phone_entry(html: str) -> bool:
        markers = [
            'data-launch-name="telephone"',
            'class="desc-phone',
            'data-test="phone"',
            "电话",
        ]
        lower_html = (html or "").lower()
        return any(marker.lower() in lower_html for marker in markers)

    def _extract_fields(self, html: str) -> dict:
        return {
            "name": self._extract_first(
                html,
                [
                    r'data-shop-name="([^"]+)"',
                    r'<h1[^>]*data-test="shop-name"[^>]*>(.*?)</h1>',
                    r'<h1[^>]*>(.*?)</h1>',
                ],
            ),
            "phone": self._extract_first(
                html,
                [
                    r'data-phone="([^"]+)"',
                    r'<[^>]*data-test="phone"[^>]*>(.*?)</[^>]+>',
                    r'联系电话[^<]*</span>\s*<span[^>]*>(.*?)</span>',
                    r'class="desc-phone[^"]*"[^>]*>(.*?)</div>',
                ],
            ),
            "address": self._extract_first(
                html,
                [
                    r'data-address="([^"]+)"',
                    r'<[^>]*data-test="address"[^>]*>(.*?)</[^>]+>',
                    r'地址[^<]*</span>\s*<span[^>]*>(.*?)</span>',
                ],
            ),
            "open_time": self._extract_first(
                html,
                [
                    r'data-open-time="([^"]+)"',
                    r'<[^>]*data-test="open-time"[^>]*>(.*?)</[^>]+>',
                    r'营业时间[^<]*</span>\s*<span[^>]*>(.*?)</span>',
                ],
            ),
            "category": self._extract_first(
                html,
                [
                    r'data-category="([^"]+)"',
                    r'<[^>]*data-test="category"[^>]*>(.*?)</[^>]+>',
                ],
            ),
            "district": self._extract_first(
                html,
                [
                    r'data-district="([^"]+)"',
                    r'<[^>]*data-test="district"[^>]*>(.*?)</[^>]+>',
                ],
            ),
            "shop_notice": self._extract_first(
                html,
                [
                    r'data-shop-notice="([^"]+)"',
                    r'<[^>]*data-test="shop-notice"[^>]*>(.*?)</[^>]+>',
                ],
            ),
            "merchant_tags": " | ".join(
                self._extract_all(
                    html,
                    [
                        r'<li[^>]*data-test="merchant-tag"[^>]*>(.*?)</li>',
                        r'<span[^>]*data-test="merchant-tag"[^>]*>(.*?)</span>',
                    ],
                )
            ),
            "photo_count": self._extract_int(
                html,
                [
                    r'data-photo-count="(\d+)"',
                    r'<[^>]*data-test="photo-count"[^>]*>(\d+)</[^>]+>',
                ],
            ),
        }

    def _extract_first(self, html: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            text = self._clean_text(match.group(1))
            if text:
                return text
        return ""

    def _extract_all(self, html: str, patterns: list[str]) -> list[str]:
        results = []
        seen = set()
        for pattern in patterns:
            for item in re.findall(pattern, html, re.IGNORECASE | re.DOTALL):
                text = self._clean_text(item)
                if text and text not in seen:
                    seen.add(text)
                    results.append(text)
        return results

    def _extract_int(self, html: str, patterns: list[str]) -> int | str:
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if match:
                return int(match.group(1))
        return ""

    @staticmethod
    def _clean_text(value: str) -> str:
        no_tags = re.sub(r"<[^>]+>", " ", value or "")
        normalized = re.sub(r"\s+", " ", unescape(no_tags)).strip()
        return normalized

    @staticmethod
    def _excerpt(html: str, limit: int = 500) -> str:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
        return text[:limit]

    @staticmethod
    def _default_error_message(status: str) -> str:
        mapping = {
            "blocked": "页面命中风控或验证",
            "not_found": "页面不存在或商家无效",
            "timeout": "页面关键节点加载超时",
        }
        return mapping.get(status, "页面访问失败")


class StructuredShopDataset:
    """负责种子数据写入、待处理记录筛选和结果回写。"""

    def __init__(self, store: CaptureStore, dataset_code: str = DATASET_CODE):
        self.store = store
        self.dataset_code = dataset_code

    def seed_records(self, records: list[dict]):
        inserted_or_updated = 0
        for record in records:
            record_key = self._resolve_record_key(record)
            if not record_key:
                logger.warning("跳过缺少唯一键的 mock 记录")
                continue

            payload = {
                "shop_id": str(record.get("shop_id", "") or "").strip(),
                "shop_uuid": str(record.get("shop_uuid", "") or "").strip(),
                "name": str(record.get("name", "") or "").strip(),
                "region_name": str(record.get("region_name", "") or "").strip(),
                "shop_type": record.get("shop_type", ""),
                "starScore": record.get("starScore", record.get("rating", "")),
                "district": str(record.get("district", "") or "").strip(),
                "rating": record.get("rating", ""),
                "avg_price": record.get("avg_price", ""),
                "price_text": str(record.get("price_text", "") or "").strip(),
                "category_name": str(record.get("category_name", "") or "").strip(),
                "phone": "",
                "has_phone": "",
                "new_phone_flag": 0,
                "contacted": 0,
            }
            self.store.upsert_structured_record(
                dataset_code=self.dataset_code,
                record_key=record_key,
                data=payload,
                parse_status="parsed",
                enrich_status="need_enrich",
                overwrite_existing=False,
                force_overwrite_keys=["shop_uuid"],
            )
            inserted_or_updated += 1
        return inserted_or_updated

    def list_pending_records(
        self,
        limit: int = 20,
        include_keys: set[str] | None = None,
        force_rerun: bool = False,
        only_without_phone: bool = False,
    ) -> list[dict]:
        rows = self.store.list_structured_records(dataset_code=self.dataset_code, limit=10000)
        rows = sorted(rows, key=lambda item: int(item.get("id", 0)))
        pending = []
        for row in rows:
            record_key = str(row.get("record_key", "") or "").strip()
            if include_keys is not None and record_key not in include_keys:
                continue

            data = row.get("data", {})
            if not str(data.get("shop_uuid", "") or "").strip():
                continue

            detail_status = str(data.get("detail_fetch_status", "") or "").strip()
            phone_status = normalize_phone_status(
                data.get("has_phone"),
                data.get("phone"),
                detail_status,
            )

            if only_without_phone and not force_rerun:
                if phone_status == PHONE_STATUS_HAS:
                    continue
            elif not force_rerun and detail_status in DONE_STATUSES:
                continue

            pending.append(row)
            if len(pending) >= limit:
                break
        return pending

    def save_detail_result(self, record_key: str, detail_data: dict):
        detail_status = str(detail_data.get("detail_fetch_status", "") or "").strip()
        enrich_status = "done" if detail_status in DONE_STATUSES else "need_enrich"
        existing_row = self.store.get_structured_record(self.dataset_code, record_key)
        existing_data = existing_row.get("data", {}) if existing_row else {}
        previous_phone_status = normalize_phone_status(
            existing_data.get("has_phone"),
            existing_data.get("phone"),
            existing_data.get("detail_fetch_status"),
        )

        normalized_data = dict(detail_data)

        if detail_status == "success":
            normalized_data["has_phone"] = PHONE_STATUS_HAS
        elif detail_status and detail_status != "success":
            normalized_data["has_phone"] = PHONE_STATUS_NONE
        else:
            normalized_data["has_phone"] = previous_phone_status
            if not normalized_data.get("phone"):
                normalized_data["phone"] = existing_data.get("phone", "")

        current_phone_status = normalize_phone_status(
            normalized_data.get("has_phone"),
            normalized_data.get("phone"),
            detail_status,
        )
        if current_phone_status == PHONE_STATUS_HAS and previous_phone_status == PHONE_STATUS_NONE:
            normalized_data["new_phone_flag"] = 1
        elif current_phone_status == PHONE_STATUS_HAS:
            normalized_data["new_phone_flag"] = normalize_bool_flag(existing_data.get("new_phone_flag"))
        else:
            normalized_data["new_phone_flag"] = 0
        normalized_data["contacted"] = normalize_bool_flag(existing_data.get("contacted"))

        self.store.upsert_structured_record(
            dataset_code=self.dataset_code,
            record_key=record_key,
            data=normalized_data,
            parse_status="parsed",
            enrich_status=enrich_status,
            overwrite_existing=False,
            force_overwrite_keys=[
                "shop_url",
                "detail_fetch_status",
                "detail_fetch_time",
                "has_phone",
                "phone",
                "new_phone_flag",
                "raw_html_excerpt",
                "detail_error_message",
            ],
        )

    def save_detail_result_for_row(self, row: dict, detail_data: dict):
        record_key = str(row.get("record_key", "") or "").strip()
        if not record_key:
            raise ValueError("待回写记录缺少 record_key")
        self.save_detail_result(record_key, detail_data)

    def export_excel(self, output_path: Path, columns: list[str] | None = None) -> str:
        return self.store.export_structured_excel(
            str(output_path),
            dataset_code=self.dataset_code,
            columns=columns or DEFAULT_EXPORT_COLUMNS,
        )

    @staticmethod
    def _resolve_record_key(record: dict) -> str:
        return str(record.get("shop_uuid") or record.get("shop_id") or "").strip()


class DianpingDetailEnricher:
    """串行执行详情补全。"""

    def __init__(self, dataset: StructuredShopDataset, client: DetailPageClient, parser: DianpingDetailParser | None = None):
        self.dataset = dataset
        self.client = client
        self.parser = parser or DianpingDetailParser()

    def run(
        self,
        limit: int = 20,
        stop_on_blocked: bool = True,
        sleep_range: tuple[float, float] = (0.0, 0.0),
        artifact_dir: Path | None = None,
        include_keys: set[str] | None = None,
        force_rerun: bool = False,
        only_without_phone: bool = False,
    ) -> dict:
        pending_rows = self.dataset.list_pending_records(
            limit=limit,
            include_keys=include_keys,
            force_rerun=force_rerun,
            only_without_phone=only_without_phone,
        )
        summary = {
            "processed": 0,
            "status_breakdown": {},
            "stopped_on_blocked": False,
            "results": [],
        }

        for row in pending_rows:
            record_key = row.get("record_key", "")
            record = row.get("data", {})
            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            snapshot = self.client.fetch(record)
            detail_data = self.parser.parse(snapshot)
            self.dataset.save_detail_result(record_key, detail_data)

            status = detail_data.get("detail_fetch_status", "unknown")
            summary["processed"] += 1
            summary["status_breakdown"][status] = summary["status_breakdown"].get(status, 0) + 1
            html_file = self._write_html_snapshot(artifact_dir, record_key, snapshot.html) if artifact_dir else ""
            result_item = {
                "record_key": record_key,
                "shop_uuid": record.get("shop_uuid", ""),
                "shop_url": detail_data.get("shop_url", snapshot.shop_url),
                "status": status,
                "started_at": started_at,
                "finished_at": detail_data.get("detail_fetch_time", ""),
                "error_message": detail_data.get("detail_error_message", ""),
                "html_file": html_file,
            }
            summary["results"].append(result_item)

            if status in {"blocked", "timeout", "not_found"}:
                logger.warning(
                    f"详情补全结果: key={record_key}, status={status}, error={result_item['error_message'] or '-'}"
                )
            else:
                logger.info(f"详情补全完成: key={record_key}, status={status}")

            if status == "blocked" and stop_on_blocked:
                summary["stopped_on_blocked"] = True
                logger.warning("命中 blocked，按策略停止当前批次")
                break

            self._sleep_between_requests(sleep_range)

        return summary

    def run_rows(
        self,
        rows: list[dict],
        stop_on_blocked: bool = True,
        sleep_range: tuple[float, float] = (0.0, 0.0),
        artifact_dir: Path | None = None,
    ) -> dict:
        summary = {
            "processed": 0,
            "status_breakdown": {},
            "stopped_on_blocked": False,
            "results": [],
        }

        for row in rows:
            record_key = row.get("record_key", "")
            record = row.get("data", {})
            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            snapshot = self.client.fetch(record)
            detail_data = self.parser.parse(snapshot)
            self.dataset.save_detail_result(record_key, detail_data)

            status = detail_data.get("detail_fetch_status", "unknown")
            summary["processed"] += 1
            summary["status_breakdown"][status] = summary["status_breakdown"].get(status, 0) + 1
            html_file = self._write_html_snapshot(artifact_dir, record_key, snapshot.html) if artifact_dir else ""
            result_item = {
                "record_key": record_key,
                "shop_uuid": record.get("shop_uuid", ""),
                "shop_url": detail_data.get("shop_url", snapshot.shop_url),
                "status": status,
                "started_at": started_at,
                "finished_at": detail_data.get("detail_fetch_time", ""),
                "error_message": detail_data.get("detail_error_message", ""),
                "html_file": html_file,
            }
            summary["results"].append(result_item)

            if status in {"blocked", "timeout", "not_found"}:
                logger.warning(
                    f"详情补全结果: key={record_key}, status={status}, error={result_item['error_message'] or '-'}"
                )
            else:
                logger.info(f"详情补全完成: key={record_key}, status={status}")

            if status == "blocked" and stop_on_blocked:
                summary["stopped_on_blocked"] = True
                logger.warning("命中 blocked，按策略停止当前批次")
                break

            self._sleep_between_requests(sleep_range)

        return summary

    @staticmethod
    def _sleep_between_requests(sleep_range: tuple[float, float]):
        min_sleep, max_sleep = sleep_range
        if max_sleep <= 0:
            return
        time.sleep(random.uniform(min_sleep, max_sleep))

    @staticmethod
    def _write_html_snapshot(artifact_dir: Path, record_key: str, html: str) -> str:
        html_dir = artifact_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        file_path = html_dir / f"{record_key}.html"
        file_path.write_text(html or "", encoding="utf-8")
        return str(file_path)


def build_shop_url(shop_uuid: str) -> str:
    return f"https://www.dianping.com/shop/{shop_uuid}"


def resolve_browser_launch_options(browser_path: Path | str | None = None, browser_channel: str = "auto") -> dict:
    if browser_path:
        resolved = Path(browser_path).expanduser()
        if not resolved.exists():
            raise RuntimeError(f"指定的浏览器路径不存在: {resolved}")
        logger.info(f"使用用户指定浏览器: {resolved}")
        return {"executable_path": str(resolved)}

    if browser_channel and browser_channel != "auto":
        logger.info(f"使用指定浏览器 channel: {browser_channel}")
        return {"channel": browser_channel}

    detected = detect_local_chromium_executable()
    if detected:
        logger.info(f"使用本机 Chromium 浏览器: {detected}")
        return {"executable_path": str(detected)}

    logger.warning("未探测到本机 Chrome/Chromium，将回退到 Playwright 默认 Chromium")
    return {}


def select_phone_fetch_rows(rows: list[dict], limit: int = 20, star_score_threshold: float = 0.0) -> list[dict]:
    selected = []
    seen = set()
    normalized_limit = max(1, int(limit or 1))
    normalized_threshold = float(star_score_threshold or 0.0)

    for row in rows:
        record_key = str(row.get("record_key", "") or "").strip()
        if not record_key or record_key in seen:
            continue

        data = row.get("data", {})
        phone_status = normalize_phone_status(
            data.get("has_phone"),
            data.get("phone"),
            data.get("detail_fetch_status"),
        )
        if phone_status == PHONE_STATUS_HAS:
            continue

        if normalized_threshold > 0:
            raw_star_score = data.get("starScore", data.get("rating", ""))
            try:
                parsed_star_score = float(raw_star_score)
            except Exception:
                continue
            if not parsed_star_score < normalized_threshold:
                continue

        selected.append(row)
        seen.add(record_key)
        if len(selected) >= normalized_limit:
            break

    return selected


class AsyncPlaywrightBatchRunner:
    def __init__(
        self,
        dataset: StructuredShopDataset,
        user_data_dir: Path,
        parser: DianpingDetailParser | None = None,
        headless: bool = False,
        timeout_ms: int = 15000,
        login_wait_ms: int = 180000,
        browser_path: Path | str | None = None,
        browser_channel: str = "auto",
    ):
        self.dataset = dataset
        self.user_data_dir = Path(user_data_dir)
        self.parser = parser or DianpingDetailParser()
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.login_wait_ms = login_wait_ms
        self.browser_path = browser_path
        self.browser_channel = browser_channel

    def run(
        self,
        rows: list[dict],
        concurrency: int = 1,
        stop_on_blocked: bool = False,
        sleep_range: tuple[float, float] = (2.0, 5.0),
        artifact_dir: Path | None = None,
        progress_callback=None,
    ) -> dict:
        return asyncio.run(
            self._run(
                rows=rows,
                concurrency=concurrency,
                stop_on_blocked=stop_on_blocked,
                sleep_range=sleep_range,
                artifact_dir=artifact_dir,
                progress_callback=progress_callback,
            )
        )

    async def _run(
        self,
        rows: list[dict],
        concurrency: int,
        stop_on_blocked: bool,
        sleep_range: tuple[float, float],
        artifact_dir: Path | None,
        progress_callback,
    ) -> dict:
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "未安装 playwright，真实模式请先执行 `pip install playwright` 并运行 `playwright install chromium`。"
            ) from exc

        if not rows:
            return {
                "processed": 0,
                "status_breakdown": {},
                "stopped_on_blocked": False,
                "results": [],
            }

        total = len(rows)
        normalized_concurrency = max(1, min(int(concurrency or 1), total))
        summary = {
            "processed": 0,
            "status_breakdown": {},
            "stopped_on_blocked": False,
            "results": [],
        }
        result_items = []
        result_lock = asyncio.Lock()
        stop_event = asyncio.Event()
        queue: asyncio.Queue = asyncio.Queue()
        for index, row in enumerate(rows):
            queue.put_nowait((index, row))

        async with async_playwright() as playwright:
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            launch_options = {
                "user_data_dir": str(self.user_data_dir),
                "headless": self.headless,
                **resolve_browser_launch_options(self.browser_path, self.browser_channel),
            }
            context = await playwright.chromium.launch_persistent_context(**launch_options)
            try:
                pages = [await context.new_page() for _ in range(normalized_concurrency)]
                for page in pages:
                    page.set_default_timeout(self.timeout_ms)

                first_row = rows[0]
                first_target_url = build_shop_url(str(first_row.get("data", {}).get("shop_uuid", "") or "").strip())
                await self._prepare_page_for_fetch(
                    pages[0],
                    first_target_url,
                    PlaywrightTimeoutError,
                )

                workers = [
                    asyncio.create_task(
                        self._page_worker(
                            page=page,
                            worker_index=worker_index,
                            queue=queue,
                            total=total,
                            summary=summary,
                            result_items=result_items,
                            result_lock=result_lock,
                            stop_event=stop_event,
                            stop_on_blocked=stop_on_blocked,
                            sleep_range=sleep_range,
                            artifact_dir=artifact_dir,
                            progress_callback=progress_callback,
                            timeout_error_cls=PlaywrightTimeoutError,
                        )
                    )
                    for worker_index, page in enumerate(pages, start=1)
                ]
                await asyncio.gather(*workers)
            finally:
                await context.close()

        summary["results"] = [item["result"] for item in sorted(result_items, key=lambda entry: entry["index"])]
        return summary

    async def _page_worker(
        self,
        page,
        worker_index: int,
        queue: asyncio.Queue,
        total: int,
        summary: dict,
        result_items: list,
        result_lock: asyncio.Lock,
        stop_event: asyncio.Event,
        stop_on_blocked: bool,
        sleep_range: tuple[float, float],
        artifact_dir: Path | None,
        progress_callback,
        timeout_error_cls,
    ):
        while True:
            if stop_event.is_set() and queue.empty():
                return

            try:
                index, row = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            if stop_event.is_set():
                queue.task_done()
                return

            record_key = str(row.get("record_key", "") or "").strip()
            record = row.get("data", {}) or {}
            shop_uuid = str(record.get("shop_uuid", "") or "").strip()
            target_url = build_shop_url(shop_uuid)
            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                snapshot = await self._fetch_with_page(page, record, target_url, timeout_error_cls)
            except Exception as exc:  # pragma: no cover - browser runtime dependent
                snapshot = PageSnapshot(
                    shop_uuid=shop_uuid,
                    shop_url=target_url,
                    final_url=target_url,
                    html="",
                    status_hint="blocked",
                    error_message=str(exc),
                )

            detail_data = self.parser.parse(snapshot)
            self.dataset.save_detail_result_for_row(row, detail_data)

            status = detail_data.get("detail_fetch_status", "unknown")
            html_file = DianpingDetailEnricher._write_html_snapshot(artifact_dir, record_key, snapshot.html) if artifact_dir else ""
            result_item = {
                "record_key": record_key,
                "shop_uuid": shop_uuid,
                "shop_url": detail_data.get("shop_url", snapshot.shop_url),
                "status": status,
                "started_at": started_at,
                "finished_at": detail_data.get("detail_fetch_time", ""),
                "error_message": detail_data.get("detail_error_message", ""),
                "html_file": html_file,
                "worker": worker_index,
            }

            async with result_lock:
                summary["processed"] += 1
                summary["status_breakdown"][status] = summary["status_breakdown"].get(status, 0) + 1
                result_items.append({"index": index, "result": result_item})
                processed = summary["processed"]
                if progress_callback:
                    progress_callback(
                        f"已完成 {processed}/{total} 家，当前 tab {worker_index} -> {shop_uuid or record_key} [{status}]"
                    )
                if status == "blocked" and stop_on_blocked:
                    summary["stopped_on_blocked"] = True
                    stop_event.set()

            if status in {"blocked", "timeout", "not_found"}:
                logger.warning(
                    f"详情补全结果: key={record_key}, tab={worker_index}, status={status}, error={result_item['error_message'] or '-'}"
                )
            else:
                logger.info(f"详情补全完成: key={record_key}, tab={worker_index}, status={status}")

            queue.task_done()
            await self._sleep_between_requests(sleep_range)

    async def _fetch_with_page(self, page, record: dict, target_url: str, timeout_error_cls):
        shop_uuid = str(record.get("shop_uuid", "") or "").strip()
        if not shop_uuid:
            return PageSnapshot(
                shop_uuid="",
                shop_url="",
                status_hint="not_found",
                error_message="记录缺少 shop_uuid",
            )

        try:
            await page.goto(target_url, wait_until="domcontentloaded")
            await self._ensure_access_ready(page, target_url, timeout_error_cls)
            await self._close_open_app_modal(page)
            await self._wait_until_ready(page, target_url, timeout_error_cls)
            html = await self._wait_for_detail_html(page, target_url, timeout_error_cls)
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=target_url,
                final_url=page.url,
                html=html,
            )
        except timeout_error_cls:
            html = await self._safe_page_content(page)
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=target_url,
                final_url=page.url if page else target_url,
                html=html,
                status_hint="timeout",
                error_message="页面关键节点等待超时",
            )
        except Exception as exc:  # pragma: no cover - depends on browser runtime
            html = await self._safe_page_content(page)
            return PageSnapshot(
                shop_uuid=shop_uuid,
                shop_url=target_url,
                final_url=page.url if page else target_url,
                html=html,
                status_hint="blocked",
                error_message=str(exc),
            )

    async def _prepare_page_for_fetch(self, page, target_url: str, timeout_error_cls):
        if not target_url:
            return
        await page.goto(target_url, wait_until="domcontentloaded")
        await self._ensure_access_ready(page, target_url, timeout_error_cls)
        await self._close_open_app_modal(page)
        await self._wait_until_ready(page, target_url, timeout_error_cls)

    async def _ensure_access_ready(self, page, target_url: str, timeout_error_cls):
        deadline = time.time() + (self.login_wait_ms / 1000.0)
        verification_logged = False
        login_logged = False

        while time.time() < deadline:
            current_url = (page.url or "").lower()

            if await self._is_verification_in_progress(page):
                if not verification_logged:
                    logger.info("检测到页面校验/拖动验证，等待人工处理完成后继续")
                    verification_logged = True
                await page.wait_for_timeout(1000)
                continue

            if await self._is_login_entry_visible(page):
                if not login_logged:
                    logger.warning("检测到点评网页版未登录，请在浏览器中手动登录")
                    try:
                        await page.locator(PlaywrightDetailPageClient.LOGIN_SELECTOR).first.click()
                    except Exception:
                        pass
                    login_logged = True
                await page.wait_for_timeout(1000)
                continue

            if await self._is_login_pending(page):
                if not login_logged:
                    logger.info("等待登录流程完成并返回点评页面")
                    login_logged = True
                await page.wait_for_timeout(1000)
                continue

            if await self._is_logged_in(page) and self._is_dianping_page_url(page.url):
                if not self._is_target_shop_page_url(page.url, target_url):
                    logger.info("登录/校验完成，重新进入目标详情页")
                    await page.goto(target_url, wait_until="domcontentloaded")
                return

            if "dianping.com" not in current_url and not current_url:
                await page.wait_for_timeout(1000)
                continue

            await page.wait_for_timeout(1000)

        raise timeout_error_cls("等待登录/校验完成并返回点评页面超时")

    async def _is_login_entry_visible(self, page) -> bool:
        locator = page.locator(PlaywrightDetailPageClient.LOGIN_SELECTOR)
        try:
            return await locator.count() > 0 and await locator.first.is_visible()
        except Exception:
            return False

    async def _is_verification_in_progress(self, page) -> bool:
        url = (page.url or "").lower()
        if any(keyword in url for keyword in ["verify", "captcha", "challenge", "yoda"]):
            return True
        return await self._has_visible_selector(page, PlaywrightDetailPageClient.VERIFICATION_SELECTORS)

    async def _is_login_pending(self, page) -> bool:
        url = (page.url or "").lower()
        if "account.dianping.com/login" in url or "login" in url:
            return True

        if await self._has_visible_selector(page, PlaywrightDetailPageClient.LOGIN_FORM_SELECTORS):
            return True

        locator = page.locator(PlaywrightDetailPageClient.LOGIN_SELECTOR)
        try:
            return await locator.count() > 0 and await locator.first.is_visible()
        except Exception:
            return False

    async def _is_logged_in(self, page) -> bool:
        if await self._has_visible_selector(page, PlaywrightDetailPageClient.LOGGED_IN_SELECTORS):
            return True

        current_url = (page.url or "").lower()
        if "account.dianping.com/login" in current_url:
            return False

        locator = page.locator(PlaywrightDetailPageClient.LOGIN_SELECTOR)
        try:
            if await locator.count() > 0 and await locator.first.is_visible():
                return False
        except Exception:
            pass

        return True

    async def _has_visible_selector(self, page, selectors: list[str]) -> bool:
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0 and await locator.first.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _close_open_app_modal(self, page):
        modal_close = page.locator(PlaywrightDetailPageClient.APP_MODAL_CLOSE_SELECTOR)
        try:
            if await modal_close.count() == 0:
                return
            if await modal_close.first.is_visible():
                await modal_close.first.click()
                await page.wait_for_timeout(300)
        except Exception:
            logger.warning("打开 App 弹层关闭失败，继续检查页面状态")

    async def _wait_until_ready(self, page, target_url: str, timeout_error_cls):
        await self._wait_for_document_complete(page)

        for selector in PlaywrightDetailPageClient.READY_SELECTORS:
            try:
                await page.locator(selector).first.wait_for(state="visible", timeout=3000)
                break
            except Exception:
                continue

        await self._wait_for_document_complete(page)

        if not self._is_target_shop_page_url(page.url, target_url):
            raise timeout_error_cls("页面未回到目标详情页")

    async def _wait_for_document_complete(self, page):
        try:
            await page.wait_for_function("document.readyState === 'complete'", timeout=5000)
        except Exception:
            pass

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    async def _wait_for_detail_html(self, page, target_url: str, timeout_error_cls) -> str:
        deadline = time.time() + 15
        last_html = ""
        while time.time() < deadline:
            if await self._is_verification_in_progress(page) or await self._is_login_pending(page):
                await self._ensure_access_ready(page, target_url, timeout_error_cls)
                await self._close_open_app_modal(page)
                await self._wait_for_document_complete(page)

            if not self._is_target_shop_page_url(page.url, target_url):
                await page.goto(target_url, wait_until="domcontentloaded")
                await self._wait_for_document_complete(page)

            html = await self._safe_page_content(page)
            if html:
                last_html = html

            if self._looks_like_detail_html(html):
                return html

            await page.wait_for_timeout(1200)
            await self._wait_for_document_complete(page)

        return last_html

    def _looks_like_detail_html(self, html: str) -> bool:
        if not html:
            return False

        lower_html = html.lower()
        if any(keyword in lower_html for keyword in ["pclogin", "verify.meituan.com", "captcha", "yoda"]):
            return False

        text_only = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text_only = re.sub(r"<style[\s\S]*?</style>", " ", text_only, flags=re.IGNORECASE)
        return any(marker.lower() in text_only.lower() for marker in PlaywrightDetailPageClient.DETAIL_PAGE_MARKERS)

    async def _safe_page_content(self, page) -> str:
        try:
            return await page.content()
        except Exception:
            return ""

    @staticmethod
    async def _sleep_between_requests(sleep_range: tuple[float, float]):
        min_sleep, max_sleep = sleep_range
        if max_sleep <= 0:
            return
        await asyncio.sleep(random.uniform(min_sleep, max_sleep))

    @staticmethod
    def _is_dianping_page_url(url: str) -> bool:
        return "dianping.com" in (url or "").lower()

    @staticmethod
    def _is_target_shop_page_url(current_url: str, target_url: str) -> bool:
        return (current_url or "").lower().startswith((target_url or "").lower())


def normalize_phone_status(has_phone, phone="", detail_status="") -> str:
    if str(phone or "").strip():
        return PHONE_STATUS_HAS

    if has_phone is True:
        return PHONE_STATUS_HAS
    if has_phone is False:
        return PHONE_STATUS_NONE

    text = str(has_phone or "").strip()
    if text in {PHONE_STATUS_HAS, "true", "True", "1"}:
        return PHONE_STATUS_HAS
    if text in {PHONE_STATUS_NONE, "false", "False"}:
        return PHONE_STATUS_NONE

    normalized_detail_status = str(detail_status or "").strip()
    if normalized_detail_status and normalized_detail_status != "success":
        return PHONE_STATUS_NONE
    return ""


def normalize_bool_flag(value) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value or "").strip().lower()
    return 1 if text in {"1", "true", "yes", "y", "有"} else 0


def detect_local_chromium_executable() -> Path | None:
    env_candidates = [
        os.environ.get("CHROME_PATH", ""),
        os.environ.get("CHROMIUM_PATH", ""),
    ]
    for candidate in env_candidates:
        resolved = _normalize_browser_candidate(candidate)
        if resolved:
            return resolved

    for name in [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ]:
        resolved = _normalize_browser_candidate(shutil.which(name))
        if resolved:
            return resolved

    system_name = platform.system().lower()
    for candidate in _browser_candidates_for_system(system_name):
        resolved = _normalize_browser_candidate(candidate)
        if resolved:
            return resolved

    return None


def _normalize_browser_candidate(candidate: str | Path | None) -> Path | None:
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    return path if path.exists() else None


def _browser_candidates_for_system(system_name: str) -> list[str]:
    if system_name == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            str(Path.home() / "Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]

    if system_name == "windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Users\Default\AppData\Local\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Chromium\Application\chrome.exe",
            r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
        ]
        for base_dir in [
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ]:
            if not base_dir:
                continue
            candidates.extend(
                [
                    str(Path(base_dir) / "Google/Chrome/Application/chrome.exe"),
                    str(Path(base_dir) / "Chromium/Application/chrome.exe"),
                ]
            )
        return candidates

    return [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
    ]


def load_mock_records(mock_data_path: Path | str = DEFAULT_MOCK_DATA_FILE) -> list[dict]:
    path = Path(mock_data_path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_shop_records_from_file(shop_list_file: Path | str) -> list[dict]:
    path = Path(shop_list_file)
    if not path.exists():
        raise FileNotFoundError(f"未找到 shop 列表文件: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("JSON 文件必须是数组")
        return _normalize_shop_records(payload)

    if suffix in {".txt", ".csv"}:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = []
        for line in lines:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            values.append(raw.split(",")[0].strip())
        return _normalize_shop_records(values)

    raise ValueError("仅支持 .json / .txt / .csv 格式的 shop 列表文件")


def _normalize_shop_records(items: list) -> list[dict]:
    normalized = []
    for item in items:
        if isinstance(item, str):
            shop_uuid = item.strip()
            if not shop_uuid:
                continue
            normalized.append(
                {
                    "shop_id": "",
                    "shop_uuid": shop_uuid,
                    "name": "",
                    "region_name": "",
                    "shop_type": "",
                    "starScore": "",
                    "district": "",
                    "rating": "",
                    "avg_price": "",
                    "price_text": "",
                    "category_name": "",
                }
            )
            continue

        if isinstance(item, dict):
            shop_uuid = str(item.get("shop_uuid", "") or "").strip()
            if not shop_uuid:
                raise ValueError("记录缺少 shop_uuid。网页版详情抓取必须提供 shop_uuid，不能只给 shop_id。")
            normalized.append(
                {
                    "shop_id": str(item.get("shop_id", "") or "").strip(),
                    "shop_uuid": shop_uuid,
                    "name": str(item.get("name", "") or "").strip(),
                    "region_name": str(item.get("region_name", "") or "").strip(),
                    "shop_type": item.get("shop_type", ""),
                    "starScore": item.get("starScore", item.get("rating", "")),
                    "district": str(item.get("district", "") or "").strip(),
                    "rating": item.get("rating", ""),
                    "avg_price": item.get("avg_price", ""),
                    "price_text": str(item.get("price_text", "") or "").strip(),
                    "category_name": str(item.get("category_name", "") or "").strip(),
                }
            )
            continue

        raise ValueError("shop 列表文件中的记录必须是字符串或对象")

    return normalized


def reset_database(db_path: Path):
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)


def run_mock_test(db_path: Path, export_path: Path, limit: int = 20) -> dict:
    reset_database(db_path)
    store = CaptureStore(db_path=db_path)
    dataset = StructuredShopDataset(store)
    seeded = dataset.seed_records(load_mock_records())
    client = MockDetailPageClient(DEFAULT_MOCK_FIXTURES_DIR)
    enricher = DianpingDetailEnricher(dataset, client)
    artifact_paths = build_run_output_paths(export_path.parent, run_label="mock_test")
    summary = enricher.run(limit=limit, stop_on_blocked=False, artifact_dir=artifact_paths["run_dir"])
    write_run_artifacts(artifact_paths, summary)
    exported_path = dataset.export_excel(export_path)
    summary["seeded"] = seeded
    summary["exported_path"] = exported_path
    summary["results_file"] = str(artifact_paths["results_jsonl"])
    summary["summary_file"] = str(artifact_paths["summary_json"])
    return summary


def build_run_output_paths(base_dir: Path, run_label: str | None = None) -> dict[str, Path]:
    label = run_label or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / "runs" / label
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "results_jsonl": run_dir / "results.jsonl",
        "summary_json": run_dir / "summary.json",
    }


def write_run_artifacts(paths: dict[str, Path], summary: dict):
    results = summary.get("results", [])
    with open(paths["results_jsonl"], "w", encoding="utf-8") as file:
        for item in results:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    payload = dict(summary)
    payload["results_file"] = str(paths["results_jsonl"])
    payload["run_dir"] = str(paths["run_dir"])
    paths["summary_json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_client(args) -> DetailPageClient:
    if args.mode == "mock":
        fixtures_dir = Path(args.fixtures_dir or DEFAULT_MOCK_FIXTURES_DIR)
        return MockDetailPageClient(fixtures_dir)

    user_data_dir = Path(args.user_data_dir or (Settings.DATA_DIR / "playright" / "browser_profile"))
    return PlaywrightDetailPageClient(
        user_data_dir=user_data_dir,
        headless=bool(args.headless),
        browser_path=args.browser_path or None,
        browser_channel=args.browser_channel,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="点评网页版详情补全")
    parser.add_argument("--mode", choices=["mock", "playwright"], default="mock")
    parser.add_argument("--mock-test", action="store_true", help="使用内置 mock 数据完整跑一遍")
    parser.add_argument("--seed-mock", action="store_true", help="把 mock 列表数据写入 SQLite")
    parser.add_argument("--run", action="store_true", help="执行详情补全")
    parser.add_argument("--export", action="store_true", help="导出结构化 Excel")
    parser.add_argument("--limit", type=int, default=20, help="本批最多处理多少条")
    parser.add_argument("--headless", action="store_true", help="真实模式下无头运行")
    parser.add_argument("--db-path", default="", help="SQLite 路径")
    parser.add_argument("--export-path", default="", help="导出 Excel 路径")
    parser.add_argument("--result-dir", default="", help="运行结果目录，默认输出到 data/playright/runs")
    parser.add_argument("--fixtures-dir", default="", help="mock HTML 目录")
    parser.add_argument("--mock-data", default="", help="mock 列表 JSON 路径")
    parser.add_argument("--shop-list-file", default="", help="待抓取 shop 列表文件，支持 .json/.txt/.csv")
    parser.add_argument("--user-data-dir", default="", help="playwright 用户目录")
    parser.add_argument("--browser-path", default="", help="显式指定本机 Chrome/Chromium 路径")
    parser.add_argument(
        "--browser-channel",
        choices=["auto", "chrome"],
        default="auto",
        help="浏览器 channel，默认自动优先本机浏览器",
    )
    parser.add_argument("--reset-db", action="store_true", help="运行前重置目标数据库")
    parser.add_argument("--stop-on-blocked", action="store_true", help="遇到 blocked 后停止批次")
    parser.add_argument("--force-rerun", action="store_true", help="忽略已完成状态，强制重跑 shop-list-file 中的记录")
    parser.add_argument("--sleep-min", type=float, default=2.0, help="店铺之间最小等待秒数")
    parser.add_argument("--sleep-max", type=float, default=5.0, help="店铺之间最大等待秒数")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    if args.mock_test:
        db_path = Path(args.db_path or (Settings.DATA_DIR / "playright" / "mock_test.db"))
        export_path = Path(args.export_path or (Settings.DATA_DIR / "playright" / "dianping_shop_mock.xlsx"))
        summary = run_mock_test(db_path=db_path, export_path=export_path, limit=args.limit)
        logger.info(f"mock 测试完成: {json.dumps(summary, ensure_ascii=False)}")
        return 0

    db_path = Path(args.db_path or Settings.CAPTURE_DB_FILE)
    export_path = Path(args.export_path or (Settings.DATA_DIR / "playright" / "dianping_shop.xlsx"))
    result_base_dir = Path(args.result_dir or (Settings.DATA_DIR / "playright"))

    if args.reset_db:
        reset_database(db_path)

    store = CaptureStore(db_path=db_path)
    dataset = StructuredShopDataset(store)

    if args.seed_mock:
        mock_data_path = Path(args.mock_data or DEFAULT_MOCK_DATA_FILE)
        seeded = dataset.seed_records(load_mock_records(mock_data_path))
        logger.info(f"已写入 mock 记录: {seeded}")

    if args.shop_list_file:
        input_records = load_shop_records_from_file(args.shop_list_file)
        seeded = dataset.seed_records(input_records)
        logger.info(f"已写入外部 shop 列表记录: {seeded}")
    else:
        input_records = []

    if args.run:
        artifact_paths = build_run_output_paths(result_base_dir)
        client = create_client(args)
        if hasattr(client, "__enter__") and hasattr(client, "__exit__"):
            with client:
                summary = DianpingDetailEnricher(dataset, client).run(
                    limit=args.limit,
                    stop_on_blocked=bool(args.stop_on_blocked),
                    sleep_range=(args.sleep_min, args.sleep_max) if args.mode == "playwright" else (0.0, 0.0),
                    artifact_dir=artifact_paths["run_dir"],
                    include_keys={item["shop_uuid"] for item in input_records} if input_records else None,
                    force_rerun=bool(args.force_rerun),
                )
        else:
            summary = DianpingDetailEnricher(dataset, client).run(
                limit=args.limit,
                stop_on_blocked=bool(args.stop_on_blocked),
                artifact_dir=artifact_paths["run_dir"],
                include_keys={item["shop_uuid"] for item in input_records} if input_records else None,
                force_rerun=bool(args.force_rerun),
            )
        write_run_artifacts(artifact_paths, summary)
        summary["results_file"] = str(artifact_paths["results_jsonl"])
        summary["summary_file"] = str(artifact_paths["summary_json"])
        logger.info(f"详情补全统计: {json.dumps(summary, ensure_ascii=False)}")

    if args.export:
        exported = dataset.export_excel(export_path)
        logger.info(f"已导出 Excel: {exported}")

    if not any([args.seed_mock, args.run, args.export]):
        parser.print_help()

    return 0
