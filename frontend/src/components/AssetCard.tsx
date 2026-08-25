import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { Asset, Variant } from '@/api/types'

/** One finished creative, at the gate.
 *
 * The image is the work, so it gets the whole top of the card at its real
 * aspect and nothing is laid over it. Everything the machine says *about* the
 * creative — QA's verdict, the director's earlier one — stays underneath,
 * small and grey, in the same register `VariantCard` uses.
 *
 * A flagged asset is visibly flagged rather than mixed in with the passes. The
 * point of QA running before a human is that a reviewer's attention lands
 * where it is worth spending, and that only works if the screen says where. */
export function AssetCard({
  asset,
  variant,
  busy,
  onApprove,
  onReject,
  onRedo,
}: {
  asset: Asset
  variant?: Variant
  busy: boolean
  onApprove: () => void
  onReject: () => void
  // Awaited, so the button can say `Rendering…` for the whole round trip.
  onRedo: () => void | Promise<void>
}) {
  const [redoing, setRedoing] = useState(false)
  const flagged = asset.qa_status === 'flagged'
  const decided = asset.review_status !== 'pending'

  return (
    <article
      className={cn(
        'on-paper flex h-full w-full flex-col overflow-hidden rounded-2xl bg-paper shadow-[0_18px_44px_-28px_rgba(0,0,0,0.9)]',
        flagged && 'ring-1 ring-flag/40',
      )}
    >
      {/* Capped rather than left at its full square: the whole point of the
          gate is the three buttons under it, and a card whose actions start
          below the fold is a card nobody acts on. */}
      <div className="max-h-[52%] w-full shrink-0 overflow-hidden">
        <img
          src={asset.media_url}
          alt={variant ? `Creative for “${variant.headline}”` : 'Generated creative'}
          className="aspect-square w-full object-cover"
          loading="lazy"
        />
      </div>

      <div className="quiet-scroll fade-b min-h-0 flex-1 overflow-y-auto px-6 pt-4 pb-5">
        <div className="flex items-center justify-between gap-3">
          <span className="data truncate text-text-3">
            {variant?.hook_type ?? `variant ${asset.variant_id}`}
          </span>
          <span
            className={cn(
              'text-[0.6875rem] whitespace-nowrap',
              flagged ? 'text-flag' : 'text-go',
            )}
          >
            {flagged ? 'QA flagged' : 'QA passed'}
          </span>
        </div>

        {flagged && asset.qa_notes && (
          <p className="mt-3 rounded-lg bg-flag/10 px-3.5 py-2.5 text-[0.8125rem] leading-relaxed">
            <span className="label text-flag">Quality checker</span>
            <br />
            {asset.qa_notes}
          </p>
        )}

        {variant?.director_status === 'flagged' && (
          <p className="mt-3 text-[0.75rem] leading-relaxed text-text-3">
            The director flagged the copy behind this one too
            {variant.director_notes ? ` — ${variant.director_notes}` : '.'}
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <Action
            label={asset.review_status === 'approved' ? 'Approved' : 'Approve'}
            tone="go"
            active={asset.review_status === 'approved'}
            disabled={busy || redoing}
            onClick={onApprove}
          />
          <Action
            label={redoing ? 'Rendering…' : 'Redo'}
            tone="quiet"
            disabled={busy || redoing}
            onClick={async () => {
              // A redo is a second round trip to the vendor, so the button says
              // so for as long as it takes rather than looking inert.
              setRedoing(true)
              try {
                await onRedo()
              } finally {
                setRedoing(false)
              }
            }}
          />
          <Action
            label={asset.review_status === 'rejected' ? 'Rejected' : 'Reject'}
            tone="flag"
            active={asset.review_status === 'rejected'}
            disabled={busy || redoing}
            onClick={onReject}
          />
        </div>

        {decided && (
          <p className="mt-3 text-[0.6875rem] text-text-3">
            You can change your mind until the gate is closed.
          </p>
        )}
      </div>
    </article>
  )
}

function Action({
  label,
  tone,
  active = false,
  disabled,
  onClick,
}: {
  label: string
  tone: 'go' | 'flag' | 'quiet'
  active?: boolean
  disabled: boolean
  onClick: () => void | Promise<void>
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => void onClick()}
      className={cn(
        'display rounded-full border px-3.5 py-1.5 text-[0.75rem] transition-colors duration-200',
        'disabled:cursor-not-allowed disabled:opacity-40',
        active
          ? tone === 'go'
            ? 'border-go bg-go/15 text-go'
            : 'border-flag bg-flag/15 text-flag'
          : 'border-border text-text-2 hover:border-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}
