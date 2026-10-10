---
title: 定时任务执行：租户隔离缺 event
slug: scheduled-task-tenant-isolation-event
status: delivered
domain: scheduler
when: 定时任务「未能重启/不执行」、worker 报缺少 event、with_tenant_isolation
keywords:
  - scheduled-task/execute
  - with_tenant_isolation
  - Taskiq
  - scheduled_task_executor
  - _extract_event
standard: Taskiq scheduled-task/execute + with_tenant_isolation
---

# 定时任务执行：租户隔离缺 event

- 日期：2026-10-03
- 状态：已交付

## 目标

修复业务侧定时任务被 scheduler 投递后执行器立即失败（看似「未能重启/不执行」）的问题。

## 何时读 / 禁止另起

- 何时读：新事件工作流、定时任务调度骨架
- 禁止：另写调度循环；handler 签名不要离开单参 `event`

## 标准入口

- FE：系统/业务配置 → 定时任务
- BE：`scheduled_tasks_minute_tick` → `run_scheduled_task_scheduler_tick` → `dispatch_event(scheduled-task/execute)` → `scheduled_task_executor_function`
- 运行依赖：Taskiq worker + scheduler（`.logs/worker.pid` / `scheduler.pid`）

## 关键文件

| 角色 | 路径 |
|------|------|
| 租户隔离 | `riveredge-backend/src/core/utils/workflow_tenant_isolation.py` |
| 调度 tick | `riveredge-backend/src/core/workflows/functions/scheduled_task_scheduler.py` |
| 执行器 | `riveredge-backend/src/core/workflows/functions/scheduled_task_executor.py` |
| dispatcher | `riveredge-backend/src/core/tasks/dispatcher.py`（单参 `handler(event)`） |
| 回归测试 | `riveredge-backend/tests/core/utils/test_workflow_tenant_isolation.py` |

## 扩展点

1. 新事件工作流：`@workflow_client.create_function` + `@with_tenant_isolation`，函数签名保持单参 `event`
2. 内置任务：挂 `scheduled_job_registry` / handlers，不另写调度骨架

## 过程

1. 查 `.logs`：scheduler 在投递，worker 对 `scheduled_task_executor_function` 报「缺少 event」
2. 根因：`_run_handler` 对 `@wraps` 后单参 handler 直传 `TaskEvent`；旧 `with_tenant_isolation` 只认 `ctx.event`
3. 增加 `_extract_event`，兼容直传 event 与 `TaskContext.event`

## 踩坑

- 本机若仅有 stale pidfile、无 taskiq 进程，定时任务也不会跑；需 `launch.dev.sh` / wizard 重启 worker+scheduler
- 验收：`pytest tests/core/utils/test_workflow_tenant_isolation.py`；worker 日志不再出现「缺少 event」

## 关联

- `principles/reuse-existing-patterns.md`
- `features/fast-deploy-scripts.md`
