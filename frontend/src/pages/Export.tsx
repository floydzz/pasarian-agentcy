import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { EASE_OUT } from '@/lib/motion'
import { api, ApiError } from '@/api/client'
import type {
  Campaign,
  Creative,
  DemoVideo,
  MarketingVideo,
  ReviewStatus,
  Variant,
} from '@/api/types'

/** The end of the line: what the machine actually made.
 *
 * This screen answers one question — *show me the product* — and it answers it
 * for the whole machine at `/export` and for one campaign at
 * `/campaigns/:id/export`. Both are the same room; the campaign route only
 * narrows what is in it, and adds the copy that runs beside each creative,
 * which is only knowable per campaign.
 *
 * It used to show approved work and nothing else, which was right in principle
 * and wrong in practice: a campaign whose creatives were all still at the gate
 * rendered a blank page, and a blank page is indistinguishable from a machine
 * that produced nothing. It opens on everything instead. The argument for
 * approved-only was that the gate's whole return is a person deciding, and a
 * screen that ignored the decision would be spending it for nothing — but the
 * decision is not ignored here, it is *stamped on every piece*, and the newest
 * work is by definition the work nobody has decided about yet. Filtering to
 * approved is one click away and says how many it is holding back.
 */
type Filter = 'all' | ReviewStatus

/** A video from either studio, flattened to the handful of fields this screen
 * draws. The product explainer and a campaign film are different rows in
 * different tables and the same object to a person looking at the work. */
type Film = {
  key: string
  id: number
  title: string
  media_url: string
  poster_url: string
  duration_seconds: number
  scene_count: number
  review_status: ReviewStatus
  campaign_id: number | null
  origin: string
}

export function Export() {
  const params = useParams()
  const scoped = params.id ? Number(params.id) : null
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [creatives, setCreatives] = useState<Creative[]>([])
  const [films, setFilms] = useState<Film[]>([])
  const [variants, setVariants] = useState<Variant[]>([])
  const [loaded, setLoaded] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')

  const load = useCallback(async () => {
    if (scoped !== null) {
      const [fetched, images, videos, itsVariants] = await Promise.all([
        api.getCampaign(scoped),
        api.listCreatives(scoped),
        api.listCampaignVideos(scoped),
        api.listVariants(scoped),
      ])
      setCampaign(fetched)
      setCreatives(images)
      setFilms(videos.map(fromMarketing))
      setVariants(itsVariants)
      return
    }
    const [images, videos, demos] = await Promise.all([
      api.listCreatives(),
      api.listVideos(),
      api.listDemoVideos(),
    ])
    setCreatives(images)
    setFilms([...videos.map(fromMarketing), ...demos.map(fromDemo)])
  }, [scoped])

  useEffect(() => {
    load()
      .then(() => setLoaded(true))
      .catch((error: ApiError) => {
        toast.error(error.message)
        setLoaded(true)
      })
  }, [load])

  const keep = <T extends { review_status: ReviewStatus }>(rows: T[]) =>
    filter === 'all' ? rows : rows.filter((row) => row.review_status === filter)

  const images = useMemo(() => keep(creatives), [creatives, filter])
  const reels = useMemo(() => keep(films), [films, filter])
  const total = creatives.length + films.length

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
          ? `Everything ${campaign.name} has produced, at full size, with the copy that runs beside each creative.`
          : 'Every finished piece the machine has made — creatives and films — ready to download.'}
      </PageHead>

      {loaded && total > 0 && (
        <Filters
          value={filter}
          onChange={setFilter}
          counts={{
            all: total,
            approved: countOf([...creatives, ...films], 'approved'),
            pending: countOf([...creatives, ...films], 'pending'),
            rejected: countOf([...creatives, ...films], 'rejected'),
          }}
        />
      )}

      {!loaded ? (
        <p className="mt-12 text-sm text-text-3">Gathering the work.</p>
      ) : total === 0 ? (
        <p className="mt-12 text-sm text-text-3">
          Nothing has been made yet.{' '}
          <Link to="/" className="underline underline-offset-4 hover:text-foreground">
            Start a campaign
          </Link>{' '}
          and its creatives will land here.
        </p>
      ) : images.length + reels.length === 0 ? (
        <p className="mt-12 text-sm text-text-3">
          Nothing is {filter} yet — {total} {total === 1 ? 'piece' : 'pieces'} of
          work {total === 1 ? 'is' : 'are'} here under another status.
        </p>
      ) : (
        <div className="mt-12 space-y-20">
          {reels.length > 0 && (
            <Section label="Films" count={reels.length} tint="text-video">
              <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
                {reels.map((film, index) => (
                  <FilmCard key={film.key} film={film} index={index} />
                ))}
              </div>
            </Section>
          )}

          {images.length > 0 && (
            <Section label="Creatives" count={images.length} tint="text-image">
              <div className="space-y-16">
                {images.map((creative, index) => (
                  <CreativeCard
                    key={creative.id}
                    creative={creative}
                    variant={variants.find((v) => v.id === creative.variant_id)}
                    showOwner={scoped === null}
                    index={index}
                  />
                ))}
              </div>
            </Section>
          )}
        </div>
      )}
    </Page>
  )
}

const fromMarketing = (video: MarketingVideo): Film => ({
  key: `video-${video.id}`,
  id: video.id,
  title: video.name,
  media_url: video.media_url,
  poster_url: video.poster_url,
  duration_seconds: video.duration_seconds,
  scene_count: video.scene_count,
  review_status: video.review_status,
  campaign_id: video.campaign_id,
  origin: video.campaign_id === null ? 'video studio' : 'campaign film',
})

const fromDemo = (video: DemoVideo): Film => ({
  key: `demo-${video.id}`,
  id: video.id,
  title: video.title,
  media_url: video.media_url,
  poster_url: video.poster_url,
  duration_seconds: video.duration_seconds,
  scene_count: video.scene_count,
  review_status: video.review_status,
  campaign_id: null,
  origin: 'product explainer',
})

const countOf = (
  rows: { review_status: ReviewStatus }[],
  status: ReviewStatus,
): number => rows.filter((row) => row.review_status === status).length

function Filters({
  value,
  onChange,
  counts,
}: {
  value: Filter
  onChange: (next: Filter) => void
  counts: Record<Filter, number>
}) {
  const options: Filter[] = ['all', 'approved', 'pending', 'rejected']
  return (
    <div className="mt-8 flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          className={cn(
            'data rounded-full border px-3 py-1.5 transition-colors',
            value === option
              ? 'border-foreground text-foreground'
              : 'border-edge text-text-3 hover:border-text-3 hover:text-text-2',
          )}
        >
          {option === 'all' ? 'everything' : option} · {counts[option]}
        </button>
      ))}
    </div>
  )
}

function Section({
  label,
  count,
  tint,
  children,
}: {
  label: string
  count: number
  tint: string
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-7 flex items-baseline gap-3 border-b border-edge pb-3">
        <h2 className={cn('display text-[1.0625rem]', tint)}>{label}</h2>
        <span className="data text-text-3">{count}</span>
      </div>
      {children}
    </section>
  )
}

/** A status a person set, drawn as a word rather than a colour alone — the
 * three states are a decision, and a coloured dot cannot say which. */
function Stamp({ status }: { status: ReviewStatus }) {
  return (
    <span
      className={cn(
        'data',
        status === 'approved'
          ? 'text-go'
          : status === 'rejected'
            ? 'text-flag'
            : 'text-text-3',
      )}
    >
      {status === 'pending' ? 'awaiting review' : status}
    </span>
  )
}

function FilmCard({ film, index }: { film: Film; index: number }) {
  return (
    <motion.figure
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.04 + index * 0.05, duration: 0.45, ease: EASE_OUT }}
      className="min-w-0"
    >
      {/* Played in place rather than linked away: the point of this screen is
          seeing the thing, and a link to a bare .mp4 is a file, not a film. */}
      <video
        src={film.media_url}
        poster={film.poster_url}
        controls
        playsInline
        preload="none"
        className="w-full rounded-2xl bg-black"
      />
      <figcaption className="mt-3 space-y-1.5">
        <p className="truncate text-[0.9375rem] text-text-2" title={film.title}>
          {film.title}
        </p>
        <p className="data text-text-3">
          {film.origin} · {film.duration_seconds}s · {film.scene_count} scenes
        </p>
        <div className="flex items-center gap-4">
          <a
            href={film.media_url}
            download
            className="data text-text-3 transition-colors hover:text-foreground"
          >
            download
          </a>
          <Stamp status={film.review_status} />
        </div>
      </figcaption>
    </motion.figure>
  )
}

function CreativeCard({
  creative,
  variant,
  showOwner,
  index,
}: {
  creative: Creative
  variant?: Variant
  showOwner: boolean
  index: number
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 + index * 0.05, duration: 0.5, ease: EASE_OUT }}
      className="grid gap-8 md:grid-cols-[minmax(0,1fr)_18rem]"
    >
      <figure className="min-w-0">
        <img
          src={creative.media_url}
          alt={`Creative for “${creative.headline}”`}
          className="w-full rounded-2xl"
        />
        <figcaption className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {/* Opened rather than fetched: the file is served from this same
              origin, so a plain link is the whole feature. */}
          <a
            href={creative.media_url}
            download
            className="data text-text-3 transition-colors hover:text-foreground"
          >
            download the image
          </a>
          <Stamp status={creative.review_status} />
          {variant && <span className="data text-text-3">{variant.hook_type}</span>}
        </figcaption>
      </figure>

      <div className="min-w-0 space-y-5">
        {showOwner && (
          <div>
            <span className="label">Campaign</span>
            <p className="mt-1.5">
              <Link
                to={`/campaigns/${creative.campaign_id}/export`}
                className="text-[0.9375rem] text-text-2 underline underline-offset-4 transition-colors hover:text-foreground"
              >
                {creative.campaign_name}
              </Link>
            </p>
            <p className="data mt-1 text-text-3">{creative.concept_theme}</p>
          </div>
        )}
        {variant ? (
          <>
            <CopyField label="Headline" value={variant.headline} />
            <CopyField label="Body" value={variant.body} />
            <CopyField label="Call to action" value={variant.cta} />
          </>
        ) : (
          <CopyField label="Headline" value={creative.headline} />
        )}
      </div>
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
