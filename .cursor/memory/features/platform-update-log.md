---
title: 平台更新日志每次交付补一条
slug: platform-update-log
status: active
domain: system
when: 用户可见的功能、修复、改进交付时；工作台版本卡、更新说明
keywords:
  - platformUpdateLog.ts
  - PLATFORM_UPDATE_LOG_GENERAL
  - PLATFORM_UPDATE_LOG_DEDICATED
  - pages.dashboard.updateLog.entries
  - DashboardUpdateLogModal
standard: 通用插 GENERAL 头部；定制插 DEDICATED；同步 zh-CN 两条 i18n。
---

# 平台更新日志每次交付补一条

## 目标

用户能在工作台「更新说明」看到本次改动。交付用户可见能力时必须写一条，不要等发版再补。

## 何时读 / 禁止另起

- 何时读：新功能、修复、改进、安全项合入且终端用户能感知。
- 禁止：另写一套 changelog 页；只改代码不写日志；把 HaoliGO / DocToolkit / `.gen/docgen` 造数写进通用日志。

不写：纯内部重构、仅 Agent/运维脚本、用户无感知的改字段名。

## 标准入口

| 层 | 标准 |
|----|------|
| 通用 | `PLATFORM_UPDATE_LOG_GENERAL` 数组**头部**插入 |
| 定制应用 | `PLATFORM_UPDATE_LOG_DEDICATED` 头部；`scope: 'dedicated'` + `dedicatedAppCode` |
| 文案 | `riveredge-frontend/src/locales/zh-CN.ts` 的 `pages.dashboard.updateLog.entries.{id}.title` 与 `.description` |
| 展示 | `DashboardUpdateLogModal`（工作台版本卡） |

## 关键文件

| 角色 | 路径 |
|------|------|
| 通用条目 | `riveredge-frontend/src/pages/system/dashboard/platformUpdateLog.ts` |
| 定制条目 | `riveredge-frontend/src/pages/system/dashboard/platformUpdateLogDedicated.ts` |
| 弹窗 | `riveredge-frontend/src/pages/system/dashboard/DashboardUpdateLogModal.tsx` |
| zh-CN | `riveredge-frontend/src/locales/zh-CN.ts` |

## 扩展点

1. `id`：短横线 slug + `-r01`；同主题再改则 `-r02`。
2. `date`：`YYYY-MM-DD`（当天）。
3. `type`：`major` \| `feature` \| `improvement` \| `fix` \| `security`。
4. `titleKey` / `descriptionKey` 必须等于 `pages.dashboard.updateLog.entries.{id}.*`。
5. 定制：`dedicatedAppCode` 用 manifest 应用 code（不对用户展示）。

## 过程

1. 在对应数组最前面插入一条对象。
2. 在 zh-CN 增加 title / description（用户口吻，写「原来怎样、现在怎样」）。
3. 不要为这条单独跑其它语言文件（见 i18n-zh-cn-only）。

## 踩坑

- 插到数组尾部会排到很旧，工作台按头部优先。
- 只加 TS 条目、漏 i18n，弹窗会露出 key。
- 通用日志不要写仅某定制租户能用的内容；那种走 DEDICATED。

## 关联

- `principles/feature-delivery.md`
- `.cursor/rules/feature-delivery-checklist.mdc`
