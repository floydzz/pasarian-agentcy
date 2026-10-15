import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { calendarApi, itemPayload } from '@/api/calendar'
import type { BusinessEvent, MarketingItem, MarketingPlan, PlanningPreferences, PlanningRequest } from '@/api/calendar'

export function Editor({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return <Dialog open onOpenChange={open => { if (!open) onClose() }}><DialogContent className="max-h-[88dvh] overflow-y-auto sm:max-w-xl"><DialogTitle className="pr-8 text-lg font-semibold">{title}</DialogTitle><DialogDescription className="sr-only">Edit your marketing calendar details. Changes are saved when you submit the form.</DialogDescription>{children}</DialogContent></Dialog>
}
const Field = ({ label, children }: { label: string; children: ReactNode }) => <label className="workspace-label">{label}{children}</label>

export function CalendarForm({ action, children, button = 'Save changes' }: { action: () => Promise<void>; children: ReactNode; button?: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await action() } catch (error) { setError((error as Error).message) } finally { setBusy(false) }
  }
  return <form onSubmit={submit} className="grid gap-4">{children}{error && <p role="alert" className="rounded-lg bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}<button className="workspace-button mt-1" disabled={busy}>{busy ? 'Saving…' : button}</button></form>
}

export function EventEditor({ date, event, onSaved }: { date: string; event?: BusinessEvent; onSaved: () => Promise<void> }) {
  const [draft, setDraft] = useState({ title: event?.title ?? '', start_date: event?.start_date ?? date, end_date: event?.end_date ?? date, description: event?.description ?? '', archived: event?.archived ?? false })
  return <CalendarForm action={async () => { if (event) await calendarApi.updateEvent({ ...draft, id: event.id, version: event.version }); else await calendarApi.addEvent(draft); await onSaved() }}>
    <Field label="Event name"><input className="workspace-input" required maxLength={200} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} placeholder="Product launch or store anniversary" /></Field>
    <div className="grid grid-cols-2 gap-3"><Field label="Start date"><input className="workspace-input" type="date" required value={draft.start_date} onChange={e => setDraft({ ...draft, start_date: e.target.value })} /></Field><Field label="End date"><input className="workspace-input" type="date" min={draft.start_date} required value={draft.end_date} onChange={e => setDraft({ ...draft, end_date: e.target.value })} /></Field></div>
    <Field label="What should the strategist know?"><textarea className="workspace-input" rows={3} maxLength={4000} value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} /></Field>
    {event && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.archived} onChange={e => setDraft({ ...draft, archived: e.target.checked })} />Archive event</label>}
  </CalendarForm>
}

export function PreferencesEditor({ initial, states, onSaved }: { initial: PlanningPreferences; states: Record<string, string>; onSaved: () => Promise<void> }) {
  const [draft, setDraft] = useState(initial)
  const [blackouts, setBlackouts] = useState(initial.blackout_dates.join(', '))
  return <CalendarForm action={async () => { await calendarApi.savePreferences({ ...draft, blackout_dates: blackouts.split(',').map(x => x.trim()).filter(Boolean) }); await onSaved() }}>
    <fieldset><legend className="mb-2 text-sm text-text-2">Target states</legend><div className="grid grid-cols-2 gap-2">{Object.entries(states).map(([code, name]) => <label className="flex items-center gap-2 text-xs" key={code}><input type="checkbox" checked={draft.states.includes(code)} onChange={e => setDraft({ ...draft, states: e.target.checked ? [...draft.states, code] : draft.states.filter(s => s !== code) })} />{name}</label>)}</div></fieldset>
    <Field label="Marketing goals"><textarea className="workspace-input" maxLength={2000} rows={2} value={draft.goals} onChange={e => setDraft({ ...draft, goals: e.target.value })} placeholder="Grow repeat orders and promote our gifting range" /></Field>
    <div className="grid grid-cols-2 gap-3"><Field label="Roadmap budget (MYR, optional)"><input className="workspace-input" type="number" min="0" max="1000000000" step="0.01" value={draft.annual_budget ?? ''} onChange={e => setDraft({ ...draft, annual_budget: e.target.value ? Number(e.target.value) : null })} /></Field><Field label="Maximum campaigns / month"><input className="workspace-input" type="number" min="1" max="10" required value={draft.campaigns_per_month} onChange={e => setDraft({ ...draft, campaigns_per_month: Number(e.target.value) })} /></Field></div>
    <div className="grid grid-cols-2 gap-3"><Field label="Preparation lead time (days)"><input className="workspace-input" type="number" min="1" max="90" required value={draft.lead_days} onChange={e => setDraft({ ...draft, lead_days: Number(e.target.value) })} /></Field><Field label="Remind me before (days)"><input className="workspace-input" type="number" min="1" max="30" required value={draft.reminder_days} onChange={e => setDraft({ ...draft, reminder_days: Number(e.target.value) })} /></Field></div>
    <Field label="Blackout dates (YYYY-MM-DD, separated by commas)"><input className="workspace-input" value={blackouts} onChange={e => setBlackouts(e.target.value)} placeholder="2027-01-15, 2027-02-01" /></Field>
    <p className="text-xs text-text-3">Dates use Malaysia time. Reminders appear in the app.</p>
  </CalendarForm>
}

export function PlanningEditor({ initial, onSubmit }: { initial: Omit<PlanningRequest, 'request_key'>; onSubmit: (request: PlanningRequest) => Promise<void> }) {
  const [draft, setDraft] = useState(initial)
  return <CalendarForm button="Prepare AI proposal" action={() => onSubmit({ ...draft, request_key: crypto.randomUUID() })}>
    {!draft.plan_id && draft.operation === 'annual' && <div className="flex flex-wrap gap-2">{[90, 365].map(days => <button type="button" key={days} className="workspace-secondary" onClick={() => { const start = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); const end = new Date(start + 'T12:00:00Z'); end.setUTCDate(end.getUTCDate() + days - 1); setDraft({ ...draft, start_date: start, end_date: end.toISOString().slice(0, 10) }) }}>{days === 90 ? 'Next 90 days' : 'Next 12 months'}</button>)}<button type="button" className="workspace-secondary" onClick={() => setDraft({ ...draft, start_date: initial.start_date.slice(0, 4) + '-01-01', end_date: initial.start_date.slice(0, 4) + '-12-31' })}>Calendar year</button></div>}
    <p className="text-sm leading-relaxed text-text-2">Get an editable roadmap grounded in your brand and verified occasions. Review the proposal before saving it. Campaign production starts separately.</p>
    <div className="grid grid-cols-2 gap-3"><Field label="Planning starts"><input type="date" className="workspace-input" required disabled={!!draft.plan_id} value={draft.start_date} onChange={e => setDraft({ ...draft, start_date: e.target.value })} /></Field><Field label="Planning ends"><input type="date" className="workspace-input" required disabled={!!draft.plan_id} min={draft.start_date} value={draft.end_date} onChange={e => setDraft({ ...draft, end_date: e.target.value })} /></Field></div>
    <Field label="What should this plan achieve?"><textarea className="workspace-input" rows={4} maxLength={4000} value={draft.instructions} onChange={e => setDraft({ ...draft, instructions: e.target.value })} placeholder="Prioritize gifting, customer retention and campaigns we can prepare with a small team." /></Field>
    <p className="text-xs text-text-3">Up to 24 ideas. Detailed preparation is focused on the next 90 days. Budget and capacity come from Planning preferences.</p>
  </CalendarForm>
}

export function PlanEditor({ plan, year, onSaved }: { plan?: MarketingPlan; year: number; onSaved: (plan: MarketingPlan) => Promise<void> }) {
  const [draft, setDraft] = useState({ name: plan?.name ?? `${year} marketing plan`, start_date: plan?.start_date ?? `${year}-01-01`, end_date: plan?.end_date ?? `${year}-12-31`, goals: plan?.goals ?? '', status: plan?.status ?? 'draft' })
  return <CalendarForm action={async () => { const saved = plan ? await calendarApi.updatePlan(plan.id, { ...draft, version: plan.version }) : await calendarApi.createPlan({ name: draft.name, start_date: draft.start_date, end_date: draft.end_date, goals: draft.goals }); await onSaved(saved) }}>
    <Field label="Plan name"><input className="workspace-input" required maxLength={200} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></Field>
    <div className="grid grid-cols-2 gap-3"><Field label="Starts"><input className="workspace-input" type="date" required value={draft.start_date} onChange={e => setDraft({ ...draft, start_date: e.target.value })} /></Field><Field label="Ends"><input className="workspace-input" type="date" required min={draft.start_date} value={draft.end_date} onChange={e => setDraft({ ...draft, end_date: e.target.value })} /></Field></div>
    <Field label="Goals"><textarea className="workspace-input" maxLength={2000} value={draft.goals} onChange={e => setDraft({ ...draft, goals: e.target.value })} /></Field>
    {plan && <Field label="Plan status"><select className="workspace-input" value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}><option value="draft">Draft</option><option value="accepted">Accepted</option><option value="archived">Archived</option></select></Field>}
  </CalendarForm>
}

export function ItemEditor({ plan, item, date, onSaved }: { plan: MarketingPlan; item?: MarketingItem; date: string; onSaved: (item: MarketingItem) => Promise<void> }) {
  const [draft, setDraft] = useState(item ? itemPayload(item) : { occasion_id: null, business_event_id: null, title: '', rationale: '', strategy: '', audience: '', products: [], offer: '', budget: null, campaign_start: date, campaign_end: date, preparation_start: date, status: 'proposed' as const, tasks: [] })
  return <CalendarForm action={async () => { await onSaved(item ? await calendarApi.updateItem(item.id, draft) : await calendarApi.addItem(plan, draft)) }}>
    {item?.campaign_id && <p className="text-sm text-halt">This updates the roadmap only. The production brief and approved creatives stay as saved.</p>}
    <Field label="Campaign idea"><input className="workspace-input" required maxLength={200} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></Field>
    <Field label="Strategy"><textarea className="workspace-input" required maxLength={4000} rows={3} value={draft.strategy} onChange={e => setDraft({ ...draft, strategy: e.target.value })} /></Field>
    <Field label="Why this campaign?"><textarea className="workspace-input" maxLength={2000} value={draft.rationale} onChange={e => setDraft({ ...draft, rationale: e.target.value })} /></Field>
    <Field label="Audience"><input className="workspace-input" maxLength={2000} value={draft.audience} onChange={e => setDraft({ ...draft, audience: e.target.value })} /></Field>
    <Field label="Proposed offer (requires business confirmation)"><input className="workspace-input" maxLength={1000} value={draft.offer} onChange={e => setDraft({ ...draft, offer: e.target.value })} /></Field>
    <div className="grid grid-cols-2 gap-3"><Field label="Campaign starts"><input className="workspace-input" type="date" required min={plan.start_date} max={plan.end_date} value={draft.campaign_start} onChange={e => setDraft({ ...draft, campaign_start: e.target.value })} /></Field><Field label="Campaign ends"><input className="workspace-input" type="date" required min={draft.campaign_start} max={plan.end_date} value={draft.campaign_end} onChange={e => setDraft({ ...draft, campaign_end: e.target.value })} /></Field></div>
    <div className="grid grid-cols-2 gap-3"><Field label="Preparation starts"><input className="workspace-input" type="date" required max={draft.campaign_start} value={draft.preparation_start} onChange={e => setDraft({ ...draft, preparation_start: e.target.value })} /></Field><Field label="Budget estimate (MYR)"><input className="workspace-input" type="number" min="0" max="1000000000" step=".01" value={draft.budget ?? ''} onChange={e => setDraft({ ...draft, budget: e.target.value ? Number(e.target.value) : null })} /></Field></div>
    <Field label="Planning status"><select className="workspace-input" value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value as MarketingItem['status'] })}><option value="proposed">Proposed</option><option value="planned">Accepted for planning</option><option value="skipped">Skip</option><option value="cancelled">Cancel</option></select></Field>
    {item?.source_changed && <p className="text-sm text-halt">Review the updated occasion dates before saving. Saving acknowledges the current source.</p>}
  </CalendarForm>
}


export function TaskEditor({ item, onSaved }: { item: MarketingItem; onSaved: () => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [due, setDue] = useState(item.campaign_start)
  return <CalendarForm action={async () => { await calendarApi.addTask(item.id, title, due); await onSaved() }}>
    <Field label="Preparation task"><input className="workspace-input" required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="Confirm stock or delivery cutoff" /></Field>
    <Field label="Due date"><input className="workspace-input" type="date" required min={item.preparation_start} max={item.campaign_end} value={due} onChange={e => setDue(e.target.value)} /></Field>
  </CalendarForm>
}
