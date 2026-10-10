---
title: 备份列表禁止解压 dump
slug: data-backup-list-no-zip-extract
status: delivered
domain: system
when: 备份页刷新卡死、Worker 状态未知、全平台备份后列表挂起
keywords:
  - data-backups
  - infer_source_tenant_id_from_zip
  - to_response
  - ERR 卡死
standard: 列表 to_response 不读 dump；详情只读 metadata.json；恢复再 dump 推断
---

# 备份列表禁止解压 dump

## 目标

全平台成功包（可达数百 MB）后，打开/刷新数据备份页不再卡死。

## 何时读 / 禁止另起

- 何时读：列表卡住、Worker「未知」、进度轮询把 API 打满
- 禁止：在 `get_backups` / `to_response` 里调用 `infer_source_tenant_id_from_zip`

## 标准入口

| 层 | 标准 |
|----|------|
| 列表 | `to_response(backup)` → `source_tenant_id` 用记录 `tenant_id`（all 为 null） |
| 详情 | `to_response(backup, enrich=True)` → 只读 zip 内 `backup_metadata.json` |
| 恢复 | `restore_backup` 内再 dump 推断 |
| FE | 有进行中任务时轮询不拉 `page_size=1000` |

## 踩坑

- 旧实现每条成功备份都整包解压 `database.dump`，再叠加 2.5s×1000 条轮询，API 与浏览器一起假死
- Worker「未知」常是健康检查被同池请求堵死，不是 worker 真离线
