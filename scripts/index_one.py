import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
import sys

import redis.asyncio as redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eng_universe.config import Settings
from eng_universe.ingest.etl import parse_html
from eng_universe.index.indexer import index_document


def read_text(path: str) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Index a single crawl doc id")
    parser.add_argument("doc_id", help="Crawl doc ID to index")
    args = parser.parse_args()

    redis_client = redis.from_url(Settings.redis_url)
    crawl_key = f"{Settings.crawl_doc_key_prefix}{args.doc_id}"
    crawl_meta = await redis_client.hgetall(crawl_key)
    if not crawl_meta:
        print(f"Missing crawl metadata for {crawl_key}")
        return
    url = crawl_meta.get(b"url", b"").decode()
    source = crawl_meta.get(b"source", b"").decode()
    raw_path = crawl_meta.get(b"raw_path", b"").decode()
    cleaned_path = crawl_meta.get(b"cleaned_path", b"").decode()

    raw_html = read_text(raw_path)
    cleaned_html = read_text(cleaned_path)
    if not url or not (raw_html or cleaned_html):
        print("Missing url or HTML content to index.")
        return

    base_html = raw_html or cleaned_html
    parsed = parse_html(url, base_html)
    if cleaned_html:
        cleaned_parsed = parse_html(url, cleaned_html)
        parsed = replace(parsed, content=cleaned_parsed.content)

    await index_document(redis_client, parsed, source=source)
    print(f"Indexed {args.doc_id} -> doc:{parsed.url}")


if __name__ == "__main__":
    asyncio.run(main())
