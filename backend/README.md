# Agentcy — backend

FastAPI + MySQL + Chroma + LangGraph. The planning agent and the generation
crew, both behind human gates, both narrated to the console as they run.

## Run it

For the packaged application — console included, nothing to install — use
`docker compose up --build` from the repo root and see `../README.md`. This is
the native loop, which is the one worth having while writing code:

```bash
docker compose up -d mysql          # from the repo root — MySQL 8.4 on :3308
python scripts/init_db.py           # create the schema
python scripts/ingest_kb.py         # embed data/company_kb + data/trends
uvicorn app.main:app --reload       # http://127.0.0.1:8000/docs
```

Then `cd ../frontend && npm run dev` for the console on :5173, which proxies
`/api` here. If `../frontend/dist` exists, this app also serves that build at
`/` — the same mount the container uses, so the packaged layout is exercised in
development rather than only in CI.

## Running without keys

Set both providers to `demo` in `.env`:

```bash
LLM_PROVIDER=demo
EMBEDDING_PROVIDER=demo
```

Nothing leaves the machine and nothing is billed. Retrieval, citation
verification, the gates and the director's revision loop all run for real —
only the writing is canned, and every canned string is prefixed `[demo]` so it
can never be mistaken for the model's work. This is the mode to rehearse the
demo in; see the risk register in the implementation plan.

With a real provider, `scripts/ingest_kb.py` needs `OPENAI_API_KEY` (or
`DASHSCOPE_API_KEY` with `EMBEDDING_PROVIDER=qwen`), and `LLM_PROVIDER` needs
the matching key. **Switching embedding provider means re-ingesting** — vectors
from two models are not comparable, so `rm -rf .chroma` first.

## Tests

```bash
../.venv/bin/python -m pytest tests/ -q
```

The suite needs the MySQL container up; it never touches the network. Its API
harness forces LLM and embeddings to `demo`, so a developer's `.env` cannot
affect results. Chroma runs for real against a deterministic local embedder,
and the LLM providers are exercised through injected fakes rather than mocks.

## Layout

| Path | What it holds |
|---|---|
| `app/domain.py` | Pydantic contracts + the campaign status machine |
| `app/models.py` | SQLAlchemy tables: campaigns → concepts → variants → assets |
| `app/llm/` | Provider-swappable structured output (Claude, OpenAI, Qwen) |
| `app/rag/` | Chunking, embeddings, the two-collection Chroma store, ingestion |
| `app/trends/` | SerpApi Google Trends (`geo=MY`) with on-disk snapshots |
| `app/agents/planner.py` | Brief → grounded, cited concepts, and gate edits |
| `app/agents/crew.py` | The LangGraph: copywriter → art director → director |
| `app/agents/video_studio.py` | Generic storyboard render, QA and file-persistence service |
| `app/agents/events.py` | What the agents report about themselves as they work |
| `app/api/` | Routes, schemas, NDJSON run streaming, dependency wiring |
| `app/brand_profile.py` | User-entered company ground truth, rendered for the company corpus |
| `app/video/explainer.py` | Configurable vertical MP4 renderer; uses FFmpeg for H.264 encoding |
| `data/` | Company KB and the hand-curated trend seed |
| `scripts/` | Schema creation, ingestion, and the container's DB wait |

## Two rules the code enforces

**The corpora never merge.** Company knowledge and trend signals live in
separate Chroma collections, are retrieved separately, and enter the prompt
under separate headings with an explicit ranking: the brief directs, company
knowledge is ground truth, trends are inspiration only. A concept that cites a
trend chunk as brand grounding has that citation stripped.

**Nothing advances itself.** Campaign status moves one step at a time, only
through the API, and generation cannot open until a human has approved at least
one concept. Auto-mode bypasses the screen, not the state machine — concepts
still carry an explicit `approved` status, so the audit trail cannot tell the
difference between auto-mode and a human who approved everything.

**No loop is unbounded.** The director gets two revisions. Past that the
variants fall through carrying `director_status="flagged"` and the director's
last notes, because a demo must never hang on an agent and a reviewer must
never be handed work while being told it was approved.

**The video studio is deterministic by design.** It is not a text-to-video
prompt: it renders each persisted marketing-video storyboard into an MP4 so
captions and product UI stay exact. The Agentcy software walkthrough is a
default preset, not a special code path. Docker includes FFmpeg; a native
backend needs it on `PATH` to call `POST /api/videos/render`.
