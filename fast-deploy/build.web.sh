#!/usr/bin/env bash
# 【默认停用】构建 riveredge-frontend 并发布 dist。两种发布模式：
#
#   模式 A（默认，上游 dist 仓）：
#     npm build → 推送 riveredge-frontend/dist 到同级 ../kuaigeyun-dist 仓根
#     （或 deploy.env 的 WEB_DIST_REPO_*），主仓始终不提交 dist。
#     生产机 update/start 走 PROD_WEB_DIST_SOURCE=dist_repo 同步（见 cmd_ensure_frontend_dist）。
#   模式 B（legacy，BUILD_WEB_LEGACY_MAIN_DIST=1）：
#     旧「剥离历史 dist → npm build → 仅提交 dist 到主仓 → force-with-lease 推送」，
#     历史仅 tip 一份 dist。需要 git-filter-repo。
#
# 2026-11-19 起 dist 不再入库、部署机 update/start 时 npm run build 现构建，本脚本默认跳过。
# 仅在需要恢复发布流程时显式打开：
#   BUILD_WEB_PUBLISH=1 ./fast-deploy/build.web.sh
# 未开开关直接退出 0（跳过，不算失败），可安全留在自动化/文档中。
#
# 模式 B 说明：Git 只提交未压缩 dist（.gz/.br 被 gitignore，避免仓库膨胀）；
# 生产机 update/start 在 cmd_ensure_frontend_dist 里按 dist 现生成预压缩，供 Caddy precompressed。
#
# 前置：当前分支已设置上游（如 kuaigeyun/develop 或 origin/<branch>），且能访问该 remote。
# 模式 B 依赖：git-filter-repo（pip install git-filter-repo）；模式 B 硬性要求：
# 除 riveredge-frontend/dist 外工作区必须干净（已 commit），否则 filter-repo 会冲掉本地源码。
#
# Usage: BUILD_WEB_PUBLISH=1 ./fast-deploy/build.web.sh [dist 提交说明]
#
# 环境变量：
#   BUILD_WEB_PUBLISH=1               总开关；未设置时脚本直接跳过
#   BUILD_WEB_SKIP_PULL=1             跳过「落后则自动 merge 拉取」（仅调试）
#   BUILD_WEB_SKIP_DIST_PUBLISH=1     模式 A：只构建不推 dist 仓（本地验证）
#   BUILD_WEB_SKIP_NPM_BUILD=1        跳过 npm（沿用已有 riveredge-frontend/dist，仅发布）
#   BUILD_WEB_SKIP_AMOUNT_SCAN=1      跳过采购价税契约扫描（仅本地调试）
#   BUILD_WEB_LEGACY_MAIN_DIST=1      模式 B：filter-repo + 在主仓提交 dist（不推荐）
#   BUILD_WEB_SKIP_HISTORY_REWRITE=1  模式 B：跳过历史剥离与普通 push（调试/应急）
#   BUILD_WEB_GC=1                    模式 B：剥离后 git gc（默认关）
#
# 注意：本脚本不跑 AOCI。AOCI 认知索引可单独发布，见 fast-deploy/publish.aoci.sh / install-aoci。

set -euo pipefail

if [ "${BUILD_WEB_PUBLISH:-0}" != "1" ]; then
  echo "build.web.sh 默认停用：dist 不再入库，部署机部署时现构建。"
  echo "确需恢复发布流程时显式打开：BUILD_WEB_PUBLISH=1 $0"
  exit 0
fi

export NODE_OPTIONS="--max-old-space-size=16384"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/build_web_git.sh
source "$SCRIPT_DIR/lib/build_web_git.sh"
export DEPLOY_MODE=dev
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

cd "$PROJECT_ROOT" || exit 1

git rev-parse --is-inside-work-tree >/dev/null

if [ -f "$PROJECT_ROOT/.git/MERGE_HEAD" ]; then
  echo "错误: 当前处于 merge 中，请先完成或 abort merge 后再构建。"
  exit 1
fi
build_web_assert_no_rebase

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

SOURCE_COMMIT_FULL=$(git rev-parse HEAD)
SOURCE_COMMIT=$(git rev-parse --short HEAD)
SOURCE_MSG=$(git log -1 --pretty=%s)

echo "构建 Web: ${SOURCE_COMMIT} ${SOURCE_MSG}"

build_web_assert_source_tree_committed

if [ "${BUILD_WEB_LEGACY_MAIN_DIST:-0}" = "1" ]; then
  build_web_strip_dist_from_history
fi

WEB_DIST="$PROJECT_ROOT/riveredge-frontend/dist"
if [ "${BUILD_WEB_SKIP_NPM_BUILD:-0}" = "1" ]; then
  echo "BUILD_WEB_SKIP_NPM_BUILD=1：跳过 npm，使用已有 ${WEB_DIST}"
else
  cd "$PROJECT_ROOT/riveredge-frontend"
  # P5-3：构建前显式同步 CAD wasm/workers（postinstall 已有，部署机无 node_modules 变更时仍需）
  SYNC_START=$SECONDS
  npm run sync:libredwg
  echo "sync:libredwg 耗时 $((SECONDS - SYNC_START))s"
  if [ "${BUILD_WEB_SKIP_AMOUNT_SCAN:-0}" != "1" ]; then
    echo "采购价税契约扫描（scan_purchase_amount_contract）..."
    PYBIN="$(command -v python || command -v python3)"
    "$PYBIN" scripts/scan_purchase_amount_contract.py --fail-on high || {
      echo "错误: 采购价税契约扫描失败。修复后重试，或仅本地调试 BUILD_WEB_SKIP_AMOUNT_SCAN=1"
      exit 1
    }
  fi
  BUILD_START=$SECONDS
  npm run build:16g
  echo "vite build:16g 耗时 $((SECONDS - BUILD_START))s"
fi
test -f "$WEB_DIST/index.html"
test -f "$WEB_DIST/login.html"

USER_MSG=${1:-}

if [ "${BUILD_WEB_LEGACY_MAIN_DIST:-0}" = "1" ]; then
  cd "$PROJECT_ROOT"
  # dist 已 gitignore（默认不入库）；legacy 开关开启时 -f 强制纳入本次发布
  git add -fA riveredge-frontend/dist
  git diff --staged --quiet && {
    echo "错误: dist 无变化，无需提交。"
    echo "（源码改动须先单独 commit；本脚本只提交 riveredge-frontend/dist。）"
    exit 1
  }
  if [ -n "$USER_MSG" ]; then
    COMMIT_MSG="$USER_MSG (build-web @ ${SOURCE_COMMIT})"
  else
    COMMIT_MSG="chore: build-web sync (build-web @ ${SOURCE_COMMIT})"
  fi
  git commit -m "$COMMIT_MSG"
  build_web_verify_single_dist_commit || true
  # 构建耗时长，推送前再合一次上游，降低 period 内被并行推送打成 non-FF 的概率
  git fetch "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH"
  BEHIND_AFTER=$(git rev-list --count HEAD.."@{upstream}")
  if [ "${BEHIND_AFTER}" != "0" ]; then
    if [ "${BUILD_WEB_SKIP_PULL:-0}" = "1" ]; then
      echo "错误: 构建后本地落后于 ${UPSTREAM_REF}，且 BUILD_WEB_SKIP_PULL=1，拒绝推送。"
      exit 1
    fi
    echo "构建期间上游前进 ${BEHIND_AFTER} 个提交，推送前再 git pull --no-rebase..."
    git pull --no-rebase "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH" || {
      echo "错误: 推送前与上游合并失败，请先手动解决冲突。"
      exit 1
    }
  fi
  build_web_push_with_lease "$CURRENT_BRANCH"
  echo "完成（legacy）: 主仓已推送 dist @ ${SOURCE_COMMIT}（历史仅 tip 含 dist）"
  exit 0
fi

if [ "${BUILD_WEB_SKIP_DIST_PUBLISH:-0}" = "1" ]; then
  echo "BUILD_WEB_SKIP_DIST_PUBLISH=1：已构建 ${WEB_DIST}，跳过 kuaigeyun-dist 发布。"
  exit 0
fi

PUBLISH_START=$SECONDS
publish_web_dist_to_repo "$WEB_DIST" "$UPSTREAM_BRANCH" "$SOURCE_COMMIT_FULL" "$SOURCE_COMMIT" "$USER_MSG" || exit 1
echo "publish kuaigeyun-dist 耗时 $((SECONDS - PUBLISH_START))s"

echo "完成: Web dist 已发布到 kuaigeyun-dist（主仓源码请单独 git push，不含 dist）"
if [ "${AHEAD}" != "0" ] || [ "$(git rev-list --count "@{upstream}"..HEAD)" != "0" ]; then
  echo "提示: 主仓仍有未推送源码提交，请执行: git push ${UPSTREAM_REMOTE} ${CURRENT_BRANCH}"
fi
