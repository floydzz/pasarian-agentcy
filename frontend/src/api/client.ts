import type {
  Agent,
  AgentUpdate,
  Campaign,
  Concept,
  ConceptStatus,
  Generation,
  Plan,
  Run,
  RunDetail,
  ScrapeResult,
  System,
  TrendSource,
  TrendStatus,
  Variant,
} from './types'

/** A failed call carries the backend's own explanation, not a status code.
 *
 * The API's 409s and 502s are written for a person to read — "campaign is
 * generating, not draft" — so they go straight to the screen rather than being
 * replaced with something vaguer. */
export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError('Cannot reach the backend. Is uvicorn running?', 0)
  }

  if (!response.ok) {
    throw new ApiError(await explain(response), response.status)
  }
  // A 204 has no body to parse, and a delete that "failed" only because
  // there was nothing to read would be an unpleasant lie.
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function explain(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    // FastAPI validation errors arrive as a list of field problems.
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg: string }) => d.msg).join('; ')
    }
  } catch {
    /* fall through to the generic message */
  }
  return `Request failed (${response.status})`
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

export const api = {
  listCampaigns: () => request<Campaign[]>('/campaigns'),

  getCampaign: (id: number) => request<Campaign>(`/campaigns/${id}`),

  createCampaign: (payload: { name: string; brief: string; source_event?: string }) =>
    post<Campaign>('/campaigns', payload),

  listConcepts: (id: number) => request<Concept[]>(`/campaigns/${id}/concepts`),

  plan: (id: number) => post<Plan>(`/campaigns/${id}/plan`),

  decide: (conceptId: number, decision: ConceptStatus, editNote?: string) =>
    post<Concept>(`/concepts/${conceptId}/decision`, {
      decision,
      edit_note: editNote ?? null,
    }),

  revise: (conceptId: number, note: string) =>
    post<Concept>(`/concepts/${conceptId}/revise`, { note }),

  approvePlan: (id: number) => post<Campaign>(`/campaigns/${id}/approve`),

  setAutoMode: (
    id: number,
    payload: { auto_approve_plan?: boolean; auto_approve_assets?: boolean },
  ) =>
    request<Campaign>(`/campaigns/${id}/auto-mode`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  generate: (id: number) => post<Generation>(`/campaigns/${id}/generate`),

  listVariants: (id: number) => request<Variant[]>(`/campaigns/${id}/variants`),

  // -- the machine ---------------------------------------------------------

  system: () => request<System>('/system'),

  listAgents: () => request<Agent[]>('/agents'),

  tuneAgent: (agent: string, payload: AgentUpdate) =>
    patch<Agent>(`/agents/${agent}`, payload),

  resetAgent: (agent: string) => post<Agent>(`/agents/${agent}/reset`),

  // -- history -------------------------------------------------------------

  listRuns: (campaignId?: number) =>
    request<Run[]>(
      campaignId === undefined ? '/runs' : `/runs?campaign_id=${campaignId}`,
    ),

  getRun: (id: number) => request<RunDetail>(`/runs/${id}`),

  // -- trends --------------------------------------------------------------

  trendStatus: () => request<TrendStatus>('/trends/status'),

  listTrendSources: () => request<TrendSource[]>('/trends/sources'),

  addTrendSource: (payload: { keyword: string; note?: string }) =>
    post<TrendSource>('/trends/sources', payload),

  updateTrendSource: (
    id: number,
    payload: { keyword?: string; note?: string; enabled?: boolean },
  ) => patch<TrendSource>(`/trends/sources/${id}`, payload),

  removeTrendSource: (id: number) =>
    request<void>(`/trends/sources/${id}`, { method: 'DELETE' }),

  scrape: (sourceId?: number) =>
    post<ScrapeResult[]>(
      sourceId === undefined ? '/trends/scrape' : `/trends/scrape?source_id=${sourceId}`,
    ),
}
