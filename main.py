import argparse
import asyncio

from eng_universe.config import Settings
from eng_universe.crawler import run_crawlers, seed_queue
from eng_universe.indexer import create_search_index
from eng_universe.metrics_server import run_metrics_server
from eng_universe.pipeline import index_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Eng Universe CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="Seed the crawl queue")
    sub.add_parser("crawl", help="Run crawler workers")
    sub.add_parser("index", help="Run indexer workers")
    sub.add_parser("init-index", help="Create Redis search index")
    sub.add_parser("metrics", help="Run Prometheus metrics server")

    args = parser.parse_args()

    if args.command == "seed":
        for url in Settings.seed_start_urls.split(","):
            url = url.strip()
            if url:
                asyncio.run(seed_queue(url))
        return
    if args.command == "crawl":
        asyncio.run(run_crawlers())
        return
    if args.command == "index":
        asyncio.run(index_worker())
        return
    if args.command == "init-index":
        import redis.asyncio as redis

        redis_client = redis.from_url(Settings.redis_url)
        asyncio.run(create_search_index(redis_client, "idx:blogs"))
        return
    if args.command == "metrics":
        run_metrics_server()
        return


if __name__ == "__main__":
    main()
