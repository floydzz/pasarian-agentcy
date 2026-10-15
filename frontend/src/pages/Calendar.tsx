import { CalendarEntryDetails } from '@/components/CalendarEntryDetails'
import { useScrollMemory } from '@/hooks/useScrollMemory'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import listPlugin from '@fullcalendar/list'
import multiMonthPlugin from '@fullcalendar/multimonth'
import interactionPlugin from '@fullcalendar/interaction'
import type { DatesSetArg } from '@fullcalendar/core'
import { ArrowLeft, ArrowRight, Plus, SlidersHorizontal, Sparkles, X, Check, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import type { ReactNode } from 'react'
import { PageHead } from '@/components/os/Sidebar'
import { api } from '@/api/client'
import { calendarApi } from '@/api/calendar'
import type { BusinessEvent, CalendarAttention, CalendarEntry, CalendarResult, MarketingItem, MarketingPlan, Occasion, PlanningPreferences, PlanningRequest, PlanningRun, PlanningRunSummary } from '@/api/calendar'
import { streamRun } from '@/api/stream'
import { Editor, EventEditor, ItemEditor, PlanEditor, PlanningEditor, PreferencesEditor, TaskEditor } from './CalendarEditors'
import { calendarKinds as kinds, labelDate, linkedCalendarItems, malaysiaToday, shiftDay, validCalendarDate } from '@/lib/marketingCalendar'
type Mode = 'event' | 'preferences' | 'planning' | 'plan' | 'item' | 'task' | null

export function Calendar() {
  const scroll = useScrollMemory()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const dateParam = params.get('date'), entryParam = params.get('entry'), actionParam = params.get('action'), stateParam = params.get('state')
  const initialDate = validCalendarDate(dateParam) ? dateParam : malaysiaToday()
  const consumedIntent = useRef('')
  const loadedRange = useRef('')
  const requestedState = useRef(stateParam)
  const calendar = useRef<FullCalendar>(null)
  const dateDetails = useRef<HTMLElement>(null)
  const revealDate = useRef('')
  const [detailRequest, setDetailRequest] = useState(0)
  const initialLocation = useRef({ plan: params.get("plan"), item: params.get("item") })
  const [refreshKey, setRefreshKey] = useState(0)
  const running = useRef(new Set<number>())
  const currentRun = useRef<number | null>(null)
  const [data, setData] = useState<CalendarResult | null>(null)
  const [prefs, setPrefs] = useState<PlanningPreferences | null>(null)
  const [runHistory, setRunHistory] = useState<PlanningRunSummary[]>([])
  const [plans, setPlans] = useState<MarketingPlan[]>([])
  const [plan, setPlan] = useState<MarketingPlan | null>(null)
  const [notices, setNotices] = useState<CalendarAttention[]>([])
  const [state, setState] = useState(stateParam || 'SGR')
  const [types, setTypes] = useState<string[]>(Object.keys(kinds))
  const [range, setRange] = useState({ start: initialDate.slice(0, 7) + '-01', end: shiftDay(initialDate, 40) })
  const [title, setTitle] = useState('')
  const [year, setYear] = useState(Number(malaysiaToday().slice(0, 4)))
  const [view, setView] = useState('dayGridMonth')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selected, setSelected] = useState<CalendarEntry | null>(null)
  const [selectedDate, setSelectedDate] = useState(initialDate)
  const [item, setItem] = useState<MarketingItem | null>(null)
  const [mode, setMode] = useState<Mode>(null)
  const [request, setRequest] = useState<Omit<PlanningRequest, 'request_key'>>({ operation: 'annual', start_date: malaysiaToday(), end_date: shiftDay(malaysiaToday(), 364), instructions: '' })
  const [run, setRun] = useState<PlanningRun | null>(null)
  const [progress, setProgress] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [brandMissing, setBrandMissing] = useState(false)

  const refresh = useCallback(async () => {
    const [list, reminders, history] = await Promise.all([calendarApi.plans(), calendarApi.attention(), calendarApi.runs()])
    setPlans(list); setNotices(reminders); setRunHistory(history); setRefreshKey(value => value + 1)
  }, [setPlans, setNotices, setRunHistory, setRefreshKey])
  useEffect(() => { let current = true; setLoading(true); calendarApi.entries(range.start, range.end, state, types, { includeLinks: true }).then(result => { if (current) { loadedRange.current = `${range.start}:${range.end}:${state}`; setData(result); setError('') } }).catch(e => { if (current) setError(e.message) }).finally(() => { if (current) setLoading(false) }); return () => { current = false } }, [range.start, range.end, state, types, refreshKey])
  useEffect(() => {
    let current = true
    Promise.all([calendarApi.preferences(), calendarApi.plans(), calendarApi.attention(), api.getBrandProfile(), calendarApi.runs()]).then(([preferences, list, reminders, brand, history]) => { if (!current) return; setPrefs(preferences); setState(requestedState.current || preferences.states[0]); setPlans(list); setNotices(reminders); setRunHistory(history); setBrandMissing(!brand.company_name) }).catch(e => { if (current) setError(e.message) })
    return () => { current = false }
  }, [])
  useEffect(() => { requestedState.current = stateParam; if (stateParam) setState(stateParam) }, [stateParam])
  useEffect(() => { if (validCalendarDate(dateParam)) { setSelectedDate(dateParam); calendar.current?.getApi().gotoDate(dateParam) } }, [dateParam])
  const planParam = params.get('plan'), itemParam = params.get('item'), runParam = params.get('run')
  useEffect(() => {
    if (planParam && Number(planParam) > 0) calendarApi.plan(Number(planParam)).then(saved => { setPlan(saved); if (initialLocation.current.plan === planParam && !initialLocation.current.item) { calendar.current?.getApi().gotoDate(saved.start_date); initialLocation.current = { plan: null, item: null } } }).catch(e => setError(e.message))
    else setPlan(null)
  }, [planParam])
  useEffect(() => {
    if (!itemParam) return
    calendarApi.item(Number(itemParam)).then(saved => { const focus = validCalendarDate(dateParam) && dateParam >= saved.preparation_start && dateParam <= saved.campaign_end ? dateParam : saved.campaign_start; setItem(saved); setSelected(null); setSelectedDate(focus); calendar.current?.getApi().gotoDate(focus); return calendarApi.plan(saved.plan_id) }).then(setPlan).catch(e => setError(e.message))
  }, [itemParam, dateParam])

  const processRun = useCallback(async (saved: PlanningRun) => {
    currentRun.current = saved.id
    setRun(saved)
    if (saved.status !== 'pending' || running.current.has(saved.id)) return
    running.current.add(saved.id); setBusy(true); setProgress('Preparing your marketing proposal…')
    try {
      let failure = ''
      await streamRun(`/calendar/runs/${saved.id}/stream`, line => {
        if (line.kind === 'event') setProgress(line.detail)
        else if (line.kind === 'error') failure = line.detail
        else if (line.kind === 'result' && currentRun.current === saved.id) setRun(line.run as PlanningRun)
      })
      const latest = await calendarApi.run(saved.id); if (currentRun.current === saved.id) setRun(latest)
      if (failure && latest.status !== 'succeeded') setError(failure)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false); setProgress('') }
  }, [])
  useEffect(() => {
    if (!runParam || Number(runParam) < 1) return
    calendarApi.run(Number(runParam)).then(saved => void processRun(saved)).catch(e => setError(e.message))
  }, [runParam, processRun])
  useEffect(() => {
    if (run?.status !== 'running') return
    const timer = window.setInterval(() => { calendarApi.run(run.id).then(setRun).catch(e => setError(e.message)) }, 3000)
    return () => window.clearInterval(timer)
  }, [run?.id, run?.status])

  async function act(work: () => Promise<void>) {
    if (busy) return
    setBusy(true); setError('')
    try { await work() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  function selectEntry(entry: CalendarEntry) {
    setSelectedDate(entry.start_date)
    if (entry.kind === 'plan' || entry.kind === 'task') {
      setParams({ item: String(entry.entity_id) })
    } else { setSelected(entry); setItem(null); setParams(plan ? { plan: String(plan.id) } : {}) }
  }
  function selectDate(value: string) {
    setSelectedDate(value); setSelected(null); setItem(null); setParams(plan ? { plan: String(plan.id) } : {})
    if (calendar.current?.getApi().view.type === 'multiMonthYear') { calendar.current.getApi().changeView('dayGridMonth', value); setView('dayGridMonth') }
    revealDate.current = value; setDetailRequest(request => request + 1)
  }
  useEffect(() => {
    if (!detailRequest || revealDate.current !== selectedDate || params.get('date') || params.get('entry') || itemParam) return
    const frame = requestAnimationFrame(() => {
      revealDate.current = ''
      dateDetails.current?.focus({ preventScroll: true })
      dateDetails.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
    })
    return () => cancelAnimationFrame(frame)
  }, [selectedDate, params, itemParam, detailRequest])
  function datesChanged(arg: DatesSetArg) { setTitle(arg.view.title); setYear(arg.view.currentStart.getFullYear()); setRange({ start: arg.startStr.slice(0, 10), end: shiftDay(arg.endStr.slice(0, 10), -1) }) }
  async function askStrategist() {
    await act(async () => {
      const savedItem = item ?? (sourceItems.length === 1 ? sourceItems[0] : null)
      const context = savedItem ? { marketing_plan_id: savedItem.plan_id, marketing_plan_item_id: savedItem.id, campaign_id: savedItem.campaign_id ?? undefined } : selected ? selected.kind === 'business' ? { calendar_business_event_id: selected.entity_id } : { calendar_occasion_id: selected.entity_id } : plan ? { marketing_plan_id: plan.id } : {}
      const thread = await api.createConversation({ title: item?.title ?? selected?.title ?? plan?.name ?? 'Calendar strategy', ...context })
      navigate(`/chat?thread=${thread.id}`)
    })
  }
  function openPlanning(scope: 'annual' | 'item' = 'annual') {
    let start = scope === 'annual' && view !== 'multiMonthYear' ? malaysiaToday() : `${year}-01-01`
    let end = scope === 'annual' && view !== 'multiMonthYear' ? shiftDay(start, 364) : `${year}-12-31`
    if (plan && scope === 'item' && item) { start = plan.start_date; end = plan.end_date }
    setRequest({ states: [state], operation: scope, start_date: start, end_date: end, instructions: '', ...(scope === 'item' && item ? { plan_id: item.plan_id, item_id: item.id } : scope === 'item' && selected ? selected.kind === 'business' ? { business_event_id: selected.entity_id } : { occasion_id: selected.entity_id } : {}) })
    setMode('planning')
  }
  const visibleDates = data?.entries.filter(entry => entry.start_date <= selectedDate && entry.end_date >= selectedDate) ?? []
  const activeYearCoverage = data?.coverage[String(year)]?.categories ?? []
  const selectedEvent = selected?.kind === 'business' ? selected.details as BusinessEvent : undefined
  const occasion = selected && selected.kind !== 'business' ? selected.details as Occasion : undefined
  const sourceItems = linkedCalendarItems(selected, data?.linked_items ?? [])
  // Overview selects the same date/source before opening the existing form.
  // Resolving a link never starts a run or creates a campaign.
  useEffect(() => {
    if ((!dateParam && !entryParam && !actionParam) || !data || loading || !prefs || itemParam || loadedRange.current !== `${range.start}:${range.end}:${state}`) return
    const key = `${dateParam}|${entryParam}|${actionParam}|${stateParam}`
    if (consumedIntent.current === key) return
    const date = validCalendarDate(dateParam) ? dateParam : malaysiaToday()
    const entry = entryParam ? data.entries.find(row => row.id === entryParam && row.start_date <= date && row.end_date >= date) : null
    consumedIntent.current = key
    if (entryParam && !entry) { setError('This calendar activity is no longer available for the selected date or state.'); return }
    setSelectedDate(date); setSelected(entry ?? null); setItem(null)
    const existing = linkedCalendarItems(entry ?? null, data.linked_items ?? [])
    if (actionParam === 'plan' && !existing.length) {
      if (entry && !['business', 'plan', 'task'].includes(entry.kind) && (entry.details as Occasion).publication_status === 'withdrawn') { setError('This occasion has been withdrawn. Choose another event.'); return }
      const start = entry ? date.slice(0, 4) + '-01-01' : date
      setRequest({ states: [state], operation: entry ? 'item' : 'annual', start_date: start, end_date: entry ? date.slice(0, 4) + '-12-31' : shiftDay(start, 364), instructions: entry ? '' : `Start with marketing opportunities around ${labelDate(date)}.`, ...(entry ? entry.kind === 'business' ? { business_event_id: entry.entity_id } : { occasion_id: entry.entity_id } : {}) })
      setMode('planning')
    }
    if (actionParam) {
      const clean = new URLSearchParams(params); clean.delete('action')
      consumedIntent.current = `${dateParam}|${entryParam}|null|${stateParam}`
      setParams(clean, { replace: true })
    }
  }, [dateParam, entryParam, actionParam, stateParam, data, loading, prefs, itemParam, state, range.start, range.end, params, setParams])

  return (
    <div ref={scroll} className="quiet-scroll h-full overflow-y-auto px-4 py-7 sm:px-8 lg:px-10">
      <div className="mx-auto max-w-[1500px]">
        <PageHead title="Marketing calendar" action={<div className="flex flex-wrap gap-2"><button className="workspace-secondary" onClick={() => { setSelected(null); setMode('event') }}><Plus size={15} />Add event</button><button className="workspace-button" onClick={() => openPlanning()}><Sparkles size={15} />Plan with AI</button></div>}><span className="hidden sm:inline">Make room for the right moments. Plan your year, prepare campaigns, and keep track of what comes next.</span><span className="sm:hidden">Plan the right moments.</span></PageHead>
        {error && <div role="alert" className="mt-5 flex items-start justify-between gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={17} /></button></div>}
        {brandMissing && <p className="mt-5 rounded-xl bg-accent p-4 text-sm text-primary">Add your products, audience and restrictions in <Link to="/brand" className="font-semibold underline">Brand</Link> to get useful marketing recommendations.</p>}
        {notices.length > 0 && <details className="mt-5 rounded-xl border border-edge bg-rise px-4 py-3"><summary className="cursor-pointer text-sm font-medium text-halt">{notices.length} {notices.length === 1 ? 'item needs' : 'items need'} attention</summary><div className="mt-3 grid gap-2">{notices.slice(0, 8).map(n => <div key={n.key} className="flex flex-wrap items-center justify-between gap-2 border-t border-edge py-2 text-sm"><span>{n.title}{n.due_date ? ` · ${labelDate(n.due_date)}` : ''}</span><div className="flex gap-3"><Link to={n.url} className="font-medium text-primary">{n.action}</Link><button disabled={busy} onClick={() => void act(async () => { await calendarApi.snooze(n.key, shiftDay(malaysiaToday(), 7)); await refresh() })} className="text-xs text-text-3">Snooze 7 days</button></div></div>)}</div></details>}

        <div className="mt-7 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2"><button className="calendar-nav-control" aria-label="Previous calendar period" onClick={() => calendar.current?.getApi().prev()}><ArrowLeft size={16} /></button><button className="calendar-nav-control" aria-label="Next calendar period" onClick={() => calendar.current?.getApi().next()}><ArrowRight size={16} /></button><button className="calendar-today-control" onClick={() => calendar.current?.getApi().gotoDate(malaysiaToday())}>Today</button><h2 className="ml-0 text-[.9375rem] font-semibold tracking-tight sm:ml-3 sm:text-lg">{title}</h2></div>
          <div className="flex flex-wrap items-center gap-2"><div className="flex rounded-lg border border-edge bg-rise p-1" aria-label="Calendar view">{[['dayGridMonth', 'Month'], ['multiMonthYear', 'Year'], ['listMonth', 'Agenda']].map(([value, label]) => <button key={value} aria-pressed={view === value} className={`rounded-md px-3 py-1.5 text-xs ${view === value ? 'bg-accent font-medium text-primary' : 'text-text-2'}`} onClick={() => { calendar.current?.getApi().changeView(value); setView(value) }}>{label}</button>)}</div><button className="workspace-secondary px-3" aria-label="Planning preferences" title="Planning preferences" onClick={() => setMode('preferences')}><SlidersHorizontal size={16} /></button></div>
        </div>
        <button type="button" className="mt-3 flex items-center gap-2 text-xs text-text-2 sm:hidden" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(!filtersOpen)}><SlidersHorizontal size={13} />Filters · {data?.states[state] ?? state}</button>
        <div className={`${filtersOpen ? 'flex' : 'hidden sm:flex'} mt-4 flex-wrap items-center gap-x-5 gap-y-3 text-xs`}>
          <label className="flex items-center gap-2 text-text-2">State<select aria-label="Filter calendar by Malaysian state" className="rounded-lg border border-edge bg-rise px-3 py-2 text-foreground" value={state} onChange={e => setState(e.target.value)}>{Object.entries(data?.states ?? { SGR: 'Selangor' }).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label>
          {Object.entries(kinds).filter(([kind]) => !['festival', 'commercial'].includes(kind)).map(([kind, spec]) => <label key={kind} className="flex items-center gap-1.5 text-text-2"><input type="checkbox" checked={types.includes(kind)} onChange={e => { setTypes(e.target.checked ? [...types, kind] : types.filter(k => k !== kind)) }} /><span style={{ backgroundColor: spec.color }} className="h-1.5 w-1.5 rounded-full" />{spec.label}</label>)}
        </div>

        <div className={`mt-4 grid items-start gap-5 ${selected || item ? 'xl:grid-cols-[minmax(0,1fr)_21rem]' : ''}`}>
          <section aria-label="Interactive marketing calendar" aria-busy={loading} className="calendar-surface min-w-0 overflow-hidden rounded-2xl border border-edge bg-rise p-2 sm:p-4">
            <FullCalendar ref={calendar} plugins={[dayGridPlugin, listPlugin, multiMonthPlugin, interactionPlugin]} initialView="dayGridMonth" initialDate={initialDate} headerToolbar={false} height="auto" firstDay={1} fixedWeekCount={false} dayMaxEvents={3} displayEventTime={false} eventDisplay="block" navLinks navLinkDayClick={date => selectDate(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`)} multiMonthMaxColumns={3} multiMonthMinWidth={220} datesSet={datesChanged} dateClick={arg => selectDate(arg.dateStr)} eventClick={arg => { const entry = data?.entries.find(e => e.id === arg.event.id); if (entry) selectEntry(entry) }} eventDidMount={arg => { arg.el.setAttribute('aria-label', `${arg.event.extendedProps.kind}: ${arg.event.title}`); arg.el.setAttribute('tabindex', '0'); arg.el.setAttribute('role', 'button'); arg.el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); const entry = data?.entries.find(row => row.id === arg.event.id); if (entry) selectEntry(entry) } }) }} events={(data?.entries ?? []).map(entry => ({ id: entry.id, title: view === 'listMonth' && entry.end_date !== entry.start_date ? `${entry.title} · through ${labelDate(entry.end_date)}` : entry.title, start: view === 'listMonth' && entry.start_date < range.start ? range.start : entry.start_date, end: shiftDay(view === 'listMonth' ? (entry.start_date < range.start ? range.start : entry.start_date) : entry.end_date, 1), allDay: true, backgroundColor: kinds[entry.kind].color + '12', borderColor: kinds[entry.kind].color + '35', textColor: kinds[entry.kind].color, extendedProps: { kind: kinds[entry.kind].label } }))} noEventsContent="No calendar entries in this period." />
            <p className="mt-4 border-t border-edge pt-3 text-[.6875rem] leading-relaxed text-text-3">{loading ? 'Updating calendar…' : `${data?.entries.length ?? 0} entries shown`} · Malaysia time · Published dates may change. Observed replacements and special declarations are imported when verified.</p>
            {!activeYearCoverage.includes('holiday') && !loading && <p className="mt-2 text-xs text-halt">Verified public-holiday coverage is unavailable for {year}. You can still plan custom business events.</p>}
          </section>

          {(selected || item) && !mode && !run && <DetailPanel onClose={() => { setSelected(null); setItem(null); setParams({}) }}>
            <div className="mb-4 flex justify-between"><span className="text-xs font-medium text-primary">{item ? 'Marketing plan' : selected ? kinds[selected.kind].label : ''}</span><button aria-label="Close event details" onClick={() => { setSelected(null); setItem(null); setParams({}) }}><X size={17} /></button></div>
            <h3 className="text-xl font-semibold tracking-tight">{item?.title ?? selected?.title}</h3>
            <p className="mt-2 text-xs text-text-3">{labelDate(item?.campaign_start ?? selected!.start_date)}{(item?.campaign_end ?? selected!.end_date) !== (item?.campaign_start ?? selected!.start_date) && ` – ${labelDate(item?.campaign_end ?? selected!.end_date)}`}</p>
            {occasion && <><p className="mt-4 text-sm text-text-2">{occasion.publication_status === 'tentative' ? 'Published date · subject to change' : occasion.publication_status === 'withdrawn' ? 'Withdrawn · review your plan' : 'Published official date'}</p><p className="mt-2 text-xs leading-relaxed text-text-3">Applies in {occasion.states.map(code => data?.states[code] ?? code).join(', ')}.</p><a href={occasion.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-primary">Official source <ExternalLink size={12} /></a><p className="mt-1 text-[.6875rem] text-text-3">Verified {occasion.verified_at}</p></>}
            {selectedEvent && <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-text-2">{selectedEvent.description || 'Add business details to help plan this event.'}</p>}
            {item && <><p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-text-2">{item.strategy}</p><p className="mt-3 text-xs leading-relaxed text-text-3">{item.rationale}</p>{item.source_changed && <p role="status" className="mt-3 rounded-lg bg-halt/10 p-3 text-xs text-halt">The occasion changed. Previously {item.source_snapshot.start_date ?? 'unspecified'}; now {item.current_source_snapshot.start_date ?? item.current_source_snapshot.publication_status}. Review and save the item before creating a campaign.</p>}<dl className="mt-4 grid gap-2 text-xs"><div><dt className="text-text-3">Preparation starts</dt><dd className="mt-1">{labelDate(item.preparation_start)}</dd></div><div><dt className="text-text-3">Budget estimate</dt><dd className="mt-1">{item.budget === null ? 'Not provided' : `MYR ${item.budget.toLocaleString('en-MY')}`}</dd></div><div><dt className="text-text-3">Status</dt><dd className="mt-1">{item.status}{item.campaign_status ? ` · ${item.campaign_status.replaceAll('_', ' ')}` : ''}</dd></div></dl>
              <div className="mt-5 space-y-3">{item.tasks.map(task => <div key={task.id} className="flex items-start gap-2 text-xs"><input type="checkbox" aria-label={`Complete ${task.title}`} checked={task.status === 'done'} disabled={busy} onChange={() => void act(async () => { await calendarApi.task(task, task.status === 'done' ? 'todo' : 'done'); setItem(await calendarApi.item(item.id)); await refresh() })} /><div className="min-w-0 flex-1"><p className={task.status === 'done' ? 'text-text-3 line-through' : ''}>{task.title}</p><input aria-label={`Due date for ${task.title}`} className="mt-1 max-w-full rounded border border-edge px-1 py-1 text-[.6875rem] text-text-3" type="date" value={task.due_date} disabled={busy} onChange={e => { const date = e.target.value; if (date) void act(async () => { await calendarApi.task(task, task.status, date); setItem(await calendarApi.item(item.id)); await refresh() }) }} /></div></div>)}</div></>}
            <div className="mt-5 grid gap-2">
              {sourceItems.length ? sourceItems.map(saved => <Link key={saved.id} className="workspace-button" to={saved.campaign_id && !saved.source_changed ? `/campaigns/${saved.campaign_id}` : `/calendar?item=${saved.id}`}>{saved.source_changed ? "Review calendar changes" : saved.campaign_id ? "Continue campaign" : "Review calendar plan"}{sourceItems.length > 1 ? `: ${saved.title}` : ""}</Link>) : item?.campaign_id ? <Link className="workspace-button" to={`/campaigns/${item.campaign_id}`}>Open campaign</Link> : item ? <button className="workspace-button" disabled={busy || item.status !== 'planned' || item.source_changed} onClick={() => void act(async () => { const result = await calendarApi.createCampaign(item); navigate(`/campaigns/${result.campaign_id}`) })}>Create campaign</button> : <button className="workspace-button" disabled={busy || occasion?.publication_status === 'withdrawn'} onClick={() => openPlanning('item')}>Plan this occasion</button>}
              <button className="workspace-secondary" disabled={busy} onClick={() => void askStrategist()}>Discuss with strategist</button>
              {item && <button className="text-xs text-primary" onClick={() => setMode('task')}>Add preparation task</button>}
              {item && <button className="workspace-secondary" onClick={() => setMode('item')}>Edit plan item</button>}
              {item && !item.campaign_id && <button className="text-xs text-primary" onClick={() => openPlanning('item')}>Prepare detailed strategy and tasks</button>}
              {selectedEvent && <button className="workspace-secondary" onClick={() => setMode('event')}>Edit business event</button>}
            </div>
          </DetailPanel>}
        </div>

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <section className="rounded-2xl border border-edge bg-rise p-5"><div className="flex items-center justify-between gap-3"><h3 className="font-medium">Your roadmaps</h3><button className="text-xs font-medium text-primary" onClick={() => { setPlan(null); setMode('plan') }}>Create manually</button></div><p className="mt-1 text-xs text-text-3">Review a year of ideas, then produce one campaign at a time.</p><div className="mt-4 space-y-2">{plans.filter(p => p.status !== 'archived').length === 0 ? <p className="py-3 text-sm text-text-3">Start with an AI proposal or create your first plan.</p> : plans.filter(p => p.status !== 'archived').map(p => <button className={`flex w-full items-center justify-between rounded-lg p-3 text-left text-sm ${plan?.id === p.id ? 'bg-accent text-primary' : 'bg-void text-text-2'}`} key={p.id} onClick={() => { setItem(null); setSelected(null); setParams({ plan: String(p.id) }); calendar.current?.getApi().gotoDate(p.start_date) }}><span>{p.name}<span className="mt-1 block text-[.6875rem] text-text-3">{labelDate(p.start_date)} – {labelDate(p.end_date)}</span></span><ArrowRight size={15} /></button>)}</div>{plan && <div className="mt-4 border-t border-edge pt-4"><div className="flex flex-wrap gap-3"><button className="text-xs font-medium text-primary" onClick={() => { setItem(null); setMode('item') }}>Add campaign idea</button><button className="text-xs text-text-2" onClick={() => setMode('plan')}>Edit roadmap</button><button className="text-xs text-text-2" onClick={() => void askStrategist()}>Discuss plan</button></div><ul className="mt-3 divide-y divide-edge">{plan.items?.map(i => <li key={i.id}><button className="flex w-full justify-between gap-3 py-3 text-left text-xs" onClick={() => setParams({ item: String(i.id) })}><span>{i.title}</span><span className="shrink-0 text-text-3">{i.campaign_start}</span></button></li>)}</ul></div>}<details className="mt-4 border-t border-edge pt-3"><summary className="cursor-pointer text-xs text-primary">Recent planning requests</summary><div className="mt-2 space-y-1">{runHistory.length === 0 && <p className="py-2 text-xs text-text-3">No planning requests yet.</p>}{runHistory.slice(0, 8).map(r => <button className="flex w-full justify-between gap-3 rounded-lg p-2 text-left text-xs hover:bg-void" key={r.id} onClick={() => setParams({ run: String(r.id) })}><span>{r.period}</span><span className="shrink-0 text-text-3">{r.accepted ? 'Saved' : r.status === 'succeeded' ? 'Ready to review' : r.status}</span></button>)}</div></details></section>
          <section ref={dateDetails} tabIndex={-1} aria-label="Selected date activities" className="rounded-2xl border border-edge bg-rise p-5"><h3 className="font-medium">{labelDate(selectedDate)}</h3><div className="mt-3 space-y-2">{visibleDates.length === 0 ? <p className="text-sm text-text-3">A clear day. Add an event or leave room between campaigns.</p> : visibleDates.map(e => <article key={e.id} className="border-t border-edge py-4"><button className="flex min-h-11 w-full items-center gap-3 text-left text-base font-medium leading-relaxed" onClick={() => selectEntry(e)}><span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: kinds[e.kind].color }} /><span><span>{e.title}</span><span className="mt-1 block text-[.6875rem] text-text-3">{kinds[e.kind].label}</span></span></button><div className="mt-3"><CalendarEntryDetails entry={e} states={data?.states} /></div></article>)}</div><button className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-primary" onClick={() => { setSelected(null); setMode('event') }}><Plus size={13} />Add event on this date</button></section>
        </div>
      </div>

      {mode === 'event' && <Editor title={selectedEvent ? 'Edit business event' : 'Add business event'} onClose={() => setMode(null)}><EventEditor date={selectedDate} event={selectedEvent} onSaved={async () => { setMode(null); setSelected(null); await refresh() }} /></Editor>}
      {mode === 'preferences' && prefs && data && <Editor title="Planning preferences" onClose={() => setMode(null)}><PreferencesEditor initial={prefs} states={data.states} onSaved={async () => { const updated = await calendarApi.preferences(); setPrefs(updated); setState(updated.states[0]); setMode(null); await refresh() }} /></Editor>}
      {mode === 'planning' && <Editor title={request.operation === 'annual' ? 'Plan your marketing year' : 'Plan this occasion'} onClose={() => setMode(null)}><PlanningEditor initial={request} onSubmit={async payload => { const saved = await calendarApi.newRun(payload); setMode(null); setParams({ run: String(saved.id) }); await processRun(saved); setRunHistory(await calendarApi.runs()) }} /></Editor>}
      {mode === 'plan' && <Editor title={plan ? 'Edit roadmap' : 'Create a roadmap'} onClose={() => setMode(null)}><PlanEditor plan={plan ?? undefined} year={year} onSaved={async saved => { setPlan(saved); setMode(null); setParams(saved.status === 'archived' ? {} : { plan: String(saved.id) }); await refresh() }} /></Editor>}
      {mode === 'task' && item && <Editor title="Add preparation task" onClose={() => setMode(null)}><TaskEditor item={item} onSaved={async () => { setItem(await calendarApi.item(item.id)); setMode(null); await refresh() }} /></Editor>}
      {mode === 'item' && plan && <Editor title={item ? 'Edit campaign idea' : 'Add campaign idea'} onClose={() => setMode(null)}><ItemEditor plan={plan} item={item ?? undefined} date={selectedDate < plan.start_date || selectedDate > plan.end_date ? plan.start_date : selectedDate} onSaved={async saved => { setItem(saved); setPlan(await calendarApi.plan(saved.plan_id)); setMode(null); setParams({ item: String(saved.id) }); await refresh() }} /></Editor>}
      {run && <Editor title="Your AI calendar proposal" onClose={() => { currentRun.current = null; setRun(null); setParams({}) }}><div aria-live="polite" className="space-y-4">
        {(busy || run.status === 'running' || run.status === 'pending') && <p className="rounded-xl bg-accent p-4 text-sm text-primary">{progress || 'Planning is in progress. You can reopen this saved request.'}</p>}
        {(run.status === 'failed' || run.status === 'interrupted') && <div role="alert"><p className="text-sm text-destructive">{run.error || error}</p><button className="workspace-secondary mt-3" onClick={() => void act(async () => { const fresh = await calendarApi.newRun({ ...run.input.request, request_key: crypto.randomUUID() }); setParams({ run: String(fresh.id) }); setRun(fresh) })}>Retry with current inputs</button></div>}
        {run.input.request.item_id && <p className="rounded-lg bg-void p-3 text-xs text-text-3">Completed and manually dated tasks stay as saved. Pending generated tasks follow the campaign schedule, and new tasks are added.</p>}
        {run.proposal && <><p className="text-sm leading-relaxed text-text-2">{run.proposal.summary}</p><div className="divide-y divide-edge">{run.proposal.items.map((draft, index) => <div key={index} className="py-3"><p className="text-sm font-medium">{draft.title}</p><p className="mt-1 text-xs text-text-3">{labelDate(draft.campaign_start)} – {labelDate(draft.campaign_end)} · {draft.budget === null ? 'Budget not provided' : `MYR ${draft.budget}`}</p><p className="mt-2 text-xs leading-relaxed text-text-2">{draft.rationale}</p><details className="mt-2 text-xs"><summary className="cursor-pointer text-primary">Strategy and preparation</summary><p className="mt-2 whitespace-pre-wrap leading-relaxed text-text-2">{draft.strategy}</p>{draft.tasks.map((task, n) => <p key={n} className="mt-2 text-text-3">{task.due_date} · {task.title}</p>)}</details></div>)}</div>{run.proposal.assumptions.length > 0 && <div className="rounded-lg bg-void p-3 text-xs text-text-3">{run.proposal.assumptions.map((a, i) => <p key={i} className="mb-1">{a}</p>)}</div>}
          {run.accepted ? <p className="flex items-center gap-2 text-sm text-primary"><Check size={16} />Saved to your calendar <Link to={`/calendar?plan=${run.accepted_plan_id}`} className="ml-2 underline" onClick={() => { currentRun.current = null; setRun(null) }}>Open roadmap</Link></p> : <><button className="workspace-button w-full" disabled={busy} onClick={() => void act(async () => { const saved = await calendarApi.accept(run, `${run.input.request.start_date.slice(0, 4)} marketing roadmap`); setPlan(saved); setRun(null); setSelected(null); const focus = saved.items?.find(i => i.id === run.input.request.item_id) ?? saved.items?.[0]; setItem(focus ?? null); setParams(focus ? { plan: String(saved.id), item: String(focus.id) } : { plan: String(saved.id) }); calendar.current?.getApi().gotoDate(focus?.campaign_start ?? saved.start_date); await refresh(); toast.success('Marketing plan saved. Select an idea when you are ready to create its campaign.') })}>Accept and save to calendar</button><p className="text-xs text-text-3">You can edit or skip each saved idea before creating a campaign.</p></>}
        </>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <details className="text-xs text-text-3"><summary className="cursor-pointer">Planning activity</summary>{run.events.map((event, i) => <p key={i} className="mt-2">{event.agent} · {event.detail}</p>)}{run.elapsed_ms !== null && <p className="mt-2">{(run.elapsed_ms / 1000).toFixed(1)}s · request {run.id}</p>}</details>
      </div></Editor>}
    </div>
  )
}


function DetailPanel({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const [wide, setWide] = useState(() => window.matchMedia('(min-width: 1280px)').matches)
  useEffect(() => { const media = window.matchMedia('(min-width: 1280px)'); const update = () => setWide(media.matches); media.addEventListener('change', update); return () => media.removeEventListener('change', update) }, [])
  if (wide) return <aside aria-label="Selected event details" className="sticky top-4 rounded-2xl border border-edge bg-rise p-5">{children}</aside>
  return <Dialog open onOpenChange={open => { if (!open) onClose() }}><DialogContent showCloseButton={false} className="top-auto bottom-3 max-h-[85dvh] -translate-y-0 overflow-y-auto sm:max-w-lg"><DialogTitle className="sr-only">Selected event details</DialogTitle><DialogDescription className="sr-only">Review the event, plan its campaign or update preparation tasks.</DialogDescription>{children}</DialogContent></Dialog>
}
