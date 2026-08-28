# Marketing chatbot — design

Date: 2026-08-28
Status: proposed (approach A)

## The problem

The pipeline works but it has no front door. To get a campaign made you fill
in a name and a brief, press Plan, read three concepts, approve one, press
Generate, press Render. Every screen assumes you already know what you want to
make. Nothing in the product helps you decide *what* to run — which is the part
a small business actually needs help with.

The ask is a chatbot that talks about marketing ideas, knows what is worth
asking, and can drive the pipeline once the idea is real.

There is one architectural obstacle. `LLMProvider` exposes exactly one method:

```python
def structured(self, *, system, prompt, schema, images=None) -> T: ...
```

Every agent in this codebase returns a validated Pydantic object. **Nothing
here can produce a sentence addressed to a human.** A chatbot has to produce
prose *and* take actions, and the design has to resolve that.

## Decisions taken

- **Authority: talk, and drive up to each gate.** The bot may create a
  campaign, run `/plan`, and run `/generate`. It stops dead at the concept
  gate, the asset gate, and `/render`. The human decides anything that spends
  an image.
- **Scope: one standing assistant.** A single `/chat` page with persistent,
  named threads. A thread may adopt a campaign once one exists, and outlives
  it — ideas start before campaigns do.
- **Character: opinionated strategist.** Reads the brand profile and the trend
  corpus before speaking. Proposes angles unasked. Pushes back when an idea
  conflicts with a stated restriction. Asks a question only when the answer
  would change the work — never a checklist.
- **Approach A: one structured turn per message.** The reply text and the
  proposed action travel together inside one schema, through the existing
  `structured()` call. No new provider surface.

### Why approach A

The two alternatives were a native tool-calling loop and a two-pass
converse-then-classify split.

Tool calling is the textbook answer and the wrong one here. It means a second
protocol implemented across four providers, and it routes around `_coerce`,
which is the workaround for DashScope returning `[{...}]` instead of `{...}`.
This vendor has already cost us the wrapped-array quirk, `enable_interleave`,
and three model names that no longer exist. An unverified vendor surface is not
a day's work.

The two-pass split doubles latency and spend per message to buy a separation
nobody sees.

Approach A inherits everything already built on `structured()`: the
`enable_thinking: False` switch, the per-model quota failover chain, the array
unwrap, and a `demo` provider that lets the whole feature be tested offline
with no quota. What it gives up is token-by-token streaming — the reply arrives
whole. That can be added later on top of `app/api/streaming.py` without
touching the agent.

## 1. The agent

`backend/app/agents/chat.py` — `MarketingChat`, built like `PlanningAgent`:
constructed with a provider, the knowledge store, and a standing note.

```python
class ChatAction(StrEnum):
    NONE = "none"
    CREATE_CAMPAIGN = "create_campaign"
    RUN_PLAN = "run_plan"
    RUN_GENERATE = "run_generate"


class BriefDraft(BaseModel):
    name: str = Field(max_length=120)
    brief: str


class ChatTurn(BaseModel):
    reply: str
    action: ChatAction = ChatAction.NONE
    #: Required when action is CREATE_CAMPAIGN, ignored otherwise.
    draft: BriefDraft | None = None
```

`ChatAction` is the whole authority model. `run_render`, `approve_plan` and
`approve_assets` are not members of the enum, so the bot cannot name them, and
a model that invents `"run_render"` fails Pydantic validation rather than
reaching the executor.

**Grounding.** Every turn retrieves from both corpora before the call, exactly
as the planner does, and the system prompt inherits the planner's three-source
hierarchy:

1. THE CONVERSATION is what the human wants.
2. COMPANY KNOWLEDGE is ground truth and can veto an idea outright.
3. TREND SIGNALS are inspiration, never fact.

Retrieval widths reuse the planner's `company_k` / `trend_k` shape and are
tunable from the agents screen through `Tuning`, like every other agent.
Context is rendered with `render_context()` and the standing note applied with
`with_house_note()` — both already in `app/agents/base.py`.

**Character, in the prompt.** Three rules do the work:

- Open with a position, not a question. If the brand profile supports an
  angle, propose it.
- Ask at most one question per turn, and only when the answer changes what
  gets made. Budget, audience and occasion usually change it; favourite
  colour does not.
- When an idea conflicts with a restriction in the brand profile, say so and
  name the restriction. Do not quietly comply.

**State the agent sees.** The prompt carries the campaign's current status
when a thread has adopted one, so the bot knows whether it is waiting on the
human at a gate. It is told plainly that it cannot approve anything and cannot
render, and that when the pipeline reaches a gate its job is to summarise what
is waiting and hand over.

## 2. The executor

The agent proposes; `app/api/chat.py` disposes. A returned action is a
*suggestion* checked against real state before anything happens:

| action | precondition | effect |
|---|---|---|
| `create_campaign` | thread has no campaign; `draft` present | creates the campaign inline; the thread adopts it |
| `run_plan` | campaign is `draft` | **authorized**, not run here — see below |
| `run_generate` | campaign is `generating` | **authorized**, not run here |
| `none` | — | — |

A precondition that fails is not an error to the user. The turn's `reply` is
still shown; the action is dropped and a short system line is appended saying
why ("the plan is waiting for your approval — I can't do that part"). The
model is never allowed to be authoritative about state: the existing 409s in
`campaigns.py` and `generation.py` remain the only real gate, and this table is
a cheap pre-check that keeps them from being hit as errors.

**Created inline, run by the client.** Creating a campaign is a database write
and happens inside the message request. Planning and generating are minutes of
model calls that already have streaming endpoints and a console built to watch
them, so the executor does not run them — it *authorizes* them, records a
system line saying so, and names the route in its response. The frontend then
calls `/campaigns/{id}/plan/stream` exactly as the studio does today. The
chatbot gains no second copy of the run machinery, and a long run does not sit
inside an HTTP request that a browser will time out.

## 3. Persistence

Two new tables. No conversation storage exists today.

```
conversations
  id, title, campaign_id (nullable FK), created_at, updated_at

messages
  id, conversation_id FK, role (user|assistant|system),
  content TEXT, action (nullable), created_at
```

`campaign_id` is nullable and set once, when the bot creates a campaign — the
thread "adopts" it. `ON DELETE SET NULL`, so deleting a campaign leaves the
conversation intact. That is the point of threads outliving campaigns.

The `system` role is for the executor's own lines (what it ran, what it
refused). They are stored so a reloaded thread reads the same as it did live.

**Context window.** The prompt carries the last N turns rather than the whole
thread, N tunable, defaulting to 20. A thread that runs long loses its oldest
turns; summarisation is out of scope for this build.

## 4. API

```
GET    /api/conversations                 list threads, newest first
POST   /api/conversations                 start one  {title?}
GET    /api/conversations/{id}            thread + messages
PATCH  /api/conversations/{id}            rename
DELETE /api/conversations/{id}            delete
POST   /api/conversations/{id}/messages   send a message, get the turn back
```

The send endpoint is synchronous — a chat turn is one model call — and returns:

```json
{
  "message":   { "role": "assistant", "content": "..." },
  "campaign":  { "id": 13, "status": "draft", ... } | null,
  "authorized": "run_plan" | "run_generate" | null
}
```

It is not itself streamed. When `authorized` is set, the frontend calls the
matching existing stream route for that campaign and renders the run in the
transcript with the same event components the studio uses. A refused action
produces no `authorized` field and a stored system message explaining why.

## 5. Frontend

A new route `/chat`, a Work-group rail entry above Campaigns.

Two panes: a thread list on the left (title, adopted campaign badge, last
activity), the conversation on the right. Message bubbles for user and
assistant; system lines render as a thin centred rule with text, visually
distinct from anything the bot said.

When a turn adopts or advances a campaign, an inline card appears in the
transcript — campaign name, status, and a link into the studio. At a gate the
card is the handoff: "3 concepts waiting for your approval →". The chat never
grows its own approval buttons; the gate lives on the gate screen, which is
what makes the authority boundary visible rather than merely enforced.

Styling follows the existing dark palette and the `StudioShell` conventions.
No new accent colour — chat is not a third medium.

## 6. Testing

TDD as everywhere else, all of it offline against the `demo` provider.

- **Agent:** grounded prompts include both corpora and the standing note; the
  schema rejects an invented action; a turn with `create_campaign` and no
  draft is refused.
- **Executor:** each precondition in the table, both ways. Specifically, that
  a proposed `run_generate` on a campaign at `pending_plan_approval` is
  dropped and explained rather than raised, and that no action can reach
  render or either approval path.
- **Persistence:** a thread survives its campaign's deletion with
  `campaign_id` nulled; message order is stable; the context window truncates
  at N.
- **API:** the six routes, including 404s and renaming.

## Out of scope

Token streaming of the reply. Conversation summarisation past the window.
Multi-user threads. The bot touching video, trends ingestion, or the brand
profile. Approving or rendering anything, ever.
