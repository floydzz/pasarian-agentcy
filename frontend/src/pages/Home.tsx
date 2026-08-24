import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, useReducedMotion } from 'motion/react'
import { toast } from 'sonner'
import { AgentCore } from '@/components/agents/AgentCore'
import { cn } from '@/lib/utils'
import { EASE_IN_OUT, EASE_OUT, MICRO, SETTLE, rise } from '@/lib/motion'
import { AGENTS } from '@/hooks/useConsole'
import { api, ApiError } from '@/api/client'
import type { Campaign } from '@/api/types'

/** Centres of the four columns — where the work sits while each agent holds it. */
const RAIL = ['12.5%', '37.5%', '62.5%', '87.5%'] as const

const STATUS_LABEL: Record<Campaign['status'], string> = {
  draft: 'draft',
  planning: 'planning',
  pending_plan_approval: 'halted — plan gate',
  generating: 'generating',
  pending_asset_review: 'halted — asset gate',
  ready_to_publish: 'ready',
  published: 'published',
}

/** The entrance.
 *
 * The hero is the crew itself, running its real sequence: planner, copywriter,
 * art director, creative director, one at a time, in the order work actually
 * moves through them. It is the most characteristic thing this product has, so
 * it is the first thing on the page — a demonstration rather than a
 * description of one. */
export function Home() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null)
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()
  const lit = useSequence(AGENTS.length)

  useEffect(() => {
    api
      .listCampaigns()
      .then(setCampaigns)
      .catch((error: ApiError) => {
        setCampaigns([])
        toast.error(error.message)
      })
  }, [])

  async function create(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim() || !brief.trim() || creating) return
    setCreating(true)
    try {
      const campaign = await api.createCampaign({ name: name.trim(), brief: brief.trim() })
      navigate(`/campaigns/${campaign.id}`)
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <motion.div
      initial="hidden"
      animate="shown"
      className="quiet-scroll relative h-full overflow-x-hidden overflow-y-auto bg-void text-foreground"
    >
      <Ambience />

      <div className="relative mx-auto w-full max-w-5xl px-6 py-16 sm:px-10 lg:py-24">
        <motion.p variants={rise(0)} className="data text-text-3">
          agentcy
        </motion.p>

        <motion.h1
          variants={rise(0.06)}
          className="display-tight mt-5 max-w-3xl text-[2.5rem] leading-[1.02] text-balance sm:text-[3.5rem]"
        >
          Four agents do the work.
          <br />
          <span className="text-text-3">You decide what ships.</span>
        </motion.h1>

        <motion.p
          variants={rise(0.12)}
          className="mt-6 max-w-xl text-[0.9375rem] leading-relaxed text-text-2"
        >
          A planner reads your brand knowledge and today’s Malaysian trends and proposes
          concepts with their sources attached. A copywriter, an art director and a
          creative director build the ones you approve — and the run halts at every gate
          until a person releases it.
        </motion.p>

        {/* The crew, running its real sequence — with the handoff visible.
            The work is on the rail, and it only ever sits under one core. */}
        <motion.div variants={rise(0.2)} className="relative mt-12 sm:mt-16">
          <div className="pointer-events-none absolute inset-x-[12.5%] top-12 hidden h-px bg-edge sm:block" />
          <motion.span
            aria-hidden
            className="pointer-events-none absolute top-12 hidden h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground sm:block"
            animate={{ left: RAIL[Math.max(lit, 0)] }}
            transition={{ duration: 0.9, ease: EASE_IN_OUT }}
          />

          <div className="grid grid-cols-2 gap-y-10 sm:grid-cols-4 sm:gap-y-0">
            {AGENTS.map((agent, index) => {
              const live = lit === index
              return (
                <div
                  key={agent.id}
                  className="relative flex flex-col items-center text-center"
                >
                  {/* Only the working core is lit, and the light is what says
                      so — there is no badge to read. */}
                  <motion.span
                    aria-hidden
                    className="pointer-events-none absolute top-0 h-24 w-24 rounded-full bg-[radial-gradient(closest-side,rgba(233,238,247,0.16),transparent_70%)] blur-xl"
                    animate={{ opacity: live ? 1 : 0, scale: live ? 1.6 : 1 }}
                    transition={{ duration: 0.7, ease: EASE_OUT }}
                  />
                  <motion.div
                    className={cn(
                      'relative h-24 w-24 transition-colors duration-700',
                      live ? 'text-[#e9eef7]' : 'text-[rgba(233,238,247,0.13)]',
                    )}
                    animate={{ y: live ? -5 : 0 }}
                    transition={SETTLE}
                  >
                    <AgentCore agent={agent.id} state={live ? 'running' : 'idle'} />
                  </motion.div>
                  <p
                    className={cn(
                      'display mt-5 text-[0.8125rem] transition-colors duration-700',
                      live ? 'text-foreground' : 'text-text-3',
                    )}
                  >
                    {agent.label}
                  </p>
                  <p
                    className={cn(
                      'mt-1 max-w-[11rem] text-[0.6875rem] leading-snug transition-colors duration-700',
                      live ? 'text-text-2' : 'text-text-3',
                    )}
                  >
                    {agent.role}
                  </p>
                </div>
              )
            })}
          </div>
        </motion.div>

        {/* The work starts here. */}
        <motion.div
          variants={rise(0.28)}
          className="mt-14 grid gap-10 border-t border-edge pt-12 sm:mt-20 lg:grid-cols-[1fr_1fr] lg:gap-16"
        >
          <section>
            <h2 className="display text-sm">New campaign</h2>
            <form onSubmit={create} className="mt-5 space-y-5">
              <Field label="Name" htmlFor="name">
                <input
                  id="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Merdeka 2026 — hydrating serum"
                  className="w-full rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-sm text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]"
                />
              </Field>

              <Field
                label="Brief"
                htmlFor="brief"
                hint="Say what you’re selling, to whom, and the angle you want."
              >
                <textarea
                  id="brief"
                  rows={5}
                  value={brief}
                  onChange={(event) => setBrief(event.target.value)}
                  placeholder="Push the Embun serum through Merdeka. Target working women in KL and Selangor who buy on Shopee. Lead with the humidity problem, not the festival."
                  className="w-full resize-none rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-sm leading-relaxed text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]"
                />
              </Field>

              <motion.button
                type="submit"
                disabled={!name.trim() || !brief.trim() || creating}
                whileHover={{ y: -1 }}
                whileTap={{ y: 0, scale: 0.985 }}
                transition={MICRO}
                className="display rounded-full bg-foreground px-5 py-2.5 text-[0.8125rem] text-void transition-opacity hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {creating ? 'Opening…' : 'Open a console'}
              </motion.button>
            </form>
          </section>

          <section className="min-w-0">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="display text-sm">Campaigns</h2>
              {campaigns && <span className="data text-text-3">{campaigns.length}</span>}
            </div>

            {campaigns === null ? (
              <p className="mt-5 text-sm text-text-3">Loading…</p>
            ) : campaigns.length === 0 ? (
              <p className="mt-5 text-sm text-text-3">
                Nothing here yet. Write a brief and the planner will take it from there.
              </p>
            ) : (
              <ul className="mt-2 divide-y divide-edge">
                {campaigns.map((campaign) => {
                  const halted = campaign.status.startsWith('pending_')
                  return (
                    <li key={campaign.id}>
                      <Link
                        to={`/campaigns/${campaign.id}`}
                        className="group flex items-center gap-4 py-3.5 transition-colors"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-text-2 transition-colors group-hover:text-foreground">
                            {campaign.name}
                          </span>
                          <span className="mt-0.5 block truncate text-[0.6875rem] text-text-3">
                            {campaign.brief}
                          </span>
                        </span>
                        <span
                          className={cn(
                            'data shrink-0',
                            halted ? 'text-halt' : 'text-text-3',
                          )}
                        >
                          {STATUS_LABEL[campaign.status]}
                        </span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </motion.div>
      </div>
    </motion.div>
  )
}

/** Cycles through the crew in the order work moves through it. */
function useSequence(count: number, everyMs = 2600) {
  const still = useReducedMotion()
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (still) return
    const timer = setInterval(() => setIndex((current) => (current + 1) % count), everyMs)
    return () => clearInterval(timer)
  }, [count, everyMs, still])

  return still ? -1 : index
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string
  htmlFor: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="label block">
        {label}
      </label>
      <div className="mt-2">{children}</div>
      {hint && <p className="mt-2 text-[0.6875rem] text-text-3">{hint}</p>}
    </div>
  )
}

function Ambience() {
  const still = useReducedMotion()
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -top-1/4 left-1/2 h-[60vh] w-[120vw] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(closest-side,rgba(233,238,247,0.08),transparent_70%)]" />
      {!still && (
        <motion.div
          className="absolute top-[10vh] left-1/2 h-[45vh] w-[65vw] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(closest-side,rgba(233,238,247,0.045),transparent_70%)]"
          animate={{ x: ['-53%', '-47%', '-53%'], scale: [1, 1.1, 1] }}
          transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 1 }}
        animate={{ opacity: 0 }}
        transition={{ duration: 1.2, ease: EASE_OUT }}
        style={{ background: '#05070b' }}
      />
    </div>
  )
}
