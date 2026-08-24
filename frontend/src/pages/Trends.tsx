import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { toast } from 'sonner'
import { Switch } from '@/components/ui/switch'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { cn } from '@/lib/utils'
import { EASE_OUT, MICRO, SETTLE } from '@/lib/motion'
import { api, ApiError } from '@/api/client'
import type { TrendSignal, TrendSource, TrendStatus } from '@/api/types'

/** What the planner is allowed to call “the moment”.
 *
 * This is the only steering anyone has over that input, so the watchlist is
 * the page rather than a setting buried in one. Two things are stated plainly
 * and repeatedly: trends are inspiration and can never become a fact about the
 * product, and — when no SerpApi key is configured — the signals below were
 * generated rather than measured.
 */
export function Trends() {
  const [sources, setSources] = useState<TrendSource[] | null>(null)
  const [status, setStatus] = useState<TrendStatus | null>(null)
  const [scraping, setScraping] = useState<number | 'all' | null>(null)

  const refresh = useCallback(async () => {
    const [fetched, corpus] = await Promise.all([
      api.listTrendSources(),
      api.trendStatus(),
    ])
    setSources(fetched)
    setStatus(corpus)
  }, [])

  useEffect(() => {
    refresh().catch((error: ApiError) => {
      setSources([])
      toast.error(error.message)
    })
  }, [refresh])

  const act = useCallback(
    async (action: () => Promise<unknown>) => {
      try {
        await action()
      } catch (error) {
        toast.error((error as ApiError).message)
      } finally {
        await refresh().catch(() => undefined)
      }
    },
    [refresh],
  )

  async function scrape(sourceId?: number) {
    setScraping(sourceId ?? 'all')
    try {
      const results = await api.scrape(sourceId)
      const chunks = results.reduce((total, result) => total + result.chunks, 0)
      const failed = results.filter((result) => result.mode === 'failed')
      if (failed.length > 0) {
        toast.error(
          `${failed.length} of ${results.length} failed — ${failed[0].error ?? 'no reason given'}`,
        )
      } else {
        toast.success(
          `${chunks} ${chunks === 1 ? 'chunk' : 'chunks'} into the trend corpus`,
        )
      }
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setScraping(null)
      await refresh().catch(() => undefined)
    }
  }

  const enabled = sources?.filter((source) => source.enabled).length ?? 0

  return (
    <Page>
      <PageHead
        title="Trend watch"
        action={
          <motion.button
            type="button"
            onClick={() => scrape()}
            disabled={scraping !== null || enabled === 0}
            whileHover={scraping ? undefined : { y: -1 }}
            whileTap={scraping ? undefined : { scale: 0.985 }}
            transition={MICRO}
            className="display shrink-0 rounded-full bg-foreground px-5 py-2 text-[0.8125rem] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
          >
            {scraping === 'all'
              ? 'Pulling…'
              : `Pull ${enabled} ${enabled === 1 ? 'keyword' : 'keywords'}`}
          </motion.button>
        }
      >
        Keywords the scraper watches. What it finds is chunked into the trend
        corpus, where the planner reads it as inspiration — never as a fact
        about your product.
      </PageHead>

      {status && !status.live && <Rehearsal />}

      {sources === null ? (
        <p className="mt-14 text-sm text-text-3">Loading…</p>
      ) : (
        <>
          <ul className="mt-10 flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {sources.map((source) => (
                <Watch
                  key={source.id}
                  source={source}
                  busy={scraping === source.id}
                  onScrape={() => scrape(source.id)}
                  onToggle={(enabledNow) =>
                    act(() => api.updateTrendSource(source.id, { enabled: enabledNow }))
                  }
                  onRemove={() => act(() => api.removeTrendSource(source.id))}
                />
              ))}
            </AnimatePresence>
          </ul>

          <AddKeyword
            onAdd={(keyword, note) =>
              act(async () => {
                await api.addTrendSource({ keyword, note })
                toast.success(`Watching “${keyword}” — pull it to fetch signals`)
              })
            }
          />
        </>
      )}

      {status && <Corpus status={status} />}
    </Page>
  )
}

/** Said once, at the top, and never dressed up.
 *
 * Deliberately achromatic: amber in this product means a human decision is
 * blocking a run, and a missing key is not that. It earns its weight through
 * contrast and position instead of through colour. */
function Rehearsal() {
  return (
    <motion.p
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: EASE_OUT }}
      className="mt-8 border-l-2 border-edge-strong pl-4 text-[0.8125rem] leading-relaxed text-text-2"
    >
      <span className="text-foreground">No SerpApi key is set.</span> Pulls
      return generated samples rather than measured search interest, so the
      whole pipeline can be rehearsed offline. Every document written this way
      says so in its heading, and that admission travels into any concept that
      cites it. Set <span className="data">SERPAPI_KEY</span> for live signals.
    </motion.p>
  )
}

function Watch({
  source,
  busy,
  onScrape,
  onToggle,
  onRemove,
}: {
  source: TrendSource
  busy: boolean
  onScrape: () => void
  onToggle: (enabled: boolean) => void
  onRemove: () => void
}) {
  const still = useReducedMotion()
  const shown = strongest(source.last_signals)

  return (
    <motion.li
      layout={!still}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
      transition={still ? { duration: 0 } : SETTLE}
      className={cn(
        'glass rounded-xl px-5 py-4 transition-opacity sm:px-6',
        !source.enabled && 'opacity-45',
      )}
    >
      <div className="flex flex-wrap items-start gap-x-5 gap-y-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="display text-[0.9375rem]">{source.keyword}</h2>
            <span className="data text-text-3">{source.geo}</span>
            <Freshness source={source} />
          </div>
          {source.note && (
            <p className="mt-1.5 text-[0.75rem] leading-relaxed text-text-3">
              {source.note}
            </p>
          )}
          {source.last_error && (
            <p className="mt-1.5 text-[0.75rem] leading-relaxed text-flag">
              {source.last_error}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-4">
          <button
            type="button"
            onClick={onScrape}
            disabled={busy}
            className="text-[0.75rem] text-text-3 transition-colors hover:text-foreground disabled:opacity-40"
          >
            {busy ? 'Pulling…' : 'Pull'}
          </button>
          <Switch
            checked={source.enabled}
            onCheckedChange={onToggle}
            aria-label={`Include ${source.keyword} in the watchlist`}
          />
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Stop watching ${source.keyword}`}
            className="text-text-3 transition-colors hover:text-flag"
          >
            <svg viewBox="0 0 14 14" className="h-3.5 w-3.5" aria-hidden>
              <path
                d="M3 3l8 8M11 3l-8 8"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
      </div>

      {shown.length > 0 && (
        <ul className="mt-4 flex flex-col gap-1.5 border-t border-edge pt-4">
          {shown.map(({ signal, ceiling }) => (
            <Signal
              key={signal.query}
              signal={signal}
              ceiling={ceiling}
              still={Boolean(still)}
            />
          ))}
        </ul>
      )}
    </motion.li>
  )
}

/** One query, with its interest drawn against the strongest in its own set.
 *
 * Rising and top are distinguished by weight rather than by hue — the machine
 * is achromatic — and rising queries are the brighter of the two because a
 * breakout is what a marketer is scanning for. */
function Signal({
  signal,
  ceiling,
  still,
}: {
  signal: TrendSignal
  ceiling: number
  still: boolean
}) {
  return (
    <li className="flex items-center gap-3">
      <span
        className={cn(
          'data w-10 shrink-0',
          signal.rising ? 'text-text-2' : 'text-text-3',
        )}
      >
        {signal.rising ? 'rising' : 'top'}
      </span>
      <span
        className={cn(
          'min-w-0 flex-1 truncate text-[0.8125rem]',
          signal.rising ? 'text-foreground' : 'text-text-2',
        )}
      >
        {signal.query}
      </span>
      <span className="hidden h-px w-28 shrink-0 bg-[rgba(233,238,247,0.08)] sm:block">
        <motion.span
          className={cn(
            'block h-px',
            signal.rising ? 'bg-foreground' : 'bg-[rgba(233,238,247,0.35)]',
          )}
          initial={still ? false : { scaleX: 0 }}
          animate={{ scaleX: Math.max(0.03, signal.value / ceiling) }}
          transition={{ duration: 0.55, ease: EASE_OUT }}
          style={{ transformOrigin: 'left' }}
        />
      </span>
      <span className="data w-10 shrink-0 text-right text-text-3">{signal.value}</span>
    </li>
  )
}

function Freshness({ source }: { source: TrendSource }) {
  if (source.last_mode === 'never') {
    return <span className="data text-text-3">never pulled</span>
  }
  if (source.last_mode === 'failed') {
    return <span className="data text-flag">last pull failed</span>
  }
  return (
    <span className="data text-text-3">
      {source.last_mode === 'offline' ? 'sample' : 'live'} ·{' '}
      {source.last_scraped_at ? ago(source.last_scraped_at) : '—'}
    </span>
  )
}

function AddKeyword({ onAdd }: { onAdd: (keyword: string, note: string) => void }) {
  const [keyword, setKeyword] = useState('')
  const [note, setNote] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!keyword.trim()) return
    onAdd(keyword.trim(), note.trim())
    setKeyword('')
    setNote('')
  }

  return (
    <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-3">
      <div className="min-w-[12rem] flex-1">
        <label htmlFor="keyword" className="label block">
          Watch another keyword
        </label>
        <input
          id="keyword"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="hari raya hamper"
          className="mt-2 w-full rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-sm text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]"
        />
      </div>
      <div className="min-w-[12rem] flex-[1.4]">
        <label htmlFor="why" className="label block">
          Why you’re watching it
        </label>
        <input
          id="why"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Gifting demand peaks three weeks out."
          className="mt-2 w-full rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-sm text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]"
        />
      </div>
      <motion.button
        type="submit"
        disabled={!keyword.trim()}
        whileHover={keyword.trim() ? { y: -1 } : undefined}
        whileTap={keyword.trim() ? { scale: 0.985 } : undefined}
        transition={MICRO}
        className="display rounded-full border border-edge-strong px-4 py-2.5 text-[0.8125rem] text-foreground transition-colors hover:bg-[rgba(233,238,247,0.06)] disabled:cursor-not-allowed disabled:opacity-35"
      >
        Add
      </motion.button>
    </form>
  )
}

/** What the two corpora actually hold, side by side.
 *
 * Shown together because the separation between them is the load-bearing idea:
 * brand knowledge can veto a concept, trends cannot, and they are indexed
 * apart so a hashtag can never be cited as a product fact. */
function Corpus({ status }: { status: TrendStatus }) {
  return (
    <section className="mt-16 border-t border-edge pt-10">
      <h2 className="display text-sm">What the planner reads</h2>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <Corpora
          title="Trend corpus"
          chunks={status.trend_chunks}
          rule="Inspiration. Can suggest an angle, never justify a claim."
        />
        <Corpora
          title="Company knowledge"
          chunks={status.company_chunks}
          rule="Ground truth. Can veto a concept outright."
        />
      </div>

      {status.documents.length > 0 && (
        <ul className="mt-8 divide-y divide-edge">
          {status.documents.map((document) => (
            <li
              key={document.source}
              className="flex items-baseline gap-4 py-2.5"
            >
              <span className="data shrink-0 text-text-3">{document.source}</span>
              <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-text-2">
                {document.heading}
              </span>
              <span className="data shrink-0 text-text-3">
                {document.chunks} {document.chunks === 1 ? 'chunk' : 'chunks'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Corpora({
  title,
  chunks,
  rule,
}: {
  title: string
  chunks: number
  rule: string
}) {
  return (
    <div className="rounded-xl border border-edge px-5 py-4">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-[0.8125rem] text-text-2">{title}</span>
        <span className="display text-[1.25rem]">{chunks}</span>
      </div>
      <p className="mt-2 text-[0.75rem] leading-relaxed text-text-3">{rule}</p>
    </div>
  )
}

/** The strongest few of each kind, each measured against its own kind.
 *
 * Rising and top are not one ranking. Google scores a breakout query as a
 * multiple of its old volume and a top query on a 0–100 share, so a single
 * sort buries every top query under the rising ones, and a single bar scale
 * draws a dominant top query as a stub. Both are shown, and each is drawn
 * against the strongest of its own bucket.
 */
function strongest(
  signals: TrendSignal[],
): { signal: TrendSignal; ceiling: number }[] {
  const bucket = (rising: boolean, take: number) => {
    const inBucket = signals
      .filter((signal) => signal.rising === rising)
      .sort((a, b) => b.value - a.value)
    const ceiling = Math.max(1, ...inBucket.map((signal) => signal.value))
    return inBucket.slice(0, take).map((signal) => ({ signal, ceiling }))
  }
  return [...bucket(true, 4), ...bucket(false, 3)]
}

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}
