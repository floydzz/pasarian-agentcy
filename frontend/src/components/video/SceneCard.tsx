import { cn } from '@/lib/utils'
import type { MarketingVideoScene, VideoSceneLayout } from '@/api/types'

const field =
  'w-full rounded-lg border border-edge bg-[rgba(233,238,247,0.035)] px-3 py-2 text-[0.8125rem] leading-relaxed text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-video/60 focus:bg-[rgba(233,238,247,0.07)]'

const LAYOUTS: { value: VideoSceneLayout; label: string }[] = [
  { value: 'hero', label: 'Hero' },
  { value: 'feature', label: 'Feature' },
  { value: 'workflow', label: 'Workflow' },
  { value: 'proof', label: 'Proof' },
  { value: 'cta', label: 'Call to action' },
]

/** One beat of the storyboard, editable in place.
 *
 * The storyboard is the video's plan, and unlike an image concept no agent
 * proposed it — a person writes it. So the card is a form rather than a
 * verdict to accept or reject, and it sits in the same filmstrip the image
 * studio's concepts sit in, at the same size, in the same rhythm.
 */
export function SceneCard({
  index,
  scene,
  removable,
  busy,
  onChange,
  onRemove,
}: {
  index: number
  scene: MarketingVideoScene
  removable: boolean
  busy: boolean
  onChange: (patch: Partial<MarketingVideoScene>) => void
  onRemove: () => void
}) {
  return (
    <article className="glass flex h-full w-full flex-col overflow-hidden rounded-xl">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-edge px-4 py-2.5">
        <span className="data text-video">scene {String(index + 1).padStart(2, '0')}</span>
        {removable && (
          <button
            type="button"
            onClick={onRemove}
            disabled={busy}
            className="text-[0.75rem] text-text-3 transition-colors hover:text-foreground disabled:opacity-40"
          >
            Remove
          </button>
        )}
      </header>

      <div className="quiet-scroll flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
        <Labelled label="Scene label">
          <input
            value={scene.eyebrow}
            disabled={busy}
            onChange={(event) => onChange({ eyebrow: event.target.value })}
            className={field}
          />
        </Labelled>
        <Labelled label="Headline">
          <textarea
            rows={2}
            value={scene.headline}
            disabled={busy}
            onChange={(event) => onChange({ headline: event.target.value })}
            className={cn(field, 'resize-none')}
          />
        </Labelled>
        <Labelled label="Supporting copy">
          <textarea
            rows={3}
            value={scene.body}
            disabled={busy}
            onChange={(event) => onChange({ body: event.target.value })}
            className={cn(field, 'resize-none')}
          />
        </Labelled>
        <Labelled label="Screen layout">
          <select
            value={scene.layout}
            disabled={busy}
            onChange={(event) => onChange({ layout: event.target.value as VideoSceneLayout })}
            className={field}
          >
            {LAYOUTS.map((layout) => (
              <option key={layout.value} value={layout.value}>
                {layout.label}
              </option>
            ))}
          </select>
        </Labelled>
      </div>
    </article>
  )
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">{label}</span>
      {children}
    </label>
  )
}

/** The card that adds a beat. It is a card rather than a button above the
 * strip so the storyboard reads as one continuous piece of film. */
export function AddSceneCard({ onAdd, disabled }: { onAdd: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onAdd}
      disabled={disabled}
      className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-edge-strong text-text-3 transition-colors hover:border-video/60 hover:text-video disabled:cursor-not-allowed disabled:opacity-40"
    >
      <svg viewBox="0 0 16 16" className="h-5 w-5" aria-hidden>
        <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span className="text-[0.8125rem]">Add a scene</span>
    </button>
  )
}
