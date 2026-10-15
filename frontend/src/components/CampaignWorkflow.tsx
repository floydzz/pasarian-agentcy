import { Link } from 'react-router-dom'
import type { Campaign } from '@/api/types'
import { campaignFlow } from '@/lib/campaignFlow'
export function CampaignWorkflow({ campaign }: { campaign: Campaign }) {
  const flow = campaignFlow(campaign)
  return <section aria-label="Campaign workflow" className="my-5 rounded-xl border border-edge bg-rise p-4"><ol className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Campaign steps">{['Brief', 'Concepts', 'Creatives', 'Review', 'Publish'].map((label, index) => <li key={label} aria-current={flow.step === index ? 'step' : undefined} className={`text-xs ${flow.step === index ? 'font-semibold text-brand' : 'text-text-3'}`}>{index < flow.step ? '✓' : index + 1}. {label}</li>)}</ol><div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-text-2">{flow.detail}</p><Link className="workspace-button" to={flow.to}>{flow.action}</Link></div></section>
}
