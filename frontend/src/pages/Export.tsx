import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { EASE_OUT } from '@/lib/motion'
import { api, ApiError } from '@/api/client'
import type { Asset, Campaign, Variant } from '@/api/types'

/** The end of the line: what actually ships.
 *
 * Only approved creatives are here. The gate's whole return is that a person
 * decided, so a screen that quietly showed the rejects beside the approvals
 * would be spending that decision and then ignoring it.
 *
 * Each creative comes with its copy as text, because the image is only half of
 * what gets pasted into an ad manager — the headline, body and CTA are typed
 * into fields, and retyping them off a picture is how a typo reaches a
 * campaign. */
export function Export() {
  const id = Number(useParams().id)
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [assets, setAssets] = useState<Asset[]>([])
  const [variants, setVariants] = useState<Variant[]>([])

  const load = useCallback(async () => {
    const [fetched, itsAssets, itsVariants] = await Promise.all([
      api.getCampaign(id),
      api.listAssets(id),
      api.listVariants(id),
    ])
    setCampaign(fetched)
    setAssets(itsAssets)
    setVariants(itsVariants)
  }, [id])

  useEffect(() => {
    load().catch((error: ApiError) => toast.error(error.message))
  }, [load])

  const approved = assets.filter((asset) => asset.review_status === 'approved')

  return (
    <Page>
      <PageHead
        title="Export"
        action={
          campaign ? (
            <Link
              to={`/campaigns/${campaign.id}`}
              className="data shrink-0 text-text-3 transition-colors hover:text-foreground"
            >
              ← back to the console
            </Link>
          ) : undefined
        }
      >
        {campaign
          ? `The approved creatives for ${campaign.name}, at full size, with the copy that runs beside each one.`
          : 'Loading the approved creatives.'}
      </PageHead>

      {campaign && approved.length === 0 ? (
        <p className="mt-12 text-sm text-text-3">
          Nothing has been approved yet. Creatives you approve at the asset gate
          land here.
        </p>
      ) : (
        <div className="mt-12 space-y-16">
          {approved.map((asset, index) => (
            <Creative
              key={asset.id}
              asset={asset}
              variant={variants.find((v) => v.id === asset.variant_id)}
              index={index}
            />
          ))}
        </div>
      )}
    </Page>
  )
}

function Creative({
  asset,
  variant,
  index,
}: {
  asset: Asset
  variant?: Variant
  index: number
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 + index * 0.06, duration: 0.5, ease: EASE_OUT }}
      className="grid gap-8 md:grid-cols-[minmax(0,1fr)_18rem]"
    >
      <figure className="min-w-0">
        <img
          src={asset.media_url}
          alt={variant ? `Creative for “${variant.headline}”` : 'Approved creative'}
          className="w-full rounded-2xl"
        />
        <figcaption className="mt-3 flex items-center gap-4">
          {/* Opened rather than downloaded: the file is served from this same
              origin, so a plain link is the whole feature. */}
          <a
            href={asset.media_url}
            download
            className="data text-text-3 transition-colors hover:text-foreground"
          >
            download the image
          </a>
          {variant && <span className="data text-text-3">{variant.hook_type}</span>}
        </figcaption>
      </figure>

      {variant && (
        <div className="min-w-0 space-y-5">
          <CopyField label="Headline" value={variant.headline} />
          <CopyField label="Body" value={variant.body} />
          <CopyField label="Call to action" value={variant.cta} />
        </div>
      )}
    </motion.section>
  )
}

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="label">{label}</span>
        <button
          type="button"
          className="data text-text-3 transition-colors hover:text-foreground"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value)
              setCopied(true)
              setTimeout(() => setCopied(false), 1400)
            } catch {
              // A browser that refuses the clipboard is not an error worth a
              // toast — the text is on screen and selectable either way.
              toast.error('This browser would not let us reach the clipboard.')
            }
          }}
        >
          {copied ? 'copied' : 'copy'}
        </button>
      </div>
      <p className="copy mt-1.5 text-[0.9375rem] leading-relaxed text-text-2">{value}</p>
    </div>
  )
}
