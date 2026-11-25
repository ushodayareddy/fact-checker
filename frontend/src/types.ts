export type VerdictLabel = 'true' | 'false' | 'misleading' | 'partly_true' | 'unverifiable'
export type Stance = 'supports' | 'refutes' | 'neutral'

export interface Language {
  code: string
  name: string
  native_name: string
  script: string
  tier: 'high' | 'medium' | 'low'
}

export interface Claim {
  id: string
  text: string
  text_en: string | null
  claim_type: string | null
}

export interface Evidence {
  id: string
  claim_id: string
  source: string
  url: string
  title: string
  snippet: string
  published: string | null
  relevance: number
}

export interface SourceScore {
  evidence_id: string
  credibility: number
  tier: string
  reasons: string[]
}

export interface StanceJudgment {
  evidence_id: string
  stance: Stance
  quote: string
  rationale: string
}

export interface Verdict {
  claim_id: string
  label: VerdictLabel
  confidence: number
  explanation: string
  citations: string[]
  caveats: string[]
}

export interface TraceEvent {
  agent: string
  status: 'started' | 'progress' | 'done' | 'error'
  message: string
  data: Record<string, unknown>
}

export interface CheckResult {
  language: Language | null
  claims: Claim[]
  evidence: Record<string, Evidence[]>
  scores: Record<string, SourceScore>
  stances: Record<string, StanceJudgment[]>
  verdicts: Verdict[]
  warnings: string[]
}
