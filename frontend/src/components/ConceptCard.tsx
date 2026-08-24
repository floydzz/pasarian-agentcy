import { useState } from 'react'
import { motion } from 'motion/react'
import { Rationale } from '@/components/Rationale'
import { EditDialog } from '@/components/EditDialog'
import { cn } from '@/lib/utils'
import { MICRO } from '@/lib/motion'
import type { Concept, ConceptStatus } from '@/api/types'

const STATUS_LABEL: Record<ConceptStatus, string> = {
  pending: 'Undecided',
  approved: 'Approved',
  rejected: 'Rejected',
  edited: 'Edited — look again',
}

/** One proposed concept, on paper.
 *
 * Everything the crew produced renders on a light surface inside the dark
 * instrument, so the work can never be mistaken for the machine that made it.
 * Nothing on this card is amber except the decision it is asking you for. */
export function ConceptCard({
  concept,
  index,
  open,
  busy,
  onDecide,
  onRevise,
}: {
  concept: Concept
  index: number
  /** False once the plan is approved — the gate has closed behind this one. */
  open: boolean
  busy: boolean
  onDecide: (decision: ConceptStatus) => void
  onRevise: (note: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)

  return (
    <article
      className={cn(
        'on-paper flex h-full w-full flex-col overflow-hidden rounded-2xl bg-paper shadow-[0_18px_44px_-28px_rgba(0,0,0,0.9)] transition-opacity duration-500',
        concept.status === 'rejected' && 'opacity-45',
      )}
    >
      <header className="shrink-0 px-6 pt-5 pb-4">
        <div className="flex items-center justify-between gap-3">
          <p className="data text-text-3">
            {String(index + 1).padStart(2, '0')} · {concept.format}
          </p>
          <span
            className={cn(
              'text-[0.6875rem] whitespace-nowrap transition-colors',
              concept.status === 'pending' && 'text-halt',
              concept.status === 'approved' && 'text-go',
              concept.status === 'edited' && 'text-halt',
              concept.status === 'rejected' && 'text-text-3',
            )}
          >
            {STATUS_LABEL[concept.status]}
          </span>
        </div>
        <h3 className="display-tight mt-2 text-[1.375rem] leading-[1.15] text-balance">
          {concept.theme}
        </h3>
      </header>

      <div className="quiet-scroll fade-b min-h-0 flex-1 space-y-4 overflow-y-auto px-6 pb-5">
        <Rationale kind="brand" rationale={concept.brand_rationale} />
        <Rationale kind="trend" rationale={concept.trend_rationale} />

        <div>
          <p className="label">{concept.variant_count} variants — one per axis</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {concept.variation_axes.map((axis) => (
              <li
                key={axis}
                className="rounded-full border border-border px-2.5 py-1 text-[0.6875rem] text-text-2"
              >
                {axis}
              </li>
            ))}
          </ul>
        </div>

        {concept.edit_note && (
          <p className="rounded-lg bg-halt/10 px-3.5 py-2.5 text-[0.8125rem] leading-relaxed">
            <span className="label text-halt">You asked for</span>
            <br />
            {concept.edit_note}
          </p>
        )}
      </div>

      {open && (
        <footer className="flex shrink-0 gap-2 border-t border-border px-6 py-3.5">
          <Action
            tone="approve"
            disabled={busy || concept.status === 'approved'}
            onClick={() => onDecide('approved')}
          >
            Approve
          </Action>
          <Action tone="quiet" disabled={busy} onClick={() => setEditing(true)}>
            Edit
          </Action>
          <Action
            tone="reject"
            disabled={busy || concept.status === 'rejected'}
            onClick={() => onDecide('rejected')}
          >
            Reject
          </Action>
        </footer>
      )}

      <EditDialog
        concept={concept}
        open={editing}
        onOpenChange={setEditing}
        onSubmit={onRevise}
      />
    </article>
  )
}

function Action({
  tone,
  disabled,
  onClick,
  children,
}: {
  tone: 'approve' | 'quiet' | 'reject'
  disabled: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <motion.button
      type="button"
      disabled={disabled}
      onClick={onClick}
      whileHover={disabled ? undefined : { y: -1 }}
      whileTap={disabled ? undefined : { y: 0, scale: 0.98 }}
      transition={MICRO}
      className={cn(
        'rounded-full px-4 py-1.5 text-[0.8125rem] transition-colors disabled:cursor-not-allowed disabled:opacity-35',
        tone === 'approve' && 'bg-foreground text-background hover:bg-foreground/90',
        tone === 'quiet' && 'border border-border text-text-2 hover:text-foreground',
        tone === 'reject' && 'text-text-3 hover:text-flag',
      )}
    >
      {children}
    </motion.button>
  )
}
