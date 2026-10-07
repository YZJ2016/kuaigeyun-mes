"""星数采模型。"""

from apps.kuaiiot.models.alert import KuaiiotAlert, KuaiiotAlertRule
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.dedup import KuaiiotIngestDedup
from apps.kuaiiot.models.delivery import KuaiiotDelivery
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.command import KuaiiotDeviceCommand
from apps.kuaiiot.models.group import KuaiiotDeviceGroup
from apps.kuaiiot.models.message_log import KuaiiotMessageLog
from apps.kuaiiot.models.product import KuaiiotProduct
from apps.kuaiiot.models.edge_config import KuaiiotEdgeConfig
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagHistory, KuaiiotTagSnapshot

__all__ = [
    "KuaiiotAlert",
    "KuaiiotAlertRule",
    "KuaiiotConnection",
    "KuaiiotDevice",
    "KuaiiotDeviceCommand",
    "KuaiiotDeviceGroup",
    "KuaiiotEdgeConfig",
    "KuaiiotIngestDedup",
    "KuaiiotDelivery",
    "KuaiiotMessageLog",
    "KuaiiotProduct",
    "KuaiiotTagDefinition",
    "KuaiiotTagHistory",
    "KuaiiotTagSnapshot",
]
