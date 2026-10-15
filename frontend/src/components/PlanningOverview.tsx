import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin from '@fullcalendar/interaction'
import { ArrowLeft, ArrowRight, ArrowUpRight, MessageSquare } from 'lucide-react'
import { api } from '@/api/client'
import { calendarApi } from '@/api/calendar'
import type { CalendarEntry, CalendarItemLink, CalendarResult, MarketingTask, Occasion, PlanningPreferences } from '@/api/calendar'
import { calendarKinds, calendarLocation, labelDate, linkedCalendarItems, malaysiaToday, shiftDay, validCalendarDate } from '@/lib/marketingCalendar'
import { useAuth } from '@/lib/auth'
import { CalendarEntryDetails } from '@/components/CalendarEntryDetails'
import { useWorkspaceRefresh } from '@/hooks/useWorkspaceRefresh'

const overviewTypes = ['holiday', 'festival', 'commercial', 'business', 'plan', 'task']
const available = (entry: CalendarEntry) => entry.kind !== 'task' || (entry.details as MarketingTask).status !== 'done'
const dayDifference = (start: string, end: string) => Math.round((Date.parse(end + 'T12:00:00Z') - Date.parse(start + 'T12:00:00Z')) / 86400000)

export function PlanningOverview() {
  const actor = useAuth()
  const canPlan = actor.role === 'owner' || actor.role === 'editor'
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const today = malaysiaToday()
  const requestedDate = params.get('date')
  const selectedDate = validCalendarDate(requestedDate) ? requestedDate : today
  const selectedId = params.get('entry')
  const calendar = useRef<FullCalendar>(null)
  const details = useRef<HTMLElement>(null)
  const revealSelection = useRef('')
  const [detailRequest, setDetailRequest] = useState(0)
  const mounted = useRef(true)
  const [preferences, setPreferences] = useState<PlanningPreferences | null>(null)
  const [preferencesError, setPreferencesError] = useState('')
  const state = params.get('state') || preferences?.states[0] || ''
  const [range, setRange] = useState({ start: '', end: '', title: '' })
  const [monthResult, setMonthResult] = useState<{ key: string; data?: CalendarResult; error?: string } | null>(null)
  const [upcomingResult, setUpcomingResult] = useState<{ key: string; data?: CalendarResult; error?: string } | null>(null)
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const monthKey = `${state}:${range.start}:${range.end}:${revision}`
  const upcomingKey = `${state}:${today}:${revision}`
  const month = monthResult?.key === monthKey ? monthResult.data ?? null : null
  const upcoming = upcomingResult?.key === upcomingKey ? upcomingResult.data ?? null : null
  const monthError = monthResult?.key === monthKey ? monthResult.error ?? '' : ''
  const upcomingError = upcomingResult?.key === upcomingKey ? upcomingResult.error ?? '' : ''
  useWorkspaceRefresh(() => setRevision(value => value + 1))
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    calendarApi.preferences(controller.signal).then(value => { setPreferences(value); setPreferencesError('') }).catch(error => { if (!controller.signal.aborted) setPreferencesError(error.message) })
    return () => controller.abort()
  }, [revision])
  useEffect(() => {
    if (!state || !range.start) return
    const controller = new AbortController()
    calendarApi.entries(range.start, range.end, state, overviewTypes, { signal: controller.signal, includeLinks: true }).then(data => { if (!controller.signal.aborted) setMonthResult({ key: monthKey, data }) }).catch(error => { if (!controller.signal.aborted) setMonthResult({ key: monthKey, error: error.message }) })
    return () => controller.abort()
  }, [state, range.start, range.end, monthKey])
  useEffect(() => {
    if (!state) return
    const controller = new AbortController()
    calendarApi.entries(today, shiftDay(today, 90), state, overviewTypes, { signal: controller.signal, includeLinks: true }).then(data => { if (!controller.signal.aborted) setUpcomingResult({ key: upcomingKey, data }) }).catch(error => { if (!controller.signal.aborted) setUpcomingResult({ key: upcomingKey, error: error.message }) })
    return () => controller.abort()
  }, [state, today, upcomingKey])
  useEffect(() => {
    const api = calendar.current?.getApi()
    if (api && api.view.currentStart.toISOString().slice(0, 7) !== selectedDate.slice(0, 7)) api.gotoDate(selectedDate)
  }, [selectedDate])

  const entries = (month?.entries ?? []).filter(available)
  const dayEntries = entries.filter(entry => entry.start_date <= selectedDate && entry.end_date >= selectedDate)
  const moments = (upcoming?.entries ?? []).filter(entry => available(entry) && entry.start_date >= today && entry.kind !== 'task' && entry.kind !== 'plan' && (entry.kind === 'business' || (entry.details as Occasion).publication_status !== 'withdrawn')).sort((a, b) => a.start_date.localeCompare(b.start_date) || a.title.localeCompare(b.title))
  const next = moments[0] ?? upcoming?.entries.filter(entry => entry.kind === 'plan' && entry.end_date >= today).sort((a, b) => a.start_date.localeCompare(b.start_date))[0] ?? null
  const focus = selectedId ? dayEntries.find(entry => entry.id === selectedId) ?? null : dayEntries[0] ?? (selectedDate === today ? next : null)
  const allLinks = [...new Map([...(month?.linked_items ?? []), ...(upcoming?.linked_items ?? [])].map(item => [item.id, item])).values()]
  const linked = linkedCalendarItems(focus, allLinks)
  const source = focus && !['business', 'plan', 'task'].includes(focus.kind) ? focus.details as Occasion : null
  const stateName = month?.states[state] ?? upcoming?.states[state] ?? state
  const date = focus?.start_date ?? selectedDate
  const until = dayDifference(today, date)
  const loading = !month && !monthError && !preferencesError
  const detailLoading = !monthError && !preferencesError && (loading || (!upcoming && !upcomingError && selectedDate === today && !dayEntries.length && !selectedId))
  const fullCalendar = calendarLocation(selectedDate, state, focus)
  const missingSelection = !!selectedId && !!month && !focus
  const withdrawn = source?.publication_status === 'withdrawn'

  useEffect(() => {
    if (!detailRequest || revealSelection.current !== `${selectedDate}:${selectedId ?? ''}`) return
    const frame = requestAnimationFrame(() => {
      revealSelection.current = ''
      details.current?.focus({ preventScroll: true })
      details.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
    })
    return () => cancelAnimationFrame(frame)
  }, [selectedDate, selectedId, detailRequest])

  function chooseDate(value: string, entry?: CalendarEntry, reveal = true) {
    setActionError('')
    setParams({ date: value, ...(state ? { state } : {}), ...(entry ? { entry: entry.id } : {}) }, { replace: true })
    if (reveal) { revealSelection.current = `${value}:${entry?.id ?? ''}`; setDetailRequest(value => value + 1) }
  }
  function moveMonth(direction: 'prev' | 'next') {
    const api = calendar.current?.getApi()
    if (!api) return
    api[direction]()
    chooseDate(api.view.currentStart.toISOString().slice(0, 10), undefined, false)
  }
  async function discuss() {
    if (busy || !canPlan) return
    setBusy(true); setActionError('')
    const item = linked.length === 1 ? linked[0] : null
    const title = focus?.title ?? `Marketing for ${labelDate(selectedDate)}`
    const context = item ? { marketing_plan_id: item.plan_id, marketing_plan_item_id: item.id, campaign_id: item.campaign_id ?? undefined } : focus ? focus.kind === 'business' ? { calendar_business_event_id: focus.entity_id } : focus.kind === 'plan' || focus.kind === 'task' ? { marketing_plan_item_id: focus.entity_id } : { calendar_occasion_id: focus.entity_id } : {}
    try {
      const thread = await api.createConversation({ title: title.slice(0, 255), ...context })
      if (!mounted.current) return
      const draft = `Help me ${item ? 'review and continue the existing campaign' : 'prepare a marketing strategy'} for ${title}, ${labelDate(date)}${focus && focus.end_date !== date ? ` to ${labelDate(focus.end_date)}` : ''}, in ${stateName}, Malaysia (Asia/Kuala_Lumpur). Use the saved brand, calendar context and business goals. Suggest the offer, preparation timeline and next steps for my review; do not assume discounts, stock or delivery promises are confirmed.`
      navigate(`/chat?thread=${thread.id}`, { state: { calendarDraft: draft } })
    } catch (error) { if (mounted.current) setActionError((error as Error).message) }
    finally { if (mounted.current) setBusy(false) }
  }
  const retry = () => setRevision(value => value + 1)
  return <div className="planning-overview">
    <section className="overview-month calendar-surface" aria-label="Overview marketing calendar" aria-busy={loading}>
      <div className="overview-calendar-heading"><div><h2 className="font-medium">Your marketing month</h2><p className="mt-1 text-xs text-text-3">Malaysia{stateName ? ` · ${stateName}` : ''}</p></div><Link to={calendarLocation(selectedDate, state)} className="inline-flex min-h-10 items-center gap-1 text-xs text-text-2 underline-offset-4 hover:underline">Full calendar<ArrowUpRight size={14} /></Link></div>
      <div className="overview-calendar-toolbar"><h3 className="text-base font-medium tracking-tight">{range.title || 'Your calendar'}</h3><div className="flex items-center gap-1.5"><button type="button" className="calendar-nav-control" aria-label="Previous overview month" onClick={() => moveMonth('prev')}><ArrowLeft size={15} /></button><button type="button" className="calendar-today-control" onClick={() => chooseDate(today, undefined, false)}>Today</button><button type="button" className="calendar-nav-control" aria-label="Next overview month" onClick={() => moveMonth('next')}><ArrowRight size={15} /></button></div></div>
      {(monthError || preferencesError) && <div role="alert" className="mb-4 text-sm text-halt"><p>{monthError || preferencesError}</p><button type="button" className="workspace-secondary mt-2" onClick={retry}>Retry calendar</button></div>}
      <FullCalendar ref={calendar} plugins={[dayGridPlugin, interactionPlugin]} initialView="dayGridMonth" initialDate={selectedDate} now={today} timeZone="UTC" headerToolbar={false} height="auto" firstDay={1} fixedWeekCount={false} dayMaxEvents={3} displayEventTime={false} eventDisplay="block" handleWindowResize
        datesSet={arg => setRange({ start: arg.startStr.slice(0, 10), end: shiftDay(arg.endStr.slice(0, 10), -1), title: arg.view.title })}
        dateClick={arg => chooseDate(arg.dateStr)}
        dayCellClassNames={arg => arg.date.toISOString().slice(0, 10) === selectedDate ? ['overview-selected-day'] : []}
        dayCellContent={arg => {
          const date = arg.date.toISOString().slice(0, 10)
          const activities = entries.filter(entry => entry.start_date <= date && entry.end_date >= date)
          const kinds = [...new Set(activities.map(entry => entry.kind))].slice(0, 3)
          return <button type="button" className="overview-date-button" aria-label={`Select ${labelDate(date)}${activities.length ? `, ${activities.length} ${activities.length === 1 ? 'activity' : 'activities'}` : ''}`} aria-pressed={date === selectedDate} onClick={event => { event.stopPropagation(); chooseDate(date) }}><span className="overview-date-number">{arg.dayNumberText}</span>{activities.length > 0 && <span className="overview-date-markers" aria-hidden="true">{kinds.map(kind => <i key={kind} style={{ backgroundColor: calendarKinds[kind].color }} />)}{activities.length > 1 && <span>{activities.length}</span>}</span>}</button>
        }}
        eventContent={arg => <button type="button" className="overview-event-button" aria-label={`${arg.event.extendedProps.kind}: ${arg.event.title}`} title={arg.event.title} onClick={event => { event.stopPropagation(); const entry = entries.find(entry => entry.id === arg.event.id); if (entry) chooseDate(entry.start_date, entry) }}><span className="overview-event-dot" /><span className="overview-event-title">{arg.event.title}</span></button>}
        events={entries.map(entry => ({ id: entry.id, title: entry.title, start: entry.start_date, end: shiftDay(entry.end_date, 1), allDay: true, backgroundColor: calendarKinds[entry.kind].color + '12', borderColor: calendarKinds[entry.kind].color + '35', textColor: calendarKinds[entry.kind].color, extendedProps: { kind: calendarKinds[entry.kind].label } }))}
      />
      <div className="overview-calendar-legend" aria-label="Calendar legend">{[['Holidays', calendarKinds.holiday.color], ['Campaigns', calendarKinds.plan.color], ['Preparation', calendarKinds.task.color], ['Business', calendarKinds.business.color]].map(([label, color]) => <span key={label}><i style={{ backgroundColor: color }} />{label}</span>)}</div>
      <div className="mt-3 text-xs leading-relaxed text-text-3" role="status">{loading ? 'Loading calendar activities…' : month ? entries.length ? <><span className="overview-wide-hint">Select a date or activity to plan your next step.</span><span className="overview-mobile-hint">Select a date to view its activities and planning actions below.</span></> : 'No activities scheduled this month. Choose a date to start planning.' : 'Calendar activities are unavailable.'}</div>
      {month && !month.coverage[range.title.match(/\d{4}/)?.[0] ?? selectedDate.slice(0, 4)]?.categories.includes('holiday') && <p className="mt-2 text-xs leading-relaxed text-halt">Verified public-holiday coverage is unavailable for this year. Custom events and campaign planning are still available.</p>}
    </section>
    <aside ref={details} tabIndex={-1} className="overview-planning-details" aria-label="Marketing planning details" aria-busy={detailLoading}>
      {detailLoading ? <div className="space-y-4" role="status"><p className="text-xs text-text-3">Finding your next marketing moment…</p><div className="h-6 w-3/4 animate-pulse rounded bg-lift" /><div className="h-16 animate-pulse rounded bg-lift" /></div> : monthError || preferencesError ? <><h2 className="font-medium">Your planning calendar</h2><p className="mt-3 text-sm leading-relaxed text-text-2">Restore the calendar connection to select an activity or start a plan.</p></> : <>
        <p className="mb-4 border-b border-edge pb-3 text-sm font-medium text-text-2">{labelDate(selectedDate)} · {dayEntries.length} {dayEntries.length === 1 ? 'activity' : 'activities'}</p>
        <p className="text-xs text-brand">{missingSelection ? 'Activity unavailable' : focus ? selectedDate === today && !dayEntries.length && !selectedId ? 'Next marketing opportunity' : calendarKinds[focus.kind].label : 'Room to plan'}</p>
        <h2 className="mt-3 text-xl font-semibold tracking-tight">{focus?.title ?? labelDate(selectedDate)}</h2>
        {focus && <p className="mt-2 text-xs leading-relaxed text-text-3">{labelDate(date)}{focus.end_date !== date ? ` – ${labelDate(focus.end_date)}` : ''} · {stateName}</p>}
        {focus && until >= 0 && <p className="mt-4 inline-block rounded-md border border-edge px-2 py-1 text-xs text-brand">{until ? `${until} ${until === 1 ? 'day' : 'days'} to prepare` : 'Happening today'}</p>}
        {focus ? <div className="mt-5"><CalendarEntryDetails entry={focus} states={month?.states ?? upcoming?.states} /></div> : <p className="mt-4 text-sm leading-relaxed text-text-2">{missingSelection ? 'This activity is no longer available for the selected date or state. Choose another date or activity.' : 'No activity planned for this date. Start with an idea or leave breathing room between campaigns.'}</p>}
        {source && linked.length > 0 && <p className="mt-4 text-sm leading-relaxed text-text-2">This occasion already has a saved campaign idea. Continue it below to keep your strategy and approvals together.</p>}
        <div className="mt-5 grid gap-2">
          {linked.length ? linked.map(item => <SavedItemAction key={item.id} item={item} state={state} date={date} multiple={linked.length > 1} />) : !withdrawn && !missingSelection && canPlan && <Link className="workspace-button justify-center" to={calendarLocation(date, state, focus, true)}>{focus ? focus.kind === 'task' || focus.kind === 'plan' ? 'Review calendar plan' : 'Plan this occasion' : 'Plan this date'}</Link>}
          {canPlan && !withdrawn && !missingSelection && <button type="button" className="workspace-secondary justify-center" disabled={busy} onClick={() => void discuss()}><MessageSquare size={15} />{busy ? 'Opening strategist…' : 'Discuss with strategist'}</button>}
          {!canPlan && !linked.length && <Link className="workspace-secondary justify-center" to={fullCalendar}>View in calendar</Link>}
        </div>
        {actionError && <p role="alert" className="mt-3 text-xs leading-relaxed text-halt">{actionError}</p>}
        {dayEntries.length > 1 && <section className="mt-6 border-t border-edge pt-4" aria-label="Other activities on selected date"><h3 className="text-sm font-medium text-text-2">Also on {labelDate(selectedDate)}</h3><div className="divide-y divide-edge">{dayEntries.filter(entry => entry.id !== focus?.id).map(entry => <article key={entry.id} className="py-4"><button type="button" className="min-h-11 w-full text-left text-base font-medium leading-relaxed hover:text-brand" onClick={() => chooseDate(selectedDate, entry)}><span>{entry.title}</span><span className="mt-1 block text-xs font-normal text-text-3">{calendarKinds[entry.kind].label} · {labelDate(entry.start_date)}{entry.end_date !== entry.start_date ? ` – ${labelDate(entry.end_date)}` : ''}</span></button><div className="mt-3"><CalendarEntryDetails entry={entry} states={month?.states} /></div></article>)}</div></section>}
        <div className="mt-6 border-t border-edge pt-4"><h3 className="text-xs font-medium text-text-2">Your planning flow</h3><p className="mt-2 text-xs leading-relaxed text-text-3">Calendar → Strategist → Campaign → Review → Publish</p><p className="mt-2 text-xs leading-relaxed text-text-3">You review the brief and proposal before AI production starts.</p></div>
        {upcomingError && <div className="mt-4 text-xs text-halt" role="alert"><p>Upcoming opportunities could not load. {upcomingError}</p><button type="button" onClick={retry} className="mt-2 min-h-10 underline underline-offset-4">Retry opportunities</button></div>}
        {!focus && selectedDate === today && upcoming && !next && <p className="mt-4 text-xs leading-relaxed text-text-3">No upcoming occasions were found in the next 90 days. You can still plan a custom campaign.</p>}
      </>}
    </aside>
  </div>
}

function SavedItemAction({ item, state, date, multiple }: { item: CalendarItemLink; state: string; date: string; multiple: boolean }) {
  const to = item.source_changed || !item.campaign_id ? `/calendar?${new URLSearchParams({ item: String(item.id), date, state })}` : `/campaigns/${item.campaign_id}`
  const label = item.source_changed ? 'Review calendar changes' : item.campaign_id ? 'Continue campaign' : 'Review calendar plan'
  return <div><Link className="workspace-button w-full justify-center text-center" to={to}>{multiple ? `${label}: ${item.title}` : label}</Link>{item.source_changed && <p className="mt-2 text-xs leading-relaxed text-halt">The source date or details changed. Review the saved idea before creating a campaign.</p>}</div>
}
