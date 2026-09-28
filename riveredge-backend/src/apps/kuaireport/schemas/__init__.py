"""星报表 Schema 包。"""

from apps.kuaireport.schemas.data_source import DataSourceCreate, DataSourceOut, DataSourceUpdate
from apps.kuaireport.schemas.execute import ExecuteReportResult

__all__ = [
    "DataSourceCreate",
    "DataSourceOut",
    "DataSourceUpdate",
    "ExecuteReportResult",
]
