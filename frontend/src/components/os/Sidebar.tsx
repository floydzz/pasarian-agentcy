import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'
import { EASE_OUT, SETTLE } from '@/lib/motion'
import { api } from '@/api/client'
import type { System } from '@/api/types'

/** The rail.
 *
 * Two groups, and the split says something true: the top group is work the
 * machine has done and you look at, the bottom is the machine itself and you
 * set it. A flat list of four would have implied they are the same kind of
 * thing, and reaching for the agents' settings is not the same act as opening
 * a campaign.
 *
 * Marks are drawn from the product's own vocabulary rather than from an icon
 * set — the four dots really are the four agents, the rising steps really are
 * what the trend watchlist measures.
 */
const GROUPS = [
  {
    label: 'Work',
    items: [
      { to: '/', label: 'Campaigns', mark: Stack, end: true },
      // Both studios sit at the top level. A studio belongs to a campaign, but
      // burying the way in would mean digging through a campaign every time
      // you want to look at the work you were doing five minutes ago.
      { to: '/studio/image', label: 'Image studio', mark: Frame, tint: 'text-image' },
      { to: '/studio/video', label: 'Video studio', mark: Play, tint: 'text-video' },
      { to: '/progress', label: 'Progress', mark: Pulse },
      { to: '/publish', label: 'Publish', mark: Tray },
      { to: '/history', label: 'History', mark: Rings },
    ],
  },
  {
    label: 'Machine',
    items: [
      { to: '/brand', label: 'Brand profile', mark: Brand },
      { to: '/agents', label: 'Agents', mark: Quad },
      { to: '/trends', label: 'Trends', mark: Steps },
    ],
  },
] as const

export function Sidebar() {
  const [system, setSystem] = useState<System | null>(null)
  const still = useReducedMotion()
  const { pathname } = useLocation()

  useEffect(() => {
    api.system().then(setSystem).catch(() => setSystem(null))
  }, [])

  // A studio is a place inside a campaign, so the rail lights the studio you
  // are standing in rather than losing your place — and the campaign hub
  // itself lights Campaigns, which is where it came from.
  const active = pathname.endsWith('/image')
    ? '/studio/image'
    : pathname.endsWith('/video')
      ? '/studio/video'
      : pathname.startsWith('/campaigns')
        ? '/'
        : pathname

  return (
    <nav
      aria-label="Sections"
      className="relative z-30 flex h-full w-16 shrink-0 flex-col border-r border-edge bg-void lg:w-[13.5rem]"
    >
      <NavLink
        to="/"
        className="flex h-16 shrink-0 items-center gap-3 px-4 lg:px-5"
        aria-label="Agentcy home"
      >
        <Aperture />
        <span className="display hidden text-[0.9375rem] lg:block">Agentcy</span>
      </NavLink>

      <div className="flex min-h-0 flex-1 flex-col gap-7 overflow-y-auto px-2.5 py-2 lg:px-3">
        {GROUPS.map((group) => (
          <div key={group.label}>
            <p className="label mb-1.5 hidden px-2.5 lg:block">{group.label}</p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const lit = active === item.to
                const sharedClass = cn(
                  'group relative flex w-full items-center gap-3 rounded-lg px-2.5 py-2.5 text-left transition-colors',
                  lit
                    ? 'text-foreground'
                    : 'text-text-3 hover:bg-[rgba(233,238,247,0.03)] hover:text-text-2',
                )
                const contents = (
                  <>
                    {/* The lit segment travels between entries rather than
                        appearing and disappearing, so the rail reads as one
                        continuous control with a position. */}
                    {lit && (
                      <motion.span
                        layoutId="rail-mark"
                        transition={still ? { duration: 0 } : SETTLE}
                        className="absolute inset-0 -z-10 rounded-lg bg-[rgba(233,238,247,0.06)]"
                      >
                        <span className="absolute top-1/2 -left-2.5 h-5 w-px -translate-y-1/2 bg-foreground lg:-left-3" />
                      </motion.span>
                    )}
                    <span className={cn('shrink-0', 'tint' in item && !lit ? item.tint : undefined)}>
                      <item.mark />
                    </span>
                    <span className="hidden text-[0.8125rem] lg:block">
                      {item.label}
                    </span>
                  </>
                )
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={'end' in item ? item.end : false}
                      // The label is in the DOM at every width for assistive
                      // tech; the tooltip is for sighted people on the narrow
                      // rail, where it is the only way to read a mark.
                      title={item.label}
                      className={sharedClass}
                    >
                      {contents}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>

      <Footer system={system} />
    </nav>
  )
}

/** What the machine is currently made of.
 *
 * The provider is on screen at all times on purpose: `demo` writes copy that
 * reads like copy, and a rehearsal must never be mistaken for a live model by
 * whoever is watching. */
function Footer({ system }: { system: System | null }) {
  if (!system) return <div className="h-14 shrink-0" />

  const rehearsing = system.llm_provider === 'demo'
  return (
    <div className="shrink-0 border-t border-edge px-4 py-3.5 lg:px-5">
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            'h-1.5 w-1.5 shrink-0 rounded-full',
            rehearsing ? 'bg-[rgba(233,238,247,0.3)]' : 'bg-go',
          )}
        />
        <span className="data hidden truncate text-text-2 lg:block">
          {system.llm_provider}
        </span>
      </div>
      <p className="data mt-1 hidden text-text-3 lg:block">
        {rehearsing ? 'offline rehearsal' : 'live model'} · {system.geo}
      </p>
    </div>
  )
}

// -- marks -----------------------------------------------------------------

/** The product's mark: the creative director's aperture, open. */
function Aperture() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6 shrink-0 text-foreground" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <circle
        cx="12"
        cy="12"
        r="3.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.55"
      />
      {[0, 60, 120, 180, 240, 300].map((angle) => (
        <line
          key={angle}
          x1="12"
          y1="12"
          x2={12 + 9 * Math.cos((angle * Math.PI) / 180)}
          y2={12 + 9 * Math.sin((angle * Math.PI) / 180)}
          stroke="currentColor"
          strokeWidth="0.9"
          opacity="0.28"
        />
      ))}
    </svg>
  )
}

/** Campaigns: work stacked, the top one in focus. */
function Stack() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <rect x="2" y="3" width="12" height="3" rx="1" fill="currentColor" />
      <rect x="2" y="8" width="12" height="3" rx="1" fill="currentColor" opacity="0.5" />
      <rect x="2" y="13" width="8" height="1.5" rx="0.75" fill="currentColor" opacity="0.28" />
    </svg>
  )
}

/** Progress: one live signal moving through the work. */
function Pulse() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <path d="M1.5 8h3l1.5-3.5 3 7L10.5 8h4" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Export: a finished piece leaving the tray. */
function Tray() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <path
        d="M2.5 9.5v3h11v-3M11 6 8 9 5 6M8 8.5V1.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** History: passes stacked back in time, the oldest faintest. */
function Rings() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <circle cx="8" cy="8" r="2" fill="currentColor" />
      <circle cx="8" cy="8" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.55" />
      <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.25" />
    </svg>
  )
}

/** Image studio: a frame with a horizon and a sun in it. */
function Frame() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <rect x="2" y="3" width="12" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="6" cy="6.5" r="1.2" fill="currentColor" />
      <path d="M3 11.5 6.5 8l2.5 2.5L11 9l2 2.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  )
}

/** Video studio: a vertical frame with the playhead inside it. */
function Play() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <rect x="3" y="1.5" width="10" height="13" rx="2" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <path d="m6.5 5 4 3-4 3z" fill="currentColor" />
    </svg>
  )
}

/** Agents: the four of them. */
function Quad() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      {[
        [5, 5],
        [11, 5],
        [5, 11],
        [11, 11],
      ].map(([x, y], index) => (
        <circle
          key={`${x}-${y}`}
          cx={x}
          cy={y}
          r="2"
          fill="currentColor"
          opacity={index === 0 ? 1 : 0.45}
        />
      ))}
    </svg>
  )
}

/** Brand profile: a source document with one grounded product mark. */
function Brand() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <path
        d="M3 2.5h7l3 3v8H3z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
      <path d="M10 2.5v3h3M5.5 9h5M5.5 11.5h3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" />
    </svg>
  )
}

/** Trends: rising interest, which is the only thing the watchlist measures. */
function Steps() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" aria-hidden>
      <path
        d="M2 12.5 L6 8.5 L9 10.5 L14 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="14" cy="4" r="1.6" fill="currentColor" />
    </svg>
  )
}

/** Shared by every page that is not the console: a quiet page header. */
export function PageHead({
  title,
  children,
  action,
}: {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <motion.header
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE_OUT }}
      className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4"
    >
      <div className="min-w-0">
        <h1 className="display-tight text-[1.75rem] sm:text-[2rem]">{title}</h1>
        <p className="mt-2 max-w-xl text-[0.875rem] leading-relaxed text-text-2">
          {children}
        </p>
      </div>
      {action}
    </motion.header>
  )
}
