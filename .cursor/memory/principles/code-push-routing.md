---
title: 代码推送分流：何时只 push、何时构建产物
slug: code-push-routing
status: active
domain: principle
when: 构建推送、只改后端还要不要编前端、web/H5/工位推送选哪条、dist 要不要提交
keywords:
  - 构建推送
  - 代码推送
  - dist不入库
  - 只要 git push
  - 没改前端
  - web端构建推送
  - 分流
standard: 按改动路径选最小推送集；产物构建与源码 push 分离；AOCI 仅托管对象
---

# 代码推送分流

- 写入：2026-10-10；修订：2026-11-19（dist 出库，PC Web 推送不再有构建步骤）
- 规则真源：`.cursor/rules/build-push-aoci.mdc`
- AOCI：`principles/aoci-git-commit.md`；脚本入口：`features/fast-deploy-scripts.md`

## 何时读

- 「构建推送」但不确定要不要编前端
- 只改了后端 / deploy / 记忆库
- 纠正「每次交付都 build.web / 提交 dist」的旧习惯

## 一句话

**推送 ≠ 构建前端。** `riveredge-frontend/dist` 不入库：所有推送都是 AOCI（若需要）→ commit → `git push`。PC 前端由部署机部署时现构建；只有 H5 / 工位**产物源**变了，才跑对应产物脚本。

## 决策表

| 你改了什么 | AOCI | 源码 push | 产物构建 |
|------------|------|-----------|----------|
| 后端 API / 服务 / 迁移 | 要（托管对象） | `git push` | 不要 |
| `fast-deploy/` 部署脚本 | 要 | `git push`；生产 `deploy.sh update` | 不要 |
| `.cursor/memory/**` 记忆库 | **跳过** maintain（scope 已 exclude，不建 Entry） | `git push` | 不要 |
| `.cursor/rules` / 说明文档 | 改了 rules 则 maintain；纯说明可跳过 | `git push` | 不要 |
| `riveredge-frontend/src` 等 PC 前端 | 要 | `git push` | **不要**（dist 不入库，部署机部署时构建） |
| 移动端 UI（client） | `aoci-client` | client commit | **要** H5：`build.mobile.web.sh` → 交 `web-dist` |
| 工位需发安装包（client） | `aoci-client` | client commit | **要**：`npm run pack`（`release/` 不入库） |
| 同时改了前端 + 后端 | 要 | 源码 commit（可含两端） | 仅移动/工位产物（若有） |

## 用户口令怎么理解

| 用户说 | Agent 应做 |
|--------|------------|
| 「构建推送」（未指端） | 看 diff 分流；仅后端/deploy/记忆库 → 只源码 push，并说明未编前端 |
| 「web端构建推送」 | 源码 push 即可；本机验证构建跑 `npm run build`（产物勿提交） |
| 「推送」「提交推送」 | 一律源码路径 |
| 「移动端构建推送」「工位打包推送」 | 走 client 对应产物路径 |

## 与 AOCI 的衔接

- **要索引**：改了业务/部署等 AOCI 托管（index）对象 → 稳定后一次 maintain →（候选）update_entry → 再 commit  
- **不要索引**：只改 `.cursor/memory/**`（已 exclude）或纯说明 → 直接 commit/push  
- **git 入库记忆库**是为了 Agent 能读，**不是**为了每篇笔记进 `aoci.code.txt`  
- 跑产物构建前：当前 tip 上**业务相关** missing/stale 须清零（skipped / exclude 除外）  

细节见 `principles/aoci-git-commit.md`。

## 禁止

- 把 `riveredge-frontend/dist` 提交进 git（已 gitignore）
- 本机 `npm run build` 后手写 commit/push dist
- 把「业务发版」理解成「三端产物全打一遍」  
- 索引脏着推 H5 / 工位包  

## 关联

- `.cursor/rules/build-push-aoci.mdc`
- `features/fast-deploy-scripts.md`
- `principles/aoci-git-commit.md`
