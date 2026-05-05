# 归档说明

## 归档背景

当前桌面端主链已经收敛为 **iOS 手动抓包 + 实时抓包查看 + 结构化数据管理 + Playwright 电话补抓**。

以下能力已退出当前主发布链：

1. 节点编排式自动化流程编辑
2. 基于模板识别的截图 / 点击 / 滚动自动化
3. Android ADB 连接、无线配对、代理自动下发
4. 旧的全量桌面主窗口总装配

为了避免这些历史代码继续干扰当前维护和打包，相关文件已集中移动到 `archive/legacy_desktop/`。

## 当前主入口

- 桌面端主入口：`node_editor_app.py`
- 当前实际主窗口：`gui/capture/capture_only_window.py`

当前主链只保留：

- `gui/capture/capture_only_window.py`
- `gui/capture/realtime_capture_*`
- `gui/capture/data_management_panel.py`
- `gui/capture/structured_data_controller.py`
- `gui/capture/capture_settings_panel.py`
- `gui/capture/ios_capture_controller.py`
- `gui/capture/ca_certificate_controller.py`
- `integration/http_capture.py`
- `playright/`

## 已归档内容

`archive/legacy_desktop/` 下包含以下历史模块：

- `main.py`
  - 旧自动化执行入口

- `automation/`
  - 节点自动化流程引擎、区域识别、滚动采集

- `core/`
  - ADB、截图、点击模拟、模板匹配、节点执行等基础能力

- `gui/node_editor.py`
  - 旧的全量桌面主窗口

- `gui/screenshot_tool.py`
  - 模板截图和框选工具

- `gui/capture/android_*`
  - Android ADB 与代理自动控制逻辑

- `gui/capture/adb_panel.py`
  - 旧的设备与代理面板

- `templates/`
  - 旧编排链路的模板图片资源

- 根目录历史文档
  - 包括 `QUICKSTART.md`、`INSTALL.md`、`需求文档.md` 等旧自动化/旧入口说明
  - 这些文档当前仅保留作历史参考，不再代表当前主链

`archive/root_misc/` 下包含以下已移出根目录的杂项文件：

- `ci/`
  - Gitee / GitHub / CI 相关配置与目录

- `analysis/`
  - 仓库分析脚本、跨平台分析脚本

- `cleanup/`
  - 历史 git 清理辅助脚本

- `configs/`
  - 当前主链未使用的额外配置文件

- `tmp/`
  - 临时文件、测试文件、历史备份目录

- `ci_legacy/`
  - 已退出主维护链的历史 Gitee 配置副本
  - 当前唯一生产配置真源是根目录 `gitee.yml`

## 维护约定

1. 当前需求如果只涉及 iPhone 抓包、点评结构化入库、数据管理、Playwright 电话补抓，不要再改 `archive/legacy_desktop/`。
2. 如果后续要恢复 Android 自动代理或节点编排，请先评估是否真的需要回到旧架构，再决定是直接复用归档代码，还是按当前 `capture-only` 架构重新设计。
3. 打包和依赖以当前主链为准，归档目录默认不参与主发布物。
4. 根目录默认只保留当前主链真正需要的入口、打包、安装、运行、测试、配置与核心代码目录。
