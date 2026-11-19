---
title: fast-deploy 脚本入口（构建 / 部署）
slug: fast-deploy-scripts
status: delivered
domain: deploy
when: 构建前端 dist、本机起停、生产更新、H5、compose 专业包、要不要编前端
keywords:
  - fast-deploy
  - deploy.sh
  - dist不入库
  - 部署机构建
  - deploy.sh
  - launch.dev.sh
  - cmd_ensure_frontend_dist
  - npm run build
  - 没改前端
  - install-service
  - 开机自启
  - SERVICE_USER
standard: dist 不入库；推送只有源码 commit+push；PC 前端由部署机 deploy.sh update 时现构建；本机验证用 deploy.sh build
---

# fast-deploy 脚本入口（构建 / 部署）

- 日期：2026-10-03；分流澄清：2026-10-10；**dist 出库重构：2026-11-19**
- 状态：已交付（文档化，供后续构建一律走脚本）
- ⚠️ 2026-11-19 起：`riveredge-frontend/dist` 不再入库，`build.web.sh`/`build_web_git.sh` 已删除，历史不再被 filter-repo 改写

## 目标

主仓所有「构建前端、本机起停、生产更新」只走 `fast-deploy/` 现有脚本。  
`riveredge-frontend/dist` **不入库**：任何推送只有源码；PC 前端在部署机 `deploy.sh update/start` 时 `npm run build` 现构建。

## 何时读 / 禁止另起

- 何时读：本机/部署机构建 PC dist、部署机更新、H5、pro-apps、本机起停
- 禁止：把 `riveredge-frontend/dist` 提交进 git；平行 `npm run build` 后手写 commit/push dist；对 develop 擅自 `--force`；新步骤另起顶层脚本

## 标准入口

| 场景 | 命令 | 说明 |
|------|------|------|
| 任何源码推送（含 PC 前端） | `git push` | dist 不入库，无构建步骤 |
| 部署机构建 dist | `./fast-deploy/deploy.sh update`（prod） | `cmd_ensure_frontend_dist` → `cmd_build`：`npm run build` 现构建 + 预压缩 |
| 本机构建/验证 dist | `./fast-deploy/deploy.sh build` 或 `cd riveredge-frontend && npm run build` | 产物留在工作区，**勿提交** |
| 移动端 H5 本地构建 | `./fast-deploy/build.mobile.web.sh` | `riveredge-app/mobile` → `web-dist`，默认不进主仓 |
| 部署机装 H5 | `./fast-deploy/deploy.sh install-h5` | 拉 `kuaigeyun-client`，Caddy `/mobile` |
| 统一部署向导 | `./fast-deploy/deploy.sh` / `dev` / `wizard` | check/install/configure/migrate/build/start/stop/status/update |
| 生产开机自启 | `./fast-deploy/deploy.sh install-service`（向导 BOOT） | 非 root；用户解析见下；缺 uv 自动装到服务用户 home |
| 本机开发起停 | `./fast-deploy/launch.dev.sh`（`with-h5` / `stop` / `status`） | 不走蓝绿；需蓝绿用 `deploy.sh dev` |
| Windows PS 起停 | `.\fast-deploy\launch.dev.ps1 withh5` | **勿**在 PS 里直接 `.\launch.dev.sh`（会另开 git-bash、无输出）；手机口 **8098** |
| 专业/定制组装 | `python fast-deploy/tools/workspace/compose.py` | 或 `deploy.sh pro-apps` |
| Linux 薄封装 | `linux/dev.sh` / `linux/prod.sh` | 设 `DEPLOY_MODE` 后 `fd_dispatch` |
| Windows PS | `windows/dev.ps1` / `windows/prod.ps1` | 逻辑在 `lib/common.ps1` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 入口说明 | `fast-deploy/README.md` |
| 部署总入口 | `fast-deploy/deploy.sh` → `lib/common.sh` `fd_dispatch` |
| 部署机构建 dist | `cmd_ensure_frontend_dist` → `cmd_build`（`common.sh`，每次 update 现构建） |
| PS 对等实现 | `lib/common.ps1` `Invoke-Build` / `Ensure-FrontendDist` |
| 蓝绿 | `lib/blue_green.sh` / `blue_green.ps1` |
| 向导 | `lib/wizard.sh` |
| 移动 H5 | `build.mobile.web.sh`；`cmd_install_client_repo` |
| 配置样例 | `fast-deploy/config/deploy.env.example` |
| Caddy 模板 | `fast-deploy/templates/Caddyfile.template` |

## 构建链路（PC Web）

1. 源码照常 AOCI 对齐 → commit → `git push`（无 dist、无构建步骤）
2. 部署机：`git pull` → `deploy.sh update` → `cmd_ensure_frontend_dist` 每次执行 `npm run build`（`NODE_BUILD_MEM` 默认 4096MB）→ `precompress_web_dist` 现生成 `.gz/.br`
3. 本机调试/验证：`deploy.sh build` 或 `npm run build`，产物留在 `riveredge-frontend/dist`（已 gitignore）

历史包袱：`build.web.sh` 曾用 git-filter-repo 剥离历史 dist 并 force-push，导致 develop 周期性整条链哈希改写（新旧链分叉）。该流程已随 dist 出库一并移除。

## 扩展点

- 新部署步骤：挂 `fd_dispatch` / `KNOWN_CMDS`
- 新前端产物检查：与 `cmd_ensure_frontend_dist`（须含 `login.html`）对齐
- H5 / 专业包：分别走 `install-h5` 与 `compose.py`

## 开机自启（Linux systemd）

- 运行用户优先级：`deploy.env` 的 `SERVICE_USER` → `SUDO_USER` → 当前用户 → `$PROJECT_ROOT` 属主 → **已安装 unit 的 `User=`**；**禁止** `User=root`。root 直登且目录属主也是 root 时，脚本会读 `/etc/systemd/system/riveredge-backend.service` 并写回 `SERVICE_USER`；仍失败则须人工写入 `SERVICE_USER`。
- `prepare_systemd_prerequisites`：服务用户无 uv 时 `ensure_uv_for_user` 自动 pip/官方脚本装到其 `~/.local/bin`，勿把 root 的 uv 写进 unit
- 向导 BOOT 菜单展示运行用户、uv/caddy 就绪态；失败信息含可复制手装命令
- **203/EXEC**：`check_systemd_exec_scripts` 纳入 `deploy.sh check`；`ensure_systemd_exec_scripts_ready` 在 `install-service` / `start_prod_via_systemd` / `fix_systemd_runtime_permissions` 去 CRLF + `chmod +x`；仓库侧 `linux/.gitattributes` + `100755`
- 真源：`lib/common.sh` 的 `resolve_service_user` / `ensure_uv_for_user` / `ensure_systemd_exec_scripts_ready` / `cmd_install_service`

## 踩坑

- `journalctl` 报 `deploy.env: Permission denied` 且 `riveredge-backend` 重启计数狂涨：服务用户读不到 `fast-deploy/config/deploy.env`（常见 root 编辑后 `chmod 600`）。`fix_systemd_runtime_permissions` 会 chown 配置目录与 `deploy.env`；`install-service` / systemd `start` 启动前会跑。应急：`sudo ./fast-deploy/deploy.sh install-service` 或手动 `chown` 给 `SERVICE_USER`。
- `journalctl` 报 `status=203/EXEC` + `Permission denied`：包装脚本无 +x 或含 `\r`（Windows 检出）。先 `./fast-deploy/deploy.sh check`，再 `install-service` / `start`（会自动 `ensure_systemd_exec_scripts_ready`）。
- PowerShell 执行 `.\fast-deploy\launch.dev.sh`：Windows 把 `.sh` 关联到 `git-bash.exe`，Cursor 终端无日志、exit 0，手机端未起。改用 `.\fast-deploy\launch.dev.ps1 withh5` 或 Git Bash。
- 手机 H5 开发口默认 **8098**，不是 8081（Hyper-V 保留段）。
- **正式 AOCI 资产**（`aoci.txt` / `aoci.*.txt` / 放行的 `.aoci/config.json` 等）应随业务变更提交，勿故意排除；`.aoci` 下 lock/ledger/batch 助手文件仍勿提交（见 `.cursor/rules/aoci-git-commit.mdc`）
- 跟踪远程以 `@{upstream}` 为准，勿写死 origin
- 推送 HTTPS 用组织令牌 `oauth2:<token>`
- `cmd_build` 用 `npm run build`
- 阿里云 PyPI 偶发对 `uv.lock` hash 路径 `.whl.metadata` 404（如 `python-dotenv`）：`uv_sync_backend_with_fallback` 回退清华/官方，**成功源须写回父进程 `UV_INDEX_URL`**（勿在子 shell 里 export）；迁移用 `uv run --no-sync aerich upgrade` 禁止二次拉包。仍可显式 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/`

## 关联

- `principles/reuse-existing-patterns.md`
- `fast-deploy/README.md`
- Vault SOP：`E:\AI-Memory\30-Knowledge\MES-Codebase\web-build-push-sop.md`
- Vault 决策：`E:\AI-Memory\40-Decisions\2026-09-27-web-build-push-flow.md`
