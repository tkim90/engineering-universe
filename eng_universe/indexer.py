import logging
import struct
from dataclasses import dataclass

import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.embeddings import get_embedding_provider, normalize_embedding
from eng_universe.entities import extract_topics
from eng_universe.etl import ParsedDocument
from eng_universe.metrics import record_index
from eng_universe.pylate_backend import add_documents as pylate_add_documents

LOGGER = logging.getLogger("indexer")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S"
    )


def log_event(event: str, **fields: object) -> None:
    if not Settings.crawl_log:
        return
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    LOGGER.info("%-8s %s", event.upper(), parts)


@dataclass
class IndexRecord:
    doc_id: str
    title: str
    content: str
    topics: list[str]
    source: str
    company: str
    authors: list[str]
    published_at: str | None
    url: str
    lang: str | None
    embedding: bytes | None


def vector_to_bytes(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


async def index_document(
    redis_client: redis.Redis, doc: ParsedDocument, source: str
) -> None:
    log_event("index", url=doc.url, title=doc.title, source=source)
    embedding_bytes: bytes | None = None
    provider_name = Settings.embeddings_provider.lower()
    if provider_name in {"pylate", "colbert"}:
        pylate_add_documents([doc.url], [f"{doc.title}\n{doc.content}"])
    else:
        provider = get_embedding_provider()
        embedding = provider.embed(f"{doc.title}\n{doc.content}")
        vector = normalize_embedding(embedding.vector, Settings.embeddings_dim)
        embedding_bytes = vector_to_bytes(vector)
    record = IndexRecord(
        doc_id=doc.url,
        title=doc.title,
        content=doc.content,
        topics=extract_topics(doc.content),
        source=source,
        company=doc.company,
        authors=doc.authors,
        published_at=doc.published_at,
        url=doc.canonical_url or doc.url,
        lang=doc.language,
        embedding=embedding_bytes,
    )
    mapping = {
        "doc_id": record.doc_id,
        "title": record.title,
        "content": record.content,
        "topics": ",".join(record.topics),
        "source": record.source,
        "company": record.company,
        "authors": ",".join(record.authors),
        "published_at": record.published_at or "",
        "url": record.url,
        "lang": record.lang or "",
    }
    if record.embedding is not None:
        mapping["embedding"] = record.embedding
    await redis_client.hset(f"doc:{record.doc_id}", mapping=mapping)
    record_index()


async def create_search_index(redis_client: redis.Redis, index_name: str) -> None:
    provider_name = Settings.embeddings_provider.lower()
    if provider_name in {"pylate", "colbert"}:
        from eng_universe.pylate_backend import create_plaid_index

        log_event(
            "init-index",
            backend="pylate",
            index=f"{Settings.pylate_index_folder}/{Settings.pylate_index_name}",
        )
        create_plaid_index(override=True)
        log_event("ready", backend="pylate")
    vector_dim = Settings.embeddings_dim
    try:
        log_event(
            "init-index",
            backend="redis",
            index=index_name,
            dim=vector_dim,
        )
        schema = [
            "title",
            "TEXT",
            "content",
            "TEXT",
            "topics",
            "TAG",
            "SEPARATOR",
            ",",
            "source",
            "TAG",
            "SEPARATOR",
            ",",
            "company",
            "TAG",
            "SEPARATOR",
            ",",
            "authors",
            "TAG",
            "SEPARATOR",
            ",",
            "published_at",
            "TEXT",
            "url",
            "TEXT",
            "lang",
            "TAG",
            "SEPARATOR",
            ",",
        ]
        if provider_name not in {"pylate", "colbert"}:
            schema.extend(
                [
                    "embedding",
                    "VECTOR",
                    "HNSW",
                    "6",
                    "TYPE",
                    "FLOAT32",
                    "DIM",
                    vector_dim,
                    "DISTANCE_METRIC",
                    "COSINE",
                ]
            )
        await redis_client.execute_command(
            "FT.CREATE",
            index_name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            "doc:",
            "SCHEMA",
            *schema,
        )
        log_event("ready", backend="redis", index=index_name)
    except redis.ResponseError as exc:
        if "Index already exists" not in str(exc):
            raise
        log_event("ready", backend="redis", index=index_name, status="exists")
