"""星报表配置键。

报表只绑一个已登记数据源，执行只走 execute_report。
数据集查询仍调用平台 DatasetService，不在这里另写 SQL 执行器。
"""

DATA_SOURCE_TYPES = frozenset({"static", "dataset", "http"})

# 配置与 report_config 顶层禁止这些键，避免把 SQL / query_config 抄进来。
FORBIDDEN_CONFIG_KEYS = frozenset({"query_config", "sql", "statement"})

# 报表绑定只认 report_config.extra.data_source_uuid，指向本租户已登记数据源。
REPORT_DATA_SOURCE_UUID = "data_source_uuid"

DATASET_UUID_KEY = "dataset_uuid"
DATASET_DISPLAY_NAME_KEY = "display_name"
HTTP_URL_KEY = "url"
STATIC_ROWS_KEY = "rows"

DATASET_CONFIG_KEYS = frozenset({DATASET_UUID_KEY, DATASET_DISPLAY_NAME_KEY})
HTTP_CONFIG_KEYS = frozenset({HTTP_URL_KEY})
STATIC_CONFIG_KEYS = frozenset({STATIC_ROWS_KEY})

PAGINATION_KEYS = frozenset({"limit", "offset"})
# 筛选里若夹带地址，不得覆盖已登记的 HTTP 地址。
HTTP_ADDRESS_OVERRIDE_KEYS = frozenset({"url", "address"})
