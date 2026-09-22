"""交付项目（订单交机）常量"""

from enum import Enum
from typing import Any, Dict, List


class DeliveryProjectStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryNodeStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class DeliveryNodeReportStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeliveryIssueType(str, Enum):
    BLOCKER = "blocker"
    QUALITY = "quality"
    DELIVERY = "delivery"
    OTHER = "other"


class DeliveryIssueStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DeliveryIssuePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DeliveryNodeTaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class DeliveryTaskTrackMode(str, Enum):
    """节点任务跟踪方式：进度百分比 / 齐套有无"""

    PROGRESS = "progress"
    KIT = "kit"


class DeliveryTaskParticipantMode(str, Enum):
    """节点任务协作方式：负责人独占 / 会签 / 或签 / 分人操作"""

    SOLO = "solo"
    SIGNOFF_ALL = "signoff_all"
    SIGNOFF_ANY = "signoff_any"
    EACH_ACT = "each_act"


class DeliveryTaskParticipantActionStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"


class DeliveryTaskKitStatus(str, Enum):
    NONE = "none"
    READY = "ready"
    NA = "na"


class DeliveryBoardSection(str, Enum):
    """车间台账分段（对齐 Excel 库存/退回/在制/已发）"""

    INVENTORY = "inventory"
    RETURNED = "returned"
    ACTIVE = "active"
    SHIPPED = "shipped"


class DeliveryLineRole(str, Enum):
    """主线 / 旁线（换热器等部件独立履约）"""

    MAIN = "main"
    SIDELINE = "sideline"


# 机台配置属性中用于型号工期匹配的约定键（值为租户产品型号）
DELIVERY_CONFIG_ATTR_PRODUCT_MODEL = "product_model"


DELIVERY_PROJECT_STATUS_LABELS: Dict[str, str] = {
    DeliveryProjectStatus.DRAFT.value: "草稿",
    DeliveryProjectStatus.IN_PROGRESS.value: "进行中",
    DeliveryProjectStatus.PAUSED.value: "暂停",
    DeliveryProjectStatus.COMPLETED.value: "已完成",
    DeliveryProjectStatus.CANCELLED.value: "已取消",
}

DELIVERY_NODE_STATUS_LABELS: Dict[str, str] = {
    DeliveryNodeStatus.NOT_STARTED.value: "未开始",
    DeliveryNodeStatus.IN_PROGRESS.value: "进行中",
    DeliveryNodeStatus.COMPLETED.value: "已完成",
    DeliveryNodeStatus.OVERDUE.value: "逾期",
}

DELIVERY_NODE_REPORT_STATUS_LABELS: Dict[str, str] = {
    DeliveryNodeReportStatus.DRAFT.value: "草稿",
    DeliveryNodeReportStatus.SUBMITTED.value: "已提交",
    DeliveryNodeReportStatus.APPROVED.value: "已通过",
    DeliveryNodeReportStatus.REJECTED.value: "已驳回",
}

DELIVERY_ISSUE_TYPE_LABELS: Dict[str, str] = {
    DeliveryIssueType.BLOCKER.value: "阻塞",
    DeliveryIssueType.QUALITY.value: "质量",
    DeliveryIssueType.DELIVERY.value: "交期",
    DeliveryIssueType.OTHER.value: "其他",
}

DELIVERY_ISSUE_STATUS_LABELS: Dict[str, str] = {
    DeliveryIssueStatus.OPEN.value: "待处理",
    DeliveryIssueStatus.IN_PROGRESS.value: "处理中",
    DeliveryIssueStatus.RESOLVED.value: "已解决",
    DeliveryIssueStatus.CLOSED.value: "已关闭",
}

DELIVERY_ISSUE_PRIORITY_LABELS: Dict[str, str] = {
    DeliveryIssuePriority.LOW.value: "低",
    DeliveryIssuePriority.NORMAL.value: "普通",
    DeliveryIssuePriority.HIGH.value: "高",
    DeliveryIssuePriority.URGENT.value: "紧急",
}

DELIVERY_NODE_TASK_STATUS_LABELS: Dict[str, str] = {
    DeliveryNodeTaskStatus.TODO.value: "待办",
    DeliveryNodeTaskStatus.IN_PROGRESS.value: "进行中",
    DeliveryNodeTaskStatus.DONE.value: "已完成",
    DeliveryNodeTaskStatus.CANCELLED.value: "已取消",
}

DELIVERY_TASK_TRACK_MODE_LABELS: Dict[str, str] = {
    DeliveryTaskTrackMode.PROGRESS.value: "进度",
    DeliveryTaskTrackMode.KIT.value: "齐套",
}

DELIVERY_TASK_PARTICIPANT_MODE_LABELS: Dict[str, str] = {
    DeliveryTaskParticipantMode.SOLO.value: "负责人",
    DeliveryTaskParticipantMode.SIGNOFF_ALL.value: "会签",
    DeliveryTaskParticipantMode.SIGNOFF_ANY.value: "或签",
    DeliveryTaskParticipantMode.EACH_ACT.value: "分人操作",
}

DELIVERY_TASK_PARTICIPANT_ACTION_STATUS_LABELS: Dict[str, str] = {
    DeliveryTaskParticipantActionStatus.PENDING.value: "待确认",
    DeliveryTaskParticipantActionStatus.DONE.value: "已确认",
}

DELIVERY_TASK_KIT_STATUS_LABELS: Dict[str, str] = {
    DeliveryTaskKitStatus.NONE.value: "无",
    DeliveryTaskKitStatus.READY.value: "有",
    DeliveryTaskKitStatus.NA.value: "不适用",
}

DELIVERY_BOARD_SECTION_LABELS: Dict[str, str] = {
    DeliveryBoardSection.INVENTORY.value: "库存",
    DeliveryBoardSection.RETURNED.value: "退回",
    DeliveryBoardSection.ACTIVE.value: "在制",
    DeliveryBoardSection.SHIPPED.value: "已发",
}

DELIVERY_LINE_ROLE_LABELS: Dict[str, str] = {
    DeliveryLineRole.MAIN.value: "主线",
    DeliveryLineRole.SIDELINE.value: "旁线",
}

DEFAULT_DELIVERY_PROCESS_NODES: List[Dict[str, Any]] = [
    {
        "node_key": "design",
        "node_name": "方案设计",
        "sort_order": 1,
        "default_owner_role": "designer",
        "planned_duration_days": 7,
        "is_critical": True,
        "is_milestone": True,
    },
    {
        "node_key": "procurement",
        "node_name": "采购",
        "sort_order": 2,
        "default_owner_role": "buyer",
        "planned_duration_days": 14,
        "is_critical": True,
        "is_milestone": False,
    },
    {
        "node_key": "machining",
        "node_name": "加工外协",
        "sort_order": 3,
        "default_owner_role": "production",
        "planned_duration_days": 10,
        "is_critical": False,
        "is_milestone": False,
    },
    {
        "node_key": "assembly",
        "node_name": "组装",
        "sort_order": 4,
        "default_owner_role": "production",
        "planned_duration_days": 7,
        "is_critical": True,
        "is_milestone": False,
    },
    {
        "node_key": "commissioning",
        "node_name": "厂内验收",
        "sort_order": 5,
        "default_owner_role": "quality",
        "planned_duration_days": 5,
        "is_critical": True,
        "is_milestone": True,
    },
    {
        "node_key": "shipping",
        "node_name": "发运签收",
        "sort_order": 6,
        "default_owner_role": "logistics",
        "planned_duration_days": 3,
        "is_critical": True,
        "is_milestone": True,
    },
]

# 节点可关联单据类型（与前端 LinkedDocumentDetail 对齐；inbound/outbound 用入库/出库抽屉类型）
DELIVERY_NODE_DOCUMENT_TYPES = frozenset({
    "sales_order",
    "purchase_order",
    "work_order",
    "purchase_receipt",
    "sales_delivery",
    "quality_inspection",
    "rd_project",
})

DELIVERY_NODE_DUE_SOON_DAYS = 3

DELIVERY_ALERT_KIND_DUE_SOON = "due_soon"
DELIVERY_ALERT_KIND_OVERDUE = "overdue"
DELIVERY_ALERT_KIND_MILESTONE_OVERDUE = "milestone_overdue"
