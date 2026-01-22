import time
from dataclasses import dataclass

import redis.asyncio as redis

from eng_universe.config import Settings


@dataclass
class CrawlItem:
    url: str
    source: str
    depth: int = 0


def _serialize(item: CrawlItem) -> str:
    return f"{item.url}\t{item.source}\t{item.depth}"


def _deserialize(raw: bytes) -> CrawlItem | None:
    parts = raw.decode().split("\t")
    if len(parts) < 2:
        return None
    url = parts[0]
    source = parts[1]
    depth = 0
    if len(parts) > 2:
        try:
            depth = int(parts[2])
        except ValueError:
            depth = 0
    return CrawlItem(url=url, source=source, depth=depth)


async def enqueue(
    redis_client: redis.Redis, item: CrawlItem, *, dedupe: bool = True
) -> None:
    if dedupe:
        added = await redis_client.sadd(Settings.crawl_seen_key, item.url)
        if not added:
            return
    await redis_client.rpush(Settings.crawl_queue_key, _serialize(item))


async def dequeue(redis_client: redis.Redis) -> CrawlItem | None:
    raw = await redis_client.lpop(Settings.crawl_queue_key)
    if raw is None:
        return None
    return _deserialize(raw)


async def delay(redis_client: redis.Redis, item: CrawlItem, when_ts: int) -> None:
    await redis_client.zadd(
        Settings.crawl_delay_key,
        {_serialize(item): float(when_ts)},
    )


async def promote_due(redis_client: redis.Redis, max_items: int = 100) -> int:
    now = time.time()
    items = await redis_client.zrangebyscore(
        Settings.crawl_delay_key, "-inf", now, start=0, num=max_items
    )
    if not items:
        return 0
    pipe = redis_client.pipeline()
    for raw in items:
        pipe.zrem(Settings.crawl_delay_key, raw)
        pipe.rpush(Settings.crawl_queue_key, raw)
    await pipe.execute()
    return len(items)
