#!/bin/bash
# Git 历史清理脚本 - 彻底删除大文件

echo "============================================================"
echo "Git 历史清理工具 - 删除大文件"
echo "============================================================"

echo ""
echo "⚠️  警告: 此操作将重写Git历史，不可逆！"
echo ""
echo "将要删除的文件:"
echo "  - installer/*.dmg (约988MB)"
echo ""

read -p "确认继续? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "============================================================"
echo "步骤 1: 备份当前分支"
echo "============================================================"

git branch backup-before-cleanup 2>/dev/null
echo "✓ 已创建备份分支: backup-before-cleanup"

echo ""
echo "============================================================"
echo "步骤 2: 使用 git filter-branch 清理历史"
echo "============================================================"

echo "正在清理 installer/ 目录..."
git filter-branch --force --index-filter \
  'git rm -rf --cached --ignore-unmatch installer/' \
  --prune-empty --tag-name-filter cat -- --all

echo "✓ 历史清理完成"

echo ""
echo "============================================================"
echo "步骤 3: 清理引用和垃圾回收"
echo "============================================================"

rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "✓ 垃圾回收完成"

echo ""
echo "============================================================"
echo "步骤 4: 检查清理效果"
echo "============================================================"

echo "当前仓库大小:"
du -sh .git

echo ""
echo "大文件检查:"
git rev-list --objects --all | \
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | \
  awk '/^blob/ {print substr($0,6)}' | \
  sort -n -k2 | \
  tail -n 10 | \
  while read sha size rest; do
    if [ $size -gt 1048576 ]; then
      mb=$((size / 1048576))
      echo "  ${mb}MB  $rest"
    fi
  done

echo ""
echo "============================================================"
echo "后续步骤"
echo "============================================================"
echo ""
echo "1. 检查仓库是否正常:"
echo "   git log --oneline"
echo ""
echo "2. 强制推送到远程:"
echo "   git push origin main --force"
echo ""
echo "3. 如果出现问题，恢复备份:"
echo "   git reset --hard backup-before-cleanup"
echo ""
echo "4. 确认无误后，删除备份分支:"
echo "   git branch -D backup-before-cleanup"
echo ""
