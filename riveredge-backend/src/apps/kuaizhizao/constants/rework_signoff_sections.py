"""会签返工多分区节点子区 key（无其它依赖，避免 chain 模块半加载）。"""

POSITION_REVIEW_SUB_SECTIONS = ("prod_mgr", "quality_mgr", "pqc")
REWORK_EXEC_SUB_SECTIONS = ("warehouse", "production", "quality_pqc")

MULTI_SECTION_NODE_KEYS = frozenset({"position_review", "rework_exec"})