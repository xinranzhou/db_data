# 当前桌面端架构说明

## 当前定位

当前桌面应用已经从“自动化工作台”收敛为 **iOS 手动抓包工作台**。

面向当前业务，主链只解决四件事：

1. 启动 `mitmproxy` 抓包服务
2. 给 iPhone 提供手动代理地址和 CA 下载入口
3. 同步点评抓包并转成结构化商家数据
4. 对无电话商家执行 Playwright 补抓

## 当前页面

桌面端当前只保留三个页面：

1. 抓取实时数据
2. 数据管理
3. 抓包配置

## 当前主入口

- 应用启动入口：`node_editor_app.py`
- 主窗口实现：`gui/capture/capture_only_window.py`

## 当前关键模块

- `gui/capture/capture_only_window.py`
  - 当前桌面端总装配

- `integration/http_capture.py`
  - `mitmdump` 启停、CA 服务、抓包 inbox 导入

- `data/structured_capture.py`
  - 点评协议加载与结构化入库

- `gui/capture/realtime_capture_controller.py`
  - 实时抓包同步、录入、导出、清理

- `gui/capture/structured_data_controller.py`
  - 结构化列表筛选、分页、导出、电话补抓

- `playright/detail_enricher.py`
  - 浏览器详情页补抓与回写

## 已退出主链的能力

以下能力已不再参与当前桌面端运行和打包：

1. 节点编排页面
2. 模板截图与模板匹配自动化
3. Android ADB 连接
4. Android 代理自动应用 / 清理 / 诊断
5. 旧的自动化执行入口 `main.py`

这些代码已统一归档到：

- `archive/legacy_desktop/`

## 依赖收敛结果

当前主链不再依赖以下旧自动化依赖：

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
