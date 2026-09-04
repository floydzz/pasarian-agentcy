import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import type { Campaign, ChatMessage, Conversation } from '@/api/types'
import { cn } from '@/lib/utils'
import { DEPTH, SETTLE, STAGGER, STAGGER_CHILD } from '@/lib/motion'

/** A persistent strategist beside the work, rather than a separate room.
 *
 * The dock keeps discussion and campaign control together: when the server
 * authorizes a plan or crew run, it sends the person to Image studio with a
 * one-use intent. The studio owns the stream and is therefore the truthful
 * place to watch the agents, their graph and their gates work.
 */
export function MarketingChatDock({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const campaignId = campaignFromPath(pathname)
  const [threads, setThreads] = useState<Conversation[]>([])
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [startingNew, setStartingNew] = useState(false)
  const [pageCampaign, setPageCampaign] = useState<Campaign | null>(null)
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [pendingMessage, setPendingMessage] = useState<ChatMessage | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const refreshThreads = useCallback(async () => {
    const listed = await api.listConversations()
    setThreads(listed)
    return listed
  }, [])

  const selectForPage = useCallback(
    (listed: Conversation[]) => {
      if (campaignId !== null) {
        return listed.find((thread) => thread.campaign_id === campaignId) ?? null
      }
      if (startingNew) return null
      return listed.find((thread) => thread.id === conversation?.id) ?? listed[0] ?? null
    },
    [campaignId, conversation?.id, startingNew],
  )

  useEffect(() => {
    let current = true
    setLoading(true)
    refreshThreads()
      .then((listed) => {
        if (current) setConversation(selectForPage(listed))
      })
      .catch((error: ApiError) => toast.error(error.message))
      .finally(() => current && setLoading(false))
    return () => {
      current = false
    }
  }, [refreshThreads, selectForPage])

  useEffect(() => {
    if (campaignId === null) {
      setPageCampaign(null)
      return
    }
    let current = true
    api
      .getCampaign(campaignId)
      .then((campaign) => current && setPageCampaign(campaign))
      .catch((error: ApiError) => current && toast.error(error.message))
    return () => {
      current = false
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

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    const content = draft.trim()
    if (!content || sending) return

    setSending(true)
    setDraft('')
    // Render the marketer's thought at once. The persisted version from the
    // server replaces this temporary line as soon as the request finishes.
    setPendingMessage(optimisticMessage(content, conversation?.id ?? -1))
    try {
      const active = await activeThread()
      const result = await api.sendConversationMessage(active.id, content)
      const refreshed = await api.getConversation(active.id)
      setPendingMessage(null)
      replaceThread(refreshed)

      if (result.authorized && result.campaign) {
        // The server has already rechecked campaign state and approvals. The
        // query is a short-lived UI handoff, not an authority to run anything.
        navigate(`/campaigns/${result.campaign.id}/image?run=${result.authorized}`)
        toast.success(
          result.authorized === 'plan'
            ? 'Opening Image studio to monitor planning.'
            : 'Opening Image studio to monitor the creative crew.',
        )
      }
    } catch (error) {
      setPendingMessage(null)
      toast.error((error as ApiError).message)
      setDraft(content)
    } finally {
      setSending(false)
    }
  }

  function submitOnShortcut(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void submit()
  }

  const title = pageCampaign?.name ?? conversation?.campaign?.name ?? 'Marketing strategist'
  const status = pageCampaign?.status ?? conversation?.campaign?.status
  const selectableThreads = threads.filter(
    (thread) => thread.campaign !== null || thread.messages.length > 0,
  )
  const visibleMessages = pendingMessage
    ? [...(conversation?.messages ?? []), pendingMessage]
    : (conversation?.messages ?? [])

  return (
    // `layoutId` is shared with the bubble in the shell, so the strategist
    // grows out of the control you pressed instead of the control vanishing
    // while a panel appears somewhere else on screen. One object, two sizes.
    <motion.aside
      layoutId="strategist"
      aria-label="Marketing strategist"
      transition={DEPTH}
      style={{ borderRadius: 16 }}
      className="fixed inset-y-3 right-3 z-50 flex w-[calc(100vw-1.5rem)] max-w-[27rem] flex-col overflow-hidden border border-edge bg-void shadow-2xl sm:inset-y-5 sm:right-5 sm:w-[26rem]"
    >
      <header className="flex shrink-0 items-start justify-between gap-3 border-b border-edge px-5 py-4">
        <div className="min-w-0">
          <p className="label">Marketing strategist</p>
          <p className="display mt-1 truncate text-[0.9375rem]">{title}</p>
          <p className="data mt-1 text-text-3">
            {status ? `Context: ${stageLabel(status)}` : 'Ask a question or start a new strategy'}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => void startThread()}
            className="data rounded-full border border-edge px-2.5 py-1.5 text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
          >
            New
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close marketing chat"
            className="flex h-7 w-7 items-center justify-center rounded-full border border-edge text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
          >
            ×
          </button>
        </div>
      </header>

      {conversation && selectableThreads.length > 1 && (
        <label className="flex shrink-0 items-center gap-2 border-b border-edge px-5 py-2.5">
          <span className="data shrink-0 text-text-3">Thread</span>
          <select
            value={conversation?.id ?? ''}
            onChange={(event) => {
              const next = selectableThreads.find((thread) => thread.id === Number(event.target.value))
              if (next) {
                setStartingNew(false)
                setConversation(next)
              }
            }}
            className="min-w-0 flex-1 bg-transparent text-[0.75rem] text-text-2 outline-none"
          >
            {selectableThreads.map((thread) => (
              <option key={thread.id} value={thread.id} className="bg-void">
                {threadLabel(thread)}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="quiet-scroll min-h-0 flex-1 overflow-y-auto px-4 py-5">
        {loading ? (
          <p className="px-1 text-sm text-text-3">Loading strategy context…</p>
        ) : visibleMessages.length === 0 ? (
          <div className="px-1 pt-2">
            <p className="label">Always beside the work</p>
            <p className="mt-3 text-[0.875rem] leading-relaxed text-text-2">
              Describe the outcome. I will shape the brief, check it against the brand, and take you to the right studio when there is work to monitor.
            </p>
          </div>
        ) : (
          <motion.div variants={STAGGER} initial="hidden" animate="shown" className="space-y-3">
            {visibleMessages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <AnimatePresence>{sending && <Thinking />}</AnimatePresence>
          </motion.div>
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="shrink-0 border-t border-edge bg-[rgba(5,7,11,0.88)] px-4 py-4 backdrop-blur">
        <div className="flex items-end gap-2 rounded-xl border border-edge bg-[rgba(233,238,247,0.035)] p-2 transition-colors focus-within:border-edge-strong">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={submitOnShortcut}
            rows={2}
            disabled={sending}
            placeholder="Ask what to do next…"
            className="min-h-[3rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-[0.8125rem] leading-relaxed text-foreground outline-none placeholder:text-text-3 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!draft.trim() || sending}
            className="display mb-0.5 rounded-lg bg-foreground px-3 py-2 text-[0.6875rem] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
          >
            {sending ? 'Thinking' : 'Send'}
          </button>
        </div>
        <p className="mt-2 px-1 text-[0.625rem] text-text-3">
          ⌘/Ctrl + Enter · approval decisions always stay with you.
        </p>
      </form>
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
          'max-w-[92%] rounded-xl px-3 py-2.5',
          user
            ? 'bg-[rgba(233,238,247,0.12)] text-foreground'
            : 'border border-edge bg-[rgba(233,238,247,0.035)] text-text-2',
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
        <p className="whitespace-pre-wrap text-[0.8125rem] leading-relaxed">{message.content}</p>
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
      <div className="flex items-center gap-1.5 rounded-xl border border-edge bg-[rgba(233,238,247,0.035)] px-3.5 py-3">
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
