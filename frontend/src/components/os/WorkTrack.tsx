import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { EASE_OUT, STAGGER, STAGGER_CHILD } from '@/lib/motion'

/** One section of the strip: what it is called and how much of it there is. */
export interface Track {
  id: string
  label: string
  count: number
}

/** The work, as a filmstrip rather than a list.
 *
 * A decision about a concept deserves the whole width of the screen, not a
 * column beside four other panels. Cards snap, so whatever you are deciding on
 * is always the thing centred in front of you.
 *
 * The sections are given rather than fixed, because an image studio holds
 * concepts, variants and creatives while a video studio holds a storyboard and
 * cuts — and both deserve the same filmstrip. */
export function WorkTrack({
  tracks,
  tab,
  onTab,
  empty,
  review = false,
  children,
}: {
  tracks: readonly Track[]
  tab: string
  onTab: (tab: string) => void
  empty: string | null
  /** Decisions are read vertically; production work stays a filmstrip. */
  review?: boolean
  children: ReactNode
}) {
  return (
    <section className={cn('flex flex-col', review ? 'shrink-0' : 'min-h-0 flex-1')}>
      <header className="flex shrink-0 items-center gap-1 px-5 pt-4 pb-3 sm:px-8">
        {tracks.map((track) => (
          <Tab
            key={track.id}
            active={tab === track.id}
            onClick={() => onTab(track.id)}
            count={track.count}
          >
            {track.label}
          </Tab>
        ))}
        <span className="ml-auto hidden text-[0.6875rem] text-text-3 sm:block">
          {empty ? '' : review ? 'Review below ↓' : 'Scroll sideways →'}
        </span>
      </header>

      <div className="min-h-0 flex-1">
        <AnimatePresence mode="wait" initial={false}>
          {empty ? (
            <motion.p
              key={`empty-${tab}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="px-5 py-10 text-sm text-text-3 sm:px-8"
            >
              {empty}
            </motion.p>
          ) : (
            <motion.div
              key={tab}
              variants={STAGGER}
              initial="hidden"
              animate="shown"
              exit={{ opacity: 0, transition: { duration: 0.14 } }}
              className={cn(
                review
                  ? 'grid grid-cols-1 items-stretch gap-4 px-5 pb-6 sm:px-8 lg:grid-cols-2 2xl:grid-cols-3'
                  : 'quiet-scroll snap-track flex h-full items-stretch gap-4 overflow-x-auto overflow-y-hidden px-5 pb-5 sm:px-8',
              )}
            >
              {children}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}

/** One card in the strip. Fixed width so the strip has a rhythm. */
export function TrackItem({ children, review = false }: { children: ReactNode; review?: boolean }) {
  return (
    <motion.div
      variants={STAGGER_CHILD}
      layout
      className={cn(
        'flex',
        review
          ? 'min-h-[33rem] w-full'
          : 'snap-card h-full min-h-[12rem] w-[21rem] shrink-0 sm:w-[25rem]',
      )}
    >
      {children}
    </motion.div>
  )
}

function Tab({
  active,
  onClick,
  count,
  children,
}: {
  active: boolean
  onClick: () => void
  count: number
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative rounded-full px-3.5 py-1.5 text-[0.8125rem] transition-colors duration-300',
        active ? 'text-foreground' : 'text-text-3 hover:text-text-2',
      )}
    >
      {active && (
        <motion.span
          layoutId="track-tab"
          className="absolute inset-0 rounded-full border border-edge bg-[rgba(233,238,247,0.05)]"
          transition={{ duration: 0.32, ease: EASE_OUT }}
        />
      )}
      <span className="relative">
        {children}
        {count > 0 && <span className="data ml-1.5 text-text-3">{count}</span>}
      </span>
    </button>
  )
}
