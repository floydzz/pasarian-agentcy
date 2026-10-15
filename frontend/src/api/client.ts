import type {
  Agent,
  AgentUpdate,
  Asset,
  BrandProfile,
  BrandProfileWrite,
  Campaign,
  ChatSendResult,
  CinematicTrailer,
  CinematicTrailerCreate,
  Concept,
  ConceptStatus,
  Conversation,
  Creative,
  Generation,
  DemoVideo,
  DemoVideoCreate,
  MarketingVideo,
  MarketingVideoCreate,
  Plan,
  ProductReference,
  RenderResult,
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
  code: string
  requestId: string
  fields: { field: string; message: string }[]
  retryable: boolean
  constructor(message: string, status: number, code = 'request_failed', requestId = '', fields: { field: string; message: string }[] = [], retryable = false) {
    super(message)
    this.name = 'ApiError'
    this.status = status; this.code = code; this.requestId = requestId; this.fields = fields; this.retryable = retryable
  }
}

let csrfToken = ''
const cache = new Map<string, { at: number; value: unknown }>()
const pending = new Map<string, Promise<unknown>>()
let generation = 0
export function invalidateData() {
  generation += 1
  cache.clear()
  window.dispatchEvent(new Event('workspace-data-changed'))
}
export function setSessionToken(token: string) {
  csrfToken = token
  pending.clear()
  invalidateData()
}
export function sessionHeaders() { return { 'X-CSRF-Token': csrfToken } }

export type Job = { id: string; path: string; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'interrupted' | 'cancelled'; events: Record<string, unknown>[]; cursor: number; result: Record<string, unknown> | unknown[] | null; error: string | null; updated_at: string }

export async function waitForJob(job: Job, onUpdate?: (job: Job) => void, signal?: AbortSignal): Promise<Record<string, unknown> | unknown[]> {
  let cursor = 0
  let reconnects = 0
  for (;;) {
    if (signal?.aborted) throw new DOMException('Stopped watching this job', 'AbortError')
    let latest: Job
    try {
      latest = await request<Job>(`/jobs/${job.id}?after=${cursor}`, { signal })
      reconnects = 0
    } catch (failure) {
      if (signal?.aborted || !(failure instanceof ApiError) || !failure.retryable || reconnects >= 10) throw failure
      reconnects += 1
      await new Promise(resolve => window.setTimeout(resolve, Math.min(1000 * reconnects, 5000)))
      continue
    }
    if (signal?.aborted) throw new DOMException('Stopped watching this job', 'AbortError')
    cursor = latest.cursor
    onUpdate?.(latest)
    if (['succeeded', 'failed', 'interrupted', 'cancelled'].includes(latest.status)) {
      invalidateData()
      if (latest.status === 'succeeded' && latest.result !== null) return latest.result
      throw new ApiError(latest.error || 'The job did not complete. Open Progress to review and retry it.', 409, latest.status)
    }
    await new Promise<void>((resolve, reject) => {
      const stop = () => { window.clearTimeout(timer); reject(new DOMException('Stopped watching this job', 'AbortError')) }
      const timer = window.setTimeout(() => { signal?.removeEventListener('abort', stop); resolve() }, 1000)
      signal?.addEventListener('abort', stop, { once: true })
    })
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? 'GET'
  const reusable = method === 'GET' && !init?.signal && !path.startsWith('/auth/') && !path.startsWith('/jobs')
  const hit = reusable ? cache.get(path) : undefined
  if (hit && Date.now() - hit.at < 5000) return structuredClone(hit.value) as T
  const existing = reusable ? pending.get(path) : undefined
  if (existing) return structuredClone(await existing) as T
  const version = generation
  const fetchRequest = async () => {
    let response: Response
    try {
      response = await fetch(`/api${path}`, {
        ...init, credentials: 'same-origin',
        headers: { ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...sessionHeaders(), ...init?.headers },
        signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000),
      })
    } catch (error) {
      if (init?.signal?.aborted) throw error
      throw new ApiError('We could not connect. Check your connection and try again. Existing work is saved.', 0, 'connection_failed', '', [], true)
    }
    if (!response.ok) {
      let body: { detail?: string | { msg: string }[]; code?: string; request_id?: string; fields?: { field: string; message: string }[]; retryable?: boolean } = {}
      try { body = await response.json() } catch { /* keep the safe fallback */ }
      if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('authentication-required'))
      throw new ApiError(typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(d => d.msg).join('; ') : `The request could not complete (${response.status}).`, response.status, body.code, body.request_id, body.fields, body.retryable)
    }
    if (response.status === 204) { if (method !== 'GET') invalidateData(); return undefined as T }
    let value
    try { value = await response.json() } catch { throw new ApiError('The service returned incomplete data. Check saved progress before trying again.', 502, 'incomplete_response', response.headers.get('X-Request-ID') ?? '', [], true) }
    if (method !== 'GET') invalidateData()
    if (value.__job__) return await waitForJob(value.__job__, undefined, init?.signal ?? undefined) as T
    if (reusable && version === generation) cache.set(path, { at: Date.now(), value: structuredClone(value) })
    return value as T
  }
  const operation = fetchRequest().catch(async failure => {
    if (method !== 'GET' || !(failure instanceof ApiError) || !failure.retryable || init?.signal?.aborted || version !== generation) throw failure
    await new Promise(resolve => window.setTimeout(resolve, 300))
    if (init?.signal?.aborted || version !== generation) throw failure
    return fetchRequest()
  })
  if (reusable) pending.set(path, operation)
  try { return await operation } finally { if (reusable && pending.get(path) === operation) pending.delete(path) }
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

export const api = {
  // -- company ground truth ------------------------------------------------

  getBrandProfile: () => request<BrandProfile>('/brand-profile'),

  saveBrandProfile: (payload: BrandProfileWrite) =>
    request<BrandProfile>('/brand-profile', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  listCampaigns: () => request<Campaign[]>('/campaigns?limit=100'),

  campaignDirectory: (query: string, status: string, offset: number, signal?: AbortSignal) => request<{ items: Campaign[]; total: number; offset: number; limit: number }>(`/campaign-directory?q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}&offset=${offset}&limit=20`, { signal }),

  getCampaign: (id: number) => request<Campaign>(`/campaigns/${id}`),

  createCampaign: (payload: { name: string; brief: string; source_event?: string }) =>
    post<Campaign>('/campaigns', payload),

  listProductReferences: (campaignId: number) =>
    request<ProductReference[]>(`/campaigns/${campaignId}/product-references`),

  uploadProductReference: (
    campaignId: number,
    payload: { label: string; data_url: string; is_primary?: boolean },
  ) => post<ProductReference>(`/campaigns/${campaignId}/product-references`, payload),

  updateProductReference: (
    campaignId: number,
    referenceId: number,
    payload: { label?: string; is_primary?: boolean },
  ) => patch<ProductReference>(`/campaigns/${campaignId}/product-references/${referenceId}`, payload),

  deleteProductReference: (campaignId: number, referenceId: number) =>
    request<void>(`/campaigns/${campaignId}/product-references/${referenceId}`, {
      method: 'DELETE',
    }),

  // -- marketing chat -----------------------------------------------------

  listConversations: (offset = 0) => request<Conversation[]>(`/conversations?summary=true&limit=30&offset=${offset}`),

  // Send `{}` for the default title as well. The API can then distinguish a
  // deliberate default thread from a missing request body.
  createConversation: (payload: { title?: string; campaign_id?: number; marketing_plan_id?: number; marketing_plan_item_id?: number; calendar_occasion_id?: number; calendar_business_event_id?: number } = {}) =>
    post<Conversation>('/conversations', payload),

  getConversation: (id: number) => request<Conversation>(`/conversations/${id}`),

  updateConversation: (
    id: number,
    payload: { title?: string; campaign_id?: number | null },
  ) => patch<Conversation>(`/conversations/${id}`, payload),

  deleteConversation: (id: number) =>
    request<void>(`/conversations/${id}`, { method: 'DELETE' }),

  sendConversationMessage: (id: number, content: string) =>
    post<ChatSendResult>(`/conversations/${id}/messages`, { content }),

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

  // -- creatives -----------------------------------------------------------

  listAssets: (id: number) => request<Asset[]>(`/campaigns/${id}/assets`),

  renderAssets: (id: number) => post<RenderResult>(`/campaigns/${id}/render`),

  approveAsset: (assetId: number) => post<Asset>(`/assets/${assetId}/approve`),

  rejectAsset: (assetId: number) => post<Asset>(`/assets/${assetId}/reject`),

  redoAsset: (assetId: number) => post<Asset>(`/assets/${assetId}/redo`),

  approveAllAssets: (id: number) => post<Campaign>(`/campaigns/${id}/assets/approve`),

  // -- legacy fixed product-explainer video --------------------------------

  listDemoVideos: () => request<DemoVideo[]>('/demo-videos'),

  renderDemoVideo: (payload: DemoVideoCreate) => post<DemoVideo>('/demo-videos/render', payload),

  approveDemoVideo: (videoId: number) => post<DemoVideo>(`/demo-videos/${videoId}/approve`),

  rejectDemoVideo: (videoId: number) => post<DemoVideo>(`/demo-videos/${videoId}/reject`),

  redoDemoVideo: (videoId: number) => post<DemoVideo>(`/demo-videos/${videoId}/redo`),

  // -- reusable marketing-video studio ------------------------------------

  listVideos: () => request<MarketingVideo[]>('/videos'),

  listCampaignVideos: (id: number) =>
    request<MarketingVideo[]>(`/campaigns/${id}/videos`),

  /** A first draft of the campaign's video, seeded from its approved work. */
  campaignVideoBrief: (id: number) =>
    request<MarketingVideoCreate>(`/campaigns/${id}/video-brief`),

  renderCampaignVideo: (id: number, payload: MarketingVideoCreate) =>
    post<MarketingVideo>(`/campaigns/${id}/videos/render`, payload),

  renderVideo: (payload: MarketingVideoCreate) => post<MarketingVideo>('/videos/render', payload),

  approveVideo: (videoId: number) => post<MarketingVideo>(`/videos/${videoId}/approve`),

  rejectVideo: (videoId: number) => post<MarketingVideo>(`/videos/${videoId}/reject`),

  redoVideo: (videoId: number) => post<MarketingVideo>(`/videos/${videoId}/redo`),

  // -- cinematic AI trailers ----------------------------------------------

  listCinematicTrailers: (campaignId?: number) =>
    request<CinematicTrailer[]>(
      campaignId === undefined
        ? '/cinematic-trailers'
        : `/cinematic-trailers?campaign_id=${campaignId}`,
    ),

  createCinematicTrailer: (payload: Partial<CinematicTrailerCreate> = {}) =>
    post<CinematicTrailer>('/cinematic-trailers', payload),

  submitCinematicTrailer: (trailerId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/submit`),

  refreshCinematicTrailer: (trailerId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/refresh`),

  composeCinematicTrailer: (trailerId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/compose`),

  uploadCinematicTrailerCapture: (trailerId: number, dataUrl: string) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/application-capture`, {
      data_url: dataUrl,
    }),

  uploadCinematicTrailerSoundtrack: (trailerId: number, dataUrl: string) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/soundtrack`, {
      data_url: dataUrl,
    }),

  uploadCinematicTrailerProductReference: (trailerId: number, dataUrl: string) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/product-reference`, {
      data_url: dataUrl,
    }),

  regenerateCinematicTrailerShot: (trailerId: number, shotId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/shots/${shotId}/regenerate`),

  regenerateAllCinematicTrailerShots: (trailerId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/shots/regenerate`),

  approveCinematicTrailer: (trailerId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/approve`),

  rejectCinematicTrailer: (trailerId: number) =>
    post<CinematicTrailer>(`/cinematic-trailers/${trailerId}/reject`),

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

  listCreatives: (campaignId?: number) =>
    request<Creative[]>(
      campaignId === undefined ? '/creatives' : `/creatives?campaign_id=${campaignId}`,
    ),

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
