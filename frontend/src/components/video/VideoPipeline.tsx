import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { FlowGraph, VIDEO_FLOW } from '@/components/os/FlowGraph'
import { AgentCore } from '@/components/agents/AgentCore'
import { cn } from '@/lib/utils'
import { EASE_OUT, SETTLE } from '@/lib/motion'
import type { AgentName } from '@/api/stream'
import type { AgentState } from '@/hooks/useConsole'

const VIDEO_AGENTS = [
  { id: 'planner', label: 'Video strategist', role: 'Reads the brief and checks the story', flow: 'brief' },
  { id: 'visual_planner', label: 'Storyboard designer', role: 'Maps every beat to a screen', flow: 'storyboard' },
  { id: 'renderer', label: 'Motion renderer', role: 'Draws scenes and encodes H.264', flow: 'render' },
  { id: 'vision_qa', label: 'Quality checker', role: 'Checks the final review frame', flow: 'QA' },
] as const satisfies ReadonlyArray<{
  id: Exclude<AgentName, 'system'>
  label: string
  role: string
  flow: string
}>

const STATE_LABEL: Record<AgentState, string> = {
  idle: 'standby',
  running: 'working',
  done: 'complete',
  unknown: 'check saved progress',
  failed: 'needs attention',
}

/** The monitor for a structured video render. It uses the same visual grammar
 * as the image pipeline, but only shows the four agents that actually own a
 * video from brief through the human review gate. */
export function VideoPipeline({
  agents,
  lastDetail,
  running,
  awaitingReview,
}: {
  agents: Record<AgentName, AgentState>
  lastDetail: Partial<Record<AgentName, string>>
  running: boolean
  awaitingReview: boolean
}) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-edge bg-[rgba(233,238,247,0.03)] px-4 py-5 sm:px-7 sm:py-7">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-[rgba(233,238,247,0.035)] to-transparent" />
      <div className="relative flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="label text-text-3">Live render pipeline</p>
          <p className="display mt-1 text-[0.95rem]">Brief → storyboard → motion → QA → review</p>
        </div>
        <PipelineState running={running} awaitingReview={awaitingReview} />
      </div>

      <div className="relative mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        {VIDEO_AGENTS.map((agent, index) => (
          <AgentBay
            key={agent.id}
            agent={agent.id}
            index={index}
            label={agent.label}
            role={agent.role}
            state={agents[agent.id]}
            detail={lastDetail[agent.id]}
          />
        ))}
      </div>

      <div aria-label="Video workflow diagram" className="relative mt-4 min-w-0">
        <FlowGraph flow={VIDEO_FLOW} agents={agents} gates={{ review_gate: awaitingReview ? 'blocking' : 'quiet' }} lastVerdict={null} />
      </div>
    </section>
  )
}

function PipelineState({ running, awaitingReview }: { running: boolean; awaitingReview: boolean }) {
  const still = useReducedMotion()
  const label = running ? 'agents working' : awaitingReview ? 'your review needed' : 'storyboard ready'
  return (
    <span className={cn('data relative flex items-center gap-2', awaitingReview ? 'text-halt' : 'text-text-3')}>
      <span className={cn('relative h-1.5 w-1.5 rounded-full', awaitingReview ? 'bg-halt' : 'bg-foreground/45')}>
        {running && !still && (
          <motion.span
            className="absolute inset-0 rounded-full bg-foreground"
            animate={{ scale: [1, 3.1], opacity: [0.7, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut' }}
          />
        )}
      </span>
      {label}
    </span>
  )
}

function AgentBay({
  agent,
  index,
  label,
  role,
  state,
  detail,
}: {
  agent: (typeof VIDEO_AGENTS)[number]['id']
  index: number
  label: string
  role: string
  state: AgentState
  detail?: string
}) {
  const still = useReducedMotion()
  const live = state === 'running'
  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: live ? -4 : 0 }}
      transition={{ delay: index * 0.06, ...SETTLE }}
      className={cn(
        'group relative overflow-hidden rounded-xl border transition-colors duration-500',
        live ? 'border-edge-strong bg-[rgba(233,238,247,0.075)]' : 'border-edge bg-[rgba(233,238,247,0.03)]',
      )}
    >
      <AnimatePresence>
        {live && (
          <motion.span
            className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-[rgba(233,238,247,0.13)] to-transparent"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: EASE_OUT }}
          />
        )}
      </AnimatePresence>
      {live && !still && (
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[rgba(233,238,247,0.65)] to-transparent"
          animate={{ opacity: [0, 1, 0], y: [0, 130] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <div className="relative flex flex-col items-center px-2.5 pt-3.5 pb-3">
        <div
          className={cn(
            'h-14 w-14 transition-colors duration-500 sm:h-[4.25rem] sm:w-[4.25rem]',
            live && 'text-brand',
            state === 'done' && 'text-foreground',
            state === 'failed' && 'text-flag',
            state === 'idle' && 'text-text-2',
          )}
        >
          <AgentCore agent={agent} state={state} />
        </div>
        <h3 className={cn('display mt-2 text-center text-[0.75rem] leading-tight', live ? 'text-foreground' : 'text-text-2')}>
          {label}
        </h3>
        <p className={cn('data mt-1', state === 'failed' ? 'text-flag' : live ? 'text-foreground' : 'text-text-3')}>
          {STATE_LABEL[state]}
        </p>
      </div>
      <p className="relative line-clamp-2 min-h-[2.15rem] border-t border-edge px-2.5 py-2 text-center text-[0.65rem] leading-snug text-text-3">
        {detail ?? role}
      </p>
    </motion.article>
  )
}
