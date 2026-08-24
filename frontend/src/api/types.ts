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

export interface VisualBrief {
  composition_notes: string
  image_prompt: string
  text_placement: string
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

// -- the machine itself ----------------------------------------------------

export interface System {
  llm_provider: string
  embedding_provider: string
  trends_live: boolean
  geo: string
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
}

// -- history ---------------------------------------------------------------

export interface Run {
  id: number
  campaign_id: number | null
  campaign_name: string
  kind: 'plan' | 'generate'
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
