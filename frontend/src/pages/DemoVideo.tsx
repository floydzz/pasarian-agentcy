import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { LogDrawer } from '@/components/os/LogDrawer'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { VideoPipeline } from '@/components/video/VideoPipeline'
import { ApiError, api } from '@/api/client'
import type { AgentName } from '@/api/stream'
import type {
  MarketingVideo,
  MarketingVideoCreate,
  MarketingVideoScene,
  VideoProfile,
  VideoSceneLayout,
} from '@/api/types'
import { useConsole } from '@/hooks/useConsole'
import { DEPTH } from '@/lib/motion'

const inputClass =
  'mt-2 w-full rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-[0.8125rem] leading-relaxed text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]'

const AGENTCY_DEMO_PRESET: MarketingVideoCreate = {
  name: 'Agentcy software explainer',
  profile: 'software_demo',
  brand_name: 'Agentcy',
  product_name: 'AI marketing campaign workspace',
  target_audience: 'Marketing teams who need a grounded, reviewable campaign workflow.',
  cta: 'Build your next campaign with Agentcy.',
  // Off, and not offered here: this video's subject is Agentcy's own screens,
  // and a generated backdrop behind a product walkthrough would be showing
  // footage of something that is not the product.
  use_broll: false,
  storyboard: [
    {
      eyebrow: 'Your marketing team, on demand',
      headline: 'Marketing should move at the speed of your ideas.',
      body: 'Agentcy turns your brand truth and a clear brief into a reviewable marketing campaign.',
      layout: 'hero',
    },
    {
      eyebrow: 'Start with what is true',
      headline: 'Set your brand profile.',
      body: 'Your company, products, claims and guardrails ground every agent before work begins.',
      layout: 'feature',
    },
    {
      eyebrow: 'One connected workflow',
      headline: 'Brief it. Make it. Review it.',
      body: 'The planner, copywriter, visual planner and director move the campaign forward together.',
      layout: 'workflow',
    },
    {
      eyebrow: 'Keep the decision',
      headline: 'Review before anything leaves.',
      body: 'Vision QA checks the creative first. Your team decides what is approved, redone or rejected.',
      layout: 'proof',
    },
    {
      eyebrow: 'Make the next campaign',
      headline: 'From clear brief to work worth sharing.',
      body: 'Grounded strategy, reviewable creative and a workflow your team can actually run.',
      layout: 'cta',
    },
  ],
}

function clonePreset(): MarketingVideoCreate {
  return structuredClone(AGENTCY_DEMO_PRESET)
}

function newScene(): MarketingVideoScene {
  return {
    eyebrow: 'A clear next step',
    headline: 'Show the value in one scene.',
    body: 'Explain the moment, feature or proof point this part of the video should carry.',
    layout: 'feature',
  }
}

/** The reusable, structured marketing-video pipeline. It opens on Agentcy's
 * own software-explainer preset, but every persisted storyboard is editable. */
export function DemoVideo() {
  const [draft, setDraft] = useState<MarketingVideoCreate>(clonePreset)
  const [videos, setVideos] = useState<MarketingVideo[]>([])
  const [actingOn, setActingOn] = useState<number | null>(null)
  const { log, agents, running, error, run, clearError } = useConsole()

  useEffect(() => {
    api.listVideos().then(setVideos).catch((error: ApiError) => toast.error(error.message))
  }, [])

  useEffect(() => {
    if (!error) return
    toast.error(error)
    clearError()
  }, [error, clearError])

  const lastDetail = useMemo(() => {
    const latest: Partial<Record<AgentName, string>> = {}
    for (const line of log) latest[line.agent] = line.detail
    return latest
  }, [log])

  const awaitingReview = videos.some((video) => video.review_status === 'pending')

  async function render(event: React.FormEvent) {
    event.preventDefault()
    if (running) return
    await run(
      'video studio',
      '/videos/render/stream',
      (result) => {
        const video = result as unknown as MarketingVideo
        setVideos((current) => [video, ...current])
        toast.success('Marketing video rendered — review it before sharing')
      },
      draft,
    )
  }

  async function act(video: MarketingVideo, action: 'approve' | 'reject' | 'redo') {
    if (actingOn !== null || running) return
    setActingOn(video.id)
    try {
      const changed =
        action === 'approve'
          ? await api.approveVideo(video.id)
          : action === 'reject'
            ? await api.rejectVideo(video.id)
            : await api.redoVideo(video.id)
      setVideos((current) => current.map((item) => (item.id === changed.id ? changed : item)))
      toast.success(
        action === 'redo'
          ? 'Video re-rendered from its saved storyboard'
          : action === 'approve'
            ? 'Video approved and ready to export'
            : 'Video marked as rejected',
      )
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setActingOn(null)
    }
  }

  function updateScene(index: number, patch: Partial<MarketingVideoScene>) {
    setDraft({
      ...draft,
      storyboard: draft.storyboard.map((scene, sceneIndex) =>
        sceneIndex === index ? { ...scene, ...patch } : scene,
      ),
    })
  }

  return (
    <Page>
      <PageHead
        title="Video studio"
        action={<p className="data shrink-0 text-text-3">vertical MP4 · 3 seconds per scene · review gate</p>}
      >
        A reusable marketing-video pipeline with the Agentcy software demo loaded as its default.
        Change the brand, product and storyboard to make another caption-led product video without
        changing the render, QA or export path.
      </PageHead>

      <motion.div
        className="mt-8"
        animate={{ scale: awaitingReview ? 0.975 : 1, opacity: awaitingReview ? 0.58 : 1 }}
        transition={DEPTH}
        style={{ transformOrigin: 'top center' }}
      >
        <VideoPipeline
          agents={agents}
          lastDetail={lastDetail}
          running={running !== null}
          awaitingReview={awaitingReview}
        />
      </motion.div>

      <VideoGate
        formId="video-config"
        running={running !== null}
        awaitingReview={awaitingReview}
        sceneCount={draft.storyboard.length}
        disabled={!isUsable(draft)}
      />

      <div className="mt-3">
        <LogDrawer log={log} running={running} />
      </div>

      <div className="mt-10 grid max-w-7xl gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(19rem,0.9fr)]">
        <form id="video-config" onSubmit={render} className="space-y-5 pb-12">
          <section className="glass rounded-xl px-5 py-5 sm:px-7 sm:py-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="display text-[0.9375rem]">Video brief</h2>
                <p className="mt-1.5 max-w-xl text-[0.8125rem] leading-relaxed text-text-3">
                  The preset is tuned for Agentcy’s software demo. It is still a full video brief,
                  so another product can use the same pipeline.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDraft(clonePreset())}
                className="rounded-full border border-edge px-3 py-1.5 text-[0.75rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
              >
                Load Agentcy preset
              </button>
            </div>

            <div className="mt-6 grid gap-5 sm:grid-cols-2">
              <Field label="Project name" htmlFor="video-name">
                <input
                  id="video-name"
                  value={draft.name}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Video profile" htmlFor="video-profile">
                <select
                  id="video-profile"
                  value={draft.profile}
                  onChange={(event) =>
                    setDraft({ ...draft, profile: event.target.value as VideoProfile })
                  }
                  className={inputClass}
                >
                  <option value="software_demo">Software explainer</option>
                  <option value="product_marketing">Product marketing</option>
                </select>
              </Field>
              <Field label="Brand" htmlFor="video-brand">
                <input
                  id="video-brand"
                  value={draft.brand_name}
                  onChange={(event) => setDraft({ ...draft, brand_name: event.target.value })}
                  className={inputClass}
                />
              </Field>
              <Field label="Product or offer" htmlFor="video-product">
                <input
                  id="video-product"
                  value={draft.product_name}
                  onChange={(event) => setDraft({ ...draft, product_name: event.target.value })}
                  className={inputClass}
                />
              </Field>
            </div>
            <div className="mt-5 space-y-5">
              <Field label="Target audience" htmlFor="video-audience">
                <textarea
                  id="video-audience"
                  rows={3}
                  value={draft.target_audience}
                  onChange={(event) => setDraft({ ...draft, target_audience: event.target.value })}
                  className={`${inputClass} resize-y`}
                />
              </Field>
              <Field label="Closing call to action" htmlFor="video-cta">
                <textarea
                  id="video-cta"
                  rows={2}
                  value={draft.cta}
                  onChange={(event) => setDraft({ ...draft, cta: event.target.value })}
                  className={`${inputClass} resize-y`}
                />
              </Field>
            </div>
          </section>

          <section className="glass rounded-xl px-5 py-5 sm:px-7 sm:py-6">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <h2 className="display text-[0.9375rem]">Storyboard</h2>
                <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-text-3">
                  {draft.storyboard.length} scenes · {draft.storyboard.length * 3} seconds. Each scene is
                  saved with the video, so re-rendering is reproducible.
                </p>
              </div>
              <span className="data text-text-3">3–8 scenes</span>
            </div>
            <div className="mt-6 space-y-4">
              {draft.storyboard.map((scene, index) => (
                <SceneEditor
                  key={index}
                  index={index}
                  scene={scene}
                  removable={draft.storyboard.length > 3}
                  onChange={(patch) => updateScene(index, patch)}
                  onRemove={() =>
                    setDraft({
                      ...draft,
                      storyboard: draft.storyboard.filter((_, sceneIndex) => sceneIndex !== index),
                    })
                  }
                />
              ))}
            </div>
            {draft.storyboard.length < 8 && (
              <button
                type="button"
                onClick={() => setDraft({ ...draft, storyboard: [...draft.storyboard, newScene()] })}
                className="mt-5 text-[0.8125rem] text-text-2 transition-colors hover:text-foreground"
              >
                + Add scene
              </button>
            )}
          </section>

          <p className="mt-3 text-[0.75rem] leading-relaxed text-text-3">
            The current renderer is deterministic motion graphics: it protects readable captions and product
            UI. Docker includes FFmpeg, so it needs no video-model API key.
          </p>
        </form>

        <section aria-label="Rendered marketing videos" className="space-y-5 pb-12">
          {videos.length === 0 ? (
            <EmptyVideo />
          ) : (
            videos.map((video) => (
              <VideoCard
                key={video.id}
                video={video}
                busy={actingOn === video.id || running !== null}
                onAct={act}
              />
            ))
          )}
        </section>
      </div>
    </Page>
  )
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="label">{label}</label>
      {children}
    </div>
  )
}

/** The review seam, in the same place the campaign console puts its gates.
 * The button submits the configuration form above through its id, so the
 * controls may sit visually beside the machine instead of at form-bottom. */
function VideoGate({
  formId,
  running,
  awaitingReview,
  sceneCount,
  disabled,
}: {
  formId: string
  running: boolean
  awaitingReview: boolean
  sceneCount: number
  disabled: boolean
}) {
  const headline = running
    ? 'The video agents hold the work'
    : awaitingReview
      ? 'A rendered video needs your decision'
      : 'Storyboard ready for a render'
  const detail = running
    ? 'Watch the stage above as the brief becomes a storyboard, vertical MP4 and QA review.'
    : awaitingReview
      ? 'Approve, reject or re-render from the saved storyboard below. The machine stays behind the gate.'
      : 'The current configuration will become a reviewable video; nothing is exported automatically.'
  return (
    <section
      className={`relative mt-3 overflow-hidden border-y px-5 py-3.5 sm:px-7 ${
        awaitingReview ? 'border-halt/25 bg-halt/[0.055]' : 'border-edge bg-[rgba(233,238,247,0.03)]'
      }`}
    >
      {awaitingReview && (
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px w-1/3 bg-gradient-to-r from-transparent via-halt to-transparent"
          animate={{ x: ['-100%', '400%'] }}
          transition={{ duration: 4.2, repeat: Infinity, ease: 'linear' }}
        />
      )}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-1 items-center gap-3.5">
          <span className={`h-2.5 w-2.5 shrink-0 rotate-45 border ${awaitingReview ? 'border-halt bg-halt' : 'border-[rgba(233,238,247,0.3)]'}`} />
          <div className="min-w-0">
            <p className={`display text-sm ${awaitingReview ? 'text-halt' : 'text-text-2'}`}>{headline}</p>
            <p className="mt-0.5 text-[0.6875rem] leading-relaxed text-text-3">{detail}</p>
          </div>
        </div>
        <button
          form={formId}
          type="submit"
          disabled={running || disabled}
          className={`display shrink-0 rounded-full px-5 py-2 text-[0.8125rem] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            awaitingReview ? 'bg-halt text-[#1a1206]' : 'bg-foreground text-void'
          }`}
        >
          {running ? 'Rendering…' : awaitingReview ? 'Render another video' : `Render ${sceneCount * 3}s video`}
        </button>
      </div>
    </section>
  )
}

function SceneEditor({
  index,
  scene,
  removable,
  onChange,
  onRemove,
}: {
  index: number
  scene: MarketingVideoScene
  removable: boolean
  onChange: (patch: Partial<MarketingVideoScene>) => void
  onRemove: () => void
}) {
  return (
    <article className="resolve rounded-lg border border-edge bg-[rgba(233,238,247,0.032)] p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="label text-text-3">Scene {String(index + 1).padStart(2, '0')}</p>
        {removable && (
          <button type="button" onClick={onRemove} className="text-[0.75rem] text-text-3 hover:text-foreground">
            Remove
          </button>
        )}
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,1fr)_11rem]">
        <Field label="Scene label" htmlFor={`scene-eyebrow-${index}`}>
          <input
            id={`scene-eyebrow-${index}`}
            value={scene.eyebrow}
            onChange={(event) => onChange({ eyebrow: event.target.value })}
            className={inputClass}
          />
        </Field>
        <Field label="Screen layout" htmlFor={`scene-layout-${index}`}>
          <select
            id={`scene-layout-${index}`}
            value={scene.layout}
            onChange={(event) => onChange({ layout: event.target.value as VideoSceneLayout })}
            className={inputClass}
          >
            <option value="hero">Hero</option>
            <option value="feature">Feature</option>
            <option value="workflow">Workflow</option>
            <option value="proof">Proof</option>
            <option value="cta">CTA</option>
          </select>
        </Field>
      </div>
      <div className="mt-4 space-y-4">
        <Field label="Headline" htmlFor={`scene-headline-${index}`}>
          <textarea
            id={`scene-headline-${index}`}
            rows={2}
            value={scene.headline}
            onChange={(event) => onChange({ headline: event.target.value })}
            className={`${inputClass} resize-y`}
          />
        </Field>
        <Field label="Supporting copy" htmlFor={`scene-body-${index}`}>
          <textarea
            id={`scene-body-${index}`}
            rows={3}
            value={scene.body}
            onChange={(event) => onChange({ body: event.target.value })}
            className={`${inputClass} resize-y`}
          />
        </Field>
      </div>
    </article>
  )
}

function EmptyVideo() {
  return (
    <div className="glass flex min-h-96 flex-col justify-end rounded-xl p-6 sm:p-8">
      <div className="mb-auto flex h-11 w-11 items-center justify-center rounded-full border border-edge bg-[rgba(233,238,247,0.04)] text-text-2">
        <PlayMark />
      </div>
      <h2 className="display mt-8 text-[1.05rem]">Your rendered videos will appear here.</h2>
      <p className="mt-2 max-w-sm text-[0.8125rem] leading-relaxed text-text-3">
        Each project stores its full brief and storyboard beside the vertical H.264 MP4, ready for review,
        download or a reproducible re-render.
      </p>
    </div>
  )
}

function VideoCard({
  video,
  busy,
  onAct,
}: {
  video: MarketingVideo
  busy: boolean
  onAct: (video: MarketingVideo, action: 'approve' | 'reject' | 'redo') => void
}) {
  const approved = video.review_status === 'approved'
  return (
    <article className="resolve glass overflow-hidden rounded-xl">
      <div className="grid sm:grid-cols-[minmax(0,0.7fr)_minmax(15rem,1.3fr)]">
        <video
          controls
          playsInline
          preload="metadata"
          poster={video.poster_url}
          src={video.media_url}
          className="aspect-[9/16] min-h-72 w-full bg-void object-cover"
        >
          Your browser cannot play this MP4. Download it instead.
        </video>
        <div className="flex min-w-0 flex-col px-5 py-5 sm:px-6 sm:py-6">
          <div className="flex items-start justify-between gap-3">
            <p className="data text-text-3">
              {video.duration_seconds}s · {video.scene_count} scenes · {profileLabel(video.profile)}
            </p>
            <StatusBadge status={video.review_status} />
          </div>
          <h2 className="display mt-4 text-[1.05rem] leading-snug">{video.name}</h2>
          <p className="mt-2 text-[0.8125rem] leading-relaxed text-text-2">
            {video.brand_name} · {video.product_name}
          </p>
          <p className="mt-3 text-[0.8125rem] leading-relaxed text-text-3">CTA: {video.cta}</p>

          <div className="mt-5 rounded-lg border border-edge bg-[rgba(233,238,247,0.035)] px-3.5 py-3">
            <p className="label text-text-3">Automated QA · {video.qa_status}</p>
            <p className="mt-1.5 text-[0.75rem] leading-relaxed text-text-2">
              {video.qa_notes ?? 'The representative closing frame passed the first QA check.'}
            </p>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            {!approved && (
              <>
                <ActionButton onClick={() => onAct(video, 'approve')} disabled={busy} primary>
                  Approve
                </ActionButton>
                <ActionButton onClick={() => onAct(video, 'redo')} disabled={busy}>
                  {busy ? 'Rendering…' : 'Re-render'}
                </ActionButton>
                <ActionButton onClick={() => onAct(video, 'reject')} disabled={busy} quiet>
                  Reject
                </ActionButton>
              </>
            )}
            {approved && (
              <a
                href={video.media_url}
                download={`${safeFilename(video.name)}.mp4`}
                className="display rounded-full bg-foreground px-4 py-2 text-[0.75rem] text-void transition-opacity hover:opacity-85"
              >
                Download MP4
              </a>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}

function ActionButton({
  primary = false,
  quiet = false,
  children,
  ...props
}: React.ComponentProps<'button'> & { primary?: boolean; quiet?: boolean }) {
  const styles = primary
    ? 'display rounded-full bg-foreground px-4 py-2 text-[0.75rem] text-void disabled:opacity-40'
    : quiet
      ? 'px-2 py-2 text-[0.75rem] text-text-3 transition-colors hover:text-foreground disabled:opacity-40'
      : 'rounded-full border border-edge px-4 py-2 text-[0.75rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground disabled:opacity-40'
  return <button type="button" className={styles} {...props}>{children}</button>
}

function StatusBadge({ status }: { status: MarketingVideo['review_status'] }) {
  const label = status === 'approved' ? 'approved' : status === 'rejected' ? 'rejected' : 'needs review'
  const color = status === 'approved'
    ? 'bg-[rgba(108,208,159,0.13)] text-[#a5e7c5]'
    : status === 'rejected'
      ? 'bg-[rgba(237,125,125,0.13)] text-[#f2b2b2]'
      : 'bg-[rgba(233,238,247,0.07)] text-text-2'
  return <span className={`data rounded-full px-2.5 py-1 ${color}`}>{label}</span>
}

function PlayMark() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden>
      <path d="M5 3.5 12 8l-7 4.5z" fill="currentColor" />
    </svg>
  )
}

function profileLabel(profile: VideoProfile) {
  return profile === 'software_demo' ? 'software explainer' : 'product marketing'
}

function safeFilename(value: string) {
  return value.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-').replaceAll(/^-|-$/g, '') || 'marketing-video'
}

function isUsable(draft: MarketingVideoCreate) {
  return Boolean(
    draft.name.trim()
      && draft.brand_name.trim()
      && draft.product_name.trim()
      && draft.target_audience.trim()
      && draft.cta.trim()
      && draft.storyboard.length >= 3
      && draft.storyboard.every((scene) => scene.eyebrow.trim() && scene.headline.trim() && scene.body.trim()),
  )
}
