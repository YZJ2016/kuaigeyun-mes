---
title: AOCI 何时维护、提交什么、与构建推送顺序
slug: aoci-git-commit
status: active
domain: principle
when: 要不要跑 AOCI、每次提交是否 maintain、构建推送前索引、提不提 aoci.txt
keywords:
  - aoci
  - aoci_maintain
  - aoci_update_entry
  - 提交前先索引
  - 构建推送
  - 要不要跑 AOCI
  - 勿排除索引
  - baseline.json
standard: 改了托管对象才 maintain；正式资产随变更提交；构建推送前 tip 索引须已对齐
---

# AOCI 正式资产与 Git 提交

- 写入：2026-10-09；澄清「非每次 push 都跑」：2026-10-10
- 规则真源：`.cursor/rules/aoci-git-commit.mdc`、`.cursor/rules/build-push-aoci.mdc`
- MCP 绑仓：`features/aoci-mcp-three-repos.md`

## 何时读

- 「每次提交推送要不要跑 AOCI？」
- 「提交时不要带 / 要不要提 aoci」
- 交付收尾、`build.web.sh` 因未跟踪 `aoci*.txt` 失败
- Web / H5 / 工位构建推送前

## 一句话

**不是每次 `git push` 都要跑。** 改了本仓 AOCI **托管对象**（源码、受管配置等）→ 源码稳定后 **先** `aoci_maintain`（有候选再 `aoci_update_entry`）**再** `git commit`；构建推送时 tip 上索引不得落后。未改托管对象的纯说明提交可跳过 maintain。

旧偏好「永远排除 aoci」已废止；正式索引是仓库契约，默认与业务一并提交。

## 要跑 maintain（强制）

| 场景 | 动作 |
|------|------|
| 改了受管源码/配置后的业务/发版提交 | 稳定后 **一次** `aoci_maintain` → 有候选则整批 `aoci_update_entry` → 再 commit |
| 「web端构建推送」「移动端构建推送」「工位打包推送」 | 推送前 tip 须已对齐；有未维护 stale/missing（非 skipped）先维护再构建 |
| Agent 交付改了托管对象 | 收尾默认 maintain；用户未禁 AOCI 时正式资产应入库 |

要点：

- **对象已最终稳定再 maintain**，勿每改一个文件就调一次
- 三仓各自 MCP：主仓 `aoci` / client `aoci-client` / pro `aoci-pro`，任务落哪仓调哪套
- 有候选时保留机器签发的 `source_sha256`、`candidate_id`、`code_batch_id`

## 可跳过 maintain

| 场景 | 说明 |
|------|------|
| 未改任何托管对象的纯说明性提交 | 可跳过；勿留下未跟踪的正式 `aoci*.txt` |
| `build.web.sh` 自动的 `chore: build-web sync` | 脚本只交 dist；**此前**源码 tip 索引须已对齐 |
| 用户明确禁止改 AOCI / `.aoci` | 服从，并报告索引与源码不一致 |

## 与「构建推送」的关系

AOCI → commit → **源码 `git push`** 是一条路径。  
**产物构建**（`build.web.sh` / H5 / 工位 pack）是另一条路径，仅当对应 UI 源变更时才做。

完整分流见 `principles/code-push-routing.md` 与规则 `build-push-aoci.mdc`。

有产物构建时顺序（不可颠倒）：

1. 源码改到稳定（不含 dist / 工位 `release/`）
2. AOCI：`maintain` →（候选）`update_entry` → 必要时 verify
3. `git add` 正式 AOCI + 业务 → `git commit`
4. 再跑**对应**产物脚本（不要无前端改动却跑 Web 构建）

禁止：先 commit 业务再补 aoci；索引脏着推产物；用「构建后再补索引」跳过。

## 应提交 / 勿提交

**应提交（正式资产）**

- `aoci.txt`、`aoci.meta.txt`、`aoci.code.txt`（及未来同类 volume）
- `AGENTS.md` 中 `<!-- aoci:begin -->`…`<!-- aoci:end -->`（若有改动）
- `.aoci/` 白名单：`config.json`、`baseline.json`、`curation.json`、`.gitignore`（以 `.aoci/.gitignore` 为准）

**勿提交（本机运行时）**

- `.aoci/` 下 lock、ledger、batch JSON、mk 助手、drafts、mcp 调试产物等

**gitignore**

- 根 `.gitignore` **禁止**写整夹 `.aoci/`（会挡住白名单）
- 运行时忽略与正式放行只维护在 `.aoci/.gitignore`

## 给人 vs 给 Agent

- **你本人**：小改可先提交业务；至少在发版 / 构建推送前对齐一次，避免脏索引挡干净树检查
- **Agent**：改了托管对象则收尾默认跑 maintain 并提交正式资产（除非你明确禁止）

## 入库约定（主仓）

根 `.gitignore` **不得**再写整夹 `.cursor/`。应放行 `.cursor/memory/**` 与 `.cursor/rules/**`，仅忽略本机 `mcp.json` 等。否则「永久记忆库」只在本机、进不了 git，与 `dev-memory-library.mdc` 冲突。

## 关联

- `.cursor/rules/aoci-git-commit.mdc`、`.cursor/rules/build-push-aoci.mdc`
- `features/aoci-mcp-three-repos.md`、`features/fast-deploy-scripts.md`
- Vault：`web-build-push-sop.md`
