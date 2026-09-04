import { useEffect, useState } from 'react'
import { Link, useViewTransitionState } from 'react-router-dom'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { useRoomNav } from '@/lib/rooms'
import { api, ApiError } from '@/api/client'
import type { Campaign } from '@/api/types'

/** The campaign directory is deliberately a directory, not another dashboard.
 * A campaign is the container for work; the studio and publish links are the
 * useful next decisions, so they live on every row rather than behind a
 * campaign-detail detour. New briefs begin in the strategist bubble. */
const STATUS: Record<Campaign['status'], string> = {
  draft: 'Brief ready',
  planning: 'Planning in progress',
  pending_plan_approval: 'Concepts need a decision',
  generating: 'Creative team working',
  pending_asset_review: 'Creatives need a decision',
  ready_to_publish: 'Ready to publish',
  published: 'Published',
}

export function Home() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null)

  useEffect(() => {
    api.listCampaigns().then(setCampaigns).catch((error: ApiError) => {
      setCampaigns([])
      toast.error(error.message)
    })
  }, [])

  return (
    <Page>
      <PageHead
        title="Campaigns"
        action={
          <Link
            to="/?chat=open"
            className="rounded-full bg-foreground px-4 py-2 text-[0.75rem] text-void transition-opacity hover:opacity-90"
          >
            Start with the strategist
          </Link>
        }
      >
        Every brief you have built. Open its production console or take its approved work to Publish.
      </PageHead>

      {campaigns === null ? (
        <p className="mt-12 text-sm text-text-3">Loading campaigns…</p>
      ) : campaigns.length === 0 ? (
        <Empty />
      ) : (
        <ul className="mt-10 divide-y divide-edge border-y border-edge">
          {campaigns.map((campaign, index) => (
            <CampaignRow key={campaign.id} campaign={campaign} index={index} />
          ))}
        </ul>
      )}
    </Page>
  )
}

export function CampaignRow({ campaign, index }: { campaign: Campaign; index: number }) {
  const needsYou = campaign.status.startsWith('pending_')
  const roomNav = useRoomNav()
  const toImage = `/campaigns/${campaign.id}/image`
  const toVideo = `/campaigns/${campaign.id}/video`
  const toPublish = `/campaigns/${campaign.id}/publish`

  // Only the row you are actually leaving through is named. Naming all of
  // them would leave every other row as an exiting element with its own
  // animation, and a directory dissolving row by row is not what the gesture
  // is about — one campaign travelling into its studio is.
  const enteringImage = useViewTransitionState(toImage)
  const enteringVideo = useViewTransitionState(toVideo)
  const leaving = enteringImage || enteringVideo

  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.035, 0.24), duration: 0.35 }}
      className="grid gap-4 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-8"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2
            style={{ viewTransitionName: leaving ? `campaign-${campaign.id}` : undefined }}
            className="display text-[1rem] text-foreground"
          >
            {campaign.name}
          </h2>
          <span className={cn('data', needsYou ? 'text-halt' : 'text-text-3')}>
            {STATUS[campaign.status]}
          </span>
        </div>
        <p className="copy mt-2 line-clamp-2 max-w-3xl text-[0.875rem] leading-relaxed text-text-2">
          {campaign.brief}
        </p>
        <p className="data mt-2 text-text-3">
          Updated {new Date(campaign.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        </p>
      </div>
      <div className="flex flex-wrap gap-2 sm:justify-end">
        <Link to={toImage} viewTransition onClick={() => roomNav(toImage)} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 transition-colors hover:border-image/60 hover:text-image">
          Image console
        </Link>
        <Link to={toVideo} viewTransition onClick={() => roomNav(toVideo)} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-video transition-colors hover:border-video/60">
          Video studio
        </Link>
        <Link to={toPublish} viewTransition onClick={() => roomNav(toPublish)} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground">
          Publish
        </Link>
      </div>
    </motion.li>
  )
}

function Empty() {
  return (
    <section className="mt-12 max-w-xl rounded-xl border border-dashed border-edge-strong px-6 py-10">
      <p className="display text-[0.9375rem]">Your campaign directory is empty.</p>
      <p className="mt-2 text-[0.8125rem] leading-relaxed text-text-3">
        Open the strategist bubble, describe what you want to market, and it will turn the conversation into a campaign when you approve the brief.
      </p>
      <Link to="/?chat=open" className="mt-5 inline-block text-[0.8125rem] text-foreground underline underline-offset-4">
        Open strategist
      </Link>
    </section>
  )
}
