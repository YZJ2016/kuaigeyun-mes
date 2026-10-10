---
title: 工位端 ST2 安全与报工契约
slug: station-st2-security-contract
status: delivered
domain: mes-station
when: 改工位 Electron IPC、刷脸会话、共享报工状态机、工位文档/打印、安灯失败态、操作员头
keywords:
  - ST2
  - station:apiFetch
  - X-Station-Operator
  - document-flags
  - FaceEngine
  - RequireMode
standard: 工位写操作走 stationApi 带头与 SOP worker_id；文档走 /station/work-orders/.../documents；打印走鉴权 blob
---

# 工位端 ST2 安全与报工契约

## 目标

工位终端 IPC、人脸、报工状态机、文档/打印、队列批量标志与模式路由对齐 `test_st2_station_contract.py`。

## 何时读 / 禁止另起

- 何时读：工位 SSRF、刷脸 ATM、共享报工门禁、ESOP/图纸、条码打印、安灯加载失败。
- 禁止：再开一套 SOP/图纸 master-data 直链；`window.open` 裸 API 打印；未匹配人脸刷新会话；列表 N+1 `checkShortage`；在「切换操作员」里做人脸录入。

## 标准入口

| 层 | 标准 |
|----|------|
| FE Electron | `riveredge-app-station/electron/main.ts` `station:apiFetch` |
| FE 会话 | `SharedReportTerminal` `matched && has_station_role` + `sessionGenerationRef` |
| FE API | `stationApi` + `X-Station-Operator` |
| BE 录脸 | 设备设置 `StationSettingsModal` → `FaceEnrollModal`；`FaceTemplateService.enroll` / `list_accounts` |
| 文档 | `GET /apps/kuaizhizao/station/work-orders/{id}/operations/{op}/documents` |

## 关键文件

| 角色 | 路径 |
|------|------|
| IPC | `riveredge-app-station/electron/main.ts` |
| 人脸 | `src/face/FaceEngine.ts` `FaceCaptureView.tsx` |
| 门禁 | `D:\pytest\d-kuaigeyun-client\station\test_st2_station_contract.py` |

## 扩展点

1. 工位写接口继续走 `stationOperatorHeaders()`。
2. 队列附件角标走 `document-flags`；选中工单齐套着色走 `getKittingAnalysis`（勿用 `checkShortage`，见 `station-shortage-andon-call`）。

## 踩坑

- ST2-11 的 `useEffect` 正则不能写成 `useEffect(() =>`，空参 `()` 会截断；用 `useEffect(ctxGen => { setLastReportingRecordId(null)`。
- 打印后端装饰器必须与 path/`print` 同一行，pytest 按单行 `@router.get(...print` 搜。
- `npm run typecheck:electron` 脚本不存在，等价 `build:electron`（`tsc -p tsconfig.electron.json`）。
- FaceEngine 启用了 `antispoof`/`liveness` 且分数缺失 fail-closed：`copy-face-models.mjs` **必须**拷贝 `antispoof.*` + `liveness.*`，否则永远 `low_score`、识别不到；改脚本后需重跑 `node scripts/copy-face-models.mjs`（或 `npm run build`）并重装/重开工位包。
