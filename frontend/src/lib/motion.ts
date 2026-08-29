import type { Transition, Variants } from 'motion/react'

/** The instrument's motion vocabulary.
 *
 * Two rules hold everywhere:
 *
 * 1. Nothing moves unless work is moving. Ambient drift is the single
 *    exception, and it is slow enough to read as atmosphere rather than as
 *    activity.
 * 2. Motion is depth before it is position. When a gate halts the run, the
 *    machine recedes and the work comes forward — the interface performs the
 *    product's actual claim, that a person stands between the agents and the
 *    ad spend.
 */

/** Expo-out. Arrives fast, settles slowly: reads as mass, not as bounce. */
export const EASE_OUT = [0.16, 1, 0.3, 1] as const

/** Apple's favourite curve for things that move under their own power. */
export const EASE_IN_OUT = [0.65, 0, 0.35, 1] as const

/** Something arrived and has weight: a card, a gate bar, a panel. */
export const SETTLE: Transition = {
  type: 'spring',
  stiffness: 240,
  damping: 28,
  mass: 0.9,
}

/** A hover, a chip, a toggle. Fast enough to feel like a direct consequence. */
export const MICRO: Transition = { duration: 0.16, ease: EASE_OUT }

/** A layer changing depth. Slow enough to read as distance rather than size. */
export const DEPTH: Transition = { duration: 0.72, ease: EASE_IN_OUT }

/** An agent is thinking. An LLM call runs 10–30s; this is what says "alive,
 * not hung". Long and even — a blink would read as an alarm. */
export const BREATH: Transition = {
  duration: 2.6,
  repeat: Infinity,
  ease: 'easeInOut',
}

/** Work travelling along an edge of the graph. */
export const FLOW_SECONDS = 1.5

/** Each robot core runs on its own clock, so four working agents do not
 * lock into step and read as one animation. */
export const CORE_PERIOD = {
  chat: 3.4,
  planner: 3.2,
  copywriter: 2.4,
  visual_planner: 3.6,
  director: 4.0,
  renderer: 3.0,
  vision_qa: 2.8,
} as const

/** The instrument powering on.
 *
 * An orchestrated sequence rather than scattered fades: the ground arrives,
 * then the agents in the order work flows through them, then the graph draws
 * itself, then the chrome. Roughly 1.1s end to end. */
export const BOOT = {
  ground: 0,
  station: 0.18,
  agent: (index: number) => 0.18 + index * 0.09,
  graph: 0.62,
  chrome: 0.86,
} as const

export function rise(delay = 0): Variants {
  return {
    hidden: { opacity: 0, y: 14 },
    shown: {
      opacity: 1,
      y: 0,
      transition: { delay, duration: 0.62, ease: EASE_OUT },
    },
  }
}

/** A list whose children arrive one after another rather than all at once. */
export const STAGGER: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.05 } },
}

export const STAGGER_CHILD: Variants = {
  hidden: { opacity: 0, y: 12 },
  shown: { opacity: 1, y: 0, transition: SETTLE },
}
