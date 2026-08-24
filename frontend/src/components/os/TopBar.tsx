import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'
import { BOOT, MICRO, rise } from '@/lib/motion'
import type { Campaign } from '@/api/types'

const STATUS_LABEL: Record<Campaign['status'], string> = {
  draft: 'draft',
  planning: 'planning',
  pending_plan_approval: 'halted at the plan gate',
  generating: 'generating',
  pending_asset_review: 'halted at the asset gate',
  ready_to_publish: 'ready',
  published: 'published',
}

/** The header floats: no fill, no bottom rule, no chrome.
 *
 * The instrument should look like it is suspended in the dark rather than
 * assembled out of panels, so nothing here draws a box. */
export function TopBar({
  campaign,
  running,
}: {
  campaign: Campaign
  running: string | null
}) {
  const halted = campaign.status.startsWith('pending_')
  const still = useReducedMotion()

  return (
    <motion.header
      variants={rise(BOOT.chrome)}
      className="relative z-20 flex shrink-0 items-center gap-4 px-5 py-4 sm:px-8"
    >
      <Link
        to="/"
        className="group flex shrink-0 items-center gap-2 text-text-3 transition-colors hover:text-foreground"
      >
        <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
          <path
            d="M7.5 2.5 4 6l3.5 3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
        <span className="text-xs">Campaigns</span>
      </Link>

      <div className="min-w-0 flex-1">
        <h1 className="display truncate text-[0.9375rem] text-foreground sm:text-base">
          {campaign.name}
        </h1>
      </div>

      {campaign.source_event && (
        <span className="data hidden shrink-0 text-text-3 sm:block">
          calendar · {campaign.source_event}
        </span>
      )}

      <span
        className={cn(
          'data shrink-0 transition-colors duration-500',
          halted ? 'text-halt' : 'text-text-3',
        )}
      >
        {STATUS_LABEL[campaign.status]}
      </span>

      {/* The live indicator is the one thing in the header that can move, and
          it moves only while a run is open. */}
      <span className="flex shrink-0 items-center gap-2">
        <span className="relative flex h-1.5 w-1.5">
          {running && !still && (
            <motion.span
              className="absolute inset-0 rounded-full bg-foreground"
              animate={{ scale: [1, 3.2], opacity: [0.6, 0] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut' }}
            />
          )}
          <motion.span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              running ? 'bg-foreground' : 'bg-[rgba(233,238,247,0.28)]',
            )}
            animate={{ opacity: 1 }}
            transition={MICRO}
          />
        </span>
        <span className={cn('data', running ? 'text-foreground' : 'text-text-3')}>
          {running ?? 'idle'}
        </span>
      </span>
    </motion.header>
  )
}
