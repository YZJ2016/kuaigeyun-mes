"""星数采 ORM 模块注册。入站表，以及迁移 521/524 已有的告警表。"""

ORM_MODEL_MODULES: list[str] = [
    "apps.kuaiiot.models.connection",
    "apps.kuaiiot.models.device",
    "apps.kuaiiot.models.tag",
    "apps.kuaiiot.models.dedup",
    "apps.kuaiiot.models.alert",
    "apps.kuaiiot.models.edge_config",
    "apps.kuaiiot.models.product",
    "apps.kuaiiot.models.group",
    "apps.kuaiiot.models.command",
    "apps.kuaiiot.models.message_log",
    "apps.kuaiiot.models.delivery",
]
