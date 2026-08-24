import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { AgentCore } from '@/components/agents/AgentCore'
import { cn } from '@/lib/utils'
import { BOOT, EASE_OUT, SETTLE, rise } from '@/lib/motion'
import { AGENTS, type AgentState } from '@/hooks/useConsole'
import type { AgentName } from '@/api/stream'

/** The station: four agents, watched.
 *
 * Only one bay can be lit, because the graph is sequential — so the lit bay
 * answers "what is it doing right now?" without reading a single word. An idle
 * bay is a still wireframe; the core only runs while its agent holds the work.
 */

const STATE_LABEL: Record<AgentState, string> = {
  idle: 'standby',
  running: 'working',
  done: 'complete',
  failed: 'sent back',
}

export function AgentStation({
  agents,
  lastDetail,
}: {
  agents: Record<AgentName, AgentState>
  lastDetail: Partial<Record<AgentName, string>>
}) {
  return (
    <div className="mx-auto grid w-full max-w-[52rem] grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
      {AGENTS.map((agent, index) => (
        <Bay
          key={agent.id}
          index={index}
          label={agent.label}
          role={agent.role}
          agent={agent.id}
          state={agents[agent.id]}
          detail={lastDetail[agent.id]}
        />
      ))}
    </div>
  )
}

function Bay({
  index,
  label,
  role,
  agent,
  state,
  detail,
}: {
  index: number
  label: string
  role: string
  agent: 'planner' | 'copywriter' | 'visual_planner' | 'director'
  state: AgentState
  detail?: string
}) {
  const still = useReducedMotion()
  const live = state === 'running'

  return (
    <motion.article
      variants={rise(BOOT.agent(index))}
      className={cn(
        'group relative overflow-hidden rounded-xl border transition-colors duration-500',
        live
          ? 'border-edge-strong bg-[rgba(233,238,247,0.045)]'
          : 'border-edge bg-[rgba(233,238,247,0.014)]',
      )}
      animate={{ y: live ? -4 : 0 }}
      transition={SETTLE}
    >
      {/* A working bay is lit from above rather than outlined — the light is
          the status, so there is no badge to read. */}
      <AnimatePresence>
        {live && (
          <motion.span
            key="lit"
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-[rgba(233,238,247,0.12)] to-transparent"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, ease: EASE_OUT }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {live && !still && (
          <motion.span
            key="scan"
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[rgba(233,238,247,0.55)] to-transparent"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0], y: [0, 148] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
          />
        )}
      </AnimatePresence>

      <div className="relative flex flex-col items-center px-3 pt-4 pb-3">
        <div
          className={cn(
            'h-[4.5rem] w-[4.5rem] transition-colors duration-500',
            live && 'text-[#e9eef7]',
            state === 'done' && 'text-[rgba(233,238,247,0.5)]',
            state === 'failed' && 'text-flag',
            state === 'idle' && 'text-[rgba(233,238,247,0.26)]',
          )}
        >
          <AgentCore agent={agent} state={state} />
        </div>

        <h3
          className={cn(
            'display mt-3 text-center text-[0.8125rem] transition-colors duration-500',
            live || state === 'failed' ? 'text-foreground' : 'text-text-2',
          )}
        >
          {label}
        </h3>

        <p
          className={cn(
            'data mt-1 transition-colors duration-500',
            live && 'text-foreground',
            state === 'failed' && 'text-flag',
            (state === 'idle' || state === 'done') && 'text-text-3',
          )}
        >
          {STATE_LABEL[state]}
        </p>
      </div>

      {/* What it is doing, in its own words. Falls back to the job description
          so a standby bay still says what the agent is for. */}
      <p className="relative line-clamp-2 min-h-[2.25rem] border-t border-edge px-3 py-2 text-center text-[0.6875rem] leading-snug text-text-3">
        {detail ?? role}
      </p>
    </motion.article>
  )
}
