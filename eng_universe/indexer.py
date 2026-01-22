import struct
from dataclasses import dataclass

import redis.asyncio as redis

from eng_universe.config import Settings
from eng_universe.embeddings import get_embedding_provider
from eng_universe.entities import extract_topics
from eng_universe.etl import ParsedDocument
from eng_universe.metrics import record_index


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
    embedding: bytes


def vector_to_bytes(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


async def index_document(
    redis_client: redis.Redis, doc: ParsedDocument, source: str
) -> None:
    provider = get_embedding_provider()
    embedding = provider.embed(f"{doc.title}\n{doc.content}")
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
        embedding=vector_to_bytes(embedding.vector),
    )
    await redis_client.hset(
        f"doc:{record.doc_id}",
        mapping={
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
            "embedding": record.embedding,
        },
    )
    record_index()


async def create_search_index(redis_client: redis.Redis, index_name: str) -> None:
    vector_dim = Settings.embeddings_dim
    try:
        await redis_client.execute_command(
            "FT.CREATE",
            index_name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            "doc:",
            "SCHEMA",
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
            "embedding",
            "VECTOR",
            "HNSW",
            "12",
            "TYPE",
            "FLOAT32",
            "DIM",
            vector_dim,
            "DISTANCE_METRIC",
            "COSINE",
        )
    except redis.ResponseError as exc:
        if "Index already exists" not in str(exc):
            raise
