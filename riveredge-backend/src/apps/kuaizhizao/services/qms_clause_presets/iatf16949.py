from __future__ import annotations

from typing import List

from apps.kuaizhizao.services.qms_clause_presets.iso9001 import ISO9001_2015_PRESET
from apps.kuaizhizao.services.qms_clause_presets.types import ClausePresetItem

IATF16949_2016_STANDARD = "IATF16949:2016"

_IATF_EXTRA: List[ClausePresetItem] = [
    {"clause_code": "8.1.1", "title": "运行策划和控制 补充", "parent_code": "8.1", "sort_order": 811},
    {"clause_code": "8.1.2", "title": "保密", "parent_code": "8.1", "sort_order": 812},
    {"clause_code": "8.2.1", "title": "顾客沟通 补充", "parent_code": "8.2", "sort_order": 821},
    {"clause_code": "8.2.2", "title": "产品和服务要求的确定", "parent_code": "8.2", "sort_order": 822},
    {"clause_code": "8.2.3", "title": "产品和服务要求的评审", "parent_code": "8.2", "sort_order": 823},
    {"clause_code": "8.3.1", "title": "设计和开发策划 补充", "parent_code": "8.3", "sort_order": 831},
    {"clause_code": "8.3.2", "title": "设计和开发输入", "parent_code": "8.3", "sort_order": 832},
    {"clause_code": "8.3.3", "title": "设计和开发控制", "parent_code": "8.3", "sort_order": 833},
    {"clause_code": "8.3.4", "title": "设计和开发输出", "parent_code": "8.3", "sort_order": 834},
    {"clause_code": "8.3.5", "title": "设计和开发更改", "parent_code": "8.3", "sort_order": 835},
    {"clause_code": "8.4.1", "title": "总则 补充", "parent_code": "8.4", "sort_order": 841},
    {"clause_code": "8.4.2", "title": "类型和范围的控制", "parent_code": "8.4", "sort_order": 842},
    {"clause_code": "8.4.3", "title": "外部供方开发", "parent_code": "8.4", "sort_order": 843},
    {"clause_code": "8.5.1.1", "title": "控制计划", "parent_code": "8.5.1", "sort_order": 8511},
    {"clause_code": "8.5.1.2", "title": "标准化作业", "parent_code": "8.5.1", "sort_order": 8512},
    {"clause_code": "8.5.1.3", "title": "作业准备验证", "parent_code": "8.5.1", "sort_order": 8513},
    {"clause_code": "8.5.1.4", "title": "故障预防", "parent_code": "8.5.1", "sort_order": 8514},
    {"clause_code": "8.5.1.5", "title": "生产工装管理", "parent_code": "8.5.1", "sort_order": 8515},
    {"clause_code": "8.5.1.6", "title": "设备和过程变更", "parent_code": "8.5.1", "sort_order": 8516},
    {"clause_code": "8.5.1.7", "title": "生产排程", "parent_code": "8.5.1", "sort_order": 8517},
    {"clause_code": "8.5.2.1", "title": "标识和可追溯性 补充", "parent_code": "8.5.2", "sort_order": 8521},
    {"clause_code": "8.5.6.1", "title": "更改控制 补充", "parent_code": "8.5.6", "sort_order": 8561},
    {"clause_code": "8.6.1", "title": "产品和服务的放行 补充", "parent_code": "8.6", "sort_order": 861},
    {"clause_code": "8.7.1", "title": "不合格输出的控制 补充", "parent_code": "8.7", "sort_order": 871},
]

IATF16949_2016_PRESET: List[ClausePresetItem] = list(ISO9001_2015_PRESET) + _IATF_EXTRA
