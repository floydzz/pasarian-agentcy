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
  // -- company ground truth ------------------------------------------------

  getBrandProfile: () => request<BrandProfile>('/brand-profile'),

  saveBrandProfile: (payload: BrandProfileWrite) =>
    request<BrandProfile>('/brand-profile', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  listCampaigns: () => request<Campaign[]>('/campaigns'),

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

  listConversations: () => request<Conversation[]>('/conversations'),

  // Send `{}` for the default title as well. The API can then distinguish a
  // deliberate default thread from a missing request body.
  createConversation: (payload: { title?: string } = {}) =>
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
