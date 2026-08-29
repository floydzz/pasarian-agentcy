import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AgentStation } from '@/components/os/AgentStation'
import { FlowGraph, IMAGE_FLOW, type NodeState } from '@/components/os/FlowGraph'
import { ImageGate } from '@/components/os/ImageGate'
import { Booting, StageCaption, StudioShell } from '@/components/os/StudioShell'
import { TrackItem, WorkTrack } from '@/components/os/WorkTrack'
import { AssetCard } from '@/components/AssetCard'
import { ConceptCard } from '@/components/ConceptCard'
import { ProductReferenceLibrary } from '@/components/ProductReferenceLibrary'
import { VariantCard } from '@/components/VariantCard'
import { useConsole } from '@/hooks/useConsole'
import { rememberCampaign } from '@/lib/lastCampaign'
import { api, ApiError } from '@/api/client'
import type { AgentName } from '@/api/stream'
import type { Asset, Campaign, Concept, ConceptStatus, ProductReference, Variant } from '@/api/types'

/** The image studio: a campaign's still creative, from brief to shippable.
 *
 * It fills the shared studio shell, so everything structural about it — where
 * the machine sits, how it recedes at a gate, where the work track runs — is
 * the same here as in the video studio, and stays the same by construction.
 */
export function ImageStudio() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [concepts, setConcepts] = useState<Concept[]>([])
  const [variants, setVariants] = useState<Variant[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [productReferences, setProductReferences] = useState<ProductReference[]>([])
  const [tab, setTab] = useState('concepts')
  const { log, agents, running, error, run, clearError } = useConsole()
  const acceptedHandoffs = useRef(new Set<string>())

  const refresh = useCallback(async () => {
    const [fetched, itsConcepts, itsVariants, itsAssets, itsProductReferences] = await Promise.all([
      api.getCampaign(id),
      api.listConcepts(id),
      api.listVariants(id),
      api.listAssets(id),
      api.listProductReferences(id),
    ])
    setCampaign(fetched)
    setConcepts(itsConcepts)
    setVariants(itsVariants)
    setAssets(itsAssets)
    setProductReferences(itsProductReferences)
  }, [id])

  useEffect(() => {
    rememberCampaign(id)
    refresh().catch((thrown: ApiError) => toast.error(thrown.message))
  }, [id, refresh])

  useEffect(() => {
    if (error) {
      toast.error(error)
      clearError()
      refresh().catch(() => undefined)
    }
  }, [error, clearError, refresh])

  /** The chat dock may request a stage, but this studio owns execution and
   * the live monitor. Removing the one-use query before opening the stream
   * also makes refreshes safe: they never replay a paid pipeline action. */
  useEffect(() => {
    if (!campaign) return
    const stage = searchParams.get('run')
    if (stage !== 'plan' && stage !== 'generate') return
    const handoff = `${campaign.id}:${stage}`
    if (acceptedHandoffs.current.has(handoff)) return
    acceptedHandoffs.current.add(handoff)
    setSearchParams({}, { replace: true })

    if (stage === 'plan') {
      void run('planner', `/campaigns/${campaign.id}/plan/stream`, () => {
        setTab('concepts')
        refresh().catch(() => undefined)
      })
    } else {
      void run('crew', `/campaigns/${campaign.id}/generate/stream`, () => {
        setTab('variants')
        refresh().catch(() => undefined)
      })
    }
  }, [campaign, refresh, run, searchParams, setSearchParams])

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

  const gate = (which: 'plan' | 'asset'): NodeState => {
    const waived =
      which === 'plan' ? campaign.auto_approve_plan : campaign.auto_approve_assets
    if (waived) return 'waived'
    const open = which === 'plan' ? atPlanGate : atAssetGate
    return open ? 'blocking' : 'quiet'
  }

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

  const caption = revision
    ? `Revision ${revision.current} of ${revision.max}`
    : lastVerdict
      ? `Last verdict — ${lastVerdict.replace(/_/g, ' ')}`
      : running
        ? 'Bounded to two revisions'
        : null

  return (
    <StudioShell
      medium="image"
      campaign={campaign}
      running={running}
      halted={halted}
      log={log}
      station={<AgentStation agents={agents} lastDetail={lastDetail} />}
      graph={
        <FlowGraph
          flow={IMAGE_FLOW}
          agents={agents}
          gates={{ plan_gate: gate('plan'), asset_gate: gate('asset') }}
          lastVerdict={lastVerdict}
        />
      }
      caption={<StageCaption text={caption} />}
      gate={
        <ImageGate
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
          onRejectRest={() =>
            act(async () => {
              // Sequential rather than in parallel: these are writes to the
              // same campaign and the gate re-reads it afterwards, so a burst
              // would race the refresh for no gain on a handful of rows.
              const undecided = assets.filter(
                (asset) => asset.review_status === 'pending',
              )
              for (const asset of undecided) await api.rejectAsset(asset.id)
              setTab('creatives')
              toast.success(
                `${undecided.length} ${undecided.length === 1 ? 'creative' : 'creatives'} rejected`,
              )
            })
          }
          onExport={() => navigate(`/campaigns/${campaign.id}/export`)}
          onAutoMode={(payload) => act(() => api.setAutoMode(campaign.id, payload))}
        />
      }
    >
      <ProductReferenceLibrary
        campaignId={campaign.id}
        references={productReferences}
        disabled={running !== null}
        onChange={setProductReferences}
      />
      <WorkTrack
        tracks={[
          { id: 'concepts', label: 'Concepts', count: concepts.length },
          { id: 'variants', label: 'Variants', count: variants.length },
          { id: 'creatives', label: 'Creatives', count: assets.length },
        ]}
        tab={tab}
        onTab={setTab}
        empty={empty}
        review={atPlanGate && tab === 'concepts'}
      >
        {tab === 'concepts'
          ? concepts.map((concept, index) => (
              <TrackItem key={concept.id} review={atPlanGate}>
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
    </StudioShell>
  )
}
