"""设备保养方案：维护类型真源（禁止页面/Schema 另写一套）。"""

# 保养周期类维护类型（非维修档位）
EQUIPMENT_MAINTENANCE_TYPES: tuple[str, ...] = (
    "日常保养",
    "月度",
    "季度",
    "半年度",
    "年度",
)

# 维护类型 → 默认周期（仅 cycle_type=按时间）；前端新建/切换类型时预填，允许用户改
EQUIPMENT_MAINTENANCE_TYPE_DEFAULT_CYCLE: dict[str, tuple[int, str]] = {
    "日常保养": (1, "天"),
    "月度": (1, "月"),
    "季度": (3, "月"),
    "半年度": (6, "月"),
    "年度": (1, "年"),
}

# 非日历周期类型 → 默认周期值/单位
EQUIPMENT_CYCLE_TYPE_DEFAULTS: dict[str, tuple[int, str]] = {
    "按运行时长": (100, "小时"),
    "按使用次数": (100, "次"),
}

EQUIPMENT_CYCLE_TYPE_TIME = "按时间"
EQUIPMENT_CYCLE_TYPE_RUNTIME = "按运行时长"
EQUIPMENT_CYCLE_TYPE_COUNT = "按使用次数"
EQUIPMENT_CYCLE_TYPES: tuple[str, ...] = (
    EQUIPMENT_CYCLE_TYPE_TIME,
    EQUIPMENT_CYCLE_TYPE_RUNTIME,
    EQUIPMENT_CYCLE_TYPE_COUNT,
)

# 历史维修档位 → 新维护类型（迁移回填用；禁止在业务读侧再做这套翻译）
LEGACY_EQUIPMENT_MAINTENANCE_TYPE_REMAP: dict[str, str] = {
    "小修": "月度",
    "中修": "季度",
    "大修": "年度",
}
