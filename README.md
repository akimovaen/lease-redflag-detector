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

Current stage: 2.

## Results

Stage 1: extraction of 9 fields and red flags from 30 lease texts in English and
Ukrainian, scored against a golden set of 10. Best run of each model; details, all
configs and the error analysis are in [REPORT.md](REPORT.md).

| Model | Prompt | Field accuracy | Red flag F1 | Valid outputs | Latency p50 | $ / 1000 leases |
|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | v3 | 0.98 | 0.84 | 100% | 3.4 s | 34.18 |
| claude-haiku-5-5 | v3 | 0.96 | 0.80 | 100% | 10.8 s | 2.89 |
| qwen3:8b (local, Ollama) | v3 | 0.39 | 0.37 | 53% | 92 s | 0 |

Production choice: Claude Haiku 5.5 with prompt v3. The golden set is small, so
differences below about 0.08 F1 are within run-to-run noise.

## Stage 2: RAG

**Scenario.** An assistant for the lawyer of a landlord, a private company that lets
offices and retail premises in Ukraine. Given a question or a lease clause a tenant
proposes, it finds what the landlord's leasing policy, its approved clause wording and
the law say, and answers or proposes a redline, citing the document and section for
every claim. In stage 3 an agent runs it over every red flag the stage 1 extractor
finds in a lease.

**Corpus.** 35 Ukrainian documents in four formats (DOCX, PDF, HTML, Markdown),
described in [data/README.md](data/README.md#rag-corpus):

- the landlord's documents, written for this project (the company is fictional): the
  leasing policy, current (2026) and outdated (2024), the clause library, minutes of
  the commercial committee, a market study, a brochure, a web page, a staff newsletter;
- a draft lease sent by a tenant;
- laws and resolutions from zakon.rada.gov.ua, two of them no longer in force;
- 19 signed leases from Prozorro.Sale, mostly scans read with OCR; nine are by one
  landlord on one template.

The outdated policy and laws, the near-identical leases and the marketing texts that
promise more than the policy allows are there on purpose: they are the traps a RAG
system falls into.

**Ingestion** (`make corpus`): extraction that keeps headings, numbered clauses, lists
and tables; cleaning of page headers and footers, hyphenation, OCR look-alike letters
and site chrome; pseudonymization; exact and near-duplicate detection; a manifest.

### Chunking

Chunks follow the structure of the documents (`make chunks` →
`data/corpus/chunks.jsonl`):

1. A document is split at its headings into sections: an article of a law, an entry
   of the clause library, a section of a policy or a contract. A chunk never spans two
   sections.
2. A section of up to 450 tokens is one chunk. A longer one (a contract section, a
   chapter of the lease procedure) is packed from whole paragraphs, list items and
   tables up to about 350 tokens, cut before a numbered clause.
3. Only a single paragraph over 450 tokens is split, at sentence ends; a table at row
   ends, repeating its header row.
4. The document title and the path of headings are prepended to the chunk for
   retrieval: "Політика … > 4. Дострокове розірвання договору орендарем". The header
   counts toward the 512 tokens the embedding model reads, so nothing is cut off.
5. A few words of a contract with no sentence in them or in its signature block
   ("АКЦІОНЕРНЕ ТОВАРИСТВО ОРЕНДАР:") are dropped: they match many queries and answer
   none.

Why this way:

- **The unit of an answer is the unit the documents are written in.** A lawyer cites
  "Article 774 of the Civil Code" or "clause 4.2 of the policy". A chunk that holds
  exactly that unit can be cited by section, and the answer can be checked against it.
- **A rule cut in two is dangerous.** Policy clauses read "acceptable concession: … but
  not earlier than 24 months …"; a window that ends before the condition retrieves a
  permission without its limit.
- **Sizes come from the documents and the embedding model.** A Civil Code article is
  98 tokens at the median and at most 233; a contract section is 512 at the median,
  and one in ten is over 1,500. The embedding model (multilingual-e5) reads at most
  512 tokens, so 450 leaves room for the header. Units larger than that are split by
  clause, which keeps each chunk on one topic; small units stay small, since an article
  of 80 tokens is a complete answer.
- **No overlap.** Chunks end at clause boundaries, and the heading path gives each
  chunk the context an overlap would.

#### Other approaches

| Approach | How it splits | Why not here |
|---|---|---|
| Fixed-size windows with overlap | every N tokens | cuts clauses and rules in two, no section to cite; measured below as the baseline |
| Recursive splitting (LangChain `RecursiveCharacterTextSplitter`) | at paragraphs, then lines, then sentences, to a size | ends at a paragraph, but not at a section: a policy section still spills into the next chunk, and the chunk does not know which section it is in |
| By page | one page of a PDF | pages of a scanned contract end mid-clause; laws and HTML have no pages |
| By sentence | one or a few sentences | too small: the condition and the exception of a rule are in other sentences |
| Semantic chunking | where the embeddings of neighbouring sentences diverge | needs every sentence embedded and a threshold to tune; the clauses of one policy section (the base position, the concessions, what is unacceptable) are about one topic, so the boundaries fall where the meaning does not change. The documents already mark their topics with headings |
| LLM chunking (propositions, agentic) | an LLM rewrites the text into self-contained statements | a call per passage of a 170,000-word corpus against a $5 budget, and the chunks are paraphrases, while an answer must quote the source word for word |
| Late chunking | embeds the whole document, then pools token vectors per chunk | needs a long-context embedding model; multilingual-e5 reads 512 tokens |

Two techniques are used in a lighter form and are the next step if the search
evaluation shows a need:

- **Contextual headers instead of contextual retrieval.** Anthropic's contextual
  retrieval has an LLM write a sentence of context for each chunk. Here the context is
  the heading path, which costs nothing, is deterministic and for these documents says
  the same: which act, which chapter, which article.
- **Section-sized chunks instead of parent-child retrieval.** Small-to-big retrieval
  searches small chunks and returns their parent section. Most sections here fit one
  chunk; for long contract sections the parent can be added later.

#### Structural against fixed size

Compared with fixed windows of 350 tokens and 50 tokens of overlap, on six documents
(two policy documents, two laws, two leases):

| | Structural | Fixed size |
|---|---|---|
| Sections and clauses kept whole in one chunk | 100% | 89% |
| Chunks starting in the middle of a sentence | 5% | 78% |
| Chunks that can be cited by section | 98% | 0% |

The first row is 100% for the structural chunker by construction, since it never cuts a
unit that fits a chunk; it measures what fixed windows lose. Which chunking finds the
right passage is measured with the search evaluation; the fixed-size chunks are
computed on the fly there and here, not stored. Per-document numbers are in
[results/rag/chunking_comparison.md](results/rag/chunking_comparison.md)
(`uv run python scripts/compare_chunking.py`).

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

Ukrainian leases come from [Prozorro.Sale](https://prozorro.sale), Ukraine's public
e-auction system, where signed leases are published after the lease auction (of state
and municipal property, and commercial leases of some companies). They are public information without an explicit license, used
here for non-commercial research with personal data pseudonymized;
`scripts/fetch_prozorro.py` downloads them. See [data/README.md](data/README.md).

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
data/texts/     # stage 1 evaluation texts and their manifest
data/corpus/    # stage 2 RAG corpus: sources, documents, chunks, manifest
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

The ALeaseBERT dataset, the Prozorro.Sale leases and the legislation texts are **not**
covered by the MIT License (the legislation is not an object of copyright). ALeaseBERT is licensed separately under CC BY-NC 4.0 and may be used for
non-commercial purposes only, with attribution to its authors.
