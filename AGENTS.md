# py_test 开发维护说明

## 1. 当前项目定位

当前项目已经从“自动化工作台”收敛为 **iOS 手动抓包工作台**，当前主链重点只有三类能力：

1. iPhone / iPad 手动代理抓包配置
2. 点评 / 美团接口实时抓取、结构化入库、数据管理
3. 基于 Playwright 的商家详情补抓，当前主要用于补抓电话字段

当前桌面端**不再默认启用**以下能力：

1. 节点编排式自动化流程编辑
2. 模板截图、模板匹配、点击/滚动自动化
3. Android ADB 连接与代理自动下发

这些旧能力已统一归档到 `archive/legacy_desktop/`。

## 2. 当前主入口

当前桌面端主入口：

- `node_editor_app.py`

当前实际主窗口：

- `gui/capture/capture_only_window.py`

当前桌面端固定三个页面：

1. 抓取实时数据
2. 数据管理
3. 抓包配置

## 3. 当前核心目录

- `gui/capture/`
  - 当前桌面端主链 UI 与控制器
  - 包含实时抓包、数据管理、iOS 手动抓包说明、CA 证书页、当前主窗口

- `integration/`
  - 抓包链路相关集成
  - 当前核心是 `http_capture.py`、`mitm_capture_addon.py`、`cert_asset_server.py`

- `data/`
  - 抓包临时数据、SQLite 数据库、结构化数据转换逻辑
  - `captures.db` 是当前抓包与结构化记录的核心数据库

- `playright/`
  - Playwright 补抓详情页逻辑
  - 当前用于补抓商家电话、输出结果文件、回写结构化数据

- `config/`
  - 全局配置与协议配置
  - `config/meituan/` 存放抓包协议和字段转换规则

- `archive/legacy_desktop/`
  - 已退出主链的历史代码
  - 包括旧节点编排、Android ADB、模板截图、自动化执行入口

## 4. 当前关键文件

- `node_editor_app.py`
  - 桌面端启动入口

- `gui/capture/capture_only_window.py`
  - 当前主窗口和总装配文件

- `integration/http_capture.py`
  - 抓包进程管理
  - CA 资产服务启动
  - inbox 导入
  - 临时抓包清理

- `data/structured_capture.py`
  - 点评协议加载与结构化转换核心

- `playright/detail_enricher.py`
  - Playwright 详情页补抓核心逻辑

- `start_playright.sh`
  - Playwright 独立测试脚本入口

## 5. 当前抓包链路说明

当前抓包链路大致为：

1. UI 保存抓包配置
2. `integration/http_capture.py` 启动 `mitmdump`
3. `integration/mitm_capture_addon.py` 根据运行时配置匹配目标请求
4. 命中的响应写入 `data/capture_inbox.jsonl`
5. `HttpCaptureManager.import_pending()` 把 inbox 内容导入 `data/captures.db`
6. `data/structured_capture.py` 根据 `config/meituan/*.json` 协议规则转换为结构化记录
7. “数据管理”页从 `structured_records` 中展示最终结果

当前抓包模式以 **iOS 手动代理模式** 为主：

1. 启动抓包服务
2. 在 iPhone Wi-Fi 设置里手动填写代理
3. 用 Safari 打开 CA 下载地址并安装证书
4. 在系统设置里手动开启完全信任
5. 回到桌面端同步抓包并录入结构化数据

## 6. 当前页面职责约定

- “抓取实时数据”页：
  - 只负责实时抓包同步、查看、转换

- “数据管理”页：
  - 只负责最终结构化结果管理

- “抓包配置”页：
  - 只负责抓包服务、CA 下载、iOS 手动抓包说明

当前主链下，不要再往桌面端加入新的 Android 自动代理或节点编排入口。

## 7. 已归档模块说明

以下内容已经统一归档到 `archive/legacy_desktop/`：

- `main.py`
  - 旧自动化执行入口

- `automation/`
  - 自动化流程引擎和业务级执行逻辑

- `core/`
  - ADB、截图、点击模拟、模板匹配、节点执行等基础能力

- `gui/node_editor.py`
  - 旧的全量桌面主窗口

- `gui/screenshot_tool.py`
  - 旧模板截图工具

- `gui/capture/android_*`
  - Android ADB 与代理自动控制逻辑

- `gui/capture/adb_panel.py`
  - 旧设备代理面板

- `templates/`
  - 旧节点编排模板资源

除非明确要恢复旧自动化方案，否则不要修改这些归档文件。

## 8. 当前依赖原则

当前主链已经不再依赖以下旧自动化依赖：

- `opencv-python`
- `numpy`
- `pyautogui`

当前主链仍保留：

- `PyQt5`
- `mitmproxy`
- `qrcode[pil]`
- `openpyxl`
- `playwright`
- `pillow`

## 9. 测试与校验

当前可直接执行的基础校验命令：

```bash
python3 -m py_compile node_editor_app.py gui/capture/capture_only_window.py gui/capture/*.py integration/http_capture.py
python3 -m unittest test_auth_service.py
```

说明：

- 旧文档里提到的 `test_capture_connectivity.py`、`test_http_capture_manager.py`、`test_playright_mock.py` 在当前仓库快照中不存在，不应再作为当前默认验证命令。

## 10. 开发约定

1. 如果需求只涉及 iPhone 抓包、点评结构化入库、数据管理、Playwright 电话补抓，直接在当前主链实现，不要回到归档代码里加功能。
2. 如果后续真的要恢复 Android 自动代理或节点编排，请先说明原因，并先评估是复用归档代码，还是基于当前 `capture-only` 架构重新设计。
3. 修改打包逻辑时，默认以 `node_editor_app.py -> gui/capture/capture_only_window.py` 为唯一桌面发布入口。
4. Gitee CI/CD 只以根目录 `gitee.yml` 为唯一生产真源；其他历史 Gitee 配置仅归档参考，不再并行维护。


<claude-mem-context>
# Memory Context

# [py_test] recent context, 2026-05-05 8:44pm GMT+8

No previous sessions found.
</claude-mem-context>
