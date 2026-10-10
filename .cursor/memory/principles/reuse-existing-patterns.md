---
title: 复用优先：同一功能只有一套标准实现
slug: reuse-existing-patterns
status: active
domain: principle
when: 任何新功能、看起来「差不多」的面板/同步/推送/下拉/部署入口
keywords:
  - SyncPushHub
  - DocumentPushBatchPanel
  - sync-from-source
  - preferIds
  - 复用
standard: 已落地且用户熟悉的实现为唯一标准
---

# 复用优先：同一功能只有一套标准实现

- 写入：2026-10-01
- 同步规则：`.cursor/rules/reuse-existing-patterns.mdc`（alwaysApply）

## 原则

同样的功能不要做出两个不一样的。开发前**先搜索**仓库与本记忆库；有则统一走那一套方法与交互，禁止平行发明第二套。

## 动手前

1. 先读 `.cursor/memory/README.md` 关键词路由
2. 再搜代码：`SyncPushHub`、`DocumentPushBatchPanel`、`sync-from-source`、`preferIds`
3. 选定标准：以已落地且用户熟悉的实现为唯一标准
4. 对齐契约：同一入口、同一组件/服务、同一权限与文案模式；只补业务差异

## 禁止

- 为「差不多」的需求再写一套面板 / 门禁 / profile 过滤 / 勾选传递
- 前端白名单与后端注册表漏登导致半残功能
- 用「本次更快」跳过复用

## 交付

- 行为对齐至少一个现有页面
- 新类型只挂既有扩展点
- 标准有缺口则**先修标准再复用**
- 写一篇 `features/<slug>.md`，并更新 `README.md` 索引

## 关联

- `principles/memory-note-format.md`
- `principles/feature-delivery.md`
- `.cursor/rules/reuse-existing-patterns.mdc`
