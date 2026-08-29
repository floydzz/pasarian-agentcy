import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { api, ApiError } from '@/api/client'
import type { Campaign, Run } from '@/api/types'

const ACTIVE = new Set<Campaign['status']>(['planning', 'generating'])

const LABEL: Record<Campaign['status'], string> = {
  draft: 'Brief ready',
  planning: 'Planning concepts',
  pending_plan_approval: 'Waiting for your concept decision',
  generating: 'Generating creative work',
  pending_asset_review: 'Waiting for creative review',
  ready_to_publish: 'Ready for publishing',
  published: 'Published',
}

/** A durable, polling progress board. The work itself runs on the server; the
 * board reads campaign state and completed run records so people can change
 * pages, close a console, and come back to the truth rather than a spinner. */
export function Progress() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null)
  const [runs, setRuns] = useState<Run[]>([])
  const [updated, setUpdated] = useState<Date | null>(null)

  const refresh = useCallback(async () => {
    const [nextCampaigns, nextRuns] = await Promise.all([api.listCampaigns(), api.listRuns()])
    setCampaigns(nextCampaigns)
    setRuns(nextRuns)
    setUpdated(new Date())
  }, [])

  useEffect(() => {
    refresh().catch((error: ApiError) => toast.error(error.message))
    const timer = window.setInterval(() => refresh().catch(() => undefined), 8_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const active = useMemo(
    () => (campaigns ?? []).filter((campaign) => ACTIVE.has(campaign.status)),
    [campaigns],
  )
  const needsDecision = useMemo(
    () => (campaigns ?? []).filter((campaign) => campaign.status.startsWith('pending_')),
    [campaigns],
  )
  const latestRun = (campaignId: number) => runs.find((run) => run.campaign_id === campaignId)

  return (
    <Page>
      <PageHead
        title="Progress"
        action={<span className="data text-text-3">{updated ? `Updated ${updated.toLocaleTimeString()}` : 'Connecting…'}</span>}
      >
        Keep working elsewhere while Agentcy runs. This board refreshes automatically and brings you back to the exact campaign when a decision is due.
      </PageHead>

      {campaigns === null ? (
        <p className="mt-12 text-sm text-text-3">Checking the workspace…</p>
      ) : (
        <>
          <section className="mt-10 grid gap-3 sm:grid-cols-3">
            <Metric label="Working now" value={active.length} accent="text-video" />
            <Metric label="Needs your decision" value={needsDecision.length} accent="text-halt" />
            <Metric label="Campaigns" value={campaigns.length} accent="text-foreground" />
          </section>

          <section className="mt-12">
            <div className="flex items-baseline justify-between gap-4 border-b border-edge pb-3">
              <h2 className="display text-[1rem]">Campaign activity</h2>
              <button type="button" onClick={() => void refresh()} className="data text-text-3 hover:text-foreground">Refresh now</button>
            </div>
            {campaigns.length === 0 ? (
              <p className="mt-8 text-sm text-text-3">Nothing is running yet.</p>
            ) : (
              <ul className="divide-y divide-edge">
                {campaigns.map((campaign) => (
                  <ProgressRow key={campaign.id} campaign={campaign} run={latestRun(campaign.id)} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </Page>
  )
}

function Metric({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <article className="rounded-xl border border-edge bg-rise px-5 py-4">
      <p className="label">{label}</p>
      <p className={cn('display mt-2 text-2xl', accent)}>{value}</p>
    </article>
  )
}

function ProgressRow({ campaign, run }: { campaign: Campaign; run?: Run }) {
  const working = ACTIVE.has(campaign.status)
  const attention = campaign.status.startsWith('pending_')
  return (
    <li className="grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <p className="display text-[0.9375rem]">{campaign.name}</p>
          {working && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-video" />}
          <span className={cn('data', attention ? 'text-halt' : working ? 'text-video' : 'text-text-3')}>
            {LABEL[campaign.status]}
          </span>
        </div>
        <p className="mt-1 truncate text-[0.75rem] text-text-3">
          {run ? `${run.kind} · ${run.status} · ${run.summary}` : 'No completed run recorded yet.'}
        </p>
      </div>
      <div className="flex gap-2">
        <Link to={`/campaigns/${campaign.id}/image`} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 hover:border-edge-strong hover:text-foreground">
          Open console
        </Link>
        <Link to={`/campaigns/${campaign.id}/publish`} className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 hover:border-edge-strong hover:text-foreground">
          Publish
        </Link>
      </div>
    </li>
  )
}
