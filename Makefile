CONFIG ?= configs/claude-haiku-medium-v3.toml

.PHONY: run extract metrics corpus chunks test lint

run: extract metrics

extract:
	uv run python -m lease_redflag_detector.extraction.run --config $(CONFIG)

metrics:
	uv run python -m lease_redflag_detector.extraction.metrics

# Stage 2: rebuild the RAG corpus (needs data/raw/, see data/README.md) and its chunks.
corpus:
	uv run python -m lease_redflag_detector.rag.ingest

chunks:
	uv run python -m lease_redflag_detector.rag.chunking

test:
	uv run pytest

lint:
	uv run ruff check .
