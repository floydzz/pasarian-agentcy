import { cn } from '@/lib/utils'
import { splitCitations } from '@/lib/citations'

/** One grounded claim, with the chunks it rests on.
 *
 * The rule down the left carries the corpus boundary the backend enforces:
 * company knowledge is ground truth and gets a solid rule, trends are
 * inspiration only and get a dashed one. Two rationales never look alike, so
 * nobody reads a passing TikTok hashtag as a fact about the product. */
export function Rationale({
  kind,
  rationale,
}: {
  kind: 'brand' | 'trend'
  rationale: string
}) {
  const { text, sources } = splitCitations(rationale)

  return (
    <div
      className={cn(
        'border-l pl-3.5',
        kind === 'brand'
          ? 'border-solid border-foreground/40'
          : 'border-dashed border-foreground/20',
      )}
    >
      <p className="label">
        {kind === 'brand' ? 'Brand — ground truth' : 'Trend — inspiration'}
      </p>
      <p className="mt-1.5 text-[0.875rem] leading-relaxed">{text}</p>
      {sources.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {sources.map((source) => (
            <li
              key={source}
              className="data rounded bg-muted px-1.5 py-0.5 text-text-3"
              title="Retrieved chunk this claim cites"
            >
              {source}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
