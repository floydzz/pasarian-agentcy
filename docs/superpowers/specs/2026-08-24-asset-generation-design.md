# Asset generation — design

**Date:** 2026-08-24 · **Phase:** 3 · **Status:** approved design, not yet planned

Phase 3 of `campaign-ai-implementation-plan.md`: the half of the pipeline that
turns a reviewed variant into a creative a human can ship. Today the crew stops
at the director (`crew.py:101`), `Asset` is declared in `domain.py:110` and
`models.py:120` but nothing ever constructs one, and the console already draws
an `asset_gate` waypoint (`FlowGraph.tsx:29`) that leads nowhere.

## Decisions taken before this document

| Decision | Choice | Why |
|---|---|---|
| Vendor | DashScope (Alibaba) for image and video | `DASHSCOPE_API_KEY` is already wired at `config.py:29`; cheapest; no new billing account |
| Text on creative | Composited, not model-rendered | Legibility stops depending on the vendor's weakest capability |
| Stage placement | Separate render stage, own route and run kind | Renders take minutes; the crew returns in seconds and must keep doing so |
| Video | A product feature, used to make Agentcy's own ad | Dogfood: the submission video's centrepiece is an ad the app generated |
| Sequencing | Images (3a) fully working before video (3b) | Video is the vendor risk the plan already flagged; slippage should land on a finished image pipeline |

The 3–5 minute submission video is assembled conventionally — screen recordings
of real runs plus narration. The app produces the 15–30s ad inside it. If the
video renderer is unusable by September, the fallback is to cut to the image ad
and the submission still ships.

## Architecture

Two graphs, not one. `/generate` runs the crew and persists variants in
seconds. `/render` runs the studio and persists assets in minutes.

```
POST /campaigns/{id}/generate        (exists)
  copywriter → visual_planner → director → variants

POST /campaigns/{id}/render          (new)
  for each variant without an asset:
    renderer → vision_qa ──flagged──┐
        ↑                            │
        └────── redo, bounded 2 ─────┘
                     │ passed, or budget spent
                     ↓
              PENDING_ASSET_REVIEW
```

The redo loop mirrors the director's revision loop exactly: bounded at 2, and
past the budget the asset falls through carrying `qa_status="flagged"` and QA's
last notes. The rule from `crew.py:12` holds here — a reviewer is never handed
work while being told it was approved.

### New modules

`backend/app/media/` deliberately mirrors `backend/app/llm/`:

| File | Contents |
|---|---|
| `base.py` | `MediaProvider` ABC — `render_image(prompt, *, aspect) -> bytes`, `render_video(prompt, *, seconds, aspect) -> bytes`. Requires a key in `__init__` like `LLMProvider` does |
| `dashscope.py` | Wanx image synthesis and Wan video, both over the async task API |
| `demo.py` | Offline provider — a deterministic Pillow placeholder keyed on the prompt hash for stills, and a short canned clip for video, every file stamped `[demo]` |
| `compose.py` | Pillow overlay: background bytes + headline + CTA + zone → finished creative |
| `storage.py` | Writes bytes to the assets directory under a UUID, returns the `/media/...` path |

`backend/app/agents/vision_qa.py` — the QA agent. `backend/app/agents/studio.py`
— the render/QA graph. `backend/app/api/assets.py` — the routes.

### DashScope is two different APIs

`QwenProvider` reaches DashScope through its OpenAI-compatible gateway
(`openai_compatible.py:46`). **Image synthesis does not live there.** It is a
native async task API: submit with `X-DashScope-Async: enable`, receive a
`task_id`, poll `/api/v1/tasks/{task_id}` until `SUCCEEDED` or `FAILED`, then
download the result URL. `MediaProvider` therefore needs its own HTTP client and
its own polling loop with a timeout — it cannot reuse the `openai` SDK path.

Polling is bounded by `media_timeout_seconds`. A timeout raises `RenderError`,
which the studio treats the same way the crew treats `CrewError`: keep what
finished, mark the run failed, stay resumable.

## Compositing

`VisualBrief` gains one field. `text_placement` stays as it is — prose is what
goes into the image prompt (*"leave the upper-left third clear, uncluttered
sky"*), and no enum expresses that. The new field drives Pillow:

```python
PlacementZone = Literal[
    "top-left", "top-center", "top-right",
    "mid-left", "mid-center", "mid-right",
    "bottom-left", "bottom-center", "bottom-right",
]

class VisualBrief(BaseModel):
    composition_notes: str
    image_prompt: str
    text_placement: str          # unchanged — steers the image prompt
    placement_zone: PlacementZone  # new — drives the compositor
```

The two must agree, which is the point: if the model doesn't know where the text
is going, the headline lands on someone's face. `VisualDraft` in
`visual_planner.py:42` gains the same field, and `SYSTEM_PROMPT` gains a line
requiring `placement_zone` to match what `text_placement` describes.

Text colour is **not** in the schema. Asking the planner to predict the
brightness of an image that does not exist yet is a guess; the pixels are ground
truth. The compositor samples mean luminance inside the target rectangle and
picks the contrasting colour from that, then draws a soft scrim behind the text
so legibility survives a busy background.

Headline wraps and auto-sizes down until it fits its zone. CTA renders beneath it.

Font resolution falls through rather than depending on one location: any `.ttf`
dropped into `backend/data/fonts/` wins, then known system paths, then Pillow's
built-in face. The container installs `fonts-dejavu-core` so it always lands on
a real face; the fallback chain exists because a native `pytest` run on macOS
has no `backend/data/fonts/` and must still compose rather than raise.

## Vision QA needs a multimodal call

`LLMProvider.structured()` is text-only — `system` and `prompt` strings
(`llm/base.py:47`). It gains an optional parameter:

```python
def structured(self, *, system: str, prompt: str, schema: type[T],
               images: list[bytes] | None = None) -> T: ...
```

`demo.py` ignores it. `claude.py` maps to native image content blocks.
`openai_compatible.py` maps to `image_url` with a base64 data URI. A provider
that cannot accept images raises a clear error naming itself.

QA checks what the plan asks for (`plan:43`): composited text legible against
the background it landed on, spelling intact, no obvious generation artifacts,
nothing off-brand. Its verdict is `passed | flagged` plus notes, and flagged
sends one redo with the notes fed back into the image prompt.

**Risk:** structured output on vision models is less reliable than on text
models. If `qwen-vl-max` will not honour `response_format`, QA degrades to
`flagged` with an explanatory note rather than blocking the pipeline — a
degraded QA pass costs a human a look, a broken one costs the demo.

## Storage and serving

Assets are files, not blobs in MySQL. `Asset.media_url` stores `/media/<uuid>.png`.

- Files land in `backend/data/assets/`, beside the existing `backend/data/trends/`.
- `ASSETS_PATH` is absolute in the container (`/data/assets`), exactly as
  `CHROMA_PATH` is, so it resolves onto the volume and not the writable layer.
- A `StaticFiles` mount at `/media` registers in `main.py` **before**
  `_mount_console` (`main.py:79`), which mounts at `/` and would otherwise
  swallow it.
- `docker-compose.yml` gains an `agentcy_assets` volume. Generated media
  outliving `docker compose down` matches how the embedded corpora already behave.

## Configuration

`Settings` (`config.py:17`) gains, following the existing provider pattern where
a missing key names its own environment variable:

```python
MediaProviderName = Literal["dashscope", "demo"]

media_provider: MediaProviderName = "demo"
dashscope_image_model: str = "wanx2.1-t2i-turbo"
dashscope_video_model: str = "wanx2.1-t2v-turbo"
demo_image_model: str = "demo-offline"

assets_path: str = "data/assets"
media_timeout_seconds: int = 120      # 600 for video
max_renders_per_run: int = 24
```

`media_provider` defaults to `demo` for the same reason `LLM_PROVIDER` does in
compose (`docker-compose.yml:42`): `docker compose up` with no keys must run the
whole pipeline and bill nothing. It reuses `DASHSCOPE_API_KEY` rather than
introducing a second key for the same account.

Aspect ratio is not a planner decision. Image ads render 1:1 and video 9:16 by
default, overridable per campaign later. Making the planner choose a frame
shape adds a field the compositor's zone grid would have to vary against, for a
choice that is really a channel convention.

## Routes

| Route | Purpose |
|---|---|
| `POST /api/campaigns/{id}/render` | Run the studio over pending variants |
| `POST /api/campaigns/{id}/render/stream` | The same run, narrated as NDJSON |
| `GET /api/campaigns/{id}/assets` | The review gate's data |
| `POST /api/assets/{id}/approve` | Per-asset approve |
| `POST /api/assets/{id}/reject` | Per-asset reject |
| `POST /api/assets/{id}/redo` | Re-render one asset |
| `POST /api/campaigns/{id}/assets/approve` | Close the gate, advance the campaign |

Resume works the way `_pending` already does at `generation.py:154`: a variant
that already has an asset is skipped, so a retry after a partial failure never
writes a second asset beside the first.

Every variant with no asset is rendered, including director-flagged ones. The
asset gate is where a human filters; the console shows `director_status` on the
card so a flagged variant is visibly flagged rather than quietly dropped.

`MAX_RENDERS_PER_RUN` caps a single run at 24 renders. Three concepts at six
variants is 18, so the cap is a runaway guard, not a normal limit.

### Status and auto-mode

No state machine change. `GENERATING → PENDING_ASSET_REVIEW` is already the next
legal transition (`domain.py:34`), and `PENDING_ASSET_REVIEW → READY_TO_PUBLISH`
follows it. `auto_approve_assets` (`generation.py:38`) is already persisted and
currently unread; it now does what `auto_approve_plan` does at `campaigns.py:110`
— assets still carry an explicit approved status so nothing downstream has to
know a human was skipped.

History gains `RENDER = "render"` beside `PLAN` and `GENERATE`
(`history.py:31`), so render runs appear in History with no further work.

## Console

- `FlowGraph.tsx` gains `renderer` and `qa` waypoints between `director` (x 588)
  and the existing `asset_gate` (x 706); the x-coordinates re-space to fit.
- An asset gate reusing `GateBar`, so both gates behave identically — the plan's
  non-functional requirement at `plan:62`.
- `AssetCard` showing the creative, QA verdict, director status, and
  approve/redo/reject.
- An export screen: final previews with download and copy.

## Testing

Mirroring the existing suite, and never touching the network (`README:113`):

| File | Covers |
|---|---|
| `test_media_providers.py` | Task submit/poll/download against a stubbed transport; timeout raises `RenderError` |
| `test_compose.py` | Zone rectangles, luminance-driven contrast, wrap and auto-size, output is a valid PNG |
| `test_vision_qa.py` | Verdict parsing, notes feeding the redo prompt, image-less provider raising clearly |
| `test_studio.py` | Redo bounded at 2; falls through flagged when the budget is spent |
| `test_api_assets.py` | Gate transitions, per-asset actions, auto-mode, resume skipping rendered variants |

Existing tests needing updates: `test_crew_agents.py` and `test_domain.py` for
`placement_zone`, `test_llm_providers.py` for the `images` parameter.

## Milestone 3b — video

Same provider, same graph, same gate. `Concept.format` is already
`Literal["image", "video", "carousel"]` (`domain.py:60`), so the renderer
dispatches on a value the planner can already emit.

What video adds:

- `render_video` over DashScope's Wan text-to-video task API — same async
  submit/poll shape, longer timeout, lower cap.
- **ffmpeg in the runtime image.** The runtime stage (`Dockerfile:48`) installs
  no apt packages today; this is a real addition. It is not optional: vision QA
  cannot inspect a clip without extracted frames, and the review gate needs a
  poster frame to show a video in a grid. Text overlay via `drawtext` comes
  along with it.
- `Asset` distinguishes media kind so the gate renders a `<video>` rather than
  an `<img>`.

3b starts only once 3a runs end to end.

## Definition of done

**3a:** a brief goes from planning through the approval gate, the crew, render,
vision QA and the asset gate to an export screen with downloadable image
creatives, offline in `demo` mode and against DashScope with a key.

**3b:** the same path produces a 15–30s video ad, and the ad for Agentcy itself
is generated by Agentcy.
