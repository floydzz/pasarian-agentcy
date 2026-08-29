import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { api, ApiError } from '@/api/client'
import type { Campaign } from '@/api/types'

/** The studio entry point is a campaign picker. A studio does not guess which
 * job someone meant to resume: it asks once, then opens that campaign's
 * dedicated production console. */
export function StudioShortcut({ medium }: { medium: 'image' | 'video' }) {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null)
  const image = medium === 'image'
  const title = image ? 'Image Studio' : 'Video Studio'

  useEffect(() => {
    api.listCampaigns().then(setCampaigns).catch((error: ApiError) => {
      setCampaigns([])
      toast.error(error.message)
    })
  }, [])

  return (
    <Page>
      <PageHead title={title}>
        {image
          ? 'Choose the campaign whose concepts, copy and product references you want to turn into still creatives.'
          : 'Choose a campaign to shape its script and storyboard, then generate AI clips and compose the finished film.'}
      </PageHead>

      {!image && (
        <Link
          to="/cinematic-trailer"
          className="mt-8 block rounded-xl border border-video/35 bg-video/[0.045] p-5 transition-colors hover:bg-video/[0.09]"
        >
          <p className="label text-video">Agentcy product film</p>
          <p className="display mt-2 text-[1rem]">Create the 120-second cinematic feature trailer</p>
          <p className="mt-2 max-w-2xl text-[0.8125rem] leading-relaxed text-text-2">
            The Network Woke Up uses a guided recording of the real Agentcy journey as the visual source for its AI feature shots, then projects the same exact screens into the finished cut.
          </p>
          <p className="data mt-5 text-video">Open product trailer →</p>
        </Link>
      )}

      {campaigns === null ? (
        <p className="mt-8 text-sm text-text-3">Loading campaigns…</p>
      ) : campaigns.length === 0 ? (
        <p className="mt-8 max-w-lg text-sm leading-relaxed text-text-3">
          There is no campaign to open yet. Start the brief in the strategist, then return here to choose its studio.
        </p>
      ) : (
        <ul className="mt-8 grid gap-3 lg:grid-cols-2">
          {campaigns.map((campaign) => (
            <li key={campaign.id}>
              <Link
                to={`/campaigns/${campaign.id}/${medium}`}
                className={`group block rounded-xl border border-edge bg-rise p-5 transition-colors hover:bg-[rgba(233,238,247,0.045)] ${image ? 'hover:border-image/50' : 'hover:border-video/50'}`}
              >
                <p className="display text-[1rem]">{campaign.name}</p>
                <p className="copy mt-2 line-clamp-2 text-[0.8125rem] leading-relaxed text-text-2">{campaign.brief}</p>
                <p className={`data mt-5 ${image ? 'text-image' : 'text-video'}`}>
                  {image ? 'Open image console →' : 'Open script & clips →'}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Page>
  )
}
