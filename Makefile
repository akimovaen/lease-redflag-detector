CONFIG ?= configs/claude-sonnet-medium.toml

.PHONY: run test lint

run:
	uv run python -m lease_redflag_detector.extraction.run --config $(CONFIG)

test:
	uv run pytest

lint:
	uv run ruff check .
