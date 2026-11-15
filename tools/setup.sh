#!/bin/sh
# 新克隆后执行一次：启用约定式提交钩子与提交模板
set -e
git config core.hooksPath .githooks
git config commit.template .gitmessage
chmod +x .githooks/commit-msg 2>/dev/null || true
echo "ok: hooksPath=$(git config --get core.hooksPath), template=$(git config --get commit.template)"
