import asyncio
from dataclasses import dataclass
import time
from urllib.parse import urlparse

import aiohttp
import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.metrics import record_crawl
from eng_universe.queue import CrawlItem, delay, dequeue, enqueue, promote_due
from eng_universe.robots import (
    get_next_allowed,
    get_or_fetch_robots,
    parse_domain,
    update_next_allowed,
)
from urllib.robotparser import RobotFileParser


@dataclass
class CrawlResult:
    url: str
    status: int
    html: str


async def fetch_html(session: aiohttp.ClientSession, url: str) -> CrawlResult:
    async with session.get(url, timeout=Settings.request_timeout_s) as response:
        html = await response.text()
        return CrawlResult(url=url, status=response.status, html=html)


async def should_fetch(
    redis_client: redis.Redis, session: aiohttp.ClientSession, url: str
) -> bool:
    domain = parse_domain(url)
    rules = await get_or_fetch_robots(redis_client, session, domain)
    parser = RobotFileParser()
    parser.parse(rules.text.splitlines())
    if not parser.can_fetch(Settings.user_agent, url):
        return False
    next_allowed = await get_next_allowed(redis_client, domain)
    return next_allowed <= int(time.time())


async def schedule_next_allowed(
    redis_client: redis.Redis, session: aiohttp.ClientSession, url: str
) -> int:
    domain = parse_domain(url)
    rules = await get_or_fetch_robots(redis_client, session, domain)
    await update_next_allowed(redis_client, domain, rules.crawl_delay_s)
    return rules.crawl_delay_s


async def crawl_worker(
    redis_client: redis.Redis, session: aiohttp.ClientSession, raw_key_prefix: str
) -> None:
    while True:
        await promote_due(redis_client)
        item = await dequeue(redis_client)
        if item is None:
            await asyncio.sleep(0.2)
            continue
        if not await should_fetch(redis_client, session, item.url):
            domain = parse_domain(item.url)
            next_allowed = await get_next_allowed(redis_client, domain)
            await delay(redis_client, item, next_allowed)
            continue
        result = await fetch_html(session, item.url)
        await schedule_next_allowed(redis_client, session, item.url)
        if result.status >= 400:
            continue
        doc_id = item.url
        await redis_client.hset(
            f"{raw_key_prefix}{doc_id}",
            mapping={"url": item.url, "html": result.html, "source": item.source},
        )
        await redis_client.rpush(Settings.raw_queue_key, doc_id)
        record_crawl(urlparse(item.url).netloc)


async def run_crawlers(raw_key_prefix: str = "raw:") -> None:
    redis_client = redis.from_url(Settings.redis_url)
    async with aiohttp.ClientSession(
        headers={"User-Agent": Settings.user_agent}
    ) as session:
        workers = [
            asyncio.create_task(crawl_worker(redis_client, session, raw_key_prefix))
            for _ in range(Settings.max_concurrency)
        ]
        await asyncio.gather(*workers)


async def seed_queue(seed_url: str, source: str = "seed") -> None:
    redis_client = redis.from_url(Settings.redis_url)
    await enqueue(redis_client, CrawlItem(url=seed_url, source=source))
