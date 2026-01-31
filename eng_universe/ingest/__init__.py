"""Ingest subpackage: data acquisition components."""

from eng_universe.ingest.crawler import (
    CrawlResult,
    clean_html,
    crawl_worker,
    extract_links,
    extract_text,
    is_allowed_url,
    normalize_url,
    run_crawlers,
    seed_queue,
)
from eng_universe.ingest.etl import ParsedDocument, parse_html
from eng_universe.ingest.queue import CrawlItem, delay, dequeue, enqueue, promote_due
from eng_universe.ingest.robots import (
    RobotsRules,
    get_or_fetch_robots,
    parse_domain,
    reserve_next_allowed,
)

__all__ = [
    # crawler
    "CrawlResult",
    "clean_html",
    "crawl_worker",
    "extract_links",
    "extract_text",
    "is_allowed_url",
    "normalize_url",
    "run_crawlers",
    "seed_queue",
    # etl
    "ParsedDocument",
    "parse_html",
    # queue
    "CrawlItem",
    "delay",
    "dequeue",
    "enqueue",
    "promote_due",
    # robots
    "RobotsRules",
    "get_or_fetch_robots",
    "parse_domain",
    "reserve_next_allowed",
]
