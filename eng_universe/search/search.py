import logging
import math
import re
import struct
import time
from dataclasses import dataclass

import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.search.embeddings import get_embedding_provider, normalize_embedding
from eng_universe.monitoring.metrics import SEARCH_LATENCY_MS
from eng_universe.search.pylate_backend import retrieve as pylate_retrieve

LOGGER = logging.getLogger("search")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S"
    )


@dataclass
class SearchResult:
    doc_id: str
    title: str
    url: str
    snippet: str
    authors: list[str]
    company: str
    published_at: str | None
    score: float


def _make_snippet(content: str, query: str, max_len: int = 200) -> str:
    if not content:
        return ""
    normalized = " ".join(content.split())
    if not query:
        return normalized[:max_len]
    lower_content = normalized.lower()
    lower_query = query.lower()
    match_index = lower_content.find(lower_query)
    if match_index == -1:
        return normalized[:max_len]
    start = max(match_index - max_len // 3, 0)
    end = min(start + max_len, len(normalized))
    snippet = normalized[start:end]
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(normalized):
        snippet = f"{snippet}…"
    return snippet


_REDIS_SPECIAL_CHARS = re.compile(r'([\\@{}\[\]\(\)\|<>\"\'=:;!#$%^&*+\-=~,\.])')


def _escape_redis_query(text: str) -> str:
    return _REDIS_SPECIAL_CHARS.sub(r"\\\1", text)


def _build_text_query(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        return "*"
    fields = [field.name for field in Settings.keyword_fields if field.field_type == "TEXT"]
    if not fields:
        fields = ["title", "content"]
    field_expr = "|".join(fields)
    return f"@{field_expr}:({_escape_redis_query(cleaned)})"


def _decode_value(value: object) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return str(value)


def _decode_hash(
    raw: dict[bytes, bytes], *, keep_bytes: set[str] | None = None
) -> dict[str, object]:
    keep = keep_bytes or set()
    decoded: dict[str, object] = {}
    for key, value in raw.items():
        name = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
        if name in keep:
            decoded[name] = value
        else:
            decoded[name] = _decode_value(value)
    return decoded


def _bytes_to_vector(raw: object) -> list[float]:
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return []
    if len(raw) % 4 != 0:
        return []
    count = len(raw) // 4
    return list(struct.unpack(f"{count}f", raw))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(l * r for l, r in zip(left, right))
    left_norm = math.sqrt(sum(l * l for l in left))
    right_norm = math.sqrt(sum(r * r for r in right))
    denom = left_norm * right_norm
    if denom == 0:
        return 0.0
    return dot / denom


async def search(
    redis_client: redis.Redis,
    index_name: str,
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
) -> list[SearchResult]:
    start = time.time()
    query = query.strip()
    if not query:
        return []
    if Settings.keyword_only and mode != "keyword":
        mode = "keyword"
    provider_name = Settings.embeddings_provider.lower()
    if Settings.debug_search:
        LOGGER.info(
            "search request provider=%s mode=%s query=%r limit=%s",
            provider_name,
            mode,
            query,
            limit,
        )
    if provider_name in {"pylate", "colbert"} and mode != "keyword":
        results = await _search_pylate(redis_client, query, limit)
        if Settings.debug_search:
            LOGGER.info("search pylate results=%s", len(results))
        SEARCH_LATENCY_MS.observe((time.time() - start) * 1000)
        return results
    text_query = _build_text_query(query)
    if mode == "keyword":
        args = [
            "FT.SEARCH",
            index_name,
            text_query,
            "LIMIT",
            "0",
            str(limit),
            "RETURN",
            "6",
            "title",
            "url",
            "content",
            "authors",
            "company",
            "published_at",
            "DIALECT",
            "2",
        ]
        if Settings.debug_search:
            LOGGER.info("search redis mode=keyword query=%s", text_query)
    else:
        if Settings.debug_search:
            LOGGER.info("search redis mode=%s text_query=%s", mode, text_query)
        provider = get_embedding_provider()
        embedding = provider.embed(query).vector
        embedding = normalize_embedding(embedding, Settings.embeddings_dim)
        vector_bytes = struct.pack(
            f"{Settings.embeddings_dim}f", *embedding
        )
        if mode == "hybrid":
            bm25_limit = max(limit * 5, limit)
            vector_limit = max(limit * 5, limit)
            bm25_raw = await redis_client.execute_command(
                "FT.SEARCH",
                index_name,
                text_query,
                "LIMIT",
                "0",
                str(bm25_limit),
                "RETURN",
                "0",
                "WITHSCORES",
                "DIALECT",
                "2",
            )
            vector_raw = await redis_client.execute_command(
                "FT.SEARCH",
                index_name,
                f"*=>[KNN {vector_limit} @embedding $vec AS vector_score]",
                "PARAMS",
                "2",
                "vec",
                vector_bytes,
                "SORTBY",
                "vector_score",
                "RETURN",
                "0",
                "DIALECT",
                "2",
            )
            bm25_scores: dict[str, float] = {}
            bm25_ids: list[str] = []
            if bm25_raw and len(bm25_raw) > 1:
                i = 1
                while i < len(bm25_raw):
                    doc_key = _decode_value(bm25_raw[i])
                    score = float(bm25_raw[i + 1])
                    bm25_scores[doc_key] = score
                    bm25_ids.append(doc_key)
                    i += 2
            vector_ids: list[str] = []
            if vector_raw and len(vector_raw) > 1:
                for i in range(1, len(vector_raw)):
                    vector_ids.append(_decode_value(vector_raw[i]))
            doc_keys = list(dict.fromkeys(bm25_ids + vector_ids))
            if Settings.debug_search:
                LOGGER.info(
                    "search hybrid candidates bm25=%s vector=%s union=%s",
                    len(bm25_ids),
                    len(vector_ids),
                    len(doc_keys),
                )
            if not doc_keys:
                return []
            pipe = redis_client.pipeline()
            for doc_key in doc_keys:
                pipe.hgetall(doc_key)
            raw_docs = await pipe.execute()
            results: list[SearchResult] = []
            for doc_key, raw_doc in zip(doc_keys, raw_docs):
                if not raw_doc:
                    continue
                mapping = _decode_hash(raw_doc, keep_bytes={"embedding"})
                embedding_raw = mapping.get("embedding")
                doc_vector = _bytes_to_vector(embedding_raw)
                try:
                    doc_vector = normalize_embedding(
                        doc_vector, Settings.embeddings_dim
                    )
                except ValueError:
                    continue
                score = _cosine_similarity(embedding, doc_vector)
                authors_raw = mapping.get("authors", "")
                authors = [
                    item.strip()
                    for item in str(authors_raw).split(",")
                    if item.strip()
                ]
                content = str(mapping.get("content", ""))
                results.append(
                    SearchResult(
                        doc_id=str(mapping.get("doc_id") or doc_key),
                        title=str(mapping.get("title", "")),
                        url=str(mapping.get("url", "")),
                        snippet=_make_snippet(content, query),
                        authors=authors,
                        company=str(mapping.get("company", "")),
                        published_at=str(mapping.get("published_at") or "") or None,
                        score=score,
                    )
                )
            results.sort(key=lambda item: item.score, reverse=True)
            SEARCH_LATENCY_MS.observe((time.time() - start) * 1000)
            return results[:limit]
        if mode == "semantic":
            text_query = "*"
        if text_query == "*":
            query_expr = f"*=>[KNN {limit} @embedding $vec AS vector_score]"
        else:
            query_expr = (
                f"({text_query})=>[KNN {limit} @embedding $vec AS vector_score]"
            )
        if Settings.debug_search:
            LOGGER.info("search redis mode=%s query=%s", mode, query_expr)
        args = [
            "FT.SEARCH",
            index_name,
            query_expr,
            "PARAMS",
            "2",
            "vec",
            vector_bytes,
            "SORTBY",
            "vector_score",
            "RETURN",
            "7",
            "title",
            "url",
            "content",
            "authors",
            "company",
            "published_at",
            "vector_score",
            "DIALECT",
            "2",
        ]
    raw = await redis_client.execute_command(*args)
    if Settings.debug_search:
        raw_count = 0
        if raw:
            try:
                raw_count = int(raw[0])
            except (TypeError, ValueError):
                raw_count = 0
        LOGGER.info("search redis raw_count=%s", raw_count)
    results = []
    if raw and len(raw) > 1:
        for i in range(1, len(raw), 2):
            doc_id = raw[i].decode() if isinstance(raw[i], (bytes, bytearray)) else raw[i]
            fields = raw[i + 1]
            mapping = {
                fields[j].decode(): fields[j + 1].decode()
                for j in range(0, len(fields), 2)
            }
            authors_raw = mapping.get("authors", "")
            authors = [item.strip() for item in authors_raw.split(",") if item.strip()]
            content = mapping.get("content", "")
            results.append(
                SearchResult(
                    doc_id=doc_id,
                    title=mapping.get("title", ""),
                    url=mapping.get("url", ""),
                    snippet=_make_snippet(content, query),
                    authors=authors,
                    company=mapping.get("company", ""),
                    published_at=mapping.get("published_at") or None,
                    score=float(mapping.get("vector_score", "0")),
                )
            )
    SEARCH_LATENCY_MS.observe((time.time() - start) * 1000)
    return results


async def _search_pylate(
    redis_client: redis.Redis, query: str, limit: int
) -> list[SearchResult]:
    try:
        hits = pylate_retrieve(query, k=limit)
    except ValueError as exc:
        if "index is empty" in str(exc).lower():
            if Settings.debug_search:
                LOGGER.info("search pylate index empty")
            return []
        raise
    results: list[SearchResult] = []
    for hit in hits:
        doc_id = str(hit.get("id", ""))
        if not doc_id:
            continue
        raw = await redis_client.hgetall(f"doc:{doc_id}")
        if not raw:
            continue
        mapping = _decode_hash(raw)
        authors_raw = mapping.get("authors", "")
        authors = [item.strip() for item in authors_raw.split(",") if item.strip()]
        content = mapping.get("content", "")
        results.append(
            SearchResult(
                doc_id=doc_id,
                title=mapping.get("title", ""),
                url=mapping.get("url", ""),
                snippet=_make_snippet(content, query),
                authors=authors,
                company=mapping.get("company", ""),
                published_at=mapping.get("published_at") or None,
                score=float(hit.get("score", 0.0)),
            )
        )
    return results
