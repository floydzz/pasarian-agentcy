import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { EASE_OUT, SETTLE } from '@/lib/motion'

/** The seam between the machine and the person.
 *
 * A gate is an interrupt: the run halts and stays halted until someone
 * services it. This bar is the only warm surface in the product — amber
 * appears nowhere the machine acts alone — so a warm strip on screen always
 * means the same thing, and it means it before you have read a word.
 *
 * Every gate in the product is drawn here, image or video. A person who has
 * learned one gate has learned all of them: same amber, same sweep, same
 * button in the same place. What differs between studios is only what the
 * gate *says* and what its button does, so that is all the studios supply.
 */
export interface GateAction {
  label: string
  onClick: () => void
  disabled: boolean
}

export function GateShell({
  halted,
  still,
  message,
  messageKey,
  policies,
  action,
  secondary,
}: {
  halted: boolean
  still: boolean
  /** One line: what is being asked of you, or what the machine is doing. */
  message: string
  /** Changes whenever the message should re-animate rather than morph. */
  messageKey: string
  policies?: ReactNode
  action: GateAction | null
  /** The other thing you might do here, drawn quieter and to the left.
   *
   * A gate that only offers the way forward is not a decision, it is a
   * formality — "approve" means nothing if refusing is not on screen beside
   * it. Kept visually subordinate because the forward path is still the
   * common one, and only ever a real alternative, never a second primary. */
  secondary?: GateAction | null
}) {
  return (
    <motion.section
      layout
      className={cn(
        'relative z-10 shrink-0 overflow-hidden border-y transition-colors duration-700',
        halted ? 'border-halt/25 bg-halt/[0.055]' : 'border-edge bg-transparent',
      )}
    >
      {/* While halted, a slow sweep runs the top edge. It is the only ambient
          motion in a studio and it means exactly one thing: you. */}
      <AnimatePresence>
        {halted && !still && (
          <motion.span
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-px w-1/3 bg-gradient-to-r from-transparent via-halt to-transparent"
            initial={{ opacity: 0, x: '-100%' }}
            animate={{ opacity: 1, x: ['-100%', '400%'] }}
            exit={{ opacity: 0 }}
            transition={{
              x: { duration: 4.2, repeat: Infinity, ease: 'linear' },
              opacity: { duration: 0.5 },
            }}
          />
        )}
      </AnimatePresence>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3.5 sm:px-8">
        <div className="flex min-w-0 flex-1 items-center gap-3.5">
          <Marker halted={halted} still={still} />
          <div className="min-w-0">
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={messageKey}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.28, ease: EASE_OUT }}
                className={cn(
                  'display truncate text-sm',
                  halted ? 'text-halt' : 'text-text-2',
                )}
              >
                {message}
              </motion.p>
            </AnimatePresence>
            <p className="mt-0.5 truncate text-[0.6875rem] text-text-3">
              {halted
                ? 'The run is stopped here until you release it.'
                : 'No gate is open.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-5">
          {policies}

          {secondary && (
            <motion.button
              type="button"
              layout
              onClick={secondary.onClick}
              disabled={secondary.disabled}
              whileHover={secondary.disabled ? undefined : { y: -1 }}
              whileTap={secondary.disabled ? undefined : { y: 0, scale: 0.985 }}
              transition={SETTLE}
              className={cn(
                'display shrink-0 rounded-full border px-4 py-2 text-[0.8125rem] transition-colors duration-300',
                'disabled:cursor-not-allowed disabled:opacity-40',
                'border-border text-text-2 hover:border-flag hover:text-flag',
              )}
            >
              {secondary.label}
            </motion.button>
          )}

          {action && (
            <motion.button
              type="button"
              layout
              onClick={action.onClick}
              disabled={action.disabled}
              whileHover={action.disabled ? undefined : { y: -1 }}
              whileTap={action.disabled ? undefined : { y: 0, scale: 0.985 }}
              transition={SETTLE}
              className={cn(
                'display shrink-0 rounded-full px-5 py-2 text-[0.8125rem] transition-colors duration-300',
                'disabled:cursor-not-allowed disabled:opacity-40',
                halted
                  ? 'bg-halt text-[#1a1206] hover:bg-halt/90'
                  : 'bg-foreground text-void hover:bg-foreground/90',
              )}
            >
              {action.label}
            </motion.button>
          )}
        </div>
      </div>
    </motion.section>
  )
}

/** A diamond, matching the gate glyph in the graph — the same object seen
 * twice, so the bar and the waypoint are obviously the same thing. */
function Marker({ halted, still }: { halted: boolean; still: boolean }) {
  return (
    <span className="relative flex h-5 w-5 shrink-0 items-center justify-center">
      {halted && !still && (
        <motion.span
          className="absolute h-2.5 w-2.5 rotate-45 bg-halt"
          animate={{ scale: [1, 2.6], opacity: [0.55, 0] }}
          transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
        />
      )}
      <motion.span
        className={cn(
          'h-2.5 w-2.5 rotate-45 border',
          halted ? 'border-halt bg-halt' : 'border-edge-strong bg-transparent',
        )}
        animate={{ rotate: 45 }}
        transition={{ duration: 0.4, ease: EASE_OUT }}
      />
    </span>
  )
}

/** A gate a person has chosen to waive in advance. */
export function Policy({
  id,
  label,
  checked,
  disabled,
  accent = 'halt',
  onCheckedChange,
}: {
  id: string
  label: string
  checked: boolean
  disabled: boolean
  /** Amber is reserved for "a person is needed". A policy that only picks a
   * rendering path is not that, so it takes its medium's accent instead. */
  accent?: 'halt' | 'video'
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="hidden items-center gap-2.5 md:flex">
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className={accent === 'video' ? 'data-[state=checked]:bg-video' : 'data-[state=checked]:bg-halt'}
      />
      <Label
        htmlFor={id}
        className={cn(
          'text-[0.6875rem] font-normal whitespace-nowrap transition-colors',
          checked ? (accent === 'video' ? 'text-video' : 'text-halt') : 'text-text-3',
        )}
      >
        {label}
      </Label>
    </div>
  )
}
