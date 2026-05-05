#!/usr/bin/env python3
"""
Git 大文件分析工具 - 查找Git仓库中的大文件

使用方法:
    python analyze_git_size.py
"""

import subprocess
import os
import sys


def get_git_objects():
    """获取Git对象列表"""
    cmd = "git rev-list --objects --all"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("错误: 无法获取Git对象")
        return []
    
    objects = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            objects.append((parts[0], ' '.join(parts[1:])))
    
    return objects


def get_object_size(sha):
    """获取对象大小"""
    cmd = f"git cat-file -s {sha}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        return 0
    
    try:
        return int(result.stdout.strip())
    except:
        return 0


def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def analyze_large_files(min_size_mb=1):
    """分析大文件"""
    print("="*60)
    print("Git 大文件分析")
    print("="*60)
    
    print("\n正在扫描Git对象...")
    objects = get_git_objects()
    
    if not objects:
        print("没有找到Git对象")
        return
    
    print(f"找到 {len(objects)} 个Git对象")
    
    print("\n正在计算文件大小...")
    file_sizes = []
    
    for i, (sha, filepath) in enumerate(objects):
        if i % 100 == 0:
            print(f"  处理进度: {i}/{len(objects)}", end='\r')
        
        size = get_object_size(sha)
        if size >= min_size_mb * 1024 * 1024:  # 大于指定MB
            file_sizes.append((sha, filepath, size))
    
    print(f"\n找到 {len(file_sizes)} 个大文件 (>{min_size_mb}MB)")
    
    if not file_sizes:
        print("\n✅ 没有找到大文件")
        return
    
    file_sizes.sort(key=lambda x: x[2], reverse=True)
    
    print("\n" + "="*60)
    print(f"大文件列表 (>{min_size_mb}MB)")
    print("="*60)
    
    total_size = 0
    for sha, filepath, size in file_sizes[:20]:  # 只显示前20个
        total_size += size
        print(f"{format_size(size):>12}  {filepath}")
    
    print("\n" + "="*60)
    print("统计信息")
    print("="*60)
    print(f"大文件总数: {len(file_sizes)}")
    print(f"大文件总大小: {format_size(total_size)}")
    
    if len(file_sizes) > 20:
        print(f"\n(只显示前20个，共{len(file_sizes)}个大文件)")


def check_current_tracking():
    """检查当前追踪的大文件"""
    print("\n" + "="*60)
    print("当前追踪的大文件")
    print("="*60)
    
    cmd = "git ls-files"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        return
    
    files = result.stdout.strip().split('\n')
    large_files = []
    
    for filepath in files:
        if not filepath or not os.path.exists(filepath):
            continue
        
        try:
            size = os.path.getsize(filepath)
            if size >= 1024 * 1024:  # 大于1MB
                large_files.append((filepath, size))
        except:
            continue
    
    if large_files:
        large_files.sort(key=lambda x: x[1], reverse=True)
        
        for filepath, size in large_files:
            print(f"{format_size(size):>12}  {filepath}")
    else:
        print("✅ 当前没有追踪大文件")


def check_git_history():
    """检查Git历史中的大文件"""
    print("\n" + "="*60)
    print("Git历史中的大文件")
    print("="*60)
    
    cmd = "git log --all --pretty=format: --name-only --diff-filter=A | sort -u"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        return
    
    files = result.stdout.strip().split('\n')
    large_files = []
    
    for filepath in files:
        if not filepath:
            continue
        
        cmd = f"git log --all --pretty=format:'%H' -- '{filepath}' | head -1"
        result2 = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result2.returncode != 0:
            continue
        
        commit = result2.stdout.strip()
        if not commit:
            continue
        
        cmd = f"git show {commit}:{filepath} 2>/dev/null | wc -c"
        result3 = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        try:
            size = int(result3.stdout.strip())
            if size >= 1024 * 1024:  # 大于1MB
                large_files.append((filepath, size, commit[:8]))
        except:
            continue
    
    if large_files:
        large_files.sort(key=lambda x: x[1], reverse=True)
        
        for filepath, size, commit in large_files[:10]:
            print(f"{format_size(size):>12}  {filepath} (commit: {commit})")
    else:
        print("✅ 历史中没有找到大文件")


if __name__ == '__main__':
    analyze_large_files(min_size_mb=1)
    check_current_tracking()
    check_git_history()
    
    print("\n" + "="*60)
    print("建议")
    print("="*60)
    print("\n如果发现历史中有大文件:")
    print("1. 使用 git filter-branch 或 BFG Repo-Cleaner 清理")
    print("2. 强制推送到远程: git push --force")
    print("3. 通知团队成员重新克隆仓库")
