#!/usr/bin/env python3
"""
自动安装脚本
检测系统并自动安装依赖
"""

import os
import sys
import platform
import subprocess
from pathlib import Path


def get_platform():
    """获取平台信息"""
    system = platform.system()
    return {
        'system': system,
        'is_windows': system == 'Windows',
        'is_macos': system == 'Darwin',
        'is_linux': system == 'Linux',
        'python_version': sys.version,
    }


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 版本过低，需要 Python 3.8+")
        print(f"   当前版本: {sys.version}")
        return False

    print(f"✅ Python 版本: {sys.version.split()[0]}")
    return True


def install_adb_tools(platform_info):
    """安装 ADB 工具"""
    print("\n📱 安装 ADB 工具...")

    if platform_info['is_macos']:
        print("检测到 macOS 系统")
        # 检查是否安装了 Homebrew
        try:
            subprocess.run(['brew', '--version'], capture_output=True, check=True)
            print("✅ Homebrew 已安装")

            # 安装 ADB
            print("正在安装 android-platform-tools...")
            subprocess.run(['brew', 'install', 'android-platform-tools'], check=True)
            print("✅ ADB 工具安装成功")

        except (FileNotFoundError, subprocess.CalledProcessError):
            print("❌ 未安装 Homebrew")
            print("请先安装 Homebrew: https://brew.sh/")
            print("或手动下载 ADB: https://developer.android.com/studio/releases/platform-tools")
            return False

    elif platform_info['is_windows']:
        print("检测到 Windows 系统")
        print("请手动下载并安装 ADB 工具:")
        print("https://developer.android.com/studio/releases/platform-tools")
        print("\n下载后解压，并将路径添加到系统环境变量 PATH 中")

        input("\n按 Enter 继续...")

    elif platform_info['is_linux']:
        print("检测到 Linux 系统")
        try:
            # 尝试使用 apt
            subprocess.run(['sudo', 'apt', 'update'], check=True)
            subprocess.run(['sudo', 'apt', 'install', '-y', 'adb'], check=True)
            print("✅ ADB 工具安装成功")
        except:
            print("请使用包管理器安装 adb:")
            print("  Ubuntu/Debian: sudo apt install adb")
            print("  Fedora: sudo dnf install android-tools")
            print("  Arch: sudo pacman -S android-tools")
            return False

    # 验证安装
    try:
        result = subprocess.run(['adb', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ ADB 版本: {result.stdout.split()[4]}")
            return True
    except FileNotFoundError:
        pass

    print("⚠️  ADB 工具未正确安装")
    return False


def install_python_dependencies():
    """安装 Python 依赖"""
    print("\n📦 安装 Python 依赖...")

    requirements_file = Path(__file__).parent / "requirements.txt"

    if not requirements_file.exists():
        print("❌ 未找到 requirements.txt")
        return False

    try:
        subprocess.run([
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(requirements_file)
        ], check=True)

        print("✅ Python 依赖安装成功")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        return False


def install_playwright_runtime():
    """
    安装 Playwright 运行时说明。

    当前详情补全默认优先使用本机 Chrome/Chromium，
    因此安装 Python 包即可；只有在需要 Playwright 自带浏览器时，
    才额外执行 `python -m playwright install chromium`。
    """
    print("\n🌐 Playwright 说明...")
    print("✅ 已通过 requirements.txt 安装 playwright Python 包")
    print("ℹ️  详情补全默认优先使用本机 Chrome/Chromium")
    print("ℹ️  如需使用 Playwright 自带浏览器，再执行:")
    print(f"   {sys.executable} -m playwright install chromium")


def resolve_runtime_python():
    """优先返回项目虚拟环境 Python。"""
    project_dir = Path(__file__).parent
    if platform.system() == "Windows":
        venv_python = project_dir / "venv" / "Scripts" / "python.exe"
    else:
        venv_python = project_dir / "venv" / "bin" / "python"

    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def create_desktop_shortcut(platform_info):
    """创建桌面快捷方式"""
    print("\n🔗 创建桌面快捷方式...")

    app_path = Path(__file__).parent / "node_editor_app.py"
    runtime_python = resolve_runtime_python()

    if platform_info['is_macos']:
        # macOS: 创建 .command 文件
        shortcut_path = Path.home() / "Desktop" / "大众点评自动化.command"
        content = f"""#!/bin/bash
cd "{app_path.parent}"
"{runtime_python}" node_editor_app.py
"""
        shortcut_path.write_text(content)
        os.chmod(shortcut_path, 0o755)
        print(f"✅ 快捷方式已创建: {shortcut_path}")

    elif platform_info['is_windows']:
        # Windows: 创建 .bat 文件
        shortcut_path = Path.home() / "Desktop" / "大众点评自动化.bat"
        content = f"""@echo off
cd /d "{app_path.parent}"
"{runtime_python}" node_editor_app.py
pause
"""
        shortcut_path.write_text(content, encoding='gbk')
        print(f"✅ 快捷方式已创建: {shortcut_path}")

    elif platform_info['is_linux']:
        # Linux: 创建 .desktop 文件
        shortcut_path = Path.home() / "Desktop" / "dianping-auto.desktop"
        content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=大众点评自动化
Comment=大众点评小程序自动化采集系统
Exec={runtime_python} {app_path}
Path={app_path.parent}
Terminal=false
"""
        shortcut_path.write_text(content)
        os.chmod(shortcut_path, 0o755)
        print(f"✅ 快捷方式已创建: {shortcut_path}")


def main():
    """主函数"""
    print("=" * 60)
    print("DP采集器 - 自动安装程序")
    print("=" * 60)

    # 1. 获取平台信息
    platform_info = get_platform()
    print(f"\n🖥️  系统: {platform_info['system']}")

    # 2. 检查 Python 版本
    if not check_python_version():
        sys.exit(1)

    # 3. 安装 Python 依赖
    if not install_python_dependencies():
        print("\n⚠️  依赖安装失败，但可以继续")
    else:
        install_playwright_runtime()

    # 4. 安装 ADB 工具
    if not install_adb_tools(platform_info):
        print("\n⚠️  ADB 工具未安装，手机连接功能将不可用")
        print("   但仍可使用 GUI 编辑器配置节点")

    # 5. 创建桌面快捷方式
    try:
        create_desktop_shortcut(platform_info)
    except Exception as e:
        print(f"⚠️  创建快捷方式失败: {e}")

    # 6. 完成
    print("\n" + "=" * 60)
    print("✅ 安装完成！")
    print("=" * 60)
    print("\n📝 使用说明:")
    print("  1. 双击桌面快捷方式启动程序")
    print("  2. 或运行: python node_editor_app.py")
    print("  3. 详情补全可运行: ./start_playright.sh")
    print("\n📱 手机连接:")
    print("  1. 开启手机 USB 调试")
    print("  2. 连接手机到电脑")
    print("  3. 在程序中点击'刷新设备'")
    print("\n📚 文档:")
    print("  - README.md - 完整文档")
    print("  - QUICKSTART.md - 快速开始")
    print("\n")


if __name__ == "__main__":
    main()
