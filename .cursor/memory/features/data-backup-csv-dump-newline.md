---
title: 数据备份 CSV dump 换行探测
slug: data-backup-csv-dump-newline
status: delivered
domain: system
when: 备份一开始失败、error_message 只有 read、进度条刚开始就失败
keywords:
  - data-backups
  - UnsupportedOperation
  - read
  - _ensure_binary_file_ends_with_newline
standard: COPY 用同线程 callback 写入 dump；换行只 write 不 read
---

# 数据备份 CSV dump 换行探测

## 目标

租户/全量逻辑备份第一张表 COPY 成功后不要立刻失败。

## 何时读 / 禁止另起

- 何时读：备份立刻失败、错误是 `read` 或 `UnsupportedOperation`
- 禁止：另写 pg_dump 客户端路径当默认备份

## 标准入口

| 层 | 标准 |
|----|------|
| BE | `run_backup_dump_and_zip` → `_export_tenant_csv_dump` / `_export_all_csv_dump` |

## 关键文件

| 角色 | 路径 |
|------|------|
| dump | `riveredge-backend/src/core/services/system/data_backup_jobs.py` |
| 失败落库 | `riveredge-backend/src/core/tasks/data_backup_handlers.py` |

## 踩坑

- `open(..., "wb")` 后 `file.read(1)` 在 Windows 上是 `UnsupportedOperation: read`
- 失败时 `backup.save()` 会把 Reporter 已写入的进度盖回 0
- 改代码后必须**杀干净** Taskiq 再拉起：Windows spawn 的 worker 子进程命令行没有 `taskiq`，旧 `kill_taskiq_processes` 会漏杀，残留进程仍跑旧代码，2 秒内失败且 worker.log 看不到这次任务
- 本地库偶发能过、远程必现：都是 `wb` + COPY 后 `read`；远程 COPY 线程写完文件仍不可读
- 切 `.env` 的 `DB_HOST` 后必须重启 API **和** Worker，否则任务连的还是旧库

## 关联

- `features/data-backup-stalled-reclaim.md`
