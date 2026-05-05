# 安装和打包指南

## 运行环境

- Python `3.11+`
- Windows `10/11 x64`
- macOS `10.14+`
- 项目运行依赖 `PyQt5`、`mitmproxy`、`playwright`

说明：

- 当前官方打包目标只支持三种：
  - `macos-arm64`
  - `macos-x86_64`
  - `windows-x64`
- Linux 目前只建议源码运行，不在 `build_app.py` 官方打包目标内。

---

## 本地安装

### 1. 创建虚拟环境并安装依赖

```bash
cd /Users/xinranzhou/Documents/zft/auto_ocr/py_test

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

如果需要 Playwright 自带浏览器，再额外执行：

```bash
python -m playwright install chromium
```

### 2. 启动桌面端

```bash
python node_editor_app.py
```

### 3. 一键安装脚本

- Windows：双击 `install.bat`
- macOS / Linux：执行 `./install.sh`

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

macOS / Linux:

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
- `images/` 当前不会自动打入包内，如后续运行依赖该目录，需要再补进打包脚本
- macOS 和 Windows 需要各自在本机目标系统上构建，不建议混用产物

---

## 分发建议

### 方式 1：源码分发

适合内部开发或调试：

1. 分发整个项目目录
2. 使用 `install.bat` 或 `install.sh`
3. 首次启动后在登录页输入账号密码

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
