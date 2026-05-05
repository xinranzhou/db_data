#!/bin/bash
# Git 历史清理 - 快速版（针对Gitee 100MB限制）

echo "============================================================"
echo "Git 历史清理 - 解决Gitee 100MB限制问题"
echo "============================================================"

echo ""
echo "问题: Git历史中存在超过100MB的文件"
echo "  - installer/macos-arm64/rw.45547.DianpingAutoCollector-macos-arm64.dmg (119MB)"
echo "  - installer/macos-arm64/rw.68861.DianpingAutoCollector-macos-arm64.dmg (374MB)"
echo ""
echo "解决方案: 从Git历史中彻底删除 installer/ 目录"
echo ""

read -p "确认继续? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "============================================================"
echo "步骤 1: 创建备份"
echo "============================================================"

git branch backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null
echo "✓ 已创建备份分支"

echo ""
echo "============================================================"
echo "步骤 2: 清理Git历史中的 installer 目录"
echo "============================================================"

echo "正在清理... (这可能需要几分钟)"

git filter-branch --force --index-filter \
  'git rm -rf --cached --ignore-unmatch installer/' \
  --prune-empty --tag-name-filter cat -- --all 2>&1 | grep -E "(Rewrite|rm)"

if [ $? -eq 0 ]; then
    echo "✓ 历史清理完成"
else
    echo "✗ 清理失败"
    exit 1
fi

echo ""
echo "============================================================"
echo "步骤 3: 清理引用"
echo "============================================================"

rm -rf .git/refs/original/
git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin 2>/dev/null
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "✓ 引用清理完成"

echo ""
echo "============================================================"
echo "步骤 4: 验证清理效果"
echo "============================================================"

echo "检查是否还有大文件..."

large_files=$(git rev-list --objects --all | \
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | \
  awk '/^blob/ {if ($3 > 104857600) print $4}')

if [ -z "$large_files" ]; then
    echo "✓ 没有发现超过100MB的文件"
else
    echo "✗ 仍然存在大文件:"
    echo "$large_files"
    exit 1
fi

echo ""
echo "当前仓库大小:"
du -sh .git

echo ""
echo "============================================================"
echo "步骤 5: 推送到远程"
echo "============================================================"

echo ""
echo "现在可以推送到Gitee了:"
echo ""
echo "  git push origin main --force"
echo ""
echo "⚠️  注意: 必须使用 --force 参数"
echo ""

read -p "是否立即推送? (yes/no): " push_confirm

if [ "$push_confirm" == "yes" ]; then
    echo ""
    echo "正在推送..."
    git push origin main --force
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ 推送成功!"
    else
        echo ""
        echo "✗ 推送失败，请手动执行: git push origin main --force"
    fi
fi

echo ""
echo "============================================================"
echo "完成"
echo "============================================================"
