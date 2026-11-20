# CLAUDE.md

Instructions for the coding agent (Claude Code) working in this repository.

## Project

Red flag detection in commercial leases for the lawyer of a landlord (offices and
retail, Ukraine). Stage 1 extracts fields and red flags, stage 2 proposes redlines
with sources (RAG), stage 3 turns it into an agent with tools and an own MCP server.
Red flags are judged from the landlord's side. See README.md and REPORT.md.

## Commands

- `uv sync` installs; Python ≥ 3.12. Keys only in `.env` (template: `.env.example`).
- `make lint`, `make test` before every commit; CI runs both.
- `make check` checks the saved runs against `evals/thresholds.toml`, no API calls.
- `make retrieval`, `make redline`, `make evals` call models or cost money: say what a
  run will cost before starting it.
- Set `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` for local runs that load Hugging Face models.
- Start Ollama only for a local run that needs it, and stop it afterwards.

## Confidential data — never break these

- The landlord's internal playbook lives only under `data/raw/` and is not public.
  Never put its text in code, prompts, the corpus or docs, and never paraphrase it.
  Only the ideas the user has approved may be used, in own words. Its structure and
  numbers stay out of the own policy.
- `data/raw/` and `.env` are never committed. The repository is public.
- The pseudonymization map (real names) stays local under `data/raw/`. Pseudonymize
  personal data before a document reaches the repo; strip author metadata from DOCX.
- Never print or log API keys.

## Evals and prompts

- No case-specific tuning: a prompt change must be a general rule, never a fix for
  one failing case. Ideas that are not implemented go to `docs/improvements.md`.
- Every eval or task set is reviewed by the user (a lawyer) before it counts. Mark
  drafts as unreviewed.
- Results vary between runs: compare configurations over several runs, not one.
- Do not claim what no run or test has shown. When a number is quoted, it comes
  from a saved run in `results/`.
- Prompts are versioned files under `prompts/`; a new version gets a new file and a
  `prompts/CHANGELOG.md` entry. Each run is saved to its own folder in `results/`.
- Stay within the budget agreed for the stage; report the spend after paid runs.

## Git and CI

- Commit, push, open and merge pull requests only when the user asks.
- Never push while a CI run on the branch is in progress (`gh run list`); a push
  cancels it and wastes the paid fresh run.
- Work on a branch, never directly on `main`.

## Style

- Write code like the surrounding code: its naming, comment density and idioms.
  Ruff is the linter.
- Code, comments, docs and prompts are in English. The corpus and the model's
  answers are in Ukrainian.
