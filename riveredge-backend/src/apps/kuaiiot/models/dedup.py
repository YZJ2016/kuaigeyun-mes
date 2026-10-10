"""星数采入站幂等模型（兼容别名，实体定义在 iot.py）。"""

from .iot import IotIngestDedup as KuaiiotIngestDedup

__all__ = ["KuaiiotIngestDedup"]
