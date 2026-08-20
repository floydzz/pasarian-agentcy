# Agentcy — backend

FastAPI + MySQL + Chroma. Phase 1 foundations: campaign schema, the two
knowledge corpora, Google Trends ingestion, and the planning agent behind a
human approval gate.

## Run it

```bash
docker compose up -d mysql          # from the repo root — MySQL 8.4 on :3307
python scripts/init_db.py           # create the schema
python scripts/ingest_kb.py         # embed data/company_kb + data/trends
uvicorn app.main:app --reload       # http://127.0.0.1:8000/docs
```

`scripts/ingest_kb.py` calls a real embedding provider, so it needs
`OPENAI_API_KEY` (or `DASHSCOPE_API_KEY` with `EMBEDDING_PROVIDER=qwen`) in
`.env`. Everything else runs without keys.

## Tests

```bash
../.venv/bin/python -m pytest tests/ -q
```

The suite needs the MySQL container up; it never touches the network. Chroma
runs for real against a deterministic local embedder, and the LLM providers are
exercised through injected fakes rather than mocks.

## Layout

| Path | What it holds |
|---|---|
| `app/domain.py` | Pydantic contracts + the campaign status machine |
| `app/models.py` | SQLAlchemy tables: campaigns → concepts → variants → assets |
| `app/llm/` | Provider-swappable structured output (Claude, OpenAI, Qwen) |
| `app/rag/` | Chunking, embeddings, the two-collection Chroma store, ingestion |
| `app/trends/` | SerpApi Google Trends (`geo=MY`) with on-disk snapshots |
| `app/agents/planner.py` | Brief → grounded, cited concepts |
| `app/api/` | Routes, schemas, dependency wiring |
| `data/` | Company KB and the hand-curated trend seed |

## Two rules the code enforces

**The corpora never merge.** Company knowledge and trend signals live in
separate Chroma collections, are retrieved separately, and enter the prompt
under separate headings with an explicit ranking: the brief directs, company
knowledge is ground truth, trends are inspiration only. A concept that cites a
trend chunk as brand grounding has that citation stripped.

**Nothing advances itself.** Campaign status moves one step at a time, only
through the API, and generation cannot open until a human has approved at least
one concept.
