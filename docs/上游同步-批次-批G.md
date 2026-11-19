# 上游同步·批G deploy/ops/仓库治理/造数收尾

> 数据源：handoff-01 附录批次圈定 + `上游同步台账.md` 判定 + 本地 `同步上游:*` 提交映射（每轮同步后可重生成）。
> 状态：✅已摘/已评（附本地 hash 或台账方式）｜🟡缓置（备注=领回条件）｜⬜未评（候选队列）｜⏭跳过。
> 返回：[批次总表](上游同步-批次总表.md)（各批次总览数字）

共 **59** 笔：✅0 ｜ 🟡0 ｜ ⬜59 ｜ ⏭0

| 上游 | 主题 | 状态 | 备注 |
|---|---|---|---|
| `c7fa35d334` | chore: 依赖口径清理与看板图表懒加载韧性 | ⬜未评 |  |
| `2c2c2c6848` | chore(aoci): 修复合并冲突残留并补齐合入侧索引 | ⬜未评 |  |
| `54fec48d47` | chore: workspace compose 同步与 PLM/福尼特更新日志 | ⬜未评 |  |
| `2182a09f88` | chore(aoci): 合入后补齐 missing/stale 索引 | ⬜未评 |  |
| `41fcf29a17` | fix: 修复 platformUpdateLog 合并残留多余大括号 | ⬜未评 |  |
| `77448fd970` | chore: 流程造数与设备运维造数移出仓库（本机保留） | ⬜未评 |  |
| `3ab10aefc2` | docs: 推送 SOP 按分流重写，死代码自检降为可选 | ⬜未评 |  |
| `992f191c27` | chore(fast-deploy): legacy 主仓 dist 提交使用 git a | ⬜未评 |  |
| `f978467013` | improve(fast-deploy): 生产向导可选 dist 拉取或本机构建 | ⬜未评 |  |
| `577b7cad81` | improve(fast-deploy): 向导一步三选一并通用化文案 | ⬜未评 |  |
| `8c4db8cdad` | fix(fast-deploy): dist 仓 commit 继承主仓作者并支持跳过 n | ⬜未评 |  |
| `76fcb4cfea` | chore(aoci): 主仓停止跟踪 .aoci 治理 JSON | ⬜未评 |  |
| `90f3593703` | chore(repo): 收窄 Git 跟踪范围并加索引漂移扫描 | ⬜未评 |  |
| `5c313c150c` | chore(aoci): 主仓完全停止跟踪 .aoci 目录 | ⬜未评 |  |
| `1bca62aecf` | chore(repo): 主仓停止跟踪 .cursor、AGENTS.md、.gitatt | ⬜未评 |  |
| `310daba2bf` | chore(fast-deploy): AOCI 仓同步 AGENTS/.cursor 与 | ⬜未评 |  |
| `c91b13c20c` | docs: 更新微信群截图素材 | ⬜未评 |  |
| `09300569ac` | feat(fast-deploy): 适配 CTyunOS/openEuler 系安装与 | ⬜未评 |  |
| `521f06b72f` | fix(fast-deploy): CTyunOS 上 Caddy 改走官方静态包 | ⬜未评 |  |
| `e1650484c4` | fix(fast-deploy): Caddy 静态包优先国内镜像下载 | ⬜未评 |  |
| `995b74b491` | fix(deploy): Windows 按用户安装 Node 后环境检测可识别 | ⬜未评 |  |
| `f0f05414c6` | fix(deploy): Windows uv sync 预装 Python 3.11 并 | ⬜未评 |  |
| `47cb9831a8` | docs: 对齐分仓推送 SOP 与 push.sh 默认行为 | ⬜未评 |  |
| `bf97d3a44a` | chore(docs): 更新微信群截图并停止跟踪内部文档 | ⬜未评 |  |
| `ffa55326df` | docs: 记录移动端登录鉴权回退到 10-31 | ⬜未评 |  |
| `9093398b50` | fix(deploy): 一般模式恢复蓝绿，低配关闭蓝绿 | ⬜未评 |  |
| `0368c115f6` | fix(deploy): 一般模式 update 默认蓝绿（含运维台非交互） | ⬜未评 |  |
| `99c960026c` | fix(fast-deploy): repair Windows dependency i | ⬜未评 |  |
| `34b1a1d3ed` | fix(fast-deploy): Windows uv detection and Ca | ⬜未评 |  |
| `5f9690fc5f` | fix(fast-deploy): avoid PowerShell $args shad | ⬜未评 |  |
| `27552972c4` | fix(deploy): Ubuntu 无 pip 时装 uv 与 LOCALAPPDAT | ⬜未评 |  |
| `d827731540` | fix(deploy): 迁移与 uvicorn 改 python -m 避开 uv tr | ⬜未评 |  |
| `a1c2a8d424` | fix(deploy): aerich 迁移改用 python -m aerich.cli | ⬜未评 |  |
| `4f572a2431` | fix(deploy): Windows 跳过 PATH 中 Linux 版 Caddy | ⬜未评 |  |
| `d003ff3404` | fix(deploy): 蓝绿 backend 健康等待随 worker 加长 | ⬜未评 |  |
| `18cd0581d9` | fix(deploy): Taskiq 启动改 python -m taskiq 避开 u | ⬜未评 |  |
| `8700bd8a16` | revert(deploy): 恢复 fast-deploy 至 11-05 末版 (5f | ⬜未评 |  |
| `351fe4815e` | revert(deploy): 恢复 fast-deploy 至 11-04 日快照 (0 | ⬜未评 |  |
| `0d021ef663` | revert(deploy): 移除 11-05 新增的 promote-prod-bra | ⬜未评 |  |
| `489fb03d8a` | fix(deploy): Windows 识别可用 uv，不用 11-05 install | ⬜未评 |  |
| `1821d9dfb7` | fix(deploy): Windows 识别 Roaming Python312 Scr | ⬜未评 |  |
| `c05a1f0f33` | fix(deploy): 迁移改用 python -m aerich.cli 避开 uv | ⬜未评 |  |
| `34177331ca` | fix(deploy): 迁移直调 .venv python，不再 uv run | ⬜未评 |  |
| `fd25330958` | fix(deploy): Windows 全站绕过 uv run，直调 .venv Pyt | ⬜未评 |  |
| `1cd3a1dfeb` | fix(deploy): Windows 直调 venv 时去掉多余 python 参数 | ⬜未评 |  |
| `f26a029719` | fix(deploy): Windows 跳过 PATH 上 Linux 版 caddy | ⬜未评 |  |
| `08ed0e510f` | fix(deploy): Windows Caddy 下载修复 curl 调用与 IWR | ⬜未评 |  |
| `83a29492cf` | fix(deploy): update 时保留 fast-deploy/.tools 便携 | ⬜未评 |  |
| `8a0f731a42` | fix(deploy): Windows Caddy 改存主仓外 riveredge-ru | ⬜未评 |  |
| `ab912e4c14` | fix(deploy): Windows Caddy 国内优先山大 Release 镜像 | ⬜未评 |  |
| `aa7d181320` | fix(deploy): install-component.ps1 Caddy 错误文案 | ⬜未评 |  |
| `c16cf35d1c` | fix(deploy): 锁定 Windows Caddy 唯一落点 riveredge- | ⬜未评 |  |
| `95efae8f6d` | fix(deploy): 撤回 riveredge-runtime，Caddy 固定 fa | ⬜未评 |  |
| `454e306f9a` | fix(deploy): Windows 不 git clean；禁止 install 覆 | ⬜未评 |  |
| `0ea3994534` | fix(deploy): 移除未核实的 SDU Caddy 镜像，优先 ghproxy.n | ⬜未评 |  |
| `8908591c5f` | chore(docs): 更新微信交流群截图 | ⬜未评 |  |
| `12550024bb` | fix(migrate,deploy): 报工/返工 review_status 列幂等与 | ⬜未评 |  |
| `707700c8d0` | fix(deploy): install-web-dist 同步刷新 dist-live， | ⬜未评 |  |
| `220d2ce271` | fix(deploy): 低配机后端健康检查超时改为 360s | ⬜未评 |  |
