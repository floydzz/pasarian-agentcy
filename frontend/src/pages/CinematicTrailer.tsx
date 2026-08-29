import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { api, ApiError } from '@/api/client'
import { cn } from '@/lib/utils'
import type { CinematicTrailer, CinematicTrailerShot, System } from '@/api/types'

/** The long-form AI-video room.
 *
 * This is intentionally task-oriented rather than a spinner around one big
 * request: each generated shot is a paid remote job and stays visible,
 * resumable and reviewable while the rest of the trailer is still running.
 */
export function CinematicTrailer() {
  const [trailers, setTrailers] = useState<CinematicTrailer[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [system, setSystem] = useState<System | null>(null)
  const [busy, setBusy] = useState(false)
  const captureInput = useRef<HTMLInputElement>(null)
  const productInput = useRef<HTMLInputElement>(null)
  const soundtrackInput = useRef<HTMLInputElement>(null)

  const current = useMemo(
    () => trailers.find((trailer) => trailer.id === selected) ?? trailers[0] ?? null,
    [selected, trailers],
  )
  const usesAiNativeProductScenes = Boolean(current?.shots.some(
    (shot) => shot.mode === 'reference_to_video' && shot.product_surface !== 'none' && !shot.protect_reference,
  ))
  const hasActiveShots = Boolean(current?.shots.some(
    (shot) => shot.provider_status === 'pending' || shot.provider_status === 'running',
  ))
  const hasFinishedShots = Boolean(current?.shots.some(
    (shot) => shot.provider_status === 'succeeded' || shot.provider_status === 'failed',
  ))
  const progress = useMemo(() => {
    if (!current) return null
    const counts = current.shots.reduce(
      (total, shot) => {
        total[shot.provider_status] += 1
        return total
      },
      { draft: 0, pending: 0, running: 0, succeeded: 0, failed: 0 },
    )
    const active = counts.pending + counts.running
    const ready = counts.succeeded + counts.failed
    return {
      ...counts,
      active,
      ready,
      percent: Math.round((ready / current.shots.length) * 100),
    }
  }, [current])

  const refreshList = useCallback(async () => {
    const rows = await api.listCinematicTrailers()
    setTrailers(rows)
    setSelected((id) => id ?? rows[0]?.id ?? null)
  }, [])

  useEffect(() => {
    refreshList().catch((error: ApiError) => toast.error(error.message))
    api.system().then(setSystem).catch(() => setSystem(null))
  }, [refreshList])

  const replace = (trailer: CinematicTrailer) => {
    setTrailers((current) => {
      const found = current.some((item) => item.id === trailer.id)
      return found ? current.map((item) => (item.id === trailer.id ? trailer : item)) : [trailer, ...current]
    })
    setSelected(trailer.id)
  }

  const act = async (operation: () => Promise<CinematicTrailer>, notice: string) => {
    setBusy(true)
    try {
      replace(await operation())
      toast.success(notice)
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  const attachCapture = (file: File | undefined) => {
    if (!file || !current) return
    if (file.type !== 'video/mp4') {
      toast.error('Choose an MP4 screen recording.')
      return
    }
    if (file.size > 120 * 1024 * 1024) {
      toast.error('The UI recording must be 120 MB or smaller.')
      return
    }
    const reader = new FileReader()
    reader.onerror = () => toast.error('Could not read that UI recording.')
    reader.onload = () => {
      const dataUrl = reader.result
      if (typeof dataUrl !== 'string') {
        toast.error('Could not read that UI recording.')
        return
      }
      void act(
        () => api.uploadCinematicTrailerCapture(current.id, dataUrl),
        'Real UI recording attached for screen replacement',
      )
    }
    reader.readAsDataURL(file)
  }

  /** A product photo is kept out of the video model. The finishing pass lays
   * the original pixels into the generated scene, which is how a label remains
   * readable instead of becoming a plausible-but-wrong AI recreation. */
  const attachProduct = (file: File | undefined) => {
    if (!file || !current) return
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      toast.error('Choose a PNG, JPEG, or WEBP product image.')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error('The product image must be 20 MB or smaller.')
      return
    }
    const reader = new FileReader()
    reader.onerror = () => toast.error('Could not read that product image.')
    reader.onload = () => {
      const dataUrl = reader.result
      if (typeof dataUrl !== 'string') {
        toast.error('Could not read that product image.')
        return
      }
      void act(
        () => api.uploadCinematicTrailerProductReference(current.id, dataUrl),
        'Product lock attached for cinematic composition',
      )
    }
    reader.readAsDataURL(file)
  }

  const attachSoundtrack = (file: File | undefined) => {
    if (!file || !current) return
    const allowed = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav']
    if (!allowed.includes(file.type)) {
      toast.error('Choose an MP3 or WAV instrumental track.')
      return
    }
    if (file.size > 50 * 1024 * 1024) {
      toast.error('The soundtrack must be 50 MB or smaller.')
      return
    }
    const reader = new FileReader()
    reader.onerror = () => toast.error('Could not read that soundtrack.')
    reader.onload = () => {
      const dataUrl = reader.result
      if (typeof dataUrl !== 'string') {
        toast.error('Could not read that soundtrack.')
        return
      }
      void act(
        () => api.uploadCinematicTrailerSoundtrack(current.id, dataUrl),
        'Soundtrack attached — it will be mixed continuously across the final cut',
      )
    }
    reader.readAsDataURL(file)
  }

  // The provider's task is durable. Polling is a refresh, not a long-lived
  // browser request, so closing the page never loses a paid render.
  useEffect(() => {
    if (!current || current.status !== 'generating' || busy) return
    const timer = window.setInterval(() => {
      api.refreshCinematicTrailer(current.id).then(replace).catch(() => undefined)
    }, 15_000)
    return () => window.clearInterval(timer)
  }, [busy, current?.id, current?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Page>
      <PageHead
        title="Cinematic trailer"
        action={<span className="data shrink-0 text-video">AI shots · 16:9 · 120 seconds</span>}
      >
        Generate Agentcy’s long-form product film shot by shot. A guided recording supplies the exact UI state for every feature scene; the resulting reference-to-video clips remain fully AI-generated.
      </PageHead>

      <section className="glass mt-8 flex flex-wrap items-center justify-between gap-5 rounded-xl px-5 py-5 sm:px-7">
        <div>
          <p className="display text-[0.9375rem]">The Network Woke Up</p>
          <p className="mt-1 text-[0.8125rem] text-text-3">
            A two-minute product narrative: threat-story opening, a seamless Agentcy feature tour, then the original fourth-wall ending.
          </p>
          {!system?.broll_available && (
            <p className="mt-2 text-[0.75rem] text-halt">
              Configure DashScope video generation before submitting shots.
            </p>
          )}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => act(api.createCinematicTrailer, 'Two-minute trailer storyboard created')}
          className="rounded-full bg-video px-4 py-2 text-[0.75rem] font-medium text-void transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          New Agentcy trailer
        </button>
      </section>

      {!current ? (
        <Empty />
      ) : (
        <>
          <section className="mt-6 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="display text-lg">{current.title}</p>
              <p className="data mt-1 text-text-3">
                {current.duration_seconds}s · {current.shots.length} shots · {current.aspect_ratio} · {current.status.replaceAll('_', ' ')}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                ref={captureInput}
                type="file"
                accept="video/mp4"
                className="hidden"
                onChange={(event) => {
                  attachCapture(event.target.files?.[0])
                  event.currentTarget.value = ''
                }}
              />
              <input
                ref={productInput}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(event) => {
                  attachProduct(event.target.files?.[0])
                  event.currentTarget.value = ''
                }}
              />
              <input
                ref={soundtrackInput}
                type="file"
                accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,.mp3,.wav"
                className="hidden"
                onChange={(event) => {
                  attachSoundtrack(event.target.files?.[0])
                  event.currentTarget.value = ''
                }}
              />
              <Action busy={busy} onClick={() => productInput.current?.click()}>
                {current.product_reference_url ? 'Replace product image' : 'Attach product image'}
              </Action>
              <Action busy={busy} onClick={() => captureInput.current?.click()}>
                {current.application_capture_url ? 'Replace UI recording' : 'Attach real UI recording'}
              </Action>
              <Action busy={busy} onClick={() => soundtrackInput.current?.click()}>
                {current.soundtrack_url ? 'Replace soundtrack' : 'Attach soundtrack'}
              </Action>
              {current.status === 'draft' || current.status === 'failed' ? (
                <Action busy={busy} disabled={!current.application_capture_url} onClick={() => act(() => api.submitCinematicTrailer(current.id), 'AI shots submitted')}>Generate shots · billed</Action>
              ) : null}
              {current.status === 'generating' ? (
                <Action busy={busy} onClick={() => act(() => api.refreshCinematicTrailer(current.id), 'Shot progress refreshed')}>Refresh progress</Action>
              ) : null}
              {current.status === 'ready_to_compose' ? (
                <Action busy={busy} onClick={() => act(() => api.composeCinematicTrailer(current.id), 'Trailer composed and ready for review')}>Compose master</Action>
              ) : null}
              {current.status === 'rendered' && current.review_status === 'pending' ? (
                <Action busy={busy} tone="go" onClick={() => act(() => api.approveCinematicTrailer(current.id), 'Trailer approved')}>Approve trailer</Action>
              ) : null}
              {hasFinishedShots && !hasActiveShots ? (
                <Action busy={busy} onClick={() => act(() => api.regenerateAllCinematicTrailerShots(current.id), 'New takes submitted with the saved script and UI mapping')}>Regenerate all takes · billed</Action>
              ) : null}
            </div>
          </section>

          <p className={cn('mt-3 text-[0.75rem]', current.application_capture_url ? 'text-go' : 'text-text-3')}>
            {current.product_reference_url
              ? 'Product lock is active for its intended story beats. Agentcy feature scenes remain AI-generated from their saved UI references.'
              : current.application_capture_url
              ? 'Exact UI reference is active: Agentcy extracts a feature-specific still for the AI model. The final master preserves the generated clip—no UI screenshot is pasted over it.'
              : usesAiNativeProductScenes
              ? 'A guided Agentcy recording is required before billed generation. It gives the model a real product state instead of a generic invented dashboard.'
              : 'Attach a short Agentcy screen recording before composing to replace static UI inserts with a moving product journey.'}
          </p>

          {!current.application_capture_url && usesAiNativeProductScenes && (
            <section className="mt-4 rounded-xl border border-video/30 bg-video/[0.045] px-5 py-4">
              <p className="label text-video">Guided capture required before generation</p>
              <p className="mt-2 text-[0.8125rem] leading-relaxed text-text-2">
                Record one 16:9 MP4 journey in this order: Marketing strategist, Brand profile, Campaigns, Image Studio, Video Studio, Progress, creative approval, Publish, then History. Hold each screen for about five seconds. Agentcy maps those moments to the matching trailer scenes automatically.
              </p>
            </section>
          )}

          <p className={cn('mt-3 text-[0.75rem]', current.soundtrack_url ? 'text-go' : 'text-text-3')}>
            {current.soundtrack_url
              ? 'Continuous soundtrack attached. The composer loops, fades and ducks it under native clip audio across the finished master.'
              : 'Optional: attach an MP3 or WAV instrumental after it is licensed or generated. It is mixed into the master without regenerating clips.'}
          </p>

          {progress && current.status !== 'draft' && (
            <section className="glass mt-5 rounded-xl px-5 py-4 sm:px-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="label text-video">Trailer progress</p>
                  <p className="display mt-1 text-[0.9375rem]">
                    {current.status === 'ready_to_compose'
                      ? 'Every clip is ready for the master cut'
                      : current.status === 'rendered'
                        ? 'Master trailer rendered'
                        : `${progress.ready} of ${current.shots.length} shots finished`}
                  </p>
                </div>
                <span className="data text-video">{progress.percent}% complete</span>
              </div>

              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-edge">
                <div
                  className="h-full rounded-full bg-video transition-[width] duration-500"
                  style={{ width: `${progress.percent}%` }}
                />
              </div>

              <div className="mt-4 grid gap-2 text-[0.75rem] sm:grid-cols-4">
                <ProgressMetric label="Completed" value={progress.succeeded} tone="text-go" />
                <ProgressMetric label="Generating" value={progress.active} tone="text-video" />
                <ProgressMetric label="Queued" value={progress.draft} tone="text-text-2" />
                <ProgressMetric label="Needs retry" value={progress.failed} tone={progress.failed ? 'text-flag' : 'text-text-3'} />
              </div>

              <p className="mt-4 text-[0.75rem] leading-relaxed text-text-3">
                {current.status === 'generating'
                  ? 'This view refreshes automatically. As provider slots free up, Agentcy submits the next saved shot without changing your script.'
                  : current.status === 'ready_to_compose'
                    ? 'All visual takes are available. Compose master joins the AI-generated clips and any attached soundtrack.'
                    : current.status === 'rendered'
                      ? 'The full trailer is ready above. Regenerate a take only if you want a different visual result.'
                      : 'Generation is paused. Review the clip errors below, then retry the affected take.'}
              </p>
            </section>
          )}

          {current.media_url && (
            <section className="glass mt-6 overflow-hidden rounded-xl">
              <video controls playsInline poster={current.poster_url ?? undefined} src={current.media_url} className="aspect-video w-full bg-void object-contain">
                Your browser cannot play this MP4.
              </video>
            </section>
          )}

          <section className="mt-6 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {current.shots.map((shot) => (
              <ShotCard
                key={shot.id}
                shot={shot}
                busy={busy}
                onRegenerate={() => act(
                  () => api.regenerateCinematicTrailerShot(current.id, shot.id),
                  'New take submitted with the saved script and exact UI mapping',
                )}
              />
            ))}
          </section>
        </>
      )}
    </Page>
  )
}

function Empty() {
  return (
    <div className="mt-16 max-w-xl rounded-xl border border-dashed border-edge-strong px-6 py-10 text-center">
      <p className="display text-[0.9375rem]">Start with the finished trailer blueprint.</p>
      <p className="mt-2 text-[0.8125rem] leading-relaxed text-text-3">
        Creating it saves every shot, prompt, audio cue and voiceover before any model work begins.
      </p>
    </div>
  )
}

function ProgressMetric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-edge bg-void/20 px-3 py-2">
      <span className="text-text-3">{label}</span>
      <span className={cn('data', tone)}>{value}</span>
    </div>
  )
}

function ShotCard({ shot, busy, onRegenerate }: { shot: CinematicTrailerShot; busy: boolean; onRegenerate: () => void }) {
  const succeeded = shot.provider_status === 'succeeded'
  return (
    <article className="glass overflow-hidden rounded-xl">
      {shot.media_url ? (
        <video controls playsInline preload="metadata" src={shot.media_url} className="aspect-video w-full bg-void object-cover" />
      ) : (
        <div className="flex aspect-video items-end bg-[radial-gradient(circle_at_50%_20%,rgba(176,140,255,0.16),transparent_55%)] p-4">
          <span className="data text-text-3">AI shot {String(shot.position).padStart(2, '0')}</span>
        </div>
      )}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <p className="data text-text-3">{String(shot.position).padStart(2, '0')} · {shot.duration_seconds}s · {shot.mode.replaceAll('_', ' ')}</p>
          <span className={cn('data shrink-0', succeeded ? 'text-go' : shot.provider_status === 'failed' ? 'text-flag' : 'text-video')}>
            {shot.provider_status}
          </span>
        </div>
        <h2 className="display mt-3 text-[0.9375rem]">{shot.title_card}</h2>
        <p className="mt-2 line-clamp-3 text-[0.75rem] leading-relaxed text-text-3">{shot.voiceover}</p>
        {shot.product_surface !== 'none' && <p className="mt-3 text-[0.6875rem] text-video">Agentcy {shot.product_surface.replaceAll('_', ' ')} interface reference</p>}
        {shot.provider_error && <p className="mt-3 text-[0.75rem] leading-relaxed text-flag">{shot.provider_error}</p>}
        {(shot.provider_status === 'succeeded' || shot.provider_status === 'failed') && (
          <button
            type="button"
            disabled={busy}
            onClick={onRegenerate}
            className="mt-4 rounded-full border border-video/50 px-3 py-1.5 text-[0.6875rem] text-video transition-colors hover:bg-video/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Regenerate take · billed
          </button>
        )}
      </div>
    </article>
  )
}

function Action({ onClick, busy, disabled = false, tone, children }: { onClick: () => void; busy: boolean; disabled?: boolean; tone?: 'go'; children: React.ReactNode }) {
  return (
    <button type="button" disabled={busy || disabled} onClick={onClick} className={cn(
      'rounded-full border px-4 py-2 text-[0.75rem] transition-colors disabled:cursor-not-allowed disabled:opacity-40',
      tone === 'go' ? 'border-go/50 text-go hover:bg-go/10' : 'border-video/50 text-video hover:bg-video/10',
    )}>
      {children}
    </button>
  )
}
