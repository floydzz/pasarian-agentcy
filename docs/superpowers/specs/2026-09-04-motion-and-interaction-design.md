# Motion and interaction design

Date: 2026-09-04
Status: approved, for implementation

## Problem

The frontend has a real motion system already. `frontend/src/lib/motion.ts` states a
doctrine and implements it: a shared easing vocabulary (`EASE_OUT`, `SETTLE`, `DEPTH`,
`BREATH`), per-agent clocks so concurrent agents do not lock into step, an orchestrated
`BOOT` sequence, and the central idea in `StudioShell.tsx` — when a gate halts the run
the machine scales down, dims, blurs and goes `inert` while the work comes forward.

The doctrine stops halfway through the app. Roughly 22 files import `motion`; about 15
do not, and the ones that do not are where the user actually decides things.

Measured gaps:

1. **Navigation is a hard cut.** `Shell.tsx` renders a bare `<Outlet />`. Every other
   transition in the app has mass; navigation has none.
2. **The decision surface has no motion.** `AssetCard.tsx` is the product's central
   claim — a human between the agents and the ad spend — and approve/reject is a
   `transition-colors duration-200`. `ConceptCard.tsx` has a single opacity fade.
3. **Generated images pop.** Five bare `<img>` tags. The product's output is generated
   imagery and the moment it resolves is the least designed frame in the app.
4. **No scroll choreography** on the long pages: `DemoVideo` (619 lines),
   `History` (537), `Trends` (470), `CinematicTrailer` (439).
5. **The chat dock has zero motion.** 358 lines, no `motion` import, mounted by a bare
   `open &&`.

## Goal

Hold the existing doctrine across the entire runtime with no seams. This is optimised
for demo impact, not for daily-use ergonomics.

## Browser policy

**Chrome only.** No fallbacks for Firefox or Safari are written. View Transitions and
scroll-driven animation are used natively and unguarded.

`prefers-reduced-motion` support is retained: the existing global block at the end of
`index.css` already collapses durations and iteration counts, which covers CSS-driven
view transitions and scroll-driven animations as well as the `motion` work.

## Design

### 1. The motion contract

Motion currently lives only in JS. The new work is declarative CSS, so the two would
drift apart unless they share one source.

Add a motion block to `index.css` mirroring `lib/motion.ts` exactly — `--ease-out`,
`--ease-in-out`, `--dur-micro`, `--dur-settle`, `--dur-depth` — and a comment in
`motion.ts` binding them together. One vocabulary, two syntaxes.

Extend the doctrine with a third clause, because the existing two do not cover
navigation:

> 3. Moving between rooms is a camera move, not a cut. The instrument does not reload;
>    it turns to face something else.

### 2. Navigation as a camera move

The routes have a real hierarchy: `/` -> `/campaigns/:id` -> `/campaigns/:id/image` ->
`/publish`. A new `lib/navDepth.ts` maps a pathname to a depth integer. Before each
navigation, `<html>` is stamped `data-nav="forward" | "back"`, and
`::view-transition-old(root)` / `::view-transition-new(root)` slide and dim
accordingly. Going deeper pushes in; going back pulls out. This is the existing `DEPTH`
idea applied to rooms rather than to layers.

**Persisting chrome must not blink.** View transitions snapshot the whole viewport, so
`Sidebar` and `MarketingChatDock` would cross-fade on every navigation without care.
Both take a stable `view-transition-name` so the browser treats them as the same
element across the snapshot and leaves them in place.

The rail's existing `layoutId="rail-mark"` takes `view-transition-name: none`, so
`motion` keeps sole ownership of that element and the two systems never animate the
same pixel.

**Shared elements that carry meaning across rooms:**

- A campaign row title on `Home` and the `<h1>` in `TopBar` share
  `view-transition-name: campaign-{id}`. The name travels into the studio rather than
  being redrawn. Names remain unique per snapshot because `Home` renders each id once.
- The studio accent rule in `TopBar` morphs image-blue to video-purple when switching
  studios — the moment a viewer reads the two studios as one machine.

React Router 7.18 exposes `viewTransition` on `<Link>` as a stable prop, so this is CSS
plus a prop. No new dependency; the animation runs on the compositor.

### 3. The image developing

A generated asset arrives like a print developing: blurred and slightly over-scaled,
then resolving over roughly 700ms on `--ease-out`, triggered on the image's `load`
event rather than on mount, so the animation describes the decode rather than the
mount.

This is extracted into one `components/Plate.tsx` so every call site behaves
identically and cannot drift. It also owns the empty and error states, which the bare
tags do not have today.

Call sites: `AssetCard`, `ProductReferenceLibrary`, `Publish`, `History`.

`pages/Export.tsx` is deliberately excluded: `App.tsx` redirects both `/export` and
`/campaigns/:id/export` to `/publish`, so the file is unreachable and animating it
would be work with no user-visible result.

### 4. The gate has weight

- **Approve:** the card commits under the press, settles on `SETTLE`, and a hairline in
  `--go` draws around it.
- **Reject:** the card recedes rather than fades — desaturates and drops back in Z —
  and the filmstrip closes the gap using the `layout` prop already present on
  `TrackItem`.
- **Redo:** the plate returns to its undeveloped state, so a re-render is visible as a
  re-render instead of only as a changed button label.
- **The gate closing:** the amber sweep in `GateShell` resolves with a final pass before
  the border goes cool, rather than unmounting mid-sweep.

### 5. The scroll is the film

Scroll-driven CSS animation via `animation-timeline: view()` and `scroll()`. No JS, no
scroll listeners, all off the main thread.

- `CinematicTrailer` and `DemoVideo`: layered parallax, so ambient light and foreground
  content move at different rates. Depth on scroll, matching the existing doctrine.
- The filmstrip (`.snap-track`): cards resolve as they approach the centre of the
  scroller and recede as they leave it. Scroll snap is already in place, so this sits
  on existing structure.
- `History` and `Trends`: entries resolve on entry rather than all at once.

### 6. The dock has mass

`MarketingChatDock` slides in on `DEPTH`. Messages arrive on the existing
`STAGGER_CHILD`. The floating Strategist button morphs into the dock via a shared
`layoutId` rather than vanishing while a panel appears elsewhere.

## Non-goals

- No animation library beyond `motion`, which is already a dependency.
- No drag-to-reorder in the video storyboard.
- No keyboard shortcuts. These are a daily-use win, not a demo one.
- No non-Chrome fallbacks.
- No changes to `pages/Export.tsx`, which is unreachable.

## Verification

`npm run build` (`tsc -b && vite build`) and `npm run lint` must pass. Motion work is
visual and is confirmed by running the app, not by unit tests; there is no existing
frontend test suite to extend.
