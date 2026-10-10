---
title: 平台管理员全平台租户备份
slug: data-backup-platform-all-tenants
status: delivered
domain: system
when: 平台管理员要备份全部租户、backup_scope=all、组织管理员不该看到全平台包
keywords:
  - data-backups
  - backup_scope
  - is_infra_admin
  - 全平台
standard: 创建弹窗仅平台管理员可选「全平台所有组织」；记录 tenant_id 为空
---

# 平台管理员全平台租户备份

## 目标

平台管理员可导出全部租户业务表，也可为指定组织打租户级备份；组织管理员仍只能打当前组织。

## 何时读 / 禁止另起

- 何时读：全平台备份、backup_scope=all、平台管理员给租户备份、target_tenant_id
- 禁止：再写一套备份创建 API；不要把全平台 zip 挂在某个组织 tenant_id 下；不要要求平台管理员先「切换租户」才能租户备份

## 标准入口

| 层 | 标准 |
|----|------|
| FE | 创建弹窗：`backup_scope` +（tenant 时）`target_tenant_id` 选组织，仅 `is_infra_admin` |
| BE | `POST /core/data-backups`：infra 可用 `target_tenant_id`；`all` 写 `tenant_id=None` |
| 导出 | `_export_tenant_csv_dump` / `_export_all_csv_dump` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 弹窗 | `riveredge-frontend/src/pages/system/data-backups/index.tsx` |
| Schema | `riveredge-backend/src/core/schemas/data_backup.py` |
| API | `riveredge-backend/src/core/api/data_backups/data_backups.py` |
| 服务 | `riveredge-backend/src/core/services/system/data_backup_service.py` |

## 踩坑

- 全平台包若写入当前租户，该组织管理员能下载到所有租户数据
- 平台账号常无 `tenant_id=null`；租户级必须显式传 `target_tenant_id`，不能再要求「先切换组织」
- 权限判断用 `is_infra_admin` 标志（`_is_platform_backup_admin`），不要用 `is_infra_admin_user()`：后者要求 `tenant_id is None`，切换进组织后会误判成非平台管理员
- 可见性：`all` 仅平台管理员；`tenant` = 归属组织 + 平台管理员（列表/详情/下载/worker-health 同一套）
- 平台管理员列表必须 `DataBackup.all()`：指定组织备份挂在目标 `tenant_id`，若只查「当前租户|null|all」会创建成功却看不见
- 组织侧列表：`tenant_id=当前` 且 `exclude(backup_scope=all)`，防止误挂全平台包泄露
- Windows 默认关热重载（`RIVEREDGE_DEV_RELOAD`）；改列表过滤后须重启 8201（Caddy:8080 反代目标），只 touch `main.py` 不生效
- 本环境平台账号是 `InfraSuperAdmin`（`core_users.is_infra_admin` 可为 0），靠虚拟用户 `is_infra_admin=True`
