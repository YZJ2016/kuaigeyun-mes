# 上游同步台账 `superset` 全量复核 · 交接文档

> 交接背景：R3–R5 摘取收口后的第二轮深度 review 发现一例真缺口，证明台账中
> `superset` 判定**不保证**文件无需摘取。需要对所有 `superset` 行做一次全量复核。
>
> 撰写日期：2026-11-26。适用仓库：`C:\workspaces-all\llm-workspaces\startech-mes\kuaigeyun-mes`。

## 1. 为什么必须复核（触发案例）

`riveredge-backend/migrations/models/1016_20261109143000_packing_binding_lines_audit_cols.py`
在台账中被标为 `superset`（本地被判定为上游该文件的超集），因此 R 批次未摘取。

**事实**：上游 1016 迁移是给 `packing_profiles` / `packing_binding_lines` 补 BaseModel
审计列（`created_by/created_by_name/updated_by/updated_by_name`）的**修复迁移**。本地
摘了上游建表迁移 `20261125120015_packing_hu_profile_lines.py` 但建表语句不含审计列，
ORM 模型却有这些字段 → 任何 `packing_profiles` 写入会数据库报错。已补本地迁移
`20261126000002_packing_audit_cols.py` 修复。

**结论**：`superset` 判定的语义是「评估时刻本地文件是上游 @sha_at_eval 的超集」，
但实际发生过误判/过时判定，**必须逐行重验，不能信任原判定**。

## 2. 台账结构

文件：`docs/上游同步-文件级台账.tsv`（由 `scripts/sync_upstream_audit.py` 维护）

```
列：upstream_path<TAB>sha_at_eval<TAB>verdict<TAB>note
verdict ∈ tracked | applied | superset | deferred | domain-out
```

- `sha_at_eval = <40位sha>`：评估时用的上游 blob/commit sha，文件在上游存在
- `sha_at_eval = DELETED`：上游 tip 无此路径（本地独有或上游已删）

## 3. 复核范围统计（当前 1036 行 superset）

### 3.1 有 sha 的 567 行 —— **重点复核对象**

| 目录 | 行数 | 优先级 |
|---|---|---|
| `riveredge-backend/src` | 254 | **P0** |
| `riveredge-frontend/src` | 204 | **P0** |
| `riveredge-backend/migrations` | 82 | **P0**（本案例所在） |
| `riveredge-backend/tests` | 16 | P1 |
| `fast-deploy/`、`riveredge-frontend/scripts` 等 | ~11 | P2 |

### 3.2 `DELETED` 的 469 行 —— 低风险抽查

| 前缀 | 行数 | 评估建议 |
|---|---|---|
| `.cursor/`（记忆库） | 199 | 本地独有资产，可信，抽查即可 |
| `riveredge-frontend` | 108 | **需逐条确认**：是「上游已删但本地仍在用」（合法保留）还是「本地漏删/上游改名」 |
| `riveredge-backend` | 55 | 同上 |
| `docs/` | 43 | 本地文档，低风险 |
| `.aoci/`、`aoci*.txt`、`AGENTS.md` | ~8 | 本地治理资产，可信 |
| `.merge-tmp/`、`*.py` 临时文件 | ~8 | 应清理的遗留产物 |

## 4. 复核方法（每个 sha 行）

**前提**：先 `git fetch gitee`（上游 remote 名 `gitee`，主分支 `develop`）。
工作区应为 `git status` 干净状态——本轮 review 修复可能尚未提交，先确认。

对每条 `superset` + 有 sha 行，执行「**上游该文件在 gitee/develop tip 的内容** vs
**本地文件内容**」的 diff，判断本地是否覆盖上游全部变更：

```bash
cd C:/workspaces-all/llm-workspaces/startech-mes/kuaigeyun-mes
git fetch gitee
# 单个文件
git diff gitee/develop -- <upstream_path>        # 本地 vs 上游 tip
git show gitee/develop:<upstream_path> | diff - <upstream_path>
```

注意：`sha_at_eval` 是**评估时刻**的 sha，不是上游 tip。直接用 `gitee/develop`
对照 tip 即可——若上游在评估后又有新变更且本地未摘，也算漏摘。

**判定分三类**：

| 判定 | 含义 | 台账回写 |
|---|---|---|
| `superset` 确认 | 本地确实覆盖上游全部内容（或分叉是有意的） | 保留 verdict，note 追加 `复核ok` |
| `partial`（漏摘） | 上游有本地没有的有效内容 | 摘取差异 → verdict 改 `applied`，note 注明补摘日期 |
| `deferred` | 差异存在但需用户决策（语义分叉） | 改 `deferred`，note 写明冲突点 |

**禁止**：脚本批量摘取（见 `.cursor/rules/no-batch-codemod.mdc`）；同分叉点改 >1 文件前
先试点验证。

## 5. 已知「有意分叉」清单（复核时勿误报为漏摘）

本地相对上游的**有意语义分叉**，复核遇到时直接判 `superset` 确认：

1. **委外让步接收**：`_execute_accept_concession_inbound`
   （`src/apps/kuaizhizao/services/defect_record_service.py:1509`）——检验单关联
   `outsource_material_receipt_id` 时**跳过入库单生成**（本地语义，防止委外件二次入账；
   上游会对 supplier 检验单自动建采购入库）。
2. **金蝶撤回同步钩子本地 patch 化**：`goods_receipt_service` 等撤回路径的
   `push_kingdee_*_withdraw` 在测试中全部 stub，本地实现有意保留。
3. **dept_uuids 多部门回填**：`data_scope_service.py` `_policy_to_q` /
   `data_scope_resolvers.py` `resolve_scope_department` 已按上游移植完毕
   （`dept_uuids: list[str]`），若 diff 只剩注释/格式差异即算确认。
4. **`tests/**/__init__.py` 包化**：本地 tests 全目录有 `__init__.py`（解决同名
   测试文件冲突），上游没有——不是漏摘。
5. **zh-CN.ts 615 行重复 updateLog key 已删**：本地比上游少了重复条目（上游文件
   本身也有重复），diff 显示「本地少行」是正常的。
6. **4 个死页面副本**（`production-execution/outsource-orders`、
   `outsource-work-orders`、`quality-management/iso-clauses`、
   `equipment-management/inspection`）：路由已重定向，上游已删，本地保留待用户决策
   （见 §7 待决项 3）。

## 6. 第二轮深度 review 已修的漏摘（供参照，勿重复处理）

- `purchase-requisitions/index.tsx`：补 uni-batch 导入、`resolveRequisitionIdFromSelectionKey`、
  `detailFlatRows` 状态、`runPurchaseRequisitionSubmitAfterSave`、
  `{purchaseRequisitionInitiatorModal}` 挂载（此前构建可过但运行时 ReferenceError——
  **esbuild 不做类型检查，同类文件复核时注意「用了但未 import」的标识符**）。
- `sales_order_service.py:189`：`dept_uuid` → `dept_uuids` + `department_uuids=`
- `data_scope_resolvers.py:47`：单数 dept → `department_uuids` 列表遍历
- `payment-applications/index.tsx`：payload 补 `paymentReason`
- `payment_application.py` schema：`payment_reason` 必填 + Create/Update 双 validator
- `migrations/models/20261126000002_packing_audit_cols.py`：补 packing 审计列

**复核技巧**：对前端文件，光 diff 不够——检查「使用了但无定义/未 import」的标识符
（本轮的发现都是这一类）。可用 `npx tsc --noEmit`（项目级，当前基线有 ~4 处
kuaicaiwu/共享组件既有错误可忽略）或对单文件快速 grep 未定义标识符。

## 7. 遗留待决策 MEDIUM 项（复核中遇到先挂起，等用户定）

1. 其他让步处置（`quarantine`/`downgrade`/`return`）是否同样跳过
   `outsource_material_receipt_id` 入库
2. `_resolve_accept_material_and_warehouse` 在委外跳过之前执行 → 委外让步仍强制
   选仓库，是否前移守卫
3. §5.6 的 4 个死页面是否删除（对齐上游）
4. `zh-CN.ts` ~1452 个孤儿 `updateLog.entries.*` i18n key（条目已删、key 残留）是否清理
5. `payment_application_po_header.py:92` `getattr(order,'invoice_status',None)` 死分支
   （上游同样存在，可能故意）

## 8. 验收标准

- 567 行 sha-superset 全部有复核结论（`复核ok` / 摘取 / `deferred`）
- DELETED 行中 `riveredge-*` 的 163 行逐条确认保留原因
- 复核完成后：`cd riveredge-backend && uv run pytest`（基线 4510 通过 / 0 失败 /
  19 skipped）+ `cd riveredge-frontend && npm run build`（基线通过，~7min）
- 台账 TSV 回写、修复提交（commit 风格参照 `git log`，附 Devin 署名 trailer）
