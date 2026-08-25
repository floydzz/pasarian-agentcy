import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { toast } from 'sonner'
import { AgentStation } from '@/components/os/AgentStation'
import { FlowGraph } from '@/components/os/FlowGraph'
import { GateBar } from '@/components/os/GateBar'
import { LogDrawer } from '@/components/os/LogDrawer'
import { TopBar } from '@/components/os/TopBar'
import { TrackItem, WorkTrack, type TrackTab } from '@/components/os/WorkTrack'
import { AssetCard } from '@/components/AssetCard'
import { ConceptCard } from '@/components/ConceptCard'
import { VariantCard } from '@/components/VariantCard'
import { useConsole } from '@/hooks/useConsole'
import { BOOT, DEPTH, EASE_OUT, rise } from '@/lib/motion'
import { api, ApiError } from '@/api/client'
import type { AgentName } from '@/api/stream'
import type { Asset, Campaign, Concept, ConceptStatus, Variant } from '@/api/types'

/** The console.
 *
 * One screen, and one structural idea: depth is attention. While the machine
 * works, the station and the graph are forward and lit. The moment a gate
 * halts the run, the machine recedes — back, dim, out of focus — and the work
 * comes to the front. The product's whole claim is that a person stands
 * between the agents and the ad spend, so the interface performs it rather
 * than captioning it. */
export function Console() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [concepts, setConcepts] = useState<Concept[]>([])
  const [variants, setVariants] = useState<Variant[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [tab, setTab] = useState<TrackTab>('concepts')
  const { log, agents, running, error, run, clearError } = useConsole()
  const still = useReducedMotion()

  const refresh = useCallback(async () => {
    const [fetched, itsConcepts, itsVariants, itsAssets] = await Promise.all([
      api.getCampaign(id),
      api.listConcepts(id),
      api.listVariants(id),
      api.listAssets(id),
    ])
    setCampaign(fetched)
    setConcepts(itsConcepts)
    setVariants(itsVariants)
    setAssets(itsAssets)
  }, [id])

  useEffect(() => {
    refresh().catch((thrown: ApiError) => toast.error(thrown.message))
  }, [refresh])

  useEffect(() => {
    if (error) {
      toast.error(error)
      clearError()
      refresh().catch(() => undefined)
    }
  }, [error, clearError, refresh])

  /** Every mutation refreshes, so the screen can never disagree with the API. */
  const act = useCallback(
    async (action: () => Promise<unknown>) => {
      try {
        await action()
      } catch (thrown) {
        toast.error((thrown as ApiError).message)
      } finally {
        await refresh().catch(() => undefined)
      }
    },
    [refresh],
  )

  const lastDetail = useMemo(() => {
    const latest: Partial<Record<AgentName, string>> = {}
    for (const line of log) latest[line.agent] = line.detail
    return latest
  }, [log])

  const revision = useMemo(() => {
    for (let index = log.length - 1; index >= 0; index -= 1) {
      const { data } = log[index]
      if (typeof data?.revision === 'number') {
        return { current: data.revision as number, max: 2 }
      }
    }
    return null
  }, [log])

  /** The last time work came back: the director's verdict, or QA's.
   *
   * Both are read here rather than only the director's, because the graph draws
   * a return edge for each and a picture that only ever fires two of its three
   * arcs would be quietly lying about the third. */
  const lastVerdict = useMemo(() => {
    for (let index = log.length - 1; index >= 0; index -= 1) {
      const { data } = log[index]
      if (typeof data?.verdict === 'string') return data.verdict
      if (typeof data?.status === 'string') return data.status
    }
    return null
  }, [log])

  if (!campaign) return <Booting />

  const atPlanGate = campaign.status === 'pending_plan_approval'
  const atAssetGate = campaign.status === 'pending_asset_review'
  const halted = atPlanGate || atAssetGate
  const awaitingCrew = concepts.filter(
    (concept) =>
      concept.status === 'approved' &&
      !variants.some((variant) => variant.concept_id === concept.id),
  ).length
  const awaitingRender = variants.filter(
    (variant) => !assets.some((asset) => asset.variant_id === variant.id),
  ).length
  const variantOf = (asset: Asset) => variants.find((v) => v.id === asset.variant_id)

  const empty =
    tab === 'concepts'
      ? concepts.length === 0
        ? 'No concepts yet. Run the planner and they will land here for review.'
        : null
      : tab === 'variants'
        ? variants.length === 0
          ? 'No variants yet. Approve at least one concept and run the crew.'
          : null
        : assets.length === 0
          ? 'No creatives yet. Render the variants and they will land here.'
          : null

  return (
    <motion.div
      initial="hidden"
      animate="shown"
      className="relative flex h-full flex-col overflow-hidden bg-void text-foreground"
    >
      <Ambience active={running !== null} halted={halted} still={Boolean(still)} />

      <TopBar campaign={campaign} running={running} />

      {/* The machine. It steps back when you are needed. */}
      <motion.div
        className="relative z-10 shrink-0 px-5 sm:px-8"
        initial={false}
        animate={{
          scale: halted ? 0.955 : 1,
          opacity: halted ? 0.5 : 1,
          filter: halted && !still ? 'blur(1.5px)' : 'blur(0px)',
          marginBottom: halted ? '-3rem' : '0rem',
        }}
        transition={DEPTH}
        style={{ transformOrigin: 'top center' }}
        // A receded machine is out of reach as well as out of focus, so tabbing
        // cannot land on a control the interface has visibly put away.
        inert={halted}
      >
        <motion.div variants={rise(BOOT.station)}>
          <AgentStation agents={agents} lastDetail={lastDetail} />
        </motion.div>

        <div className="mx-auto mt-2 w-full max-w-[52rem]">
          <FlowGraph agents={agents} campaign={campaign} lastVerdict={lastVerdict} />
        </div>

        <StageCaption
          revision={running ? revision : null}
          lastVerdict={lastVerdict}
          running={running}
        />
      </motion.div>

      <GateBar
        campaign={campaign}
        concepts={concepts}
        assets={assets}
        running={running}
        awaitingCrew={awaitingCrew}
        awaitingRender={awaitingRender}
        onPlan={() =>
          run('planner', `/campaigns/${campaign.id}/plan/stream`, () => {
            setTab('concepts')
            refresh().catch(() => undefined)
          })
        }
        onGenerate={() =>
          run('crew', `/campaigns/${campaign.id}/generate/stream`, () => {
            setTab('variants')
            refresh().catch(() => undefined)
          })
        }
        onRender={() =>
          run('studio', `/campaigns/${campaign.id}/render/stream`, () => {
            setTab('creatives')
            refresh().catch(() => undefined)
          })
        }
        onApprovePlan={() =>
          act(async () => {
            await api.approvePlan(campaign.id)
            toast.success('Plan released — the crew can start')
          })
        }
        onApproveAssets={() =>
          act(async () => {
            await api.approveAllAssets(campaign.id)
            toast.success('Creatives approved — ready to export')
            navigate(`/campaigns/${campaign.id}/export`)
          })
        }
        onAutoMode={(payload) => act(() => api.setAutoMode(campaign.id, payload))}
      />

      <WorkTrack
        tab={tab}
        onTab={setTab}
        counts={{
          concepts: concepts.length,
          variants: variants.length,
          creatives: assets.length,
        }}
        empty={empty}
      >
        {tab === 'concepts'
          ? concepts.map((concept, index) => (
              <TrackItem key={concept.id}>
                <ConceptCard
                  concept={concept}
                  index={index}
                  open={atPlanGate}
                  busy={running !== null}
                  onDecide={(decision: ConceptStatus) =>
                    act(() => api.decide(concept.id, decision))
                  }
                  onRevise={(note) =>
                    act(async () => {
                      await api.revise(concept.id, note)
                      toast.success('Concept reworked — take another look')
                    })
                  }
                />
              </TrackItem>
            ))
          : tab === 'variants'
            ? variants.map((variant) => (
                <TrackItem key={variant.id}>
                  <VariantCard variant={variant} />
                </TrackItem>
              ))
            : assets.map((asset) => (
                <TrackItem key={asset.id}>
                  <AssetCard
                    asset={asset}
                    variant={variantOf(asset)}
                    busy={running !== null}
                    onApprove={() => act(() => api.approveAsset(asset.id))}
                    onReject={() => act(() => api.rejectAsset(asset.id))}
                    onRedo={() =>
                      act(async () => {
                        await api.redoAsset(asset.id)
                        toast.success('Re-rendered — take another look')
                      })
                    }
                  />
                </TrackItem>
              ))}
      </WorkTrack>

      <LogDrawer log={log} running={running} />
    </motion.div>
  )
}

/** One line under the graph: what the machine is doing to itself right now.
 *
 * A revision outranks everything else, because it is the only event that costs
 * work already done. */
function StageCaption({
  revision,
  lastVerdict,
  running,
}: {
  revision: { current: number; max: number } | null
  lastVerdict: string | null
  running: string | null
}) {
  const text = revision
    ? `Revision ${revision.current} of ${revision.max}`
    : lastVerdict
      ? `Last verdict — ${lastVerdict.replace(/_/g, ' ')}`
      : running
        ? 'Bounded to two revisions'
        : null

  return (
    <div className="flex h-5 items-center justify-center">
      <AnimatePresence mode="wait" initial={false}>
        {text && (
          <motion.p
            key={text}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.28, ease: EASE_OUT }}
            className="data text-text-3"
          >
            {text}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}

/** The light the instrument sits in.
 *
 * It brightens while work is moving and turns warm while a gate is open —
 * the room reacting, not a widget. This is the one thing on screen that drifts
 * when nothing is happening, and it drifts slowly enough to read as air. */
function Ambience({
  active,
  halted,
  still,
}: {
  active: boolean
  halted: boolean
  still: boolean
}) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <motion.div
        className="absolute -top-1/3 left-1/2 h-[70vh] w-[110vw] -translate-x-1/2 rounded-[50%]"
        initial={false}
        animate={{
          opacity: active ? 0.85 : 0.42,
          background: halted
            ? 'radial-gradient(closest-side, rgba(255,190,106,0.13), transparent 72%)'
            : 'radial-gradient(closest-side, rgba(233,238,247,0.09), transparent 72%)',
        }}
        transition={{ duration: 1.1, ease: EASE_OUT }}
      />
      {!still && (
        <motion.div
          className="absolute -top-1/4 left-1/2 h-[55vh] w-[70vw] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(closest-side,rgba(233,238,247,0.05),transparent_70%)]"
          animate={{ x: ['-52%', '-48%', '-52%'], scale: [1, 1.08, 1] }}
          transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      {/* Weight at the bottom of the frame, so the instrument sits in the dark
          rather than floating on a flat field. */}
      <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/50 to-transparent" />
    </div>
  )
}

function Booting() {
  return (
    <div className="flex h-full items-center justify-center bg-void">
      <motion.div
        className="h-1.5 w-1.5 rounded-full bg-foreground"
        animate={{ scale: [1, 2.4, 1], opacity: [0.35, 1, 0.35] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}
