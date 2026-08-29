import { useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { toast } from 'sonner'
import { AgentCore } from '@/components/agents/AgentCore'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { EASE_OUT, MICRO, SETTLE } from '@/lib/motion'
import { api, ApiError } from '@/api/client'
import type { AgentUpdate, Agent as AgentConfig, Knob } from '@/api/types'
import type { AgentName } from '@/api/stream'

/** Where the crew is tuned.
 *
 * The strategist sits first as the front door; the crew follows in the order
 * work moves through it. The copywriter cannot run before the planner and the
 * director judges what the other two made. Numbering here is information, not
 * decoration.
 *
 * Every card states what its agent may *not* do next to what it does. That is
 * the division of labour the whole design rests on — a director that could fix
 * the copy itself would stop being a review — and a settings screen that only
 * showed the knobs would quietly hide it.
 */
export function Agents() {
  const [agents, setAgents] = useState<AgentConfig[] | null>(null)

  useEffect(() => {
    api
      .listAgents()
      .then(setAgents)
      .catch((error: ApiError) => {
        setAgents([])
        toast.error(error.message)
      })
  }, [])

  const changed = agents?.filter((agent) => !agent.is_default).length ?? 0

  return (
    <Page>
      <PageHead
        title="The crew"
        action={
          <p className="data shrink-0 text-text-3">
            {changed === 0
              ? 'all at shipped defaults'
              : `${changed} ${changed === 1 ? 'agent' : 'agents'} tuned`}
          </p>
        }
      >
        The strategist opens the work, then the crew carries it through the
        pipeline. What you set here applies to the next run — including one
        you start a second later.
      </PageHead>

      {agents === null ? (
        <p className="mt-14 text-sm text-text-3">Loading…</p>
      ) : (
        <div className="mt-12 flex flex-col gap-4">
          {agents.map((agent, index) => (
            <Bay
              key={agent.agent}
              agent={agent}
              position={index + 1}
              last={index === agents.length - 1}
              onSaved={(saved) =>
                setAgents((current) =>
                  (current ?? []).map((one) =>
                    one.agent === saved.agent ? saved : one,
                  ),
                )
              }
            />
          ))}
        </div>
      )}
    </Page>
  )
}

function Bay({
  agent,
  position,
  last,
  onSaved,
}: {
  agent: AgentConfig
  position: number
  last: boolean
  onSaved: (saved: AgentConfig) => void
}) {
  const still = useReducedMotion()
  const [hovered, setHovered] = useState(false)
  const [draft, setDraft] = useState(() => toDraft(agent))
  const [saving, setSaving] = useState(false)

  // The server is the authority on what a value became — it clamps — so the
  // draft is rebuilt from whatever came back rather than from what was sent.
  useEffect(() => setDraft(toDraft(agent)), [agent])

  const dirty = useMemo(() => {
    if ((draft.note ?? '') !== (agent.standing_note ?? '')) return true
    return agent.knobs.some((knob) => draft.values[knob.field] !== knob.value)
  }, [draft, agent])

  async function save() {
    setSaving(true)
    try {
      const payload: AgentUpdate = { standing_note: draft.note }
      for (const knob of agent.knobs) {
        payload[knob.field as keyof AgentUpdate] = draft.values[
          knob.field
        ] as never
      }
      onSaved(await api.tuneAgent(agent.agent, payload))
      toast.success(`${agent.label} updated — it takes effect on the next run`)
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    setSaving(true)
    try {
      onSaved(await api.resetAgent(agent.agent))
      toast.success(`${agent.label} back to its shipped settings`)
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE_OUT, delay: position * 0.06 }}
      className="glass relative rounded-xl px-5 py-5 sm:px-7 sm:py-6"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* The line that carries the work to the next agent. It runs between the
          cards rather than inside them, so the four read as one chain. */}
      {!last && (
        <span
          aria-hidden
          className="absolute -bottom-4 left-[4.75rem] h-4 w-px bg-edge sm:left-[5.5rem]"
        />
      )}

      <div className="flex items-start gap-4 sm:gap-5">
        <span className="data mt-1 w-3 shrink-0 text-text-3">{position}</span>
        {/* Hovering the card runs the core: the fastest way to know what an
            agent looks like working is to see it work. */}
        <div className="h-14 w-14 shrink-0 text-foreground">
          <AgentCore
            agent={agent.agent as Exclude<AgentName, 'system'>}
            state={hovered && !still ? 'running' : 'idle'}
          />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h2 className="display text-[0.9375rem]">{agent.label}</h2>
            {!agent.is_default && <span className="data text-text-3">tuned</span>}
          </div>
          <p className="mt-1.5 text-[0.875rem] leading-relaxed text-text-2">
            {agent.role}
          </p>
          <p className="mt-2.5 border-l border-edge-strong pl-3 text-[0.8125rem] leading-relaxed text-text-3">
            {agent.boundary}
          </p>
        </div>
      </div>

      <div className="mt-6 sm:pl-[5.25rem]">
        {agent.knobs.length > 0 && (
          <div className="mb-7 grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            {agent.knobs.map((knob) => (
              <Meter
                key={knob.field}
                knob={knob}
                value={draft.values[knob.field]}
                onChange={(value) =>
                  setDraft((current) => ({
                    ...current,
                    values: { ...current.values, [knob.field]: value },
                  }))
                }
              />
            ))}
          </div>
        )}

        <div className="max-w-2xl">
          <label htmlFor={`note-${agent.agent}`} className="label block">
            Standing instruction
          </label>
          <textarea
            id={`note-${agent.agent}`}
            rows={2}
            value={draft.note}
            placeholder={agent.note_placeholder}
            onChange={(event) =>
              setDraft((current) => ({ ...current, note: event.target.value }))
            }
            className="mt-2 w-full resize-none rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-[0.8125rem] leading-relaxed text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]"
          />
          <p className="mt-2 text-[0.6875rem] leading-relaxed text-text-3">
            Added to this agent’s brief. It can direct — never override the brand
            guardrails or the grounding rules.
          </p>
        </div>

        <div className="mt-5 flex items-center gap-4">
          <motion.button
            type="button"
            onClick={save}
            disabled={!dirty || saving}
            whileHover={!dirty || saving ? undefined : { y: -1 }}
            whileTap={!dirty || saving ? undefined : { scale: 0.985 }}
            transition={MICRO}
            className="display rounded-full bg-foreground px-4 py-1.5 text-[0.75rem] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
          >
            {saving ? 'Saving…' : 'Save'}
          </motion.button>
          <button
            type="button"
            onClick={reset}
            disabled={agent.is_default || saving}
            className="text-[0.75rem] text-text-3 transition-colors hover:text-text-2 disabled:cursor-not-allowed disabled:opacity-30"
          >
            Reset to default
          </button>
          {dirty && (
            <span className="data text-text-3">unsaved</span>
          )}
        </div>
      </div>
    </motion.section>
  )
}

/** One integer, as a level a person can set by pointing at it.
 *
 * A meter rather than a number box because these values have a shape: the
 * distance to the maximum is the useful information — how much further this
 * can be pushed, and how far it already is from what the agent shipped with.
 */
function Meter({
  knob,
  value,
  onChange,
}: {
  knob: Knob
  value: number
  onChange: (value: number) => void
}) {
  const still = useReducedMotion()
  const stops = Array.from(
    { length: knob.maximum - knob.minimum + 1 },
    (_, index) => knob.minimum + index,
  )

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-[0.8125rem] text-text-2">{knob.label}</span>
        <span className="flex items-baseline gap-2">
          {value !== knob.default && (
            <span className="data text-text-3">was {knob.default}</span>
          )}
          <span className="data text-[0.875rem] text-foreground">{value}</span>
        </span>
      </div>

      <div
        role="group"
        aria-label={knob.label}
        className="mt-2.5 flex h-7 max-w-[15rem] items-end gap-[2px]"
      >
        {stops.map((stop) => {
          const set = stop === value
          const under = stop < value
          return (
            <button
              key={stop}
              type="button"
              onClick={() => onChange(stop)}
              aria-label={`${knob.label}: ${stop}`}
              aria-pressed={set}
              title={String(stop)}
              className="group flex h-7 min-w-0 flex-1 items-end rounded-sm outline-none focus-visible:ring-1 focus-visible:ring-[rgba(233,238,247,0.5)]"
            >
              <motion.span
                className={cn(
                  'w-full rounded-[1px]',
                  set
                    ? 'bg-foreground'
                    : under
                      ? 'bg-[rgba(233,238,247,0.42)]'
                      : 'bg-[rgba(233,238,247,0.13)] group-hover:bg-[rgba(233,238,247,0.28)]',
                )}
                initial={false}
                animate={{ height: set ? '100%' : under ? '52%' : '30%' }}
                transition={still ? { duration: 0 } : SETTLE}
              />
            </button>
          )
        })}
      </div>

      <p className="mt-2 text-[0.6875rem] leading-relaxed text-text-3">{knob.help}</p>
    </div>
  )
}

function toDraft(agent: AgentConfig) {
  return {
    note: agent.standing_note ?? '',
    values: Object.fromEntries(
      agent.knobs.map((knob) => [knob.field, knob.value]),
    ) as Record<string, number>,
  }
}
