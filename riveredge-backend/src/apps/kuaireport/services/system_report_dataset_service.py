"""KRP-D6 系统报表专属数据集（spec 188）。

每张系统报表一条 ``core_datasets`` 行（``sysrep_<report_code>``），
走本租户 ``system_default`` 应用主库连接，SQL 自带 ``:tenant_id`` 条件。
种入与列表懒补齐共用 ``ensure_system_report_datasets``——按 (tenant_id, code) 幂等；
系统自有数据集按定义刷新 query_config / display_config，保证代码与库内口径一致。

查询条件约定：可选参数在 ``query_config.parameters`` 里声明默认 None，
SQL 写成 ``(:param::text IS NULL OR 条件)`` 容错形式——参数首次出现必须带
``::`` 显式类型，否则 PostgreSQL 无法推断 NULL 绑定参数的类型；
dateRange 拆 ``{key}_start`` / ``{key}_end``，前端发 ``YYYY-MM-DD`` 字符串，
参数保持 ``::text`` 并用 ``to_date()`` 转列比较（asyncpg 不给 date 绑定 str）。
与 ``execute_service._declared_parameter_keys`` 的放行规则一致。
"""

from __future__ import annotations

from typing import Any

from core.models.dataset import Dataset
from core.schemas.dataset import DatasetCreate
from core.services.data.dataset_service import DatasetService
from core.services.integration.integration_config_service import (
    IntegrationConfigService,
)

DATASET_CODE_PREFIX = "sysrep_"

# (field, label)。列名与下方 SQL 投影一一对应，同时写进数据集 display_config
# 与报表 report_config.fields，向导「检测字段」直接读到同一清单。
_DEF_INV_LEDGER_COLUMNS = (
    ("warehouse_code", "仓库编码"),
    ("warehouse_name", "仓库名称"),
    ("material_code", "物料编码"),
    ("material_name", "物料名称"),
    ("material_spec", "规格型号"),
    ("material_unit", "单位"),
    ("batch_no", "批次号"),
    ("production_date", "生产日期"),
    ("expiry_date", "失效日期"),
    ("quality_status", "质量状态"),
    ("quantity", "结存数量"),
    ("status", "批次状态"),
)

_DEF_WO_TRACKING_COLUMNS = (
    ("work_order_code", "工单号"),
    ("work_order_name", "工单名称"),
    ("product_code", "产品编码"),
    ("product_name", "产品名称"),
    ("sales_order_code", "销售订单号"),
    ("workshop_name", "车间"),
    ("work_center_name", "工作中心"),
    ("status", "工单状态"),
    ("priority", "优先级"),
    ("planned_quantity", "计划数量"),
    ("completed_quantity", "完工数量"),
    ("qualified_quantity", "合格数量"),
    ("unqualified_quantity", "不合格数量"),
    ("readiness_rate", "齐套率"),
    ("planned_start_date", "计划开工"),
    ("planned_end_date", "计划完工"),
    ("actual_start_date", "实际开工"),
    ("actual_end_date", "实际完工"),
)

_DEF_QC_PASS_RATE_COLUMNS = (
    ("inspection_type", "检验类型"),
    ("material_code", "物料编码"),
    ("material_name", "物料名称"),
    ("inspection_count", "检验批次数"),
    ("inspection_quantity", "检验数量"),
    ("qualified_quantity", "合格数量"),
    ("unqualified_quantity", "不合格数量"),
    ("pass_rate_pct", "合格率%"),
)

_DEF_PERF_STATS_COLUMNS = (
    ("worker_name", "员工"),
    ("team_name", "班组"),
    ("work_order_code", "工单号"),
    ("operation_name", "工序"),
    ("report_count", "报工次数"),
    ("reported_quantity", "报工数量"),
    ("qualified_quantity", "合格数量"),
    ("unqualified_quantity", "不合格数量"),
    ("work_hours", "工时"),
    ("qty_per_hour", "小时产出"),
)

_DEF_NODE_TIMELINESS_COLUMNS = (
    ("document_type", "单据类型"),
    ("document_code", "单据编号"),
    ("node_code", "节点编码"),
    ("node_name", "节点名称"),
    ("start_time", "开始时间"),
    ("end_time", "完成时间"),
    ("duration_hours", "耗时(小时)"),
    ("operator_name", "处理人"),
)

_DEF_PROCESS_EFFICIENCY_COLUMNS = (
    ("document_type", "单据类型"),
    ("node_code", "节点编码"),
    ("node_name", "节点名称"),
    ("node_runs", "处理次数"),
    ("avg_duration_hours", "平均耗时(小时)"),
    ("max_duration_hours", "最长耗时(小时)"),
    ("min_duration_hours", "最短耗时(小时)"),
)

_DEF_SALES_TRACE_COLUMNS = (
    ("sales_order_code", "销售订单号"),
    ("customer_name", "客户"),
    ("order_date", "下单日期"),
    ("delivery_date", "交期"),
    ("order_status", "订单状态"),
    ("review_status", "审核状态"),
    ("material_code", "物料编码"),
    ("material_name", "物料名称"),
    ("order_quantity", "订单数量"),
    ("delivered_quantity", "已发货数量"),
    ("remaining_quantity", "未发数量"),
    ("item_delivery_status", "行发货状态"),
    ("work_order_code", "关联工单号"),
    ("work_order_status", "工单状态"),
    ("wo_completed_quantity", "工单完工数量"),
    ("delivery_count", "发货次数"),
    ("last_delivery_time", "最近发货时间"),
)

_DEF_PURCHASE_TRACE_COLUMNS = (
    ("purchase_order_code", "采购订单号"),
    ("requisition_code", "采购申请号"),
    ("supplier_name", "供应商"),
    ("order_date", "下单日期"),
    ("delivery_date", "交期"),
    ("order_status", "订单状态"),
    ("review_status", "审核状态"),
    ("material_code", "物料编码"),
    ("material_name", "物料名称"),
    ("ordered_quantity", "订购数量"),
    ("received_quantity", "已收货数量"),
    ("outstanding_quantity", "未收数量"),
    ("receipt_count", "入库次数"),
    ("last_receipt_time", "最近入库时间"),
    ("inspection_count", "来料检验批次数"),
)

_DEF_MATERIAL_TRACE_COLUMNS = (
    ("trace_key", "追溯键"),
    ("trace_kind", "追溯类型"),
    ("material_code", "物料编码"),
    ("material_name", "物料名称"),
    ("event_type", "业务动作"),
    ("direction", "方向"),
    ("quantity", "数量"),
    ("source_type", "来源类型"),
    ("source_doc_code", "来源单号"),
    ("occurred_at", "发生时间"),
    ("operator_name", "操作人"),
)

_DEF_BIZ_OVERVIEW_COLUMNS = (
    ("metric", "指标"),
    ("value", "数值"),
)

# (key, label, control[, options])。key 即 SQL 命名参数名（dateRange 拆 _start/_end）。
_DEF_INV_LEDGER_PARAMS = (
    ("warehouse_code", "仓库编码", "text"),
    ("material_code", "物料编码", "text"),
    ("batch_no", "批次号", "text"),
    ("quality_status", "质量状态", "text"),
    ("production_date", "生产日期", "dateRange"),
)

_DEF_WO_TRACKING_PARAMS = (
    ("work_order_code", "工单号", "text"),
    ("product_code", "产品编码", "text"),
    ("sales_order_code", "销售订单号", "text"),
    ("status", "工单状态", "text"),
    ("planned_start_date", "计划开工", "dateRange"),
)

_DEF_QC_PASS_RATE_PARAMS = (
    (
        "inspection_type",
        "检验类型",
        "select",
        (
            {"label": "IQC", "value": "IQC"},
            {"label": "IPQC", "value": "IPQC"},
            {"label": "FQC", "value": "FQC"},
            {"label": "OQC", "value": "OQC"},
            {"label": "委外检验", "value": "委外检验"},
        ),
    ),
    ("material_code", "物料编码", "text"),
    ("inspection_time", "检验时间", "dateRange"),
)

_DEF_PERF_STATS_PARAMS = (
    ("worker_name", "员工", "text"),
    ("work_order_code", "工单号", "text"),
    ("work_start_time", "开工时间", "dateRange"),
)

_DEF_NODE_TIMELINESS_PARAMS = (
    ("document_type", "单据类型", "text"),
    ("document_code", "单据编号", "text"),
    ("start_time", "开始时间", "dateRange"),
)

_DEF_PROCESS_EFFICIENCY_PARAMS = (
    ("document_type", "单据类型", "text"),
    ("node_code", "节点编码", "text"),
)

_DEF_SALES_TRACE_PARAMS = (
    ("sales_order_code", "销售订单号", "text"),
    ("customer_name", "客户", "text"),
    ("order_status", "订单状态", "text"),
    ("order_date", "下单日期", "dateRange"),
)

_DEF_PURCHASE_TRACE_PARAMS = (
    ("purchase_order_code", "采购订单号", "text"),
    ("supplier_name", "供应商", "text"),
    ("order_status", "订单状态", "text"),
    ("order_date", "下单日期", "dateRange"),
)

_DEF_MATERIAL_TRACE_PARAMS = (
    ("trace_key", "追溯键", "text"),
    ("material_code", "物料编码", "text"),
    ("event_type", "业务动作", "text"),
    ("occurred_at", "发生时间", "dateRange"),
)

_DEF_BIZ_OVERVIEW_PARAMS: tuple = ()

# report_code -> (sql, columns, params)。SQL 约定：投影必须含 tenant_id 列
# （执行器外包 WHERE dataset_q.tenant_id 时引用它），表内仍写 :tenant_id 条件。
SYSTEM_REPORT_DATASETS: dict[
    str, tuple[str, tuple[tuple[str, str], ...], tuple]
] = {
    "inv_ledger": (
        """
SELECT
    b.tenant_id,
    w.code AS warehouse_code,
    COALESCE(b.warehouse_name, w.name) AS warehouse_name,
    m.code AS material_code,
    m.name AS material_name,
    m.specification AS material_spec,
    m.base_unit AS material_unit,
    b.batch_no,
    b.production_date,
    b.expiry_date,
    b.quality_status,
    b.quantity,
    b.status
FROM apps_master_data_material_batches b
LEFT JOIN apps_master_data_materials m
    ON m.id = b.material_id AND m.tenant_id = b.tenant_id AND m.deleted_at IS NULL
LEFT JOIN apps_master_data_warehouses w
    ON w.id = b.warehouse_id AND w.tenant_id = b.tenant_id AND w.deleted_at IS NULL
WHERE b.tenant_id = :tenant_id AND b.deleted_at IS NULL
    AND (:warehouse_code::text IS NULL OR w.code = :warehouse_code)
    AND (:material_code::text IS NULL OR m.code ILIKE '%' || :material_code || '%')
    AND (:batch_no::text IS NULL OR b.batch_no ILIKE '%' || :batch_no || '%')
    AND (:quality_status::text IS NULL OR b.quality_status = :quality_status)
    AND (:production_date_start::text IS NULL OR b.production_date >= to_date(:production_date_start, 'YYYY-MM-DD'))
    AND (:production_date_end::text IS NULL OR b.production_date < to_date(:production_date_end, 'YYYY-MM-DD') + 1)
ORDER BY warehouse_code, material_code, b.batch_no
""",
        _DEF_INV_LEDGER_COLUMNS,
        _DEF_INV_LEDGER_PARAMS,
    ),
    "wo_tracking": (
        """
SELECT
    w.tenant_id,
    w.code AS work_order_code,
    w.name AS work_order_name,
    w.product_code,
    w.product_name,
    w.sales_order_code,
    w.workshop_name,
    w.work_center_name,
    w.status,
    w.priority,
    w.quantity AS planned_quantity,
    w.completed_quantity,
    w.qualified_quantity,
    w.unqualified_quantity,
    w.readiness_rate,
    w.planned_start_date,
    w.planned_end_date,
    w.actual_start_date,
    w.actual_end_date
FROM apps_kuaizhizao_work_orders w
WHERE w.tenant_id = :tenant_id AND w.deleted_at IS NULL
    AND (:work_order_code::text IS NULL OR w.code ILIKE '%' || :work_order_code || '%')
    AND (:product_code::text IS NULL OR w.product_code ILIKE '%' || :product_code || '%')
    AND (:sales_order_code::text IS NULL OR w.sales_order_code ILIKE '%' || :sales_order_code || '%')
    AND (:status::text IS NULL OR w.status = :status)
    AND (:planned_start_date_start::text IS NULL OR w.planned_start_date >= to_date(:planned_start_date_start, 'YYYY-MM-DD'))
    AND (:planned_start_date_end::text IS NULL OR w.planned_start_date < to_date(:planned_start_date_end, 'YYYY-MM-DD') + 1)
ORDER BY w.created_at DESC
""",
        _DEF_WO_TRACKING_COLUMNS,
        _DEF_WO_TRACKING_PARAMS,
    ),
    "qc_pass_rate": (
        """
SELECT
    t.tenant_id,
    t.inspection_type,
    t.material_code,
    t.material_name,
    COUNT(*) AS inspection_count,
    COALESCE(SUM(t.inspection_quantity), 0) AS inspection_quantity,
    COALESCE(SUM(t.qualified_quantity), 0) AS qualified_quantity,
    COALESCE(SUM(t.unqualified_quantity), 0) AS unqualified_quantity,
    ROUND(
        COALESCE(SUM(t.qualified_quantity), 0)::numeric * 100
        / NULLIF(COALESCE(SUM(t.inspection_quantity), 0), 0),
        2
    ) AS pass_rate_pct
FROM (
    SELECT tenant_id, 'IQC' AS inspection_type, material_code, material_name,
        inspection_quantity, qualified_quantity, unqualified_quantity, inspection_time
    FROM apps_kuaizhizao_incoming_inspections
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL AND is_active = TRUE
    UNION ALL
    SELECT tenant_id, 'IPQC', material_code, material_name,
        inspection_quantity, qualified_quantity, unqualified_quantity, inspection_time
    FROM apps_kuaizhizao_process_inspections
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL AND is_active = TRUE
    UNION ALL
    SELECT tenant_id, 'FQC', material_code, material_name,
        inspection_quantity, qualified_quantity, unqualified_quantity, inspection_time
    FROM apps_kuaizhizao_finished_goods_inspections
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL AND is_active = TRUE
    UNION ALL
    SELECT tenant_id, 'OQC', material_code, material_name,
        inspection_quantity, qualified_quantity, unqualified_quantity, inspection_time
    FROM apps_kuaizhizao_oqc_inspections
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT tenant_id, '委外检验', material_code, material_name,
        inspection_quantity, qualified_quantity, unqualified_quantity, inspection_time
    FROM apps_kuaizhizao_outsource_inspections
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
) t
WHERE (:inspection_type::text IS NULL OR t.inspection_type = :inspection_type)
    AND (:material_code::text IS NULL OR t.material_code ILIKE '%' || :material_code || '%')
    AND (:inspection_time_start::text IS NULL OR t.inspection_time >= to_date(:inspection_time_start, 'YYYY-MM-DD'))
    AND (:inspection_time_end::text IS NULL OR t.inspection_time < to_date(:inspection_time_end, 'YYYY-MM-DD') + 1)
GROUP BY t.tenant_id, t.inspection_type, t.material_code, t.material_name
ORDER BY t.inspection_type, t.material_code
""",
        _DEF_QC_PASS_RATE_COLUMNS,
        _DEF_QC_PASS_RATE_PARAMS,
    ),
    "perf_stats": (
        """
SELECT
    r.tenant_id,
    r.worker_name,
    r.team_name,
    r.work_order_code,
    r.operation_name,
    COUNT(*) AS report_count,
    COALESCE(SUM(r.reported_quantity), 0) AS reported_quantity,
    COALESCE(SUM(r.qualified_quantity), 0) AS qualified_quantity,
    COALESCE(SUM(r.unqualified_quantity), 0) AS unqualified_quantity,
    COALESCE(SUM(r.work_hours), 0) AS work_hours,
    CASE
        WHEN COALESCE(SUM(r.work_hours), 0) > 0
        THEN ROUND(SUM(r.reported_quantity)::numeric / SUM(r.work_hours)::numeric, 2)
        ELSE NULL
    END AS qty_per_hour
FROM apps_kuaizhizao_reporting_records r
WHERE r.tenant_id = :tenant_id AND r.deleted_at IS NULL
    AND (:worker_name::text IS NULL OR r.worker_name ILIKE '%' || :worker_name || '%')
    AND (:work_order_code::text IS NULL OR r.work_order_code ILIKE '%' || :work_order_code || '%')
    AND (:work_start_time_start::text IS NULL OR r.work_start_time >= to_date(:work_start_time_start, 'YYYY-MM-DD'))
    AND (:work_start_time_end::text IS NULL OR r.work_start_time < to_date(:work_start_time_end, 'YYYY-MM-DD') + 1)
GROUP BY r.tenant_id, r.worker_name, r.team_name, r.work_order_code, r.operation_name
ORDER BY r.worker_name, r.work_order_code
""",
        _DEF_PERF_STATS_COLUMNS,
        _DEF_PERF_STATS_PARAMS,
    ),
    "node_timeliness": (
        """
SELECT
    t.tenant_id,
    t.document_type,
    t.document_code,
    t.node_code,
    t.node_name,
    t.start_time,
    t.end_time,
    t.duration_hours,
    t.operator_name
FROM apps_kuaizhizao_document_node_timings t
WHERE t.tenant_id = :tenant_id AND t.deleted_at IS NULL
    AND (:document_type::text IS NULL OR t.document_type = :document_type)
    AND (:document_code::text IS NULL OR t.document_code ILIKE '%' || :document_code || '%')
    AND (:start_time_start::text IS NULL OR t.start_time >= to_date(:start_time_start, 'YYYY-MM-DD'))
    AND (:start_time_end::text IS NULL OR t.start_time < to_date(:start_time_end, 'YYYY-MM-DD') + 1)
ORDER BY t.document_type, t.document_code, t.node_code
""",
        _DEF_NODE_TIMELINESS_COLUMNS,
        _DEF_NODE_TIMELINESS_PARAMS,
    ),
    "process_efficiency": (
        """
SELECT
    t.tenant_id,
    t.document_type,
    t.node_code,
    t.node_name,
    COUNT(*) AS node_runs,
    ROUND(AVG(t.duration_hours)::numeric, 2) AS avg_duration_hours,
    ROUND(MAX(t.duration_hours)::numeric, 2) AS max_duration_hours,
    ROUND(MIN(t.duration_hours)::numeric, 2) AS min_duration_hours
FROM apps_kuaizhizao_document_node_timings t
WHERE t.tenant_id = :tenant_id AND t.deleted_at IS NULL AND t.duration_hours IS NOT NULL
    AND (:document_type::text IS NULL OR t.document_type = :document_type)
    AND (:node_code::text IS NULL OR t.node_code = :node_code)
GROUP BY t.tenant_id, t.document_type, t.node_code, t.node_name
ORDER BY t.document_type, t.node_code
""",
        _DEF_PROCESS_EFFICIENCY_COLUMNS,
        _DEF_PROCESS_EFFICIENCY_PARAMS,
    ),
    "sales_trace": (
        """
SELECT
    so.tenant_id,
    so.order_code AS sales_order_code,
    so.customer_name,
    so.order_date,
    so.delivery_date,
    so.status AS order_status,
    so.review_status,
    soi.material_code,
    soi.material_name,
    soi.order_quantity,
    soi.delivered_quantity,
    soi.remaining_quantity,
    soi.delivery_status AS item_delivery_status,
    wo.code AS work_order_code,
    wo.status AS work_order_status,
    wo.completed_quantity AS wo_completed_quantity,
    d.delivery_count,
    d.last_delivery_time
FROM apps_kuaizhizao_sales_orders so
LEFT JOIN apps_kuaizhizao_sales_order_items soi
    ON soi.sales_order_id = so.id AND soi.tenant_id = so.tenant_id AND soi.deleted_at IS NULL
LEFT JOIN apps_kuaizhizao_work_orders wo
    ON wo.id = soi.work_order_id AND wo.tenant_id = so.tenant_id AND wo.deleted_at IS NULL
LEFT JOIN (
    SELECT tenant_id, sales_order_id,
        COUNT(*) AS delivery_count, MAX(delivery_time) AS last_delivery_time
    FROM apps_kuaizhizao_sales_deliveries
    WHERE deleted_at IS NULL
    GROUP BY tenant_id, sales_order_id
) d ON d.sales_order_id = so.id AND d.tenant_id = so.tenant_id
WHERE so.tenant_id = :tenant_id AND so.deleted_at IS NULL
    AND (:sales_order_code::text IS NULL OR so.order_code ILIKE '%' || :sales_order_code || '%')
    AND (:customer_name::text IS NULL OR so.customer_name ILIKE '%' || :customer_name || '%')
    AND (:order_status::text IS NULL OR so.status = :order_status)
    AND (:order_date_start::text IS NULL OR so.order_date >= to_date(:order_date_start, 'YYYY-MM-DD'))
    AND (:order_date_end::text IS NULL OR so.order_date < to_date(:order_date_end, 'YYYY-MM-DD') + 1)
ORDER BY so.order_date DESC, so.order_code
""",
        _DEF_SALES_TRACE_COLUMNS,
        _DEF_SALES_TRACE_PARAMS,
    ),
    "purchase_trace": (
        """
SELECT
    po.tenant_id,
    po.order_code AS purchase_order_code,
    rq.requisition_code,
    po.supplier_name,
    po.order_date,
    po.delivery_date,
    po.status AS order_status,
    po.review_status,
    poi.material_code,
    poi.material_name,
    poi.ordered_quantity,
    poi.received_quantity,
    poi.outstanding_quantity,
    pri.receipt_count,
    pri.last_receipt_time,
    iq.inspection_count
FROM apps_kuaizhizao_purchase_orders po
LEFT JOIN apps_kuaizhizao_purchase_order_items poi
    ON poi.order_id = po.id AND poi.tenant_id = po.tenant_id AND poi.deleted_at IS NULL
LEFT JOIN apps_kuaizhizao_purchase_requisition_items ri
    ON ri.purchase_order_item_id = poi.id AND ri.tenant_id = po.tenant_id AND ri.deleted_at IS NULL
LEFT JOIN apps_kuaizhizao_purchase_requisitions rq
    ON rq.id = ri.requisition_id AND rq.tenant_id = po.tenant_id AND rq.deleted_at IS NULL
LEFT JOIN (
    SELECT tenant_id, purchase_order_id,
        COUNT(*) AS receipt_count, MAX(receipt_time) AS last_receipt_time
    FROM apps_kuaizhizao_purchase_receipts
    WHERE deleted_at IS NULL
    GROUP BY tenant_id, purchase_order_id
) pri ON pri.purchase_order_id = po.id AND pri.tenant_id = po.tenant_id
LEFT JOIN (
    SELECT tenant_id, purchase_order_id, COUNT(*) AS inspection_count
    FROM apps_kuaizhizao_incoming_inspections
    WHERE deleted_at IS NULL AND purchase_order_id IS NOT NULL
    GROUP BY tenant_id, purchase_order_id
) iq ON iq.purchase_order_id = po.id AND iq.tenant_id = po.tenant_id
WHERE po.tenant_id = :tenant_id AND po.deleted_at IS NULL
    AND (:purchase_order_code::text IS NULL OR po.order_code ILIKE '%' || :purchase_order_code || '%')
    AND (:supplier_name::text IS NULL OR po.supplier_name ILIKE '%' || :supplier_name || '%')
    AND (:order_status::text IS NULL OR po.status = :order_status)
    AND (:order_date_start::text IS NULL OR po.order_date >= to_date(:order_date_start, 'YYYY-MM-DD'))
    AND (:order_date_end::text IS NULL OR po.order_date < to_date(:order_date_end, 'YYYY-MM-DD') + 1)
ORDER BY po.order_date DESC, po.order_code
""",
        _DEF_PURCHASE_TRACE_COLUMNS,
        _DEF_PURCHASE_TRACE_PARAMS,
    ),
    "material_trace": (
        """
SELECT
    t.tenant_id,
    t.trace_key,
    t.trace_kind,
    t.material_code,
    t.material_name,
    t.event_type,
    t.direction,
    t.quantity,
    t.source_type,
    t.source_doc_code,
    t.occurred_at,
    t.operator_name
FROM (
    SELECT
        l.tenant_id,
        l.serial_no AS trace_key,
        '序列号' AS trace_kind,
        m.code AS material_code,
        m.name AS material_name,
        l.movement_type AS event_type,
        l.direction,
        NULL::numeric AS quantity,
        l.source_type,
        l.source_doc_code,
        l.occurred_at,
        l.operator_name
    FROM apps_kuaizhizao_material_serial_document_ledgers l
    LEFT JOIN apps_master_data_materials m
        ON m.id = l.material_id AND m.tenant_id = l.tenant_id AND m.deleted_at IS NULL
    WHERE l.tenant_id = :tenant_id
    UNION ALL
    SELECT
        v.tenant_id,
        COALESCE(v.batch_no, v.material_code) AS trace_key,
        '批次' AS trace_kind,
        v.material_code,
        v.material_name,
        v.movement_type AS event_type,
        NULL AS direction,
        v.quantity,
        v.source_doc_type AS source_type,
        v.source_doc_code,
        v.created_at AS occurred_at,
        v.operator_name
    FROM apps_kuaizhizao_material_stock_movements v
    WHERE v.tenant_id = :tenant_id
) t
WHERE (:trace_key::text IS NULL OR t.trace_key ILIKE '%' || :trace_key || '%')
    AND (:material_code::text IS NULL OR t.material_code ILIKE '%' || :material_code || '%')
    AND (:event_type::text IS NULL OR t.event_type = :event_type)
    AND (:occurred_at_start::text IS NULL OR t.occurred_at >= to_date(:occurred_at_start, 'YYYY-MM-DD'))
    AND (:occurred_at_end::text IS NULL OR t.occurred_at < to_date(:occurred_at_end, 'YYYY-MM-DD') + 1)
ORDER BY t.occurred_at DESC
""",
        _DEF_MATERIAL_TRACE_COLUMNS,
        _DEF_MATERIAL_TRACE_PARAMS,
    ),
    "biz_overview": (
        """
SELECT t.tenant_id, t.metric, t.value, t.sort_no
FROM (
    SELECT :tenant_id AS tenant_id, '销售订单数' AS metric,
        COUNT(*)::numeric AS value, 1 AS sort_no
    FROM apps_kuaizhizao_sales_orders
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '销售金额合计',
        COALESCE(SUM(total_amount), 0)::numeric, 2
    FROM apps_kuaizhizao_sales_orders
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '生产工单数', COUNT(*)::numeric, 3
    FROM apps_kuaizhizao_work_orders
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '采购订单数', COUNT(*)::numeric, 4
    FROM apps_kuaizhizao_purchase_orders
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '采购金额合计',
        COALESCE(SUM(total_amount), 0)::numeric, 5
    FROM apps_kuaizhizao_purchase_orders
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '检验批次数', COUNT(*)::numeric, 6
    FROM (
        SELECT id, tenant_id, deleted_at FROM apps_kuaizhizao_incoming_inspections
        UNION ALL
        SELECT id, tenant_id, deleted_at FROM apps_kuaizhizao_process_inspections
        UNION ALL
        SELECT id, tenant_id, deleted_at FROM apps_kuaizhizao_finished_goods_inspections
        UNION ALL
        SELECT id, tenant_id, deleted_at FROM apps_kuaizhizao_oqc_inspections
        UNION ALL
        SELECT id, tenant_id, deleted_at FROM apps_kuaizhizao_outsource_inspections
    ) insp
    WHERE insp.tenant_id = :tenant_id AND insp.deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '库存批次数', COUNT(*)::numeric, 7
    FROM apps_master_data_material_batches
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '库存数量合计',
        COALESCE(SUM(quantity), 0)::numeric, 8
    FROM apps_master_data_material_batches
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '发货单数', COUNT(*)::numeric, 9
    FROM apps_kuaizhizao_sales_deliveries
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    UNION ALL
    SELECT :tenant_id, '采购入库单数', COUNT(*)::numeric, 10
    FROM apps_kuaizhizao_purchase_receipts
    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
) t
ORDER BY t.sort_no
""",
        _DEF_BIZ_OVERVIEW_COLUMNS,
        _DEF_BIZ_OVERVIEW_PARAMS,
    ),
}


def dataset_code_for(report_code: str) -> str:
    return f"{DATASET_CODE_PREFIX}{report_code}"


def _display_columns(columns: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    return [{"field": field, "label": label, "visible": True} for field, label in columns]


def _parameter_specs(params: tuple) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for item in params:
        key, label, control, *rest = item
        spec: dict[str, Any] = {
            "key": key,
            "label": label,
            "control": control,
            "required": False,
        }
        if rest and isinstance(rest[0], (list, tuple)):
            spec["options"] = [dict(option) for option in rest[0]]
        specs.append(spec)
    return specs


def _sql_param_defaults(params: tuple) -> dict[str, Any]:
    """query_config.parameters 默认 NULL——报表不带条件执行时命名参数仍能绑定。

    dateRange 在 SQL 里用 ``{key}_start`` / ``{key}_end`` 两个占位符。
    """
    defaults: dict[str, Any] = {}
    for item in params:
        key, _label, control = item[0], item[1], item[2]
        if control == "dateRange":
            defaults[f"{key}_start"] = None
            defaults[f"{key}_end"] = None
        else:
            defaults[key] = None
    return defaults


def system_report_config(
    dataset_uuid: str,
    columns: tuple[tuple[str, str], ...],
    params: tuple = (),
) -> dict[str, Any]:
    """向导形状的报表配置：dataset_uuid 直连平台数据集，可直接被向导编辑器回读。"""
    parameters = _parameter_specs(params)
    return {
        "chart_type": "table",
        "dataset_uuid": dataset_uuid,
        "fields": [
            {"field": field, "label": label, "visible": True, "x_axis": False, "y_axis": False}
            for field, label in columns
        ],
        "parameters": parameters,
        "interaction": {
            "drilldown": {
                "enabled": False,
                "dimension_field": None,
                "detail_chart_type": "table",
                "title": "明细下钻",
            },
            "global_filter_keys": [spec["key"] for spec in parameters],
        },
        "page_size": 50,
    }


def config_dataset_uuid(report_config: Any) -> str | None:
    if not isinstance(report_config, dict):
        return None
    raw = report_config.get("dataset_uuid")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _desired_query_config(sql: str, params: tuple) -> dict[str, Any]:
    return {"sql": sql, "parameters": _sql_param_defaults(params)}


def _desired_display_config(columns: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    return {"columns": _display_columns(columns)}


async def ensure_system_report_datasets(
    tenant_id: int, names: dict[str, str] | None = None
) -> dict[str, str]:
    """确保每张系统报表存在专属数据集。返回 report_code -> dataset_uuid。

    按 (tenant_id, code) 幂等；系统自有数据集（sysrep_*）的
    query_config / display_config / name 与定义不一致时按定义刷新。
    已软删的同名 code 会让 create_dataset 继续报已存在，
    此时直接查不到该行则让下层报错，不在这里重建。
    """
    ensured = await IntegrationConfigService.ensure_system_default(tenant_id)
    integration = ensured["item"]
    service = DatasetService()
    mapping: dict[str, str] = {}
    for report_code, (sql, columns, params) in SYSTEM_REPORT_DATASETS.items():
        code = dataset_code_for(report_code)
        existing = await Dataset.filter(
            tenant_id=tenant_id, code=code, deleted_at__isnull=True
        ).first()
        query_config = _desired_query_config(sql, params)
        display_config = _desired_display_config(columns)
        if existing is None:
            existing = await service.create_dataset(
                tenant_id,
                DatasetCreate(
                    name=(names or {}).get(report_code, code),
                    code=code,
                    description="系统报表专属数据集",
                    query_type="sql",
                    query_config=query_config,
                    output_type="list",
                    display_config=display_config,
                    is_active=True,
                    data_source_uuid=integration.uuid,
                ),
            )
        else:
            changed = False
            if existing.query_config != query_config:
                existing.query_config = query_config
                changed = True
            if existing.display_config != display_config:
                existing.display_config = display_config
                changed = True
            wanted_name = (names or {}).get(report_code)
            if wanted_name and existing.name != wanted_name:
                existing.name = wanted_name
                changed = True
            if changed:
                await existing.save()
        mapping[report_code] = str(existing.uuid)
    return mapping
