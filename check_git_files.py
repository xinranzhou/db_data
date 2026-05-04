#!/usr/bin/env python3
"""
Git 提交检查工具 - 检查哪些文件应该提交到 Git

使用方法:
    python check_git_files.py
"""

import os
import subprocess
from pathlib import Path


def get_file_size(path):
    """获取文件大小"""
    try:
        return os.path.getsize(path)
    except:
        return 0


def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def check_git_status():
    """检查 Git 状态"""
    print("="*60)
    print("Git 提交文件检查")
    print("="*60)
    
    result = subprocess.run(['git', 'status', '--short'], 
                          capture_output=True, text=True)
    
    if result.returncode != 0:
        print("错误: 当前目录不是 Git 仓库")
        return
    
    lines = result.stdout.strip().split('\n')
    
    should_commit = []
    should_not_commit = []
    
    for line in lines:
        if not line.strip():
            continue
        
        status = line[:2].strip()
        filepath = line[3:].strip()
        
        if not os.path.exists(filepath):
            continue
        
        size = get_file_size(filepath)
        
        if filepath.startswith('venv/'):
            should_not_commit.append((filepath, size, '虚拟环境'))
        elif filepath.startswith('__pycache__/'):
            should_not_commit.append((filepath, size, 'Python缓存'))
        elif filepath.startswith('installer/'):
            should_not_commit.append((filepath, size, '安装包'))
        elif filepath.endswith(('.dmg', '.app', '.exe')):
            should_not_commit.append((filepath, size, '安装包'))
        elif filepath.endswith(('.jpg', '.png', '.jpeg')) and any(x in filepath for x in ['result', 'test_', 'match_']):
            should_not_commit.append((filepath, size, '生成的图片'))
        elif filepath.endswith('.pyc'):
            should_not_commit.append((filepath, size, 'Python编译文件'))
        elif filepath == '.DS_Store':
            should_not_commit.append((filepath, size, 'macOS系统文件'))
        elif 'copy' in filepath.lower():
            should_not_commit.append((filepath, size, '复制文件'))
        else:
            should_commit.append((filepath, size))
    
    print("\n✅ 应该提交的文件:")
    print("-" * 60)
    if should_commit:
        for filepath, size in should_commit:
            print(f"  {filepath:<40} {format_size(size):>10}")
    else:
        print("  无")
    
    print("\n❌ 不应该提交的文件:")
    print("-" * 60)
    if should_not_commit:
        for filepath, size, reason in should_not_commit:
            print(f"  {filepath:<40} {format_size(size):>10}  ({reason})")
    else:
        print("  无")
    
    print("\n" + "="*60)
    print("建议操作")
    print("="*60)
    
    if should_commit:
        print("\n# 添加应该提交的文件:")
        print("git add \\")
        for i, (filepath, _) in enumerate(should_commit):
            if i == len(should_commit) - 1:
                print(f"  {filepath}")
            else:
                print(f"  {filepath} \\")
    
    if should_not_commit:
        print("\n# 更新 .gitignore:")
        for filepath, _, reason in should_not_commit:
            if os.path.isfile(filepath):
                print(f"echo '{filepath}' >> .gitignore")


if __name__ == '__main__':
    check_git_status()
