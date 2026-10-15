import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { calendarApi } from '@/api/calendar'
import type { MarketingItem } from '@/api/calendar'

export function CalendarCampaignLink({ campaignId }: { campaignId: number }) {
  const [item, setItem] = useState<MarketingItem | null>(null)
  useEffect(() => { let active = true; calendarApi.campaignItem(campaignId).then(value => { if (active) setItem(value) }).catch(() => undefined); return () => { active = false } }, [campaignId])
  if (!item) return null
  return <Link to={`/calendar?item=${item.id}`} className="inline-flex flex-wrap items-center gap-2 text-xs font-medium text-primary"><span>View calendar plan →</span><span className="font-normal text-text-3">{item.campaign_start} – {item.campaign_end}</span>{item.source_changed && <span className="text-halt">Date review needed</span>}</Link>
}
