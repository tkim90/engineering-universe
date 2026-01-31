from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

from eng_universe.config import Settings


@dataclass
class ColBERTStack:
    model: Any
    index: Any
    retriever: Any


def _require_pylate() -> tuple[Any, Any, Any]:
    try:
        from pylate import indexes, models, retrieve
    except ImportError as exc:
        raise RuntimeError("pylate package is required for ColBERT indexing.") from exc
    return indexes, models, retrieve


def _device_setting() -> str | None:
    device = Settings.pylate_device.strip()
    return device or None


@lru_cache(maxsize=1)
def get_colbert_model() -> Any:
    _, models, _ = _require_pylate()
    return models.ColBERT(
        model_name_or_path=Settings.pylate_model_name,
        device=_device_setting(),
    )


def create_plaid_index(*, override: bool = False) -> Any:
    indexes, _, _ = _require_pylate()
    return indexes.PLAID(
        index_folder=Settings.pylate_index_folder,
        index_name=Settings.pylate_index_name,
        override=override,
    )


@lru_cache(maxsize=1)
def get_plaid_index() -> Any:
    return create_plaid_index(override=False)


@lru_cache(maxsize=1)
def get_colbert_retriever() -> Any:
    _, _, retrieve = _require_pylate()
    return retrieve.ColBERT(index=get_plaid_index())


@lru_cache(maxsize=1)
def get_colbert_stack() -> ColBERTStack:
    return ColBERTStack(
        model=get_colbert_model(),
        index=get_plaid_index(),
        retriever=get_colbert_retriever(),
    )


def encode_documents(documents: Sequence[str]) -> Any:
    model = get_colbert_model()
    return model.encode(
        list(documents),
        batch_size=Settings.pylate_batch_size,
        is_query=False,
        show_progress_bar=Settings.pylate_show_progress,
    )


def encode_queries(queries: Sequence[str]) -> Any:
    model = get_colbert_model()
    return model.encode(
        list(queries),
        batch_size=Settings.pylate_batch_size,
        is_query=True,
        show_progress_bar=Settings.pylate_show_progress,
    )


def add_documents(documents_ids: Sequence[str], documents: Sequence[str]) -> None:
    if len(documents_ids) != len(documents):
        raise ValueError("documents_ids and documents must be the same length")
    embeddings = encode_documents(documents)
    index = get_plaid_index()
    index.add_documents(
        documents_ids=list(documents_ids),
        documents_embeddings=embeddings,
    )


def retrieve(query: str, k: int) -> list[dict[str, float]]:
    if not query:
        return []
    queries_embeddings = encode_queries([query])
    retriever = get_colbert_retriever()
    results = retriever.retrieve(queries_embeddings=queries_embeddings, k=k)
    if not results:
        return []
    return results[0]
