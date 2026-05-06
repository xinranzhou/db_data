#!/usr/bin/env python3
"""
跨平台打包脚本。

当前支持的发布目标：
- macos-arm64
- macos-x86_64
- windows-x64
- windows-x86
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "DP采集器"
APP_DISPLAY_NAME = "DP采集器"
APP_VERSION = "1.0.0"
BASE_DIR = Path(__file__).parent.resolve()
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
INSTALLER_DIR = BASE_DIR / "installer"
RUNTIME_HOOKS_DIR = BASE_DIR / "build_hooks"
SUPPORTED_TARGETS = ("macos-arm64", "macos-x86_64", "windows-x64", "windows-x86")


@dataclass(frozen=True)
class BuildTarget:
    key: str
    os_name: str
    arch: str
    icon_name: str | None
    pyinstaller_target_arch: str | None
    installer_kind: str
    executable_name: str
    bundle_mode: str


TARGETS = {
    "macos-arm64": BuildTarget(
        key="macos-arm64",
        os_name="macos",
        arch="arm64",
        icon_name="icon.icns",
        pyinstaller_target_arch="arm64",
        installer_kind="dmg",
        executable_name=f"{APP_NAME}.app",
        bundle_mode="onedir",
    ),
    "macos-x86_64": BuildTarget(
        key="macos-x86_64",
        os_name="macos",
        arch="x86_64",
        icon_name="icon.icns",
        pyinstaller_target_arch="x86_64",
        installer_kind="dmg",
        executable_name=f"{APP_NAME}.app",
        bundle_mode="onedir",
    ),
    "windows-x64": BuildTarget(
        key="windows-x64",
        os_name="windows",
        arch="x64",
        icon_name="icon.ico",
        pyinstaller_target_arch=None,
        installer_kind="iss",
        executable_name=f"{APP_NAME}.exe",
        bundle_mode="onefile",
    ),
    "windows-x86": BuildTarget(
        key="windows-x86",
        os_name="windows",
        arch="x86",
        icon_name="icon.ico",
        pyinstaller_target_arch=None,
        installer_kind="iss",
        executable_name=f"{APP_NAME}.exe",
        bundle_mode="onefile",
    ),
}


def normalize_host_platform() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        os_name = "macos"
        if machine in {"arm64", "aarch64"}:
            arch = "arm64"
        elif machine in {"x86_64", "amd64"}:
            arch = "x86_64"
        else:
            arch = machine
        return os_name, arch

    if system == "windows":
        os_name = "windows"
        if machine in {"amd64", "x86_64"}:
            arch = "x64"
        elif machine in {"x86", "i386", "i686", "AMD64"}:
            arch = "x86"
        else:
            arch = machine
        return os_name, arch

    return system, machine


def install_pyinstaller():
    print("Installing PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)


def ensure_supported_target(target_key: str) -> BuildTarget:
    if target_key not in TARGETS:
        raise ValueError(f"Unsupported target: {target_key}. Supported: {', '.join(SUPPORTED_TARGETS)}")
    return TARGETS[target_key]


def ensure_host_can_build(target: BuildTarget):
    host_os, host_arch = normalize_host_platform()
    if host_os != target.os_name:
        raise RuntimeError(
            f"Host platform {host_os}-{host_arch} cannot build target {target.key}. "
            f"Please build {target.key} on a matching {target.os_name} host."
        )

    if target.os_name == "macos" and host_arch != target.arch:
        raise RuntimeError(
            f"Host architecture {host_arch} cannot build target {target.key}. "
            f"Please build on macOS {target.arch}."
        )

    if target.os_name == "windows":
        if target.arch == "x86" and host_arch not in ["x86", "x64"]:
            raise RuntimeError(
                f"Host architecture {host_arch} cannot build target {target.key}. "
                "Please build on Windows x86 or x64."
            )
        elif target.arch == "x64" and host_arch != "x64":
            raise RuntimeError(
                f"Host architecture {host_arch} cannot build target {target.key}. "
                "Only Windows x64 is supported by this script."
            )


def ensure_output_dirs(target: BuildTarget) -> dict[str, Path]:
    dist_path = DIST_DIR / target.key
    work_path = BUILD_DIR / target.key / "pyinstaller"
    spec_path = BUILD_DIR / target.key / "spec"
    cache_path = BUILD_DIR / target.key / "pyinstaller-cache"
    installer_path = INSTALLER_DIR / target.key
    dist_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    spec_path.mkdir(parents=True, exist_ok=True)
    cache_path.mkdir(parents=True, exist_ok=True)
    installer_path.mkdir(parents=True, exist_ok=True)
    return {
        "dist": dist_path,
        "work": work_path,
        "spec": spec_path,
        "cache": cache_path,
        "installer": installer_path,
    }


def get_data_dirs() -> list[Path]:
    names = ["config", "integration"]
    result = []
    for name in names:
        path = BASE_DIR / name
        if path.exists():
            result.append(path)
    return result


def get_data_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []

    for relative_path in [
        Path("data") / "capture_store.py",
        Path("data") / "structured_capture.py",
    ]:
        source_path = BASE_DIR / relative_path
        if source_path.exists():
            files.append((source_path, str(relative_path.parent)))

    for relative_path in [
        Path("data") / ".gitkeep",
        Path("data") / "capture_assets" / ".gitkeep",
        Path("data") / "playright" / ".gitkeep",
        Path("data") / "playright" / "runs" / ".gitkeep",
        Path("data") / "playright" / "browser_profile" / ".gitkeep",
    ]:
        source_path = BASE_DIR / relative_path
        if source_path.exists():
            files.append((source_path, str(relative_path.parent)))

    return files


def build_mitmdump_helper_command(target: BuildTarget, paths: dict[str, Path]) -> list[str]:
    helper_name = "mitmdump-helper"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        helper_name,
        "--clean",
        "--noconfirm",
        "--distpath",
        str(paths["dist"]),
        "--workpath",
        str(paths["work"] / "mitmdump-helper"),
        "--specpath",
        str(paths["spec"]),
    ]

    cmd.append("--onefile")

    if target.pyinstaller_target_arch:
        cmd.extend(["--target-arch", target.pyinstaller_target_arch])

    cmd.extend(["--collect-all", "mitmproxy"])
    cmd.append("mitmdump_helper_app.py")
    return cmd


def copy_runtime_support_dirs(target: BuildTarget, paths: dict[str, Path]):
    artifact = resolve_build_artifact(target, paths)
    if target.bundle_mode == "onefile":
        return

    if target.os_name == "macos":
        runtime_root = artifact / "Contents" / "Resources"
    else:
        runtime_root = artifact

    tools_src = BASE_DIR / "tools"
    tools_dest = runtime_root / "tools"

    if tools_dest.exists():
        shutil.rmtree(tools_dest)
    tools_dest.mkdir(parents=True, exist_ok=True)

    keep_files = [".gitkeep"]
    for name in keep_files:
        source = tools_src / name
        if source.exists():
            shutil.copy2(source, tools_dest / name)


def build_mitmdump_helper(target: BuildTarget, paths: dict[str, Path]) -> Path:
    print(f"Building mitmdump helper for {target.key}...")
    cmd = build_mitmdump_helper_command(target, paths)
    print("Command:", " ".join(cmd))
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(paths["cache"])
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR), env=env)

    helper_artifact = paths["dist"] / ("mitmdump-helper.exe" if target.os_name == "windows" else "mitmdump-helper")

    if not helper_artifact.exists():
        raise RuntimeError(f"mitmdump helper artifact missing: {helper_artifact}")
    return helper_artifact


def install_mitmdump_helper_into_bundle(target: BuildTarget, paths: dict[str, Path], helper_artifact: Path):
    artifact = resolve_build_artifact(target, paths)
    if target.bundle_mode == "onefile":
        return

    destinations: list[Path]
    if target.os_name == "macos":
        destinations = [
            artifact / "Contents" / "Frameworks" / "tools" / "bin",
            artifact / "Contents" / "Resources" / "tools" / "bin",
        ]
    else:
        destinations = [artifact / "tools" / "bin"]

    filename = "mitmdump-helper.exe" if target.os_name == "windows" else "mitmdump-helper"
    for tools_bin_dir in destinations:
        tools_bin_dir.mkdir(parents=True, exist_ok=True)
        destination = tools_bin_dir / filename
        shutil.copy2(helper_artifact, destination)
        destination.chmod(0o755)


def resign_macos_bundle_if_needed(target: BuildTarget, paths: dict[str, Path]):
    if target.os_name != "macos" or target.bundle_mode == "onefile":
        return

    artifact = resolve_build_artifact(target, paths)
    cmd = [
        "codesign",
        "--force",
        "--deep",
        "--sign",
        "-",
        str(artifact),
    ]
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR))


def build_pyinstaller_command(target: BuildTarget, paths: dict[str, Path]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        APP_NAME,
        "--windowed",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(paths["dist"]),
        "--workpath",
        str(paths["work"]),
        "--specpath",
        str(paths["spec"]),
    ]

    if target.bundle_mode == "onefile":
        cmd.append("--onefile")
    elif target.bundle_mode == "onedir":
        cmd.append("--onedir")
    else:
        raise RuntimeError(f"Unsupported PyInstaller bundle mode: {target.bundle_mode}")

    if target.pyinstaller_target_arch:
        cmd.extend(["--target-arch", target.pyinstaller_target_arch])

    icon_path = BASE_DIR / target.icon_name if target.icon_name else None
    if icon_path and icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
    elif icon_path:
        print(f"Warning: icon file not found, skipping: {icon_path.name}")

    for data_dir in get_data_dirs():
        cmd.extend(["--add-data", f"{data_dir.resolve()}{os.pathsep}{data_dir.name}"])

    for data_file, target_dir in get_data_files():
        cmd.extend(["--add-data", f"{data_file.resolve()}{os.pathsep}{target_dir}"])

    hidden_imports = [
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
        "PIL",
        "loguru",
        "yaml",
        "qrcode",
        "openpyxl",
        "playwright",
        "tenacity",
        "sqlite3",
        "data.capture_store",
        "data.structured_capture",
        "gui.capture",
        "gui.capture.ca_certificate_controller",
        "gui.capture.capture_only_window",
        "gui.capture.capture_settings_panel",
        "gui.capture.data_management_panel",
        "gui.capture.ios_capture_controller",
        "gui.capture.network_utils",
        "gui.capture.platform_state",
        "gui.capture.realtime_capture_controller",
        "gui.capture.realtime_capture_panel",
        "gui.capture.structured_data_controller",
    ]
    for module in hidden_imports:
        cmd.extend(["--hidden-import", module])

    collect_all_modules = [
        "gui",
        "playright",
        "playwright",
    ]
    for module in collect_all_modules:
        cmd.extend(["--collect-all", module])

    cmd.append("node_editor_app.py")
    return cmd


def build_app(target: BuildTarget, paths: dict[str, Path]):
    print(f"Building application for {target.key}...")
    cmd = build_pyinstaller_command(target, paths)
    print("Command:", " ".join(cmd))
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(paths["cache"])
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR), env=env)

    artifact = resolve_build_artifact(target, paths)
    if not artifact.exists():
        raise RuntimeError(f"PyInstaller finished but expected artifact is missing: {artifact}")

    copy_runtime_support_dirs(target, paths)
    print(f"Build completed: {artifact}")


def resolve_build_artifact(target: BuildTarget, paths: dict[str, Path]) -> Path:
    direct_path = paths["dist"] / target.executable_name
    if direct_path.exists():
        return direct_path

    if target.os_name == "macos":
        app_bundle = paths["dist"] / f"{APP_NAME}.app"
        if app_bundle.exists():
            return app_bundle

        app_dir = paths["dist"] / APP_NAME
        if app_dir.exists():
            return app_dir

    raise RuntimeError(
        f"PyInstaller finished but no known artifact was found under {paths['dist']} for target {target.key}"
    )


def create_windows_installer(target: BuildTarget, paths: dict[str, Path]) -> Path:
    artifact = resolve_build_artifact(target, paths)
    output_name = f"{APP_NAME}-Setup-{target.key}"
    iss_path = paths["installer"] / f"{APP_NAME}-{target.key}.iss"
    architecture_lines = []
    if target.arch == "x64":
        architecture_lines = [
            "ArchitecturesAllowed=x64",
            "ArchitecturesInstallIn64BitMode=x64",
        ]
    elif target.arch == "x86":
        architecture_lines = [
            "ArchitecturesAllowed=x86",
        ]

    iss_content = f"""
[Setup]
AppName={APP_DISPLAY_NAME}
AppVersion={APP_VERSION}
DefaultDirName={{pf}}\\{APP_NAME}
DefaultGroupName={APP_DISPLAY_NAME}
OutputDir={paths["installer"]}
OutputBaseFilename={output_name}
{os.linesep.join(architecture_lines)}

[Files]
Source: "{artifact}"; DestDir: "{{app}}"
Source: "{BASE_DIR / 'config'}\\*"; DestDir: "{{app}}\\config"; Flags: recursesubdirs
Source: "{BASE_DIR / 'tools'}\\*"; DestDir: "{{app}}\\tools"; Flags: recursesubdirs

[Icons]
Name: "{{group}}\\{APP_DISPLAY_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"
Name: "{{commondesktop}}\\{APP_DISPLAY_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"
""".strip()

    iss_path.write_text(iss_content, encoding="utf-8")
    print(f"Installer script generated: {iss_path}")
    print("Use Inno Setup on Windows x64 to compile it into an installer exe.")
    return iss_path


def create_macos_installer(target: BuildTarget, paths: dict[str, Path]) -> Path:
    artifact = resolve_build_artifact(target, paths)
    dmg_path = paths["installer"] / f"{APP_NAME}-{target.key}.dmg"

    create_dmg = shutil.which("create-dmg")
    if not create_dmg:
        raise RuntimeError(
            "create-dmg is not installed. Install it first, for example via `brew install create-dmg`."
        )

    if dmg_path.exists():
        dmg_path.unlink()

    cmd = [
        create_dmg,
        "--volname",
        f"{APP_DISPLAY_NAME}-{target.arch}",
        "--window-pos",
        "200",
        "120",
        "--window-size",
        "640",
        "420",
        "--icon-size",
        "100",
        "--app-drop-link",
        "440",
        "200",
        str(dmg_path),
        str(artifact),
    ]
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR))
    print(f"DMG created: {dmg_path}")
    return dmg_path


def create_installer(target: BuildTarget, paths: dict[str, Path]) -> Path:
    print(f"Packaging installer for {target.key}...")
    if target.installer_kind == "iss":
        return create_windows_installer(target, paths)
    if target.installer_kind == "dmg":
        return create_macos_installer(target, paths)
    raise RuntimeError(f"Unsupported installer kind: {target.installer_kind}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and package desktop app by system + architecture target.")
    parser.add_argument(
        "--target",
        choices=SUPPORTED_TARGETS,
        help="Build target. Defaults to the current host target if supported.",
    )
    parser.add_argument(
        "--skip-installer",
        action="store_true",
        help="Only run PyInstaller build and skip dmg/iss packaging step.",
    )
    parser.add_argument(
        "--skip-pyinstaller-install",
        action="store_true",
        help="Skip automatic `pip install pyinstaller`.",
    )
    return parser.parse_args()


def infer_default_target() -> str:
    host_os, host_arch = normalize_host_platform()
    target_key = f"{host_os}-{host_arch}"
    if target_key not in TARGETS:
        raise RuntimeError(
            f"Current host {host_os}-{host_arch} is not one of the supported targets: {', '.join(SUPPORTED_TARGETS)}"
        )
    return target_key


def main():
    args = parse_args()
    target_key = args.target or infer_default_target()
    target = ensure_supported_target(target_key)

    print("=" * 60)
    print(f"{APP_DISPLAY_NAME} build tool")
    print(f"Target: {target.key}")
    print("=" * 60)

    try:
        ensure_host_can_build(target)
        paths = ensure_output_dirs(target)

        if not args.skip_pyinstaller_install:
            install_pyinstaller()

        build_app(target, paths)
        helper_artifact = build_mitmdump_helper(target, paths)
        install_mitmdump_helper_into_bundle(target, paths, helper_artifact)
        resign_macos_bundle_if_needed(target, paths)

        if not args.skip_installer:
            create_installer(target, paths)

        print("\n" + "=" * 60)
        print("Build finished")
        print("=" * 60)
    except Exception as exc:
        print(f"\nBuild failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
