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

Later stages propose a redline for each red flag, citing the landlord's policy, its
approved clauses and the law, run the whole review through an agent, and serve it as
an API.

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
2. **RAG.** For a red flag, find what the policy, the clause library, the law and past
   committee decisions say and propose a redline with a verdict and a risk level,
   citing a source for every claim; quality tests.
3. **Agent.** Multi-step tasks using tools.
4. **Service.** API, auth, monitoring, cost tracking.

Current stage: 3.

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

Stage 2: redlines for 24 red flags, scored against expected answers reviewed by the
landlord's lawyer; details, the judge calibration and the error analysis are in
[REPORT.md](REPORT.md#report--stage-2-rag).

| Model | Prompt | Retrieval recall | Trap passages | Verdict | Risk | Expected sources cited | Faithfulness | No answer → lawyer | Latency p50 | $ / 1000 red flags |
|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | rag/v3 | 0.95 | 0 | 0.88 (0.79–0.88) | 0.83 | 1.00 | 0.73 | 2 of 2 | 23 s | 2.82 |

The numbers are of the saved production run; the verdict range is over five runs of
the same config (mean 0.84), so differences of a few hundredths are noise. Both
questions without an answer went to the lawyer in all five runs.

The main error: when the sources do not settle a question, the model names the gap but
still gives a verdict instead of not_covered (0 of 2 such flags). So every answer with
a gap is marked in code as needing the lawyer's decision: both such flags are referred,
and 0 to 4 of the 13 answers that need none.

## Stage 2: RAG

**Scenario.** An assistant for the lawyer of a landlord, a private company that lets
offices and retail premises in Ukraine. Given a red flag from the stage 1 extractor
(its type and the clause quote), it finds what the landlord's leasing policy, its
approved clause wording, the law and the minutes of the commercial committee say, and
proposes a redline: a verdict by the levels of the policy, a risk level, the changed
clause and the points the sources do not settle, citing the document and section for
every claim. In stage 3 an agent runs it over every red flag found in a lease.

**Search by role.** A redline rests on different kinds of source: the policy says what
is wrong with the clause (position), the clause library gives approved wording, the
law sets the bounds, the minutes give precedents, market leases give background. In
one ranked list the policy and the library crowd out the law and the minutes, so each
role is searched on its own, with a metadata filter that also keeps outdated documents
out. Details and numbers are in [REPORT.md](REPORT.md#report--stage-2-rag).

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

Two techniques are used in a lighter form. With the role search finding 0.95 of the
expected passages, neither was needed on this eval set; they are the next step if a
larger or held-out set shows misses:

- **Contextual headers instead of contextual retrieval.** Anthropic's contextual
  retrieval has an LLM write a sentence of context for each chunk. Here the context is
  the heading path, which costs nothing, is deterministic and for these documents says
  the same: which act, which chapter, which article.
- **Section-sized chunks instead of parent-child retrieval.** Small-to-big retrieval
  searches small chunks and returns their parent section. Most sections here fit one
  chunk; for long contract sections the parent can be added later if needed.

#### Structural against fixed size

Compared with fixed windows of 350 tokens and 50 tokens of overlap, on six documents
(two policy documents, two laws, two leases):

| | Structural | Fixed size |
|---|---|---|
| Sections and clauses kept whole in one chunk | 100% | 89% |
| Chunks starting in the middle of a sentence | 5% | 81% |
| Chunks that can be cited by section | 98% | 0% |

The first row is 100% for the structural chunker by construction, since it never cuts a
unit that fits a chunk; it measures what fixed windows lose.

In the search evaluation on the 24 red flags, the production role search finds 0.95 of
the expected passages over structural chunks and 0.90 over fixed windows; the gap is
in the law articles (0.93 against 0.70) and the committee precedents (1.00 against
0.71), where a window mixes two or three units. In one ranked list the difference is
small (0.70 against 0.68). Details are in [REPORT.md](REPORT.md#retrieval). The
fixed-size chunks are computed on the fly there and here, not stored. Per-document
numbers are in
[results/rag/chunking_comparison.md](results/rag/chunking_comparison.md)
(`uv run python scripts/compare_chunking.py`).

## Stage 3: lease registry as an MCP server

The agent of stage 3 reads leases through its own [MCP](https://modelcontextprotocol.io)
server, the lease registry ([registry_server.py](src/lease_redflag_detector/agent/registry_server.py)).
The rest of the agent (the loop, the tools, the approval queue, the eval tasks) is
described in [REPORT.md](REPORT.md) at the end of the stage.

### Why a separate server

- **One place for access rights.** Who may read which lease is decided in the server,
  so it holds for every client: the agent, Claude Desktop, another agent. The agent's
  own tools that need a lease's text (red flags, redlines) take it from the server
  too, and are refused exactly when the lawyer is.
- **A replaceable registry.** Today it reads the pseudonymized leases of the corpus; a
  company would put its CRM or document system behind the same tools, and the agent
  would not change.
- **The server describes its tools.** The agent takes their names, descriptions and
  schemas from the server, as any MCP client does; the descriptions are the versioned
  files in [prompts/tools/](prompts/tools/).

### What it serves

| Name | Kind | For | What it returns |
|---|---|---|---|
| `find_leases` | tool | the model | leases by part of a party's or city name; a closed lease marked `restricted` with the reason |
| `get_lease` | tool | the model | parties, date and the numbered sections of a lease |
| `read_lease_section` | tool | the model | the text of one section |
| `lease://{lease_id}` | resource | code | the full text, for the red flag extractor and the redline generator |
| `leases://shared` | resource | code | the leases every user of the caller's entity may read: the only ones a redline may use as market practice |

It only reads. Every argument is validated (a lease id is `lease_` and digits, a filter
is one of two fields); nothing runs a query, opens a path or a shell from its
arguments. An expected failure goes to the client as its message, any other without
details. The agent starts it as a subprocess over stdio with only the safe environment
variables of the MCP SDK, so the API keys stay with the agent.

### Access rights

Users ([configs/users.toml](configs/users.toml)) and the marks of the leases
([configs/lease_access.toml](configs/lease_access.toml)) are fictional, chosen with the
landlord's lawyer:

| User | Role | Legal entity |
|---|---|---|
| `lawyer` | lawyer | ТОВ «Орендодавець» |
| `litigator` | litigation team | ТОВ «Орендодавець» |
| `head` | head of legal | ТОВ «Орендодавець» |
| `lawyer_b` | lawyer | ТОВ «Орендодавець-Б» |

| Reason | Lease | Who reads it | In others' search |
|---|---|---|---|
| B: another legal entity of the group | `lease_56855` | users of ТОВ «Орендодавець-Б» | not listed |
| A: a court dispute | `lease_35532` | the litigation team | listed as restricted |
| C: an NDA with an anchor tenant | `lease_92441` | the head of legal | listed as restricted |

A refused read gets the reason, e.g. `Access denied: lease_92441: it is under an NDA
with an anchor tenant; only the head of legal may read it.` The agent sees it as a
`denied` error, which is never retried. Two more paths are closed in code:

- `search_corpus` never returns a lease of the registry, so a lease is read only
  through the registry;
- a redline takes signed leases as market practice only from those open to the whole
  entity, since it goes to the approval queue, where others read it: even the head of
  legal does not bring the NDA lease into a redline.

`make review` shows a person only the requests for the leases they may read, and
records a decision only by a lawyer or the head of legal who may read the lease. The
same holds for the lawyer's notes the agent keeps across conversations
([memory.py](src/lease_redflag_detector/agent/memory.py)): a note about a lease
reaches only whoever may read the lease, and the agent keeps or forgets one only
after the lawyer confirms. After each answer of `make chat` the lawyer may rate it or
correct it ([feedback.py](src/lease_redflag_detector/agent/feedback.py)): a correction
may become a note on its lease, a committee's rejection becomes one, and a minus is a
candidate for the eval tasks, moved into them only once the lawyer has reviewed its
checks and they fail the answer the lawyer corrected.

**What shows it.** [tests/test_bypass.py](tests/test_bypass.py) runs an agent that asks,
as the lawyer, for the NDA lease through every tool, over the real corpus with BM25 and
Qdrant: no phrase of the lease reaches any tool result, and the head of legal reads
every phrase back. Disabling any of six protections in turn makes the test fail. With
the real model, nine access tasks (a denial and a control for each reason, "I am the
head of legal" in the question, a closed lease not submitted) passed in 27 of 27 runs
([results/agent/runs/](results/agent/runs/), `2026-11-24_access-tasks*`); the agent never
asked for a closed lease again.

### Limits

- **No real authentication.** Whoever starts the agent says who they are
  (`AS_USER=`, `REGISTRY_USER`): anyone can start it as `head`. In a company this would
  be a sign-in with the corporate account, passed to the server instead of the
  variable. What is real is that the model cannot change the user: it is not an
  argument of any tool.
- One user per server process, local only (stdio); no network transport.
- The approval queue, the notes and the feedback are local SQLite files
  (`data/agent/`, not committed), one set for everyone who works on the machine.
- After a denial the agent sometimes offers "confirm you are the head of legal and I
  will read it", which nothing in the conversation can do; a prompt fix is planned
  ([docs/improvements.md](docs/improvements.md)).

### Running it

```sh
make agent Q="Який строк дії договору lease_35532?" AS_USER=litigator  # as another user
make review BY=lawyer                    # the approval queue as lawyer sees it
make mcp AS_USER=head                    # the server alone, over stdio
npx @modelcontextprotocol/inspector -e REGISTRY_USER=lawyer \
  uv run python -m lease_redflag_detector.agent.registry_server        # try it by hand
```

In Claude Desktop (`claude_desktop_config.json`), with the path of your clone:

```json
{
  "mcpServers": {
    "lease-registry": {
      "command": "uv",
      "args": ["--directory", "/path/to/lease-redflag-detector", "run", "python",
               "-m", "lease_redflag_detector.agent.registry_server"],
      "env": {"REGISTRY_USER": "lawyer"}
    }
  }
}
```

If Claude Desktop does not find `uv`, give its full path (`which uv`): a desktop app
may not see the PATH of the terminal. The same command is checked by a test (it starts
the server and reads a lease); it was not tried in Claude Desktop itself, and the
MCP Inspector command was not run.

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
and municipal property, and commercial leases of some companies). They are public
information without an explicit license, used here for non-commercial research with
personal data pseudonymized; `scripts/fetch_prozorro.py` downloads them. See
[data/README.md](data/README.md).

## Project structure

```
src/lease_redflag_detector/
  extraction/   # stage 1
  rag/          # stage 2
  agent/        # stage 3
  api/          # stage 4
configs/        # run configs: model, prompt, sampling (rag-*.toml for stage 2,
                #   agent-*.toml for stage 3); users.toml, lease_access.toml
prompts/        # versioned prompts and their changelog
results/        # stage 1: one JSON per text and run, metrics.md
results/rag/    # stage 2: retrieval/ and generation/ runs with history.md,
                #   judge calibration, chunking comparison
results/agent/  # stage 3: runs of the agent tasks with their traces, history.md
data/texts/     # stage 1 evaluation texts and their manifest
data/corpus/    # stage 2 RAG corpus: sources, documents, chunks, manifest
data/golden/    # stage 1 reference outputs
data/raw/       # original documents (not in git)
data/processed/ # caches: embeddings (not in git), reranker scores (committed for CI)
scripts/        # dataset and corpus building, golden set tools, evals, LLM judge,
                #   chunking comparison, run merging
evals/          # stage 2 eval sets: red flags with expected passages and answers,
                #   the lawyer's grades for judge calibration, CI thresholds;
                #   stage 3 agent tasks (agent_tasks.toml)
docs/           # improvement ideas by level
notebooks/      # experiments
tests/
.github/workflows/  # CI: evals.yml on every push, retrieval.yml when search can change
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

**Stage 2 in one command:** `make evals` generates redlines for the 24 red flags of the
eval set, runs the LLM judges, scores the answers and checks the thresholds (about
$0.6); `make redline` alone generates without the judges (about $0.07). Answers come
from Claude Haiku 5.5 at $2.82 per 1,000 red flags; the embedding model and the
reranker run locally at no cost.

Stage 2 runs on the committed chunks (`data/corpus/chunks.jsonl`); the embedding
model and the reranker are downloaded from Hugging Face on the first run. Every run
goes to its own folder under `results/rag/` and is added to its `history.md`:

```sh
make corpus    # rebuild data/corpus/documents (needs the Prozorro leases in data/raw)
make chunks    # rebuild data/corpus/chunks.jsonl from the documents
make retrieval NAME=my-change NOTE="what changed"   # retrieval eval, no API calls
make evals NAME=my-change                           # generate, judge, score, check (about $0.6)
make redline NAME=my-change                         # or step by step: generate (about $0.07)
make judge RUN=2026-11-13_my-change                 # LLM judges (about $0.5)
make scores                                         # rescore every generation run
make calibrate                                      # judge against the lawyer's grades
make check                                          # thresholds of evals/thresholds.toml
```

**Stage 3:** the agent answers one question at a time; it uses Claude Haiku 5.5 and
costs about $0.006 per question (its budget per request is $0.05). The registry
server and the access rights are above.

```sh
make agent Q="Перевір договір lease_55572 на ризики для орендодавця."  # about $0.014
make agent Q="…" AS_USER=litigator FAULTS=search_corpus:503   # another user, a failing tool
make chat [AS_USER=head]                 # a conversation: several questions, remembered
make notes BY=lawyer [ID=N-0003 FORGET=1]     # the lawyer's notes the agent keeps
make candidates BY=lawyer [ID=F-0007 ACCEPT=1]  # minuses and corrections from make chat
make promote ID=F-0007                   # a reviewed draft into the task set
make review BY=lawyer [ID=R-0001] [STATUS=погоджено COMMENT="…"]   # the approval queue
make agent-evals NAME=my-change [ONLY="a26 a27"] [REPEAT=3]   # all the tasks, about $0.25
```

CI runs on every push and pull request
([.github/workflows/evals.yml](.github/workflows/evals.yml)): lint, tests and the saved
production generation run rescored against the expected answers, and the totals of
the final runs of the agent tasks; the role search
([retrieval.yml](.github/workflows/retrieval.yml)) runs when the search can change. A
run fails when a metric is below its threshold in
[evals/thresholds.toml](evals/thresholds.toml). A pull request to main also generates
new answers (about $0.07, needs the `ANTHROPIC_API_KEY` repository secret), unless it
changes only documentation; the LLM judges run only by hand from the Actions tab. See
[REPORT.md](REPORT.md#ci).

## License

The code is released under the [MIT License](LICENSE).

The ALeaseBERT dataset, the Prozorro.Sale leases and the legislation texts are **not**
covered by the MIT License (the legislation is not an object of copyright). ALeaseBERT
is licensed separately under CC BY-NC 4.0 and may be used for non-commercial purposes
only, with attribution to its authors.
