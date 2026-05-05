#!/usr/bin/env python3
"""
跨平台依赖分析工具 - 分析项目中的跨平台限制

使用方法:
    python analyze_cross_platform.py
"""

import subprocess
import sys
from pathlib import Path


def analyze_dependencies():
    """分析依赖的跨平台兼容性"""
    
    print("="*60)
    print("跨平台依赖分析")
    print("="*60)
    
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print("错误: requirements.txt 不存在")
        return
    
    dependencies = {
        "opencv-python": {
            "platforms": ["Windows", "macOS", "Linux"],
            "issues": [
                "依赖平台特定的二进制库",
                "不同平台需要不同的wheel包",
                "某些功能在不同平台表现不同"
            ],
            "solutions": [
                "使用opencv-python-headless减少依赖",
                "在目标平台上重新安装依赖"
            ]
        },
        "PyQt5": {
            "platforms": ["Windows", "macOS", "Linux"],
            "issues": [
                "GUI框架，依赖平台特定的窗口系统",
                "macOS需要特定版本的Qt",
                "Windows需要特定的DLL",
                "打包后体积较大"
            ],
            "solutions": [
                "考虑使用PyQt6或PySide6",
                "确保在目标平台安装正确的Qt版本"
            ]
        },
        "pyobjc-framework-Quartz": {
            "platforms": ["macOS ONLY"],
            "issues": [
                "macOS专有框架",
                "无法在Windows/Linux上运行",
                "依赖macOS系统API"
            ],
            "solutions": [
                "使用条件导入",
                "提供平台特定的替代方案",
                "在requirements中标记为可选"
            ]
        },
        "mitmproxy": {
            "platforms": ["Windows", "macOS", "Linux"],
            "issues": [
                "依赖平台特定的网络库",
                "某些功能在不同平台表现不同",
                "打包后体积较大"
            ],
            "solutions": [
                "确保在目标平台测试",
                "考虑使用轻量级替代方案"
            ]
        },
        "playwright": {
            "platforms": ["Windows", "macOS", "Linux"],
            "issues": [
                "需要下载平台特定的浏览器驱动",
                "打包时需要包含浏览器二进制",
                "体积非常大(>100MB)"
            ],
            "solutions": [
                "使用playwright install安装驱动",
                "考虑使用系统浏览器",
                "打包时包含浏览器驱动"
            ]
        },
        "pyautogui": {
            "platforms": ["Windows", "macOS", "Linux"],
            "issues": [
                "依赖平台特定的GUI自动化库",
                "macOS需要辅助功能权限",
                "Linux需要X11"
            ],
            "solutions": [
                "确保在目标平台测试",
                "提供权限设置指南"
            ]
        }
    }
    
    print("\n" + "="*60)
    print("依赖分析结果")
    print("="*60)
    
    for dep_name, info in dependencies.items():
        print(f"\n📦 {dep_name}")
        print(f"   支持平台: {', '.join(info['platforms'])}")
        print(f"   潜在问题:")
        for issue in info['issues']:
            print(f"     - {issue}")
        print(f"   解决方案:")
        for solution in info['solutions']:
            print(f"     ✓ {solution}")
    
    return dependencies


def analyze_code_platform_specific():
    """分析代码中的平台特定部分"""
    
    print("\n" + "="*60)
    print("代码中的平台特定部分")
    print("="*60)
    
    platform_specific_imports = [
        "pyobjc",
        "Quartz",
        "AppKit",
        "win32",
        "ctypes.windll",
    ]
    
    platform_specific_code = []
    
    for py_file in Path(".").rglob("*.py"):
        if py_file.name.startswith("test_"):
            continue
        if py_file.name in ["analyze_cross_platform.py"]:
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8")
            
            for pattern in platform_specific_imports:
                if pattern in content:
                    platform_specific_code.append({
                        "file": str(py_file),
                        "pattern": pattern
                    })
        except:
            continue
    
    if platform_specific_code:
        print("\n发现平台特定代码:")
        for item in platform_specific_code:
            print(f"  📄 {item['file']}")
            print(f"     发现: {item['pattern']}")
    else:
        print("\n✓ 未发现明显的平台特定代码")


def analyze_build_config():
    """分析打包配置"""
    
    print("\n" + "="*60)
    print("打包配置分析")
    print("="*60)
    
    build_file = Path("build_app.py")
    if not build_file.exists():
        print("错误: build_app.py 不存在")
        return
    
    content = build_file.read_text(encoding="utf-8")
    
    print("\n支持的目标平台:")
    print("  ✓ macos-arm64 (Apple Silicon)")
    print("  ✓ macos-x86_64 (Intel Mac)")
    print("  ✓ windows-x64 (Windows 64位)")
    
    print("\n打包限制:")
    print("  1. 必须在对应平台上打包")
    print("     - macOS应用必须在macOS上打包")
    print("     - Windows应用必须在Windows上打包")
    print("  2. 架构必须匹配")
    print("     - arm64必须在Apple Silicon Mac上打包")
    print("     - x86_64必须在Intel Mac上打包")
    
    print("\n原因:")
    print("  - PyInstaller打包的二进制文件依赖平台")
    print("  - PyQt5等GUI库需要平台特定的Qt库")
    print("  - pyobjc等macOS专有库无法跨平台")


def generate_recommendations():
    """生成改进建议"""
    
    print("\n" + "="*60)
    print("改进建议")
    print("="*60)
    
    recommendations = [
        {
            "title": "分离平台特定依赖",
            "description": "将macOS专有依赖标记为可选",
            "example": """
# requirements.txt
opencv-python>=4.5.0
PyQt5>=5.15.0

# macOS特定（可选）
pyobjc-framework-Quartz>=8.0; sys_platform == 'darwin'
            """
        },
        {
            "title": "使用条件导入",
            "description": "在代码中使用条件导入处理平台差异",
            "example": """
import sys

if sys.platform == 'darwin':
    try:
        from Quartz import CGWindowListCopyWindowInfo
        HAS_QUARTZ = True
    except ImportError:
        HAS_QUARTZ = False
else:
    HAS_QUARTZ = False
            """
        },
        {
            "title": "使用CI/CD跨平台构建",
            "description": "使用GitHub Actions等工具在不同平台上构建",
            "example": """
# .github/workflows/build.yml
jobs:
  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v2
      - run: python build_app.py --target macos-arm64
  
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - run: python build_app.py --target windows-x64
            """
        },
        {
            "title": "考虑替代方案",
            "description": "使用跨平台替代方案",
            "alternatives": [
                "PyQt5 → PyQt6 或 PySide6 (更好的跨平台支持)",
                "pyobjc → platform-specific adapters",
                "opencv-python → opencv-python-headless (更小的体积)"
            ]
        }
    ]
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['title']}")
        print(f"   {rec['description']}")
        if 'example' in rec:
            print(f"\n   示例:")
            for line in rec['example'].strip().split('\n'):
                print(f"     {line}")
        if 'alternatives' in rec:
            print(f"\n   替代方案:")
            for alt in rec['alternatives']:
                print(f"     - {alt}")


def main():
    analyze_dependencies()
    analyze_code_platform_specific()
    analyze_build_config()
    generate_recommendations()
    
    print("\n" + "="*60)
    print("总结")
    print("="*60)
    print("""
主要跨平台限制来源:

1. 🔴 macOS专有依赖
   - pyobjc-framework-Quartz (仅macOS)
   - 解决: 标记为可选依赖

2. 🟡 GUI框架
   - PyQt5 (跨平台但需要平台特定的Qt库)
   - 解决: 在目标平台重新安装

3. 🟡 浏览器自动化
   - Playwright (需要平台特定的浏览器驱动)
   - 解决: 打包时包含驱动或运行时下载

4. 🟢 OpenCV
   - opencv-python (跨平台但有平台特定二进制)
   - 解决: 使用headless版本或在目标平台安装

建议:
✓ 使用CI/CD在不同平台上构建
✓ 分离平台特定依赖
✓ 提供详细的安装和打包文档
✓ 考虑使用Docker容器化部署
    """)


if __name__ == '__main__':
    main()
