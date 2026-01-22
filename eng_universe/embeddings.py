from __future__ import annotations

from dataclasses import dataclass

from eng_universe.config import Settings


@dataclass
class EmbeddingResult:
    vector: list[float]
    provider: str


class EmbeddingProvider:
    def embed(self, text: str) -> EmbeddingResult:
        raise NotImplementedError


class DummyEmbeddingProvider(EmbeddingProvider):
    def embed(self, text: str) -> EmbeddingResult:
        length = Settings.embeddings_dim
        vector = [0.0] * length
        for index, ch in enumerate(text[:length]):
            vector[index] = float((ord(ch) % 97) / 96.0)
        return EmbeddingResult(vector=vector, provider="dummy")


def get_embedding_provider() -> EmbeddingProvider:
    provider = Settings.embeddings_provider.lower()
    if provider == "dummy":
        return DummyEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {provider}")
