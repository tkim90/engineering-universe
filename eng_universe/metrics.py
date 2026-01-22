from prometheus_client import Counter, Histogram


CRAWL_PAGES = Counter(
    "crawler_pages_total", "Total pages fetched by crawler", ["domain"]
)
INDEX_DOCS = Counter("indexer_docs_total", "Total docs indexed")
SEARCH_LATENCY_MS = Histogram(
    "search_latency_ms",
    "Search latency in milliseconds",
    buckets=(5, 10, 20, 30, 40, 50, 75, 100, 200, 400, 800),
)


def record_crawl(domain: str) -> None:
    CRAWL_PAGES.labels(domain=domain).inc()


def record_index() -> None:
    INDEX_DOCS.inc()
