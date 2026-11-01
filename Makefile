CONFIG ?= configs/claude-haiku-medium-v3.toml

.PHONY: run extract metrics test lint

run: extract metrics

extract:
	uv run python -m lease_redflag_detector.extraction.run --config $(CONFIG)

metrics:
	uv run python -m lease_redflag_detector.extraction.metrics

test:
	uv run pytest

lint:
	uv run ruff check .
