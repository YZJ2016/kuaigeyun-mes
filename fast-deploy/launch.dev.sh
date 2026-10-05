#!/bin/bash
# RiverEdge SaaS 多组织框架 - 一键启动脚本 (重构稳定版)
# 用法:
#   ./fast-deploy/launch.dev.sh              # 后端 + Worker + PC 前端
#   ./fast-deploy/launch.dev.sh with-h5      # 同上。H5 由本机 HBuilderX 发行，不启动 Expo，不编译 uni-app x
#   ./fast-deploy/launch.dev.sh stop|status|be|fe|me|h5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# 环境参数
BACKEND_PORT=8200
FRONTEND_PORT=8100
# 8081 常落在 Windows Hyper-V 保留段 7998-8097 内，Node 无法 bind；Expo 非交互模式会直接 Skip
MOBILE_PORT=8098
# 旧 Expo 目录：仅用于 kill_expo_mobile_tree 按路径匹配清理历史残留进程；uni-app x 产物不在此目录
MOBILE_APP_DIR="$PROJECT_ROOT/riveredge-app/mobile"
BACKEND_START_TIMEOUT=90
PORT_KILL_MAX_ROUNDS=6
WITH_H5=0

log_info() { echo -e "\033[0;34m[$(date +'%H:%M:%S')] INFO: $1\033[0m"; }
log_warn() { echo -e "\033[1;33m[$(date +'%H:%M:%S')] WARN: $1\033[0m"; }
log_success() { echo -e "\033[0;32m[$(date +'%H:%M:%S')] SUCCESS: $1\033[0m"; }
log_error() { echo -e "\033[0;31m[$(date +'%H:%M:%S')] ERROR: $1\033[0m"; }

is_windows_gitbash() {
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

# Git Bash / Cursor 终端 PATH 常不含 Astral 安装目录（~/.local/bin），
# 交互式 bash 能跑 `uv`，nohup 却报 failed to run command 'uv'。
ensure_uv_path() {
    local p
    for p in \
        "$HOME/.local/bin" \
        "$HOME/.cargo/bin" \
        "${USERPROFILE:-}/.local/bin" \
        "${LOCALAPPDATA:-}/Programs/Python/Python312/Scripts" \
        "${LOCALAPPDATA:-}/Programs/Python/Python313/Scripts"
    do
        if [[ "$p" == [A-Za-z]:* ]] && command -v cygpath >/dev/null 2>&1; then
            p="$(cygpath -u "$p" 2>/dev/null || echo "$p")"
        fi
        [ -d "$p" ] && PATH="$p:$PATH"
    done
    export PATH
}

# 返回可 exec 的绝对路径。Windows 上优先 uv.exe，避免 nohup 找不到无后缀名。
resolve_uv() {
    if [ -n "${RIVEREDGE_UV:-}" ] && [ -x "${RIVEREDGE_UV}" ]; then
        echo "${RIVEREDGE_UV}"
        return 0
    fi
    ensure_uv_path
    local found="" c
    if command -v uv >/dev/null 2>&1; then
        found="$(command -v uv)"
    fi
    for c in \
        "${found}.exe" \
        "$found" \
        "$HOME/.local/bin/uv.exe" \
        "$HOME/.local/bin/uv" \
        "$HOME/.cargo/bin/uv.exe" \
        "$HOME/.cargo/bin/uv"
    do
        [ -n "$c" ] || continue
        [ -x "$c" ] && { echo "$c"; return 0; }
    done
    return 1
}

# Git Bash 常缺 nvm-windows 的 PATH；补齐后再跑 npx vite / expo
ensure_nodejs_path() {
    if command -v node >/dev/null 2>&1 && command -v npx >/dev/null 2>&1; then
        return 0
    fi
    is_windows_gitbash || {
        log_error "未找到 node/npx，请先安装 Node.js 22+"
        return 1
    }
    local nvm_root nvm_link settings win_path unix_path ver best=""
    nvm_root="${NVM_HOME:-${LOCALAPPDATA}/nvm}"
    if [[ "$nvm_root" == [A-Za-z]:* ]] && command -v cygpath >/dev/null 2>&1; then
        nvm_root="$(cygpath -u "$nvm_root")"
    fi
    settings="${nvm_root}/settings.txt"
    if [ -f "$settings" ]; then
        win_path="$(grep -E '^path:' "$settings" 2>/dev/null | head -1 | sed 's/^path:[[:space:]]*//;s/\r$//')"
        if [ -n "$win_path" ] && command -v cygpath >/dev/null 2>&1; then
            unix_path="$(cygpath -u "$win_path" 2>/dev/null || true)"
            [ -n "$unix_path" ] && [ -d "$unix_path" ] && PATH="$unix_path:$PATH"
        fi
        win_path="$(grep -E '^root:' "$settings" 2>/dev/null | head -1 | sed 's/^root:[[:space:]]*//;s/\r$//')"
        if [ -n "$win_path" ] && command -v cygpath >/dev/null 2>&1; then
            unix_path="$(cygpath -u "$win_path" 2>/dev/null || true)"
            [ -n "$unix_path" ] && [ -d "$unix_path" ] && nvm_root="$unix_path"
        fi
    fi
    for nvm_link in \
        "$SCRIPT_DIR/.tools/node" \
        "/c/nvm4w/nodejs" \
        "/d/nvm4w/nodejs" \
        "/c/Program Files/nodejs" \
        "/c/Program Files (x86)/nodejs"
    do
        [ -d "$nvm_link" ] && PATH="$nvm_link:$PATH"
    done
    if [ -d "$nvm_root" ]; then
        for ver in "$nvm_root"/v*; do
            [ -x "$ver/node.exe" ] || [ -x "$ver/node" ] || continue
            best="$ver"
        done
        [ -n "$best" ] && PATH="$best:$PATH"
    fi
    export PATH
    if command -v node >/dev/null 2>&1 && command -v npx >/dev/null 2>&1; then
        log_info "已加载 Node $(node -v | tr -d '\r')（npx $(npx -v 2>/dev/null | tr -d '\r')）"
        return 0
    fi
    log_error "未找到 node/npx。请安装 Node 22+，或用 nvm-windows 安装后执行: nvm use 22"
    log_error "也可把 Node 目录加入用户 PATH 后重开终端（常见: %LOCALAPPDATA%\\nvm\\v22.x.x）"
    return 1
}

# Windows: 直接对端口监听者 Stop-Process（不依赖 Git Bash 能否 tasklist 到 PID）
powershell_stop_port_listeners() {
    local port=$1
    command -v powershell.exe >/dev/null 2>&1 || return 0
    powershell.exe -NoProfile -Command "
        \$port = ${port}
        \$pids = @(
            Get-NetTCPConnection -LocalPort \$port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique |
                Where-Object { \$_ -gt 0 }
        )
        foreach (\$pid in \$pids) {
            Stop-Process -Id \$pid -Force -ErrorAction SilentlyContinue
            cmd /c \"taskkill /F /PID \$pid /T\" 2>\$null | Out-Null
        }
    " 2>/dev/null || true
}

get_listening_pids_raw() {
    local port=$1
    if command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -Command "
            Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue |
              Select-Object -ExpandProperty OwningProcess -Unique |
              Where-Object { \$_ -gt 0 }
        " 2>/dev/null | tr -d '\r' | sort -u | grep -E '^[0-9]+$' || true
    elif command -v lsof >/dev/null 2>&1; then
        # macOS / Linux：netstat -ano 是 Windows 输出格式，Unix 上恒为空，须用 lsof
        lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u | grep -E '^[0-9]+$' || true
    else
        netstat -ano 2>/dev/null \
            | grep LISTENING \
            | grep -E "[:.]${port}[[:space:]]" \
            | awk '{print $NF}' \
            | sort -u \
            | grep -E '^[0-9]+$' || true
    fi
}

# 状态展示用：仅返回仍存活的 PID
get_listening_pids() {
    local port=$1
    local alive=""
    local pid
    for pid in $(get_listening_pids_raw "$port"); do
        pid_is_alive "$pid" && alive="${alive}${pid} "
    done
    echo "$alive" | xargs 2>/dev/null || true
}

backend_http_ready() {
    curl -sf --connect-timeout 1 --max-time 1 "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1
}

backend_port_ready() {
    [ -n "$(get_listening_pids_raw "${BACKEND_PORT}")" ]
}

check_port() {
    backend_http_ready
}

pid_is_alive() {
    local pid=$1
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null && return 0
    tasklist.exe //FI "PID eq $pid" 2>/dev/null | grep -q "$pid" && return 0
    return 1
}

graceful_kill_pid() {
    local pid=$1
    [ -z "$pid" ] && return 0
    pid_is_alive "$pid" || return 0
    kill -INT "$pid" 2>/dev/null || taskkill.exe //PID "$pid" //T 2>/dev/null || true
    sleep 3
    if pid_is_alive "$pid"; then
        taskkill.exe //F //PID "$pid" //T 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
}

kill_pids() {
    local pids=$1
    local pid
    for pid in $pids; do
        [ -n "$pid" ] || continue
        kill -INT "$pid" 2>/dev/null || taskkill.exe //PID "$pid" 2>/dev/null || true
    done
    sleep 2
    for pid in $pids; do
        [ -n "$pid" ] || continue
        taskkill.exe //F //PID "$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    done
    sleep 1
}

kill_port() {
    local port=$1
    local skip_uvicorn_tree_kill=${2:-0}
    local round=0
    local pids

    while [ "$round" -lt "$PORT_KILL_MAX_ROUNDS" ]; do
        if [ "$port" = "${BACKEND_PORT}" ] && [ "$skip_uvicorn_tree_kill" != "1" ]; then
            kill_uvicorn_reload_tree "${BACKEND_PORT}"
        fi
        powershell_stop_port_listeners "$port"
        pids="$(get_listening_pids_raw "$port")"
        alive_pids=""
        for pid in $pids; do
            pid_is_alive "$pid" && alive_pids="${alive_pids}${pid} "
        done
        if [ -n "$alive_pids" ]; then
            log_warn "清理端口 $port（第 $((round + 1)) 轮）: ${alive_pids}"
            kill_pids "$alive_pids"
        fi
        if [ "$port" = "${BACKEND_PORT}" ]; then
            # /health 挂了但端口仍被僵尸进程占用时不能算清完，否则新实例 bind 失败
            if ! backend_http_ready && [ -z "$(get_listening_pids_raw "$port")" ]; then
                return 0
            fi
        else
            [ -z "$(get_listening_pids_raw "$port")" ] && return 0
        fi
        round=$((round + 1))
        sleep 1
    done

    if [ "$port" = "${BACKEND_PORT}" ]; then
        backend_http_ready && { log_error "端口 $port 仍被占用（HTTP /health 可访问）"; return 1; }
        pids="$(get_listening_pids_raw "$port")"
        [ -n "$pids" ] && { log_error "端口 $port 仍有监听: $pids"; return 1; }
        return 0
    fi
    pids="$(get_listening_pids_raw "$port")"
    if [ -n "$pids" ]; then
        log_error "端口 $port 仍有监听: $pids"
        return 1
    fi
}

# Windows：清理 uvicorn --reload 整棵树（reloader + spawn_main worker + 后台 bash 启动器）
# TCP OwningProcess 常为已退出的 reloader 幽灵 PID，杀它无效；须杀 worker 与启动 shell。
kill_uvicorn_reload_tree() {
    local port=$1
    command -v powershell.exe >/dev/null 2>&1 || return 0
    powershell.exe -NoProfile -Command "
        \$port = '${port}'
        \$killed = @()

        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
            \$cmd = \$_.CommandLine
            if (-not \$cmd) { return }
            \$id = \$_.ProcessId
            \$name = \$_.Name
            \$shouldKill = \$false

            # reload worker（真正处理 HTTP 的 spawn 子进程）
            if (\$cmd -match 'multiprocessing\.spawn import spawn_main') {
                \$shouldKill = \$true
            }

            # python / uv 本体上的 uvicorn（排除 bash/powershell/wmic 包装命令）
            if (-not \$shouldKill -and \$name -match '^(python|uv|uvicorn)(\.exe)?$') {
                if ((\$cmd -match 'server\.main:app') -and (\$cmd -match ('--port[\s=]' + \$port))) {
                    \$shouldKill = \$true
                }
            }

            # 直接启动后端的 bash（含 Cursor 后台终端；排除 Agent 工具包装）
            if (-not \$shouldKill -and \$name -match 'bash') {
                if ((\$cmd -match 'riveredge-backend') -and (\$cmd -match 'uv run.*uvicorn.*server\.main:app') -and (\$cmd -match ('--port[\s=]' + \$port)) -and (\$cmd -notmatch 'CURSOR_STATE_INPUT_FILE')) {
                    \$shouldKill = \$true
                }
            }

            if (\$shouldKill) {
                Stop-Process -Id \$id -Force -ErrorAction SilentlyContinue
                \$killed += \$id
            }
        }

        if (\$killed.Count -gt 0) {
            Write-Output ('killed: ' + (\$killed -join ', '))
        }
    " 2>/dev/null || true
    sleep 2
}

kill_backend_by_command_line() {
    kill_uvicorn_reload_tree "${BACKEND_PORT}"
}

# Windows：清理 Expo / Metro 整棵树（mobile.pid 仅为 nohup bash，8081 监听常在 node 子进程）
kill_expo_mobile_tree() {
    command -v powershell.exe >/dev/null 2>&1 || return 0
    powershell_stop_port_listeners "${MOBILE_PORT}"
    local mobile_dir_ps
    mobile_dir_ps="${MOBILE_APP_DIR//\\/\\\\}"
    powershell.exe -NoProfile -Command "
        \$mobilePath = '${mobile_dir_ps}'.Replace('/', [char]92)
        \$mobilePort = '${MOBILE_PORT}'
        \$killed = @()
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
            \$cmd = \$_.CommandLine
            if (-not \$cmd) { return }
            \$id = \$_.ProcessId
            \$name = \$_.Name
            \$shouldKill = \$false

            if (\$cmd -like \"*\$mobilePath*\" -and (\$cmd -match 'expo|@expo/cli|metro|react-native')) {
                \$shouldKill = \$true
            }
            if (-not \$shouldKill -and \$name -match '^(node|npm)(\.exe)?$') {
                if (\$cmd -match '@expo/cli|\\\\expo\\\\|metro|react-native') {
                    if ((\$cmd -match 'expo start') -or (\$cmd -match ('--port[\\s=]' + \$mobilePort)) -or (\$cmd -like \"*\$mobilePath*\")) {
                        \$shouldKill = \$true
                    }
                }
            }
            if (-not \$shouldKill -and \$name -match 'bash') {
                if ((\$cmd -match 'expo start|npx expo') -and ((\$cmd -match 'riveredge-app[\\\\/]mobile') -or (\$cmd -match ('--port[\\s=]' + \$mobilePort)))) {
                    \$shouldKill = \$true
                }
            }

            if (\$shouldKill) {
                Stop-Process -Id \$id -Force -ErrorAction SilentlyContinue
                cmd /c \"taskkill /F /PID \$id /T\" 2>\$null | Out-Null
                \$killed += \$id
            }
        }
        if (\$killed.Count -gt 0) {
            Write-Output ('killed expo: ' + (\$killed -join ', '))
        }
    " 2>/dev/null || true
    sleep 2
}

# Windows：清理 taskiq worker / scheduler 整棵树（uv run / taskiq.exe 会 fork，仅杀 pidfile 会残留占 PG 连接的子进程）
kill_taskiq_processes() {
    if ! command -v powershell.exe >/dev/null 2>&1; then
        # macOS / Linux：按命令行匹配 taskiq worker/scheduler（uv run 启动器与 python 子进程均含此串）
        pkill -INT -f 'core\.tasks\.taskiq_app:(broker|scheduler)' 2>/dev/null || true
        sleep 2
        pkill -KILL -f 'core\.tasks\.taskiq_app:(broker|scheduler)' 2>/dev/null || true
        return 0
    fi
    local round=0
    while [ "$round" -lt 3 ]; do
        local killed
        killed="$(powershell.exe -NoProfile -Command "
            \$killed = @()
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
                \$cmd = \$_.CommandLine
                if (-not \$cmd) { return }
                \$id = \$_.ProcessId
                \$name = \$_.Name
                \$shouldKill = \$false

                # taskiq.exe / taskiq worker|scheduler（Windows 命令行常为 taskiq.exe\" worker ...）
                if (\$cmd -match 'core\.tasks\.taskiq_app:(broker|scheduler)') {
                    \$shouldKill = \$true
                }
                if (-not \$shouldKill -and \$cmd -match 'taskiq(\.exe)?[\"'']?\s+(worker|scheduler)') {
                    \$shouldKill = \$true
                }
                if (-not \$shouldKill -and \$name -match '^(python|uv|nohup)(\.exe)?$') {
                    if ((\$cmd -match 'riveredge-backend') -and (\$cmd -match 'taskiq (worker|scheduler)')) {
                        \$shouldKill = \$true
                    }
                }
                if (-not \$shouldKill -and \$name -match 'bash') {
                    if ((\$cmd -match 'riveredge-backend') -and (\$cmd -match 'taskiq (worker|scheduler)')) {
                        \$shouldKill = \$true
                    }
                }

                if (\$shouldKill) {
                    \$killed += \$id
                }
            }
            \$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
            \$ids = [System.Collections.Generic.HashSet[int]]::new()
            foreach (\$id in \$killed) { [void]\$ids.Add([int]\$id) }
            \$changed = \$true
            while (\$changed) {
                \$changed = \$false
                foreach (\$p in \$procs) {
                    if (\$ids.Contains([int]\$p.ParentProcessId) -and -not \$ids.Contains([int]\$p.ProcessId)) {
                        [void]\$ids.Add([int]\$p.ProcessId)
                        \$changed = \$true
                    }
                }
            }
            foreach (\$p in \$procs) {
                if (-not \$p.CommandLine) { continue }
                if (\$p.CommandLine -notmatch 'from multiprocessing\.spawn import spawn_main') { continue }
                if (\$p.CommandLine -notmatch 'parent_pid=(\d+)') { continue }
                \$pp = [int]\$Matches[1]
                \$parent = \$null
                foreach (\$c in \$procs) { if ([int]\$c.ProcessId -eq \$pp) { \$parent = \$c; break } }
                \$parentIsTaskiq = \$false
                if (\$parent -and \$parent.CommandLine -and (\$parent.CommandLine -match 'taskiq')) { \$parentIsTaskiq = \$true }
                if (\$ids.Contains(\$pp) -or \$parentIsTaskiq -or (-not \$parent)) {
                    [void]\$ids.Add([int]\$p.ProcessId)
                }
            }
            foreach (\$id in \$ids) {
                Stop-Process -Id \$id -Force -ErrorAction SilentlyContinue
            }
            if (\$ids.Count -gt 0) { Write-Output ((\$ids | Sort-Object) -join ', ') }
        " 2>/dev/null | tr -d '\r' || true)"
        if [ -n "$killed" ]; then
            log_warn "清理 taskiq 残留进程（第 $((round + 1)) 轮）: ${killed}"
        else
            break
        fi
        round=$((round + 1))
        sleep 2
    done
    sleep 1
}

taskiq_service_running() {
    local token=$1
    if command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -Command "
            \$found = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { \$_.CommandLine -and (\$_.CommandLine -match 'core\.tasks\.taskiq_app:${token}') }
            if (\$found) { exit 0 } else { exit 1 }
        " >/dev/null 2>&1
    else
        pgrep -f "core\.tasks\.taskiq_app:${token}" >/dev/null 2>&1
    fi
}

cleanup_backend_processes() {
    log_info "清理后端进程 (port ${BACKEND_PORT})..."

    if [ -f ".logs/backend.pid" ]; then
        local pid
        pid="$(cat .logs/backend.pid 2>/dev/null)"
        [ -n "$pid" ] && graceful_kill_pid "$pid"
        rm -f .logs/backend.pid
    fi

    kill_backend_by_command_line
    kill_port "${BACKEND_PORT}" 1 || {
        log_error "8200 仍被占用。若 Cursor 里还有后台 uvicorn 终端，请手动关闭后重试。"
        return 1
    }
}

start_backend() {
    local skip_cleanup=${1:-0}
    local uv_bin
    uv_bin="$(resolve_uv)" || {
        log_error "未找到 uv（Astral 默认装在 ~/.local/bin，当前 PATH 不含该目录）"
        log_error "安装: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""
        return 1
    }
    log_info "正在拉起后端 (${BACKEND_PORT})..."
    if [ "$skip_cleanup" != "1" ]; then
        cleanup_backend_processes || { log_error "后端端口未释放，拒绝启动"; return 1; }
    elif backend_http_ready || backend_port_ready; then
        log_error "8200 仍被占用，请先结束其他终端的 uvicorn 后重试"
        return 1
    fi

    cd riveredge-backend
    export MENU_CACHE_ENABLED="${MENU_CACHE_ENABLED:-true}"
    export RIVEREDGE_DB_POOL_MIN="${RIVEREDGE_DB_POOL_MIN:-1}"
    export RIVEREDGE_DB_POOL_MAX="${RIVEREDGE_DB_POOL_MAX:-5}"
    PYTHONPATH="src" nohup "$uv_bin" run --extra ocr --extra pdf python scripts/run_dev_server.py > ../.logs/backend.log 2>&1 &
    local backend_launcher_pid=$!
    echo "${backend_launcher_pid}" > ../.logs/backend.pid
    cd ..

    local retries=0
    local ready_mode=""
    while [ "$retries" -lt "$BACKEND_START_TIMEOUT" ]; do
        if backend_http_ready; then
            ready_mode="health"
            break
        fi
        if backend_port_ready; then
            ready_mode="port"
            break
        fi
        if ! pid_is_alive "${backend_launcher_pid}"; then
            log_error "后端进程已退出，请查看 .logs/backend.log"
            return 1
        fi
        sleep 1
        retries=$((retries + 1))
    done
    if [ -z "${ready_mode}" ]; then
        log_error "后端启动超时 (${BACKEND_START_TIMEOUT}s)，请查看 .logs/backend.log"
        return 1
    fi

    local listeners
    listeners="$(get_listening_pids "${BACKEND_PORT}" | tr '\n' ' ')"
    if [ "${ready_mode}" = "health" ]; then
        log_success "后端就绪! (监听 PID: ${listeners:-unknown})"
    else
        log_success "后端已监听，健康检查将很快可用! (监听 PID: ${listeners:-unknown})"
    fi
}

start_worker() {
    local uv_bin
    uv_bin="$(resolve_uv)" || {
        log_error "未找到 uv，无法启动 Taskiq"
        return 1
    }
    log_info "正在拉起 Taskiq Worker/Scheduler..."
    kill_taskiq_processes
    cd riveredge-backend
    [ -f "../.logs/worker.pid" ] && rm -f "../.logs/worker.pid"
    # 开发环境默认 1 worker，避免 API reload + 多 worker 占满 PostgreSQL max_connections
    TASKIQ_WORKERS="${TASKIQ_WORKERS:-1}"
    export RIVEREDGE_TASKIQ_POOL_MIN="${RIVEREDGE_TASKIQ_POOL_MIN:-1}"
    export RIVEREDGE_TASKIQ_POOL_MAX="${RIVEREDGE_TASKIQ_POOL_MAX:-2}"
    PYTHONPATH="src" nohup "$uv_bin" run --extra ocr --extra pdf taskiq worker \
        --app-dir src \
        --workers "$TASKIQ_WORKERS" \
        core.tasks.taskiq_app:broker \
        core.tasks.taskiq_app \
        core.tasks.ai_tasks \
        core.tasks.worker_bootstrap \
        core.tasks.data_backup_handlers > ../.logs/worker.log 2>&1 &
    echo $! > ../.logs/worker.pid
    local worker_launcher_pid=$!

    [ -f "../.logs/scheduler.pid" ] && rm -f "../.logs/scheduler.pid"
    PYTHONPATH="src" nohup "$uv_bin" run --extra ocr --extra pdf taskiq scheduler \
        --app-dir src \
        core.tasks.taskiq_app:scheduler \
        core.tasks.taskiq_app > ../.logs/scheduler.log 2>&1 &
    echo $! > ../.logs/scheduler.pid
    local scheduler_launcher_pid=$!

    sleep 5
    if ! taskiq_service_running broker; then
        cd ..
        log_error "Taskiq Worker 启动失败，请查看 .logs/worker.log"
        return 1
    fi
    if ! taskiq_service_running scheduler; then
        cd ..
        log_error "Taskiq Scheduler 启动失败，请查看 .logs/scheduler.log"
        return 1
    fi
    cd ..
    log_success "Taskiq 异步引擎已就绪!"
}

# 前端不能只清端口：vite 默认遇占用会悄悄换端口（strictPort 未开时漂到 8101+），
# 且旧实例可能端口检测不到，须连 pidfile 一起杀
stop_frontend() {
    if [ -f ".logs/frontend.pid" ]; then
        local pid
        pid="$(cat .logs/frontend.pid 2>/dev/null)"
        [ -n "$pid" ] && graceful_kill_pid "$pid"
        rm -f .logs/frontend.pid
    fi
    kill_port "${FRONTEND_PORT}" || true
}

start_frontend() {
    ensure_nodejs_path || return 1
    log_info "正在拉起前端 (${FRONTEND_PORT})..."
    stop_frontend
    cd riveredge-frontend
    export VITE_BACKEND_HOST="${VITE_BACKEND_HOST:-127.0.0.1}"
    export VITE_BACKEND_PORT="${VITE_BACKEND_PORT:-${BACKEND_PORT}}"
    nohup npx vite --port "${FRONTEND_PORT}" --strictPort --host 0.0.0.0 > ../.logs/frontend.log 2>&1 &
    echo $! > ../.logs/frontend.pid
    cd ..

    local retries=0
    while [ "$retries" -lt 15 ]; do
        if [ -n "$(get_listening_pids_raw "${FRONTEND_PORT}")" ]; then
            log_success "前端已挂起!"
            return 0
        fi
        if ! pid_is_alive "$(cat .logs/frontend.pid 2>/dev/null)"; then
            log_error "前端进程已退出，请查看 .logs/frontend.log"
            return 1
        fi
        sleep 1
        retries=$((retries + 1))
    done
    log_error "前端 ${FRONTEND_PORT} 未监听，请查看 .logs/frontend.log"
    return 1
}

note_h5_hbuilderx() {
    log_info "H5 由本机 HBuilderX 发行。本脚本不要求 riveredge-app/mobile/package.json，不启动 Expo，也不编译 uni-app x。"
    log_info "发行 Web 后，产物在 kuaigeyun-client/riveredge-app-mobile/unpackage/dist/build/web。"
}

stop_mobile() {
    if [ -f ".logs/mobile.pid" ]; then
        local pid
        pid="$(cat .logs/mobile.pid 2>/dev/null)"
        [ -n "$pid" ] && graceful_kill_pid "$pid"
        rm -f .logs/mobile.pid
    fi
    kill_expo_mobile_tree
    kill_port "${MOBILE_PORT}" || true
}

stop_all() {
    log_info "停止所有服务..."
    for pidfile in .logs/worker.pid .logs/scheduler.pid; do
        if [ -f "$pidfile" ]; then
            local pid
            pid="$(cat "$pidfile")"
            graceful_kill_pid "$pid"
            rm -f "$pidfile"
        fi
    done
    kill_taskiq_processes
    cleanup_backend_processes || log_warn "后端清理未完全成功，请检查 .logs/backend.log"
    stop_frontend
    stop_mobile
}

frontend_http_ready() {
    curl -sf --max-time 2 "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1
}

pidfile_alive() {
    local pidfile=$1
    [ -f "$pidfile" ] || return 1
    local pid
    pid="$(cat "$pidfile" 2>/dev/null)"
    [ -n "$pid" ] || return 1
    pid_is_alive "$pid"
}

# 解析 with-h5（可与子命令组合，如: with-h5 status 无效；仅全量启动时生效）
CMD=""
for arg in "$@"; do
    case "$arg" in
        with-h5|withh5|with5|--with-h5)
            WITH_H5=1
            ;;
        stop|status|be|fe|me|h5)
            CMD="$arg"
            ;;
        "")
            ;;
        *)
            if [ -z "$CMD" ]; then
                CMD="$arg"
            else
                log_error "未知参数: $arg"
                echo "用法: ./fast-deploy/launch.dev.sh [with-h5] [stop|status|be|fe|me|h5]"
                exit 1
            fi
            ;;
    esac
done

case "$CMD" in
    stop) stop_all ;;
    status)
        backend_http_ready && log_success "Backend [OK] ($(get_listening_pids "${BACKEND_PORT}" | tr '\n' ' '))" || log_warn "Backend [OFF]"
        frontend_http_ready && log_success "Frontend [OK]" || log_warn "Frontend [OFF]"
        log_info "Mobile H5 由本机 HBuilderX 发行，本脚本不启动 Expo，也不编译 uni-app x"
        if pidfile_alive ".logs/worker.pid" || taskiq_service_running broker; then
            log_success "Worker [OK]"
        else
            log_warn "Worker [OFF]"
        fi
        if pidfile_alive ".logs/scheduler.pid" || taskiq_service_running scheduler; then
            log_success "Scheduler [OK]"
        else
            log_warn "Scheduler [OFF]"
        fi
        ;;
    be) start_backend ;;
    fe) start_frontend ;;
    me|h5)
        note_h5_hbuilderx
        ;;
    "")
        mkdir -p .logs
        stop_all
        # 前端必须先起：Vite 只做反向代理，不依赖后端就绪。
        # 若排在 start_backend（最长等 90s health）+ start_worker 之后，前端会离线约 2 分钟，
        # 期间浏览器里的 @vite/client 进入 "server connection lost. Polling for restart..."，
        # 并在 Vite 回来的那一秒执行 location.reload() —— 表现为「系统开着好一会儿后页面自己刷一下」。
        if start_frontend && start_backend 1 && start_worker; then
            if [ "$WITH_H5" = "1" ]; then
                note_h5_hbuilderx
            fi
            log_success "🚀 RiverEdge 系统已恢复就绪!"
            echo "  - Web: http://127.0.0.1:${FRONTEND_PORT} / http://localhost:${FRONTEND_PORT}"
            echo "  - API: http://127.0.0.1:${BACKEND_PORT} / http://localhost:${BACKEND_PORT}"
            if [ "$WITH_H5" = "1" ]; then
                echo "  - Mobile H5: 由本机 HBuilderX 发行，本脚本不启动 Expo，也不编译 uni-app x"
            fi
            echo "  - 局域网用本机 IP 替换主机名（前后端均监听 0.0.0.0）"
            if [ "$WITH_H5" != "1" ]; then
                echo "  - 提示: with-h5 不启动手机 Expo。H5 由本机 HBuilderX 发行"
            fi
        else
            log_error "启动未完成，请查看 .logs/backend.log / .logs/frontend.log"
            exit 1
        fi
        ;;
    *)
        log_error "未知命令: $CMD"
        echo "用法: ./fast-deploy/launch.dev.sh [with-h5] [stop|status|be|fe|me|h5]"
        exit 1
        ;;
esac
