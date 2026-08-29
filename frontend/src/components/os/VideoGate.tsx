import { useReducedMotion } from 'motion/react'
import { GateShell, Policy, type GateAction } from '@/components/os/GateShell'
import type { MarketingVideo } from '@/api/types'

/** The video pipeline's single gate.
 *
 * One gate rather than two, and that is honest rather than a simplification:
 * a video has no plan to release, because the storyboard on screen *is* the
 * plan and the person wrote it. The only moment a decision is owed is when a
 * cut comes back from QA. */
export function VideoGate({
  videos,
  running,
  scenes,
  broll,
  brollAvailable,
  onBroll,
  onRender,
  onApprove,
}: {
  videos: MarketingVideo[]
  running: string | null
  /** How many scenes the storyboard currently holds. */
  scenes: number
  /** Whether the next render should generate backdrops. */
  broll: boolean
  /** False when no provider is configured — the switch is then not offered
   * at all, rather than shown and quietly ignored. */
  brollAvailable: boolean
  onBroll: (broll: boolean) => void
  onRender: () => void
  onApprove: () => void
}) {
  const still = Boolean(useReducedMotion())
  const busy = running !== null
  const pending = videos.filter((video) => video.review_status === 'pending')
  const approved = videos.filter((video) => video.review_status === 'approved').length
  const flagged = pending.filter((video) => video.qa_status === 'flagged').length
  const halted = pending.length > 0

  const action: GateAction | null = halted
    ? {
        label: `Approve the cut · ${pending.length}`,
        onClick: onApprove,
        disabled: busy,
      }
    : {
        label: running ? 'Rendering…' : videos.length === 0 ? 'Render the video' : 'Render another cut',
        onClick: onRender,
        disabled: busy || scenes < 3,
      }

  const message = halted
    ? flagged > 0
      ? `${flagged} of ${pending.length} ${pending.length === 1 ? 'cut was' : 'cuts were'} flagged by QA`
      : `${pending.length} ${pending.length === 1 ? 'cut is' : 'cuts are'} waiting on your review`
    : videos.length === 0
      ? scenes < 3
        ? 'A storyboard needs at least three scenes'
        : `${scenes} scenes ready to render`
      : `All ${videos.length} decided — ${approved} approved`

  return (
    <GateShell
      halted={halted}
      still={still}
      message={message}
      messageKey={`${halted}-${message}`}
      policies={
        brollAvailable && !halted ? (
          <Policy
            id="use-broll"
            label="Generated b-roll"
            accent="video"
            checked={broll}
            // Only while nothing is rendering: the choice is made per render,
            // and changing it mid-run would describe a video that is not the
            // one being made.
            disabled={busy}
            onCheckedChange={onBroll}
          />
        ) : undefined
      }
      action={action}
    />
  )
}
