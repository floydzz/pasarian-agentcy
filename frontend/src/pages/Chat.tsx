import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import { streamRun, type StreamLine } from '@/api/stream'
import type { Campaign, ChatMessage, Conversation } from '@/api/types'
import { cn } from '@/lib/utils'

type RunState = {
  stage: 'plan' | 'generate'
  lines: string[]
  failed: boolean
}

/** The strategist's room.
 *
 * A thread is just conversation until the agent has a usable brief. Then the
 * server adopts the created campaign into it, and this view can start the
 * pipeline's unchanged streaming routes. There are intentionally no approval
 * controls here: gates belong to the campaign workspace, where the work can
 * actually be reviewed.
 */
export function Chat() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Conversation[]>([])
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [pendingMessage, setPendingMessage] = useState<ChatMessage | null>(null)
  const [run, setRun] = useState<RunState | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const refreshThreads = useCallback(async () => {
    const listed = await api.listConversations()
    setThreads(listed)
    return listed
  }, [])

  const open = useCallback(async (id: number) => {
    try {
      setConversation(await api.getConversation(id))
    } catch (error) {
      toast.error((error as ApiError).message)
    }
  }, [])

  useEffect(() => {
    refreshThreads()
      .then((listed) => {
        if (listed[0]) return open(listed[0].id)
        return undefined
      })
      .catch((error: ApiError) => toast.error(error.message))
      .finally(() => setLoading(false))
  }, [open, refreshThreads])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [conversation?.messages.length, pendingMessage, run, sending])

  const replaceThread = useCallback((next: Conversation) => {
    setThreads((current) => {
      const rest = current.filter((thread) => thread.id !== next.id)
      return [next, ...rest].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      )
    })
    setConversation(next)
  }, [])

  async function createThread() {
    try {
      const created = await api.createConversation()
      replaceThread(created)
      setDraft('')
      return created
    } catch (error) {
      toast.error((error as ApiError).message)
      return null
    }
  }

  async function removeThread(thread: Conversation) {
    if (!window.confirm(`Delete “${thread.title}”? Its messages cannot be recovered.`)) return
    try {
      await api.deleteConversation(thread.id)
      const listed = await refreshThreads()
      const next = listed.find((item) => item.id !== thread.id) ?? null
      setConversation(next)
      if (next) await open(next.id)
    } catch (error) {
      toast.error((error as ApiError).message)
    }
  }

  async function renameThread(thread: Conversation) {
    const title = window.prompt('Thread name', thread.title)?.trim()
    if (!title || title === thread.title) return
    try {
      replaceThread(await api.updateConversation(thread.id, { title }))
    } catch (error) {
      toast.error((error as ApiError).message)
    }
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    const content = draft.trim()
    if (!content || sending) return
    setSending(true)
    setDraft('')
    setPendingMessage(optimisticMessage(content, conversation?.id ?? -1))
    try {
      let active = conversation
      if (!active) active = await createThread()
      if (!active) {
        setPendingMessage(null)
        return
      }

      const result = await api.sendConversationMessage(active.id, content)
      const refreshed = await api.getConversation(active.id)
      setPendingMessage(null)
      replaceThread(refreshed)
      if (result.authorized && result.campaign) {
        await startRun(active.id, result.campaign, result.authorized)
      }
    } catch (error) {
      setPendingMessage(null)
      toast.error((error as ApiError).message)
      setDraft(content)
    } finally {
      setSending(false)
    }
  }

  const visibleMessages = pendingMessage
    ? [...(conversation?.messages ?? []), pendingMessage]
    : (conversation?.messages ?? [])

  async function startRun(
    conversationId: number,
    campaign: Campaign,
    stage: 'plan' | 'generate',
  ) {
    const path = `/campaigns/${campaign.id}/${stage}/stream`
    let failed = false
    setRun({ stage, lines: [], failed: false })
    await streamRun(path, (line: StreamLine) => {
      if (line.kind === 'event') {
        setRun((current) =>
          current
            ? { ...current, lines: [...current.lines, line.detail] }
            : current,
        )
      } else if (line.kind === 'error') {
        failed = true
        setRun((current) =>
          current
            ? { ...current, failed: true, lines: [...current.lines, line.detail] }
            : current,
        )
      } else {
        setRun((current) =>
          current
            ? { ...current, lines: [...current.lines, 'Run complete.'] }
            : current,
        )
      }
    })
    const refreshed = await api.getConversation(conversationId)
    replaceThread(refreshed)
    if (failed) toast.error(`${stage === 'plan' ? 'Planning' : 'Generation'} could not finish.`)
    else toast.success(stage === 'plan' ? 'Concepts are ready for review.' : 'Creative generation is complete.')
  }

  function submitOnShortcut(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void submit()
  }

  return (
    <div className="flex h-full min-w-0 bg-void">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-edge bg-[rgba(233,238,247,0.018)] lg:flex">
        <div className="flex items-center justify-between border-b border-edge px-5 py-5">
          <div>
            <p className="label">Strategy threads</p>
            <p className="display mt-1 text-[0.9375rem]">Marketing chat</p>
          </div>
          <button
            type="button"
            onClick={() => void createThread()}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-edge text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
            aria-label="New strategy thread"
            title="New strategy"
          >
            <span className="text-lg leading-none">+</span>
          </button>
        </div>

        <div className="quiet-scroll min-h-0 flex-1 overflow-y-auto px-2.5 py-3">
          {threads.length === 0 ? (
            <p className="px-2.5 pt-3 text-[0.8125rem] leading-relaxed text-text-3">
              Start a thread when you are ready to shape a campaign.
            </p>
          ) : (
            <ul className="space-y-1">
              {threads.map((thread) => (
                <li key={thread.id}>
                  <button
                    type="button"
                    onClick={() => void open(thread.id)}
                    className={cn(
                      'group w-full rounded-lg px-3 py-3 text-left transition-colors',
                      conversation?.id === thread.id
                        ? 'bg-[rgba(233,238,247,0.08)]'
                        : 'hover:bg-[rgba(233,238,247,0.035)]',
                    )}
                  >
                    <span className="flex items-start justify-between gap-2">
                      <span className="line-clamp-2 text-[0.8125rem] leading-snug text-foreground">
                        {thread.title}
                      </span>
                      <span className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation()
                            void renameThread(thread)
                          }}
                          className="text-text-3 hover:text-foreground"
                          title="Rename"
                        >
                          ···
                        </span>
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation()
                            void removeThread(thread)
                          }}
                          className="text-text-3 hover:text-flag"
                          title="Delete"
                        >
                          ×
                        </span>
                      </span>
                    </span>
                    <span className="data mt-2 block truncate text-text-3">
                      {thread.campaign ? stageLabel(thread.campaign.status) : 'briefing'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-edge px-6 py-4 sm:px-9">
          <div className="min-w-0">
            <p className="label">Marketing strategist</p>
            <h1 className="display mt-1 truncate text-[1rem]">
              {conversation?.title ?? 'New strategy'}
            </h1>
          </div>
          {conversation?.campaign && (
            <button
              type="button"
              onClick={() => navigate(`/campaigns/${conversation.campaign?.id}`)}
              className="max-w-[13rem] rounded-full border border-edge px-3 py-1.5 text-left transition-colors hover:border-edge-strong"
            >
              <span className="data block truncate text-text-2">{conversation.campaign.name}</span>
              <span className="data mt-0.5 block text-text-3">{stageLabel(conversation.campaign.status)}</span>
            </button>
          )}
        </header>

        <div className="quiet-scroll min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-6 py-10 sm:px-10 sm:py-14">
            {loading ? (
              <p className="text-sm text-text-3">Loading strategy threads…</p>
            ) : visibleMessages.length === 0 ? (
              <Welcome onStart={() => void createThread()} />
            ) : (
              <div className="space-y-5">
                {visibleMessages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
                {sending && <Thinking />}
                {run && <RunCard run={run} />}
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        <form onSubmit={submit} className="shrink-0 border-t border-edge bg-[rgba(5,7,11,0.88)] px-6 py-4 backdrop-blur sm:px-9 sm:py-5">
          <div className="mx-auto flex max-w-3xl items-end gap-3 rounded-xl border border-edge bg-[rgba(233,238,247,0.035)] p-2 transition-colors focus-within:border-edge-strong">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={submitOnShortcut}
              rows={2}
              disabled={sending}
              placeholder="Describe the campaign you need, or ask what to do next…"
              className="min-h-[3rem] flex-1 resize-none bg-transparent px-2.5 py-2 text-[0.875rem] leading-relaxed text-foreground outline-none placeholder:text-text-3 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!draft.trim() || sending}
              className="display mb-0.5 rounded-lg bg-foreground px-4 py-2 text-[0.75rem] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-30"
            >
              {sending ? 'Thinking' : 'Send'}
            </button>
          </div>
          <p className="mx-auto mt-2 max-w-3xl px-2.5 text-[0.6875rem] text-text-3">
            ⌘/Ctrl + Enter to send · concept and asset decisions always stay with you.
          </p>
        </form>
      </section>
    </div>
  )
}

function Welcome({ onStart }: { onStart: () => void }) {
  return (
    <div className="max-w-xl pt-8">
      <p className="label">The front door to the campaign machine</p>
      <h2 className="display mt-3 text-3xl leading-tight sm:text-4xl">Start with the outcome, not the form.</h2>
      <p className="mt-5 text-[1rem] leading-relaxed text-text-2">
        Tell the strategist what you are promoting, who needs to care, and what a useful result looks like. It will ground the brief in your brand and trend context, then stop at every human gate.
      </p>
      <button
        type="button"
        onClick={onStart}
        className="display mt-8 rounded-full border border-edge px-4 py-2 text-[0.75rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground"
      >
        New strategy thread
      </button>
    </div>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'system') {
    return (
      <div className="mx-auto max-w-xl border-l border-halt/70 py-1 pl-3 text-[0.8125rem] leading-relaxed text-text-2">
        {message.content}
      </div>
    )
  }
  const user = message.role === 'user'
  return (
    <article className={cn('flex', user ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[88%] rounded-xl px-4 py-3 sm:max-w-[78%]',
          user
            ? 'bg-[rgba(233,238,247,0.12)] text-foreground'
            : 'border border-edge bg-[rgba(233,238,247,0.035)] text-text-2',
        )}
      >
        <div className="mb-1.5 flex items-center gap-2">
          <span className="data text-text-3">{user ? 'you' : 'strategist'}</span>
          {message.action && (
            <span className="data rounded-full border border-edge px-1.5 py-0.5 text-text-3">
              {actionLabel(message.action)}
            </span>
          )}
        </div>
        <p className="whitespace-pre-wrap text-[0.875rem] leading-relaxed">{message.content}</p>
      </div>
    </article>
  )
}

function Thinking() {
  return (
    <article className="flex justify-start" aria-label="Strategist is typing">
      <div className="flex items-center gap-1.5 rounded-xl border border-edge bg-[rgba(233,238,247,0.035)] px-3.5 py-3">
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-2"
            style={{ animationDelay: `${dot * 140}ms` }}
          />
        ))}
        <span className="sr-only">Strategist is reading the brief and context…</span>
      </div>
    </article>
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

function RunCard({ run }: { run: RunState }) {
  return (
    <article className={cn('rounded-xl border p-4', run.failed ? 'border-flag/50' : 'border-edge bg-[rgba(233,238,247,0.025)]')}>
      <div className="flex items-center justify-between gap-3">
        <p className="display text-[0.8125rem]">
          {run.stage === 'plan' ? 'Planning concepts' : 'Generating creatives'}
        </p>
        <span className={cn('data', run.failed ? 'text-flag' : 'text-text-3')}>
          {run.failed ? 'needs attention' : 'machine run'}
        </span>
      </div>
      <div className="mt-3 space-y-1.5 border-l border-edge pl-3">
        {run.lines.slice(-5).map((line, index) => (
          <p key={`${line}-${index}`} className="text-[0.75rem] leading-relaxed text-text-3">{line}</p>
        ))}
        {run.lines.length === 0 && <p className="text-[0.75rem] text-text-3">Opening the pipeline…</p>}
      </div>
    </article>
  )
}

function stageLabel(status: Campaign['status']) {
  return status.replaceAll('_', ' ')
}

function actionLabel(action: NonNullable<ChatMessage['action']>) {
  return action.replaceAll('_', ' ')
}
