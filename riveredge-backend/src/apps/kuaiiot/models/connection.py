"""星数采连接源模型（兼容别名，实体定义在 iot.py）。"""

from .iot import IotConnection as KuaiiotConnection
from .iot import IotConnectionMessage as KuaiiotConnectionMessage

__all__ = ["KuaiiotConnection", "KuaiiotConnectionMessage"]
