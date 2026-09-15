"""HTTP request metrics exported for Prometheus scraping."""

from prometheus_client import Counter, Histogram

SLOW_API_THRESHOLD_MS = 1000

HTTP_REQUEST_DURATION = Histogram(
    "riveredge_http_request_duration_seconds",
    "HTTP request latency in seconds for /api routes",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

HTTP_REQUESTS_TOTAL = Counter(
    "riveredge_http_requests_total",
    "Total HTTP requests for /api routes",
    ["method", "path", "status"],
)

HTTP_SLOW_REQUESTS_TOTAL = Counter(
    "riveredge_http_slow_requests_total",
    "HTTP requests exceeding the slow API threshold",
    ["method", "path"],
)
