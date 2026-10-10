---
title: 工位人脸录入与采样管理在设备设置
slug: station-face-settings-manage
status: delivered
domain: mes-station
when: 工位录脸入口、已录入人脸账号、采样删除、切换操作员里找不到录入
keywords:
  - FaceEnrollModal
  - StationSettingsModal
  - face-templates
  - list_accounts
standard: 录入/补采/删采样只在设备设置；识别仍走 face-identify。
---

# 工位人脸录入与采样管理在设备设置

## 目标

工位机在设备设置里录入人脸，并按账号管理已有采样；切换操作员只识别不录入。

## 何时读 / 禁止另起

- 何时读：录脸入口、人脸模板列表、清除某账号全部采样。
- 禁止：再在 OperatorSwitchModal / StationTerminal 挂 FaceEnrollModal；用内部角色顶替触屏专用登录工位。

## 标准入口

| 层 | 标准 |
|----|------|
| FE 设置 | `StationSettingsModal`；齿轮仅登录页或 `canUseStationSettings`（管理员 + 触屏专用） |
| FE 采集 | `FaceEnrollModal`（设置里打开） |
| FE API | `stationApi.listFaceAccounts` / `deleteFaceTemplate` / `deleteFaceAccount` |
| BE | `GET/POST /station/face-templates`、`DELETE .../by-user/{id}`、`DELETE .../{template_id}` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 列表服务 | `riveredge-backend/src/infra/services/face_template_service.py` `list_accounts` |
| 路由 | `riveredge-backend/src/apps/kuaizhizao/api/station/station.py` |

## 扩展点

1. 识别阈值仍在 `FaceTemplateService.DEFAULT_MATCH_THRESHOLD`，与本页无关。
2. 列表不返回 descriptor。
3. 工位登录必须 `role_type=station`；报工不要求管理员。设备设置（含录脸）要管理员 bypass + 触屏专用，见 `stationAccess.ts` / `api/station/access.py`。

## 踩坑

- 登录前打开设置没有 token，只提示「请先登录后再管理人脸采样」。
- `DELETE /face-templates/by-user/{id}` 必须写在 `/{template_id}` 前面。
- 「经常识别不到」优先查 `public/models` / `resources/models` 是否有 `antispoof`+`liveness`（见 `copy-face-models.mjs`）；缺模型时活体门禁会把描述子全部挡掉。

## 关联

- `features/station-st2-security-contract.md`
