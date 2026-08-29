import { useReducedMotion } from 'motion/react'
import { GateShell, Policy, type GateAction } from '@/components/os/GateShell'
import type { Asset, Campaign, Concept } from '@/api/types'

/** The image pipeline's two gates, in one bar.
 *
 * Two gates rather than one because a campaign asks twice: once before the
 * crew spends model calls on a plan, and once before anything is shipped.
 * Which of them is open is never in question — the bar says so and the button
 * does the only thing that gate can do next.
 */
export function ImageGate({
  campaign,
  concepts,
  assets,
  running,
  awaitingCrew,
  awaitingRender,
  onPlan,
  onGenerate,
  onRender,
  onApprovePlan,
  onApproveAssets,
  onRejectRest,
  onExport,
  onAutoMode,
}: {
  campaign: Campaign
  concepts: Concept[]
  assets: Asset[]
  running: string | null
  awaitingCrew: number
  awaitingRender: number
  onPlan: () => void
  onGenerate: () => void
  onRender: () => void
  onApprovePlan: () => void
  onApproveAssets: () => void
  /** Reject every creative still undecided, in one go. */
  onRejectRest: () => void
  onExport: () => void
  onAutoMode: (
    payload: Partial<Pick<Campaign, 'auto_approve_plan' | 'auto_approve_assets'>>,
  ) => void
}) {
  const still = Boolean(useReducedMotion())
  const atPlanGate = campaign.status === 'pending_plan_approval'
  const atAssetGate = campaign.status === 'pending_asset_review'
  const halted = atPlanGate || atAssetGate

  const undecided = concepts.filter((concept) => concept.status === 'pending').length
  const approved = concepts.filter((concept) => concept.status === 'approved').length
  const undecidedAssets = assets.filter((asset) => asset.review_status === 'pending').length
  const approvedAssets = assets.filter((asset) => asset.review_status === 'approved').length
  const busy = running !== null

  const action: GateAction | null = atPlanGate
    ? {
        label: approved === 0 ? 'Approve one to continue' : `Release the plan · ${approved}`,
        onClick: onApprovePlan,
        disabled: busy || approved === 0,
      }
    : atAssetGate
      ? awaitingRender > 0
        ? {
            label:
              running === 'studio' ? 'Rendering…' : `Render the rest · ${awaitingRender}`,
            onClick: onRender,
            disabled: busy,
          }
        : {
            label:
              approvedAssets === 0
                ? 'Approve one to continue'
                : `Ship these · ${approvedAssets}`,
            onClick: onApproveAssets,
            disabled: busy || approvedAssets === 0,
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
          : campaign.status === 'generating' && awaitingRender > 0
            ? {
                label: running === 'studio' ? 'Rendering…' : `Render · ${awaitingRender}`,
                onClick: onRender,
                disabled: busy,
              }
            // A finished campaign is not a dead end. Without this the terminal
            // state drew no button at all, and the export screen — the whole
            // point of reaching it — was reachable only by typing its URL.
            : campaign.status === 'ready_to_publish' || campaign.status === 'published'
              ? { label: 'Export', onClick: onExport, disabled: busy }
              : null

  // Refusing is only offered where it means something: at the open asset gate,
  // against creatives nobody has ruled on yet. Approving one at a time stays
  // on the cards — this is for clearing what you have already looked at.
  const secondary: GateAction | null =
    atAssetGate && awaitingRender === 0 && undecidedAssets > 0
      ? {
          label: `Reject the rest · ${undecidedAssets}`,
          onClick: onRejectRest,
          disabled: busy,
        }
      : null

  const message = atPlanGate
    ? undecided > 0
      ? `${undecided} of ${concepts.length} ${concepts.length === 1 ? 'concept needs' : 'concepts still need'} your decision`
      : `All ${concepts.length} decided — ${approved} approved`
    : atAssetGate
      ? awaitingRender > 0
        ? `${awaitingRender} ${awaitingRender === 1 ? 'variant is' : 'variants are'} still unrendered`
        : undecidedAssets > 0
          ? `${undecidedAssets} of ${assets.length} ${assets.length === 1 ? 'creative needs' : 'creatives still need'} your decision`
          : `All ${assets.length} decided — ${approvedAssets} approved`
      : campaign.status === 'draft'
        ? 'Nothing has run yet'
        : awaitingCrew > 0
          ? `${awaitingCrew} approved ${awaitingCrew === 1 ? 'concept' : 'concepts'} waiting on the crew`
          : awaitingRender > 0
            ? `${awaitingRender} ${awaitingRender === 1 ? 'variant' : 'variants'} waiting on the studio`
            : campaign.status === 'ready_to_publish'
              ? 'Approved and ready to export'
              : 'The crew holds the work'

  return (
    <GateShell
      halted={halted}
      still={still}
      message={message}
      messageKey={halted ? `halted-${campaign.status}` : campaign.status}
      action={action}
      secondary={secondary}
      policies={
        <>
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
            // Waivable right up to the moment the creatives exist: after that
            // the decision has already been asked for and answered.
            disabled={
              busy ||
              ['pending_asset_review', 'ready_to_publish', 'published'].includes(
                campaign.status,
              )
            }
            onCheckedChange={(auto_approve_assets) => onAutoMode({ auto_approve_assets })}
          />
        </>
      }
    />
  )
}
