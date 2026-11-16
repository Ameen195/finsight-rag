# FinSight — Agentic RAG Copilot for Indian IT Annual Reports

> Project specification for Claude Code. Read this whole file before writing any code.

---

## 0. Who I am and how to work with me

- I'm Ameen, an aspiring AI Engineer. This is a **portfolio project for startup AI/ML job applications**, so code quality, evaluation and presentation matter as much as features.
- **I want to learn while we build.** After creating or changing a file, explain in 2–5 lines what it does and why that design was chosen. Explain non-obvious code with short comments.
- **Environment:** Windows, PowerShell, VS Code. Project lives at `D:\projects\finsight-rag`. Give terminal commands as **PowerShell** commands.
- **Python 3.12**, managed with **uv** (`uv add`, `uv run`). Never use plain `pip install`.
- **Deadline:** one week. Work in the phases below, in order.

### Working rules (must follow)

1. **One phase at a time.** At the start of each phase, give a short plan (files to create, key decisions). Then build it. At the end, run the checks, show results, suggest a git commit message, and **stop and wait for my approval** before the next phase.
2. **Never read, print or log the contents of `.env`.** Never hardcode API keys. All secrets come from environment variables via `config.py`.
3. **Never delete or overwrite my files** (especially `data/raw/` PDFs and `eval/golden_set.jsonl`) without asking first.
4. **Don't run `git commit` or `git push` unless I ask.**
5. **Free tier only.** No paid APIs or services. If something would need payment, stop and tell me.
6. **Ask before adding dependencies** not listed in section 3.
7. **Never invent facts or numbers for the golden set** (see Phase 3).
8. Code style: type hints everywhere, docstrings on public functions, small functions, `ruff` clean, no unused code, `logging` instead of `print` (except CLIs).
9. If a command fails, show the error, explain the cause, then fix it. Don't silently work around failures.

---

## 1. What we're building

A web app where a user asks questions about the annual reports of 5 Indian IT companies and gets **accurate answers with page-level citations**.

- **Companies (v1):** TCS, Infosys, Wipro, HCLTech, Tech Mahindra. One latest annual report each (I download the PDFs into `data/raw/`).
- **Example questions:**
  - "What was Infosys's revenue in FY2025?" (single fact)
  - "What was TCS's employee headcount at year end?" (number from a table)
  - "Compare attrition at Wipro and HCLTech." (multi-company comparison)
  - "What is TCS's revenue from Mars?" (unanswerable, so it must refuse)
- **Every answer must cite sources** as `[Company, FY, p.X]`. If the retrieved context doesn't support an answer, the system says it doesn't have enough information.

### What makes this project stand out (the priorities)

1. **Measured retrieval quality**: compare 4 retrieval configs with Hit@k and MRR on a hand-written golden set.
2. **Measured answer quality**: faithfulness, correctness, refusal accuracy.
3. **Hybrid search + reranking** in a single Postgres database.
4. **Agentic handling of comparison questions** with LangGraph.
5. **Production basics**: tests, Docker, CI, tracing, live deployment, great README.

---

## 2. Architecture

```
                    ┌──────────── OFFLINE (run locally once) ────────────┐
 data/raw/*.pdf ──► │ Docling parse ─► heading-aware chunking ─► bge-small│──► Supabase Postgres
                    │ (cache to data/parsed/)   (tables kept whole)  embed│     (pgvector + FTS)
                    └─────────────────────────────────────────────────────┘
                                                                              │
 ONLINE (deployed):                                                           ▼
 User ─► Gradio UI / FastAPI /ask ─► LangGraph agent:
           1. classify   (small LLM, JSON: type, companies, years)
           2. decompose  (comparison → one sub-question per company)
           3. retrieve   (dense + keyword ─► RRF fusion ─► metadata filter ─► rerank top20→top5)
           4. generate   (big LLM, cited answer or refusal)
           5. verify     (deterministic: every citation must match a retrieved chunk)
         ─► answer + citations + source snippets + latency
 All LLM/retrieval steps traced in Langfuse.
```

---

## 3. Tech stack (all free)

| Concern | Choice | Notes |
|---|---|---|
| Package manager | `uv` | `src/` layout, package name `finsight` |
| Config | `pydantic-settings` | Reads `.env` |
| PDF parsing | `docling` | Keeps tables; export tables as Markdown. Slow on CPU → cache output |
| Tokenizer (chunk sizing) | `tiktoken` (`cl100k_base`) | Approximate token counts |
| Embeddings | `sentence-transformers` + `BAAI/bge-small-en-v1.5` | 384 dims, `normalize_embeddings=True`. For **queries**, prepend `"Represent this sentence for searching relevant passages: "` (bge v1.5 convention); no prefix for passages |
| Reranker | `sentence-transformers` `CrossEncoder("BAAI/bge-reranker-base")` | Rerank top 20 → keep top 5 |
| Database | Supabase Postgres + `pgvector`, via `psycopg[binary]` + `pgvector` Python package | Connection string in `DATABASE_URL` (session pooler) |
| LLM | **Groq** (`groq` SDK) | Big model for answers (default `openai/gpt-oss-120b`), small model for classify/decompose/judge (default `llama-3.1-8b-instant`). Both configurable. Verify model IDs against the Groq console |
| Retries | `tenacity` | Exponential backoff on 429/5xx |
| Agent | `langgraph` | Typed state |
| Tracing | `langfuse` (Cloud Hobby, free) | Use the `@observe` decorator; app must still work if Langfuse keys are missing |
| API | `fastapi` + `uvicorn` | |
| UI | `gradio`, mounted inside FastAPI with `gr.mount_gradio_app` | One process, port **7860** |
| Tests | `pytest` | No network calls in tests |
| Lint | `ruff` | |
| Hosting | Hugging Face Spaces (Docker SDK, free CPU) | Port 7860, run as uid 1000 |
| CI | GitHub Actions | |

Already installed: `fastapi uvicorn[standard] pydantic-settings groq sentence-transformers docling psycopg[binary] pgvector langgraph langfuse gradio tiktoken`, dev: `pytest ruff`. Also allowed when needed: `tenacity`, `pyyaml`, `httpx` (tests), `python-dotenv`.

### Free-tier limits to design around

- **Groq free plan:** about 30 requests/min, 1,000 requests/day, **8,000 tokens/min**, 200,000 tokens/day **per model** (check console for exact values).
  - Keep each generation request **under ~4,000 tokens total** (5 chunks × ~500 tokens + question + answer).
  - Implement a simple client-side rate limiter (tokens-per-minute budget) + tenacity backoff.
  - Eval scripts must throttle (configurable delay) and **cache results to disk** so a crash doesn't waste quota.
- **Supabase free:** 500 MB DB; project pauses after 7 days inactive (handled by a keep-alive workflow).
- **HF Spaces free CPU:** sleeps when idle. Pre-download models at Docker build time to reduce cold start.

---

## 4. Project structure

```
finsight-rag/
├── data/
│   ├── raw/                 # PDFs (gitignored) — DO NOT modify
│   ├── parsed/              # Docling output cache (gitignored)
│   └── manifest.yaml        # list of reports to ingest
├── src/finsight/
│   ├── __init__.py
│   ├── config.py            # Settings (pydantic-settings)
│   ├── db.py                # connection, schema helpers
│   ├── models.py            # shared Pydantic models (Chunk, Citation, Answer...)
│   ├── ingest/
│   │   ├── parse.py         # Docling → structured elements with page numbers
│   │   ├── chunk.py         # heading-aware chunking, tables kept whole
│   │   ├── embed.py         # embedding model wrapper (passages + queries)
│   │   └── cli.py           # `finsight-ingest` command
│   ├── retrieval/
│   │   ├── dense.py
│   │   ├── keyword.py
│   │   ├── hybrid.py        # RRF fusion
│   │   ├── filters.py       # company / fiscal-year extraction
│   │   ├── rerank.py
│   │   └── retriever.py     # single entry point: retrieve(query, mode, filters, k)
│   ├── generation/
│   │   ├── llm.py           # Groq client wrapper: rate limit, retry, token budget
│   │   ├── prompts.py
│   │   └── agent.py         # LangGraph graph
│   └── api/
│       ├── main.py          # FastAPI app + Gradio mount
│       └── ui.py            # Gradio Blocks UI
├── eval/
│   ├── golden_set.jsonl     # WRITTEN BY AMEEN — never overwrite
│   ├── golden_set_candidates.jsonl  # Claude-generated drafts for Ameen to verify
│   ├── eval_retrieval.py
│   ├── eval_answers.py
│   └── results/             # markdown + json results (committed)
├── tests/
├── scripts/
│   └── schema.sql
├── .github/workflows/
│   ├── ci.yml
│   └── keepalive.yml
├── Dockerfile
├── .dockerignore
├── .env.example             # variable names only, no values
├── .gitignore
├── pyproject.toml
└── README.md
```

---

## 5. Database schema (`scripts/schema.sql`)

I've already run this in Supabase. Keep it in the repo as the source of truth. Add new columns only through a new SQL snippet I can run myself.

```sql
create extension if not exists vector;

create table if not exists chunks (
  id           bigserial primary key,
  company      text not null,
  fiscal_year  text not null,
  page         int  not null,
  section      text,
  content      text not null,
  is_table     boolean default false,
  embedding    vector(384),
  fts          tsvector generated always as (to_tsvector('english', content)) stored
);

create index if not exists chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);
create index if not exists chunks_fts_idx       on chunks using gin (fts);
create index if not exists chunks_meta_idx      on chunks (company, fiscal_year);
```

Suggested addition (propose it in Phase 2 and let me run it): `content_hash text` + unique index on `(company, fiscal_year, content_hash)` for idempotent ingestion.

---

## 6. Phases

Each phase lists **deliverables** and **acceptance checks**. Don't move on until the checks pass and I approve.

### Phase 1: Foundation
**Deliverables**
- `pyproject.toml` set up (src layout, console script `finsight-ingest`, ruff + pytest config).
- `config.py`: `Settings` with `groq_api_key`, `database_url`, `langfuse_*` (optional), model names, `embedding_model`, `reranker_model`, `retrieval_top_k=20`, `rerank_top_n=5`, `max_context_tokens=3000`.
- `.env.example`, `.gitignore` (must include `.env`, `data/raw/`, `data/parsed/`, `.venv/`, caches), `.dockerignore`.
- `db.py`: connection helper registering pgvector; `ping()` function.
- `models.py`: Pydantic models `Chunk`, `RetrievedChunk` (with scores), `Citation`, `AnswerResponse`.
- `generation/llm.py`: Groq wrapper with tenacity retry, simple TPM limiter, and `complete(messages, model, json_mode=False)`.
- A smoke script/command that checks: DB ping, pgvector enabled, Groq "hello" call works.

**Checks:** `uv run ruff check .` clean; smoke check passes; `.env` is gitignored (`git check-ignore .env`).

### Phase 2: Ingestion pipeline
**Deliverables**
- `data/manifest.yaml` format, e.g.:
  ```yaml
  reports:
    - company: TCS
      fiscal_year: FY2025
      pdf: data/raw/tcs_ar_fy2025.pdf
  ```
- `parse.py`: Docling conversion → list of elements `{type: heading|text|table, text, page, section_path}`. Tables exported as Markdown. **Cache** each parsed report to `data/parsed/<company>_<fy>.json`; skip parsing if the cache exists (add `--force` to re-parse).
- `chunk.py`:
  - Heading-aware: don't merge across major sections.
  - Target ~500 tokens, ~50 overlap, using `tiktoken`.
  - **Tables are standalone chunks.** If a table > 1,500 tokens, split by rows and **repeat the header row** in each part.
  - Keep the page number of where the chunk starts.
  - Drop noise: page headers/footers, empty chunks, chunks < 30 tokens.
  - **Contextual header for embedding:** embed `"{company} | {fiscal_year} | {section}\n{content}"` but store `content` cleanly.
- `embed.py`: lazy-loaded singleton model; `embed_passages(list[str])` (batched) and `embed_query(str)` (with the bge query prefix).
- `cli.py`: `uv run finsight-ingest` (all reports in manifest) or `--company TCS`. **Idempotent**: re-running replaces that report's rows in a transaction. Prints a summary table: pages, chunks, tables, avg tokens, time.

**Checks:** unit tests for chunking (table never split mid-row, header repeated, overlap correct, page numbers preserved, tiny chunks dropped) using small synthetic inputs, no PDFs needed. Run ingestion on one report and show summary stats + 3 sample chunks (one table).

### Phase 3: Golden set + retrieval
**Golden set (important honesty rule)**
- `eval/golden_set.jsonl` is **written and verified by me**. Never create, modify or overwrite it.
- Help me by generating **candidates** into `eval/golden_set_candidates.jsonl` from the parsed reports: each with `question`, `expected_answer`, `company`, `fiscal_year`, `page`, `type`, and the **exact source text** it came from. I'll verify against the PDF and copy the good ones into `golden_set.jsonl`.
- Schema per line:
  ```json
  {"id": "q001", "question": "...", "expected_answer": "...", "type": "fact|table|comparison|explanation|unanswerable",
   "companies": ["TCS"], "fiscal_year": "FY2025", "relevant_pages": [{"company": "TCS", "page": 112}]}
  ```
  Unanswerable questions have empty `relevant_pages`. Target mix: 15 fact, 10 table, 10 comparison, 5 explanation, 5–10 unanswerable.

**Retrieval deliverables**
- `dense.py`: cosine search via pgvector `<=>`, with optional company/year filter in SQL.
- `keyword.py`: Postgres FTS using `websearch_to_tsquery` + `ts_rank_cd`, same filters.
- `hybrid.py`: **Reciprocal Rank Fusion** (k=60) over dense + keyword results (top 20 each).
- `filters.py`: deterministic extraction of company names (incl. aliases: "Tata Consultancy Services", "HCL Technologies", "TechM", "Infy") and fiscal years ("FY25", "FY2025", "2024-25").
- `rerank.py`: CrossEncoder rerank top 20 → top 5.
- `retriever.py`: `retrieve(query, mode: Literal["dense","keyword","hybrid","hybrid_rerank"], filters=None) -> list[RetrievedChunk]`.
- `eval/eval_retrieval.py`: for every answerable golden question and all 4 modes, compute **Hit@1, Hit@5, MRR@10** (a hit = a retrieved chunk whose company+page matches a relevant page; allow ±1 page tolerance, configurable). Output `eval/results/retrieval.md` (markdown table) + `retrieval.json`. Also print per-type breakdown and the 5 worst questions for debugging.

**Checks:** unit tests for RRF (hand-computed example) and filter extraction. Eval runs end-to-end and produces the table. Discuss results with me and suggest one improvement if hybrid_rerank isn't clearly the best.

### Phase 4: Generation + LangGraph agent
**Deliverables**
- `prompts.py`:
  - System prompt: answer **only** from provided context; cite every factual claim as `[Company, FY, p.X]`; if context is insufficient, reply exactly with a refusal starting `"I don't have enough information in the annual reports to answer that."`; be concise; numbers must keep units and currency (₹ crore, US$ million) as written in the source.
  - Context formatting: each chunk labelled with its `[Company, FY, p.X]` tag.
- `agent.py`: LangGraph `StateGraph` with typed state:
  1. `classify` → small model, **JSON output** `{type: "single"|"comparison", companies: [...], fiscal_years: [...]}`; merge with `filters.py` results (deterministic wins on conflict).
  2. `decompose` → for comparisons, one sub-question per company.
  3. `retrieve` → `hybrid_rerank` per (sub-)question with company filter; dedupe; enforce `max_context_tokens`.
  4. `generate` → big model.
  5. `verify_citations` → deterministic: parse citations, drop/flag any that don't match a retrieved chunk; if the answer has zero valid citations and isn't a refusal, convert it to a refusal.
- Return `AnswerResponse`: `answer`, `citations` (company, fiscal_year, page, snippet), `question_type`, `latency_ms`, `trace_id` (optional).
- Langfuse `@observe` on every node + LLM call; works with no Langfuse keys.

**Checks:** unit tests for citation parsing/verification and the refusal fallback (mock LLM). Run 5 real questions (fact, table, comparison, explanation, unanswerable) and show answers + citations + latency.

### Phase 5: API, UI, tests, Docker
**Deliverables**
- `api/main.py`: FastAPI with `POST /api/ask` (body: `question`, optional `companies`), `GET /api/companies`, `GET /api/health` (checks DB). Pydantic request/response models, input length limit, sensible error responses. Models load once at startup (lifespan).
- `api/ui.py`: Gradio Blocks UI mounted at `/`:
  - Title + one-line description; question box; company multiselect filter; 4–5 clickable example questions.
  - Answer rendered as Markdown; citations as a list; expandable "Sources" panel showing each snippet with its tag.
  - Footer: latency, link to GitHub repo.
  - Clean and professional. No emojis overload.
- Tests: API tests with FastAPI `TestClient`, retriever and LLM mocked (dependency injection or monkeypatch). Whole test suite runs **offline**.
- `Dockerfile`:
  - `python:3.12-slim`, install uv, `uv sync --frozen --no-dev`.
  - **Pre-download** embedding + reranker models at build time into the image.
  - Non-root user with uid 1000 (HF Spaces requirement), `EXPOSE 7860`, run uvicorn on `0.0.0.0:7860`.
  - Install CPU-only torch to keep the image small (ask me before changing torch source config).
  - Ingestion is **not** run in the container. The DB is already populated.

**Checks:** `uv run pytest` all green; `docker build` + `docker run -p 7860:7860 --env-file .env` works locally; show me the commands.

### Phase 6: Answer evaluation, deployment, CI
**Deliverables**
- `eval/eval_answers.py`: runs the full agent on every golden question (throttled, cached to `eval/results/answers_cache.jsonl`, resumable), then uses the **small model as judge** with a strict rubric (JSON output) to score:
  - **Faithfulness** (0/1): every claim supported by the cited context.
  - **Correctness** (0/1/partial 0.5): matches `expected_answer` (numbers must match).
  - **Refusal accuracy**: refuses on unanswerable; doesn't refuse on answerable.
  - **Citation validity**: % of citations pointing to a relevant page.
  - Also p50/p95 latency.
  - Output `eval/results/answers.md` + `answers.json`, with per-type breakdown and list of failures.
- Deployment guide (in README + told to me step by step): create HF Docker Space, add secrets (`GROQ_API_KEY`, `DATABASE_URL`, Langfuse keys), push. Add HF Space YAML front-matter to README if needed (`sdk: docker`, `app_port: 7860`).
- `.github/workflows/ci.yml`: on push/PR → uv setup, `ruff check`, `pytest` (offline).
- `.github/workflows/keepalive.yml`: daily cron → `curl` the deployed `/api/health` (URL from a repo variable) so Supabase and the Space stay awake.

**Checks:** eval results tables generated; CI green on GitHub; live URL answers a question.

### Phase 7: README and presentation
**README.md** (this is what recruiters read, make it excellent):
1. Title, one-line pitch, badges (CI), **Live Demo** link, demo GIF/video placeholder.
2. The problem and what FinSight does (3–4 lines).
3. **Architecture diagram** in Mermaid.
4. **Results**: retrieval table (4 modes) + answer-quality table, pulled from `eval/results/`.
5. Key design decisions and *why*: hybrid + RRF, reranking, tables-as-chunks, contextual headers, citation verification, refusal behavior, free-tier constraints.
6. Tech stack.
7. How to run locally (PowerShell commands) and how to reproduce the eval.
8. Limitations and future work (honest).
- Also draft for me: a 150-word **LinkedIn post** and a **2-line resume bullet** using the real eval numbers (never invent numbers; leave `[X]` placeholders if a number isn't available).

---

## 7. Definition of done

- [ ] Ingestion works for all 5 reports, idempotent, with summary stats.
- [ ] Golden set of 40–50 verified questions (by Ameen).
- [ ] Retrieval eval table comparing 4 modes; hybrid_rerank justified by numbers.
- [ ] Answer eval: faithfulness, correctness, refusal accuracy, citation validity, latency.
- [ ] Agent handles comparison questions via decomposition.
- [ ] Every answer has verified citations or is an explicit refusal.
- [ ] Offline test suite green; ruff clean; CI green.
- [ ] Dockerized, deployed on HF Spaces, live URL works.
- [ ] Langfuse traces visible.
- [ ] README with diagram, results, decisions, limitations.
- [ ] No secrets in git history.
