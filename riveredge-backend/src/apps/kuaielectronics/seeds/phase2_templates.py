"""第二阶段行业包预置种子（真源：.custom/funide-oa/5.资料模板/用户提供）。

通用产品只保留中性框架；下列种子仅在启用 kuaielectronics 时写入租户。
"""

from __future__ import annotations

from typing import Any

from apps.kuaielectronics.seeds.annual_supplier_audit_clauses import (
    ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_CLAUSES,
    ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_CLAUSE_COUNT,
)

# 真源：生产/生产日报.xlsx 表头行
ELECTRONICS_PRODUCTION_DAILY_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_code": "line_daily",
        "template_name": "产线日报",
        "description": "行业预置：产线/班组生产日报（真源 生产/生产日报.xlsx）",
        "sort_order": 10,
        "field_schema": [
            {"key": "report_date", "label": "日期", "type": "text", "required": True},
            {"key": "shift_group", "label": "班组", "type": "text", "required": True},
            {"key": "process_step", "label": "作业工序", "type": "text", "required": False},
            {"key": "product_model", "label": "产品型号", "type": "text", "required": True},
            {"key": "work_order_no", "label": "配料单/返工单编号", "type": "text", "required": False},
            {"key": "work_order_qty", "label": "配料/返工单数量(只)", "type": "number", "required": False},
            {"key": "daily_completed_qty", "label": "当日完成数量(只)", "type": "number", "required": True},
            {"key": "start_time", "label": "开始时间", "type": "text", "required": False},
            {"key": "end_time", "label": "结束时间", "type": "text", "required": False},
            {"key": "deduct_hours", "label": "扣除工时(H)", "type": "number", "required": False},
            {"key": "actual_hours", "label": "实际用时(H)", "type": "number", "required": False},
            {"key": "project_name", "label": "项目名称", "type": "text", "required": False},
            {"key": "project_detail", "label": "项目明细", "type": "textarea", "required": False},
            {
                "key": "remarks",
                "label": "备注(返工、回流、加工时填写原因)",
                "type": "textarea",
                "required": False,
            },
        ],
    },
    {
        "template_code": "dadp_daily",
        "template_name": "DADP日报",
        "description": "行业预置：DA/DP 日报（真源 生产/DADP日报.xlsx）",
        "sort_order": 20,
        "field_schema": [
            {"key": "report_date", "label": "日期", "type": "text", "required": True},
            {"key": "shift_group", "label": "班组", "type": "text", "required": True},
            {"key": "product_model", "label": "产品型号", "type": "text", "required": True},
            {"key": "production_qty", "label": "生产数量", "type": "number", "required": True},
            {"key": "material_name", "label": "物料名称", "type": "text", "required": False},
            {"key": "da_defect", "label": "DA(来料不良)", "type": "number", "required": False},
            {"key": "dp_defect", "label": "DP(制程不良)", "type": "number", "required": False},
            {"key": "over_limit_reason", "label": "超标原因", "type": "textarea", "required": False},
            {"key": "dismantle_count_da", "label": "拆机数(DA)", "type": "number", "required": False},
            {"key": "dismantle_ratio_da", "label": "拆机比例(DA)", "type": "text", "required": False},
            {"key": "dismantle_count_dp", "label": "拆机数(DP)", "type": "number", "required": False},
            {"key": "dismantle_ratio_dp", "label": "拆机比例(DP)", "type": "text", "required": False},
        ],
    },
    {
        "template_code": "exception_daily",
        "template_name": "异常日报",
        "description": "行业预置：异常日报（真源 生产/异常日报.xlsx）",
        "sort_order": 30,
        "field_schema": [
            {"key": "report_date", "label": "日期", "type": "text", "required": True},
            {"key": "shift_group", "label": "班组", "type": "text", "required": True},
            {"key": "product_model", "label": "产品型号", "type": "text", "required": True},
            {"key": "exception_category", "label": "异常类别", "type": "text", "required": True},
            {"key": "equipment_material_name", "label": "设备/物料名称", "type": "text", "required": False},
            {"key": "exception_phenomenon", "label": "异常现象", "type": "textarea", "required": True},
            {"key": "start_time", "label": "开始时间", "type": "text", "required": False},
            {"key": "end_time", "label": "结束时间", "type": "text", "required": False},
            {"key": "deduct_hours", "label": "扣除工时(H)", "type": "number", "required": False},
            {"key": "actual_hours", "label": "实际耗时(H)", "type": "number", "required": False},
            {"key": "equipment_exception", "label": "设备异常", "type": "text", "required": False},
            {"key": "disposition", "label": "处置方式", "type": "textarea", "required": False},
            {"key": "responsible_person", "label": "责任人员", "type": "text", "required": False},
            {"key": "config_qty", "label": "配置数量", "type": "number", "required": False},
            {"key": "fault_qty", "label": "故障数量", "type": "number", "required": False},
            {"key": "yield_rate", "label": "直通率", "type": "text", "required": False},
            {"key": "disposition_person", "label": "处置人员", "type": "text", "required": False},
            {"key": "responsible_engineer", "label": "责任工程师", "type": "text", "required": False},
            {"key": "remarks", "label": "备注", "type": "textarea", "required": False},
        ],
    },
]

ELECTRONICS_PRODUCTION_DAILY_TEMPLATE_CODES = frozenset(
    t["template_code"] for t in ELECTRONICS_PRODUCTION_DAILY_TEMPLATES
)

# 真源：质量部/供方季度评价表.xlsx（条款已去客户专名，保留 EMS 评审语义）
ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE: dict[str, Any] = {
    "code": "electronics_quarterly_review",
    "name": "供方季度复审评定",
    "version": "v1",
    "grade_version": "v1",
    "period_type": "quarterly",
    "grade_bands": [
        {"min": 81, "grade": "A"},
        {"min": 71, "grade": "B"},
        {"min": 60, "grade": "C"},
        {"min": 0, "grade": "D"},
    ],
    "clauses": [
        {"line_no": 1, "clause_code": "Q01", "clause_name": "供方来料批次合格率", "weight": 1, "max_score": 10},
        {
            "line_no": 2,
            "clause_code": "Q02",
            "clause_name": "生产过程中发现异常时是否都能及时处理与回复",
            "weight": 1,
            "max_score": 10,
        },
        {
            "line_no": 3,
            "clause_code": "Q03",
            "clause_name": "环保管控从原材料、制程及设备均有管理要求及落实；第三方检测报告按期提供",
            "weight": 1,
            "max_score": 10,
        },
        {
            "line_no": 4,
            "clause_code": "Q04",
            "clause_name": "相关4M变更是否均按流程向需方提出",
            "weight": 1,
            "max_score": 10,
        },
        {
            "line_no": 5,
            "clause_code": "Q05",
            "clause_name": "是否制定对原材料供应商的选择标准及定期评估",
            "weight": 1,
            "max_score": 10,
        },
        {"line_no": 6, "clause_code": "D01", "clause_name": "准时交货率", "weight": 1, "max_score": 10},
        {
            "line_no": 7,
            "clause_code": "D02",
            "clause_name": "交货的准确性（包装、标识、数量、环保标识）",
            "weight": 1,
            "max_score": 10,
        },
        {
            "line_no": 8,
            "clause_code": "D03",
            "clause_name": "紧急订单时是否缩短生产周期及时保证交货",
            "weight": 1,
            "max_score": 10,
        },
        {
            "line_no": 9,
            "clause_code": "C01",
            "clause_name": "价格竞争力及与市场平均价格水平对比",
            "weight": 1,
            "max_score": 10,
        },
        {
            "line_no": 10,
            "clause_code": "S01",
            "clause_name": "沟通联络顺畅度与异常投诉处理及时性",
            "weight": 1,
            "max_score": 10,
        },
    ],
}

ELECTRONICS_SUPPLIER_EVAL_TEMPLATE_CODE = ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE["code"]

# 真源：质量部/供方年度评价表.xls「审核项目」（0-3 分，87 条）
ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE: dict[str, Any] = {
    "code": "electronics_annual_onsite_audit",
    "name": "供方年度现场审核",
    "version": "v1",
    "grade_version": "v1",
    "period_type": "annual",
    "grade_bands": [
        {"min": 90, "grade": "A"},
        {"min": 80, "grade": "B"},
        {"min": 70, "grade": "C"},
        {"min": 0, "grade": "D"},
    ],
    "clauses": ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_CLAUSES,
}

ELECTRONICS_SUPPLIER_EVAL_TEMPLATE_CODES = frozenset(
    {
        ELECTRONICS_SUPPLIER_EVAL_QUARTERLY_TEMPLATE["code"],
        ELECTRONICS_SUPPLIER_EVAL_ANNUAL_ONSITE_TEMPLATE["code"],
    }
)

PRODUCTION_FILE_CHECKLIST_CONFIG_KEY = "industry.ext.electronics.production_file_checklist"

# 真源：研发电子/OA系统模版.xls Sheet2（清单对照，不含客户人名）
ELECTRONICS_PRODUCTION_FILE_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {
        "item_code": "firmware_sample",
        "priority": "必须前期",
        "item_name": "产品固件表单/样例",
        "purpose": "固件上传、审核、下载与版本",
        "host_module": "kuaiplm.firmware",
    },
    {
        "item_code": "burn_prod_test_sample",
        "priority": "必须前期",
        "item_name": "烧录工具/产测文件样例",
        "purpose": "研发产测版本管理",
        "host_module": "kuaiplm.production_file",
        "catalog_kind": "rd_tool",
        "file_types": ["rd_burn_tool", "rd_prod_test"],
    },
    {
        "item_code": "drawing_spec_sample",
        "priority": "必须前期",
        "item_name": "图纸、产品规格书样例",
        "purpose": "电子侧图纸规格下发",
        "host_module": "kuaiplm.document",
    },
    {
        "item_code": "component_trial_form",
        "priority": "必须前期",
        "item_name": "元件试流单现行表",
        "purpose": "元件试流（经理/采购/生产）",
        "host_module": "kuaiplm.trial_flow",
    },
    {
        "item_code": "smt_application",
        "priority": "必须前期",
        "item_name": "样品SMT申请表",
        "purpose": "SMT钢网申请节点",
        "host_module": "kuaiplm.sample_process",
    },
    {
        "item_code": "smt_file_set",
        "priority": "必须前期",
        "item_name": "SMT文件集样例（Gerber/贴片BOM/坐标/丝印）",
        "purpose": "SMT文件归档",
        "host_module": "kuaiplm.rd_project",
    },
    {
        "item_code": "cob_role_list",
        "priority": "必须前期",
        "item_name": "COB角色名单",
        "purpose": "SMT提交COB权限",
        "host_module": "system.permission",
        "notes": "角色名单由租户在权限矩阵配置",
    },
    {
        "item_code": "material_spec_sample",
        "priority": "必须前期",
        "item_name": "材料部品规格书/软件开发规格书样例",
        "purpose": "文件类型对齐",
        "host_module": "kuaiplm.document",
    },
    {
        "item_code": "rd_layout_gerber",
        "priority": "必须前期",
        "item_name": "原理图、Layout、Gerber、拼版资料样例",
        "purpose": "电子侧设计资料归档",
        "host_module": "kuaiplm.document",
    },
    {
        "item_code": "material_review_rules",
        "priority": "必须前期",
        "item_name": "电子料评审表+优先使用/限用/禁止使用规则",
        "purpose": "电子料评审状态",
        "host_module": "kuaiplm.material_review",
    },
    {
        "item_code": "test_report_sample",
        "priority": "必须前期",
        "item_name": "测试报告样例（部品·整机）",
        "purpose": "测试报告归档与料号关联",
        "host_module": "kuaiplm.document",
    },
    {
        "item_code": "file_approval_roles",
        "priority": "必须前期",
        "item_name": "电子侧文件审批/下载角色",
        "purpose": "版本可见与提醒",
        "host_module": "system.permission",
        "notes": "审批与下载角色由租户在权限矩阵配置",
    },
    {
        "item_code": "bom_electronics_section",
        "priority": "必须前期",
        "item_name": "BOM中电子负责部分填报说明",
        "purpose": "与结构并行编辑BOM",
        "host_module": "kuaiplm.bom",
    },
]

ANNUAL_TRAINING_PLAN_CONFIG_KEY = "industry.ext.electronics.annual_training_plan"

# 真源：人事/04-01年度培训计划.pdf（仅表头，无样例行；FND/R-04-01，保存 3 年）
ELECTRONICS_ANNUAL_TRAINING_PLAN_PROFILE: dict[str, Any] = {
    "document_code": "FND/R-04-01",
    "document_title": "年度培训计划",
    "retention_years": 3,
    "approval_slots": ["编制", "审核", "批准"],
    "line_field_schema": [
        {"key": "line_no", "label": "序号", "type": "number"},
        {"key": "trainee_target", "label": "培训对象", "type": "text"},
        {
            "key": "training_content",
            "label": "培训项目、内容及要求",
            "type": "textarea",
            "required": True,
        },
        {"key": "training_department", "label": "培训部门", "type": "text"},
        {"key": "owner_name", "label": "责任人", "type": "text"},
        {"key": "due_date", "label": "要求完成期限", "type": "date"},
        {"key": "training_method", "label": "培训方式", "type": "text"},
        {"key": "evaluation_method", "label": "效果评估方式", "type": "text"},
        {"key": "remarks", "label": "备注", "type": "textarea"},
    ],
}

SUPPLIER_AUDIT_PLAN_CONFIG_KEY = "industry.ext.electronics.supplier_audit_plan"

# 真源：质量部/供方年度审核计划.xls「供应商监督审核计划」（排程表，非评价条款）
ELECTRONICS_SUPPLIER_AUDIT_PLAN_PROFILE: dict[str, Any] = {
    "plan_name_pattern": "{year}年供应商监督审核计划",
    "period_type": "annual",
    "default_audit_mode": "onsite",
    "default_template_code": "electronics_annual_onsite_audit",
    "default_supplier_grade": "A",
    "default_audit_form_label": "现场审核",
    "line_fields": [
        {"key": "line_no", "label": "序号", "type": "number"},
        {"key": "supplier_code", "label": "供应商代码", "type": "text"},
        {"key": "supplier_name", "label": "供应商", "type": "text", "required": True},
        {"key": "supplier_grade", "label": "供应商等级类别", "type": "text"},
        {"key": "audit_form", "label": "审核形式", "type": "text"},
        {"key": "auditor_name", "label": "审核人", "type": "text"},
    ],
    "month_tracking": {
        "months": list(range(1, 13)),
        "row_kinds": [
            {"key": "plan", "label": "计划"},
            {"key": "actual", "label": "实际"},
        ],
    },
    "quarterly_review_summary": {
        "title": "年供应商季度评审汇总表",
        "columns": [
            {"key": "line_no", "label": "序号"},
            {"key": "supplier_code", "label": "供应商代码"},
            {"key": "supplier_name", "label": "供应商"},
            {"key": "supplier_grade", "label": "供应商等级类别"},
            {"key": "auditor_name", "label": "审核人"},
            {"key": "q1_grade", "label": "第一季度"},
            {"key": "q2_grade", "label": "第二季度"},
            {"key": "q3_grade", "label": "第三季度"},
            {"key": "q4_grade", "label": "第四季度"},
        ],
    },
}

LICENSE_CATALOG_CONFIG_KEY = "industry.ext.electronics.license_catalog"

# 真源：IT及设备/证照/(2026年)公司证件类工作事项跟踪表_V3.xls（前 15 项合规事项；不含人名/具体日期）
ELECTRONICS_LICENSE_CATALOG_ITEMS: list[dict[str, Any]] = [
    {
        "item_code": "group_accident_insurance",
        "item_name": "团体意外伤害保险",
        "license_type": "vehicle_group_insurance",
        "renewal_frequency": "annual",
        "default_reminder_days": 30,
    },
    {
        "item_code": "canteen_food_hygiene",
        "item_name": "食堂食品卫生许可证",
        "license_type": "hygiene_permit",
        "renewal_frequency": "5year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "canteen_shop_agreement",
        "item_name": "食堂小卖部协议",
        "license_type": "canteen_agreement",
        "renewal_frequency": "2year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "solid_waste_contract",
        "item_name": "固体废弃物合同",
        "license_type": "waste_clearance_agreement",
        "renewal_frequency": "long_term",
        "default_reminder_days": 30,
    },
    {
        "item_code": "domestic_waste_contract",
        "item_name": "生活垃圾合同",
        "license_type": "waste_clearance_agreement",
        "renewal_frequency": "annual",
        "default_reminder_days": 30,
    },
    {
        "item_code": "kitchen_waste_contract",
        "item_name": "餐厨垃圾清运服务协议",
        "license_type": "waste_clearance_agreement",
        "renewal_frequency": "3year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "greening_contract",
        "item_name": "绿化合同",
        "license_type": "greening",
        "renewal_frequency": "3year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "canteen_staff_health",
        "item_name": "食堂人员健康证",
        "license_type": "hygiene_permit",
        "renewal_frequency": "annual",
        "default_reminder_days": 30,
    },
    {
        "item_code": "business_license_annual",
        "item_name": "工商营业执照年审",
        "license_type": "business_license_annual",
        "renewal_frequency": "annual",
        "default_reminder_days": 30,
    },
    {
        "item_code": "urban_drainage_permit",
        "item_name": "城镇污水排入排水管网许可证",
        "license_type": "urban_drainage_permit",
        "renewal_frequency": "5year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "pollution_discharge_receipt",
        "item_name": "固定污染源排污登记回执",
        "license_type": "pollution_discharge_receipt",
        "renewal_frequency": "5year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "sewage_treatment_contract",
        "item_name": "污水处理服务合同",
        "license_type": "sewage_treatment",
        "renewal_frequency": "annual",
        "default_reminder_days": 30,
    },
    {
        "item_code": "utility_insurance",
        "item_name": "天然气等设施保险",
        "license_type": "vehicle_group_insurance",
        "renewal_frequency": "annual",
        "default_reminder_days": 30,
    },
    {
        "item_code": "trademark_registration",
        "item_name": "商标注册证",
        "license_type": "trademark_registration",
        "renewal_frequency": "10year",
        "default_reminder_days": 30,
    },
    {
        "item_code": "foreign_investment_approval",
        "item_name": "外商投资企业批准证书",
        "license_type": "foreign_investment_approval",
        "renewal_frequency": "30year",
        "default_reminder_days": 30,
    },
]

# 真源：生产/上岗证.xls + 人事/ESD考核试卷 xls
ELECTRONICS_TRAINING_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_code": "electronics_work_license",
        "template_name": "上岗证",
        "template_kind": "training_record",
        "notes": "真源 生产/上岗证.xls：打印字段与考核行",
        "content_body": (
            '{"title":"上岗证","header_fields":['
            '{"key":"holder_name","label":"姓名"},'
            '{"key":"join_date","label":"进厂日期"}],'
            '"assessment_columns":['
            '{"key":"assessment_date","label":"考核日期"},'
            '{"key":"position_name","label":"岗位名称"},'
            '{"key":"assessor","label":"考核人"},'
            '{"key":"assessment_result","label":"考核结果"},'
            '{"key":"remarks","label":"备注"}]}'
        ),
    },
    {
        "template_code": "electronics_esd_exam_initial",
        "template_name": "ESD培训考核试卷（初次）",
        "template_kind": "exam_paper",
        "notes": "真源 人事/ESD（初次）考核试卷20241111（更新）.xls",
        "content_body": (
            '{"title":"ESD培训考核试卷（初次）","header_fields":["姓名","工号","部门"],'
            '"sections":[{"title":"单选题","total_points":40,"items":['
            '{"no":1,"question":"ESD含义是什么","options":["静电防护","静电","静电放电"]},'
            '{"no":2,"question":"下列哪个标识不属于ESD防护标识","options":["A","B","C"]},'
            '{"no":3,"question":"EPA的中文是什么","options":["静电放电保护区","ESD敏感器件隔离区","静电放电敏感物品放置区"]},'
            '{"no":4,"question":"下列不属于静电防护用品的是","options":["防静电腕带","防静电衣","防静电口罩"]},'
            '{"no":5,"question":"公司规定静电手环的点检频率为","options":["1天/次","4小时/次","1天/两次"]}'
            ']},{"title":"判断题","total_points":60,"items":['
            '{"no":1,"question":"装载敏感性元件及散料之物料架，无须接地。"},'
            '{"no":2,"question":"EAP内工作站之工作桌面均需铺上静电皮并接地。"},'
            '{"no":3,"question":"防静电桌垫，导电地垫，导电手环使用须确实接地。"},'
            '{"no":4,"question":"静电的定义是物质因失去或得到电子而带电。"},'
            '{"no":5,"question":"物料员拿未拆包装的敏感元器件不需要带静电腕带。"},'
            '{"no":6,"question":"以坐姿操作或接触产品时，作业人员必须穿戴好静电手环接地。"},'
            '{"no":7,"question":"PCB线路板或元器件可以暂时放在设备的金属表面上。"},'
            '{"no":8,"question":"在EPA区操作接触有静电敏感件及PCB板子，不一定要戴静电手环接地。"},'
            '{"no":9,"question":"不必要的绝缘材料不准带入EPA区。"},'
            '{"no":10,"question":"静电接地与电源接地为了方便可以接在一起。"}'
            ']}]}'
        ),
    },
    {
        "template_code": "electronics_esd_exam_periodic",
        "template_name": "ESD培训考核试卷（周期）",
        "template_kind": "exam_paper",
        "notes": "真源 人事/ESD（周期）考核试卷20241111（新增）.xls",
        "content_body": (
            '{"title":"ESD培训考核试卷（周期）","header_fields":["姓名","工号","部门"],'
            '"sections":[{"title":"单选题","total_points":30,"items":['
            '{"no":1,"question":"工厂建立ESD管理体系，目的是","options":["确保防静电物品持续有效","减少静电放电损害电子产品","防止静电引发爆炸等人员损害"]},'
            '{"no":2,"question":"不必要的绝缘体必须远离敏感器件至少多少厘米","options":["2.5","10","30"]},'
            '{"no":3,"question":"关于佩戴防静电腕带下列说法正确的是","options":["处理产品就必须佩戴静电腕带","在EPA区域内不需要佩戴静电腕带","佩戴静电腕带时腕带上的铁片必须与皮肤接触"]},'
            '{"no":4,"question":"以下哪种静电接地方式错误","options":["所有接触器件的物体采用等电位接地","以坐姿操作时穿戴好静电手环接地","以坐姿操作时穿戴好静电鞋与地面接地"]},'
            '{"no":5,"question":"有关EPA区域管理下面描述错误的是","options":["不必要的绝缘材料不准带入EPA区","不能隔离的绝缘材料须确定静电压小于125V","有完成EPA人员陪同的任何无关人员都可以进入EPA区域"]}'
            ']},{"title":"多选题","total_points":50,"items":['
            '{"no":1,"question":"以下哪些岗位作业时必须佩戴防静电腕带","options":["插件","总装外观检验","电性能维修"]},'
            '{"no":2,"question":"正确佩戴防静电腕带必须注意的事项有","options":["作业前点检静电腕带","腕带必须与皮肤接触","香蕉头必须插入接地插座"]},'
            '{"no":3,"question":"可能发生CDM损害的情况包括","options":["ESDS物料从包装管倒在金属工作台","无保护ESDS物料在金属托盘内","人员裸手取放ESDS物料"]}'
            ']}]}'
        ),
    },
]

ELECTRONICS_TRAINING_TEMPLATE_CODES = frozenset(
    t["template_code"] for t in ELECTRONICS_TRAINING_TEMPLATES
)
