---
title: 新功能交付：14 位时间戳迁移 + 菜单同步 + 更新日志
slug: feature-delivery
status: active
domain: principle
when: 加菜单、权限、新表、新模块、改 manifest
keywords:
  - aerich
  - manifest
  - sync-manifest
  - 权限码
  - module_references
  - platformUpdateLog
standard: 14 位时间戳迁移 + 前后端双 manifest 同步 + 仅通用更新日志；环境受限未执行须明示
---

# 新功能交付：迁移 + 菜单同步

- 规则真源：外层根仓 `.cursor/rules/feature-delivery-checklist.mdc`、`.cursor/rules/platform-update-log.mdc`
- 细节以规则全文为准，本篇只作检索摘要。

## 动手前 / 交付时

1. **数据库迁移**：在 `riveredge-backend/migrations/models/` 新建 aerich 迁移并注册 `orm_models`；文件名第一段**必须为 14 位时间戳**且大于已有最大时间戳（严禁续接上游连续序号）。环境可连库时用 UTF-8 执行 `uv run aerich upgrade`；受限时须显式标注「仅写文件、未执行迁移」。
2. **改 `manifest.json`**：前后端两份一起改；新权限码写入 `permissions`，跨模块引用声明 `module_references`；环境可用时同步目标应用 manifest，未执行须明示。
3. **前端联调配套**：路由、懒加载、默认只改 `zh-CN`（遵循 `i18n-zh-cn-only.mdc`）；列表导入传 `importHeaders` 等有效字段；状态列传 `statusEnum`。
4. **平台更新日志**：用户可见改动只在 `platformUpdateLog.ts` 的 `PLATFORM_UPDATE_LOG_GENERAL` 头部插一条并补 `zh-CN`（不维护域外 `platformUpdateLogDedicated.ts`）。
5. **多端改动**：同时触及 API/PC 与 `kuaigeyun-client/` 时更新 `principles/three-repo-map.md`；单端内部改动可跳过。

## 关联

- `../.cursor/rules/feature-delivery-checklist.mdc`
- `../.cursor/rules/platform-update-log.mdc`
- `principles/three-repo-map.md`
- `principles/reuse-existing-patterns.md`
