from fastapi import FastAPI, Query
import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.search import search as run_search


app = FastAPI()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query("", min_length=1),
    mode: str = Query("hybrid", pattern="^(keyword|hybrid|semantic)$"),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    redis_client = redis.from_url(Settings.redis_url)
    results = await run_search(redis_client, "idx:blogs", q, mode=mode, limit=limit)
    return {
        "query": q,
        "mode": mode,
        "count": len(results),
        "results": [result.__dict__ for result in results],
    }
