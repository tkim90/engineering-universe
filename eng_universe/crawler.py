import asyncio
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
import time
from urllib.parse import urldefrag, urljoin, urlparse
import xml.etree.ElementTree as ElementTree

import aiohttp
from bs4 import BeautifulSoup
import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.metrics import record_crawl
from eng_universe.queue import CrawlItem, delay, dequeue, enqueue, promote_due
from eng_universe.robots import (
    get_or_fetch_robots,
    parse_domain,
    reserve_next_allowed,
)
from urllib.robotparser import RobotFileParser


@dataclass
class CrawlResult:
    url: str
    status: int
    html: str


UNWANTED_TAGS = ("nav", "footer", "aside", "script", "style", "noscript")

LOGGER = logging.getLogger("crawler")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S"
    )


def log_event(event: str, **fields: object) -> None:
    if not Settings.crawl_log:
        return
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    LOGGER.info("%-8s %s", event.upper(), parts)

ALLOWED_URL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "engineering.fb.com": [
        re.compile(r"^/\d{4}/\d{2}/\d{2}/[^/]+/[^/]+$"),
    ],
    "builders.ramp.com": [re.compile(r"^/post/[^/]+$")],
    "airbnb.tech": [re.compile(r"^/[^/]+/[^/]+$")],
    "www.anthropic.com": [re.compile(r"^/engineering/[^/]+$")],
    "developers.openai.com": [re.compile(r"^/blog/[^/]+$")],
    "blog.cloudflare.com": [re.compile(r"^/[^/]+$")],
    "developers.googleblog.com": [re.compile(r"^/[^/]+$")],
    "www.notion.com": [re.compile(r"^/blog/[^/]+$")],
    "cursor.com": [re.compile(r"^/blog/[^/]+$")],
    "shopify.engineering": [re.compile(r"^/[^/]+$")],
    "netflixtechblog.com": [re.compile(r"^/[^/]+-[0-9a-f]{8,}$")],
    "github.blog": [re.compile(r"^/engineering/[^/]+/[^/]+$")],
    "engineering.atspotify.com": [re.compile(r"^/\d{4}/\d{1,2}/[^/]+$")],
    "slack.engineering": [re.compile(r"^/[^/]+$")],
    "stripe.com": [re.compile(r"^/blog/[^/]+$")],
    "www.uber.com": [re.compile(r"^/blog/[^/]+$")],
}

ALLOWED_SEED_PATHS: dict[str, set[str]] = {
    "engineering.fb.com": {"/"},
    "builders.ramp.com": {"/"},
    "airbnb.tech": {"/"},
    "www.anthropic.com": {"/engineering"},
    "developers.openai.com": {"/blog"},
    "blog.cloudflare.com": {"/"},
    "developers.googleblog.com": {"/"},
    "www.notion.com": {"/blog"},
    "cursor.com": {"/blog"},
    "shopify.engineering": {"/"},
    "netflixtechblog.com": {"/"},
    "github.blog": {"/engineering"},
    "engineering.atspotify.com": {"/"},
    "slack.engineering": {"/"},
    "stripe.com": {"/blog"},
    "www.uber.com": {"/blog"},
}

DEFAULT_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml")
SITEMAP_PATHS: dict[str, tuple[str, ...]] = {
    "netflixtechblog.com": ("/sitemap/sitemap.xml", "/sitemap.xml"),
}


def _clean_container(soup: BeautifulSoup) -> BeautifulSoup:
    for tag_name in UNWANTED_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    return soup.find("article") or soup.find("main") or soup.body or soup


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return str(_clean_container(soup))


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    container = _clean_container(soup)
    return " ".join(container.get_text(" ", strip=True).split())


def normalize_url(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc:
        return None
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path)
    return normalized.geturl()


def extract_links(soup: BeautifulSoup, base_url: str) -> set[str]:
    links: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = tag.get("href")
        if not href:
            continue
        href = href.strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        normalized = normalize_url(absolute)
        if normalized:
            links.add(normalized)
    return links


def is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    seed_paths = ALLOWED_SEED_PATHS.get(parsed.netloc)
    path = parsed.path or "/"
    if seed_paths and path in seed_paths:
        return True
    patterns = ALLOWED_URL_PATTERNS.get(parsed.netloc)
    if not patterns:
        return False
    for pattern in patterns:
        if pattern.match(path):
            return True
    return False


def is_listing_url(url: str) -> bool:
    parsed = urlparse(url)
    seed_paths = ALLOWED_SEED_PATHS.get(parsed.netloc)
    if not seed_paths:
        return False
    path = parsed.path or "/"
    return path in seed_paths


def sitemap_urls_for_domain(domain: str) -> set[str]:
    if domain not in ALLOWED_URL_PATTERNS:
        return set()
    paths = SITEMAP_PATHS.get(domain, DEFAULT_SITEMAP_PATHS)
    return {f"https://{domain}{path}" for path in paths}


def is_sitemap_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_URL_PATTERNS:
        return False
    if parsed.path.endswith(".xml") or "sitemap" in parsed.path:
        return True
    return url in sitemap_urls_for_domain(parsed.netloc)


def parse_sitemap_links(xml_text: str) -> set[str]:
    if not xml_text.lstrip().startswith("<"):
        return set()
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return set()

    def tag_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    root_tag = tag_name(root.tag)
    if root_tag not in {"urlset", "sitemapindex"}:
        return set()

    urls: set[str] = set()
    for loc in root.iter():
        if tag_name(loc.tag) != "loc":
            continue
        if loc.text:
            urls.add(loc.text.strip())
    return urls


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def storage_paths(base_dir: Path, doc_id: int, url: str) -> tuple[Path, Path]:
    digest = url_hash(url)
    raw_path = base_dir / str(doc_id) / f"raw_{digest}.html"
    cleaned_path = base_dir / str(doc_id) / f"clean_{digest}.html"
    return raw_path, cleaned_path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def fetch_html(session: aiohttp.ClientSession, url: str) -> CrawlResult | None:
    try:
        async with session.get(url, timeout=Settings.request_timeout_s) as response:
            html = await response.text()
            return CrawlResult(url=url, status=response.status, html=html)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def crawl_worker(
    redis_client: redis.Redis,
    session: aiohttp.ClientSession,
    doc_key_prefix: str,
    storage_dir: Path,
    stop_event: asyncio.Event | None = None,
    max_docs: int | None = None,
    counter: list[int] | None = None,
    counter_lock: asyncio.Lock | None = None,
) -> None:
    while True:
        if stop_event and stop_event.is_set():
            return
        await promote_due(redis_client)
        item = await dequeue(redis_client)
        if item is None:
            await asyncio.sleep(0.2)
            continue
        log_event(
            "pick",
            url=item.url,
            depth=item.depth,
            source=item.source,
        )
        domain = parse_domain(item.url)
        rules = await get_or_fetch_robots(redis_client, session, domain)
        parser = RobotFileParser()
        parser.parse(rules.text.splitlines())
        if not parser.can_fetch(Settings.user_agent, item.url):
            log_event("deny", url=item.url, reason="robots")
            continue
        min_delay_s = max(rules.crawl_delay_s, rules.request_rate_s)
        allowed, next_allowed = await reserve_next_allowed(
            redis_client, domain, min_delay_s
        )
        if not allowed:
            await delay(redis_client, item, next_allowed)
            log_event("delay", url=item.url, until=next_allowed)
            continue
        result = await fetch_html(session, item.url)
        if result is None or result.status >= 400:
            log_event(
                "fail",
                url=item.url,
                status=result.status if result else "error",
            )
            continue
        if is_sitemap_url(result.url):
            sitemap_links = parse_sitemap_links(result.html)
            for link in sitemap_links:
                normalized = normalize_url(link)
                if not normalized or not is_allowed_url(normalized):
                    continue
                await enqueue(
                    redis_client,
                    CrawlItem(url=normalized, source="sitemap", depth=item.depth + 1),
                )
            log_event("sitemap", url=item.url, links=len(sitemap_links))
            continue
        soup = BeautifulSoup(result.html, "html.parser")
        links = extract_links(soup, result.url)
        if not Settings.crawl_allow_external:
            links = {link for link in links if parse_domain(link) == domain}
        links = {link for link in links if is_allowed_url(link)}
        if item.depth < Settings.crawl_depth_limit:
            next_depth = item.depth + 1
            for link in links:
                if link == item.url:
                    continue
                await enqueue(
                    redis_client,
                    CrawlItem(url=link, source=item.source, depth=next_depth),
                )
        stored = False
        if (
            not (item.source == "seed" and item.depth == 0)
            and item.source != "sitemap"
            and not is_listing_url(item.url)
        ):
            cleaned_html = str(_clean_container(soup))
            doc_id = int(await redis_client.incr(Settings.crawl_doc_seq_key))
            raw_path, cleaned_path = storage_paths(storage_dir, doc_id, item.url)
            await asyncio.to_thread(write_text, raw_path, result.html)
            await asyncio.to_thread(write_text, cleaned_path, cleaned_html)
            await redis_client.hset(
                f"{doc_key_prefix}{doc_id}",
                mapping={
                    "url": item.url,
                    "domain": domain,
                    "source": item.source,
                    "depth": item.depth,
                    "raw_path": str(raw_path),
                    "cleaned_path": str(cleaned_path),
                    "url_hash": url_hash(item.url),
                    "fetched_at": int(time.time()),
                    "status": result.status,
                },
            )
            await redis_client.rpush(Settings.raw_queue_key, doc_id)
            stored = True
            log_event(
                "stored",
                id=doc_id,
                url=item.url,
                raw=str(raw_path),
                cleaned=str(cleaned_path),
            )
        else:
            if item.source == "seed" and item.depth == 0:
                reason = "seed"
            elif is_listing_url(item.url):
                reason = "listing"
            else:
                reason = item.source
            log_event("skip", url=item.url, reason=reason)
        record_crawl(domain)
        if (
            stored
            and max_docs is not None
            and stop_event is not None
            and counter is not None
            and counter_lock is not None
        ):
            async with counter_lock:
                counter[0] += 1
                if counter[0] >= max_docs:
                    stop_event.set()


async def run_crawlers(
    doc_key_prefix: str | None = None, max_docs: int | None = None
) -> None:
    redis_client = redis.from_url(Settings.redis_url)
    prefix = doc_key_prefix or Settings.crawl_doc_key_prefix
    storage_dir = Path(Settings.crawl_storage_dir)
    if max_docs is not None and max_docs <= 0:
        return
    stop_event = asyncio.Event() if max_docs is not None else None
    counter = [0] if max_docs is not None else None
    counter_lock = asyncio.Lock() if max_docs is not None else None
    async with aiohttp.ClientSession(
        headers={"User-Agent": Settings.user_agent}
    ) as session:
        workers = [
            asyncio.create_task(
                crawl_worker(
                    redis_client,
                    session,
                    prefix,
                    storage_dir,
                    stop_event=stop_event,
                    max_docs=max_docs,
                    counter=counter,
                    counter_lock=counter_lock,
                )
            )
            for _ in range(Settings.max_concurrency)
        ]
        await asyncio.gather(*workers)


async def seed_queue(seed_url: str, source: str = "seed") -> None:
    redis_client = redis.from_url(Settings.redis_url)
    normalized = normalize_url(seed_url)
    if not normalized:
        return
    await enqueue(redis_client, CrawlItem(url=normalized, source=source, depth=0))
    for sitemap_url in sitemap_urls_for_domain(parse_domain(normalized)):
        await enqueue(
            redis_client,
            CrawlItem(url=sitemap_url, source="sitemap", depth=0),
        )
