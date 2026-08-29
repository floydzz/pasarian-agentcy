import { cn } from '@/lib/utils'
import type { MarketingVideo } from '@/api/types'

/** One rendered cut, waiting on a decision.
 *
 * The video keeps a light frame around it the way a creative does elsewhere in
 * the product: the thing the machine made must never dissolve into the
 * instrument that made it.
 */
export function CutCard({
  video,
  busy,
  onApprove,
  onReject,
  onRedo,
}: {
  video: MarketingVideo
  busy: boolean
  onApprove: () => void
  onReject: () => void
  onRedo: () => void
}) {
  const decided = video.review_status !== 'pending'

  return (
    <article className="glass flex h-full w-full flex-col overflow-hidden rounded-xl">
      <video
        controls
        playsInline
        preload="metadata"
        poster={video.poster_url}
        src={video.media_url}
        className="aspect-[9/16] max-h-[18rem] w-full shrink-0 bg-void object-contain"
      >
        Your browser cannot play this MP4.
      </video>

      <div className="flex min-h-0 flex-1 flex-col px-4 py-3.5">
        <div className="flex items-start justify-between gap-3">
          <p className="data text-text-3">
            {video.duration_seconds}s · {video.scene_count} scenes
          </p>
          <span
            className={cn(
              'data shrink-0',
              video.review_status === 'approved'
                ? 'text-go'
                : video.review_status === 'rejected'
                  ? 'text-flag'
                  : 'text-halt',
            )}
          >
            {video.review_status}
          </span>
        </div>

        <p
          className={cn(
            'mt-2 line-clamp-3 text-[0.75rem] leading-relaxed',
            video.qa_status === 'flagged' ? 'text-flag' : 'text-text-2',
          )}
        >
          {video.qa_notes ?? 'Vision QA passed this cut.'}
        </p>

        {!decided && (
          <div className="mt-auto flex flex-wrap gap-2 pt-3">
            <Action onClick={onApprove} disabled={busy} tone="go">
              Approve
            </Action>
            <Action onClick={onRedo} disabled={busy}>
              Render again
            </Action>
            <Action onClick={onReject} disabled={busy} tone="flag">
              Reject
            </Action>
          </div>
        )}
      </div>
    </article>
  )
}

function Action({
  onClick,
  disabled,
  tone,
  children,
}: {
  onClick: () => void
  disabled: boolean
  tone?: 'go' | 'flag'
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-full border px-3 py-1.5 text-[0.75rem] transition-colors disabled:cursor-not-allowed disabled:opacity-40',
        tone === 'go'
          ? 'border-go/40 text-go hover:bg-go/10'
          : tone === 'flag'
            ? 'border-flag/40 text-flag hover:bg-flag/10'
            : 'border-edge-strong text-text-2 hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}
