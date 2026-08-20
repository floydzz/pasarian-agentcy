# AI marketing campaign system — requirements & implementation plan

**Team:** solo · **Timeline:** Aug 20 – Sept 15, 2026 (27 days) · **Category:** AI marketing campaign / AI agent
**Judging weights:** business value 30% · innovation 20% · AI application ability 20% · completeness 20% · presentation 10%

---

## Part 1 — requirements plan

### Problem statement
SMEs and marketers spend disproportionate time and agency budget on campaign ideation and creative production. Turnaround from brief to finished ad creative is typically days to weeks and requires an agency relationship most SMEs can't afford.

### Why it's worth doing
Turnaround-time and cost reduction, from days/weeks to hours, with real before/after numbers captured once the core loop is running end to end.

### Functional requirements, by pipeline stage

**Data layer**
- [ ] Company knowledge base: brand voice guide, product info, past campaign notes — embedded into Chroma
- [ ] Trend corpus: automated pull from Google Trends (geo=MY) via SerpApi
- [ ] Trend corpus: manually curated seed file from TikTok Creative Center + Shopee/Lazada trending (no API exists for either — refresh by hand before demo)

**Planning agent**
- [ ] Retrieves separately from trend corpus and company KB (never merged into one index)
- [ ] Context assembled with explicit roles: company KB = ground truth, trends = inspiration only, human brief = directive
- [ ] Outputs structured JSON: list of concept objects (see schema below), each with a stated `variation_axes` diversity strategy for its `variant_count`

**Approval gate**
- [ ] Per-concept review — approve / edit / reject, never all-or-nothing
- [ ] Auto-mode toggle that bypasses the screen entirely
- [ ] Edit routes to a chat handoff (not a full inline rich editor) so edits stay grounded

**Generation crew (LangGraph)**
- [ ] Copywriter agent: writes `variant_count` copy variants per concept, one per `variation_axes` entry
- [ ] Visual planner agent: runs after copywriter, consumes actual copy text to plan composition/text placement
- [ ] Director agent: reviews copy+visual pairs against brand KB, checks real variant diversity, cyclic revision loop back to the relevant agent, bounded to 2 retries before falling through flagged

**Asset generation**
- [ ] Image generation for real ad creatives (text-in-image support required)
- [ ] Video generation: cut for MVP (see scope cuts)

**Review gate**
- [ ] Automated vision QA pass on generated assets (flags garbled/misspelled on-image text, obvious artifacts) before the human sees them
- [ ] Per-asset review — approve / redo / reject
- [ ] Auto-mode toggle, same pattern as the approval gate

**Publish**
- [ ] Preview/export screen: final ad-format previews, download/copy action
- [ ] Live posting to Meta/TikTok/Google Ads: cut for MVP, integration point built but not wired to real API access (see scope cuts)

**Calendar & proactive recommendation (stretch — build after the core manual-brief path works end to end)**
- [ ] Curated JSON of ~15–20 Malaysia commercial/cultural events for the year (static, not API-driven)
- [ ] APScheduler job checking which events fall within a 2–3 week lookahead window
- [ ] Auto-drafted brief generator — formats an upcoming event into the same brief shape a human would type
- [ ] Auto-drafted briefs feed the existing planning agent unchanged; trend retrieval still happens at trigger time, not a year in advance, so it's grounded in current trends
- [ ] Approval gate shows a provenance tag on calendar-triggered concepts ("suggested: Hari Raya, 18 days out")
- [ ] Simple calendar view in the UI showing the year's events and each one's campaign status

### Non-functional requirements
- [ ] Every LLM call uses structured/tool-use output — no free-text parsing between agents
- [ ] Revision and retry loops are bounded (max 2 passes) — no unbounded loop can run during a live demo
- [ ] Auto-mode behaves identically at both gates — one consistent human-in-the-loop pattern, not two different ones
- [ ] At least one full end-to-end run recorded and working before demo day

### Competition submission checklist
- [ ] Project deck, 5–10 pages
- [ ] Demo video, 3–5 minutes
- [ ] AI workflow documentation (this doc + the architecture diagrams from planning discussions cover this)
- [ ] Answered: what problem does it solve, why worth doing, which AI used, how would it scale
- [ ] Everything uploaded to the team Drive folder

### Explicit scope cuts (and why — these are external constraints, not skill gaps)
| Cut | Reason |
|---|---|
| Video generation | Vendor landscape (Veo, Sora, Kling, Runway, etc.) still varies too much in quality/reliability to depend on for a live demo |
| Live posting to ad platforms | Meta/TikTok/Google all require an app-review process that takes weeks and isn't in your control |
| Live TikTok Creative Center / Shopee / Lazada scraping | No public API exists for any of them — manual curation stands in |
| Adaptor agent | Shared KB access across agents already covers brand adaptation — no dedicated agent needed |

---

## Part 2 — implementation plan

### Tech stack
| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + MySQL | Your existing stack — no new tooling to learn |
| Orchestration | LangGraph | You already know it; native cycles + human-in-the-loop checkpoints match the gates directly |
| Vector store | Chroma | Fastest to stand up for demo-scale corpora, no server to manage |
| Embeddings | OpenAI `text-embedding-3-small` or Voyage AI | Cheap, fast, good enough at this scale |
| Trend data | SerpApi (Google Trends, `geo=MY`) | pytrends is dead (archived Apr 2025); this avoids maintaining scraping code |
| Image generation | Ideogram (direct, or via an aggregator like fal.ai) | Strongest current option for legible on-image text |
| LLM | Claude or GPT, structured output mode | Forces valid JSON between agents instead of parsing free text |
| Frontend | Your call — a lightweight React app or server-rendered HTMX both work fine against FastAPI | Not yet decided in our discussions; pick whichever you're fastest in |
| Scheduler (stretch) | APScheduler | You already used it on the finance tracker — no new tool to learn |
| Event data (stretch) | Hand-curated JSON | Malaysia's major commercial dates are known in advance; no reason to depend on a live API |

### Core data schemas

```json
// Concept object — planning agent output
{
  "concept_id": "string",
  "theme": "string",
  "format": "image | video | carousel",
  "trend_rationale": "string — cites a specific trend corpus chunk",
  "brand_rationale": "string — cites a specific company KB chunk",
  "variant_count": "integer",
  "variation_axes": ["emotional hook", "specific detail emphasized", "cta phrasing"],
  "status": "pending | approved | rejected | edited"
}
```

```json
// Variant object — copywriter + visual planner output, director-reviewed
{
  "variant_id": "string",
  "concept_id": "string",
  "hook_type": "string — which variation axis this variant executes",
  "headline": "string",
  "body": "string",
  "cta": "string",
  "visual_brief": {
    "composition_notes": "string",
    "image_prompt": "string",
    "text_placement": "string"
  },
  "director_status": "pass | flagged",
  "director_notes": "string | null"
}
```

```json
// Asset object — post-generation, review gate
{
  "asset_id": "string",
  "variant_id": "string",
  "media_url": "string",
  "qa_status": "passed | flagged",
  "qa_notes": "string | null",
  "review_status": "pending | approved | rejected"
}
```

```json
// Event object — stretch feature, calendar seed data
{
  "event_id": "string",
  "name": "string — e.g. Hari Raya, CNY, 11.11",
  "date": "YYYY-MM-DD",
  "lookahead_days": "integer — how far ahead to trigger a brief",
  "suggested_tone": "string — short hint for the auto-drafted brief"
}
```

**Campaign status state machine:**
`draft → planning → pending_plan_approval → generating → pending_asset_review → ready_to_publish → published`

### Phased timeline (27 days)

**Phase 1 — foundations · Aug 20–24 (5 days)**
- [ ] FastAPI skeleton + MySQL schema for campaigns, concepts, variants, assets
- [ ] Chroma set up, company KB embedded
- [ ] SerpApi integration, `geo=MY` Google Trends pull
- [ ] Manual trend seed file (TikTok + Shopee/Lazada, hand-curated)
- [ ] Planning agent: RAG context assembly, structured JSON output with `variation_axes`

**Phase 2 — approval gate + generation crew · Aug 25–30 (6 days)**
- [ ] Approval gate UI, wired to real planning agent output
- [ ] LangGraph nodes: copywriter → visual planner → director
- [ ] Director's cyclic revision edge, bounded to 2 retries

**Phase 3 — asset generation + review gate · Aug 31–Sept 5 (6 days)**
- [ ] Image generation integration (Ideogram or aggregator)
- [ ] Automated vision QA pre-check agent
- [ ] Review gate UI, wired to generated assets + QA flags
- [ ] Preview/export screen

**Phase 4 — end-to-end integration + polish · Sept 6–10 (5 days)**
- [ ] Full LangGraph graph wired start to finish
- [ ] Auto-mode toggle working consistently at both gates
- [ ] Error handling on every external API call (SerpApi, image gen, LLM)
- [ ] Several full runs on real Malaysia SME examples — pick the cleanest for the demo

**Phase 5 — deck, demo, submission · Sept 11–15 (5 days)**
- [ ] Record 3–5 minute demo video
- [ ] Build 5–10 page deck (problem, why, which AI, architecture, how it scales, screenshots)
- [ ] Final check of submission package against requirements checklist above
- [ ] Upload to team Drive folder
- [ ] 1 day of buffer — keep it unscheduled, something will need it

**Stretch phase — calendar & proactive recommendation · attempt only once Phases 1–4 are solid**
- [ ] Curate the Malaysia event JSON
- [ ] APScheduler lookahead job + auto-brief generator
- [ ] Provenance tag on the approval gate
- [ ] Simple calendar view showing the year's events and campaign status

### Risk register
| Risk | Mitigation |
|---|---|
| SerpApi rate limits or downtime on demo day | Cache/snapshot trend results ahead of time; don't call it live during the demo itself |
| Image gen cost/latency during live demo | Pre-generate the demo run's assets in advance; don't generate live on stage |
| LangGraph state complexity balloons | Keep the graph to exactly the nodes in this doc — resist adding agents mid-build |
| Running out of time before Phase 5 | The Phase 1 cut-list above (manual trend seed instead of live SerpApi) is the fallback if any earlier phase slips |

### Definition of done
A single real Malaysia SME example that goes from human brief → approved plan → generated, reviewed assets → export preview, recorded end to end, plus the deck and demo video answering all four required questions.
