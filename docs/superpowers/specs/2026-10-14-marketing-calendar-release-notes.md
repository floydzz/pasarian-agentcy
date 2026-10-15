# Marketing Calendar: Phase 1–4 release verification

> Historical verification of the initial 14 October release. The subsequent
> authenticated workspace, durable jobs, current graphite/ivory/champagne palette,
> planning overview and automated regression coverage are documented in
> [the current upgrade guide](../../workspace-upgrade.md). The limits below
> describe that initial release, not the current installation.

Delivered locally on 14 October 2026. Preview: http://127.0.0.1:8002/calendar.

## Delivered behavior

1. **Workspace:** light neutral/deep teal theme, dedicated Chat, simplified primary navigation, campaign next actions, and technical activity behind a disclosure. Chat and the contextual strategist reuse one implementation. Existing studio, history, agents, trends, demo, and export routes remain reachable.
2. **Calendar:** real month and twelve-month grids plus agenda; Malaysian state/type filters; reviewed 2026/2027 public-holiday and school-break records; source/status metadata; business events; editable plans, items, tasks, and preferences. Mobile retains date cells and uses a sheet for details.
3. **AI planning:** annual roadmap and selected-item proposals use the existing structured provider and strategist. Authoritative dates come from saved source records. Proposals are validated and reviewed before saving. Replanning preserves manual tasks and completed work. One item converts idempotently to a campaign and production conversation, retaining the existing concept/creative approval gates and export flow.
4. **Readiness:** in-app deadlines and source-change notices, snoozing, persisted run history, explicit failure/retry handling, optimistic conflicts, migration/import scripts, demo fixtures, and setup documentation.

Annual plans contain at most 24 campaign ideas; detailed generated preparation is limited to the next 90 days. Saving an annual strategy does not automatically produce every campaign. Production briefs remain snapshots when calendar dates are edited.

## Verification

| Check | Result |
| --- | --- |
| Backend `../.venv/bin/python -m pytest tests/ -q` | **624 passed** in 15.63s; one existing Starlette status-code deprecation warning |
| Frontend `npm run build` | Passed TypeScript and production Vite build; largest JS chunk approximately 281 KB |
| Frontend `npm run lint` | Exit 0, no errors; React lint warnings remain, including effects/ref patterns in changed calendar/chat components |
| `git diff --check` | Passed |
| Production dependency audit | 0 reported vulnerabilities with `npm audit --omit=dev`; seven upstream development-tool advisories remain |
| Existing-schema upgrade | Automated legacy campaign/conversation preservation and repeat-upgrade checks passed |
| Concurrent campaign creation | Two independent database transactions returned the same campaign and conversation |
| Calendar validation | Date boundaries, state filtering, source changes, malformed proposals, stale versions, budgets, manual/completed task preservation, and campaign handoff covered by backend tests |
| Real browser | Chat yearly planning, proposal review/save, month/year/agenda, event details, plan/campaign links, and mobile 390px layout verified |
| Packaged creative journey | Holiday → AI proposal → saved plan → campaign → concepts → approval → 3 images → approval/export → 9-second video → QA → approval/export completed with demo providers |
| Packaged runtime | App and MySQL healthy, localhost-only ports; final backend service and frontend index hashes match workspace |

The browser exercise created clearly marked demo plans and campaign 23, `[demo] Hari Deepavali campaign`, while preserving the existing application data. No paid model/media provider or external posting was used. Temporary native development servers were stopped; Docker remains running in demo mode.

## Runtime/build detail

A cold Compose build was stopped because registry downloads were extremely slow. Runtime verification used the existing local `agentcy:latest` dependency image, added Alembic, and copied the current backend and compiled frontend into a new local image. That packaged image was run through Compose and exercised with its bundled FFmpeg. A clean, from-scratch Docker dependency build has **not** been confirmed by this verification.

The current demo environment was passed to Compose at startup; it was not written over the project `.env`. Use the documented provider configuration for a deliberate non-demo restart. The existing application has one unauthenticated workspace and is bound to loopback. Shared multi-business hosting still requires authentication and isolation across the entire app.

## Operational limits

- Holiday datasets are reviewed local publications, not a live feed. Ad hoc declarations and observed replacements need explicit sourced updates and re-import. Tentative dates stay labelled. Existing plans expose source changes for review.
- Reminders appear inside the app. Email/WhatsApp/push, external calendar sync, automatic posting, and sales attribution are outside this version.
- AI run execution uses the current request/stream lifecycle, without a durable job queue. Interrupted runs expose recovery; stale running requests become retryable after 15 minutes.
- Browser verification was performed against the real UI. No automated frontend regression suite is claimed.
- The implementation is verified against the checks above; warning-free lint, paid-provider behavior, and public production deployment are not claimed.
