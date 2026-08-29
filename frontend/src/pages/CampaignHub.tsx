import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { cn } from '@/lib/utils'
import { EASE_OUT, STAGGER, STAGGER_CHILD } from '@/lib/motion'
import { rememberCampaign } from '@/lib/lastCampaign'
import { api, ApiError } from '@/api/client'
import type { Asset, Campaign, Concept, MarketingVideo } from '@/api/types'

/** Where a campaign decides what it wants to be.
 *
 * Every campaign starts as a brief and a decision: stills, film, or both. This
 * is the only screen that knows about both mediums at once — each studio past
 * this point is single-minded — so this is where the choice belongs, and the
 * choice is three cards rather than a menu buried in a settings panel.
 *
 * It is not a gate. Nothing here stops anyone: both studios are also one click
 * away in the rail, because a person who knows they want images should never
 * have to walk through a chooser to reach them.
 */
const STATUS_LINE: Record<Campaign['status'], string> = {
  draft: 'Nothing has run yet.',
  planning: 'The planner is working.',
  pending_plan_approval: 'The plan gate is open — concepts need your decision.',
  generating: 'The crew is working.',
  pending_asset_review: 'The asset gate is open — creatives need your decision.',
  ready_to_publish: 'Approved and ready to export.',
  published: 'Published.',
}

export function CampaignHub() {
  const id = Number(useParams().id)
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [concepts, setConcepts] = useState<Concept[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [videos, setVideos] = useState<MarketingVideo[]>([])

  useEffect(() => {
    rememberCampaign(id)
    Promise.all([
      api.getCampaign(id),
      api.listConcepts(id),
      api.listAssets(id),
      api.listCampaignVideos(id),
    ])
      .then(([fetched, itsConcepts, itsAssets, itsVideos]) => {
        setCampaign(fetched)
        setConcepts(itsConcepts)
        setAssets(itsAssets)
        setVideos(itsVideos)
      })
      .catch((thrown: ApiError) => toast.error(thrown.message))
  }, [id])

  if (!campaign) return <Page><div className="h-40" /></Page>

  const halted = campaign.status.startsWith('pending_')
  const approvedAssets = assets.filter((asset) => asset.review_status === 'approved').length
  const pendingCuts = videos.filter((video) => video.review_status === 'pending').length

  return (
    <Page>
      <motion.header
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE_OUT }}
      >
        <Link to="/" className="text-xs text-text-3 transition-colors hover:text-foreground">
          ← Campaigns
        </Link>
        <h1 className="display-tight mt-4 text-[1.75rem] sm:text-[2rem]">{campaign.name}</h1>
        <p className="copy mt-3 max-w-2xl text-[0.9375rem] leading-relaxed text-text-2">
          {campaign.brief}
        </p>
        <p className={cn('mt-3 text-[0.8125rem]', halted ? 'text-halt' : 'text-text-3')}>
          {STATUS_LINE[campaign.status]}
        </p>
      </motion.header>

      <motion.section
        variants={STAGGER}
        initial="hidden"
        animate="shown"
        className="mt-10 grid gap-4 md:grid-cols-3"
      >
        <StudioCard
          to={`/campaigns/${campaign.id}/image`}
          medium="image"
          title="Images"
          blurb="The planner proposes concepts, the crew writes them, the studio renders the stills."
          stats={[
            `${concepts.length} ${concepts.length === 1 ? 'concept' : 'concepts'}`,
            `${assets.length} ${assets.length === 1 ? 'creative' : 'creatives'}`,
            `${approvedAssets} approved`,
          ]}
          mark={<ImageMark />}
        />
        <StudioCard
          to={`/campaigns/${campaign.id}/video`}
          medium="video"
          title="Video"
          blurb="A storyboard seeded from this campaign's approved work, rendered scene by scene."
          stats={[
            `${videos.length} ${videos.length === 1 ? 'cut' : 'cuts'}`,
            pendingCuts > 0 ? `${pendingCuts} awaiting review` : 'nothing waiting',
          ]}
          mark={<VideoMark />}
        />
        <StudioCard
          to={`/campaigns/${campaign.id}/image`}
          medium="both"
          title="Both"
          blurb="Start with the stills — the approved headline and call to action then seed the video's storyboard."
          stats={['images first', 'then video']}
          mark={<BothMark />}
        />
      </motion.section>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.5 }}
        className="mt-8 text-[0.8125rem] text-text-3"
      >
        Both studios are also in the rail, so you never have to come back through here.
      </motion.p>
    </Page>
  )
}

const TONE = {
  image: {
    ring: 'hover:border-image/50',
    glow: 'from-image/[0.14]',
    text: 'text-image',
  },
  video: {
    ring: 'hover:border-video/50',
    glow: 'from-video/[0.14]',
    text: 'text-video',
  },
  both: {
    ring: 'hover:border-edge-strong',
    glow: 'from-[rgba(233,238,247,0.08)]',
    text: 'text-text-2',
  },
} as const

function StudioCard({
  to,
  medium,
  title,
  blurb,
  stats,
  mark,
}: {
  to: string
  medium: keyof typeof TONE
  title: string
  blurb: string
  stats: string[]
  mark: React.ReactNode
}) {
  const tone = TONE[medium]
  return (
    <motion.div variants={STAGGER_CHILD}>
      <Link
        to={to}
        className={cn(
          'group relative flex h-full flex-col overflow-hidden rounded-xl border border-edge bg-rise p-5 transition-colors duration-300',
          tone.ring,
        )}
      >
        <span
          aria-hidden
          className={cn(
            'pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100',
            tone.glow,
          )}
        />
        <span className={cn('relative', tone.text)}>{mark}</span>
        <h2 className="display relative mt-4 text-[1.0625rem]">{title}</h2>
        <p className="relative mt-2 text-[0.8125rem] leading-relaxed text-text-2">{blurb}</p>
        <p className="data relative mt-auto pt-5 text-text-3">{stats.join(' · ')}</p>
      </Link>
    </motion.div>
  )
}

function ImageMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="8.5" cy="10" r="1.6" fill="currentColor" />
      <path d="M4 17l5-5 4 4 3-2 4 4" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  )
}

function VideoMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="m10 9 5 3-5 3z" fill="currentColor" />
    </svg>
  )
}

function BothMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden>
      <rect x="3" y="7" width="12" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <rect x="9" y="4" width="12" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.3" opacity="0.5" />
    </svg>
  )
}
