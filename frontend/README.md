# Agentcy — console

React + Vite + Tailwind + motion. An instrument for watching four agents work,
not a wizard that walks you through a form.

```bash
npm install
npm run dev        # :5173, proxies /api to the backend on :8000
```

The backend must be running. See `../backend/README.md` — and set both
providers to `demo` there to drive the whole thing with no API keys. To run it
the way it ships, `docker compose up --build` from the repo root and open
:8002, where FastAPI serves this build directly.

## The rooms

A rail on the left, in two groups, and the split is the point: the top group is
work the machine has done and you look at, the bottom is the machine itself and
you set it. Reaching for the agents' settings is not the same act as opening a
campaign, so they are not the same kind of entry.

| | | |
|---|---|---|
| **Campaigns** | `/` | The work. A console per campaign. |
| **Video studio** | `/video-studio` | Configurable marketing videos; opens on the Agentcy demo preset. |
| **History** | `/history` | Every pass the machine has made, replayable. |
| **Brand profile** | `/brand` | The company facts and product truth the crew may use. |
| **Agents** | `/agents` | The four, in pipeline order, and their few knobs. |
| **Trends** | `/trends` | The watchlist that decides what "the moment" means. |

The rail is outside the scroll container, so it never scrolls away — including
from a console mid-run. Its marks come from the product's own vocabulary rather
than an icon set: the four dots really are the four agents, the rising steps
really are what the watchlist measures. Its footer names the LLM provider at
all times, because `demo` writes copy that reads like copy and a rehearsal must
never be mistaken on stage for a live model.

**Agents** shows what each agent may *not* do beside what it does — a director
that could fix the copy itself would stop being a review — and numbers them by
position, because work genuinely moves through them in that order. Knobs are
meters, not number boxes: the useful information is the distance left to the
maximum. Hovering a card runs its core.

**History** groups runs by day and draws each one's duration against the longest
on the page, because model calls are the expensive part of this product and
that is the only place their cost is visible at a glance. Opening a run replays
its events rather than summarising them.

**Trends** draws rising and top queries against separate scales. They are not
one ranking — Google scores a breakout as a multiple of its old volume and a
top query as a 0–100 share — so a single scale draws a dominant top query as a
stub. With no SerpApi key the page says so at the top, and the samples it
returns admit it in every document heading they write.

## The idea

The product's claim is that a person stands between the machine and the ad
spend. The interface performs that claim instead of captioning it.

**Depth is attention.** While the crew works, the agent station and the graph
are forward and lit. The moment a gate halts the run, the machine *recedes* —
back, dim, out of focus, and `inert` so you cannot even tab into it — and the
work rises to the front on paper. Nothing announces the handover; the room
rearranges around you.

**The machine is achromatic.** Agents, edges, waypoints and telemetry are made
of white light at varying intensity and nothing else. Amber appears in exactly
one situation: a human decision is required. So a warm pixel anywhere on screen
always means the same thing, and it means it before you have read a word. Two
colours survive beyond that, both rare — coral when the director spent its
revision budget, mint when a decision has opened the path.

**The work is on paper.** Anything the crew produced renders on a white card
(`.on-paper` in `index.css`), so it can never dissolve into the instrument that
made it. Ad copy is set in Newsreader, the chrome in Archivo, and machine data
— chunk ids, clocks, counts — in JetBrains Mono and nowhere else.

## The agent station

Four robot cores, one per agent, each built out of the thing its agent actually
does rather than out of a mascot:

| Agent | Core | Why |
|---|---|---|
| Planner | A radar sweeping a field of points | Retrieval is a search over a space; each point is a chunk, lighting as the sweep crosses it |
| Copywriter | Lines being written under a caret | One variant per axis, composed in order |
| Art director | A reticle hunting the thirds of a frame | The visual brief is composition — where the product sits, where the text goes |
| Creative director | An aperture that opens, judges, and shuts | Review is looking, then deciding; a rejection snaps it closed |

A core runs **only while its agent holds the work**. Four idle cores are four
still wireframes, so one glance at the station tells you where the work is.

## Typography

Archivo is loaded with its variable width axis and display type is set wide
(`wdth` 112–118) with tight tracking — the proportions of instrument lettering
rather than of a web heading. Labels are sentence case and quiet; the previous
console shouted every label in uppercase mono, which made six panels compete
for the same attention and read as a generated dashboard.

## Two rules the code keeps

**Nothing moves unless work is moving.** A pulse travels the edge the work is
travelling. A waypoint breathes only while it holds the work. The ambient glow
behind the stage drifts, and it is the only exception — slow enough to read as
air rather than as activity. `prefers-reduced-motion` turns all of it off.

**Never animate an SVG transform without a bounding box.** Motion derives an
SVG element's `transform-origin` from `getBBox()`, which is still zero on the
first paint — anything that scales or rotates there pivots about the wrong
point and, with `overflow: visible`, paints itself across the page. Gates are
drawn as diamond paths rather than rotated squares, waypoints reveal with
opacity and a translate, and the radar's sweep group carries an unpainted
centred circle purely so its bbox is centred.
