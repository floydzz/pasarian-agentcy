import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { DEPTH, EASE_OUT } from '@/lib/motion'
import { api, ApiError } from '@/api/client'
import type { Run, RunDetail } from '@/api/types'

const TAG: Record<string, string> = {
  planner: 'planner',
  copywriter: 'copy',
  visual_planner: 'art',
  director: 'director',
  renderer: 'render',
  vision_qa: 'QA',
  system: 'graph',
}

/** What the machine has already done.
 *
 * A console you have to be watching is a console that forgets, so every pass
 * is kept with the agent events exactly as they were streamed. Opening a run
 * replays it rather than summarising it — which is the difference between an
 * audit trail and a status line, and the reason a flagged variant from last
 * week can still be traced to the verdict that flagged it.
 */
export function History() {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [open, setOpen] = useState<number | null>(null)

  useEffect(() => {
    api
      .listRuns()
      .then(setRuns)
      .catch((error: ApiError) => {
        setRuns([])
        toast.error(error.message)
      })
  }, [])

  // The longest run sets the scale, so the bars compare passes against each
  // other rather than against an arbitrary ceiling.
  const longest = Math.max(1, ...(runs ?? []).map((run) => run.duration_ms))
  const days = groupByDay(runs ?? [])

  return (
    <Page>
      <PageHead
        title="History"
        action={
          runs && runs.length > 0 ? (
            <p className="data shrink-0 text-text-3">
              {runs.length} {runs.length === 1 ? 'run' : 'runs'}
            </p>
          ) : undefined
        }
      >
        Every planning pass and every crew run, with the events the console
        showed while it happened. Open one to replay it.
      </PageHead>

      {runs === null ? (
        <p className="mt-14 text-sm text-text-3">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="mt-14 max-w-md text-sm leading-relaxed text-text-3">
          Nothing has run yet. Open a campaign and start the planner — this page
          fills itself.
        </p>
      ) : (
        <div className="mt-12 flex flex-col gap-10">
          {days.map(([day, ofThatDay]) => (
            <section key={day}>
              <h2 className="label sticky top-0 z-10 -mx-2 bg-void/85 px-2 py-2 backdrop-blur">
                {day}
              </h2>
              <ul className="mt-1">
                {ofThatDay.map((run) => (
                  <Entry
                    key={run.id}
                    run={run}
                    longest={longest}
                    open={open === run.id}
                    onToggle={() => setOpen((was) => (was === run.id ? null : run.id))}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Page>
  )
}

function Entry({
  run,
  longest,
  open,
  onToggle,
}: {
  run: Run
  longest: number
  open: boolean
  onToggle: () => void
}) {
  const failed = run.status === 'failed'

  return (
    <li className="border-b border-edge last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="group flex w-full items-start gap-4 py-3.5 text-left transition-colors"
      >
        <Mark kind={run.kind} failed={failed} />

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
            <span className="truncate text-[0.875rem] text-text-2 transition-colors group-hover:text-foreground">
              {run.campaign_name}
            </span>
            <span className="data text-text-3">{run.kind}</span>
            {run.flagged > 0 && (
              <span className="data text-flag">
                {run.flagged} flagged
              </span>
            )}
            {run.revisions > 0 && (
              <span className="data text-text-3">
                {run.revisions} {run.revisions === 1 ? 'revision' : 'revisions'}
              </span>
            )}
          </span>
          <span
            className={cn(
              'mt-1 block truncate text-[0.75rem]',
              failed ? 'text-flag' : 'text-text-3',
            )}
          >
            {run.summary}
          </span>
        </span>

        <span className="flex shrink-0 flex-col items-end gap-2 pt-0.5">
          {/* How long this pass took, against the longest on the page. Model
              calls are the expensive part of this product and this is the only
              place their cost is visible at a glance. The bar sits beside the
              figure it measures, not under it, where it read as an underline. */}
          <span className="flex items-center gap-2.5">
            <span className="hidden h-px w-16 bg-[rgba(233,238,247,0.09)] sm:block">
              <motion.span
                className={cn('block h-px', failed ? 'bg-flag' : 'bg-foreground/60')}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: Math.max(0.02, run.duration_ms / longest) }}
                transition={{ duration: 0.6, ease: EASE_OUT }}
                style={{ transformOrigin: 'left' }}
              />
            </span>
            <span className="data w-12 text-right text-text-2">
              {seconds(run.duration_ms)}
            </span>
          </span>
          <span className="data text-text-3">{clock(run.started_at)}</span>
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={DEPTH}
            className="overflow-hidden"
          >
            <Replay run={run} />
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  )
}

/** The run reopened: its events, in order, as the log drawer showed them. */
function Replay({ run }: { run: Run }) {
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [failedToLoad, setFailedToLoad] = useState(false)

  useEffect(() => {
    api
      .getRun(run.id)
      .then(setDetail)
      .catch(() => setFailedToLoad(true))
  }, [run.id])

  return (
    <div className="mb-4 rounded-lg border border-edge bg-[rgba(233,238,247,0.02)] px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5">
        <Fact label="provider" value={run.provider} />
        {run.concepts > 0 && <Fact label="concepts" value={String(run.concepts)} />}
        {run.variants > 0 && <Fact label="variants" value={String(run.variants)} />}
        {run.campaign_id !== null && (
          <Link
            to={`/campaigns/${run.campaign_id}`}
            className="data ml-auto text-text-3 underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            open the console →
          </Link>
        )}
      </div>

      {run.error && (
        <p className="mt-3 border-l border-flag/40 pl-3 text-[0.75rem] leading-relaxed text-flag">
          {run.error}
        </p>
      )}

      <div className="quiet-scroll mt-3 max-h-64 overflow-y-auto">
        {failedToLoad ? (
          <p className="data text-text-3">Could not reopen this run.</p>
        ) : detail === null ? (
          <p className="data text-text-3">Reopening…</p>
        ) : detail.events.length === 0 ? (
          <p className="data text-text-3">
            This run recorded no events before it ended.
          </p>
        ) : (
          <ol>
            {detail.events.map((event, index) => (
              <li key={index} className="data flex gap-4 py-[0.1875rem] leading-relaxed">
                <span className="w-16 shrink-0 text-text-3">
                  {TAG[event.agent] ?? event.agent}
                </span>
                <span
                  className={cn(
                    'min-w-0',
                    event.phase === 'failed' ? 'text-flag' : 'text-text-2',
                  )}
                >
                  {event.detail}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="data text-text-3">{label}</span>
      <span className="data text-text-2">{value}</span>
    </span>
  )
}

/** Two glyphs, because there are two kinds of pass: one agent alone, or the
 * crew as a cycle. A failed run keeps its glyph and loses its fill. */
function Mark({ kind, failed }: { kind: Run['kind']; failed: boolean }) {
  const still = useReducedMotion()
  const tone = failed ? 'text-flag' : 'text-text-3'
  return (
    <motion.span
      className={cn('mt-0.5 shrink-0', tone)}
      initial={still ? false : { opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: EASE_OUT }}
    >
      <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden>
        {kind === 'plan' ? (
          <>
            <circle
              cx="8"
              cy="8"
              r="5.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.2"
            />
            <circle cx="8" cy="8" r="1.6" fill={failed ? 'none' : 'currentColor'} />
          </>
        ) : (
          <>
            <path
              d="M3 8a5 5 0 0 1 9-3M13 8a5 5 0 0 1-9 3"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
            />
            <path d="M12 2.5V5.2H9.4" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4 13.5V10.8h2.6" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </>
        )}
      </svg>
    </motion.span>
  )
}

// -- formatting ------------------------------------------------------------

function seconds(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Runs bucketed by the day they started, newest day first.
 *
 * A flat list of timestamps makes you do the date arithmetic yourself; the
 * useful question about a run is nearly always "was that today". */
function groupByDay(runs: Run[]): [string, Run[]][] {
  const days = new Map<string, Run[]>()
  for (const run of runs) {
    const day = dayLabel(run.started_at)
    days.set(day, [...(days.get(day) ?? []), run])
  }
  return [...days.entries()]
}

function dayLabel(iso: string): string {
  const at = new Date(iso)
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)
  const elapsed = midnight.getTime() - at.getTime()

  if (elapsed <= 0) return 'Today'
  if (elapsed <= 86_400_000) return 'Yesterday'
  return at.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: at.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  })
}
