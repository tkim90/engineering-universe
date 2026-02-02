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


_REDIS_SPECIAL_CHARS = re.compile(r"([\\@{}\[\]\(\)\|<>\"\'=:;!#$%^&*+\-=~,\.])")


def _escape_redis_query(text: str) -> str:
    return _REDIS_SPECIAL_CHARS.sub(r"\\\1", text)


_PREFIX_WORD = re.compile(r"\w+$")
_PREFIX_TWO = re.compile(r"\w{2}$")
_PREFIX_ONE = re.compile(r"\w$")


def _split_prefix_query(text: str) -> tuple[str, str | None]:
    """
    Normalizes special characters (hyphens, spaces, quotes, etc).
    If normalized text has 1 or 2+ chars at the end, splits off as separate word:
      Example: "machine lear" -> ("machine", "lear")
      Example: "python p" -> ("python", "p")
    """
    normalized = text.replace("-", " ")
    normalized = re.sub(
        r"[\u2013\u2014\u2026\u00ab\u00bb\u2018\u2019]", " ", normalized
    )
    normalized = re.sub(r"[\u201c\u201d]", '"', normalized)
    normalized = normalized.strip()
    if not normalized:
        return "", None
    if _PREFIX_TWO.search(normalized):
        match = _PREFIX_WORD.search(normalized)
        if match:
            return normalized[: match.start()], normalized[match.start() :]
    if _PREFIX_ONE.search(normalized):
        return normalized[:-1], None
    return normalized, None


def _build_text_query(query: str) -> str:
    """
    Returns redis full text query from user input.
    """
    base, prefix = _split_prefix_query(query)
    if not base and not prefix:
        return "*"
    fields = [
        field.name for field in Settings.keyword_fields if field.field_type == "TEXT"
    ]
    if not fields:
        fields = ["title", "content"]
    field_expr = "|".join(fields)
    if prefix:
        base_expr = _escape_redis_query(base)
        prefix_expr = _escape_redis_query(prefix)
        query_expr = f"{base_expr}({prefix_expr}|{prefix_expr}*)"
    else:
        query_expr = _escape_redis_query(base)
    return f"@{field_expr}:({query_expr})"


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


def _decode_doc_ids(raw: object) -> list[str]:
    """Extract docIDs from Redis response"""
    if not raw:
        return []
    if not isinstance(raw, (list, tuple)) or len(raw) <= 1:
        return []
    return [_decode_value(item) for item in raw[1:]]


def _result_from_mapping(
    mapping: dict[str, object],
    *,
    doc_key: str,
    query: str,
    score: float,
) -> SearchResult:
    authors_raw = mapping.get("authors", "")
    authors = [item.strip() for item in str(authors_raw).split(",") if item.strip()]
    content = str(mapping.get("content", ""))
    return SearchResult(
        doc_id=str(mapping.get("doc_id") or doc_key),
        title=str(mapping.get("title", "")),
        url=str(mapping.get("url", "")),
        snippet=_make_snippet(content, query),
        authors=authors,
        company=str(mapping.get("company", "")),
        published_at=str(mapping.get("published_at") or "") or None,
        score=score,
    )


async def load_doc_cache(
    redis_client: redis.Redis, *, batch_size: int = 500
) -> dict[str, dict[str, object]]:
    cache: dict[str, dict[str, object]] = {}
    batch: list[str] = []
    async for key in redis_client.scan_iter(match="doc:*", count=batch_size):
        key_str = _decode_value(key)
        batch.append(key_str)
        if len(batch) >= batch_size:
            await _load_doc_cache_batch(redis_client, cache, batch)
            batch = []
    if batch:
        await _load_doc_cache_batch(redis_client, cache, batch)
    return cache


async def _load_doc_cache_batch(
    redis_client: redis.Redis, cache: dict[str, dict[str, object]], keys: list[str]
) -> None:
    pipe = redis_client.pipeline()
    for key in keys:
        pipe.hgetall(key)
    raw_docs = await pipe.execute()
    for key, raw_doc in zip(keys, raw_docs):
        if not raw_doc:
            continue
        cache[key] = _decode_hash(raw_doc, keep_bytes={"embedding"})


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
    doc_cache: dict[str, dict[str, object]] | None = None,
) -> tuple[list[SearchResult], float]:
    query_latency_ms = 0.0
    query = query.strip()
    if not query:
        return [], query_latency_ms
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
        results, query_latency_ms = await _search_pylate(
            redis_client, query, limit, doc_cache=doc_cache
        )
        if Settings.debug_search:
            LOGGER.info("search pylate results=%s", len(results))
        SEARCH_LATENCY_MS.observe(query_latency_ms)
        return results, query_latency_ms
    text_query = _build_text_query(query)
    needs_vector_score = False
    embedding: list[float] | None = None
    if mode == "keyword":
        args = [
            "FT.SEARCH",
            index_name,
            text_query,
            "LIMIT",
            "0",
            str(limit),
            "RETURN",
            "0",
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
        vector_bytes = struct.pack(f"{Settings.embeddings_dim}f", *embedding)
        if mode == "hybrid":
            bm25_limit = max(limit * 5, limit)
            vector_limit = max(limit * 5, limit)
            start_query = time.perf_counter()
            bm25_raw = await redis_client.execute_command(
                "FT.SEARCH",
                index_name,
                text_query,
                "LIMIT",
                "0",
                str(bm25_limit),
                "RETURN",
                "0",
                "DIALECT",
                "2",
            )
            query_latency_ms += (time.perf_counter() - start_query) * 1000
            start_query = time.perf_counter()
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
            query_latency_ms += (time.perf_counter() - start_query) * 1000
            bm25_ids = _decode_doc_ids(bm25_raw)
            vector_ids = _decode_doc_ids(vector_raw)
            doc_keys = list(dict.fromkeys(bm25_ids + vector_ids))
            if Settings.debug_search:
                LOGGER.info(
                    "search hybrid candidates bm25=%s vector=%s union=%s",
                    len(bm25_ids),
                    len(vector_ids),
                    len(doc_keys),
                )
            if not doc_keys:
                SEARCH_LATENCY_MS.observe(query_latency_ms)
                return [], query_latency_ms
            results: list[SearchResult] = []
            doc_items: list[tuple[str, dict[str, object]]] = []
            if doc_cache is None:
                pipe = redis_client.pipeline()
                for doc_key in doc_keys:
                    pipe.hgetall(doc_key)
                raw_docs = await pipe.execute()
                for doc_key, raw_doc in zip(doc_keys, raw_docs):
                    if not raw_doc:
                        continue
                    mapping = _decode_hash(raw_doc, keep_bytes={"embedding"})
                    doc_items.append((doc_key, mapping))
            else:
                for doc_key in doc_keys:
                    mapping = doc_cache.get(doc_key)
                    if not mapping:
                        continue
                    doc_items.append((doc_key, mapping))
            for doc_key, mapping in doc_items:
                embedding_raw = mapping.get("embedding")
                doc_vector = _bytes_to_vector(embedding_raw)
                try:
                    doc_vector = normalize_embedding(
                        doc_vector, Settings.embeddings_dim
                    )
                except ValueError:
                    continue
                score = _cosine_similarity(embedding, doc_vector)
                results.append(
                    _result_from_mapping(
                        mapping,
                        doc_key=doc_key,
                        query=query,
                        score=score,
                    )
                )
            results.sort(key=lambda item: item.score, reverse=True)
            SEARCH_LATENCY_MS.observe(query_latency_ms)
            return results[:limit], query_latency_ms
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
            "0",
            "DIALECT",
            "2",
        ]
        needs_vector_score = True
    start_query = time.perf_counter()
    raw = await redis_client.execute_command(*args)
    query_latency_ms += (time.perf_counter() - start_query) * 1000
    if Settings.debug_search:
        raw_count = 0
        if raw:
            try:
                raw_count = int(raw[0])
            except (TypeError, ValueError):
                raw_count = 0
        LOGGER.info("search redis raw_count=%s", raw_count)
    doc_keys = _decode_doc_ids(raw)
    if not doc_keys:
        SEARCH_LATENCY_MS.observe(query_latency_ms)
        return [], query_latency_ms
    results: list[SearchResult] = []
    doc_items: list[tuple[str, dict[str, object]]] = []
    if doc_cache is None:
        pipe = redis_client.pipeline()
        for doc_key in doc_keys:
            pipe.hgetall(doc_key)
        raw_docs = await pipe.execute()
        keep_bytes = {"embedding"} if needs_vector_score else None
        for doc_key, raw_doc in zip(doc_keys, raw_docs):
            if not raw_doc:
                continue
            mapping = _decode_hash(raw_doc, keep_bytes=keep_bytes)
            doc_items.append((doc_key, mapping))
    else:
        for doc_key in doc_keys:
            mapping = doc_cache.get(doc_key)
            if not mapping:
                continue
            doc_items.append((doc_key, mapping))
    for doc_key, mapping in doc_items:
        score = 0.0
        if needs_vector_score and embedding is not None:
            embedding_raw = mapping.get("embedding")
            doc_vector = _bytes_to_vector(embedding_raw)
            try:
                doc_vector = normalize_embedding(doc_vector, Settings.embeddings_dim)
            except ValueError:
                continue
            score = _cosine_similarity(embedding, doc_vector)
        results.append(
            _result_from_mapping(
                mapping,
                doc_key=doc_key,
                query=query,
                score=score,
            )
        )
    if needs_vector_score:
        results.sort(key=lambda item: item.score, reverse=True)
        results = results[:limit]
    SEARCH_LATENCY_MS.observe(query_latency_ms)
    return results, query_latency_ms


async def _search_pylate(
    redis_client: redis.Redis,
    query: str,
    limit: int,
    *,
    doc_cache: dict[str, dict[str, object]] | None = None,
) -> tuple[list[SearchResult], float]:
    try:
        start_query = time.perf_counter()
        hits = pylate_retrieve(query, k=limit)
        query_latency_ms = (time.perf_counter() - start_query) * 1000
    except ValueError as exc:
        if "index is empty" in str(exc).lower():
            if Settings.debug_search:
                LOGGER.info("search pylate index empty")
            return [], 0.0
        raise
    results: list[SearchResult] = []
    for hit in hits:
        doc_id = str(hit.get("id", ""))
        if not doc_id:
            continue
        doc_key = f"doc:{doc_id}"
        mapping: dict[str, object] | None = None
        if doc_cache is not None:
            mapping = doc_cache.get(doc_key)
        if mapping is None:
            raw = await redis_client.hgetall(doc_key)
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
    return results, query_latency_ms
