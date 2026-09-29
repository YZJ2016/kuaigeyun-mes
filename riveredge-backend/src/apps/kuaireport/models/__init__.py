"""星报表模型。"""

from apps.kuaireport.models.dashboard import KuaireportDashboard, KuaireportDashboardVersion
from apps.kuaireport.models.data_source import KuaireportDataSource
from apps.kuaireport.models.report import KuaireportReport

__all__ = [
    "KuaireportDashboard",
    "KuaireportDashboardVersion",
    "KuaireportDataSource",
    "KuaireportReport",
]
