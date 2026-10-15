import { useAuth } from '@/lib/auth'
import { useWorkspaceRefresh } from '@/hooks/useWorkspaceRefresh'
import { useEffect, useState } from 'react'
import { Link, useSearchParams, useViewTransitionState } from 'react-router-dom'
import { motion } from 'motion/react'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { useRoomNav } from '@/lib/rooms'
import { campaignFlow } from '@/lib/campaignFlow'
import { api } from '@/api/client'
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
  const actor = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => { sessionStorage.setItem(`agentcy-directory:${actor.user.id}:${actor.workspace_id}`, `/campaigns${searchParams.size ? '?' + searchParams.toString() : ''}`) }, [searchParams, actor.user.id, actor.workspace_id])
  const query = searchParams.get('q') ?? ''
  const filter = searchParams.get('filter') ?? 'all'
  const offset = Math.max(0, Number(searchParams.get('offset')) || 0)
  const [page, setPage] = useState<{ items: Campaign[]; total: number; limit: number } | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  useWorkspaceRefresh(() => setRetry(value => value + 1))
  function change(values: Record<string, string>) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(values)) { if (!value || value === 'all' || value === '0') next.delete(key); else next.set(key, value) }
    setSearchParams(next, { replace: true })
  }
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    const timer = window.setTimeout(() => {
      api.campaignDirectory(query, filter, offset, controller.signal).then(setPage).catch((failure: Error) => { if (!controller.signal.aborted) setError(failure.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    }, 200)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, filter, offset, retry])
  return <Page>
    <PageHead title="Campaigns" action={<Link to="/chat" className="workspace-button">New campaign</Link>}>Your marketing work, from the first idea to approved creative.</PageHead>
    <div className="mt-7 space-y-3"><label className="block max-w-xl"><span className="sr-only">Search campaigns</span><input type="search" maxLength={200} className="workspace-input" placeholder="Search name, occasion or brief" value={query} onChange={event => change({ q: event.target.value, offset: '0' })} /></label><div className="flex flex-wrap gap-2" aria-label="Campaign filters">{[['all', 'All'], ['review', 'Needs review'], ['working', 'In progress'], ['ready', 'Ready'], ['draft', 'Drafts']].map(([id, label]) => <button key={id} type="button" aria-pressed={filter === id} className={filter === id ? 'workspace-secondary bg-accent font-medium' : 'workspace-secondary text-text-3'} onClick={() => change({ filter: id, offset: '0' })}>{label}</button>)}</div></div>
    {error ? <div role="alert" className="mt-8 rounded-xl border border-halt/40 p-5 text-sm"><p>{error}</p><button className="workspace-secondary mt-3" onClick={() => setRetry(value => value + 1)}>Retry loading campaigns</button></div> : loading ? <p role="status" className="mt-10 text-sm text-text-3">Loading campaigns…</p> : page && page.total === 0 && !query && filter === 'all' ? <Empty /> : <>
      <p className="mt-6 text-xs text-text-3">{page?.total ?? 0} campaigns{query || filter !== 'all' ? ' match your filters' : ' in your workspace'}</p>
      {page?.items.length ? <ul className="mt-3 divide-y divide-edge border-y border-edge">{page.items.map((campaign, index) => <CampaignRow key={campaign.id} campaign={campaign} index={index} />)}</ul> : <p className="py-8 text-sm text-text-3">No campaigns match. Try another search or choose All.</p>}
      {page && (page.total > page.limit || offset > 0) && <nav aria-label="Campaign pagination" className="mt-5 flex flex-wrap items-center gap-3"><button className="workspace-secondary" disabled={!offset} onClick={() => change({ offset: String(Math.max(0, offset - page.limit)) })}>Previous</button><span className="text-xs text-text-3">{Math.min(offset + 1, page.total)}–{Math.min(offset + page.limit, page.total)} of {page.total}</span><button className="workspace-secondary" disabled={offset + page.limit >= page.total} onClick={() => change({ offset: String(offset + page.limit) })}>Next page</button></nav>}
    </>}
  </Page>
}

export function CampaignRow({ campaign, index }: { campaign: Campaign; index: number }) {
  const needsYou = campaign.status.startsWith('pending_')
  const flow = campaignFlow(campaign)
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
      className="grid gap-4 py-5 campaign-row"
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
      <div className="campaign-actions flex flex-wrap gap-2">
        <Link to={flow.to} className="workspace-button">{flow.action}</Link>
        <details className="relative"><summary className="workspace-secondary">More</summary><div className="absolute right-0 z-20 mt-2 grid w-40 gap-2 rounded-xl border border-edge bg-rise p-3 shadow-sm">
        <Link to={toImage} viewTransition onClick={() => roomNav(toImage)} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 transition-colors hover:border-image/60 hover:text-image">
          Image console
        </Link>
        <Link to={toVideo} viewTransition onClick={() => roomNav(toVideo)} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-video transition-colors hover:border-video/60">
          Video studio
        </Link>
        <Link to={toPublish} viewTransition onClick={() => roomNav(toPublish)} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground">
          Publish
        </Link>
        </div></details>
      </div>
    </motion.li>
  )
}

function Empty() {
  return (
    <section className="mt-12 max-w-xl rounded-xl border border-dashed border-edge-strong px-6 py-10">
      <p className="display text-[0.9375rem]">Your campaign directory is empty.</p>
      <p className="mt-2 text-[0.8125rem] leading-relaxed text-text-3">
        Open Chat, describe what you want to market, and it will turn the conversation into a campaign when you approve the brief.
      </p>
      <Link to="/chat" className="mt-5 inline-block text-[0.8125rem] text-foreground underline underline-offset-4">
        Open strategist
      </Link>
    </section>
  )
}
