import argparse
import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import redis.asyncio as redis

from eng_universe.config import Settings


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Requeue crawl docs from crawl metadata."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the raw queue before requeuing.",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1000,
        help="Batch size for RPUSH.",
    )
    args = parser.parse_args()

    redis_client = redis.from_url(Settings.redis_url)
    if args.clear:
        await redis_client.delete(Settings.raw_queue_key)

    prefix = Settings.crawl_doc_key_prefix
    queue_key = Settings.raw_queue_key
    batch: list[str] = []
    total = 0

    async for key in redis_client.scan_iter(match=f"{prefix}*", count=1000):
        key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
        if not key_str.startswith(prefix):
            continue
        doc_id = key_str[len(prefix) :]
        if not doc_id:
            continue
        batch.append(doc_id)
        if len(batch) >= args.batch:
            await redis_client.rpush(queue_key, *batch)
            total += len(batch)
            batch.clear()

    if batch:
        await redis_client.rpush(queue_key, *batch)
        total += len(batch)

    print(f"Requeued {total} docs into {queue_key}.")


if __name__ == "__main__":
    asyncio.run(main())
