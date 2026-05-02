#!/usr/bin/env python3

import json
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidgetItem, QWidget

from config.settings import Settings
from playright.detail_enricher import select_phone_fetch_rows


class StructuredDataController:
    def __init__(self, editor):
        self.editor = editor

    def show_data_management_help(self):
        QMessageBox.information(
            self.editor,
            "数据管理说明",
            "1. 这里展示最终解析后的结构化商家列表\n"
            "2. 可按区域、商家名、评分、电话状态和新增标签筛选\n"
            "3. 可分页查看并导出当前列表结果\n"
            "4. 可直接批量抓取无电话商家，支持按 `starScore < 阈值` 限定抓取范围\n"
            "5. “新增电话”会在“是否有电话”列中高亮显示，可在操作列移除标签或删除整条记录",
        )

    def refresh_structured_views(self, reset_page: bool = False):
        entity_code = self.editor._get_selected_entity_code()
        if reset_page:
            self.editor.structured_current_page = 1

        filters = self.collect_structured_filters()
        summary = self.editor.capture_store.summarize_structured_records(
            dataset_code=entity_code,
            filters=filters,
        )
        query_result = self.editor.capture_store.query_structured_records(
            dataset_code=entity_code,
            filters=filters,
            page=self.editor.structured_current_page,
            page_size=self.editor.structured_page_size,
        )
        self.editor.structured_total_records = query_result["total"]
        self.editor.structured_total_pages = query_result["total_pages"]
        self.editor.structured_current_page = min(query_result["page"], self.editor.structured_total_pages)
        if self.editor.structured_current_page != query_result["page"]:
            query_result = self.editor.capture_store.query_structured_records(
                dataset_code=entity_code,
                filters=filters,
                page=self.editor.structured_current_page,
                page_size=self.editor.structured_page_size,
            )
        self.editor.structured_record_rows = query_result["rows"]
        self._populate_structured_table()
        self._refresh_summary_badges(summary)

    def collect_structured_filters(self):
        return {
            "region_name": self.editor.structured_region_filter.text().strip() if hasattr(self.editor, "structured_region_filter") else "",
            "keyword": self.editor.structured_keyword_filter.text().strip() if hasattr(self.editor, "structured_keyword_filter") else "",
            "score_filter": self.editor.structured_score_filter.text().strip() if hasattr(self.editor, "structured_score_filter") else "",
            "has_phone": self.editor.structured_phone_filter.currentText() if hasattr(self.editor, "structured_phone_filter") else "",
            "new_phone_flag": self._normalize_new_phone_filter_value(
                self.editor.structured_new_phone_filter.currentText()
            ) if hasattr(self.editor, "structured_new_phone_filter") else "",
        }

    def apply_structured_filters(self):
        self.refresh_structured_views(reset_page=True)

    def reset_structured_filters(self):
        if hasattr(self.editor, "structured_region_filter"):
            self.editor.structured_region_filter.clear()
        if hasattr(self.editor, "structured_keyword_filter"):
            self.editor.structured_keyword_filter.clear()
        if hasattr(self.editor, "structured_score_filter"):
            self.editor.structured_score_filter.clear()
        if hasattr(self.editor, "structured_phone_filter"):
            self.editor.structured_phone_filter.setCurrentIndex(0)
        if hasattr(self.editor, "structured_new_phone_filter"):
            self.editor.structured_new_phone_filter.setCurrentIndex(0)
        self.refresh_structured_views(reset_page=True)

    def change_structured_page(self, delta: int):
        next_page = self.editor.structured_current_page + delta
        if next_page < 1 or next_page > self.editor.structured_total_pages:
            return
        self.editor.structured_current_page = next_page
        self.refresh_structured_views(reset_page=False)

    def handle_structured_selection_changed(self):
        return

    def handle_structured_item_changed(self, item):
        return

    def start_playwright_phone_fetch(self):
        if self.editor.playwright_worker and self.editor.playwright_worker.isRunning():
            QMessageBox.information(self.editor, "电话抓取", "当前已有抓取任务在运行")
            return

        filters = self.collect_structured_filters()
        entity_code = self.editor._get_selected_entity_code()
        query_result = self.editor.capture_store.query_structured_records(
            dataset_code=entity_code,
            filters=filters,
            page=1,
            page_size=100000,
        )
        star_score_threshold = self.editor.playwright_star_score_spin.value() if hasattr(self.editor, "playwright_star_score_spin") else 0.0
        limit = self.editor.playwright_limit_spin.value()
        candidate_rows = select_phone_fetch_rows(
            query_result["rows"],
            limit=limit,
            star_score_threshold=star_score_threshold,
        )

        if not candidate_rows:
            QMessageBox.information(self.editor, "电话抓取", "当前筛选结果中没有需要抓取的无电话商家")
            return

        concurrency = self.editor.playwright_concurrency_spin.value()
        worker = self.editor.playwright_worker_factory(
            db_path=Settings.CAPTURE_DB_FILE,
            records=candidate_rows,
            concurrency=concurrency,
            parent=self.editor,
        )
        worker.progress.connect(self.handle_playwright_worker_progress)
        worker.completed.connect(self.handle_playwright_worker_completed)
        worker.failed.connect(self.handle_playwright_worker_failed)
        self.editor.playwright_worker = worker
        self.editor.playwright_run_status_label.setText(
            f"抓取: 运行中 ({len(candidate_rows)} 家 / 并发 {max(1, int(concurrency or 1))})"
        )
        if hasattr(self.editor, "playwright_run_button"):
            self.editor.playwright_run_button.setEnabled(False)
        worker.start()

    def handle_playwright_worker_progress(self, message: str):
        if hasattr(self.editor, "playwright_run_status_label"):
            self.editor.playwright_run_status_label.setText(f"抓取: {message}")
        self.editor.statusBar().showMessage(message, 4000)

    def handle_playwright_worker_completed(self, summary: dict):
        processed = summary.get("processed", 0)
        breakdown = summary.get("status_breakdown", {})
        self.editor.playwright_worker = None
        if hasattr(self.editor, "playwright_run_status_label"):
            self.editor.playwright_run_status_label.setText(f"抓取: 已完成 {processed} 家")
        if hasattr(self.editor, "playwright_run_button"):
            self.editor.playwright_run_button.setEnabled(True)
        self.refresh_structured_views(reset_page=False)
        self.editor.statusBar().showMessage("电话抓取完成", 4000)
        QMessageBox.information(
            self.editor,
            "电话抓取完成",
            "本次电话抓取已完成。\n\n"
            f"处理数量: {processed}\n"
            f"状态统计: {json.dumps(breakdown, ensure_ascii=False)}\n"
            f"结果文件: {summary.get('results_file', '-')}\n"
            f"汇总文件: {summary.get('summary_file', '-')}",
        )

    def handle_playwright_worker_failed(self, message: str):
        self.editor.playwright_worker = None
        if hasattr(self.editor, "playwright_run_status_label"):
            self.editor.playwright_run_status_label.setText("抓取: 执行失败")
        if hasattr(self.editor, "playwright_run_button"):
            self.editor.playwright_run_button.setEnabled(True)
        self.editor.statusBar().showMessage("电话抓取失败", 4000)
        QMessageBox.warning(self.editor, "电话抓取失败", message)

    def export_structured_excel(self):
        protocols = self.editor._get_selected_protocols()
        entity_code = self.editor._get_selected_entity_code()
        if not protocols or not entity_code:
            QMessageBox.warning(self.editor, "导出结构化 Excel", "请先选择可用的点评接口")
            return

        export_columns = []
        seen = set()
        for protocol in protocols:
            for column in protocol.get("export_columns", []):
                if column not in seen:
                    seen.add(column)
                    export_columns.append(column)

        default_name = f"{entity_code}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename, _ = QFileDialog.getSaveFileName(
            self.editor,
            "导出结构化 Excel",
            str(Settings.DATA_DIR / default_name),
            "Excel 文件 (*.xlsx)",
        )
        if not filename:
            return

        rows = self.editor.capture_store.list_structured_records(dataset_code=entity_code, limit=10000)
        output = self.editor.capture_store.export_structured_excel(
            filename,
            dataset_code=entity_code,
            columns=export_columns,
            rows=rows,
        )
        QMessageBox.information(self.editor, "导出成功", f"已导出到:\n{output}")

    def _populate_structured_table(self):
        if not hasattr(self.editor, "structured_table"):
            return

        self.editor.structured_table_updating = True
        self.editor.structured_table.setRowCount(len(self.editor.structured_record_rows))
        for row_index, row in enumerate(self.editor.structured_record_rows):
            data = row.get("data", {})
            star_score = data.get("starScore", data.get("rating", ""))
            values = [
                data.get("name", ""),
                data.get("region_name", "") or data.get("regionName", "") or data.get("district", ""),
                data.get("shop_uuid", ""),
                "" if star_score is None else str(star_score),
                row.get("phone_status_label", "未抓"),
                row.get("recent_time_label", ""),
                "",
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.editor.structured_table.setItem(row_index, col_index, item)
            self.editor.structured_table.setCellWidget(
                row_index,
                4,
                self._build_phone_status_widget(
                    row.get("phone_status_label", "未抓"),
                    self.editor.capture_store.normalize_bool_flag(data.get("new_phone_flag")) == 1,
                ),
            )
            self.editor.structured_table.setCellWidget(
                row_index,
                6,
                self._build_action_widget(
                    row.get("record_key", ""),
                    self.editor.capture_store.normalize_bool_flag(data.get("new_phone_flag")) == 1,
                ),
            )
        self.editor.structured_table_updating = False

    def _refresh_summary_badges(self, summary: dict):
        if hasattr(self.editor, "structured_summary_label"):
            self.editor.structured_summary_label.setText(f"记录: {summary['total']}")
        if hasattr(self.editor, "structured_phone_has_label"):
            self.editor.structured_phone_has_label.setText(f"有: {summary['has_phone']}")
        if hasattr(self.editor, "structured_phone_none_label"):
            self.editor.structured_phone_none_label.setText(f"无: {summary['no_phone']}")
        if hasattr(self.editor, "structured_new_phone_label"):
            self.editor.structured_new_phone_label.setText(f"新增: {summary['new_phone']}")
        if hasattr(self.editor, "structured_interface_label"):
            protocols = self.editor._get_selected_protocols()
            if not protocols:
                self.editor.structured_interface_label.setText("接口: 未配置")
            elif self.editor.selected_interface_key == "all":
                self.editor.structured_interface_label.setText("接口: 全部点评接口")
            else:
                self.editor.structured_interface_label.setText(f"接口: {protocols[0].get('name', '-')}")
        if hasattr(self.editor, "playwright_page_label"):
            self.editor.playwright_page_label.setText(
                f"第 {self.editor.structured_current_page} / {self.editor.structured_total_pages} 页"
            )
        if hasattr(self.editor, "playwright_prev_page_button"):
            self.editor.playwright_prev_page_button.setEnabled(self.editor.structured_current_page > 1)
        if hasattr(self.editor, "playwright_next_page_button"):
            self.editor.playwright_next_page_button.setEnabled(
                self.editor.structured_current_page < self.editor.structured_total_pages
            )

    def _build_phone_status_widget(self, phone_status: str, has_new_phone_tag: bool):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        status_label = QLabel(phone_status or "未抓")
        status_label.setAlignment(Qt.AlignCenter)
        status_style = {
            "有": "background:#e8f7ee;color:#0f7a3d;border:1px solid #8ad3a8;",
            "无": "background:#fff1f0;color:#c23b2a;border:1px solid #f1a89f;",
            "未抓": "background:#f2f4f7;color:#475467;border:1px solid #d0d5dd;",
        }.get(phone_status or "未抓", "background:#f2f4f7;color:#475467;border:1px solid #d0d5dd;")
        status_label.setStyleSheet(f"padding:2px 8px;border-radius:10px;font-weight:600;{status_style}")
        layout.addWidget(status_label, 0, Qt.AlignLeft)

        if has_new_phone_tag:
            new_label = QLabel("新增电话")
            new_label.setAlignment(Qt.AlignCenter)
            new_label.setStyleSheet(
                "padding:2px 8px;border-radius:10px;"
                "background:#fff4d6;color:#9a6700;border:1px solid #f5c451;font-weight:700;"
            )
            layout.addWidget(new_label, 0, Qt.AlignLeft)

        layout.addStretch()
        return widget

    def _build_action_widget(self, record_key: str, has_new_phone_tag: bool):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        btn_delete = QPushButton("删除")
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setMinimumHeight(30)
        btn_delete.setMinimumWidth(72)
        btn_delete.setStyleSheet(
            "QPushButton {padding: 4px 12px; border-radius: 8px; "
            "border: 1px solid #f3b0a8; background: #fff3f1; color: #b42318; font-weight: 600;}"
            "QPushButton:hover {background: #ffe6e2;}"
        )
        btn_delete.clicked.connect(lambda _checked=False, rk=record_key: self._delete_structured_record(rk))
        layout.addWidget(btn_delete)

        btn_remove_tag = QPushButton("移除新增标")
        btn_remove_tag.setCursor(Qt.PointingHandCursor)
        btn_remove_tag.setMinimumHeight(30)
        btn_remove_tag.setMinimumWidth(92)
        btn_remove_tag.setStyleSheet(
            "QPushButton {padding: 4px 12px; border-radius: 8px; "
            "border: 1px solid #cbd5e1; background: #ffffff; color: #334155; font-weight: 600;}"
            "QPushButton:hover {background: #f8fafc;}"
            "QPushButton:disabled {color: #98a2b3; background: #f8fafc; border-color: #e4e7ec;}"
        )
        btn_remove_tag.setEnabled(has_new_phone_tag)
        btn_remove_tag.clicked.connect(lambda _checked=False, rk=record_key: self._clear_new_phone_flag(rk))
        layout.addWidget(btn_remove_tag)

        layout.addStretch()
        return widget

    def _clear_new_phone_flag(self, record_key: str):
        try:
            self.editor.capture_store.patch_structured_record_data(
                dataset_code=self.editor._get_selected_entity_code(),
                record_key=record_key,
                patch_data={"new_phone_flag": 0},
                force_overwrite_keys=["new_phone_flag"],
            )
        except Exception as exc:
            QMessageBox.warning(self.editor, "移除失败", str(exc))
            return

        self.refresh_structured_views(reset_page=False)
        self.editor.statusBar().showMessage(f"已移除 {record_key} 的新增电话标签", 3000)

    def _delete_structured_record(self, record_key: str):
        confirmed = QMessageBox.question(
            self.editor,
            "删除记录",
            f"确认删除记录 {record_key} 吗？该操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmed != QMessageBox.Yes:
            return

        try:
            self.editor.capture_store.delete_structured_record(
                dataset_code=self.editor._get_selected_entity_code(),
                record_key=record_key,
            )
        except Exception as exc:
            QMessageBox.warning(self.editor, "删除失败", str(exc))
            return

        self.refresh_structured_views(reset_page=False)
        self.editor.statusBar().showMessage(f"已删除记录 {record_key}", 3000)

    @staticmethod
    def _normalize_new_phone_filter_value(value: str) -> str:
        mapping = {
            "仅新增": "仅新增电话",
            "非新增": "非新增电话",
        }
        return mapping.get(str(value or "").strip(), str(value or "").strip())
