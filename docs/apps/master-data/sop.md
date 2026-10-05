# 标准操作 SOP（电子 + 纸质文控）

## 落点

基础数据 → 工艺 → **标准操作 SOP**（`/apps/master-data/process/sop`）。

同一套 SOP 身份（编码 + 工序/物料绑定）同时管理：

| 载体 | 说明 |
|------|------|
| `electronic` | 电子作业指导（ProFlow 步骤 + 可选报工采集） |
| `paper` | 纸质受控件：扫描 PDF/图片 + 存放位置 |
| `hybrid` | 电子步骤与纸质原件并存 |

**不**并入质量体系「体系文件」菜单；可选字段 `qms_document_uuid` 做单向引用。

## 文控状态

| 状态 | 含义 |
|------|------|
| `draft` | 草稿，可编辑 |
| `in_review` | 已提交，待审核 |
| `effective` | 现行有效，工位/报工仅匹配此状态 |
| `obsolete` | 已作废 |

流程：草稿 → 提交 → 审核通过 → **发布生效** →（升版回到草稿）→ 作废。

`is_active` 仍控制是否参与匹配；工位还要求 `control_status=effective`。

## 受控份（纸质）

- 仅 **生效中** SOP 可发放受控份（份号 `C-001` 起）。
- 升版发布时，原 `issued` 份自动变为 `pending_retrieve`，须回收或标记丢失。
- 权限：`dispatch` 发放、`recall` 回收、`print` 打印（受控/非受控水印）。

## 现场匹配

工位/报工/工单相关 SOP **同一套排序**（`collect_shopfloor_sops`）：

1. 绑该物料且工序精确
2. 绑该物料且未绑工序（适用全部工序）
3. 绑物料组且工序精确
4. 绑物料组且未绑工序
5. **未绑任何物料/组**且工序精确（已绑其他物料的 SOP 不得因同工序进入本档）

报工/工位择一：同档多份生效 SOP 视为配置错误，拒绝按编码静默取第一条。工单详情列表展示全部档位（不去重成一条）。

`route_uuids` / `bom_load_mode` 只用于从工艺路线批量生成，**不参与现场匹配**。

QC 材料 SOP（`sop_domain=qc`）与 PE 共用文控；工位默认 `pe`。检验/材料场景调用 `for-material?sopDomain=qc`。编码与绑定冲突按 **组织+业务域** 隔离。QC 菜单权限仍是 `master-data:process:sop:*`（同一模块，不另开权限码）。

`version` 与 `current_revision` 在创建/升版/发布时同步；现场确认绑修订号，展示读现行主行。

PC `SOPExecution` 是设计演练，不绑工单。现场真源：工位确认 + 报工 `sop_parameters`。

发布生效时强制 `is_active=true`。自定义字段逻辑表名 `master_data_sops`，物理表 `apps_master_data_sop`（注册表已互指）。

## 工位与确认

- 工位文档 API 返回 `carrier`、现行修订、存放位置、本工位份号（若已发放到该工位）。
- 纸质/混合优先展示受控扫描件；电子/混合仍展示 ProFlow 工步。
- 开工确认记录绑定 **SOP UUID + 修订号**；换版后须重新确认。
- PC 路径 `/process/sop/execution` 仅设计演练，不进入工位闭环。

## 与体系文件边界

| 项 | SOP | QMS 体系文件 |
|----|-----|--------------|
| 用途 | 工序+物料绑定的作业指导 | 质量手册/程序文件 |
| 编码 | `master_data_sop.code` | `document_code` |
| 现场匹配 | 工单/报工/工位 | 不直接匹配工序 |

## 权限（manifest）

`read/create/update/delete/submit/approve/reject/revoke/publish/obsolete/dispatch/recall/print/import/export`
