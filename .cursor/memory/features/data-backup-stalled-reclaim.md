---
title: 数据备份堆积回收
slug: data-backup-stalled-reclaim
status: delivered
domain: system
when: 改数据备份队列、Worker 堆积、pending 卡死
keywords:
  - data-backups
  - reclaim-stalled
  - 任务堆积
standard: DataBackupService.reclaim_stalled_backups + POST /core/data-backups/reclaim-stalled
---

# 数据备份堆积回收

## 目标

pending 卡住不再靠人手删记录；并发备份排队而不是直接失败。

## 何时读 / 禁止另起

- 何时读：备份 Worker「任务堆积」、队列重投、advisory lock
- 禁止：再写第二套备份队列或前端轮询自己 kiq

## 标准入口

| 层 | 标准 |
|----|------|
| FE | 堆积时「重试堆积任务」→ `reclaimStalledBackups` |
| BE | `DataBackupService.reclaim_stalled_backups`；`data_backup_reclaim_tick` 每 2 分钟 |
| Handler | 锁冲突保持 pending；进行中且 30 分钟内有进度则跳过重入 |

## 关键路径

- `data_backup_service.py` / `data_backup_handlers.py` / `taskiq_app.py` / `data_backups.py`

## 过程要点

1. 堆积 = pending>2min 且 10min 无完成；常见是 LISTEN 丢通知或 worker 挂了
2. 定时回收只 NOTIFY pending 备份消息，禁止回滚 processing（长 COPY 会误伤）
3. 抢锁失败在 handler 内 sleep 重试（消息保持 processing）；超时才 pending
4. running 是否死亡看 advisory lock，不看 30 分钟无进度
5. 查队列失败当作已有消息，禁止再 kiq

## 关联原则

- [[principles/reuse-existing-patterns|复用优先]]
