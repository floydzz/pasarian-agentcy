import { useWorkspaceRefresh } from '@/hooks/useWorkspaceRefresh'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Page } from '@/components/os/Shell'
import { PlanningOverview } from '@/components/PlanningOverview'
import { request } from '@/api/client'
import { campaignFlow } from '@/lib/campaignFlow'
import type { CalendarAttention } from '@/api/calendar'
import type { Campaign } from '@/api/types'
import { calendarLocation, malaysiaToday, validCalendarDate } from '@/lib/marketingCalendar'
import { useAuth } from '@/lib/auth'

type Overview = { active_jobs: number; counts: Record<string, number>; needs_review: Campaign[]; recent: Campaign[]; attention: CalendarAttention[]; active_plans: number }
export function Dashboard() {
  const actor = useAuth()
  const [params] = useSearchParams()
  const today = malaysiaToday()
  const requestedDate = params.get('date')
  const date = validCalendarDate(requestedDate) ? requestedDate : today
  const canPlan = actor.role === 'owner' || actor.role === 'editor'
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useWorkspaceRefresh(() => setRetry(value => value + 1))
  useEffect(() => {
    const controller = new AbortController()
    request<Overview>('/workspace/overview', { signal: controller.signal }).then(value => { setData(value); setError('') }).catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
    return () => controller.abort()
  }, [retry])
  const reviewCount = (data?.counts.pending_plan_approval ?? 0) + (data?.counts.pending_asset_review ?? 0)
  const workingCount = data?.active_jobs ?? 0
  return <Page><header className="overview-page-heading"><div><p className="mb-2 text-xs text-text-3">{new Intl.DateTimeFormat('en-MY', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(today + 'T12:00:00Z'))}</p><h1 className="display-tight text-2xl font-semibold tracking-tight sm:text-3xl">Overview</h1><p className="mt-2 text-sm leading-relaxed text-text-2">See what’s coming. Make your next move.</p></div><Link to={calendarLocation(date, params.get('state') ?? '', null, canPlan)} className={canPlan ? 'workspace-button' : 'workspace-secondary'}>{canPlan && <Sparkles size={15} />}{canPlan ? 'Plan with AI' : 'Open calendar'}</Link></header>
    <nav aria-label="Workspace activity" className="overview-status-row">{data ? <>{[[`${reviewCount} awaiting review`, '/campaigns?filter=review'], [`${workingCount} active runs`, '/progress'], [`${data.active_plans} roadmaps`, '/calendar']].map(([label, to]) => <Link key={to} to={to} className="min-h-9 content-center text-xs text-text-2 hover:text-foreground">{label}</Link>)}</> : <p className="text-xs text-text-3" role="status">{error ? 'Workspace activity is unavailable.' : 'Loading workspace activity…'}</p>}</nav>
    <PlanningOverview key={`${actor.user.id}:${actor.workspace_id}`} />
    {error ? <div role="alert" className="mt-6 rounded-xl border border-halt/40 p-4 text-sm"><p>{error}</p><button className="workspace-secondary mt-3" onClick={() => setRetry(value => value + 1)}>Retry overview</button></div> : data && <>
      <section className="mt-7" aria-label="Campaign decisions"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-medium">Needs your decision <span className="ml-1 text-xs font-normal text-text-3">{reviewCount}</span></h2><Link to="/campaigns?filter=review" className="inline-flex min-h-10 items-center text-xs text-text-2 underline underline-offset-4">All reviews</Link></div><CampaignList rows={data.needs_review.slice(0, 2)} empty="No approvals are waiting for you." /></section>
      <div className="mt-5 grid gap-3"><details className="rounded-xl border border-edge px-4 py-3"><summary className="min-h-9 cursor-pointer content-center text-sm">Continue working</summary><CampaignList rows={data.recent} empty="Start in Chat with your marketing idea. Your saved campaigns will appear here." /><Link to="/campaigns" className="inline-flex min-h-10 items-center text-xs text-brand">All campaigns →</Link></details><details className="rounded-xl border border-edge px-4 py-3"><summary className="min-h-9 cursor-pointer content-center text-sm">Preparation reminders <span className="ml-1 text-xs text-text-3">{data.attention.length}</span></summary>{data.attention.length ? <ul className="mt-2 divide-y divide-edge">{data.attention.slice(0, 5).map(row => <li key={row.key} className="py-3"><p className="break-words text-sm">{row.title}</p>{row.due_date && <p className="mt-1 text-xs text-text-3">Due {row.due_date}</p>}<Link to={row.url} className="inline-flex min-h-10 items-center text-xs text-brand">{row.action} →</Link></li>)}</ul> : <p className="py-3 text-sm text-text-3">No reminders need attention.</p>}</details></div>
      <nav aria-label="Planning shortcuts" className="mt-6 flex flex-wrap gap-3"><Link className="workspace-secondary" to="/chat">Discuss an idea</Link><Link className="workspace-secondary" to="/calendar">Plan the year</Link><Link className="workspace-secondary" to="/progress">Check AI jobs</Link></nav>
    </>}
  </Page>
}
function CampaignList({ rows, empty }: { rows: Campaign[]; empty: string }) {
  return rows.length ? <ul className="mt-4 divide-y divide-edge">{rows.map(row => { const flow = campaignFlow(row); return <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div className="min-w-0 flex-[1_1_12rem]"><p className="break-words text-sm font-medium">{row.name}</p><p className="mt-1 text-xs leading-relaxed text-text-3">{flow.detail}</p></div><Link className="workspace-secondary" to={flow.to}>{flow.action} →</Link></li> })}</ul> : <p className="mt-4 text-sm leading-relaxed text-text-3">{empty}</p>
}
