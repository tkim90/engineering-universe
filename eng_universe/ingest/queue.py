import time
from dataclasses import dataclass

from eng_universe.monitoring.logging_utils import get_event_logger
import redis.asyncio as redis

from eng_universe.config import Settings

log_event = get_event_logger("queue")


@dataclass
class CrawlItem:
    url: str
    source: str
    depth: int = 0


def _serialize(item: CrawlItem) -> str:
    return f"{item.url}\t{item.source}\t{item.depth}"


def _deserialize(raw: bytes) -> CrawlItem | None:
    """Deserializes redis item from bytes to CrawlItem"""
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
    log_event("enqueue", item=item)
    if dedupe:
        # Try adding url to redis set
        added = await redis_client.sadd(Settings.crawl_seen_key, item.url)
        if not added:
            return
    # Append url to queue
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


async def requeue_delayed_items(redis_client: redis.Redis, max_items: int = 100) -> int:
    """
    Moves items from the delay queue back to main crawl queue when their
    scheduled time arrives. It queries for items with timestamps up to current time,
    removes them from delay queue, and pushes them back to the main queue for processing.
    """
    now = time.time()

    # Fetch earliest items until now
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
