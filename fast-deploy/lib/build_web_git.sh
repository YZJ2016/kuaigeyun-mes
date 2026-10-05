#!/usr/bin/env bash
# build.web.sh 专用：Git 历史仅保留 tip 一份 riveredge-frontend/dist。
# 依赖 git-filter-repo；filter-repo 会暂时移除 remote，由本脚本恢复。

set -euo pipefail

BUILD_WEB_REMOTES_FILE=""

build_web_assert_no_rebase() {
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    echo "错误: 当前处于 rebase 中，请先 git rebase --abort 或 --continue。" >&2
    exit 1
  fi
}

# filter-repo 会重写 checkout，未 commit 的源码（含已 git add 未 commit）会被冲掉。
build_web_assert_source_tree_committed() {
  local dirty=""
  dirty="$(
    git status --porcelain --untracked-files=all |
      while IFS= read -r line; do
        [ -n "$line" ] || continue
        path="${line:3}"
        case "$path" in
          riveredge-frontend/dist/*|riveredge-frontend/dist|\
          riveredge-frontend/dist-blue/*|riveredge-frontend/dist-blue|\
          riveredge-frontend/dist-green/*|riveredge-frontend/dist-green|\
          riveredge-frontend/dist-live/*|riveredge-frontend/dist-live|\
          riveredge-frontend/.perf/*|riveredge-frontend/.perf) continue ;;
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

build_web_commit_is_pure_dist() {
  local sha="$1"
  local non_dist=""
  non_dist="$(
    git diff-tree --no-commit-id --name-only -r "$sha" 2>/dev/null |
      grep -Ev '^riveredge-frontend/dist(/|$)' |
      head -1
  )"
  [ -z "$non_dist" ]
}

# 自 HEAD 到该 dist 提交之间若有 merge，rebase 易冲突，改走 filter-repo。
build_web_range_has_merge_since() {
  local dist_sha="$1"
  local tip="${2:-HEAD}"
  [ -n "$(git log --merges --format=%H "${dist_sha}..${tip}" 2>/dev/null | head -1)" ]
}

# 快速路径：git rebase --onto dist^ dist HEAD，只重写 dist 之后的线性历史。
build_web_drop_pure_dist_commits() {
  local sha dropped=0 tip branch
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$branch" = "HEAD" ]; then
    echo "错误: 当前处于 detached HEAD，请先 git checkout develop 再构建。" >&2
    return 1
  fi
  tip="$(git rev-parse HEAD)"
  build_web_assert_no_rebase
  while true; do
    sha="$(git log --format=%H -1 -- riveredge-frontend/dist 2>/dev/null || true)"
    [ -n "$sha" ] || break
    if ! build_web_commit_is_pure_dist "$sha"; then
      return 1
    fi
    if build_web_range_has_merge_since "$sha" "$tip"; then
      echo "快速剥离跳过: ${sha:0:7} 与 HEAD 之间存在 merge 提交"
      return 1
    fi
    echo "快速剥离: 移除纯 dist 提交 ${sha:0:7}（rebase --onto ${sha:0:7}^）..."
    if ! git rebase --onto "${sha}^" "$sha" "$branch"; then
      git rebase --abort 2>/dev/null || true
      return 1
    fi
    dropped=$((dropped + 1))
    tip="$(git rev-parse HEAD)"
    branch="$(git rev-parse --abbrev-ref HEAD)"
  done
  if [ "$dropped" -gt 0 ]; then
    echo "快速剥离完成: 共移除 ${dropped} 个纯 dist 提交"
  fi
  return 0
}

build_web_restore_upstream_after_rewrite() {
  local branch upstream remote ref
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
}

build_web_maybe_gc() {
  if [ "${BUILD_WEB_GC:-0}" != "1" ]; then
    return 0
  fi
  echo "BUILD_WEB_GC=1: 执行 git gc --prune=now..."
  git reflog expire --expire=now --all 2>/dev/null || true
  git gc --prune=now 2>/dev/null || true
}

build_web_strip_dist_from_history() {
  if [ "${BUILD_WEB_SKIP_HISTORY_REWRITE:-0}" = "1" ]; then
    echo "跳过历史 dist 剥离（BUILD_WEB_SKIP_HISTORY_REWRITE=1）"
    return 0
  fi

  build_web_assert_source_tree_committed
  build_web_assert_no_rebase

  local strip_start=$SECONDS

  if build_web_drop_pure_dist_commits; then
    if [ -z "$(git log --format=%H -1 -- riveredge-frontend/dist 2>/dev/null || true)" ]; then
      echo "历史 dist 剥离（快速路径）耗时 $((SECONDS - strip_start))s"
      build_web_maybe_gc
      return 0
    fi
    echo "仍存在含 dist 的历史提交，改用 git filter-repo 全量剥离..."
  else
    echo "快速剥离不可用，改用 git filter-repo 全量剥离..."
  fi

  build_web_assert_no_rebase
  build_web_require_filter_repo
  build_web_save_remotes

  echo "剥离 Git 历史中的 frontend dist（filter-repo，可能较慢）..."
  rm -rf .git/filter-repo
  GIT_FILTER_REPO_SQUELCH_WARNING=1 git filter-repo \
    --path riveredge-frontend/dist \
    --invert-paths \
    --force

  build_web_restore_remotes
  build_web_restore_upstream_after_rewrite
  echo "历史 dist 剥离（filter-repo）耗时 $((SECONDS - strip_start))s"
  build_web_maybe_gc
}

build_web_verify_single_dist_commit() {
  local count
  count="$(git log --format=%H -- riveredge-frontend/dist 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${count:-0}" -gt 1 ]; then
    echo "警告: 历史中仍存在 ${count} 份含 dist 的提交，请检查剥离是否成功。" >&2
    return 1
  fi
  return 0
}

build_web_push_with_lease() {
  local branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
  local upstream remote
  upstream="$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
  if [ -n "$upstream" ]; then
    remote="${upstream%%/*}"
  else
    remote="origin"
  fi
  if [ "${BUILD_WEB_SKIP_HISTORY_REWRITE:-0}" = "1" ]; then
    git push "$remote" "$branch"
    return
  fi
  echo "推送（--force-with-lease → ${remote}/${branch}：历史已重写，仅 tip 含 dist）..."
  git push --force-with-lease "$remote" "$branch"
}
