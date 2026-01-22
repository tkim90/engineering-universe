import time
from dataclasses import dataclass

import redis.asyncio as redis

from eng_universe.config import Settings


@dataclass
class CrawlItem:
    url: str
    source: str


async def enqueue(redis_client: redis.Redis, item: CrawlItem) -> None:
    await redis_client.rpush(Settings.crawl_queue_key, f"{item.url}\t{item.source}")


async def dequeue(redis_client: redis.Redis) -> CrawlItem | None:
    raw = await redis_client.lpop(Settings.crawl_queue_key)
    if raw is None:
        return None
    url, source = raw.decode().split("\t", 1)
    return CrawlItem(url=url, source=source)


async def delay(redis_client: redis.Redis, item: CrawlItem, when_ts: int) -> None:
    await redis_client.zadd(
        Settings.crawl_delay_key,
        {f"{item.url}\t{item.source}": float(when_ts)},
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
