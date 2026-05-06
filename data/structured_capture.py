#!/usr/bin/env python3
"""
点评专用结构化抓取导入
"""

import importlib
import json
import re
from pathlib import Path
from typing import Any

from config.settings import Settings
from utils.logger import logger


class MeituanConfigLoader:
    """加载点评接口协议"""

    def __init__(self, config_dir=None):
        self.config_dir = Path(config_dir or Settings.MEITUAN_CONFIG_DIR)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def list_protocols(self):
        protocols = []
        for path in sorted(self.config_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                protocol = self._normalize_protocol(raw)
                protocol["config_path"] = str(path)
                protocols.append(protocol)
            except Exception as exc:
                logger.error(f"加载点评协议失败: {path.name}, error={exc}")
        return sorted(protocols, key=lambda item: (int(item.get("priority", 100) or 100), item.get("key", "")))

    def get_protocol(self, key: str):
        key = (key or "").strip()
        for protocol in self.list_protocols():
            if protocol["key"] == key:
                return protocol
        return None

    @staticmethod
    def _normalize_protocol(protocol: dict):
        normalized = {
            "key": "",
            "name": "",
            "platform": "meituan",
            "enabled": True,
            "priority": 100,
            "url_pattern": "",
            "entity_code": "dianping_shop",
            "record_key": {
                "mode": "path",
                "expr": "",
            },
            "root_path": "",
            "list_path": "",
            "overwrite_existing": False,
            "fields": [],
            "processor": "",
            "export_columns": [],
        }
        normalized.update(protocol or {})

        record_key = normalized.get("record_key") or {}
        normalized["record_key"] = {
            "mode": str(record_key.get("mode", "path")).strip() or "path",
            "expr": str(record_key.get("expr", "")).strip(),
        }

        fields = []
        for field in normalized.get("fields", []) or []:
            fields.append({
                "target": str(field.get("target", "")).strip(),
                "source": str(field.get("source", "")).strip(),
                "type": str(field.get("type", "string")).strip() or "string",
                "default": field.get("default", ""),
                "array_mode": str(field.get("array_mode", "")).strip(),
                "joiner": field.get("joiner", ","),
                "item_field": str(field.get("item_field", "")).strip(),
            })
        normalized["fields"] = [field for field in fields if field["target"]]
        normalized["export_columns"] = [str(item).strip() for item in normalized.get("export_columns", []) if str(item).strip()]
        return normalized


class MeituanCaptureImporter:
    """按点评接口协议把原始抓包转换成结构化记录"""

    def __init__(self, store):
        self.store = store

    def validate_protocol(self, protocol: dict):
        if not protocol.get("key"):
            return "协议缺少 key"
        if not protocol.get("url_pattern"):
            return "协议缺少接口匹配规则"
        record_key = protocol.get("record_key") or {}
        if record_key.get("mode") not in {"path", "plugin"}:
            return "record_key.mode 仅支持 path 或 plugin"
        if not record_key.get("expr"):
            return "record_key.expr 不能为空"
        return ""

    def import_protocols(self, protocols, batch_size: int = 500):
        results = []
        ordered_protocols = sorted(protocols or [], key=lambda item: int(item.get("priority", 100) or 100))
        for protocol in ordered_protocols:
            if not protocol.get("enabled", True):
                continue
            results.append(self.import_protocol(protocol, batch_size=batch_size))
        return results

    def import_protocol(self, protocol: dict, batch_size: int = 500):
        validation_error = self.validate_protocol(protocol)
        if validation_error:
            return self._build_result(protocol, error=validation_error)

        protocol_key = protocol["key"]
        last_capture_id = self.store.get_sync_state(protocol_key)
        current_cursor = last_capture_id
        matched = 0
        inserted = 0
        updated = 0
        failed = 0

        while True:
            captures = self.store.list_captures_after(current_cursor, limit=batch_size)
            if not captures:
                break

            for capture in captures:
                current_cursor = capture["id"]
                if not self._match_protocol(protocol, capture):
                    continue

                matched += 1
                try:
                    stats = self._process_capture(protocol, capture)
                    inserted += stats["inserted"]
                    updated += stats["updated"]
                    failed += stats["failed"]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(f"点评结构化导入失败: protocol={protocol_key}, capture={capture['id']}, error={exc}")
                    self.store.insert_failure(
                        dataset_code=protocol_key,
                        source_capture_id=capture["id"],
                        failure_stage="process_capture",
                        failure_reason=str(exc),
                        raw_excerpt=capture.get("response_text", ""),
                    )
                    failed += 1

            self.store.save_sync_state(protocol_key, current_cursor)

        return self._build_result(
            protocol,
            matched=matched,
            imported=inserted,
            updated=updated,
            failed=failed,
            last_capture_id=current_cursor,
        )

    def _process_capture(self, protocol: dict, capture: dict):
        protocol_key = protocol["key"]
        entity_code = protocol.get("entity_code", protocol_key)
        body = capture.get("response_text", "") or ""
        try:
            response_json = json.loads(body)
        except Exception:
            self.store.insert_failure(
                dataset_code=protocol_key,
                source_capture_id=capture["id"],
                failure_stage="parse_json",
                failure_reason="响应不是合法 JSON",
                raw_excerpt=body,
            )
            return {"inserted": 0, "updated": 0, "failed": 1}

        root = self._extract_source_value(response_json, capture, protocol.get("root_path", ""))
        if root is None:
            root = response_json

        items = self._resolve_items(root, protocol.get("list_path", ""))
        if not items:
            self.store.insert_failure(
                dataset_code=protocol_key,
                source_capture_id=capture["id"],
                failure_stage="extract_items",
                failure_reason="未提取到可转换数据",
                raw_excerpt=body,
            )
            return {"inserted": 0, "updated": 0, "failed": 1}

        inserted = 0
        updated = 0
        failed = 0
        processor = self._load_callable(protocol.get("processor", ""))

        for item in items:
            try:
                context = {
                    "item": item,
                    "root": root,
                    "response": response_json,
                    "capture": capture,
                    "protocol": protocol,
                    "record": {},
                }
                record = self._build_record_data(protocol, context)
                context["record"] = record
                if processor:
                    processed = processor(context)
                    if isinstance(processed, dict):
                        record.update({key: value for key, value in processed.items() if value is not None})
                        context["record"] = record

                record_key = self._resolve_record_key(protocol, context)
                if not record_key:
                    self.store.insert_failure(
                        dataset_code=protocol_key,
                        source_capture_id=capture["id"],
                        failure_stage="resolve_key",
                        failure_reason="唯一 key 为空，已跳过",
                        raw_excerpt=json.dumps(item, ensure_ascii=False)[:4000],
                    )
                    failed += 1
                    continue

                _, created = self.store.upsert_structured_record(
                    dataset_code=entity_code,
                    record_key=record_key,
                    data=record,
                    source_capture_id=capture["id"],
                    parse_status="parsed",
                    enrich_status="done",
                    overwrite_existing=bool(protocol.get("overwrite_existing", False)),
                )
                if created:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                self.store.insert_failure(
                    dataset_code=protocol_key,
                    source_capture_id=capture["id"],
                    failure_stage="build_record",
                    failure_reason=str(exc),
                    raw_excerpt=json.dumps(item, ensure_ascii=False)[:4000],
                )
                failed += 1

        return {"inserted": inserted, "updated": updated, "failed": failed}

    @staticmethod
    def _build_result(protocol: dict, error: str = "", **stats):
        result = {
            "protocol_key": protocol.get("key", ""),
            "protocol_name": protocol.get("name", ""),
            "entity_code": protocol.get("entity_code", ""),
            "error": error,
            "matched": 0,
            "imported": 0,
            "updated": 0,
            "failed": 0,
            "last_capture_id": 0,
        }
        result.update(stats)
        return result

    @staticmethod
    def _match_protocol(protocol: dict, capture: dict):
        pattern = (protocol.get("url_pattern") or "").strip()
        if not pattern:
            return False
        url = capture.get("url", "") or ""
        try:
            return re.search(pattern, url) is not None
        except re.error:
            return pattern in url

    @staticmethod
    def _resolve_items(root: Any, list_path: str):
        if list_path:
            items = MeituanCaptureImporter._extract_path(root, list_path)
        else:
            items = root

        if isinstance(items, list):
            return items
        if items is None:
            return []
        return [items]

    def _build_record_data(self, protocol: dict, context: dict):
        record = {}
        for field in protocol.get("fields", []):
            value = self._extract_source_value(context["item"], context["capture"], field.get("source", ""), context, record)
            value = self._transform_field_value(field, value)
            if self._is_empty_value(value):
                default_value = field.get("default", "")
                if default_value not in ("", None):
                    value = default_value
            record[field["target"]] = value
        return record

    def _resolve_record_key(self, protocol: dict, context: dict):
        record_key = protocol.get("record_key") or {}
        mode = (record_key.get("mode") or "path").strip()
        expr = (record_key.get("expr") or "").strip()
        if mode == "plugin":
            func = self._load_callable(expr)
            if not func:
                raise ValueError(f"无法加载 key 插件: {expr}")
            value = func(context)
        else:
            value = self._extract_source_value(context["item"], context["capture"], expr, context, context.get("record", {}))

        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value).strip()

    def _transform_field_value(self, field: dict, value):
        if isinstance(value, list):
            value = self._transform_array_value(field, value)

        value_type = (field.get("type") or "string").strip().lower()
        if value_type == "json":
            return json.dumps(value, ensure_ascii=False) if value not in (None, "") else ""
        return self._coerce_value(value, value_type)

    def _transform_array_value(self, field: dict, value: list):
        mode = (field.get("array_mode") or "").strip().lower()
        if not mode:
            if value and all(not isinstance(item, (dict, list)) for item in value):
                mode = "join"
            elif field.get("item_field"):
                mode = "pluck_join"
            else:
                mode = "json"

        joiner = field.get("joiner", ",")
        item_field = (field.get("item_field") or "").strip()

        if mode == "json":
            return json.dumps(value, ensure_ascii=False)

        if mode == "pluck_join":
            parts = []
            for item in value:
                if isinstance(item, dict):
                    extracted = self._extract_path(item, item_field) if item_field else None
                else:
                    extracted = item
                if extracted not in (None, ""):
                    parts.append(str(extracted).strip())
            return joiner.join(parts)

        parts = []
        for item in value:
            if isinstance(item, dict):
                if item_field:
                    extracted = self._extract_path(item, item_field)
                    if extracted not in (None, ""):
                        parts.append(str(extracted).strip())
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            elif item not in (None, ""):
                parts.append(str(item).strip())
        return joiner.join(parts)

    def _extract_source_value(self, item, capture: dict, source: str, context: dict = None, record_data: dict = None):
        source = (source or "").strip()
        if not source:
            return item

        context = context or {}
        record_data = record_data or {}

        if source.startswith("capture."):
            return self._extract_path(capture, source[len("capture."):])
        if source.startswith("root."):
            return self._extract_path(context.get("root"), source[len("root."):])
        if source == "root":
            return context.get("root")
        if source.startswith("response."):
            return self._extract_path(context.get("response"), source[len("response."):])
        if source == "response":
            return context.get("response")
        if source.startswith("record."):
            return self._extract_path(record_data, source[len("record."):])
        if source == "item":
            return item
        return self._extract_path(item, source)

    @staticmethod
    def _extract_path(data: Any, path: str):
        current = data
        for token in MeituanCaptureImporter._tokenize_path(path):
            if current is None:
                return None
            if isinstance(token, int):
                if not isinstance(current, list) or token >= len(current):
                    return None
                current = current[token]
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(token)
        return current

    @staticmethod
    def _tokenize_path(path: str):
        tokens = []
        for part in (path or "").split("."):
            if not part:
                continue
            while "[" in part and "]" in part:
                prefix, rest = part.split("[", 1)
                if prefix:
                    tokens.append(prefix)
                index_text, part = rest.split("]", 1)
                if index_text.isdigit():
                    tokens.append(int(index_text))
                if part.startswith("."):
                    part = part[1:]
            if part:
                tokens.append(part)
        return tokens

    @staticmethod
    def _coerce_value(value, value_type: str):
        if value is None:
            return None
        if value_type == "string":
            return str(value).strip()
        if value_type == "int":
            try:
                return int(float(value))
            except Exception:
                return None
        if value_type == "float":
            try:
                return float(value)
            except Exception:
                return None
        if value_type == "bool":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in {"1", "true", "yes", "y"}:
                return True
            if text in {"0", "false", "no", "n"}:
                return False
            return None
        return value

    @staticmethod
    def _is_empty_value(value):
        return value in (None, "", [], {})

    @staticmethod
    def _load_callable(path: str):
        path = (path or "").strip()
        if not path:
            return None
        if ":" in path:
            module_name, attr_name = path.split(":", 1)
        else:
            module_name, attr_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)


def enrich_dianping_shop_list_record(context: dict):
    item = context.get("item") or {}
    shop_info = item.get("shopInfo") if isinstance(item, dict) else {}
    if not isinstance(shop_info, dict):
        shop_info = {}

    price_text = str(shop_info.get("priceText", "") or "").strip()
    shop_uuid = str(
        context.get("record", {}).get("shop_uuid")
        or shop_info.get("shopUuid")
        or shop_info.get("shop_uuid")
        or ""
    ).strip()
    shop_id = str(context.get("record", {}).get("shop_id") or shop_info.get("id") or "").strip()

    return {
        "shop_id": shop_id,
        "shop_uuid": shop_uuid,
        "price_text": price_text,
        "avg_price": _parse_price_text(price_text),
        "region_name": str(shop_info.get("regionName", "") or "").strip(),
        "shop_type": _coerce_int(shop_info.get("shopType")),
        "category_name": str(shop_info.get("categoryName", "") or "").strip(),
        "has_phone": "",
        "phone": "",
        "new_phone_flag": 0,
        "contacted": 0,
        "detail_fetch_status": "",
        "detail_fetch_time": "",
        "detail_error_message": "",
    }


def _parse_price_text(price_text: str):
    if not price_text:
        return 0
    match = re.search(r"(\d+(?:\.\d+)?)", price_text)
    if not match:
        return 0
    try:
        return float(match.group(1))
    except Exception:
        return 0


def _coerce_int(value):
    try:
        return int(value)
    except Exception:
        return ""
