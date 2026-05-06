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

## 启动与构建

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
- 如果你本机已经长期使用 `uv` 管理 Python 环境，也可以正常运行本项目，但当前仓库没有 `pyproject.toml` / `uv.lock`，所以这里推荐使用 `uv venv + uv pip`，不要用 `uv sync`。
- 本地运行建议使用 `Python 3.11.x`。
- 本地打包当前固定使用 `Python 3.11.x`，不要使用 `Python 3.12+ / 3.13+`。
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
- `mitmproxy` 需要安装到当前可执行 Python 环境；应用内已提供一键安装入口。
- 为保证详情补抓稳定可用，建议本地也安装 Playwright Chromium：

```bash
python -m playwright install chromium
```

### 1.1 如果使用 `uv`

`uv` 不是必需的，但可以用。推荐两种方式。

方式一：先创建并激活 `.venv`

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
python node_editor_app.py
```

如果需要 Playwright 自带浏览器，再执行：

```bash
source .venv/bin/activate
python -m playwright install chromium
```

方式二：不手动激活，直接通过 `uv run` 启动

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
uv venv --python 3.11 .venv
uv pip install -r requirements.txt
uv run --python .venv/bin/python python node_editor_app.py
```

如果是启动 Playwright 独立补抓：

```bash
uv run --python .venv/bin/python python -m playright
```

说明：

- `uv run` 方式适合不想手动 `source` 环境的场景。
- 当前桌面端正式入口仍然是 `node_editor_app.py`。
- 如果你已经激活了 `.venv`，后续命令直接用 `python ...` 即可。

### 1.2 清理并重装依赖

如果出现“打包后缺依赖”或本地环境已经混乱，先直接重装一遍，不要在旧环境上继续叠加。

`venv + pip` 方式：

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
rm -rf venv .build-venvs build dist installer __pycache__
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

`uv` 方式：

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
rm -rf .venv .build-venvs build dist installer __pycache__
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
python -m playwright install chromium
```

说明：

- `playwright` Python 包来自 `requirements.txt`。
- `python -m playwright install chromium` 只负责浏览器运行时，不会替代 Python 包安装。
- 当前源码环境建议安装 Chromium 运行时，用于本地补抓验证。

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

当前正式发布流水线只构建：

- `macos-arm64`
- `macos-x86_64`
- `windows-x64`

推荐本地正式构建入口：

- macOS / Linux：`./build_release.sh`
- Windows PowerShell：`.\build_release.ps1`
- 或直接：`python3 bootstrap_build.py`

统一构建入口会自动：

- 识别当前机器对应的打包目标
- 创建独立构建虚拟环境 `.build-venvs/`
- 安装 `requirements.txt`
- 安装 `pyinstaller`
- 执行 `python -m playwright install chromium`
- 把 Chromium 下载到 `tools/playwright-browsers/`
- macOS 下按需安装 `create-dmg`
- 调用 `build_app.py` 完成正式打包

说明：

- GitHub Actions 仍然使用 `3.11`。
- 本地如果当前默认 `python3` 是 `3.13`，请显式改用 `python3.11` 再执行构建。
- 如果之前已经用别的 Python 版本创建过 `.build-venvs/`，构建脚本会自动重建对应虚拟环境。
- 发布产物当前不再内置 Playwright Chromium，避免安装包体积失控。
- `--target macos-arm64 --skip-installer` 会跳过安装包构建
- `./build_release.sh` 会自动识别当前机器对应的打包目标
常用命令：

```bash
./build_release.sh 
python3 bootstrap_build.py --target macos-arm64
python3 build_app.py --target macos-arm64 --skip-installer
```

### 6.1 构建前目录约定

当前仓库中的 `data/` 目录只保留最小骨架，运行时文件不会提交：

- 保留提交：
  - `data/capture_store.py`
  - `data/structured_capture.py`
  - `data/.gitkeep`
  - `data/capture_assets/.gitkeep`
  - `data/playright/.gitkeep`
  - `data/playright/runs/.gitkeep`
  - `data/playright/browser_profile/.gitkeep`
- 运行时自动生成：
  - `data/captures.db`
  - `data/capture_inbox.jsonl`
  - `data/capture_inbox.offset`
  - `data/capture_runtime.json`
  - `data/playright/browser_profile/*`
  - `data/playright/runs/*`

说明：

- 源码运行时，运行数据仍然写入项目根目录下的 `data/`。
- 打包运行时，运行数据会自动切到用户可写目录，不再依赖 `.app` 或 `.exe` 安装目录可写。
- `tools/playwright-browsers/` 仅用于本地源码环境和构建环境缓存，不进入正式安装包。

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

## CI/CD

当前正式构建流水线以 GitHub Actions 为准：

- `.github/workflows/cross-platform-build.yml`

说明：

- 合并到 `release` 分支后，默认并行构建 `Windows x64 / macOS arm64`
- `macOS x86_64` 作为可选构建项，通过 GitHub Actions 手动触发时开启
- 构建产物会分别上传，并额外汇总为 `all-platform-packages`
- workflow 默认使用 GitHub-hosted runner：
  - `windows-latest`
  - `macos-15-intel`
  - `macos-latest`
- `gitee.yml` 如继续保留，建议仅用于轻量校验，不再作为正式多平台打包入口

## 文档入口

当前主文档以本文件为准：

- `README.md`：启动、依赖、构建、CI/CD 主说明
- `docs/current-app-architecture.md`：当前应用结构说明
- `archive/README.md`：归档代码说明
