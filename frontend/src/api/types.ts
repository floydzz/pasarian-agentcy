/** Mirrors the Pydantic contracts in `backend/app/api/schemas.py`. */

export const CAMPAIGN_FLOW = [
  'draft',
  'planning',
  'pending_plan_approval',
  'generating',
  'pending_asset_review',
  'ready_to_publish',
  'published',
] as const

export type CampaignStatus = (typeof CAMPAIGN_FLOW)[number]

export type ConceptStatus = 'pending' | 'approved' | 'rejected' | 'edited'

export interface Campaign {
  id: number
  name: string
  brief: string
  status: CampaignStatus
  source_event: string | null
  auto_approve_plan: boolean
  auto_approve_assets: boolean
  created_at: string
  updated_at: string
}

/** A marketer-supplied product photo, distinct from model-generated assets. */
export interface ProductReference {
  id: number
  campaign_id: number
  label: string
  media_url: string
  is_primary: boolean
  created_at: string
  updated_at: string
}

// -- marketing chat -------------------------------------------------------

export type ChatRole = 'user' | 'assistant' | 'system'
export type ChatAction = 'create_campaign' | 'run_plan' | 'run_generate' | 'none'

export interface ChatMessage {
  id: number
  conversation_id: number
  role: ChatRole
  content: string
  action: ChatAction | null
  created_at: string
  updated_at: string
}

export interface Conversation {
  id: number
  title: string
  campaign_id: number | null
  campaign: Campaign | null
  messages: ChatMessage[]
  created_at: string
  updated_at: string
}

export interface ChatSendResult {
  message: ChatMessage
  campaign: Campaign | null
  authorized: 'plan' | 'generate' | null
}

export interface Concept {
  id: number
  campaign_id: number
  theme: string
  format: 'image' | 'video' | 'carousel'
  trend_rationale: string
  brand_rationale: string
  variant_count: number
  variation_axes: string[]
  status: ConceptStatus
  edit_note: string | null
}

export interface Plan {
  strategy_summary: string
  concepts: Concept[]
}

export type PlacementZone =
  | 'top-left' | 'top-center' | 'top-right'
  | 'mid-left' | 'mid-center' | 'mid-right'
  | 'bottom-left' | 'bottom-center' | 'bottom-right'

export type TextTreatment = 'bare' | 'soft-gradient' | 'glass-panel' | 'ribbon'

export interface VisualBrief {
  composition_notes: string
  image_prompt: string
  text_placement: string
  /** The same intent as `text_placement`, in the form the compositor acts on. */
  placement_zone: PlacementZone
  /** The copy surface selected by the visual planner for this composition. */
  text_treatment?: TextTreatment
}

export interface Variant {
  id: number
  concept_id: number
  hook_type: string
  headline: string
  body: string
  cta: string
  visual_brief: VisualBrief
  director_status: 'pass' | 'flagged'
  director_notes: string | null
  revision_count: number
}

export interface Generation {
  concepts_generated: number
  concepts_skipped: number
  variants: Variant[]
}

export type QAStatus = 'passed' | 'flagged'
export type ReviewStatus = 'pending' | 'approved' | 'rejected'

/** One finished creative — a generated background with the copy composited on,
 * pre-screened by vision QA before it reaches the gate. */
export interface Asset {
  id: number
  variant_id: number
  media_url: string
  qa_status: QAStatus
  qa_notes: string | null
  review_status: ReviewStatus
}

/** One finished creative with the campaign it belongs to.
 *
 * The gallery is browsed away from any one campaign, so a creative that
 * arrives there carrying only a variant id is a picture of nothing. */
export interface Creative extends Asset {
  created_at: string
  campaign_id: number
  campaign_name: string
  concept_theme: string
  headline: string
}

export interface RenderResult {
  variants_rendered: number
  variants_skipped: number
  assets: Asset[]
}

// -- Agentcy product-explainer video -------------------------------------

export interface DemoVideoCreate {
  title: string
  strapline: string
  cta: string
}

export interface DemoVideo {
  id: number
  title: string
  strapline: string
  cta: string
  media_url: string
  poster_url: string
  duration_seconds: number
  scene_count: number
  qa_status: QAStatus
  qa_notes: string | null
  review_status: ReviewStatus
  created_at: string
  updated_at: string
}

// -- reusable marketing-video studio -------------------------------------

export type VideoProfile = 'software_demo' | 'product_marketing'
export type VideoSceneLayout = 'hero' | 'feature' | 'workflow' | 'proof' | 'cta'

export interface MarketingVideoScene {
  eyebrow: string
  headline: string
  body: string
  layout: VideoSceneLayout
}

export interface MarketingVideoCreate {
  name: string
  profile: VideoProfile
  brand_name: string
  product_name: string
  target_audience: string
  cta: string
  storyboard: MarketingVideoScene[]
  /** Opt-in generative backdrops. The captions are still drawn by the
   * renderer either way; this only changes what is behind them. */
  use_broll: boolean
  product_reference_id?: number | null
}

export interface MarketingVideo extends MarketingVideoCreate {
  id: number
  /** Null for the product explainer and any video made outside a campaign. */
  campaign_id: number | null
  product_reference_url: string | null
  media_url: string
  poster_url: string
  duration_seconds: number
  scene_count: number
  qa_status: QAStatus
  qa_notes: string | null
  review_status: ReviewStatus
  created_at: string
  updated_at: string
}

// -- cinematic AI trailer -------------------------------------------------

export type CinematicShotMode = 'text_to_video' | 'image_to_video' | 'reference_to_video'
export type CinematicShotStatus = 'draft' | 'pending' | 'running' | 'succeeded' | 'failed'
export type CinematicTrailerStatus = 'draft' | 'generating' | 'ready_to_compose' | 'rendered' | 'failed'
export type CinematicProductSurface = 'none' | 'studio' | 'hub' | 'history'

export interface CinematicTrailerShot {
  id: number
  position: number
  label: string
  title_card: string
  prompt: string
  mode: CinematicShotMode
  duration_seconds: number
  voiceover: string
  audio_cue: string
  reference_asset_urls: string[]
  protect_reference: boolean
  product_surface: CinematicProductSurface
  remote_task_id: string | null
  provider_status: CinematicShotStatus
  provider_error: string | null
  media_url: string | null
}

export interface CinematicTrailer {
  id: number
  campaign_id: number | null
  title: string
  aspect_ratio: '16:9' | '9:16'
  cta: string
  status: CinematicTrailerStatus
  media_url: string | null
  poster_url: string | null
  application_capture_url: string | null
  soundtrack_url: string | null
  product_reference_url: string | null
  duration_seconds: number
  review_status: ReviewStatus
  shots: CinematicTrailerShot[]
  created_at: string
  updated_at: string
}

export interface CinematicTrailerCreate {
  campaign_id?: number | null
  title: string
  aspect_ratio: '16:9' | '9:16'
  cta: string
  shots: Array<{
    label: string
    title_card: string
    prompt: string
    mode: CinematicShotMode
    duration_seconds: number
    voiceover: string
    audio_cue: string
    reference_asset_urls?: string[]
    protect_reference?: boolean
    product_surface?: CinematicProductSurface
  }>
}

// -- company ground truth --------------------------------------------------

export interface BrandProduct {
  name: string
  description: string
  price: string | null
  benefits: string | null
}

export interface BrandProfile {
  configured: boolean
  knowledge_chunks: number
  company_name: string
  industry: string
  website: string | null
  description: string
  brand_voice: string
  target_audience: string
  products: BrandProduct[]
  approved_claims: string | null
  restrictions: string | null
  updated_at: string | null
}

export interface BrandProfileWrite {
  company_name: string
  industry: string
  website: string | null
  description: string
  brand_voice: string
  target_audience: string
  products: BrandProduct[]
  approved_claims: string | null
  restrictions: string | null
}

// -- the machine itself ----------------------------------------------------

export interface System {
  llm_provider: string
  embedding_provider: string
  trends_live: boolean
  geo: string
  /** False when no b-roll provider is configured, so the video studio can
   * hide the option rather than offer a switch that does nothing. */
  broll_available: boolean
}

/** One integer a person may move, carrying the range it may move inside.
 *
 * The bounds come from the backend rather than being restated here: they exist
 * because these numbers buy model calls, and a console that invents its own
 * limits would eventually disagree with the machine enforcing them. */
export interface Knob {
  field: string
  label: string
  help: string
  minimum: number
  maximum: number
  default: number
  value: number
}

export interface Agent {
  agent: string
  label: string
  role: string
  boundary: string
  note_placeholder: string
  standing_note: string | null
  knobs: Knob[]
  is_default: boolean
}

export interface AgentUpdate {
  standing_note?: string
  concept_count?: number
  company_k?: number
  trend_k?: number
  max_revisions?: number
  max_redos?: number
  context_turns?: number
}

// -- history ---------------------------------------------------------------

export interface Run {
  id: number
  campaign_id: number | null
  campaign_name: string
  kind: 'plan' | 'generate' | 'render'
  status: 'succeeded' | 'failed'
  started_at: string
  duration_ms: number
  summary: string
  error: string | null
  concepts: number
  variants: number
  flagged: number
  revisions: number
  provider: string
}

export interface RunEventRecord {
  agent: string
  phase: 'started' | 'finished' | 'failed'
  detail: string
  data?: Record<string, unknown>
}

export interface RunDetail extends Run {
  events: RunEventRecord[]
}

// -- trend scraping --------------------------------------------------------

export interface TrendSignal {
  query: string
  value: number
  rising: boolean
}

export interface TrendSource {
  id: number
  keyword: string
  geo: string
  enabled: boolean
  note: string | null
  last_scraped_at: string | null
  last_mode: 'never' | 'live' | 'offline' | 'failed'
  last_error: string | null
  last_signals: TrendSignal[]
}

export interface ScrapeResult {
  source_id: number
  keyword: string
  mode: 'live' | 'offline' | 'failed'
  chunks: number
  signals: TrendSignal[]
  error: string | null
}

export interface CorpusSource {
  source: string
  chunks: number
  heading: string
}

export interface TrendStatus {
  live: boolean
  geo: string
  trend_chunks: number
  company_chunks: number
  documents: CorpusSource[]
}
