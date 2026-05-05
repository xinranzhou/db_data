# py_test 使用说明

## 项目简介

当前项目已经收敛为一个以 `PyQt5` 为桌面入口的 **iOS 手动抓包工作台**，当前主链能力包括：

1. iPhone / iPad 手动代理抓包配置
2. 点评 / 美团接口实时抓取与结构化入库
3. 结构化数据管理与导出
4. 基于 Playwright 的商家详情补抓，当前主要用于补抓电话字段

当前桌面端主入口：

- `node_editor_app.py`

当前实际主窗口：

- `gui/capture/capture_only_window.py`

已退出主链的旧能力：

- 节点编排式自动化流程编辑
- 模板截图、模板匹配、点击/滚动自动化
- Android ADB 连接与代理自动下发

这些旧代码已统一归档到：

- `archive/legacy_desktop/`

## 启动方式

### 1. 安装依赖

推荐使用项目内虚拟环境：

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

说明：

- 当前项目不需要 `uv`，直接使用 `venv + pip` 即可。
- 当前主链依赖已收敛为：
  - `PyQt5`
  - `mitmproxy`
  - `playwright`
  - `openpyxl`
  - `qrcode[pil]`
  - `pillow`
- 当前主链已经不再依赖：
  - `opencv-python`
  - `numpy`
  - `pyautogui`
- 默认优先使用本机 Chrome / Chromium，不强制安装 Playwright 自带浏览器。
- 只有在需要 Playwright 自带浏览器时，才执行：

```bash
python -m playwright install chromium
```

### 2. 启动桌面端

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
source venv/bin/activate
python node_editor_app.py
```

桌面端当前只包含三个页面：

1. 抓取实时数据
2. 数据管理
3. 抓包配置

### 3. 当前推荐抓包流程

标准路径：

1. 打开桌面端
2. 进入“抓包配置”
3. 启动抓取服务
4. 在 iPhone Wi-Fi 设置中手动配置代理
5. 用 Safari 打开 CA 下载地址，安装证书
6. 在系统设置中手动开启完全信任
7. 回到“抓取实时数据”页同步抓包
8. 执行“录入抓取数据”
9. 到“数据管理”页查看、筛选、导出、补抓电话

### 4. 登录配置

当前桌面端登录默认走真实接口：

```text
http://admin.aowu100.com/member/api
```

可选环境变量：

- `AUTH_API_BASE_URL`
- `AUTH_API_BASE_URL_DEV`
- `AUTH_API_BASE_URL_PROD`
- `AUTH_TOKEN_TTL_MS`
- `AUTH_ENABLE_MOCK_LOGIN`

### 5. 启动 Playwright 独立补抓

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
./start_playright.sh
```

### 6. 构建打包

当前 `build_app.py` 支持：

- `macos-arm64`
- `macos-x86_64`
- `windows-x64`
- `windows-x86`

## 常用命令

### 1. 启动程序

启动桌面端：

```bash
python node_editor_app.py
```

启动 Playwright 详情补抓：

```bash
./start_playright.sh
```

### 2. 测试与校验

```bash
python3 -m py_compile node_editor_app.py gui/capture/capture_only_window.py gui/capture/*.py integration/http_capture.py
python3 -m unittest test_auth_service.py
```

## 架构说明

当前主链说明见：

- `docs/current-app-architecture.md`

归档说明见：

- `archive/README.md`

## Gitee CI/CD

当前 Gitee CI/CD 的唯一生产配置真源是：

- `gitee.yml`

说明：

- 合并到 `release` 分支后，会按 `Windows x64 / macOS x86_64 / macOS arm64` 三路并行构建
- 指向 `release` 的合并请求会触发预检
- 历史多份 Gitee 配置已移到 `archive/root_misc/ci_legacy/`，仅保留作参考，不再继续维护
