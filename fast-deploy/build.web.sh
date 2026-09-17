#!/usr/bin/env bash
# 构建 riveredge-frontend，历史仅保留 tip 一份 dist，并推送供生产机 git pull 部署。
#
# 流程：剥离历史 dist → npm run build → 提交最新 dist + 已跟踪改动 → force-with-lease 推送。
# 生产机 update 直接消费 Git 中的 dist，无需在服务器构建（见 cmd_ensure_frontend_dist）。
#
# 依赖：git-filter-repo（pip install git-filter-repo）
# 前置：当前分支已设置上游（git push -u origin <branch>），且能访问 origin。
# 未跟踪的新文件需自行 git add；Usage: ./fast-deploy/build.web.sh [commit 说明]
#
# 环境变量：
#   BUILD_WEB_SKIP_HISTORY_REWRITE=1  跳过历史剥离与普通 push（调试/应急）

set -euo pipefail
export NODE_OPTIONS="--max-old-space-size=16384"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/build_web_git.sh
source "$SCRIPT_DIR/lib/build_web_git.sh"

cd "$PROJECT_ROOT" || exit 1

git rev-parse --is-inside-work-tree >/dev/null

git fetch origin

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git rev-parse @{u} >/dev/null 2>&1 || {
  echo "错误: 当前分支未配置上游。执行: git push -u origin ${CURRENT_BRANCH}"
  exit 1
}

BEHIND=$(git rev-list --count HEAD.."@{upstream}")
AHEAD=$(git rev-list --count "@{upstream}"..HEAD)
echo "分支 ${CURRENT_BRANCH} | 相对上游 落后 ${BEHIND} / 未推送 ${AHEAD}"
if [ "${BEHIND}" != "0" ]; then
  echo "错误: 本地落后于 origin，请先 git pull 合并远程后再构建发布。"
  exit 1
fi

SOURCE_COMMIT=$(git rev-parse --short HEAD)
SOURCE_MSG=$(git log -1 --pretty=%s)

echo "构建 Web: ${SOURCE_COMMIT} ${SOURCE_MSG}"

build_web_strip_dist_from_history

cd "$PROJECT_ROOT/riveredge-frontend"
npm run build:16g

WEB_DIST="$PROJECT_ROOT/riveredge-frontend/dist"
test -f "$WEB_DIST/index.html"
test -f "$WEB_DIST/login.html"

cd "$PROJECT_ROOT"
git add -A riveredge-frontend/dist
# 已跟踪文件中的其它修改（后端、fast-deploy、文档等）一并纳入本次发布
git add -u

git diff --staged --quiet && {
  echo "错误: 暂存区为空。dist 无变化，且仓库内没有其它已跟踪文件的修改可提交。"
  echo "（若有新文件，请先 git add 后再运行本脚本。）"
  exit 1
}

USER_MSG=${1:-}
if [ -n "$USER_MSG" ]; then
  COMMIT_MSG="$USER_MSG (build-web @ ${SOURCE_COMMIT})"
else
  COMMIT_MSG="chore: build-web sync (build-web @ ${SOURCE_COMMIT})"
fi

git commit -m "$COMMIT_MSG"
build_web_verify_single_dist_commit || true

build_web_push_with_lease "$CURRENT_BRANCH"
echo "完成: $(git rev-parse --short HEAD) 已推送到 origin/${CURRENT_BRANCH}（历史仅 tip 含 dist）"
