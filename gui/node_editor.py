#!/usr/bin/env python3
"""
Canvas 节点编辑器主界面
使用 PyQt5 构建可拖拽流程编排 GUI
"""

import os
import sys
import json
import io
import time
import secrets
import subprocess
import string
from pathlib import Path

from PyQt5.QtCore import QLineF, QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QKeySequence, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QDialog,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QShortcut,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger
from config.settings import Settings
from config.app_settings import AppSettings
from core.screen_capture import ScreenCapture
from core.adb_device import ADBDevice
from data.capture_store import CaptureStore
from data.structured_capture import MeituanCaptureImporter, MeituanConfigLoader
from gui.capture import (
    AndroidAdbController,
    AndroidProxyController,
    CaptureCertificateController,
    IOSCaptureController,
    RealtimeCaptureController,
    StructuredDataController,
    build_adb_group,
    build_data_management_page,
    build_capture_settings_page,
    build_realtime_capture_page,
)
from gui.screenshot_tool import ScreenshotTool
from integration.http_capture import HttpCaptureManager
from login.auth_service import clear_session as auth_clear_session, is_mock_auth_enabled, login as auth_login, verify_auth
from playright.detail_enricher import (
    AsyncPlaywrightBatchRunner,
    DATASET_CODE as PLAYRIGHT_DATASET_CODE,
    StructuredShopDataset,
    build_run_output_paths,
    write_run_artifacts,
)

try:
    import qrcode
except Exception:
    qrcode = None


NODE_TYPE_COLORS = {
    "start": QColor("#15803D"),
    "click": QColor("#0F766E"),
    "verify": QColor("#1D4ED8"),
    "wait": QColor("#7C3AED"),
    "swipe": QColor("#EA580C"),
    "function": QColor("#BE185D"),
    "end": QColor("#334155"),
}

EDGE_COLORS = {
    "next_node": QColor("#16A34A"),
    "failure_node": QColor("#DC2626"),
}

class FlowConnectionItem(QGraphicsPathItem):
    """节点间的连线"""

    def __init__(self, source_item, target_item, field_name: str, on_rewire_requested=None):
        super().__init__()
        self.source_item = source_item
        self.target_item = target_item
        self.field_name = field_name
        self.on_rewire_requested = on_rewire_requested
        self.label_item = QGraphicsSimpleTextItem(self._label_text(), self)
        self.label_item.setBrush(QBrush(QColor("#111827")))
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)
        self.update_path()

    def _label_text(self) -> str:
        return "success" if self.field_name == "next_node" else "failure"

    def update_path(self):
        """更新路径和标签位置"""
        start = self.source_item.connection_point("output", self.field_name)
        end = self.target_item.connection_point("input")
        dx = max(80, abs(end.x() - start.x()) * 0.5)

        path = QPainterPath(start)
        path.cubicTo(
            start.x() + dx, start.y(),
            end.x() - dx, end.y(),
            end.x(), end.y(),
        )

        self.setPath(path)
        self._apply_pen()

        midpoint = path.pointAtPercent(0.5)
        self.label_item.setPos(midpoint.x() - 24, midpoint.y() - 18)

    def _apply_pen(self):
        width = 4.0 if self.isSelected() else 2.5
        pen = QPen(EDGE_COLORS[self.field_name], width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(14.0)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        self._apply_pen()
        super().paint(painter, option, widget)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.on_rewire_requested:
            self.on_rewire_requested(self, event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)


class FlowPreviewConnectionItem(QGraphicsPathItem):
    """连线预览"""

    def __init__(self, source_item, field_name: str):
        super().__init__()
        self.source_item = source_item
        self.field_name = field_name
        self.target_point = source_item.connection_point("output", field_name)
        self.setZValue(-1)
        self.setPen(QPen(EDGE_COLORS[field_name], 2, Qt.DashLine))
        self.update_path(self.target_point)

    def update_path(self, target_point: QPointF):
        """更新预览路径"""
        self.target_point = target_point
        start = self.source_item.connection_point("output", self.field_name)
        end = target_point
        dx = max(80.0, abs(end.x() - start.x()) * 0.5)

        path = QPainterPath(start)
        path.cubicTo(
            start.x() + dx, start.y(),
            end.x() - dx, end.y(),
            end.x(), end.y(),
        )
        self.setPath(path)


class FlowNodeItem(QGraphicsObject):
    """画布中的节点卡片"""

    clicked = pyqtSignal(str)
    double_clicked = pyqtSignal(str, int, str)
    moved = pyqtSignal(str)

    WIDTH = 220
    HEIGHT = 108

    def __init__(self, node: dict):
        super().__init__()
        self.node = node
        self.node_id = node["id"]
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        base = NODE_TYPE_COLORS.get(self.node.get("type", "click"), QColor("#334155"))
        border = QColor(base)
        fill = QColor(base)
        fill.setAlpha(36)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(border, 3 if self.isSelected() else 2))
        painter.drawRoundedRect(rect, 16, 16)

        header_rect = QRectF(0, 0, rect.width(), 34)
        header = QColor(base)
        header.setAlpha(220)
        painter.setBrush(QBrush(header))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(header_rect, 16, 16)
        painter.drawRect(QRectF(0, 17, rect.width(), 17))

        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(14, 8, 160, 20), Qt.AlignLeft | Qt.AlignVCenter, self.node.get("type", "node").upper())
        painter.drawText(QRectF(170, 8, 36, 20), Qt.AlignRight | Qt.AlignVCenter, self.node_id.split("_")[-1])

        painter.setPen(QColor("#0F172A"))
        painter.drawText(QRectF(14, 42, rect.width() - 28, 24), Qt.AlignLeft | Qt.AlignVCenter, self.node.get("name", "未命名节点"))

        template_text = self._detail_text()
        painter.setPen(QColor("#475569"))
        painter.drawText(QRectF(14, 68, rect.width() - 28, 18), Qt.AlignLeft | Qt.AlignVCenter, template_text[:32])

        tags = self._build_tags()
        painter.setPen(QColor("#334155"))
        painter.drawText(QRectF(14, 88, rect.width() - 28, 14), Qt.AlignLeft | Qt.AlignVCenter, " | ".join(tags) if tags else "未连线")

        if self.node.get("type") == "verify":
            self._draw_verify_ports(painter, rect)

    def _detail_text(self) -> str:
        node_type = self.node.get("type", "click")
        if node_type == "start":
            next_node = self.node.get("next_node") or "未连接"
            return f"入口: {next_node}"
        if node_type == "click":
            template = self.node.get("template") or "未配置模板"
            return f"模板: {template}"
        if node_type == "verify":
            template = self.node.get("template") or "未配置模板"
            timeout = self.node.get("timeout", 0)
            if timeout and float(timeout) > 0:
                return f"判断: {template} ({timeout}s)"
            return f"判断: {template} (即时)"
        if node_type == "wait":
            wait_min = self.node.get("wait_min")
            wait_max = self.node.get("wait_max")
            if wait_min is None and wait_max is None:
                return "等待: 未配置"
            if wait_min == wait_max or wait_max is None:
                return f"等待: {wait_min}s"
            if wait_min is None:
                return f"等待: {wait_max}s"
            return f"等待: {wait_min}-{wait_max}s"
        if node_type == "swipe":
            stop_template = self.node.get("stop_template")
            rules = [line for line in (self.node.get("stop_rules_text") or "").splitlines() if line.strip()]
            if stop_template:
                return f"停止: {stop_template}"
            if rules:
                return f"停止规则: {len(rules)} 条"
            return "停止: 最大次数"
        if node_type == "function":
            function_path = self.node.get("function_path") or "未配置函数"
            return f"函数: {function_path}"
        if node_type == "end":
            message = self.node.get("end_message") or "流程结束"
            return f"结束: {message}"
        return "未配置"

    def _build_tags(self):
        tags = []
        node_type = self.node.get("type")
        if self.node.get("is_start") or node_type == "start":
            tags.append("START")
        if self.node.get("is_init"):
            tags.append("INIT")
        if node_type == "function":
            tags.append("FUNC")
        if node_type == "end":
            tags.append("END")
        if self.node.get("next_node"):
            tags.append("S")
        if self.node.get("failure_node"):
            tags.append("F")
        return tags

    def _draw_verify_ports(self, painter: QPainter, rect: QRectF):
        success_point = self._local_connection_point("output", "next_node")
        failure_point = self._local_connection_point("output", "failure_node")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#16A34A"))
        painter.drawEllipse(success_point, 4.5, 4.5)
        painter.setBrush(QColor("#DC2626"))
        painter.drawEllipse(failure_point, 4.5, 4.5)

        painter.setPen(QColor("#166534"))
        painter.drawText(
            QRectF(rect.width() - 58, success_point.y() - 10, 42, 14),
            Qt.AlignRight | Qt.AlignVCenter,
            "YES",
        )
        painter.setPen(QColor("#991B1B"))
        painter.drawText(
            QRectF(rect.width() - 52, failure_point.y() - 10, 36, 14),
            Qt.AlignRight | Qt.AlignVCenter,
            "NO",
        )

    def _verify_output_hit_rect(self, field_name: str) -> QRectF:
        point = self._local_connection_point("output", field_name)
        return QRectF(point.x() - 42, point.y() - 12, 48, 24)

    def _preferred_connection_field(self, local_pos: QPointF) -> str:
        if self.node.get("type") != "verify":
            return ""
        if self._verify_output_hit_rect("next_node").contains(local_pos):
            return "next_node"
        if self._verify_output_hit_rect("failure_node").contains(local_pos):
            return "failure_node"
        return ""

    def mousePressEvent(self, event):
        self.clicked.emit(self.node_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.clicked.emit(self.node_id)
        self.double_clicked.emit(
            self.node_id,
            int(event.modifiers()),
            self._preferred_connection_field(event.pos()),
        )
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.moved.emit(self.node_id)
        return super().itemChange(change, value)

    def _local_connection_point(self, side: str, field_name: str = None) -> QPointF:
        rect = self.boundingRect()
        center_y = rect.center().y()

        if side in {"left", "input"}:
            return QPointF(rect.left(), center_y)

        if self.node.get("type") == "verify":
            if field_name == "next_node":
                center_y -= 18
            elif field_name == "failure_node":
                center_y += 18

        return QPointF(rect.right(), center_y)

    def connection_point(self, side: str, field_name: str = None) -> QPointF:
        return self.mapToScene(self._local_connection_point(side, field_name))


class NodeCanvasView(QGraphicsView):
    """支持缩放和平移的画布"""

    scene_mouse_moved = pyqtSignal(QPointF)
    background_clicked = pyqtSignal(QPointF)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._panning = False
        self._pan_start = None
        self._zoom_min = 0.35
        self._zoom_max = 2.8
        self._connection_preview_active = False
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QColor("#F8FAFC"))
        self.setSceneRect(-2400, -2400, 4800, 4800)

    def set_connection_preview_active(self, active: bool):
        """设置是否处于连线预览模式"""
        self._connection_preview_active = active

    def wheelEvent(self, event):
        scale_factor = 1.12 if event.angleDelta().y() > 0 else 0.9
        current_scale = self.transform().m11()
        next_scale = current_scale * scale_factor
        if next_scale < self._zoom_min or next_scale > self._zoom_max:
            event.accept()
            return
        self.scale(scale_factor, scale_factor)
        event.accept()

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        item = self.itemAt(event.pos())

        if event.button() == Qt.LeftButton and item is None:
            if self._connection_preview_active:
                self.background_clicked.emit(scene_pos)
                event.accept()
                return
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.scene_mouse_moved.emit(self.mapToScene(event.pos()))
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)
        left = int(rect.left()) - (int(rect.left()) % 40)
        top = int(rect.top()) - (int(rect.top()) % 40)
        grid_pen = QPen(QColor("#E2E8F0"), 1)
        painter.setPen(grid_pen)

        x = left
        while x < rect.right():
            painter.drawLine(QLineF(float(x), rect.top(), float(x), rect.bottom()))
            x += 40

        y = top
        while y < rect.bottom():
            painter.drawLine(QLineF(rect.left(), float(y), rect.right(), float(y)))
            y += 40


class LoginWindow(QWidget):
    """登录入口"""

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
        subtitle = QLabel("请输入账号密码后进入主页面")
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
        self.main_window = NodeEditorApp(app_settings=self.app_settings)
        self.main_window.show()
        self.close()


class AdbQrPairDialog(QDialog):
    """ADB 二维码配对弹窗"""

    def __init__(self, adb_path: str, parent=None):
        super().__init__(parent)
        self.adb_path = adb_path
        self.connected_address = ""
        self.service_name = self._build_service_name()
        self.password = self._build_password()
        self.qr_payload = f"WIFI:T:ADB;S:{self.service_name};P:{self.password};;"
        self._busy = False
        self._paired = False
        self._pair_ip = ""
        self._attempt_count = 0
        self._last_status_text = ""

        self.setWindowTitle("二维码配对 ADB")
        self.setModal(True)
        self.resize(420, 520)
        self._create_ui()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_services)
        self.poll_timer.start(1800)
        self._update_status("等待手机扫码二维码并确认无线调试配对...")

    @staticmethod
    def _build_service_name() -> str:
        alphabet = string.ascii_letters + string.digits + "@<>()[]{}+-_=:/.*"
        suffix = "".join(secrets.choice(alphabet) for _ in range(10))
        return f"studio-{suffix}"

    @staticmethod
    def _build_password() -> str:
        alphabet = string.ascii_letters + string.digits + "()[]{}<>!@#$%^&*+-_=:/."
        return "".join(secrets.choice(alphabet) for _ in range(12))

    def _create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("请用 Android 手机扫描此二维码")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        title.setAlignment(Qt.AlignCenter)

        desc = QLabel(
            "手机路径: 开发者选项 -> 无线调试 -> 使用二维码配对设备\n"
            "扫码后本窗口会自动发现配对服务并执行连接。"
        )
        desc.setWordWrap(True)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(280, 280)

        if qrcode is None:
            self.qr_label.setText("未安装 qrcode，无法生成二维码")
        else:
            image = qrcode.make(self.qr_payload)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue(), "PNG")
            self.qr_label.setPixmap(pixmap.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.meta_label = QLabel(
            f"服务名: {self.service_name}\n密码: {self.password}"
        )
        self.meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meta_label.setStyleSheet("background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 10px; padding: 10px;")

        self.status_label = QLabel("准备中...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 10px;")

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.qr_label, 0, Qt.AlignCenter)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(btn_close, 0, Qt.AlignRight)

    def _update_status(self, text: str):
        if text != self._last_status_text:
            self.status_label.setText(text)
            self._last_status_text = text

    def _poll_services(self):
        if self._busy:
            return

        self._busy = True
        try:
            self._attempt_count += 1
            services = ADBDevice.list_mdns_services(self.adb_path)
            if not self._paired:
                self._poll_pairing_service(services)
            else:
                self._poll_connect_service(services)
        finally:
            self._busy = False

    def _poll_pairing_service(self, services):
        service = next(
            (item for item in services if item.get("type") == "_adb-tls-pairing._tcp" and item.get("name") == self.service_name),
            None,
        )
        if not service:
            dots = "." * ((self._attempt_count % 3) + 1)
            self._update_status(f"等待手机扫码二维码并打开配对服务{dots}")
            return

        self._update_status(f"已发现配对服务: {service['address']}，正在执行配对...")
        success, output = ADBDevice.pair_remote(service["address"], self.password, adb_path=self.adb_path)
        if not success:
            self._update_status(f"已发现配对服务，但配对失败: {output or '未知错误'}\n请确认手机端已扫码并允许配对。")
            return

        self._paired = True
        self._pair_ip = service["address"].split(":", 1)[0]
        self._update_status("二维码配对成功，正在等待设备发布无线调试连接地址...")
        self._poll_connect_service(services)

    def _poll_connect_service(self, services):
        connect_service = next(
            (
                item for item in services
                if item.get("type") == "_adb-tls-connect._tcp"
                and item.get("address", "").startswith(f"{self._pair_ip}:")
            ),
            None,
        )
        if not connect_service:
            self._update_status("已完成配对，正在等待无线调试连接服务出现...")
            return

        success, output = ADBDevice.connect_remote(connect_service["address"], adb_path=self.adb_path)
        if not success:
            self._update_status(f"已找到连接服务，但连接失败: {output or '未知错误'}")
            return

        self.connected_address = connect_service["address"]
        self._update_status(f"配对并连接成功: {self.connected_address}")
        self.poll_timer.stop()
        QTimer.singleShot(600, self.accept)

    def reject(self):
        if hasattr(self, "poll_timer"):
            self.poll_timer.stop()
        super().reject()


class PlaywrightBatchWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        db_path: Path,
        records: list[dict],
        concurrency: int,
        sleep_min: float = 2.0,
        sleep_max: float = 5.0,
        parent=None,
    ):
        super().__init__(parent)
        self.db_path = Path(db_path)
        self.records = [item for item in (records or []) if item and item.get("record_key")]
        self.concurrency = max(1, int(concurrency or 1))
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max

    def run(self):
        try:
            total = len(self.records)
            self.progress.emit(f"开始抓取电话数据，本次执行 {total} 家，并发 {self.concurrency} tab")
            store = CaptureStore(db_path=self.db_path)
            dataset = StructuredShopDataset(store, dataset_code=PLAYRIGHT_DATASET_CODE)
            artifact_paths = build_run_output_paths(Settings.DATA_DIR / "playright")
            runner = AsyncPlaywrightBatchRunner(
                dataset=dataset,
                user_data_dir=Settings.DATA_DIR / "playright" / "browser_profile",
                headless=False,
            )
            summary = runner.run(
                rows=self.records,
                concurrency=self.concurrency,
                stop_on_blocked=False,
                sleep_range=(self.sleep_min, self.sleep_max),
                artifact_dir=artifact_paths["run_dir"],
                progress_callback=self.progress.emit,
            )
            write_run_artifacts(artifact_paths, summary)
            summary["results_file"] = str(artifact_paths["results_jsonl"])
            summary["summary_file"] = str(artifact_paths["summary_json"])
            self.completed.emit(summary)
        except Exception as exc:
            logger.error(f"Playwright 批量抓取失败: {exc}", exc_info=True)
            self.failed.emit(str(exc))


class NodeEditorApp(QMainWindow):
    """Canvas 节点编辑器主应用"""

    def __init__(self, app_settings=None):
        super().__init__()
        self.setWindowTitle("DP采集器")
        self.setGeometry(60, 40, 1640, 980)

        self.nodes = []
        self.node_map = {}
        self.node_items = {}
        self.connection_items = []
        self.current_node_id = None
        self.pending_connection = None
        self.preview_connection_item = None
        self.last_scene_mouse_pos = QPointF(0, 0)
        self.form_rows = {}
        self.form_labels = {}
        self.config_file = Settings.NODES_CONFIG
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

        self.screen_capture = ScreenCapture()
        self.screenshot_tool = ScreenshotTool(self.screen_capture, str(Settings.TEMPLATE_DIR))
        self.adb_device = None
        self.android_adb_controller = AndroidAdbController(self)
        self.android_proxy_controller = AndroidProxyController(self)
        self.ios_capture_controller = IOSCaptureController(self)
        self.capture_certificate_controller = CaptureCertificateController(self, qrcode_module=qrcode)
        self.realtime_capture_controller = RealtimeCaptureController(self)
        self.structured_data_controller = StructuredDataController(self)
        self.playwright_worker_factory = PlaywrightBatchWorker
        self.device_proxy_panel = None
        self.device_proxy_dialog = None

        self._create_ui()
        self._create_menu_bar()
        self._create_shortcuts()
        self._apply_styles()
        self._load_config()
        self._ensure_device_proxy_panel_initialized()
        self._load_app_settings_to_form()
        self._refresh_top_info()
        self._refresh_capture_table()
        self.capture_refresh_timer = QTimer(self)
        self.capture_refresh_timer.timeout.connect(self._refresh_capture_table)
        self.capture_refresh_timer.start(3000)
        logger.info("Canvas 节点编辑器启动")

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
        action_save = QAction("保存节点配置", self)
        action_save.triggered.connect(self._save_config)
        action_export = QAction("导出原始抓取 Excel", self)
        action_export.triggered.connect(self._export_capture_excel)
        action_export_structured = QAction("导出点评结果 Excel", self)
        action_export_structured.triggered.connect(self._export_structured_excel)
        action_exit = QAction("退出", self)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_save)
        file_menu.addAction(action_export)
        file_menu.addAction(action_export_structured)
        file_menu.addSeparator()
        file_menu.addAction(action_exit)

        view_menu = menu_bar.addMenu("视图")
        action_workflow = QAction("节点编排", self)
        action_workflow.triggered.connect(lambda: self._switch_page("workflow"))
        action_realtime_data = QAction("抓取实时数据", self)
        action_realtime_data.triggered.connect(lambda: self._switch_page("realtime_data"))
        action_data_management = QAction("数据管理", self)
        action_data_management.triggered.connect(lambda: self._switch_page("data_management"))
        action_settings = QAction("抓包配置", self)
        action_settings.triggered.connect(lambda: self._switch_page("settings"))
        view_menu.addActions([action_workflow, action_realtime_data, action_data_management, action_settings])

        tools_menu = menu_bar.addMenu("工具")
        action_refresh_devices = QAction("刷新 ADB 设备", self)
        action_refresh_devices.triggered.connect(self._refresh_devices)
        action_download_adb = QAction("下载 ADB 工具", self)
        action_download_adb.triggered.connect(self._download_adb_tools)
        action_start_capture = QAction("启动抓取服务", self)
        action_start_capture.triggered.connect(self._start_capture_service)
        action_stop_capture = QAction("停止抓取服务", self)
        action_stop_capture.triggered.connect(self._stop_capture_service)
        action_sync_capture = QAction("同步抓取数据", self)
        action_sync_capture.triggered.connect(self._refresh_capture_table)
        action_import_structured = QAction("转换点评结果", self)
        action_import_structured.triggered.connect(self._import_structured_records)
        tools_menu.addActions([
            action_refresh_devices,
            action_download_adb,
            action_start_capture,
            action_stop_capture,
            action_sync_capture,
            action_import_structured,
        ])

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

        self.device_proxy_button = QPushButton("设备代理")
        self.device_proxy_button.setMinimumHeight(36)
        self.device_proxy_button.clicked.connect(self._open_device_proxy_dialog)
        self.logout_button = QPushButton("退出登录")
        self.logout_button.setMinimumHeight(36)
        self.logout_button.clicked.connect(self._logout)

        layout.addWidget(account_title)
        layout.addWidget(self.account_name_label)
        layout.addStretch()
        layout.addWidget(self.device_proxy_button)
        layout.addWidget(self.logout_button)
        return container

    def _build_account_group(self):
        group = QGroupBox("账号信息")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        self.account_name_label = QLabel("账号: 未登录")
        self.account_workspace_label = QLabel("状态: 未登录")
        btn_settings = QPushButton("打开抓包配置")
        btn_settings.clicked.connect(lambda: self._switch_page("settings"))

        layout.addWidget(self.account_name_label)
        layout.addWidget(self.account_workspace_label)
        layout.addWidget(btn_settings, 0, Qt.AlignLeft)
        return group

    def _build_sidebar(self):
        self.sidebar_menu = QListWidget()
        self.sidebar_menu.setFixedWidth(180)
        self.sidebar_menu.addItem(QListWidgetItem("节点编排"))
        self.sidebar_menu.addItem(QListWidgetItem("抓取实时数据"))
        self.sidebar_menu.addItem(QListWidgetItem("数据管理"))
        self.sidebar_menu.addItem(QListWidgetItem("抓包配置"))
        self.sidebar_menu.currentRowChanged.connect(self._handle_sidebar_changed)
        return self.sidebar_menu

    def _build_content_stack(self):
        self.content_stack = QStackedWidget()
        self.workflow_page = self._build_workflow_page()
        self.realtime_data_page = self._build_realtime_data_page()
        self.data_management_page = self._build_data_management_page()
        self.settings_page = self._build_settings_page()

        self.content_stack.addWidget(self.workflow_page)
        self.content_stack.addWidget(self.realtime_data_page)
        self.content_stack.addWidget(self.data_management_page)
        self.content_stack.addWidget(self.settings_page)
        return self.content_stack

    def _build_workflow_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_canvas_panel())
        splitter.addWidget(self._build_properties_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.status_message = QLabel("双击节点开始成功连线，Shift+双击开始失败连线；verify 节点可直接双击 YES/NO 出口起线；滚轮缩放，空白区域左键拖动画布。")
        self.status_message.setObjectName("statusMessage")
        layout.addWidget(self.status_message)
        return page

    def _create_shortcuts(self):
        """注册全局快捷键"""
        self.shortcut_cancel = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.shortcut_cancel.activated.connect(self._handle_escape)

        self.shortcut_delete = QShortcut(QKeySequence(Qt.Key_Delete), self)
        self.shortcut_delete.activated.connect(self._handle_delete_shortcut)

        # macOS 键盘上的 Delete 常常映射为 Backspace
        self.shortcut_backspace = QShortcut(QKeySequence(Qt.Key_Backspace), self)
        self.shortcut_backspace.activated.connect(self._handle_delete_shortcut)

        # 兼容某些环境下把主键盘删除误当作 Enter 使用的情况
        self.shortcut_return = QShortcut(QKeySequence(Qt.Key_Return), self)
        self.shortcut_return.activated.connect(self._handle_delete_shortcut)

        self.shortcut_enter = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.shortcut_enter.activated.connect(self._handle_delete_shortcut)

    def _build_toolbar(self):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        btn_new = QPushButton("新建点击节点")
        btn_new.clicked.connect(lambda: self._add_node("click"))
        btn_new_start = QPushButton("新建开始节点")
        btn_new_start.clicked.connect(lambda: self._add_node("start"))
        btn_new_function = QPushButton("新建函数节点")
        btn_new_function.clicked.connect(lambda: self._add_node("function"))
        btn_new_end = QPushButton("新建结束节点")
        btn_new_end.clicked.connect(lambda: self._add_node("end"))
        btn_delete = QPushButton("删除节点")
        btn_delete.clicked.connect(self._delete_node)
        btn_connect_success = QPushButton("连接成功")
        btn_connect_success.clicked.connect(lambda: self._begin_connection("next_node"))
        btn_connect_fail = QPushButton("连接失败")
        btn_connect_fail.clicked.connect(lambda: self._begin_connection("failure_node"))
        btn_clear_edges = QPushButton("清除当前连线")
        btn_clear_edges.clicked.connect(self._clear_current_connections)
        btn_layout = QPushButton("自动布局")
        btn_layout.clicked.connect(self._auto_layout)
        btn_import = QPushButton("导入配置")
        btn_import.clicked.connect(self._import_config)
        btn_export = QPushButton("导出配置")
        btn_export.clicked.connect(self._export_config)
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._save_config)

        for widget in [
            btn_new, btn_new_start, btn_new_function, btn_new_end,
            btn_delete, btn_connect_success, btn_connect_fail,
            btn_clear_edges, btn_layout, btn_import, btn_export, btn_save,
        ]:
            toolbar.addWidget(widget)

        toolbar.addStretch()
        return toolbar

    def _build_adb_group(self):
        return build_adb_group(self)

    def _ensure_device_proxy_panel_initialized(self):
        if self.device_proxy_panel is None:
            self.device_proxy_panel = self._build_adb_group()
        return self.device_proxy_panel

    def _open_device_proxy_dialog(self):
        panel = self._ensure_device_proxy_panel_initialized()
        if self.device_proxy_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("设备代理")
            dialog.setModal(False)
            dialog.resize(1180, 380)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)
            layout.addWidget(panel)

            self.device_proxy_dialog = dialog

        self.device_proxy_dialog.show()
        self.device_proxy_dialog.raise_()
        self.device_proxy_dialog.activateWindow()

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

        if self.device_proxy_dialog is not None:
            self.device_proxy_dialog.close()

        self.login_window = LoginWindow(app_settings=self.app_settings)
        self.login_window.show()
        self.close()

    def _build_canvas_panel(self):
        panel = QGroupBox("流程画布")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        info = QLabel("拖动节点调整布局，选中节点后可在右侧编辑；绿色线为成功流转，红色线为失败流转。")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.scene = QGraphicsScene(self)
        self.canvas = NodeCanvasView(self.scene, self)
        self.canvas.scene_mouse_moved.connect(self._handle_canvas_mouse_moved)
        self.canvas.background_clicked.connect(self._handle_background_clicked)
        layout.addWidget(self.canvas)
        return panel

    def _build_realtime_data_page(self):
        return build_realtime_capture_page(self)

    def _build_data_management_page(self):
        return build_data_management_page(self)

    def _build_settings_page(self):
        return build_capture_settings_page(self)

    def _build_properties_panel(self):
        panel = QGroupBox("节点属性")
        root_layout = QVBoxLayout(panel)
        root_layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        form = QGridLayout(content)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(10)
        row = 0
        self.form_rows = {}

        self.selected_node_label = QLabel("未选择节点")
        self.selected_node_label.setObjectName("selectedNodeLabel")
        form.addWidget(self.selected_node_label, row, 0, 1, 2)

        row += 1
        self.name_entry = QLineEdit()
        row = self._add_form_row(form, row, "name", "名称:", self.name_entry)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["start", "click", "verify", "wait", "swipe", "function", "end"])
        self.type_combo.currentTextChanged.connect(self._update_form_visibility)
        row = self._add_form_row(form, row, "type", "类型:", self.type_combo)

        template_layout = QHBoxLayout()
        self.template_entry = QLineEdit()
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self._browse_template)
        template_layout.addWidget(self.template_entry)
        template_layout.addWidget(btn_browse)
        row = self._add_form_layout_row(form, row, "template", "模板图片:", template_layout)

        self.threshold_entry = QLineEdit()
        row = self._add_form_row(form, row, "threshold", "匹配阈值:", self.threshold_entry)

        self.center_entry = QLineEdit()
        row = self._add_form_row(form, row, "center", "缓存中心点:", self.center_entry)

        self.timeout_entry = QLineEdit()
        self.timeout_entry.setPlaceholderText("0 表示立即判断，适合循环")
        row = self._add_form_row(form, row, "timeout", "超时(verify):", self.timeout_entry)

        self.wait_min_entry = QLineEdit()
        self.wait_min_entry.setPlaceholderText("例如 0.8")
        row = self._add_form_row(form, row, "wait_min", "随机等待最小值:", self.wait_min_entry)

        self.wait_max_entry = QLineEdit()
        self.wait_max_entry.setPlaceholderText("例如 1.6")
        row = self._add_form_row(form, row, "wait_max", "随机等待最大值:", self.wait_max_entry)

        self.retry_entry = QLineEdit()
        row = self._add_form_row(form, row, "retry", "重试次数(click):", self.retry_entry)

        self.delay_after_entry = QLineEdit()
        row = self._add_form_row(form, row, "delay_after", "节点后等待:", self.delay_after_entry)

        self.max_steps_entry = QLineEdit()
        row = self._add_form_row(form, row, "max_steps", "最大执行步数:", self.max_steps_entry)

        self.next_node_entry = QLineEdit()
        row = self._add_form_row(form, row, "next_node", "成功后节点ID:", self.next_node_entry)

        self.failure_node_entry = QLineEdit()
        row = self._add_form_row(form, row, "failure_node", "失败后节点ID:", self.failure_node_entry)

        self.swipe_direction_combo = QComboBox()
        self.swipe_direction_combo.addItems(["up", "down", "left", "right"])
        row = self._add_form_row(form, row, "swipe_direction", "滑动方向:", self.swipe_direction_combo)

        self.swipe_distance_entry = QLineEdit()
        row = self._add_form_row(form, row, "swipe_distance", "滑动距离:", self.swipe_distance_entry)

        self.swipe_duration_entry = QLineEdit()
        row = self._add_form_row(form, row, "swipe_duration", "滑动时长:", self.swipe_duration_entry)

        self.max_swipes_entry = QLineEdit()
        row = self._add_form_row(form, row, "max_swipes", "最大滑动次数:", self.max_swipes_entry)

        self.max_failures_entry = QLineEdit()
        row = self._add_form_row(form, row, "max_failures", "最大失败次数:", self.max_failures_entry)

        self.stop_template_entry = QLineEdit()
        row = self._add_form_row(form, row, "stop_template", "停止模板:", self.stop_template_entry)

        self.stop_threshold_entry = QLineEdit()
        row = self._add_form_row(form, row, "stop_threshold", "停止阈值:", self.stop_threshold_entry)

        self.stop_next_node_entry = QLineEdit()
        self.stop_next_node_entry.setPlaceholderText("命中默认停止模板后跳到哪个节点")
        row = self._add_form_row(form, row, "stop_next_node", "默认停止后节点:", self.stop_next_node_entry)

        self.stop_rules_text = QTextEdit()
        self.stop_rules_text.setPlaceholderText(
            "每行一条规则，格式: 模板名或节点ID -> 下一个节点ID\n"
            "示例:\n"
            "no_more.png -> node_010\n"
            "node_005 -> node_020"
        )
        self.stop_rules_text.setFixedHeight(92)
        row = self._add_form_row(form, row, "stop_rules_text", "停止规则:", self.stop_rules_text)

        self.function_path_entry = QLineEdit()
        self.function_path_entry.setPlaceholderText("例如: workflow.click_region_filter 或 my_module:my_func")
        row = self._add_form_row(form, row, "function_path", "函数路径:", self.function_path_entry)

        self.function_args_text = QTextEdit()
        self.function_args_text.setPlaceholderText(
            "可选 JSON 参数\n"
            "例如:\n"
            "{\"region\": \"黄浦区\"}\n"
            "[1, 2, 3]"
        )
        self.function_args_text.setFixedHeight(84)
        row = self._add_form_row(form, row, "function_args_text", "函数参数:", self.function_args_text)

        self.end_success_checkbox = QCheckBox("结束时标记为成功")
        row = self._add_form_single_widget_row(form, row, "end_success", self.end_success_checkbox)

        self.end_message_entry = QLineEdit()
        self.end_message_entry.setPlaceholderText("例如: 全部流程完成")
        row = self._add_form_row(form, row, "end_message", "结束消息:", self.end_message_entry)

        self.is_start_checkbox = QCheckBox("起始节点")
        self.is_init_checkbox = QCheckBox("初始化节点")
        row = self._add_form_dual_widget_row(form, row, "node_flags", self.is_start_checkbox, self.is_init_checkbox)

        self.continue_on_fail_checkbox = QCheckBox("失败后继续按顺序执行")
        row = self._add_form_single_widget_row(form, row, "continue_on_fail", self.continue_on_fail_checkbox)

        self.success_on_max_swipes_checkbox = QCheckBox("达到最大滑动次数也算成功")
        row = self._add_form_single_widget_row(form, row, "success_on_max_swipes", self.success_on_max_swipes_checkbox)

        btn_screenshot = QPushButton("截图并框选")
        btn_screenshot.clicked.connect(self._screenshot_and_select)
        row = self._add_form_single_widget_row(form, row, "screenshot", btn_screenshot)

        btn_save_node = QPushButton("保存节点属性")
        btn_save_node.clicked.connect(self._save_node)
        row = self._add_form_single_widget_row(form, row, "save_node", btn_save_node)

        form.setRowStretch(row + 1, 1)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)
        self._update_form_visibility(self.type_combo.currentText())
        return panel

    def _add_form_row(self, form, row, key, label_text, widget):
        label = QLabel(label_text)
        form.addWidget(label, row, 0)
        form.addWidget(widget, row, 1)
        self.form_rows[key] = [label, widget]
        self.form_labels[key] = label
        return row + 1

    def _add_form_layout_row(self, form, row, key, label_text, layout):
        label = QLabel(label_text)
        container = QWidget()
        container.setLayout(layout)
        form.addWidget(label, row, 0)
        form.addWidget(container, row, 1)
        self.form_rows[key] = [label, container]
        self.form_labels[key] = label
        return row + 1

    def _add_form_single_widget_row(self, form, row, key, widget):
        placeholder = QWidget()
        placeholder.setFixedWidth(1)
        form.addWidget(placeholder, row, 0)
        form.addWidget(widget, row, 1)
        self.form_rows[key] = [placeholder, widget]
        return row + 1

    def _add_form_dual_widget_row(self, form, row, key, left_widget, right_widget):
        form.addWidget(left_widget, row, 0)
        form.addWidget(right_widget, row, 1)
        self.form_rows[key] = [left_widget, right_widget]
        return row + 1

    def _set_form_row_visible(self, key, visible: bool):
        for widget in self.form_rows.get(key, []):
            widget.setVisible(visible)

    def _set_form_label_text(self, key, text: str):
        label = self.form_labels.get(key)
        if label:
            label.setText(text)

    def _apply_dynamic_form_text(self, node_type: str):
        label_texts = {
            "template": "模板图片:",
            "threshold": "匹配阈值:",
            "timeout": "超时(verify):",
            "delay_after": "节点后等待:",
            "next_node": "成功后节点ID:",
            "failure_node": "失败后节点ID:",
            "stop_next_node": "默认停止后节点:",
        }
        placeholders = {
            "timeout": "",
            "delay_after": "",
            "next_node": "",
            "failure_node": "",
        }

        if node_type == "start":
            label_texts["next_node"] = "开始后节点ID:"
            placeholders["next_node"] = "流程从这里进入的第一个节点"
        elif node_type == "click":
            label_texts["next_node"] = "点击成功后节点ID:"
            label_texts["failure_node"] = "点击失败后节点ID:"
            placeholders["next_node"] = "点击成功后跳转到哪个节点"
            placeholders["failure_node"] = "点击失败后跳转到哪个节点"
        elif node_type == "verify":
            label_texts["template"] = "判断模板:"
            label_texts["timeout"] = "判断超时:"
            label_texts["next_node"] = "匹配成功后节点ID:"
            label_texts["failure_node"] = "未匹配后节点ID:"
            placeholders["timeout"] = "0 表示立即判断，适合循环"
            placeholders["next_node"] = "检测到目标后跳转到哪个节点"
            placeholders["failure_node"] = "未检测到目标时跳转到哪个节点"
        elif node_type == "wait":
            label_texts["next_node"] = "等待后节点ID:"
            placeholders["next_node"] = "等待完成后跳转到哪个节点"
        elif node_type == "swipe":
            label_texts["delay_after"] = "每次滑动后等待:"
            label_texts["next_node"] = "滑动完成后节点ID:"
            label_texts["failure_node"] = "滑动失败后节点ID:"
            label_texts["stop_next_node"] = "命中停止后节点:"
            placeholders["delay_after"] = "每次滑动后的页面稳定等待"
            placeholders["next_node"] = "达到最大次数或成功结束后跳转"
            placeholders["failure_node"] = "滑动异常或失败后跳转"
        elif node_type == "function":
            label_texts["next_node"] = "函数成功后节点ID:"
            label_texts["failure_node"] = "函数失败后节点ID:"
            placeholders["next_node"] = "函数返回成功后跳转到哪个节点"
            placeholders["failure_node"] = "函数返回失败后跳转到哪个节点"

        for key, text in label_texts.items():
            self._set_form_label_text(key, text)

        self.timeout_entry.setPlaceholderText(placeholders["timeout"])
        self.delay_after_entry.setPlaceholderText(placeholders["delay_after"])
        self.next_node_entry.setPlaceholderText(placeholders["next_node"])
        self.failure_node_entry.setPlaceholderText(placeholders["failure_node"])

    def _update_form_visibility(self, node_type: str = None):
        current_type = node_type or self.type_combo.currentText()
        common_rows = {
            "name", "type", "save_node",
        }
        type_rows = {
            "start": {"next_node"},
            "click": {
                "template", "threshold", "center", "retry", "screenshot",
                "next_node", "failure_node",
            },
            "verify": {
                "template", "threshold", "timeout", "screenshot",
                "next_node", "failure_node",
            },
            "wait": {"wait_min", "wait_max", "next_node"},
            "swipe": {
                "swipe_direction", "swipe_distance", "swipe_duration", "max_swipes",
                "max_failures", "stop_template", "stop_threshold", "stop_next_node", "stop_rules_text", "delay_after",
                "success_on_max_swipes", "screenshot", "next_node", "failure_node",
            },
            "function": {"function_path", "function_args_text", "next_node", "failure_node"},
            "end": {"end_success", "end_message"},
        }
        visible_rows = common_rows | type_rows.get(current_type, set())

        for key in self.form_rows:
            self._set_form_row_visible(key, key in visible_rows)
        self._apply_dynamic_form_text(current_type)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #F8FAFC;
                color: #0F172A;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #CBD5E1;
                border-radius: 14px;
                margin-top: 12px;
                padding-top: 14px;
                background: #FFFFFF;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 4px;
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
            QLabel#statusMessage {
                background: #E0F2FE;
                border: 1px solid #BAE6FD;
                border-radius: 10px;
                padding: 10px 12px;
            }
            QLabel#selectedNodeLabel {
                background: #F1F5F9;
                border-radius: 10px;
                padding: 10px 12px;
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

    def _handle_sidebar_changed(self, index: int):
        self.content_stack.setCurrentIndex(max(0, index))

    def _switch_page(self, page_name: str):
        mapping = {"workflow": 0, "realtime_data": 1, "data_management": 2, "settings": 3}
        index = mapping.get(page_name, 0)
        self.sidebar_menu.setCurrentRow(index)
        self.content_stack.setCurrentIndex(index)

    def _load_app_settings_to_form(self):
        capture = self.app_settings.get("capture", {})
        self.capture_enabled_checkbox.setChecked(bool(capture.get("enabled", False)))
        self.capture_platform_combo.setCurrentText(capture.get("platform", "android"))
        self.capture_android_proxy_checkbox.setChecked(bool(capture.get("android_proxy_auto_apply", False)))
        self._load_meituan_capture_settings()
        adb_settings = self.app_settings.get("adb", {})
        self.remote_address_entry.setText(adb_settings.get("remote_address", ""))
        self.pair_address_entry.setText(adb_settings.get("pair_address", ""))

        self._refresh_capture_status()
        self._refresh_adb_tool_status()
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
            "android_proxy_auto_apply": self.capture_android_proxy_checkbox.isChecked(),
            "ios_proxy_manual": True,
            "max_body_kb": int(current_capture.get("max_body_kb", 512) or 512),
            "export_default_name": current_capture.get("export_default_name", "captures.xlsx"),
        }

    def _load_meituan_capture_settings(self):
        data_capture = self.app_settings.get("data_capture", {})
        self.selected_platform = data_capture.get("selected_platform", "meituan") or "meituan"
        self.selected_interface_key = data_capture.get("selected_interface_key", "all") or "all"
        self.meituan_protocols = self.protocol_loader.list_protocols()

        if hasattr(self, "capture_platform_display"):
            self.capture_platform_display.blockSignals(True)
            self.capture_platform_display.setCurrentIndex(0)
            self.capture_platform_display.blockSignals(False)

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

    def _save_app_settings(self):
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
        self.app_settings.setdefault("adb", {
            "adb_path": "",
            "remote_address": "",
            "pair_address": "",
            "proxy_backup": "",
            "last_applied_proxy": "",
        })
        self.app_settings["capture"] = self._collect_capture_settings_from_form()
        self.app_settings["data_capture"] = self._collect_data_capture_settings()
        self.app_settings["adb"] = self._collect_adb_settings_from_form()
        AppSettings.save(self.app_settings)
        self._refresh_top_info()
        self._refresh_capture_status()
        self._refresh_capture_rule_summary()
        self._refresh_adb_tool_status()
        self._refresh_capture_platform_ui()
        QMessageBox.information(self, "成功", "抓包配置已保存")

    def _get_capture_platform(self) -> str:
        if hasattr(self, "capture_platform_combo"):
            value = self.capture_platform_combo.currentText().strip()
            if value:
                return value
        return self.app_settings.get("capture", {}).get("platform", "android") or "android"

    def _capture_platform_supports_android(self) -> bool:
        return self._get_capture_platform() in {"android", "both"}

    def _capture_platform_supports_ios(self) -> bool:
        return self._get_capture_platform() in {"ios", "both"}

    def _refresh_capture_platform_ui(self):
        self.ios_capture_controller.apply_platform_ui()
        self._refresh_device_proxy_status()

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
        combos = []
        if hasattr(self, "capture_interface_combo"):
            combos.append(self.capture_interface_combo)
        if hasattr(self, "management_interface_combo"):
            combos.append(self.management_interface_combo)
        if not combos:
            return

        selected_key = self.selected_interface_key or "all"
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("全部点评接口", "all")
            for protocol in self.meituan_protocols:
                combo.addItem(protocol["name"], protocol["key"])

            current_index = 0
            for index in range(combo.count()):
                if combo.itemData(index) == selected_key:
                    current_index = index
                    break
            combo.setCurrentIndex(current_index)
            combo.blockSignals(False)

        self.selected_interface_key = selected_key

    def _handle_platform_selection_changed(self, index: int):
        _ = index
        self.selected_platform = "meituan"
        self._refresh_interface_selector()
        self._refresh_protocol_summary()
        self._refresh_structured_views()

    def _handle_interface_selection_changed(self, index: int):
        if index < 0:
            return
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            combo = self.capture_interface_combo if hasattr(self, "capture_interface_combo") else None
        if combo is None:
            return
        self.selected_interface_key = combo.itemData(index) or "all"
        self._sync_interface_combos(combo)
        self._save_capture_rules()
        self._refresh_protocol_summary()
        self._refresh_structured_views()

    def _sync_interface_combos(self, source_combo: QComboBox):
        target_combos = []
        if hasattr(self, "capture_interface_combo") and self.capture_interface_combo is not source_combo:
            target_combos.append(self.capture_interface_combo)
        if hasattr(self, "management_interface_combo") and self.management_interface_combo is not source_combo:
            target_combos.append(self.management_interface_combo)

        for combo in target_combos:
            combo.blockSignals(True)
            for index in range(combo.count()):
                if combo.itemData(index) == self.selected_interface_key:
                    combo.setCurrentIndex(index)
                    break
            combo.blockSignals(False)

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

    def _get_selected_failure_code(self):
        if self.selected_interface_key == "all":
            return ""
        protocols = self._get_selected_protocols()
        if not protocols:
            return ""
        return protocols[0].get("key", "")

    def _refresh_protocol_summary(self):
        if not hasattr(self, "protocol_summary_label"):
            return

        protocols = self._get_selected_protocols()
        if not protocols:
            self.protocol_summary_label.setText("未发现点评接口协议，请检查 config/meituan/ 目录。")
            self.protocol_fields_label.setText("导出字段: -")
            self.protocol_config_path_label.setText("协议文件: -")
            return

        if self.selected_interface_key == "all":
            protocol_names = "、".join(protocol["name"] for protocol in protocols)
            patterns = "\n".join(f"- {protocol['name']}: {protocol['url_pattern']}" for protocol in protocols)
            self.protocol_summary_label.setText(
                "当前选择: 全部点评接口\n"
                f"转换实体: {self._get_selected_entity_code() or '-'}\n"
                f"匹配规则:\n{patterns}"
            )
            merged_columns = []
            seen = set()
            for protocol in protocols:
                for column in protocol.get("export_columns", []):
                    if column not in seen:
                        seen.add(column)
                        merged_columns.append(column)
            self.protocol_fields_label.setText(f"导出字段: {', '.join(merged_columns) if merged_columns else '-'}")
            config_paths = "\n".join(f"- {protocol.get('config_path', '-')}" for protocol in protocols)
            self.protocol_config_path_label.setText(f"协议文件:\n{config_paths}")
            return

        protocol = protocols[0]
        record_key = protocol.get("record_key", {})
        fields = ", ".join(protocol.get("export_columns", [])) or "-"
        self.protocol_summary_label.setText(
            f"当前接口: {protocol['name']}\n"
            f"匹配规则: {protocol.get('url_pattern', '-')}\n"
            f"实体编码: {protocol.get('entity_code', '-')}\n"
            f"唯一 key: {record_key.get('mode', 'path')} -> {record_key.get('expr', '-')}"
        )
        self.protocol_fields_label.setText(f"导出字段: {fields}")
        self.protocol_config_path_label.setText(f"协议文件: {protocol.get('config_path', '-')}")

    def _show_data_operation_help(self):
        self.realtime_capture_controller.show_data_operation_help()

    def _show_data_management_help(self):
        self.structured_data_controller.show_data_management_help()

    def _save_capture_rules(self):
        return self.realtime_capture_controller.save_capture_rules()

    def _clear_temporary_capture_data(self):
        self.realtime_capture_controller.clear_temporary_capture_data()

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
            if hasattr(self, "account_workspace_label"):
                self.account_workspace_label.setText(f"状态: 已登录 | ID: {admin_id}")
        else:
            self.account_name_label.setText("未登录")
            self.account_name_label.setToolTip("登录已失效，请重新登录")
            if hasattr(self, "account_workspace_label"):
                self.account_workspace_label.setText("状态: 登录已失效，请重新登录")

    def _collect_adb_settings_from_form(self):
        return self.android_adb_controller.collect_adb_settings_from_form()

    def _get_configured_adb_path(self):
        return self.android_adb_controller.get_configured_adb_path()

    def _get_saved_proxy_backup(self) -> str:
        return self.android_adb_controller.get_saved_proxy_backup()

    def _has_saved_proxy_backup(self) -> bool:
        return self.android_adb_controller.has_saved_proxy_backup()

    def _save_proxy_backup(self, proxy_value: str, last_applied_proxy: str = None):
        self.android_adb_controller.save_proxy_backup(proxy_value, last_applied_proxy=last_applied_proxy)

    def _clear_proxy_backup(self):
        self.android_adb_controller.clear_proxy_backup()

    def _refresh_adb_tool_status(self):
        self.android_adb_controller.refresh_adb_tool_status()

    def _refresh_local_network_hint(self):
        self.android_adb_controller.refresh_local_network_hint()

    def _refresh_adb_summary(self):
        self.android_adb_controller.refresh_adb_summary()

    def _ensure_adb_available(self, prompt_download: bool = True):
        return self.android_adb_controller.ensure_adb_available(prompt_download=prompt_download)

    def _download_adb_tools(self, silent: bool = False):
        return self.android_adb_controller.download_adb_tools(silent=silent)

    def _connect_remote_device(self):
        self.android_adb_controller.connect_remote_device()

    def _pair_remote_device(self):
        self.android_adb_controller.pair_remote_device()

    def _open_qr_pair_dialog(self):
        if qrcode is None:
            QMessageBox.warning(self, "二维码配对", "未安装 qrcode，无法生成配对二维码")
            return
        if not self._ensure_adb_available(prompt_download=True):
            return

        dialog = AdbQrPairDialog(self._get_configured_adb_path(), self)
        if dialog.exec_() != QDialog.Accepted or not dialog.connected_address:
            return

        self.remote_address_entry.setText(dialog.connected_address)
        self.app_settings.setdefault("adb", {})
        self.app_settings["adb"]["remote_address"] = dialog.connected_address
        AppSettings.save(self.app_settings)
        self._refresh_devices(select_device_id=dialog.connected_address)
        QMessageBox.information(
            self,
            "二维码配对",
            f"设备已完成二维码配对并建立无线连接:\n{dialog.connected_address}",
        )

    def _disconnect_remote_device(self):
        self.android_adb_controller.disconnect_remote_device()

    def _refresh_capture_status(self):
        self.capture_certificate_controller.refresh_capture_status()

    def _should_prompt_apply_proxy(self) -> bool:
        capture = self.app_settings.get("capture", {})
        return bool(capture.get("enabled") or self.capture_manager.is_running())

    def _update_ca_qr(self):
        self.capture_certificate_controller.update_ca_qr()

    def _start_ca_service(self):
        self.capture_certificate_controller.start_ca_service()

    def _stop_ca_service(self):
        self.capture_certificate_controller.stop_ca_service()

    def _start_capture_service(self):
        self._save_settings_if_needed(silent=True)
        capture = self.app_settings.get("capture", {})
        success, message = self.capture_manager.start(capture)
        self._refresh_capture_status()

        if success and self._capture_platform_supports_android() and capture.get("android_proxy_auto_apply"):
            self._apply_android_proxy_settings(silent=True)

        if success:
            self.statusBar().showMessage(message, 4000)
        else:
            QMessageBox.warning(self, "抓取服务", message)

    def _stop_proxy_capture_only(self):
        _, capture_message = self.capture_manager.stop()
        self._refresh_capture_status()

        QMessageBox.information(
            self,
            "已停止抓包",
            capture_message,
        )
        return True

    def _stop_proxy_capture_and_clear_proxy(self):
        _, capture_message = self.capture_manager.stop()
        self._refresh_capture_status()

        extra_message = ""
        if not self._capture_platform_supports_android():
            extra_message = "\n当前为 iOS 手动抓包模式，系统不会自动清除 iPhone 代理，请在设备上手动关闭。"
        elif self.adb_device and self.adb_device.connected:
            if self._clear_android_proxy_settings():
                extra_message = "\n手机代理已清除。"
            else:
                extra_message = "\n抓包已停止，但手机代理清除失败。"
        else:
            extra_message = "\n抓包已停止，但当前没有已连接的 Android 设备，未执行手机代理清除。"

        QMessageBox.information(
            self,
            "已停止抓包并清除手机代理",
            f"{capture_message}{extra_message}",
        )
        return True

    def _quick_setup_android_capture(self):
        self.capture_platform_combo.setCurrentText("android")
        self._save_settings_if_needed(silent=True)

        success, message = self.capture_manager.start(self.app_settings.get("capture", {}))
        self._refresh_capture_status()
        if not success:
            QMessageBox.warning(self, "一键配置", message)
            return

        apply_message = "手机未连接，请先连接 Android 设备后再点“应用手机代理”。"
        if self.adb_device and self.adb_device.connected:
            if self._apply_android_proxy_settings(silent=True):
                apply_message = "已自动应用手机代理。"
            else:
                apply_message = "抓取服务已启动，但手机代理应用失败，请手动点“应用手机代理”。"

        QMessageBox.information(
            self,
            "一键配置完成",
            "抓取服务和 CA 服务已就绪。\n\n"
            f"{apply_message}\n\n"
            f"CA 下载地址:\n{self.capture_manager.get_ca_install_url(self.app_settings.get('capture', {})) if self.capture_manager.get_proxy_address(self.app_settings.get('capture', {}))[0] else '未识别本机局域网IP'}",
        )

    def _stop_capture_service(self):
        _, message = self.capture_manager.stop()
        self._refresh_capture_status()
        self.statusBar().showMessage(message, 4000)

    def _refresh_capture_table(self):
        self.realtime_capture_controller.refresh_capture_table()

    def _refresh_structured_views(self, reset_page: bool = False):
        self.structured_data_controller.refresh_structured_views(reset_page=reset_page)

    def _collect_structured_filters(self):
        return self.structured_data_controller.collect_structured_filters()

    def _apply_structured_filters(self):
        self.structured_data_controller.apply_structured_filters()

    def _reset_structured_filters(self):
        self.structured_data_controller.reset_structured_filters()

    def _change_structured_page(self, delta: int):
        self.structured_data_controller.change_structured_page(delta)

    def _handle_structured_selection_changed(self):
        self.structured_data_controller.handle_structured_selection_changed()

    def _handle_structured_item_changed(self, item):
        self.structured_data_controller.handle_structured_item_changed(item)

    def _start_playwright_phone_fetch(self):
        self.structured_data_controller.start_playwright_phone_fetch()

    def _handle_playwright_worker_progress(self, message: str):
        self.structured_data_controller.handle_playwright_worker_progress(message)

    def _handle_playwright_worker_completed(self, summary: dict):
        self.structured_data_controller.handle_playwright_worker_completed(summary)

    def _handle_playwright_worker_failed(self, message: str):
        self.structured_data_controller.handle_playwright_worker_failed(message)

    def _import_structured_records(self):
        self.realtime_capture_controller.import_structured_records()

    def _handle_capture_selection_changed(self):
        self.realtime_capture_controller.handle_capture_selection_changed()

    def _export_capture_excel(self):
        self.realtime_capture_controller.export_capture_excel()

    def _export_structured_excel(self):
        self.structured_data_controller.export_structured_excel()

    def _apply_android_proxy_settings(self, silent: bool = False):
        return self.android_proxy_controller.apply_android_proxy_settings(silent=silent)

    def _get_expected_android_proxy(self):
        return self.android_proxy_controller.get_expected_android_proxy()

    def _clear_android_proxy_settings(self):
        return self.android_proxy_controller.clear_android_proxy_settings()

    def _emergency_clear_android_proxy(self):
        return self.android_proxy_controller.emergency_clear_android_proxy()

    def _fix_android_proxy_from_topbar(self):
        self._apply_android_proxy_settings()

    def _restore_previous_android_proxy(self):
        return self.android_proxy_controller.restore_previous_android_proxy()

    def _refresh_device_proxy_status(self):
        self.android_proxy_controller.refresh_device_proxy_status()

    def _detect_android_proxy_settings(self):
        return self.android_proxy_controller.detect_android_proxy_settings()

    def _test_android_proxy_connectivity(self):
        return self.android_proxy_controller.test_android_proxy_connectivity()

    def _show_capture_https_diagnosis(self):
        return self.capture_certificate_controller.show_https_diagnosis()

    def _show_android_https_diagnosis(self):
        self.android_proxy_controller.show_android_https_diagnosis()

    def _show_ios_capture_checklist(self):
        return self.ios_capture_controller.show_capture_checklist()

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
        self.app_settings.setdefault("adb", {
            "adb_path": "",
            "remote_address": "",
            "pair_address": "",
            "proxy_backup": "",
            "last_applied_proxy": "",
        })
        self.app_settings["capture"] = self._collect_capture_settings_from_form()
        self.app_settings["data_capture"] = self._collect_data_capture_settings()
        self.app_settings["adb"] = self._collect_adb_settings_from_form()
        AppSettings.save(self.app_settings)
        self._refresh_top_info()
        self._refresh_capture_status()
        self._refresh_capture_rule_summary()
        self._refresh_adb_tool_status()
        if not silent:
            self.statusBar().showMessage("抓包配置已保存", 3000)

    def _load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.nodes = config.get("nodes", [])
                self._normalize_nodes()
                self._ensure_single_start_node()
                self._rebuild_index()
                self._refresh_canvas()
                logger.info(f"加载配置成功，共 {len(self.nodes)} 个节点")
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                QMessageBox.critical(self, "错误", f"加载配置失败: {e}")

    def _save_config(self):
        try:
            self._sync_positions_from_canvas()
            self._ensure_single_start_node()

            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            else:
                config = {}

            config["nodes"] = self.nodes

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info("配置已保存")
            QMessageBox.information(self, "成功", "Canvas 编排已保存")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            QMessageBox.critical(self, "错误", f"保存配置失败: {e}")

    def _normalize_nodes(self):
        for index, node in enumerate(self.nodes):
            if not node.get("id"):
                node["id"] = f"node_{index + 1:03d}"
            if "position" not in node:
                node["position"] = {
                    "x": (index % 4) * 280,
                    "y": (index // 4) * 170,
                }
            if node.get("position") is None:
                node["position"] = {"x": 0, "y": 0}
            if node.get("type") == "start":
                node["is_start"] = True

    def _rebuild_index(self):
        self.node_map = {node["id"]: node for node in self.nodes}

    def _refresh_canvas(self):
        self.scene.clear()
        self.node_items = {}
        self.connection_items = []
        self.preview_connection_item = None
        self.canvas.set_connection_preview_active(False)

        for node in self.nodes:
            item = FlowNodeItem(node)
            item.clicked.connect(self._handle_node_clicked)
            item.double_clicked.connect(self._handle_node_double_clicked)
            item.moved.connect(self._handle_node_moved)
            self.scene.addItem(item)
            position = node.get("position", {"x": 0, "y": 0})
            item.setPos(float(position.get("x", 0)), float(position.get("y", 0)))
            self.node_items[node["id"]] = item

        self._rebuild_connections()

        if self.current_node_id and self.current_node_id in self.node_items:
            self.node_items[self.current_node_id].setSelected(True)
            self._load_node_details(self.node_map[self.current_node_id])
        else:
            self._clear_form()

    def _rebuild_connections(self):
        for item in self.connection_items:
            self.scene.removeItem(item)
        self.connection_items = []

        for node in self.nodes:
            source_item = self.node_items.get(node["id"])
            if not source_item:
                continue

            for field_name in ("next_node", "failure_node"):
                target_id = node.get(field_name)
                target_item = self.node_items.get(target_id)
                if target_item:
                    connection = FlowConnectionItem(
                        source_item,
                        target_item,
                        field_name,
                        on_rewire_requested=self._start_rewire_connection,
                    )
                    self.scene.addItem(connection)
                    self.connection_items.append(connection)

    def _update_connections_for_node(self, node_id: str):
        _ = node_id
        for item in self.connection_items:
            item.update_path()

    def _handle_node_clicked(self, node_id: str):
        if self.pending_connection:
            self._finish_connection(node_id)
            return
        self._select_node(node_id)

    def _handle_node_double_clicked(self, node_id: str, modifiers: int, preferred_field: str):
        field_name = preferred_field or ("failure_node" if modifiers & int(Qt.ShiftModifier) else "next_node")
        self._select_node(node_id)
        self._start_preview_connection(node_id, field_name)

    def _handle_node_moved(self, node_id: str):
        item = self.node_items.get(node_id)
        node = self.node_map.get(node_id)
        if item and node:
            node["position"] = {"x": round(item.pos().x(), 1), "y": round(item.pos().y(), 1)}
            self._update_connections_for_node(node_id)
            if (
                self.pending_connection
                and self.pending_connection["source_node_id"] == node_id
                and self.preview_connection_item
            ):
                self.preview_connection_item.update_path(self.last_scene_mouse_pos)

    def _select_node(self, node_id: str):
        self.current_node_id = node_id
        for nid, item in self.node_items.items():
            item.setSelected(nid == node_id)
        node = self.node_map.get(node_id)
        if node:
            self._load_node_details(node)
            self.status_message.setText(f"当前选中: {node['name']} [{node_id}]")

    def _load_node_details(self, node: dict):
        self.selected_node_label.setText(f"当前节点: {node.get('name', '未命名')} [{node['id']}]")
        self.name_entry.setText(node.get("name", ""))
        self.type_combo.setCurrentText(node.get("type", "click"))
        self.template_entry.setText(node.get("template", ""))
        self.threshold_entry.setText(str(node.get("threshold", 0.7)))
        self.timeout_entry.setText(self._to_text(node.get("timeout")))
        wait_min = node.get("wait_min")
        wait_max = node.get("wait_max")
        duration = node.get("duration")
        if wait_min is None and wait_max is None and duration is not None:
            wait_min = duration
            wait_max = duration
        self.wait_min_entry.setText(self._to_text(wait_min))
        self.wait_max_entry.setText(self._to_text(wait_max))
        self.retry_entry.setText(self._to_text(node.get("retry")))
        self.delay_after_entry.setText(self._to_text(node.get("delay_after")))
        self.max_steps_entry.setText(self._to_text(node.get("max_steps")))
        self.next_node_entry.setText(node.get("next_node", ""))
        self.failure_node_entry.setText(node.get("failure_node", ""))
        self.swipe_direction_combo.setCurrentText(node.get("swipe_direction", "up"))
        self.swipe_distance_entry.setText(self._to_text(node.get("swipe_distance")))
        self.swipe_duration_entry.setText(self._to_text(node.get("swipe_duration")))
        self.max_swipes_entry.setText(self._to_text(node.get("max_swipes")))
        self.max_failures_entry.setText(self._to_text(node.get("max_failures")))
        self.stop_template_entry.setText(node.get("stop_template", ""))
        self.stop_threshold_entry.setText(self._to_text(node.get("stop_threshold")))
        self.stop_next_node_entry.setText(node.get("stop_next_node", ""))
        self.stop_rules_text.setPlainText(node.get("stop_rules_text", ""))
        self.function_path_entry.setText(node.get("function_path", ""))
        self.function_args_text.setPlainText(node.get("function_args_text", ""))
        self.end_success_checkbox.setChecked(node.get("end_success", True))
        self.end_message_entry.setText(node.get("end_message", ""))

        center = node.get("cached_center")
        if center:
            self.center_entry.setText(f"{center[0]}, {center[1]}")
        else:
            self.center_entry.clear()

        self.is_start_checkbox.setChecked(node.get("is_start", False))
        self.is_init_checkbox.setChecked(node.get("is_init", False))
        self.continue_on_fail_checkbox.setChecked(node.get("continue_on_fail", False))
        self.success_on_max_swipes_checkbox.setChecked(node.get("success_on_max_swipes", False))
        self._update_form_visibility(node.get("type", "click"))

    def _clear_form(self):
        self.selected_node_label.setText("未选择节点")
        for widget in [
            self.name_entry, self.template_entry, self.threshold_entry, self.center_entry,
            self.timeout_entry, self.wait_min_entry, self.wait_max_entry, self.retry_entry, self.delay_after_entry,
            self.max_steps_entry, self.next_node_entry, self.failure_node_entry,
            self.swipe_distance_entry, self.swipe_duration_entry, self.max_swipes_entry,
            self.max_failures_entry, self.stop_template_entry, self.stop_threshold_entry,
            self.stop_next_node_entry, self.function_path_entry, self.end_message_entry,
        ]:
            widget.clear()
        self.stop_rules_text.clear()
        self.function_args_text.clear()
        self.type_combo.setCurrentText("click")
        self.swipe_direction_combo.setCurrentText("up")
        self.is_start_checkbox.setChecked(False)
        self.is_init_checkbox.setChecked(False)
        self.continue_on_fail_checkbox.setChecked(False)
        self.success_on_max_swipes_checkbox.setChecked(False)
        self.end_success_checkbox.setChecked(True)
        self._update_form_visibility("click")

    def _save_node(self):
        if not self.current_node_id:
            QMessageBox.warning(self, "警告", "请先在画布上选择一个节点")
            return

        node = self.node_map[self.current_node_id]
        node["name"] = self.name_entry.text().strip() or node["id"]
        node["type"] = self.type_combo.currentText()
        node["template"] = self.template_entry.text().strip()
        node["threshold"] = self._parse_float(self.threshold_entry.text(), 0.7)
        node["timeout"] = self._parse_optional_float(self.timeout_entry.text())
        wait_min = self._parse_optional_float(self.wait_min_entry.text())
        wait_max = self._parse_optional_float(self.wait_max_entry.text())
        if wait_min is not None and wait_max is None:
            wait_max = wait_min
        if wait_max is not None and wait_min is None:
            wait_min = wait_max
        node["wait_min"] = wait_min
        node["wait_max"] = wait_max
        node["retry"] = self._parse_optional_int(self.retry_entry.text())
        node["delay_after"] = self._parse_float(self.delay_after_entry.text(), 0.5)
        node["max_steps"] = self._parse_optional_int(self.max_steps_entry.text())
        node["next_node"] = self.next_node_entry.text().strip()
        node["failure_node"] = self.failure_node_entry.text().strip()
        node["swipe_direction"] = self.swipe_direction_combo.currentText()
        node["swipe_distance"] = self._parse_optional_int(self.swipe_distance_entry.text())
        node["swipe_duration"] = self._parse_optional_float(self.swipe_duration_entry.text())
        node["max_swipes"] = self._parse_optional_int(self.max_swipes_entry.text())
        node["max_failures"] = self._parse_optional_int(self.max_failures_entry.text())
        node["stop_template"] = self.stop_template_entry.text().strip()
        node["stop_threshold"] = self._parse_optional_float(self.stop_threshold_entry.text())
        node["stop_next_node"] = self.stop_next_node_entry.text().strip()
        node["stop_rules_text"] = self.stop_rules_text.toPlainText().strip()
        node["function_path"] = self.function_path_entry.text().strip()
        node["function_args_text"] = self.function_args_text.toPlainText().strip()
        node["end_success"] = self.end_success_checkbox.isChecked()
        node["end_message"] = self.end_message_entry.text().strip()
        node["is_start"] = self.is_start_checkbox.isChecked()
        node["is_init"] = self.is_init_checkbox.isChecked()
        node["continue_on_fail"] = self.continue_on_fail_checkbox.isChecked()
        node["success_on_max_swipes"] = self.success_on_max_swipes_checkbox.isChecked()

        if node["type"] == "start":
            node["is_start"] = True

        center_text = self.center_entry.text().strip()
        if center_text:
            try:
                parts = center_text.split(",")
                node["cached_center"] = [int(parts[0].strip()), int(parts[1].strip())]
            except Exception:
                logger.warning(f"缓存中心点格式无效: {center_text}")
        else:
            node["cached_center"] = None

        if node["is_start"]:
            self._ensure_single_start_node(node["id"])

        self._cleanup_type_specific_fields(node)
        self._cleanup_empty_fields(node)
        self._rebuild_connections()
        self._refresh_selected_item()
        self.status_message.setText(f"已保存节点属性: {node['name']} [{node['id']}]")
        QMessageBox.information(self, "成功", "节点属性已保存")

    def _cleanup_type_specific_fields(self, node):
        node_type = node.get("type")
        fields_by_type = {
            "start": {"next_node", "is_start"},
            "click": {
                "template", "threshold", "cached_center", "retry",
                "next_node", "failure_node",
            },
            "verify": {
                "template", "threshold", "timeout", "next_node", "failure_node",
            },
            "wait": {
                "wait_min", "wait_max", "next_node",
            },
            "swipe": {
                "swipe_direction", "swipe_distance", "swipe_duration", "max_swipes",
                "max_failures", "stop_template", "stop_threshold", "stop_next_node", "stop_rules_text", "delay_after",
                "success_on_max_swipes", "next_node", "failure_node",
            },
            "function": {
                "function_path", "function_args_text", "next_node", "failure_node",
            },
            "end": {"end_success", "end_message"},
        }
        allowed_fields = fields_by_type.get(node_type, set()) | {"id", "name", "type", "position", "cached_rect"}

        for field in list(node.keys()):
            if field not in allowed_fields:
                node.pop(field, None)

    def _refresh_selected_item(self):
        item = self.node_items.get(self.current_node_id)
        if item:
            item.node = self.node_map[self.current_node_id]
            item.update()

    def _ensure_single_start_node(self, keep_id: str = None):
        start_nodes = [node for node in self.nodes if node.get("is_start")]
        if not start_nodes and keep_id is None and self.nodes:
            return

        selected_id = keep_id or (start_nodes[0]["id"] if start_nodes else None)
        for node in self.nodes:
            node["is_start"] = node["id"] == selected_id

    def _cleanup_empty_fields(self, node):
        empty_fields = [
            "timeout", "duration", "wait_min", "wait_max", "retry", "max_steps", "next_node", "failure_node",
            "swipe_distance", "swipe_duration", "max_swipes", "max_failures",
            "stop_template", "stop_threshold", "stop_next_node", "stop_rules_text",
            "function_path", "function_args_text", "end_message",
        ]
        for field in empty_fields:
            value = node.get(field)
            if value in ("", None):
                node.pop(field, None)

    def _sync_positions_from_canvas(self):
        for node_id, item in self.node_items.items():
            if node_id in self.node_map:
                self.node_map[node_id]["position"] = {
                    "x": round(item.pos().x(), 1),
                    "y": round(item.pos().y(), 1),
                }

    def _default_position(self, index: int):
        return {"x": (index % 4) * 280, "y": (index // 4) * 170}

    def _add_node(self, node_type: str = "click"):
        node_id = self._next_node_id()
        default_names = {
            "start": "开始",
            "click": "点击",
            "verify": "条件判断",
            "wait": "等待",
            "swipe": "滑动",
            "function": "函数调用",
            "end": "结束",
        }
        new_node = {
            "id": node_id,
            "name": default_names.get(node_type, "新节点"),
            "type": node_type,
            "template": "",
            "threshold": 0.7,
            "cached_rect": None,
            "cached_center": None,
            "wait_min": None,
            "wait_max": None,
            "retry": 3,
            "delay_after": 0.5,
            "swipe_direction": "up",
            "swipe_distance": 500,
            "swipe_duration": 0.5,
            "max_swipes": 10,
            "max_failures": 3,
            "stop_template": "",
            "stop_next_node": "",
            "stop_threshold": 0.8,
            "stop_rules_text": "",
            "function_path": "",
            "function_args_text": "",
            "end_success": True,
            "end_message": "",
            "position": self._default_position(len(self.nodes)),
            "is_start": node_type == "start" or not self.nodes,
            "is_init": False,
        }
        if node_type == "verify":
            new_node["timeout"] = 0.0
        self.nodes.append(new_node)
        if new_node["is_start"]:
            self._ensure_single_start_node(node_id)
        self._rebuild_index()
        self._refresh_canvas()
        self._select_node(node_id)

    def _next_node_id(self) -> str:
        used_numbers = []
        for node in self.nodes:
            try:
                used_numbers.append(int(node["id"].split("_")[-1]))
            except Exception:
                continue
        next_num = max(used_numbers, default=0) + 1
        return f"node_{next_num:03d}"

    def _delete_node(self):
        if not self.current_node_id:
            QMessageBox.warning(self, "警告", "请先选择要删除的节点")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除节点 {self.current_node_id} 吗？相关连线也会一并移除。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted_id = self.current_node_id
        self.nodes = [node for node in self.nodes if node["id"] != deleted_id]
        for node in self.nodes:
            if node.get("next_node") == deleted_id:
                node.pop("next_node", None)
            if node.get("failure_node") == deleted_id:
                node.pop("failure_node", None)
            if node.get("is_start") and node["id"] == deleted_id:
                node["is_start"] = False

        if self.nodes and not any(node.get("is_start") for node in self.nodes):
            self.nodes[0]["is_start"] = True

        self.current_node_id = None
        self._rebuild_index()
        self._refresh_canvas()

    def _begin_connection(self, field_name: str):
        if not self.current_node_id:
            QMessageBox.warning(self, "警告", "请先选择作为起点的节点")
            return
        self._start_preview_connection(self.current_node_id, field_name)

    def _start_preview_connection(self, source_node_id: str, field_name: str, previous_target_id: str = None, hidden_connection=None):
        self._cancel_preview_connection(clear_status=False)

        source_item = self.node_items.get(source_node_id)
        source_node = self.node_map.get(source_node_id)
        if not source_item:
            return

        self.pending_connection = {
            "source_node_id": source_node_id,
            "field_name": field_name,
            "previous_target_id": previous_target_id,
            "hidden_connection": hidden_connection,
        }

        self.preview_connection_item = FlowPreviewConnectionItem(source_item, field_name)
        self.scene.addItem(self.preview_connection_item)
        self.canvas.set_connection_preview_active(True)

        if source_node and source_node.get("type") == "verify":
            field_label = "YES" if field_name == "next_node" else "NO"
            tip = "双击目标节点即可完成条件分支连线。"
        else:
            field_label = "成功" if field_name == "next_node" else "失败"
            tip = "按住 Shift 双击节点可直接创建失败连线。" if field_name == "next_node" else "当前为失败连线模式。"
        self.status_message.setText(
            f"连线模式: 从 {source_node_id} 的{field_label}出口拖向目标节点。{tip}"
        )

    def _start_rewire_connection(self, connection: FlowConnectionItem, scene_pos: QPointF):
        if self.preview_connection_item and self.pending_connection:
            hidden_connection = self.pending_connection.get("hidden_connection")
            if hidden_connection is connection:
                self.preview_connection_item.update_path(scene_pos)
                return
            self._cancel_preview_connection(clear_status=False)

        self._select_node(connection.source_item.node_id)
        connection.setVisible(False)
        self._start_preview_connection(
            connection.source_item.node_id,
            connection.field_name,
            previous_target_id=connection.target_item.node_id,
            hidden_connection=connection,
        )
        if self.preview_connection_item:
            self.preview_connection_item.update_path(scene_pos)

    def _finish_connection(self, target_node_id: str):
        source_node_id = self.pending_connection["source_node_id"]
        field_name = self.pending_connection["field_name"]
        source_node = self.node_map.get(source_node_id)
        if not source_node:
            self._cancel_preview_connection()
            return

        if target_node_id == source_node_id:
            self._cancel_preview_connection(clear_status=False)
            self.status_message.setText("已取消连线：不能把节点连接到自己")
            return

        source_node[field_name] = target_node_id

        if source_node_id == self.current_node_id:
            if field_name == "next_node":
                self.next_node_entry.setText(target_node_id)
            else:
                self.failure_node_entry.setText(target_node_id)

        self._cancel_preview_connection(clear_status=False)
        self._rebuild_connections()
        self._refresh_selected_item()
        self.status_message.setText(f"已连接: {source_node_id}.{field_name} -> {target_node_id}")

    def _clear_current_connections(self):
        if not self.current_node_id:
            QMessageBox.warning(self, "警告", "请先选择节点")
            return

        node = self.node_map[self.current_node_id]
        node.pop("next_node", None)
        node.pop("failure_node", None)
        self.next_node_entry.clear()
        self.failure_node_entry.clear()
        self._rebuild_connections()
        self._refresh_selected_item()
        self.status_message.setText(f"已清除节点连线: {self.current_node_id}")

    def _delete_selected_connections(self):
        selected_connections = [
            item for item in self.scene.selectedItems() if isinstance(item, FlowConnectionItem)
        ]
        if not selected_connections:
            return False

        for connection in selected_connections:
            source_node = self.node_map.get(connection.source_item.node_id)
            if not source_node:
                continue

            if source_node.get(connection.field_name) == connection.target_item.node_id:
                source_node.pop(connection.field_name, None)

            if self.current_node_id == connection.source_item.node_id:
                if connection.field_name == "next_node":
                    self.next_node_entry.clear()
                elif connection.field_name == "failure_node":
                    self.failure_node_entry.clear()

        self._rebuild_connections()
        self.status_message.setText("已删除选中的连线")
        return True

    def _handle_escape(self):
        """Esc 取消当前预览连线"""
        if self.preview_connection_item or self.pending_connection:
            self._cancel_preview_connection(clear_status=False)
            self.status_message.setText("已取消连线模式")

    def _handle_delete_shortcut(self):
        """删除当前选中的连线"""
        self._delete_selected_connections()

    def _handle_canvas_mouse_moved(self, scene_pos: QPointF):
        self.last_scene_mouse_pos = scene_pos
        if self.preview_connection_item:
            self.preview_connection_item.update_path(scene_pos)

    def _handle_background_clicked(self, scene_pos: QPointF):
        _ = scene_pos
        if self.preview_connection_item:
            self._cancel_preview_connection()

    def _cancel_preview_connection(self, clear_status: bool = True):
        if self.preview_connection_item:
            self.scene.removeItem(self.preview_connection_item)
            self.preview_connection_item = None
        if self.pending_connection:
            hidden_connection = self.pending_connection.get("hidden_connection")
            if hidden_connection:
                hidden_connection.setVisible(True)
        self.pending_connection = None
        self.canvas.set_connection_preview_active(False)
        if clear_status:
            self.status_message.setText("已取消连线模式")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            if self._delete_selected_connections():
                event.accept()
                return
        super().keyPressEvent(event)

    def _auto_layout(self):
        if not self.nodes:
            return

        spacing_x = 300
        spacing_y = 180
        for index, node in enumerate(self.nodes):
            x = (index % 4) * spacing_x
            y = (index // 4) * spacing_y
            node["position"] = {"x": x, "y": y}

        self._refresh_canvas()
        self.status_message.setText("已执行自动布局")

    def _browse_template(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择模板图片",
            str(Settings.TEMPLATE_DIR),
            "图片文件 (*.png *.jpg *.jpeg)",
        )
        if filename:
            self.template_entry.setText(Path(filename).name)

    def _screenshot_and_select(self):
        if not self.current_node_id:
            QMessageBox.warning(self, "警告", "请先选择节点")
            return

        target_entry = self.stop_template_entry if self.type_combo.currentText() == "swipe" else self.template_entry
        template_name = target_entry.text().strip()
        if not template_name:
            template_name = f"{self.current_node_id}.png"

        self.showMinimized()
        QTimer.singleShot(1000, lambda: self._do_screenshot(template_name))

    def _do_screenshot(self, template_name: str):
        try:
            result = self.screenshot_tool.capture_and_select(template_name)
            if result:
                target_entry = self.stop_template_entry if self.type_combo.currentText() == "swipe" else self.template_entry
                target_entry.setText(Path(result["template_path"]).name)
                self.center_entry.setText(f"{result['center'][0]}, {result['center'][1]}")
                QMessageBox.information(self, "成功", "模板已保存")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            QMessageBox.critical(self, "错误", f"截图失败: {e}")
        finally:
            self.showNormal()

    def _import_config(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON文件 (*.json)")
        if filename:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.nodes = config.get("nodes", [])
                self.current_node_id = None
                self._normalize_nodes()
                self._ensure_single_start_node()
                self._rebuild_index()
                self._refresh_canvas()
                QMessageBox.information(self, "成功", "配置已导入")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入失败: {e}")

    def _export_config(self):
        filename, _ = QFileDialog.getSaveFileName(self, "导出配置", "", "JSON文件 (*.json)")
        if filename:
            try:
                self._sync_positions_from_canvas()
                config = {"nodes": self.nodes}
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", "配置已导出")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _refresh_devices(self, select_device_id: str = None):
        self.android_adb_controller.refresh_devices(select_device_id=select_device_id)

    def _connect_device(self):
        self.android_adb_controller.connect_device()

    def _start_automation(self):
        if not self.adb_device or not self.adb_device.connected:
            QMessageBox.warning(self, "警告", "请先连接设备")
            return

        self._save_settings_if_needed(silent=True)
        self._save_config()
        reply = QMessageBox.question(
            self,
            "确认启动",
            "即将启动自动化流程\n\n请确保:\n1. 目标应用已打开到正确页面\n2. 手机屏幕保持常亮\n3. 不要手动操作手机\n\n是否继续?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self.app_settings.get("capture", {}).get("enabled"):
                self._start_capture_service()
            self.showMinimized()
            QTimer.singleShot(500, self._run_main_program)

    def _run_main_program(self):
        try:
            project_root = Path(__file__).parent.parent
            python_executable = sys.executable or "python3"
            env = os.environ.copy()
            env["ADB_DEVICE_ID"] = self.adb_device.device_id
            adb_path = self._get_configured_adb_path()
            if adb_path:
                env["ADB_PATH"] = adb_path
            if self.capture_manager.is_running():
                env["CAPTURE_MANAGED_BY_GUI"] = "1"

            process = subprocess.Popen(
                [python_executable, str(project_root / "main.py")],
                env=env,
                cwd=str(project_root),
            )

            QMessageBox.information(
                self,
                "已启动",
                f"自动化流程已启动\n进程ID: {process.pid}\n\n请查看终端日志了解执行情况",
            )
            self.showNormal()
        except Exception as e:
            logger.error(f"启动主程序失败: {e}")
            QMessageBox.critical(self, "错误", f"启动主程序失败: {e}")
            self.showNormal()

    @staticmethod
    def _parse_float(text: str, default: float):
        try:
            return float(text.strip()) if text.strip() else default
        except ValueError:
            return default

    @staticmethod
    def _parse_optional_float(text: str):
        try:
            return float(text.strip()) if text.strip() else None
        except ValueError:
            return None

    @staticmethod
    def _parse_optional_int(text: str):
        try:
            return int(text.strip()) if text.strip() else None
        except ValueError:
            return None

    @staticmethod
    def _to_text(value):
        return "" if value is None else str(value)

    def closeEvent(self, event):
        try:
            if hasattr(self, "capture_refresh_timer"):
                self.capture_refresh_timer.stop()
            if self.capture_manager:
                self.capture_manager.stop()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app_settings = AppSettings.load()
    if app_settings.get("auth", {}).get("token") and not AppSettings.is_auth_valid(app_settings):
        app_settings = AppSettings.clear_auth()
    elif AppSettings.is_auth_valid(app_settings):
        verify_result = verify_auth()
        if not verify_result.get("data", {}).get("valid"):
            app_settings = AppSettings.load()
        else:
            app_settings = AppSettings.load()

    if AppSettings.is_auth_valid(app_settings):
        window = NodeEditorApp(app_settings=app_settings)
    else:
        window = LoginWindow(app_settings=app_settings)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
