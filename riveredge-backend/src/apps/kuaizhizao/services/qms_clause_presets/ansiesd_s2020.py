from __future__ import annotations

from typing import List

from apps.kuaizhizao.services.qms_clause_presets.types import ClausePresetItem

# 标准代号与条款标题取自 ESDA 公开发布的目录结构（非标准正文）。
ANSI_ESD_S20_20_2021_STANDARD = "ANSI/ESD S20.20:2021"

ANSI_ESD_S20_20_2021_PRESET: List[ClausePresetItem] = [
    {"clause_code": "1", "title": "目的", "parent_code": None, "sort_order": 100},
    {"clause_code": "2", "title": "范围", "parent_code": None, "sort_order": 200},
    {"clause_code": "3", "title": "引用文件", "parent_code": None, "sort_order": 300},
    {"clause_code": "4", "title": "术语和定义", "parent_code": None, "sort_order": 400},
    {"clause_code": "5", "title": "人员安全", "parent_code": None, "sort_order": 500},
    {"clause_code": "6", "title": "ESD 控制方案", "parent_code": None, "sort_order": 600},
    {
        "clause_code": "6.1",
        "title": "ESD 控制方案要求",
        "parent_code": "6",
        "sort_order": 610,
    },
    {
        "clause_code": "6.2",
        "title": "ESD 控制方案管理者或协调人",
        "parent_code": "6",
        "sort_order": 620,
    },
    {"clause_code": "6.3", "title": "裁剪", "parent_code": "6", "sort_order": 630},
    {
        "clause_code": "7",
        "title": "ESD 控制方案管理要求",
        "parent_code": None,
        "sort_order": 700,
    },
    {
        "clause_code": "7.1",
        "title": "ESD 控制方案计划",
        "parent_code": "7",
        "sort_order": 710,
    },
    {"clause_code": "7.2", "title": "培训计划", "parent_code": "7", "sort_order": 720},
    {
        "clause_code": "7.3",
        "title": "产品鉴定计划",
        "parent_code": "7",
        "sort_order": 730,
    },
    {
        "clause_code": "7.4",
        "title": "符合性验证计划",
        "parent_code": "7",
        "sort_order": 740,
    },
    {
        "clause_code": "8",
        "title": "ESD 控制方案技术要求",
        "parent_code": None,
        "sort_order": 800,
    },
    {
        "clause_code": "8.1",
        "title": "接地/等电位连接系统",
        "parent_code": "8",
        "sort_order": 810,
    },
    {"clause_code": "8.2", "title": "人员接地", "parent_code": "8", "sort_order": 820},
    {
        "clause_code": "8.3",
        "title": "ESD 防护区（EPA）",
        "parent_code": "8",
        "sort_order": 830,
    },
    {"clause_code": "8.3.1", "title": "绝缘体", "parent_code": "8.3", "sort_order": 831},
    {
        "clause_code": "8.3.2",
        "title": "孤立导体",
        "parent_code": "8.3",
        "sort_order": 832,
    },
    {"clause_code": "8.4", "title": "包装", "parent_code": "8", "sort_order": 840},
    {
        "clause_code": "8.4.1",
        "title": "美国国防部（DoD）包装要求",
        "parent_code": "8.4",
        "sort_order": 841,
    },
    {"clause_code": "8.5", "title": "标识", "parent_code": "8", "sort_order": 850},
]
