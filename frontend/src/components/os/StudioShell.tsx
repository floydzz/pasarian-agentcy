import type { ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { LogDrawer } from '@/components/os/LogDrawer'
import { TopBar } from '@/components/os/TopBar'
import { BOOT, DEPTH, EASE_OUT, rise } from '@/lib/motion'
import type { LogLine } from '@/hooks/useConsole'
import type { Campaign } from '@/api/types'

/** The arrangement both studios are made of.
 *
 * One structural idea: depth is attention. While the machine works, the
 * station and the graph are forward and lit. The moment a gate halts the run,
 * the machine recedes — back, dim, out of focus — and the work comes to the
 * front. The product's whole claim is that a person stands between the agents
 * and the ad spend, so the interface performs it rather than captioning it.
 *
 * It lives here, in one place, for a reason the user gave: the video studio
 * must have the same arrangement as the image studio. Two pages composing the
 * same layout by hand would agree today and disagree within a month. Two pages
 * filling the same shell cannot disagree at all.
 */
export type StudioMedium = 'image' | 'video'

export function StudioShell({
  medium,
  campaign,
  running,
  halted,
  station,
  graph,
  caption,
  gate,
  log,
  children,
}: {
  medium: StudioMedium
  campaign: Campaign
  running: string | null
  halted: boolean
  station: ReactNode
  graph: ReactNode
  caption: ReactNode
  gate: ReactNode
  log: LogLine[]
  /** The work track. */
  children: ReactNode
}) {
  const still = Boolean(useReducedMotion())

  return (
    <motion.div
      initial="hidden"
      animate="shown"
      // A plan review can be taller than a laptop viewport. The shell, rather
      // than the browser body, owns that vertical scroll so the rail stays
      // fixed while the decision cards remain reachable below the machine.
      className="quiet-scroll relative flex h-full flex-col overflow-x-hidden overflow-y-auto bg-void text-foreground"
    >
      <Ambience medium={medium} active={running !== null} halted={halted} still={still} />

      <TopBar campaign={campaign} running={running} medium={medium} />

      {/* The machine. It steps back when you are needed. */}
      <motion.div
        className="relative z-10 shrink-0 px-5 sm:px-8"
        initial={false}
        animate={{
          scale: halted ? 0.955 : 1,
          opacity: halted ? 0.5 : 1,
          filter: halted && !still ? 'blur(1.5px)' : 'blur(0px)',
          marginBottom: halted ? '-3rem' : '0rem',
        }}
        transition={DEPTH}
        style={{ transformOrigin: 'top center' }}
        // A receded machine is out of reach as well as out of focus, so tabbing
        // cannot land on a control the interface has visibly put away.
        inert={halted}
      >
        <motion.div variants={rise(BOOT.station)}>{station}</motion.div>

        <div className="mx-auto mt-2 w-full max-w-[52rem]">{graph}</div>

        <div className="flex h-5 items-center justify-center">{caption}</div>
      </motion.div>

      {gate}

      {children}

      <LogDrawer log={log} running={running} />
    </motion.div>
  )
}

/** One line under the graph: what the machine is doing to itself right now. */
export function StageCaption({ text }: { text: string | null }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      {text && (
        <motion.p
          key={text}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.28, ease: EASE_OUT }}
          className="data text-text-3"
        >
          {text}
        </motion.p>
      )}
    </AnimatePresence>
  )
}

/** The light the instrument sits in.
 *
 * It brightens while work is moving and turns warm while a gate is open —
 * the room reacting, not a widget. Which studio you are in tints it, faintly:
 * enough that the two rooms are not the same room, never enough to compete
 * with the one warm colour that means a person is needed.
 */
const MEDIUM_LIGHT: Record<StudioMedium, string> = {
  image: 'rgba(110,155,255,0.10)',
  video: 'rgba(176,140,255,0.10)',
}

function Ambience({
  medium,
  active,
  halted,
  still,
}: {
  medium: StudioMedium
  active: boolean
  halted: boolean
  still: boolean
}) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <motion.div
        className="absolute -top-1/3 left-1/2 h-[70vh] w-[110vw] -translate-x-1/2 rounded-[50%]"
        initial={false}
        animate={{
          opacity: active ? 0.85 : 0.42,
          background: halted
            ? 'radial-gradient(closest-side, rgba(255,190,106,0.15), transparent 72%)'
            : `radial-gradient(closest-side, ${MEDIUM_LIGHT[medium]}, transparent 72%)`,
        }}
        transition={{ duration: 1.1, ease: EASE_OUT }}
      />
      {!still && (
        <motion.div
          className="absolute -top-1/4 left-1/2 h-[55vh] w-[70vw] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(closest-side,rgba(233,238,247,0.05),transparent_70%)]"
          animate={{ x: ['-52%', '-48%', '-52%'], scale: [1, 1.08, 1] }}
          transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      {/* Weight at the bottom of the frame, so the instrument sits in the dark
          rather than floating on a flat field. */}
      <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/50 to-transparent" />
    </div>
  )
}

/** The pause before a studio has its campaign. */
export function Booting() {
  return (
    <div className="flex h-full items-center justify-center bg-void">
      <motion.div
        className="h-1.5 w-1.5 rounded-full bg-foreground"
        animate={{ scale: [1, 2.4, 1], opacity: [0.35, 1, 0.35] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}
