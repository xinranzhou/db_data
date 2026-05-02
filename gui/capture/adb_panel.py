#!/usr/bin/env python3

from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


def build_adb_group(editor):
    adb_group = QGroupBox("设备与代理")
    adb_layout = QVBoxLayout(adb_group)
    adb_layout.setSpacing(8)

    editor.adb_summary_label = QLabel("先连接 Android 设备，再到“抓包配置”按 3 步完成代理与证书设置。")
    editor.adb_summary_label.setObjectName("captureInlineMeta")
    editor.adb_summary_label.setWordWrap(True)

    editor.device_combo = QComboBox()
    editor.device_combo.setMinimumWidth(240)
    editor.remote_address_entry = QLineEdit()
    editor.remote_address_entry.setPlaceholderText("192.168.1.2:5555")
    editor.remote_address_entry.setMinimumWidth(180)
    editor.pair_address_entry = QLineEdit()
    editor.pair_address_entry.setPlaceholderText("192.168.1.2:37143")
    editor.pair_code_entry = QLineEdit()
    editor.pair_code_entry.setPlaceholderText("6位配对码")
    editor.pair_code_entry.setMaxLength(12)

    btn_refresh = QPushButton("刷新设备")
    btn_refresh.clicked.connect(editor._refresh_devices)
    btn_connect_remote = QPushButton("无线连接")
    btn_connect_remote.clicked.connect(editor._connect_remote_device)
    btn_disconnect_remote = QPushButton("断开无线")
    btn_disconnect_remote.clicked.connect(editor._disconnect_remote_device)
    btn_pair_remote = QPushButton("无线配对")
    btn_pair_remote.clicked.connect(editor._pair_remote_device)
    btn_qr_pair = QPushButton("二维码配对")
    btn_qr_pair.clicked.connect(editor._open_qr_pair_dialog)
    btn_install_adb = QPushButton("安装ADB")
    btn_install_adb.clicked.connect(editor._download_adb_tools)
    btn_connect = QPushButton("连接")
    btn_connect.clicked.connect(editor._connect_device)

    editor.status_label = QLabel("未连接")
    editor.proxy_status_label = QLabel("代理: 未检测")
    editor.proxy_status_label.setStyleSheet("color: #475569; font-weight: 600;")
    editor.proxy_fix_button = QPushButton("一键修正代理")
    editor.proxy_fix_button.clicked.connect(editor._fix_android_proxy_from_topbar)
    editor.proxy_fix_button.setVisible(False)
    editor.proxy_restore_button = QPushButton("恢复原代理")
    editor.proxy_restore_button.clicked.connect(editor._restore_previous_android_proxy)
    editor.proxy_restore_button.setVisible(False)
    editor.proxy_emergency_clear_button = QPushButton("紧急清除手机代理")
    editor.proxy_emergency_clear_button.clicked.connect(editor._emergency_clear_android_proxy)
    editor.adb_tool_label = QLabel("ADB: 检测中")
    editor.adb_network_label = QLabel("局域网: 检测中")
    editor.adb_network_label.setWordWrap(True)
    editor.adb_guide_label = QLabel("首次无线调试：先二维码配对或配对码配对，再填写调试地址连接。")
    editor.adb_guide_label.setWordWrap(True)
    editor.btn_start = QPushButton("启动自动化")
    editor.btn_start.clicked.connect(editor._start_automation)
    editor.btn_start.setEnabled(False)

    connect_row = QHBoxLayout()
    connect_row.setSpacing(8)
    connect_row.addWidget(QLabel("已发现设备:"))
    connect_row.addWidget(editor.device_combo)
    connect_row.addWidget(QLabel("无线地址:"))
    connect_row.addWidget(editor.remote_address_entry)
    connect_row.addWidget(btn_refresh)
    connect_row.addWidget(btn_connect_remote)
    connect_row.addWidget(btn_disconnect_remote)
    connect_row.addWidget(btn_connect)
    connect_row.addWidget(editor.btn_start)

    pair_row = QHBoxLayout()
    pair_row.setSpacing(8)
    pair_row.addWidget(QLabel("配对地址:"))
    pair_row.addWidget(editor.pair_address_entry)
    pair_row.addWidget(QLabel("配对码:"))
    pair_row.addWidget(editor.pair_code_entry)
    pair_row.addWidget(btn_pair_remote)
    pair_row.addWidget(btn_qr_pair)
    pair_row.addWidget(btn_install_adb)
    pair_row.addStretch()
    pair_row.addWidget(editor.adb_tool_label)

    info_row = QHBoxLayout()
    info_row.setSpacing(12)
    info_row.addWidget(editor.status_label, 1)
    info_row.addWidget(editor.proxy_status_label, 1)
    info_row.addWidget(editor.proxy_fix_button)
    info_row.addWidget(editor.proxy_restore_button)
    info_row.addWidget(editor.proxy_emergency_clear_button)
    info_row.addWidget(editor.adb_network_label, 1)
    info_row.addWidget(editor.adb_tool_label)

    adb_layout.addWidget(editor.adb_summary_label)
    adb_layout.addLayout(connect_row)
    adb_layout.addLayout(pair_row)
    adb_layout.addLayout(info_row)
    adb_layout.addWidget(editor.adb_guide_label)
    return adb_group
