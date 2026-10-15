# AI Marketing Calendar and Workspace Redesign Implementation Plan

Date: 2026-10-14

Follow-up: the current palette, authenticated workspaces, durable jobs and
planning overview are documented in [the upgrade guide](../../workspace-upgrade.md).
The architecture and visual decisions below record the original plan.

Status: Delivered through Phase 4 on 2026-10-14. See [release verification](../specs/2026-10-14-marketing-calendar-release-notes.md).

Build a state-aware Malaysian marketing calendar connected to the existing strategist and campaign pipeline. Simplify the interface around Chat, Calendar and Campaigns, using the selected light neutral and deep teal palette. Deliver the existing single-workspace product first; shared multi-tenant hosting requires the broader isolation work described below.

## Product decisions

- Chat is a dedicated page and the main starting point for strategy discussions.
- Calendar is a real interactive calendar with month, year and agenda views. Month is the default; retain a usable month grid on mobile with an explicit Agenda view switch.
- Campaigns remains the place to review concepts, produce creatives, approve images/video and prepare exports.
- The calendar contains verified occasions, private business events, saved marketing ideas, campaign periods and preparation deadlines. Users can filter these independently.
- An annual plan is an editable marketing roadmap. Creating it does not create twelve campaigns or trigger media generation.
- Detailed preparation is generated for selected items in the next 90 days. Later months contain high-level ideas until the user asks for detail.
- Reminders in version one appear inside the app. Email, WhatsApp, push notifications, external calendar sync and social posting are later features.
- Existing human approval gates and explicitly enabled auto-approval behavior retain their current semantics. New campaigns use the existing false defaults for auto-approval.
- Publish continues to mean preview/export in this app. Calendar status must not imply a post went live.

## Existing architecture and integration points

| Existing component | Observed behavior | Planned change |
| --- | --- | --- |
| `frontend/src/App.tsx` | `/chat` redirects to `/?chat=open`; no calendar route | Restore `/chat`; add `/calendar`; retain existing campaign routes |
| `frontend/src/pages/Chat.tsx` | Full chat implementation exists but is not routed | Reuse the active dock component in full-page mode |
| `frontend/src/components/os/MarketingChatDock.tsx` | Handles saved threads, campaign context and authorized studio navigation | Reuse its current behavior in the dedicated page; offer a contextual panel only when requested |
| `frontend/src/components/os/Shell.tsx` | Forces dark mode and gives the dock 27rem of desktop space | Apply light tokens and simpler navigation; remove forced dark mode and duplicate chat mounting |
| `frontend/src/components/os/Sidebar.tsx` | Nine main destinations expose work and machine configuration | Prioritize Chat, Calendar, Campaigns and Brand; move secondary tools under More/settings |
| `backend/app/agents/chat.py` | One structured response proposes a bounded action | Add validated calendar context and narrowly defined planning proposals |
| `backend/app/api/chat.py` | Validates proposed actions; one campaign per conversation | Execute calendar proposals through calendar services; retain one campaign per production conversation |
| `backend/app/models.py` | `Campaign.source_event` is a nullable string | Preserve it as a display/provenance snapshot; add durable plan-item relationships |
| `backend/app/agents/planner.py` | Already accepts `source_event` | Supply the selected occasion plus validated campaign timing in planner input |
| `backend/app/api/history.py` | Records campaign runs and agent events | Reuse event vocabulary; add calendar run history independent of a campaign |
| `backend/app/db.py` | `create_all` plus additive column reconciliation; no migration framework | Add explicit versioned migrations for constraints, indexes and existing records |
| `backend/app/models.py`, `api/profile.py`, `rag/store.py` | Single brand/workspace and shared corpora | Preserve single-workspace scope; do not advertise multi-tenant support |

Do not rewrite FastAPI, SQLAlchemy, the structured LLM provider, LangGraph campaign production, React Router, Tailwind v4 or the existing component system.

## Navigation and page responsibilities

### Main navigation

1. Chat — strategy, questions and proposed plans.
2. Calendar — timing, occasions, annual roadmap and preparation.
3. Campaigns — active work and approvals.
4. Brand — products, audience, restrictions and planning preferences.

Settings/More contains Agents, Trends and History. Image/video studios and Publish remain available inside campaign workspaces. Standalone studio shortcuts remain accessible under More for existing users. Progress is surfaced within the campaign and remains reachable through its existing route. Product demo/trailer routes remain available under More/demo access.

Keep `/` as the campaign directory for backward compatibility. Add `/campaigns` as its canonical navigation destination without breaking existing links. `/chat` becomes a real destination. Existing `?chat=open` links open the contextual strategist on their current route; replace internal links with explicit Chat destinations where that better fits the task.

On small screens, use labelled navigation for Chat, Calendar and Campaigns, with Brand/settings in More. Avoid an icon-only navigation rail as the sole way to discover core pages.

### Chat page

- Collapsible conversation history, spacious central transcript and a fixed composer within the chat pane.
- Starting suggestions: “Plan my next 90 days”, “Build a yearly marketing plan”, “What should I promote next month?”
- Selected occasion, plan and campaign appear as compact context above the composer. Switching threads restores their persisted context.
- Recommendations render as readable summaries with reason, suggested timing, missing inputs and one next action.
- Draft actions provide “Save to calendar”, “Adjust” and “Dismiss”. Saving a plan does not start production.
- Calendar navigation can open Chat with a selected occasion/item ID. The server resolves the ID; URL text never supplies authoritative holiday facts.
- A campaign conversation shows “Review concepts”, “Review images” or “Review video” according to live state. These links lead to the existing review surface.
- Only one transcript/composer mounts at a time. On Chat, hide the floating dock. In Calendar or a campaign, opening contextual chat shares the same thread, draft and pending state.
- Share conversation loading, sending and authorized-action routing through the same component in full-page/dock modes. Preserve the dock's current actions, demo suggestions and campaign adoption; do not simply reactivate the older page and maintain two action implementations.

### Calendar page

Toolbar: previous/next, Today, month/year title, Month/Year/Agenda switch, Malaysian state filter, event filters, Add event and Plan with AI.

The main area is a seven-column month grid containing actual date cells and event labels. Multi-day campaign bars span their date range. Limit visible entries per cell and provide an accessible “+N more” list. Clearly mark today and the selected date.

The year view displays twelve navigable mini-month grids. Selecting a month opens it; selecting an occasion opens its details. “Plan the year” starts a roadmap draft for the selected calendar year. Also support a rolling 12-month plan crossing December.

A collapsed-by-default details panel opens when an event is selected. It shows date/source/status, applicable states, campaign idea, preparation deadlines and linked campaign. On phones it becomes a sheet; month navigation and date selection remain available.

Event actions depend on type:

- Official occasion: Ask strategist, Add a marketing plan.
- Business event: Edit, Plan a campaign, Archive.
- Plan item: Edit, Accept plan, Create campaign, Open campaign when linked.
- Deadline: Mark complete, Adjust date, Open related plan/campaign.

Show a compact “Needs attention” section for due tasks, incomplete planning and holiday changes. Keep AI suggestions out of date cells until saved, so the calendar remains legible.

Use FullCalendar's standard React implementation for month, list and multi-month views, themed to the app. It supports React 19 and a year grid; validate the selected release's package/API compatibility before installation and pin a matching set. Current v7 and older v6 imports differ, so do not mix documentation versions. Do not add Premium resource scheduling for this scope.

References: [React integration](https://fullcalendar.io/docs/react), [multi-month grid](https://fullcalendar.io/docs/multimonth-grid).

### Campaign experience

- Campaign directory shows campaign name, occasion/date when present, readable status and a single primary next action.
- Campaign hub presents Brief → Concepts → Creatives → Review → Export as user-facing steps while retaining existing backend status transitions.
- Keep image and video available as clear tabs/actions within the campaign.
- Show a concise stage summary during generation. Put the agent graph, retrieved evidence, token usage and detailed logs behind “Activity and details”; retain full observability.
- Show calendar timing and a link back to the plan on campaign pages. Editing a plan does not silently rewrite a production brief or regenerate approved work.

## Visual system

Selected direction: light neutral surfaces with deep teal interaction color.

| Role | Proposed token |
| --- | --- |
| App background | `#F7F8F5` |
| Main surface | `#FFFFFF` |
| Muted surface | `#EEF2EE` |
| Main text | `#172B29` |
| Secondary text | `#52645F` |
| Borders | `#DCE5DF` |
| Primary action | `#0F625B` |
| Primary hover | `#0B4C47` |
| Selected surface | `#E3F1EB` |
| Attention | `#946313` |
| Error | `#B43D3D` |

Use the already installed Geist font, a compact type scale, 14–16px readable body text, tabular dates/numbers, restrained borders and 8–12px corner radii. Use teal for actions and selection; semantic states get text/icon labels alongside restrained color. Verify contrast for the actual text/surface combinations.

Replace forced dark surfaces and hardcoded white/black utility colors throughout touched screens, not just root variables. Audit gradient/telemetry-specific backgrounds, dialogs, tooltips, media controls and toasts. Media preview canvases may retain a dark backdrop where it helps inspect the creative.

Prefer one primary action per section, short labels and disclosure of advanced controls. Preserve visible keyboard focus, sensible tab order, sufficient touch targets, reduced-motion support and screen-reader names. Avoid decorative motion that competes with planning.

Required states: first-use brand setup, missing planning inputs, empty plan, loading, provider failure, data-source unavailable, unavailable holiday year, unsaved edits and conflicting updates. A failed request must not render as an empty calendar or erase the current draft.

## Calendar facts and data sourcing

Use a small reviewed dataset backed by official publications, not LLM-generated holiday dates. Start with the current year and next year wherever the official calendars are available. Record missing coverage explicitly instead of guessing future dates.

Primary source: [BKPP federal and state holiday publications](https://www.kabinet.gov.my/hari-kelepasan-am/). School calendar sources should point to the original KPM publication. Treat festival periods, commercial occasions and public holidays as distinct categories even when they share dates.

Version one ingestion:

1. Prepare versioned JSON records under `backend/data/calendar/` with official source URLs and reviewer metadata.
2. Run an explicit import script that validates dates, state codes, unique source identities and source revisions, then upserts in a transaction.
3. Persist verification time, source revision and publication status. Keep the last valid dataset when import validation fails.
4. Record changes so plans referencing an older revision show “Date/source changed — review timing”.

This is a controlled import workflow, not a promise of automatic live government synchronization. A later adapter may fetch a stable feed; the calendar page never scrapes remote websites during rendering.

Store actual occasion dates separately from observed replacement holidays and link them where appropriate. Use explicit state applicability, including exceptions, rather than assuming a federal occasion applies uniformly. Include confirmed/tentative/withdrawn status. Do not implement a blanket “Sunday means Monday replacement” rule.

All-day occasions and planning deadlines use SQL `DATE` and ISO `YYYY-MM-DD` values. User-facing planning uses `Asia/Kuala_Lumpur`. Audit/job timestamps keep the existing UTC contract. Calendar rendering adapts inclusive domain end dates to the library's exclusive end convention at one boundary, with leap-year and cross-year tests.

## Persistence

Use ordinary relational records for relationships and queryable dates. Use JSON for bounded generated strategy details and input snapshots; do not hide campaign links or task deadlines in unqueryable prose.

| Table | Essential contents |
| --- | --- |
| `calendar_occasions` | Stable key, title, category, start/end dates, applicable state codes, observed-for ID, source URL/revision, verification time and publication status |
| `business_events` | Title, dates, description, archived flag; private to the workspace |
| `marketing_preferences` | Selected states, timezone, goals, planning budget/currency, campaign capacity, lead times and blackout periods; singleton in current app |
| `marketing_plans` | Name, start/end dates, goals/constraints snapshot, draft/accepted/archived state and optimistic version |
| `marketing_plan_items` | Plan ID, optional occasion/business-event ID, title, rationale, audience/product references, strategy, proposed offer, estimated budget, campaign dates, preparation start, proposed/planned/skipped/cancelled state, nullable unique campaign ID and version |
| `marketing_tasks` | Plan-item ID, title, due date, relative offset/anchor where relevant, todo/done state and manual-date override |
| `calendar_runs` | Requested operation/range, pending/running/succeeded/failed state, bounded input snapshot, output/proposal, model usage when available, events, errors and request key |

Add nullable `marketing_plan_id` and `marketing_plan_item_id` context to conversations. Validate that a supplied item belongs to the supplied plan. A conversation can discuss a whole annual plan; production conversations remain bound to a single campaign.

Keep `Campaign.source_event` as the compatible label snapshot. The linked plan item carries the durable connection; record the selected occasion revision and campaign input snapshot when converting it. Future changes to holiday titles do not rewrite existing campaign provenance.

Constraints and indexes:

- Stable source key/revision strategy prevents duplicate imported occasions.
- Date-range indexes support bounded calendar queries; cap requested ranges and returned records.
- Plan items index `(plan_id, campaign_start)` and tasks index `(status, due_date)`.
- A unique nullable `marketing_plan_items.campaign_id` enforces the version-one one-to-one link.
- Archive accepted plans/items rather than deleting provenance. Campaign deletion clears the item link with `SET NULL`; the roadmap and task history survive.
- Existing campaigns and conversations remain valid with null calendar relationships.
- Require expected version for edits and draft acceptance; return a recoverable 409 if another tab changed the record.

Introduce Alembic migrations for the new schema and additive conversation fields. Bootstrap/stamp existing databases only after checking the known schema, run upgrades before app startup, and avoid a destructive reset. Test both a clean database and an existing seeded database. New tables can initially coexist with legacy additive reconciliation, but new migrations own calendar fields and constraints. Back up before upgrades; application rollback should normally retain additive data. Downgrades that drop calendar data require an explicit backup/recovery decision.

## Calendar services and AI behavior

Keep three explicit responsibilities:

1. Calendar query service selects authoritative occasions, business events, accepted items, linked campaign progress and deadlines for the requested range.
2. Marketing planning service assembles bounded context, calls the existing structured provider and validates proposed strategy/items.
3. Calendar application service accepts proposals, edits plans and converts one item into a campaign transactionally.

Suggested modules: `backend/app/marketing_calendar.py` for queries/application operations, `backend/app/agents/calendar_planner.py` for structured AI planning, and `backend/app/api/calendar.py` for endpoints. Split further only when responsibilities become difficult to trace.

Context includes:

- Verified relevant occasion IDs/dates/state applicability and their revisions.
- Brand profile, product facts, approved claims and restrictions.
- Planning goals, budget/capacity and known operational deadlines.
- Existing planned items/campaigns to avoid repetition and overlap.
- Separately labelled trend inspiration, following the existing grounding hierarchy.

The LLM may choose an occasion ID and propose a campaign window. It cannot create authoritative public-holiday dates, claim stock availability, confirm a discount or claim a budget was spent. Resolve occasion facts server-side and reject unknown IDs, reversed ranges, out-of-plan dates, negative budgets and invalid product references. Check total suggested budget/capacity after model output. Missing budgets stay unknown; any illustrative amount must be labelled as an estimate.

An annual draft is one bounded structured request with at most 24 items. It does not produce a year of post copy or trigger per-item generation. Detailed task planning is a separate explicit operation for selected near-term items. Keep retries bounded to the existing provider policy and a limited validation repair; fail with an editable proposal or clear error rather than accepting fabricated facts.

Cache/reuse identical accepted inputs and require explicit regeneration to incur another call. Existing accepted/manual items remain in place: regenerated results are proposals with an explicit merge preview, not replacement writes.

Store provider latency, usage when available, source IDs/revisions, validation failures and action outcomes. Reuse `AgentEvent` and stream rendering conventions. `calendar_runs` is separate because annual planning has no campaign yet; do not create a dummy campaign to satisfy campaign Run history.

Planning runs follow the app's existing stream architecture. Persist the run before provider work and the proposal before its terminal success event. Reopening the page fetches the saved run/proposal. A running row after restart is marked interrupted; manual retry is explicit. Version one does not promise work continues after process death. Avoid holding database locks while waiting for the provider.

### Strategist integration

Extend the existing structured response schema with optional typed calendar proposals and a small set of calendar intents: view calendar, propose annual plan, propose item plan and propose item edit. Reuse common planning services rather than duplicating logic in chat prompts.

The executor validates current record/version and request intent. A model proposal does not itself accept an annual plan, move a campaign date or start production. Chat exposes the returned proposal and calls the same accept/create endpoints as Calendar after the user's corresponding action.

Calendar context comes from database IDs on every relevant turn. Pass only the selected item and a bounded date window rather than every event in the year. A missing or archived context gets a visible status and can be cleared; never silently attach a different plan.

Keep annual strategy conversations unbound to production campaigns. “Create campaign” for a selected item creates/reuses a campaign-specific conversation and opens it or the campaign. The annual conversation retains its plan context and links to the result.

### Campaign conversion

Use the same conversion operation for Chat and Calendar:

1. Load the selected planned item and validate current version, required inputs and user edits.
2. Lock/recheck the item in a short database transaction. If a campaign already exists, return it.
3. Construct the ordinary campaign brief from accepted strategy, dates, products, approved offer and constraints; set `source_event` from the authoritative occasion/event title.
4. Create the campaign in `draft`, save its input snapshot and link it to the item in the same transaction.
5. Create/reuse its production conversation and return links to the campaign and calendar item.
6. Existing `/plan/stream` and generation/render endpoints handle the remaining work through their existing state checks and review gates.

One item creates at most one campaign in version one; double clicks and retries return the same campaign. Users wanting a separate variant campaign duplicate the plan item explicitly. Do not run an LLM or media call inside the conversion transaction.

After conversion, task completion may use real concept/asset/video approvals where appropriate. Manual business tasks remain manual. Production state is read from the campaign; do not maintain a second writable campaign status in the calendar.

## API outline

Keep the existing `/api/conversations` and campaign endpoints backward compatible. New names below are proposed contracts to finalize with Pydantic and TypeScript together.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/calendar?start=&end=&state=&types=` | Bounded unified calendar entries; includes coverage/source metadata |
| `GET /api/calendar/preferences` / `PUT` | Planning preferences |
| `POST /api/calendar/business-events` | Create a private dated event |
| `PATCH /api/calendar/business-events/{id}` | Update/archive an event with expected version |
| `GET /api/marketing-plans` / `POST` | List/create a manual plan |
| `GET /api/marketing-plans/{id}` / `PATCH` | Read/update a plan, including accepted state |
| `POST /api/marketing-plans/{id}/items` | Add a manual plan item |
| `PATCH /api/marketing-plan-items/{id}` | Edit, accept, skip or cancel an item |
| `POST /api/calendar/runs` | Create an idempotent annual/item planning request |
| `GET /api/calendar/runs/{id}` | Read durable run/proposal state |
| `POST /api/calendar/runs/{id}/stream` | Execute one pending run with guarded state transition; stream progress |
| `POST /api/calendar/runs/{id}/accept` | Apply a reviewed proposal against expected plan/item versions |
| `POST /api/marketing-plan-items/{id}/campaign` | Transactionally create/reuse its draft campaign |
| `PATCH /api/marketing-tasks/{id}` | Mark complete or edit a due date |
| `GET /api/calendar/attention` | Due tasks, readiness issues, date changes and resolvable links |

Return stable entry IDs, source/entity references and typed entry kinds so the frontend opens the correct detail view. Do not infer behavior from an event title. Validate state codes, ranges, field sizes, versions and all foreign-key relationships in the API.

## Readiness reminders

Derive reminders from current persisted dates and production state on app/page load and after related actions. Version one requires no always-on scheduler or background model calls.

- Preparation deadline approaching, with configurable lead time.
- Overdue manual task.
- Campaign start approaching while concepts or assets await approval.
- Changed/withdrawn occasion source affecting a saved plan.
- An accepted plan exceeding the user's configured capacity/budget.

Use stable reminder keys and persist snooze/dismissal only where needed, resetting when the underlying issue meaningfully changes. Include a direct next action. A lack of inventory/order integration means inventory warnings can only refer to user-entered tasks, not claimed live stock.

## Workspace and tenant boundaries

The current app intentionally has one brand profile and no authentication. Version one runs within that existing deployment model. Adding `workspace_id` only to calendar tables would not isolate existing campaigns, conversations, media or RAG.

Before shared multi-business hosting, add authenticated membership and server-derived workspace context across all existing/new resources, enforce ownership on every relationship, namespace retrieval collections/caches, protect media access, migrate existing records to an initial workspace and test cross-workspace access failures. Apply this to run history, exports and streaming as well. This is a prerequisite for shared hosting, not a completed property of the calendar MVP.

## Delivery sequence

### Phase 1 — Simplify the workspace and restore Chat

- [x] Add shared light/teal tokens and audit hardcoded dark colors.
- [x] Simplify navigation while preserving all existing routes/features.
- [x] Share the active chat component/action routing and restore the dedicated `/chat` page.
- [x] Hide duplicate dock on Chat; preserve contextual conversation access elsewhere.
- [x] Simplify campaign directory/hub and put technical detail behind Activity.
- [x] Verify existing strategist → concepts → image/video → review → export journey.

Exit: existing production flow works in the new visual shell with a standalone Chat page and no lost conversations.

### Phase 2 — Calendar foundation

- [x] Add versioned migrations and test upgrades on the existing seed.
- [x] Add reviewed occasion datasets/importer with year coverage metadata.
- [x] Add preferences, custom events, plan/items/tasks and bounded calendar queries.
- [x] Build `/calendar` with actual month/year grids, agenda and event detail/edit flows.
- [x] Implement state/type filters, cross-year ranges and date-only handling.

Exit: a user can browse Malaysian occasions, add business events and maintain a manual annual roadmap without AI.

### Phase 3 — AI planning and campaign handoff

- [x] Add bounded structured annual/item planning and persisted run/proposal records.
- [x] Integrate calendar context and proposal cards into the current strategist.
- [x] Add review/accept/edit flow and safe proposal merging.
- [x] Add idempotent plan-item conversion shared by Chat and Calendar.
- [x] Link calendar items, campaign timing and production conversations in both directions.
- [x] Extend demo provider/scripted-demo responses so the new flow works offline and bills nothing.

Exit: “Plan my next year” produces an editable roadmap; one selected item proceeds through the existing campaign pipeline with source provenance intact.

### Phase 4 — Readiness and release verification

- [x] Add in-app attention reminders and readiness links.
- [x] Handle source revisions, optimistic conflicts, provider failures and interrupted runs.
- [x] Complete responsive/accessibility checks and offline end-to-end coverage.
- [x] Update README/seed restore instructions and add a representative calendar demo fixture.

Exit: existing seeded users can upgrade without data loss, and calendar planning remains usable when AI or remote source availability fails.

## Verification and acceptance criteria

Use existing offline pytest/API patterns. Verify the critical cross-page flow in the real browser; automated backend tests cover persistence, validation, and campaign integration. A maintained automated frontend test suite is deferred.

- Existing database upgrade preserves campaigns, conversations, approvals and media links; fresh installs also work.
- State-specific holidays filter correctly; missing future coverage is visible; the LLM cannot insert fake official occasions.
- Leap days, observed dates, multi-day ranges and December-to-January planning render on the intended dates in Malaysia.
- Annual generation is bounded, respects known budget/capacity and can return useful drafts with explicit missing inputs.
- A rejected/malformed/provider-failed proposal does not overwrite an accepted plan or hide a previously valid calendar.
- Repeated proposal acceptance and two simultaneous campaign-conversion requests cannot duplicate items/campaigns.
- Concurrent edits return a recoverable conflict instead of losing user changes.
- One annual strategy conversation can link to several campaign conversations without replacing its own campaign association.
- Calendar → Chat → accept item → create campaign → plan → approve concepts → generate/review creatives → export works in demo mode without paid calls.
- Existing direct Chat/campaign/studio/export links continue to resolve, and reviews still enforce the current backend state machine.
- A campaign date or official occasion change shows a reviewable difference; approved production work is not silently rewritten.
- Mobile calendar retains real date cells, labelled navigation, touchable entries and readable agenda/detail views.
- Keyboard users can change date/view, inspect events, edit a plan and reach the next campaign action. Labels distinguish event types and status without color alone.
- UI build/lint pass, backend calendar/chat/campaign integration checks pass, and browser smoke tests cover the restored Chat and Calendar routes.

Defer ad-platform/sales integrations, automatic posting, notification delivery, external calendar synchronization, recurring event rules, advanced drag scheduling, and automated ROI learning until this planning-to-production loop is reliable.
