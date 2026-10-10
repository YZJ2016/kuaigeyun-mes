---
title: 编码规则页面配置加载加速
slug: code-rule-page-config-load
status: delivered
domain: code-rule
when: 新建单据/主数据编号预览慢、先拉 page-config 再 test-generate
keywords:
  - getCodeRulePageConfig
  - testGenerateCode
  - get_page_config_by_code
  - CODE_RULE_PAGES
  - invalidate_installed_application_codes_cache
standard: OperationFormModal + GET /code-rules/pages/{page_code}
---

# 编码规则页面配置加载加速

- 日期：2026-10-03
- 状态：已交付

## 目标

新建工序时编号预览不要先卡在「拉页面配置（含已安装应用）」上，本地规则先出预览。

## 何时读 / 禁止另起

- 何时读：其它主数据新建弹窗同样「先 page-config 再 test-generate」
- 禁止：安装态变更只靠 30s TTL 而不调失效函数

## 标准入口

- FE：`getPageRuleCode` / `isAutoGenerateEnabled` 立刻 `testGenerateCode`；`getCodeRulePageConfig` 并行校正
- BE：`get_page_config_by_code` 字典查找；`get_installed_application_codes` 30s 缓存

## 关键文件

| 角色 | 路径 |
|------|------|
| 工序弹窗 | `riveredge-frontend/src/apps/master-data/components/OperationFormModal.tsx` |
| 页面配置 API | `riveredge-backend/src/core/api/code_rules/code_rules.py` |
| 静态页索引 | `riveredge-backend/src/core/config/code_rule_pages.py` |
| 已安装应用缓存 | `riveredge-backend/src/core/services/system/installed_feature_scope.py` |
| 缓存失效 | `ApplicationService` 安装/卸载/启用/停用 |

## 扩展点

1. 其它主数据新建弹窗对齐工序：本地规则先预览
2. 安装态变更必须调 `invalidate_installed_application_codes_cache(tenant_id)`

## 过程

1. 瓶颈是串行：`getCodeRulePageConfig`（内部再查已安装应用）→ `testGenerateCode`
2. `CODE_RULE_PAGES` 线性扫描改为 `page_code` 字典
3. 已安装应用 30s 进程内缓存，生命周期变更失效

## 踩坑

- 打开新建工序：编号输入应在 `test-generate` 返回后即可填上，不必等 pages 接口
- 租户关闭自动编号时，pages 返回后会清空预览
- 安装/停用应用后 30s 内编码规则页过滤应立刻更新（因失效）

## 关联

- `principles/reuse-existing-patterns.md`
