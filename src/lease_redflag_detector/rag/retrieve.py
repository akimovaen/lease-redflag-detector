"""Search over the chunks: vector, BM25, hybrid, and hybrid with reranking.

- **Vector**: multilingual-e5 embeddings in a local Qdrant collection.
- **BM25**: over lemmas (`lexical.py`), which finds exact terms the embeddings blur:
  article numbers, "ІСЦ", "суборенда".
- **Hybrid**: the two ranked lists fused with Reciprocal Rank Fusion, which needs no
  score calibration between them: score = Σ 1 / (60 + rank).
- **Rerank**: a cross-encoder reads the query and each of the top hybrid candidates
  together and orders them again. Its scores are cached on disk by a hash of the
  model, the query and the chunk text: the score of a pair never changes, and on a CPU
  the reranker is the slow part of an eval run.

Metadata filters apply to every mode: by default only documents in force
(`status = current`), so the 2024 policy and the repealed laws are left out unless
asked for. Other conditions: document type, access, date range, and excluded lease
regimes (state-property acts and leases).

    uv run python -m lease_redflag_detector.rag.retrieve "Чи можна суборенду без згоди?"
"""

import atexit
import hashlib
import json
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path

import numpy as np

from lease_redflag_detector.rag.chunking import Chunk
from lease_redflag_detector.rag.embeddings import Embedder
from lease_redflag_detector.rag.lexical import BM25

ROOT = Path(__file__).resolve().parents[3]
CHUNKS = ROOT / "data" / "corpus" / "chunks.jsonl"
QDRANT = ROOT / "data" / "processed" / "qdrant"
RERANK_CACHE = ROOT / "data" / "processed" / "rerank"
RERANKER = "BAAI/bge-reranker-v2-m3"
MODES = ("vector", "bm25", "hybrid", "hybrid_rerank")
RRF_K = 60
# How many of each list go into the fusion, and how many fused candidates are reranked.
CANDIDATES = 50
RERANK_CANDIDATES = 30


@dataclass
class Filters:
    """Metadata conditions; None means any value."""

    types: list[str] | None = None
    status: list[str] | None = field(default_factory=lambda: ["current"])
    access: list[str] | None = None
    date_from: str | None = None  # ISO dates, inclusive
    date_to: str | None = None
    # Documents without a regime (the policy, research) always pass.
    exclude_regimes: list[str] | None = None

    def matches(self, meta: dict) -> bool:
        date = str(meta.get("date", ""))
        return (
            (self.types is None or meta.get("type") in self.types)
            and (self.status is None or meta.get("status") in self.status)
            and (self.access is None or meta.get("access") in self.access)
            and (self.date_from is None or date >= self.date_from)
            and (self.date_to is None or (bool(date) and date <= self.date_to))
            and not (
                self.exclude_regimes and meta.get("regime") in self.exclude_regimes
            )
        )

    def to_qdrant(self):
        from qdrant_client import models

        conditions = [
            models.FieldCondition(key=key, match=models.MatchAny(any=values))
            for key, values in [
                ("type", self.types),
                ("status", self.status),
                ("access", self.access),
            ]
            if values is not None
        ]
        if self.date_from or self.date_to:
            conditions.append(
                models.FieldCondition(
                    key="date",
                    range=models.DatetimeRange(gte=self.date_from, lte=self.date_to),
                )
            )
        excluded = (
            [
                models.FieldCondition(
                    key="regime", match=models.MatchAny(any=self.exclude_regimes)
                )
            ]
            if self.exclude_regimes
            else []
        )
        if not conditions and not excluded:
            return None
        return models.Filter(must=conditions or None, must_not=excluded or None)


NO_FILTERS = Filters(status=None)


@dataclass
class Hit:
    chunk: Chunk
    score: float


def load_chunks(path: Path = CHUNKS) -> list[Chunk]:
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            chunks.append(
                Chunk(
                    id=data["id"],
                    doc_id=data["doc_id"],
                    text=data["text"],
                    section_path=data["section_path"],
                    tokens=data["tokens"],
                    meta=data["meta"],
                )
            )
    return chunks


@cache
def qdrant_client(path: Path | None):
    """One client per storage folder: local Qdrant locks the folder it opens."""
    from qdrant_client import QdrantClient

    if path is None:
        client = QdrantClient(":memory:")
    else:
        path.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(path))
    atexit.register(client.close)  # before the interpreter tears down its modules
    return client


class RerankScores:
    """The cross-encoder with an on-disk cache of its scores."""

    def __init__(self, model: str = RERANKER, cache_dir: Path = RERANK_CACHE):
        self.model_name = model
        self.cache_path = cache_dir / f"{model.replace('/', '__')}.json"
        self.cache: dict[str, float] = (
            json.loads(self.cache_path.read_text(encoding="utf-8"))
            if self.cache_path.exists()
            else {}
        )

    @cached_property
    def model(self):
        from sentence_transformers import CrossEncoder

        return CrossEncoder(self.model_name, max_length=512)

    def key(self, query: str, text: str) -> str:
        return hashlib.sha256(
            f"{self.model_name}\n{query}\n{text}".encode()
        ).hexdigest()

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        keys = [self.key(query, text) for query, text in pairs]
        missing = [
            (k, pair)
            for k, pair in zip(keys, pairs, strict=True)
            if k not in self.cache
        ]
        if missing:
            scores = self.model.predict([pair for _, pair in missing])
            self.cache.update(
                (k, float(s)) for (k, _), s in zip(missing, scores, strict=True)
            )
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")
        return [self.cache[k] for k in keys]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Fuse ranked lists of item indices; returns (index, score), best first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: -item[1])


class Retriever:
    """Indexes `chunks` in the Qdrant collection `collection` (rebuilt on creation;
    the embeddings are cached) and in BM25."""

    def __init__(
        self,
        chunks: list[Chunk],
        collection: str = "chunks",
        embedder: Embedder | None = None,
        qdrant_path: Path | None = QDRANT,
    ):
        from qdrant_client import models

        self.chunks = chunks
        self.collection = collection
        self.embedder = embedder or Embedder()
        self.bm25 = BM25([chunk.search_text for chunk in chunks])
        vectors = self.embedder.passages([chunk.search_text for chunk in chunks])
        self.qdrant = qdrant_client(qdrant_path)
        if self.qdrant.collection_exists(collection):
            self.qdrant.delete_collection(collection)
        self.qdrant.create_collection(
            collection,
            vectors_config=models.VectorParams(
                size=vectors.shape[1], distance=models.Distance.COSINE
            ),
        )
        self.qdrant.upload_points(
            collection,
            [
                models.PointStruct(
                    id=i,
                    vector=vector.tolist(),
                    payload=chunk.meta | {"chunk_id": chunk.id, "doc_id": chunk.doc_id},
                )
                for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ],
        )

    @cached_property
    def reranker(self):
        return RerankScores()

    def vector_ranking(self, query: str, filters: Filters, limit: int) -> list[int]:
        response = self.qdrant.query_points(
            self.collection,
            query=self.embedder.query(query).tolist(),
            query_filter=filters.to_qdrant(),
            limit=limit,
        )
        return [point.id for point in response.points]

    def bm25_ranking(self, query: str, filters: Filters, limit: int) -> list[int]:
        scores = self.bm25.scores(query)
        allowed = np.array([filters.matches(chunk.meta) for chunk in self.chunks])
        scores = np.where(allowed, scores, -np.inf)
        order = np.argsort(-scores, kind="stable")[:limit]
        return [int(i) for i in order if scores[i] > 0]

    def search(
        self,
        query: str,
        mode: str = "hybrid_rerank",
        k: int = 5,
        filters: Filters | None = None,
        rerank_candidates: int = RERANK_CANDIDATES,
    ) -> list[Hit]:
        filters = filters or Filters()
        if mode == "vector":
            ranking = self.vector_ranking(query, filters, k)
            return [Hit(self.chunks[i], 1.0 / (r + 1)) for r, i in enumerate(ranking)]
        if mode == "bm25":
            ranking = self.bm25_ranking(query, filters, k)
            return [Hit(self.chunks[i], 1.0 / (r + 1)) for r, i in enumerate(ranking)]
        fused = rrf(
            [
                self.vector_ranking(query, filters, CANDIDATES),
                self.bm25_ranking(query, filters, CANDIDATES),
            ]
        )
        if mode == "hybrid":
            return [Hit(self.chunks[i], score) for i, score in fused[:k]]
        if mode != "hybrid_rerank":
            raise ValueError(f"unknown mode {mode!r}, expected one of {MODES}")
        candidates = [i for i, _ in fused[:rerank_candidates]]
        if not candidates:
            return []
        scores = self.reranker.predict(
            [(query, self.chunks[i].search_text) for i in candidates]
        )
        order = np.argsort(-np.asarray(scores), kind="stable")[:k]
        return [Hit(self.chunks[candidates[j]], float(scores[j])) for j in order]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search the RAG corpus.")
    parser.add_argument("query")
    parser.add_argument("--mode", choices=MODES, default="hybrid_rerank")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--type", nargs="+", dest="types")
    parser.add_argument("--all-versions", action="store_true", help="include outdated")
    args = parser.parse_args()

    filters = Filters(
        types=args.types, status=None if args.all_versions else ["current"]
    )
    retriever = Retriever(load_chunks())
    for hit in retriever.search(args.query, args.mode, args.k, filters):
        chunk = hit.chunk
        print(
            f"{hit.score:7.3f}  {chunk.id}  [{chunk.meta.get('status')}] {chunk.context}"
        )
        print("         " + chunk.text[:200].replace("\n", " "))


if __name__ == "__main__":
    main()
