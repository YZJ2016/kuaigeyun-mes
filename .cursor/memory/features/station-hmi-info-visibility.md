---
title: 工位 HMI 信息可见性
slug: station-hmi-info-visibility
status: delivered
domain: mes-station
when: 工位字被裁切、看不清、ellipsis、顶栏工位名消失、中区滚不动
keywords:
  - overflow hidden
  - line-clamp
  - TEXT_SECONDARY
  - hmi-workbench
standard: 工位可见性只改 HMI token + hmi.css/station.css；禁止另起皮肤
---

# 工位 HMI 信息可见性

## 目标

1920×1080 触屏上产品名、工序、告警、工位路径能读完，不被 `overflow:hidden` 吃掉。

## 何时读 / 禁止另起

- 何时读：工位界面信息不全、字太淡、单行截断
- 禁止：新主题、靠顶栏横向滚动当展示方案、正文用 12/13px 或 tertiary

## 标准入口

| 层 | 标准 |
|----|------|
| Token | `HMI_DESIGN_TOKENS` 对比度、`HMI_STATION_LAYOUT` 列宽 |
| CSS | `hmi.css` + `station.css`（`.hmi-root.hmi-station`） |

## 关键文件

| 角色 | 路径 |
|------|------|
| Token | `riveredge-app-station/src/hmi/tokens/design.ts` `layout.ts` |
| 样式 | `riveredge-app-station/src/hmi/styles/hmi.css` `station.css` |

## 踩坑

- 中区/右栏禁止滚动：`HmiFitScale` 整体等比缩小；进度环跟同一比例
- 左栏工单列表仍可滚
- ellipsis 只留给工单号/图号/条码；产品名工序名告警用 2 行 clamp
- 顶栏 CSS 84px 与 token 必须一致；内钮 ≥48

## 关联

- `features/station-st2-security-contract.md`
