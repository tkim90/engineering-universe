"""Search subpackage: search operations."""

from eng_universe.search.embeddings import (
    EmbeddingProvider,
    EmbeddingResult,
    get_embedding_provider,
    normalize_embedding,
)
from eng_universe.search.pylate_backend import (
    add_documents,
    create_plaid_index,
    encode_documents,
    encode_queries,
    get_colbert_model,
    get_colbert_retriever,
    get_colbert_stack,
    get_plaid_index,
    retrieve,
)
from eng_universe.search.search import SearchResult, search

__all__ = [
    # embeddings
    "EmbeddingProvider",
    "EmbeddingResult",
    "get_embedding_provider",
    "normalize_embedding",
    # pylate_backend
    "add_documents",
    "create_plaid_index",
    "encode_documents",
    "encode_queries",
    "get_colbert_model",
    "get_colbert_retriever",
    "get_colbert_stack",
    "get_plaid_index",
    "retrieve",
    # search
    "SearchResult",
    "search",
]
