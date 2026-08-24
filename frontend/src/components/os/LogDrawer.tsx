import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { DEPTH, EASE_OUT } from '@/lib/motion'
import type { LogLine } from '@/hooks/useConsole'

const TAG: Record<string, string> = {
  planner: 'planner',
  copywriter: 'copy',
  visual_planner: 'art',
  director: 'director',
  system: 'graph',
}

/** The audit trail, kept out of the way until it is wanted.
 *
 * Collapsed it is one line: whatever the crew said last. That is enough to
 * follow a run. Opened it is everything, in order, which is what you need when
 * a variant arrives flagged and you want to know which test it failed. */
export function LogDrawer({ log, running }: { log: LogLine[]; running: string | null }) {
  const [open, setOpen] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const latest = log[log.length - 1]

  useEffect(() => {
    if (open) end.current?.scrollIntoView({ block: 'end' })
  }, [log.length, open])

  return (
    <motion.section layout className="relative z-20 shrink-0 border-t border-edge bg-void">
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="full"
            initial={{ height: 0, opacity: 0 }}
            // Sized to its contents rather than to a fixed slab: an empty log
            // that steals 260px from the work below it is a drawer that
            // punishes you for opening it.
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={DEPTH}
            className="quiet-scroll max-h-[11rem] overflow-y-auto"
          >
            {log.length === 0 && (
              <p className="data px-5 py-4 text-text-3 sm:px-8">
                Nothing has run yet. Start the planner and the agents report here.
              </p>
            )}
            <ol className="px-5 py-3 sm:px-8">
              {log.map((line) => (
                <li
                  key={line.seq}
                  className="data flex gap-4 py-[0.1875rem] leading-relaxed"
                >
                  <span className="shrink-0 text-text-3">{line.at}</span>
                  <span className="w-16 shrink-0 text-text-3">{TAG[line.agent] ?? line.agent}</span>
                  <span
                    className={cn(
                      'min-w-0',
                      line.phase === 'failed' ? 'text-flag' : 'text-text-2',
                    )}
                  >
                    {line.detail}
                  </span>
                </li>
              ))}
              <div ref={end} />
            </ol>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        className="flex w-full items-center gap-3.5 px-5 py-2.5 text-left transition-colors hover:bg-[rgba(233,238,247,0.025)] sm:px-8"
      >
        <span className="data shrink-0 text-text-3">
          {running ? `${running} running` : `${log.length} events`}
        </span>

        {/* The newest line, replaced in place. The log reads as a ticker while
            a run is open, which is all the detail anyone needs mid-run.
            Keyed and remounted rather than wrapped in AnimatePresence: events
            can land faster than an exit animation runs, and a ticker that is
            waiting for the previous line to leave is a ticker that is blank
            for exactly as long as the run is interesting. */}
        <span className="min-w-0 flex-1 overflow-hidden">
          <motion.span
            key={latest?.seq ?? 'none'}
            initial={{ opacity: 0, y: 7 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.26, ease: EASE_OUT }}
            className={cn(
              'data block truncate',
              latest?.phase === 'failed' ? 'text-flag' : 'text-text-2',
            )}
          >
            {latest
              ? `${TAG[latest.agent] ?? latest.agent} · ${latest.detail}`
              : 'Nothing has run yet.'}
          </motion.span>
        </span>

        <motion.span
          className="shrink-0 text-text-3"
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.32, ease: EASE_OUT }}
        >
          <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
            <path
              d="M2.5 7.5 6 4l3.5 3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </motion.span>
      </button>
    </motion.section>
  )
}
