#!/usr/bin/env bash
# build.web.sh 专用：Git 历史仅保留 tip 一份 riveredge-frontend/dist。
# 依赖 git-filter-repo；filter-repo 会暂时移除 remote，由本脚本恢复。

set -euo pipefail

BUILD_WEB_REMOTES_FILE=""

# filter-repo 会重写 checkout，未 commit 的源码（含已 git add 未 commit）会被冲掉。
build_web_assert_source_tree_committed() {
  local dirty=""
  dirty="$(
    git status --porcelain --untracked-files=all |
      while IFS= read -r line; do
        [ -n "$line" ] || continue
        path="${line:3}"
        case "$path" in
          riveredge-frontend/dist/*) continue ;;
        esac
        printf '%s\n' "$line"
      done
  )"
  if [ -n "$dirty" ]; then
    echo "错误: 工作区存在未 commit 的源码改动；filter-repo 会将其冲掉（含已暂存的新文件）。" >&2
    echo "请先 git add 并 git commit 全部源码，再执行 build.web.sh。" >&2
    echo "$dirty" >&2
    exit 1
  fi
}

build_web_require_filter_repo() {
  if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "错误: build.web.sh 需要 git-filter-repo。" >&2
    echo "安装: pip install git-filter-repo" >&2
    exit 1
  fi
}

build_web_save_remotes() {
  BUILD_WEB_REMOTES_FILE="$(mktemp "${TMPDIR:-/tmp}/build-web-remotes.XXXXXX")"
  git remote | while read -r name; do
    url="$(git remote get-url "$name" 2>/dev/null || true)"
    [ -n "$url" ] || continue
    printf '%s\t%s\n' "$name" "$url"
  done >"$BUILD_WEB_REMOTES_FILE"
}

build_web_restore_remotes() {
  [ -n "${BUILD_WEB_REMOTES_FILE:-}" ] && [ -f "$BUILD_WEB_REMOTES_FILE" ] || return 0
  while IFS=$'\t' read -r name url; do
    [ -n "$name" ] && [ -n "$url" ] || continue
    if git remote get-url "$name" >/dev/null 2>&1; then
      git remote set-url "$name" "$url"
    else
      git remote add "$name" "$url"
    fi
  done <"$BUILD_WEB_REMOTES_FILE"
  rm -f "$BUILD_WEB_REMOTES_FILE"
  BUILD_WEB_REMOTES_FILE=""
}

# 从全部提交历史中移除 dist；工作区 dist 也会被清掉，须在此之后重新 npm run build。
build_web_strip_dist_from_history() {
  if [ "${BUILD_WEB_SKIP_HISTORY_REWRITE:-0}" = "1" ]; then
    echo "跳过历史 dist 剥离（BUILD_WEB_SKIP_HISTORY_REWRITE=1）"
    return 0
  fi

  build_web_assert_source_tree_committed

  build_web_require_filter_repo
  build_web_save_remotes

  echo "剥离 Git 历史中的 frontend dist（发布后将仅 tip 保留一份）..."
  rm -rf .git/filter-repo
  GIT_FILTER_REPO_SQUELCH_WARNING=1 git filter-repo \
    --path riveredge-frontend/dist \
    --invert-paths \
    --force

  build_web_restore_remotes

  local branch upstream
  branch="$(git rev-parse --abbrev-ref HEAD)"
  upstream="$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
  if [ -n "$upstream" ]; then
    remote="${upstream%%/*}"
    ref="${upstream#*/}"
    if git remote get-url "$remote" >/dev/null 2>&1; then
      git fetch "$remote" "$ref" 2>/dev/null || true
      git branch --set-upstream-to="$upstream" "$branch" 2>/dev/null || true
    fi
  fi

  git reflog expire --expire=now --all 2>/dev/null || true
  git gc --prune=now 2>/dev/null || true
}

build_web_verify_single_dist_commit() {
  local count=0
  local line
  while IFS= read -r line; do
    count=$((count + 1))
    if [ "$count" -gt 1 ]; then
      echo "警告: 历史中仍存在多份 dist 提交，请检查 filter-repo 是否成功。" >&2
      return 1
    fi
  done < <(
    git rev-list --all | while read -r c; do
      if git ls-tree -r --name-only "$c" -- riveredge-frontend/dist 2>/dev/null | grep -q .; then
        echo "$c"
      fi
    done
  )
  return 0
}

build_web_push_with_lease() {
  local branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
  if [ "${BUILD_WEB_SKIP_HISTORY_REWRITE:-0}" = "1" ]; then
    git push origin "$branch"
    return
  fi
  echo "推送（--force-with-lease：历史已重写，仅 tip 含 dist）..."
  git push --force-with-lease origin "$branch"
}
