import { useId, type ReactNode } from 'react'
import { AnimatePresence, LayoutGroup, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { EASE_OUT, STAGGER, STAGGER_CHILD } from '@/lib/motion'

export interface Track { id: string; label: string; count: number }

/** Both studios use a wrapping grid sized to their available panel width. */
export function WorkTrack({ tracks, tab, onTab, empty, review = false, children }: {
  tracks: readonly Track[]; tab: string; onTab: (tab: string) => void
  empty: string | null; review?: boolean; children: ReactNode
}) {
  const tabsId = useId()
  return (
    <section className="relative min-w-0 shrink-0">
      <LayoutGroup id={tabsId}><header className="flex flex-wrap items-center gap-1 px-4 pt-4 pb-4 sm:px-8">
        {tracks.map(track => <Tab key={track.id} active={tab === track.id} onClick={() => onTab(track.id)} count={track.count}>{track.label}</Tab>)}
      </header></LayoutGroup>
      <AnimatePresence mode="popLayout" initial={false}>
        {empty ? (
          <motion.p key={`empty-${tab}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, pointerEvents: 'none' }} transition={{ duration: .2 }} className="px-4 py-10 text-sm text-text-3 sm:px-8">{empty}</motion.p>
        ) : (
          <motion.div key={tab} variants={STAGGER} initial="hidden" animate="shown" exit={{ opacity: 0, pointerEvents: 'none', transition: { duration: .14 } }} style={{ pointerEvents: 'auto' }} data-review={review} className="work-grid px-4 pb-24 sm:px-8 sm:pb-8">
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

export function TrackItem({ children, review = false }: { children: ReactNode; review?: boolean }) {
  return <motion.div variants={STAGGER_CHILD} layout="position" data-review={review} className="work-grid-item">{children}</motion.div>
}

function Tab({ active, onClick, count, children }: { active: boolean; onClick: () => void; count: number; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={cn('relative rounded-lg px-3 py-2 text-sm transition-colors', active ? 'text-foreground' : 'text-text-3 hover:text-text-2')}>
      {active && <motion.span layoutId="track-tab" className="absolute inset-0 rounded-lg border border-edge bg-lift" transition={{ duration: .32, ease: EASE_OUT }} />}
      <span className="relative">{children}{count > 0 && <span className="ml-2 text-xs text-text-3">{count}</span>}</span>
    </button>
  )
}
