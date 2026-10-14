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

Stage 1: red flag detection on the ALeaseBERT annotations.

| Model | Precision | Recall | F1 | Cost / lease | Latency / lease |
|---|---|---|---|---|---|
| | | | | | |

## Data

[ALeaseBERT: A Benchmark for Lease Contract Review](https://doi.org/10.21942/uva.19732993)
by Leivaditi, Rossi and Kanoulas (University of Amsterdam): 179 commercial leases annotated
with entities and red flags. Licensed under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

The annotations are used as ground truth to measure how well the system finds red flags.

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
data/raw/       # original documents (not in git)
data/processed/
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

## License

The code is released under the [MIT License](LICENSE).

The ALeaseBERT dataset is **not** covered by the MIT License. It is licensed separately under
CC BY-NC 4.0 and may be used for non-commercial purposes only, with attribution to its authors.
