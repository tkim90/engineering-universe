from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
import sys

from eng_universe.config import Settings
from eng_universe.search.search import load_doc_cache, search as run_search
from eng_universe.monitoring.logging_utils import get_event_logger


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
log_event = get_event_logger("api")


@app.on_event("startup")
async def startup() -> None:
    redis_client = redis.from_url(Settings.redis_url)
    app.state.redis_client = redis_client
    app.state.doc_cache = await load_doc_cache(redis_client)

    # Measure cache size
    num_docs = len(app.state.doc_cache)
    cache_size_bytes = sys.getsizeof(app.state.doc_cache)
    log_event(
        "doc_cache",
        num_docs=num_docs,
        cache_size_bytes=cache_size_bytes,
        cache_size_bytes_mb=(cache_size_bytes / (1024 * 1024)),
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    redis_client = getattr(app.state, "redis_client", None)
    if redis_client is not None:
        await redis_client.close()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query("", min_length=1),
    mode: str = Query("hybrid", pattern="^(keyword|hybrid|semantic)$"),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    redis_client = app.state.redis_client
    doc_cache = app.state.doc_cache
    results, query_latency_ms = await run_search(
        redis_client, "idx:blogs", q, mode=mode, limit=limit, doc_cache=doc_cache
    )
    duration_ms = round(query_latency_ms, 1)
    return {
        "query": q,
        "mode": mode,
        "count": len(results),
        "duration_ms": duration_ms,
        "results": [result.__dict__ for result in results],
    }
