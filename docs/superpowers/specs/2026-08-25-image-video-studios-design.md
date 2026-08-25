# Image Studio + Video Studio — design

Date: 2026-08-25
Status: approved (approach A)

## The problem

Three things are wrong with the console as it stands.

1. The console is the image pipeline, but nothing names it that. A second
   medium now exists and there is no room for it in the vocabulary.
2. The video page (`/video-studio` → `DemoVideo`) shares no arrangement with
   the console. It is a form and a card list; the console is a station, a
   graph, a gate and a filmstrip. Two mediums, two unrelated interfaces.
3. Contrast is too low to read. `--text-3` is white at 32% on `#05070b`,
   which fails WCAG AA, and hairlines at 7% disappear entirely on a dim
   display. The complaint is measurable, not taste.

Video work is also unscoped: `marketing_videos` has no `campaign_id`, so a
campaign cannot honestly report what video work belongs to it.

## Decisions taken

- **Campaign hub + rail shortcuts.** The campaign owns the spine; the rail
  also jumps straight into either studio, so the image studio is never buried.
- **Contrast fix plus two cool studio accents.** Blue for image, violet for
  video. Both stay far from amber, which keeps its single meaning.
- **Full backend scoping.** `MarketingVideo` gains `campaign_id`.
- **Storyboard seeded from the approved variant**, falling back to the brief
  and the brand profile.
- **Approach A — a shared `StudioShell` with a data-driven pipeline.** The
  arrangement lives in one component, so the two studios cannot drift.

## 1. Routes and navigation

```
/                        Campaigns list
/campaigns/:id           Campaign hub — brief + Images / Video / Both
/campaigns/:id/image     Image Studio  (today's Console, renamed)
/campaigns/:id/video     Video Studio  (new, same shell)
/campaigns/:id/export    Export
/demo-video              Agentcy product explainer, off the campaign spine
/brand /agents /trends /history
```

The rail's Work group becomes **Campaigns · Image studio · Video studio ·
History**. The two studio entries resolve to the last campaign opened (kept in
`localStorage`); with no campaign they land on the campaigns list rather than a
dead end. `/video-studio` redirects to `/demo-video`.

The fixed Agentcy explainer keeps its own route and its own table: its subject
is Agentcy itself, not a customer campaign.

## 2. The shared shell

`components/os/StudioShell.tsx` owns the arrangement and the depth
choreography: ambience, top bar, the machine block (station + graph + caption)
that recedes when a gate opens, the gate bar, the work track and the log
drawer. It takes slots, not pipeline knowledge.

```tsx
StudioShell({ campaign, running, halted, accent, station, graph,
              caption, gate, children /* track */, log })
```

Two components become data-driven rather than hardcoded:

- **`FlowGraph`** takes `{ nodes, arcs, feeds, width }`. `IMAGE_FLOW` is
  today's eight waypoints and three return arcs; `VIDEO_FLOW` is brief →
  storyboard → render → QA → review gate.
- **`AgentStation`** takes its bay list as a prop, defaulting to the image
  crew. The video crew is four bays.

`GateBar` splits into a presentational `GateShell` (bar, amber treatment,
sweep, marker, policy slot, primary action) plus `ImageGate` and `VideoGate`
bodies. The gate semantics genuinely differ — plan gate and asset gate versus
a single video review gate — so two honest bodies beat one component with a
mode flag.

`WorkTrack`'s tab type widens from the image triple to a generic
`{ id, label, count }[]`.

## 3. The campaign hub

`/campaigns/:id` shows the campaign name, brief and status, then three cards:
**Images**, **Video**, **Both**. Each card carries its accent and its live
counts (concepts / creatives; videos), and says what the next step is. *Both*
opens the image studio and marks the video studio as the follow-on. The hub is
the only screen that knows about both mediums at once.

## 4. Backend

- `MarketingVideo.campaign_id` — nullable FK to `campaigns.id`, `ondelete
  CASCADE`, indexed. Nullable because the explainer and any ad-hoc video have
  no campaign.
- `create_all()` gains an idempotent column check, since the project has no
  Alembic and existing dev databases already hold `marketing_videos`.
- `GET /api/videos?campaign_id=` filters; `POST /api/campaigns/{id}/videos/render`
  and `.../render/stream` create campaign-scoped videos.
- `GET /api/campaigns/{id}/video-brief` returns a prefilled
  `MarketingVideoCreate`: brand profile supplies brand, audience and product;
  the approved variant supplies the headline, body and CTA of the hero and CTA
  scenes; the concept themes supply the middle beats. With no approved variant
  it falls back to the campaign brief.

## 5. Palette

`index.css` tokens change:

| token | from | to |
|---|---|---|
| `--rise` | `#0a0d13` | `#0d1119` |
| `--lift` | `#10141c` | `#171d28` |
| `--edge` | 7% | 12% |
| `--edge-strong` | 15% | 26% |
| `--text-2` | 56% | 72% |
| `--text-3` | 32% | 50% |

New: `--image: #6E9BFF`, `--video: #B08CFF`, exposed as `--color-image` and
`--color-video`. They mark medium — rail entry, hub card, studio accent line —
and never state. Amber still means, and only means, that a person is needed.

## 6. Testing

Backend: `campaign_id` round-trips on create and read; `?campaign_id=` filters;
the seed endpoint prefills from an approved variant and falls back without one;
deleting a campaign takes its videos.

Frontend: `tsc -b --noEmit` clean; both studios render through the same shell.
