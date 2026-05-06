#!/usr/bin/env python3
"""源码运行环境安装脚本。"""

import subprocess
from pathlib import Path
import sys
import venv


BASE_DIR = Path(__file__).parent.resolve()
VENV_DIR = BASE_DIR / "venv"


def run(cmd: list[str]):
    print("Command:", " ".join(str(part) for part in cmd))
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR))


def check_python_version():
    """检查 Python 版本。"""
    version = sys.version_info
    if version.major != 3 or version.minor < 11:
        print("❌ Python 版本不受支持，需要 Python 3.11+")
        print(f"   当前版本: {sys.version}")
        return False

    print(f"✅ Python 版本: {sys.version.split()[0]}")
    return True


def ensure_local_venv() -> Path:
    """创建或复用项目本地虚拟环境。"""
    print("\n🐍 准备项目虚拟环境...")

    if not VENV_DIR.exists():
        print(f"创建虚拟环境: {VENV_DIR}")
        venv.create(VENV_DIR, with_pip=True)

    venv_python = get_venv_python()
    if not venv_python.exists():
        raise RuntimeError(f"虚拟环境 Python 不存在: {venv_python}")

    print(f"✅ 虚拟环境已就绪: {venv_python}")
    return venv_python


def get_venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def install_python_dependencies(venv_python: Path):
    """安装 Python 依赖。"""
    print("\n📦 安装 Python 依赖...")

    requirements_file = BASE_DIR / "requirements.txt"

    if not requirements_file.exists():
        print("❌ 未找到 requirements.txt")
        return False

    try:
        run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)])
        print("✅ Python 依赖安装成功")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        return False


def install_playwright_runtime(venv_python: Path):
    """输出 Playwright 运行时安装说明。"""
    print("\n🌐 Playwright 说明...")
    print("✅ 已通过 requirements.txt 安装 playwright Python 包")
    print("ℹ️  当前建议继续安装 Playwright Chromium，用于详情补抓与打包校验")
    print("ℹ️  请继续执行:")
    print(f"   {venv_python} -m playwright install chromium")


def main():
    """主函数"""
    print("=" * 60)
    print("DP采集器 - 源码环境安装")
    print("=" * 60)

    if not check_python_version():
        sys.exit(1)

    try:
        venv_python = ensure_local_venv()
    except Exception as exc:
        print(f"❌ 创建虚拟环境失败: {exc}")
        sys.exit(1)

    if not install_python_dependencies(venv_python):
        sys.exit(1)

    install_playwright_runtime(venv_python)

    print("\n" + "=" * 60)
    print("✅ 安装完成！")
    print("=" * 60)
    print("\n📝 使用说明:")
    if sys.platform == "win32":
        print("  1. 继续执行: venv\\Scripts\\python -m playwright install chromium")
        print("  2. 启动桌面端: venv\\Scripts\\python node_editor_app.py")
    else:
        print("  1. 继续执行: source venv/bin/activate")
        print("  2. 安装 Chromium: python -m playwright install chromium")
        print("  3. 启动桌面端: python node_editor_app.py")
    print("\n📚 文档:")
    print("  - README.md - 完整文档")
    print("  - QUICKSTART.md - 快速开始")
    print("\n")


if __name__ == "__main__":
    main()
