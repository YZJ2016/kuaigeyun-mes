#!/usr/bin/env bash
# 发版机：将主仓工作区 AOCI 正式资产发布到同级 ../kuaigeyun-aoci（或 deploy.env AOCI_REPO_*）。
# 只发布白名单资产：aoci*.txt、AGENTS.md、.gitattributes、.aoci/{config,baseline,curation,database-baseline}.json、
# .cursor/rules、.cursor/memory；.cursor/mcp.json 等本机密钥/运行时文件一律不发布。
#
# Usage: ./fast-deploy/publish.aoci.sh [提交说明]
#
# 等价子命令：./fast-deploy/deploy.sh publish-aoci [说明]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export DEPLOY_MODE="${DEPLOY_MODE:-dev}"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

cd "$PROJECT_ROOT" || exit 1
git rev-parse --is-inside-work-tree >/dev/null

SOURCE_BRANCH=$(git rev-parse --abbrev-ref HEAD)
SOURCE_COMMIT_FULL=$(git rev-parse HEAD)
SOURCE_COMMIT=$(git rev-parse --short HEAD)
USER_MSG=${1:-}

publish_aoci_to_repo "$SOURCE_BRANCH" "$SOURCE_COMMIT_FULL" "$SOURCE_COMMIT" "$USER_MSG" || exit 1
echo "完成: AOCI 正式资产已发布到 kuaigeyun-aoci"
