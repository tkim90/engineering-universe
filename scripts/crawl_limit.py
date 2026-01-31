import argparse
import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eng_universe.ingest.crawler import run_crawlers
from eng_universe.config import Settings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run crawler for a limited number of docs")
    parser.add_argument("--max-docs", type=int, default=5, help="Max docs to store")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of crawler workers to run",
    )
    args = parser.parse_args()
    Settings.max_concurrency = max(1, args.concurrency)
    await run_crawlers(max_docs=args.max_docs)


if __name__ == "__main__":
    asyncio.run(main())
