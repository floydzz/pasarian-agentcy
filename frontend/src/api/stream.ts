export type AgentName =
  | 'planner'
  | 'copywriter'
  | 'visual_planner'
  | 'director'
  | 'renderer'
  | 'vision_qa'
  | 'system'

export type Phase = 'started' | 'finished' | 'failed'

export interface RunEvent {
  kind: 'event'
  seq: number
  agent: AgentName
  phase: Phase
  detail: string
  data: Record<string, unknown>
}

export type StreamLine =
  | RunEvent
  | ({ kind: 'result' } & Record<string, unknown>)
  | { kind: 'error'; detail: string }

/** Read a newline-delimited JSON run, handing each line over as it lands.
 *
 * The point of streaming is that the console shows an agent as busy while it is
 * busy, so lines are dispatched the moment they arrive rather than buffered
 * until the run finishes. */
export async function streamRun(
  path: string,
  onLine: (line: StreamLine) => void,
  body?: unknown,
  signal?: AbortSignal,
): Promise<void> {
  const { request, waitForJob } = await import('./client')
  const job = await request<import('./client').Job>('/jobs', {
    method: 'POST', body: JSON.stringify({ path, payload: body ?? null, request_key: crypto.randomUUID() }), signal,
  })
  const result = await waitForJob(job, update => {
    for (const event of update.events) onLine(event as unknown as RunEvent)
  }, signal)
  if (Array.isArray(result)) throw new Error('The job returned an unexpected result. Review saved progress.')
  onLine({ kind: 'result', ...result })
}
