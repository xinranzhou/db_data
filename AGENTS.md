# py_test 开发维护说明

## 1. 项目定位

这是一个以 `PyQt5` 为桌面入口的自动化工作台，当前主要包含四类能力：

1. 节点编排式自动化流程编辑与执行
2. Android / iOS 抓包配置与抓包服务管理
3. 点评 / 美团接口实时抓取、结构化入库、数据管理
4. 基于 Playwright 的商家详情补抓，当前主要用于补抓电话字段

当前主入口仍然是：

- `node_editor_app.py`
- `gui/node_editor.py`

其中 `gui/node_editor.py` 仍然是总装配层，但抓包相关 UI 和行为已经开始拆分到 `gui/capture/`。

---

## 2. 顶层目录说明

### 2.1 核心目录

- `gui/`
  - 桌面端 UI 相关代码
  - 当前主窗口在 `gui/node_editor.py`
  - 截图工具在 `gui/screenshot_tool.py`

- `gui/capture/`
  - 抓包模块拆分后的子模块
  - 负责 Android ADB、代理、CA、iOS 手动抓包提示、实时抓包页、数据管理页
  - 这是后续继续演进抓包模块的主目录

- `core/`
  - 自动化执行的基础能力
  - 包括 `adb_device.py`、`screen_capture.py`、`node_executor.py`、`template_matcher.py`

- `automation/`
  - 自动化流程引擎和业务级执行逻辑
  - 包括滚动采集、区域识别、重试处理、工作流引擎

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

- `templates/`
  - 图像模板资源，用于节点自动化识别

- `logs/`
  - 运行日志目录

---

## 3. 当前关键入口文件

- `node_editor_app.py`
  - 启动桌面应用的入口

- `gui/node_editor.py`
  - 当前主窗口和总装配文件
  - 管理四个页面：
    - 节点编排
    - 抓取实时数据
    - 数据管理
    - 抓包配置
  - 当前仍然偏大，但抓包相关职责已拆出一部分

- `main.py`
  - 旧入口或命令型入口，保留时需先确认实际使用路径

- `start_playright.sh`
  - Playwright 独立测试脚本入口

- `playright/__main__.py`
  - Playwright 命令行入口

---

## 4. 当前抓包模块拆分状态

### 4.1 已拆出的目录

`gui/capture/` 当前文件职责如下：

- `adb_panel.py`
  - 顶部“设备与代理”区域 UI

- `android_adb_controller.py`
  - Android ADB 连接、无线配对、设备刷新、ADB 下载、设备连接

- `android_proxy_controller.py`
  - Android 代理应用、恢复、清理、连通性检测、状态刷新

- `ca_certificate_controller.py`
  - 抓包服务状态、CA 下载地址、二维码、证书状态、HTTPS 诊断

- `ios_capture_controller.py`
  - iOS 手动抓包模式提示、检查项、平台切换相关逻辑

- `capture_settings_panel.py`
  - “抓包配置”页面 UI

- `realtime_capture_panel.py`
  - “抓取实时数据”页面 UI

- `realtime_capture_controller.py`
  - 实时抓包同步、录入抓取数据、导出原始抓包、清理临时抓包

- `data_management_panel.py`
  - “数据管理”页面 UI

- `structured_data_controller.py`
  - 结构化列表刷新、筛选、分页、结构化导出、电话补抓启动与回调

- `platform_state.py`
  - 平台状态相关辅助逻辑

### 4.2 当前未完全拆完的部分

以下逻辑仍主要集中在 `gui/node_editor.py`：

- 节点编排画布与属性编辑
- 页面总装配
- 协议选择与接口同步逻辑
- 设置保存与部分总控行为
- Playwright Worker 定义

结论：

- 抓包模块已经初步形成 `panel + controller` 结构
- 但 `node_editor.py` 仍是总线文件，后续若继续重构，建议优先拆“协议选择/规则同步”

---

## 5. 抓包链路说明

### 5.1 运行链路

当前抓包链路大致为：

1. UI 保存抓包配置
2. `integration/http_capture.py` 启动 `mitmdump`
3. `integration/mitm_capture_addon.py` 根据运行时配置匹配目标请求
4. 命中的响应写入 `data/capture_inbox.jsonl`
5. `HttpCaptureManager.import_pending()` 把 inbox 内容导入 `data/captures.db`
6. `data/structured_capture.py` 根据 `config/meituan/*.json` 协议规则转换为结构化记录
7. “数据管理”页从 `structured_records` 中展示最终结果

### 5.2 关键数据文件

- `data/capture_inbox.jsonl`
  - mitm 插件落地的原始抓包流

- `data/capture_inbox.offset`
  - inbox 已消费偏移量

- `data/capture_runtime.json`
  - 当前抓包运行时规则

- `data/captures.db`
  - SQLite 主数据库
  - 包含：
    - `captures`
    - `structured_records`
    - `record_failures`
    - `dataset_sync_state`

### 5.3 抓包服务核心代码

- `integration/http_capture.py`
  - 抓包进程管理
  - CA 资产服务启动
  - inbox 导入
  - 临时抓包清理

- `integration/cert_asset_server.py`
  - 本地 CA 下载服务

- `integration/mitm_capture_addon.py`
  - mitm 插件

---

## 6. 协议配置与结构化入库

### 6.1 协议目录

- `config/meituan/`

当前目录下主要放：

- 接口匹配规则
- 导出字段
- 记录唯一 key 规则
- 实体编码
- 结构化字段映射

### 6.2 结构化转换核心

- `data/structured_capture.py`
  - `MeituanConfigLoader`
  - `MeituanCaptureImporter`

当前原则：

1. “抓取实时数据”页只做实时抓包查看与转换触发
2. “数据管理”页只展示最终结构化结果
3. 录入抓取数据时只按当前选中的接口协议执行，不再全量混跑

---

## 7. 数据管理模块说明

### 7.1 页面职责

“数据管理”页是当前结构化结果的维护入口，主要负责：

1. 列表展示最终商家数据
2. 支持区域、商家名称、电话状态、新增电话标签筛选
3. 支持分页展示
4. 支持导出结构化结果
5. 启动 Playwright 批量补抓无电话商家

### 7.2 当前关键字段

当前列表重点关注这些字段：

- 商家名称 `name`
- 区域 `regionName` / `region_name`
- 店铺 ID `shopUuid` / `shop_uuid`
- 类型 `shopType` / `shop_type`
- 评分 `starScore`
- 是否有电话
- 电话
- 新增电话标记
- 是否已沟通
- 抓取状态
- 抓取时间

### 7.3 状态维护规则

- “新增电话”支持手动勾选
- “是否已沟通”支持手动勾选
- 电话补抓时只跑当前筛选结果中的无电话商家
- 支持 `starScore < 阈值` 过滤后再补抓

---

## 8. Playwright 补抓模块说明

### 8.1 目录

- `playright/`

当前主要文件：

- `playright/detail_enricher.py`
  - 详情页抓取核心逻辑
  - 数据集适配
  - 结果文件输出
  - 数据库回写

- `playright/__main__.py`
  - 命令行入口

- `start_playright.sh`
  - Shell 启动脚本

- `test_playright_mock.py`
  - mock 测试

### 8.2 当前用途

当前 Playwright 主要用于：

1. 批量打开点评商家详情页
2. 识别是否存在电话入口
3. 抓取电话信息并回写到结构化数据
4. 输出运行结果文件到 `data/playright/runs/`

### 8.3 当前集成方式

桌面端通过 `PlaywrightBatchWorker` 启动批量补抓任务，页面层只负责：

- 设置本次数量
- 设置并发
- 设置评分阈值
- 展示进度与完成状态

---

## 9. 自动化节点编排模块说明

### 9.1 主要文件

- `gui/node_editor.py`
  - 节点画布、节点属性编辑、连线、保存/导入导出

- `core/node_executor.py`
  - 节点执行基础逻辑

- `automation/workflow_engine.py`
  - 流程执行引擎

- `core/template_matcher.py`
  - 图像匹配

- `core/click_simulator.py`
  - 点击模拟

- `core/screen_capture.py`
  - 屏幕截图

### 9.2 当前页面结构

桌面应用当前固定四个页面：

1. 节点编排
2. 抓取实时数据
3. 数据管理
4. 抓包配置

---

## 10. 配置与持久化文件

### 10.1 全局路径定义

- `config/settings.py`
  - 定义项目级路径和默认参数

### 10.2 应用设置

- `config/app_settings.json`
  - UI 层保存的运行配置

- `config/app_settings.py`
  - 应用设置读写逻辑

### 10.3 节点配置

- `config/nodes.json`
  - 节点编排保存结果

- `config/regions.json`
  - 区域配置

- `config/cache.json`
  - 缓存数据

---

## 11. 测试与校验

当前已存在的重点测试文件：

- `test_capture_connectivity.py`
  - 抓包连通性检测相关测试

- `test_http_capture_manager.py`
  - 抓包管理器相关测试

- `test_playright_mock.py`
  - Playwright mock 测试

常用校验命令：

```bash
python3 -m py_compile gui/node_editor.py gui/capture/*.py
python3 -m unittest test_capture_connectivity.py test_http_capture_manager.py
python3 -m unittest test_playright_mock.py
```

---

## 12. 当前开发约定

### 12.1 页面职责约定

- “抓取实时数据”页：
  - 只负责实时抓包同步、查看、转换

- “数据管理”页：
  - 只负责最终结构化结果管理

- “抓包配置”页：
  - 只负责抓包服务、代理、CA、平台切换

### 12.2 抓包模块开发约定

后续新增抓包功能时，优先遵循以下结构：

1. `panel.py` 负责 UI 组件构建
2. `controller.py` 负责行为和状态更新
3. `gui/node_editor.py` 只负责装配、桥接和全局入口

### 12.3 修改风险点

以下位置改动时要特别谨慎：

- `integration/http_capture.py`
  - 容易影响抓包服务启动、端口监听、CA 服务

- `data/capture_store.py`
  - 容易影响数据库结构、抓包导出、结构化记录读写

- `data/structured_capture.py`
  - 容易影响协议匹配、字段转换、去重逻辑

- `playright/detail_enricher.py`
  - 容易影响详情页补抓成功率与结果回写

- `gui/node_editor.py`
  - 仍是总装配核心，改动容易牵连多个页面

---

## 13. 后续建议

当前如果继续整理代码，建议优先顺序如下：

1. 继续从 `gui/node_editor.py` 拆出“协议选择 / 规则同步”控制器
2. 逐步把抓包相关的总控逻辑从 `node_editor.py` 下沉到 `gui/capture/`
3. 为 `structured_data_controller.py` 和 `realtime_capture_controller.py` 增加更细粒度测试
4. 对 `playright/` 增加更明确的运行参数说明和结果文件说明

---

## 14. 当前建议阅读顺序

新开发同学建议按下面顺序读代码：

1. `config/settings.py`
2. `gui/node_editor.py`
3. `gui/capture/` 目录
4. `integration/http_capture.py`
5. `data/capture_store.py`
6. `data/structured_capture.py`
7. `playright/detail_enricher.py`
8. `core/adb_device.py`

这样可以先理解总入口，再理解抓包链路、数据链路和补抓链路。


<claude-mem-context>
# Memory Context

# [py_test] recent context, 2026-04-30 11:07am GMT+8

No previous sessions found.
</claude-mem-context>