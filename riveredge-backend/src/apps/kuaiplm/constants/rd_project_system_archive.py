"""研发项目体系归档清单（R-01 #70 + 研发项目 PRD §2.13）。

真源：01-体系 §2.2.1 八类 + 10-研发项目 §2.13 阶段关联清单；模板字段来自 R01-归档三模板与样机制作书.xlsx。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, TypedDict


class RdSystemArchiveFillStatus(str, Enum):
    EMPTY = "empty"
    UPLOADED = "uploaded"
    LINKED = "linked"
    MISSING_MARKED = "missing_marked"


class RdSystemArchiveAcceptanceStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SystemArchiveTypeDef(TypedDict, total=False):
    code: str
    name: str
    sort_order: int
    modes: List[str]
    link_target_types: List[str]
    template_key: str
    description: str


# 01 八类 + 10 研发项目 §2.13 阶段项（新建项目 seed_for_project 自动补齐）
SYSTEM_ARCHIVE_TYPE_DEFINITIONS: List[SystemArchiveTypeDef] = [
    {
        "code": "project_proposal",
        "name": "项目建议书",
        "sort_order": 10,
        "modes": ["link"],
        "link_target_types": ["project_proposal"],
    },
    {
        "code": "design_task_plan",
        "name": "设计任务计划书",
        "sort_order": 20,
        "modes": ["upload"],
        "template_key": "design_task_plan",
    },
    {
        "code": "product_implementation_plan",
        "name": "产品实现方案书",
        "sort_order": 30,
        "modes": ["upload"],
        "template_key": "product_implementation_plan",
    },
    {
        "code": "drawing_design",
        "name": "图纸设计",
        "sort_order": 40,
        "modes": ["link"],
        "link_target_types": ["rd_deliverable"],
        "description": "关联丝印/总装/包装/线路板组件等生产图纸交付物",
    },
    {
        "code": "design_review",
        "name": "设计评审",
        "sort_order": 50,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
        "description": "关联设计开发/色彩合并/样机评审单",
    },
    {
        "code": "handboard_prototype_build",
        "name": "手板样机制作",
        "sort_order": 60,
        "modes": ["upload", "link"],
        "link_target_types": ["prototype_build_sheet"],
        "description": "手板阶段制作记录或关联 round=handboard 样机制作书",
    },
    {
        "code": "handboard_prototype_review",
        "name": "手板样机评审",
        "sort_order": 70,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
    },
    {
        "code": "t1_prototype_build",
        "name": "T1样机制作",
        "sort_order": 80,
        "modes": ["link"],
        "link_target_types": ["prototype_build_sheet"],
    },
    {
        "code": "t1_prototype_verify",
        "name": "T1样机验证",
        "sort_order": 90,
        "modes": ["link"],
        "link_target_types": ["lab_request", "rd_deliverable"],
    },
    {
        "code": "t1_prototype_review",
        "name": "T1样机评审",
        "sort_order": 100,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
    },
    {
        "code": "t2_prototype_build",
        "name": "T2样机制作",
        "sort_order": 110,
        "modes": ["link"],
        "link_target_types": ["prototype_build_sheet"],
    },
    {
        "code": "t2_prototype_verify",
        "name": "T2样机验证",
        "sort_order": 120,
        "modes": ["link"],
        "link_target_types": ["lab_request", "rd_deliverable"],
    },
    {
        "code": "t2_prototype_review",
        "name": "T2样机评审",
        "sort_order": 130,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
    },
    {
        "code": "t3_prototype_build",
        "name": "T3样机制作",
        "sort_order": 140,
        "modes": ["link"],
        "link_target_types": ["prototype_build_sheet"],
    },
    {
        "code": "t3_prototype_verify",
        "name": "T3样机验证",
        "sort_order": 150,
        "modes": ["link"],
        "link_target_types": ["lab_request", "rd_deliverable"],
    },
    {
        "code": "t3_prototype_review",
        "name": "T3样机评审",
        "sort_order": 160,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
    },
    {
        "code": "customer_confirmation",
        "name": "客户确认书",
        "sort_order": 170,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
    },
    {
        "code": "bom_release",
        "name": "BOM制作下发",
        "sort_order": 180,
        "modes": ["link"],
        "link_target_types": ["bom_collaboration"],
    },
    {
        "code": "material_confirmation",
        "name": "物料确认书下发",
        "sort_order": 190,
        "modes": ["link"],
        "link_target_types": ["kuaioa_form_request"],
    },
    {
        "code": "trial_production",
        "name": "试生产",
        "sort_order": 200,
        "modes": ["link"],
        "link_target_types": ["trial_flow"],
    },
    {
        "code": "project_summary",
        "name": "项目总结报告",
        "sort_order": 210,
        "modes": ["upload"],
        "template_key": "project_summary",
    },
    {
        "code": "qms_materials",
        "name": "体系资料",
        "sort_order": 220,
        "modes": ["upload", "link"],
        "link_target_types": ["rd_deliverable", "qms_system_document"],
        "description": "项目体系类受控资料，可上传或关联已有受控文件",
    },
    {
        "code": "product_tech_detail_sheet",
        "name": "产品技术资料明细表",
        "sort_order": 230,
        "modes": ["upload", "link"],
        "link_target_types": ["rd_deliverable"],
    },
    {
        "code": "sample_contact",
        "name": "打样联系单",
        "sort_order": 240,
        "modes": ["upload", "link"],
        "link_target_types": ["mold_sample_order", "kuaioa_form_request"],
    },
    {
        "code": "prototype_build_sheet",
        "name": "样机制作书",
        "sort_order": 250,
        "modes": ["link"],
        "link_target_types": ["prototype_build_sheet"],
        "template_key": "prototype_build_sheet",
    },
    {
        "code": "test_report",
        "name": "测试报告",
        "sort_order": 260,
        "modes": ["upload", "link"],
        "link_target_types": ["lab_request", "rd_deliverable"],
    },
]

SYSTEM_ARCHIVE_TYPE_BY_CODE: Dict[str, SystemArchiveTypeDef] = {
    str(d["code"]): d for d in SYSTEM_ARCHIVE_TYPE_DEFINITIONS
}

# 客户模板字段列（R01-归档三模板与样机制作书.xlsx）
SYSTEM_ARCHIVE_UPLOAD_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "design_task_plan": {
        "title": "设计任务计划书",
        "columns": [
            "项目代号",
            "项目名称",
            "任务内容",
            "责任人",
            "计划开始",
            "计划完成",
            "实际完成",
            "备注",
        ],
        "hint": "按甲方设计任务计划书模板填写后上传。",
    },
    "product_implementation_plan": {
        "title": "产品实现方案书",
        "columns": [
            "项目代号",
            "产品型号",
            "方案摘要",
            "评审结论",
            "新品评审表附件",
            "编制人",
            "日期",
        ],
        "hint": "可含新品评审表上传。",
    },
    "project_summary": {
        "title": "项目总结报告单",
        "columns": [
            "项目代号",
            "产品型号",
            "总结内容",
            "遗留问题",
            "编制人",
            "日期",
            "附件",
        ],
        "hint": "按甲方项目总结报告单模板填写后上传。",
    },
    "prototype_build_sheet": {
        "title": "样机制作书",
        "columns": [
            "单号",
            "项目代号",
            "产品型号",
            "相关要求文字",
            "图片附件清单",
            "其他附件",
            "电子填写人",
            "结构填写人",
            "制造意见",
            "质量意见",
            "状态",
        ],
        "hint": "流程：项目发起，电子与结构并行填写，审核下发制造样机组，制造与质量会签。",
    },
}

SYSTEM_ARCHIVE_TOTAL_COUNT = len(SYSTEM_ARCHIVE_TYPE_DEFINITIONS)
