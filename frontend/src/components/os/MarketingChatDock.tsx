import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useIsPresent } from 'motion/react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/lib/auth'
import { api, ApiError, request } from '@/api/client'
import type { Campaign, ChatMessage, Conversation } from '@/api/types'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { STRATEGIST_MORPH, SETTLE, STAGGER, STAGGER_CHILD } from '@/lib/motion'

const dockFrame = 'fixed inset-y-3 right-3 z-50 w-[calc(100vw-1.5rem)] max-w-[27rem] sm:inset-y-5 sm:right-5 sm:w-[26rem]'

/** A persistent strategist beside the work, rather than a separate room.
 *
 * The dock keeps discussion and campaign control together: when the server
 * authorizes a plan or crew run, it sends the person to Image studio with a
 * one-use intent. The studio owns the stream and is therefore the truthful
 * place to watch the agents, their graph and their gates work.
 */
export function MarketingChatDock({ onClose, fullPage = false, morphToLauncher = true }: { onClose: () => void; fullPage?: boolean; morphToLauncher?: boolean }) {
  const present = useIsPresent()
  const navigate = useNavigate()
  const { pathname, search, state: routeState } = useLocation()
  const requestedThread = Number(new URLSearchParams(search).get("thread")) || null
  const routeRef = useRef(pathname + search)
  useEffect(() => { routeRef.current = pathname + search }, [pathname, search])
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const campaignId = campaignFromPath(pathname)
  const [threads, setThreads] = useState<Conversation[]>([])
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [startingNew, setStartingNew] = useState(false)
  const [pageCampaign, setPageCampaign] = useState<Campaign | null>(null)
  const actor = useAuth()
  const draftKey = `agentcy-chat-draft:${actor.user.id}:${actor.workspace_id}`
  const [draft, setDraft] = useState(() => fullPage && typeof routeState?.calendarDraft === 'string' ? routeState.calendarDraft : sessionStorage.getItem(draftKey) ?? '')
  useEffect(() => { sessionStorage.setItem(draftKey, draft) }, [draft, draftKey])
  // Calendar briefs enter the composer for review, never the send handler.
  // Consume the navigation state so browser Back does not restore a sent brief.
  useEffect(() => {
    if (fullPage && typeof routeState?.calendarDraft === 'string') navigate(pathname + search, { replace: true, state: null })
  }, [fullPage, routeState, pathname, search, navigate])
  const [moreThreads, setMoreThreads] = useState(true)
  const [historyEnd, setHistoryEnd] = useState<number | null>(null)
  const [manage, setManage] = useState<'rename' | 'delete' | null>(null)
  const [threadName, setThreadName] = useState('')
  const [manageError, setManageError] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [scriptedDemo, setScriptedDemo] = useState(false)
  const [pendingMessage, setPendingMessage] = useState<ChatMessage | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.system().then((system) => setScriptedDemo(system.scripted_demo)).catch(() => undefined)
  }, [])

  const refreshThreads = useCallback(async () => {
    const listed = await api.listConversations()
    setThreads(listed)
    setMoreThreads(listed.length === 30)
    return listed
  }, [])

  const selectForPage = useCallback(
    (listed: Conversation[]) => {
      if (requestedThread !== null && !startingNew) return listed.find(thread => thread.id === requestedThread) ?? null
      if (campaignId !== null) {
        return listed.find((thread) => thread.campaign_id === campaignId) ?? null
      }
      if (startingNew) return null
      return listed.find((thread) => thread.id === conversation?.id) ?? listed[0] ?? null
    },
    [campaignId, conversation?.id, startingNew, requestedThread],
  )

  useEffect(() => {
    let current = true
    setLoading(true)
    refreshThreads()
      .then((listed) => {
        const selected = selectForPage(listed)
        if (selected) return api.getConversation(selected.id).then(full => { if (current) setConversation(full) })
        if (requestedThread !== null && !startingNew) return api.getConversation(requestedThread).then(full => { if (current) setConversation(full) })
        if (current) setConversation(null)
      })
      .catch((error: ApiError) => toast.error(error.message))
      .finally(() => current && setLoading(false))
    return () => {
      current = false
    }
  }, [refreshThreads, selectForPage, requestedThread, startingNew])

  useEffect(() => {
    if (campaignId === null) {
      setPageCampaign(null)
      return
    }
    let current = true
    const syncCampaign = () =>
      document.hidden ? Promise.resolve() : api
        .getCampaign(campaignId)
        .then((campaign) => current && setPageCampaign(campaign))
        .catch((error: ApiError) => current && toast.error(error.message))
    void syncCampaign()
    // Studio actions happen outside the chat request. Refreshing the compact
    // route context means the next suggested reply changes from image review
    // to video generation without closing or reopening the strategist.
    const timer = window.setInterval(syncCampaign, 3_000)
    return () => {
      current = false
      window.clearInterval(timer)
    }
  }, [campaignId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [conversation?.messages.length, pendingMessage, sending])

  const replaceThread = useCallback((next: Conversation) => {
    setThreads((current) => {
      const rest = current.filter((thread) => thread.id !== next.id)
      return [next, ...rest].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      )
    })
    setConversation(next)
    setStartingNew(false)
  }, [])

  function startThread() {
    // A blank thread is intent, not a useful record. It becomes durable only
    // when the marketer sends their first request via `activeThread`.
    if (fullPage) navigate('/chat')
    setStartingNew(true)
    setConversation(null)
    setDraft('')
    setPendingMessage(null)
  }

  /** Reuse the page's thread, attaching a new one only when the person sends.
   * Opening the dock is not enough reason to leave empty records behind. */
  async function activeThread(): Promise<Conversation> {
    if (campaignId !== null) {
      const existing = threads.find((thread) => thread.campaign_id === campaignId)
      if (existing) return existing

      const created = await api.createConversation({ title: 'Campaign strategy' })
      const attached = await api.updateConversation(created.id, { campaign_id: campaignId })
      replaceThread(attached)
      return attached
    }
    if (conversation) return conversation

    const created = await api.createConversation()
    replaceThread(created)
    return created
  }

  async function submit(event?: FormEvent, suggested?: string) {
    event?.preventDefault()
    const content = (suggested ?? draft).trim()
    if (!content || sending) return

    const submittedFrom = pathname + search
    setSending(true)
    setDraft('')
    // Render the marketer's thought at once. The persisted version from the
    // server replaces this temporary line as soon as the request finishes.
    setPendingMessage(optimisticMessage(content, conversation?.id ?? -1))
    try {
      const active = await activeThread()
      const result = await api.sendConversationMessage(active.id, content)
      if (!mounted.current || routeRef.current !== submittedFrom) return
      const refreshed = await api.getConversation(active.id)
      if (!mounted.current || routeRef.current !== submittedFrom) return
      setPendingMessage(null)
      replaceThread(refreshed)
      if (result.campaign) setPageCampaign(result.campaign)
      if (fullPage && !result.authorized) navigate(`/chat?thread=${active.id}`, { replace: true })

      if (result.authorized === 'calendar') {
        navigate(result.calendar_run_id ? `/calendar?run=${result.calendar_run_id}` : '/calendar')
      } else if (result.authorized === 'cinematic') {
        navigate('/cinematic-trailer/demo')
        toast.success(handoffMessage(result.authorized))
      } else if (result.authorized && result.campaign) {
        // The server has already rechecked campaign state and approvals. The
        // query is a short-lived UI handoff, not an authority to run anything.
        const base = `/campaigns/${result.campaign.id}`
        if (result.authorized === 'plan' || result.authorized === 'generate' || result.authorized === 'render') {
          navigate(`${base}/image?run=${result.authorized}`)
        } else if (result.authorized === 'image') {
          navigate(`${base}/image`)
        } else if (result.authorized === 'video') {
          navigate(
            result.message.action === 'run_video'
              ? `${base}/video/demo?run=render`
              : `${base}/video`,
          )
        } else {
          navigate(`${base}/publish`)
        }
        toast.success(handoffMessage(result.authorized))
      }
    } catch (error) {
      if (!mounted.current || routeRef.current !== submittedFrom) return
      setPendingMessage(null)
      toast.error((error as ApiError).message)
      setDraft(content)
    } finally {
      if (mounted.current) { setSending(false); setPendingMessage(null) }
    }
  }

  function submitOnShortcut(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void submit()
  }

  const title = pageCampaign?.name ?? conversation?.campaign?.name ?? 'Marketing strategist'
  const status = pageCampaign?.status ?? conversation?.campaign?.status
  const selectableThreads = threads.filter(
    (thread) => thread.id === conversation?.id || thread.campaign !== null || (thread.message_count ?? thread.messages.length) > 0,
  )
  const visibleMessages = pendingMessage
    ? [...(conversation?.messages ?? []), pendingMessage]
    : (conversation?.messages ?? [])

  return (
    // Move the complete panel together. The direct child's layout projection
    // corrects content scaling; retiring content cannot intercept clicks.
    // Full-page Chat has no shared layout identity.
    <motion.aside
      layoutId={!fullPage && morphToLauncher ? 'strategist' : undefined}
      aria-label="Marketing strategist"
      aria-hidden={!present || undefined}
      inert={!present}
      transition={STRATEGIST_MORPH}
      style={{ borderRadius: 16, pointerEvents: present ? 'auto' : 'none' }}
      className={fullPage ? 'h-full w-full overflow-hidden bg-void' : cn(dockFrame, 'overflow-hidden border border-edge bg-rise shadow-xl')}
    >
      <motion.div layout={fullPage ? false : 'position'} transition={STRATEGIST_MORPH} className="flex h-full w-full flex-col">
      <header className="flex shrink-0 flex-wrap items-start justify-between gap-3 border-b border-edge px-5 py-4">
        <div className="min-w-0 flex-[1_1_12rem]">
          <p className="label">{fullPage ? 'Your marketing workspace' : 'Marketing strategist'}</p>
          <p className="display mt-1 break-words text-[0.9375rem]">{title}</p>
          {conversation?.marketing_plan_id && <Link to={`/calendar?plan=${conversation.marketing_plan_id}`} className="mt-2 inline-block text-xs font-medium text-brand">View marketing roadmap →</Link>}
          {conversation?.calendar_occasion_id && <Link to="/calendar" className="mt-2 inline-block text-xs font-medium text-brand">Calendar occasion selected</Link>}
          <p className="data mt-1 text-text-3">
            {status ? `Context: ${stageLabel(status)}` : 'Ask a question or start a new strategy'}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => void startThread()}
            disabled={sending}
            className="data rounded-full border border-edge px-2.5 py-1.5 text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
          >
            New
          </button>
          {fullPage && conversation && <button type="button" disabled={sending} className="text-xs text-text-2" onClick={() => { setThreadName(conversation.title); setManageError(''); setManage('rename') }}>Rename</button>}
          {fullPage && conversation && <button type="button" disabled={sending} className="text-xs text-text-3" onClick={() => { setManageError(''); setManage('delete') }}>Delete</button>}
          {!fullPage && <button
            type="button"
            onClick={onClose}
            aria-label="Close marketing chat"
            className="flex h-7 w-7 items-center justify-center rounded-full border border-edge text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
          >
            ×
          </button>}
        </div>
      </header>

      {selectableThreads.length > 0 && (
        <label className="flex shrink-0 items-center gap-2 border-b border-edge px-5 py-2.5">
          <span className="data shrink-0 text-text-3">Thread</span>
          <select disabled={sending}
            value={conversation?.id ?? ''}
            onChange={(event) => {
              const next = selectableThreads.find((thread) => thread.id === Number(event.target.value))
              if (next) {
                setStartingNew(false)
                void api.getConversation(next.id).then(setConversation).catch((error: Error) => toast.error(error.message))
                if (fullPage) navigate(`/chat?thread=${next.id}`)
              }
            }}
            className="min-w-0 flex-1 bg-transparent text-[0.75rem] text-text-2 outline-none"
          >
            <option value="" disabled>Select a conversation</option>
            {selectableThreads.map((thread) => (
              <option key={thread.id} value={thread.id} className="bg-void">
                {threadLabel(thread)}
              </option>
            ))}
          </select>
        </label>
      )}

      {moreThreads && threads.length >= 30 && <button type="button" className="workspace-secondary mx-4 my-2" disabled={loading} onClick={() => { setLoading(true); void api.listConversations(threads.length).then(next => { setThreads(current => [...current, ...next.filter(row => !current.some(existing => existing.id === row.id))]); setMoreThreads(next.length === 30) }).catch(failure => toast.error(failure.message)).finally(() => setLoading(false)) }}>Load more conversations</button>}
      <div className="quiet-scroll min-h-0 flex-1 overflow-y-auto px-4 py-5">
        {conversation && conversation.messages.length >= 50 && historyEnd !== conversation.id && <button className="workspace-secondary mb-4" type="button" onClick={() => { const before = conversation.messages[0].id; void request<ChatMessage[]>(`/conversations/${conversation.id}/messages?before=${before}`).then(rows => { setHistoryEnd(rows.length === 50 ? null : conversation.id); setConversation(current => current?.id === conversation.id ? { ...current, messages: [...rows, ...current.messages] } : current) }).catch(failure => toast.error(failure.message)) }}>Load earlier messages</button>}
        {loading ? (
          <p className="px-1 text-sm text-text-3">Loading strategy context…</p>
        ) : visibleMessages.length === 0 ? (
          <div className="mx-auto max-w-2xl px-1 pt-12">
            <p className="label">A clear plan starts here</p>
            <h1 className="display-tight mb-3 text-3xl">What are we planning?</h1>
            <p className="mt-3 text-[0.875rem] leading-relaxed text-text-2">
              Turn your products, Malaysian occasions and business goals into a practical marketing plan. Start with an idea or explore the calendar.
            </p>
            <div className="mt-6 flex flex-wrap gap-2"><Link to="/calendar" className="workspace-button">Explore calendar</Link><button type="button" className="workspace-secondary" onClick={() => setDraft("Help me plan my next 90 days")}>Plan next 90 days</button><button type="button" className="workspace-secondary" onClick={() => setDraft("Build my next year marketing calendar")}>Plan next year</button></div>
          </div>
        ) : (
          <motion.div variants={STAGGER} initial="hidden" animate="shown" className="mx-auto max-w-3xl space-y-5">
            {visibleMessages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <AnimatePresence>{sending && <Thinking />}</AnimatePresence>
          </motion.div>
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="shrink-0 border-t border-edge bg-rise px-4 py-4 backdrop-blur">
        {scriptedDemo && (
          <div className="mb-3 px-1">
            <p className="mb-2 text-[0.6875rem] leading-relaxed text-text-3">
              {demoNextStep(status)}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {demoReplies(status).map((reply) => (
                <button
                  key={reply}
                  type="button"
                  disabled={sending}
                  onClick={() => void submit(undefined, reply)}
                  className="data rounded-full border border-edge px-2.5 py-1.5 text-[0.625rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground disabled:opacity-100"
                >
                  {reply}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="mx-auto max-w-3xl flex items-end gap-2 rounded-xl border border-edge bg-rise p-2 transition-colors focus-within:border-edge-strong">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={submitOnShortcut}
            rows={2}
            disabled={sending}
            aria-label="Message the strategist" placeholder="Ask what to promote, plan an occasion, or create a campaign…"
            className="min-h-[3rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-[0.8125rem] leading-relaxed text-foreground outline-none placeholder:text-text-3 disabled:opacity-100"
          />
          <button
            type="submit"
            disabled={!draft.trim() || sending}
            className="display mb-0.5 rounded-lg bg-foreground px-3 py-2 text-[0.6875rem] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-100"
          >
            {sending ? 'Thinking' : 'Send'}
          </button>
        </div>
        <p className="mt-2 px-1 text-[0.625rem] text-text-3">
          {scriptedDemo ? 'Scripted demo · zero model tokens · approvals stay with you.' : '⌘/Ctrl + Enter · approval decisions always stay with you.'}
        </p>
      </form>
      <Dialog open={manage !== null} onOpenChange={open => { if (!open) setManage(null) }}><DialogContent><DialogTitle>{manage === 'delete' ? 'Delete this conversation?' : 'Rename conversation'}</DialogTitle><DialogDescription>{manage === 'delete' ? 'This removes the saved messages. Linked campaigns and calendar plans remain available.' : 'Choose a name that is easy to find later.'}</DialogDescription>{manage === 'rename' && <input aria-label="Conversation name" className="workspace-input" maxLength={255} value={threadName} onChange={e => setThreadName(e.target.value)} />}{manageError && <p role="alert" className="text-sm text-destructive">{manageError}</p>}<div className="flex gap-2"><button className="workspace-secondary" onClick={() => setManage(null)}>Cancel</button><button className="workspace-button" disabled={sending || (manage === 'rename' && !threadName.trim())} onClick={() => { if (!conversation) return; setSending(true); void (async () => { try { if (manage === 'rename') replaceThread(await api.updateConversation(conversation.id, { title: threadName.trim() })); else { await api.deleteConversation(conversation.id); setConversation(null); setStartingNew(true); navigate('/chat'); await refreshThreads() } setManage(null) } catch (error) { setManageError((error as Error).message) } finally { setSending(false) } })() }}>{manage === 'delete' ? 'Delete conversation' : 'Save name'}</button></div></DialogContent></Dialog>
      </motion.div>
    </motion.aside>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'system') {
    return (
      <motion.div
        variants={STAGGER_CHILD}
        initial="hidden"
        animate="shown"
        className="border-l border-halt/70 py-1 pl-2.5 text-[0.75rem] leading-relaxed text-text-2"
      >
        {message.content}
      </motion.div>
    )
  }
  const user = message.role === 'user'
  return (
    <motion.article
      variants={STAGGER_CHILD}
      initial="hidden"
      animate="shown"
      className={cn('flex', user ? 'justify-end' : 'justify-start')}
    >
      <div
        className={cn(
          'max-w-full min-w-0 break-words rounded-xl px-3 py-2.5',
          user
            ? 'bg-accent text-foreground'
            : 'border border-edge bg-rise text-text-2',
        )}
      >
        <div className="mb-1 flex items-center gap-1.5">
          <span className="data text-[0.625rem] text-text-3">{user ? 'you' : 'strategist'}</span>
          {message.action && (
            <span className="data rounded-full border border-edge px-1.5 py-0.5 text-[0.5625rem] text-text-3">
              {message.action.replaceAll('_', ' ')}
            </span>
          )}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
        {message.calendar_run_id && <Link className="mt-3 inline-block text-xs font-semibold text-brand underline" to={`/calendar?run=${message.calendar_run_id}`}>Review calendar proposal →</Link>}
      </div>
    </motion.article>
  )
}

function Thinking() {
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={SETTLE}
      className="flex justify-start"
      aria-label="Strategist is typing"
    >
      <div className="flex items-center gap-1.5 rounded-xl border border-edge bg-rise px-3.5 py-3">
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-2"
            style={{ animationDelay: `${dot * 140}ms` }}
          />
        ))}
        <span className="sr-only">Strategist is checking the brief…</span>
      </div>
    </motion.article>
  )
}

function optimisticMessage(content: string, conversationId: number): ChatMessage {
  const now = new Date().toISOString()
  return {
    id: -Date.now(),
    conversation_id: conversationId,
    role: 'user',
    content,
    action: null,
    created_at: now,
    updated_at: now,
  }
}

function campaignFromPath(pathname: string): number | null {
  const matched = pathname.match(/^\/campaigns\/(\d+)(?:\/|$)/)
  return matched ? Number(matched[1]) : null
}

function demoReplies(status?: Campaign['status']) {
  if (!status) {
    return ['Create a complete NailIt Merdeka campaign for luxury-minded Malaysian shoppers.']
  }
  if (status === 'draft') return ['Plan this campaign']
  if (status === 'pending_plan_approval') return ['Open Image console for concept approval']
  if (status === 'generating') return ['Continue image generation']
  if (status === 'pending_asset_review') return ['Open Image console for asset approval']
  if (status === 'ready_to_publish') return ['Generate the campaign video', 'Open cinematic cut demo', 'Open Publish']
  return ['Open Publish']
}

function demoNextStep(status?: Campaign['status']) {
  if (status === 'pending_plan_approval') return 'Approve a concept in Image Studio, then I will unlock image generation.'
  if (status === 'pending_asset_review') return 'Approve the image assets you want to keep. Video generation unlocks after the asset gate closes.'
  if (status === 'ready_to_publish') return 'Images are approved. Generate the campaign video next, or open Publish if you are showing image ads only.'
  return 'I will keep the walkthrough at the next safe stage; approvals always stay with you.'
}

function handoffMessage(stage: NonNullable<import('@/api/types').ChatSendResult['authorized']>) {
  return {
    calendar: 'Opening your calendar proposal.',
    plan: 'Opening Image Studio to monitor the scripted plan.',
    generate: 'Opening Image Studio to monitor the scripted creative crew.',
    render: 'Opening Image Studio to reuse the saved asset library.',
    image: 'Opening Image Studio at the approval gate.',
    video: 'Opening Video Studio for the campaign cut.',
    cinematic: 'Opening the seeded cinematic cut demo.',
    publish: 'Opening the publish-ready campaign package.',
  }[stage]
}

function stageLabel(status: Campaign['status']) {
  return status.replaceAll('_', ' ')
}

function threadLabel(thread: Conversation) {
  if (thread.campaign?.name) return thread.campaign.name
  if (thread.title !== 'New strategy') return thread.title
  const firstRequest = thread.messages.find((message) => message.role === 'user')
  if (firstRequest) return firstRequest.content.split(/\s+/).slice(0, 7).join(' ') + (firstRequest.content.split(/\s+/).length > 7 ? '…' : '')
  return `Untitled strategy #${thread.id}`
}
