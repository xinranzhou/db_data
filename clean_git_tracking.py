#!/usr/bin/env python3
"""
清理 Git 追踪 - 移除不应该提交的文件

使用方法:
    python clean_git_tracking.py [--dry-run]
    
    --dry-run: 只显示将要删除的文件，不实际执行
"""

import os
import subprocess
import sys


def run_command(cmd, dry_run=False):
    """执行命令"""
    if dry_run:
        print(f"  [DRY RUN] {cmd}")
        return None
    else:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result


def get_tracked_files():
    """获取所有被Git追踪的文件"""
    result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return result.stdout.strip().split('\n')


def should_remove_from_git(filepath):
    """判断文件是否应该从Git中移除"""
    remove_patterns = [
        'venv/',
        '__pycache__/',
        'installer/',
        '.vscode/',
        '.idea/',
        '.matplotlib/',
        '.DS_Store',
        'result.jpg',
        'result.png',
        'diagnosis_best_match.jpg',
        'best_scale_match.jpg',
        'best_scale_result.jpg',
        'sift_result.jpg',
        'simple_result.jpg',
        'test_result.jpg',
        'test_template.jpg',
        'test_target.jpg',
        'detailed_diagnosis.jpg',
        'xxx.txtx',
    ]
    
    remove_extensions = [
        '.dmg',
        '.app',
        '.exe',
        '.msi',
        '.pyc',
        '.log',
        '.tmp',
        '.temp',
        '.bak',
    ]
    
    for pattern in remove_patterns:
        if filepath.startswith(pattern) or pattern in filepath:
            return True
    
    for ext in remove_extensions:
        if filepath.endswith(ext):
            return True
    
    if ' copy/' in filepath or filepath.endswith(' copy'):
        return True
    
    if 'match_' in filepath and filepath.endswith('.jpg'):
        return True
    
    return False


def clean_git_tracking(dry_run=True):
    """清理Git追踪"""
    print("="*60)
    print("Git 追踪清理工具")
    print("="*60)
    
    if dry_run:
        print("\n⚠️  模拟模式 - 只显示将要删除的文件，不实际执行")
    else:
        print("\n⚠️  实际执行模式 - 将从Git中移除文件（保留本地文件）")
    
    print("\n检查被Git追踪的文件...")
    tracked_files = get_tracked_files()
    
    if not tracked_files:
        print("没有找到被追踪的文件")
        return
    
    files_to_remove = []
    
    for filepath in tracked_files:
        if should_remove_from_git(filepath):
            files_to_remove.append(filepath)
    
    if not files_to_remove:
        print("\n✅ 没有需要移除的文件")
        return
    
    print(f"\n找到 {len(files_to_remove)} 个需要移除的文件:")
    print("-"*60)
    
    for filepath in files_to_remove:
        print(f"  {filepath}")
    
    print("\n" + "="*60)
    print("执行清理")
    print("="*60)
    
    if dry_run:
        print("\n模拟执行以下命令:")
    
    for filepath in files_to_remove:
        cmd = f"git rm --cached '{filepath}'"
        result = run_command(cmd, dry_run)
        
        if not dry_run and result:
            if result.returncode == 0:
                print(f"✓ 已移除: {filepath}")
            else:
                print(f"✗ 移除失败: {filepath}")
                print(f"  错误: {result.stderr}")
    
    if not dry_run:
        print("\n" + "="*60)
        print("后续步骤")
        print("="*60)
        print("\n1. 检查 .gitignore 文件是否已更新")
        print("2. 提交更改:")
        print("   git add .gitignore")
        print("   git commit -m 'chore: 清理不需要追踪的文件'")
        print("3. 推送到远程:")
        print("   git push")


if __name__ == '__main__':
    dry_run = '--dry-run' not in sys.argv
    
    if '--help' in sys.argv or '-h' in sys.argv:
        print(__doc__)
        print("\n选项:")
        print("  --dry-run    模拟运行，只显示将要删除的文件")
        print("  --help, -h   显示帮助信息")
        sys.exit(0)
    
    if dry_run:
        print("\n提示: 使用 --dry-run 参数可以模拟运行")
        response = input("\n是否继续执行实际清理? (y/N): ")
        if response.lower() != 'y':
            print("已取消")
            sys.exit(0)
    
    clean_git_tracking(dry_run=False)
