# Indian-language Fact Checker

A multi-agent pipeline that checks claims in any of India's 22 scheduled languages (plus English). It retrieves evidence, validates sources, verifies the claim against each source, and explains the verdict in the user's language. All LLM work runs locally through Ollama.

```
input (text or URL)
  → Claim Extractor → Language ID → Claim Router
  → Evidence Retriever (parallel sources, routed by claim type)
  → Source Validator → Claim Verifier → Verdict Synthesizer
```

## Setup

```bash
# 1. Ollama + models (verify the tags exist in the Ollama library; override with FC_* env vars)
brew install ollama
ollama serve &
ollama pull qwen3:14b      # reasoning / generation (FC_REASONING_MODEL)
ollama pull bge-m3         # multilingual embeddings (FC_EMBEDDING_MODEL)

# 2. Backend (Python 3.12 via uv)
cd backend
uv sync --python 3.12
uv run uvicorn app.main:app --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev                # http://localhost:5173, proxies /api to :8000
```

Optional keys (set as `FC_*` env vars or in `backend/.env`); adapters without a key skip themselves or fall back:

| Variable | Effect |
|---|---|
| `FC_GOOGLE_FACTCHECK_API_KEY` | Use Google Fact Check Tools instead of domain-restricted search for existing fact-checks |
| `FC_TAVILY_API_KEY` / `FC_SEARXNG_URL` | Better web search than the default DuckDuckGo HTML scrape |

## How verdicts are decided

The LLM never picks the verdict label. Each evidence item gets a stance (supports / refutes / neutral) that must be backed by a quote copied verbatim from the evidence; otherwise it is downgraded to neutral. Labels and confidence are then computed from credibility-weighted stances in `backend/app/agents/synthesizer.py` (`aggregate`), with thresholds as named constants. The LLM only writes the explanation.

- Source credibility comes from `backend/app/data/source_tiers.yaml` plus recency and relevance adjustments.
- Confidence is capped by language tier (high 0.95, medium 0.8, low 0.6).
- No credible evidence → `unverifiable`, never a guess.

## Known limitations

- **Low-resource languages** (Maithili, Konkani, Dogri, Bodo, Kashmiri, Manipuri, Sindhi, Santali) have weak model and retrieval support. The UI warns and confidence is capped. Language ID only distinguishes languages that share a script (e.g. Hindi/Marathi/Nepali) among those `lingua` supports; others default to the script's main language.
- **Translation** currently relies on the claim-extraction LLM's English rendering. IndicTrans2 integration (planned) would be more reliable for low-resource languages.
- **Government and fact-check sources** use domain-restricted web search, not first-party APIs. `data.gov.in` dataset lookup and Wikidata property/SPARQL queries are not implemented, so numeric claims depend on finding the figure in page text.
- The domain credibility registry is a hand-written prior; review the IFCN list against current signatories.
- Thresholds in `aggregate` are untuned. There is no labelled evaluation set yet (`backend/eval/` is empty); accuracy is unmeasured.
- Verified only with mocked HTTP and mocked LLM. A live run against Ollama and real sources has not been done.

## Tests

```bash
cd backend && uv run pytest
cd frontend && npm run build   # type-check
```

## Evaluation (50 labelled cases, needs the live app)

`backend/eval/cases.yaml` holds 50 claims across 13 languages (true, false, health myths, and 3 inputs with nothing checkable). Start Ollama and the backend, then:

```bash
cd backend
uv run python -m eval.run_eval                        # all 50
uv run python -m eval.run_eval --limit 5              # quick smoke run
uv run python -m eval.run_eval --lang hi --lang ta    # some languages
uv run python -m eval.run_eval --id en-01 --id hi-06  # specific cases
```

Each case scores `pass`, `abstain` (said unverifiable: unhelpful, not wrong), `fail` (confidently wrong), or `error`. The report breaks accuracy down by language and category and is saved to `backend/eval/results/` as timestamped `.json` and `.md` files, plus `latest.json` / `latest.md`. The results folder is git-ignored; share a report by pasting `latest.md`. The first full run on a local model takes a long time (roughly a minute or more per case).

**Windows:** `eval.bat` starts Ollama and the backend if needed, runs the eval, and opens `latest.md`. It passes arguments through (`eval.bat --limit 5`).

Caveats: the non-English claims were translated by an AI and have not been reviewed by native speakers; review them before blaming the model for a failure. `mr-03` is a known language-ID gap (the detector scores a Marathi sentence as Hindi).
