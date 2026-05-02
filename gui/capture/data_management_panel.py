#!/usr/bin/env python3

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


def build_data_management_page(editor):
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
    hero_layout = QHBoxLayout(hero_card)
    hero_layout.setContentsMargins(18, 16, 18, 16)
    hero_layout.setSpacing(10)

    hero_title = QLabel("数据管理")
    hero_title.setObjectName("dataHeroTitle")
    editor.structured_interface_label = QLabel("接口: -")
    editor.structured_interface_label.setObjectName("dataBadge")

    btn_refresh_list = QPushButton("刷新")
    btn_refresh_list.clicked.connect(lambda: editor._refresh_structured_views(reset_page=False))
    btn_export_structured = QPushButton("导出")
    btn_export_structured.clicked.connect(editor._export_structured_excel)
    btn_management_help = QPushButton("说明")
    btn_management_help.clicked.connect(editor._show_data_management_help)
    for button in [btn_refresh_list, btn_export_structured, btn_management_help]:
        button.setMinimumWidth(74)
        button.setMinimumHeight(34)
    editor.structured_summary_label = QLabel("记录: 0")
    editor.structured_summary_label.setObjectName("dataBadge")
    editor.structured_phone_has_label = QLabel("有: 0")
    editor.structured_phone_has_label.setObjectName("dataBadge")
    editor.structured_phone_none_label = QLabel("无: 0")
    editor.structured_phone_none_label.setObjectName("dataBadge")
    editor.structured_new_phone_label = QLabel("新增: 0")
    editor.structured_new_phone_label.setObjectName("dataBadge")
    editor.playwright_run_status_label = QLabel("抓取: 未启动")
    editor.playwright_run_status_label.setObjectName("dataBadge")
    hero_layout.addWidget(hero_title)
    hero_layout.addWidget(editor.structured_interface_label)
    hero_layout.addWidget(editor.structured_summary_label)
    hero_layout.addWidget(editor.structured_phone_has_label)
    hero_layout.addWidget(editor.structured_phone_none_label)
    hero_layout.addWidget(editor.structured_new_phone_label)
    hero_layout.addWidget(editor.playwright_run_status_label)
    hero_layout.addStretch()
    hero_layout.addWidget(btn_refresh_list)
    hero_layout.addWidget(btn_export_structured)
    hero_layout.addWidget(btn_management_help)
    layout.addWidget(hero_card)

    structured_panel = QWidget()
    structured_layout = QVBoxLayout(structured_panel)
    structured_layout.setContentsMargins(0, 0, 0, 0)
    structured_layout.setSpacing(8)
    structured_hint = QLabel("这里管理最终商家数据和电话状态。")
    structured_hint.setWordWrap(True)
    structured_layout.addWidget(structured_hint)

    filter_row = QHBoxLayout()
    filter_row.setSpacing(8)
    editor.structured_region_filter = QLineEdit()
    editor.structured_region_filter.setPlaceholderText("区域模糊搜索")
    editor.structured_region_filter.setMinimumWidth(120)
    editor.structured_keyword_filter = QLineEdit()
    editor.structured_keyword_filter.setPlaceholderText("商家名称搜索")
    editor.structured_keyword_filter.setMinimumWidth(150)
    editor.structured_score_filter = QLineEdit()
    editor.structured_score_filter.setPlaceholderText("评分，如 <4.0 / 3.5-4.2")
    editor.structured_score_filter.setMinimumWidth(150)
    editor.structured_phone_filter = QComboBox()
    editor.structured_phone_filter.addItems(["全部", "有", "无", "未抓"])
    editor.structured_phone_filter.setMinimumWidth(88)
    editor.structured_new_phone_filter = QComboBox()
    editor.structured_new_phone_filter.addItems(["全部", "仅新增", "非新增"])
    editor.structured_new_phone_filter.setMinimumWidth(96)
    btn_apply_filter = QPushButton("查询")
    btn_apply_filter.clicked.connect(editor._apply_structured_filters)
    btn_reset_filter = QPushButton("重置")
    btn_reset_filter.clicked.connect(editor._reset_structured_filters)
    btn_apply_filter.setMinimumWidth(68)
    btn_reset_filter.setMinimumWidth(68)
    filter_row.addWidget(QLabel("区域"))
    filter_row.addWidget(editor.structured_region_filter)
    filter_row.addWidget(QLabel("商家"))
    filter_row.addWidget(editor.structured_keyword_filter)
    filter_row.addWidget(QLabel("评分"))
    filter_row.addWidget(editor.structured_score_filter)
    filter_row.addWidget(QLabel("电话"))
    filter_row.addWidget(editor.structured_phone_filter)
    filter_row.addWidget(QLabel("新增"))
    filter_row.addWidget(editor.structured_new_phone_filter)
    filter_row.addWidget(btn_apply_filter)
    filter_row.addWidget(btn_reset_filter)
    filter_row.addStretch()
    structured_layout.addLayout(filter_row)

    batch_row = QHBoxLayout()
    batch_row.setSpacing(8)
    editor.playwright_limit_spin = QSpinBox()
    editor.playwright_limit_spin.setRange(1, 10000)
    editor.playwright_limit_spin.setValue(20)
    editor.playwright_concurrency_spin = QSpinBox()
    editor.playwright_concurrency_spin.setRange(1, 8)
    editor.playwright_concurrency_spin.setValue(1)
    editor.playwright_star_score_spin = QDoubleSpinBox()
    editor.playwright_star_score_spin.setRange(0.0, 5.0)
    editor.playwright_star_score_spin.setDecimals(2)
    editor.playwright_star_score_spin.setSingleStep(0.1)
    editor.playwright_star_score_spin.setValue(5.0)
    editor.playwright_star_score_spin.setSpecialValueText("不限")
    editor.playwright_page_label = QLabel("第 1 / 1 页")
    editor.playwright_run_button = QPushButton("抓取无电话商家")
    editor.playwright_run_button.clicked.connect(editor._start_playwright_phone_fetch)
    editor.playwright_prev_page_button = QPushButton("上一页")
    editor.playwright_prev_page_button.clicked.connect(lambda: editor._change_structured_page(-1))
    editor.playwright_next_page_button = QPushButton("下一页")
    editor.playwright_next_page_button.clicked.connect(lambda: editor._change_structured_page(1))
    batch_row.addWidget(QLabel("抓取商家数"))
    batch_row.addWidget(editor.playwright_limit_spin)
    batch_row.addWidget(QLabel("一次性抓取数"))
    batch_row.addWidget(editor.playwright_concurrency_spin)
    batch_row.addWidget(QLabel("评分要求<"))
    batch_row.addWidget(editor.playwright_star_score_spin)
    batch_row.addWidget(editor.playwright_run_button)
    batch_row.addStretch()
    batch_row.addWidget(editor.playwright_prev_page_button)
    batch_row.addWidget(editor.playwright_page_label)
    batch_row.addWidget(editor.playwright_next_page_button)
    structured_layout.addLayout(batch_row)

    editor.structured_table = QTableWidget(0, 7)
    editor.structured_table.setHorizontalHeaderLabels([
        "商家名称",
        "区域",
        "shop_uuid",
        "评分",
        "是否有电话",
        "最近时间",
        "操作",
    ])
    editor.structured_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    editor.structured_table.verticalHeader().setVisible(False)
    header = editor.structured_table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)
    editor.structured_table.setMinimumHeight(520)
    editor.structured_table.setColumnWidth(0, 280)
    editor.structured_table.setColumnWidth(1, 160)
    editor.structured_table.setColumnWidth(2, 150)
    editor.structured_table.setColumnWidth(3, 100)
    editor.structured_table.setColumnWidth(4, 180)
    editor.structured_table.setColumnWidth(5, 190)
    editor.structured_table.setColumnWidth(6, 220)
    editor.structured_table.itemSelectionChanged.connect(editor._handle_structured_selection_changed)
    structured_layout.addWidget(editor.structured_table, 1)

    layout.addWidget(structured_panel, 1)
    return page
