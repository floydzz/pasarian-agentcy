# Workspace ownership and dependable AI execution

This upgrade retains the existing campaign state machine and calendar approval
flow. Legacy records belong to workspace 1. Migration creates no user and grants
no visitor ownership: an installation-local setup code is required to create the
first owner. New workspaces have independent brand knowledge, campaigns, messages,
plans, settings and media. Official holiday records remain a shared read-only
catalogue; business events and planning preferences are workspace-owned.

## Start and sign in

Build the image before starting all services:

```sh
docker compose build app
docker compose up -d
docker compose ps
```

Open `http://127.0.0.1:8002`. Initial setup asks for your name, email, password,
workspace name and the code in `/data/state/bootstrap-token` inside the app
container. An operator can read that file locally using `docker compose exec app
cat /data/state/bootstrap-token`. Treat the code as a secret. It cannot be reused
to claim an already configured workspace. In this upgrade session a private,
Git-ignored copy is stored at `backend/data/.bootstrap-token` for initial setup.

The owner manages team accounts and workspaces under **Account & team**. Team
account creation does not send email. Share initial credentials privately; users
can change their password in Account, which revokes all of their sessions. Existing accounts keep their credentials when added to another workspace or restored after removal.

| Role | Allowed work |
| --- | --- |
| Owner | All workspace work, approvals, brand/agent settings, auto-mode policy, budgets and membership |
| Editor | Chat, planning, production, calendar editing and campaign results; no creative approval or settings changes |
| Reviewer | Read workspace work and approve/reject concepts, plans and creatives |
| Viewer | Read workspace work |

Opaque session tokens are stored as hashes. Cookies are HttpOnly and SameSite
Lax. Unsafe requests require the session's CSRF token; cross-site origins are
rejected. Login attempts are throttled in the database across web processes.
Sessions have a seven-day absolute lifetime and twelve-hour idle lifetime by
default. Membership is checked on each request and again when a job starts.

Owner password recovery is local and interactive:

```sh
docker compose exec app python scripts/manage_account.py owner@example.com
```

Before internet deployment, configure HTTPS at your reverse proxy,
`PUBLIC_ORIGIN=https://your-domain`, `SESSION_SECURE=true`, strong database
credentials and restricted database/network access. The included Compose file
is a loopback-only development installation, with explicitly offline demo
providers by default. It is not a production credentials template.

## Execution and recovery

`app` serves authenticated APIs and the UI. `worker` claims persistent MySQL
jobs. `chroma` serves one shared vector index to the web app and worker; its
collections are workspace-namespaced. The existing Chroma volume and legacy
workspace's collection names are preserved. Embedded Chroma remains supported
for isolated tests and single-process development when `CHROMA_HOST` is empty.

Every long operation is listed explicitly in `app/jobs.py`. It is queued before
execution. The worker invokes the existing FastAPI validation and dependency
path in-process with a trusted actor context, preserving human approval gates.
An ordinary browser or caller cannot create that trusted context.

Jobs have idempotency keys and a unique active resource key. Two requests cannot
start concurrent operations for the same campaign/resource. Database claims use
row locks and `SKIP LOCKED`. Events and results are persisted and can be replayed
after navigation, browser closure or reconnect. Successful concept and image
outputs are checkpointed separately. Database writes from an obsolete worker
are rejected by the job lease fence.

Expired leases mark jobs **interrupted**, retaining their events and saved
output. Recovery restores transient planning gates. Retry is explicit because a
provider may have charged for a call whose response was lost; the worker never
automatically repeats ambiguous paid work. Queued work can be cancelled. A call
already in flight completes so its output can be saved. Review the existing
output before choosing **Retry unfinished work** in Progress.

Provider SDK automatic retries are disabled. Qwen's existing quota-exhaustion
fallback remains observable; it is disabled under a monetary limit unless the
operator explicitly retries with a selected, priced model. Each text-model call
records model, prompt/schema fingerprint, evidence references, duration, provider
request reference, attempt count and available token usage. Unknown usage stays
null. Prices are owner-configured USD per million tokens. Estimated text costs
are not invoices and exclude media/video charges. Existing image/video run caps
remain active. Image-based model QA is flagged for manual review when its input cost cannot be reserved under an enabled text-model monetary limit. Text call/token/cost guards reserve allowance before concurrent
calls, and missing prices fail closed when a monetary limit is enabled.

## API contract

All `/api/*` routes except health/readiness, auth status, login and initial setup
require a session cookie. Media also requires authentication and matching
workspace ownership. Set `X-CSRF-Token` from `/api/auth/me` on mutations.

Long existing POST operations now return **202** with `{"__job__": {...}}` rather
than keeping a browser-owned stream alive. The frontend adapter polls the job
and supplies the original successful result shape to existing consumers.
Explicit job submission uses `POST /api/jobs` with `path`, `payload` and
`request_key`. Stored paths must match the operation catalogue. `GET
/api/jobs/{id}?after=N` returns subsequent events, a cursor and terminal status.
Job details also expose workspace-scoped usage accounting. OpenAPI documents
authentication, CSRF and the public 202 queue contract.

| Endpoint | Purpose |
| --- | --- |
| `/api/auth/*` | Login, owner setup, session identity, logout, password and workspace membership |
| `/api/jobs`, `/api/jobs/{id}` | Submit/list jobs, replay progress and inspect usage |
| `/api/jobs/{id}/cancel`, `/retry` | Cancel queued work or explicitly retry failed/interrupted work |
| `/api/campaign-directory?q=&status=&offset=&limit=` | Search/filter paginated campaign summaries |
| `/api/conversations?summary=true&limit=&offset=` | Conversation summaries without message bodies |
| `/api/conversations/{id}/messages?before=` | Earlier messages; selected threads initially load the latest 50 |
| `/api/workspace/overview` | Dashboard aggregates, review queue, recent work and reminders |
| `/api/workspace/budgets` | Owner-configured call/token/text-cost limits and model prices |
| `/api/campaigns/{id}/results` | Validated, versioned performance periods |
| `/api/health`, `/api/ready` | Process liveness; schema/database/worker/Chroma/config readiness |

Errors retain `detail` and add `code`, `request_id`, `retryable` and field-level
validation errors. Upstream failure bodies are kept out of public error
responses. Correlate private operator logs using request/job IDs.

Campaign results track spend, revenue, impressions, engagement, leads and sales
by channel and reporting period. Overlapping periods are refused; updates use a
version to prevent lost changes. ROAS remains unavailable when spend is zero.
Currencies remain separate. Chat, calendar planning and campaign concept
planning receive these explicitly user-reported measurements as historical
evidence, never as verified brand claims or proof of causation. Publish still
prepares/downloads approved media and copy; connecting social accounts and
posting to networks is a separate integration.

The console revalidates its entry HTML on refresh. Missing versioned page files
return a real 404 instead of the SPA document. If an open tab still references
files from a previous deployment, it refreshes once (at most once per minute);
persistent loading failures show a recovery screen with a manual refresh button.
Authentication cookies and saved workspace records survive this refresh. This
follows [Vite's deployment recovery guidance](https://vite.dev/guide/build.html#load-error-handling).

## Planning overview

Overview opens with a real month calendar and the next relevant marketing
occasion, using the workspace's preferred Malaysian state and Malaysia's current
date. The compact activity row and two approval items retain direct access to
reviews, saved roadmaps and background jobs; recent campaigns and preparation
reminders remain available underneath.

Calendar dates and state persist in the Overview URL. Full Calendar receives
`date`, `state`, and either `entry` or `item` so the selected context survives the
handoff. `action=plan` opens the existing proposal form for review, then is consumed;
it does not start an AI run. Discuss with strategist creates a validated scoped
conversation and places an editable brief in its composer without sending it.
When the source already has a saved item, both pages offer that existing plan or
campaign, including campaigns scheduled before the source event's month.

`GET /api/calendar?include_links=true` adds bounded `linked_items` metadata;
ordinary calendar responses remain backward compatible. Links use source IDs
and workspace ownership, not title matching. Creating a conversation can include
`campaign_id`, validated against both the active workspace and any selected plan
item. No database schema change is required for this overview.

### Calendar readability

Event names use 13px wrapping labels on desktop and tablet; the overview keeps
its calendar full width until there is enough room for both seven readable
columns and a details panel. Phones retain clear date cells with activity
markers and show full names in the date details underneath. Selecting a date
brings that panel into view and moves keyboard focus there; reduced-motion
preferences disable the smooth scroll. Month navigation does not move focus
away from the calendar.

Date-detail scrolling waits for the URL selection to commit, so page-position
restoration cannot override the requested reveal. The selected day shows all
its activities, including full descriptions and
source metadata. Saved campaign ideas show strategy, rationale, audience,
products, proposed offer, budget, campaign dates, preparation dates and tasks.
The dedicated Calendar page uses the same read-only detail renderer in its
selected-date list. Selection does not send a chat message, run AI or create a
campaign; the existing review and strategist actions remain explicit.

### Local commit phases

The earlier delivered work was consolidated into four reviewable commits on
15 October 2026. These group the final integrated implementation by dependency,
rather than recreating intermediate states from the original delivery plan:

1. Backend foundation: authentication, workspace ownership, calendar data and
   migrations, strategist/campaign services, durable jobs, accounting and tests.
2. Workspace UI: palette, responsive navigation and studios, shared Chat,
   calendar/overview, account controls, jobs and campaign results.
3. Calendar readability: larger wrapping names, full date details and accessible
   selection behavior across overview and dedicated Calendar.
4. Release verification: responsive browser regressions, CI, generated OpenAPI
   and setup/recovery documentation.

## Migration, backup and rollback

The schema revision is `20261015_workspaces`, following the calendar and chat
context revisions. The upgrade is additive: existing rows gain workspace 1,
agent/request-key uniqueness becomes workspace-scoped, and new authentication,
job and result tables are added. Legacy additive-column reconciliation is now
tracked in the migration. MySQL schema initialization takes an advisory lock;
only the app initializer performs it, while workers retry until it is ready.
Future changes belong in new Alembic revisions, not bootstrap column lists.

Stop application and worker writes before a coordinated backup. Back up MySQL,
Chroma and media together, store them privately outside source control, and
restore into a separate installation before relying on them. Local private
backups for this upgrade are under `backend/data/backups/`; `.gitignore` and
`.dockerignore` exclude backups, assets, bootstrap secrets and browser traces.
Do not publish those files or mount the state volume under the media root.

The database backup was restored into `agentcy_upgrade_rehearsal`; the migration
was applied twice, verifying preserved legacy records and ownership backfill.
There is no destructive downgrade that strips ownership. Application rollback
must retain the authenticated compatible schema, or restore the coordinated
pre-upgrade backup into an isolated stopped installation. Do not run the old
unauthenticated application against newly separated customer workspaces.

## Verification

Local verification on 2026-10-15 passed 649 backend tests, 45 browser tests
(three duplicate end-to-end journeys intentionally skipped), and the frontend
production build. After the final date-selection ordering fix, the 20 planning
calendar browser scenarios were rechecked across all four configurations.
Lint completed with 31 non-failing warnings. Migration
and restore checks preserved all 706 legacy records across 22 tables and verified
520 media/knowledge files. Provider calls in the automated journey use offline
fixtures; these checks do not spend live AI credits.

```sh
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec playwright install chromium
npm --prefix frontend run test:browser
```

Backend tests refuse to reset a MySQL database whose name does not end in
`_test`. Real-session security tests use their own disposable SQLite database;
legacy gate/provider tests use an explicit test-only actor. Browser tests start
an entirely temporary offline installation, independent of the user's database
and credentials. They cover protected navigation, real calendar rendering,
panels, errors, query persistence, job recovery and results entry at desktop,
tablet, phone and reduced-motion settings. CI runs those checks on MySQL 8.4.

Implementation references: [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[SQLAlchemy scoped loader criteria](https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#sqlalchemy.orm.with_loader_criteria),
[Chroma client/server mode](https://docs.trychroma.com/production/chroma-server/client-server-mode),
[Playwright web servers](https://playwright.dev/docs/test-webserver).
