#!/bin/bash
# Git 清理提交脚本
# 用于提交从Git中移除不需要追踪的文件的更改

echo "============================================================"
echo "Git 清理提交"
echo "============================================================"

echo ""
echo "当前状态:"
git status --short

echo ""
echo "============================================================"
echo "执行提交"
echo "============================================================"

# 添加 .gitignore 更改
if [ -f .gitignore ]; then
    git add .gitignore
    echo "✓ 已添加 .gitignore"
fi

# 提交删除的文件
git commit -m "chore: 清理不需要追踪的文件

- 移除安装包文件 (*.dmg)
- 移除复制的模板目录 (templates copy/)
- 移除临时文件 (xxx.txtx)
- 更新 .gitignore 配置"

echo ""
echo "============================================================"
echo "后续步骤"
echo "============================================================"
echo ""
echo "1. 检查提交内容:"
echo "   git show"
echo ""
echo "2. 推送到远程仓库:"
echo "   git push origin main"
echo ""
echo "3. 如果需要撤销这次提交:"
echo "   git reset --soft HEAD~1"
echo ""
