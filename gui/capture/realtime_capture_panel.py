#!/usr/bin/env python3

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from data.capture_store import CaptureStore


def build_realtime_capture_page(editor):
    page = QWidget()
    root_layout = QVBoxLayout(page)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    root_layout.addWidget(scroll)

    content = QWidget()
    scroll.setWidget(content)

    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    hero_card = QFrame()
    hero_card.setObjectName("dataHeroCard")
    hero_layout = QVBoxLayout(hero_card)
    hero_layout.setContentsMargins(20, 18, 20, 18)
    hero_layout.setSpacing(14)

    hero_title = QLabel("抓取实时数据")
    hero_title.setObjectName("dataHeroTitle")
    hero_subtitle = QLabel("这里处理实时抓包、接口转换和原始抓包导出。")
    hero_subtitle.setWordWrap(True)
    hero_subtitle.setObjectName("dataHeroSubtitle")

    control_row = QHBoxLayout()
    control_row.setSpacing(10)
    editor.capture_interface_combo = QComboBox()
    editor.capture_interface_combo.currentIndexChanged.connect(editor._handle_interface_selection_changed)
    editor.capture_interface_combo.setMinimumWidth(240)
    btn_sync_raw = QPushButton("开始收集数据")
    btn_sync_raw.clicked.connect(editor._refresh_capture_table)
    btn_import_structured = QPushButton("录入抓取数据")
    btn_import_structured.clicked.connect(editor._import_structured_records)
    btn_export_capture = QPushButton("导出原始抓包")
    btn_export_capture.clicked.connect(editor._export_capture_excel)
    btn_clear_capture = QPushButton("清理临时抓包")
    btn_clear_capture.clicked.connect(editor._clear_temporary_capture_data)
    btn_operation_help = QPushButton("操作说明")
    btn_operation_help.clicked.connect(editor._show_data_operation_help)
    for button in [
        btn_sync_raw,
        btn_import_structured,
        btn_export_capture,
        btn_clear_capture,
        btn_operation_help,
    ]:
        button.setMinimumWidth(108)
    control_row.addWidget(QLabel("接口"))
    control_row.addWidget(editor.capture_interface_combo)
    control_row.addStretch()
    control_row.addWidget(btn_sync_raw)
    control_row.addWidget(btn_import_structured)
    control_row.addWidget(btn_export_capture)
    control_row.addWidget(btn_clear_capture)
    control_row.addWidget(btn_operation_help)

    badge_row = QHBoxLayout()
    badge_row.setSpacing(10)
    editor.capture_rules_summary_label = QLabel("抓包接口: -")
    editor.capture_rules_summary_label.setObjectName("dataBadge")
    editor.capture_status_label = QLabel("抓取状态: 未启动")
    editor.capture_status_label.setObjectName("dataBadge")
    badge_row.addWidget(editor.capture_rules_summary_label)
    badge_row.addWidget(editor.capture_status_label)
    badge_row.addStretch()

    hero_layout.addWidget(hero_title)
    hero_layout.addWidget(hero_subtitle)
    hero_layout.addLayout(control_row)
    hero_layout.addLayout(badge_row)
    layout.addWidget(hero_card)

    editor.protocol_summary_label = QLabel("当前尚未加载接口协议")
    editor.protocol_summary_label.setWordWrap(True)
    editor.protocol_summary_label.setObjectName("dataInfo")
    editor.protocol_fields_label = QLabel("导出字段: -")
    editor.protocol_fields_label.setWordWrap(True)
    editor.protocol_fields_label.setObjectName("dataInfo")
    editor.protocol_config_path_label = QLabel("协议文件: -")
    editor.protocol_config_path_label.setWordWrap(True)
    editor.protocol_config_path_label.setObjectName("dataInfo")

    layout.addWidget(editor.protocol_summary_label)
    layout.addWidget(editor.protocol_fields_label)
    layout.addWidget(editor.protocol_config_path_label)

    editor.capture_table = QTableWidget(0, len(CaptureStore.COLUMNS))
    editor.capture_table.setHorizontalHeaderLabels([title for _, title in CaptureStore.COLUMNS])
    editor.capture_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    editor.capture_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    editor.capture_table.verticalHeader().setVisible(False)
    editor.capture_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    editor.capture_table.itemSelectionChanged.connect(editor._handle_capture_selection_changed)

    editor.capture_detail_text = QPlainTextEdit()
    editor.capture_detail_text.setReadOnly(True)
    editor.capture_detail_text.setPlaceholderText("选中一条抓取记录后，这里显示完整响应体。")

    raw_panel = QWidget()
    raw_layout = QVBoxLayout(raw_panel)
    raw_layout.setContentsMargins(0, 0, 0, 0)
    raw_layout.setSpacing(8)

    raw_splitter = QSplitter(Qt.Vertical)
    raw_splitter.addWidget(editor.capture_table)
    raw_splitter.addWidget(editor.capture_detail_text)
    raw_splitter.setStretchFactor(0, 3)
    raw_splitter.setStretchFactor(1, 2)
    raw_layout.addWidget(raw_splitter, 1)

    layout.addWidget(raw_panel, 1)
    return page
