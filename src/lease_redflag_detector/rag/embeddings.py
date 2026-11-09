"""Embeddings of chunks and queries with a local multilingual model.

multilingual-e5 expects "passage: " before an indexed text and "query: " before a
search query. Vectors are normalized, so the dot product is the cosine similarity.

Passage vectors are cached on disk by a hash of the model name and the text, so a
rebuild embeds only the chunks that changed.
"""

import hashlib
from functools import cached_property
from pathlib import Path

import numpy as np

from lease_redflag_detector.rag.chunking import PASSAGE_PREFIX, TOKENIZER

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "processed" / "embeddings"
MODEL = TOKENIZER
QUERY_PREFIX = "query: "


class Embedder:
    def __init__(self, model: str = MODEL, cache_dir: Path = CACHE_DIR):
        self.model_name = model
        self.cache_path = cache_dir / f"{model.replace('/', '__')}.npz"
        self._cache: dict[str, np.ndarray] | None = None

    @cached_property
    def model(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name)

    @property
    def dimension(self) -> int:
        return self.model.get_embedding_dimension()

    def key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}\n{text}".encode()).hexdigest()

    def cache(self) -> dict[str, np.ndarray]:
        if self._cache is None:
            self._cache = {}
            if self.cache_path.exists():
                with np.load(self.cache_path) as data:
                    self._cache = dict(zip(data["keys"], data["vectors"], strict=True))
        return self._cache

    def save_cache(self) -> None:
        cache = self.cache()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            self.cache_path,
            keys=np.array(list(cache)),
            vectors=np.stack(list(cache.values())),
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            texts, normalize_embeddings=True, batch_size=16, convert_to_numpy=True
        )

    def passages(self, texts: list[str]) -> np.ndarray:
        """Vectors of texts to index, from the cache where possible."""
        cache = self.cache()
        keys = [self.key(PASSAGE_PREFIX + text) for text in texts]
        missing = list(dict.fromkeys(k for k in keys if k not in cache))
        if missing:
            by_key = dict(zip(keys, texts, strict=True))
            vectors = self.encode([PASSAGE_PREFIX + by_key[k] for k in missing])
            cache.update(zip(missing, vectors, strict=True))
            self.save_cache()
        return np.stack([cache[k] for k in keys])

    def query(self, text: str) -> np.ndarray:
        return self.encode([QUERY_PREFIX + text])[0]
