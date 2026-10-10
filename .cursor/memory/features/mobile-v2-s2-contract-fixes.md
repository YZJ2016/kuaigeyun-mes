---
title: 移动端第二轮 S2 静态门禁修复
slug: mobile-v2-s2-contract-fixes
status: delivered
domain: mobile
when: 改 riveredge-app-mobile 报工/仓储确认/权限 hook/扫码竞态/列表空态，或跑 mobile-v2 外置门禁
keywords:
  - S2-01
  - canAction
  - searchSeq
  - loadError
  - test_m2_mobile_contract
standard: 只改 kuaigeyun-client/riveredge-app-mobile；门禁 pytest 在 D:\pytest\d-kuaigeyun-client\mobile-v2
---

# 移动端第二轮 S2 静态门禁修复

## 目标

对齐 `test_m2_mobile_contract.py`（S2-01～S2-19）：报工闸门、代报 assign、仓储确认、弱网续期、权限 fail-closed。

## 何时读 / 禁止另起

- 何时读：移动端报工双连击、代报 403、confirm 按钮看不见、token 误登出、Alert.alert 混用。
- 禁止：不要改后端/PC；仓储确认不要用 `canAction('approve')` 挡 confirm（manifest 虽有 inbound:approve，仓管常只有 update）。

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `useResourcePermissions` + antd `Modal.alert` + `searchSeq` 去重 |
| BE | 只读对照：`reporting.py` 代报 `:assign`；领料 `.../confirm` |
| 权限 | 代报 `canAction('assign')`；质检卡片 `canAction('execute')`；仓储详情 `canUpdate` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 报工 | `kuaigeyun-client/riveredge-app-mobile/app/mes/report.tsx` |
| 权限 | `.../src/hooks/useResourcePermissions.ts` |
| 续期 | `.../src/utils/tokenRefresh.ts`（`'ok'\|'denied'\|'network'`） |
| 门禁 | `D:\pytest\d-kuaigeyun-client\mobile-v2\test_m2_mobile_contract.py` |

## 扩展点

1. 仓储其它详情若仍 `canAction('approve')`（return/other-inbound 等）按同一口径改 `canUpdate`。
2. `api.ts` 全局失败勿从该层 import antd Modal（易拖垮 tsc）；业务层 `Toast.fail(e.message)`。

## 踩坑

- 外置测试用 `src.find("ops.find")` / 首个 `inspectionQty` 附近 1200 字，锚点字符串必须靠近。
- `canAction` 空 action / 未知码必须 false；不要 `skip` 恒 true。
- 刷新失败：仅 401/403 → `denied` 才 `clearAuth`；网络/5xx → `network` 保留 token。
