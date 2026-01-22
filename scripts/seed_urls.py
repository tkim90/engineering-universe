import asyncio

from eng_universe.config import Settings
from eng_universe.crawler import seed_queue


async def main() -> None:
    for url in Settings.seed_start_urls.split(","):
        url = url.strip().rstrip('/')
        if url:
            await seed_queue(url)


if __name__ == "__main__":
    asyncio.run(main())
