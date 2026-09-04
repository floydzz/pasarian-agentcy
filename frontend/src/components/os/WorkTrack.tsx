import { createContext, Children, useContext } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { EASE_OUT, STAGGER, STAGGER_CHILD } from '@/lib/motion'

/** Whether the strip is long enough for centre-focus to mean anything.
 *
 * The scroll-driven focus effect reads a card's position in its scroller. In a
 * strip that does not overflow, no card ever reaches the centre, so every card
 * would sit permanently at its dimmed end state and the track would look
 * broken rather than focused. Below the threshold the whole strip is simply
 * present, which is the truth: there is nothing there to scroll past. */
const Focusable = createContext(false)

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
 * cuts — and both deserve the same filmstrip.
 *
 * The track must also keep enough vertical space for a card. The studio's
 * station, gate, and product library can fill a short viewport before the
 * track begins. Letting this flex item absorb only the leftover pixels made
 * the cards effectively unreachable and left the parent with nothing to
 * scroll. A minimum height lets the StudioShell overflow vertically while the
 * cards continue to scroll sideways. */
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
  // Three cards fit across a laptop at this card width, so a fourth is the
  // first that can actually be scrolled to.
  const focusable = !review && Children.count(children) >= 4

  return (
    <section
      className={cn(
        'flex flex-col',
        review ? 'shrink-0' : 'min-h-[32rem] shrink-0',
      )}
    >
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
              <Focusable value={focusable}>{children}</Focusable>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}

/** One card in the strip. Fixed width so the strip has a rhythm. */
export function TrackItem({ children, review = false }: { children: ReactNode; review?: boolean }) {
  const focusable = useContext(Focusable)

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
      {/* The focus effect gets its own element. Putting it on the motion
          element above would have a CSS animation and `motion` writing the
          same transform, and the CSS animation wins — which would silently
          delete the entrance stagger. */}
      {focusable ? (
        <div className="track-focus flex h-full w-full">{children}</div>
      ) : (
        children
      )}
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
