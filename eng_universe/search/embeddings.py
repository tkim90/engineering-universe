from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

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


def _require_setting(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _mean_pool(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    width = len(vectors[0])
    sums = [0.0] * width
    for row in vectors:
        if len(row) != width:
            raise ValueError("Embedding rows have inconsistent dimensions")
        for index, value in enumerate(row):
            sums[index] += float(value)
    count = float(len(vectors))
    return [value / count for value in sums]


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError(
                "huggingface_hub package is required for Hugging Face embeddings."
            ) from exc
        api_key = _require_setting(Settings.huggingface_api_key, "HUGGINGFACE_API_KEY")
        self._model = _require_setting(
            Settings.huggingface_embedding_model, "HUGGINGFACE_EMBEDDINGS_MODEL"
        )
        if "colbert" in self._model.lower():
            raise RuntimeError(
                "ColBERT models require EMBEDDINGS_PROVIDER=pylate; "
                "use a standard embedding model for Hugging Face feature extraction."
            )
        provider = Settings.huggingface_provider
        self._client = InferenceClient(api_key=api_key, provider=provider)

    def embed(self, text: str) -> EmbeddingResult:
        output = self._client.feature_extraction(text, model=self._model)
        if hasattr(output, "tolist"):
            output = output.tolist()
        vector: list[float]
        if isinstance(output, list) and output:
            if isinstance(output[0], list):
                vector = _mean_pool(output)  # type: ignore[arg-type]
            else:
                vector = [float(value) for value in output]  # type: ignore[arg-type]
        else:
            raise RuntimeError("Unexpected Hugging Face embedding response")
        return EmbeddingResult(vector=vector, provider="huggingface")


def normalize_embedding(vector: list[float], dim: int) -> list[float]:
    if len(vector) < dim:
        raise ValueError(f"Embedding dim {len(vector)} < expected {dim}")
    if len(vector) > dim:
        return vector[:dim]
    return vector


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    provider = Settings.embeddings_provider.lower()
    if provider == "dummy":
        return DummyEmbeddingProvider()
    if provider in {"huggingface", "hf"}:
        return HuggingFaceEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {provider}")
