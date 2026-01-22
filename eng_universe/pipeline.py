import asyncio

import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.etl import parse_html
from eng_universe.indexer import index_document


async def index_worker(raw_key_prefix: str = "raw:") -> None:
    redis_client = redis.from_url(Settings.redis_url)
    while True:
        raw_doc_id = await redis_client.lpop(Settings.raw_queue_key)
        if raw_doc_id is None:
            await asyncio.sleep(0.2)
            continue
        raw_doc_id = raw_doc_id.decode()
        raw = await redis_client.hgetall(f"{raw_key_prefix}{raw_doc_id}")
        if not raw:
            continue
        url = raw.get(b"url", b"").decode()
        html = raw.get(b"html", b"").decode()
        source = raw.get(b"source", b"").decode()
        parsed = parse_html(url, html)
        await index_document(redis_client, parsed, source=source)
