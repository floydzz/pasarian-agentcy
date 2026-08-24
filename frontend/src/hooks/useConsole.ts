import { useCallback, useRef, useState } from 'react'
import { streamRun, type AgentName, type RunEvent, type StreamLine } from '@/api/stream'

export type AgentState = 'idle' | 'running' | 'done' | 'failed'

/** The four agents the console watches. `system` is the graph itself — it
 * narrates routing decisions and does not hold work, so it has no lane. */
export const AGENTS: { id: Exclude<AgentName, 'system'>; label: string; role: string }[] = [
  { id: 'planner', label: 'Planner', role: 'Brief → grounded concepts' },
  { id: 'copywriter', label: 'Copywriter', role: 'One variant per axis' },
  { id: 'visual_planner', label: 'Art director', role: 'Images around the copy' },
  { id: 'director', label: 'Creative director', role: 'Reviews and sends back' },
]

const IDLE: Record<AgentName, AgentState> = {
  planner: 'idle',
  copywriter: 'idle',
  visual_planner: 'idle',
  director: 'idle',
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

  const run = useCallback(
    async (
      label: string,
      path: string,
      onResult?: (result: Record<string, unknown>) => void,
    ) => {
      setRunning(label)
      setError(null)
      // Agents reset per run, but the log does not: the point of the log is
      // that you can scroll back through everything the crew has done today.
      setAgents(IDLE)

      const finish = (line: StreamLine) => {
        if (line.kind === 'event') {
          // Stamped out here, not inside the updater: two events arriving in
          // one tick would both read the ref after both increments and end up
          // sharing a key.
          counter.current += 1
          const stamped: LogLine = { ...line, seq: counter.current, at: clock() }
          setLog((lines) => [...lines, stamped])
          setAgents((current) => ({
            ...current,
            [line.agent]: stateFor(line.phase),
          }))
        } else if (line.kind === 'error') {
          setError(line.detail)
        } else {
          onResult?.(line)
        }
      }

      try {
        await streamRun(path, finish)
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

function stateFor(phase: RunEvent['phase']): AgentState {
  if (phase === 'started') return 'running'
  return phase === 'failed' ? 'failed' : 'done'
}

function clock(): string {
  return new Date().toLocaleTimeString('en-GB', { hour12: false })
}
