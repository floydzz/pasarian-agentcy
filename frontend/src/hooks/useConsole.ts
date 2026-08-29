import { useCallback, useRef, useState } from 'react'
import { streamRun, type AgentName, type RunEvent, type StreamLine } from '@/api/stream'

export type AgentState = 'idle' | 'running' | 'done' | 'failed'

/** The agents the console watches, in pipeline order. `system` is the graph
 * itself — it narrates routing decisions and does not hold work, so it has no
 * lane. The last two belong to the studio rather than the crew, but they hold
 * work exactly the same way, so they get the same lane. */
export const AGENTS: { id: Exclude<AgentName, 'system'>; label: string; role: string }[] = [
  { id: 'planner', label: 'Planner', role: 'Brief → grounded concepts' },
  { id: 'copywriter', label: 'Copywriter', role: 'One variant per axis' },
  { id: 'visual_planner', label: 'Art director', role: 'Images around the copy' },
  { id: 'director', label: 'Creative director', role: 'Reviews and sends back' },
  { id: 'renderer', label: 'Renderer', role: 'Background, then the type on it' },
  { id: 'vision_qa', label: 'Quality checker', role: 'Looks before you do' },
]

/** The video crew: four of the same agents, doing the video's version of the
 * job. They are the same agents on purpose — a person who has watched the art
 * director work on an image already knows what the storyboard designer is. */
export const VIDEO_AGENTS: { id: Exclude<AgentName, 'system'>; label: string; role: string }[] = [
  { id: 'planner', label: 'Video strategist', role: 'Reads the brief and checks the story' },
  { id: 'visual_planner', label: 'Storyboard designer', role: 'Maps every beat to a screen' },
  { id: 'renderer', label: 'Motion renderer', role: 'Draws the scenes and encodes them' },
  { id: 'vision_qa', label: 'Quality checker', role: 'Looks at the cut before you do' },
]

const IDLE: Record<AgentName, AgentState> = {
  planner: 'idle',
  copywriter: 'idle',
  visual_planner: 'idle',
  director: 'idle',
  renderer: 'idle',
  vision_qa: 'idle',
  system: 'idle',
}

export interface LogLine extends RunEvent {
  at: string
}

export function useConsole() {
  const [log, setLog] = useState<LogLine[]>([])
  const [agents, setAgents] = useState<Record<AgentName, AgentState>>(IDLE)
  const [running, setRunning] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const counter = useRef(0)
  // How many of each agent are working right now, and which ones failed at
  // some point in this run. Counted rather than inferred from the last event
  // seen: the backend generates concepts in parallel and renders variants in
  // parallel, so three copywriters really are running at once and the first of
  // them to finish must not put the lane out while the other two are still
  // going. `failed` is sticky for the run — one variant failing is the thing
  // worth seeing, and a later success should not quietly cover it up.
  const inflight = useRef<Partial<Record<AgentName, number>>>({})
  const failed = useRef<Set<AgentName>>(new Set())

  const run = useCallback(
    async (
      label: string,
      path: string,
      onResult?: (result: Record<string, unknown>) => void,
      body?: unknown,
    ) => {
      setRunning(label)
      setError(null)
      // Agents reset per run, but the log does not: the point of the log is
      // that you can scroll back through everything the crew has done today.
      setAgents(IDLE)
      inflight.current = {}
      failed.current = new Set()

      const finish = (line: StreamLine) => {
        if (line.kind === 'event') {
          // Stamped out here, not inside the updater: two events arriving in
          // one tick would both read the ref after both increments and end up
          // sharing a key.
          counter.current += 1
          const stamped: LogLine = { ...line, seq: counter.current, at: clock() }
          setLog((lines) => [...lines, stamped])
          const counts = inflight.current
          if (line.phase === 'started') {
            counts[line.agent] = (counts[line.agent] ?? 0) + 1
          } else {
            counts[line.agent] = Math.max(0, (counts[line.agent] ?? 1) - 1)
            if (line.phase === 'failed') failed.current.add(line.agent)
          }
          setAgents((current) => ({
            ...current,
            [line.agent]: stateFor(
              counts[line.agent] ?? 0,
              failed.current.has(line.agent),
            ),
          }))
        } else if (line.kind === 'error') {
          setError(line.detail)
        } else {
          onResult?.(line)
        }
      }

      try {
        await streamRun(path, finish, body)
      } catch (thrown) {
        setError(thrown instanceof Error ? thrown.message : 'The run was cut off.')
      } finally {
        setRunning(null)
        // Anything still marked running finished when the stream closed.
        setAgents((current) =>
          Object.fromEntries(
            Object.entries(current).map(([agent, state]) => [
              agent,
              state === 'running' ? 'done' : state,
            ]),
          ) as Record<AgentName, AgentState>,
        )
      }
    },
    [],
  )

  return { log, agents, running, error, run, clearError: () => setError(null) }
}

/** What a lane shows, given how many of that agent are still working and
 * whether any of them failed during this run. */
function stateFor(working: number, everFailed: boolean): AgentState {
  if (working > 0) return 'running'
  return everFailed ? 'failed' : 'done'
}

function clock(): string {
  return new Date().toLocaleTimeString('en-GB', { hour12: false })
}
