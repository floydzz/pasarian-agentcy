import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { BOOT, EASE_OUT, FLOW_SECONDS } from '@/lib/motion'
import type { AgentName } from '@/api/stream'
import type { AgentState } from '@/hooks/useConsole'

/** The graph, drawn as a flight path rather than as a flowchart.
 *
 * Waypoints and hairlines, not labelled rectangles: these are moments in a
 * flow, not containers holding anything. The three return edges are the reason
 * the picture earns its space — a progress bar cannot show that the director
 * sends copy back to the copywriter but visuals back to the art director, and
 * that the difference decides how much work is thrown away. They curve, and
 * they curve at different depths, so the more expensive rejection is visibly
 * the longer fall — and QA's redo, which throws away the least, falls least.
 *
 * The picture is a description now rather than a hardcoded drawing, because
 * there are two pipelines to draw and one of them must not be a second,
 * slightly different graph component that drifts away from this one.
 */

const Y = 40
const H = 124

export interface FlowNode {
  id: string
  label: string
  x: number
  /** A gate is a diamond: it is where the run can stop and wait for a person. */
  gate?: boolean
}

export interface FlowArc {
  id: string
  from: number
  to: number
  depth: number
  label: string
  /** The verdict that lights this arc up when it comes back from the machine. */
  fires: string
}

export interface FlowSpec {
  width: number
  description: string
  nodes: readonly FlowNode[]
  arcs: readonly FlowArc[]
  /** Which forward edge feeds each agent — the one carrying work while it runs. */
  feeds: Partial<Record<AgentName, number>>
}

export type NodeState = AgentState | 'blocking' | 'waived' | 'quiet'

/** The image pipeline: two gates, and three ways for work to come back. */
export const IMAGE_FLOW: FlowSpec = {
  width: 870,
  description:
    "Flow: planner, plan gate, copywriter, art director, creative director, renderer, vision QA, asset gate — with the director's two return edges and QA's redo edge",
  nodes: [
    { id: 'planner', label: 'planner', x: 58 },
    { id: 'plan_gate', label: 'plan gate', x: 168, gate: true },
    { id: 'copywriter', label: 'copy', x: 278 },
    { id: 'visual_planner', label: 'art', x: 388 },
    { id: 'director', label: 'director', x: 498 },
    { id: 'renderer', label: 'render', x: 608 },
    { id: 'vision_qa', label: 'QA', x: 706 },
    { id: 'asset_gate', label: 'asset gate', x: 812, gate: true },
  ],
  arcs: [
    // revise_visuals — the copy survives, only the images are replanned.
    { id: 'ret-visuals', from: 498, to: 388, depth: 78, label: 'revise visuals', fires: 'revise_visuals' },
    // revise_copy — rewritten copy invalidates the visuals planned around it,
    // so this arc re-enters further back and falls further.
    { id: 'ret-copy', from: 498, to: 278, depth: 104, label: 'revise copy', fires: 'revise_copy' },
    // redo — QA sends the creative back to be re-rendered. Shallower, and it
    // should be: a redo throws away one render, not a pass of written work.
    { id: 'ret-redo', from: 706, to: 608, depth: 72, label: 'redo', fires: 'flagged' },
  ],
  feeds: {
    copywriter: 1,
    visual_planner: 2,
    director: 3,
    renderer: 4,
    vision_qa: 5,
  },
}

/** The video pipeline: one gate, and one way back — QA asking for another cut.
 *
 * It is a shorter flight than the image one and the picture says so. There is
 * no director loop here because a storyboard is written by the person, not
 * argued over by two agents. */
export const VIDEO_FLOW: FlowSpec = {
  width: 870,
  description:
    'Flow: brief, storyboard, render, vision QA, review gate — with QA’s recut edge',
  nodes: [
    { id: 'planner', label: 'brief', x: 90 },
    { id: 'visual_planner', label: 'storyboard', x: 280 },
    { id: 'renderer', label: 'render', x: 470 },
    { id: 'vision_qa', label: 'QA', x: 640 },
    { id: 'review_gate', label: 'review gate', x: 800, gate: true },
  ],
  arcs: [
    { id: 'ret-recut', from: 640, to: 470, depth: 80, label: 'recut', fires: 'flagged' },
  ],
  feeds: {
    visual_planner: 1,
    renderer: 2,
    vision_qa: 3,
  },
}

export function FlowGraph({
  flow = IMAGE_FLOW,
  agents,
  gates,
  lastVerdict,
}: {
  flow?: FlowSpec
  agents: Record<AgentName, AgentState>
  /** Gate node id → its state. Only the studio knows what opens its gates. */
  gates: Record<string, NodeState>
  lastVerdict: string | null
}) {
  const still = Boolean(useReducedMotion())
  const firing = useFiring(lastVerdict)
  const { width: W, nodes: NODES } = flow

  const stateOf = (id: string): NodeState =>
    gates[id] ?? agents[id as AgentName] ?? 'idle'

  const busy = (Object.entries(agents) as [AgentName, AgentState][]).find(
    ([, state]) => state === 'running',
  )?.[0]
  const liveEdge = busy ? flow.feeds[busy] : undefined

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full overflow-visible"
      role="img"
      aria-label={flow.description}
    >
      <defs>
        <filter id="bloom" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="4" />
        </filter>
        <filter id="bloom-tight" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="2" />
        </filter>
      </defs>

      {/* Forward edges, drawn left to right as the instrument powers on. */}
      {NODES.slice(0, -1).map((node, index) => {
        const next = NODES[index + 1]
        const live = liveEdge === index
        return (
          <g key={node.id}>
            <motion.path
              id={`fwd-${index}`}
              d={`M ${node.x + 14} ${Y} H ${next.x - 14}`}
              fill="none"
              stroke="var(--text)"
              strokeWidth={live ? 1.4 : 1}
              initial={{ pathLength: 0, strokeOpacity: 0 }}
              animate={{
                pathLength: 1,
                strokeOpacity: live ? 0.75 : 0.13,
              }}
              transition={{
                pathLength: { delay: BOOT.graph + index * 0.07, duration: 0.5, ease: EASE_OUT },
                strokeOpacity: { duration: 0.4, ease: EASE_OUT },
              }}
            />
            {live && !still && <Pulse path={`fwd-${index}`} />}
          </g>
        )
      })}

      {flow.arcs.map((arc) => (
        <ReturnArc
          key={arc.id}
          id={arc.id}
          from={arc.from}
          to={arc.to}
          depth={arc.depth}
          label={arc.label}
          firing={firing === arc.fires}
          still={still}
        />
      ))}

      {NODES.map((node, index) => (
        <Waypoint
          key={node.id}
          node={node}
          state={stateOf(node.id)}
          still={still}
          index={index}
        />
      ))}
    </svg>
  )
}

/** A verdict fires its return arc once, then goes quiet.
 *
 * Held for a beat rather than tied to the run's state, so the moment stays
 * legible even when the next agent picks the work straight back up. */
function useFiring(lastVerdict: string | null) {
  const [firing, setFiring] = useState<string | null>(null)

  useEffect(() => {
    // `flagged` is QA's verdict; `revise_*` are the director's. Both are the
    // same event as far as the picture is concerned: work coming back.
    if (!lastVerdict?.startsWith('revise_') && lastVerdict !== 'flagged') return
    setFiring(lastVerdict)
    const timer = setTimeout(() => setFiring(null), 1800)
    return () => clearTimeout(timer)
  }, [lastVerdict])

  return firing
}

function Pulse({ path, colour = 'var(--text)' }: { path: string; colour?: string }) {
  return (
    <>
      <circle r="9" fill={colour} opacity="0.2" filter="url(#bloom)">
        <animateMotion dur={`${FLOW_SECONDS}s`} repeatCount="indefinite" calcMode="linear">
          <mpath href={`#${path}`} />
        </animateMotion>
      </circle>
      <circle r="2.6" fill={colour}>
        <animateMotion dur={`${FLOW_SECONDS}s`} repeatCount="indefinite" calcMode="linear">
          <mpath href={`#${path}`} />
        </animateMotion>
        <animate
          attributeName="opacity"
          values="0;1;1;0"
          keyTimes="0;0.1;0.9;1"
          dur={`${FLOW_SECONDS}s`}
          repeatCount="indefinite"
        />
      </circle>
    </>
  )
}

function Waypoint({
  node,
  state,
  still,
  index,
}: {
  node: FlowNode
  state: NodeState
  still: boolean
  index: number
}) {
  const gate = Boolean(node.gate)
  const hot = state === 'running' || state === 'blocking'
  // Amber is reserved for a human decision; the machine's own states are light.
  const colour = state === 'blocking'
    ? 'var(--halt)'
    : state === 'failed'
      ? 'var(--flag)'
      : 'var(--text)'

  const opacity =
    hot ? 1 : state === 'done' ? 0.55 : state === 'waived' ? 0.22 : 0.3

  return (
    <motion.g
      // Opacity and a translate only. Motion derives an SVG element's
      // transform-origin from getBBox(), which is still zero on the first
      // paint — so anything that scales or rotates here pivots about the wrong
      // point and, with overflow visible, paints itself across the page.
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: BOOT.graph + index * 0.07, duration: 0.5, ease: EASE_OUT }}
    >
      {hot && !still && (
        <>
          <motion.circle
            cx={node.x}
            cy={Y}
            r={13}
            fill={colour}
            filter="url(#bloom)"
            animate={{ opacity: [0.18, 0.42, 0.18] }}
            transition={{ duration: 2.6, repeat: Infinity, ease: 'easeInOut' }}
          />
          {/* A ring leaves the active waypoint on every beat — the machine
              reporting that it is still alive during a long model call. */}
          <motion.circle
            cx={node.x}
            cy={Y}
            fill="none"
            stroke={colour}
            strokeWidth={1}
            initial={{ r: 9, opacity: 0.5 }}
            animate={{ r: [9, 22], opacity: [0.5, 0] }}
            transition={{ duration: 2.6, repeat: Infinity, ease: 'easeOut' }}
          />
        </>
      )}

      {gate ? (
        // Drawn as a diamond rather than a rotated square, so there is no
        // transform to get wrong.
        <motion.path
          d={`M ${node.x} ${Y - 8} L ${node.x + 8} ${Y} L ${node.x} ${Y + 8} L ${node.x - 8} ${Y} Z`}
          fill={colour}
          stroke={colour}
          strokeWidth={1.4}
          strokeDasharray={state === 'waived' ? '2.5 2.5' : undefined}
          initial={false}
          animate={{
            strokeOpacity: opacity,
            fillOpacity: state === 'blocking' ? 1 : 0,
          }}
          transition={{ duration: 0.4, ease: EASE_OUT }}
        />
      ) : (
        <>
          <motion.circle
            cx={node.x}
            cy={Y}
            r={6}
            fill="none"
            stroke={colour}
            strokeWidth={1.2}
            initial={false}
            animate={{ strokeOpacity: opacity }}
            transition={{ duration: 0.4, ease: EASE_OUT }}
          />
          <motion.circle
            cx={node.x}
            cy={Y}
            r={2.4}
            fill={colour}
            initial={false}
            animate={{ opacity: state === 'idle' ? 0 : opacity }}
            transition={{ duration: 0.4, ease: EASE_OUT }}
          />
        </>
      )}

      <motion.text
        x={node.x}
        y={Y - 16}
        textAnchor="middle"
        initial={false}
        animate={{ opacity: hot ? 1 : 0.46 }}
        transition={{ duration: 0.4, ease: EASE_OUT }}
        fill={state === 'blocking' ? 'var(--halt)' : 'var(--text)'}
        style={{
          font: '400 10.5px var(--font-sans)',
          fontVariationSettings: "'wdth' 112, 'wght' 450",
          letterSpacing: '0.01em',
        }}
      >
        {state === 'waived' ? `${node.label} · waived` : node.label}
      </motion.text>
    </motion.g>
  )
}

function ReturnArc({
  id,
  from,
  to,
  depth,
  label,
  firing,
  still,
}: {
  id: string
  from: number
  to: number
  depth: number
  label: string
  firing: boolean
  still: boolean
}) {
  // Leaves the director downward and re-enters the target from below — a fall
  // and a climb, rather than a right-angled circuit trace.
  const d = `M ${from} ${Y + 11} C ${from} ${depth}, ${to} ${depth}, ${to} ${Y + 11}`

  return (
    <g>
      <motion.path
        id={id}
        d={d}
        fill="none"
        stroke="var(--text)"
        initial={{ pathLength: 0, strokeOpacity: 0 }}
        animate={{
          pathLength: 1,
          strokeOpacity: firing ? 0.8 : 0.1,
          strokeWidth: firing ? 1.6 : 1,
        }}
        transition={{
          pathLength: { delay: BOOT.graph + 0.3, duration: 0.6, ease: EASE_OUT },
          default: { duration: 0.25, ease: EASE_OUT },
        }}
      />
      {firing && !still && <Pulse path={id} />}
      <motion.text
        x={(from + to) / 2}
        y={depth + 12}
        textAnchor="middle"
        initial={false}
        animate={{ opacity: firing ? 1 : 0.26 }}
        transition={{ duration: 0.25, ease: EASE_OUT }}
        fill="var(--text)"
        style={{ font: '400 9.5px var(--font-mono)', letterSpacing: '0.02em' }}
      >
        {label}
      </motion.text>
    </g>
  )
}
