import { request } from './client'

export interface PlanningPreferences {
  states: string[]; goals: string; annual_budget: number | null; campaigns_per_month: number; lead_days: number; reminder_days: number; blackout_dates: string[]; version: number
}
export interface Occasion {
  id: number; title: string; category: string; start_date: string; end_date: string; states: string[]; source_url: string; source_revision: string; verified_at: string; publication_status: string; observed_for: string | null
}
export interface BusinessEvent { id: number; title: string; description: string; start_date: string; end_date: string; archived: boolean; version: number }
export interface MarketingTask { id: number; item_id: number; title: string; due_date: string; status: 'todo' | 'done'; manual_date: boolean; version: number }
export interface ItemDraft {
  occasion_id: number | null; business_event_id: number | null; title: string; rationale: string; strategy: string; audience: string; products: string[]; offer: string; budget: number | null; campaign_start: string; campaign_end: string; preparation_start: string; tasks: { title: string; due_date: string }[]
}
export interface MarketingItem extends ItemDraft {
  id: number; plan_id: number; status: 'proposed' | 'planned' | 'skipped' | 'cancelled'; campaign_id: number | null; campaign_status: string | null; source_snapshot: Record<string, string>; current_source_snapshot: Record<string, string>; source_changed: boolean; version: number; tasks: MarketingTask[]
}
export interface MarketingPlan { id: number; name: string; start_date: string; end_date: string; goals: string; status: string; constraints: Record<string, unknown>; version: number; items?: MarketingItem[] }
export interface CalendarEntry { id: string; entity_id: number; kind: 'holiday' | 'school' | 'festival' | 'commercial' | 'business' | 'plan' | 'task'; title: string; start_date: string; end_date: string; details: Occasion | BusinessEvent | MarketingItem | MarketingTask }
export type CalendarItemLink = Pick<MarketingItem, 'id' | 'plan_id' | 'title' | 'occasion_id' | 'business_event_id' | 'campaign_id' | 'campaign_status' | 'status' | 'campaign_start' | 'campaign_end' | 'preparation_start' | 'source_changed'>
export interface CalendarResult { entries: CalendarEntry[]; linked_items?: CalendarItemLink[]; coverage: Record<string, { categories: string[]; note: string }>; states: Record<string, string>; timezone: string }
export interface CalendarAttention { key: string; title: string; kind: string; due_date?: string; url: string; action: string }
export interface PlanningRequest { states?: string[]; operation: 'annual' | 'item'; start_date: string; end_date: string; plan_id?: number; item_id?: number; occasion_id?: number; business_event_id?: number; instructions: string; request_key: string }
export interface PlanningRunSummary { id: number; status: string; accepted: boolean; created_at: string; period: string }
export interface PlanningRun {
  id: number; status: string; input: { request: PlanningRequest; plan_version: number | null; item_version: number | null }; proposal: { summary: string; items: ItemDraft[]; assumptions: string[] } | null; error: string | null; events: { agent: string; phase: string; detail: string }[]; accepted: boolean; accepted_plan_id: number | null; elapsed_ms: number | null
}
export type ItemPayload = ItemDraft & { status: MarketingItem['status']; version?: number }
const post = <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })
const patch = <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
export const calendarApi = {
  entries: (start: string, end: string, state: string, types: string[], options: { signal?: AbortSignal; includeLinks?: boolean } = {}) => request<CalendarResult>(`/calendar?${new URLSearchParams({ start, end, state, types: types.length ? types.join(',') : 'none', ...(options.includeLinks ? { include_links: 'true' } : {}) })}`, { signal: options.signal }),
  preferences: (signal?: AbortSignal) => request<PlanningPreferences>('/calendar/preferences', { signal }),
  savePreferences: (body: PlanningPreferences) => request<PlanningPreferences>('/calendar/preferences', { method: 'PUT', body: JSON.stringify(body) }),
  plans: () => request<MarketingPlan[]>('/marketing-plans'),
  plan: (id: number) => request<MarketingPlan>(`/marketing-plans/${id}`),
  createPlan: (body: { name: string; start_date: string; end_date: string; goals: string }) => post<MarketingPlan>('/marketing-plans', body),
  updatePlan: (id: number, body: { name: string; start_date: string; end_date: string; goals: string; status: string; version: number }) => patch<MarketingPlan>(`/marketing-plans/${id}`, body),
  item: (id: number) => request<MarketingItem>(`/marketing-plan-items/${id}`),
  addItem: (plan: MarketingPlan, body: ItemPayload) => post<MarketingItem>(`/marketing-plans/${plan.id}/items?version=${plan.version}`, body),
  updateItem: (id: number, body: ItemPayload) => patch<MarketingItem>(`/marketing-plan-items/${id}`, body),
  createCampaign: (item: MarketingItem) => post<{ campaign_id: number; conversation_id: number | null; item: MarketingItem }>(`/marketing-plan-items/${item.id}/campaign`, { version: item.version }),
  campaignItem: (id: number) => request<MarketingItem | null>(`/campaigns/${id}/calendar`),
  addEvent: (body: Omit<BusinessEvent, 'id' | 'version'>) => post<BusinessEvent>('/calendar/business-events', body),
  updateEvent: (event: BusinessEvent) => patch<BusinessEvent>(`/calendar/business-events/${event.id}`, { title: event.title, start_date: event.start_date, end_date: event.end_date, description: event.description, archived: event.archived, version: event.version }),
  addTask: (itemId: number, title: string, due_date: string) => post<MarketingTask>(`/marketing-plan-items/${itemId}/tasks`, { title, due_date }),
  task: (task: MarketingTask, status: 'todo' | 'done', due_date = task.due_date) => patch<MarketingTask>(`/marketing-tasks/${task.id}`, { status, due_date, version: task.version }),
  runs: () => request<PlanningRunSummary[]>('/calendar/runs'),
  run: (id: number) => request<PlanningRun>(`/calendar/runs/${id}`),
  newRun: (body: PlanningRequest) => post<PlanningRun>('/calendar/runs', body),
  accept: (run: PlanningRun, name: string) => post<MarketingPlan>(`/calendar/runs/${run.id}/accept`, { name, expected_version: run.input.plan_version }),
  attention: () => request<CalendarAttention[]>('/calendar/attention'),
  snooze: (key: string, until: string) => post('/calendar/attention/dismiss', { key, until }),
}

export function itemPayload(item: MarketingItem): ItemPayload {
  return { occasion_id: item.occasion_id, business_event_id: item.business_event_id, title: item.title, rationale: item.rationale, strategy: item.strategy, audience: item.audience, products: item.products, offer: item.offer, budget: item.budget, campaign_start: item.campaign_start, campaign_end: item.campaign_end, preparation_start: item.preparation_start, status: item.status, version: item.version, tasks: item.tasks.map(t => ({ title: t.title, due_date: t.due_date })) }
}
