#!/usr/bin/env python3
"""
抓取数据存储
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from config.settings import Settings

try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover - graceful fallback
    Workbook = None


class CaptureStore:
    """SQLite 抓取存储"""

    COLUMNS = [
        ("created_at", "抓取时间"),
        ("pattern", "命中规则"),
        ("platform", "平台"),
        ("method", "方法"),
        ("status_code", "状态码"),
        ("host", "域名"),
        ("path", "路径"),
        ("url", "完整URL"),
        ("response_size", "响应大小"),
        ("response_preview", "响应预览"),
    ]

    def __init__(self, db_path=None):
        self.db_path = Path(db_path or Settings.CAPTURE_DB_FILE)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _connection(self):
        return closing(self._connect())

    def _init_db(self):
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS captures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    pattern TEXT,
                    platform TEXT,
                    method TEXT,
                    status_code INTEGER,
                    host TEXT,
                    path TEXT,
                    url TEXT,
                    response_size INTEGER,
                    response_preview TEXT,
                    response_text TEXT,
                    headers_json TEXT,
                    meta_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS structured_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_code TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    source_capture_id INTEGER,
                    parse_status TEXT NOT NULL DEFAULT 'parsed',
                    enrich_status TEXT NOT NULL DEFAULT 'pending',
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(dataset_code, record_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS record_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_code TEXT NOT NULL,
                    source_capture_id INTEGER,
                    failure_stage TEXT NOT NULL,
                    failure_reason TEXT NOT NULL,
                    raw_excerpt TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_sync_state (
                    dataset_code TEXT PRIMARY KEY,
                    last_capture_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_captures_id ON captures(id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_dataset ON structured_records(dataset_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_failures_dataset ON record_failures(dataset_code)")
            conn.commit()

    def insert_capture(self, payload: dict):
        created_at = payload.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        headers_json = json.dumps(payload.get("headers", {}), ensure_ascii=False)
        meta_json = json.dumps(payload.get("meta", {}), ensure_ascii=False)
        response_text = payload.get("response_text", "") or ""
        response_preview = response_text[:3000]

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO captures (
                    created_at, pattern, platform, method, status_code,
                    host, path, url, response_size, response_preview,
                    response_text, headers_json, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    payload.get("pattern", ""),
                    payload.get("platform", ""),
                    payload.get("method", ""),
                    payload.get("status_code"),
                    payload.get("host", ""),
                    payload.get("path", ""),
                    payload.get("url", ""),
                    payload.get("response_size", len(response_text.encode("utf-8"))),
                    response_preview,
                    response_text,
                    headers_json,
                    meta_json,
                ),
            )
            conn.commit()

    def clear_captures(self):
        with self._connection() as conn:
            conn.execute("DELETE FROM captures")
            conn.commit()

    def list_captures(self, limit: int = 300):
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, pattern, platform, method, status_code,
                       host, path, url, response_size, response_preview
                FROM captures
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_capture(self, capture_id: int):
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM captures
                WHERE id = ?
                """,
                (capture_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_captures_after(self, capture_id: int, limit: int = 1000):
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM captures
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (capture_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_structured_record(
        self,
        dataset_code: str,
        record_key: str,
        data: dict,
        source_capture_id: int = None,
        parse_status: str = "parsed",
        enrich_status: str = "pending",
        overwrite_existing: bool = False,
        force_overwrite_keys=None,
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record_data = data or {}

        with self._connection() as conn:
            existing = conn.execute(
                """
                SELECT id, data_json, created_at
                FROM structured_records
                WHERE dataset_code = ? AND record_key = ?
                """,
                (dataset_code, record_key),
            ).fetchone()

            if existing:
                existing_data = json.loads(existing["data_json"] or "{}")
                merged_data = self._merge_record_data(
                    existing_data,
                    record_data,
                    overwrite_existing=overwrite_existing,
                    force_overwrite_keys=force_overwrite_keys,
                )
                conn.execute(
                    """
                    UPDATE structured_records
                    SET source_capture_id = ?,
                        parse_status = ?,
                        enrich_status = ?,
                        data_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        source_capture_id,
                        parse_status,
                        enrich_status,
                        json.dumps(merged_data, ensure_ascii=False),
                        now,
                        existing["id"],
                    ),
                )
                conn.commit()
                return existing["id"], False

            cursor = conn.execute(
                """
                INSERT INTO structured_records (
                    dataset_code, record_key, source_capture_id, parse_status,
                    enrich_status, data_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_code,
                    record_key,
                    source_capture_id,
                    parse_status,
                    enrich_status,
                    json.dumps(record_data, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid, True

    def insert_failure(
        self,
        dataset_code: str,
        source_capture_id: int,
        failure_stage: str,
        failure_reason: str,
        raw_excerpt: str = "",
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO record_failures (
                    dataset_code, source_capture_id, failure_stage,
                    failure_reason, raw_excerpt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_code,
                    source_capture_id,
                    failure_stage,
                    failure_reason,
                    (raw_excerpt or "")[:4000],
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def list_structured_records(self, dataset_code: str = "", limit: int = 500):
        query = [
            "SELECT id, dataset_code, record_key, source_capture_id, parse_status, enrich_status, created_at, updated_at, data_json",
            "FROM structured_records",
        ]
        params = []
        if dataset_code:
            query.append("WHERE dataset_code = ?")
            params.append(dataset_code)
        query.append("ORDER BY id DESC")
        if limit and limit > 0:
            query.append("LIMIT ?")
            params.append(limit)

        with self._connection() as conn:
            rows = conn.execute("\n".join(query), params).fetchall()

        return [self._deserialize_structured_row(row) for row in rows]

    def get_structured_record(self, dataset_code: str, record_key: str):
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, dataset_code, record_key, source_capture_id, parse_status, enrich_status, created_at, updated_at, data_json
                FROM structured_records
                WHERE dataset_code = ? AND record_key = ?
                """,
                (dataset_code, record_key),
            ).fetchone()
        return self._deserialize_structured_row(row) if row else None

    def patch_structured_record_data(
        self,
        dataset_code: str,
        record_key: str,
        patch_data: dict,
        force_overwrite_keys=None,
    ):
        existing = self.get_structured_record(dataset_code, record_key)
        if not existing:
            raise ValueError(f"未找到结构化记录: {dataset_code}/{record_key}")

        merged = self._merge_record_data(
            existing.get("data", {}),
            patch_data or {},
            overwrite_existing=True,
            force_overwrite_keys=force_overwrite_keys,
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE structured_records
                SET data_json = ?, updated_at = ?
                WHERE dataset_code = ? AND record_key = ?
                """,
                (
                    json.dumps(merged, ensure_ascii=False),
                    now,
                    dataset_code,
                    record_key,
                ),
            )
            conn.commit()
        return self.get_structured_record(dataset_code, record_key)

    def delete_structured_record(self, dataset_code: str, record_key: str):
        existing = self.get_structured_record(dataset_code, record_key)
        if not existing:
            raise ValueError(f"未找到结构化记录: {dataset_code}/{record_key}")

        with self._connection() as conn:
            conn.execute(
                """
                DELETE FROM structured_records
                WHERE dataset_code = ? AND record_key = ?
                """,
                (dataset_code, record_key),
            )
            conn.commit()
        return existing

    def query_structured_records(
        self,
        dataset_code: str,
        filters: dict | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        rows = self.list_structured_records(dataset_code=dataset_code, limit=100000)
        filtered = self._filter_structured_rows(rows, filters or {})
        total = len(filtered)
        current_page = max(1, int(page or 1))
        normalized_page_size = max(1, int(page_size or 50))
        start = (current_page - 1) * normalized_page_size
        end = start + normalized_page_size
        return {
            "rows": filtered[start:end],
            "total": total,
            "page": current_page,
            "page_size": normalized_page_size,
            "total_pages": max(1, (total + normalized_page_size - 1) // normalized_page_size),
        }

    def summarize_structured_records(self, dataset_code: str, filters: dict | None = None):
        rows = self.list_structured_records(dataset_code=dataset_code, limit=100000)
        filtered = self._filter_structured_rows(rows, filters or {})
        summary = {
            "total": len(filtered),
            "has_phone": 0,
            "no_phone": 0,
            "unfetched": 0,
            "new_phone": 0,
        }
        for row in filtered:
            data = row.get("data", {})
            phone_status = row.get("phone_status_label") or self.normalize_phone_status(
                data.get("has_phone"),
                data.get("phone"),
                data.get("detail_fetch_status"),
            ) or "未抓"
            if phone_status == "有":
                summary["has_phone"] += 1
            elif phone_status == "无":
                summary["no_phone"] += 1
            else:
                summary["unfetched"] += 1

            if self.normalize_bool_flag(data.get("new_phone_flag")):
                summary["new_phone"] += 1
        return summary

    def list_failures(self, dataset_code: str = "", limit: int = 200):
        query = [
            "SELECT id, dataset_code, source_capture_id, failure_stage, failure_reason, raw_excerpt, created_at",
            "FROM record_failures",
        ]
        params = []
        if dataset_code:
            query.append("WHERE dataset_code = ?")
            params.append(dataset_code)
        query.append("ORDER BY id DESC LIMIT ?")
        params.append(limit)

        with self._connection() as conn:
            rows = conn.execute("\n".join(query), params).fetchall()
        return [dict(row) for row in rows]

    def get_sync_state(self, dataset_code: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT last_capture_id
                FROM dataset_sync_state
                WHERE dataset_code = ?
                """,
                (dataset_code,),
            ).fetchone()
        if not row:
            return 0
        return int(row["last_capture_id"] or 0)

    def save_sync_state(self, dataset_code: str, last_capture_id: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO dataset_sync_state(dataset_code, last_capture_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(dataset_code) DO UPDATE SET
                    last_capture_id = excluded.last_capture_id,
                    updated_at = excluded.updated_at
                """,
                (dataset_code, int(last_capture_id or 0), now),
            )
            conn.commit()

    def get_structured_stats(self, dataset_code: str = ""):
        params = []
        record_where = ""
        failure_where = ""
        if dataset_code:
            record_where = "WHERE dataset_code = ?"
            failure_where = "WHERE dataset_code = ?"
            params.append(dataset_code)

        with self._connection() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_records,
                    SUM(CASE WHEN enrich_status = 'need_enrich' THEN 1 ELSE 0 END) AS need_enrich_count,
                    SUM(CASE WHEN enrich_status = 'done' THEN 1 ELSE 0 END) AS done_count
                FROM structured_records
                {record_where}
                """,
                params,
            ).fetchone()
            failure_row = conn.execute(
                f"""
                SELECT COUNT(*) AS failure_count
                FROM record_failures
                {failure_where}
                """,
                params,
            ).fetchone()
        return {
            "total_records": int((row["total_records"] if row else 0) or 0),
            "need_enrich_count": int((row["need_enrich_count"] if row else 0) or 0),
            "done_count": int((row["done_count"] if row else 0) or 0),
            "failure_count": int((failure_row["failure_count"] if failure_row else 0) or 0),
        }

    def export_excel(self, output_path: str, rows=None):
        rows = rows or self.list_captures(limit=5000)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        headers = [title for _, title in self.COLUMNS]
        sheet_rows = [headers]
        for row in rows:
            sheet_rows.append([row.get(key, "") for key, _ in self.COLUMNS])

        return self._write_sheet_workbook(output, "Captures", headers, sheet_rows)

    def export_structured_excel(self, output_path: str, dataset_code: str, columns=None, rows=None):
        structured_rows = rows or self.list_structured_records(dataset_code=dataset_code, limit=10000)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        export_columns = [column for column in (columns or []) if column]
        if not export_columns:
            export_columns = self._collect_structured_columns(structured_rows)

        headers = ["record_key", "updated_at"] + export_columns
        sheet_rows = [headers]
        for row in structured_rows:
            data = row.get("data", {})
            sheet_rows.append([row.get("record_key", ""), row.get("updated_at", "")] + [data.get(column, "") for column in export_columns])

        sheet_name = dataset_code[:31] or "Records"
        return self._write_sheet_workbook(output, sheet_name, headers, sheet_rows)

    def _write_sheet_workbook(self, output: Path, sheet_name: str, headers, sheet_rows):
        output.parent.mkdir(parents=True, exist_ok=True)

        if Workbook is not None:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = sheet_name
            for row in sheet_rows:
                sheet.append(row)
            workbook.save(str(output))
            return str(output)

        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", self._content_types_xml())
            archive.writestr("_rels/.rels", self._rels_xml())
            archive.writestr("xl/workbook.xml", self._workbook_xml(sheet_name))
            archive.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml())
            archive.writestr("xl/styles.xml", self._styles_xml())
            archive.writestr("xl/worksheets/sheet1.xml", self._sheet_xml(sheet_rows))

        return str(output)

    @staticmethod
    def _cell_ref(col_index: int, row_index: int):
        col_name = ""
        index = col_index + 1
        while index:
            index, remainder = divmod(index - 1, 26)
            col_name = chr(65 + remainder) + col_name
        return f"{col_name}{row_index}"

    def _sheet_xml(self, rows):
        row_xml = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row):
                ref = self._cell_ref(col_index, row_index)
                text = "" if value is None else escape(str(value))
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

        dimension = f"A1:{self._cell_ref(max(len(rows[0]) - 1, 0), max(len(rows), 1))}"
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<dimension ref="{dimension}"/>'
            '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
            '<sheetFormatPr defaultRowHeight="18"/>'
            f'<sheetData>{"".join(row_xml)}</sheetData>'
            '</worksheet>'
        )

    @staticmethod
    def _content_types_xml():
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )

    @staticmethod
    def _rels_xml():
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _workbook_xml(sheet_name: str):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        )

    @staticmethod
    def _workbook_rels_xml():
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _styles_xml():
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

    @staticmethod
    def _is_empty_value(value):
        return value in (None, "", [], {})

    @staticmethod
    def _deserialize_structured_row(row):
        item = dict(row)
        try:
            item["data"] = json.loads(item.get("data_json") or "{}")
        except Exception:
            item["data"] = {}
        return item

    def _filter_structured_rows(self, rows, filters: dict):
        region_text = str(filters.get("region_name", "") or "").strip().lower()
        keyword_text = str(filters.get("keyword", "") or "").strip().lower()
        phone_filter = str(filters.get("has_phone", "") or "").strip()
        new_phone_filter = str(filters.get("new_phone_flag", "") or "").strip()
        score_filter = str(filters.get("score_filter", "") or "").strip()

        filtered = []
        for row in rows:
            data = row.get("data", {})
            region_candidates = [
                str(data.get("region_name", "") or "").strip(),
                str(data.get("regionName", "") or "").strip(),
                str(data.get("district", "") or "").strip(),
            ]
            name = str(data.get("name", "") or "").strip()
            phone_status = self.normalize_phone_status(
                data.get("has_phone"),
                data.get("phone"),
                data.get("detail_fetch_status"),
            )
            phone_status_label = phone_status or "未抓"
            new_phone_flag = self.normalize_bool_flag(data.get("new_phone_flag"))
            recent_time = (
                str(data.get("detail_fetch_time", "") or "").strip()
                or str(row.get("updated_at", "") or "").strip()
                or str(row.get("created_at", "") or "").strip()
            )
            score_value = self._parse_numeric_score(data.get("starScore", data.get("rating", "")))

            if region_text and not any(region_text in candidate.lower() for candidate in region_candidates if candidate):
                continue
            if keyword_text and keyword_text not in name.lower():
                continue
            if score_filter and not self._match_score_filter(score_value, score_filter):
                continue
            if phone_filter and phone_filter != "全部" and phone_status_label != phone_filter:
                continue
            if new_phone_filter == "仅新增电话" and new_phone_flag != 1:
                continue
            if new_phone_filter == "非新增电话" and new_phone_flag == 1:
                continue

            enriched_row = dict(row)
            enriched_row["phone_status_label"] = phone_status_label
            enriched_row["new_phone_flag_value"] = new_phone_flag
            enriched_row["recent_time_label"] = recent_time
            enriched_row["score_value"] = score_value
            filtered.append(enriched_row)

        filtered.sort(
            key=lambda item: (
                str(item.get("recent_time_label", "") or ""),
                int(item.get("id", 0) or 0),
            ),
            reverse=True,
        )
        return filtered

    @staticmethod
    def _parse_numeric_score(value):
        try:
            text = str(value or "").strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    @classmethod
    def _match_score_filter(cls, score_value, score_filter: str) -> bool:
        if not score_filter:
            return True
        if score_value is None:
            return False

        text = str(score_filter or "").strip().replace(" ", "")
        operators = [">=", "<=", ">", "<", "="]
        for operator in operators:
            if text.startswith(operator):
                try:
                    target = float(text[len(operator):])
                except Exception:
                    return True
                if operator == ">=":
                    return score_value >= target
                if operator == "<=":
                    return score_value <= target
                if operator == ">":
                    return score_value > target
                if operator == "<":
                    return score_value < target
                return score_value == target

        if "-" in text:
            left, right = text.split("-", 1)
            try:
                min_value = float(left)
                max_value = float(right)
            except Exception:
                return True
            return min_value <= score_value <= max_value

        try:
            target = float(text)
        except Exception:
            return True
        return score_value == target

    @staticmethod
    def normalize_phone_status(has_phone, phone="", detail_status="") -> str:
        if str(phone or "").strip():
            return "有"

        text = str(has_phone or "").strip()
        if text in {"有", "true", "True", "1"}:
            return "有"
        if text in {"无", "false", "False"}:
            return "无"
        if has_phone is True:
            return "有"
        if has_phone is False:
            return "无"

        normalized_detail_status = str(detail_status or "").strip()
        if normalized_detail_status and normalized_detail_status != "success":
            return "无"
        return ""

    @staticmethod
    def normalize_bool_flag(value) -> int:
        if isinstance(value, bool):
            return 1 if value else 0
        text = str(value or "").strip().lower()
        return 1 if text in {"1", "true", "yes", "y", "有"} else 0

    @classmethod
    def _merge_record_data(
        cls,
        existing: dict,
        incoming: dict,
        overwrite_existing: bool = False,
        force_overwrite_keys=None,
    ):
        merged = dict(existing or {})
        forced_keys = set(force_overwrite_keys or [])
        for key, value in (incoming or {}).items():
            if key in forced_keys:
                merged[key] = value
                continue

            if overwrite_existing:
                if not cls._is_empty_value(value):
                    merged[key] = value
                elif key not in merged:
                    merged[key] = value
                continue

            if key not in merged or cls._is_empty_value(merged.get(key)):
                merged[key] = value
        return merged

    @staticmethod
    def _collect_structured_columns(rows):
        ordered = []
        seen = set()
        for row in rows:
            for key in (row.get("data") or {}).keys():
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        return ordered
