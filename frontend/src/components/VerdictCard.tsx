import type { Claim, Evidence, SourceScore, StanceJudgment, Verdict, VerdictLabel } from '../types'

const LABEL: Record<VerdictLabel, string> = {
  true: 'True',
  false: 'False',
  misleading: 'Misleading',
  partly_true: 'Partly true',
  unverifiable: 'Unverifiable',
}

const TIER_NAME: Record<string, string> = {
  government: 'Government',
  ifcn_factchecker: 'Fact-checker',
  reference: 'Reference',
  major_outlet: 'News outlet',
  social_or_user_generated: 'Social / user-generated',
  unknown: 'Unknown source',
}

const STANCE_NAME = { supports: 'Supports', refutes: 'Refutes', neutral: 'Neutral' } as const

interface Props {
  claim: Claim
  verdict: Verdict | undefined
  evidence: Evidence[]
  scores: Record<string, SourceScore>
  stances: StanceJudgment[]
}

export function VerdictCard({ claim, verdict, evidence, scores, stances }: Props) {
  const stanceOf = new Map(stances.map((s) => [s.evidence_id, s]))
  const cited = new Set(verdict?.citations ?? [])
  // Cited evidence first, then by credibility.
  const sorted = [...evidence].sort(
    (a, b) =>
      Number(cited.has(b.id)) - Number(cited.has(a.id)) ||
      (scores[b.id]?.credibility ?? 0) - (scores[a.id]?.credibility ?? 0),
  )

  return (
    <article className="card">
      <header>
        <p className="claim-text" lang="und">{claim.text}</p>
        {claim.text_en && claim.text_en !== claim.text && <p className="claim-en">{claim.text_en}</p>}
        {claim.claim_type && <span className="chip">{claim.claim_type}</span>}
      </header>

      {verdict && (
        <section className={`verdict v-${verdict.label}`} aria-label="Verdict">
          <div className="verdict-head">
            <strong className="verdict-label">{LABEL[verdict.label]}</strong>
            {verdict.label !== 'unverifiable' && (
              <span className="confidence" title="Confidence is computed from source credibility and agreement">
                {Math.round(verdict.confidence * 100)}% confidence
              </span>
            )}
          </div>
          <p className="explanation" lang="und">{verdict.explanation}</p>
          {verdict.caveats.length > 0 && (
            <ul className="caveats">
              {verdict.caveats.map((c) => <li key={c}>{c}</li>)}
            </ul>
          )}
        </section>
      )}

      <section aria-label="Evidence">
        <h3>Evidence ({evidence.length})</h3>
        {evidence.length === 0 && <p className="muted">No evidence was found for this claim.</p>}
        <ul className="evidence">
          {sorted.map((e) => {
            const score = scores[e.id]
            const stance = stanceOf.get(e.id)
            return (
              <li key={e.id} className={cited.has(e.id) ? 'cited' : ''}>
                <div className="ev-top">
                  {stance && <span className={`stance s-${stance.stance}`}>{STANCE_NAME[stance.stance]}</span>}
                  <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title || e.url}</a>
                </div>
                <p className="ev-snippet" lang="und">{e.snippet.length > 280 ? e.snippet.slice(0, 280) + '…' : e.snippet}</p>
                {stance?.quote && <blockquote lang="und">“{stance.quote}”</blockquote>}
                <div className="ev-meta">
                  {score && (
                    <span title={score.reasons.join('\n')}>
                      {TIER_NAME[score.tier] ?? score.tier} · credibility {Math.round(score.credibility * 100)}%
                    </span>
                  )}
                  {e.published && <span>{e.published}</span>}
                  <span>via {e.source}</span>
                </div>
              </li>
            )
          })}
        </ul>
      </section>
    </article>
  )
}
