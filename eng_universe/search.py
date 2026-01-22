import struct
import time
from dataclasses import dataclass

import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.embeddings import get_embedding_provider
from eng_universe.metrics import SEARCH_LATENCY_MS


@dataclass
class SearchResult:
    doc_id: str
    title: str
    url: str
    score: float


async def search(
    redis_client: redis.Redis,
    index_name: str,
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
) -> list[SearchResult]:
    start = time.time()
    if mode == "keyword":
        args = [
            "FT.SEARCH",
            index_name,
            f"@title|content:{query}",
            "LIMIT",
            "0",
            str(limit),
            "RETURN",
            "2",
            "title",
            "url",
            "DIALECT",
            "2",
        ]
    else:
        provider = get_embedding_provider()
        embedding = provider.embed(query).vector
        vector_bytes = struct.pack(
            f"{Settings.embeddings_dim}f", *embedding[: Settings.embeddings_dim]
        )
        args = [
            "FT.SEARCH",
            index_name,
            f"(@title|content:{query})=>[KNN {limit} @embedding $vec AS vector_score]",
            "PARAMS",
            "2",
            "vec",
            vector_bytes,
            "SORTBY",
            "vector_score",
            "RETURN",
            "3",
            "title",
            "url",
            "vector_score",
            "DIALECT",
            "2",
        ]
    raw = await redis_client.execute_command(*args)
    results = []
    if raw and len(raw) > 1:
        for i in range(1, len(raw), 2):
            doc_id = raw[i].decode() if isinstance(raw[i], (bytes, bytearray)) else raw[i]
            fields = raw[i + 1]
            mapping = {
                fields[j].decode(): fields[j + 1].decode()
                for j in range(0, len(fields), 2)
            }
            results.append(
                SearchResult(
                    doc_id=doc_id,
                    title=mapping.get("title", ""),
                    url=mapping.get("url", ""),
                    score=float(mapping.get("vector_score", "0")),
                )
            )
    SEARCH_LATENCY_MS.observe((time.time() - start) * 1000)
    return results
