import type { CheckResult, TraceEvent } from './types'

export interface HealthStatus {
  ok: boolean
  ollama: boolean
  missing_models: string[]
}

export async function getHealth(): Promise<HealthStatus> {
  const r = await fetch('/api/health')
  if (!r.ok) throw new Error(`Backend returned ${r.status}`)
  return r.json()
}

interface Handlers {
  onTrace: (e: TraceEvent) => void
  onResult: (r: CheckResult) => void
  onError: (message: string) => void
}

/** Parse one SSE block ("event: x\r\ndata: y") into its parts. */
export function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  return data.length ? { event, data: data.join('\n') } : null
}

/** POST a claim and stream the pipeline's SSE events. EventSource can't POST, so use fetch. */
export async function checkClaim(input: string, h: Handlers, signal: AbortSignal): Promise<void> {
  let resp: Response
  try {
    resp = await fetch('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
      signal,
    })
  } catch (e) {
    if (signal.aborted) return
    h.onError('Cannot reach the backend. Is it running on port 8000?')
    return
  }
  if (!resp.ok || !resp.body) {
    h.onError(resp.status === 422 ? 'Input is empty or too long (max 10,000 characters).' : `Backend error ${resp.status}`)
    return
  }

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  let finished = false
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const msg = parseSseBlock(block)
        if (!msg) continue
        const payload = JSON.parse(msg.data)
        if (msg.event === 'trace') h.onTrace(payload)
        else if (msg.event === 'result') { finished = true; h.onResult(payload) }
        else if (msg.event === 'error') { finished = true; h.onError(payload.message) }
      }
    }
  } catch (e) {
    if (signal.aborted) return
    h.onError('The connection dropped before the check finished.')
    return
  }
  if (!finished && !signal.aborted) h.onError('The check ended without a result.')
}
