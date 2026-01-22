import time

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.search import search as run_search


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    start = time.perf_counter()
    results = await run_search(redis_client, "idx:blogs", q, mode=mode, limit=limit)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "query": q,
        "mode": mode,
        "count": len(results),
        "duration_ms": duration_ms,
        "results": [result.__dict__ for result in results],
    }
