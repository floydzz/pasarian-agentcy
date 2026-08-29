import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AgentStation } from '@/components/os/AgentStation'
import { FlowGraph, VIDEO_FLOW, type NodeState } from '@/components/os/FlowGraph'
import { Booting, StageCaption, StudioShell } from '@/components/os/StudioShell'
import { VideoGate } from '@/components/os/VideoGate'
import { TrackItem, WorkTrack } from '@/components/os/WorkTrack'
import { AddSceneCard, SceneCard } from '@/components/video/SceneCard'
import { CutCard } from '@/components/video/CutCard'
import { ProductReferenceLibrary } from '@/components/ProductReferenceLibrary'
import { CinematicComposerPanel } from '@/components/video/CinematicComposerPanel'
import { useConsole, VIDEO_AGENTS } from '@/hooks/useConsole'
import { rememberCampaign } from '@/lib/lastCampaign'
import { api, ApiError } from '@/api/client'
import type { AgentName } from '@/api/stream'
import type {
  Campaign,
  MarketingVideo,
  MarketingVideoCreate,
  MarketingVideoScene,
  ProductReference,
} from '@/api/types'

/** The video studio: the same campaign, moving.
 *
 * It is the image studio's twin by construction — same shell, same station,
 * same graph, same filmstrip — and differs only where the medium genuinely
 * differs. A video has one gate instead of two, because the storyboard is
 * written by the person rather than proposed by the planner, so the only
 * decision owed is on the cut that comes back.
 *
 * The storyboard opens seeded from the campaign's approved work, so a person
 * who has already decided what this campaign says is not asked to say it again.
 */
const MIN_SCENES = 3
const MAX_SCENES = 8

export function VideoStudio() {
  const id = Number(useParams().id)
  const [searchParams, setSearchParams] = useSearchParams()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [draft, setDraft] = useState<MarketingVideoCreate | null>(null)
  const [videos, setVideos] = useState<MarketingVideo[]>([])
  const [productReferences, setProductReferences] = useState<ProductReference[]>([])
  const [tab, setTab] = useState('storyboard')
  // Whether the workspace has a b-roll provider at all. Asked once: it is a
  // fact about configuration, not about this campaign.
  const [brollAvailable, setBrollAvailable] = useState(false)
  const { log, agents, running, error, run, clearError } = useConsole()

  useEffect(() => {
    api
      .system()
      .then((system) => setBrollAvailable(system.broll_available))
      .catch(() => setBrollAvailable(false))
  }, [])

  const refresh = useCallback(async () => {
    const [fetched, itsVideos, itsProductReferences] = await Promise.all([
      api.getCampaign(id),
      api.listCampaignVideos(id),
      api.listProductReferences(id),
    ])
    setCampaign(fetched)
    setVideos(itsVideos)
    setProductReferences(itsProductReferences)
  }, [id])

  useEffect(() => {
    rememberCampaign(id)
    refresh().catch((thrown: ApiError) => toast.error(thrown.message))
  }, [id, refresh])

  // The seed is fetched once per campaign. Re-seeding on every refresh would
  // throw away edits the person had already made to the storyboard.
  useEffect(() => {
    let current = true
    api
      .campaignVideoBrief(id)
      .then((brief) => {
        if (current) setDraft(brief)
      })
      .catch((thrown: ApiError) => toast.error(thrown.message))
    return () => {
      current = false
    }
  }, [id])

  useEffect(() => {
    if (error) {
      toast.error(error)
      clearError()
      refresh().catch(() => undefined)
    }
  }, [error, clearError, refresh])

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

  const lastVerdict = useMemo(() => {
    for (let index = log.length - 1; index >= 0; index -= 1) {
      const { data } = log[index]
      if (typeof data?.verdict === 'string') return data.verdict
      if (typeof data?.status === 'string') return data.status
    }
    return null
  }, [log])

  if (!campaign || !draft) return <Booting />

  const workspace = searchParams.get('view') === 'clips' ? 'clips' : 'script'
  const setWorkspace = (next: 'script' | 'clips') =>
    setSearchParams(next === 'clips' ? { view: 'clips' } : {}, { replace: true })

  const scenes = draft.storyboard
  const pending = videos.filter((video) => video.review_status === 'pending')
  const halted = pending.length > 0

  const patchScene = (index: number, patch: Partial<MarketingVideoScene>) =>
    setDraft({
      ...draft,
      storyboard: scenes.map((scene, at) => (at === index ? { ...scene, ...patch } : scene)),
    })

  const addScene = () =>
    setDraft({
      ...draft,
      storyboard: [
        ...scenes,
        {
          eyebrow: 'New beat',
          headline: 'What this scene says',
          body: 'One clear sentence the viewer should leave with.',
          layout: 'feature',
        },
      ],
    })

  const removeScene = (index: number) =>
    setDraft({ ...draft, storyboard: scenes.filter((_, at) => at !== index) })

  const render = () =>
    run(
      'studio',
      `/campaigns/${campaign.id}/videos/render/stream`,
      () => {
        setTab('cuts')
        refresh().catch(() => undefined)
      },
      draft,
    )

  /** Approving at the gate clears every cut still waiting on a decision. */
  const approveAll = () =>
    act(async () => {
      await Promise.all(pending.map((video) => api.approveVideo(video.id)))
      toast.success(pending.length === 1 ? 'Cut approved' : 'Cuts approved')
    })

  const gate: NodeState = halted ? 'blocking' : 'quiet'

  const empty =
    tab === 'cuts' && videos.length === 0
      ? 'No cuts yet. Write the storyboard and render it — they will land here for review.'
      : null

  const caption = running
    ? 'Rendering scene by scene'
    : lastVerdict
      ? `Last verdict — ${lastVerdict.replace(/_/g, ' ')}`
      : `${scenes.length * 3}s · ${scenes.length} scenes`

  return (
    <StudioShell
      medium="video"
      campaign={campaign}
      running={running}
      halted={halted}
      log={log}
      station={<AgentStation crew={VIDEO_AGENTS} agents={agents} lastDetail={lastDetail} />}
      graph={
        <FlowGraph
          flow={VIDEO_FLOW}
          agents={agents}
          gates={{ review_gate: gate }}
          lastVerdict={lastVerdict}
        />
      }
      caption={<StageCaption text={caption} />}
      gate={
        <VideoGate
          videos={videos}
          running={running}
          scenes={scenes.length}
          broll={draft.use_broll}
          brollAvailable={brollAvailable}
          onBroll={(use_broll) => setDraft({ ...draft, use_broll })}
          onRender={render}
          onApprove={approveAll}
        />
      }
    >
      <div className="flex shrink-0 items-center gap-1 border-b border-edge px-5 pt-3 sm:px-8">
        <WorkspaceTab active={workspace === 'script'} onClick={() => setWorkspace('script')}>
          Script & storyboard
        </WorkspaceTab>
        <WorkspaceTab active={workspace === 'clips'} onClick={() => setWorkspace('clips')}>
          AI clips & compose
        </WorkspaceTab>
      </div>

      {workspace === 'script' ? (
        <>
          <ProductReferenceLibrary
            campaignId={campaign.id}
            references={productReferences}
            disabled={running !== null}
            onChange={(next) => {
              setProductReferences(next)
              setDraft((current) =>
                current
                  ? {
                      ...current,
                      product_reference_id:
                        next.find((reference) => reference.is_primary)?.id ?? null,
                    }
                  : current,
              )
            }}
          />
          <WorkTrack
            tracks={[
              { id: 'storyboard', label: 'Storyboard', count: scenes.length },
              { id: 'cuts', label: 'Local cuts', count: videos.length },
            ]}
            tab={tab}
            onTab={setTab}
            empty={empty}
          >
            {tab === 'storyboard' ? (
              <>
                {scenes.map((scene, index) => (
                  <TrackItem key={index}>
                    <SceneCard
                      index={index}
                      scene={scene}
                      removable={scenes.length > MIN_SCENES}
                      busy={running !== null}
                      onChange={(patch) => patchScene(index, patch)}
                      onRemove={() => removeScene(index)}
                    />
                  </TrackItem>
                ))}
                {scenes.length < MAX_SCENES && (
                  <TrackItem key="add">
                    <AddSceneCard onAdd={addScene} disabled={running !== null} />
                  </TrackItem>
                )}
              </>
            ) : (
              videos.map((video) => (
                <TrackItem key={video.id}>
                  <CutCard
                    video={video}
                    busy={running !== null}
                    onApprove={() => act(() => api.approveVideo(video.id))}
                    onReject={() => act(() => api.rejectVideo(video.id))}
                    onRedo={() =>
                      act(async () => {
                        await api.redoVideo(video.id)
                        toast.success('Re-rendered — take another look')
                      })
                    }
                  />
                </TrackItem>
              ))
            )}
          </WorkTrack>
        </>
      ) : (
        <CinematicComposerPanel campaign={campaign} script={draft} />
      )}
    </StudioShell>
  )
}

function WorkspaceTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative px-3.5 py-2.5 text-[0.75rem] transition-colors ${active ? 'text-video' : 'text-text-3 hover:text-text-2'}`}
    >
      {children}
      {active && <span className="absolute inset-x-3.5 bottom-0 h-px bg-video" />}
    </button>
  )
}
