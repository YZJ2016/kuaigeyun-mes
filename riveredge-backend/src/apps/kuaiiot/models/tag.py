"""星数采点位模型（兼容别名，实体定义在 iot.py）。"""

from .iot import IotTagDefinition as KuaiiotTagDefinition
from .iot import IotTagHistory as KuaiiotTagHistory
from .iot import IotTagSnapshot as KuaiiotTagSnapshot

__all__ = ["KuaiiotTagDefinition", "KuaiiotTagHistory", "KuaiiotTagSnapshot"]
