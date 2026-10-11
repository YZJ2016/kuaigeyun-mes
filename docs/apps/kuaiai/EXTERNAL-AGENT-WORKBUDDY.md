# KU-Bridge 外部 Agent（WorkBuddy）对接说明（实验室）

> **实验室能力，非正式 GA。** 接口、工具名与配置字段可能变更；生产使用前请自行评估风险。

## 目标

让 WorkBuddy 等外部 Agent 经 **MCP** 只读访问租户 MES 数据，产品入口在 **KU-AI → 设置 → 外部 Agent（实验室）** 与 **能力矩阵 KU-Bridge**。

本能力**不是** MES「应用连接器」市场里的卡片；WorkBuddy 侧在 **企业 Connector 管理** 中登记 MCP URL。

## 架构

```text
WorkBuddy Agent
  → WorkBuddy 企业自定义连接器（HTTPS MCP）
  → kuaigeyun-pro/tools/workbuddy-mcp（Sidecar）
  → 开放 API（integration 渠道 + 应用 grants）
  → /api/v1/apps/kuaizhizao/* 只读 GET
```

## 启用步骤

1. 租户已安装并激活 **KU-AI**（专业版 License）。
2. **KU-AI → 设置**：打开「外部 Agent / WorkBuddy（实验室）」开关。
3. **基础设施 → 开放 API**：新建应用，仅勾选只读授权（首版建议）：
   - `kuaizhizao:sales-order:read`
   - `kuaizhizao:work-order:read`
   - `kuaizhizao:warehouse-management-inventory:read`（库存查询走报表接口）
4. 生产 `.env`：按需配置 `INTEGRATION_CLIENT_IP_ALLOWLIST`（MCP 服务器出口 IP）。
5. 部署 Sidecar：见 `kuaigeyun-pro/tools/workbuddy-mcp/README.md`。
6. WorkBuddy 管理后台：新建自定义连接器，MCP Server URL 指向 Sidecar HTTPS 地址。

## Sidecar 环境变量

| 变量 | 说明 |
|------|------|
| `RIVEREDGE_BASE_URL` | 例如 `https://your-host` |
| `OPEN_API_ACCT_ID` | 账套 ID |
| `OPEN_API_APP_ID` | 应用 ID |
| `OPEN_API_APP_SECRET` | 应用秘钥 |
| `OPEN_API_TENANT_ID` | 租户 ID（`X-Tenant-ID`） |

Sidecar 自动换票并缓存 Token；所有业务请求带 `X-Client-Channel: integration`。

## 首版 MCP 工具（只读）

| 工具 | 开放 API 路径 |
|------|----------------|
| `list_sales_orders` | GET `/api/v1/apps/kuaizhizao/sales-orders` |
| `get_sales_order` | GET `/api/v1/apps/kuaizhizao/sales-orders/{uuid}` |
| `list_work_orders` | GET `/api/v1/apps/kuaizhizao/work-orders` |
| `get_work_order` | GET `/api/v1/apps/kuaizhizao/work-orders/{uuid}` |
| `search_inventory` | GET `/api/v1/apps/kuaizhizao/reports/inventory/material-balances` |

## 禁止事项

- 勿用普通用户 JWT 或 PC 渠道对接 WorkBuddy。
- 勿将 WorkBuddy 配进 MES「应用连接器」并期望外打进 MES。
- 首版勿开放写操作、KU-Act、`propose_action` 经 integration 外放。
- 勿直连数据库；权限以开放 API grants 为准。

## 相关文档

- [API 写防护与开放 API 运维](../../riveredge-backend/docs/api-write-protection-ops.md)
- [KU-AI ROADMAP](./ROADMAP.md)
