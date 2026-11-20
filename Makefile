CONFIG ?= configs/claude-haiku-medium-v3.toml
RAG_CONFIG ?= configs/rag-haiku-v3.toml
NAME ?= $(shell git rev-parse --short HEAD)
NOTE ?=
RUN ?=

.PHONY: run extract metrics corpus chunks retrieval redline judge scores calibrate \
	check check-retrieval check-generation check-fresh evals agent test lint

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

# Stage 2 evals. Each run goes to its own folder: make retrieval NAME=my-change NOTE="..."
retrieval:
	uv run python scripts/eval_retrieval.py --name $(NAME) --note "$(NOTE)"

# Redline proposals for every red flag (API calls, about $0.07 with Haiku).
redline:
	uv run python scripts/run_redline.py --config $(RAG_CONFIG) --name $(NAME) --note "$(NOTE)"

# LLM judges on a generation run (about $0.5): make judge RUN=2026-11-11_haiku-v3
judge:
	uv run python scripts/judge_redline.py $(RUN)

# Rescore every generation run and rebuild its history.
scores:
	uv run python scripts/eval_redline.py

calibrate:
	uv run python scripts/calibrate_judge.py

# Thresholds of evals/thresholds.toml, as in CI; no API calls.
check: check-retrieval check-generation

# A run just generated, against the looser [fresh] thresholds: make check-fresh RUN=...
check-fresh:
	uv run python scripts/check_evals.py fresh $(RUN)

check-retrieval:
	uv run python scripts/check_evals.py retrieval

check-generation:
	uv run python scripts/check_evals.py generation $(RUN)

# The whole stage 2 loop on the current code: generate, judge, score, check.
evals:
	$(MAKE) redline NAME=$(NAME)
	$(MAKE) judge RUN=$$(date +%F)_$(NAME)
	$(MAKE) scores
	$(MAKE) check-generation RUN=$$(date +%F)_$(NAME)

# Stage 3: ask the agent one question (API calls, about $0.001-0.05 per question):
# make agent Q="Хто погоджує поступки?" [MAX_STEPS=3] [MAX_USD=0.01]
agent:
	@test -n "$(Q)" || (echo 'Usage: make agent Q="питання"'; exit 1)
	uv run python -m lease_redflag_detector.agent.cli "$(Q)" \
		$(if $(MAX_STEPS),--max-steps $(MAX_STEPS)) $(if $(MAX_USD),--max-usd $(MAX_USD))

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
