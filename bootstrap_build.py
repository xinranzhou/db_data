#!/usr/bin/env python3
"""
源码拉取后的统一构建入口。

目标机只需要：
1. git pull / git clone
2. 运行本脚本

脚本会自动：
- 识别当前机器对应的发布目标
- 创建独立构建虚拟环境
- 安装 requirements.txt 与 pyinstaller
- macOS 下按需安装 create-dmg
- 调用 build_app.py 完成正式打包
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import build_app


BASE_DIR = Path(__file__).parent.resolve()
DEFAULT_BUILD_VENV_ROOT = BASE_DIR / ".build-venvs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap build environment and package the app on the current host.")
    parser.add_argument(
        "--target",
        choices=build_app.SUPPORTED_TARGETS,
        help="Build target. Defaults to the current host target.",
    )
    parser.add_argument(
        "--python",
        help="Python interpreter used to create the build virtualenv. Defaults to the current interpreter.",
    )
    parser.add_argument(
        "--venv-root",
        default=str(DEFAULT_BUILD_VENV_ROOT),
        help="Root directory for build virtualenvs. Default: .build-venvs",
    )
    parser.add_argument(
        "--skip-installer",
        action="store_true",
        help="Only build the application and skip dmg/iss packaging.",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip dependency installation and reuse the existing build virtualenv.",
    )
    return parser.parse_args()


def run(cmd: list[str], *, cwd: Path | None = None):
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(cwd or BASE_DIR))


def ensure_build_venv(venv_dir: Path, python_cmd: str) -> Path:
    python_path = Path(python_cmd).expanduser()
    if not python_path.is_absolute():
        resolved = shutil.which(python_cmd)
        if not resolved:
            raise RuntimeError(f"Python interpreter not found: {python_cmd}")
        python_path = Path(resolved)

    if not venv_dir.exists():
        run([str(python_path), "-m", "venv", str(venv_dir)])

    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        raise RuntimeError(f"Build virtualenv is missing python: {venv_python}")

    return venv_python


def install_build_dependencies(venv_python: Path):
    run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"])
    run([str(venv_python), "-m", "pip", "install", "pyinstaller"])


def ensure_create_dmg():
    if shutil.which("create-dmg"):
        return

    brew = shutil.which("brew")
    if not brew:
        raise RuntimeError("create-dmg is not installed and Homebrew is unavailable. Install create-dmg first.")

    run([brew, "install", "create-dmg"])


def main():
    args = parse_args()
    target_key = args.target or build_app.infer_default_target()
    target = build_app.ensure_supported_target(target_key)
    build_app.ensure_host_can_build(target)

    venv_root = Path(args.venv_root).expanduser()
    venv_dir = venv_root / target.key
    python_cmd = args.python or sys.executable

    print("=" * 60)
    print(f"{build_app.APP_DISPLAY_NAME} bootstrap build")
    print(f"Target: {target.key}")
    print(f"Build venv: {venv_dir}")
    print("=" * 60)

    venv_python = ensure_build_venv(venv_dir, python_cmd)

    if not args.skip_deps:
        install_build_dependencies(venv_python)

    if target.os_name == "macos" and not args.skip_installer:
        ensure_create_dmg()

    build_cmd = [str(venv_python), "build_app.py", "--target", target.key, "--skip-pyinstaller-install"]
    if args.skip_installer:
        build_cmd.append("--skip-installer")
    run(build_cmd)


if __name__ == "__main__":
    main()
