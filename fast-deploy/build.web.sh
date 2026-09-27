#!/usr/bin/env bash
# 构建 riveredge-frontend，历史仅保留 tip 一份 dist，并推送供生产机 git pull 部署。
#
# 流程：fetch 上游 → 落后则 pull --no-rebase 合并 → 校验源码已 commit
#       → 剥离历史 dist → npm run build → 仅提交 dist → force-with-lease 推送。
# 生产机 update 直接消费 Git 中的 dist，无需在服务器构建（见 cmd_ensure_frontend_dist）。
#
# 依赖：git-filter-repo（pip install git-filter-repo）
# 前置：当前分支已设置上游（如 kuaigeyun/develop 或 origin/<branch>），且能访问该 remote。
# 硬性要求：除 riveredge-frontend/dist 外工作区必须干净（已 commit）；否则 filter-repo 会冲掉本地源码。
# Usage: ./fast-deploy/build.web.sh [dist 提交说明]
#
# 环境变量：
#   BUILD_WEB_SKIP_HISTORY_REWRITE=1  跳过历史剥离与普通 push（调试/应急）
#   BUILD_WEB_SKIP_PULL=1             跳过「落后则自动 merge 拉取」（仅调试）

set -euo pipefail
export NODE_OPTIONS="--max-old-space-size=16384"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/build_web_git.sh
source "$SCRIPT_DIR/lib/build_web_git.sh"

cd "$PROJECT_ROOT" || exit 1

git rev-parse --is-inside-work-tree >/dev/null

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git rev-parse @{u} >/dev/null 2>&1 || {
  echo "错误: 当前分支未配置上游。执行: git push -u <remote> ${CURRENT_BRANCH}"
  exit 1
}

UPSTREAM_REF="$(git rev-parse --abbrev-ref '@{upstream}')"
UPSTREAM_REMOTE="${UPSTREAM_REF%%/*}"
UPSTREAM_BRANCH="${UPSTREAM_REF#*/}"

git fetch "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH"

BEHIND=$(git rev-list --count HEAD.."@{upstream}")
AHEAD=$(git rev-list --count "@{upstream}"..HEAD)
echo "分支 ${CURRENT_BRANCH} | 上游 ${UPSTREAM_REF} | 落后 ${BEHIND} / 未推送 ${AHEAD}"

if [ "${BEHIND}" != "0" ]; then
  if [ "${BUILD_WEB_SKIP_PULL:-0}" = "1" ]; then
    echo "错误: 本地落后于 ${UPSTREAM_REF}，且 BUILD_WEB_SKIP_PULL=1，拒绝构建。"
    exit 1
  fi
  echo "本地落后 ${BEHIND} 个提交，先 git pull --no-rebase 合并上游再构建..."
  # 合并前再次确认非 dist 工作区干净，避免 pull 把本地半成品带进冲突
  build_web_assert_source_tree_committed
  git pull --no-rebase "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH" || {
    echo "错误: 与上游合并失败，请先手动解决冲突后再执行 build.web.sh。"
    exit 1
  }
  BEHIND=$(git rev-list --count HEAD.."@{upstream}")
  AHEAD=$(git rev-list --count "@{upstream}"..HEAD)
  echo "合并后 | 落后 ${BEHIND} / 未推送 ${AHEAD}"
  if [ "${BEHIND}" != "0" ]; then
    echo "错误: pull 后仍落后于 ${UPSTREAM_REF}，请检查上游配置后重试。"
    exit 1
  fi
fi

SOURCE_COMMIT=$(git rev-parse --short HEAD)
SOURCE_MSG=$(git log -1 --pretty=%s)

echo "构建 Web: ${SOURCE_COMMIT} ${SOURCE_MSG}"

build_web_strip_dist_from_history

cd "$PROJECT_ROOT/riveredge-frontend"
# P5-3：构建前显式同步 CAD wasm/workers（postinstall 已有，部署机无 node_modules 变更时仍需）
npm run sync:libredwg
npm run build:16g

WEB_DIST="$PROJECT_ROOT/riveredge-frontend/dist"
test -f "$WEB_DIST/index.html"
test -f "$WEB_DIST/login.html"

cd "$PROJECT_ROOT"
git add -A riveredge-frontend/dist

git diff --staged --quiet && {
  echo "错误: dist 无变化，无需提交。"
  echo "（源码改动须先单独 commit；本脚本只提交 riveredge-frontend/dist。）"
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
echo "完成: $(git rev-parse --short HEAD) 已推送到 ${UPSTREAM_REMOTE}/${CURRENT_BRANCH}（历史仅 tip 含 dist）"
