import type { TraceEvent } from '../types'

const AGENTS: { id: string; label: string }[] = [
  { id: 'claim_extractor', label: 'Extract claims' },
  { id: 'language_id', label: 'Detect language' },
  { id: 'claim_router', label: 'Route claims' },
  { id: 'evidence_retriever', label: 'Retrieve evidence' },
  { id: 'source_validator', label: 'Validate sources' },
  { id: 'claim_verifier', label: 'Verify claims' },
  { id: 'verdict_synthesizer', label: 'Write verdict' },
]

type Phase = 'pending' | 'running' | 'done' | 'error'

function phaseOf(agent: string, events: TraceEvent[]): Phase {
  const mine = events.filter((e) => e.agent === agent)
  if (mine.some((e) => e.status === 'done')) return 'done'
  if (mine.some((e) => e.status === 'error')) return 'error'
  return mine.length ? 'running' : 'pending'
}

const ICON: Record<Phase, string> = { pending: '○', running: '◐', done: '●', error: '▲' }

export function AgentTrace({ events, active }: { events: TraceEvent[]; active: boolean }) {
  return (
    <ol className="trace" aria-label="Agent progress" aria-live="polite">
      {AGENTS.map(({ id, label }) => {
        const phase = phaseOf(id, events)
        const last = [...events].reverse().find((e) => e.agent === id && e.message)
        return (
          <li key={id} className={`trace-step ${phase}${phase === 'running' && active ? ' pulse' : ''}`}>
            <span className="trace-icon" aria-hidden="true">{ICON[phase]}</span>
            <span className="trace-label">{label}</span>
            <span className="sr-only"> {phase}</span>
            {last && <span className="trace-msg">{last.message}</span>}
          </li>
        )
      })}
    </ol>
  )
}
