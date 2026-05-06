#!/usr/bin/env python3

from __future__ import annotations

import json
import sys

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QShortcut,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.app_settings import AppSettings
from config.settings import Settings
from data.capture_store import CaptureStore
from data.structured_capture import MeituanCaptureImporter, MeituanConfigLoader
from gui.capture.ca_certificate_controller import CaptureCertificateController
from gui.capture.capture_settings_panel import build_capture_settings_page
from gui.capture.data_management_panel import build_data_management_page
from gui.capture.ios_capture_controller import IOSCaptureController
from gui.capture.realtime_capture_controller import RealtimeCaptureController
from gui.capture.realtime_capture_panel import build_realtime_capture_page
from gui.capture.structured_data_controller import StructuredDataController
from integration.http_capture import HttpCaptureManager
from login.auth_service import clear_session as auth_clear_session, is_mock_auth_enabled, login as auth_login
from playright.detail_enricher import (
    AsyncPlaywrightBatchRunner,
    DATASET_CODE as PLAYRIGHT_DATASET_CODE,
    StructuredShopDataset,
    build_run_output_paths,
    write_run_artifacts,
)
from utils.logger import logger

try:
    import qrcode
except Exception:
    qrcode = None


class PlaywrightBatchWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, db_path, records, concurrency=1, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.records = records
        self.concurrency = max(1, int(concurrency or 1))

    def run(self):
        try:
            store = CaptureStore(db_path=self.db_path)
            dataset = StructuredShopDataset(store)
            result_base_dir = Settings.PLAYRIGHT_DIR
            result_base_dir.mkdir(parents=True, exist_ok=True)
            user_data_dir = Settings.PLAYRIGHT_BROWSER_PROFILE_DIR
            run_paths = build_run_output_paths(Settings.PLAYRIGHT_RUNS_DIR)
            runner = AsyncPlaywrightBatchRunner(
                dataset=dataset,
                user_data_dir=user_data_dir,
            )
            summary = runner.run(
                rows=self.records,
                concurrency=self.concurrency,
                artifact_dir=run_paths["run_dir"],
                progress_callback=self._emit_progress,
            )
            write_run_artifacts(run_paths, summary)
            summary["results_file"] = str(run_paths["results_jsonl"])
            summary["summary_file"] = str(run_paths["summary_json"])
            self.completed.emit(summary)
        except Exception as exc:
            logger.exception("Playwright 批量抓取失败")
            self.failed.emit(str(exc))

    def _emit_progress(self, message: str):
        self.progress.emit(message)


class PackageInstallWorker(QThread):
    completed = pyqtSignal(bool, str)

    def __init__(self, command: list[str], success_message: str, parent=None):
        super().__init__(parent)
        self.command = command
        self.success_message = success_message

    def run(self):
        try:
            result = __import__("subprocess").run(
                self.command,
                check=True,
                capture_output=True,
                text=True,
            )
            detail = (result.stdout or "").strip()
            message = self.success_message if not detail else f"{self.success_message}\n\n{detail}"
            self.completed.emit(True, message)
        except Exception as exc:
            self.completed.emit(False, str(exc))


class LoginWindow(QWidget):
    def __init__(self, app_settings=None):
        super().__init__()
        self.app_settings = app_settings or AppSettings.load()
        self.main_window = None
        self.setWindowTitle("DP采集器 登录")
        self.setFixedSize(480, 760)
        self._create_ui()
        self._apply_styles()

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        title = QLabel("DP采集器")
        title.setObjectName("loginTitle")
        subtitle = QLabel("请输入账号密码后进入抓包工作台")
        subtitle.setObjectName("loginSubtitle")

        form_card = QFrame()
        form_card.setObjectName("loginCard")
        form = QVBoxLayout(form_card)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)

        form_title = QLabel("账号登录")
        form_title.setObjectName("loginCardTitle")

        username_label = QLabel("账号")
        username_label.setObjectName("loginFieldLabel")
        password_label = QLabel("密码")
        password_label.setObjectName("loginFieldLabel")

        self.username_entry = QLineEdit()
        self.username_entry.setPlaceholderText("请输入账号")
        self.username_entry.setMinimumHeight(42)
        self.username_entry.setClearButtonEnabled(True)
        self.password_entry = QLineEdit()
        self.password_entry.setPlaceholderText("请输入密码")
        self.password_entry.setMinimumHeight(42)
        self.password_entry.setEchoMode(QLineEdit.Password)
        self.username_entry.returnPressed.connect(self.password_entry.setFocus)
        self.password_entry.returnPressed.connect(self._handle_login)
        self.username_entry.setFocusPolicy(Qt.StrongFocus)
        self.password_entry.setFocusPolicy(Qt.StrongFocus)

        form.addWidget(form_title)
        form.addSpacing(4)
        form.addWidget(username_label)
        form.addWidget(self.username_entry)
        form.addSpacing(20)
        form.addWidget(password_label)
        form.addWidget(self.password_entry)

        self.login_hint = QLabel("开发兜底账号: admin / admin")
        self.login_hint.setObjectName("loginHint")
        self.login_hint.setVisible(is_mock_auth_enabled())

        self.btn_login = QPushButton("登录")
        self.btn_login.clicked.connect(self._handle_login)
        self.btn_login.setDefault(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(form_card)
        layout.addWidget(self.login_hint)
        layout.addStretch()
        layout.addWidget(self.btn_login)

        self.setTabOrder(self.username_entry, self.password_entry)
        self.setTabOrder(self.password_entry, self.btn_login)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #F8FAFC;
                color: #0F172A;
                font-size: 14px;
            }
            QLabel#loginTitle {
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#loginSubtitle {
                color: #475569;
            }
            QLabel#loginCardTitle {
                color: #0F172A;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#loginHint {
                color: #1D4ED8;
                background: #DBEAFE;
                border: 1px solid #BFDBFE;
                border-radius: 10px;
                padding: 10px 12px;
            }
            QLabel#loginFieldLabel {
                color: #334155;
                font-size: 13px;
                font-weight: 700;
                padding-left: 2px;
            }
            QFrame#loginCard {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 16px;
            }
            QLineEdit {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                padding: 10px 12px;
                color: #0F172A;
                selection-background-color: #BFDBFE;
                selection-color: #0F172A;
            }
            QLineEdit::placeholder {
                color: #94A3B8;
            }
            QLineEdit:focus {
                border: 1px solid #2563EB;
            }
            QPushButton {
                background: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                padding: 12px 16px;
                min-height: 44px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #1D4ED8;
            }
            """
        )

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self._focus_username)

    def _focus_username(self):
        self.username_entry.setFocus(Qt.ActiveWindowFocusReason)
        self.username_entry.selectAll()

    def _handle_login(self):
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "登录失败", "请输入账号和密码")
            self.password_entry.setFocus()
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("登录中...")
        QApplication.processEvents()
        try:
            response = auth_login({"username": username, "password": password})
        finally:
            self.btn_login.setEnabled(True)
            self.btn_login.setText("登录")

        if not response.get("success"):
            QMessageBox.warning(self, "登录失败", response.get("message") or "登录失败")
            self.password_entry.clear()
            self.password_entry.setFocus()
            return

        self.app_settings = AppSettings.load()
        self.main_window = CaptureOnlyApp(app_settings=self.app_settings)
        self.main_window.show()
        self.close()


class CaptureOnlyApp(QMainWindow):
    def __init__(self, app_settings=None):
        super().__init__()
        self.setWindowTitle("DP采集器")
        self.setGeometry(80, 50, 1440, 940)

        self.app_settings = app_settings or AppSettings.load()
        self.capture_manager = HttpCaptureManager()
        self.capture_store = self.capture_manager.store
        self.capture_rows = []
        self.protocol_loader = MeituanConfigLoader()
        self.meituan_protocols = []
        self.selected_platform = "meituan"
        self.selected_interface_key = "all"
        self.structured_record_rows = []
        self.structured_importer = MeituanCaptureImporter(self.capture_store)
        self.structured_current_page = 1
        self.structured_page_size = 50
        self.structured_total_pages = 1
        self.structured_total_records = 0
        self.structured_table_updating = False
        self.playwright_worker = None
        self.package_install_worker = None

        self.ios_capture_controller = IOSCaptureController(self)
        self.capture_certificate_controller = CaptureCertificateController(self, qrcode_module=qrcode)
        self.realtime_capture_controller = RealtimeCaptureController(self)
        self.structured_data_controller = StructuredDataController(self)
        self.playwright_worker_factory = PlaywrightBatchWorker

        self._create_ui()
        self._create_menu_bar()
        self._create_shortcuts()
        self._apply_styles()
        self._load_meituan_capture_settings()
        self._load_app_settings_to_form()
        self._refresh_top_info()
        self._refresh_capture_table()

        self.capture_refresh_timer = QTimer(self)
        self.capture_refresh_timer.timeout.connect(self._refresh_capture_table)
        self.capture_refresh_timer.start(3000)
        logger.info("Capture-only 工作台启动")

    def _create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        main_layout.addWidget(self._build_top_info_bar())

        body_layout = QHBoxLayout()
        body_layout.setSpacing(12)
        body_layout.addWidget(self._build_sidebar())
        body_layout.addWidget(self._build_content_stack(), 1)
        main_layout.addLayout(body_layout, 1)
        self.sidebar_menu.setCurrentRow(0)

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件")
        action_export = QAction("导出原始抓取 Excel", self)
        action_export.triggered.connect(self._export_capture_excel)
        action_export_structured = QAction("导出点评结果 Excel", self)
        action_export_structured.triggered.connect(self._export_structured_excel)
        action_exit = QAction("退出", self)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_export)
        file_menu.addAction(action_export_structured)
        file_menu.addSeparator()
        file_menu.addAction(action_exit)

        view_menu = menu_bar.addMenu("视图")
        action_realtime_data = QAction("抓取实时数据", self)
        action_realtime_data.triggered.connect(lambda: self._switch_page("realtime_data"))
        action_data_management = QAction("数据管理", self)
        action_data_management.triggered.connect(lambda: self._switch_page("data_management"))
        action_settings = QAction("抓包配置", self)
        action_settings.triggered.connect(lambda: self._switch_page("settings"))
        view_menu.addActions([action_realtime_data, action_data_management, action_settings])

        tools_menu = menu_bar.addMenu("工具")
        action_start_capture = QAction("启动抓取服务", self)
        action_start_capture.triggered.connect(self._start_capture_service)
        action_stop_capture = QAction("停止抓取服务", self)
        action_stop_capture.triggered.connect(self._stop_capture_service)
        action_sync_capture = QAction("同步抓取数据", self)
        action_sync_capture.triggered.connect(self._refresh_capture_table)
        action_import_structured = QAction("转换点评结果", self)
        action_import_structured.triggered.connect(self._import_structured_records)
        tools_menu.addActions([
            action_start_capture,
            action_stop_capture,
            action_sync_capture,
            action_import_structured,
        ])

    def _create_shortcuts(self):
        self.shortcut_refresh = QShortcut("F5", self)
        self.shortcut_refresh.activated.connect(self._refresh_capture_table)

    def _build_top_info_bar(self):
        container = QFrame()
        container.setObjectName("topInfoBar")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        account_title = QLabel("账号")
        account_title.setObjectName("topInfoLabel")
        self.account_name_label = QLabel("未登录")
        self.account_name_label.setObjectName("topAccountName")
        self.account_name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.logout_button = QPushButton("退出登录")
        self.logout_button.setMinimumHeight(36)
        self.logout_button.clicked.connect(self._logout)

        layout.addWidget(account_title)
        layout.addWidget(self.account_name_label)
        layout.addStretch()
        layout.addWidget(self.logout_button)
        return container

    def _build_sidebar(self):
        self.sidebar_menu = QListWidget()
        self.sidebar_menu.setFixedWidth(180)
        self.sidebar_menu.addItem(QListWidgetItem("抓取实时数据"))
        self.sidebar_menu.addItem(QListWidgetItem("数据管理"))
        self.sidebar_menu.addItem(QListWidgetItem("抓包配置"))
        self.sidebar_menu.currentRowChanged.connect(self._handle_sidebar_changed)
        return self.sidebar_menu

    def _build_content_stack(self):
        self.content_stack = QStackedWidget()
        self.realtime_data_page = build_realtime_capture_page(self)
        self.data_management_page = build_data_management_page(self)
        self.settings_page = build_capture_settings_page(self)

        self.content_stack.addWidget(self.realtime_data_page)
        self.content_stack.addWidget(self.data_management_page)
        self.content_stack.addWidget(self.settings_page)
        return self.content_stack

    def _handle_sidebar_changed(self, index: int):
        self.content_stack.setCurrentIndex(max(0, index))

    def _switch_page(self, page_name: str):
        mapping = {"realtime_data": 0, "data_management": 1, "settings": 2}
        index = mapping.get(page_name, 0)
        self.sidebar_menu.setCurrentRow(index)
        self.content_stack.setCurrentIndex(index)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #F8FAFC;
                color: #0F172A;
                font-size: 13px;
            }
            QPushButton {
                background: #E2E8F0;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: #CBD5E1;
            }
            QPushButton:pressed {
                background: #94A3B8;
            }
            QPushButton:disabled {
                color: #94A3B8;
                background: #F1F5F9;
            }
            QLineEdit, QComboBox {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QTextEdit, QPlainTextEdit, QTableWidget, QListWidget {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 12px;
            }
            QListWidget::item {
                padding: 12px 14px;
                border-radius: 10px;
                margin: 4px;
            }
            QListWidget::item:selected {
                background: #DBEAFE;
                color: #1D4ED8;
                font-weight: 700;
            }
            QHeaderView::section {
                background: #E2E8F0;
                border: none;
                padding: 8px;
                font-weight: 600;
            }
            QFrame#captureHeroCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #EFF6FF, stop:1 #F8FAFC);
                border: 1px solid #BFDBFE;
                border-radius: 18px;
            }
            QLabel#captureHeroTitle {
                font-size: 20px;
                font-weight: 700;
                color: #0F172A;
            }
            QFrame#captureStepCard {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 18px;
            }
            QLabel#captureStepBadge {
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                border-radius: 14px;
                background: #DBEAFE;
                color: #1D4ED8;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }
            QLabel#captureStepTitle {
                font-size: 16px;
                font-weight: 700;
                color: #0F172A;
            }
            QLabel#captureStepStatus {
                background: #F1F5F9;
                border: 1px solid #CBD5E1;
                border-radius: 999px;
                padding: 6px 10px;
                color: #334155;
                font-weight: 600;
            }
            QLabel#captureInlineMeta {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 10px 12px;
            }
            QFrame#topInfoBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F8FAFC, stop:1 #EFF6FF);
                border: 1px solid #D8E3F0;
                border-radius: 16px;
                padding: 12px 16px;
            }
            QLabel#topInfoLabel {
                color: #475467;
                font-weight: 600;
                padding-right: 2px;
            }
            QLabel#topAccountName {
                color: #0F172A;
                font-size: 16px;
                font-weight: 700;
                padding: 2px 0;
            }
            QFrame#dataHeroCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ECFDF5, stop:0.5 #F0FDF4, stop:1 #EFF6FF);
                border: 1px solid #BBF7D0;
                border-radius: 20px;
            }
            QLabel#dataHeroTitle {
                font-size: 22px;
                font-weight: 700;
                color: #064E3B;
            }
            QLabel#dataHeroSubtitle {
                color: #166534;
            }
            QLabel#dataBadge {
                background: #FFFFFF;
                border: 1px solid #D1FAE5;
                border-radius: 999px;
                padding: 7px 12px;
                color: #065F46;
                font-weight: 600;
            }
            QLabel#dataInfo {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                padding: 12px 14px;
                color: #334155;
            }
            """
        )

    def _logout(self):
        confirmed = QMessageBox.question(
            self,
            "退出登录",
            "确认退出当前登录状态吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmed != QMessageBox.Yes:
            return

        auth_clear_session()
        self.app_settings = AppSettings.load()
        self.login_window = LoginWindow(app_settings=self.app_settings)
        self.login_window.show()
        self.close()

    def _load_app_settings_to_form(self):
        capture = self.app_settings.get("capture", {})
        self.capture_enabled_checkbox.setChecked(bool(capture.get("enabled", False)))
        self.capture_platform_combo.blockSignals(True)
        self.capture_platform_combo.clear()
        self.capture_platform_combo.addItem("ios")
        self.capture_platform_combo.setCurrentText("ios")
        self.capture_platform_combo.setEnabled(False)
        self.capture_platform_combo.blockSignals(False)
        self.capture_android_proxy_checkbox.setChecked(False)
        self._refresh_capture_status()
        self._refresh_capture_platform_ui()

    def _collect_capture_settings_from_form(self):
        current_capture = self.app_settings.get("capture", {})
        return {
            "enabled": self.capture_enabled_checkbox.isChecked(),
            "tool": "mitmproxy",
            "listen_host": current_capture.get("listen_host", "0.0.0.0") or "0.0.0.0",
            "listen_port": int(current_capture.get("listen_port", 8081) or 8081),
            "asset_port": int(current_capture.get("asset_port", 8765) or 8765),
            "patterns_text": self._get_selected_patterns_text(),
            "platform": self.capture_platform_combo.currentText(),
            "android_proxy_auto_apply": False,
            "ios_proxy_manual": True,
            "max_body_kb": int(current_capture.get("max_body_kb", 512) or 512),
            "export_default_name": current_capture.get("export_default_name", "captures.xlsx"),
        }

    def _load_meituan_capture_settings(self):
        data_capture = self.app_settings.get("data_capture", {})
        self.selected_platform = data_capture.get("selected_platform", "meituan") or "meituan"
        self.selected_interface_key = data_capture.get("selected_interface_key", "all") or "all"
        self.meituan_protocols = self.protocol_loader.list_protocols()
        self._refresh_interface_selector()
        self._refresh_capture_rule_summary()
        self._refresh_protocol_summary()
        self._refresh_structured_views()

    def _collect_data_capture_settings(self):
        return {
            "selected_platform": self.selected_platform,
            "selected_interface_key": self.selected_interface_key,
            "structured_export_name": self.app_settings.get("data_capture", {}).get("structured_export_name", "dianping_shop.xlsx"),
        }

    def _get_capture_platform(self) -> str:
        if hasattr(self, "capture_platform_combo"):
            value = self.capture_platform_combo.currentText().strip()
            if value:
                return value
        return self.app_settings.get("capture", {}).get("platform", "ios") or "ios"

    def _refresh_capture_platform_ui(self):
        self.ios_capture_controller.apply_platform_ui()

    def _refresh_capture_rule_summary(self):
        if not hasattr(self, "capture_rules_summary_label"):
            return

        selected = self._get_selected_protocols()
        if not selected:
            self.capture_rules_summary_label.setText("抓包接口: 未配置")
            return
        if self.selected_interface_key == "all":
            names = " / ".join(protocol["name"] for protocol in selected)
            self.capture_rules_summary_label.setText(f"抓包接口: 全部点评接口 ({names})")
        else:
            self.capture_rules_summary_label.setText(f"抓包接口: {selected[0]['name']}")

    def _refresh_interface_selector(self):
        if not hasattr(self, "capture_interface_combo"):
            return

        selected_key = self.selected_interface_key or "all"
        self.capture_interface_combo.blockSignals(True)
        self.capture_interface_combo.clear()
        self.capture_interface_combo.addItem("全部点评接口", "all")
        for protocol in self.meituan_protocols:
            self.capture_interface_combo.addItem(protocol["name"], protocol["key"])

        current_index = 0
        for index in range(self.capture_interface_combo.count()):
            if self.capture_interface_combo.itemData(index) == selected_key:
                current_index = index
                break
        self.capture_interface_combo.setCurrentIndex(current_index)
        self.capture_interface_combo.blockSignals(False)
        self.selected_interface_key = selected_key

    def _handle_interface_selection_changed(self, index: int):
        if index < 0:
            return
        self.selected_interface_key = self.capture_interface_combo.itemData(index) or "all"
        self._save_capture_rules()
        self._refresh_protocol_summary()
        self._refresh_structured_views()

    def _get_selected_protocols(self):
        if self.selected_interface_key == "all":
            return [protocol for protocol in self.meituan_protocols if protocol.get("enabled", True)]
        return [
            protocol
            for protocol in self.meituan_protocols
            if protocol.get("enabled", True) and protocol["key"] == self.selected_interface_key
        ]

    def _get_selected_patterns_text(self):
        patterns = [protocol.get("url_pattern", "").strip() for protocol in self._get_selected_protocols() if protocol.get("url_pattern", "").strip()]
        return "\n".join(patterns)

    def _get_selected_entity_code(self):
        protocols = self._get_selected_protocols()
        if not protocols:
            return ""
        return protocols[0].get("entity_code", "")

    def _refresh_protocol_summary(self):
        return

    def _refresh_top_info(self):
        auth = self.app_settings.get("auth", {})
        admin = auth.get("admin", {}) if isinstance(auth, dict) else {}
        account = self.app_settings.get("account", {})
        display_name = admin.get("nickname") or account.get("display_name") or "未登录"
        username = admin.get("username") or "-"
        admin_id = admin.get("id") or account.get("account_id") or "-"
        if AppSettings.is_auth_valid(self.app_settings):
            self.account_name_label.setText(display_name)
            self.account_name_label.setToolTip(f"账号: {display_name}\n用户名: {username}\nID: {admin_id}")
        else:
            self.account_name_label.setText("未登录")
            self.account_name_label.setToolTip("登录已失效，请重新登录")

    def _show_data_operation_help(self):
        self.realtime_capture_controller.show_data_operation_help()

    def _show_data_management_help(self):
        self.structured_data_controller.show_data_management_help()

    def _save_capture_rules(self):
        return self.realtime_capture_controller.save_capture_rules()

    def _clear_temporary_capture_data(self):
        self.realtime_capture_controller.clear_temporary_capture_data()

    def _refresh_capture_status(self):
        self.capture_certificate_controller.refresh_capture_status()

    def _start_ca_service(self):
        self.capture_certificate_controller.start_ca_service()

    def _stop_ca_service(self):
        self.capture_certificate_controller.stop_ca_service()

    def _start_capture_service(self):
        self._save_settings_if_needed(silent=True)
        capture = self.app_settings.get("capture", {})
        success, message = self.capture_manager.start(capture)
        self._refresh_capture_status()
        if success:
            self.statusBar().showMessage(message, 4000)
            QTimer.singleShot(1500, self._refresh_capture_status)
        else:
            if "mitmdump" in message and not getattr(sys, "frozen", False):
                reply = QMessageBox.question(
                    self,
                    "抓取服务",
                    f"{message}\n\n是否立即在当前 Python 环境安装 mitmproxy？\n\n{sys.executable} -m pip install mitmproxy",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    self._install_mitmproxy_runtime()
            else:
                QMessageBox.warning(self, "抓取服务", message)

    def _stop_proxy_capture_only(self):
        _, capture_message = self.capture_manager.stop()
        self._refresh_capture_status()
        QMessageBox.information(self, "已停止抓包", capture_message)
        return True

    def _stop_proxy_capture_and_clear_proxy(self):
        _, capture_message = self.capture_manager.stop()
        self._refresh_capture_status()
        QMessageBox.information(
            self,
            "已停止抓包",
            f"{capture_message}\n当前为 iOS 手动抓包模式，请在设备上手动关闭 Wi-Fi 代理。",
        )
        return True

    def _stop_capture_service(self):
        _, message = self.capture_manager.stop()
        self._refresh_capture_status()
        self.statusBar().showMessage(message, 4000)

    def _quick_setup_android_capture(self):
        QMessageBox.information(self, "iOS 手动抓包", "当前精简版仅保留 iOS 手动抓包流程。")

    def _apply_android_proxy_settings(self, silent: bool = False):
        _ = silent
        self.ios_capture_controller.show_ios_mode_apply_proxy_hint()
        return False

    def _clear_android_proxy_settings(self):
        self.ios_capture_controller.show_ios_mode_clear_proxy_hint()
        return False

    def _detect_android_proxy_settings(self):
        self.ios_capture_controller.show_ios_mode_detect_proxy_hint()
        return False

    def _test_android_proxy_connectivity(self):
        return self._show_capture_https_diagnosis()

    def _refresh_device_proxy_status(self):
        if hasattr(self, "capture_proxy_step_status"):
            self.capture_proxy_step_status.setText("iOS 手动配置")
        if hasattr(self, "capture_device_proxy_summary_label"):
            self.capture_device_proxy_summary_label.setText("手机代理: iOS 不支持自动检测")

    def _refresh_capture_table(self):
        self.realtime_capture_controller.refresh_capture_table()

    def _refresh_structured_views(self, reset_page: bool = False):
        self.structured_data_controller.refresh_structured_views(reset_page=reset_page)

    def _apply_structured_filters(self):
        self.structured_data_controller.apply_structured_filters()

    def _reset_structured_filters(self):
        self.structured_data_controller.reset_structured_filters()

    def _change_structured_page(self, delta: int):
        self.structured_data_controller.change_structured_page(delta)

    def _handle_structured_selection_changed(self):
        self.structured_data_controller.handle_structured_selection_changed()

    def _start_playwright_phone_fetch(self):
        self.structured_data_controller.start_playwright_phone_fetch()

    def _install_playwright_runtime(self):
        self._run_package_install(
            command=[sys.executable, "-m", "playwright", "install", "chromium"],
            success_message="浏览器运行时安装完成。",
            title="安装浏览器运行时",
        )

    def _install_mitmproxy_runtime(self):
        if getattr(sys, "frozen", False):
            QMessageBox.information(
                self,
                "安装 mitmproxy",
                "正式打包版不再通过应用内执行 pip 安装 mitmproxy。\n\n请直接使用包内抓包组件；如果仍提示缺失，请重新打包或重新安装当前应用。",
            )
            return
        self._run_package_install(
            command=[sys.executable, "-m", "pip", "install", "mitmproxy"],
            success_message="mitmproxy 安装完成。",
            title="安装 mitmproxy",
        )

    def _run_package_install(self, command: list[str], success_message: str, title: str):
        if self.package_install_worker and self.package_install_worker.isRunning():
            QMessageBox.information(self, title, "已有安装任务正在执行，请稍候。")
            return

        self.statusBar().showMessage(f"{title}中...", 0)
        self.package_install_worker = PackageInstallWorker(command, success_message, self)
        self.package_install_worker.completed.connect(lambda ok, message: self._handle_package_install_completed(title, ok, message))
        self.package_install_worker.start()

    def _handle_package_install_completed(self, title: str, success: bool, message: str):
        self.package_install_worker = None
        self.statusBar().clearMessage()
        if success:
            QMessageBox.information(self, title, message)
            self._refresh_capture_status()
        else:
            QMessageBox.warning(self, title, message)

    def _import_structured_records(self):
        self.realtime_capture_controller.import_structured_records()

    def _handle_capture_selection_changed(self):
        self.realtime_capture_controller.handle_capture_selection_changed()

    def _export_capture_excel(self):
        self.realtime_capture_controller.export_capture_excel()

    def _export_structured_excel(self):
        self.structured_data_controller.export_structured_excel()

    def _show_capture_https_diagnosis(self):
        return self.capture_certificate_controller.show_https_diagnosis()

    def _save_app_settings(self):
        self._save_settings_if_needed(silent=False)
        QMessageBox.information(self, "成功", "抓包配置已保存")

    def _save_settings_if_needed(self, silent: bool = False):
        self.app_settings.setdefault("account", {
            "display_name": "未登录",
            "account_id": "",
            "workspace": "默认工作区",
        })
        self.app_settings.setdefault("auth", {
            "token": "",
            "expires_at": 0,
            "timestamp": "",
            "admin": {},
        })
        self.app_settings["capture"] = self._collect_capture_settings_from_form()
        self.app_settings["data_capture"] = self._collect_data_capture_settings()
        self.app_settings["adb"] = {
            "adb_path": "",
            "remote_address": "",
            "pair_address": "",
            "proxy_backup": "",
            "last_applied_proxy": "",
        }
        AppSettings.save(self.app_settings)
        self._refresh_top_info()
        self._refresh_capture_status()
        self._refresh_capture_rule_summary()
        if not silent:
            self.statusBar().showMessage("抓包配置已保存", 3000)


def main():
    app = QApplication.instance() or QApplication([])
    settings = AppSettings.load()
    if AppSettings.is_auth_valid(settings):
        window = CaptureOnlyApp(app_settings=settings)
    else:
        window = LoginWindow(app_settings=settings)
    window.show()
    return app.exec_()
