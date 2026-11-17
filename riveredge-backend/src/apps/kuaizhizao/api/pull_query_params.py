"""取单列表 API 公共查询参数。"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import Query

PullQueryDateFrom = Annotated[
    Optional[date],
    Query(description="来源单据日期起（站点日历 YYYY-MM-DD）"),
]
PullQueryDateTo = Annotated[
    Optional[date],
    Query(description="来源单据日期止（站点日历 YYYY-MM-DD）"),
]
