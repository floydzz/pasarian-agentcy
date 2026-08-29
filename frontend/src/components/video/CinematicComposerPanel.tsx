import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import { cn } from '@/lib/utils'
import type { Campaign, CinematicTrailer, CinematicTrailerCreate, MarketingVideoCreate } from '@/api/types'

/** The campaign-facing cinematic room. It consumes the editable storyboard
 * from Video Studio, turns each beat into a durable AI clip job, and keeps the
 * resulting clips plus the local composition pass together. */
export function CinematicComposerPanel({ campaign, script }: { campaign: Campaign; script: MarketingVideoCreate }) {
  const [trailers, setTrailers] = useState<CinematicTrailer[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const current = useMemo(
    () => trailers.find((trailer) => trailer.id === selected) ?? trailers[0] ?? null,
    [selected, trailers],
  )
  const hasActiveShots = Boolean(current?.shots.some(
    (shot) => shot.provider_status === 'pending' || shot.provider_status === 'running',
  ))
  const hasFinishedShots = Boolean(current?.shots.some(
    (shot) => shot.provider_status === 'succeeded' || shot.provider_status === 'failed',
  ))

  const refresh = useCallback(async () => {
    const rows = await api.listCinematicTrailers(campaign.id)
    setTrailers(rows)
    setSelected((value) => value ?? rows[0]?.id ?? null)
  }, [campaign.id])

  const replace = useCallback((trailer: CinematicTrailer) => {
    setTrailers((rows) => {
      const existing = rows.some((row) => row.id === trailer.id)
      return existing ? rows.map((row) => (row.id === trailer.id ? trailer : row)) : [trailer, ...rows]
    })
    setSelected(trailer.id)
  }, [])

  useEffect(() => {
    refresh().catch((error: ApiError) => toast.error(error.message))
  }, [refresh])

  useEffect(() => {
    if (current?.status !== 'generating' || busy) return
    const timer = window.setInterval(() => {
      api.refreshCinematicTrailer(current.id).then(replace).catch(() => undefined)
    }, 12_000)
    return () => window.clearInterval(timer)
  }, [busy, current?.id, current?.status, replace])

  const act = async (work: () => Promise<CinematicTrailer>, message: string) => {
    setBusy(true)
    try {
      replace(await work())
      toast.success(message)
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="px-5 pt-4 pb-8 sm:px-8">
      <div className="rounded-xl border border-video/30 bg-video/[0.045] p-5">
        <p className="label text-video">AI clips & composition</p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="display text-[1.0625rem]">Turn this storyboard into a cinematic film</h2>
            <p className="mt-1 max-w-2xl text-[0.8125rem] leading-relaxed text-text-2">
              The {script.storyboard.length}-beat script for {campaign.name} becomes one durable clip job per scene. You can leave this page and follow its status in Progress while the provider works.
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => void act(() => api.createCinematicTrailer(blueprint(campaign, script)), 'Cinematic clip plan created from your script')}
            className="shrink-0 rounded-full bg-video px-4 py-2 text-[0.75rem] font-medium text-void disabled:opacity-40"
          >
            Create clip plan
          </button>
        </div>
      </div>

      {trailers.length > 1 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {trailers.map((trailer) => (
            <button
              type="button"
              key={trailer.id}
              onClick={() => setSelected(trailer.id)}
              className={cn('data rounded-full border px-3 py-1.5', current?.id === trailer.id ? 'border-video text-video' : 'border-edge text-text-3')}
            >
              {trailer.title}
            </button>
          ))}
        </div>
      )}

      {!current ? (
        <p className="mt-10 text-sm text-text-3">Create a clip plan when the script is ready. No generation is billed until you choose Generate clips.</p>
      ) : (
        <>
          <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="display text-[1rem]">{current.title}</p>
              <p className="data mt-1 text-text-3">{current.duration_seconds}s · {current.shots.length} clips · {current.status.replaceAll('_', ' ')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(current.status === 'draft' || current.status === 'failed') && <Action busy={busy} onClick={() => void act(() => api.submitCinematicTrailer(current.id), 'AI clip generation started')}>Generate clips</Action>}
              {current.status === 'generating' && <Action busy={busy} onClick={() => void act(() => api.refreshCinematicTrailer(current.id), 'Clip progress refreshed')}>Refresh clips</Action>}
              {current.status === 'ready_to_compose' && <Action busy={busy} onClick={() => void act(() => api.composeCinematicTrailer(current.id), 'Cinematic master composed')}>Compose master</Action>}
              {current.status === 'rendered' && current.review_status === 'pending' && <Action busy={busy} tone="go" onClick={() => void act(() => api.approveCinematicTrailer(current.id), 'Cinematic film approved')}>Approve film</Action>}
              {hasFinishedShots && !hasActiveShots && <Action busy={busy} onClick={() => void act(() => api.regenerateAllCinematicTrailerShots(current.id), 'New takes submitted with the saved campaign script')}>Regenerate all takes · billed</Action>}
            </div>
          </div>

          <p className="mt-3 text-[0.75rem] text-text-3">
            Regeneration keeps each clip’s saved title, prompt, duration, narration and audio direction. It changes the take, not the approved storyboard.
          </p>

          {current.media_url && <video controls playsInline src={current.media_url} poster={current.poster_url ?? undefined} className="mt-5 aspect-video w-full rounded-xl bg-black object-contain" />}

          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {current.shots.map((shot) => (
              <article key={shot.id} className="overflow-hidden rounded-xl border border-edge bg-rise">
                {shot.media_url ? <video controls playsInline preload="metadata" src={shot.media_url} className="aspect-video w-full bg-black object-cover" /> : <div className="flex aspect-video items-end bg-video/[0.06] p-3"><span className="data text-text-3">Clip {String(shot.position).padStart(2, '0')}</span></div>}
                <div className="p-3.5">
                  <div className="flex justify-between gap-2"><span className="data text-text-3">{shot.duration_seconds}s · {shot.mode.replaceAll('_', ' ')}</span><span className={cn('data', shot.provider_status === 'failed' ? 'text-flag' : shot.provider_status === 'succeeded' ? 'text-go' : 'text-video')}>{shot.provider_status}</span></div>
                  <p className="display mt-2 text-[0.875rem]">{shot.title_card}</p>
                  {shot.provider_error && <p className="mt-2 text-[0.6875rem] leading-relaxed text-flag">{shot.provider_error}</p>}
                  {(shot.provider_status === 'succeeded' || shot.provider_status === 'failed') && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void act(
                        () => api.regenerateCinematicTrailerShot(current.id, shot.id),
                        'New take submitted with the saved campaign script',
                      )}
                      className="mt-3 rounded-full border border-video/50 px-3 py-1.5 text-[0.6875rem] text-video transition-colors hover:bg-video/10 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Regenerate take · billed
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

function Action({ busy, onClick, tone, children }: { busy: boolean; onClick: () => void; tone?: 'go'; children: React.ReactNode }) {
  return <button type="button" disabled={busy} onClick={onClick} className={cn('rounded-full border px-3.5 py-2 text-[0.75rem] disabled:opacity-40', tone === 'go' ? 'border-go/50 text-go hover:bg-go/10' : 'border-video/50 text-video hover:bg-video/10')}>{children}</button>
}

function blueprint(campaign: Campaign, script: MarketingVideoCreate): CinematicTrailerCreate {
  return {
    campaign_id: campaign.id,
    title: `${campaign.name} — cinematic film`,
    aspect_ratio: '9:16',
    cta: script.cta,
    shots: script.storyboard.map((scene, index) => ({
      label: `Beat ${index + 1}: ${scene.eyebrow}`,
      title_card: scene.headline,
      prompt: `Cinematic premium marketing film for ${script.brand_name}. Product: ${script.product_name}. Audience: ${script.target_audience}. Scene direction: ${scene.body}. Layout intention: ${scene.layout}. Elegant editorial lighting, refined movement, coherent visual continuity, no on-screen text except the title card added in composition.`,
      mode: 'text_to_video',
      duration_seconds: 8,
      voiceover: scene.body,
      audio_cue: index === script.storyboard.length - 1 ? 'Music resolves, warm final hit.' : 'Polished cinematic rhythm, subtly building.',
    })),
  }
}
