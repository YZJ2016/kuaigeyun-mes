---
title: 记忆库书写与检索约定
slug: memory-note-format
status: active
domain: principle
when: 新增或改写 .cursor/memory 笔记时
keywords:
  - frontmatter
  - keywords
  - _TEMPLATE
  - README
standard: features/_TEMPLATE.md + 本篇
---

# 记忆库书写与检索约定

- 写入：2026-10-03
- 同步规则：`.cursor/rules/dev-memory-library.mdc`

## 给谁写

笔记是给 **后续 Agent** 用的，不是给人类写周报。优先：能 Grep、能 30 秒判断「该不该读」、能找到唯一标准入口。

## 一篇笔记只记一件可复用能力

- slug：小写短横线，与文件名一致，例如 `sync-push-hub-master-data.md`
- 不要把无关能力塞进同一篇；有关联用文末「关联」指到另一篇路径
- 过程流水最多 8 条；细节以仓库源码为准，笔记只留契约和坑

## 必须有 YAML frontmatter

字段固定，便于 Agent 扫前 20 行：

```yaml
---
title: 人类可读标题
slug: 与文件名不含扩展名一致
status: delivered | in_progress | active
domain: 见下方词表
when: 一句话，什么任务必须读这篇
keywords:
  - 组件名
  - API 片段
  - 权限码或脚本名
standard: 标准入口一句话
---
```

`domain` 只用这些值：`sync-push` | `sync-from-source` | `scheduler` | `kuaiiot` | `master-data-ui` | `code-rule` | `deploy` | `principle`。新域先改本篇词表和 `README.md` 路由表。

## 正文标题固定（features）

按此顺序，缺段写「无」不要删标题：

1. `#` 标题（与 `title` 同义）
2. `## 目标` — 一句话
3. `## 何时读 / 禁止另起` — 触发条件 + 禁止平行实现
4. `## 标准入口` — 表：层 / 标准（组件、API、权限）
5. `## 关键文件` — **仓库相对完整路径**，禁止 `.../` 省略
6. `## 扩展点` — 新类型怎么挂，编号列表
7. `## 过程` — 可选，短
8. `## 踩坑` — 可验收的现象
9. `## 关联` — 用反引号路径，可附 Obsidian `[[wikilink]]`

原则类笔记用：原则 / 动手前 / 禁止 / 交付。

## 路径与链接

- 文件：`riveredge-frontend/src/...` 这种完整相对根路径
- 关联笔记：`` `features/foo.md` ``，不要只写 `[[foo]]`
- 规则文件：``.cursor/rules/xxx.mdc``
- 本机或 Vault 绝对路径可以附在关联里，但标准入口必须是仓库内路径

## 索引必须同步

新笔记：改 `README.md` 的「关键词路由」+「索引」两张表。漏登等于 Agent 读不到。

## 禁止

- 大段粘贴源码（给路径和符号名）
- 把临时诊断日志、租户 id、token 写进记忆库
- 同一能力两篇互相矛盾还不标明哪篇作废
- 用散文代替 `keywords`（Grep 靠关键词，不靠修辞）
