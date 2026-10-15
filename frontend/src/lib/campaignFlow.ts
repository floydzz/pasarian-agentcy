import type { Campaign } from '@/api/types'
export function campaignFlow(campaign: Campaign) {
  const base = `/campaigns/${campaign.id}`
  const states = {
    draft: { step: 0, action: 'Plan campaign concepts', to: `${base}/image?run=plan`, detail: 'Your brief is ready for planning.' },
    planning: { step: 1, action: 'View planning progress', to: '/progress', detail: 'The strategist is preparing concepts.' },
    pending_plan_approval: { step: 1, action: 'Review concepts', to: `${base}/image`, detail: 'Choose the concepts to produce.' },
    generating: { step: 2, action: 'Continue creative production', to: `${base}/image`, detail: 'Produce the approved concepts, then review the output.' },
    pending_asset_review: { step: 3, action: 'Review creatives', to: `${base}/image`, detail: 'Approve the work you want to publish.' },
    ready_to_publish: { step: 4, action: 'Prepare publishing', to: `${base}/publish`, detail: 'Approved work is ready to prepare for your channels.' },
    published: { step: 4, action: 'Review campaign results', to: base + '#results', detail: 'Record the outcomes to inform your next campaign.' },
  }
  return states[campaign.status]
}
