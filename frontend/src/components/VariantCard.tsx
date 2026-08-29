import { cn } from '@/lib/utils'
import type { Variant } from '@/api/types'

/** One finished variant: the copy as it would run, and the brief behind it.
 *
 * The copy gets the room a proof would get and is set in the serif, because it
 * is the work. Everything the machine says *about* the work — the axis, the
 * verdict, the revision count — stays small, grey, and out of the way. */
export function VariantCard({ variant }: { variant: Variant }) {
  const flagged = variant.director_status === 'flagged'

  return (
    <article className="on-paper flex h-full w-full flex-col overflow-hidden rounded-2xl bg-paper shadow-[0_18px_44px_-28px_rgba(0,0,0,0.9)]">
      <header className="flex shrink-0 items-center justify-between gap-3 px-6 pt-5 pb-3">
        <span className="data truncate text-text-3">{variant.hook_type}</span>
        <span
          className={cn(
            'text-[0.6875rem] whitespace-nowrap',
            flagged ? 'text-flag' : 'text-go',
          )}
        >
          {flagged ? 'Flagged' : 'Director passed'}
        </span>
      </header>

      <div className="quiet-scroll fade-b min-h-0 flex-1 overflow-y-auto px-6 pb-5">
        <p className="copy text-[1.625rem] leading-[1.2] font-medium text-balance">
          {variant.headline}
        </p>
        <p className="copy mt-3.5 text-[1.0625rem] leading-relaxed text-text-2">
          {variant.body}
        </p>
        <p className="copy mt-5 inline-block border-b-2 border-foreground pb-0.5 text-[1.0625rem] font-medium">
          {variant.cta}
        </p>

        {flagged && variant.director_notes && (
          <p className="mt-5 rounded-lg bg-flag/10 px-3.5 py-2.5 text-[0.8125rem] leading-relaxed">
            <span className="label text-flag">
              Director, after {variant.revision_count} revisions
            </span>
            <br />
            {variant.director_notes}
          </p>
        )}

        <details className="group mt-5 border-t border-border pt-3.5">
          <summary className="label cursor-pointer list-none transition-colors hover:text-foreground">
            Visual brief
            <span className="ml-1.5 inline-block transition-transform group-open:rotate-90">
              ›
            </span>
          </summary>
          <dl className="mt-3 space-y-3">
            <Field label="Image prompt" value={variant.visual_brief.image_prompt} />
            <Field label="Text placement" value={variant.visual_brief.text_placement} />
            <Field label="Copy treatment" value={formatTreatment(variant.visual_brief.text_treatment)} />
            <Field label="Composition" value={variant.visual_brief.composition_notes} />
          </dl>
        </details>
      </div>
    </article>
  )
}

function formatTreatment(treatment: Variant['visual_brief']['text_treatment']) {
  return treatment ? treatment.replace('-', ' ') : 'glass panel (legacy plan)'
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mt-1 text-[0.8125rem] leading-relaxed text-text-2">{value}</dd>
    </div>
  )
}
