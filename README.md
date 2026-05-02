# py_test 使用说明

## 项目简介

这是一个以 `PyQt5` 为桌面入口的自动化工作台，当前主要包含以下能力：

1. 节点编排式自动化流程编辑
2. Android / iOS 抓包配置与抓包服务管理
3. 点评 / 美团接口实时抓取与结构化入库
4. 基于 Playwright 的商家详情补抓，当前主要用于补抓电话字段

主入口文件：

- `node_editor_app.py`
- `gui/node_editor.py`

---

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
- `requirements.txt` 已包含：
  - `PyQt5`
  - `mitmproxy`
  - `playwright`
  - `openpyxl`
  - `qrcode`
- 默认优先使用本机 Chrome / Chromium，不强制安装 Playwright 自带浏览器。
- 只有在需要 Playwright 自带浏览器时，才执行：

```bash
python -m playwright install chromium
```

如果希望走安装脚本，也可以使用：

```bash
python3 install.py
```

或：

```bash
./install.sh
```

### 2. 启动桌面端

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
source venv/bin/activate
python node_editor_app.py
```

如果没有创建虚拟环境，也可以直接：

```bash
python3 node_editor_app.py
```

桌面端当前包含四个页面：

1. 节点编排
2. 抓取实时数据
3. 数据管理
4. 抓包配置

### 2.1 登录配置

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

示例：

```bash
export AUTH_API_BASE_URL=http://admin.aowu100.com/member/api
python node_editor_app.py
```

### 3. 启动 Playwright 独立补抓

默认优先使用本机 Chrome / Chromium：

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
./start_playright.sh
```

脚本会优先使用：

1. `venv/bin/python`
2. 系统 `python3`

首次运行会打开真实浏览器窗口，用于复用登录态。浏览器用户数据目录默认保存在：

- `data/playright/browser_profile/`

### 4. 启动抓包服务

抓包服务通常从桌面端“抓包配置”页面启动，不建议直接手工操作 `mitmdump`。

标准路径：

1. 打开桌面端
2. 进入“抓包配置”
3. 启动抓取服务
4. Android 设备应用代理 / iOS 手动配置代理
5. 安装并信任 CA 证书

### 5. 构建打包

当前 `build_app.py` 只支持三种目标：

- `macos-arm64`
- `macos-x86_64`
- `windows-x64`

推荐在目标机上直接运行：

```bash
./build_release.sh
```

或：

```bash
python3 bootstrap_build.py
```

该脚本会自动创建单独的构建虚拟环境并完成依赖安装，然后再调用 `build_app.py`。

查看帮助：

```bash
python3 build_app.py --help
```

按目标构建：

```bash
python3 build_app.py --target macos-arm64
python3 build_app.py --target macos-x86_64
python build_app.py --target windows-x64
```

说明：

- 必须在对应目标系统上构建，当前不支持跨系统打包
- macOS 打 `.dmg` 需要额外安装 `create-dmg`
- Windows 当前会生成 `dist/windows-x64/DianpingAutoCollector.exe`
- Windows 安装包步骤当前输出为 `installer/windows-x64/*.iss`，需再用 Inno Setup 编译

---

## 常用命令

### 1. 环境与依赖

创建虚拟环境：

```bash
python3 -m venv venv
```

激活虚拟环境：

```bash
source venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

安装 Playwright 自带 Chromium（仅在需要时）：

```bash
python -m playwright install chromium
```

### 2. 启动程序

启动桌面端：

```bash
python node_editor_app.py
```

启动主流程入口：

```bash
python main.py
```

启动 Playwright 详情补抓：

```bash
./start_playright.sh
```

### 3. Playwright 常用示例

只跑 5 条：

```bash
./start_playright.sh --limit 5
```

指定店铺列表文件：

```bash
./start_playright.sh --shop-list-file shops.txt
```

指定浏览器路径：

```bash
./start_playright.sh --browser-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

命中阻塞即停止：

```bash
./start_playright.sh --shop-list-file shops.txt --export --stop-on-blocked
```

使用 mock 测试链路：

```bash
python3 -m playright --mock-test
```

### 4. 测试与校验

编译检查：

```bash
python3 -m py_compile gui/node_editor.py gui/capture/*.py
```

抓包模块测试：

```bash
python3 -m unittest test_capture_connectivity.py test_http_capture_manager.py
```

Playwright mock 测试：

```bash
python3 -m unittest test_playright_mock.py
```

系统测试：

```bash
python3 test_system.py
```

### 5. 日志与数据查看

实时查看自动化日志：

```bash
tail -f logs/automation_$(date +%Y-%m-%d).log
```

查看抓包代理日志：

```bash
tail -f logs/capture_proxy.log
```

查看 Playwright 运行结果目录：

```bash
ls -R data/playright/runs
```

### 6. 常见文件位置

- 应用配置：`config/app_settings.json`
- 节点配置：`config/nodes.json`
- 区域配置：`config/regions.json`
- 抓包数据库：`data/captures.db`
- 抓包临时 inbox：`data/capture_inbox.jsonl`
- 抓包运行时规则：`data/capture_runtime.json`
- Playwright 结果目录：`data/playright/runs/`

---

## 常见故障排查

### 1. 启动桌面端时报 `No module named 'PyQt5'`

原因：

- 当前 Python 环境没有安装依赖
- 没有激活项目虚拟环境

处理方式：

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test
source venv/bin/activate
pip install -r requirements.txt
python node_editor_app.py
```

如果没有 `venv`，先创建：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动抓包服务时报 `未找到 mitmdump`

原因：

- `mitmproxy` 没有安装到当前 Python 环境

处理方式：

```bash
source venv/bin/activate
pip install -r requirements.txt
```

验证：

```bash
which mitmdump
python -m mitmproxy --version
```

如果 `which mitmdump` 为空，但 `pip` 已安装成功，优先确认你是否使用了错误的 Python 环境。

### 3. ADB 设备无法连接

优先检查：

1. 手机是否开启开发者模式和 USB 调试
2. 无线调试是否已开启
3. 手机与电脑是否在同一局域网
4. 当前 Python 环境或系统是否能找到 `adb`

验证：

```bash
adb devices
```

如果系统没有 `adb`，可以：

1. 运行 `python3 install.py`
2. 或在桌面端点击“安装ADB”

### 4. 抓包服务启动了，但手机或模拟器没有网络

优先排查：

1. 代理地址是否为电脑当前局域网 IP
2. 抓包端口 `8081` 是否真的监听成功
3. CA 下载服务端口 `8765` 是否真的监听成功
4. macOS 防火墙是否拦截
5. 手机与电脑是否存在局域网隔离

建议检查：

```bash
tail -f logs/capture_proxy.log
```

并在桌面端使用：

- “检测当前代理”
- “测试代理连通性”
- “HTTPS 诊断”

### 5. Android 微信小程序走代理后无网络

这是当前技术链路中的已知限制点之一。

说明：

- Android 7+ 对用户证书信任和应用网络安全策略有更严格限制
- 即使浏览器能访问、微信聊天能联网，小程序也可能不信任该证书链路
- 这不是单纯 UI 改动导致的问题，而是 Android / 微信小程序抓 HTTPS 的常见限制

当前结论：

1. 普通代理 + 用户级 CA 证书，不保证 Android 微信小程序可抓
2. `whistle` 同样可能受限
3. 这类问题通常需要更深层方案，例如更换抓包对象、改平台、或研究 Frida / 注入类方案

当前系统更适合：

- Android 浏览器 / 普通 Web 页抓包
- iOS 配合手动代理与证书信任抓包

### 6. iOS 抓包不生效

优先检查：

1. 是否已经在 iPhone 的 Wi-Fi 设置里手动配置 HTTP 代理
2. 是否已经安装证书
3. 是否已经在“设置 -> 通用 -> 关于本机 -> 证书信任设置”中手动信任证书
4. 抓包服务和 CA 服务是否已启动

当前 iOS 模式是手动代理模式，不会像 Android 那样自动写入系统代理。

### 7. Playwright 启动后提示“Chrome 正在受自动测试软件控制”

这是 Chromium / Chrome 的常见自动化提示，不代表脚本失败。

当前系统已经默认优先走本机 Chrome / Chromium，并复用本机登录态。后续如果需要进一步降低识别风险，再单独处理浏览器指纹和启动参数。

### 8. Playwright 无法启动浏览器

优先检查：

1. 本机是否安装 Chrome 或 Chromium
2. 指定的 `--browser-path` 是否正确
3. 当前 Python 环境是否已安装 `playwright`

测试：

```bash
./start_playright.sh --limit 1
```

如果仍失败，可显式传入浏览器路径：

```bash
./start_playright.sh --browser-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

### 9. Playwright 已打开浏览器，但一直无法进入抓取

优先检查：

1. 是否已经完成登录
2. 是否仍停留在滑块、人机校验、二次跳转页面
3. 页面是否真的回到了 `www.dianping.com`

当前逻辑要求：

- 完成登录或校验后，页面必须真正回到点评目标页面，才会继续抓取

如果仍卡住，优先查看运行结果目录和失败日志：

- `data/playright/runs/`

### 10. 提供了 4 个 shop id，但结果数量不对

优先排查：

1. 输入文件是否真的包含 4 条有效 shop id
2. 是否开启了 `--stop-on-blocked`
3. 中途是否命中校验、跳转、超时
4. 是否有店铺在筛选前就被判定为不可处理

建议保留结果文件并查看：

- `results.jsonl`
- `summary.json`

### 11. “录入抓取数据”后没有数据

优先检查：

1. 当前是否已经先执行“开始收集数据”
2. 当前接口选择是否正确
3. 当前协议配置是否能命中该抓包 URL
4. 返回体字段结构是否与 `config/meituan/*.json` 规则一致

说明：

- 当前“录入抓取数据”只会按当前选中的接口协议执行，不会全量混跑

### 12. 数据管理页没有看到电话补抓结果

优先检查：

1. 当前列表筛选条件是否把结果过滤掉了
2. 当前店铺是否本来就已有电话
3. `starScore < 阈值` 是否把目标记录排除了
4. Playwright 任务是否真正执行完成

必要时检查：

- `data/captures.db`
- `data/playright/runs/`

### 13. 列表滚动不到底部或页面显示不完整

当前页面已改为可滚动布局。如果仍有问题，优先确认：

1. 是否使用了旧版本代码
2. 是否在异常缩放比例下运行桌面端
3. 是否有本地样式或平台差异导致控件高度异常

---

## 推荐使用顺序

如果是日常使用，推荐按下面顺序：

1. 激活虚拟环境
2. 启动 `python node_editor_app.py`
3. 在“抓包配置”中启动抓包服务
4. 在“抓取实时数据”中开始收集数据并录入抓取数据
5. 在“数据管理”中筛选和维护最终结果
6. 对无电话商家启动 Playwright 补抓

---

## 参考文档

- 快速开始：`QUICKSTART.md`
- 安装说明：`INSTALL.md`
- 开发维护说明：`AGENTS.md`
