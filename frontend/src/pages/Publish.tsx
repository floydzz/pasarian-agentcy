import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Bookmark,
  Heart,
  MessageCircle,
  MoreHorizontal,
  Music2,
  Play,
  Repeat2,
  Send,
  Share2,
  type LucideIcon,
} from 'lucide-react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { api, ApiError } from '@/api/client'
import type { Campaign, Creative, MarketingVideo, Variant } from '@/api/types'

type Platform = 'instagram' | 'facebook' | 'x' | 'rednote' | 'lemon8' | 'tiktok'

type PlatformSpec = {
  label: string
  format: string
  ratio: string
  tags: string
}

const PLATFORMS: Record<Platform, PlatformSpec> = {
  instagram: { label: 'Instagram', format: 'Feed 1080 × 1350', ratio: '4:5', tags: '#NailIt #NailInspo #SelfCare' },
  facebook: { label: 'Facebook', format: 'Post 1200 × 1500', ratio: '4:5', tags: '#NailIt #BeautyRoutine' },
  x: { label: 'X', format: 'Post 1600 × 900', ratio: '16:9', tags: '#NailIt' },
  rednote: { label: 'Rednote', format: 'Lifestyle post 1080 × 1440', ratio: '3:4', tags: '#美甲 #NailIt #SelfCare' },
  lemon8: { label: 'Lemon8', format: 'Editorial post 1080 × 1350', ratio: '4:5', tags: '#NailInspo #BeautyFinds #NailIt' },
  tiktok: { label: 'TikTok', format: 'Vertical video 1080 × 1920', ratio: '9:16', tags: '#NailTok #NailIt #SelfCare' },
}

type Piece =
  | { id: string; kind: 'image'; url: string; label: string; status: string; variantId?: number }
  | { id: string; kind: 'video'; url: string; poster?: string; label: string; status: string }

/** A publish workspace prepares real assets for a chosen platform alongside
 * the copywriter's approved headline/body/CTA. It deliberately stops before
 * posting to a social account: each network needs the owner's account
 * connection and explicit publish approval, neither of which Agentcy has yet. */
export function Publish() {
  const params = useParams()
  const scoped = params.id ? Number(params.id) : null
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [creatives, setCreatives] = useState<Creative[]>([])
  const [videos, setVideos] = useState<MarketingVideo[]>([])
  const [variants, setVariants] = useState<Variant[]>([])
  const [platform, setPlatform] = useState<Platform>('instagram')
  const [brandName, setBrandName] = useState('Your brand')
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    if (scoped === null) {
      const [images, films, profile] = await Promise.all([
        api.listCreatives(),
        api.listVideos(),
        api.getBrandProfile(),
      ])
      setCreatives(images)
      setVideos(films)
      setBrandName(profile.company_name.trim() || 'Your brand')
      return
    }
    const [owner, images, films, copy, profile] = await Promise.all([
      api.getCampaign(scoped),
      api.listCreatives(scoped),
      api.listCampaignVideos(scoped),
      api.listVariants(scoped),
      api.getBrandProfile(),
    ])
    setCampaign(owner)
    setCreatives(images)
    setVideos(films)
    setVariants(copy)
    setBrandName(profile.company_name.trim() || owner.name)
  }, [scoped])

  useEffect(() => {
    load().catch((error: ApiError) => toast.error(error.message)).finally(() => setLoaded(true))
  }, [load])

  const pieces = useMemo<Piece[]>(
    () => [
      ...videos.map((video) => ({
        id: `video-${video.id}`,
        kind: 'video' as const,
        url: video.media_url,
        poster: video.poster_url,
        label: video.name,
        status: video.review_status,
      })),
      ...creatives.map((creative) => ({
        id: `image-${creative.id}`,
        kind: 'image' as const,
        url: creative.media_url,
        label: creative.headline,
        status: creative.review_status,
        variantId: creative.variant_id,
      })),
    ],
    [creatives, videos],
  )
  const approved = pieces.filter((piece) => piece.status === 'approved')
  const display = approved.length ? approved : pieces

  return (
    <Page>
      <PageHead
        title="Publish"
        action={campaign ? <Link to={`/campaigns/${campaign.id}/image`} className="data text-text-3 hover:text-foreground">← campaign console</Link> : undefined}
      >
        {campaign
          ? `Prepare ${campaign.name}'s approved creative and copy for every social channel.`
          : 'Choose an output format, download the right creative, and copy a channel-ready post.'}
      </PageHead>

      <section className="mt-8 rounded-xl border border-edge bg-rise p-4 sm:p-5">
        <p className="label">Choose a channel</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(Object.keys(PLATFORMS) as Platform[]).map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setPlatform(id)}
              className={cn(
                'rounded-full border px-3 py-1.5 text-[0.75rem] transition-colors',
                platform === id ? 'border-foreground bg-foreground text-void' : 'border-edge text-text-3 hover:text-foreground',
              )}
            >
              {PLATFORMS[id].label}
            </button>
          ))}
        </div>
        <p className="data mt-3 text-text-3">{PLATFORMS[platform].format} · {PLATFORMS[platform].ratio}</p>
      </section>

      {!loaded ? (
        <p className="mt-12 text-sm text-text-3">Gathering creative work…</p>
      ) : display.length === 0 ? (
        <Empty campaign={campaign} />
      ) : (
        <section className="mt-10 grid gap-6">
          {display.map((piece) => (
            <PostKit
              key={piece.id}
              piece={piece}
              campaign={campaign}
              variant={piece.kind === 'image' ? variants.find((row) => row.id === piece.variantId) : variants[0]}
              platform={platform}
              brandName={brandName}
            />
          ))}
        </section>
      )}
    </Page>
  )
}

function PostKit({ piece, campaign, variant, platform, brandName }: {
  piece: Piece
  campaign: Campaign | null
  variant?: Variant
  platform: Platform
  brandName: string
}) {
  const spec = PLATFORMS[platform]
  const post = postContent(campaign, variant, piece)
  const caption = postCopy(platform, post)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(caption)
      toast.success(`${spec.label} copy copied`)
    } catch {
      toast.error('Could not access the clipboard. Select and copy the post text instead.')
    }
  }
  return (
    <article className="overflow-hidden rounded-xl border border-edge bg-rise">
      <div className="flex items-center justify-between gap-3 border-b border-edge px-5 py-3.5">
        <div className="min-w-0">
          <p className="display truncate text-[0.9375rem]">{piece.label}</p>
          <p className="data mt-1 text-text-3">{spec.format} · live post preview</p>
        </div>
        <span className="rounded-full border border-edge px-2.5 py-1 text-[0.6875rem] text-text-3">{spec.label}</span>
      </div>
      <div className="grid min-w-0 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-h-[33rem] items-center justify-center bg-void/45 p-5 sm:p-7">
          <SocialPostPreview platform={platform} piece={piece} post={post} brandName={brandName} />
        </div>
        <div className="border-t border-edge p-5 xl:border-t-0 xl:border-l">
          <p className="label">Post copy</p>
          <textarea readOnly value={caption} rows={9} className="quiet-scroll mt-2 w-full resize-none rounded-lg border border-edge bg-void/50 p-3 text-[0.8125rem] leading-relaxed text-text-2 outline-none" />
          <p className="mt-2 text-[0.6875rem] text-text-3">
            {platform === 'x' ? `${caption.length}/280 characters` : 'Preview copy is ready to edit after copying.'}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={() => void copy()} className="rounded-full bg-foreground px-3.5 py-2 text-[0.75rem] text-void hover:opacity-90">Copy {spec.label} post</button>
            <a href={piece.url} download className="rounded-full border border-edge px-3.5 py-2 text-[0.75rem] text-text-2 hover:border-edge-strong hover:text-foreground">Download media</a>
          </div>
        </div>
      </div>
    </article>
  )
}

type PostContent = {
  headline: string
  body: string
  cta: string
}

function postContent(campaign: Campaign | null, variant: Variant | undefined, piece: Piece): PostContent {
  const headline = variant?.headline ?? piece.label
  const body = variant?.body ?? campaign?.brief ?? 'A new creative from Agentcy.'
  const cta = variant?.cta ?? 'Discover the collection.'
  return { headline, body, cta }
}

function postCopy(platform: Platform, post: PostContent) {
  const tags = PLATFORMS[platform].tags
  const { headline, body, cta } = post
  const short = `${headline}. ${cta}`
  if (platform === 'x') return `${short.slice(0, 230)}\n\n${tags}`
  if (platform === 'facebook') return `${headline}\n\n${body}\n\n${cta}`
  if (platform === 'rednote') return `${headline}\n\n${body}\n\n${cta}\n\n${tags}`
  return `${headline}\n\n${body}\n\n${cta}\n\n${tags}`
}

function SocialPostPreview({ platform, piece, post, brandName }: {
  platform: Platform
  piece: Piece
  post: PostContent
  brandName: string
}) {
  const tags = PLATFORMS[platform].tags
  const handle = socialHandle(brandName)
  const initials = brandName.slice(0, 2).toUpperCase()
  if (platform === 'instagram') {
    return (
      <div className="w-full max-w-[390px] overflow-hidden rounded-[0.45rem] bg-white text-[#181818] shadow-2xl shadow-black/25">
        <div className="flex items-center gap-2.5 px-3 py-2.5">
          <Avatar initials={initials} tone="from-fuchsia-500 via-amber-400 to-purple-600" />
          <div className="min-w-0 flex-1 text-[0.68rem] leading-tight"><p className="font-semibold">{handle}</p><p className="text-[#777]">Kuala Lumpur, Malaysia</p></div>
          <MoreHorizontal size={18} />
        </div>
        <PostMedia piece={piece} className="aspect-[4/5]" />
        <div className="px-3 pb-3 pt-2.5">
          <div className="flex items-center gap-3"><SocialIcon icon={Heart} /><SocialIcon icon={MessageCircle} /><SocialIcon icon={Send} /><SocialIcon icon={Bookmark} className="ml-auto" /></div>
          <p className="mt-2 text-[0.68rem] font-semibold">Liked by you and 1,248 others</p>
          <p className="mt-1.5 text-[0.68rem] leading-relaxed"><b>{handle}</b> {post.headline} {post.body} <span className="text-[#3567a9]">{tags}</span></p>
          <p className="mt-1.5 text-[0.62rem] text-[#888]">View all 18 comments · 2 hours ago</p>
        </div>
      </div>
    )
  }
  if (platform === 'facebook') {
    return (
      <div className="w-full max-w-[510px] overflow-hidden rounded-lg bg-white text-[#171717] shadow-2xl shadow-black/25">
        <div className="flex items-center gap-2.5 px-3.5 pb-2 pt-3.5"><Avatar initials={initials} tone="from-blue-500 to-cyan-400" /><div className="min-w-0 flex-1 text-[0.7rem]"><p className="font-semibold">{brandName}</p><p className="text-[#65676b]">Sponsored · 🌐</p></div><MoreHorizontal size={18} className="text-[#65676b]" /></div>
        <p className="px-3.5 pb-3 text-[0.75rem] leading-relaxed">{post.headline}<br /><br />{post.body}<br /><br />{post.cta}</p>
        <PostMedia piece={piece} className="aspect-[4/5]" />
        <div className="px-3.5 py-2.5 text-[0.69rem] text-[#65676b]"><div className="flex justify-between border-b border-[#e5e7eb] pb-2"><span>👍 ❤️  248</span><span>18 comments · 4 shares</span></div><div className="grid grid-cols-3 pt-2 text-center font-semibold"><span>👍 Like</span><span>💬 Comment</span><span>↗ Share</span></div></div>
      </div>
    )
  }
  if (platform === 'x') {
    return (
      <div className="w-full max-w-[510px] rounded-2xl border border-[#d9d9d9] bg-white p-3.5 text-[#0f1419] shadow-2xl shadow-black/25">
        <div className="flex gap-2.5"><Avatar initials={initials} tone="from-[#111] to-[#555]" size="large" /><div className="min-w-0 flex-1"><div className="flex items-start gap-1 text-[0.72rem]"><span className="font-bold">{brandName}</span><span className="text-[#536471]">@{handle} · 2h</span><MoreHorizontal size={17} className="ml-auto text-[#536471]" /></div><p className="mt-1 text-[0.77rem] leading-relaxed">{post.headline}. {post.cta} <span className="text-[#1d9bf0]">{tags}</span></p><PostMedia piece={piece} className="mt-3 aspect-video overflow-hidden rounded-2xl border border-[#d9d9d9]" /><div className="mt-3 flex justify-between pr-7 text-[#536471]"><SocialIcon icon={MessageCircle} label="12" /><SocialIcon icon={Repeat2} label="31" /><SocialIcon icon={Heart} label="184" /><SocialIcon icon={Share2} /></div></div></div>
      </div>
    )
  }
  if (platform === 'rednote') {
    return (
      <div className="w-full max-w-[340px] overflow-hidden rounded-xl bg-white text-[#262626] shadow-2xl shadow-black/25">
        <PostMedia piece={piece} className="aspect-[3/4]" />
        <div className="p-3"><div className="flex items-center gap-2"><Avatar initials={initials} tone="from-rose-500 to-red-600" /><p className="min-w-0 flex-1 truncate text-[0.68rem] font-semibold">{brandName}</p><span className="text-[0.65rem] text-[#777]">Follow</span></div><p className="mt-3 text-[0.78rem] font-semibold leading-snug">{post.headline}</p><p className="mt-1.5 line-clamp-2 text-[0.69rem] leading-relaxed text-[#555]">{post.body} {post.cta}</p><div className="mt-3 flex items-center justify-between text-[0.65rem] text-[#777]"><span>{tags}</span><span>♡ 286</span></div></div>
      </div>
    )
  }
  if (platform === 'lemon8') {
    return (
      <div className="w-full max-w-[360px] overflow-hidden rounded-xl bg-[#fffaf4] text-[#34291f] shadow-2xl shadow-black/25">
        <div className="relative"><PostMedia piece={piece} className="aspect-[4/5]" /><div className="absolute inset-x-4 bottom-4 bg-[#fffaf4]/95 p-3 text-center shadow-lg"><p className="font-serif text-[1rem] leading-tight">{post.headline}</p><p className="mt-1 text-[0.59rem] uppercase tracking-[0.18em] text-[#7a6250]">Nail notes by {brandName}</p></div></div><div className="p-3"><div className="flex items-center gap-2"><Avatar initials={initials} tone="from-amber-300 to-orange-400" /><span className="text-[0.67rem] font-semibold">{brandName}</span><span className="ml-auto text-[0.64rem] text-[#7a6250]">♡ 132</span></div><p className="mt-2 line-clamp-2 text-[0.68rem] leading-relaxed text-[#6a5543]">{post.body} {post.cta}</p><p className="mt-2 text-[0.62rem] text-[#a47c58]">{tags}</p></div>
      </div>
    )
  }
  return (
    <div className="relative w-full max-w-[300px] overflow-hidden rounded-[0.6rem] bg-black text-white shadow-2xl shadow-black/35">
      <PostMedia piece={piece} className="aspect-[9/16]" />
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/35 to-transparent px-3 pb-4 pt-20"><p className="text-[0.72rem] font-semibold">@{handle}</p><p className="mt-1 line-clamp-3 text-[0.69rem] leading-relaxed">{post.headline}. {post.cta}<br />{tags}</p><div className="mt-3 flex items-center gap-2 text-[0.63rem]"><Music2 size={13} /><span className="truncate">original sound — {brandName}</span></div></div>
      <div className="absolute bottom-20 right-2.5 flex flex-col items-center gap-3 text-[0.62rem]"><Avatar initials={initials} tone="from-pink-500 to-fuchsia-600" /><SocialIcon icon={Heart} label="1,248" stacked /><SocialIcon icon={MessageCircle} label="38" stacked /><SocialIcon icon={Bookmark} label="Save" stacked /><SocialIcon icon={Share2} label="Share" stacked /></div>
    </div>
  )
}

function PostMedia({ piece, className }: { piece: Piece; className: string }) {
  return (
    <div className={cn('relative overflow-hidden bg-[#e9e9e9]', className)}>
      {piece.kind === 'image' ? <img src={piece.url} alt={piece.label} className="h-full w-full object-cover" /> : <video src={piece.url} poster={piece.poster} muted playsInline preload="metadata" className="h-full w-full object-cover" />}
      {piece.kind === 'video' && <span className="absolute left-3 top-3 grid h-8 w-8 place-items-center rounded-full bg-black/55 text-white backdrop-blur"><Play size={15} fill="currentColor" /></span>}
    </div>
  )
}

function Avatar({ initials, tone, size = 'normal' }: { initials: string; tone: string; size?: 'normal' | 'large' }) {
  return <span className={cn('grid shrink-0 place-items-center rounded-full bg-gradient-to-br font-bold text-white', size === 'large' ? 'h-10 w-10 text-[0.72rem]' : 'h-7 w-7 text-[0.56rem]', tone)}>{initials}</span>
}

function SocialIcon({ icon: Icon, label, className, stacked = false }: { icon: LucideIcon; label?: string; className?: string; stacked?: boolean }) {
  return <span className={cn('inline-flex items-center gap-1', stacked && 'flex-col gap-0.5', className)}><Icon size={stacked ? 19 : 19} strokeWidth={1.8} /><span className="text-[0.62rem]">{label}</span></span>
}

function socialHandle(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 18) || 'yourbrand'
}

function Empty({ campaign }: { campaign: Campaign | null }) {
  return (
    <section className="mt-12 max-w-xl rounded-xl border border-dashed border-edge-strong px-6 py-10">
      <p className="display text-[0.9375rem]">No publishable work yet.</p>
      <p className="mt-2 text-[0.8125rem] leading-relaxed text-text-3">
        {campaign ? 'Approve an image or video in this campaign first; it will appear here with a ready-to-adapt social post.' : 'Approved images and videos will appear here as publish-ready packages.'}
      </p>
    </section>
  )
}
