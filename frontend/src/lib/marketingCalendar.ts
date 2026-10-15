import type { CalendarEntry, CalendarItemLink } from '@/api/calendar'

export function malaysiaToday() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()) }
export function shiftDay(value: string, days: number) { const date = new Date(value + 'T12:00:00Z'); date.setUTCDate(date.getUTCDate() + days); return date.toISOString().slice(0, 10) }
export function validCalendarDate(value: string | null): value is string { return !!value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value + 'T12:00:00Z').toISOString().slice(0, 10) === value }
export const labelDate = (value: string) => new Intl.DateTimeFormat('en-MY', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T12:00:00Z'))
export const calendarKinds: Record<CalendarEntry['kind'], { label: string; color: string }> = {
  holiday: { label: 'Public holidays', color: '#c9b58e' }, school: { label: 'School holidays', color: '#b7b09d' }, festival: { label: 'Festivals', color: '#c9b58e' }, commercial: { label: 'Commercial dates', color: '#bcb9b3' }, business: { label: 'Business events', color: '#aab7c7' }, plan: { label: 'Marketing plans', color: '#c6ad86' }, task: { label: 'Deadlines', color: '#d6a09a' },
}
export function calendarLocation(date: string, state: string, entry?: CalendarEntry | null, planning = false) {
  const params = new URLSearchParams({ date, state })
  if (entry) params.set(entry.kind === 'plan' || entry.kind === 'task' ? 'item' : 'entry', entry.kind === 'plan' || entry.kind === 'task' ? String(entry.entity_id) : entry.id)
  if (planning) params.set('action', 'plan')
  return `/calendar?${params}`
}
export function linkedCalendarItems(entry: CalendarEntry | null, items: CalendarItemLink[]) {
  if (!entry) return []
  return items.filter(item => entry.kind === 'plan' || entry.kind === 'task' ? item.id === entry.entity_id : entry.kind === 'business' ? item.business_event_id === entry.entity_id : item.occasion_id === entry.entity_id)
}
