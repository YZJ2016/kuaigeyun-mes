"""星数采告警模型（兼容别名，实体定义在 iot.py）。"""

from .iot import IotAlert as KuaiiotAlert
from .iot import IotAlertRule as KuaiiotAlertRule

__all__ = ["KuaiiotAlert", "KuaiiotAlertRule"]
