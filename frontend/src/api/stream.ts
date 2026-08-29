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
): Promise<void> {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    // Refusals happen before the stream opens — a 409 gate check, say — so
    // they arrive as an ordinary body.
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* keep the generic message */
    }
    onLine({ kind: 'error', detail })
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onLine({ kind: 'error', detail: 'This browser cannot read a streamed run.' })
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // A chunk can split a line, so only whole lines are dispatched and the
    // remainder stays in the buffer for the next read.
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) dispatch(line, onLine)
  }
  dispatch(buffer, onLine)
}

function dispatch(line: string, onLine: (line: StreamLine) => void) {
  if (!line.trim()) return
  try {
    onLine(JSON.parse(line) as StreamLine)
  } catch {
    /* a partial line at the very end of a dropped connection */
  }
}
