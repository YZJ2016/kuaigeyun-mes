---
title: 工位齐套缺料预警走底栏呼叫/安灯
slug: station-shortage-andon-call
status: delivered
domain: mes-station
when: 顶栏齐套缺料叫料横幅、呼叫闪烁、安灯发起呼叫缺料提示
keywords:
  - station-header-alert
  - andonShortageAlert
  - shortageAlertText
  - AndonCenterPanel
  - 齐套缺料
  - hmi-andon-pulse
standard: 缺料不占顶栏；底栏呼叫脉冲；安灯「发起呼叫」区展示预警并预选物料
---

# 工位齐套缺料预警走底栏呼叫/安灯

## 目标

选中工单齐套 bad/warn 时，不再在顶栏重复「叫料」入口；底栏「呼叫」闪烁，打开安灯中心后在「发起呼叫」展示预警并预选物料。

## 何时读 / 禁止另起

- 何时读：顶栏 danger 缺料横幅、与底栏呼叫重复、预警位置不对、呼叫不闪。
- 禁止：再加一套顶栏叫料按钮；勿把暂停提示也塞进安灯；勿把 `hmi-andon-pulse` 直接打在底栏金属键上（会被 `box-shadow:!important` 盖掉）。

## 标准入口

| 层 | 标准 |
|----|------|
| 顶栏 | 仅保留「工序已暂停」等非叫料类提示 |
| 底栏 | `HmiActionBar.andonShortageAlert` → slot `hmi-action-bar__slot--pulse` |
| 安灯 | `AndonCenterPanel.shortageAlertText` + `initialType=material` |

## 踩坑

- 工位认知走 MCP `aoci-client`（见 `features/aoci-mcp-three-repos.md`），勿用主仓 `aoci` Overview 代替。
- 共享报工 `showAndon={false}`，缺料预警只存在于固定工位 `StationTerminal`。
- **勿用 `checkShortage` 驱动呼叫闪烁**：下达缺料只看仓库可用，不含已领料/线边；齐套 100% 仍会误闪。标准走 `getKittingAnalysis` / `readiness_rate`（`utils/workOrderKitting.ts`）。
- 底栏呼叫在 `openAndonCount > 0` 时也会脉冲（未关闭的安灯），与齐套无关。

## 关键文件

| 角色 | 路径 |
|------|------|
| 固定工位页 | `kuaigeyun-client/riveredge-app-station/src/pages/StationTerminal/index.tsx` |
| 底栏 | `.../hmi/components/HmiActionBar.tsx` |
| 安灯面板 | `.../components/station/AndonCenterPanel.tsx` |
| 队列筛选 | `.../utils/workOrderQueue.ts`（全部/指派/缺料/生产中/已冻结） |
| 齐套着色 | `.../utils/workOrderKitting.ts`（kitting-analysis，非 check-shortage） |

## 队列筛选对照

标准实现：`workOrderQueue.ts`（固定 / 共享同一套；**不**按 work_center_id 收窄队列）。

| 筛选项 | 匹配 |
|--------|------|
| 全部 | 载入 status ∈ released / in_progress |
| 指派给我 | 请求 `assigned_worker_id`（含班组），见 `station-assigned-wo-includes-team` |
| 缺料 | 客户端 kitting bad/warn 或 readiness_rate 未满 100 |
| 生产中 | status in_progress / processing / 「生产中」 |
| 已冻结 | `is_frozen` |
| 搜索 | 后端 `keyword` + 客户端模糊（编码/产品/订单/批次等） |

## 关联

- `features/station-assigned-wo-includes-team.md`
- `features/station-wo-queue-shared-filter.md`
- `principles/three-repo-map.md`（工位源码在 client）
