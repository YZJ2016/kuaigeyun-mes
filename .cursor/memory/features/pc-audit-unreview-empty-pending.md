---
title: PC 审核反审核空壳待审与补齐写回
slug: pc-audit-unreview-empty-pending
status: delivered
domain: approval
when: 修审核/反审核卡 PENDING、空壳待审、完成回调失败、revoke 无留痕、审批中心按钮可见性
keywords:
  - start_document_approval_or_raise
  - writeback_failure
  - revoke_noop
  - flow_completed
  - assert_manual_approval_action_allowed
  - purchase_order
  - process_route_change
standard: 启流程失败不得落 pending；完成回调失败写 instance.data.writeback_failure；cancel 对非 pending 记 revoke_noop；revoke verb 对齐 approve/reject 补齐
---

# PC 审核反审核空壳待审与补齐写回

## 目标

消除「状态已 PENDING、无审批实例」永久卡死，以及审批实例已结束但单据未写回时的审计静默。

## 何时读 / 禁止另起

- 何时读：审核提交启流程、完成回调写回、反审核、工艺路线变更 pending、审批实例列表按钮
- 禁止：再写一套 try/except 吞 start 失败；不要改 `audit_phase` auto 模式 pending 允许 submit/withdraw

## 标准入口

| 层 | 标准 |
|----|------|
| BE 启流程 | `audit_flow_guard.start_document_approval_or_raise`（先启再落 pending） |
| BE 门控 | `assert_manual_approval_action_allowed`（审核/驳回/反审核补齐） |
| BE 取消 | `ApprovalInstanceService.cancel_approval`（pending 真取消；否则 `revoke_noop` 历史） |
| FE 实例列表 | `current_approver_id === currentUser.id` 才显示同意/拒绝/转交 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 采购提交 | `riveredge-backend/src/apps/kuaizhizao/services/purchase_service.py` |
| 工艺变更 | `riveredge-backend/src/apps/master_data/services/process_route_change_service.py` |
| 实例服务 | `riveredge-backend/src/core/services/approval/approval_instance_service.py` |
| 门控 | `riveredge-backend/src/core/services/approval/audit_flow_guard.py` |
| 实例列表 | `riveredge-frontend/src/pages/system/approval-processes/instances/index.tsx` |

## 扩展点

1. 新单据提交审核：复用 `start_document_approval_or_raise`，禁止吞异常后写 PENDING
2. pending 扫描：短期 limit=500+warning；根治加 entity 冗余列/GIN

## 踩坑

- 销售/采购单张路由已由 `require_kuaizhizao_*_access` 按 path 映射 `audit`/`revoke`，B-11 属 informational
- 销售订单审核后副作用失败：落 `review_remarks` 补偿标记，未建 outbox（ponytail）

## 关联

- `principles/reuse-existing-patterns.md`
- 测试：`tests/apps/kuaizhizao/services/test_purchase_submit_audit_flow.py`、`tests/apps/master_data/services/test_process_route_change_submit.py`、`tests/core/services/approval/test_approval_completion_writeback.py`
