import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { request, type Job } from '@/api/client'

type Call = { attempts: number; estimated_cost_usd: number | null; id: number; model: string; schema: string; status: string; input_tokens: number | null; output_tokens: number | null; duration_ms: number; prompt_version: string; request_id: string | null; evidence: { chunk_id: string; source: string; text?: string }[] }
export function JobsPanel() {
  const actor = useAuth()
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [detail, setDetail] = useState<(Job & { calls: Call[] }) | null>(null)
  const load = useCallback(async () => {
    try { setJobs(await request<Job[]>('/jobs?limit=30')); setError('') } catch (failure) { setError((failure as Error).message) }
  }, [])
  useEffect(() => {
    void request<Job[]>('/jobs?limit=30').then(setJobs).catch(failure => setError(failure.message))
    const timer = window.setInterval(() => { if (!document.hidden) void load() }, 4000)
    return () => window.clearInterval(timer)
  }, [load])
  async function act(id: string, operation: 'cancel' | 'retry') {
    setBusy(true)
    try { await request(`/jobs/${id}/${operation}`, { method: 'POST' }); await load() } catch (failure) { setError((failure as Error).message) } finally { setBusy(false) }
  }
  return <section className="mt-7 rounded-xl border border-edge bg-rise p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-medium">Saved AI jobs</h2><button className="workspace-secondary" onClick={() => void load()}>Refresh jobs</button></div><p className="mt-2 text-sm leading-relaxed text-text-2">Jobs continue when you change pages or close the browser. Progress and completed output are saved.</p>
    {error && <p role="alert" className="mt-4 text-sm text-halt">{error}</p>}
    <ul className="mt-4 divide-y divide-edge">{jobs.map(job => <li key={job.id} className="flex flex-wrap items-start justify-between gap-4 py-4"><div className="min-w-0 flex-[1_1_18rem]"><p className="break-words text-sm font-medium">{job.path.replace(/\//g, ' › ').replace('stream', '').trim()}</p><p className="mt-1 text-xs text-text-3">{job.status} · {new Date(job.updated_at).toLocaleString()}</p>{job.error && <p className="mt-2 text-sm leading-relaxed text-halt">{job.error}</p>}</div><div className="flex flex-wrap gap-2"><button className="workspace-secondary" onClick={() => void request<Job & { calls: Call[] }>(`/jobs/${job.id}?include_usage=true`).then(setDetail).catch(failure => setError(failure.message))}>Activity & usage</button>{['owner', 'editor'].includes(actor.role) && job.status === 'queued' && <button disabled={busy} className="workspace-secondary" onClick={() => void act(job.id, 'cancel')}>Cancel queued job</button>}{['owner', 'editor'].includes(actor.role) && ['failed', 'interrupted'].includes(job.status) && <button disabled={busy} className="workspace-secondary" onClick={() => void act(job.id, 'retry')}>Retry unfinished work</button>}{job.path.startsWith('/campaigns/') && <Link className="workspace-secondary" to={`/campaigns/${job.path.split('/')[2]}`}>Open campaign</Link>}</div></li>)}</ul>
    {!jobs.length && !error && <p className="mt-4 text-sm text-text-3">No AI jobs have been submitted yet.</p>}
    {detail && <div className="mt-5 border-t border-edge pt-5"><div className="flex items-center justify-between gap-3"><h3 className="text-sm font-medium">Job activity · {detail.status}</h3><button className="workspace-secondary" onClick={() => setDetail(null)}>Close activity</button></div><ol className="mt-3 max-h-64 space-y-2 overflow-y-auto text-xs leading-relaxed text-text-2">{detail.events.map((event, index) => <li key={index} className="break-words">{String(event.agent)} · {String(event.phase)} — {String(event.detail)}</li>)}</ol><h3 className="mt-5 text-sm font-medium">Text-model usage</h3><p className="mt-2 text-xs leading-relaxed text-text-3">Unknown token counts remain unavailable. Image and video charges are not included.</p><ul className="mt-3 divide-y divide-edge">{detail.calls.map(call => <li key={call.id} className="py-3 text-xs leading-relaxed"><p className="break-words">{call.model} · {call.schema} · {call.status} · {(call.duration_ms / 1000).toFixed(1)}s · {call.attempts} attempt(s)</p><p className="mt-1 text-text-3">Input {call.input_tokens ?? 'unavailable'} · Output {call.output_tokens ?? 'unavailable'} · Estimated text cost {call.estimated_cost_usd === null ? 'unavailable' : '$' + call.estimated_cost_usd.toFixed(6)}</p><details className="mt-2 text-text-3"><summary>Evidence and request reference</summary><p className="mt-2 break-all">Prompt version: {call.prompt_version}<br />Request: {call.request_id ?? 'unavailable'}</p>{call.evidence.map((row, index) => <p key={index} className="mt-1 break-words">{row.source} · {row.chunk_id}{row.text && <span className="mt-1 block whitespace-pre-wrap">{row.text}</span>}</p>)}</details></li>)}</ul>{!detail.calls.length && <p className="mt-3 text-xs text-text-3">No text-model calls recorded for this job.</p>}</div>}
  </section>
}
