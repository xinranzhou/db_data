#!/usr/bin/env python3

from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from config.settings import Settings
from data.capture_store import CaptureStore


class RealtimeCaptureController:
    def __init__(self, editor):
        self.editor = editor

    def show_data_operation_help(self):
        platform_value = self.editor._get_capture_platform()
        step_three_text = "3. 点击“开始收集数据”拉取最新抓包数据\n"
        if platform_value == "ios":
            step_three_text = "3. iOS 模式下，请先在 iPhone 手动打开目标页面/小程序，再回到这里开始收集数据\n"
        elif platform_value == "both":
            step_three_text = "3. 双平台模式下，请先在目标设备上触发请求，再回到这里开始收集数据\n"
        QMessageBox.information(
            self.editor,
            "抓取实时数据说明",
            "1. 先在“抓包配置”页启动抓取服务\n"
            "2. 在这里选择点评接口\n"
            f"{step_three_text}"
            "4. 点击“录入抓取数据”时，只会按当前选中的接口协议执行转换\n"
            "5. “导出原始抓包”导出抓包明细，用于排查解析问题\n"
            "6. “清理临时抓包”会清空实时抓包明细和临时 inbox 数据\n"
            "7. 最终结构化列表、电话状态和补抓入口统一到“数据管理”页处理",
        )

    def save_capture_rules(self):
        self.editor._save_settings_if_needed(silent=True)
        self.editor._refresh_capture_rule_summary()
        if self.editor.capture_manager.is_running():
            ok, message = self.editor.capture_manager.start(self.editor.app_settings.get("capture", {}))
            if not ok:
                QMessageBox.warning(self.editor, "点评接口规则", message)
                return False
        self.editor.statusBar().showMessage("点评接口规则已同步", 3000)
        return True

    def clear_temporary_capture_data(self):
        reply = QMessageBox.question(
            self.editor,
            "清理临时抓包",
            "这会清空“抓取实时数据”页中的临时抓包明细，并重置 inbox/offset。\n"
            "不会删除已经入库的结构化商家数据。\n\n"
            "确定继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok, message = self.editor.capture_manager.clear_temporary_capture_data()
        if not ok:
            QMessageBox.warning(self.editor, "清理临时抓包", message)
            return

        self.editor.capture_rows = []
        if hasattr(self.editor, "capture_table"):
            self.editor.capture_table.setRowCount(0)
        if hasattr(self.editor, "capture_detail_text"):
            self.editor.capture_detail_text.clear()
        self.editor.statusBar().showMessage(message, 4000)
        QMessageBox.information(self.editor, "清理完成", message)

    def refresh_capture_table(self):
        imported = self.editor.capture_manager.import_pending()
        self.editor.capture_rows = self.editor.capture_store.list_captures()

        if hasattr(self.editor, "capture_table"):
            self.editor.capture_table.setRowCount(len(self.editor.capture_rows))
            for row_index, row in enumerate(self.editor.capture_rows):
                for col_index, (key, _) in enumerate(CaptureStore.COLUMNS):
                    value = row.get(key, "")
                    item = QTableWidgetItem("" if value is None else str(value))
                    self.editor.capture_table.setItem(row_index, col_index, item)

        if imported:
            self.editor.statusBar().showMessage(f"已同步 {imported} 条抓取记录", 4000)
        self.editor._refresh_capture_status()
        self.editor._refresh_structured_views()

    def import_structured_records(self):
        self.editor._save_settings_if_needed(silent=True)
        if self.editor.selected_interface_key == "all":
            QMessageBox.information(self.editor, "录入抓取数据", "请先选择一个具体接口，再执行“录入抓取数据”。")
            return

        raw_imported = self.editor.capture_manager.import_pending()
        protocols = self.editor._get_selected_protocols()
        results = self.editor.structured_importer.import_protocols(protocols)
        self.editor.capture_rows = self.editor.capture_store.list_captures()
        self.refresh_capture_table()

        if not results:
            QMessageBox.information(self.editor, "结构化入库", "当前没有可用的点评接口协议")
            return

        lines = []
        for result in results:
            title = result.get("protocol_name") or result.get("protocol_key") or "未命名接口"
            if result.get("error"):
                lines.append(f"{title}: {result['error']}")
            else:
                lines.append(
                    f"{title}: 命中 {result['matched']}，新增 {result['imported']}，更新 {result['updated']}，失败 {result['failed']}"
                )
        if raw_imported:
            lines.insert(0, f"原始抓包同步 {raw_imported} 条")

        QMessageBox.information(self.editor, "结构化入库", "\n".join(lines))

    def handle_capture_selection_changed(self):
        selected = self.editor.capture_table.selectedItems() if hasattr(self.editor, "capture_table") else []
        if not selected:
            return

        row_index = selected[0].row()
        if row_index >= len(self.editor.capture_rows):
            return

        capture_id = self.editor.capture_rows[row_index]["id"]
        payload = self.editor.capture_store.get_capture(capture_id)
        if not payload:
            return

        detail_text = [
            f"ID: {payload.get('id')}",
            f"时间: {payload.get('created_at')}",
            f"规则: {payload.get('pattern')}",
            f"平台: {payload.get('platform')}",
            f"URL: {payload.get('url')}",
            f"状态码: {payload.get('status_code')}",
            "",
            payload.get("response_text", ""),
        ]
        self.editor.capture_detail_text.setPlainText("\n".join(detail_text))

    def export_capture_excel(self):
        default_name = self.editor.app_settings.get("capture", {}).get("export_default_name", "captures.xlsx")
        filename, _ = QFileDialog.getSaveFileName(
            self.editor,
            "导出 Excel",
            str(Settings.DATA_DIR / default_name),
            "Excel 文件 (*.xlsx)",
        )
        if not filename:
            return

        output = self.editor.capture_store.export_excel(
            filename,
            self.editor.capture_rows or self.editor.capture_store.list_captures(),
        )
        QMessageBox.information(self.editor, "导出成功", f"已导出到:\n{output}")
