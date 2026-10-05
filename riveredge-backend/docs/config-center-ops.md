# 配置中心运维说明

入口：前端 `/system/config-center`（别名 `/system/business-config`）。  
后端：`BusinessConfigService`（`infra/services/business_config_service.py`）+ `/infra/business-config`。

## 三类控制点（不要混用）

| 能力 | 真源 | 说明 |
|------|------|------|
| **模块/菜单是否可见** | 菜单管理 `is_active` + 角色权限 | **不是**配置中心开关 |
| **单据是否人工审核** | 配置中心「审核设置」`AuditDocumentBinding` | `check_audit_required(node_key)` |
| **业务参数 / 流程前置** | `Tenant.settings.business_config.parameters` | 容差、先采购申请、报工自动审核等 |
| **列表工具栏「同步/推送」显隐** | 角色功能权限 `:sync` / `:push` | 角色权限勾选；勿再配业务配置 |

## `check_node_enabled` 已废弃

- 方法签名保留，**恒返回 `True`**，业务 Service 中的调用不再构成门禁。
- 关功能请：菜单管理停用对应菜单，或收回权限码。
- 勿再新增「依赖 `check_node_enabled` 拦截建单」的逻辑。

## 已废弃参数

| 键 | 行为 |
|----|------|
| `parameters.sales.require_contract_before_order` | 读取时剥离；写入拒绝；默认值已移除 |
| `parameters.warehouse.multi_unit` | 读取时剥离；写入拒绝；未接业务门禁（换算走主数据单位因子） |

存量租户若曾写入 `true`，读配置后不再生效，销售订单创建不再被该键阻断。

## 参数与 UI

- 配置页树：`riveredge-frontend/src/pages/system/config-center/configTree.ts`
- 后端已实装键：`IMPLEMENTED_PARAMETER_KEYS`（前端可据此灰掉假开关）
- 新增可配参数时：同步 `PARAMETER_SCHEMA` / `DEFAULT_PARAMETERS` / `PARAMETER_KEYS`（或 `PROCESS_KEYS`）/ `IMPLEMENTED_PARAMETER_KEYS` / `configTree.ts` / zh-CN·en-US 文案

## 相关页面

- 详情抽屉参数（全链路等）：`/apps/kuaizhizao/timeconfig`（不在配置中心主 Tab）
