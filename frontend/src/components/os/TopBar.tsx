import { CalendarCampaignLink } from '@/components/CalendarCampaignLink'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'
import { BOOT, MICRO, rise } from '@/lib/motion'
import { useRoomNav } from '@/lib/rooms'
import type { Campaign } from '@/api/types'

const STATUS_LABEL: Record<Campaign['status'], string> = {
  draft: 'draft',
  planning: 'planning',
  pending_plan_approval: 'Review concepts',
  generating: 'generating',
  pending_asset_review: 'Review creatives',
  ready_to_publish: 'ready',
  published: 'published',
}

const MEDIUM = {
  image: { label: 'Image studio', text: 'text-image' },
  video: { label: 'Video studio', text: 'text-video' },
} as const

/** Keep the campaign title, timing and live state readable at every panel width. */
export function TopBar({
  campaign,
  running,
  medium,
}: {
  campaign: Campaign
  running: string | null
  medium: 'image' | 'video'
}) {
  const studio = MEDIUM[medium]
  const halted = campaign.status.startsWith('pending_')
  const still = useReducedMotion()
  const roomNav = useRoomNav()
  const up = `/campaigns/${campaign.id}`

  return (
    <motion.header
      variants={rise(BOOT.chrome)}
      className="studio-topbar relative z-20 shrink-0"
    >
      <Link
        to={up}
        viewTransition
        onClick={() => roomNav(up)}
        className="studio-back group flex w-fit items-center gap-2 text-text-3 transition-colors hover:text-foreground"
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
        <span className="text-xs">Campaign</span>
      </Link>

      <div className="min-w-0">
        <h1
          style={{ viewTransitionName: `campaign-${campaign.id}` }}
          className="display break-words text-base leading-snug text-foreground sm:text-lg"
        >
          {campaign.name}
        </h1>
        <p className={cn('text-[0.6875rem]', studio.text)}>{studio.label}</p>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-3">
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
      </div>
      {campaign.source_event && <div className="studio-calendar-context flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1"><p className="text-xs text-text-3">{campaign.source_event}</p><CalendarCampaignLink campaignId={campaign.id} /></div>}

    </motion.header>
  )
}
