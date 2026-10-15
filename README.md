# Agentcy

AI marketing campaign generation for Malaysian SMEs — a planning agent and a
generation crew, both behind human approval gates, narrated live to a console
that shows the graph working.

## Run the whole thing

```bash
docker compose up --build
```

Then open <http://localhost:8002>.

That is the entire setup. No keys, no Node, no Python, no migrations to run:
the image builds the console and the backend together, and on first boot the
container waits for MySQL, creates the schema and embeds the corpora before it
starts serving.

Two services come up:

| Service | What it is | Published on |
|---|---|---|
| `app` | The console and the API in one image | `8002` |
| `mysql` | MySQL 8.4 | `3308` (for local tooling and the test suite) |

To stop, `docker compose down`. To throw away the database and the embedded
corpora as well, `docker compose down -v`.

## What is in there

Six rooms, reached from the rail on the left.

**Brand profile** is the workspace's company ground truth. Add the company,
audience, voice, products, approved claims and restrictions before creating a
campaign. Saving replaces the bundled demo knowledge with this profile, so the
agents can cite the user's actual products rather than a sample brand.

**Campaigns** is the work. Write a brief, and a console opens on it: the four
agents on a stage, the graph they move through, and the gates where the run
stops for you. The machine visibly recedes when a gate needs a person.

**Video studio** is a reusable vertical marketing-video pipeline. It opens on
the Agentcy software-explainer preset, but the brand, product, audience, CTA
and three-to-eight-scene storyboard are all saved with each project. That means
the same render → QA → human review → MP4 export path can produce another
product video, then reproduce it later from the saved configuration. The
storyboard is rendered locally so captions and product UI remain accurate;
FFmpeg is included in the packaged image, so this path needs no video-model API
key.

Generated b-roll is available as an opt-in per render. It never draws the
words: the renderer still composites every caption and the product panel on
top of the clip, because that is the part a video model cannot be trusted
with. If the vendor fails or is unconfigured, the render falls back to the
deterministic scene rather than failing. See "Running against a real model".

**Cinematic trailer** is the long-form AI-video path for Agentcy itself. Its
default storyboard is a 120-second, 14-shot trailer: each shot is submitted to
DashScope independently and keeps its remote task ID, so progress survives a
browser refresh and a failed shot can be retried without rebuying the rest.
The real Image Studio screenshot is copied into durable media storage and
composited untouched over the generated monitor shot; do not send a product UI
through image-to-video and present the warped result as the product. It needs
`VIDEO_PROVIDER=dashscope` and `DASHSCOPE_API_KEY`; creating the storyboard is
free, while **Generate shots** is the explicit metered action.

**Trend watch** is the only steering anyone has over what the planner treats as
"the moment". It is a watchlist of keywords; pulling one fetches its rising and
top queries, writes them to a markdown file under `backend/data/trends/`, and
chunks that file into the trend corpus. Trends are inspiration and can never
become a fact about the product, so they are indexed in a separate collection
from the company knowledge base and the scraper has no route into the other one.

Without a `SERPAPI_KEY` the watchlist still works: it returns generated samples
so the pipeline can be rehearsed offline. Those are labelled as samples in the
heading of every document they write, and the admission travels into any
concept that cites one.

**Agents** tunes the crew — how many concepts the planner proposes, how much of
the brand each agent reads, how many times the director may send work back, and
a standing instruction per agent. The standing note is appended after the
system prompt and is told the rules above it win, so it can direct the work
without loosening a grounding rule. Changes apply to the next run.

**History** keeps every planning pass and every crew run with the agent events
exactly as the console received them, so a run can be reopened and replayed
later. Runs outlive the campaigns they belong to.

## One image, not two

The console fetches `/api/...` with no base URL, so FastAPI serves the built
SPA from the same origin. That removes a whole class of setup — no second
container, no reverse proxy, no CORS, no per-environment API host — and it is
why the Dockerfile is multi-stage rather than the compose file being two
builds. Deep links like `/campaigns/3` are routes in React, so an unmatched
path falls back to `index.html`; the API is mounted first and answers its own
404s.

## Running against a real model

The container defaults both providers to `demo`, which runs the full pipeline
offline with canned copy — retrieval, citation verification, the gates and the
director's revision loop are all real, only the writing is fake, and every
canned string is prefixed `[demo]`. That is the mode to rehearse in.

The packaged app also defaults `SCRIPTED_DEMO=true`. In that mode every text,
embedding, image, and video provider is forced offline even if a paid key is
present. The strategist shows one-click rehearsal replies for the complete
journey. Image and campaign-video renders copy suitable files from the restored
workspace library into new campaign-owned URLs, replay the visible agent/QA
events, and return without model calls or token usage. The seeded campaign
video deliberately holds its planning, transfer, and QA stages on screen for
about five seconds, so the console animation is visible during a walkthrough.
If the library is empty, the local demo renderer remains the zero-cost fallback.

For the most reliable presentation, restore the checked-in workspace first:

```bash
./seed/restore.sh --reset
```

Then open the strategist and follow its suggested replies: create campaign,
plan, approve concepts in Image Studio, continue image generation twice
(copy/visual planning, then saved-media render), approve an image, then use
the docked strategist's **Generate the campaign video** reply. The local video
renderer carries the latest approved campaign image into the finished MP4.
Approve the cut and Publish opens automatically. Publish prepares previews,
copy, and downloads; it never posts to a live social account.

The campaign-video handoff opens
`/campaigns/:id/video/demo?run=render`; it builds a fresh campaign-owned local
MP4 around the approved campaign creative. A saved seeded MP4 remains the
fallback only for incomplete legacy campaigns without a usable image. For the separate long-form product-film showcase,
ask the strategist to **Open cinematic cut demo**, or open
`/cinematic-trailer/demo`. That route is read-only and shows the seeded master
cut plus its completed shot breakdown—no provider job is queued. Set
`SCRIPTED_DEMO_STAGE_SECONDS` (default `1.0`) if you want the video console to
linger longer or shorter at each visible demo stage.

Set `SCRIPTED_DEMO=false` only when deliberately testing configured live
providers.

To use a real model, put the keys in `.env` at the repo root — compose reads it:

```bash
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

One DashScope key covers every role, which is the cheapest way to run the
whole thing on real models:

```bash
LLM_PROVIDER=qwen
EMBEDDING_PROVIDER=qwen
MEDIA_PROVIDER=dashscope
VIDEO_PROVIDER=dashscope          # optional — generative b-roll
DASHSCOPE_API_KEY=sk-...
QWEN_MODEL=qwen3.7-plus
```

`qwen3.7-plus` is not an arbitrary pick. The agents all use schema-constrained
output, which on DashScope only the 3.7-plus/flash and 3.7/3.8-max series
support — `qwen-max` answers 400. It also accepts images, so the vision QA
pass can share the one model. If you pin a text model that cannot see, set
`QWEN_VISION_MODEL` to one that can.

Then `docker compose up -d --force-recreate app`.

**Changing `EMBEDDING_PROVIDER` means re-embedding**, and a restart is all it
takes:

```bash
docker compose up -d --force-recreate app
```

Vectors from two models are not comparable, so a corpus embedded by the
previous model cannot be queried at all — Chroma refuses on vector width and
reports only the two numbers. Start-up detects that, clears the affected corpus
and re-embeds it, so the volume never needs removing by hand. Anything that
still queries a stale corpus raises `StaleCorpusError`, which names the corpus,
both widths, and the command that fixes it.

Ingestion is otherwise skipped when the store already holds chunks, so an
ordinary restart never re-embeds and never re-bills. Force a re-embed with
`docker compose exec app python scripts/ingest_kb.py`, or skip it entirely with
`SKIP_INGEST=1`.

## Developing without Docker

Keep MySQL in Docker and run the two halves natively — the reload loops are
worth it:

```bash
docker compose up -d mysql
cd backend  && ../.venv/bin/python -m uvicorn app.main:app --reload
cd frontend && npm run dev        # :5173, proxies /api to :8000
```

See `backend/README.md` and `frontend/README.md`. The test suite needs the
MySQL container up, uses its separate `agentcy_test` database, and never
touches the network:

```bash
cd backend && ../.venv/bin/python -m pytest tests/ -q
```

## Marketing calendar and simpler workspace

The workspace now uses a light neutral palette with deep teal actions. Main navigation is **Chat**, **Calendar**, **Campaigns** and **Brand**. Agent settings, Trends, History, studio shortcuts and demos remain under **More**. Existing URLs keep working. The studios show the current task first; their agent graph is available under **Activity and details**.

- **Chat** is a dedicated strategist page at `/chat`. Saved conversations can discuss an annual roadmap or an individual campaign. The contextual strategist uses the same component and saved conversations.
- **Calendar** at `/calendar` has real month and year grids plus an agenda. Filter by Malaysian state and event type, add business events, maintain manual roadmaps or prepare an AI proposal.
- **Plan with AI** supports a calendar year or rolling 90-day/12-month period. Proposals use the brand profile, verified occasions, budget/capacity preferences and existing plans. Saving a proposal creates editable calendar ideas; **Create campaign** starts an ordinary campaign draft with the existing human approval gates.
- **Planning preferences** stores target states, goals, roadmap budget in MYR, campaign capacity, preparation lead time, blackout dates and reminder lead time. A state filter scopes a new calendar proposal without silently changing those preferences.
- **Needs attention** shows due tasks, unready campaigns and changed occasion dates. Mark tasks complete or snooze a reminder. These are in-app reminders; no email, WhatsApp, social posting or unattended model calls are enabled.

Public and school holiday datasets for **2026 and 2027** are checked in under `backend/data/calendar/`. They retain official BKPP/KPM source links, state applicability and publication qualifications. Dates marked subject to change remain labelled tentative. The app does not calculate replacement holidays from a blanket weekend rule. Coverage outside the imported years, special declarations and unimported observed replacements are explicitly limited; update the reviewed data when new official publications appear.

Database initialization now applies versioned Alembic migrations and imports reviewed occasions. Existing campaign/chat records remain intact. For an existing Docker installation, back up the database and then run:

```bash
docker compose up --build -d
```

For native development, initialize the schema and calendar before starting the API:

```bash
.venv/bin/python backend/scripts/init_db.py
.venv/bin/python backend/scripts/import_calendar.py
```

The second command is only necessary after editing a reviewed dataset; repeated imports are idempotent. No external requests occur during imports. Do not reset the database or restore the demo seed to upgrade. Application rollback retains additive calendar tables/data; destructive downgrades deliberately require a backup decision.

An optional labelled calendar example is available after initialization:

```bash
LLM_PROVIDER=demo .venv/bin/python backend/scripts/seed_calendar_demo.py
```

It uses the saved brand and current planning constraints, creates no production campaign and makes no paid provider calls. It can be run again safely. After `./seed/restore.sh --reset`, use the same script inside the rebuilt app container with `docker compose exec app python scripts/seed_calendar_demo.py` if you want this additional roadmap.

Calendar proposal runs retain source/input snapshots, validation events, model name, duration and errors. The provider interface does not expose token counts, so usage is recorded as unavailable rather than guessed. A malformed proposal gets at most one validation repair. Failed requests leave saved plans intact. Pending requests can be reopened; a request that remains running after a lost connection/process interruption is made retryable after 15 minutes. This first release does not include a durable background job queue.

Local Docker ports bind to `127.0.0.1`. This remains a **single-workspace application**. Authentication and isolation across campaigns, conversations, knowledge collections, media and calendar records are prerequisites for shared multi-business hosting.

Frontend production dependencies pass `npm audit --omit=dev`. The existing shadcn development generator currently has upstream glob-pattern advisories; compatible patches are applied without forcing a breaking generator downgrade.

Workspace accounts, ownership, durable AI jobs, campaign results and operational checks are documented in [the workspace upgrade guide](docs/workspace-upgrade.md).
