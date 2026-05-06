# 安装和打包指南

## 运行环境

- 源码运行：Python `3.11+`
- 本地打包：Python `3.11 - 3.13`
- Windows `10/11 x64`
- macOS `10.14+`
- 项目运行依赖 `PyQt5`、`mitmproxy`、`playwright`

说明：

- 当前官方打包目标只支持三种：
  - `macos-arm64`
  - `macos-x86_64`
  - `windows-x64`
- Linux 目前只建议源码运行，不在 `build_app.py` 官方打包目标内。
- 本地打包当前支持 `Python 3.11 - 3.13`，其中 `3.11.x` 与 CI 保持一致、最稳妥。
- 正式打包产物会内置 `mitmdump-helper`，正常运行不依赖系统级 `mitmproxy`。
- 源码运行时仍需通过 `requirements.txt` 安装 `mitmproxy` Python 包。

---

## 本地安装

### 1. 创建虚拟环境并安装依赖

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

为保证详情补抓稳定可用，建议继续安装 Playwright Chromium：

```bash
python -m playwright install chromium
```

### 2. 启动桌面端

```bash
python node_editor_app.py
```

### 2.1 iPhone 手动抓包使用说明

当前 iOS 抓包依赖两个本地服务：

- 抓包代理服务：`<电脑局域网IP>:8081`
- CA 下载服务：`http://<电脑局域网IP>:8765/`

两者用途不同：

- `8081`
  - 给 iPhone 的 Wi-Fi 手动代理使用
  - 填在“服务器 / 端口”里
- `8765`
  - 只用于 Safari 打开证书下载页
  - 不填到 Wi-Fi 代理里

推荐操作顺序：

1. 让 iPhone 和电脑处于同一局域网。
2. 不强制要求连接“同名 Wi-Fi”，但必须保证 iPhone 能访问电脑当前显示的局域网 IP。
3. 启动桌面端后，进入“抓包配置”。
4. 先点击“启动抓取服务”。
5. 记下页面显示的：
   - 代理地址，例如 `192.168.1.23:8081`
   - CA 下载地址，例如 `http://192.168.1.23:8765/`
6. 在 iPhone 上进入：
   设置 -> WLAN -> 当前 Wi-Fi -> 配置代理 -> 手动
7. 填写：
   - 服务器：电脑当前显示的局域网 IP
   - 端口：`8081`
8. 在 iPhone Safari 中打开 `CA 下载地址`。
9. 点击页面里的 `下载 iOS 证书`。
10. 下载后进入：
    设置 -> 已下载描述文件
    完成证书安装。
11. 安装完成后进入：
    设置 -> 通用 -> 关于本机 -> 证书信任设置
12. 找到 mitmproxy 证书，手动开启“完全信任”。
13. 之后先用 Safari 打开一个 HTTPS 页面，确认联网正常。
14. 再打开目标页面/小程序，回桌面端开始抓包。

注意：

- 如果 `CA 下载地址` 打不开，优先检查桌面端里的 `本机 CA 端口监听` 是否成功。
- 如果设置代理后完全无法上网，优先检查 `8081` 是否监听成功，以及证书是否已经信任。
- 证书只要没有重新生成，一般安装一次即可，后续不用反复安装。

### 3. 安装辅助脚本

- Windows：双击 `install.bat`
- macOS / Linux：执行 `./install.sh`

说明：

- 这两个脚本只负责创建本地 `venv`、安装依赖并提示后续启动方式。
- 正式打包不要走这里，统一使用 `build_release.sh` / `build_release.ps1` / `bootstrap_build.py`。

---

## 登录接口配置

当前桌面端登录默认走真实接口：

```text
http://admin.aowu100.com/member/api
```

可选环境变量：

- `AUTH_API_BASE_URL`
  - 直接覆盖所有环境的登录接口地址
- `AUTH_API_BASE_URL_DEV`
  - 开发态接口地址
- `AUTH_API_BASE_URL_PROD`
  - 打包后运行时接口地址
- `AUTH_TOKEN_TTL_MS`
  - 本地 token 默认有效期，单位毫秒
- `AUTH_ENABLE_MOCK_LOGIN`
  - 是否开启本地 mock 登录，默认开发环境开启，打包环境关闭

示例：

```bash
export AUTH_API_BASE_URL=http://admin.aowu100.com/member/api
python node_editor_app.py
```

---

## 打包发布

### 0. 推荐入口

如果是在目标机构建，推荐直接运行统一 bootstrap 脚本：

macOS:

```bash
./build_release.sh
```

Windows PowerShell:

```powershell
.\build_release.ps1
```

或直接：

```bash
python3 bootstrap_build.py
```

它会自动：

- 识别当前机器对应的打包目标
- 创建独立构建虚拟环境
- 安装依赖和 `pyinstaller`
- 安装 Playwright Chromium 到项目内 `tools/playwright-browsers/`
- macOS 下按需安装 `create-dmg`
- 调用 `build_app.py` 完成正式打包

### 1. 安装打包依赖

```bash
pip install pyinstaller
```

macOS 如需输出 `.dmg`，还需要：

```bash
brew install create-dmg
```

### 2. 查看命令帮助

```bash
python3 build_app.py --help
```

### 3. 按目标打包

当前脚本：

- 会按系统和架构分别输出到独立目录
- 会校验宿主机系统/架构是否与目标匹配
- 不支持跨系统打包

#### macOS Apple Silicon

```bash
python3 build_app.py --target macos-arm64
```

要求：

- 必须在 `macOS arm64` 机器上执行

输出：

- `dist/macos-arm64/DP采集器.app`
- `installer/macos-arm64/DP采集器-macos-arm64.dmg`

#### macOS Intel

```bash
python3 build_app.py --target macos-x86_64
```

要求：

- 必须在 `macOS x86_64` 机器上执行

输出：

- `dist/macos-x86_64/DP采集器.app`
- `installer/macos-x86_64/DP采集器-macos-x86_64.dmg`

#### Windows x64

```bash
python build_app.py --target windows-x64
```

要求：

- 必须在 `Windows x64` 机器上执行

输出：

- `dist/windows-x64/DP采集器.exe`
- `installer/windows-x64/DP采集器-windows-x64.iss`

说明：

- Windows 目标当前会生成 Inno Setup 脚本 `.iss`
- 如需最终安装包 `.exe`，请在 Windows x64 上使用 Inno Setup 再编译该脚本

### 4. 只构建可执行文件

```bash
python3 build_app.py --target macos-arm64 --skip-installer
```

### 5. 跳过自动安装 PyInstaller

```bash
python3 build_app.py --target macos-arm64 --skip-pyinstaller-install
```

---

## 打包注意事项

- `icon.icns` 或 `icon.ico` 不存在时，脚本会给出 warning 并跳过图标设置
- `config`、`templates`、`tools` 目录存在时会自动打入产物
- `tools/playwright-browsers/` 只作为本地源码/构建缓存，不进入正式安装包
- `images/` 当前不会自动打入包内，如后续运行依赖该目录，需要再补进打包脚本
- macOS 和 Windows 需要各自在本机目标系统上构建，不建议混用产物

---

## 分发建议

### 方式 1：源码分发

适合内部开发或调试：

1. 分发整个项目目录
2. 使用 `install.bat` 或 `install.sh` 安装源码运行依赖
3. 执行 `python node_editor_app.py`

### 方式 2：打包分发

适合非开发同学：

1. 按目标执行 `build_app.py`
2. macOS 分发 `installer/<target>/` 下的 `.dmg`
3. Windows 分发 `dist/windows-x64/DP采集器.exe` 或继续编译 `.iss` 得到安装包

---

## 常见问题

### Q: 为什么不能在 macOS 上直接打 Windows 包？

A: 当前脚本显式校验宿主机系统和目标系统，Windows 和 macOS 必须分别在对应系统构建。

### Q: macOS 打包时报 `create-dmg is not installed`

A: 先安装：

```bash
brew install create-dmg
```

### Q: Windows 只有 `.iss` 没有安装包 `.exe`

A: 当前脚本会先生成 Inno Setup 脚本，需要在 Windows x64 上使用 Inno Setup 编译成最终安装包。

### Q: 现在正式多平台构建由哪个配置文件驱动？

A: 当前正式多平台构建以 `.github/workflows/cross-platform-build.yml` 为准。它会在 `release` 分支变更后并行构建 `Windows x64 / macOS x86_64 / macOS arm64`。`gitee.yml` 如继续保留，建议仅用于轻量校验。

### Q: 打包后登录失败怎么办？

A: 优先检查：

1. 接口地址是否可访问
2. 是否被本地网络或防火墙拦截
3. 是否通过环境变量覆盖了错误的 `AUTH_API_BASE_URL`

---

## 相关文档

- [README.md](/Users/xinranzhou/Documents/zft/auto_ocr/py_test/README.md)
- [QUICKSTART.md](/Users/xinranzhou/Documents/zft/auto_ocr/py_test/QUICKSTART.md)
