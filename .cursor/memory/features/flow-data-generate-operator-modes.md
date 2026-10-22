---
title: 流程造数真实 MES 仿真契约
slug: flow-data-generate-operator-modes
status: delivered
domain: kuaizhizao-ops
when: 改流程造数、sim_mode、场景段、BusinessClock、Kit 预检、操作用户、质检旁路
keywords:
  - flow-data-generate
  - flow_sim
  - BusinessClock
  - sim_mode
  - scenarios
  - Kit
  - StepOperatorConfig
  - force_simple_when_unset
  - allow_skip_iqc
  - flow_end_at
  - mrp_push
  - purchase_inbound
  - wo_complete
  - owo_fulfill
  - ship
standard: flow_sim（clock/modes/scenarios/kit/engine）+ FlowDataGenerateService 薄编排；真实/填数隔离；预览执行共用 TimelinePlanner.for_request
---

# 流程造数真实 MES 仿真契约

## 目标

验收级真实仿真为主：场景剧本 + 现有业务 Service + 单一 `BusinessClock`。快速填数另开 `sim_mode=fill`，禁止与真实路径共享压缩/旁路。

## 何时读 / 禁止另起

- 何时读：扩展造数场景、时钟、Kit、模式门禁、步骤操作人、质检造数。
- 禁止：在真实模式再开 `flow_end_at` 压缩；`force_simple_when_unset=True` 默认真仿真；另写库存/质检旁路实现；预览与执行各推一套时间逻辑。

## 架构（真源目录）

| 层 | 路径 |
|----|------|
| 时钟 | `services/flow_sim/clock.py` → `BusinessClock`；服务内 `TimelinePlanner` 为其兼容子类 |
| 模式 | `flow_sim/modes.py`：`real` / `fill`；`apply_mode_gates` |
| 场景 | `flow_sim/scenarios.py`：`mrp_push` / `purchase_inbound` / `owo_fulfill` / `wo_complete` / `ship` |
| Kit | `flow_sim/kit.py`：BOM + 工艺 + 标准工时硬拦（真实模式） |
| 步骤目录 | `flow_sim/steps/*.py`（适配器目录；执行仍调 Service） |
| 编排 | `flow_sim/engine.py` + `FlowDataGenerateService.execute` |
| FE | `pages/.../flow-data-generate/index.tsx`：`sim_mode` + `scenarios` |
| API | `management.FlowGenerateBody.sim_mode` / `scenarios` |

## 模式隔离

| | `real`（默认） | `fill` |
|--|----------------|--------|
| `flow_end_at` | **清空/忽略**，不挂 deadline | 允许时间窗均摊 |
| `allow_skip_iqc` | **强制 False** | 按请求 |
| 强制简易质检 | **禁止**（`force_simple_when_unset=False`） | 可开（当前仍默认 False） |
| 时钟 | 工作时段 + 标准工时 `advance_capped` | 可 `remaining_events` 压缩 |
| Kit 缺项 | `blocking` 禁止开跑 | warning |

`preview` / `execute` / `precheck` 入口均先 `apply_mode_gates(req)`，再 `TimelinePlanner.for_request(...)`。

## 场景串联（唯一步骤真源）

一键全链路 = 顺序跑 `FULL_CHAIN_SCENARIOS`。UI **只勾场景**，不再另勾「生成步骤」；`map_steps_for_scenarios` 忽略页面旧 `steps` 勾选。进度/失败文案带场景 ID。

| 场景 ID | 覆盖 |
|---------|------|
| `mrp_push` | 需求计算 → 下推 WO/PO/OWO（`purchase` 入库开关不打开） |
| `purchase_inbound` | 审 PO → IQC/直入 → 入库确认 |
| `owo_fulfill` | 委外下达 → 补库 → 发料 → 收货 |
| `wo_complete` | 补库 → 领料 → 报工 → IPQC → FQC → 成品入 |
| `ship` | 发货通知/出库 |

单段采购/工单/委外：须已跑过 `mrp_push` 或带 `resume_run_id`；否则硬失败提示勾选/续跑。

## 时间改写（纠偏）

- **真实模式**：`preserve_business_dates=True`，只对齐系统戳/单号日期/操作日志；业务日保留创建时写入
- **填数模式**：可全量压到时间窗时刻

## 操作人模式

| mode | 参数 | 行为 |
|------|------|------|
| `random_role` | `role_code?` | 角色下激活用户随机 |
| `random_department` | `department_id` | 部门下随机 |
| `random_team` | `work_group_id` | 工作小组随机 |
| `operation_assigned` | — | 报工按工序派工/档案；其它工序池 |
| `fixed` / `current` | `user_id` / — | 指定 / 当前用户 |

`random_*` 空池：预检 `EMPTY_OPERATOR_POOL` + 执行抛错。

## 质检 / 委外 / 失败

- 质检：`force_simple_when_unset=False`；`none` → 跳过/直入库；其它失败仅 fill + `allow_skip_iqc` 旁路。
- 委外：`_step_outsource_fulfillment`；已收齐跳过。
- 业务失败：整轮失败 + `run_id` 续跑；撤回按段软删，已过账提示业务反审。
- `DocumentTimeRewriteService`：**纠偏/对齐**，不作主路径时钟。

## 预检硬拦（节选）

无工艺 / 无 BOM / 无标准工时（真实 Kit）/ 无供应商 / `AUTO_WO_DISABLED` / 空操作人池。

## BOM 下级自制件工序

预览/预检须展开订单行成品的 **BOM 生产树**（`build_production_tree_for_demand_item` + `flatten_production_tree`），每个 `Make` 节点解析工艺工序；候选列表带 `bom_level`（0=成品，>0=下级）。禁止只展示行物料工序而漏下级。

## 异步执行

`POST .../flow-generate` → job；`GET .../jobs/{id}` 轮询。造数页不进平台更新日志。
