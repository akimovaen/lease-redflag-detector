# lease-redflag-detector

AI-powered red flag detection in commercial lease agreements: extraction, RAG, agent, API.

## What it does

Commercial leases are long, dense and written in legal language. Reviewing one by hand
means reading dozens of pages to find a few clauses that actually matter for the business.

This project builds an AI system that reads a lease and points the reviewer to those clauses:

- **Input:** a commercial lease agreement as a raw document (PDF or scan).
- **Output:** the key terms of the lease in structured form (for example, parties, premises,
  dates and rent terms) and a list of red flags, each with the exact clause text it is based on,
  so every finding can be checked against the source.

Later stages let a user ask questions about a lease and get answers with citations,
run multi-step review tasks through an agent, and use all of it as an API service.

## Perspective

Contracts are reviewed from the **landlord's** side. A red flag is a clause that weakens
the landlord's economics or control over the lease, for example a tenant's right to
terminate early or a cost the landlord has to absorb.

## About the project

A learning project for an AI Engineering course. It is one system built incrementally
over four stages, each adding a new AI engineering technique on top of the previous one.

## Roadmap

1. **Extraction.** Pull structured data and red flags from raw documents (PDF, scans);
   compare a paid model with a local one.
2. **RAG.** Answer questions about a lease with citations to the source clause; quality tests.
3. **Agent.** Multi-step tasks using tools.
4. **Service.** API, auth, monitoring, cost tracking.

Current stage: 1.

## Results

Stage 1: extraction of 9 fields and red flags on 20 lease texts, scored against a golden
set of 7. Best run of each model; details, all configs and the error analysis are in
[REPORT.md](REPORT.md).

| Model | Prompt | Field accuracy | Red flag F1 | Valid outputs | Latency p50 | $ / 1000 leases |
|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | v3 | 0.98 | 0.86 | 100% | 3.1 s | 27.07 |
| claude-haiku-5-5 | v3 | 0.95 | 0.83 | 100% | 10.2 s | 2.53 |
| qwen3:8b (local, Ollama) | v3 | 0.37 | 0.40 | 55% | 60 s | 0 |

Production choice: Claude Haiku 5.5 with prompt v3. The golden set is small, so
differences below about 0.08 F1 are within run-to-run noise.

## Data

[ALeaseBERT: A Benchmark for Lease Contract Review](https://doi.org/10.21942/uva.19732993)
by Leivaditi, Rossi and Kanoulas (University of Amsterdam): 179 commercial leases annotated
with entities and red flags. Licensed under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

The leases are the source of the evaluation texts in [data/](data/README.md), which also
describes how they were selected, degraded with simulated OCR and labeled.

Raw data is not committed. Download it into `data/raw/aleasebert/`:

```sh
mkdir -p data/raw/aleasebert && cd data/raw/aleasebert
B=https://ndownloader.figshare.com/files
curl -L -o annotations-legend.json $B/35058112
curl -L -o annotated_dataset.zip   $B/35058109
unzip annotated_dataset.zip -d annotated
```

## Project structure

```
src/lease_redflag_detector/
  extraction/   # stage 1
  rag/          # stage 2
  agent/        # stage 3
  api/          # stage 4
configs/        # run configs: model, prompt, sampling
prompts/        # versioned prompts and their changelog
results/        # one JSON per text and run, metrics.md
data/texts/     # evaluation texts and their manifest
data/golden/    # reference outputs
data/raw/       # original documents (not in git)
data/processed/
scripts/        # dataset building and golden set tools
evals/          # test questions and reference answers
notebooks/      # experiments
tests/
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
uv sync
cp .env.example .env   # then set ANTHROPIC_API_KEY
```

Run the extraction for one config and score all runs:

```sh
make run                                       # the production config, Haiku with prompt v3
make run CONFIG=configs/claude-sonnet-medium-v3.toml
make metrics                                   # rescore results/ into results/metrics.md
make test
```

The local model needs [Ollama](https://ollama.com) (`brew install ollama`):

```sh
ollama serve &
ollama pull qwen3:8b
make run CONFIG=configs/qwen3-8b-t0-capped-v3.toml   # about 30–60 min on a laptop
```

## License

The code is released under the [MIT License](LICENSE).

The ALeaseBERT dataset is **not** covered by the MIT License. It is licensed separately under
CC BY-NC 4.0 and may be used for non-commercial purposes only, with attribution to its authors.
