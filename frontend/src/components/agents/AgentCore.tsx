import { motion, useReducedMotion } from 'motion/react'
import { CORE_PERIOD } from '@/lib/motion'
import type { AgentState } from '@/hooks/useConsole'

/** A robot core for each agent — the mechanism, drawn.
 *
 * Each core is built out of the thing its agent actually does, not out of a
 * mascot: the planner is a radar sweep finding chunks in the corpora, the
 * copywriter is lines being written under a caret, the art director is a
 * reticle hunting the thirds of a frame, the creative director is an aperture
 * that opens, judges, and snaps shut on a rejection.
 *
 * They animate only while their agent holds the work. Four idle cores are four
 * still wireframes, so a glance at the station tells you where the work is
 * without reading a word.
 */

const C = 36 // centre of the 72×72 field
const VIEW = 72

export function AgentCore({
  agent,
  state,
}: {
  agent: keyof typeof CORE_PERIOD
  state: AgentState
}) {
  const stillPreference = useReducedMotion()
  const live = state === 'running' && !stillPreference
  const period = CORE_PERIOD[agent]

  return (
    <svg
      viewBox={`0 0 ${VIEW} ${VIEW}`}
      className="h-full w-full overflow-visible"
      aria-hidden
    >
      <defs>
        <radialGradient id={`glow-${agent}`}>
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.34" />
          <stop offset="70%" stopColor="currentColor" stopOpacity="0.05" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`sweep-${agent}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.28" />
        </linearGradient>
      </defs>

      {/* The core only emits light while it is working. */}
      {live && (
        <motion.circle
          cx={C}
          cy={C}
          r={30}
          fill={`url(#glow-${agent})`}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: period, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      {agent === 'planner' && <Radar live={live} period={period} />}
      {agent === 'copywriter' && <Compositor live={live} period={period} />}
      {agent === 'visual_planner' && <Frame live={live} period={period} />}
      {agent === 'director' && <Aperture live={live} period={period} state={state} />}
    </svg>
  )
}

/* ── Planner — a radar sweeping a corpus ──────────────────────────────────
   Retrieval is a search over a space, so the core is a search over a space.
   The dots are chunks; each lights as the sweep crosses it and fades behind
   it, which is what a retrieval pass actually is. */

const CHUNKS = [
  { angle: 28, radius: 21 },
  { angle: 74, radius: 13 },
  { angle: 133, radius: 25 },
  { angle: 196, radius: 17 },
  { angle: 258, radius: 23 },
  { angle: 314, radius: 12 },
]

function Radar({ live, period }: { live: boolean; period: number }) {
  return (
    <g>
      {[11, 19, 27].map((r) => (
        <circle
          key={r}
          cx={C}
          cy={C}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.16}
          strokeWidth={0.75}
        />
      ))}
      <line x1={C - 27} y1={C} x2={C + 27} y2={C} stroke="currentColor" strokeOpacity={0.1} strokeWidth={0.75} />
      <line x1={C} y1={C - 27} x2={C} y2={C + 27} stroke="currentColor" strokeOpacity={0.1} strokeWidth={0.75} />

      {CHUNKS.map((chunk) => {
        const radians = (chunk.angle * Math.PI) / 180
        const x = C + chunk.radius * Math.cos(radians)
        const y = C + chunk.radius * Math.sin(radians)
        return (
          <motion.circle
            key={chunk.angle}
            cx={x}
            cy={y}
            r={1.5}
            fill="currentColor"
            // An explicit initial, not `initial={false}`: the idle branch below
            // animates `r` to a single value, so motion has to interpolate
            // *from* somewhere — and an SVG geometry attribute is not something
            // it can read back out of the DOM. Stating the start keeps the
            // value in motion's own bookkeeping, which is the only place it is
            // reliably there.
            initial={{ opacity: 0.28, r: 1.5 }}
            animate={live ? { opacity: [1, 0.18], r: [2.4, 1.5] } : { opacity: 0.28, r: 1.5 }}
            transition={
              live
                ? {
                    duration: period,
                    repeat: Infinity,
                    ease: 'easeOut',
                    // Each chunk lights at the instant the sweep reaches it.
                    delay: (chunk.angle / 360) * period,
                  }
                : { duration: 0.3 }
            }
          />
        )
      })}

      {live && (
        <motion.g
          animate={{ rotate: 360 }}
          transition={{ duration: period, repeat: Infinity, ease: 'linear' }}
        >
          {/* Motion pivots an SVG group about its own bounding box, and this
              group's contents sit entirely to the right of centre. This unpainted
              circle is centred on C, so the bbox is too, and the sweep turns
              about the middle of the dish rather than about itself. */}
          <circle cx={C} cy={C} r={27} fill="none" stroke="none" />
          {/* The trail behind the head, so the sweep has a direction. */}
          <path
            d={`M ${C} ${C} L ${C + 27} ${C - 12} A 29.5 29.5 0 0 1 ${C + 27} ${C} Z`}
            fill={`url(#sweep-planner)`}
          />
          <line
            x1={C}
            y1={C}
            x2={C + 27}
            y2={C}
            stroke="currentColor"
            strokeOpacity={0.85}
            strokeWidth={1}
          />
        </motion.g>
      )}
      <circle cx={C} cy={C} r={1.75} fill="currentColor" />
    </g>
  )
}

/* ── Copywriter — lines written under a caret ─────────────────────────────
   One variant per axis, written in order. The caret is the tell: it makes the
   core read as composition rather than as a loading bar. */

const LINES = [
  { y: 17, width: 42 },
  { y: 26, width: 33 },
  { y: 35, width: 46 },
  { y: 44, width: 27 },
  { y: 53, width: 38 },
]
const LEFT = 13

function Compositor({ live, period }: { live: boolean; period: number }) {
  const slot = 1 / LINES.length

  return (
    <g>
      {/* The sheet the lines are set on. */}
      <rect
        x={9}
        y={11}
        width={54}
        height={50}
        rx={2}
        fill="none"
        stroke="currentColor"
        strokeOpacity={0.14}
        strokeWidth={0.75}
      />

      {LINES.map((line, index) => {
        // Each line owns a slot of the cycle and is written inside it, so the
        // five lines compose a paragraph rather than pulsing together.
        const start = Math.max(index * slot, 0.0001)
        const end = index * slot + slot * 0.82
        return (
          <g key={line.y}>
            <motion.rect
              x={LEFT}
              y={line.y}
              width={line.width}
              height={2.5}
              rx={1.25}
              fill="currentColor"
              style={{ transformBox: 'fill-box', transformOrigin: 'left center' }}
              initial={false}
              animate={
                live
                  ? { scaleX: [0, 0, 1, 1], opacity: [0.22, 0.22, 0.92, 0.5] }
                  : { scaleX: 1, opacity: 0.3 }
              }
              transition={
                live
                  ? {
                      duration: period,
                      times: [0, start, end, 1],
                      repeat: Infinity,
                      ease: 'linear',
                    }
                  : { duration: 0.3 }
              }
            />
            {live && (
              <motion.rect
                y={line.y - 2}
                width={1.5}
                height={6.5}
                fill="currentColor"
                animate={{
                  x: [LEFT, LEFT, LEFT, LEFT + line.width, LEFT + line.width, LEFT + line.width],
                  opacity: [0, 0, 1, 1, 0, 0],
                }}
                transition={{
                  duration: period,
                  times: [0, start, start + 0.004, end, end + 0.004, 1],
                  repeat: Infinity,
                  ease: 'linear',
                }}
              />
            )}
          </g>
        )
      })}
    </g>
  )
}

/* ── Art director — a reticle hunting the thirds ──────────────────────────
   The visual brief is composition: where the product sits, where the text
   goes. So the core is a frame with its thirds drawn and a reticle settling
   on each intersection in turn. */

const FRAME = { x: 12, y: 14, w: 48, h: 44 }
const THIRD_X = [FRAME.x + FRAME.w / 3, FRAME.x + (FRAME.w * 2) / 3]
const THIRD_Y = [FRAME.y + FRAME.h / 3, FRAME.y + (FRAME.h * 2) / 3]
const STOPS = [
  { x: THIRD_X[0], y: THIRD_Y[0] },
  { x: THIRD_X[1], y: THIRD_Y[0] },
  { x: THIRD_X[1], y: THIRD_Y[1] },
  { x: THIRD_X[0], y: THIRD_Y[1] },
]

function Frame({ live, period }: { live: boolean; period: number }) {
  const corner = 7

  return (
    <g>
      {/* Corner brackets rather than a closed rectangle — a frame you are
          composing inside, not a box the content is trapped in. */}
      {[
        `M ${FRAME.x} ${FRAME.y + corner} V ${FRAME.y} H ${FRAME.x + corner}`,
        `M ${FRAME.x + FRAME.w - corner} ${FRAME.y} H ${FRAME.x + FRAME.w} V ${FRAME.y + corner}`,
        `M ${FRAME.x + FRAME.w} ${FRAME.y + FRAME.h - corner} V ${FRAME.y + FRAME.h} H ${FRAME.x + FRAME.w - corner}`,
        `M ${FRAME.x + corner} ${FRAME.y + FRAME.h} H ${FRAME.x} V ${FRAME.y + FRAME.h - corner}`,
      ].map((d) => (
        <path key={d} d={d} fill="none" stroke="currentColor" strokeOpacity={0.4} strokeWidth={1} />
      ))}

      {THIRD_X.map((x) => (
        <line key={x} x1={x} y1={FRAME.y + 3} x2={x} y2={FRAME.y + FRAME.h - 3} stroke="currentColor" strokeOpacity={0.1} strokeWidth={0.75} />
      ))}
      {THIRD_Y.map((y) => (
        <line key={y} x1={FRAME.x + 3} y1={y} x2={FRAME.x + FRAME.w - 3} y2={y} stroke="currentColor" strokeOpacity={0.1} strokeWidth={0.75} />
      ))}

      {live && (
        <motion.g
          animate={{
            x: [...STOPS.map((stop) => stop.x - C), STOPS[0].x - C],
            y: [...STOPS.map((stop) => stop.y - C), STOPS[0].y - C],
          }}
          transition={{ duration: period, repeat: Infinity, ease: [0.65, 0, 0.35, 1] }}
        >
          <circle cx={C} cy={C} r={5} fill="none" stroke="currentColor" strokeOpacity={0.9} strokeWidth={1} />
          <motion.circle
            cx={C}
            cy={C}
            fill="none"
            stroke="currentColor"
            strokeWidth={1}
            // Explicit initial: motion must never have to read an animated SVG
            // attribute back out of the DOM, because an element that mounts
            // inside a conditional has no value there yet.
            initial={{ r: 5, opacity: 0.6 }}
            animate={{ r: [5, 11], opacity: [0.6, 0] }}
            transition={{ duration: period / STOPS.length, repeat: Infinity, ease: 'easeOut' }}
          />
          <line x1={C - 8} y1={C} x2={C - 6.5} y2={C} stroke="currentColor" strokeWidth={1} />
          <line x1={C + 6.5} y1={C} x2={C + 8} y2={C} stroke="currentColor" strokeWidth={1} />
          <line x1={C} y1={C - 8} x2={C} y2={C - 6.5} stroke="currentColor" strokeWidth={1} />
          <line x1={C} y1={C + 6.5} x2={C} y2={C + 8} stroke="currentColor" strokeWidth={1} />
        </motion.g>
      )}
    </g>
  )
}

/* ── Creative director — an aperture that judges ──────────────────────────
   Review is looking, then deciding. The iris opens to look and closes on the
   verdict; when the verdict is a rejection the whole core snaps shut. */

function hexagon(radius: number): string {
  return (
    Array.from({ length: 6 }, (_, index) => {
      const radians = ((index * 60 - 90) * Math.PI) / 180
      const x = C + radius * Math.cos(radians)
      const y = C + radius * Math.sin(radians)
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    }).join(' ') + ' Z'
  )
}

function Aperture({
  live,
  period,
  state,
}: {
  live: boolean
  period: number
  state: AgentState
}) {
  const shut = state === 'failed'

  return (
    <g>
      <circle cx={C} cy={C} r={27} fill="none" stroke="currentColor" strokeOpacity={0.16} strokeWidth={0.75} />

      {/* Blade seams — six, so the hexagon reads as a mechanism. */}
      {Array.from({ length: 6 }, (_, index) => {
        const radians = ((index * 60 - 90) * Math.PI) / 180
        return (
          <line
            key={index}
            x1={C + 6 * Math.cos(radians)}
            y1={C + 6 * Math.sin(radians)}
            x2={C + 27 * Math.cos(radians)}
            y2={C + 27 * Math.sin(radians)}
            stroke="currentColor"
            strokeOpacity={0.12}
            strokeWidth={0.75}
          />
        )
      })}

      <motion.path
        d={hexagon(20)}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.25}
        strokeOpacity={0.75}
        style={{ transformOrigin: `${C}px ${C}px`, transformBox: 'view-box' }}
        initial={false}
        animate={
          shut
            ? { scale: 0.22, rotate: 0, opacity: 1 }
            : live
              ? { scale: [1, 0.34, 1], rotate: [0, 22, 0] }
              : { scale: 0.72, rotate: 0, opacity: 0.5 }
        }
        transition={
          live && !shut
            ? { duration: period, repeat: Infinity, ease: 'easeInOut' }
            : { type: 'spring', stiffness: 300, damping: 22 }
        }
      />

      {/* The pupil dilates with the iris — the thing actually being looked at. */}
      <motion.circle
        cx={C}
        cy={C}
        r={4}
        fill="currentColor"
        initial={false}
        animate={
          shut
            ? { scale: 0.35, opacity: 1 }
            : live
              ? { scale: [1, 0.4, 1], opacity: [0.9, 0.45, 0.9] }
              : { scale: 0.8, opacity: 0.35 }
        }
        style={{ transformOrigin: `${C}px ${C}px`, transformBox: 'view-box' }}
        transition={
          live && !shut
            ? { duration: period, repeat: Infinity, ease: 'easeInOut' }
            : { type: 'spring', stiffness: 300, damping: 22 }
        }
      />

      {/* A scan crossing the field while it reads the work. */}
      {live && !shut && (
        <motion.line
          x1={C - 27}
          x2={C + 27}
          stroke="currentColor"
          strokeOpacity={0.4}
          strokeWidth={0.75}
          initial={{ y1: C - 24, y2: C - 24, opacity: 0 }}
          animate={{ y1: [C - 24, C + 24], y2: [C - 24, C + 24], opacity: [0, 0.7, 0] }}
          transition={{ duration: period / 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
    </g>
  )
}
