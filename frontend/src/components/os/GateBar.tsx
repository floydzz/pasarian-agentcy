import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { EASE_OUT, SETTLE } from '@/lib/motion'
import type { Campaign, Concept } from '@/api/types'

/** The seam between the machine and the person.
 *
 * A gate is an interrupt: the run halts and stays halted until someone
 * services it. This bar is the only warm surface in the product — amber
 * appears nowhere the machine acts alone — so a warm strip on screen always
 * means the same thing, and it means it before you have read a word.
 */
export function GateBar({
  campaign,
  concepts,
  running,
  awaitingCrew,
  onPlan,
  onGenerate,
  onApprovePlan,
  onAutoMode,
}: {
  campaign: Campaign
  concepts: Concept[]
  running: string | null
  awaitingCrew: number
  onPlan: () => void
  onGenerate: () => void
  onApprovePlan: () => void
  onAutoMode: (
    payload: Partial<Pick<Campaign, 'auto_approve_plan' | 'auto_approve_assets'>>,
  ) => void
}) {
  const still = useReducedMotion()
  const halted = campaign.status === 'pending_plan_approval'
  const undecided = concepts.filter((concept) => concept.status === 'pending').length
  const approved = concepts.filter((concept) => concept.status === 'approved').length
  const busy = running !== null

  const action = halted
    ? {
        label: approved === 0 ? 'Approve one to continue' : `Release the plan · ${approved}`,
        onClick: onApprovePlan,
        disabled: busy || approved === 0,
      }
    : campaign.status === 'draft'
      ? {
          label: running === 'planner' ? 'Planning…' : 'Run the planner',
          onClick: onPlan,
          disabled: busy,
        }
      : campaign.status === 'generating' && awaitingCrew > 0
        ? {
            label: running === 'crew' ? 'Crew running…' : `Run the crew · ${awaitingCrew}`,
            onClick: onGenerate,
            disabled: busy,
          }
        : null

  return (
    <motion.section
      layout
      className={cn(
        'relative z-10 shrink-0 overflow-hidden border-y transition-colors duration-700',
        halted ? 'border-halt/25 bg-halt/[0.055]' : 'border-edge bg-transparent',
      )}
    >
      {/* While halted, a slow sweep runs the top edge. It is the only ambient
          motion in the console and it means exactly one thing: you. */}
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
          <Marker halted={halted} still={Boolean(still)} />
          <div className="min-w-0">
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={halted ? 'halted' : campaign.status}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.28, ease: EASE_OUT }}
                className={cn(
                  'display truncate text-sm',
                  halted ? 'text-halt' : 'text-text-2',
                )}
              >
                {halted
                  ? undecided > 0
                    ? `${undecided} of ${concepts.length} ${concepts.length === 1 ? 'concept needs' : 'concepts still need'} your decision`
                    : `All ${concepts.length} decided — ${approved} approved`
                  : campaign.status === 'draft'
                    ? 'Nothing has run yet'
                    : awaitingCrew > 0
                      ? `${awaitingCrew} approved ${awaitingCrew === 1 ? 'concept' : 'concepts'} waiting on the crew`
                      : 'The crew holds the work'}
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
          <Policy
            id="auto-plan"
            label="Waive plan gate"
            checked={campaign.auto_approve_plan}
            disabled={busy || campaign.status !== 'draft'}
            onCheckedChange={(auto_approve_plan) => onAutoMode({ auto_approve_plan })}
          />
          <Policy
            id="auto-assets"
            label="Waive asset gate"
            checked={campaign.auto_approve_assets}
            disabled={
              busy ||
              ['pending_asset_review', 'ready_to_publish', 'published'].includes(
                campaign.status,
              )
            }
            onCheckedChange={(auto_approve_assets) => onAutoMode({ auto_approve_assets })}
          />

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
          halted ? 'border-halt bg-halt' : 'border-[rgba(233,238,247,0.3)] bg-transparent',
        )}
        animate={{ rotate: 45 }}
        transition={{ duration: 0.4, ease: EASE_OUT }}
      />
    </span>
  )
}

function Policy({
  id,
  label,
  checked,
  disabled,
  onCheckedChange,
}: {
  id: string
  label: string
  checked: boolean
  disabled: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="hidden items-center gap-2.5 md:flex">
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        className="data-[state=checked]:bg-halt"
      />
      <Label
        htmlFor={id}
        className={cn(
          'text-[0.6875rem] font-normal whitespace-nowrap transition-colors',
          checked ? 'text-halt' : 'text-text-3',
        )}
      >
        {label}
      </Label>
    </div>
  )
}
