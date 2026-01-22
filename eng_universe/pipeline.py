import asyncio
from dataclasses import replace
from pathlib import Path

import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.etl import parse_html
from eng_universe.indexer import index_document


def _read_text(path: str) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


async def index_worker(doc_key_prefix: str | None = None) -> None:
    redis_client = redis.from_url(Settings.redis_url)
    prefix = doc_key_prefix or Settings.crawl_doc_key_prefix
    while True:
        raw_doc_id = await redis_client.lpop(Settings.raw_queue_key)
        if raw_doc_id is None:
            await asyncio.sleep(0.2)
            continue
        raw_doc_id = raw_doc_id.decode()
        crawl_meta = await redis_client.hgetall(f"{prefix}{raw_doc_id}")
        if not crawl_meta:
            continue
        url = crawl_meta.get(b"url", b"").decode()
        source = crawl_meta.get(b"source", b"").decode()
        raw_path = crawl_meta.get(b"raw_path", b"").decode()
        cleaned_path = crawl_meta.get(b"cleaned_path", b"").decode()
        raw_html = _read_text(raw_path)
        cleaned_html = _read_text(cleaned_path)
        if not url or not (raw_html or cleaned_html):
            continue
        base_html = raw_html or cleaned_html
        parsed = parse_html(url, base_html)
        if cleaned_html:
            cleaned_parsed = parse_html(url, cleaned_html)
            parsed = replace(parsed, content=cleaned_parsed.content)
        await index_document(redis_client, parsed, source=source)
