#!/usr/bin/env bash
# kuaigeyun-aoci：主仓 AOCI 正式认知资产专用仓（仓根布局与主仓一致，MCP 仍 --repo 主仓根）

AOCI_FORMAL_ROOT_FILES=(aoci.txt aoci.meta.txt aoci.code.txt)
AOCI_FORMAL_DOT_AOCI_REQUIRED=(config.json baseline.json curation.json)
AOCI_FORMAL_DOT_AOCI_OPTIONAL=(database-baseline.json)
# 主仓不再 Git 跟踪，与认知索引一并发布到 kuaigeyun-aoci
AOCI_FORMAL_ROOT_EXTRA=(AGENTS.md .gitattributes)
AOCI_FORMAL_DIR_EXTRA=(.cursor)

_aoci_default_repo_path() {
    echo "$(cd "$PROJECT_ROOT/.." && pwd)/kuaigeyun-aoci"
}

_aoci_repo_token() {
    local token
    token="$(read_deploy_env_value AOCI_GIT_TOKEN || true)"
    [ -n "$token" ] || token="$(read_deploy_env_value PRO_GIT_TOKEN || true)"
    [ -n "$token" ] || token="$(read_deploy_env_value CLIENT_GIT_TOKEN || true)"
    printf '%s\n' "$(_env_read_trim "$token")"
}

aoci_assert_formal_assets_present() {
    local root="$1" f rel
    root="${root:-$PROJECT_ROOT}"
    for f in "${AOCI_FORMAL_ROOT_FILES[@]}"; do
        [ -f "$root/$f" ] || {
            log_error "缺少 AOCI 正式文件 ${root}/${f}"
            return 1
        }
    done
    [ -f "$root/.aoci/.gitignore" ] || {
        log_error "缺少 ${root}/.aoci/.gitignore"
        return 1
    }
    for rel in "${AOCI_FORMAL_DOT_AOCI_REQUIRED[@]}"; do
        [ -f "$root/.aoci/$rel" ] || {
            log_error "缺少 ${root}/.aoci/${rel}"
            return 1
        }
    done
    return 0
}

_resolve_aoci_repo_root() {
    local repo_root="$1"
    if [ -f "$repo_root/aoci.txt" ] && [ -f "$repo_root/aoci.meta.txt" ]; then
        printf '%s\n' "$repo_root"
        return 0
    fi
    return 1
}

install_aoci_from_aoci_repo() {
    local aoci_repo_root="$1"
    local src_root dest
    src_root="$(_resolve_aoci_repo_root "$aoci_repo_root")" || {
        log_error "aoci 仓根缺少 aoci.txt / aoci.meta.txt"
        log_error "请先 publish 或 clone https://gitee.com/kuaigeyun/kuaigeyun-aoci"
        return 1
    }
    dest="$PROJECT_ROOT"
    mkdir -p "$dest/.aoci"
    for f in "${AOCI_FORMAL_ROOT_FILES[@]}" "${AOCI_FORMAL_ROOT_EXTRA[@]}"; do
        [ -f "$src_root/$f" ] || continue
        cp -f "$src_root/$f" "$dest/$f" || {
            log_error "复制 ${f} 失败"
            return 1
        }
    done
    local d
    for d in "${AOCI_FORMAL_DIR_EXTRA[@]}"; do
        [ -d "$src_root/$d" ] || continue
        mkdir -p "$dest/$d"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --delete "$src_root/$d/" "$dest/$d/" || return 1
        else
            cp -a "$src_root/$d/." "$dest/$d/" || return 1
        fi
    done
    cp -f "$src_root/.aoci/.gitignore" "$dest/.aoci/.gitignore" 2>/dev/null || true
    for rel in "${AOCI_FORMAL_DOT_AOCI_REQUIRED[@]}" "${AOCI_FORMAL_DOT_AOCI_OPTIONAL[@]}"; do
        [ -f "$src_root/.aoci/$rel" ] || continue
        cp -f "$src_root/.aoci/$rel" "$dest/.aoci/$rel" || {
            log_error "复制 .aoci/${rel} 失败"
            return 1
        }
    done
    if [ -f "$aoci_repo_root/aoci-source.meta.json" ]; then
        cp -f "$aoci_repo_root/aoci-source.meta.json" "$dest/.aoci/aoci-source.meta.json" 2>/dev/null || true
    fi
    aoci_assert_formal_assets_present "$dest" || return 1
    log_ok "AOCI 正式资产已安装 → ${dest}（来自 kuaigeyun-aoci）"
}

sync_aoci_from_repo() {
    load_deploy_env
    local url path branch token
    url="$(_read_repo_url_or_default AOCI_REPO_URL "$DEFAULT_AOCI_REPO_URL")"
    path="$(read_deploy_env_value AOCI_REPO_PATH || true)"
    [ -n "$path" ] || path="$(_aoci_default_repo_path)"
    branch="$(read_deploy_env_value AOCI_GIT_BRANCH || echo develop)"
    token="$(_aoci_repo_token)"
    _warn_missing_https_token "AOCI 仓" "$url" "$token" "AOCI_GIT_TOKEN"
    set_deploy_env_value AOCI_REPO_URL "$url"
    set_deploy_env_value AOCI_REPO_PATH "$path"
    set_deploy_env_value AOCI_GIT_BRANCH "$branch"
    sync_sibling_git_repo "kuaigeyun-aoci" "$url" "$path" "$branch" "$token" || return 1
    install_aoci_from_aoci_repo "$path" || return 1
}

cmd_install_aoci_repo() {
    sync_aoci_from_repo || return 1
    log_ok "AOCI 源仓已同步并安装到主仓工作区"
}

write_aoci_source_meta_json() {
    local dest_file="$1" source_branch="$2" source_commit_full="$3" source_commit_short="$4"
    local built_at
    built_at="$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || date -u '+%Y-%m-%dT%H:%M:%SZ')"
    cat >"$dest_file" <<EOF
{
  "source_repo": "kuaigeyun",
  "source_branch": "${source_branch}",
  "source_commit": "${source_commit_full}",
  "source_commit_short": "${source_commit_short}",
  "published_at": "${built_at}"
}
EOF
}

# 发版机：将工作区 AOCI 正式资产发布到 kuaigeyun-aoci 仓根
_ensure_aoci_sibling_repo() {
    local url path branch token auth_url clean_url git_path
    url="$1"
    path="$2"
    branch="$3"
    token="$4"
    clean_url="$(_git_strip_auth_url "$url")"
    auth_url="$(_git_auth_url "$clean_url" "$token")"
    git_path="$(_git_native_path "$path")"

    if _git_is_work_tree "$path"; then
        sync_sibling_git_repo "kuaigeyun-aoci" "$url" "$path" "$branch" "$token" || return 1
        return 0
    fi

    if _git_cmd ls-remote --heads "$auth_url" "refs/heads/${branch}" 2>/dev/null | grep -q .; then
        sync_sibling_git_repo "kuaigeyun-aoci" "$url" "$path" "$branch" "$token" || return 1
        return 0
    fi

    log_info "kuaigeyun-aoci 远程尚无 ${branch}，初始化本地仓（首次 publish）…"
    if [ -e "$path" ] && [ -n "$(ls -A "$path" 2>/dev/null)" ]; then
        rm -rf "$path" || return 1
    fi
    mkdir -p "$path"
    _git_cmd -C "$git_path" init -b "$branch" || return 1
    _git_cmd -C "$git_path" remote add origin "$clean_url" 2>/dev/null || \
        _git_cmd -C "$git_path" remote set-url origin "$clean_url" || return 1
    return 0
}

publish_aoci_to_repo() {
    local source_branch="$1" source_commit_full="$2" source_commit_short="$3" user_msg="$4"
    load_deploy_env
    local url path branch token repo_root git_path commit_msg f rel
    url="$(_read_repo_url_or_default AOCI_REPO_URL "$DEFAULT_AOCI_REPO_URL")"
    path="$(read_deploy_env_value AOCI_REPO_PATH || true)"
    [ -n "$path" ] || path="$(_aoci_default_repo_path)"
    branch="$(read_deploy_env_value AOCI_GIT_BRANCH || echo develop)"
    token="$(_aoci_repo_token)"
    _warn_missing_https_token "AOCI 仓" "$url" "$token" "AOCI_GIT_TOKEN"

    aoci_assert_formal_assets_present "$PROJECT_ROOT" || return 1

    _ensure_aoci_sibling_repo "$url" "$path" "$branch" "$token" || return 1
    repo_root="$path"
    git_path="$(_git_native_path "$repo_root")"
    mkdir -p "$repo_root/.aoci"

    _tune_sibling_git_perf "$git_path"
    # 与 dist 仓一致：禁止 CRLF 把整棵 .cursor 每次 add 重写一遍
    printf '%s\n' '* -text' >"$repo_root/.gitattributes"

    log_info "发布 AOCI → ${repo_root}（仓根与主仓路径一致）"
    for f in "${AOCI_FORMAL_ROOT_FILES[@]}" "${AOCI_FORMAL_ROOT_EXTRA[@]}"; do
        [ -f "$PROJECT_ROOT/$f" ] || {
            log_error "缺少 ${PROJECT_ROOT}/${f}"
            return 1
        }
        cp -f "$PROJECT_ROOT/$f" "$repo_root/$f"
    done
    for d in "${AOCI_FORMAL_DIR_EXTRA[@]}"; do
        [ -d "$PROJECT_ROOT/$d" ] || {
            log_error "缺少目录 ${PROJECT_ROOT}/${d}"
            return 1
        }
        # 禁止 rm -rf 整树再拷：Windows 上会对 .cursor 数百文件反复 CRLF/rename 检测。
        mkdir -p "$repo_root/$d"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --delete "$PROJECT_ROOT/$d/" "$repo_root/$d/" || return 1
        else
            cp -a "$PROJECT_ROOT/$d/." "$repo_root/$d/" || return 1
        fi
    done
    cp -f "$PROJECT_ROOT/.aoci/.gitignore" "$repo_root/.aoci/.gitignore" 2>/dev/null || true
    for rel in "${AOCI_FORMAL_DOT_AOCI_REQUIRED[@]}" "${AOCI_FORMAL_DOT_AOCI_OPTIONAL[@]}"; do
        [ -f "$PROJECT_ROOT/.aoci/$rel" ] || continue
        cp -f "$PROJECT_ROOT/.aoci/$rel" "$repo_root/.aoci/$rel"
    done
    write_aoci_source_meta_json "$repo_root/aoci-source.meta.json" "$source_branch" "$source_commit_full" "$source_commit_short"

    if [ ! -f "$repo_root/README.md" ]; then
        cat >"$repo_root/README.md" <<'EOF'
# kuaigeyun-aoci

主仓 **AOCI 正式认知资产**专用仓。布局与主仓根一致：`aoci.txt`、`aoci.meta.txt`、`aoci.code.txt`、`.aoci/config.json` 等。

- 勿手工改索引语义；由 Agent `aoci_maintain` / `aoci_update_entry` 后 `fast-deploy/publish.aoci.sh` 推送。
- 新克隆主仓：`./fast-deploy/deploy.sh install-aoci` 同步到工作区（MCP `--repo` 仍指向主仓根）。
- `aoci-source.meta.json` 记录对应主仓源码 commit。
- 发版热路径不阻塞本仓：先 build.web / 源码 push，再按需 publish.aoci。
EOF
    fi

    if [ -n "$user_msg" ]; then
        commit_msg="${user_msg} (aoci @ ${source_commit_short})"
    else
        commit_msg="chore: aoci sync (aoci @ ${source_commit_short})"
    fi

    _git_cmd -C "$git_path" -c core.autocrlf=false -c core.safecrlf=false -c diff.renames=false add -A
    if _git_cmd -C "$git_path" -c diff.renames=false diff --staged --quiet; then
        log_ok "aoci 仓与上次发布一致，跳过提交/推送"
        return 0
    fi
    _git_cmd -C "$git_path" -c diff.renames=false diff --staged --shortstat || true
    WEB_DIST_COMMIT_AUTHOR_ARGS=()
    _web_dist_git_commit_author_args "$git_path"
    _git_cmd -C "$git_path" -c core.autocrlf=false -c diff.renames=false "${WEB_DIST_COMMIT_AUTHOR_ARGS[@]}" commit -q -m "$commit_msg" || return 1
    local clean_url auth_url
    clean_url="$(_git_strip_auth_url "$url")"
    auth_url="$(_git_auth_url "$clean_url" "$token")"
    if ! _git_cmd -C "$git_path" push "$auth_url" "HEAD:refs/heads/${branch}"; then
        if ! _git_cmd -C "$git_path" push -u "$auth_url" "HEAD:refs/heads/${branch}"; then
            log_error "推送 kuaigeyun-aoci 失败（请配置 deploy.env 的 AOCI_GIT_TOKEN 或 PRO_GIT_TOKEN）"
            return 1
        fi
    fi
    log_ok "AOCI 已推送 → kuaigeyun-aoci (${branch}) @ $(_git_cmd -C "$git_path" rev-parse --short HEAD)"
}

cmd_ensure_aoci_formal_assets() {
    if aoci_assert_formal_assets_present "$PROJECT_ROOT" 2>/dev/null; then
        return 0
    fi
    if [ "${AOCI_AUTO_SYNC:-1}" = "1" ]; then
        log_warn "工作区缺少 AOCI 正式资产，尝试从 kuaigeyun-aoci 同步…"
        sync_aoci_from_repo || return 1
        return 0
    fi
    log_error "缺少 AOCI 索引。请执行 ./fast-deploy/deploy.sh install-aoci"
    return 1
}
