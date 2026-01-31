"""Monitoring subpackage: observability components."""

from eng_universe.monitoring.metrics import (
    CRAWL_PAGES,
    INDEX_DOCS,
    SEARCH_LATENCY_MS,
    record_crawl,
    record_index,
)
from eng_universe.monitoring.metrics_server import run_metrics_server

__all__ = [
    # metrics
    "CRAWL_PAGES",
    "INDEX_DOCS",
    "SEARCH_LATENCY_MS",
    "record_crawl",
    "record_index",
    # metrics_server
    "run_metrics_server",
]
