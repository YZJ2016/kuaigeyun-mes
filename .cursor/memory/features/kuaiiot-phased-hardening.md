---
title: 快数采（kuaiiot）分阶段硬化
slug: kuaiiot-phased-hardening
status: in_progress
domain: kuaiiot
when: 快数采 MES 写回、指令/填充、边缘协议、设备绑定、ingest
keywords:
  - kuaiiot
  - MesGuard
  - FILL_TARGET
  - DISPATCH_CHANNELS
  - EDGE_AGENT_IMPLEMENTED_PROTOCOLS
  - map_target
  - fill_target
standard: 快制造设备态监控写回 + 报工/点检 fill-context
---

# 快数采（kuaiiot）分阶段硬化

- 日期：2026-10-03
- 状态：进行中（P0–P2 主项已落地；中长期项另排）

## 目标

把「半上线」的 Wave1–6 能力收成可试点的通用数采：MES 写回安全、菜单可用、指令/填充契约一致、边缘协议名实相符。

## 何时读 / 禁止另起

- 何时读：新 map_target / fill_target / 指令通道 / 边缘协议
- 禁止：绕开 `_maybe_sync_mes` 写 MES 设备状态；指令枚举不走 `constants.py`

## 标准入口

- 源包（可提交）：`kuaigeyun-pro/{backend,frontend}/apps/kuaiiot/`（组装仓 `riveredge-*/src/apps/kuaiiot` 被 gitignore，改完需回写 Pro）
- FE 组装态：`riveredge-frontend/src/apps/kuaiiot/`（路由 `index.tsx`，菜单 `manifest.json`）
- BE 组装态：`riveredge-backend/src/apps/kuaiiot/`（ingest / MesGuard / Command / Tag / Edge）
- 权限：前后端 `manifest.json` 同权同菜单；关键码含 `kuaiiot:product:*`、`kuaiiot:device-group:*`
- 单测：`riveredge-backend/tests/apps/kuaiiot/`（主仓可提交）

## 关键文件

| 角色 | 路径 |
|------|------|
| MES 写回护栏 | `riveredge-backend/src/apps/kuaiiot/services/mes_guard_service.py` + ingest `_maybe_sync_mes` |
| 常量契约 | `riveredge-backend/src/apps/kuaiiot/constants.py` |
| 指令 | `services/command_service.py` + `message_log_service.py` |
| 菜单 | 前后端 `apps/kuaiiot/manifest.json` |
| 点位/填充 UI | `pages/tags`、`pages/products`、`constants/formOptions.ts` |
| 边缘协议提示 | `pages/edge-configs` + `EDGE_AGENT_IMPLEMENTED_PROTOCOLS` |

## 扩展点

1. 新 map_target：`MAP_TARGETS` 或 `other_parameters.*` 前缀；前端 `buildMapTargetOptions`
2. 新 fill_target 前缀：加入 `FILL_TARGET_PREFIXES`，并在 fill-context / kiosk 消费侧对齐
3. 新指令通道：先入 `DISPATCH_CHANNELS`，实现后再加 `DISPATCH_CHANNELS_IMPLEMENTED`
4. 新边缘协议：云侧 `EDGE_PROTOCOLS`；Agent 实现后同步 `EDGE_AGENT_IMPLEMENTED_PROTOCOLS`（前后端）

## 过程

### P0 生产安全 + 页面能用

1. ingest 接入 `MesGuardService.prepare_mes_payload`；缺 status 不默认「运行中」；MES 设备缺失吞 `NotFoundError` 不打爆入站
2. 前后端 manifest 对齐（产品模型菜单 + product/device-group 权限）
3. 设备页 import / 产品类型契约补齐

### P1 指令与填充契约

1. `MESSAGE_*` 覆盖指令链路枚举；写日志用 inbound/outbound + command_result + success/failed/timeout
2. `DISPATCH_CHANNELS` 含 TB/JL；`DISPATCH_CHANNELS_IMPLEMENTED` 门禁 http/mqtt
3. `FILL_TARGET_PREFIXES` 含 `spot_check.`；TagService 校验；UI AutoComplete 可填真实项编码

### P2 使用体验

1. 边缘协议选项标注 Agent 未实现；保存时 warning；表单 extra 提示
2. 产品/点位 map_target、tag_key、fill_target 可自定义输入
3. zh-CN / en-US 文案补齐

### P3（节流与绑定）

1. MES 写回节流：`status` / `is_online` 相对最新监控有变化时强制写回；仅同态遥测仍受 5s 节流
2. 同一租户 `equipment_uuid` 活跃绑定唯一：`DeviceService` 校验 + 批量创建禁止多台共用绑定
3. 迁移 `821_..._kuaiiot_equipment_bind_unique`：清理历史重复后建 partial unique index

### P3+（仍另排）

- 幂等原子化
- MQTT 多 worker 重复订阅
- 点检角色权限与 fill-context 门禁优化
- Agent 实现 RTU/OPC UA/S7

## 踩坑

- 护栏有单测但未接线时，维修中设备会被传感器改台账 status——必须以 `_maybe_sync_mes` 为唯一写回入口
- 指令创建若 direction/msg_type/result 与常量不一致，会在首条 MessageLog 就失败
- 前端 manifest 漏 products 时，按前端同步会吞掉物模型菜单
- 节流旧逻辑会吞 5s 内 running→fault；必须以最新 monitor 的 status/is_online 做旁路判断
- 唯一绑定迁移会解绑重复中的次小 id 记录（保留最小 id）
- 验收：`pytest tests/apps/kuaiiot/`；`aerich upgrade` 到 `821_...`；同 MES 设备绑第二台应报错；故障跳变 5s 内仍应写回

## 关联

- `principles/reuse-existing-patterns.md`
- `principles/feature-delivery.md`
- `docs/apps/kuaiiot/ROADMAP.md`
