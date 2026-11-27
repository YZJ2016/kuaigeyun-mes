---
title: 多仓拓扑与跨端功能落点（私有 Fork）
slug: three-repo-map
status: active
domain: principle
when: 跨 PC/移动/工位/PRO 应用改功能、分不清真源在哪仓、要补跨端对照
keywords:
  - kuaigeyun-client
  - kuaigeyun-mes
  - 跨端
  - 仓库拓扑
  - X-Client-Channel
  - kuaicaiwu
standard: 业务代码单仓聚合在 kuaigeyun-mes；工程文档在外层 startech-mes；对照仓只读
---

# 多仓拓扑与跨端功能落点（私有 Fork）

- 跨仓总纲：`../AGENTS.md`
- 跨仓总索引：`../docs/00.doc-map.md`
- 本地 AOCI：仅维护本仓 `kuaigeyun-mes/.aoci/`（不与外层只读 `../kuaigeyun-aoci/` 合并或覆盖）

## 仓库职责（本私有 Fork 真实布局）

| 仓库 / 路径 | Git 角色 | 职责 |
| --- | --- | --- |
| 外层 `../`（`startech-mes`，`main`） | 项目总控与文档仓 | `AGENTS.md`、`docs/00.doc-map.md`、`docs/01..06/`（需求/设计/Spec/运维/上游同步台账）、`scripts/`（治理与上游同步脚本） |
| 主仓 `kuaigeyun-mes/`（`develop`） | 唯一业务实现主仓 | `riveredge-backend/`（FastAPI）、`riveredge-frontend/`（PC Web）、`kuaigeyun-client/`（移动 uni-app x + 工位 Electron 壳）、本仓内 4 个 PRO（`kuaiai`/`kuaireport`/`kuaiiot`/`kuaivision`）与免费行业包 |
| `../kuaigeyun-aoci/`（`develop`，只读） | 上游治理对照仓 | 对照上游 AOCI 意图与 `../kuaigeyun-aoci/.cursor/skills/`，禁止合入主仓 |
| `../kuaigeyun-dist/`（`develop`，只读） | 上游前端产物对照仓 | 对照上游已发布前端界面，禁止用于本机部署或合入主仓 |

### 本地架构真源约定

- **单仓聚合**：`kuaigeyun-client/` 与 4 个 PRO 应用均直接由 `kuaigeyun-mes/` 跟踪，**不再使用上游的 Junction / 独立 client 仓 / 独立 pro 仓模式**。
- **财务唯一权威**：`apps.kuaicaiwu` 为财务唯一权威，严禁引入上游平行 `apps.kuaizhizao.finance`。
- **客户定制域**：`haoligo` / `haolisales` / `funide_oa` 等不入本仓主线，保持 `.gitignore` 排除。

## 跨端功能落点表（核心域）

| 功能 | 后端 / PC Web（本仓） | 终端（本仓 `kuaigeyun-client/`） | 渠道 / 权限要点 | 记忆 |
| --- | --- | --- | --- | --- |
| 点检/保养方案绑定执行 | BE：`EquipmentSchemeBinding`；PC 点检单+保养计划页 | `riveredge-app-mobile/` 点检/保养执行；`riveredge-app-station/` 设备状态面板 | `equipment-spot-check:create` / `maintenance-plan`；渠道 pc/mobile/station | `features/equip-ops-scheme-bind-clients.md` + `maintenance-plan-scheme-bind.md` |
| 工位 ST2 安全与报工 | BE：`/apps/kuaizhizao/station/...`；头 `X-Station-Operator` | `riveredge-app-station/`（Electron 壳，业务页仍在 `riveredge-frontend/`） | 渠道 `station`；报工 `device_info.workstation_id` | `features/station-st2-security-contract.md` |
| 移动端 S2 门禁 | BE 对照：报工 `:assign`、仓储 `.../confirm` | `riveredge-app-mobile/`（uni-app x） | 渠道 `android`/`ios`/`mobile_h5`/`miniprogram` | `features/mobile-v2-s2-contract-fixes.md` |
| API 写防护 / 渠道头 | `interactive_client_guard`、`client_channel.py`；手册 `riveredge-backend/docs/api-write-protection-ops.md` | 各端写请求带 `X-Client-Channel` | `pc\|station\|android\|ios\|mobile_h5\|miniprogram\|integration` | `principles/api-write-protection.md` |
| 快数采 kuaiiot | 本仓 `riveredge-{backend,frontend}/src/apps/kuaiiot/`（已收归主仓） | - | 权限见前后端 `manifest.json`；MES 写回走 MesGuard | `features/kuaiiot-phased-hardening.md` |

## 交付时回写

- **多端改动**（改 API 且改 `kuaigeyun-client/`）：更新本表对应行，或新增/更新 `features/<slug>.md` 并在本表加链。
- **单端内部改动**：不必动本表。

## 关联

- `../AGENTS.md`
- `../docs/00.doc-map.md`
- `principles/mes-vault-index.md`
- `../.cursor/rules/feature-delivery-checklist.mdc`
