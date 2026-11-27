CONFIG ?= configs/claude-haiku-medium-v3.toml
RAG_CONFIG ?= configs/rag-haiku-v3.toml
NAME ?= $(shell git rev-parse --short HEAD)
NOTE ?=
RUN ?=

.PHONY: run extract metrics corpus chunks retrieval redline judge scores calibrate \
	check check-retrieval check-generation check-fresh check-agent evals agent chat agent-evals review \
	notes candidates promote mcp test lint

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
check: check-retrieval check-generation check-agent

# A run just generated, against the looser [fresh] thresholds: make check-fresh RUN=...
check-fresh:
	uv run python scripts/check_evals.py fresh $(RUN)

check-retrieval:
	uv run python scripts/check_evals.py retrieval

check-generation:
	uv run python scripts/check_evals.py generation $(RUN)

# The saved final runs of the agent tasks, or other runs: make check-agent [RUN=...]
check-agent:
	uv run python scripts/check_evals.py agent $(RUN)

# The whole stage 2 loop on the current code: generate, judge, score, check.
evals:
	$(MAKE) redline NAME=$(NAME)
	$(MAKE) judge RUN=$$(date +%F)_$(NAME)
	$(MAKE) scores
	$(MAKE) check-generation RUN=$$(date +%F)_$(NAME)

# Stage 3: ask the agent one question (API calls, about $0.001-0.05 per question):
# make agent Q="Хто погоджує поступки?" [MAX_STEPS=3] [MAX_USD=0.01]
#   [FAULTS=search_corpus:503] (tool failures on purpose, see agent/faults.py)
#   [AS_USER=litigator] (another user of configs/users.toml; not USER, the login
#   name, nor AS, make's assembler)
agent:
	@test -n "$(Q)" || (echo 'Usage: make agent Q="питання"'; exit 1)
	uv run python -m lease_redflag_detector.agent.cli "$(Q)" \
		$(if $(MAX_STEPS),--max-steps $(MAX_STEPS)) $(if $(MAX_USD),--max-usd $(MAX_USD)) \
		$(if $(FAULTS),--faults "$(FAULTS)") $(if $(AS_USER),--as $(AS_USER))

# A conversation with the agent in the terminal (API calls, about $0.006 a question):
# make chat [AS_USER=litigator]
chat:
	uv run python -m lease_redflag_detector.agent.chat $(if $(AS_USER),--as $(AS_USER))

# Stage 3 tasks with deterministic checks (API calls, about $0.2 a run):
# make agent-evals NAME=my-change [NOTE="…"] [ONLY="n01 q03"] [REPEAT=3]
agent-evals:
	uv run python scripts/eval_agent.py --name $(NAME) --note "$(NOTE)" \
		$(if $(ONLY),--only $(ONLY)) $(if $(REPEAT),--repeat $(REPEAT))

# The lease registry MCP server alone (stdio), for the MCP Inspector or Claude Desktop;
# the agent starts its own. No API calls.
mcp:
	REGISTRY_USER=$(or $(AS_USER),lawyer) uv run python -m \
		lease_redflag_detector.agent.registry_server

# The approval queue the agent fills: list, show one, decide (a person, not the agent).
# make review BY=lawyer [ID=R-0001] [STATUS=погоджено|відхилено|повернуто COMMENT="…"]
review:
	uv run python -m lease_redflag_detector.agent.review $(if $(ID),--id $(ID)) \
		$(if $(STATUS),--status $(STATUS)) $(if $(BY),--by $(BY)) \
		$(if $(COMMENT),--comment "$(COMMENT)")

# The lawyer's notes the agent keeps (a person, not the agent): list, forget one.
# make notes BY=lawyer [ID=N-0003 FORGET=1]
notes:
	uv run python -m lease_redflag_detector.agent.notes $(if $(BY),--by $(BY)) \
		$(if $(ID),--id $(ID)) $(if $(FORGET),--forget)

# The lawyer's feedback as eval tasks: the candidates, a draft, the task set.
# make candidates BY=lawyer [ID=F-0007 ACCEPT=1 | DISMISS=1]; make promote ID=F-0007
candidates:
	uv run python -m lease_redflag_detector.agent.candidates candidates \
		$(if $(BY),--by $(BY)) $(if $(ID),--id $(ID)) $(if $(ACCEPT),--accept) \
		$(if $(DISMISS),--dismiss)

promote:
	uv run python -m lease_redflag_detector.agent.candidates promote $(if $(ID),--id $(ID))

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
