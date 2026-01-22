import asyncio

import redis.asyncio as redis

from eng_universe.config import Settings


async def main() -> None:
    redis_client = redis.from_url(Settings.redis_url)
    base_keys = [
        Settings.crawl_queue_key,
        Settings.crawl_delay_key,
        Settings.crawl_seen_key,
        Settings.crawl_doc_seq_key,
        Settings.raw_queue_key,
    ]
    pipe = redis_client.pipeline()
    for key in base_keys:
        pipe.delete(key)
    await pipe.execute()

    patterns = [
        f"{Settings.crawl_doc_key_prefix}*",
        f"{Settings.robots_key_prefix}*",
        f"{Settings.robots_next_allowed_prefix}*",
    ]
    deleted = 0
    for pattern in patterns:
        async for key in redis_client.scan_iter(match=pattern, count=1000):
            await redis_client.delete(key)
            deleted += 1
    print(f"Cleared crawl queues and metadata. Deleted {deleted} keys.")


if __name__ == "__main__":
    asyncio.run(main())
