import { useCallback, useEffect, useRef, useState } from 'react'
import { checkClaim, getHealth, type HealthStatus } from './api'
import { AgentTrace } from './components/AgentTrace'
import { VerdictCard } from './components/VerdictCard'
import type { CheckResult, TraceEvent } from './types'
import './App.css'

const EXAMPLES = [
  'भारत की राजधानी दिल्ली है।',
  'தமிழ்நாட்டின் தலைநகரம் சென்னை.',
  'গরম জল খেলে ক্যান্সার সেরে যায়।',
]

export default function App() {
  const [input, setInput] = useState('')
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [result, setResult] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [healthErr, setHealthErr] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealthErr(true))
    return () => abortRef.current?.abort()
  }, [])

  const submit = useCallback(async () => {
    const text = input.trim()
    if (!text || running) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setRunning(true)
    setEvents([])
    setResult(null)
    setError(null)
    await checkClaim(
      text,
      {
        onTrace: (e) => setEvents((prev) => [...prev, e]),
        onResult: setResult,
        onError: setError,
      },
      ctrl.signal,
    )
    if (abortRef.current === ctrl) setRunning(false)
  }, [input, running])

  const cancel = () => {
    abortRef.current?.abort()
    setRunning(false)
  }

  const lang = result?.language

  return (
    <main className="app">
      <header className="app-header">
        <h1>Fact Check</h1>
        <p className="muted">Check claims in any of India's 22 scheduled languages, or paste an article link.</p>
      </header>

      {healthErr && (
        <div className="banner banner-error" role="alert">
          Backend is not reachable. Start it with <code>uv run uvicorn app.main:app</code> in <code>backend/</code>.
        </div>
      )}
      {health && !health.ok && (
        <div className="banner banner-warn" role="alert">
          {!health.ollama
            ? <>Ollama is not running. Start it with <code>ollama serve</code>.</>
            : <>Missing Ollama models: {health.missing_models.map((m) => <code key={m}>ollama pull {m}</code>)}</>}
        </div>
      )}

      <form className="input-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <label htmlFor="claim-input" className="sr-only">Claim or article URL</label>
        <textarea
          id="claim-input"
          lang="und"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit() }}
          placeholder="Paste a claim in any Indian language, or an article URL…"
          rows={4}
          maxLength={10000}
        />
        <div className="actions">
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button type="button" key={ex} className="link" onClick={() => setInput(ex)} lang="und">{ex}</button>
            ))}
          </div>
          {running
            ? <button type="button" onClick={cancel}>Cancel</button>
            : <button type="submit" className="primary" disabled={!input.trim()}>Check</button>}
        </div>
      </form>

      {(running || events.length > 0) && <AgentTrace events={events} active={running} />}

      {error && <div className="banner banner-error" role="alert">{error}</div>}

      {lang?.tier === 'low' && (
        <div className="banner banner-warn" role="status">
          {lang.name} is a low-resource language for local AI models. Results are less reliable and confidence is capped.
        </div>
      )}
      {result?.warnings.filter((w) => !w.includes('low-resource')).map((w) => (
        <div key={w} className="banner banner-info" role="status">{w}</div>
      ))}

      {result && (
        <section aria-label="Results">
          {lang && <p className="muted">Detected language: {lang.name} ({lang.native_name})</p>}
          {result.claims.length === 0 && <p>No checkable factual claims were found in this input.</p>}
          {result.claims.map((c) => (
            <VerdictCard
              key={c.id}
              claim={c}
              verdict={result.verdicts.find((v) => v.claim_id === c.id)}
              evidence={result.evidence[c.id] ?? []}
              scores={result.scores}
              stances={result.stances[c.id] ?? []}
            />
          ))}
        </section>
      )}
    </main>
  )
}
